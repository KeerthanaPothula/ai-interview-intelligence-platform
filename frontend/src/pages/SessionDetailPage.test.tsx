import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { SessionDetailPage } from './SessionDetailPage';
import { ToastProvider } from '../context/ToastContext';
import * as client from '../api/client';
import type { SessionStatus } from '../api/types';

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/AuthContext')>();
  return { ...actual, useAuth: vi.fn(() => ({ token: 'test-token', isAuthenticated: true })) };
});

function mockSession(status: SessionStatus) {
  vi.spyOn(client, 'getSession').mockResolvedValue({
    id: 'sess-1',
    user_id: 'user-1',
    title: 'Live Interview – Engineer',
    job_role: 'Engineer',
    job_description: 'A Python backend engineering role.',
    status,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    questions: [],
    response_count: 0,
  });
  vi.spyOn(client, 'listResponses').mockResolvedValue([]);
  vi.spyOn(client, 'listTextAnswers').mockResolvedValue([]);
}

function renderPage() {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={['/sessions/sess-1']}>
        <Routes>
          <Route path="/sessions/:sessionId" element={<SessionDetailPage />} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  );
}

describe('SessionDetailPage', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('offers question generation for a draft session', async () => {
    mockSession('draft');
    renderPage();
    expect(await screen.findByRole('button', { name: 'Generate Questions' })).toBeTruthy();
  });

  // Backend only generates questions for drafts (409 otherwise); completed
  // live interviews are mirrored here with no questions.
  it('does not offer question generation for a completed session without questions', async () => {
    mockSession('completed');
    renderPage();
    expect(await screen.findByText('No questions to show')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Generate Questions' })).toBeNull();
    expect(screen.getByRole('link', { name: /View Report/ })).toBeTruthy();
  });

  it('submits an answer and displays saved evaluation feedback', async () => {
    mockSession('in_progress');
    vi.mocked(client.getSession).mockResolvedValue({
      id: 'sess-1', user_id: 'user-1', title: 'Practice', job_role: 'Engineer',
      job_description: 'A Python backend engineering role.', status: 'in_progress',
      created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z', response_count: 0,
      questions: [{ id: 'q-1', body: 'Describe a challenge.', sequence_order: 1, category: 'behavioral', source: 'manual', created_at: '2026-09-01T00:00:00Z' }],
    });
    vi.spyOn(client, 'submitTextAnswer').mockResolvedValue({
      id: 'a-1', session_id: 'sess-1', question_id: 'q-1', answer_text: 'I solved it.',
      overall_score: 8, strengths: ['Clear example'], weaknesses: ['More detail needed'],
      detailed_feedback: 'Strong answer.', created_at: '2026-09-01T00:00:00Z',
    });
    renderPage();
    const textarea = await screen.findByRole('textbox', { name: 'Your answer' });
    fireEvent.change(textarea, { target: { value: 'I solved it.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Submit Answer' }));
    expect(await screen.findByText('Answer saved')).toBeTruthy();
    expect(await screen.findByText('Score: 8.0 / 10')).toBeTruthy();
    expect(screen.getByText('Strong answer.')).toBeTruthy();
  });
});
