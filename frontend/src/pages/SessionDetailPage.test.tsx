import { render, screen } from '@testing-library/react';
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
});
