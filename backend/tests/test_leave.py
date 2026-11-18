import pytest
from datetime import date, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, and_
from app.main import app
from app.core.database import get_sessionmaker
from app.core.security import create_access_token
from app.models.models import User, Employee, LeaveRecord, Notification

@pytest.fixture(autouse=True)
async def cleanup_test_leaves():
    from sqlalchemy import delete
    sm = get_sessionmaker()
    async with sm() as db:
        await db.execute(delete(LeaveRecord).where(LeaveRecord.start_date >= date(2027, 1, 1)))
        await db.commit()
    yield
    async with sm() as db:
        await db.execute(delete(LeaveRecord).where(LeaveRecord.start_date >= date(2027, 1, 1)))
        await db.commit()

@pytest.fixture
async def auth_contexts():
    sm = get_sessionmaker()
    async with sm() as db:
        admin_user = (await db.execute(select(User).where(User.role == "admin"))).scalars().first()
        hr_user = (await db.execute(select(User).where(User.role == "hr_manager"))).scalars().first()
        emp_user = (await db.execute(select(User).where(User.role == "employee"))).scalars().first()
        
        assert admin_user is not None
        assert hr_user is not None
        assert emp_user is not None

        emp_profile = (await db.execute(select(Employee).where(Employee.user_id == emp_user.id))).scalars().first()
        assert emp_profile is not None

        admin_token = create_access_token({"sub": admin_user.id, "email": admin_user.email, "role": admin_user.role, "org_id": admin_user.organization_id})
        hr_token = create_access_token({"sub": hr_user.id, "email": hr_user.email, "role": hr_user.role, "org_id": hr_user.organization_id})
        emp_token = create_access_token({"sub": emp_user.id, "email": emp_user.email, "role": emp_user.role, "org_id": emp_user.organization_id})

        # Fetch a secondary employee to test cross-employee authorization
        other_user = (await db.execute(
            select(User).where(and_(User.role == "employee", User.id != emp_user.id))
        )).scalars().first()
        other_emp = None
        other_token = None
        if other_user:
            other_emp = (await db.execute(select(Employee).where(Employee.user_id == other_user.id))).scalars().first()
            other_token = create_access_token({"sub": other_user.id, "email": other_user.email, "role": other_user.role, "org_id": other_user.organization_id})

    return {
        "admin_headers": {"Authorization": f"Bearer {admin_token}"},
        "hr_headers": {"Authorization": f"Bearer {hr_token}"},
        "emp_headers": {"Authorization": f"Bearer {emp_token}"},
        "emp_profile": emp_profile,
        "other_headers": {"Authorization": f"Bearer {other_token}"} if other_token else None,
        "other_emp": other_emp
    }

@pytest.mark.asyncio
async def test_get_leave_balances_employee(auth_contexts):
    headers = auth_contexts["emp_headers"]
    emp = auth_contexts["emp_profile"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/leave/balances", headers=headers)

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["employee_id"] == emp.id
    assert "categories" in data
    cats = data["categories"]
    assert "annual" in cats
    assert "sick" in cats
    assert "casual" in cats
    assert "unpaid" in cats
    assert cats["annual"]["entitlement"] == 20.0
    assert cats["sick"]["entitlement"] == 10.0
    assert cats["casual"]["entitlement"] == 5.0
    assert cats["unpaid"]["entitlement"] is None
    assert data["total_entitlement"] == 35.0

@pytest.mark.asyncio
async def test_get_leave_balances_hr_for_target_employee(auth_contexts):
    hr_headers = auth_contexts["hr_headers"]
    emp = auth_contexts["emp_profile"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/api/v1/leave/balances?employee_id={emp.id}", headers=hr_headers)

    assert res.status_code == 200
    data = res.json()
    assert data["employee_id"] == emp.id
    assert data["employee_code"] == emp.employee_code

@pytest.mark.asyncio
async def test_apply_leave_success_and_lifecycle(auth_contexts):
    emp_headers = auth_contexts["emp_headers"]
    emp = auth_contexts["emp_profile"]
    hr_headers = auth_contexts["hr_headers"]

    # Use future dates to avoid overlap with existing seed data
    target_start = date(2027, 6, 1)
    target_end = date(2027, 6, 3) # 3 days

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Apply for leave
        apply_res = await ac.post(
            "/api/v1/leave",
            json={
                "leave_type": "annual",
                "start_date": str(target_start),
                "end_date": str(target_end),
                "reason": "Summer vacation with family"
            },
            headers=emp_headers
        )
        assert apply_res.status_code == 201, apply_res.text
        leave_data = apply_res.json()
        leave_id = leave_data["id"]
        assert leave_data["status"] == "pending"
        assert leave_data["days_count"] == 3.0
        assert leave_data["employee_id"] == emp.id
        assert leave_data["employee_name"] == f"{emp.first_name} {emp.last_name}"

        # 2. Get leave by ID
        get_res = await ac.get(f"/api/v1/leave/{leave_id}", headers=emp_headers)
        assert get_res.status_code == 200
        assert get_res.json()["id"] == leave_id

        # 3. Verify balance reflects pending leave
        bal_res = await ac.get("/api/v1/leave/balances?year=2027", headers=emp_headers)
        assert bal_res.status_code == 200
        bal_data = bal_res.json()
        assert bal_data["categories"]["annual"]["pending"] == 3.0

        # 4. HR reviews and approves leave
        review_res = await ac.put(
            f"/api/v1/leave/{leave_id}/review",
            json={
                "status": "approved",
                "resolution_notes": "Approved by HR Director. Enjoy your vacation!"
            },
            headers=hr_headers
        )
        assert review_res.status_code == 200, review_res.text
        reviewed_data = review_res.json()
        assert reviewed_data["status"] == "approved"
        assert reviewed_data["resolution_notes"] == "Approved by HR Director. Enjoy your vacation!"

        # 5. Verify invalid status is rejected and approved leave cannot be cancelled
        invalid_review = await ac.put(
            f"/api/v1/leave/{leave_id}/review",
            json={"status": "unknown_status", "resolution_notes": "Trying invalid status"},
            headers=hr_headers
        )
        assert invalid_review.status_code == 422

        cannot_cancel = await ac.post(f"/api/v1/leave/{leave_id}/cancel", headers=emp_headers)
        assert cannot_cancel.status_code == 422

@pytest.mark.asyncio
async def test_apply_leave_validation_errors(auth_contexts):
    emp_headers = auth_contexts["emp_headers"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Invalid date order: end before start
        res1 = await ac.post(
            "/api/v1/leave",
            json={
                "leave_type": "annual",
                "start_date": "2027-08-10",
                "end_date": "2027-08-05",
                "reason": "Invalid dates"
            },
            headers=emp_headers
        )
        assert res1.status_code == 422
        assert "End date cannot precede start date" in res1.text

        # Invalid leave type
        res2 = await ac.post(
            "/api/v1/leave",
            json={
                "leave_type": "sabbatical_unsupported",
                "start_date": "2027-08-01",
                "end_date": "2027-08-05",
                "reason": "Invalid type"
            },
            headers=emp_headers
        )
        assert res2.status_code == 422
        assert "Invalid leave type" in res2.text

@pytest.mark.asyncio
async def test_apply_leave_overlap_conflict(auth_contexts):
    emp_headers = auth_contexts["emp_headers"]

    start = date(2027, 9, 1)
    end = date(2027, 9, 5)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. First application succeeds
        res1 = await ac.post(
            "/api/v1/leave",
            json={
                "leave_type": "casual",
                "start_date": str(start),
                "end_date": str(end),
                "reason": "Personal emergency"
            },
            headers=emp_headers
        )
        assert res1.status_code == 201
        created_id = res1.json()["id"]

        # 2. Overlapping application (overlapping dates: 2027-09-03 to 2027-09-07)
        res2 = await ac.post(
            "/api/v1/leave",
            json={
                "leave_type": "casual",
                "start_date": "2027-09-03",
                "end_date": "2027-09-07",
                "reason": "Duplicate overlapping request"
            },
            headers=emp_headers
        )
        assert res2.status_code == 409
        assert "conflicts with an existing" in res2.text

        # Clean up: cancel first request
        cancel_res = await ac.post(f"/api/v1/leave/{created_id}/cancel", headers=emp_headers)
        assert cancel_res.status_code == 200

@pytest.mark.asyncio
async def test_apply_leave_exceeds_quota(auth_contexts):
    emp_headers = auth_contexts["emp_headers"]

    # Annual quota is 20 days. Requesting 25 days should fail.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/leave",
            json={
                "leave_type": "casual",  # Casual quota is only 5 days
                "start_date": "2027-10-01",
                "end_date": "2027-10-10",  # 10 days > 5 days quota
                "reason": "Extended casual leave"
            },
            headers=emp_headers
        )
        assert res.status_code == 422
        assert "Insufficient casual leave balance" in res.text

@pytest.mark.asyncio
async def test_cancel_pending_leave_by_employee(auth_contexts):
    emp_headers = auth_contexts["emp_headers"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Apply for leave
        res = await ac.post(
            "/api/v1/leave",
            json={
                "leave_type": "sick",
                "start_date": "2027-11-01",
                "end_date": "2027-11-02",
                "reason": "Doctor appointment"
            },
            headers=emp_headers
        )
        assert res.status_code == 201
        leave_id = res.json()["id"]

        # 2. Cancel leave with custom rationale
        cancel_res = await ac.post(
            f"/api/v1/leave/{leave_id}/cancel",
            json={"reason": "Appointment rescheduled by clinic"},
            headers=emp_headers
        )
        assert cancel_res.status_code == 200
        cancelled_data = cancel_res.json()
        assert cancelled_data["status"] == "cancelled"
        assert "Appointment rescheduled" in cancelled_data["resolution_notes"]

        # 3. Trying to cancel again fails
        cancel_again = await ac.post(f"/api/v1/leave/{leave_id}/cancel", headers=emp_headers)
        assert cancel_again.status_code == 422

@pytest.mark.asyncio
async def test_cross_employee_cancel_forbidden(auth_contexts):
    if not auth_contexts["other_headers"]:
        pytest.skip("Secondary employee profile not available")

    emp_headers = auth_contexts["emp_headers"]
    other_headers = auth_contexts["other_headers"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Employee 1 applies for leave
        create_res = await ac.post(
            "/api/v1/leave",
            json={
                "leave_type": "annual",
                "start_date": "2027-12-01",
                "end_date": "2027-12-02",
                "reason": "Personal time"
            },
            headers=emp_headers
        )
        assert create_res.status_code == 201
        leave_id = create_res.json()["id"]

        # Employee 2 attempts to cancel Employee 1's leave -> 403 Forbidden
        cancel_forbidden = await ac.post(f"/api/v1/leave/{leave_id}/cancel", headers=other_headers)
        assert cancel_forbidden.status_code == 403

        # Employee 2 attempts to view Employee 1's leave -> 403 Forbidden
        get_forbidden = await ac.get(f"/api/v1/leave/{leave_id}", headers=other_headers)
        assert get_forbidden.status_code == 403

        # Clean up
        await ac.delete(f"/api/v1/leave/{leave_id}", headers=emp_headers)

@pytest.mark.asyncio
async def test_leave_notifications_generated(auth_contexts):
    emp_headers = auth_contexts["emp_headers"]
    hr_headers = auth_contexts["hr_headers"]

    sm = get_sessionmaker()
    # Mark existing unread notifications as read to avoid deduplication suppression
    async with sm() as db:
        from sqlalchemy import update
        await db.execute(update(Notification).values(is_read=True))
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Apply leave
        res = await ac.post(
            "/api/v1/leave",
            json={
                "leave_type": "sick",
                "start_date": "2027-07-15",
                "end_date": "2027-07-16",
                "reason": "Flu symptoms"
            },
            headers=emp_headers
        )
        assert res.status_code == 201
        leave_id = res.json()["id"]

        # Verify HR received notification
        async with sm() as db:
            hr_user = (await db.execute(select(User).where(User.role == "hr_manager"))).scalars().first()
            notif = (await db.execute(
                select(Notification).where(
                    and_(
                        Notification.user_id == hr_user.id,
                        Notification.category == "leave",
                        Notification.title == "New Leave Application"
                    )
                ).order_by(Notification.created_at.desc())
            )).scalars().first()
            assert notif is not None
            assert "Flu symptoms" not in notif.message  # Reason is kept in request; message has dates/count
            assert "Sick Leave request" in notif.message

        # 2. HR rejects leave
        review_res = await ac.put(
            f"/api/v1/leave/{leave_id}/review",
            json={"status": "rejected", "resolution_notes": "Critical milestone deployment on these dates."},
            headers=hr_headers
        )
        assert review_res.status_code == 200
        assert review_res.json()["status"] == "rejected"

        # Verify employee received review notification
        async with sm() as db:
            emp_user = (await db.execute(select(User).where(User.role == "employee"))).scalars().first()
            emp_notif = (await db.execute(
                select(Notification).where(
                    and_(
                        Notification.user_id == emp_user.id,
                        Notification.category == "leave",
                        Notification.title == "Leave Request Rejected"
                    )
                ).order_by(Notification.created_at.desc())
            )).scalars().first()
            assert emp_notif is not None
            assert "rejected" in emp_notif.message
            assert "Critical milestone deployment" in emp_notif.message

@pytest.mark.asyncio
async def test_list_leave_filtering(auth_contexts):
    emp_headers = auth_contexts["emp_headers"]
    hr_headers = auth_contexts["hr_headers"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create an annual leave
        res1 = await ac.post(
            "/api/v1/leave",
            json={"leave_type": "annual", "start_date": "2027-01-10", "end_date": "2027-01-11", "reason": "New Year trip"},
            headers=emp_headers
        )
        assert res1.status_code == 201

        # List with filter leave_type=annual
        list_res = await ac.get("/api/v1/leave?leave_type=annual&status_filter=pending", headers=hr_headers)
        assert list_res.status_code == 200
        items = list_res.json()
        assert len(items) >= 1
        for item in items:
            assert item["leave_type"] == "annual"
            assert item["status"] == "pending"

@pytest.mark.asyncio
async def test_delete_endpoint_cancels_leave(auth_contexts):
    emp_headers = auth_contexts["emp_headers"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/leave",
            json={"leave_type": "sick", "start_date": "2027-02-10", "end_date": "2027-02-10", "reason": "Dentist visit"},
            headers=emp_headers
        )
        assert res.status_code == 201
        leave_id = res.json()["id"]

        # Call DELETE /leave/{id}
        del_res = await ac.delete(f"/api/v1/leave/{leave_id}", headers=emp_headers)
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "cancelled"

@pytest.mark.asyncio
async def test_admin_can_cancel_any_pending_leave(auth_contexts):
    emp_headers = auth_contexts["emp_headers"]
    admin_headers = auth_contexts["admin_headers"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/leave",
            json={"leave_type": "casual", "start_date": "2027-03-10", "end_date": "2027-03-11", "reason": "Personal errands"},
            headers=emp_headers
        )
        assert res.status_code == 201
        leave_id = res.json()["id"]

        # Admin cancels it
        cancel_res = await ac.post(
            f"/api/v1/leave/{leave_id}/cancel",
            json={"reason": "Admin schedule rebalance"},
            headers=admin_headers
        )
        assert cancel_res.status_code == 200
        data = cancel_res.json()
        assert data["status"] == "cancelled"
        assert "Admin schedule rebalance" in data["resolution_notes"]

@pytest.mark.asyncio
async def test_summary_alias_endpoint(auth_contexts):
    emp_headers = auth_contexts["emp_headers"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/leave/summary", headers=emp_headers)
        assert res.status_code == 200
        data = res.json()
        assert "categories" in data
        assert "total_available" in data

