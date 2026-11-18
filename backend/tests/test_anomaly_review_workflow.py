import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, desc
from app.main import app
from app.core.database import get_db
from app.models.models import AttendanceAnomaly, AuditLog

@pytest.fixture
async def admin_headers():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/v1/auth/login", json={
            "email": "admin@attendai.com",
            "password": "Admin@123"
        })
        assert res.status_code == 200
        token = res.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

@pytest.fixture
async def hr_headers():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/v1/auth/login", json={
            "email": "hrmanager@attendai.com",
            "password": "HRManager@123"
        })
        assert res.status_code == 200
        token = res.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

@pytest.fixture
async def employee_headers():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/v1/auth/login", json={
            "email": "employee@attendai.com",
            "password": "Employee@123"
        })
        assert res.status_code == 200
        token = res.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_all_five_resolution_statuses_e2e(admin_headers, hr_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Fetch available anomalies
        res = await client.get("/api/v1/anomalies", headers=admin_headers)
        assert res.status_code == 200
        anomalies = res.json()
        assert len(anomalies) > 0

        # We will test each of the 5 statuses:
        test_statuses = [
            ("under_review", "Audited initial punch, awaiting timesheet supervisor confirmation."),
            ("correction_requested", "Initiated attendance clock-in adjustment with manager."),
            ("escalated", "Escalated repeated overtime discrepancy to HR leadership."),
            ("dismissed", "Verified approved remote schedule variance, marked false positive."),
            ("resolved", "Shift supervisor verified overtime pre-authorization; timesheet approved.")
        ]

        async for db in get_db():
            for idx, (status_val, note_val) in enumerate(test_statuses):
                # Ensure we have a pending anomaly for testing
                anom_id = anomalies[idx % len(anomalies)]["id"]
                anom_db = (await db.execute(select(AttendanceAnomaly).where(AttendanceAnomaly.id == anom_id))).scalars().first()
                anom_db.status = "pending"
                anom_db.resolution_notes = None
                anom_db.reviewed_by = None
                anom_db.reviewed_at = None
                await db.commit()

                # Alternate between Admin and HR Manager
                current_headers = admin_headers if idx % 2 == 0 else hr_headers

                # Execute PUT /{anomaly_id}/review
                rev_res = await client.put(
                    f"/api/v1/anomalies/{anom_id}/review",
                    headers=current_headers,
                    json={
                        "status": status_val,
                        "resolution_notes": note_val
                    }
                )

                assert rev_res.status_code == 200, f"Failed for status {status_val}: {rev_res.text}"
                data = rev_res.json()
                assert data["status"] == status_val
                assert data["resolution_notes"] == note_val
                assert data["reviewed_by"] is not None
                assert data["reviewed_at"] is not None
                assert data["suggested_action"] is not None

                # Verify actual database persistence
                await db.refresh(anom_db)
                assert anom_db.status == status_val
                assert anom_db.resolution_notes == note_val

                # Verify AuditLog row persisted in DB
                audit_res = await db.execute(
                    select(AuditLog)
                    .where(AuditLog.resource_id == anom_id, AuditLog.action == "anomaly_investigation_resolution")
                    .order_by(desc(AuditLog.created_at))
                )
                audit = audit_res.scalars().first()
                assert audit is not None
                assert audit.details["new_status"] == status_val
                assert audit.details["resolution_notes"] == note_val
                assert audit.details["previous_status"] == "pending"
            break

@pytest.mark.asyncio
async def test_review_validation_and_unauthorized_rejections(admin_headers, employee_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get an anomaly
        res = await client.get("/api/v1/anomalies", headers=admin_headers)
        assert res.status_code == 200
        anom_id = res.json()[0]["id"]

        # Ensure it is pending first
        async for db in get_db():
            anom_db = (await db.execute(select(AttendanceAnomaly).where(AttendanceAnomaly.id == anom_id))).scalars().first()
            anom_db.status = "pending"
            await db.commit()
            break

        # 1. Test unauthorized employee role (Must return 403 Forbidden)
        emp_res = await client.put(
            f"/api/v1/anomalies/{anom_id}/review",
            headers=employee_headers,
            json={
                "status": "resolved",
                "resolution_notes": "Employee attempting unauthorized resolution"
            }
        )
        assert emp_res.status_code == 403

        # 2. Test invalid resolution status
        inv_res = await client.put(
            f"/api/v1/anomalies/{anom_id}/review",
            headers=admin_headers,
            json={
                "status": "unknown_action_type",
                "resolution_notes": "Some notes"
            }
        )
        assert inv_res.status_code == 400
        assert "Invalid resolution status" in inv_res.json()["detail"]

        # 3. Test empty/whitespace notes rejection
        empty_res = await client.put(
            f"/api/v1/anomalies/{anom_id}/review",
            headers=admin_headers,
            json={
                "status": "resolved",
                "resolution_notes": "   "
            }
        )
        assert empty_res.status_code == 400
        assert "Mandatory resolution notes are required" in empty_res.json()["detail"]

        # 4. Resolve legitimately
        ok_res = await client.put(
            f"/api/v1/anomalies/{anom_id}/review",
            headers=admin_headers,
            json={
                "status": "resolved",
                "resolution_notes": "Legitimate manager verification"
            }
        )
        assert ok_res.status_code == 200

        # 5. Conflict rejection when trying to re-resolve an already closed anomaly
        conflict_res = await client.put(
            f"/api/v1/anomalies/{anom_id}/review",
            headers=admin_headers,
            json={
                "status": "dismissed",
                "resolution_notes": "Trying to modify closed anomaly"
            }
        )
        assert conflict_res.status_code == 409
        assert "already been resolved and closed" in conflict_res.json()["detail"]

@pytest.mark.asyncio
async def test_investigate_already_resolved_anomaly_no_ai_insight(admin_headers):
    """Verify that investigating an already resolved anomaly does not formulate new AI insights."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/anomalies", headers=admin_headers)
        anom_id = res.json()[0]["id"]

        # Set status to resolved in DB
        async for db in get_db():
            anom_db = (await db.execute(select(AttendanceAnomaly).where(AttendanceAnomaly.id == anom_id))).scalars().first()
            anom_db.status = "resolved"
            anom_db.resolution_notes = "Audited and verified by HR compliance team."
            await db.commit()
            break

        # Investigate resolved anomaly
        inv_res = await client.get(f"/api/v1/anomalies/{anom_id}/investigate", headers=admin_headers)
        assert inv_res.status_code == 200
        data = inv_res.json()
        assert data["current_status"] == "resolved"
        assert data["current_resolution_notes"] == "Audited and verified by HR compliance team."
        # No new AI recommended action for resolved issues
        assert data["ai_recommended_action"] is None
