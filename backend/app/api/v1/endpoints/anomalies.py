from typing import List, Optional
from datetime import datetime, date, timezone
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from app.core.database import get_db
from app.core.exceptions import NotFoundException, BadRequestException, ConflictException
from app.models.models import AttendanceAnomaly, Employee, Department, User, AuditLog
from app.schemas.schemas import AnomalyResponse, AnomalyReviewRequest
from app.services.anomaly_service import AnomalyService
from app.api.deps import get_current_user, get_current_hr_or_admin
from app.anomaly.recommendation_engine.action_registry import ActionRegistry

router = APIRouter(prefix="/anomalies", tags=["Anomaly Detection"])

@router.get("", response_model=List[AnomalyResponse])
async def list_anomalies(
    severity: Optional[str] = None,
    status_filter: Optional[str] = None,
    anomaly_type: Optional[str] = None,
    department_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_hr_or_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(AttendanceAnomaly, Employee, Department)
        .join(Employee, Employee.id == AttendanceAnomaly.employee_id)
        .outerjoin(Department, Department.id == Employee.department_id)
        .where(AttendanceAnomaly.organization_id == user.organization_id)
    )

    if severity:
        stmt = stmt.where(AttendanceAnomaly.severity == severity)
    if status_filter:
        stmt = stmt.where(AttendanceAnomaly.status == status_filter)
    if anomaly_type:
        stmt = stmt.where(AttendanceAnomaly.anomaly_type == anomaly_type)
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)

    stmt = stmt.order_by(desc(AttendanceAnomaly.created_at)).offset(skip).limit(limit)
    res = await db.execute(stmt)

    from app.anomaly.recommendation_engine.action_registry import ActionRegistry

    output = []
    for anom, emp, dept in res.all():
        suggested = ActionRegistry.get_short_recommendation_summary(anom.anomaly_type)
        output.append({
            "id": anom.id,
            "organization_id": anom.organization_id,
            "employee_id": anom.employee_id,
            "attendance_record_id": anom.attendance_record_id,
            "date": anom.date,
            "anomaly_type": anom.anomaly_type,
            "severity": anom.severity,
            "score": anom.score,
            "detection_method": anom.detection_method,
            "explanation": anom.explanation,
            "status": anom.status,
            "reviewed_by": anom.reviewed_by,
            "reviewed_at": anom.reviewed_at,
            "resolution_notes": anom.resolution_notes,
            "created_at": anom.created_at,
            "employee_name": f"{emp.first_name} {emp.last_name}",
            "employee_code": emp.employee_code,
            "department_name": dept.name if dept else "General",
            "suggested_action": suggested,
            "recommendation_priority": anom.severity,
            "recommendation_source": anom.detection_method or "rule_based"
        })
    return output

@router.post("/detect")
async def trigger_anomaly_detection(
    target_date: Optional[date] = None,
    user: User = Depends(get_current_hr_or_admin),
    db: AsyncSession = Depends(get_db)
):
    count = await AnomalyService.run_detection_pipeline(
        db=db,
        organization_id=user.organization_id,
        target_date=target_date
    )
    return {
        "message": f"Anomaly detection completed. {count} new anomalies identified.",
        "anomalies_detected": count
    }

@router.get("/recommendations/dashboard")
async def get_dashboard_anomaly_recommendations(
    limit: int = Query(5, ge=1, le=20),
    user: User = Depends(get_current_hr_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns high-priority anomaly recommendations, pending review volume,
    and repeated pattern warnings for the enterprise dashboard.
    """
    from app.anomaly.recommendation_engine import AnomalyRecommendationService
    return await AnomalyRecommendationService.get_dashboard_recommendations(
        db=db,
        organization_id=user.organization_id,
        limit=limit
    )

@router.get("/{anomaly_id}/investigate")
async def investigate_anomaly_details(
    anomaly_id: str,
    user: User = Depends(get_current_hr_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Deep intelligent investigation for an anomaly flag:
    Retrieves actual attendance records, compares against scheduled shift parameters,
    computes 30-day historical context, generates structured explanation,
    and returns 2-4 authoritative corrective recommendations.
    """
    from app.anomaly.recommendation_engine import AnomalyRecommendationService
    return await AnomalyRecommendationService.investigate_anomaly(
        db=db,
        anomaly_id=anomaly_id,
        organization_id=user.organization_id
    )

VALID_RESOLUTION_STATUSES = {
    "resolved",
    "dismissed",
    "correction_requested",
    "escalated",
    "under_review",
}

@router.put("/{anomaly_id}/review", response_model=AnomalyResponse)
async def review_anomaly(
    anomaly_id: str,
    req: AnomalyReviewRequest,
    user: User = Depends(get_current_hr_or_admin),
    db: AsyncSession = Depends(get_db)
):
    # 1. Validate status against supported domain statuses
    clean_status = (req.status or "").strip().lower()
    if clean_status not in VALID_RESOLUTION_STATUSES:
        raise BadRequestException(
            f"Invalid resolution status '{req.status}'. Must be one of: {', '.join(sorted(VALID_RESOLUTION_STATUSES))}"
        )

    # 2. Validate mandatory resolution notes
    clean_notes = (req.resolution_notes or "").strip()
    if not clean_notes:
        raise BadRequestException("Mandatory resolution notes are required to document the outcome of this investigation.")

    # 3. Fetch anomaly scoped by organization
    stmt = select(AttendanceAnomaly).where(
        and_(
            AttendanceAnomaly.id == anomaly_id,
            AttendanceAnomaly.organization_id == user.organization_id
        )
    )
    anom = (await db.execute(stmt)).scalars().first()
    if not anom:
        raise NotFoundException("Anomaly record not found")

    # 4. Check if anomaly was already resolved/closed
    if anom.status in ["resolved", "dismissed"]:
        raise ConflictException(
            f"This anomaly has already been resolved and closed ({anom.status}). Re-resolving closed anomalies is not permitted."
        )

    # 5. Idempotency guard: prevent duplicate audit entries on identical repeated submissions
    if anom.status == clean_status and (anom.resolution_notes or "").strip() == clean_notes:
        emp = (await db.execute(select(Employee).where(Employee.id == anom.employee_id))).scalars().first()
        dept = (await db.execute(select(Department).where(Department.id == emp.department_id))).scalars().first() if emp and emp.department_id else None
        suggested = ActionRegistry.get_short_recommendation_summary(anom.anomaly_type)
        return {
            "id": anom.id,
            "organization_id": anom.organization_id,
            "employee_id": anom.employee_id,
            "attendance_record_id": anom.attendance_record_id,
            "date": anom.date,
            "anomaly_type": anom.anomaly_type,
            "severity": anom.severity,
            "score": anom.score,
            "detection_method": anom.detection_method,
            "explanation": anom.explanation,
            "status": anom.status,
            "reviewed_by": anom.reviewed_by,
            "reviewed_at": anom.reviewed_at,
            "resolution_notes": anom.resolution_notes,
            "created_at": anom.created_at,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else None,
            "employee_code": emp.employee_code if emp else None,
            "department_name": dept.name if dept else "General",
            "suggested_action": suggested,
            "recommendation_priority": anom.severity,
            "recommendation_source": anom.detection_method or "rule_based"
        }

    # 6. Record status transition and timestamps
    previous_status = anom.status
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    anom.status = clean_status
    anom.resolution_notes = clean_notes
    anom.reviewed_by = user.id
    anom.reviewed_at = now_utc
    anom.updated_at = now_utc

    # 7. Create Audit Log in the SAME database transaction
    emp = (await db.execute(select(Employee).where(Employee.id == anom.employee_id))).scalars().first()
    dept = (await db.execute(select(Department).where(Department.id == emp.department_id))).scalars().first() if emp and emp.department_id else None
    employee_name = f"{emp.first_name} {emp.last_name}" if emp else None
    reviewer_name = f"{user.first_name} {user.last_name}" if getattr(user, "first_name", None) else (getattr(user, "username", None) or getattr(user, "email", "HR/Admin"))

    audit_entry = AuditLog(
        organization_id=user.organization_id,
        user_id=user.id,
        action="anomaly_investigation_resolution",
        resource_type="attendance_anomaly",
        resource_id=anom.id,
        details={
            "anomaly_id": anom.id,
            "employee_id": anom.employee_id,
            "employee_name": employee_name,
            "employee_code": emp.employee_code if emp else None,
            "department_name": dept.name if dept else None,
            "anomaly_type": anom.anomaly_type,
            "severity": anom.severity,
            "score": anom.score,
            "previous_status": previous_status,
            "new_status": clean_status,
            "resolution_notes": clean_notes,
            "reviewed_by_id": user.id,
            "reviewed_by_name": reviewer_name,
            "reviewed_at": now_utc.isoformat(),
        }
    )
    db.add(audit_entry)

    # 8. Persist atomically with rollback safety
    try:
        await db.commit()
        await db.refresh(anom)
    except Exception as e:
        await db.rollback()
        raise e

    suggested = ActionRegistry.get_short_recommendation_summary(anom.anomaly_type)

    return {
        "id": anom.id,
        "organization_id": anom.organization_id,
        "employee_id": anom.employee_id,
        "attendance_record_id": anom.attendance_record_id,
        "date": anom.date,
        "anomaly_type": anom.anomaly_type,
        "severity": anom.severity,
        "score": anom.score,
        "detection_method": anom.detection_method,
        "explanation": anom.explanation,
        "status": anom.status,
        "reviewed_by": anom.reviewed_by,
        "reviewed_at": anom.reviewed_at,
        "resolution_notes": anom.resolution_notes,
        "created_at": anom.created_at,
        "employee_name": employee_name,
        "employee_code": emp.employee_code if emp else None,
        "department_name": dept.name if dept else "General",
        "suggested_action": suggested,
        "recommendation_priority": anom.severity,
        "recommendation_source": anom.detection_method or "rule_based"
    }
