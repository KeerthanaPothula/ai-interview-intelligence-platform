import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { InterviewReportPage } from './InterviewReportPage';
import { RecruiterPage } from './RecruiterPage';
import { ToastProvider } from '../context/ToastContext';
import * as auth from '../context/AuthContext';
import * as client from '../api/client';

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/AuthContext')>();
  return { ...actual, useAuth: vi.fn() };
});

const SESSION = {
  id: 'sess-1',
  user_id: 'candidate-1',
  title: 'Backend Interview',
  job_role: 'Backend Engineer',
  job_description: 'A Python backend engineering role.',
  status: 'completed' as const,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  questions: [],
  response_count: 0,
};

const REPORT = {
  id: 'rep-1',
  session_id: 'sess-1',
  overall_performance: 'Solid performance overall.',
  final_score: 8,
  confidence_score: 80,
  communication_score: 8,
  technical_score: 7,
  problem_solving_score: 7,
  strengths: '["Clear structure"]',
  weaknesses: '["Go deeper"]',
  improvement_plan: null,
  readiness_level: 'Interview Ready',
  model_used: 'test',
  created_at: '2026-09-01T00:00:00Z',
};

const CANDIDATE = {
  id: 'candidate-1',
  session_id: 'sess-1',
  name: 'Cara Candidate',
  email: 'cara@example.com',
  role: 'Backend Engineer',
  resume_score: null,
  interview_score: 80,
  communication: 80,
  technical: 70,
  sessions_completed: 1,
  status: 'applied' as const,
  applied_days: 2,
};

function signedInAs(userId: string) {
  vi.mocked(auth.useAuth).mockReturnValue({
    token: 'test-token',
    user: { id: userId },
  } as unknown as ReturnType<typeof auth.useAuth>);
}

function renderApp(path: string) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/recruiter" element={<RecruiterPage />} />
          <Route path="/sessions/:sessionId/report" element={<InterviewReportPage />} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  );
}

describe('Opening a candidate report', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(client, 'getSession').mockResolvedValue(SESSION);
    vi.spyOn(client, 'getReport').mockResolvedValue(REPORT);
    // Readiness/coaching stay owner-only on the backend.
    vi.spyOn(client, 'getReadiness').mockRejectedValue(new client.ApiError(404, 'Session not found.'));
    vi.spyOn(client, 'getCoachingPlan').mockRejectedValue(new client.ApiError(404, 'Session not found.'));
  });

  it('navigates from the recruiter pipeline to a read-only report', async () => {
    signedInAs('recruiter-1');
    vi.spyOn(client, 'listCandidates').mockResolvedValue({
      items: [CANDIDATE],
      total: 1,
      summary: { total_candidates: 1, shortlisted_count: 0, avg_resume_score: null, avg_interview_score: 80 },
    });
    renderApp('/recruiter');

    await userEvent.click(await screen.findByText('Cara Candidate'));
    await userEvent.click(await screen.findByRole('link', { name: 'View Report' }));

    expect(await screen.findByText('Performance Scores')).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Backend Interview' })).toBeTruthy();
    expect(client.getSession).toHaveBeenCalledWith('sess-1', 'test-token');
    expect(client.getReport).toHaveBeenCalledWith('sess-1', 'test-token');
    // Owner-only actions are not offered to a viewer.
    expect(screen.queryByRole('button', { name: 'Regenerate report' })).toBeNull();
    expect(screen.queryByText(/Generate Readiness Assessment/)).toBeNull();
    expect(screen.queryByText(/Generate Coaching Plan/)).toBeNull();
    expect(screen.getByRole('link', { name: /Back to candidates/ }).getAttribute('href')).toBe('/recruiter');
  });

  it('keeps the owner view unchanged for the candidate', async () => {
    signedInAs('candidate-1');
    renderApp('/sessions/sess-1/report');

    expect(await screen.findByRole('button', { name: 'Regenerate report' })).toBeTruthy();
    expect(screen.getByText(/Generate Readiness Assessment/)).toBeTruthy();
    expect(screen.getByText(/Generate Coaching Plan/)).toBeTruthy();
    expect(screen.getByRole('link', { name: /Back to session/ }).getAttribute('href')).toBe('/sessions/sess-1');
  });

  it('shows the error state when the backend denies the session', async () => {
    signedInAs('recruiter-1');
    vi.spyOn(client, 'getSession').mockRejectedValue(new client.ApiError(404, 'Session not found.'));
    renderApp('/sessions/sess-1/report');

    await waitFor(() => expect(screen.getByText('Unable to load this session.')).toBeTruthy());
  });
});
