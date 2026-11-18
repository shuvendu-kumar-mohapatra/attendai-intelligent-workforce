from typing import Optional, Dict, Any

class PolicyContextRegistry:
    """
    Associates detected workforce anomalies with authoritative corporate policies.
    Provides verifiable citations with section headers and page references.
    """

    POLICY_MAP: Dict[str, Dict[str, Any]] = {
        "excessive_overtime": {
            "policy_title": "AttendAI Global Attendance and Working Hours Policy",
            "section": "Section 3: Overtime Rules and Eligibility",
            "page_number": 2,
            "rule_summary": "Overtime commences once total worked duration in a calendar day exceeds the scheduled required shift hours (8.0 hours). Overtime must be pre-authorized by department managers.",
            "citation": "AttendAI Global Attendance Policy (Page 2, Section 3: Overtime Rules)"
        },
        "unusually_long_shift": {
            "policy_title": "AttendAI Global Attendance and Working Hours Policy",
            "section": "Section 1: Core Working Hours",
            "page_number": 1,
            "rule_summary": "A standard working day consists of 8 productive hours plus a 30-minute to 1-hour lunch break. Shifts exceeding 12 hours require strict fatigue compliance authorization.",
            "citation": "AttendAI Global Attendance Policy (Page 1, Section 1: Core Working Hours)"
        },
        "unusual_working_hours": {
            "policy_title": "AttendAI Global Attendance and Working Hours Policy",
            "section": "Section 1: Core Working Hours",
            "page_number": 1,
            "rule_summary": "AttendAI core working hours are established between 09:00 and 17:30 local time. Employees are expected to clock in and out using the portal upon duty changes.",
            "citation": "AttendAI Global Attendance Policy (Page 1, Section 1: Core Working Hours)"
        },
        "repeated_late_arrival": {
            "policy_title": "AttendAI Global Attendance and Working Hours Policy",
            "section": "Section 2: Punctuality and Grace Periods",
            "page_number": 1,
            "rule_summary": "A grace period of 15 minutes is allowed for clock-in beyond scheduled shift start. Clock-ins occurring 16 minutes or more after shift start are flagged as Late Arrivals. Repeated tardiness exceeding 3 occurrences in 7 days is surfaced for HR review.",
            "citation": "AttendAI Global Attendance Policy (Page 1, Section 2: Punctuality and Grace Periods)"
        },
        "missing_clock_out": {
            "policy_title": "AttendAI Global Attendance and Working Hours Policy",
            "section": "Section 1: Core Working Hours",
            "page_number": 1,
            "rule_summary": "Employees are required to clock out via the AttendAI portal upon concluding their daily shift. Unrecorded departure punches require supervisor verification and an attendance correction workflow.",
            "citation": "AttendAI Global Attendance Policy (Page 1, Section 1: Clock-In/Out Compliance)"
        },
        "abnormal_break_duration": {
            "policy_title": "AttendAI Global Attendance and Working Hours Policy",
            "section": "Section 1: Core Working Hours",
            "page_number": 1,
            "rule_summary": "Standard daily break allowance consists of a 30-minute to 1-hour lunch break plus designated rest periods. Cumulative breaks exceeding 120 minutes require supervisory concurrence.",
            "citation": "AttendAI Global Attendance Policy (Page 1, Section 1: Break Allocations)"
        },
        "unusual_absence_frequency": {
            "policy_title": "Comprehensive Leave and Time-Off Guidelines",
            "section": "Section 2: Sick and Emergency Leave",
            "page_number": 2,
            "rule_summary": "Employees are granted paid sick and emergency leave. Medical certificates are required for consecutive absences exceeding 3 business days. Unscheduled absences must be validated against approved leave records.",
            "citation": "Comprehensive Leave Guidelines (Page 2, Section 2: Sick and Emergency Leave)"
        },
        "duplicate_attendance": {
            "policy_title": "AttendAI Global Attendance and Working Hours Policy",
            "section": "Section 1: Core Working Hours",
            "page_number": 1,
            "rule_summary": "Daily attendance entries are unique per calendar day and shift. Duplicate punches must be audited and adjusted through the authorized correction request workflow.",
            "citation": "AttendAI Global Attendance Policy (Page 1, Section 1: Punch Auditing)"
        },
        "isolation_forest_outlier": {
            "policy_title": "AttendAI Global Attendance and Working Hours Policy",
            "section": "Section 1 & 2: Shift Standards",
            "page_number": 1,
            "rule_summary": "Attendance telemetry deviating significantly from established multivariate baseline patterns requires supervisor review to confirm shift adherence and logging accuracy.",
            "citation": "AttendAI Global Attendance Policy (Page 1: Shift Compliance Standards)"
        }
    }

    @classmethod
    def get_policy_context(cls, anomaly_type: str) -> Optional[Dict[str, Any]]:
        # Normalize anomaly type
        normalized = anomaly_type.lower().strip()
        if normalized in cls.POLICY_MAP:
            return cls.POLICY_MAP[normalized]
        for k, v in cls.POLICY_MAP.items():
            if k in normalized or normalized in k:
                return v
        return None
