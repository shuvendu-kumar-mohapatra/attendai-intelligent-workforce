from typing import Dict, Any, Optional, Set

# Universal permissions matrix strictly mapping AI tools by role
EMPLOYEE_PERSONAL_TOOLS: Set[str] = {
    "get_my_attendance",
    "get_my_attendance_summary",
    "get_my_overtime",
    "get_my_late_arrivals",
    "get_my_working_hours",
    "get_my_leave_balance",
    "get_my_shifts",
    "get_my_attendance_history",
    "get_my_anomalies",
    "search_attendance_policy",
}

ORGANIZATION_WIDE_TOOLS: Set[str] = {
    "query_workforce_attendance",
    "compare_workforce_metrics",
    "query_leave_analytics",
    "get_late_arrivals",
    "get_employee_overtime",
    "get_absenteeism",
    "get_department_analytics",
    "get_workforce_correlations",
    "get_attendance_summary",
    "get_anomaly_reports",
    "get_employee_profile",
    "search_attendance_policy",
}

ALLOWED_TOOLS_BY_ROLE: Dict[str, Set[str]] = {
    "admin": EMPLOYEE_PERSONAL_TOOLS.union(ORGANIZATION_WIDE_TOOLS),
    "hr_manager": EMPLOYEE_PERSONAL_TOOLS.union(ORGANIZATION_WIDE_TOOLS),
    "employee": EMPLOYEE_PERSONAL_TOOLS,
}

class HarnessPermissions:
    @staticmethod
    def is_tool_allowed(role: str, tool_name: str) -> bool:
        allowed = ALLOWED_TOOLS_BY_ROLE.get(role, set())
        return tool_name in allowed

    @staticmethod
    def filter_tools_for_user(role: str, tools: list) -> list:
        allowed = ALLOWED_TOOLS_BY_ROLE.get(role, set())
        return [t for t in tools if t.get("function", {}).get("name") in allowed]
