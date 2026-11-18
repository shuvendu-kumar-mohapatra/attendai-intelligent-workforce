import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.anomaly.recommendation_engine.action_registry import ActionRegistry

@pytest.fixture
async def auth_headers():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/auth/login", json={
            "email": "admin@attendai.com",
            "password": "Admin@123"
        })
        assert res.status_code == 200
        token = res.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_action_registry_short_summaries():
    """Verify all 7 standardized corrective action summaries match specifications."""
    expected_mappings = {
        "unusual_working_hours": "Verify shift duration and overtime approval",
        "excessive_overtime": "Review overtime authorization",
        "repeated_late_arrival": "Review shift timing and arrival history",
        "missing_clock_out": "Request employee/supervisor verification",
        "abnormal_break_duration": "Verify break approval and policy",
        "duplicate_attendance": "Review duplicate punch records",
        "unusual_absence_frequency": "Cross-check approved leave records",
    }
    for anom_type, expected in expected_mappings.items():
        summary = ActionRegistry.get_short_recommendation_summary(anom_type)
        assert summary == expected, f"Mismatch for {anom_type}: expected '{expected}', got '{summary}'"

@pytest.mark.asyncio
async def test_anomaly_table_api_includes_suggested_action(auth_headers):
    """Verify GET /api/v1/anomalies returns suggested_action for each row."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/anomalies", headers=auth_headers)
        assert res.status_code == 200
        anomalies = res.json()
        assert len(anomalies) > 0
        for anom in anomalies:
            assert "suggested_action" in anom
            assert anom["suggested_action"] is not None
            assert len(anom["suggested_action"]) > 5
            assert "recommendation_priority" in anom
            assert "recommendation_source" in anom

@pytest.mark.asyncio
async def test_anomaly_investigate_contains_all_popup_sections(auth_headers):
    """Verify GET /api/v1/anomalies/{id}/investigate returns all 8 required sections."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        list_res = await client.get("/api/v1/anomalies", headers=auth_headers)
        anomalies = list_res.json()
        anom_id = anomalies[0]["id"]

        res = await client.get(f"/api/v1/anomalies/{anom_id}/investigate", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()

        # 1. Anomaly details
        assert data["anomaly_id"] == anom_id
        assert data["employee_name"] is not None
        assert data["severity"] in ["low", "medium", "high", "critical"]

        # 2. Why flagged
        assert "why_flagged_explanation" in data or "explanation" in data
        assert "possible_causes" in data
        assert len(data["possible_causes"]) > 0

        # 3. Actual vs expected
        assert "actual_vs_expected" in data or "comparison" in data
        comp = data.get("actual_vs_expected") or data.get("comparison")
        assert "actual_worked_minutes" in comp

        # 4. Historical context
        assert "historical_context" in data

        # 5. Recommended actions (2-4 practical steps)
        recs = data.get("recommended_actions") or data.get("recommendations")
        assert len(recs) >= 2
        for r in recs:
            assert "title" in r
            assert "action" in r
            assert "reason" in r
            assert "required_authorization" in r

        # 6. Suggested action
        assert "suggested_action" in data
        assert len(data["suggested_action"]) > 5

@pytest.mark.asyncio
async def test_all_four_policies_reading_and_download(auth_headers):
    """Verify all 4 corporate policies exist, can be read, and downloaded without empty content."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # List policies
        res = await client.get("/api/v1/policies", headers=auth_headers)
        assert res.status_code == 200
        policies = res.json()
        assert len(policies) == 4, f"Expected exactly 4 policies, found {len(policies)}"

        for pol in policies:
            assert pol["status"] == "active"
            assert pol["chunk_count"] > 0
            assert pol["file_size"] > 0

            # Test content extraction (Reading)
            c_res = await client.get(f"/api/v1/policies/{pol['id']}/content", headers=auth_headers)
            assert c_res.status_code == 200
            content_data = c_res.json()
            assert content_data["elements_count"] > 0
            assert len(content_data["elements"]) > 0

            # Verify non-empty text in elements
            has_valid_text = any(len(el.get("text", "").strip()) > 10 for el in content_data["elements"])
            assert has_valid_text, f"Policy {pol['title']} returned empty text elements!"

            # Test download
            d_res = await client.get(f"/api/v1/policies/{pol['id']}/download", headers=auth_headers)
            assert d_res.status_code == 200
            assert len(d_res.content) > 0
            assert "Content-Disposition" in d_res.headers

@pytest.mark.asyncio
async def test_policy_search_all_four_documents(auth_headers):
    """Verify search finds sections across different policies."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Search attendance
        s1 = await client.get("/api/v1/policies/search?query=grace+period", headers=auth_headers)
        assert s1.status_code == 200
        assert len(s1.json()) > 0
        assert "Attendance" in s1.json()[0]["citation"]

        # Search leave
        s2 = await client.get("/api/v1/policies/search?query=annual+leave", headers=auth_headers)
        assert s2.status_code == 200
        assert len(s2.json()) > 0
        assert "Leave" in s2.json()[0]["citation"]

        # Search remote work
        s3 = await client.get("/api/v1/policies/search?query=remote+work", headers=auth_headers)
        assert s3.status_code == 200
        assert len(s3.json()) > 0
        assert "Remote" in s3.json()[0]["citation"]

        # Search code of conduct
        s4 = await client.get("/api/v1/policies/search?query=harassment", headers=auth_headers)
        assert s4.status_code == 200
        assert len(s4.json()) > 0
        assert "Conduct" in s4.json()[0]["citation"]
