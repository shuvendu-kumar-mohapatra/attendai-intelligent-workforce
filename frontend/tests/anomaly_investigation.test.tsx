import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { Anomalies } from '../src/pages/Anomalies';
import { AuthProvider } from '../src/context/AuthContext';
import { api } from '../src/services/api';

vi.mock('../src/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}));

describe('Anomaly Investigation Popup – AI-Recommended Action', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockAnomaliesList = [
    {
      id: 'anom-101',
      employee_id: 'emp-1',
      employee_name: 'Stephanie Wright',
      employee_code: 'EMP-001',
      department_name: 'Engineering',
      date: '2026-11-17',
      anomaly_type: 'excessive_overtime',
      severity: 'high',
      score: 0.51,
      detection_method: 'isolation_forest',
      explanation: 'Overtime duration significantly exceeds scheduled shift parameters.',
      suggested_action: 'Verify shift duration and overtime approval',
      status: 'pending',
      created_at: '2026-11-17T18:00:00Z',
    },
  ];

  const mockInvestigationData = {
    anomaly_id: 'anom-101',
    employee_id: 'emp-1',
    employee_name: 'Stephanie Wright',
    employee_code: 'EMP-001',
    department_name: 'Engineering',
    anomaly_type: 'excessive_overtime',
    detection_date: '2026-11-17',
    severity: 'high',
    score: 0.51,
    detection_method: 'isolation_forest',
    explanation: 'Employee recorded 708 minutes of work (228 minutes overtime) against 480 scheduled minutes.',
    why_flagged_explanation: 'Employee recorded 708 minutes of work (228 minutes overtime) against 480 scheduled minutes.',
    confidence_score: 0.95,
    actual_vs_expected: {
      actual_worked_minutes: 708,
      expected_worked_minutes: 480,
      worked_hours_variance_minutes: 228,
      actual_overtime_minutes: 228,
      expected_overtime_minutes: 0,
      actual_late_minutes: 0,
      shift_grace_period_minutes: 15,
      actual_break_minutes: 60,
      expected_break_minutes: 60,
      clock_in_actual: '08:00:00',
      clock_out_actual: '19:48:00',
      scheduled_start: '09:00:00',
      scheduled_end: '18:00:00',
    },
    historical_context: {
      window_days: 30,
      avg_daily_worked_hours: 8.0,
      overtime_frequency_count: 1,
      late_arrival_frequency_count: 0,
      previous_similar_anomalies_count: 0,
      assigned_shift_name: 'Standard General Shift',
    },
    ai_recommended_action: {
      title: 'Recommended Action: Verify Overtime Authorization',
      explanation: "The employee's recorded working duration is substantially higher than the expected duration. Review the assigned shift and check whether the additional working hours were approved by the supervisor.",
      suggested_steps: [
        "Verify the employee's assigned shift.",
        'Check the overtime approval record.',
        'Confirm the actual working hours with the supervisor.',
        'Initiate an attendance correction if an error is identified.',
      ],
      supporting_evidence: [
        'Worked: 708 minutes (11.8h) vs. Scheduled 480 minutes',
        'Overtime: 228 minutes (3.8h)',
        'Late arrival: 0 minutes (Grace period: 15m)',
        'Isolation Forest score: 0.51 (isolation forest)',
      ],
      policy_reference: 'Overtime & Shift Differentials Policy – Section 3.1',
      priority: 'high',
      source: 'AI-assisted (NVIDIA NIM)',
      provider: 'nvidia',
      evidence_completeness: 'complete',
      action_type: 'audit_record',
    },
    recommended_actions: [],
    possible_causes: ['Extended shift duration logged: 228m overtime'],
  };

  it('renders the investigation popup with AI-Recommended Action section and steps', async () => {
    (api.get as any).mockImplementation((url: string) => {
      if (url.includes('/anomalies/recommendations/dashboard')) {
        return Promise.resolve({
          data: {
            pending_count: 1,
            high_priority_count: 1,
            repeated_patterns_count: 0,
            prioritized_anomalies: [],
          },
        });
      }
      if (url === '/anomalies' || url.startsWith('/anomalies?')) {
        return Promise.resolve({ data: mockAnomaliesList });
      }
      if (url.includes('/investigate')) {
        return Promise.resolve({ data: mockInvestigationData });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(
      <AuthProvider>
        <BrowserRouter>
          <Anomalies />
        </BrowserRouter>
      </AuthProvider>
    );

    // Find and click the Investigate button in the table
    await waitFor(() => {
      expect(screen.getByText('Stephanie Wright')).toBeInTheDocument();
    });

    const investigateBtn = screen.getByText('Investigate');
    fireEvent.click(investigateBtn);

    // Wait for popup to open and populate
    await waitFor(() => {
      expect(screen.getByText('Investigate Anomaly Flag & Prescriptive Actions')).toBeInTheDocument();
    });

    // 1. Check Anomaly Details
    expect(screen.getByText('Isolation Forest Score:')).toBeInTheDocument();
    expect(screen.getAllByText('0.51').length).toBeGreaterThanOrEqual(1);

    // 2. Check AI-Recommended Action Section
    expect(screen.getByText('AI-Recommended Action')).toBeInTheDocument();
    expect(screen.getAllByText('Recommended Action: Verify Overtime Authorization').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/substantially higher than the expected duration/).length).toBeGreaterThanOrEqual(1);

    // Check Suggested Steps
    expect(screen.getByText("Verify the employee's assigned shift.")).toBeInTheDocument();
    expect(screen.getByText('Check the overtime approval record.')).toBeInTheDocument();
    expect(screen.getByText('Confirm the actual working hours with the supervisor.')).toBeInTheDocument();
    expect(screen.getByText('Initiate an attendance correction if an error is identified.')).toBeInTheDocument();

    // Check Source Badge & Priority
    expect(screen.getByText('Source: AI-assisted (NVIDIA NIM)')).toBeInTheDocument();
    expect(screen.getByText('Priority: high')).toBeInTheDocument();

    // Check Policy Reference
    expect(screen.getByText('Overtime & Shift Differentials Policy – Section 3.1')).toBeInTheDocument();

    // Check Action Buttons
    expect(screen.getByText('Adopt into Notes')).toBeInTheDocument();
    expect(screen.getByText('Apply Recommended Fix')).toBeInTheDocument();

    // 3. Check Supporting Evidence section
    expect(screen.getByText('Actual Attendance vs. Scheduled Baseline Comparison')).toBeInTheDocument();
    expect(screen.getByText('Historical Context (30-Day Verified Attendance Pattern)')).toBeInTheDocument();

    // 4. Test "Adopt into Notes" button
    const adoptBtn = screen.getByText('Adopt into Notes');
    fireEvent.click(adoptBtn);

    const notesTextarea = screen.getByPlaceholderText(/Document verified departure time/i) as HTMLTextAreaElement;
    expect(notesTextarea.value).toContain('Recommended Action: Verify Overtime Authorization');
    expect(notesTextarea.value).toContain("1. Verify the employee's assigned shift.");

    // 5. Test "Apply Recommended Fix" button
    const applyFixBtn = screen.getByText('Apply Recommended Fix');
    fireEvent.click(applyFixBtn);
    expect(notesTextarea.value).toContain('Actions Taken:');
  });
});
