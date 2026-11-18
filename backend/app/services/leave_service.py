import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from app.models.models import LeaveRecord, Employee, Department, User
from app.schemas.schemas import LeaveCreate, LeaveReviewRequest
from app.core.exceptions import NotFoundException, ForbiddenException, ValidationException, ConflictException
from app.services.notification_service import NotificationService

logger = logging.getLogger("attendai.leave")

class LeaveService:
    # Standard statutory annual entitlements (per calendar year)
    STANDARD_ENTITLEMENTS = {
        "annual": 20.0,
        "sick": 10.0,
        "casual": 5.0,
        "unpaid": None  # Discretionary / uncapped
    }

    ALLOWED_LEAVE_TYPES = set(STANDARD_ENTITLEMENTS.keys())

    @staticmethod
    async def format_leave_response(db: AsyncSession, leave: LeaveRecord) -> Dict[str, Any]:
        """Format a LeaveRecord entity into a complete dictionary for LeaveResponse."""
        emp = (await db.execute(select(Employee).where(Employee.id == leave.employee_id))).scalars().first()
        dept = None
        if emp and emp.department_id:
            dept = (await db.execute(select(Department).where(Department.id == emp.department_id))).scalars().first()

        reviewer_name = None
        if leave.reviewed_by:
            reviewer_user = (await db.execute(select(User).where(User.id == leave.reviewed_by))).scalars().first()
            if reviewer_user:
                rev_emp = (await db.execute(select(Employee).where(Employee.user_id == reviewer_user.id))).scalars().first()
                if rev_emp:
                    reviewer_name = f"{rev_emp.first_name} {rev_emp.last_name}"
                else:
                    reviewer_name = reviewer_user.email

        return {
            "id": leave.id,
            "organization_id": leave.organization_id,
            "employee_id": leave.employee_id,
            "leave_type": leave.leave_type,
            "start_date": leave.start_date,
            "end_date": leave.end_date,
            "days_count": leave.days_count,
            "reason": leave.reason,
            "status": leave.status,
            "reviewed_by": leave.reviewed_by,
            "reviewed_at": leave.reviewed_at,
            "resolution_notes": leave.resolution_notes,
            "created_at": leave.created_at,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else None,
            "employee_code": emp.employee_code if emp else None,
            "department_name": dept.name if dept else "General",
            "reviewer_name": reviewer_name
        }

    @classmethod
    async def calculate_leave_balances(
        cls,
        db: AsyncSession,
        organization_id: str,
        employee_id: str,
        year: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Calculate an employee's leave balance breakdown for a given calendar year.
        Returns entitlement, approved days used, pending days, and remaining available days.
        """
        emp = (await db.execute(
            select(Employee).where(
                and_(
                    Employee.id == employee_id,
                    Employee.organization_id == organization_id
                )
            )
        )).scalars().first()
        if not emp:
            raise NotFoundException("Employee profile not found")

        target_year = year or datetime.utcnow().year
        start_of_year = date(target_year, 1, 1)
        end_of_year = date(target_year, 12, 31)

        stmt = select(LeaveRecord).where(
            and_(
                LeaveRecord.organization_id == organization_id,
                LeaveRecord.employee_id == employee_id,
                LeaveRecord.start_date >= start_of_year,
                LeaveRecord.start_date <= end_of_year
            )
        )
        records = (await db.execute(stmt)).scalars().all()

        categories: Dict[str, Any] = {}
        total_entitlement = 0.0
        total_used = 0.0
        total_pending = 0.0
        total_available = 0.0
        pending_requests_count = 0

        for lt in ["annual", "sick", "casual", "unpaid"]:
            entitlement = cls.STANDARD_ENTITLEMENTS.get(lt)
            used = sum(l.days_count for l in records if l.leave_type == lt and l.status == "approved")
            pending = sum(l.days_count for l in records if l.leave_type == lt and l.status == "pending")

            if entitlement is not None:
                available = max(0.0, float(entitlement - used))
                total_entitlement += entitlement
                total_available += available
            else:
                available = None

            total_used += used
            total_pending += pending

            categories[lt] = {
                "leave_type": lt,
                "entitlement": entitlement,
                "used": float(used),
                "pending": float(pending),
                "available": available
            }

        pending_requests_count = sum(1 for l in records if l.status == "pending")

        return {
            "employee_id": emp.id,
            "employee_name": f"{emp.first_name} {emp.last_name}",
            "employee_code": emp.employee_code,
            "year": target_year,
            "categories": categories,
            "total_entitlement": float(total_entitlement),
            "total_used": float(total_used),
            "total_pending": float(total_pending),
            "total_available": float(total_available),
            "pending_requests_count": pending_requests_count
        }

    @staticmethod
    async def check_overlapping_leave(
        db: AsyncSession,
        organization_id: str,
        employee_id: str,
        start_date: date,
        end_date: date,
        exclude_leave_id: Optional[str] = None
    ) -> Optional[LeaveRecord]:
        """
        Check if employee has an active (pending or approved) leave request
        that overlaps with the specified date range [start_date, end_date].
        """
        stmt = select(LeaveRecord).where(
            and_(
                LeaveRecord.organization_id == organization_id,
                LeaveRecord.employee_id == employee_id,
                LeaveRecord.status.in_(["pending", "approved"]),
                LeaveRecord.start_date <= end_date,
                LeaveRecord.end_date >= start_date
            )
        )
        if exclude_leave_id:
            stmt = stmt.where(LeaveRecord.id != exclude_leave_id)

        result = await db.execute(stmt)
        return result.scalars().first()

    @classmethod
    async def apply_leave(
        cls,
        db: AsyncSession,
        organization_id: str,
        target_employee_id: str,
        req: LeaveCreate,
        current_user: User
    ) -> LeaveRecord:
        """
        Submit a new leave request with full date, quota, and overlap validation.
        Dispatches notification to HR managers and administrators.
        """
        # 1. Date order validation
        if req.end_date < req.start_date:
            raise ValidationException("End date cannot precede start date")

        # 2. Leave type validation
        normalized_type = req.leave_type.lower().strip()
        if normalized_type not in cls.ALLOWED_LEAVE_TYPES:
            allowed = ", ".join(sorted(cls.ALLOWED_LEAVE_TYPES))
            raise ValidationException(f"Invalid leave type '{req.leave_type}'. Allowed types: {allowed}")

        # 3. Check for overlapping existing active leaves
        conflicting = await cls.check_overlapping_leave(
            db=db,
            organization_id=organization_id,
            employee_id=target_employee_id,
            start_date=req.start_date,
            end_date=req.end_date
        )
        if conflicting:
            raise ConflictException(
                f"Leave request conflicts with an existing {conflicting.status} {conflicting.leave_type} "
                f"leave from {conflicting.start_date} to {conflicting.end_date}."
            )

        days_count = max(1.0, float((req.end_date - req.start_date).days + 1))

        # 4. Quota balance check for capped leave categories
        entitlement = cls.STANDARD_ENTITLEMENTS.get(normalized_type)
        if entitlement is not None:
            balances = await cls.calculate_leave_balances(
                db=db,
                organization_id=organization_id,
                employee_id=target_employee_id,
                year=req.start_date.year
            )
            available = balances["categories"][normalized_type]["available"]
            pending = balances["categories"][normalized_type]["pending"]
            if days_count > available:
                raise ValidationException(
                    f"Insufficient {normalized_type} leave balance. Requested {days_count:.1f} days, "
                    f"but only {available:.1f} days remain available for {req.start_date.year} "
                    f"({pending:.1f} days pending approval)."
                )

        # 5. Persist leave record
        leave = LeaveRecord(
            organization_id=organization_id,
            employee_id=target_employee_id,
            leave_type=normalized_type,
            start_date=req.start_date,
            end_date=req.end_date,
            days_count=days_count,
            reason=req.reason.strip(),
            status="pending"
        )
        db.add(leave)
        await db.commit()
        await db.refresh(leave)

        # 6. Dispatch notification to HR Managers and Admins
        try:
            emp = (await db.execute(select(Employee).where(Employee.id == target_employee_id))).scalars().first()
            emp_name = f"{emp.first_name} {emp.last_name}" if emp else "An employee"
            emp_code = f" ({emp.employee_code})" if emp else ""

            admin_users = (await db.execute(
                select(User).where(
                    and_(
                        User.organization_id == organization_id,
                        User.role.in_(["admin", "hr_manager"])
                    )
                )
            )).scalars().all()

            for mgr in admin_users:
                # Do not notify self if admin applied on own behalf
                if mgr.id != current_user.id:
                    await NotificationService.create_notification(
                        db=db,
                        organization_id=organization_id,
                        user_id=mgr.id,
                        category="leave",
                        title="New Leave Application",
                        message=f"{emp_name}{emp_code} submitted a {normalized_type.title()} Leave request for {req.start_date} to {req.end_date} ({days_count:.0f} day{'s' if days_count > 1 else ''}).",
                        priority="medium",
                        link="/leave"
                    )
        except Exception as e:
            logger.warning("Could not dispatch leave application notification: %s", e)

        return leave

    @classmethod
    async def review_leave(
        cls,
        db: AsyncSession,
        organization_id: str,
        leave_id: str,
        req: LeaveReviewRequest,
        reviewer: User
    ) -> LeaveRecord:
        """
        Review (approve or reject) a pending leave request.
        Dispatches notification to the employee.
        """
        stmt = select(LeaveRecord).where(
            and_(
                LeaveRecord.id == leave_id,
                LeaveRecord.organization_id == organization_id
            )
        )
        leave = (await db.execute(stmt)).scalars().first()
        if not leave:
            raise NotFoundException("Leave request not found")

        if req.status not in ["approved", "rejected"]:
            raise ValidationException("Review status must be either 'approved' or 'rejected'")

        if leave.status == "cancelled":
            raise ValidationException("Cannot review a cancelled leave request.")

        leave.status = req.status
        leave.resolution_notes = req.resolution_notes
        leave.reviewed_by = reviewer.id
        leave.reviewed_at = datetime.utcnow()

        await db.commit()
        await db.refresh(leave)

        # Notify the employee
        try:
            emp = (await db.execute(select(Employee).where(Employee.id == leave.employee_id))).scalars().first()
            if emp and emp.user_id:
                action_text = "approved" if req.status == "approved" else "rejected"
                notes_text = f" Rationale: {req.resolution_notes}" if req.resolution_notes else ""
                priority = "success" if req.status == "approved" else "warning"

                await NotificationService.create_notification(
                    db=db,
                    organization_id=organization_id,
                    user_id=emp.user_id,
                    category="leave",
                    title=f"Leave Request {req.status.title()}",
                    message=f"Your {leave.leave_type.title()} Leave request for {leave.start_date} to {leave.end_date} ({leave.days_count:.0f} days) was {action_text}.{notes_text}",
                    priority=priority,
                    link="/leave"
                )
        except Exception as e:
            logger.warning("Could not dispatch leave review notification: %s", e)

        return leave

    @classmethod
    async def cancel_leave(
        cls,
        db: AsyncSession,
        organization_id: str,
        leave_id: str,
        current_user: User,
        employee: Optional[Employee],
        reason: Optional[str] = None
    ) -> LeaveRecord:
        """
        Cancel a pending leave request.
        Employees can cancel their own pending requests. Admins/HR can cancel any pending request.
        """
        stmt = select(LeaveRecord).where(
            and_(
                LeaveRecord.id == leave_id,
                LeaveRecord.organization_id == organization_id
            )
        )
        leave = (await db.execute(stmt)).scalars().first()
        if not leave:
            raise NotFoundException("Leave request not found")

        # Authorization: regular employees can only cancel their own leave
        if current_user.role == "employee":
            if not employee or leave.employee_id != employee.id:
                raise ForbiddenException("You do not have permission to cancel another employee's leave request")

        if leave.status != "pending":
            raise ValidationException(f"Cannot cancel leave request in '{leave.status}' status. Only pending requests can be cancelled.")

        cancel_note = f"Cancelled by {current_user.email}"
        if reason:
            cancel_note += f": {reason.strip()}"

        leave.status = "cancelled"
        if leave.resolution_notes:
            leave.resolution_notes = f"{leave.resolution_notes} | {cancel_note}"
        else:
            leave.resolution_notes = cancel_note

        leave.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(leave)

        # Notify HR/Admin if cancelled by employee
        if current_user.role == "employee":
            try:
                emp = employee or (await db.execute(select(Employee).where(Employee.id == leave.employee_id))).scalars().first()
                emp_name = f"{emp.first_name} {emp.last_name}" if emp else "Employee"

                admin_users = (await db.execute(
                    select(User).where(
                        and_(
                            User.organization_id == organization_id,
                            User.role.in_(["admin", "hr_manager"])
                        )
                    )
                )).scalars().all()

                for mgr in admin_users:
                    await NotificationService.create_notification(
                        db=db,
                        organization_id=organization_id,
                        user_id=mgr.id,
                        category="leave",
                        title="Leave Request Cancelled",
                        message=f"{emp_name} cancelled their pending {leave.leave_type.title()} Leave request for {leave.start_date} to {leave.end_date}.",
                        priority="information",
                        link="/leave"
                    )
            except Exception as e:
                logger.warning("Could not dispatch leave cancellation notification: %s", e)

        return leave
