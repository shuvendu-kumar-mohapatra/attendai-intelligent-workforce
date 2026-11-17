import uuid
import logging
from datetime import datetime, date, time, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.models import (
    Organization, Department, Shift, User, Employee,
    EmployeeShiftAssignment, AttendanceRecord, AttendanceBreak, AttendanceAnomaly,
    Policy, PolicyChunk, LeaveRecord
)

logger = logging.getLogger("attendai.seed")

DEPARTMENTS = [
    {"name": "Engineering", "code": "ENG"},
    {"name": "Human Resources", "code": "HR"},
    {"name": "Product & Design", "code": "PRD"},
    {"name": "Sales & Marketing", "code": "SLS"},
    {"name": "Customer Success", "code": "CS"},
    {"name": "Finance & Operations", "code": "FIN"}
]

SHIFTS = [
    {"name": "General Shift", "code": "GEN", "start_time": time(9, 0), "end_time": time(17, 30), "grace": 15, "req_hours": 8.0, "overnight": False},
    {"name": "Morning Shift", "code": "MOR", "start_time": time(8, 0), "end_time": time(16, 30), "grace": 15, "req_hours": 8.0, "overnight": False},
    {"name": "Evening Shift", "code": "EVE", "start_time": time(14, 0), "end_time": time(22, 30), "grace": 15, "req_hours": 8.0, "overnight": False},
    {"name": "Night Shift", "code": "NOC", "start_time": time(22, 0), "end_time": time(6, 30), "grace": 15, "req_hours": 8.0, "overnight": True}
]

SAMPLE_POLICIES = [
    {
        "title": "AttendAI Global Attendance and Working Hours Policy",
        "category": "Attendance & Punctuality",
        "chunks": [
            ("Core Working Hours", 1, "AttendAI core working hours are established between 09:00 and 17:30 local time. Employees are expected to clock in using the AttendAI portal upon starting work and clock out when completing daily duties. A standard working day consists of 8 productive hours plus a 30-minute to 1-hour lunch break."),
            ("Punctuality and Grace Periods", 1, "A grace period of 15 minutes is allowed for clock-in beyond scheduled shift start. Clock-ins occurring 16 minutes or more after the shift commencement are flagged as Late Arrivals. Repeated late arrivals exceeding 3 occurrences within a rolling 7-day period are automatically surfaced to HR managers for review."),
            ("Overtime Rules and Eligibility", 2, "Overtime commences once total worked duration in a calendar day exceeds the scheduled required shift hours (typically 8.0 hours). Overtime must be pre-authorized by department managers. Non-exempt employees will receive compensation or compensatory time-off in accordance with local labor standards.")
        ]
    },
    {
        "title": "Comprehensive Leave and Time-Off Guidelines",
        "category": "Leave Management",
        "chunks": [
            ("Annual Leave Allocation", 1, "Full-time employees accrue 20 days of paid annual leave per calendar year. Annual leave requests should be submitted at least 5 business days in advance via the AttendAI Leave portal and require supervisor approval."),
            ("Sick and Emergency Leave", 2, "Employees are granted 10 days of paid sick leave per year. Medical certificates are required for consecutive sick leaves exceeding 3 business days. Emergency personal leaves can be approved retrospectively upon manager consultation.")
        ]
    }
]

async def seed_database_if_empty(db: AsyncSession) -> bool:
    """
    Checks if the database is unpopulated (no User records).
    If empty, automatically populates the default Organization, Departments,
    Shifts, the 3 Primary Demo Accounts (Admin, HR Manager, Employee),
    shift assignments, and sample attendance history.
    """
    stmt = select(func.count(User.id))
    user_count = (await db.execute(stmt)).scalar() or 0
    if user_count > 0:
        logger.info(f"Database already contains {user_count} users. Auto-seed skipped.")
        return False

    logger.info("Empty database detected. Initiating automated bootstrap seeding...")

    # 1. Organization
    org = Organization(
        id=str(uuid.uuid4()),
        name="AttendAI Global Technologies",
        timezone="UTC"
    )
    db.add(org)
    await db.flush()

    # 2. Departments
    dept_map = {}
    for d in DEPARTMENTS:
        dept = Department(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            name=d["name"],
            code=d["code"]
        )
        db.add(dept)
        dept_map[d["code"]] = dept
    await db.flush()

    # 3. Shifts
    shift_map = {}
    for s in SHIFTS:
        sh = Shift(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            name=s["name"],
            code=s["code"],
            start_time=s["start_time"],
            end_time=s["end_time"],
            grace_period_minutes=s["grace"],
            required_hours=s["req_hours"],
            is_overnight=s["overnight"]
        )
        db.add(sh)
        shift_map[s["code"]] = sh
    await db.flush()

    # 4. Primary Demo Users
    # 4a. System Admin
    admin_user = User(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        email="admin@attendai.com",
        hashed_password=hash_password("Admin@123"),
        role="admin",
        is_active=True
    )
    db.add(admin_user)

    # 4b. HR Manager
    hr_user = User(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        email="hrmanager@attendai.com",
        hashed_password=hash_password("HRManager@123"),
        role="hr_manager",
        is_active=True
    )
    db.add(hr_user)

    # 4c. Employee
    emp_user = User(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        email="employee@attendai.com",
        hashed_password=hash_password("Employee@123"),
        role="employee",
        is_active=True
    )
    db.add(emp_user)
    await db.flush()

    # 5. Link Employee Profiles
    hr_emp = Employee(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        department_id=dept_map["HR"].id,
        user_id=hr_user.id,
        employee_code="EMP002",
        first_name="Eleanor",
        last_name="Vance",
        email="hrmanager@attendai.com",
        phone="+1-555-0102",
        designation="HR Director",
        date_of_joining=date(2022, 5, 10),
        is_active=True
    )
    db.add(hr_emp)

    demo_emp = Employee(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        department_id=dept_map["ENG"].id,
        user_id=emp_user.id,
        employee_code="EMP001",
        first_name="Alex",
        last_name="Mercer",
        email="employee@attendai.com",
        phone="+1-555-0101",
        designation="Software Engineer",
        date_of_joining=date(2023, 1, 15),
        is_active=True
    )
    db.add(demo_emp)
    await db.flush()

    # Update HR manager as manager of HR dept
    dept_map["HR"].manager_id = hr_emp.id

    # 6. Assign Shifts
    gen_shift = shift_map["GEN"]
    for emp_record in [hr_emp, demo_emp]:
        assign = EmployeeShiftAssignment(
            id=str(uuid.uuid4()),
            employee_id=emp_record.id,
            shift_id=gen_shift.id,
            effective_from=emp_record.date_of_joining,
            is_active=True
        )
        db.add(assign)
    await db.flush()

    # 7. Seed 30-Day Attendance History for Demo Employee Alex Mercer
    today = date.today()
    for day_offset in range(30, -1, -1):
        cur_date = today - timedelta(days=day_offset)
        # Skip weekends
        if cur_date.weekday() >= 5:
            continue

        # Alternate realistic attendance
        is_late = (day_offset % 7 == 2)
        base_clock_in = datetime.combine(cur_date, time(9, 0))
        if is_late:
            clock_in_time = base_clock_in + timedelta(minutes=22)
            late_min = 22
        else:
            clock_in_time = base_clock_in - timedelta(minutes=(day_offset % 8) + 1)
            late_min = 0

        base_clock_out = datetime.combine(cur_date, time(17, 30))
        clock_out_time = base_clock_out + timedelta(minutes=(day_offset % 30))
        worked_mins = int((clock_out_time - clock_in_time).total_seconds() / 60) - 45
        ot_mins = max(0, worked_mins - 480)

        rec = AttendanceRecord(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            employee_id=demo_emp.id,
            date=cur_date,
            clock_in=clock_in_time,
            clock_out=clock_out_time,
            worked_minutes=worked_mins,
            late_minutes=late_min,
            overtime_minutes=ot_mins,
            status="late" if is_late else "present"
        )
        db.add(rec)
        await db.flush()

        # Add lunch break
        b_start = datetime.combine(cur_date, time(13, 0))
        b_end = datetime.combine(cur_date, time(13, 45))
        db.add(AttendanceBreak(
            id=str(uuid.uuid4()),
            attendance_record_id=rec.id,
            break_start=b_start,
            break_end=b_end,
            duration_minutes=45,
            reason="Lunch"
        ))

        # Add anomaly if late
        if is_late:
            db.add(AttendanceAnomaly(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                employee_id=demo_emp.id,
                attendance_record_id=rec.id,
                date=cur_date,
                anomaly_type="repeated_late",
                severity="low",
                detection_method="rule_based",
                explanation="Clock-in at 09:22 exceeded 15 minute grace period.",
                status="resolved" if day_offset > 3 else "pending"
            ))

    # 8. Policies
    for p in SAMPLE_POLICIES:
        pol_id = str(uuid.uuid4())
        policy = Policy(
            id=pol_id,
            organization_id=org.id,
            title=p["title"],
            category=p["category"],
            file_size=10240,
            status="active"
        )
        db.add(policy)
        await db.flush()

        for sec, page, content in p["chunks"]:
            db.add(PolicyChunk(
                id=str(uuid.uuid4()),
                policy_id=pol_id,
                title=p["title"],
                section=sec,
                page_number=page,
                content=content,
                token_count=len(content.split())
            ))

    # 9. Sample Leave Record
    db.add(LeaveRecord(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        employee_id=demo_emp.id,
        leave_type="annual",
        start_date=today + timedelta(days=10),
        end_date=today + timedelta(days=12),
        days_count=3.0,
        reason="Annual vacation scheduled with team.",
        status="approved"
    ))

    await db.commit()
    logger.info("Automated bootstrap seeding completed successfully. Demo accounts are ready.")
    return True
