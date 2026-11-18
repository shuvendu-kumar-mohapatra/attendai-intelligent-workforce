import pytest
from datetime import date, datetime, timedelta
from app.anomaly.recommendation_engine.action_registry import ActionRegistry as AnomalyActionRegistry
from app.anomaly.recommendation_engine.explanation_generator import ExplanationGenerator as AnomalyExplanationGenerator
from app.anomaly.recommendation_engine.recommendation_schemas import (
    AttendanceComparison, HistoricalContext, RecommendedAction
)
from app.harness.providers.mock import MockLLMProvider
from app.harness.tool_registry import ToolRegistry, TOOL_DEFINITIONS
from app.harness.permissions import HarnessPermissions
from app.harness.output_validator import OutputValidator
from app.models.models import AttendanceAnomaly, AttendanceRecord, Employee, Department, User

# -------------------------------------------------------------
# 1. Test All 7 Anomaly Types & Recommendations
# -------------------------------------------------------------
def test_all_seven_anomaly_types_have_structured_recommendations():
    anomaly_types = [
        "unusual_working_hours",
        "excessive_overtime",
        "repeated_late_arrival",
        "missing_clock_out",
        "abnormal_break_duration",
        "duplicate_attendance",
        "unusual_absence_frequency",
        "isolation_forest_outlier"
    ]

    comp = AttendanceComparison(
        actual_worked_minutes=510,
        expected_worked_minutes=480,
        worked_minutes_variance=30,
        actual_overtime_minutes=30,
        actual_late_minutes=25,
        shift_grace_period_minutes=15,
        actual_break_minutes=90,
        expected_break_minutes=60,
        assigned_shift_name="General Day Shift",
        variance_summary="Worked 30m over expected shift duration"
    )

    hist = HistoricalContext(
        average_worked_hours_30d=8.0,
        overtime_frequency_30d=2,
        late_arrival_frequency_30d=3,
        previous_similar_anomalies_count=1,
        assigned_shift_name="General Day Shift",
        grace_period_minutes=15
    )

    for a_type in anomaly_types:
        recs = AnomalyActionRegistry.get_recommendations_for_anomaly(
            anomaly_type=a_type,
            comparison=comp,
            history=hist
        )
        assert len(recs) >= 2, f"Expected at least 2 recommendations for {a_type}, got {len(recs)}"
        for r in recs:
            assert isinstance(r, RecommendedAction)
            assert r.title
            assert r.action
            assert r.reason
            assert r.expected_outcome
            assert r.required_authorization
            assert r.priority in ["high", "medium", "low"]

# -------------------------------------------------------------
# 2. Test Anomaly Explanation Generator (Grounded, No Hallucination)
# -------------------------------------------------------------
def test_anomaly_explanation_generator():
    comp = AttendanceComparison(
        actual_worked_minutes=510,
        expected_worked_minutes=480,
        worked_minutes_variance=30,
        actual_overtime_minutes=30,
        assigned_shift_name="Day Shift",
        variance_summary="Worked 30m over shift"
    )
    hist = HistoricalContext(
        average_worked_hours_30d=8.0,
        average_worked_minutes_30d=480,
        overtime_frequency_30d=1,
        late_arrival_frequency_30d=0,
        previous_similar_anomalies_count=0,
        assigned_shift_name="Day Shift",
        assigned_shift_hours=8.0
    )

    expl = AnomalyExplanationGenerator.generate_deterministic_explanation(
        anomaly_type="unusual_working_hours",
        detection_method="rule_based",
        score=0.65,
        comparison=comp,
        history=hist
    )

    assert "510 minutes" in expl or "510" in expl or "480" in expl

# -------------------------------------------------------------
# 3. Test OutputValidator Renders Anomaly Tables (Fixing Empty Header Bug)
# -------------------------------------------------------------
def test_output_validator_anomalies_table():
    sample_data = {
        "period": "November 2026",
        "filter_status": "pending",
        "total_count": 2,
        "anomalies": [
            {
                "id": "anom_1",
                "date": "2026-11-17",
                "employee": "Alex Mercer",
                "employee_code": "EMP001",
                "department": "Engineering",
                "anomaly_type": "missing_clock_out",
                "severity": "high",
                "score": 0.85,
                "detection_method": "rule_based",
                "status": "pending",
                "explanation": "No clock-out recorded for shift on 2026-11-17."
            },
            {
                "id": "anom_2",
                "date": "2026-11-16",
                "employee": "Steven Hill",
                "employee_code": "EMP007",
                "department": "Customer Success",
                "anomaly_type": "excessive_overtime",
                "severity": "critical",
                "score": 0.92,
                "detection_method": "rule_based",
                "status": "pending",
                "explanation": "Worked 240 overtime minutes exceeding policy limits."
            }
        ]
    }

    markdown = OutputValidator._format_parsed_json_to_markdown(sample_data)
    assert "### Workforce Attendance Anomalies & Risk Analysis" in markdown
    assert "| Date | Employee | ID | Department | Anomaly Type | Severity | Score | Status | Details / Explanation |" in markdown
    assert "Alex Mercer" in markdown
    assert "EMP001" in markdown
    assert "Steven Hill" in markdown
    assert "EMP007" in markdown
    assert "🔴 HIGH" in markdown or "HIGH" in markdown
    assert "Missing Clock Out" in markdown

# -------------------------------------------------------------
# 4. Test Single Anomaly Deep-Dive View (for "Explain the most recent anomaly")
# -------------------------------------------------------------
def test_output_validator_single_anomaly_deep_dive():
    sample_single = {
        "period": "All Time",
        "filter_status": "all",
        "total_count": 1,
        "anomalies": [
            {
                "id": "anom_recent",
                "date": "2026-11-17",
                "employee": "Thomas Garcia",
                "employee_code": "EMP200",
                "department": "Human Resources",
                "anomaly_type": "isolation_forest_outlier",
                "severity": "medium",
                "score": 0.68,
                "detection_method": "isolation_forest",
                "status": "pending",
                "explanation": "Unusual multivariate attendance pattern identified by machine learning."
            }
        ]
    }

    markdown = OutputValidator._format_parsed_json_to_markdown(sample_single)
    assert "#### Most Recent Flagged Anomaly: Thomas Garcia (`EMP200`)" in markdown
    assert "Human Resources" in markdown
    assert "Isolation Forest Outlier" in markdown
    assert "Outlier Score: 0.68" in markdown
    assert "Root Cause & Analysis:" in markdown

# -------------------------------------------------------------
# 5. Test Employee Personal Anomalies (get_my_anomalies)
# -------------------------------------------------------------
def test_output_validator_personal_anomalies():
    sample_personal = {
        "employee": "Elena Vance",
        "employee_code": "EMP002",
        "total_count": 1,
        "my_anomalies": [
            {
                "date": "2026-11-15",
                "anomaly_type": "repeated_late_arrivals",
                "severity": "medium",
                "score": 0.55,
                "detection_method": "rule_based",
                "status": "pending",
                "explanation": "Clocked in 25 minutes after shift start."
            }
        ]
    }

    markdown = OutputValidator._format_parsed_json_to_markdown(sample_personal)
    assert "### Personal Attendance Anomaly Flags" in markdown
    assert "Elena Vance" in markdown
    assert "EMP002" in markdown
    assert "Repeated Late Arrivals" in markdown

# -------------------------------------------------------------
# 6. Test RBAC Permissions for Anomaly Tools
# -------------------------------------------------------------
def test_rbac_anomaly_permissions():
    assert HarnessPermissions.is_tool_allowed("admin", "get_anomaly_reports") is True
    assert HarnessPermissions.is_tool_allowed("hr_manager", "get_anomaly_reports") is True
    assert HarnessPermissions.is_tool_allowed("employee", "get_anomaly_reports") is False

    assert HarnessPermissions.is_tool_allowed("employee", "get_my_anomalies") is True
    assert HarnessPermissions.is_tool_allowed("hr_manager", "get_my_anomalies") is True
    assert HarnessPermissions.is_tool_allowed("admin", "get_my_anomalies") is True

# -------------------------------------------------------------
# 7. Test Mock Provider Routes All 7 Queries Reliably
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_provider_routes_all_seven_queries():
    mock = MockLLMProvider()

    test_cases = [
        ("List pending anomalies", "get_anomaly_reports", {"status": "pending"}),
        ("Show all unresolved anomalies", "get_anomaly_reports", {"status": "pending"}),
        ("Show high-severity anomalies", "get_anomaly_reports", {"severity": "high"}),
        ("Show anomalies in my department", "get_anomaly_reports", {"department": "my department"}),
        ("Explain the most recent anomaly", "get_anomaly_reports", {"limit": 1}),
        ("Show anomalies detected this month", "get_anomaly_reports", {"period": "this_month"}),
    ]

    for query, expected_tool, expected_args in test_cases:
        resp = await mock.generate_response(messages=[{"role": "user", "content": query}], tools=TOOL_DEFINITIONS)
        assert resp.get("tool_calls"), f"No tool calls generated for query: '{query}'"
        call = resp["tool_calls"][0]
        assert call["function"]["name"] == expected_tool
        import json
        args = json.loads(call["function"]["arguments"])
        for k, v in expected_args.items():
            assert args.get(k) == v, f"Expected {k}={v} in args for query '{query}', got {args}"

    # Query 7: Personal employee scope
    emp_query = "Show my attendance anomalies"
    # When employee asks, system prompt contains role: employee or mock receives is_employee_scope
    messages_emp = [
        {"role": "system", "content": "You are AttendAI Assistant. Authenticated User: 'emp@test.com' | Role: 'Employee'."},
        {"role": "user", "content": emp_query}
    ]
    resp_emp = await mock.generate_response(messages=messages_emp, tools=TOOL_DEFINITIONS)
    assert resp_emp.get("tool_calls")
    assert resp_emp["tool_calls"][0]["function"]["name"] == "get_my_anomalies"

# -------------------------------------------------------------
# 8. Test Empty Anomalies Renders Required Message & No Citations
# -------------------------------------------------------------
def test_empty_anomalies_renders_exact_message_and_no_citation():
    empty_tool_result = [{
        "tool_name": "get_anomaly_reports",
        "output": {
            "period": "All Time",
            "filter_status": "pending",
            "total_count": 0,
            "anomalies": []
        }
    }]

    # 1. Output text must match required exact phrase
    text = OutputValidator._synthesize_tool_results_to_markdown(empty_tool_result)
    assert text == "No pending anomalies were found within your authorized department scope."

    # 2. Citations must NOT be generated when no records exist
    citations = OutputValidator._extract_citations(empty_tool_result)
    assert len(citations) == 0, f"Expected 0 citations for empty results, got {citations}"

    # 3. Overall validated output check
    res = OutputValidator.validate_and_format("", empty_tool_result, "hr_manager")
    assert res["validated_text"] == "No pending anomalies were found within your authorized department scope."
    assert len(res["citations"]) == 0

# -------------------------------------------------------------
# 9. Test Database Query Failure Displays Meaningful Error
# -------------------------------------------------------------
def test_database_query_error_displays_meaningful_error():
    error_tool_result = [{
        "tool_name": "get_anomaly_reports",
        "output": {
            "error": "Database connection timeout while querying attendance anomalies."
        }
    }]

    res = OutputValidator.validate_and_format("", error_tool_result, "hr_manager")
    assert "Database connection timeout" in res["validated_text"]
    assert "⚠️" in res["validated_text"]
    assert len(res["citations"]) == 0

# -------------------------------------------------------------
# 10. Test No Headings Without Content Across All Tools
# -------------------------------------------------------------
def test_no_headings_without_content_across_all_tools():
    # Test fallback with empty dictionary
    empty_data = {}
    res = OutputValidator._format_parsed_json_to_markdown(empty_data)
    assert "###" not in res
    assert "No records were found" in res

    # Test when raw text from LLM is solely a heading
    heading_only_text = "### Workforce Intelligence Overview\n\n"
    tool_result = [{
        "tool_name": "get_anomaly_reports",
        "output": {
            "total_count": 0,
            "anomalies": []
        }
    }]
    validated = OutputValidator.validate_and_format(heading_only_text, tool_result, "hr_manager")
    assert validated["validated_text"] == "No pending anomalies were found within your authorized department scope."

# -------------------------------------------------------------
# 11. Test Complete End-to-End Turn for All 7 Queries on Actual Database
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_end_to_end_all_seven_queries_on_actual_db(monkeypatch):
    from app.core.config import settings
    from app.core.database import get_sessionmaker
    from app.harness.orchestrator import AIOrchestrator
    from sqlalchemy import select

    # Guarantee deterministic execution during automated testing
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")

    SessionLocal = get_sessionmaker()
    orchestrator = AIOrchestrator()

    async with SessionLocal() as db:
        # 1. Fetch Eleanor Vance (HR Manager)
        stmt_hr = (
            select(User, Employee)
            .join(Employee, Employee.user_id == User.id)
            .where(User.role == "hr_manager")
        )
        hr_row = (await db.execute(stmt_hr)).first()
        assert hr_row is not None, "HR Manager user not found in seeded database"
        hr_user, hr_emp = hr_row

        # 2. Fetch Alex Mercer (Employee)
        stmt_emp = (
            select(User, Employee)
            .join(Employee, Employee.user_id == User.id)
            .where(User.role == "employee")
        )
        emp_row = (await db.execute(stmt_emp)).first()
        assert emp_row is not None, "Employee user not found in seeded database"
        emp_user, emp_emp = emp_row

        queries_hr = [
            "List pending anomalies",
            "Show all unresolved anomalies",
            "Show high-severity anomalies",
            "Show anomalies in my department",
            "Explain the most recent anomaly",
            "Show anomalies detected this month"
        ]

        for q in queries_hr:
            res = await orchestrator.execute_turn(
                db=db,
                user=hr_user,
                employee=hr_emp,
                user_message=q,
                conversation_history=[]
            )
            content = res.get("content", "")
            # Ensure content is never just empty heading
            assert len(content.strip()) > 30, f"Response too short for query '{q}': {content}"
            assert content != "### Workforce Intelligence Overview"
            # Verify records table or proper empty message
            assert (
                ("|" in content and ("EMP" in content or "Employee" in content or "Score" in content or "Late" in content)) or
                "No pending anomalies were found within your authorized department scope." in content or
                "Most Recent Flagged Anomaly" in content or
                "Recent Flagged Anomaly" in content
            ), f"Failed for query '{q}': {content}"

        # 3. Test Employee Role Query
        res_emp = await orchestrator.execute_turn(
            db=db,
            user=emp_user,
            employee=emp_emp,
            user_message="Show my attendance anomalies",
            conversation_history=[]
        )
        content_emp = res_emp.get("content", "")
        assert len(content_emp.strip()) > 20
        assert (
            "Personal Attendance Anomaly Flags" in content_emp or
            "No pending anomalies were found within your authorized department scope." in content_emp
        )
        # Ensure citations are never an empty substitute
        if "No pending anomalies" in content_emp:
            assert len(res_emp.get("citations", [])) == 0
