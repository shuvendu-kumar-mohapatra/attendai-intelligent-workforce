import logging
from typing import Optional, Dict, Any
from app.core.config import settings
from .recommendation_schemas import AttendanceComparison, HistoricalContext

logger = logging.getLogger("attendai.anomaly.explanation")

class ExplanationGenerator:
    """
    Generates clear, concise, and audit-ready explanations for detected workforce anomalies.
    Leverages configured LLM providers (NVIDIA NIM / Groq / Gemini) when reachable,
    with an immediate deterministic fallback ensuring 100% offline reliability.
    """

    @classmethod
    def generate_deterministic_explanation(
        cls,
        anomaly_type: str,
        detection_method: str,
        score: float,
        comparison: AttendanceComparison,
        history: HistoricalContext,
        raw_explanation: Optional[str] = None
    ) -> str:
        norm_type = anomaly_type.lower().strip()
        actual_m = comparison.actual_worked_minutes or 0
        exp_m = comparison.expected_worked_minutes or int(history.assigned_shift_hours * 60)
        avg_m = int(history.average_worked_minutes_30d) or exp_m
        ot_m = comparison.actual_overtime_minutes or 0
        late_m = comparison.actual_late_minutes or 0

        if norm_type in ["excessive_overtime", "unusually_long_shift"]:
            ot_h = round(ot_m / 60.0, 1) if ot_m else round(max(0, actual_m - exp_m) / 60.0, 1)
            return (
                f"Employee logged {actual_m} minutes of work ({ot_m} minutes of overtime / {ot_h} hours) "
                f"against scheduled {exp_m} minutes for shift '{history.assigned_shift_name}'. "
                f"This significantly exceeds standard daily overtime thresholds."
            )

        elif norm_type in ["repeated_late_arrival", "late_arrival"]:
            return (
                f"Employee clocked in at {comparison.clock_in_time or 'late'} ({late_m} minutes tardy), "
                f"exceeding the {history.grace_period_minutes}-minute shift grace period. "
                f"The employee has recorded {history.late_arrival_frequency_30d} late arrivals in the past 30 days."
            )

        elif norm_type in ["missing_clock_out", "unclosed_shift"]:
            return (
                f"Employee clocked in at {comparison.clock_in_time or 'shift start'} on the scheduled date, "
                f"but no corresponding departure punch was recorded. The attendance record remains unclosed."
            )

        elif norm_type in ["abnormal_break_duration", "unusual_break"]:
            actual_b = comparison.actual_break_minutes or 0
            return (
                f"Cumulative break duration of {actual_b} minutes exceeds standard shift allowance (60 minutes). "
                f"The break duration is {actual_b - 60} minutes above typical baseline."
            )

        elif norm_type in ["unusual_working_hours"]:
            return (
                f"Employee worked {actual_m} minutes compared with their usual {avg_m} minutes "
                f"(scheduled: {exp_m} minutes on '{history.assigned_shift_name}'). "
                f"The system identified this as an irregular operational duration."
            )

        elif norm_type in ["duplicate_attendance"]:
            return (
                f"Multiple conflicting attendance punch events were recorded for the employee on this date. "
                f"Requires audit to isolate valid timestamps from duplicate telemetry entries."
            )

        elif norm_type in ["unusual_absence_frequency"]:
            return (
                f"Unscheduled absence recorded without corresponding approved annual or sick leave application. "
                f"Requires reconciliation with HR leave records."
            )

        else: # isolation_forest_outlier or generic
            if raw_explanation and "multivariate" in raw_explanation.lower():
                return raw_explanation
            return (
                f"Employee worked {actual_m} minutes (overtime: {ot_m}m, tardiness: {late_m}m) "
                f"compared with their 30-day baseline average of {avg_m} minutes. "
                f"The {detection_method.replace('_', ' ').title()} engine identified this as an unusual multivariate outlier pattern (Anomaly score: {score})."
            )

    @classmethod
    async def generate_explanation(
        cls,
        anomaly_type: str,
        detection_method: str,
        score: float,
        comparison: AttendanceComparison,
        history: HistoricalContext,
        raw_explanation: Optional[str] = None
    ) -> str:
        # 1. Deterministic baseline (always computed first)
        deterministic_exp = cls.generate_deterministic_explanation(
            anomaly_type, detection_method, score, comparison, history, raw_explanation
        )

        # 2. Check if an external LLM is configured
        llm_provider = settings.LLM_PROVIDER.lower()
        has_key = bool(
            (llm_provider == "nvidia" and settings.NVIDIA_API_KEY) or
            (llm_provider == "groq" and settings.GROQ_API_KEY) or
            (llm_provider == "gemini" and settings.GEMINI_API_KEY)
        )

        if not has_key:
            return deterministic_exp

        # 3. Attempt LLM refinement if API key exists
        try:
            prompt = (
                f"You are AttendAI Workforce Intelligence Engine. "
                f"Summarize why this attendance anomaly was flagged in exactly 2 concise, executive sentences. "
                f"Use ONLY the verified facts below; do NOT invent reasons or metrics.\n\n"
                f"- Anomaly Type: {anomaly_type}\n"
                f"- Detection Method: {detection_method} (Score: {score})\n"
                f"- Actual Worked: {comparison.actual_worked_minutes}m (Expected: {comparison.expected_worked_minutes}m)\n"
                f"- Actual Overtime: {comparison.actual_overtime_minutes}m\n"
                f"- Actual Late: {comparison.actual_late_minutes}m (Grace: {history.grace_period_minutes}m)\n"
                f"- Assigned Shift: {history.assigned_shift_name} ({history.assigned_shift_hours}h required)\n"
                f"- 30-Day Average Duration: {history.average_worked_minutes_30d}m\n"
                f"- 30-Day Overtime Days: {history.overtime_frequency_30d}\n"
                f"- 30-Day Late Days: {history.late_arrival_frequency_30d}\n"
            )

            # Lazy import to avoid circular dependencies
            import asyncio
            from app.harness.orchestrator import ai_orchestrator
            provider = ai_orchestrator.get_provider()
            resp = await asyncio.wait_for(
                provider.generate_response(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1
                ),
                timeout=3.0
            )
            llm_text = (resp.get("content") or "").strip()
            if llm_text and len(llm_text) > 20 and not llm_text.startswith("{"):
                return llm_text
        except Exception as e:
            logger.debug(f"LLM explanation fallback to deterministic: {e}")

        return deterministic_exp
