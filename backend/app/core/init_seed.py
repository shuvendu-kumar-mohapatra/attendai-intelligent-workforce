import uuid
import random
import logging
from datetime import datetime, date, time, timedelta
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.models import (
    Organization, Department, Shift, User, Employee,
    EmployeeShiftAssignment, AttendanceRecord, AttendanceBreak, AttendanceAnomaly,
    Policy, PolicyChunk, LeaveRecord
)

logger = logging.getLogger("attendai.seed")

# Deterministic seed for reproducible testing
random.seed(42)

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

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
    "Kenneth", "Dorothy", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa",
    "Timothy", "Deborah", "Ronald", "Stephanie", "Edward", "Rebecca", "Jason", "Sharon"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores"
]

DESIGNATIONS = [
    "Software Engineer", "Senior Software Engineer", "Product Manager", "UX Designer",
    "HR Specialist", "Talent Acquisition Lead", "Financial Analyst", "Operations Manager",
    "Account Executive", "Marketing Coordinator", "Support Engineer", "Customer Success Lead"
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
    Checks if the database has full workforce data (>= 100 employees).
    If underpopulated, seeds the full 200 workforce employees, shift assignments,
    60 days of attendance history across all departments, realistic anomalies,
    and leave records to match the rich local demonstration environment.
    """
    stmt = select(func.count(Employee.id))
    emp_count = (await db.execute(stmt)).scalar() or 0
    if emp_count >= 100:
        logger.info(f"Database already contains {emp_count} employees. Full workforce seeding skipped.")
        return False

    logger.info(f"Database has {emp_count} employees (< 100). Initiating full workforce auto-seed...")

    # Clear placeholder data if any exists to avoid duplicate key conflicts
    if emp_count > 0:
        logger.info("Purging underpopulated placeholder records...")
        await db.execute(delete(AttendanceAnomaly))
        await db.execute(delete(AttendanceBreak))
        await db.execute(delete(AttendanceRecord))
        await db.execute(delete(LeaveRecord))
        await db.execute(delete(PolicyChunk))
        await db.execute(delete(Policy))
        await db.execute(delete(EmployeeShiftAssignment))
        await db.execute(delete(Employee))
        await db.execute(delete(Shift))
        await db.execute(delete(Department))
        await db.execute(delete(User))
        await db.execute(delete(Organization))
        await db.flush()

    # 1. Organization
    org = Organization(
        id=str(uuid.uuid4()),
        name="AttendAI Global Technologies",
        timezone="UTC"
    )
    db.add(org)
    await db.flush()

    # 2. Departments
    dept_objs = []
    for d in DEPARTMENTS:
        dept = Department(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            name=d["name"],
            code=d["code"]
        )
        db.add(dept)
        dept_objs.append(dept)
    await db.flush()

    # 3. Shifts
    shift_objs = []
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
        shift_objs.append(sh)
    await db.flush()

    # 4. Primary Demo Users
    # 4a. Admin
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

    # 5. Primary Employee profiles
    demo_emp = Employee(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        department_id=dept_objs[0].id,
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

    demo_hr_emp = Employee(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        department_id=dept_objs[1].id,
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
    db.add(demo_hr_emp)
    await db.flush()

    # Manager of HR department
    dept_objs[1].manager_id = demo_hr_emp.id

    employees_list = [demo_emp, demo_hr_emp]

    # 6. Generate 198 additional workforce employees (Total 200)
    logger.info("Generating 198 workforce employees...")
    for i in range(3, 201):
        fn = random.choice(FIRST_NAMES)
        ln = random.choice(LAST_NAMES)
        dept = random.choice(dept_objs)
        code = f"EMP{i:03d}"
        email = f"{fn.lower()}.{ln.lower()}{i}@attendai.com"
        designation = random.choice(DESIGNATIONS)
        join_date = date(2022, 1, 1) + timedelta(days=random.randint(0, 700))

        u_id = str(uuid.uuid4())
        u = User(
            id=u_id,
            organization_id=org.id,
            email=email,
            hashed_password=hash_password("AttendAI@123"),
            role="employee",
            is_active=True
        )
        db.add(u)

        emp = Employee(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            department_id=dept.id,
            user_id=u_id,
            employee_code=code,
            first_name=fn,
            last_name=ln,
            email=email,
            phone=f"+1-555-{i:04d}",
            designation=designation,
            date_of_joining=join_date,
            is_active=True
        )
        db.add(emp)
        employees_list.append(emp)

    await db.flush()

    # 7. Assign Shifts to 200 Employees
    gen_shift = shift_objs[0]
    for emp in employees_list:
        assigned_shift = random.choice(shift_objs) if random.random() < 0.25 else gen_shift
        assign = EmployeeShiftAssignment(
            id=str(uuid.uuid4()),
            employee_id=emp.id,
            shift_id=assigned_shift.id,
            effective_from=emp.date_of_joining,
            is_active=True
        )
        db.add(assign)
    await db.flush()

    # 8. Simulate 60 Days of Attendance History
    logger.info("Simulating 60 days of workforce attendance...")
    today = date.today()
    created_records_count = 0
    anomaly_count = 0

    for day_offset in range(59, -1, -1):
        cur_date = today - timedelta(days=day_offset)
        # Skip weekends
        if cur_date.weekday() >= 5:
            continue

        for emp in employees_list:
            roll = random.random()
            if roll < 0.08:
                continue  # Absent

            is_late = roll < 0.22
            is_overtime = roll > 0.85
            is_missing_punch = (roll > 0.78 and roll < 0.81 and day_offset > 0)

            shift_start = datetime.combine(cur_date, time(9, 0))
            if is_late:
                clock_in_time = shift_start + timedelta(minutes=random.randint(18, 55))
                late_min = int((clock_in_time - shift_start).total_seconds() / 60)
                status_str = "late"
            else:
                clock_in_time = shift_start - timedelta(minutes=random.randint(5, 15))
                late_min = 0
                status_str = "present"

            if is_missing_punch:
                clock_out_time = None
                worked_min = 0
                ot_min = 0
                status_str = "incomplete"
            elif is_overtime:
                worked_min = 480 + random.randint(60, 240)
                clock_out_time = clock_in_time + timedelta(minutes=worked_min + 60)
                ot_min = worked_min - 480
            else:
                worked_min = 480 + random.randint(-15, 30)
                clock_out_time = clock_in_time + timedelta(minutes=worked_min + 60)
                ot_min = max(0, worked_min - 480)

            rec_id = str(uuid.uuid4())
            rec = AttendanceRecord(
                id=rec_id,
                organization_id=org.id,
                employee_id=emp.id,
                date=cur_date,
                clock_in=clock_in_time,
                clock_out=clock_out_time,
                worked_minutes=worked_min,
                overtime_minutes=ot_min,
                late_minutes=late_min,
                status=status_str,
                is_corrected=False
            )
            db.add(rec)
            created_records_count += 1

            if clock_out_time:
                b_start = clock_in_time + timedelta(hours=4)
                b_end = b_start + timedelta(minutes=random.randint(30, 45))
                db.add(AttendanceBreak(
                    id=str(uuid.uuid4()),
                    attendance_record_id=rec_id,
                    break_start=b_start,
                    break_end=b_end,
                    duration_minutes=int((b_end - b_start).total_seconds() / 60),
                    reason="Lunch Break"
                ))

            # Anomalies
            if anomaly_count < 40:
                if is_missing_punch:
                    db.add(AttendanceAnomaly(
                        id=str(uuid.uuid4()),
                        organization_id=org.id,
                        employee_id=emp.id,
                        attendance_record_id=rec_id,
                        date=cur_date,
                        anomaly_type="missing_clock_out",
                        severity="high",
                        score=0.88,
                        detection_method="rule_based",
                        explanation=f"Missing clock-out detected for {emp.first_name} {emp.last_name} on {cur_date}.",
                        status="pending" if day_offset < 10 else "resolved",
                        resolution_notes="Resolved upon supervisor confirmation." if day_offset >= 10 else None
                    ))
                    anomaly_count += 1
                elif is_overtime and ot_min > 180:
                    db.add(AttendanceAnomaly(
                        id=str(uuid.uuid4()),
                        organization_id=org.id,
                        employee_id=emp.id,
                        attendance_record_id=rec_id,
                        date=cur_date,
                        anomaly_type="excessive_overtime",
                        severity="medium",
                        score=0.72,
                        detection_method="rule_based",
                        explanation=f"Worked overtime of {ot_min} minutes exceeds the threshold of 180 minutes.",
                        status="pending" if day_offset < 7 else "resolved"
                    ))
                    anomaly_count += 1

    # 9. HR Policies
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

    # 10. Sample Leave Records
    for i in range(15):
        emp = random.choice(employees_list[:30])
        s_date = today + timedelta(days=random.randint(2, 20))
        e_date = s_date + timedelta(days=random.randint(1, 4))
        db.add(LeaveRecord(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            employee_id=emp.id,
            leave_type=random.choice(["annual", "sick", "casual"]),
            start_date=s_date,
            end_date=e_date,
            days_count=float((e_date - s_date).days + 1),
            reason="Scheduled family vacation and personal time off.",
            status=random.choice(["pending", "approved"])
        ))

    await db.commit()
    logger.info(f"Full workforce auto-seed completed! Seeded {len(employees_list)} employees, {created_records_count} attendance records, {anomaly_count} anomalies.")
    return True
