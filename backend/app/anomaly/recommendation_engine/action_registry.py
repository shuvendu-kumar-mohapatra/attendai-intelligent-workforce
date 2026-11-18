from typing import List, Dict, Any, Optional
from .recommendation_schemas import RecommendedAction, HistoricalContext, AttendanceComparison

class ActionRegistry:
    """
    Standardized corporate corrective action registry.
    Maps detected anomaly patterns to deterministic, actionable, and compliant recommendations.
    Ensures safe, role-scoped actions that require human supervisor or HR authorization.
    """

    @classmethod
    def get_recommendations_for_anomaly(
        cls,
        anomaly_type: str,
        comparison: AttendanceComparison,
        history: HistoricalContext,
        policy_citation: Optional[str] = None
    ) -> List[RecommendedAction]:
        norm_type = anomaly_type.lower().strip()

        if norm_type in ["excessive_overtime", "unusually_long_shift"]:
            return cls._get_overtime_actions(comparison, history, policy_citation)
        elif norm_type in ["repeated_late_arrival", "late_arrival"]:
            return cls._get_late_arrival_actions(comparison, history, policy_citation)
        elif norm_type in ["missing_clock_out", "unclosed_shift"]:
            return cls._get_missing_clock_out_actions(comparison, history, policy_citation)
        elif norm_type in ["abnormal_break_duration", "unusual_break"]:
            return cls._get_break_actions(comparison, history, policy_citation)
        elif norm_type in ["unusual_working_hours", "irregular_hours"]:
            return cls._get_unusual_hours_actions(comparison, history, policy_citation)
        elif norm_type in ["duplicate_attendance", "duplicate_punch"]:
            return cls._get_duplicate_actions(comparison, history, policy_citation)
        elif norm_type in ["unusual_absence_frequency", "chronic_absenteeism"]:
            return cls._get_absence_actions(comparison, history, policy_citation)
        else:
            # Fallback for isolation_forest_outlier or custom multivariate anomalies
            return cls._get_multivariate_outlier_actions(comparison, history, policy_citation)

    @classmethod
    def get_short_recommendation_summary(cls, anomaly_type: str) -> str:
        """
        Returns a concise, standardized one-line corrective action for dashboard tables and cards.
        Deterministic, compliant, and requires zero LLM roundtrips.
        """
        norm_type = (anomaly_type or "").lower().strip()
        if norm_type in ["unusual_working_hours", "irregular_hours", "irregular_working_hours"]:
            return "Verify shift duration and overtime approval"
        elif norm_type in ["excessive_overtime", "unusually_long_shift"]:
            return "Review overtime authorization"
        elif norm_type in ["repeated_late_arrival", "late_arrival", "repeated_late", "late_arrivals"]:
            return "Review shift timing and arrival history"
        elif norm_type in ["missing_clock_out", "missing_punch", "unclosed_shift", "missing_punch_out"]:
            return "Request employee/supervisor verification"
        elif norm_type in ["abnormal_break_duration", "unusual_break", "extended_break"]:
            return "Verify break approval and policy"
        elif norm_type in ["duplicate_attendance", "duplicate_punch", "multiple_clock_in"]:
            return "Review duplicate punch records"
        elif norm_type in ["unusual_absence_frequency", "chronic_absenteeism", "unexcused_absence"]:
            return "Cross-check approved leave records"
        elif "isolation" in norm_type or "multivariate" in norm_type or "outlier" in norm_type:
            return "Review multivariate attendance pattern and supervisor verification"
        return "Review attendance record and shift configuration"

    @classmethod
    def _get_overtime_actions(
        cls, comp: AttendanceComparison, hist: HistoricalContext, citation: Optional[str]
    ) -> List[RecommendedAction]:
        ot_min = comp.actual_overtime_minutes or 0
        repeated = hist.overtime_frequency_30d >= 3
        actions = [
            RecommendedAction(
                id="rec-ot-1",
                title="Verify Manager Overtime Authorization",
                action="Check department manager pre-approval records for the logged overtime duration.",
                reason=f"Employee logged {ot_min} minutes ({round(ot_min / 60, 1)}h) of overtime exceeding standard operational thresholds.",
                expected_outcome="Confirm whether the extra duration was formally scheduled or unapproved.",
                required_authorization="Department Manager",
                action_type="audit_record",
                priority="high",
                confidence_score=0.92,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            ),
            RecommendedAction(
                id="rec-ot-2",
                title="Audit Assigned Shift Duration",
                action=f"Compare actual worked duration with scheduled shift '{hist.assigned_shift_name}' ({hist.assigned_shift_hours}h required).",
                reason="Discrepancies often arise when an employee is rostered to an 8-hour shift while working a 10-hour or 12-hour operational shift.",
                expected_outcome="Correct shift assignment if an outdated or incorrect schedule was applied.",
                required_authorization="HR Operations",
                action_type="verify_shift",
                priority="medium",
                confidence_score=0.88,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            )
        ]

        if repeated:
            actions.append(
                RecommendedAction(
                    id="rec-ot-3",
                    title="Recommend Workload Redistribution",
                    action=f"Conduct workload assessment — employee accumulated overtime across {hist.overtime_frequency_30d} days in the last 30 days ({hist.total_overtime_hours_30d}h total).",
                    reason="Frequent recurring overtime presents employee burnout risks and indicates chronic department under-staffing.",
                    expected_outcome="Reallocate shift coverage across department peers to maintain safe working limits.",
                    required_authorization="HR Manager / Department Head",
                    action_type="policy_review",
                    priority="high",
                    confidence_score=0.90,
                    evidence_completeness="complete",
                    policy_reference=citation,
                    is_automated=False
                )
            )
        else:
            actions.append(
                RecommendedAction(
                    id="rec-ot-3",
                    title="Verify Attendance Punch Precision",
                    action="Confirm actual clock-out timestamp with on-site supervisor or badge access logs.",
                    reason="Accidental late clock-outs can artificially inflate overtime calculations.",
                    expected_outcome="Ensure payroll and attendance records accurately reflect true worked duration.",
                    required_authorization="Immediate Supervisor",
                    action_type="correct_punch",
                    priority="medium",
                    confidence_score=0.82,
                    evidence_completeness="partial",
                    policy_reference=citation,
                    is_automated=False
                )
            )

        return actions

    @classmethod
    def _get_late_arrival_actions(
        cls, comp: AttendanceComparison, hist: HistoricalContext, citation: Optional[str]
    ) -> List[RecommendedAction]:
        late_min = comp.actual_late_minutes or 0
        actions = [
            RecommendedAction(
                id="rec-late-1",
                title="Verify Shift Grace-Period Configuration",
                action=f"Confirm that the standard {hist.grace_period_minutes}-minute grace period for '{hist.assigned_shift_name}' was correctly applied.",
                reason=f"Clock-in was recorded at {comp.clock_in_time or 'past scheduled start'} ({late_min} minutes tardy).",
                expected_outcome="Ensure the punctuality score reflects appropriate grace allowances.",
                required_authorization="Workforce Administrator",
                action_type="verify_shift",
                priority="medium",
                confidence_score=0.91,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            ),
            RecommendedAction(
                id="rec-late-2",
                title="Review Historical Arrival Patterns",
                action=f"Analyze employee's 30-day punctuality profile ({hist.late_arrival_frequency_30d} late arrivals in 30 days).",
                reason="Determines whether this occurrence is an isolated transit delay or part of an established repeated trend.",
                expected_outcome="Classify tardiness as situational exception versus systemic scheduling mismatch.",
                required_authorization="HR Operations",
                action_type="audit_record",
                priority="medium",
                confidence_score=0.89,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            ),
            RecommendedAction(
                id="rec-late-3",
                title="Evaluate Shift Timing Adjustment",
                action="Explore adjusting employee scheduled shift to a flexible start window (e.g. Morning Shift or Staggered Schedule).",
                reason="If commute or caregiving constraints regularly cause minor late arrivals, an adjusted schedule restores 100% punctuality.",
                expected_outcome="Eliminate recurring friction while preserving required operational hours.",
                required_authorization="Department Manager & HR",
                action_type="adjust_schedule",
                priority="low" if hist.late_arrival_frequency_30d < 3 else "high",
                confidence_score=0.86,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            )
        ]

        if hist.late_arrival_frequency_30d >= 3:
            actions.append(
                RecommendedAction(
                    id="rec-late-4",
                    title="Recommend Informal Supervisor Consultation",
                    action="Schedule an informal, supportive check-in between employee and supervisor.",
                    reason=f"Policy flags {hist.late_arrival_frequency_30d} late occurrences in recent tracking window for supportive HR resolution.",
                    expected_outcome="Identify underlying obstacles and document mutual support plan.",
                    required_authorization="Immediate Supervisor",
                    action_type="supervisor_consultation",
                    priority="high",
                    confidence_score=0.94,
                    evidence_completeness="complete",
                    policy_reference=citation,
                    is_automated=False
                )
            )

        return actions

    @classmethod
    def _get_missing_clock_out_actions(
        cls, comp: AttendanceComparison, hist: HistoricalContext, citation: Optional[str]
    ) -> List[RecommendedAction]:
        return [
            RecommendedAction(
                id="rec-mco-1",
                title="Verify Actual Departure Time with Employee/Supervisor",
                action="Send automated or direct verification inquiry to employee and supervisor for actual departure time.",
                reason=f"Clock-in logged at {comp.clock_in_time or '09:00'} on shift date, but departure punch is absent.",
                expected_outcome="Obtain validated clock-out timestamp to close the open attendance record.",
                required_authorization="Immediate Supervisor",
                action_type="correct_punch",
                priority="high",
                confidence_score=0.95,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            ),
            RecommendedAction(
                id="rec-mco-2",
                title="Check for Hardware or Network Logging Glitches",
                action="Inspect biometric device / web portal punch stream for rejected or desynchronized events.",
                reason="Network packet drops or biometric timeout can occasionally prevent timestamp registration.",
                expected_outcome="Verify whether the clock-out event was recorded incorrectly or never submitted.",
                required_authorization="System Admin",
                action_type="audit_record",
                priority="medium",
                confidence_score=0.84,
                evidence_completeness="partial",
                policy_reference=citation,
                is_automated=False
            ),
            RecommendedAction(
                id="rec-mco-3",
                title="Initiate Formal Attendance Correction Request",
                action="Open an authorized Attendance Correction ticket preserving original punch telemetry and audit log trail.",
                reason="Maintains strict compliance auditability while rectifying the missing departure data.",
                expected_outcome="Compliant attendance record without manual administrative overwrites.",
                required_authorization="HR Manager / Supervisor",
                action_type="correct_punch",
                priority="high",
                confidence_score=0.92,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            )
        ]

    @classmethod
    def _get_unusual_hours_actions(
        cls, comp: AttendanceComparison, hist: HistoricalContext, citation: Optional[str]
    ) -> List[RecommendedAction]:
        worked_m = comp.actual_worked_minutes or 0
        avg_m = int(hist.average_worked_minutes_30d) or 480
        return [
            RecommendedAction(
                id="rec-uh-1",
                title="Verify Approved Extended Shift Authorization",
                action="Verify whether an extended or double shift was pre-authorized by department leadership.",
                reason=f"Employee worked {worked_m} minutes compared with their usual working duration of ~{avg_m} minutes.",
                expected_outcome="Establish whether extra duration corresponds to legitimate emergency project coverage.",
                required_authorization="Department Manager",
                action_type="audit_record",
                priority="high",
                confidence_score=0.90,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            ),
            RecommendedAction(
                id="rec-uh-2",
                title="Check Assigned Shift Roster Duration",
                action=f"Inspect shift calendar for '{hist.assigned_shift_name}' on anomaly date.",
                reason="Temporary shift swaps or roster adjustments might not have synced with the core attendance schedule.",
                expected_outcome="Synchronize shift assignment with employee's actual working duty roster.",
                required_authorization="HR Operations",
                action_type="verify_shift",
                priority="medium",
                confidence_score=0.87,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            ),
            RecommendedAction(
                id="rec-uh-3",
                title="Confirm Punch Accuracy with Supervisor",
                action="Confirm clock-in and clock-out timestamps directly with on-duty supervisor.",
                reason="Ensures recorded times reflect active duty rather than unrecorded breaks or delayed departures.",
                expected_outcome="Accurate, validated attendance duration.",
                required_authorization="Immediate Supervisor",
                action_type="correct_punch",
                priority="medium",
                confidence_score=0.85,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            )
        ]

    @classmethod
    def _get_break_actions(
        cls, comp: AttendanceComparison, hist: HistoricalContext, citation: Optional[str]
    ) -> List[RecommendedAction]:
        b_min = comp.actual_break_minutes or 0
        return [
            RecommendedAction(
                id="rec-brk-1",
                title="Verify Extended Break Pre-Approval",
                action="Check whether employee submitted an off-site medical, personal, or administrative break request.",
                reason=f"Cumulative break duration of {b_min} minutes exceeds the standard 60-120 minute operational allowance.",
                expected_outcome="Correlate break duration with formal supervisory or HR permission.",
                required_authorization="Immediate Supervisor",
                action_type="audit_record",
                priority="medium",
                confidence_score=0.88,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            ),
            RecommendedAction(
                id="rec-brk-2",
                title="Compare with Historical Break Habits",
                action="Evaluate historical break logs over the past 30 days.",
                reason="Determines whether this is an exceptional personal emergency or an ongoing scheduling trend.",
                expected_outcome="Contextualize variance before undertaking any corrective dialogue.",
                required_authorization="HR Operations",
                action_type="audit_record",
                priority="low",
                confidence_score=0.83,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            ),
            RecommendedAction(
                id="rec-brk-3",
                title="Review Shift & Rest Period Policy Configuration",
                action="Review shift break parameters to ensure scheduled break windows fit current department operational tempo.",
                reason="Operational demands may require updated break schedules for high-volume customer teams.",
                expected_outcome="Updated break configuration aligned with labor regulations and team needs.",
                required_authorization="HR Manager",
                action_type="policy_review",
                priority="medium",
                confidence_score=0.86,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            )
        ]

    @classmethod
    def _get_duplicate_actions(
        cls, comp: AttendanceComparison, hist: HistoricalContext, citation: Optional[str]
    ) -> List[RecommendedAction]:
        return [
            RecommendedAction(
                id="rec-dup-1",
                title="Identify Duplicate Telemetry Punches",
                action="Inspect biometric terminal and web portal event stream for rapid successive clock-ins/outs.",
                reason="Employees double-tapping biometric sensors or double-clicking submit buttons can generate redundant punches.",
                expected_outcome="Isolate redundant event timestamps from authentic shift transitions.",
                required_authorization="System Admin",
                action_type="audit_record",
                priority="high",
                confidence_score=0.96,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            ),
            RecommendedAction(
                id="rec-dup-2",
                title="Execute Authorized Punch Deduplication Workflow",
                action="Void redundant timestamp record while keeping the valid initial punch and preserving audit logs.",
                reason="Prevents skewed worked hour totals and eliminates false duplicate record flags.",
                expected_outcome="Single clean attendance entry for the operational day.",
                required_authorization="HR Manager",
                action_type="correct_punch",
                priority="high",
                confidence_score=0.94,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            )
        ]

    @classmethod
    def _get_absence_actions(
        cls, comp: AttendanceComparison, hist: HistoricalContext, citation: Optional[str]
    ) -> List[RecommendedAction]:
        return [
            RecommendedAction(
                id="rec-abs-1",
                title="Reconcile with Approved Leave Applications",
                action="Cross-reference absence date against submitted and approved annual, sick, or casual leave requests.",
                reason="Unprocessed or recently submitted leave forms can cause false absenteeism flags in attendance ledgers.",
                expected_outcome="Ensure approved time off is formally linked to the daily schedule.",
                required_authorization="HR Leave Administrator",
                action_type="audit_record",
                priority="high",
                confidence_score=0.92,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            ),
            RecommendedAction(
                id="rec-abs-2",
                title="Verify On-Duty Status (Supportive Inquiry)",
                action="Conduct a supportive, confidential inquiry with employee and supervisor — do NOT assume misconduct.",
                reason="Absences may stem from urgent family emergencies, medical conditions, or off-site client meetings.",
                expected_outcome="Clarify employee welfare and document legitimate retrospective leave where justified.",
                required_authorization="HR Manager",
                action_type="supervisor_consultation",
                priority="medium",
                confidence_score=0.88,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            )
        ]

    @classmethod
    def _get_multivariate_outlier_actions(
        cls, comp: AttendanceComparison, hist: HistoricalContext, citation: Optional[str]
    ) -> List[RecommendedAction]:
        return [
            RecommendedAction(
                id="rec-ml-1",
                title="Review Multivariate Attendance Profile",
                action="Review the combination of worked hours, overtime, and punctuality against employee's 30-day baseline.",
                reason="Isolation Forest identified this record as a statistical outlier across multidimensional features.",
                expected_outcome="Determine whether the outlier represents high productivity, shift misalignment, or data entry error.",
                required_authorization="HR Manager",
                action_type="audit_record",
                priority="high",
                confidence_score=0.89,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            ),
            RecommendedAction(
                id="rec-ml-2",
                title="Verify Shift Schedule Adherence",
                action=f"Compare actual timestamps with scheduled shift '{hist.assigned_shift_name}'.",
                reason="Multivariate deviations frequently occur when employees work off-schedule without an updated roster entry.",
                expected_outcome="Align roster configuration with operational reality.",
                required_authorization="Department Manager",
                action_type="verify_shift",
                priority="medium",
                confidence_score=0.85,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            ),
            RecommendedAction(
                id="rec-ml-3",
                title="Confirm Record Integrity with Supervisor",
                action="Confirm attendance accuracy with supervisor and resolve or dismiss the statistical flag.",
                reason="Ensures anomalies flagged by machine learning receive explicit human investigation.",
                expected_outcome="Formal resolution documented in audit records.",
                required_authorization="Supervisor / HR",
                action_type="supervisor_consultation",
                priority="medium",
                confidence_score=0.87,
                evidence_completeness="complete",
                policy_reference=citation,
                is_automated=False
            )
        ]
