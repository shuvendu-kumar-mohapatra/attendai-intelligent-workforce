from datetime import date, datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class AttendanceComparison(BaseModel):
    actual_worked_minutes: Optional[int] = None
    expected_worked_minutes: Optional[int] = None
    actual_overtime_minutes: Optional[int] = None
    expected_overtime_minutes: Optional[int] = 0
    actual_late_minutes: Optional[int] = None
    expected_late_minutes: Optional[int] = 0
    actual_break_minutes: Optional[int] = None
    expected_break_minutes: Optional[int] = 60
    clock_in_time: Optional[str] = None
    clock_out_time: Optional[str] = None
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None
    variance_summary: str

class HistoricalContext(BaseModel):
    average_worked_minutes_30d: float = 0.0
    average_worked_hours_30d: float = 0.0
    overtime_frequency_30d: int = 0
    total_overtime_hours_30d: float = 0.0
    late_arrival_frequency_30d: int = 0
    previous_similar_anomalies_count: int = 0
    assigned_shift_name: str = "Standard General Shift"
    assigned_shift_code: str = "GEN"
    assigned_shift_hours: float = 8.0
    grace_period_minutes: int = 15
    data_points_analyzed: int = 0

class RecommendedAction(BaseModel):
    id: str
    title: str
    action: str
    reason: str
    expected_outcome: str
    required_authorization: str
    action_type: str
    priority: str = "medium"
    confidence_score: float = 0.85
    evidence_completeness: str = "complete" # "complete" | "partial" | "baseline_only"
    policy_reference: Optional[str] = None
    is_automated: bool = False

class AIRecommendedActionDetail(BaseModel):
    title: str
    explanation: str
    suggested_steps: List[str]
    supporting_evidence: List[str]
    policy_reference: Optional[str] = None
    priority: str = "medium"
    source: str = "Rule-based Engine"
    provider: str = "rule_based"
    evidence_completeness: str = "complete"
    action_type: str = "audit_record"

class AnomalyInvestigationResponse(BaseModel):
    anomaly_id: str
    employee_id: str
    employee_name: str
    employee_code: str
    department_name: str
    anomaly_type: str
    detection_date: str
    severity: str
    score: float
    detection_method: str
    explanation: str
    why_flagged_explanation: Optional[str] = None
    confidence_score: float = 0.92
    comparison: AttendanceComparison
    actual_vs_expected: Optional[AttendanceComparison] = None
    historical_context: HistoricalContext
    recommendations: List[RecommendedAction]
    recommended_actions: Optional[List[RecommendedAction]] = None
    suggested_action: Optional[str] = None
    possible_causes: List[str] = Field(default_factory=list)
    rule_references: List[str] = Field(default_factory=list)
    available_resolutions: List[Dict[str, str]]
    current_status: str
    current_resolution_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    ai_recommended_action: Optional[AIRecommendedActionDetail] = None

class DashboardRecommendationsResponse(BaseModel):
    pending_investigations_count: int
    high_priority_anomalies_count: int
    repeated_patterns_count: int
    top_recommendations: List[Dict[str, Any]]
    pending_count: Optional[int] = None
    high_priority_count: Optional[int] = None
    prioritized_anomalies: Optional[List[Dict[str, Any]]] = None
