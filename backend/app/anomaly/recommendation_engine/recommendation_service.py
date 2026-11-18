import logging
import time
import json
import re
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from app.models.models import AttendanceAnomaly, Employee, Department
from app.core.exceptions import NotFoundException
from app.core.config import settings
from .recommendation_schemas import (
    AnomalyInvestigationResponse,
    DashboardRecommendationsResponse,
    RecommendedAction,
    AIRecommendedActionDetail,
    AttendanceComparison,
    HistoricalContext
)
from .analyzer import AnomalyAnalyzer
from .action_registry import ActionRegistry
from .policy_context import PolicyContextRegistry
from .explanation_generator import ExplanationGenerator

logger = logging.getLogger("attendai.anomaly.recommendation")

# Cache recommendations for 10 minutes to avoid redundant LLM invocations
_RECOMMENDATION_CACHE: Dict[str, Tuple[float, AIRecommendedActionDetail]] = {}
CACHE_TTL_SECONDS = 600.0

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
    def build_rule_based_recommendation(
        cls,
        anomaly_type: str,
        detection_date: str,
        severity: str,
        score: float,
        detection_method: str,
        comparison: AttendanceComparison,
        history: HistoricalContext,
        policy_citation: Optional[str] = None
    ) -> AIRecommendedActionDetail:
        norm_type = (anomaly_type or "").lower().strip()
        actual_m = comparison.actual_worked_minutes or 0
        exp_m = comparison.expected_worked_minutes or int(history.assigned_shift_hours * 60)
        ot_m = comparison.actual_overtime_minutes or 0
        late_m = comparison.actual_late_minutes or 0
        break_m = comparison.actual_break_minutes or 0
        exp_break_m = comparison.expected_break_minutes or 60
        shift_name = history.assigned_shift_name or "Standard Shift"
        grace_m = history.grace_period_minutes or 15

        # Structured supporting evidence from actual database records
        supporting_evidence = [
            f"Worked: {actual_m} minutes ({round(actual_m/60.0, 1)}h) vs. Scheduled {exp_m} minutes",
            f"Overtime: {ot_m} minutes ({round(ot_m/60.0, 1)}h)",
            f"Late arrival: {late_m} minutes (Grace period: {grace_m}m)",
            f"Break duration: {break_m} minutes (Policy allowance: {exp_break_m}m)",
            f"Isolation Forest score: {round(score, 2)} ({detection_method.replace('_', ' ')})",
            f"30-Day Context: {history.overtime_frequency_30d} OT days, {history.late_arrival_frequency_30d} late arrivals"
        ]

        if norm_type in ["excessive_overtime", "unusually_long_shift"] or ot_m >= 120:
            title = "Recommended Action: Verify Overtime Authorization"
            explanation = (
                f"The employee's recorded working duration ({actual_m}m) is substantially higher than the "
                f"expected duration ({exp_m}m). Review the assigned shift and check whether the additional "
                f"{ot_m} working hours were approved by the supervisor."
            )
            suggested_steps = [
                f"Verify the employee's assigned shift ({shift_name}).",
                f"Check the overtime approval record for date {detection_date}.",
                "Confirm the actual working hours with the supervisor.",
                "Initiate an attendance correction if an error is identified."
            ]
            action_type = "audit_record"
            priority = "high" if ot_m >= 180 or severity in ["high", "critical"] else "medium"
            policy_ref = policy_citation or "Overtime & Shift Differentials Policy – Section 3.1"

        elif norm_type in ["unusual_working_hours"]:
            title = "Recommended Action: Verify Shift Duration and Overtime Approval"
            explanation = (
                f"The employee worked {actual_m} minutes when their usual working duration is approximately "
                f"{int(history.average_worked_minutes_30d) or exp_m} minutes (scheduled: {exp_m}m on '{shift_name}'). "
                f"Review whether an extended shift or schedule variance was authorized."
            )
            suggested_steps = [
                "Verify whether an extended shift was approved by the manager.",
                f"Check the assigned shift duration ({shift_name}).",
                f"Review overtime authorization records for date {detection_date}.",
                "Confirm whether the attendance record and punch timestamps are correct."
            ]
            action_type = "verify_shift"
            priority = severity if severity in ["high", "critical"] else "medium"
            policy_ref = policy_citation or "Global Attendance & Punctuality Policy – Section 4.2"

        elif norm_type in ["repeated_late_arrival", "late_arrival"] or late_m > grace_m:
            title = "Recommended Action: Review Shift Timing and Arrival History"
            explanation = (
                f"The employee arrived {late_m} minutes past the scheduled shift start, exceeding the "
                f"{grace_m}-minute grace period. The employee has logged {history.late_arrival_frequency_30d} "
                f"late arrivals over the past 30 days."
            )
            suggested_steps = [
                f"Check whether the assigned shift timings ({comparison.scheduled_start or '09:00'} - {comparison.scheduled_end or '18:00'}) are correct.",
                "Review the employee's historical arrival patterns over the past 30 days.",
                f"Verify whether a grace-period configuration applies ({grace_m} minutes).",
                "Suggest a shift adjustment for HR consideration or recommend a supervisor discussion."
            ]
            action_type = "supervisor_consultation"
            priority = "high" if history.late_arrival_frequency_30d >= 3 else "medium"
            policy_ref = policy_citation or "Global Attendance & Punctuality Policy – Section 3.1"

        elif norm_type in ["missing_clock_out", "unclosed_shift"] or not comparison.clock_out_time:
            title = "Recommended Action: Request Departure Verification & Attendance Correction"
            explanation = (
                f"The employee clocked in at {comparison.clock_in_time or 'start of shift'}, but no corresponding "
                f"clock-out timestamp was recorded. The attendance record remains unclosed."
            )
            suggested_steps = [
                "Ask the employee or supervisor to verify the actual departure time.",
                "Check whether a clock-out event was recorded incorrectly or failed telemetry sync.",
                "If verified, initiate an attendance correction request.",
                "Preserve the original attendance record and correction history in audit logs."
            ]
            action_type = "correct_punch"
            priority = "high"
            policy_ref = policy_citation or "Global Attendance & Punctuality Policy – Section 5.1"

        elif norm_type in ["abnormal_break_duration", "unusual_break"] or break_m > 60:
            title = "Recommended Action: Verify Break Approval and Policy Compliance"
            explanation = (
                f"Cumulative break duration of {break_m} minutes exceeds the allowable {exp_break_m} minutes limit "
                f"({break_m - exp_break_m}m variance)."
            )
            suggested_steps = [
                "Verify whether the extended break was approved by the shift supervisor.",
                "Check break policy configuration and meal duration allowances.",
                "Review the employee's historical break patterns.",
                "Initiate an attendance correction if break duration was recorded incorrectly."
            ]
            action_type = "policy_review"
            priority = "medium"
            policy_ref = policy_citation or "Global Attendance & Punctuality Policy – Section 4.3"

        elif norm_type in ["duplicate_attendance"]:
            title = "Recommended Action: Review Duplicate Punch Telemetry"
            explanation = (
                "Multiple conflicting punch records were detected for the employee on the same date. "
                "Audit is required to reconcile valid timestamps from duplicated telemetry."
            )
            suggested_steps = [
                "Review duplicate punch records and biometric telemetry timestamps.",
                "Check whether biometric devices generated duplicate entries due to network retries.",
                "Initiate an attendance correction to remove duplicate entries.",
                "Preserve the original attendance record and telemetry log trail."
            ]
            action_type = "correct_punch"
            priority = "high"
            policy_ref = policy_citation or "Global Attendance & Punctuality Policy – Section 5.2"

        elif norm_type in ["unusual_absence_frequency"]:
            title = "Recommended Action: Cross-Check Approved Leave Records"
            explanation = (
                "Unscheduled absence detected without a corresponding approved leave record in the HR system."
            )
            suggested_steps = [
                "Cross-check approved leave records in the Leave Management module.",
                "Check whether the absence was recorded correctly or if retroactive leave was filed.",
                "Contact the supervisor to verify the absence rationale.",
                "Recommend initiating a leave request or mark as unexcused absence if applicable."
            ]
            action_type = "leave_reconciliation"
            priority = "high"
            policy_ref = policy_citation or "Leave Management & Absence Policy – Section 2.4"

        else:
            title = "Recommended Action: Audit Attendance Record and Shift Baseline"
            explanation = (
                f"The attendance record exhibited an unusual pattern (score: {round(score, 2)}) "
                f"with {actual_m}m worked, {ot_m}m overtime, and {late_m}m tardiness against standard shift '{shift_name}'."
            )
            suggested_steps = [
                f"Verify the employee's assigned shift ({shift_name}) and scheduled hours.",
                "Review overtime authorization and manager sign-off records.",
                "Confirm actual working hours with the employee and direct supervisor.",
                "Initiate an attendance correction if an operational error is identified."
            ]
            action_type = "audit_record"
            priority = severity if severity in ["critical", "high", "medium", "low"] else "medium"
            policy_ref = policy_citation or "Global Attendance & Punctuality Policy – Section 4.2"

        return AIRecommendedActionDetail(
            title=title,
            explanation=explanation,
            suggested_steps=suggested_steps,
            supporting_evidence=supporting_evidence,
            policy_reference=policy_ref,
            priority=priority,
            source="Rule-based Engine",
            provider="rule_based",
            evidence_completeness="complete",
            action_type=action_type
        )

    @classmethod
    async def generate_ai_recommended_action(
        cls,
        anomaly_id: str,
        anomaly_type: str,
        detection_date: str,
        severity: str,
        score: float,
        detection_method: str,
        comparison: AttendanceComparison,
        history: HistoricalContext,
        policy_citation: Optional[str] = None
    ) -> AIRecommendedActionDetail:
        now = time.time()
        cached = _RECOMMENDATION_CACHE.get(anomaly_id)
        if cached and (now - cached[0] < CACHE_TTL_SECONDS):
            return cached[1]

        # 1. Deterministic baseline (always computed first for 100% reliability)
        rule_rec = cls.build_rule_based_recommendation(
            anomaly_type=anomaly_type,
            detection_date=detection_date,
            severity=severity,
            score=score,
            detection_method=detection_method,
            comparison=comparison,
            history=history,
            policy_citation=policy_citation
        )

        # 2. Determine available AI providers: NVIDIA NIM primary -> GroqCloud fallback
        providers_to_try = []
        if settings.NVIDIA_API_KEY:
            try:
                from app.harness.providers.nvidia import NvidiaNIMProvider
                providers_to_try.append(("AI-assisted (NVIDIA NIM)", "nvidia", NvidiaNIMProvider()))
            except Exception as e:
                logger.debug(f"Failed to load NVIDIA NIM provider: {e}")

        if settings.GROQ_API_KEY:
            try:
                from app.harness.providers.groq import GroqProvider
                providers_to_try.append(("AI-assisted (GroqCloud)", "groq", GroqProvider()))
            except Exception as e:
                logger.debug(f"Failed to load Groq provider: {e}")

        if not providers_to_try:
            _RECOMMENDATION_CACHE[anomaly_id] = (now, rule_rec)
            return rule_rec

        # 3. Prompt LLM to synthesize contextual recommendation grounded strictly in facts
        prompt = (
            f"You are AttendAI Workforce Intelligence Recommendation Engine. "
            f"Generate a concise, authoritative corrective recommendation for an HR Manager investigating this attendance anomaly.\n\n"
            f"VERIFIED ATTENDANCE FACTS:\n"
            f"- Anomaly Type: {anomaly_type}\n"
            f"- Date: {detection_date}\n"
            f"- Severity: {severity}\n"
            f"- Outlier Score: {score} (Detection Method: {detection_method})\n"
            f"- Actual Worked Duration: {comparison.actual_worked_minutes}m (Expected: {comparison.expected_worked_minutes}m)\n"
            f"- Overtime Logged: {comparison.actual_overtime_minutes}m\n"
            f"- Late Arrival: {comparison.actual_late_minutes}m (Grace: {history.grace_period_minutes}m)\n"
            f"- Break Duration: {comparison.actual_break_minutes}m (Expected: {comparison.expected_break_minutes}m)\n"
            f"- Assigned Shift: {history.assigned_shift_name} ({history.assigned_shift_hours}h required)\n"
            f"- 30-Day Context: {history.average_worked_minutes_30d}m avg daily, {history.overtime_frequency_30d} overtime days, {history.late_arrival_frequency_30d} late days\n"
            f"- Policy Citation: {rule_rec.policy_reference}\n\n"
            f"REQUIREMENTS:\n"
            f"1. Base recommendations ONLY on the facts above; never fabricate records or overtime approvals.\n"
            f"2. Return ONLY a valid JSON object with these keys:\n"
            f"   \"title\": \"Recommended Action: <Action Title>\",\n"
            f"   \"explanation\": \"<2 concise executive sentences explaining why this action is recommended>\",\n"
            f"   \"suggested_steps\": [\"1. <Step 1>\", \"2. <Step 2>\", \"3. <Step 3>\", \"4. <Step 4>\"],\n"
            f"   \"priority\": \"{rule_rec.priority}\",\n"
            f"   \"action_type\": \"{rule_rec.action_type}\"\n"
            f"Return raw JSON only, no markdown formatting."
        )

        for source_label, provider_code, provider in providers_to_try:
            try:
                resp = await asyncio.wait_for(
                    provider.generate_response(
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1
                    ),
                    timeout=3.5
                )
                raw_content = (resp.get("content") or "").strip()
                if raw_content.startswith("```"):
                    lines = raw_content.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    raw_content = "\n".join(lines).strip()

                parsed = json.loads(raw_content)
                title = parsed.get("title") or rule_rec.title
                if not title.startswith("Recommended Action:"):
                    title = f"Recommended Action: {title.replace('Recommended Action', '').lstrip(': ')}"
                explanation = parsed.get("explanation") or rule_rec.explanation
                raw_steps = parsed.get("suggested_steps") or rule_rec.suggested_steps
                clean_steps = []
                for s in raw_steps:
                    clean_s = re.sub(r"^\d+\.\s*", "", str(s).strip())
                    if clean_s:
                        clean_steps.append(clean_s)
                if not clean_steps:
                    clean_steps = rule_rec.suggested_steps

                ai_rec = AIRecommendedActionDetail(
                    title=title,
                    explanation=explanation,
                    suggested_steps=clean_steps,
                    supporting_evidence=rule_rec.supporting_evidence,
                    policy_reference=rule_rec.policy_reference,
                    priority=parsed.get("priority") or rule_rec.priority,
                    source=source_label,
                    provider=provider_code,
                    evidence_completeness="complete",
                    action_type=parsed.get("action_type") or rule_rec.action_type
                )
                _RECOMMENDATION_CACHE[anomaly_id] = (now, ai_rec)
                return ai_rec
            except Exception as e:
                logger.debug(f"{source_label} generation failed or timed out: {e}. Trying fallback.")

        # Graceful fallback to rule-based engine
        _RECOMMENDATION_CACHE[anomaly_id] = (now, rule_rec)
        return rule_rec

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

        # Determine possible causes
        causes = []
        if comparison.actual_overtime_minutes and comparison.actual_overtime_minutes > 0:
            causes.append(f"Extended shift duration logged: {comparison.actual_overtime_minutes}m overtime")
        if comparison.actual_late_minutes and comparison.actual_late_minutes > 0:
            causes.append(f"Arrival past grace period: {comparison.actual_late_minutes}m late")
        if comparison.actual_break_minutes and comparison.actual_break_minutes > 60:
            causes.append(f"Break duration {comparison.actual_break_minutes}m exceeds standard 60m allowance")
        if not comparison.clock_out_time:
            causes.append("Missing departure timestamp on shift closure")
        if not causes:
            causes.append(f"Feature deviation detected by {anomaly.detection_method.replace('_', ' ')}")

        suggested = ActionRegistry.get_short_recommendation_summary(anomaly.anomaly_type)

        # 6. Synthesize AI-recommended action (Rule-based baseline + NVIDIA NIM / Groq fallback)
        ai_rec_action = await cls.generate_ai_recommended_action(
            anomaly_id=anomaly.id,
            anomaly_type=anomaly.anomaly_type,
            detection_date=str(anomaly.date),
            severity=anomaly.severity,
            score=round(anomaly.score, 2),
            detection_method=anomaly.detection_method,
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
            why_flagged_explanation=explanation,
            confidence_score=0.92,
            comparison=comparison,
            actual_vs_expected=comparison,
            historical_context=history,
            recommendations=recommendations,
            recommended_actions=recommendations,
            suggested_action=suggested,
            possible_causes=causes,
            rule_references=[policy_citation] if policy_citation else [],
            available_resolutions=cls.AVAILABLE_RESOLUTIONS,
            current_status=anomaly.status,
            current_resolution_notes=anomaly.resolution_notes,
            ai_recommended_action=ai_rec_action
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

        prioritized = []
        for t in top_recs:
            prioritized.append({
                "anomaly_id": t["anomaly_id"],
                "employee_name": t["employee_name"],
                "employee_code": t["employee_code"],
                "department_name": t["department"],
                "anomaly_type": t["anomaly_type"],
                "detection_date": t["date"],
                "severity": t["severity"],
                "score": t["score"],
                "status": "pending",
                "primary_recommendation": {
                    "title": t["recommended_action_title"],
                    "action": t["recommended_action"],
                    "required_authorization": t["required_authorization"]
                }
            })

        return DashboardRecommendationsResponse(
            pending_investigations_count=pending_count,
            high_priority_anomalies_count=high_pri_count,
            repeated_patterns_count=repeated_count,
            top_recommendations=top_recs,
            pending_count=pending_count,
            high_priority_count=high_pri_count,
            prioritized_anomalies=prioritized
        )
