from datetime import datetime, date, time
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field

# ----------------- Auth & User -----------------
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: str = "employee"
    is_active: bool = True

class UserResponse(BaseModel):
    id: str
    organization_id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

# ----------------- Organization -----------------
class OrganizationResponse(BaseModel):
    id: str
    name: str
    timezone: str
    created_at: datetime

    class Config:
        from_attributes = True

# ----------------- Department -----------------
class DepartmentCreate(BaseModel):
    name: str
    code: str
    manager_id: Optional[str] = None

class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    manager_id: Optional[str] = None

class DepartmentResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    code: str
    manager_id: Optional[str] = None
    created_at: datetime
    employee_count: Optional[int] = 0

    class Config:
        from_attributes = True

# ----------------- Employee -----------------
class EmployeeCreate(BaseModel):
    department_id: Optional[str] = None
    employee_code: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    designation: str
    date_of_joining: date
    password: Optional[str] = "AttendAI@123"
    role: Optional[str] = "employee"

class EmployeeUpdate(BaseModel):
    department_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    designation: Optional[str] = None
    is_active: Optional[bool] = None

class EmployeeResponse(BaseModel):
    id: str
    organization_id: str
    department_id: Optional[str] = None
    user_id: Optional[str] = None
    employee_code: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    designation: str
    date_of_joining: date
    is_active: bool
    created_at: datetime
    department_name: Optional[str] = None
    current_shift: Optional[str] = None

    class Config:
        from_attributes = True

class EmployeeOnboardingRequestCreate(BaseModel):
    employee_code: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    department_id: Optional[str] = None
    designation: str
    date_of_joining: Optional[date] = None
    role: Optional[str] = "employee"

class EmployeeOnboardingReview(BaseModel):
    status: str  # approved, rejected
    rejection_reason: Optional[str] = None

class EmployeeOnboardingResponse(BaseModel):
    id: str
    organization_id: str
    requested_by_id: Optional[str] = None
    requested_by_name: Optional[str] = None
    employee_code: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    designation: Optional[str] = None
    date_of_joining: date
    role: str
    status: str
    reviewed_by_id: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

# ----------------- Shift -----------------
class ShiftCreate(BaseModel):
    name: str
    code: str
    start_time: time
    end_time: time
    grace_period_minutes: int = 15
    required_hours: float = 8.0
    is_overnight: bool = False

class ShiftUpdate(BaseModel):
    name: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    grace_period_minutes: Optional[int] = None
    required_hours: Optional[float] = None
    is_overnight: Optional[bool] = None

class ShiftResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    code: str
    start_time: time
    end_time: time
    grace_period_minutes: int
    required_hours: float
    is_overnight: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ShiftAssignmentCreate(BaseModel):
    employee_id: str
    shift_id: str
    effective_from: date
    effective_to: Optional[date] = None

class ShiftAssignmentResponse(BaseModel):
    id: str
    employee_id: str
    shift_id: str
    effective_from: date
    effective_to: Optional[date] = None
    is_active: bool
    shift_name: Optional[str] = None

    class Config:
        from_attributes = True

# ----------------- Attendance -----------------
class ClockInRequest(BaseModel):
    employee_id: Optional[str] = None # For admin punching on behalf, otherwise resolved from current user
    notes: Optional[str] = None

class ClockOutRequest(BaseModel):
    employee_id: Optional[str] = None
    notes: Optional[str] = None

class BreakRequest(BaseModel):
    employee_id: Optional[str] = None
    reason: Optional[str] = "Normal Break"

class BreakResponse(BaseModel):
    id: str
    break_start: datetime
    break_end: Optional[datetime] = None
    duration_minutes: int
    reason: Optional[str] = None

    class Config:
        from_attributes = True

class AttendanceResponse(BaseModel):
    id: str
    organization_id: str
    employee_id: str
    date: date
    clock_in: Optional[datetime] = None
    clock_out: Optional[datetime] = None
    worked_minutes: int
    overtime_minutes: int
    late_minutes: int
    status: str
    is_corrected: bool
    created_at: datetime
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    department_name: Optional[str] = None
    breaks: List[BreakResponse] = []

    class Config:
        from_attributes = True

class AttendanceCorrectionRequest(BaseModel):
    clock_in: Optional[datetime] = None
    clock_out: Optional[datetime] = None
    reason: str

# ----------------- Leave -----------------
class LeaveCreate(BaseModel):
    employee_id: Optional[str] = None
    leave_type: str = "annual" # annual, sick, casual, unpaid
    start_date: date
    end_date: date
    reason: str

class LeaveReviewRequest(BaseModel):
    status: str # approved, rejected
    resolution_notes: Optional[str] = None

class LeaveResponse(BaseModel):
    id: str
    organization_id: str
    employee_id: str
    leave_type: str
    start_date: date
    end_date: date
    days_count: float
    reason: str
    status: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    created_at: datetime
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    department_name: Optional[str] = None

    class Config:
        from_attributes = True

# ----------------- Anomalies -----------------
class AnomalyResponse(BaseModel):
    id: str
    organization_id: str
    employee_id: str
    attendance_record_id: Optional[str] = None
    date: date
    anomaly_type: str
    severity: str
    score: float
    detection_method: str
    explanation: str
    status: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    created_at: datetime
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    department_name: Optional[str] = None
    suggested_action: Optional[str] = None
    recommendation_priority: Optional[str] = None
    recommendation_source: Optional[str] = None

    class Config:
        from_attributes = True

class AnomalyReviewRequest(BaseModel):
    status: str # resolved, dismissed, correction_requested, escalated, under_review
    resolution_notes: str

# ----------------- Policy -----------------
class PolicyResponse(BaseModel):
    id: str
    organization_id: str
    title: str
    category: str
    file_path: Optional[str] = None
    file_size: int
    status: str
    chunk_count: Optional[int] = 0
    created_at: datetime

    class Config:
        from_attributes = True

class PolicySearchRequest(BaseModel):
    query: str
    limit: int = 5

class PolicyChunkResponse(BaseModel):
    id: str
    policy_id: str
    title: str
    section: Optional[str] = None
    page_number: int
    content: str
    score: Optional[float] = None
    citation: Optional[str] = None

    class Config:
        from_attributes = True

# ----------------- AI Chat -----------------
class MessageCreate(BaseModel):
    content: str

class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_results: Optional[List[Dict[str, Any]]] = None
    citations: Optional[List[Dict[str, Any]]] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    messages: List[MessageResponse] = []

    class Config:
        from_attributes = True

# ----------------- Analytics & Dashboard -----------------
class DashboardKPIs(BaseModel):
    total_employees: int
    present_today: int
    absent_today: int
    late_arrivals: int
    overtime_hours: float
    attendance_rate: float
    employees_on_leave: Optional[int] = 0
    pending_approvals: Optional[int] = 0
    pending_corrections: Optional[int] = 0
    comparison: Dict[str, float]

class AttendanceTrendItem(BaseModel):
    date: str
    present: int
    absent: int
    late: int
    rate: float

class DepartmentAttendanceItem(BaseModel):
    department: str
    present: int
    absent: int
    rate: float

class DashboardResponse(BaseModel):
    kpis: DashboardKPIs
    trends: List[AttendanceTrendItem]
    department_stats: List[DepartmentAttendanceItem]
    needs_attention: List[Dict[str, Any]]
    recent_activity: List[Dict[str, Any]]
    ai_insights: List[Dict[str, Any]]
    leave_distribution: Optional[List[Dict[str, Any]]] = []
    overtime_distribution: Optional[List[Dict[str, Any]]] = []
    absenteeism_trends: Optional[List[Dict[str, Any]]] = []
    shift_overview: Optional[List[Dict[str, Any]]] = []

class EmployeeDashboardResponse(BaseModel):
    kpis: Dict[str, Any]
    today_record: Optional[Dict[str, Any]] = None
    assigned_shift: Optional[Dict[str, Any]] = None
    recent_punches: List[Dict[str, Any]] = []
    leave_summary: Dict[str, Any] = {}
    attendance_trends: List[Dict[str, Any]] = []
    company_announcements: List[Dict[str, Any]] = []

# ----------------- Notifications -----------------
class NotificationResponse(BaseModel):
    id: str
    organization_id: str
    user_id: str
    title: str
    message: str
    category: str
    priority: str
    link: Optional[str] = None
    is_read: bool
    is_archived: bool
    created_at: datetime
    time_ago: Optional[str] = None

    class Config:
        from_attributes = True

class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    total: int
    unread_count: int
    page: int
    page_size: int

class NotificationPreferenceResponse(BaseModel):
    email_enabled: bool
    in_app_enabled: bool
    categories: Dict[str, bool]

    class Config:
        from_attributes = True

class NotificationPreferenceUpdate(BaseModel):
    email_enabled: Optional[bool] = None
    in_app_enabled: Optional[bool] = None
    categories: Optional[Dict[str, bool]] = None

# ----------------- Global Search -----------------
class SearchResultGroup(BaseModel):
    query: str
    total_results: int
    employees: List[Dict[str, Any]] = []
    departments: List[Dict[str, Any]] = []
    attendance: List[Dict[str, Any]] = []
    shifts: List[Dict[str, Any]] = []
    leave: List[Dict[str, Any]] = []
    policies: List[Dict[str, Any]] = []
    anomalies: List[Dict[str, Any]] = []
