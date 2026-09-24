import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ResumePage } from './ResumePage';
import { ToastProvider } from '../context/ToastContext';
import * as client from '../api/client';

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/AuthContext')>();
  return { ...actual, useAuth: vi.fn(() => ({ token: 'test-token', isAuthenticated: true })) };
});

const RESUME = {
  id: 'r1',
  user_id: 'u1',
  filename: 'cv.pdf',
  extracted_text: null,
  created_at: '2026-09-01T00:00:00Z',
  chunk_count: 3,
};

function renderPage() {
  return render(
    <ToastProvider>
      <ResumePage />
    </ToastProvider>,
  );
}

describe('ResumePage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(client, 'analyzeResume').mockRejectedValue(new client.ApiError(503, 'AI down'));
  });

  it('shows the upload empty state when there is no resume (404)', async () => {
    vi.spyOn(client, 'getCurrentResume').mockRejectedValue(
      new client.ApiError(404, 'No resume uploaded yet'),
    );
    renderPage();
    expect(await screen.findByText('No resume uploaded yet')).toBeTruthy();
  });

  it('shows an error with retry instead of the empty state when loading fails', async () => {
    const spy = vi
      .spyOn(client, 'getCurrentResume')
      .mockRejectedValueOnce(new client.ApiError(0, 'Cannot connect to the backend.'))
      .mockResolvedValueOnce(RESUME);
    renderPage();

    expect(await screen.findByText('Cannot connect to the backend.')).toBeTruthy();
    expect(screen.queryByText('No resume uploaded yet')).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('cv.pdf')).toBeTruthy();
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('asks for confirmation before deleting and does nothing if cancelled', async () => {
    vi.spyOn(client, 'getCurrentResume').mockResolvedValue(RESUME);
    const del = vi.spyOn(client, 'deleteResume').mockResolvedValue(undefined);
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: 'Delete resume' }));

    expect(confirm).toHaveBeenCalled();
    expect(del).not.toHaveBeenCalled();
    expect(screen.getByText('cv.pdf')).toBeTruthy();
  });
});
