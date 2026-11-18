import time
import json
import re
from typing import List, Dict, Any, Optional
from app.harness.providers.base import BaseLLMProvider
from app.harness.output_validator import OutputValidator

class MockLLMProvider(BaseLLMProvider):
    """
    Deterministic mock provider for offline development and regression tests.
    Generates structured enterprise markdown responses, valid tool calls, and handles follow-up reasoning.
    Never outputs raw JSON or unformatted data.
    """
    def __init__(self, model: str = "attendai-mock-engine"):
        self.model = model

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2
    ) -> Dict[str, Any]:
        start_time = time.perf_counter()
        last_message = messages[-1]
        content = (last_message.get("content") or "").lower().strip()

        # Check if previous message had tool results
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        tool_calls = None
        reply = ""

        if tool_messages:
            # Multi-turn tool synthesis: Combine tool results and format as clean Markdown
            synthesized_blocks = []
            for tm in tool_messages:
                raw_c = tm.get("content", "{}")
                try:
                    parsed = json.loads(raw_c) if isinstance(raw_c, str) else raw_c
                    synthesized_blocks.append(OutputValidator._format_parsed_json_to_markdown(parsed))
                except Exception:
                    synthesized_blocks.append(str(raw_c))

            reply = "\n\n---\n\n".join(synthesized_blocks)

        else:
            # Detect caller role from system prompt if present
            system_msg = messages[0].get("content", "") if messages else ""
            is_employee_scope = "Role: 'Employee'" in system_msg

            # Available tool names in this invocation
            available_tool_names = set(t.get("function", {}).get("name") for t in tools) if tools else set()

            past_user_texts = [
                m.get("content", "").lower() for m in messages
                if m.get("role") == "user" and m != last_message
            ]
            last_user_context = past_user_texts[-1] if past_user_texts else ""

            # -------------------------------------------------------------
            # Out of domain check
            # -------------------------------------------------------------
            out_of_domain_keywords = ["weather", "poem", "capital of", "recipe", "joke", "sports", "movie"]
            if any(k in content for k in out_of_domain_keywords):
                reply = (
                    "I am AttendAI's Workforce Intelligence Assistant. I specialize in attendance tracking, "
                    "shift scheduling, overtime analysis, employee leave balances, punctuality, and HR policies. "
                    "I am unable to answer general inquiries outside workforce operations."
                )
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                return {
                    "content": reply,
                    "tool_calls": None,
                    "provider": "mock",
                    "model": self.model,
                    "latency_ms": round(latency_ms, 2),
                    "tokens_used": 20
                }

            # -------------------------------------------------------------
            # 1. Employee Personal Inquiries (strictly personal tools)
            # -------------------------------------------------------------
            if is_employee_scope or (("my" in content or "i do" in content or "was i" in content) and "department" not in content):
                # Personal Anomalies (Query 7: "Show my attendance anomalies")
                if "anomal" in content or ("flag" in content and "department" not in content):
                    tool_calls = [{
                        "id": "call_my_anom_1",
                        "type": "function",
                        "function": {
                            "name": "get_my_anomalies",
                            "arguments": "{}"
                        }
                    }]
                    reply = "Retrieving your personal attendance anomaly flags and investigation status."

                # Personal Overtime
                elif "overtime" in content or "ot" in content:
                    period = "this_month" if "this month" in content or "month" in content else "this_week"
                    tool_calls = [{
                        "id": "call_my_ot_1",
                        "type": "function",
                        "function": {
                            "name": "get_my_overtime",
                            "arguments": json.dumps({"period": period})
                        }
                    }]
                    reply = "Retrieving your personal overtime history from verified attendance records."

                # Personal Late Arrivals
                elif "late" in content or "tardy" in content or "punctual" in content:
                    tool_calls = [{
                        "id": "call_my_late_1",
                        "type": "function",
                        "function": {
                            "name": "get_my_late_arrivals",
                            "arguments": json.dumps({"period": "this_month"})
                        }
                    }]
                    reply = "Checking your personal late arrival and punctuality records."

                # Personal Working Hours
                elif "hours" in content or "worked" in content:
                    tool_calls = [{
                        "id": "call_my_hours_1",
                        "type": "function",
                        "function": {
                            "name": "get_my_working_hours",
                            "arguments": json.dumps({"period": "this_month"})
                        }
                    }]
                    reply = "Calculating your verified logged working hours."

                # Personal Leave Balance
                elif "leave" in content or "pto" in content or "vacation" in content:
                    tool_calls = [{
                        "id": "call_my_leave_1",
                        "type": "function",
                        "function": {
                            "name": "get_my_leave_balance",
                            "arguments": "{}"
                        }
                    }]
                    reply = "Retrieving your personal paid time off and leave balances."

                # Personal Shifts
                elif "shift" in content or "schedule" in content:
                    tool_calls = [{
                        "id": "call_my_shifts_1",
                        "type": "function",
                        "function": {
                            "name": "get_my_shifts",
                            "arguments": "{}"
                        }
                    }]
                    reply = "Fetching your assigned shift schedule and grace period parameters."

                # Personal Punch History
                elif "history" in content or "punches" in content or "punch" in content:
                    tool_calls = [{
                        "id": "call_my_hist_1",
                        "type": "function",
                        "function": {
                            "name": "get_my_attendance_history",
                            "arguments": json.dumps({"period": "last_30_days", "limit": 15})
                        }
                    }]
                    reply = "Retrieving your chronological attendance punch logs."

                # General Personal Attendance Summary
                elif "attendance" in content or "today" in content:
                    tool_calls = [{
                        "id": "call_my_att_1",
                        "type": "function",
                        "function": {
                            "name": "get_my_attendance",
                            "arguments": json.dumps({"period": "this_month"})
                        }
                    }]
                    reply = "Retrieving your personal attendance records."

                # Policy query by employee
                elif any(w in content for w in ["policy", "handbook", "guideline", "rule", "procedure"]):
                    tool_calls = [{
                        "id": "call_policy_1",
                        "type": "function",
                        "function": {
                            "name": "search_attendance_policy",
                            "arguments": json.dumps({"query": content})
                        }
                    }]
                    reply = "Searching company HR policies for applicable guidelines."

            # -------------------------------------------------------------
            # 2. HR Policies & Guidelines (Universal)
            # -------------------------------------------------------------
            elif any(w in content for w in ["policy", "handbook", "guideline", "guidelines", "rules"]):
                tool_calls = [{
                    "id": "call_policy_1",
                    "type": "function",
                    "function": {
                        "name": "search_attendance_policy",
                        "arguments": json.dumps({"query": content})
                    }
                }]
                reply = "Searching official workforce policy documentation."

            # -------------------------------------------------------------
            # 3. Follow-ups
            # -------------------------------------------------------------
            # Follow-up: "What about Engineering?"
            elif re.search(r'what about ([a-zA-Z\s]+)\??', content):
                dept_match = re.search(r'what about ([a-zA-Z\s]+)\??', content)
                target_dept = dept_match.group(1).strip().title() if dept_match else "Engineering"
                if "overtime" in last_user_context:
                    tool_calls = [{
                        "id": "call_ot_dept_1",
                        "type": "function",
                        "function": {
                            "name": "get_employee_overtime",
                            "arguments": json.dumps({"period": "last_month" if "last month" in last_user_context else "this_month", "department": target_dept})
                        }
                    }]
                    reply = f"Filtering overtime records for {target_dept}."
                elif "late" in last_user_context:
                    tool_calls = [{
                        "id": "call_late_dept_1",
                        "type": "function",
                        "function": {
                            "name": "get_late_arrivals",
                            "arguments": json.dumps({"period": "this_month", "department": target_dept, "group_by_employee": True})
                        }
                    }]
                    reply = f"Checking late arrivals for {target_dept}."
                else:
                    tool_calls = [{
                        "id": "call_att_dept_1",
                        "type": "function",
                        "function": {
                            "name": "get_attendance_summary",
                            "arguments": json.dumps({"period": "today", "department": target_dept})
                        }
                    }]
                    reply = f"Retrieving attendance summary for {target_dept}."

            # Follow-up: "Show details for <name>"
            elif "details" in content or "profile" in content or "show their" in content:
                name_match = re.search(r'(?:for|of)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)', content)
                target_name = name_match.group(1).strip() if name_match else "Marcus Vance"
                tool_calls = [{
                    "id": "call_prof_1",
                    "type": "function",
                    "function": {
                        "name": "get_employee_profile",
                        "arguments": json.dumps({"name": target_name})
                    }
                }]
                reply = f"Retrieving profile records for {target_name}."

            # -------------------------------------------------------------
            # 4. Universal Workforce Queries (The 10 Unseen General Questions)
            # -------------------------------------------------------------
            # A. "Who arrived after 11 today?"
            elif "after 11" in content or "arrived after" in content:
                time_match = re.search(r'after\s+(\d{1,2})', content)
                t_str = f"{time_match.group(1)}:00" if time_match else "11:00"
                tool_calls = [{
                    "id": "call_time_1",
                    "type": "function",
                    "function": {
                        "name": "query_workforce_attendance",
                        "arguments": json.dumps({"period": "today", "min_clock_in_time": t_str})
                    }
                }]
                reply = f"Querying attendance records for employees arriving after {t_str}."

            # B. "Which employees have worked more than 45 hours this week?"
            elif ("more than 45 hours" in content or "> 45 hours" in content or "45 hours" in content) and "worked" in content:
                tool_calls = [{
                    "id": "call_45_hrs_1",
                    "type": "function",
                    "function": {
                        "name": "query_workforce_attendance",
                        "arguments": json.dumps({"period": "this_week", "min_worked_hours": 45.0, "group_by": "employee"})
                    }
                }]
                reply = "Analyzing weekly hours for employees exceeding 45 worked hours."

            # C. "Compare attendance between the two departments with the lowest attendance"
            elif "lowest attendance" in content or ("compare" in content and "lowest" in content):
                tool_calls = [{
                    "id": "call_lowest_att_1",
                    "type": "function",
                    "function": {
                        "name": "compare_workforce_metrics",
                        "arguments": json.dumps({"comparison_type": "departments", "metric": "attendance_rate", "departments": "lowest_attendance"})
                    }
                }]
                reply = "Identifying and comparing the two departments with the lowest attendance rates."

            # D. "Which employees have taken the most sick leave this year?"
            elif "sick leave" in content or ("leave" in content and "most" in content):
                tool_calls = [{
                    "id": "call_sick_leave_1",
                    "type": "function",
                    "function": {
                        "name": "query_leave_analytics",
                        "arguments": json.dumps({"leave_type": "sick", "period": "this_year", "group_by_employee": True})
                    }
                }]
                reply = "Ranking employees with the highest sick leave volume this year."

            # E. "Find employees who frequently take unusually long breaks"
            elif "long breaks" in content or "unusually long break" in content:
                tool_calls = [{
                    "id": "call_long_breaks_1",
                    "type": "function",
                    "function": {
                        "name": "query_workforce_attendance",
                        "arguments": json.dumps({"period": "this_month", "min_break_minutes": 60, "group_by": "employee"})
                    }
                }]
                reply = "Analyzing attendance records for employees with unusually extended breaks (>60 minutes)."

            # F. "How many employees worked overtime on weekends?"
            elif "weekend" in content and "overtime" in content:
                tool_calls = [{
                    "id": "call_wknd_ot_1",
                    "type": "function",
                    "function": {
                        "name": "query_workforce_attendance",
                        "arguments": json.dumps({"period": "this_month", "is_weekend_only": True, "min_overtime_hours": 0.1})
                    }
                }]
                reply = "Auditing weekend overtime shifts across the organization."

            # G. "Identify departments where absenteeism increased compared with last month"
            elif "absenteeism increased" in content or ("absenteeism" in content and "compared with last month" in content):
                tool_calls = [{
                    "id": "call_abs_inc_1",
                    "type": "function",
                    "function": {
                        "name": "compare_workforce_metrics",
                        "arguments": json.dumps({
                            "comparison_type": "periods",
                            "metric": "absenteeism_rate",
                            "period_a": "this_month",
                            "period_b": "last_month"
                        })
                    }
                }]
                reply = "Comparing month-over-month department absenteeism rates to isolate increasing trends."

            # H. "Show employees who arrived late but completed their full shifts"
            elif "late but completed" in content or ("late" in content and "full shift" in content):
                tool_calls = [{
                    "id": "call_late_full_1",
                    "type": "function",
                    "function": {
                        "name": "query_workforce_attendance",
                        "arguments": json.dumps({"period": "this_month", "late_but_completed_shift": True})
                    }
                }]
                reply = "Filtering for employees who experienced delayed starts but completed their full scheduled shift duration."

            # I. "Which shifts have the highest number of missing clock-outs?"
            elif "missing clock" in content or "missing clock-out" in content:
                tool_calls = [{
                    "id": "call_missing_clock_1",
                    "type": "function",
                    "function": {
                        "name": "query_workforce_attendance",
                        "arguments": json.dumps({"period": "this_month", "missing_clock_out": True, "group_by": "shift"})
                    }
                }]
                reply = "Analyzing shifts with open, unclocked punches across the workforce."

            # J. "Summarize attendance trends for the previous quarter"
            elif "previous quarter" in content or "last quarter" in content or "trends for the previous quarter" in content:
                tool_calls = [{
                    "id": "call_prev_quarter_1",
                    "type": "function",
                    "function": {
                        "name": "query_workforce_attendance",
                        "arguments": json.dumps({"period": "previous_quarter", "aggregation": "trend"})
                    }
                }]
                reply = "Synthesizing executive workforce attendance trends for the previous quarter."

            # -------------------------------------------------------------
            # 5. Core Analytical Tools
            # -------------------------------------------------------------
            # Compound Correlation: Both late and overtime
            elif ("both" in content and ("late" in content or "tardiness" in content) and "overtime" in content) or \
                 ("repeated" in content and "overtime" in content):
                tool_calls = [{
                    "id": "call_corr_1",
                    "type": "function",
                    "function": {
                        "name": "get_workforce_correlations",
                        "arguments": json.dumps({"period": "this_month", "min_late_count": 3, "min_overtime_hours": 5.0})
                    }
                }]
                reply = "Analyzing compound workforce patterns for employees with both repeated lateness and high overtime."

            # Absenteeism
            elif "absent" in content or "absenteeism" in content:
                if "compare" in content or "department" in content or "highest" in content:
                    tool_calls = [{
                        "id": "call_dept_abs_1",
                        "type": "function",
                        "function": {
                            "name": "get_department_analytics",
                            "arguments": json.dumps({"period": "this_month"})
                        }
                    }]
                    reply = "Comparing department-level absenteeism and attendance rates."
                else:
                    tool_calls = [{
                        "id": "call_abs_1",
                        "type": "function",
                        "function": {
                            "name": "get_absenteeism",
                            "arguments": json.dumps({"period": "today"})
                        }
                    }]
                    reply = "Checking today's workforce absenteeism roster."

            # Late Arrivals with numerical threshold: "more than five times"
            elif "late" in content or "tardy" in content:
                min_count = None
                if "more than five" in content or "more than 5" in content or "> 5" in content:
                    min_count = 6
                elif "at least 5" in content or "5 or more" in content or ">= 5" in content:
                    min_count = 5
                elif "more than 3" in content or "more than three" in content:
                    min_count = 4
                elif "at least 3" in content:
                    min_count = 3

                period = "this_month" if "this month" in content or "month" in content else ("today" if "today" in content else "last_7_days")

                tool_calls = [{
                    "id": "call_late_1",
                    "type": "function",
                    "function": {
                        "name": "get_late_arrivals",
                        "arguments": json.dumps({
                            "period": period,
                            "min_late_count": min_count,
                            "group_by_employee": True if min_count or "employees" in content else False,
                            "limit": 15
                        })
                    }
                }]
                reply = f"Querying verified attendance records for late arrivals in {period}."

            # Overtime
            elif "overtime" in content or "ot" in content:
                period = "last_month" if "last month" in content or "previous month" in content else "this_month"
                dept = "Engineering" if "engineering" in content else None
                tool_calls = [{
                    "id": "call_ot_1",
                    "type": "function",
                    "function": {
                        "name": "get_employee_overtime",
                        "arguments": json.dumps({"period": period, "department": dept, "limit": 10})
                    }
                }]
                reply = f"Calculating overtime records for {period}."

            # Anomalies
            elif any(w in content for w in ["anomaly", "anomalies", "flagged attendance", "unresolved anomalies", "anomaly detections"]):
                args = {}
                # Query 5: Explain the most recent anomaly / latest anomaly
                if any(w in content for w in ["explain", "most recent", "latest", "last anomaly", "recent anomaly"]):
                    args["limit"] = 1
                    reply = "Retrieving and analyzing the most recent workforce attendance anomaly."
                # Query 3: High severity anomalies
                elif any(w in content for w in ["high severity", "high-severity", "high", "critical", "severe"]):
                    args["severity"] = "high"
                    reply = "Filtering for high and critical severity attendance anomalies."
                # Query 4: Department anomalies
                elif "department" in content or "dept" in content:
                    dept_match = re.search(r'(?:in|for)\s+([a-zA-Z\s]+?)(?:\s+department|$)', content)
                    if dept_match and dept_match.group(1).strip().lower() not in ["my", "the", "all"]:
                        args["department"] = dept_match.group(1).strip().title()
                    else:
                        args["department"] = "my department"
                    reply = f"Querying attendance anomalies for {args.get('department', 'department')}."
                # Query 6: Anomalies detected this month / period
                elif "this month" in content or "month" in content:
                    args["period"] = "this_month"
                    reply = "Querying attendance anomalies detected this month."
                elif "this week" in content or "week" in content:
                    args["period"] = "this_week"
                    reply = "Querying attendance anomalies detected this week."
                elif "today" in content:
                    args["period"] = "today"
                    reply = "Querying attendance anomalies detected today."
                # Query 1 & 2: Pending / Unresolved anomalies
                elif any(w in content for w in ["pending", "unresolved", "open", "investigate", "action needed"]):
                    args["status"] = "pending"
                    reply = "Fetching pending and unresolved anomaly investigation flags."
                else:
                    args["status"] = "pending"
                    reply = "Retrieving pending attendance anomaly flags."

                tool_calls = [{
                    "id": "call_anom_1",
                    "type": "function",
                    "function": {
                        "name": "get_anomaly_reports",
                        "arguments": json.dumps(args)
                    }
                }]

            # Department Analytics
            elif "department" in content or "headcount" in content or "attendance rate" in content:
                tool_calls = [{
                    "id": "call_dept_1",
                    "type": "function",
                    "function": {
                        "name": "get_department_analytics",
                        "arguments": json.dumps({"period": "this_month"})
                    }
                }]
                reply = "Analyzing department metrics and attendance rates."

            # General Default Fallback
            else:
                tool_calls = [{
                    "id": "call_gen_att_1",
                    "type": "function",
                    "function": {
                        "name": "get_attendance_summary",
                        "arguments": json.dumps({"period": "today"})
                    }
                }]
                reply = "Querying workforce attendance summary."

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return {
            "content": reply,
            "tool_calls": tool_calls,
            "provider": "mock",
            "model": self.model,
            "latency_ms": round(latency_ms, 2),
            "tokens_used": 45
        }
