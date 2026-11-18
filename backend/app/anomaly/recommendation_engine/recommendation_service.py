import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from app.models.models import AttendanceAnomaly, Employee, Department
from app.core.exceptions import NotFoundException
from .recommendation_schemas import (
    AnomalyInvestigationResponse,
    DashboardRecommendationsResponse,
    RecommendedAction
)
from .analyzer import AnomalyAnalyzer
from .action_registry import ActionRegistry
from .policy_context import PolicyContextRegistry
from .explanation_generator import ExplanationGenerator

logger = logging.getLogger("attendai.anomaly.recommendation")

class AnomalyRecommendationService:
    """
    Intelligent recommendation and investigation service.
    Combines rule-based classification, statistical history analysis, policy citations,
    and structured resolution workflows.
    """

    AVAILABLE_RESOLUTIONS = [
        {"value": "resolved", "label": "Resolve – Investigation Completed"},
        {"value": "dismissed", "label": "Dismiss – False Positive"},
        {"value": "correction_requested", "label": "Create Attendance Correction Request"},
        {"value": "escalated", "label": "Escalate to HR/Admin"},
        {"value": "under_review", "label": "Mark for Further Review"}
    ]

    @classmethod
    async def investigate_anomaly(
        cls,
        db: AsyncSession,
        anomaly_id: str,
        organization_id: str
    ) -> AnomalyInvestigationResponse:
        # 1. Fetch anomaly
        stmt = (
            select(AttendanceAnomaly, Employee, Department)
            .join(Employee, Employee.id == AttendanceAnomaly.employee_id)
            .outerjoin(Department, Department.id == Employee.department_id)
            .where(
                and_(
                    AttendanceAnomaly.id == anomaly_id,
                    AttendanceAnomaly.organization_id == organization_id
                )
            )
        )
        row = (await db.execute(stmt)).first()
        if not row:
            raise NotFoundException("Anomaly record not found or inaccessible")

        anomaly, emp, dept = row

        # 2. Extract comparison and historical context
        comparison, history = await AnomalyAnalyzer.analyze_anomaly(db, anomaly)

        # 3. Retrieve policy context
        policy_info = PolicyContextRegistry.get_policy_context(anomaly.anomaly_type)
        policy_citation = policy_info.get("citation") if policy_info else None

        # 4. Generate structured explanation
        explanation = await ExplanationGenerator.generate_explanation(
            anomaly_type=anomaly.anomaly_type,
            detection_method=anomaly.detection_method,
            score=anomaly.score,
            comparison=comparison,
            history=history,
            raw_explanation=anomaly.explanation
        )

        # 5. Formulate recommendations
        recommendations = ActionRegistry.get_recommendations_for_anomaly(
            anomaly_type=anomaly.anomaly_type,
            comparison=comparison,
            history=history,
            policy_citation=policy_citation
        )

        return AnomalyInvestigationResponse(
            anomaly_id=anomaly.id,
            employee_id=emp.id,
            employee_name=f"{emp.first_name} {emp.last_name}",
            employee_code=emp.employee_code,
            department_name=dept.name if dept else "General Operations",
            anomaly_type=anomaly.anomaly_type,
            detection_date=str(anomaly.date),
            severity=anomaly.severity,
            score=round(anomaly.score, 2),
            detection_method=anomaly.detection_method,
            explanation=explanation,
            comparison=comparison,
            historical_context=history,
            recommendations=recommendations,
            available_resolutions=cls.AVAILABLE_RESOLUTIONS,
            current_status=anomaly.status,
            current_resolution_notes=anomaly.resolution_notes
        )

    @classmethod
    async def get_dashboard_recommendations(
        cls,
        db: AsyncSession,
        organization_id: str,
        limit: int = 5
    ) -> DashboardRecommendationsResponse:
        # 1. High-level counts
        pending_stmt = select(func.count(AttendanceAnomaly.id)).where(
            and_(
                AttendanceAnomaly.organization_id == organization_id,
                AttendanceAnomaly.status == "pending"
            )
        )
        pending_count = (await db.execute(pending_stmt)).scalar() or 0

        high_pri_stmt = select(func.count(AttendanceAnomaly.id)).where(
            and_(
                AttendanceAnomaly.organization_id == organization_id,
                AttendanceAnomaly.status == "pending",
                AttendanceAnomaly.severity.in_(["high", "critical"])
            )
        )
        high_pri_count = (await db.execute(high_pri_stmt)).scalar() or 0

        repeated_stmt = select(func.count(AttendanceAnomaly.id)).where(
            and_(
                AttendanceAnomaly.organization_id == organization_id,
                AttendanceAnomaly.status == "pending",
                AttendanceAnomaly.anomaly_type.in_(["repeated_late_arrival", "excessive_overtime"])
            )
        )
        repeated_count = (await db.execute(repeated_stmt)).scalar() or 0

        # 2. Top priority pending anomalies for recommendations preview
        top_stmt = (
            select(AttendanceAnomaly, Employee, Department)
            .join(Employee, Employee.id == AttendanceAnomaly.employee_id)
            .outerjoin(Department, Department.id == Employee.department_id)
            .where(
                and_(
                    AttendanceAnomaly.organization_id == organization_id,
                    AttendanceAnomaly.status == "pending"
                )
            )
            .order_by(
                desc(AttendanceAnomaly.severity == "critical"),
                desc(AttendanceAnomaly.severity == "high"),
                desc(AttendanceAnomaly.score),
                desc(AttendanceAnomaly.date)
            )
            .limit(limit)
        )
        top_rows = (await db.execute(top_stmt)).all()

        top_recs = []
        for anom, emp, dept in top_rows:
            policy_info = PolicyContextRegistry.get_policy_context(anom.anomaly_type)
            citation = policy_info.get("citation") if policy_info else None
            # Fast comparison summary
            comparison, history = await AnomalyAnalyzer.analyze_anomaly(db, anom)
            actions = ActionRegistry.get_recommendations_for_anomaly(
                anom.anomaly_type, comparison, history, citation
            )
            top_action = actions[0] if actions else None

            top_recs.append({
                "anomaly_id": anom.id,
                "employee_name": f"{emp.first_name} {emp.last_name}",
                "employee_code": emp.employee_code,
                "department": dept.name if dept else "General Operations",
                "anomaly_type": anom.anomaly_type,
                "date": str(anom.date),
                "severity": anom.severity,
                "score": round(anom.score, 2),
                "detection_method": anom.detection_method,
                "recommended_action_title": top_action.title if top_action else "Investigate Variance",
                "recommended_action": top_action.action if top_action else "Audit attendance records with supervisor.",
                "action_type": top_action.action_type if top_action else "audit_record",
                "required_authorization": top_action.required_authorization if top_action else "HR Manager",
                "policy_reference": citation,
                "confidence_score": top_action.confidence_score if top_action else 0.85
            })

        return DashboardRecommendationsResponse(
            pending_investigations_count=pending_count,
            high_priority_anomalies_count=high_pri_count,
            repeated_patterns_count=repeated_count,
            top_recommendations=top_recs
        )
