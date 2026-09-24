import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DashboardPage } from './DashboardPage';
import * as client from '../api/client';

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/AuthContext')>();
  return { ...actual, useAuth: vi.fn(() => ({ token: 'test-token', isAuthenticated: true })) };
});

// recharts' ResponsiveContainer needs ResizeObserver, which jsdom lacks.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(client, 'getAnalyticsOverview').mockResolvedValue({
      total_sessions: 2,
      completed_sessions: 1,
      average_overall_score: 7,
      total_responses_analyzed: 3,
      strongest_skill: 'Communication',
      weakest_skill: 'Technical',
      improvement_score: null,
    });
    vi.spyOn(client, 'getBenchmarks').mockResolvedValue({
      user_average_score: null,
      percentile_rank: null,
      total_platform_responses: 0,
      user_responses_analyzed: 3,
    });
    vi.spyOn(client, 'getInsights').mockResolvedValue({ insights: [] });
    vi.spyOn(client, 'getActivityTimeline').mockResolvedValue({ events: [] });
    // Trends include every session (backend outer join): a scored session,
    // then a newer draft with no analyses yet.
    vi.spyOn(client, 'getAnalyticsTrends').mockResolvedValue([
      {
        session_id: 's1',
        session_title: 'Scored',
        created_at: daysAgo(2),
        average_overall_score: 7,
        average_communication_score: 8.5,
        average_technical_score: 6,
        average_problem_solving_score: 7,
        average_confidence_score: 6.5,
      },
      {
        session_id: 's2',
        session_title: 'Fresh draft',
        created_at: daysAgo(0),
        average_overall_score: null,
        average_communication_score: null,
        average_technical_score: null,
        average_problem_solving_score: null,
        average_confidence_score: null,
      },
    ]);
  });

  it('shows the latest scored session in the skill breakdown, not an unscored draft', async () => {
    render(<DashboardPage />);
    expect(await screen.findByText('8.5')).toBeTruthy();
  });

  it('does not count unscored sessions toward the weekly goal', async () => {
    render(<DashboardPage />);
    expect(await screen.findByRole('progressbar', { name: '1 of 3 interviews completed' })).toBeTruthy();
  });
});
