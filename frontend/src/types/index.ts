export interface User {
  id: string;
  email: string;
  role: 'admin' | 'hr_manager' | 'employee';
  organization_id: string;
  organization_name?: string;
  employee_id?: string;
  first_name?: string;
  last_name?: string;
  employee_code?: string;
  designation?: string;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

export interface Employee {
  id: string;
  organization_id: string;
  department_id?: string;
  user_id?: string;
  employee_code: string;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  designation: string;
  date_of_joining: string;
  is_active: boolean;
  department_name?: string;
  current_shift?: string;
}

export interface Department {
  id: string;
  organization_id: string;
  name: string;
  code: string;
  manager_id?: string;
  employee_count: number;
  created_at: string;
}

export interface Shift {
  id: string;
  organization_id: string;
  name: string;
  code: string;
  start_time: string;
  end_time: string;
  grace_period_minutes: number;
  required_hours: number;
  is_overnight: boolean;
  created_at: string;
}

export interface AttendanceBreak {
  id: string;
  break_start: string;
  break_end?: string;
  duration_minutes: number;
  reason?: string;
}

export interface AttendanceRecord {
  id: string;
  organization_id: string;
  employee_id: string;
  date: string;
  clock_in?: string;
  clock_out?: string;
  worked_minutes: number;
  overtime_minutes: number;
  late_minutes: number;
  status: 'present' | 'late' | 'half_day' | 'absent' | 'incomplete';
  is_corrected: boolean;
  employee_name?: string;
  employee_code?: string;
  department_name?: string;
  breaks?: AttendanceBreak[];
}

export interface LeaveRecord {
  id: string;
  organization_id: string;
  employee_id: string;
  leave_type: 'annual' | 'sick' | 'casual' | 'unpaid';
  start_date: string;
  end_date: string;
  days_count: number;
  reason: string;
  status: 'pending' | 'approved' | 'rejected';
  reviewed_by?: string;
  reviewed_at?: string;
  resolution_notes?: string;
  employee_name?: string;
  employee_code?: string;
  department_name?: string;
  created_at: string;
}

export interface AttendanceAnomaly {
  id: string;
  organization_id: string;
  employee_id: string;
  attendance_record_id?: string;
  date: string;
  anomaly_type: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  score: number;
  detection_method: 'rule_based' | 'isolation_forest' | 'hybrid';
  explanation: string;
  status: 'pending' | 'investigating' | 'resolved' | 'dismissed' | 'correction_requested' | 'escalated' | 'under_review';
  reviewed_by?: string;
  reviewed_at?: string;
  resolution_notes?: string;
  employee_name?: string;
  employee_code?: string;
  department_name?: string;
  suggested_action?: string;
  recommendation_priority?: string;
  recommendation_source?: string;
  created_at: string;
}

export interface AttendanceComparison {
  actual_worked_minutes?: number;
  expected_worked_minutes?: number;
  worked_hours_variance_minutes?: number;
  actual_overtime_minutes?: number;
  expected_overtime_minutes?: number;
  actual_late_minutes?: number;
  shift_grace_period_minutes?: number;
  actual_break_minutes?: number;
  expected_break_minutes?: number;
  clock_in_actual?: string;
  clock_out_actual?: string;
  scheduled_start?: string;
  scheduled_end?: string;
  shift_name?: string;
  shift_code?: string;
}

export interface HistoricalContext {
  window_days: number;
  avg_daily_worked_hours: number;
  overtime_frequency_count: number;
  late_arrival_frequency_count: number;
  previous_similar_anomalies_count: number;
  assigned_shift_name?: string;
  assigned_shift_start?: string;
  assigned_shift_end?: string;
  assigned_shift_grace_minutes?: number;
}

export interface RecommendedAction {
  id: string;
  title: string;
  action: string;
  reason: string;
  expected_outcome: string;
  required_authorization: string;
  policy_citation?: string;
  priority: 'high' | 'medium' | 'low';
}

export interface AIRecommendedActionDetail {
  title: string;
  explanation: string;
  suggested_steps: string[];
  supporting_evidence: string[];
  policy_reference?: string;
  priority: string;
  source: string;
  provider: string;
  evidence_completeness: string;
  action_type: string;
}

export interface AnomalyInvestigationData {
  anomaly_id: string;
  employee_id: string;
  employee_name: string;
  employee_code: string;
  department_name: string;
  anomaly_type: string;
  detection_date: string;
  severity: string;
  score: number;
  detection_method: string;
  status: string;
  why_flagged_explanation: string;
  explanation?: string;
  confidence_score: number;
  actual_vs_expected: AttendanceComparison;
  historical_context: HistoricalContext;
  recommended_actions: RecommendedAction[];
  possible_causes: string[];
  ai_recommended_action?: AIRecommendedActionDetail;
}

export interface DashboardTriageItem {
  anomaly_id: string;
  employee_name: string;
  employee_code: string;
  department_name: string;
  anomaly_type: string;
  severity: string;
  detection_date: string;
  score: number;
  status: string;
  primary_recommendation: RecommendedAction;
  why_flagged_summary: string;
}

export interface DashboardRecommendationsData {
  pending_count: number;
  high_priority_count: number;
  repeated_patterns_count: number;
  prioritized_anomalies: DashboardTriageItem[];
}

export interface Policy {
  id: string;
  organization_id: string;
  title: string;
  category: string;
  file_path?: string;
  file_size: number;
  status: 'processing' | 'active' | 'failed' | 'empty';
  chunk_count: number;
  created_at: string;
}

export interface PolicyChunk {
  id: string;
  policy_id: string;
  title: string;
  section?: string;
  page_number: number;
  content: string;
  citation?: string;
}

export interface ConversationMessage {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  tool_calls?: any[];
  tool_results?: any[];
  citations?: any[];
  follow_ups?: string[];
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  messages: ConversationMessage[];
}

export interface DashboardData {
  kpis: {
    total_employees: number;
    present_today: number;
    absent_today: number;
    late_arrivals: number;
    overtime_hours: number;
    attendance_rate: number;
    comparison: {
      present: number;
      late: number;
      overtime: number;
    };
  };
  trends: Array<{
    date: string;
    present: number;
    absent: number;
    late: number;
    rate: number;
  }>;
  department_stats: Array<{
    department: string;
    present: number;
    absent: number;
    rate: number;
  }>;
  needs_attention: Array<{
    id: string;
    type: string;
    severity: string;
    employee: string;
    date: string;
    explanation: string;
  }>;
  recent_activity: Array<{
    id: string;
    employee: string;
    department: string;
    clock_in: string;
    clock_out: string;
    worked_hours: number;
    status: string;
  }>;
  ai_insights: Array<{
    title: string;
    insight: string;
    level: string;
  }>;
}
