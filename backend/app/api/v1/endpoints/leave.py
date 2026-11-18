from typing import List, Optional
from datetime import datetime, date, timezone
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from app.core.database import get_db
from app.core.exceptions import NotFoundException, ForbiddenException, ValidationException
from app.models.models import LeaveRecord, Employee, Department, User
from app.schemas.schemas import (
    LeaveCreate, LeaveReviewRequest, LeaveCancelRequest,
    LeaveResponse, LeaveBalanceResponse
)
from app.services.leave_service import LeaveService
from app.api.deps import get_current_user, get_current_hr_or_admin, get_current_employee_profile

router = APIRouter(prefix="/leave", tags=["Leave Management"])

@router.get("/balances", response_model=LeaveBalanceResponse)
@router.get("/summary", response_model=LeaveBalanceResponse)
async def get_leave_balances(
    employee_id: Optional[str] = None,
    year: Optional[int] = Query(None, description="Target calendar year (default: current year)"),
    user: User = Depends(get_current_user),
    employee: Optional[Employee] = Depends(get_current_employee_profile),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve live statutory and custom leave balance breakdowns (Annual, Sick, Casual, Unpaid).
    Regular employees can only view their own balances. HR Managers and Admins can query any employee.
    """
    target_emp_id = None
    if user.role in ["admin", "hr_manager"]:
        if employee_id:
            target_emp_id = employee_id
        elif employee:
            target_emp_id = employee.id
        else:
            # Fallback to first employee in organization
            first_emp = (await db.execute(
                select(Employee).where(Employee.organization_id == user.organization_id)
            )).scalars().first()
            if not first_emp:
                raise NotFoundException("No employee records found in organization")
            target_emp_id = first_emp.id
    else:
        if not employee:
            raise ValidationException("Employee profile not found")
        target_emp_id = employee.id

    return await LeaveService.calculate_leave_balances(
        db=db,
        organization_id=user.organization_id,
        employee_id=target_emp_id,
        year=year
    )

@router.post("", response_model=LeaveResponse, status_code=status.HTTP_201_CREATED)
async def apply_leave(
    req: LeaveCreate,
    user: User = Depends(get_current_user),
    employee: Optional[Employee] = Depends(get_current_employee_profile),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit a new leave application with automatic date ordering, overlap checking,
    and quota limit validation. Emits notifications to organization HR and Admins.
    """
    target_emp_id = None
    if user.role in ["admin", "hr_manager"] and req.employee_id:
        target_emp_id = req.employee_id
    elif employee:
        target_emp_id = employee.id
    else:
        raise ValidationException("Employee profile not found")

    leave = await LeaveService.apply_leave(
        db=db,
        organization_id=user.organization_id,
        target_employee_id=target_emp_id,
        req=req,
        current_user=user
    )
    return await LeaveService.format_leave_response(db, leave)

@router.get("", response_model=List[LeaveResponse])
async def list_leave(
    status_filter: Optional[str] = None,
    leave_type: Optional[str] = None,
    employee_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    employee: Optional[Employee] = Depends(get_current_employee_profile),
    db: AsyncSession = Depends(get_db)
):
    """
    List leave applications. Scoped by role: regular employees only view their own
    requests; HR Managers and Admins view organization-wide requests.
    """
    stmt = (
        select(LeaveRecord, Employee, Department)
        .join(Employee, Employee.id == LeaveRecord.employee_id)
        .outerjoin(Department, Department.id == Employee.department_id)
        .where(LeaveRecord.organization_id == user.organization_id)
    )

    if user.role == "employee":
        if not employee:
            return []
        stmt = stmt.where(LeaveRecord.employee_id == employee.id)
    elif employee_id:
        stmt = stmt.where(LeaveRecord.employee_id == employee_id)

    if status_filter:
        stmt = stmt.where(LeaveRecord.status == status_filter)
    if leave_type:
        stmt = stmt.where(LeaveRecord.leave_type == leave_type.lower().strip())
    if start_date:
        stmt = stmt.where(LeaveRecord.start_date >= start_date)
    if end_date:
        stmt = stmt.where(LeaveRecord.end_date <= end_date)

    stmt = stmt.order_by(desc(LeaveRecord.created_at)).offset(skip).limit(limit)
    res = await db.execute(stmt)

    output = []
    for l, emp, dept in res.all():
        reviewer_name = None
        if l.reviewed_by:
            rev_user = (await db.execute(select(User).where(User.id == l.reviewed_by))).scalars().first()
            if rev_user:
                rev_emp = (await db.execute(select(Employee).where(Employee.user_id == rev_user.id))).scalars().first()
                reviewer_name = f"{rev_emp.first_name} {rev_emp.last_name}" if rev_emp else rev_user.email

        output.append({
            "id": l.id,
            "organization_id": l.organization_id,
            "employee_id": l.employee_id,
            "leave_type": l.leave_type,
            "start_date": l.start_date,
            "end_date": l.end_date,
            "days_count": l.days_count,
            "reason": l.reason,
            "status": l.status,
            "reviewed_by": l.reviewed_by,
            "reviewed_at": l.reviewed_at,
            "resolution_notes": l.resolution_notes,
            "created_at": l.created_at,
            "employee_name": f"{emp.first_name} {emp.last_name}",
            "employee_code": emp.employee_code,
            "department_name": dept.name if dept else "General",
            "reviewer_name": reviewer_name
        })
    return output

@router.get("/{leave_id}", response_model=LeaveResponse)
async def get_leave(
    leave_id: str,
    user: User = Depends(get_current_user),
    employee: Optional[Employee] = Depends(get_current_employee_profile),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve details of a single leave application by ID.
    Enforces RBAC: regular employees can only access their own requests.
    """
    stmt = select(LeaveRecord).where(
        and_(
            LeaveRecord.id == leave_id,
            LeaveRecord.organization_id == user.organization_id
        )
    )
    leave = (await db.execute(stmt)).scalars().first()
    if not leave:
        raise NotFoundException("Leave request not found")

    if user.role == "employee":
        if not employee or leave.employee_id != employee.id:
            raise ForbiddenException("You do not have permission to view another employee's leave request")

    return await LeaveService.format_leave_response(db, leave)

@router.put("/{leave_id}/review", response_model=LeaveResponse)
async def review_leave(
    leave_id: str,
    req: LeaveReviewRequest,
    user: User = Depends(get_current_hr_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Approve or reject a pending leave application.
    Enforces review state validation and dispatches notification to the employee.
    """
    leave = await LeaveService.review_leave(
        db=db,
        organization_id=user.organization_id,
        leave_id=leave_id,
        req=req,
        reviewer=user
    )
    return await LeaveService.format_leave_response(db, leave)

@router.post("/{leave_id}/cancel", response_model=LeaveResponse)
@router.delete("/{leave_id}", response_model=LeaveResponse)
async def cancel_leave(
    leave_id: str,
    req: Optional[LeaveCancelRequest] = None,
    user: User = Depends(get_current_user),
    employee: Optional[Employee] = Depends(get_current_employee_profile),
    db: AsyncSession = Depends(get_db)
):
    """
    Cancel / withdraw a pending leave application.
    Employees can cancel their own pending requests. HR Managers and Admins can cancel any pending request.
    """
    leave = await LeaveService.cancel_leave(
        db=db,
        organization_id=user.organization_id,
        leave_id=leave_id,
        current_user=user,
        employee=employee,
        reason=req.reason if req else None
    )
    return await LeaveService.format_leave_response(db, leave)
