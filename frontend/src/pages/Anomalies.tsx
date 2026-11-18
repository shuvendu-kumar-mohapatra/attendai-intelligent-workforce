import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  Play,
  CheckCircle2,
  XCircle,
  Filter,
  Info,
  ShieldAlert,
  BrainCircuit,
  Sparkles,
  Lightbulb,
  BookOpen,
  Clock,
  Calendar,
  User,
  FileText,
  Check,
  ArrowRight,
  ShieldCheck,
  TrendingUp,
  X,
  ChevronRight,
  AlertCircle,
  RotateCcw
} from 'lucide-react';
import { api } from '../services/api';
import {
  AttendanceAnomaly,
  AnomalyInvestigationData,
  AIRecommendedActionDetail,
  DashboardRecommendationsData,
  DashboardTriageItem,
  RecommendedAction
} from '../types';

export const Anomalies: React.FC = () => {
  const [anomalies, setAnomalies] = useState<AttendanceAnomaly[]>([]);
  const [loading, setLoading] = useState(true);
  const [detecting, setDetecting] = useState(false);

  // Filters
  const [severityFilter, setSeverityFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // Dashboard Recommendations State
  const [dashboardData, setDashboardData] = useState<DashboardRecommendationsData | null>(null);
  const [loadingDashboard, setLoadingDashboard] = useState(false);

  // Investigation Modal State
  const [investigatingId, setInvestigatingId] = useState<string | null>(null);
  const [investigationData, setInvestigationData] = useState<AnomalyInvestigationData | null>(null);
  const [loadingInvestigation, setLoadingInvestigation] = useState(false);
  const [investigationError, setInvestigationError] = useState<string | null>(null);

  // Review Form State
  const [resolutionStatus, setResolutionStatus] = useState<
    'resolved' | 'dismissed' | 'correction_requested' | 'escalated' | 'under_review'
  >('resolved');
  const [resolutionNotes, setResolutionNotes] = useState('');
  const [submittingReview, setSubmittingReview] = useState(false);

  const fetchAnomalies = async () => {
    setLoading(true);
    try {
      const params: any = {};
      if (severityFilter) params.severity = severityFilter;
      if (statusFilter) params.status_filter = statusFilter;
      const res = await api.get('/anomalies', { params });
      setAnomalies(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      console.error('Failed to load anomalies:', e);
      setAnomalies([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchDashboardRecommendations = async () => {
    setLoadingDashboard(true);
    try {
      const res = await api.get('/anomalies/recommendations/dashboard');
      const raw = res.data || {};
      const rawList = Array.isArray(raw.prioritized_anomalies)
        ? raw.prioritized_anomalies
        : Array.isArray(raw.top_recommendations)
        ? raw.top_recommendations
        : [];

      const normalizedList: DashboardTriageItem[] = rawList.map((item: any) => ({
        anomaly_id: item.anomaly_id,
        employee_name: item.employee_name,
        employee_code: item.employee_code,
        department_name: item.department_name || item.department || 'General Operations',
        anomaly_type: item.anomaly_type,
        severity: item.severity,
        detection_date: item.detection_date || item.date || item.detection_date,
        score: item.score,
        status: item.status || 'pending',
        primary_recommendation: item.primary_recommendation || (item.recommended_action_title ? {
          title: item.recommended_action_title,
          action: item.recommended_action,
          required_authorization: item.required_authorization || 'HR Manager',
        } : undefined),
      }));

      setDashboardData({
        pending_count: raw.pending_count ?? raw.pending_investigations_count ?? 0,
        high_priority_count: raw.high_priority_count ?? raw.high_priority_anomalies_count ?? 0,
        repeated_patterns_count: raw.repeated_patterns_count ?? 0,
        prioritized_anomalies: normalizedList,
      });
    } catch (e) {
      console.error('Failed to load anomaly recommendations:', e);
      setDashboardData({
        pending_count: 0,
        high_priority_count: 0,
        repeated_patterns_count: 0,
        prioritized_anomalies: [],
      });
    } finally {
      setLoadingDashboard(false);
    }
  };

  useEffect(() => {
    fetchAnomalies();
    fetchDashboardRecommendations();
  }, [severityFilter, statusFilter]);

  const handleRunDetection = async () => {
    setDetecting(true);
    try {
      const res = await api.post('/anomalies/detect');
      alert(res.data.message);
      fetchAnomalies();
      fetchDashboardRecommendations();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to execute anomaly detection pipeline');
    } finally {
      setDetecting(false);
    }
  };

  const openInvestigationModal = async (anomalyId: string) => {
    setInvestigatingId(anomalyId);
    setLoadingInvestigation(true);
    setInvestigationError(null);
    setResolutionNotes('');
    setResolutionStatus('resolved');

    try {
      const res = await api.get(`/anomalies/${anomalyId}/investigate`);
      setInvestigationData(res.data);
      if (res.data.ai_recommended_action) {
        const top = res.data.ai_recommended_action;
        setResolutionNotes(`${top.title}\n${top.explanation}`);
      } else if (res.data.recommended_actions && res.data.recommended_actions.length > 0) {
        const topRec = res.data.recommended_actions[0];
        setResolutionNotes(`Action taken: ${topRec.action} (${topRec.title})`);
      }
    } catch (err: any) {
      console.error('Failed to load investigation details:', err);
      setInvestigationError(err.response?.data?.detail || 'Failed to load deep investigation data.');
    } finally {
      setLoadingInvestigation(false);
    }
  };

  const closeInvestigationModal = () => {
    setInvestigatingId(null);
    setInvestigationData(null);
    setResolutionNotes('');
  };

  const handleAdoptAiRecommendation = (rec: AIRecommendedActionDetail) => {
    const stepsFormatted = (rec.suggested_steps || [])
      .map((step, idx) => `${idx + 1}. ${step}`)
      .join('\n');
    const formatted = `${rec.title}\n${rec.explanation}\n\nSuggested Steps:\n${stepsFormatted}\n\nGuidance Source: ${rec.source}${rec.policy_reference ? `\nPolicy Reference: ${rec.policy_reference}` : ''}`;
    setResolutionNotes(formatted);
  };

  const handleApplyRecommendedFixDirectly = (rec: AIRecommendedActionDetail) => {
    if (rec.action_type === 'correct_punch' || rec.title.toLowerCase().includes('correction')) {
      setResolutionStatus('correction_requested');
    } else {
      setResolutionStatus('resolved');
    }
    const stepsFormatted = (rec.suggested_steps || [])
      .map((step, idx) => `${idx + 1}. ${step}`)
      .join('\n');
    const formatted = `${rec.title}\n${rec.explanation}\n\nActions Taken:\n${stepsFormatted}\n\nVerified by HR/Admin per ${rec.source}.`;
    setResolutionNotes(formatted);
  };

  const handleApplyRecommendationToNotes = (rec: RecommendedAction) => {
    const formatted = `Action: ${rec.action}\nRationale: ${rec.reason}\nAuth: ${rec.required_authorization}`;
    setResolutionNotes(formatted);
  };

  const handleReviewSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!investigatingId) return;

    if (!resolutionNotes.trim()) {
      alert('Mandatory resolution notes are required to document the outcome of this investigation.');
      return;
    }

    setSubmittingReview(true);
    try {
      await api.put(`/anomalies/${investigatingId}/review`, {
        status: resolutionStatus,
        resolution_notes: resolutionNotes,
      });
      closeInvestigationModal();
      fetchAnomalies();
      fetchDashboardRecommendations();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to submit investigation resolution');
    } finally {
      setSubmittingReview(false);
    }
  };

  const totalCount = Array.isArray(anomalies) ? anomalies.length : 0;
  const criticalCount = Array.isArray(anomalies) ? anomalies.filter((a) => a.severity === 'critical').length : 0;
  const pendingCount = Array.isArray(anomalies) ? anomalies.filter((a) => a.status === 'pending').length : 0;
  const resolvedCount = Array.isArray(anomalies)
    ? anomalies.filter(
        (a) => a.status === 'resolved' || a.status === 'dismissed' || a.status === 'correction_requested'
      ).length
    : 0;

  return (
    <div className="space-y-6 w-full min-w-0 max-w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border min-w-0">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-bold text-dark tracking-tight">Workforce Anomaly Detection & Investigation</h1>
          <p className="text-xs text-secondary mt-0.5 break-words">
            Hybrid intelligence engine combining deterministic rules, Scikit-learn Isolation Forest, and automated prescriptive recommendations.
          </p>
        </div>
        <button
          onClick={handleRunDetection}
          disabled={detecting}
          className="px-3.5 py-1.5 bg-primary text-white rounded-lg text-xs font-semibold hover:bg-primary-hover flex items-center justify-center gap-1.5 shadow-sm transition-colors disabled:opacity-50 flex-shrink-0 self-start sm:self-auto"
        >
          {detecting ? (
            <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
          ) : (
            <Play className="w-3.5 h-3.5 fill-white" />
          )}
          <span>Run Detection Pipeline</span>
        </button>
      </div>

      {/* Ethics & Fairness Notice */}
      <div className="p-3.5 rounded-xl bg-blue-50/70 border border-blue-200/80 text-blue-900 text-xs flex items-start gap-2.5 min-w-0">
        <Info className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1">
          <span className="font-semibold">Fairness & Compliance Notice:</span>
          <span className="text-blue-800 ml-1">
            Anomalies flagged by AttendAI are statistical investigation indicators, never automated disciplinary actions
            or definitive evidence of misconduct. All corrective actions require human supervisor authorization.
          </span>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 min-w-0">
        <div className="bg-card border border-border rounded-xl p-3 sm:p-4 shadow-card min-w-0">
          <span className="text-[10px] sm:text-[11px] font-semibold text-secondary uppercase tracking-wider block mb-1 truncate">
            Total Anomalies
          </span>
          <span className="text-xl sm:text-2xl font-bold text-dark">{totalCount}</span>
          <span className="text-[10px] text-secondary block mt-1 truncate">Past 30-day window</span>
        </div>
        <div className="bg-card border border-border rounded-xl p-3 sm:p-4 shadow-card min-w-0">
          <span className="text-[10px] sm:text-[11px] font-semibold text-danger uppercase tracking-wider block mb-1 truncate">
            Critical Alerts
          </span>
          <span className="text-xl sm:text-2xl font-bold text-danger">{criticalCount}</span>
          <span className="text-[10px] text-danger/80 block mt-1 truncate">Requires supervisor check</span>
        </div>
        <div className="bg-card border border-border rounded-xl p-3 sm:p-4 shadow-card min-w-0">
          <span className="text-[10px] sm:text-[11px] font-semibold text-warning uppercase tracking-wider block mb-1 truncate">
            Pending Review
          </span>
          <span className="text-xl sm:text-2xl font-bold text-warning">{pendingCount}</span>
          <span className="text-[10px] text-warning/80 block mt-1 truncate">Open triage queue</span>
        </div>
        <div className="bg-card border border-border rounded-xl p-3 sm:p-4 shadow-card min-w-0">
          <span className="text-[10px] sm:text-[11px] font-semibold text-success uppercase tracking-wider block mb-1 truncate">
            Audited / Resolved
          </span>
          <span className="text-xl sm:text-2xl font-bold text-success">{resolvedCount}</span>
          <span className="text-[10px] text-success/80 block mt-1 truncate">With resolution notes</span>
        </div>
      </div>

      {/* AI RECOMMENDED ACTIONS & HIGH-PRIORITY TRIAGE SECTION */}
      <div className="bg-gradient-to-br from-indigo-50/50 via-white to-purple-50/40 border border-indigo-100 rounded-2xl p-4 sm:p-5 shadow-card space-y-4 min-w-0 max-w-full">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pb-3 border-b border-indigo-100/70 min-w-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center shadow-sm flex-shrink-0">
              <Sparkles className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <h2 className="text-sm font-bold text-dark flex items-center gap-2 flex-wrap">
                <span>AI Recommended Actions & High-Priority Triage</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-100 text-indigo-700 whitespace-nowrap">
                  Intelligent Engine
                </span>
              </h2>
              <p className="text-xs text-secondary mt-0.5 break-words">
                Automated root cause identification, scheduled variance checks, and practical corrective actions.
              </p>
            </div>
          </div>

          {/* Quick Metrics Badges */}
          <div className="flex flex-wrap items-center gap-2 flex-shrink-0">
            <span className="px-2.5 py-1 rounded-lg text-[11px] font-medium bg-amber-50 text-amber-800 border border-amber-200/60 whitespace-nowrap">
              Pending Triage: <strong>{dashboardData?.pending_count ?? pendingCount}</strong>
            </span>
            <span className="px-2.5 py-1 rounded-lg text-[11px] font-medium bg-rose-50 text-rose-800 border border-rose-200/60 whitespace-nowrap">
              High Priority: <strong>{dashboardData?.high_priority_count ?? criticalCount}</strong>
            </span>
            <span className="px-2.5 py-1 rounded-lg text-[11px] font-medium bg-purple-50 text-purple-800 border border-purple-200/60 whitespace-nowrap">
              Repeated Patterns: <strong>{dashboardData?.repeated_patterns_count ?? 0}</strong>
            </span>
          </div>
        </div>

        {/* Prioritized Action Cards */}
        {loadingDashboard ? (
          <div className="text-center py-6 text-xs text-secondary flex items-center justify-center gap-2">
            <div className="w-4 h-4 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
            <span>Synthesizing intelligent recommendations...</span>
          </div>
        ) : !dashboardData || !dashboardData.prioritized_anomalies || dashboardData.prioritized_anomalies.length === 0 ? (
          <div className="p-4 bg-white/80 border border-slate-200/80 rounded-xl text-xs text-secondary text-center">
            No high-priority anomaly triage items pending. All recent workforce patterns align with operational baselines.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3.5 sm:gap-4 min-w-0 max-w-full">
            {dashboardData.prioritized_anomalies.map((item: DashboardTriageItem) => (
              <div
                key={item.anomaly_id}
                className="bg-white border border-slate-200/90 rounded-xl p-3.5 sm:p-4 shadow-sm hover:border-indigo-300 transition-all flex flex-col justify-between space-y-3 min-w-0 max-w-full"
              >
                <div className="space-y-2.5 min-w-0">
                  <div className="flex items-start justify-between gap-2 min-w-0">
                    <div className="min-w-0 flex-1">
                      <span className="font-bold text-dark text-xs block truncate" title={item.employee_name}>
                        {item.employee_name}
                      </span>
                      <span className="text-[10px] text-secondary font-mono block truncate" title={`${item.employee_code} • ${item.department_name}`}>
                        {item.employee_code} &bull; {item.department_name}
                      </span>
                    </div>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase border flex-shrink-0 ${
                        item.severity === 'critical'
                          ? 'bg-rose-50 text-danger border-rose-200'
                          : item.severity === 'high'
                          ? 'bg-amber-50 text-warning border-amber-200'
                          : 'bg-blue-50 text-primary border-blue-200'
                      }`}
                    >
                      {item.severity}
                    </span>
                  </div>

                  <div className="text-[11px] font-medium text-dark flex items-center gap-1.5 capitalize text-slate-700 min-w-0">
                    <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 flex-shrink-0"></span>
                    <span className="truncate">{item.anomaly_type.replace(/_/g, ' ')}</span>
                    <span className="text-secondary text-[10px] flex-shrink-0">({item.detection_date})</span>
                  </div>

                  {item.primary_recommendation && (
                    <div className="p-2.5 rounded-lg bg-indigo-50/60 border border-indigo-100 text-xs space-y-1 min-w-0">
                      <div className="font-semibold text-indigo-950 text-[11px] flex items-center gap-1 min-w-0">
                        <CheckCircle2 className="w-3 h-3 text-indigo-600 flex-shrink-0" />
                        <span className="truncate" title={item.primary_recommendation.title}>
                          {item.primary_recommendation.title}
                        </span>
                      </div>
                      <p className="text-slate-600 text-[11px] leading-relaxed break-words">
                        {item.primary_recommendation.action}
                      </p>
                      <div className="pt-1 flex items-center justify-between text-[10px] text-indigo-700 font-medium">
                        <span className="truncate">Auth: {item.primary_recommendation.required_authorization}</span>
                      </div>
                    </div>
                  )}
                </div>

                <button
                  onClick={() => openInvestigationModal(item.anomaly_id)}
                  className="w-full mt-2 py-1.5 px-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 shadow-sm transition-colors flex-shrink-0"
                >
                  <span className="truncate">Investigate & Recommend Fix</span>
                  <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Filter Bar */}
      <div className="bg-card border border-border rounded-xl p-3 sm:p-4 shadow-card flex flex-wrap items-center gap-3 justify-between min-w-0 max-w-full">
        <div className="flex flex-wrap items-center gap-3 min-w-0">
          <Filter className="w-3.5 h-3.5 text-secondary flex-shrink-0" />
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="py-1 px-3 bg-slate-50 border border-border rounded-lg text-xs text-dark"
          >
            <option value="">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="py-1 px-3 bg-slate-50 border border-border rounded-lg text-xs text-dark"
          >
            <option value="">All Review Statuses</option>
            <option value="pending">Pending</option>
            <option value="resolved">Resolved</option>
            <option value="dismissed">Dismissed</option>
            <option value="correction_requested">Correction Requested</option>
            <option value="escalated">Escalated</option>
            <option value="under_review">Under Review</option>
          </select>
        </div>
      </div>

      {/* Anomalies Table */}
      <div className="bg-card border border-border rounded-xl shadow-card overflow-hidden w-full min-w-0 max-w-full">
        <div className="overflow-x-auto w-full max-w-full overscroll-x-contain">
          <table className="w-full text-left text-xs min-w-[900px] border-collapse">
            <thead>
              <tr className="border-b border-border bg-slate-50/75 text-secondary uppercase tracking-wider text-[10px]">
                <th className="py-3 px-4 whitespace-nowrap">Date</th>
                <th className="py-3 px-4 whitespace-nowrap">Employee</th>
                <th className="py-3 px-4 whitespace-nowrap">Anomaly Type</th>
                <th className="py-3 px-4 whitespace-nowrap">Severity</th>
                <th className="py-3 px-4 whitespace-nowrap">Method</th>
                <th className="py-3 px-4 whitespace-nowrap">Score</th>
                <th className="py-3 px-4 min-w-[180px] max-w-xs">Explanation</th>
                <th className="py-3 px-4 min-w-[200px] max-w-xs">Suggested Action</th>
                <th className="py-3 px-4 whitespace-nowrap">Status</th>
                <th className="py-3 px-4 text-right whitespace-nowrap">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border font-medium">
              {loading ? (
                <tr>
                  <td colSpan={10} className="text-center py-10 text-secondary">
                    Loading anomaly queue...
                  </td>
                </tr>
              ) : !Array.isArray(anomalies) || anomalies.length === 0 ? (
                <tr>
                  <td colSpan={10} className="text-center py-10 text-secondary">
                    No anomalies found matching current filters.
                  </td>
                </tr>
              ) : (
                anomalies.map((anom) => (
                  <tr key={anom.id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="py-3 px-4 font-mono text-dark whitespace-nowrap">{anom.date}</td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span className="font-semibold text-dark block">{anom.employee_name}</span>
                      <span className="text-[10px] text-secondary font-mono">{anom.employee_code}</span>
                    </td>
                    <td className="py-3 px-4 font-semibold text-dark capitalize whitespace-nowrap">
                      {anom.anomaly_type.replace(/_/g, ' ')}
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold uppercase border ${
                          anom.severity === 'critical'
                            ? 'bg-rose-50 text-danger border-rose-200'
                            : anom.severity === 'high'
                            ? 'bg-amber-50 text-warning border-amber-200'
                            : 'bg-blue-50 text-primary border-blue-200'
                        }`}
                      >
                        {anom.severity}
                      </span>
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span className="flex items-center gap-1 text-[11px] text-secondary capitalize">
                        {anom.detection_method === 'isolation_forest' ? (
                          <>
                            <BrainCircuit className="w-3.5 h-3.5 text-purple-600 flex-shrink-0" />
                            <span>Isolation Forest</span>
                          </>
                        ) : (
                          <>
                            <ShieldAlert className="w-3.5 h-3.5 text-blue-600 flex-shrink-0" />
                            <span>Rule-Based</span>
                          </>
                        )}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-mono text-dark whitespace-nowrap">{anom.score}</td>
                    <td className="py-3 px-4 text-secondary max-w-xs truncate" title={anom.explanation}>
                      <span className="block truncate">{anom.explanation}</span>
                    </td>
                    <td className="py-3 px-4 max-w-xs">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <button
                          type="button"
                          onClick={() => openInvestigationModal(anom.id)}
                          className="group inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium bg-indigo-50/80 hover:bg-indigo-100 text-indigo-700 hover:text-indigo-900 border border-indigo-200/80 transition-all text-left shadow-2xs cursor-pointer max-w-full min-w-0"
                          title={anom.suggested_action ? `${anom.suggested_action} (Click to View Suggestion)` : 'No recommendation available – manual review required'}
                        >
                          <Sparkles className="w-3.5 h-3.5 text-indigo-600 flex-shrink-0 group-hover:scale-110 transition-transform" />
                          <span className="truncate flex-1 min-w-0">
                            {anom.suggested_action || 'No recommendation available – manual review required'}
                          </span>
                          <span className="text-[10px] text-indigo-600 font-semibold uppercase flex-shrink-0 ml-auto pl-1 group-hover:underline">
                            View
                          </span>
                        </button>
                      </div>
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold capitalize border ${
                          anom.status === 'resolved'
                            ? 'bg-emerald-50 text-success border-emerald-200'
                            : anom.status === 'dismissed'
                            ? 'bg-slate-100 text-secondary border-slate-200'
                            : anom.status === 'correction_requested'
                            ? 'bg-purple-50 text-purple-700 border-purple-200'
                            : anom.status === 'escalated'
                            ? 'bg-red-50 text-red-700 border-red-200'
                            : 'bg-amber-50 text-warning border-amber-200'
                        }`}
                      >
                        {anom.status.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right whitespace-nowrap">
                      <button
                        onClick={() => openInvestigationModal(anom.id)}
                        className="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 text-[11px] font-medium text-indigo-700 rounded-md transition-colors"
                      >
                        Investigate
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* REDESIGNED INVESTIGATION MODAL */}
      {investigatingId && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4">
          <div className="bg-white border border-border rounded-2xl shadow-2xl w-full max-w-4xl max-h-[92vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-border bg-slate-50/80 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center shadow-sm">
                  <BrainCircuit className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-dark">Investigate Anomaly Flag & Prescriptive Actions</h3>
                  <p className="text-[11px] text-secondary">
                    Grounded root-cause analysis based on verified attendance records and shift parameters.
                  </p>
                </div>
              </div>
              <button
                onClick={closeInvestigationModal}
                className="w-7 h-7 rounded-lg hover:bg-slate-200/70 flex items-center justify-center text-secondary hover:text-dark transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="overflow-y-auto p-6 space-y-6 flex-1 text-xs">
              {loadingInvestigation ? (
                <div className="py-20 text-center space-y-3">
                  <div className="w-8 h-8 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto"></div>
                  <p className="text-secondary font-medium">Retrieving attendance logs, historical context & calculating recommendations...</p>
                </div>
              ) : investigationError ? (
                <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <span>{investigationError}</span>
                </div>
              ) : investigationData ? (
                <div className="space-y-6">
                  {/* SECTION 1: ANOMALY DETAILS */}
                  <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
                      <div>
                        <h4 className="font-bold text-dark text-sm">{investigationData.employee_name}</h4>
                        <span className="text-[11px] text-secondary font-mono">
                          ID: {investigationData.employee_code} &bull; Dept: {investigationData.department_name}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="px-2.5 py-1 rounded-md text-[11px] font-semibold bg-white border border-slate-200 text-dark capitalize">
                          Type: <strong>{investigationData.anomaly_type.replace(/_/g, ' ')}</strong>
                        </span>
                        <span
                          className={`px-2.5 py-1 rounded-md text-[11px] font-bold uppercase border ${
                            investigationData.severity === 'critical'
                              ? 'bg-rose-50 text-danger border-rose-200'
                              : investigationData.severity === 'high'
                              ? 'bg-amber-50 text-warning border-amber-200'
                              : 'bg-blue-50 text-primary border-blue-200'
                          }`}
                        >
                          Severity: {investigationData.severity}
                        </span>
                        <span className="px-2.5 py-1 rounded-md text-[11px] font-mono bg-purple-50 text-purple-700 border border-purple-200">
                          Isolation Forest Score: <strong>{investigationData.score}</strong>
                        </span>
                        <span className="text-secondary text-[11px]">
                          Detection Date: <strong>{investigationData.detection_date}</strong>
                        </span>
                      </div>
                    </div>

                    {/* Anomaly Explanation */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-bold text-dark flex items-center gap-1.5">
                          <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                          <span>Anomaly Explanation & Detection Reason</span>
                        </span>
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-200/70 text-slate-700">
                          Method: {investigationData.detection_method.replace(/_/g, ' ')}
                        </span>
                      </div>
                      <p className="text-slate-800 text-xs leading-relaxed bg-white border border-slate-200 rounded-lg p-3 font-medium">
                        {investigationData.why_flagged_explanation || investigationData.explanation}
                      </p>
                    </div>
                  </div>

                  {/* SECTION 2: AI-RECOMMENDED ACTION */}
                  {investigationData.ai_recommended_action && (
                    <div className="bg-sky-50/70 border border-sky-200 rounded-xl p-4 sm:p-5 shadow-sm space-y-3.5">
                      {/* Header with Title, Source Badge and Priority */}
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-3 border-b border-sky-200/70">
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded-lg bg-sky-600 text-white flex items-center justify-center shadow-sm">
                            <Lightbulb className="w-4 h-4" />
                          </div>
                          <div>
                            <span className="text-[11px] font-bold uppercase tracking-wider text-sky-950 block">
                              AI-Recommended Action
                            </span>
                            <span className="text-[10px] text-sky-800">
                              Automated root-cause corrective guidance synthesized from verified attendance logs
                            </span>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase border ${
                              investigationData.ai_recommended_action.priority === 'critical'
                                ? 'bg-rose-100 text-rose-800 border-rose-300'
                                : investigationData.ai_recommended_action.priority === 'high'
                                ? 'bg-amber-100 text-amber-800 border-amber-300'
                                : 'bg-sky-100 text-sky-800 border-sky-300'
                            }`}
                          >
                            Priority: {investigationData.ai_recommended_action.priority}
                          </span>
                          <span
                            className={`px-2.5 py-0.5 rounded-full text-[10px] font-semibold border ${
                              investigationData.ai_recommended_action.source.includes('NVIDIA')
                                ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                                : investigationData.ai_recommended_action.source.includes('Groq')
                                ? 'bg-purple-50 text-purple-800 border-purple-300'
                                : 'bg-white text-slate-800 border-slate-300'
                            }`}
                          >
                            Source: {investigationData.ai_recommended_action.source}
                          </span>
                        </div>
                      </div>

                      {/* Recommended Action Title & Executive Explanation */}
                      <div className="space-y-1.5">
                        <h4 className="text-sm font-bold text-sky-950 flex items-center gap-2">
                          <CheckCircle2 className="w-4 h-4 text-sky-600 flex-shrink-0" />
                          <span>{investigationData.ai_recommended_action.title}</span>
                        </h4>
                        <p className="text-xs text-slate-800 leading-relaxed font-medium">
                          {investigationData.ai_recommended_action.explanation}
                        </p>
                      </div>

                      {/* Suggested Steps (Numbered 1-4) */}
                      {investigationData.ai_recommended_action.suggested_steps?.length > 0 && (
                        <div className="bg-white/90 border border-sky-200/80 rounded-lg p-3 space-y-2">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-sky-900 block">
                            Suggested Steps:
                          </span>
                          <ol className="space-y-1.5 text-xs text-slate-800">
                            {investigationData.ai_recommended_action.suggested_steps.map((step, idx) => (
                              <li key={idx} className="flex items-start gap-2">
                                <span className="w-5 h-5 rounded-full bg-sky-100 text-sky-800 text-[10px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                                  {idx + 1}
                                </span>
                                <span className="leading-tight pt-0.5">{step}</span>
                              </li>
                            ))}
                          </ol>
                        </div>
                      )}

                      {/* Supporting Attendance Evidence & Related Policy */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                        {/* Supporting Evidence Items */}
                        {investigationData.ai_recommended_action.supporting_evidence?.length > 0 && (
                          <div className="bg-white/80 border border-sky-200/70 rounded-lg p-2.5 space-y-1.5">
                            <span className="text-[10px] font-bold text-sky-900 uppercase tracking-wider block">
                              Supporting Attendance Evidence:
                            </span>
                            <div className="flex flex-wrap gap-1.5">
                              {investigationData.ai_recommended_action.supporting_evidence.map((ev, i) => (
                                <span
                                  key={i}
                                  className="px-2 py-0.5 bg-slate-50 border border-slate-200 rounded text-[10px] text-slate-700"
                                >
                                  {ev}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Policy Reference & Actions */}
                        <div className="bg-white/80 border border-sky-200/70 rounded-lg p-2.5 flex flex-col justify-between space-y-2">
                          <div>
                            <span className="text-[10px] font-bold text-sky-900 uppercase tracking-wider block mb-1">
                              Related Policy Reference:
                            </span>
                            {investigationData.ai_recommended_action.policy_reference ? (
                              <div className="flex items-center gap-1.5 text-xs text-slate-800 font-medium">
                                <BookOpen className="w-3.5 h-3.5 text-sky-600 flex-shrink-0" />
                                <span>{investigationData.ai_recommended_action.policy_reference}</span>
                              </div>
                            ) : (
                              <span className="text-xs text-secondary italic">Standard Workforce Operations Baseline</span>
                            )}
                          </div>

                          {/* Action Buttons */}
                          <div className="flex items-center gap-2 pt-1 border-t border-sky-100 flex-wrap">
                            <button
                              type="button"
                              onClick={() => handleAdoptAiRecommendation(investigationData.ai_recommended_action!)}
                              className="px-2.5 py-1.5 bg-sky-100 hover:bg-sky-200 text-sky-900 rounded-lg text-[11px] font-semibold transition-colors flex items-center gap-1.5"
                            >
                              <span>Adopt into Notes</span>
                              <ArrowRight className="w-3 h-3" />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleApplyRecommendedFixDirectly(investigationData.ai_recommended_action!)}
                              className="px-2.5 py-1.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg text-[11px] font-semibold transition-colors flex items-center gap-1.5 shadow-sm"
                            >
                              <ShieldCheck className="w-3 h-3" />
                              <span>Apply Recommended Fix</span>
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* SECTION 3: SUPPORTING EVIDENCE */}
                  <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
                    <div>
                      <span className="text-[10px] font-bold text-secondary uppercase tracking-wider block mb-2">
                        Actual Attendance vs. Scheduled Baseline Comparison
                      </span>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                        <div className="bg-white border border-slate-200 rounded-lg p-2.5">
                          <span className="text-[10px] text-secondary block">Worked Duration</span>
                          <span className="font-bold text-dark text-xs block">
                            {investigationData.actual_vs_expected.actual_worked_minutes ?? 0}m (
                            {((investigationData.actual_vs_expected.actual_worked_minutes ?? 0) / 60).toFixed(1)}h)
                          </span>
                          <span className="text-[10px] text-secondary block mt-0.5">
                            Expected: {investigationData.actual_vs_expected.expected_worked_minutes ?? 480}m
                            {investigationData.actual_vs_expected.worked_hours_variance_minutes !== undefined && (
                              <strong
                                className={`ml-1 ${
                                  investigationData.actual_vs_expected.worked_hours_variance_minutes > 0
                                    ? 'text-amber-600'
                                    : investigationData.actual_vs_expected.worked_hours_variance_minutes < 0
                                    ? 'text-rose-600'
                                    : 'text-slate-500'
                                }`}
                              >
                                ({investigationData.actual_vs_expected.worked_hours_variance_minutes > 0 ? '+' : ''}
                                {investigationData.actual_vs_expected.worked_hours_variance_minutes}m)
                              </strong>
                            )}
                          </span>
                        </div>

                        <div className="bg-white border border-slate-200 rounded-lg p-2.5">
                          <span className="text-[10px] text-secondary block">Overtime Logged</span>
                          <span className="font-bold text-dark text-xs block">
                            {investigationData.actual_vs_expected.actual_overtime_minutes ?? 0}m (
                            {((investigationData.actual_vs_expected.actual_overtime_minutes ?? 0) / 60).toFixed(1)}h)
                          </span>
                          <span className="text-[10px] text-secondary block mt-0.5">
                            Expected: {investigationData.actual_vs_expected.expected_overtime_minutes ?? 0}m
                          </span>
                        </div>

                        <div className="bg-white border border-slate-200 rounded-lg p-2.5">
                          <span className="text-[10px] text-secondary block">Late Arrival Minutes</span>
                          <span className="font-bold text-dark text-xs block">
                            {investigationData.actual_vs_expected.actual_late_minutes ?? 0}m
                          </span>
                          <span className="text-[10px] text-secondary block mt-0.5">
                            Grace: {investigationData.actual_vs_expected.shift_grace_period_minutes ?? 15}m
                          </span>
                        </div>

                        <div className="bg-white border border-slate-200 rounded-lg p-2.5">
                          <span className="text-[10px] text-secondary block">Break Duration</span>
                          <span className="font-bold text-dark text-xs block">
                            {investigationData.actual_vs_expected.actual_break_minutes ?? 0}m
                          </span>
                          <span className="text-[10px] text-secondary block mt-0.5">
                            Max Allowed: {investigationData.actual_vs_expected.expected_break_minutes ?? 60}m
                          </span>
                        </div>
                      </div>

                      {/* Timestamps Row */}
                      <div className="mt-2.5 flex flex-wrap items-center gap-4 text-[11px] text-slate-600 bg-white border border-slate-200 rounded-lg px-3 py-1.5 font-mono">
                        <div>
                          <span className="text-secondary mr-1">Actual Clock In:</span>
                          <strong>{investigationData.actual_vs_expected.clock_in_actual || 'None Recorded'}</strong>
                        </div>
                        <div>
                          <span className="text-secondary mr-1">Actual Clock Out:</span>
                          <strong>{investigationData.actual_vs_expected.clock_out_actual || 'None Recorded'}</strong>
                        </div>
                        <div>
                          <span className="text-secondary mr-1">Shift Schedule:</span>
                          <strong>
                            {investigationData.actual_vs_expected.scheduled_start || '--:--'} - {investigationData.actual_vs_expected.scheduled_end || '--:--'}
                          </strong>
                        </div>
                      </div>
                    </div>

                    {/* Historical Context */}
                    <div className="space-y-2 pt-2 border-t border-slate-200">
                      <span className="text-[10px] font-bold text-secondary uppercase tracking-wider block">
                        Historical Context (30-Day Verified Attendance Pattern)
                      </span>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                        <div className="bg-white border border-slate-200 rounded-lg p-2.5">
                          <span className="text-[10px] text-secondary block">Avg Daily Hours</span>
                          <span className="font-bold text-dark text-xs block">
                            {investigationData.historical_context.avg_daily_worked_hours}h / day
                          </span>
                          <span className="text-[10px] text-secondary block mt-0.5">30-day baseline</span>
                        </div>
                        <div className="bg-white border border-slate-200 rounded-lg p-2.5">
                          <span className="text-[10px] text-secondary block">Recent Overtime Days</span>
                          <span className="font-bold text-dark text-xs block">
                            {investigationData.historical_context.overtime_frequency_count} days
                          </span>
                          <span className="text-[10px] text-secondary block mt-0.5">In past 30 days</span>
                        </div>
                        <div className="bg-white border border-slate-200 rounded-lg p-2.5">
                          <span className="text-[10px] text-secondary block">Late Arrival Days</span>
                          <span className="font-bold text-dark text-xs block">
                            {investigationData.historical_context.late_arrival_frequency_count} days
                          </span>
                          <span className="text-[10px] text-secondary block mt-0.5">In past 30 days</span>
                        </div>
                        <div className="bg-white border border-slate-200 rounded-lg p-2.5">
                          <span className="text-[10px] text-secondary block">Prior Similar Flags</span>
                          <span className="font-bold text-dark text-xs block">
                            {investigationData.historical_context.previous_similar_anomalies_count} flags
                          </span>
                          <span className="text-[10px] text-secondary block mt-0.5">Repeat occurrence check</span>
                        </div>
                      </div>
                    </div>

                    {/* Identified Factors */}
                    {investigationData.possible_causes && investigationData.possible_causes.length > 0 && (
                      <div className="pt-2 border-t border-slate-200 flex flex-wrap gap-1.5 items-center">
                        <span className="text-[10px] text-slate-700 font-semibold">Identified Factors:</span>
                        {investigationData.possible_causes.map((cause, i) => (
                          <span
                            key={i}
                            className="px-2 py-0.5 bg-white border border-slate-200 rounded text-[10px] text-slate-700"
                          >
                            {cause}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* SECTION 4: RESOLUTION ACTION & MANDATORY NOTES */}
                  <form onSubmit={handleReviewSubmit} className="space-y-4 pt-4 border-t border-slate-200">
                    <div>
                      <label className="block text-xs font-bold text-dark mb-2">
                        Select Investigation Resolution Status:
                      </label>
                      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                        <label
                          className={`p-2.5 border rounded-xl flex items-center gap-2 cursor-pointer transition-colors ${
                            resolutionStatus === 'resolved'
                              ? 'bg-emerald-50 border-emerald-300 text-emerald-950 font-semibold'
                              : 'bg-white border-slate-200 text-dark hover:bg-slate-50'
                          }`}
                        >
                          <input
                            type="radio"
                            name="resolution_status"
                            value="resolved"
                            checked={resolutionStatus === 'resolved'}
                            onChange={() => setResolutionStatus('resolved')}
                            className="text-emerald-600 focus:ring-emerald-500"
                          />
                          <span>Resolve (Completed & Verified)</span>
                        </label>

                        <label
                          className={`p-2.5 border rounded-xl flex items-center gap-2 cursor-pointer transition-colors ${
                            resolutionStatus === 'dismissed'
                              ? 'bg-slate-100 border-slate-300 text-slate-900 font-semibold'
                              : 'bg-white border-slate-200 text-dark hover:bg-slate-50'
                          }`}
                        >
                          <input
                            type="radio"
                            name="resolution_status"
                            value="dismissed"
                            checked={resolutionStatus === 'dismissed'}
                            onChange={() => setResolutionStatus('dismissed')}
                            className="text-slate-600 focus:ring-slate-500"
                          />
                          <span>Dismiss (False Positive)</span>
                        </label>

                        <label
                          className={`p-2.5 border rounded-xl flex items-center gap-2 cursor-pointer transition-colors ${
                            resolutionStatus === 'correction_requested'
                              ? 'bg-purple-50 border-purple-300 text-purple-950 font-semibold'
                              : 'bg-white border-slate-200 text-dark hover:bg-slate-50'
                          }`}
                        >
                          <input
                            type="radio"
                            name="resolution_status"
                            value="correction_requested"
                            checked={resolutionStatus === 'correction_requested'}
                            onChange={() => setResolutionStatus('correction_requested')}
                            className="text-purple-600 focus:ring-purple-500"
                          />
                          <span>Initiate Attendance Correction</span>
                        </label>

                        <label
                          className={`p-2.5 border rounded-xl flex items-center gap-2 cursor-pointer transition-colors ${
                            resolutionStatus === 'escalated'
                              ? 'bg-red-50 border-red-300 text-red-950 font-semibold'
                              : 'bg-white border-slate-200 text-dark hover:bg-slate-50'
                          }`}
                        >
                          <input
                            type="radio"
                            name="resolution_status"
                            value="escalated"
                            checked={resolutionStatus === 'escalated'}
                            onChange={() => setResolutionStatus('escalated')}
                            className="text-red-600 focus:ring-red-500"
                          />
                          <span>Escalate to HR/Admin</span>
                        </label>

                        <label
                          className={`p-2.5 border rounded-xl flex items-center gap-2 cursor-pointer transition-colors ${
                            resolutionStatus === 'under_review'
                              ? 'bg-amber-50 border-amber-300 text-amber-950 font-semibold'
                              : 'bg-white border-slate-200 text-dark hover:bg-slate-50'
                          }`}
                        >
                          <input
                            type="radio"
                            name="resolution_status"
                            value="under_review"
                            checked={resolutionStatus === 'under_review'}
                            onChange={() => setResolutionStatus('under_review')}
                            className="text-amber-600 focus:ring-amber-500"
                          />
                          <span>Mark for Further Review</span>
                        </label>
                      </div>
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label className="block text-xs font-bold text-dark">
                          Mandatory Resolution Notes & Action Justification <span className="text-danger">*</span>
                        </label>
                        <span className="text-[10px] text-secondary">Preserved in immutable compliance audit logs</span>
                      </div>
                      <textarea
                        required
                        rows={3}
                        placeholder="Document verified departure time, supervisor approval status, shift correction rationale..."
                        value={resolutionNotes}
                        onChange={(e) => setResolutionNotes(e.target.value)}
                        className="w-full px-3 py-2 text-xs bg-slate-50 border border-border rounded-lg text-dark focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      />
                    </div>

                    <div className="flex justify-end gap-2.5 pt-3">
                      <button
                        type="button"
                        onClick={closeInvestigationModal}
                        className="px-4 py-2 border border-border rounded-lg text-xs font-medium text-secondary hover:bg-slate-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={submittingReview}
                        className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors flex items-center gap-1.5 disabled:opacity-50"
                      >
                        {submittingReview ? (
                          <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                        ) : (
                          <ShieldCheck className="w-4 h-4" />
                        )}
                        <span>Save Resolution & Audit Trail</span>
                      </button>
                    </div>
                  </form>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
