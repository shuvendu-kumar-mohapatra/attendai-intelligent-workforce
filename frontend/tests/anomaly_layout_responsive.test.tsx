import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
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

describe('Anomaly Page – Layout & Responsiveness', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockAnomaliesList = [
    {
      id: 'anom-1',
      employee_name: 'Alex Mercer',
      employee_code: 'EMP-001',
      date: '2026-11-17',
      anomaly_type: 'excessive_overtime',
      severity: 'high',
      score: 0.72,
      detection_method: 'isolation_forest',
      explanation: 'Overtime duration logged at 240 minutes, significantly exceeding normal baseline.',
      suggested_action: 'Review overtime authorization',
      status: 'pending',
    },
  ];

  const mockDashboardData = {
    pending_count: 1,
    high_priority_count: 1,
    repeated_patterns_count: 0,
    prioritized_anomalies: [
      {
        anomaly_id: 'anom-1',
        employee_name: 'Alex Mercer',
        employee_code: 'EMP-001',
        department_name: 'Engineering',
        anomaly_type: 'excessive_overtime',
        severity: 'high',
        detection_date: '2026-11-17',
        score: 0.72,
        status: 'pending',
        primary_recommendation: {
          title: 'Verify Overtime Authorization',
          action: 'Audit supervisor sign-off for extended shift duration.',
          required_authorization: 'HR Manager',
        },
      },
    ],
  };

  it('renders responsive grid with 3 cols on large, 2 on medium, 1 on mobile', async () => {
    (api.get as any).mockImplementation((url: string) => {
      if (url.includes('/anomalies/recommendations/dashboard')) {
        return Promise.resolve({ data: mockDashboardData });
      }
      if (url === '/anomalies' || url.startsWith('/anomalies?')) {
        return Promise.resolve({ data: mockAnomaliesList });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    const { container } = render(
      <AuthProvider>
        <BrowserRouter>
          <Anomalies />
        </BrowserRouter>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getAllByText('Alex Mercer').length).toBeGreaterThanOrEqual(1);
    });

    // 1. Verify recommendation cards grid classes
    const cardGrid = container.querySelector('.grid-cols-1.md\\:grid-cols-2.xl\\:grid-cols-3');
    expect(cardGrid).toBeInTheDocument();
    expect(cardGrid?.className).toContain('min-w-0');
    expect(cardGrid?.className).toContain('max-w-full');

    // 2. Verify table horizontal overflow container
    const tableScrollContainer = container.querySelector('.overflow-x-auto');
    expect(tableScrollContainer).toBeInTheDocument();
    expect(tableScrollContainer?.className).toContain('w-full');
    expect(tableScrollContainer?.className).toContain('max-w-full');

    // 3. Verify table has intelligent min-width preventing column squishing and clipping
    const table = container.querySelector('table');
    expect(table).toBeInTheDocument();
    expect(table?.className).toContain('min-w-[1100px]');

    // 4. Verify Explanation column wraps multi-line without truncation
    expect(screen.getByText('Overtime duration logged at 240 minutes, significantly exceeding normal baseline.')).toBeInTheDocument();
    const explanationEl = screen.getByText('Overtime duration logged at 240 minutes, significantly exceeding normal baseline.');
    expect(explanationEl.className).toContain('break-words');
    expect(explanationEl.className).toContain('leading-relaxed');
    expect(explanationEl.className).not.toContain('truncate');

    // 5. Verify Suggested Action button displays full text and View Suggestion link
    expect(screen.getByText('Review overtime authorization')).toBeInTheDocument();
    expect(screen.getByText('View Suggestion')).toBeInTheDocument();
    expect(screen.getByText('AI Fix')).toBeInTheDocument();

    // 6. Verify Filter Bar counter displays record count aligned with container
    expect(screen.getByText(/Showing.*anomaly records/)).toBeInTheDocument();
  });

  it('renders realistic long descriptions, long employee names, and unclipped suggested action cards', async () => {
    const longAnomaliesList = [
      {
        id: 'anom-long-1',
        employee_name: 'Alexander Bartholomew Christopher Montgomery',
        employee_code: 'EMP-998877',
        date: '2026-11-18',
        anomaly_type: 'repeated_excessive_overtime_discrepancy',
        severity: 'critical',
        score: 0.89,
        detection_method: 'isolation_forest',
        explanation:
          'Employee recorded excessive active working time exceeding the standard 480-minute schedule by 270 minutes without prior overtime authorization or manager signoff. Historical patterns indicate 3 similar occurrences over the past 14 days.',
        suggested_action:
          'Verify overtime pre-authorization in scheduling portal and conduct a supervisor interview to reconcile timesheet',
        status: 'pending',
      },
    ];

    (api.get as any).mockImplementation((url: string) => {
      if (url.includes('/anomalies/recommendations/dashboard')) {
        return Promise.resolve({ data: mockDashboardData });
      }
      if (url === '/anomalies' || url.startsWith('/anomalies?')) {
        return Promise.resolve({ data: longAnomaliesList });
      }
      if (url.includes('/investigate')) {
        return Promise.resolve({
          data: {
            anomaly_id: 'anom-long-1',
            employee_name: 'Alexander Bartholomew Christopher Montgomery',
            anomaly_type: 'repeated_excessive_overtime_discrepancy',
            detection_method: 'isolation_forest',
            score: 0.89,
            explanation: 'Detailed explanation text',
            status: 'pending',
            date: '2026-11-18',
            ai_recommended_action: {
              title: 'Reconcile Timesheet',
              explanation: 'Overtime authorization required',
              suggested_steps: ['Step 1'],
              source: 'NVIDIA NIM',
            },
          },
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    const { container } = render(
      <AuthProvider>
        <BrowserRouter>
          <Anomalies />
        </BrowserRouter>
      </AuthProvider>
    );

    // Wait for long employee name to render
    await waitFor(() => {
      expect(
        screen.getByText('Alexander Bartholomew Christopher Montgomery')
      ).toBeInTheDocument();
    });

    // Verify long employee name has break-words to prevent horizontal table blowout
    const employeeEl = screen.getByText('Alexander Bartholomew Christopher Montgomery');
    expect(employeeEl.className).toContain('break-words');

    // Verify long anomaly type has break-words
    const typeEl = screen.getByText('repeated excessive overtime discrepancy');
    expect(typeEl.className).toContain('break-words');

    // Verify long explanation wraps with break-words and leading-relaxed
    const explanationEl = screen.getByText(/Employee recorded excessive active working time/);
    expect(explanationEl).toBeInTheDocument();
    expect(explanationEl.className).toContain('break-words');
    expect(explanationEl.className).toContain('leading-relaxed');
    expect(explanationEl.className).not.toContain('truncate');

    // Verify long suggested action button displays full text and is not clipped
    const actionText = screen.getByText(
      'Verify overtime pre-authorization in scheduling portal and conduct a supervisor interview to reconcile timesheet'
    );
    expect(actionText).toBeInTheDocument();
    expect(actionText.className).toContain('break-words');
    expect(actionText.className).not.toContain('truncate');

    // Verify the Suggested Action button is interactive and clickable
    const actionBtn = actionText.closest('button');
    expect(actionBtn).toBeInTheDocument();
    expect(screen.getByText('View Suggestion')).toBeInTheDocument();
    expect(screen.getByText('AI Fix')).toBeInTheDocument();

    // Verify clicking Suggested Action button opens the investigation modal
    actionBtn?.click();
    await waitFor(() => {
      expect(
        screen.getByText('Investigate Anomaly Flag & Prescriptive Actions')
      ).toBeInTheDocument();
    });
  });
});
