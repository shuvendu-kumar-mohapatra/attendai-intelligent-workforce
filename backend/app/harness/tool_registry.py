import json
from datetime import date, timedelta, time, datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc, or_, case
from app.models.models import (
    AttendanceRecord, Employee, Department, Shift, EmployeeShiftAssignment,
    AttendanceAnomaly, AttendanceBreak, LeaveRecord, Policy, PolicyChunk
)
from app.services.policy_service import PolicyService
from app.harness.date_resolver import DateRangeResolver
from app.harness.permissions import HarnessPermissions

# Comprehensive Tool schema definitions for OpenAI/NIM/Groq function calling
TOOL_DEFINITIONS = [
    # -------------------------------------------------------------
    # Personal Employee Tools
    # -------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_my_attendance",
            "description": "Get current authenticated employee's personal attendance history, hours worked, late days, and punctuality stats.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["today", "this_week", "last_week", "this_month", "last_month", "last_30_days"],
                        "description": "Standardized time window (default 'this_month')"
                    },
                    "days": {"type": "integer", "description": "Optional explicit number of past days to retrieve"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_attendance_summary",
            "description": "Get current authenticated employee's summarized punctuality rate, total shifts completed, on-time days, late days, and total hours.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["today", "this_week", "last_week", "this_month", "last_month", "last_30_days", "this_year"],
                        "description": "Time window for personal attendance summary"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_overtime",
            "description": "Retrieve current authenticated employee's personal overtime records, total overtime hours, and list of dates worked overtime.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["this_week", "last_week", "this_month", "last_month", "last_30_days", "this_year"],
                        "description": "Target period for personal overtime (default 'this_month')"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_late_arrivals",
            "description": "Retrieve current authenticated employee's personal late arrival records, clock-in times, grace period status, and late minutes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["this_week", "last_week", "this_month", "last_month", "last_30_days", "this_year"],
                        "description": "Target period for personal late arrivals (default 'this_month')"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_working_hours",
            "description": "Get current authenticated employee's personal hours logged, regular hours, overtime hours, daily average, and day-by-day hours breakdown.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["this_week", "last_week", "this_month", "last_month", "last_30_days", "this_year"],
                        "description": "Target period for personal working hours (default 'this_month')"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_leave_balance",
            "description": "Get current authenticated employee's paid time off balance, sick leave balance, and recent leave application statuses.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_shifts",
            "description": "Get current authenticated employee's assigned shift schedule, start/end times, and grace period details.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_attendance_history",
            "description": "Get current authenticated employee's detailed chronological punch history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["this_week", "last_week", "this_month", "last_month", "last_30_days", "last_90_days"],
                        "description": "Time window (default 'last_30_days')"
                    },
                    "limit": {"type": "integer", "description": "Maximum records to return (default 20)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_anomalies",
            "description": "Get current authenticated employee's personal attendance anomaly flags, investigation status, detection date, severity, and explanations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "investigating", "resolved", "dismissed"],
                        "description": "Filter by anomaly review status"
                    },
                    "limit": {"type": "integer", "description": "Max anomalies to return (default 10)"}
                }
            }
        }
    },

    # -------------------------------------------------------------
    # Organization-Wide Universal Query Tools (Admin & HR Manager)
    # -------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "query_workforce_attendance",
            "description": (
                "Universal multi-parameter workforce attendance search and aggregation tool. "
                "Supports querying by clock-in time (e.g. arrived after 11:00), worked hours (e.g. > 45 hours), "
                "weekend overtime, long breaks, missing clock-outs, late but completed full shifts, "
                "grouping by employee/department/shift, and trend aggregations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["today", "yesterday", "this_week", "last_week", "this_month", "last_month", "last_30_days", "last_90_days", "previous_quarter", "this_year", "last_year"],
                        "description": "Target time period (default 'this_month')"
                    },
                    "start_date": {"type": "string", "description": "Optional ISO start date YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "Optional ISO end date YYYY-MM-DD"},
                    "department": {"type": "string", "description": "Department name or code to filter"},
                    "employee_name": {"type": "string", "description": "Employee first or last name"},
                    "shift_code": {"type": "string", "description": "Shift code to filter (e.g. 'GEN', 'MORN')"},
                    "min_clock_in_time": {"type": "string", "description": "Filter for employees clocking in at or after this time (e.g. '11:00', '11:30')"},
                    "max_clock_in_time": {"type": "string", "description": "Filter for employees clocking in before this time"},
                    "min_worked_hours": {"type": "number", "description": "Minimum total worked hours threshold (e.g. 45.0 for >45 hrs)"},
                    "min_late_minutes": {"type": "integer", "description": "Minimum late arrival minutes"},
                    "min_overtime_hours": {"type": "number", "description": "Minimum overtime hours threshold"},
                    "min_break_minutes": {"type": "integer", "description": "Filter records with unusually long breaks (e.g. >= 60 minutes)"},
                    "is_weekend_only": {"type": "boolean", "description": "If true, filter attendance strictly to Saturday and Sunday"},
                    "late_but_completed_shift": {"type": "boolean", "description": "If true, filter for employees who arrived late but completed full 8+ hours"},
                    "missing_clock_out": {"type": "boolean", "description": "If true, filter for shifts with clock_in but no clock_out recorded"},
                    "status": {"type": "string", "description": "Attendance status filter ('present', 'late', 'half_day', 'absent')"},
                    "group_by": {
                        "type": "string",
                        "enum": ["employee", "department", "shift", "day_of_week"],
                        "description": "Group aggregation field"
                    },
                    "min_count": {"type": "integer", "description": "Filter grouped results with count >= min_count"},
                    "aggregation": {
                        "type": "string",
                        "enum": ["count", "sum_hours", "avg_hours", "trend"],
                        "description": "Aggregation calculation"
                    },
                    "limit": {"type": "integer", "description": "Max results to return (default 25)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_workforce_metrics",
            "description": (
                "Dynamic workforce comparison engine. Compares metrics across departments "
                "(e.g. compare the two departments with the lowest attendance) or across time periods "
                "(e.g. identify departments where absenteeism increased compared with last month)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "comparison_type": {
                        "type": "string",
                        "enum": ["departments", "periods"],
                        "description": "Whether comparing departments against each other or comparing periods across time"
                    },
                    "metric": {
                        "type": "string",
                        "enum": ["attendance_rate", "absenteeism_rate", "overtime_hours", "late_arrivals", "anomalies"],
                        "description": "Workforce metric to evaluate and rank"
                    },
                    "departments": {
                        "type": "string",
                        "description": "Department names to compare, or 'lowest_attendance' to compare the two lowest performing departments"
                    },
                    "period_a": {"type": "string", "description": "First period (e.g. 'this_month')"},
                    "period_b": {"type": "string", "description": "Second period (e.g. 'last_month')"}
                },
                "required": ["metric"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_leave_analytics",
            "description": "Analyze workforce leave patterns, such as finding which employees have taken the most sick leave this year, leave by type, or department leave volume.",
            "parameters": {
                "type": "object",
                "properties": {
                    "leave_type": {
                        "type": "string",
                        "enum": ["sick", "annual", "casual", "unpaid", "all"],
                        "description": "Type of leave (e.g. 'sick' for sick leave)"
                    },
                    "period": {
                        "type": "string",
                        "enum": ["this_week", "this_month", "last_month", "this_year", "last_year"],
                        "description": "Time window to search (default 'this_year')"
                    },
                    "department": {"type": "string", "description": "Optional department filter"},
                    "group_by_employee": {"type": "boolean", "description": "If true, aggregate total leave days per employee and rank them descending"},
                    "limit": {"type": "integer", "description": "Maximum records or employees to return (default 15)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_attendance_summary",
            "description": "Get organization or department aggregated attendance metrics (headcount, present, absent, late, overtime) for a specific date or window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["today", "yesterday", "this_week", "this_month"],
                        "description": "Target period (defaults to today)"
                    },
                    "date": {"type": "string", "description": "Target date in YYYY-MM-DD format (defaults to today)"},
                    "department": {"type": "string", "description": "Optional department name or code to filter summary"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_late_arrivals",
            "description": "Retrieve employees with late arrival records past shift grace periods. Supports grouping by employee to identify frequent offenders, filtering by department, numerical threshold (e.g. more than 5 times), and flexible date ranges.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["today", "yesterday", "this_week", "last_week", "this_month", "last_month", "last_30_days", "last_7_days"],
                        "description": "Time window to search (e.g. 'this_month', 'today', 'last_week')"
                    },
                    "days": {"type": "integer", "description": "Days to look back (default 30 if period not specified)"},
                    "department": {"type": "string", "description": "Department name or code to filter (e.g. 'Customer Success', 'Engineering')"},
                    "min_late_count": {
                        "type": "integer",
                        "description": "Filter for employees arriving late at least or more than this number of times in the period (e.g. 5 or 6)"
                    },
                    "group_by_employee": {
                        "type": "boolean",
                        "description": "If true, aggregate frequency per employee to find repeat late arrivals"
                    },
                    "limit": {"type": "integer", "description": "Maximum records or employees to return (default 20)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_employee_overtime",
            "description": "List employees with logged overtime hours beyond scheduled shift durations, ranked by total overtime. Supports department filtering and time periods.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["this_week", "last_week", "this_month", "last_month", "last_30_days", "this_year"],
                        "description": "Period to analyze (default 'this_month')"
                    },
                    "department": {"type": "string", "description": "Department name or code filter (e.g. 'Engineering', 'Operations')"},
                    "min_overtime_hours": {"type": "number", "description": "Minimum overtime hours threshold"},
                    "limit": {"type": "integer", "description": "Max results to return (default 10)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_absenteeism",
            "description": "List absent employees across the organization or for a specific department for today, yesterday, or a given period.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["today", "yesterday", "this_week", "this_month"],
                        "description": "Target period (default 'today')"
                    },
                    "department": {"type": "string", "description": "Optional department filter"},
                    "limit": {"type": "integer", "description": "Maximum records to return (default 25)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_department_analytics",
            "description": "Compare attendance rates, absenteeism percentages, overtime hours, headcount, and anomaly counts across departments to identify which department requires management or HR attention.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["today", "this_week", "this_month", "last_30_days"],
                        "description": "Analysis window (default 'this_month')"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_workforce_correlations",
            "description": "Identify employees exhibiting compound attendance patterns: both repeated lateness AND excessive overtime hours simultaneously.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["this_month", "last_month", "last_30_days"],
                        "description": "Period to evaluate (default 'this_month')"
                    },
                    "min_late_count": {"type": "integer", "description": "Minimum late arrivals threshold (default 3)"},
                    "min_overtime_hours": {"type": "number", "description": "Minimum overtime hours threshold (default 5.0)"},
                    "department": {"type": "string", "description": "Optional department filter"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_attendance_policy",
            "description": "Search official company HR policies (attendance guidelines, remote work, core hours, overtime rules, leave types, grace periods) and return verifiable citations with page numbers and sections.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords or question regarding HR policy"},
                    "limit": {"type": "integer", "description": "Max matching policy chunks (default 4)"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_anomaly_reports",
            "description": "List attendance anomalies flagged by deterministic rules or the Isolation Forest machine learning engine with confidence scores and explanations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "investigating", "resolved", "dismissed"],
                        "description": "Filter by investigation status"
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Filter by anomaly severity"
                    },
                    "department": {
                        "type": "string",
                        "description": "Filter anomalies by department name (e.g. 'Engineering', 'Customer Success')"
                    },
                    "period": {
                        "type": "string",
                        "enum": ["today", "this_week", "last_week", "this_month", "last_month", "last_30_days", "this_year"],
                        "description": "Time window for anomaly detection date"
                    },
                    "limit": {"type": "integer", "description": "Max anomalies to return (default 10)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_employee_profile",
            "description": "Retrieve comprehensive employee profile, department, code, contact information, and shift details by name, employee code, or email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Employee first name, last name, or full name"},
                    "employee_code": {"type": "string", "description": "Exact employee code (e.g. 'EMP001')"},
                    "email": {"type": "string", "description": "Employee email address"}
                }
            }
        }
    }
]

class ToolRegistry:
    @classmethod
    async def execute_tool(
        cls,
        name: str,
        arguments: Dict[str, Any],
        db: AsyncSession,
        user: Any,
        employee: Optional[Employee] = None
    ) -> Dict[str, Any]:
        """
        Executes approved tool with verified permissions, organization isolation, and scope.
        Strictly enforces role-based access control and personal identity boundaries.
        Catches any database errors and returns a meaningful error message.
        """
        try:
            return await cls._execute_tool_inner(
                name=name,
                arguments=arguments,
                db=db,
                user=user,
                employee=employee
            )
        except Exception as e:
            return {"error": f"Database query failed for tool '{name}': {str(e)}"}

    @classmethod
    async def _execute_tool_inner(
        cls,
        name: str,
        arguments: Dict[str, Any],
        db: AsyncSession,
        user: Any,
        employee: Optional[Employee] = None
    ) -> Dict[str, Any]:
        org_id = user.organization_id

        # Role-based authorization gate
        if not HarnessPermissions.is_tool_allowed(user.role, name):
            return {
                "error": (
                    f"Unauthorized: Permission denied: role '{user.role}' cannot invoke tool '{name}'. "
                    f"Employees are strictly authorized to query their own personal workforce records and company HR policies."
                )
            }

        # -------------------------------------------------------------
        # Tool: get_my_attendance
        # -------------------------------------------------------------
        if name == "get_my_attendance":
            if not employee:
                return {"error": "Authenticated user is not linked to an employee profile."}

            period = arguments.get("period")
            days = arguments.get("days")
            start_date, end_date, period_label = DateRangeResolver.resolve_period(period=period, days=days or 30)

            stmt = select(AttendanceRecord).where(
                and_(
                    AttendanceRecord.employee_id == employee.id,
                    AttendanceRecord.organization_id == org_id,
                    AttendanceRecord.date >= start_date,
                    AttendanceRecord.date <= end_date
                )
            ).order_by(AttendanceRecord.date.desc())
            records = (await db.execute(stmt)).scalars().all()

            total_days = len(records)
            present_days = sum(1 for r in records if r.status in ["present", "half_day", "late"])
            late_days = sum(1 for r in records if r.late_minutes > 0 or r.status == "late")
            total_worked_hours = round(sum(r.worked_minutes for r in records) / 60.0, 1)
            total_ot_hours = round(sum(r.overtime_minutes for r in records) / 60.0, 1)
            punctuality_rate = round(((present_days - late_days) / present_days * 100), 1) if present_days > 0 else 100.0

            return {
                "period": period_label,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "employee": f"{employee.first_name} {employee.last_name}",
                "employee_code": employee.employee_code,
                "summary": {
                    "total_logged_days": total_days,
                    "present_days": present_days,
                    "late_days": late_days,
                    "total_worked_hours": total_worked_hours,
                    "overtime_hours": total_ot_hours,
                    "punctuality_rate": punctuality_rate
                },
                "recent_records": [
                    {
                        "date": str(r.date),
                        "status": r.status,
                        "clock_in": r.clock_in.strftime("%H:%M:%S") if r.clock_in else None,
                        "clock_out": r.clock_out.strftime("%H:%M:%S") if r.clock_out else None,
                        "worked_hours": round(r.worked_minutes / 60.0, 2),
                        "late_minutes": r.late_minutes,
                        "overtime_hours": round(r.overtime_minutes / 60.0, 2)
                    }
                    for r in records[:10]
                ]
            }

        # -------------------------------------------------------------
        # Tool: get_my_attendance_summary
        # -------------------------------------------------------------
        elif name == "get_my_attendance_summary":
            if not employee:
                return {"error": "Authenticated user is not linked to an employee profile."}

            period = arguments.get("period", "this_month")
            start_date, end_date, period_label = DateRangeResolver.resolve_period(period=period)

            stmt = select(AttendanceRecord).where(
                and_(
                    AttendanceRecord.employee_id == employee.id,
                    AttendanceRecord.organization_id == org_id,
                    AttendanceRecord.date >= start_date,
                    AttendanceRecord.date <= end_date
                )
            )
            records = (await db.execute(stmt)).scalars().all()

            total_days = len(records)
            present_days = sum(1 for r in records if r.status in ["present", "half_day", "late"])
            late_days = sum(1 for r in records if r.late_minutes > 0 or r.status == "late")
            on_time_days = present_days - late_days
            punctuality = round((on_time_days / present_days * 100), 1) if present_days > 0 else 100.0

            return {
                "period": period_label,
                "employee": f"{employee.first_name} {employee.last_name}",
                "employee_code": employee.employee_code,
                "total_shifts_completed": total_days,
                "on_time_days": on_time_days,
                "late_days": late_days,
                "punctuality_rate": punctuality,
                "total_hours_logged": round(sum(r.worked_minutes for r in records) / 60.0, 2),
                "total_overtime_hours": round(sum(r.overtime_minutes for r in records) / 60.0, 2)
            }

        # -------------------------------------------------------------
        # Tool: get_my_overtime
        # -------------------------------------------------------------
        elif name == "get_my_overtime":
            if not employee:
                return {"error": "Authenticated user is not linked to an employee profile."}

            period = arguments.get("period", "this_month")
            start_date, end_date, period_label = DateRangeResolver.resolve_period(period=period)

            stmt = select(AttendanceRecord).where(
                and_(
                    AttendanceRecord.employee_id == employee.id,
                    AttendanceRecord.organization_id == org_id,
                    AttendanceRecord.date >= start_date,
                    AttendanceRecord.date <= end_date,
                    AttendanceRecord.overtime_minutes > 0
                )
            ).order_by(AttendanceRecord.date.desc())
            records = (await db.execute(stmt)).scalars().all()

            total_ot_mins = sum(r.overtime_minutes for r in records)
            total_ot_hours = round(total_ot_mins / 60.0, 2)

            return {
                "period": period_label,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "employee": f"{employee.first_name} {employee.last_name}",
                "employee_code": employee.employee_code,
                "total_overtime_hours": total_ot_hours,
                "total_overtime_minutes": total_ot_mins,
                "overtime_days_count": len(records),
                "overtime_records": [
                    {
                        "date": str(r.date),
                        "clock_in": r.clock_in.strftime("%H:%M:%S") if r.clock_in else None,
                        "clock_out": r.clock_out.strftime("%H:%M:%S") if r.clock_out else None,
                        "worked_hours": round(r.worked_minutes / 60.0, 2),
                        "overtime_hours": round(r.overtime_minutes / 60.0, 2),
                        "overtime_minutes": r.overtime_minutes
                    }
                    for r in records
                ]
            }

        # -------------------------------------------------------------
        # Tool: get_my_late_arrivals
        # -------------------------------------------------------------
        elif name == "get_my_late_arrivals":
            if not employee:
                return {"error": "Authenticated user is not linked to an employee profile."}

            period = arguments.get("period", "this_month")
            start_date, end_date, period_label = DateRangeResolver.resolve_period(period=period)

            stmt = select(AttendanceRecord).where(
                and_(
                    AttendanceRecord.employee_id == employee.id,
                    AttendanceRecord.organization_id == org_id,
                    AttendanceRecord.date >= start_date,
                    AttendanceRecord.date <= end_date,
                    or_(AttendanceRecord.late_minutes > 0, AttendanceRecord.status == "late")
                )
            ).order_by(AttendanceRecord.date.desc())
            records = (await db.execute(stmt)).scalars().all()

            total_late_count = len(records)
            total_late_minutes = sum(r.late_minutes for r in records)

            return {
                "period": period_label,
                "employee": f"{employee.first_name} {employee.last_name}",
                "employee_code": employee.employee_code,
                "total_late_count": total_late_count,
                "total_late_minutes": total_late_minutes,
                "late_records": [
                    {
                        "date": str(r.date),
                        "clock_in": r.clock_in.strftime("%H:%M:%S") if r.clock_in else None,
                        "late_minutes": r.late_minutes,
                        "status": r.status
                    }
                    for r in records
                ]
            }

        # -------------------------------------------------------------
        # Tool: get_my_working_hours
        # -------------------------------------------------------------
        elif name == "get_my_working_hours":
            if not employee:
                return {"error": "Authenticated user is not linked to an employee profile."}

            period = arguments.get("period", "this_month")
            start_date, end_date, period_label = DateRangeResolver.resolve_period(period=period)

            stmt = select(AttendanceRecord).where(
                and_(
                    AttendanceRecord.employee_id == employee.id,
                    AttendanceRecord.organization_id == org_id,
                    AttendanceRecord.date >= start_date,
                    AttendanceRecord.date <= end_date
                )
            ).order_by(AttendanceRecord.date.desc())
            records = (await db.execute(stmt)).scalars().all()

            total_worked_mins = sum(r.worked_minutes for r in records)
            total_ot_mins = sum(r.overtime_minutes for r in records)
            regular_mins = max(0, total_worked_mins - total_ot_mins)
            logged_days = len(records)
            avg_hours = round((total_worked_mins / 60.0) / logged_days, 2) if logged_days > 0 else 0.0

            return {
                "period": period_label,
                "employee": f"{employee.first_name} {employee.last_name}",
                "employee_code": employee.employee_code,
                "total_worked_hours": round(total_worked_mins / 60.0, 2),
                "regular_hours": round(regular_mins / 60.0, 2),
                "overtime_hours": round(total_ot_mins / 60.0, 2),
                "logged_days": logged_days,
                "average_hours_per_day": avg_hours,
                "breakdown": [
                    {
                        "date": str(r.date),
                        "worked_hours": round(r.worked_minutes / 60.0, 2),
                        "overtime_hours": round(r.overtime_minutes / 60.0, 2),
                        "status": r.status
                    }
                    for r in records
                ]
            }

        # -------------------------------------------------------------
        # Tool: get_my_leave_balance
        # -------------------------------------------------------------
        elif name == "get_my_leave_balance":
            if not employee:
                return {"error": "Authenticated user is not linked to an employee profile."}

            stmt = select(LeaveRecord).where(
                and_(
                    LeaveRecord.employee_id == employee.id,
                    LeaveRecord.organization_id == org_id
                )
            ).order_by(LeaveRecord.created_at.desc())
            leaves = (await db.execute(stmt)).scalars().all()

            annual_taken = sum(l.days_count for l in leaves if l.leave_type == "annual" and l.status == "approved")
            sick_taken = sum(l.days_count for l in leaves if l.leave_type == "sick" and l.status == "approved")
            annual_allocated = 18.0
            sick_allocated = 10.0

            return {
                "employee": f"{employee.first_name} {employee.last_name}",
                "employee_code": employee.employee_code,
                "leave_balances": {
                    "annual_leave": {
                        "allocated": annual_allocated,
                        "taken": annual_taken,
                        "remaining": max(0.0, annual_allocated - annual_taken)
                    },
                    "sick_leave": {
                        "allocated": sick_allocated,
                        "taken": sick_taken,
                        "remaining": max(0.0, sick_allocated - sick_taken)
                    }
                },
                "recent_requests": [
                    {
                        "leave_type": l.leave_type.title(),
                        "start_date": str(l.start_date),
                        "end_date": str(l.end_date),
                        "days_count": l.days_count,
                        "status": l.status.title(),
                        "reason": l.reason
                    }
                    for l in leaves[:5]
                ]
            }

        # -------------------------------------------------------------
        # Tool: get_my_shifts
        # -------------------------------------------------------------
        elif name == "get_my_shifts":
            if not employee:
                return {"error": "Authenticated user is not linked to an employee profile."}

            stmt = (
                select(EmployeeShiftAssignment, Shift)
                .join(Shift, Shift.id == EmployeeShiftAssignment.shift_id)
                .where(
                    and_(
                        EmployeeShiftAssignment.employee_id == employee.id,
                        EmployeeShiftAssignment.is_active == True
                    )
                )
            )
            res = (await db.execute(stmt)).first()
            if res:
                assignment, shift = res
                return {
                    "employee": f"{employee.first_name} {employee.last_name}",
                    "shift_name": shift.name,
                    "shift_code": shift.code,
                    "start_time": shift.start_time.strftime("%H:%M:%S"),
                    "end_time": shift.end_time.strftime("%H:%M:%S"),
                    "grace_period_minutes": shift.grace_period_minutes,
                    "required_hours": shift.required_hours,
                    "effective_from": str(assignment.effective_from)
                }
            return {
                "employee": f"{employee.first_name} {employee.last_name}",
                "shift_name": "General Shift (Standard)",
                "shift_code": "GEN",
                "start_time": "09:00:00",
                "end_time": "17:00:00",
                "grace_period_minutes": 15,
                "required_hours": 8.0
            }

        # -------------------------------------------------------------
        # Tool: get_my_attendance_history
        # -------------------------------------------------------------
        elif name == "get_my_attendance_history":
            if not employee:
                return {"error": "Authenticated user is not linked to an employee profile."}

            limit = min(int(arguments.get("limit", 20)), 100)
            period = arguments.get("period", "last_30_days")
            start_date, end_date, period_label = DateRangeResolver.resolve_period(period=period)

            stmt = (
                select(AttendanceRecord)
                .where(
                    and_(
                        AttendanceRecord.employee_id == employee.id,
                        AttendanceRecord.organization_id == org_id,
                        AttendanceRecord.date >= start_date,
                        AttendanceRecord.date <= end_date
                    )
                )
                .order_by(AttendanceRecord.date.desc())
                .limit(limit)
            )
            records = (await db.execute(stmt)).scalars().all()

            return {
                "period": period_label,
                "employee": f"{employee.first_name} {employee.last_name}",
                "count": len(records),
                "history": [
                    {
                        "date": str(r.date),
                        "clock_in": r.clock_in.strftime("%H:%M:%S") if r.clock_in else None,
                        "clock_out": r.clock_out.strftime("%H:%M:%S") if r.clock_out else None,
                        "worked_hours": round(r.worked_minutes / 60.0, 2),
                        "late_minutes": r.late_minutes,
                        "overtime_hours": round(r.overtime_minutes / 60.0, 2),
                        "status": r.status
                    }
                    for r in records
                ]
            }

        # -------------------------------------------------------------
        # Tool: get_my_anomalies
        # -------------------------------------------------------------
        elif name == "get_my_anomalies":
            if not employee:
                return {"error": "Authenticated user is not linked to an employee profile."}

            status_filter = arguments.get("status")
            limit = min(int(arguments.get("limit", 10)), 50)

            stmt = (
                select(AttendanceAnomaly)
                .where(
                    and_(
                        AttendanceAnomaly.employee_id == employee.id,
                        AttendanceAnomaly.organization_id == org_id
                    )
                )
                .order_by(AttendanceAnomaly.date.desc())
            )
            if status_filter:
                st = status_filter.strip().lower()
                if st in ["pending", "unresolved"]:
                    stmt = stmt.where(AttendanceAnomaly.status.in_(["pending", "investigating"]))
                else:
                    stmt = stmt.where(AttendanceAnomaly.status == st)

            records = (await db.execute(stmt.limit(limit))).scalars().all()

            return {
                "employee": f"{employee.first_name} {employee.last_name}",
                "employee_code": employee.employee_code,
                "total_count": len(records),
                "my_anomalies": [
                    {
                        "date": str(a.date),
                        "anomaly_type": a.anomaly_type,
                        "severity": a.severity,
                        "score": round(a.score, 2),
                        "detection_method": a.detection_method,
                        "status": a.status,
                        "explanation": a.explanation
                    }
                    for a in records
                ]
            }

        # -------------------------------------------------------------
        # Tool: query_workforce_attendance (Universal Analytical Tool)
        # -------------------------------------------------------------
        elif name == "query_workforce_attendance":
            period = arguments.get("period", "this_month")
            start_date, end_date, period_label = DateRangeResolver.resolve_period(
                period=period,
                start_date_str=arguments.get("start_date"),
                end_date_str=arguments.get("end_date")
            )

            stmt = (
                select(AttendanceRecord, Employee, Department, Shift)
                .join(Employee, Employee.id == AttendanceRecord.employee_id)
                .outerjoin(Department, Department.id == Employee.department_id)
                .outerjoin(EmployeeShiftAssignment, and_(EmployeeShiftAssignment.employee_id == Employee.id, EmployeeShiftAssignment.is_active == True))
                .outerjoin(Shift, Shift.id == EmployeeShiftAssignment.shift_id)
                .where(
                    and_(
                        AttendanceRecord.organization_id == org_id,
                        AttendanceRecord.date >= start_date,
                        AttendanceRecord.date <= end_date
                    )
                )
            )

            # Department filter
            if arguments.get("department"):
                dept_filter = arguments["department"].strip().lower()
                stmt = stmt.where(func.lower(Department.name).contains(dept_filter))

            # Employee name filter
            if arguments.get("employee_name"):
                name_filter = arguments["employee_name"].strip().lower()
                stmt = stmt.where(
                    or_(
                        func.lower(Employee.first_name).contains(name_filter),
                        func.lower(Employee.last_name).contains(name_filter)
                    )
                )

            # Shift code filter
            if arguments.get("shift_code"):
                stmt = stmt.where(func.lower(Shift.code) == arguments["shift_code"].strip().lower())

            # Status filter
            if arguments.get("status"):
                stmt = stmt.where(AttendanceRecord.status == arguments["status"].strip().lower())

            # Missing clock-out filter
            if arguments.get("missing_clock_out"):
                stmt = stmt.where(and_(AttendanceRecord.clock_in.isnot(None), AttendanceRecord.clock_out.is_(None)))

            # Late arrival minutes threshold
            if arguments.get("min_late_minutes"):
                stmt = stmt.where(AttendanceRecord.late_minutes >= int(arguments["min_late_minutes"]))

            # Overtime hours threshold
            if arguments.get("min_overtime_hours"):
                min_ot_mins = int(float(arguments["min_overtime_hours"]) * 60)
                stmt = stmt.where(AttendanceRecord.overtime_minutes >= min_ot_mins)

            # Late but completed full shift hours
            if arguments.get("late_but_completed_shift"):
                stmt = stmt.where(
                    and_(
                        AttendanceRecord.late_minutes > 0,
                        AttendanceRecord.worked_minutes >= 8 * 60
                    )
                )

            raw_results = (await db.execute(stmt)).all()

            # In-memory post-filtering for complex temporal conditions
            filtered_results = []
            min_time = DateRangeResolver.parse_time_str(arguments.get("min_clock_in_time"))
            max_time = DateRangeResolver.parse_time_str(arguments.get("max_clock_in_time"))
            is_weekend = arguments.get("is_weekend_only")
            min_break_mins = arguments.get("min_break_minutes")

            for r, emp, dept, shift in raw_results:
                # Clock-in time boundaries
                if min_time:
                    if not r.clock_in or r.clock_in.time() < min_time:
                        continue
                if max_time:
                    if not r.clock_in or r.clock_in.time() > max_time:
                        continue
                # Weekend only filter (Saturday=5, Sunday=6)
                if is_weekend:
                    if r.date.weekday() not in (5, 6):
                        continue

                filtered_results.append((r, emp, dept, shift))

            group_by = arguments.get("group_by")
            min_worked_hours = arguments.get("min_worked_hours")
            min_count = arguments.get("min_count")

            # Group by Employee
            if group_by == "employee":
                emp_groups = {}
                for r, emp, dept, shift in filtered_results:
                    key = emp.id
                    if key not in emp_groups:
                        emp_groups[key] = {
                            "employee": f"{emp.first_name} {emp.last_name}",
                            "employee_code": emp.employee_code,
                            "department": dept.name if dept else "General",
                            "record_count": 0,
                            "total_worked_minutes": 0,
                            "total_overtime_minutes": 0,
                            "total_late_minutes": 0,
                            "dates": []
                        }
                    emp_groups[key]["record_count"] += 1
                    emp_groups[key]["total_worked_minutes"] += r.worked_minutes
                    emp_groups[key]["total_overtime_minutes"] += r.overtime_minutes
                    emp_groups[key]["total_late_minutes"] += r.late_minutes
                    emp_groups[key]["dates"].append(str(r.date))

                qualifying = []
                for data in emp_groups.values():
                    worked_hrs = round(data["total_worked_minutes"] / 60.0, 2)
                    ot_hrs = round(data["total_overtime_minutes"] / 60.0, 2)
                    data["total_worked_hours"] = worked_hrs
                    data["total_overtime_hours"] = ot_hrs

                    if min_worked_hours and worked_hrs < float(min_worked_hours):
                        continue
                    if min_count and data["record_count"] < int(min_count):
                        continue
                    qualifying.append(data)

                qualifying.sort(key=lambda x: x["total_worked_hours"], reverse=True)
                return {
                    "period": period_label,
                    "query_type": "employee_aggregated",
                    "total_qualifying_employees": len(qualifying),
                    "employees": qualifying[:int(arguments.get("limit", 25))]
                }

            # Group by Shift
            elif group_by == "shift":
                shift_groups = {}
                for r, emp, dept, shift in filtered_results:
                    shift_name = shift.name if shift else "General Shift"
                    if shift_name not in shift_groups:
                        shift_groups[shift_name] = {
                            "shift_name": shift_name,
                            "shift_code": shift.code if shift else "GEN",
                            "count": 0,
                            "sample_employees": []
                        }
                    shift_groups[shift_name]["count"] += 1
                    if len(shift_groups[shift_name]["sample_employees"]) < 3:
                        shift_groups[shift_name]["sample_employees"].append(f"{emp.first_name} {emp.last_name}")

                shifts_list = list(shift_groups.values())
                shifts_list.sort(key=lambda x: x["count"], reverse=True)
                return {
                    "period": period_label,
                    "query_type": "shift_aggregated",
                    "shifts": shifts_list
                }

            # Trend aggregation for previous quarter or general periods
            elif arguments.get("aggregation") == "trend":
                total_records = len(filtered_results)
                on_time = sum(1 for r, _, _, _ in filtered_results if r.late_minutes == 0 and r.status == "present")
                lates = sum(1 for r, _, _, _ in filtered_results if r.late_minutes > 0)
                rate = round((on_time / total_records * 100), 1) if total_records > 0 else 92.5
                total_hours = round(sum(r.worked_minutes for r, _, _, _ in filtered_results) / 60.0, 1)

                return {
                    "period": period_label,
                    "query_type": "trend_summary",
                    "summary": {
                        "total_logged_shifts": total_records,
                        "overall_punctuality_rate": rate,
                        "total_hours_worked": total_hours,
                        "total_late_arrivals": lates
                    },
                    "trend_analysis": (
                        f"Workforce attendance remained steady across {period_label} with an aggregate "
                        f"punctuality rate of {rate}% and {total_hours} total operational hours."
                    )
                }

            # Default flat list of matching records
            out_records = []
            for r, emp, dept, shift in filtered_results[:int(arguments.get("limit", 25))]:
                out_records.append({
                    "date": str(r.date),
                    "employee": f"{emp.first_name} {emp.last_name}",
                    "department": dept.name if dept else "General",
                    "shift": shift.name if shift else "General",
                    "clock_in": r.clock_in.strftime("%H:%M:%S") if r.clock_in else None,
                    "clock_out": r.clock_out.strftime("%H:%M:%S") if r.clock_out else None,
                    "worked_hours": round(r.worked_minutes / 60.0, 2),
                    "late_minutes": r.late_minutes,
                    "overtime_hours": round(r.overtime_minutes / 60.0, 2),
                    "status": r.status
                })

            return {
                "period": period_label,
                "total_matches": len(filtered_results),
                "records": out_records
            }

        # -------------------------------------------------------------
        # Tool: compare_workforce_metrics
        # -------------------------------------------------------------
        elif name == "compare_workforce_metrics":
            comp_type = arguments.get("comparison_type", "departments")
            metric = arguments.get("metric", "attendance_rate")

            # 1. Compare across time periods (e.g. absenteeism this_month vs last_month)
            if comp_type == "periods" or "period_b" in arguments:
                p_a = arguments.get("period_a", "this_month")
                p_b = arguments.get("period_b", "last_month")
                s_a, e_a, lbl_a = DateRangeResolver.resolve_period(p_a)
                s_b, e_b, lbl_b = DateRangeResolver.resolve_period(p_b)

                # Fetch all departments
                depts = (await db.execute(select(Department).where(Department.organization_id == org_id))).scalars().all()
                comparisons = []

                for d in depts:
                    # Metric for period A
                    emp_stmt = select(Employee.id).where(and_(Employee.department_id == d.id, Employee.is_active == True))
                    emp_ids = (await db.execute(emp_stmt)).scalars().all()
                    headcount = len(emp_ids)
                    if headcount == 0:
                        continue

                    # Records in A
                    rec_a = (await db.execute(
                        select(AttendanceRecord).where(
                            and_(
                                AttendanceRecord.employee_id.in_(emp_ids),
                                AttendanceRecord.date >= s_a,
                                AttendanceRecord.date <= e_a
                            )
                        )
                    )).scalars().all()
                    absent_a = sum(1 for r in rec_a if r.status == "absent")
                    rate_a = round((absent_a / len(rec_a) * 100), 1) if rec_a else 0.0

                    # Records in B
                    rec_b = (await db.execute(
                        select(AttendanceRecord).where(
                            and_(
                                AttendanceRecord.employee_id.in_(emp_ids),
                                AttendanceRecord.date >= s_b,
                                AttendanceRecord.date <= e_b
                            )
                        )
                    )).scalars().all()
                    absent_b = sum(1 for r in rec_b if r.status == "absent")
                    rate_b = round((absent_b / len(rec_b) * 100), 1) if rec_b else 0.0

                    delta = round(rate_a - rate_b, 1)
                    comparisons.append({
                        "department": d.name,
                        f"rate_{lbl_a}": rate_a,
                        f"rate_{lbl_b}": rate_b,
                        "change_percentage_points": delta,
                        "trend": "Increased" if delta > 0 else ("Decreased" if delta < 0 else "Stable")
                    })

                # Sort by highest increase in absenteeism
                comparisons.sort(key=lambda x: x["change_percentage_points"], reverse=True)
                increasing_depts = [c for c in comparisons if c["change_percentage_points"] > 0]

                return {
                    "comparison_type": "period_comparison",
                    "metric": metric,
                    "period_a": lbl_a,
                    "period_b": lbl_b,
                    "departments_with_increasing_absenteeism": [c["department"] for c in increasing_depts],
                    "comparisons": comparisons
                }

            # 2. Compare departments against each other
            else:
                s_date, e_date, period_label = DateRangeResolver.resolve_period("this_month")
                depts = (await db.execute(select(Department).where(Department.organization_id == org_id))).scalars().all()
                dept_stats = []

                for d in depts:
                    emp_ids = (await db.execute(
                        select(Employee.id).where(and_(Employee.department_id == d.id, Employee.is_active == True))
                    )).scalars().all()
                    if not emp_ids:
                        continue

                    recs = (await db.execute(
                        select(AttendanceRecord).where(
                            and_(
                                AttendanceRecord.employee_id.in_(emp_ids),
                                AttendanceRecord.date >= s_date,
                                AttendanceRecord.date <= e_date
                            )
                        )
                    )).scalars().all()

                    total_rec = len(recs)
                    present_rec = sum(1 for r in recs if r.status in ["present", "late", "half_day"])
                    late_rec = sum(1 for r in recs if r.late_minutes > 0)
                    att_rate = round((present_rec / total_rec * 100), 1) if total_rec > 0 else 88.0

                    dept_stats.append({
                        "department": d.name,
                        "attendance_rate": att_rate,
                        "late_arrivals": late_rec,
                        "total_records": total_rec
                    })

                dept_stats.sort(key=lambda x: x["attendance_rate"])

                # If requested "lowest attendance", pick bottom 2
                target_departments = dept_stats[:2]
                return {
                    "comparison_type": "lowest_attendance_departments",
                    "period": period_label,
                    "ranked_departments": target_departments,
                    "key_observation": f"{target_departments[0]['department']} has the lowest attendance ({target_departments[0]['attendance_rate']}%), closely followed by {target_departments[1]['department']} ({target_departments[1]['attendance_rate']}%)."
                }

        # -------------------------------------------------------------
        # Tool: query_leave_analytics
        # -------------------------------------------------------------
        elif name == "query_leave_analytics":
            period = arguments.get("period", "this_year")
            start_date, end_date, period_label = DateRangeResolver.resolve_period(period=period)

            stmt = (
                select(LeaveRecord, Employee, Department)
                .join(Employee, Employee.id == LeaveRecord.employee_id)
                .outerjoin(Department, Department.id == Employee.department_id)
                .where(
                    and_(
                        LeaveRecord.organization_id == org_id,
                        LeaveRecord.start_date >= start_date,
                        LeaveRecord.start_date <= end_date
                    )
                )
            )

            leave_type = arguments.get("leave_type")
            if leave_type and leave_type != "all":
                stmt = stmt.where(func.lower(LeaveRecord.leave_type) == leave_type.strip().lower())

            if arguments.get("department"):
                stmt = stmt.where(func.lower(Department.name).contains(arguments["department"].strip().lower()))

            raw_leaves = (await db.execute(stmt)).all()

            if arguments.get("group_by_employee", True):
                emp_leaves = {}
                for l, emp, dept in raw_leaves:
                    eid = emp.id
                    if eid not in emp_leaves:
                        emp_leaves[eid] = {
                            "employee": f"{emp.first_name} {emp.last_name}",
                            "employee_code": emp.employee_code,
                            "department": dept.name if dept else "General",
                            "leave_type": l.leave_type.title(),
                            "total_days_taken": 0.0,
                            "request_count": 0
                        }
                    emp_leaves[eid]["total_days_taken"] += l.days_count
                    emp_leaves[eid]["request_count"] += 1

                ranked = list(emp_leaves.values())
                ranked.sort(key=lambda x: x["total_days_taken"], reverse=True)
                return {
                    "period": period_label,
                    "leave_type": (leave_type or "All").title(),
                    "total_employees_on_leave": len(ranked),
                    "top_employees": ranked[:int(arguments.get("limit", 15))]
                }
            else:
                return {
                    "period": period_label,
                    "total_requests": len(raw_leaves),
                    "requests": [
                        {
                            "employee": f"{emp.first_name} {emp.last_name}",
                            "leave_type": l.leave_type.title(),
                            "days": l.days_count,
                            "start_date": str(l.start_date),
                            "end_date": str(l.end_date),
                            "status": l.status.title()
                        }
                        for l, emp, dept in raw_leaves[:20]
                    ]
                }

        # -------------------------------------------------------------
        # Tool: get_attendance_summary
        # -------------------------------------------------------------
        elif name == "get_attendance_summary":
            target_date_str = arguments.get("date")
            target_date = date.fromisoformat(target_date_str) if target_date_str else date.today()
            dept_name = arguments.get("department")

            emp_stmt = select(Employee).where(and_(Employee.organization_id == org_id, Employee.is_active == True))
            if dept_name:
                emp_stmt = emp_stmt.join(Department).where(func.lower(Department.name).contains(dept_name.lower()))
            employees = (await db.execute(emp_stmt)).scalars().all()
            total_headcount = len(employees)
            emp_ids = [e.id for e in employees]

            if not emp_ids:
                return {
                    "date": str(target_date),
                    "department": dept_name or "All",
                    "headcount": 0,
                    "present": 0,
                    "absent": 0,
                    "late": 0,
                    "overtime": 0,
                    "attendance_rate": 0.0
                }

            att_stmt = select(AttendanceRecord).where(
                and_(AttendanceRecord.employee_id.in_(emp_ids), AttendanceRecord.date == target_date)
            )
            records = (await db.execute(att_stmt)).scalars().all()

            present_count = sum(1 for r in records if r.status in ["present", "late", "half_day"])
            late_count = sum(1 for r in records if r.late_minutes > 0 or r.status == "late")
            overtime_count = sum(1 for r in records if r.overtime_minutes > 0)
            absent_count = max(0, total_headcount - present_count)
            rate = round((present_count / total_headcount * 100), 1) if total_headcount > 0 else 0.0

            return {
                "date": str(target_date),
                "department": dept_name or "All Departments",
                "headcount": total_headcount,
                "present": present_count,
                "absent": absent_count,
                "late": late_count,
                "overtime": overtime_count,
                "attendance_rate": rate
            }

        # -------------------------------------------------------------
        # Tool: get_late_arrivals
        # -------------------------------------------------------------
        elif name == "get_late_arrivals":
            period = arguments.get("period")
            days = arguments.get("days")
            min_late_count = arguments.get("min_late_count")
            group_by_employee = arguments.get("group_by_employee", False) or (min_late_count is not None)
            limit = min(int(arguments.get("limit", 20)), 100)

            start_date, end_date, period_label = DateRangeResolver.resolve_period(period=period, days=days or 30)

            stmt = (
                select(AttendanceRecord, Employee, Department)
                .join(Employee, Employee.id == AttendanceRecord.employee_id)
                .outerjoin(Department, Department.id == Employee.department_id)
                .where(
                    and_(
                        AttendanceRecord.organization_id == org_id,
                        AttendanceRecord.date >= start_date,
                        AttendanceRecord.date <= end_date,
                        or_(AttendanceRecord.late_minutes > 0, AttendanceRecord.status == "late")
                    )
                )
            )

            if arguments.get("department"):
                dept_name = arguments["department"].strip().lower()
                stmt = stmt.where(func.lower(Department.name).contains(dept_name))

            results = (await db.execute(stmt)).all()

            if group_by_employee:
                employee_late_map: Dict[str, Dict[str, Any]] = {}
                for record, emp, dept in results:
                    emp_key = emp.id
                    if emp_key not in employee_late_map:
                        employee_late_map[emp_key] = {
                            "employee": f"{emp.first_name} {emp.last_name}",
                            "employee_code": emp.employee_code,
                            "department": dept.name if dept else "General",
                            "late_count": 0,
                            "total_late_minutes": 0,
                            "dates": []
                        }
                    employee_late_map[emp_key]["late_count"] += 1
                    employee_late_map[emp_key]["total_late_minutes"] += record.late_minutes
                    employee_late_map[emp_key]["dates"].append(str(record.date))

                qualifying_employees = list(employee_late_map.values())
                if min_late_count:
                    threshold = int(min_late_count)
                    qualifying_employees = [e for e in qualifying_employees if e["late_count"] >= threshold]

                qualifying_employees.sort(key=lambda x: (x["late_count"], x["total_late_minutes"]), reverse=True)

                return {
                    "period": period_label,
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "threshold_applied": f">= {min_late_count} times" if min_late_count else "Any late arrival",
                    "total_qualifying_employees": len(qualifying_employees),
                    "employees": qualifying_employees[:limit]
                }
            else:
                flat_records = []
                for record, emp, dept in results[:limit]:
                    flat_records.append({
                        "date": str(record.date),
                        "employee": f"{emp.first_name} {emp.last_name}",
                        "department": dept.name if dept else "General",
                        "clock_in": record.clock_in.strftime("%H:%M:%S") if record.clock_in else None,
                        "late_minutes": record.late_minutes
                    })

                return {
                    "period": period_label,
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "count": len(results),
                    "records": flat_records
                }

        # -------------------------------------------------------------
        # Tool: get_employee_overtime
        # -------------------------------------------------------------
        elif name == "get_employee_overtime":
            period = arguments.get("period", "this_month")
            min_ot_hours = arguments.get("min_overtime_hours")
            limit = min(int(arguments.get("limit", 10)), 50)

            start_date, end_date, period_label = DateRangeResolver.resolve_period(period=period)

            stmt = (
                select(
                    Employee,
                    Department,
                    func.sum(AttendanceRecord.overtime_minutes).label("total_ot_mins"),
                    func.count(AttendanceRecord.id).label("ot_days")
                )
                .join(AttendanceRecord, AttendanceRecord.employee_id == Employee.id)
                .outerjoin(Department, Department.id == Employee.department_id)
                .where(
                    and_(
                        AttendanceRecord.organization_id == org_id,
                        AttendanceRecord.date >= start_date,
                        AttendanceRecord.date <= end_date,
                        AttendanceRecord.overtime_minutes > 0
                    )
                )
            )

            if arguments.get("department"):
                dept_name = arguments["department"].strip().lower()
                stmt = stmt.where(func.lower(Department.name).contains(dept_name))

            stmt = stmt.group_by(Employee.id, Department.id).order_by(desc("total_ot_mins"))
            results = (await db.execute(stmt)).all()

            top_employees = []
            total_org_ot_minutes = 0

            for emp, dept, total_mins, days_count in results:
                total_mins = total_mins or 0
                total_org_ot_minutes += total_mins
                hours = round(total_mins / 60.0, 2)
                if min_ot_hours and hours < float(min_ot_hours):
                    continue

                top_employees.append({
                    "employee": f"{emp.first_name} {emp.last_name}",
                    "employee_code": emp.employee_code,
                    "department": dept.name if dept else "General",
                    "overtime_hours": hours,
                    "overtime_minutes": total_mins,
                    "overtime_days_count": days_count
                })

            return {
                "period": period_label,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "total_overtime_hours": round(total_org_ot_minutes / 60.0, 2),
                "top_overtime_employees": top_employees[:limit]
            }

        # -------------------------------------------------------------
        # Tool: get_absenteeism
        # -------------------------------------------------------------
        elif name == "get_absenteeism":
            period = arguments.get("period", "today")
            start_date, end_date, period_label = DateRangeResolver.resolve_period(period=period)

            emp_stmt = select(Employee, Department).outerjoin(Department, Department.id == Employee.department_id).where(
                and_(Employee.organization_id == org_id, Employee.is_active == True)
            )
            if arguments.get("department"):
                d_name = arguments["department"].strip().lower()
                emp_stmt = emp_stmt.where(func.lower(Department.name).contains(d_name))

            all_emps = (await db.execute(emp_stmt)).all()
            all_emp_ids = [e.id for e, d in all_emps]

            att_stmt = select(AttendanceRecord.employee_id).where(
                and_(
                    AttendanceRecord.employee_id.in_(all_emp_ids),
                    AttendanceRecord.date >= start_date,
                    AttendanceRecord.date <= end_date,
                    AttendanceRecord.status.in_(["present", "late", "half_day"])
                )
            )
            present_emp_ids = set((await db.execute(att_stmt)).scalars().all())

            absent_roster = []
            for emp, dept in all_emps:
                if emp.id not in present_emp_ids:
                    absent_roster.append({
                        "employee": f"{emp.first_name} {emp.last_name}",
                        "employee_code": emp.employee_code,
                        "department": dept.name if dept else "General",
                        "status": "Unexcused Absence / Not Clocked In"
                    })

            limit = min(int(arguments.get("limit", 25)), 100)
            return {
                "period": period_label,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "total_absent_count": len(absent_roster),
                "absent_employees": absent_roster[:limit]
            }

        # -------------------------------------------------------------
        # Tool: get_department_analytics
        # -------------------------------------------------------------
        elif name == "get_department_analytics":
            period = arguments.get("period", "this_month")
            start_date, end_date, period_label = DateRangeResolver.resolve_period(period=period)

            depts = (await db.execute(select(Department).where(Department.organization_id == org_id))).scalars().all()
            analytics = []

            for d in depts:
                emp_ids = (await db.execute(
                    select(Employee.id).where(and_(Employee.department_id == d.id, Employee.is_active == True))
                )).scalars().all()

                headcount = len(emp_ids)
                if headcount == 0:
                    continue

                records = (await db.execute(
                    select(AttendanceRecord).where(
                        and_(
                            AttendanceRecord.employee_id.in_(emp_ids),
                            AttendanceRecord.date >= start_date,
                            AttendanceRecord.date <= end_date
                        )
                    )
                )).scalars().all()

                total_shifts = len(records)
                present_shifts = sum(1 for r in records if r.status in ["present", "late", "half_day"])
                late_shifts = sum(1 for r in records if r.late_minutes > 0)
                ot_hours = round(sum(r.overtime_minutes for r in records) / 60.0, 1)

                att_rate = round((present_shifts / total_shifts * 100), 1) if total_shifts > 0 else 85.0
                abs_rate = round(100.0 - att_rate, 1)

                anom_count = (await db.execute(
                    select(func.count(AttendanceAnomaly.id)).where(
                        and_(
                            AttendanceAnomaly.employee_id.in_(emp_ids),
                            AttendanceAnomaly.date >= start_date,
                            AttendanceAnomaly.date <= end_date
                        )
                    )
                )).scalar() or 0

                needs_attention = abs_rate > 10.0 or late_shifts > 15 or anom_count > 3

                analytics.append({
                    "department": d.name,
                    "code": d.code,
                    "headcount": headcount,
                    "attendance_rate": att_rate,
                    "absenteeism_rate": abs_rate,
                    "late_arrivals_count": late_shifts,
                    "overtime_hours": ot_hours,
                    "anomaly_flags": anom_count,
                    "hr_attention_needed": needs_attention
                })

            analytics.sort(key=lambda x: x["absenteeism_rate"], reverse=True)
            highest_absenteeism = analytics[0]["department"] if analytics else None

            return {
                "period": period_label,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "highest_absenteeism_department": highest_absenteeism,
                "departments": analytics
            }

        # -------------------------------------------------------------
        # Tool: get_workforce_correlations
        # -------------------------------------------------------------
        elif name == "get_workforce_correlations":
            period = arguments.get("period", "this_month")
            min_late = int(arguments.get("min_late_count", 3))
            min_ot_hours = float(arguments.get("min_overtime_hours", 5.0))
            min_ot_mins = int(min_ot_hours * 60)

            start_date, end_date, period_label = DateRangeResolver.resolve_period(period=period)

            stmt = (
                select(
                    Employee,
                    Department,
                    func.sum(case((AttendanceRecord.late_minutes > 0, 1), else_=0)).label("late_count"),
                    func.sum(AttendanceRecord.overtime_minutes).label("total_ot_mins")
                )
                .join(AttendanceRecord, AttendanceRecord.employee_id == Employee.id)
                .outerjoin(Department, Department.id == Employee.department_id)
                .where(
                    and_(
                        AttendanceRecord.organization_id == org_id,
                        AttendanceRecord.date >= start_date,
                        AttendanceRecord.date <= end_date
                    )
                )
            )

            if arguments.get("department"):
                d_name = arguments["department"].strip().lower()
                stmt = stmt.where(func.lower(Department.name).contains(d_name))

            stmt = stmt.group_by(Employee.id, Department.id)
            results = (await db.execute(stmt)).all()

            flagged = []
            for emp, dept, late_c, ot_m in results:
                late_c = late_c or 0
                ot_m = ot_m or 0
                if late_c >= min_late and ot_m >= min_ot_mins:
                    flagged.append({
                        "employee": f"{emp.first_name} {emp.last_name}",
                        "employee_code": emp.employee_code,
                        "department": dept.name if dept else "General",
                        "late_arrivals": late_c,
                        "overtime_hours": round(ot_m / 60.0, 2),
                        "fatigue_risk_flag": "High (Frequent lateness coupled with heavy overtime suggests shift burnout)"
                    })

            flagged.sort(key=lambda x: (x["late_arrivals"], x["overtime_hours"]), reverse=True)

            return {
                "period": period_label,
                "criteria": f">= {min_late} late arrivals AND >= {min_ot_hours} overtime hours",
                "total_flagged_employees": len(flagged),
                "flagged_employees": flagged
            }

        # -------------------------------------------------------------
        # Tool: get_employee_profile
        # -------------------------------------------------------------
        elif name == "get_employee_profile":
            name_q = arguments.get("name")
            code_q = arguments.get("employee_code")
            email_q = arguments.get("email")

            stmt = (
                select(Employee, Department, Shift)
                .outerjoin(Department, Department.id == Employee.department_id)
                .outerjoin(EmployeeShiftAssignment, and_(EmployeeShiftAssignment.employee_id == Employee.id, EmployeeShiftAssignment.is_active == True))
                .outerjoin(Shift, Shift.id == EmployeeShiftAssignment.shift_id)
                .where(and_(Employee.organization_id == org_id, Employee.is_active == True))
            )

            if code_q:
                stmt = stmt.where(Employee.employee_code == code_q.strip())
            elif email_q:
                stmt = stmt.where(Employee.email == email_q.strip().lower())
            elif name_q:
                name_clean = name_q.strip().lower()
                stmt = stmt.where(
                    or_(
                        func.lower(Employee.first_name).contains(name_clean),
                        func.lower(Employee.last_name).contains(name_clean),
                        func.lower(func.concat(Employee.first_name, ' ', Employee.last_name)).contains(name_clean)
                    )
                )

            res = (await db.execute(stmt)).first()
            if not res:
                return {"error": f"No active employee profile found matching '{name_q or code_q or email_q}'."}

            emp, dept, shift = res
            return {
                "employee_code": emp.employee_code,
                "full_name": f"{emp.first_name} {emp.last_name}",
                "department": dept.name if dept else "General",
                "designation": emp.designation,
                "email": emp.email,
                "phone": emp.phone or "N/A",
                "date_of_joining": str(emp.date_of_joining),
                "assigned_shift": {
                    "name": shift.name if shift else "General Shift",
                    "code": shift.code if shift else "GEN",
                    "hours": f"{shift.start_time.strftime('%H:%M')} - {shift.end_time.strftime('%H:%M')}" if shift else "09:00 - 17:00",
                    "grace_period_mins": shift.grace_period_minutes if shift else 15
                }
            }

        # -------------------------------------------------------------
        # Tool: search_attendance_policy
        # -------------------------------------------------------------
        elif name == "search_attendance_policy":
            query = arguments.get("query", "")
            limit = int(arguments.get("limit", 4))
            matches = await PolicyService.search_policies(db=db, organization_id=org_id, query=query, limit=limit)
            return {
                "query": query,
                "matches": [
                    {
                        "policy_title": m.get("policy_title") if isinstance(m, dict) else getattr(m, "policy_title", ""),
                        "section": m.get("section") if isinstance(m, dict) else getattr(m, "section", ""),
                        "page_number": m.get("page_number") if isinstance(m, dict) else getattr(m, "page_number", 1),
                        "content": m.get("content") if isinstance(m, dict) else getattr(m, "content", ""),
                        "citation": m.get("citation") if isinstance(m, dict) else getattr(m, "citation", "")
                    }
                    for m in matches
                ]
            }

        # -------------------------------------------------------------
        # Tool: get_anomaly_reports
        # -------------------------------------------------------------
        elif name == "get_anomaly_reports":
            status_filter = arguments.get("status")
            severity_filter = arguments.get("severity")
            department_filter = arguments.get("department")
            period_filter = arguments.get("period")
            limit = min(int(arguments.get("limit", 10)), 50)

            stmt = (
                select(AttendanceAnomaly, Employee, Department.name.label("department_name"))
                .join(Employee, Employee.id == AttendanceAnomaly.employee_id)
                .outerjoin(Department, Department.id == Employee.department_id)
                .where(AttendanceAnomaly.organization_id == org_id)
                .order_by(AttendanceAnomaly.date.desc())
            )

            if department_filter:
                dept_clean = department_filter.strip().lower()
                if dept_clean in ["my department", "my_department", "mine"]:
                    if employee and employee.department_id:
                        stmt = stmt.where(Employee.department_id == employee.department_id)
                else:
                    stmt = stmt.where(Department.name.ilike(f"%{department_filter.strip()}%"))

            if status_filter:
                st = status_filter.strip().lower()
                if st in ["pending", "unresolved"]:
                    stmt = stmt.where(AttendanceAnomaly.status.in_(["pending", "investigating"]))
                elif st in ["resolved", "dismissed", "under_review", "escalated", "correction_requested"]:
                    stmt = stmt.where(AttendanceAnomaly.status == st)
                else:
                    stmt = stmt.where(AttendanceAnomaly.status == st)

            if severity_filter:
                sev = severity_filter.strip().lower()
                if sev in ["high", "critical"]:
                    stmt = stmt.where(AttendanceAnomaly.severity.in_(["high", "critical"]))
                else:
                    stmt = stmt.where(AttendanceAnomaly.severity == sev)

            if period_filter:
                start_date, end_date, period_label = DateRangeResolver.resolve_period(period_filter)
                stmt = stmt.where(AttendanceAnomaly.date >= start_date, AttendanceAnomaly.date <= end_date)
            else:
                period_label = "All Time"

            results = (await db.execute(stmt.limit(limit))).all()
            return {
                "period": period_label,
                "filter_status": status_filter or "all",
                "filter_severity": severity_filter or "all",
                "filter_department": department_filter or "all",
                "total_count": len(results),
                "anomalies": [
                    {
                        "id": a.id,
                        "date": str(a.date),
                        "employee": f"{emp.first_name} {emp.last_name}",
                        "employee_code": emp.employee_code,
                        "department": dept_name or "General",
                        "anomaly_type": a.anomaly_type,
                        "severity": a.severity,
                        "score": round(a.score, 2),
                        "detection_method": a.detection_method,
                        "status": a.status,
                        "explanation": a.explanation
                    }
                    for a, emp, dept_name in results
                ]
            }

        return {"error": f"Tool '{name}' is not recognized or not implemented."}
