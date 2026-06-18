import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { LiveInterviewPage } from './LiveInterviewPage';
import * as client from '../api/client';
import * as authCtx from '../context/AuthContext';

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/AuthContext')>();
  return {
    ...actual,
    useAuth: vi.fn(() => ({
      token: 'test-token',
      isAuthenticated: true,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
    })),
  };
});

const MOCK_SESSION = {
  id: 'sess-1',
  user_id: 'user-1',
  job_role: 'Software Engineer',
  job_description: 'Python backend role',
  status: 'active' as const,
  current_turn: 1,
  max_turns: 3,
  created_at: '2026-06-18T10:00:00Z',
  completed_at: null,
  turns: [
    {
      id: 'turn-1',
      live_session_id: 'sess-1',
      turn_number: 1,
      question_text: 'Tell me about yourself.',
      difficulty_level: 1,
      response_text: null,
      audio_response_id: null,
      created_at: '2026-06-18T10:01:00Z',
    },
  ],
  current_question: {
    id: 'turn-1',
    live_session_id: 'sess-1',
    turn_number: 1,
    question_text: 'Tell me about yourself.',
    difficulty_level: 1,
    response_text: null,
    audio_response_id: null,
    created_at: '2026-06-18T10:01:00Z',
  },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LiveInterviewPage />
    </MemoryRouter>,
  );
}

describe('LiveInterviewPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the setup form by default', () => {
    renderPage();
    expect(screen.getByText('Live AI Interview')).toBeTruthy();
    expect(screen.getByLabelText('Target Job Role')).toBeTruthy();
    expect(screen.getByText('Start Interview')).toBeTruthy();
  });

  it('shows validation error if job description is too short', async () => {
    renderPage();
    await userEvent.type(screen.getByLabelText('Target Job Role'), 'Engineer');
    await userEvent.type(screen.getByLabelText('Job Description'), 'short');
    await userEvent.click(screen.getByText('Start Interview'));
    expect(screen.getByText(/at least 20 characters/i)).toBeTruthy();
  });

  it('starts the interview and shows current question', async () => {
    vi.spyOn(client, 'startLiveInterview').mockResolvedValue(MOCK_SESSION);

    renderPage();
    await userEvent.type(screen.getByLabelText('Target Job Role'), 'Software Engineer');
    await userEvent.type(
      screen.getByLabelText('Job Description'),
      'A Python backend engineering role with FastAPI.',
    );
    await userEvent.click(screen.getByText('Start Interview'));

    await waitFor(() => {
      expect(screen.getByTestId('current-question')).toBeTruthy();
    });
    expect(screen.getByTestId('current-question').textContent).toBe('Tell me about yourself.');
  });

  it('shows progress bar during interview', async () => {
    vi.spyOn(client, 'startLiveInterview').mockResolvedValue(MOCK_SESSION);

    renderPage();
    await userEvent.type(screen.getByLabelText('Target Job Role'), 'Engineer');
    await userEvent.type(
      screen.getByLabelText('Job Description'),
      'A Python backend engineering role with FastAPI.',
    );
    await userEvent.click(screen.getByText('Start Interview'));

    await waitFor(() => {
      expect(screen.getByText(/Question 1 of 3/i)).toBeTruthy();
    });
  });

  it('shows difficulty badge for current question', async () => {
    vi.spyOn(client, 'startLiveInterview').mockResolvedValue(MOCK_SESSION);

    renderPage();
    await userEvent.type(screen.getByLabelText('Target Job Role'), 'Engineer');
    await userEvent.type(
      screen.getByLabelText('Job Description'),
      'A Python backend engineering role with FastAPI.',
    );
    await userEvent.click(screen.getByText('Start Interview'));

    await waitFor(() => {
      expect(screen.getByText('Warm-up')).toBeTruthy();
    });
  });

  it('displays summary on interview end', async () => {
    vi.spyOn(client, 'startLiveInterview').mockResolvedValue(MOCK_SESSION);
    vi.spyOn(client, 'endLiveInterview').mockResolvedValue({
      session_id: 'sess-1',
      status: 'completed',
      total_turns: 1,
      summary: 'Great performance overall!',
      turns: MOCK_SESSION.turns,
    });

    renderPage();
    await userEvent.type(screen.getByLabelText('Target Job Role'), 'Engineer');
    await userEvent.type(
      screen.getByLabelText('Job Description'),
      'A Python backend engineering role with FastAPI.',
    );
    await userEvent.click(screen.getByText('Start Interview'));

    await waitFor(() => screen.getByText('End Interview'));

    // Click the header-level End Interview button (not the one inside progress bar for last turn)
    const endButtons = screen.getAllByText('End Interview');
    await userEvent.click(endButtons[0]);

    await waitFor(() => {
      expect(screen.getByText('Great performance overall!')).toBeTruthy();
    });
    expect(screen.getByText('Interview Complete')).toBeTruthy();
  });

  it('shows error message if start interview fails', async () => {
    vi.spyOn(client, 'startLiveInterview').mockRejectedValue(new Error('Network error'));

    renderPage();
    await userEvent.type(screen.getByLabelText('Target Job Role'), 'Engineer');
    await userEvent.type(
      screen.getByLabelText('Job Description'),
      'A Python backend engineering role with FastAPI.',
    );
    await userEvent.click(screen.getByText('Start Interview'));

    await waitFor(() => {
      expect(screen.getByText(/Failed to start/i)).toBeTruthy();
    });
  });
});
