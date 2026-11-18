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

    // 3. Verify table has min-width preventing column squishing
    const table = container.querySelector('table');
    expect(table).toBeInTheDocument();
    expect(table?.className).toContain('min-w-[900px]');
  });
});
