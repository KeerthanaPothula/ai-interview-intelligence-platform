import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { LiveInterviewPage } from './LiveInterviewPage';
import * as client from '../api/client';

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

// No interview in progress (the default mock below): the page shows the
// setup form once its resume check settles.
async function renderSetup() {
  const result = renderPage();
  await screen.findByLabelText('Target Role');
  return result;
}

describe('LiveInterviewPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(client, 'getActiveLiveInterview').mockResolvedValue(null);
  });

  it('renders the setup form by default', async () => {
    await renderSetup();
    expect(screen.getByText('Live AI Interview')).toBeTruthy();
    expect(screen.getByLabelText('Target Role')).toBeTruthy();
    expect(screen.getByText('Start Interview')).toBeTruthy();
  });

  it('shows validation error if job description is too short', async () => {
    await renderSetup();
    await userEvent.type(screen.getByLabelText('Target Role'), 'Engineer');
    await userEvent.type(screen.getByLabelText('Job Description'), 'short');
    await userEvent.click(screen.getByText('Start Interview'));
    expect(screen.getByText(/at least 20 characters/i)).toBeTruthy();
  });

  it('starts the interview and shows current question', async () => {
    vi.spyOn(client, 'startLiveInterview').mockResolvedValue(MOCK_SESSION);

    await renderSetup();
    await userEvent.type(screen.getByLabelText('Target Role'), 'Software Engineer');
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

    await renderSetup();
    await userEvent.type(screen.getByLabelText('Target Role'), 'Engineer');
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

    await renderSetup();
    await userEvent.type(screen.getByLabelText('Target Role'), 'Engineer');
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

    await renderSetup();
    await userEvent.type(screen.getByLabelText('Target Role'), 'Engineer');
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

  it('submits the typed answer when ending the interview', async () => {
    vi.spyOn(client, 'startLiveInterview').mockResolvedValue(MOCK_SESSION);
    const endSpy = vi.spyOn(client, 'endLiveInterview').mockResolvedValue({
      session_id: 'sess-1',
      status: 'completed',
      total_turns: 1,
      summary: 'Great performance overall!',
      turns: MOCK_SESSION.turns,
    });

    await renderSetup();
    await userEvent.type(screen.getByLabelText('Target Role'), 'Engineer');
    await userEvent.type(
      screen.getByLabelText('Job Description'),
      'A Python backend engineering role with FastAPI.',
    );
    await userEvent.click(screen.getByText('Start Interview'));

    await waitFor(() => screen.getByLabelText('Your answer'));
    await userEvent.type(screen.getByLabelText('Your answer'), 'My typed answer.');

    const endButtons = screen.getAllByText('End Interview');
    await userEvent.click(endButtons[0]);

    await waitFor(() => {
      expect(endSpy).toHaveBeenCalledWith('sess-1', 'test-token', {
        response_text: 'My typed answer.',
      });
    });
  });

  it('shows error message if start interview fails', async () => {
    vi.spyOn(client, 'startLiveInterview').mockRejectedValue(new Error('Network error'));

    await renderSetup();
    await userEvent.type(screen.getByLabelText('Target Role'), 'Engineer');
    await userEvent.type(
      screen.getByLabelText('Job Description'),
      'A Python backend engineering role with FastAPI.',
    );
    await userEvent.click(screen.getByText('Start Interview'));

    await waitFor(() => {
      expect(screen.getByText(/Failed to start/i)).toBeTruthy();
    });
  });

  it('shows the backend message when starting fails with an ApiError', async () => {
    vi.spyOn(client, 'startLiveInterview').mockRejectedValue(
      new client.ApiError(403, 'You do not have permission to perform this action.'),
    );

    await renderSetup();
    await userEvent.type(screen.getByLabelText('Target Role'), 'Engineer');
    await userEvent.type(
      screen.getByLabelText('Job Description'),
      'A Python backend engineering role with FastAPI.',
    );
    await userEvent.click(screen.getByText('Start Interview'));

    expect(
      await screen.findByText('You do not have permission to perform this action.'),
    ).toBeTruthy();
  });

  it('rejects a one-character role before calling the backend (min_length=2)', async () => {
    const spy = vi.spyOn(client, 'startLiveInterview');

    await renderSetup();
    await userEvent.type(screen.getByLabelText('Target Role'), 'X');
    await userEvent.type(
      screen.getByLabelText('Job Description'),
      'A Python backend engineering role with FastAPI.',
    );
    await userEvent.click(screen.getByText('Start Interview'));

    expect(screen.getByText(/at least 2 characters/i)).toBeTruthy();
    expect(spy).not.toHaveBeenCalled();
  });

  it('keeps the workspace and timer running when ending fails', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      vi.spyOn(client, 'startLiveInterview').mockResolvedValue(MOCK_SESSION);
      vi.spyOn(client, 'endLiveInterview').mockRejectedValue(
        new client.ApiError(409, 'Interview session is already completed'),
      );

      await renderSetup();
      await userEvent.type(screen.getByLabelText('Target Role'), 'Engineer');
      await userEvent.type(
        screen.getByLabelText('Job Description'),
        'A Python backend engineering role with FastAPI.',
      );
      await userEvent.click(screen.getByText('Start Interview'));
      await waitFor(() => screen.getByText('End Interview'));

      await userEvent.click(screen.getAllByText('End Interview')[0]);
      expect(await screen.findByText('Interview session is already completed')).toBeTruthy();
      expect(screen.getByTestId('current-question')).toBeTruthy();

      const before = screen.getByLabelText(/Elapsed time/).textContent;
      await vi.advanceTimersByTimeAsync(3000);
      expect(screen.getByLabelText(/Elapsed time/).textContent).not.toBe(before);
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not render a second <main> landmark inside the app layout', async () => {
    vi.spyOn(client, 'startLiveInterview').mockResolvedValue(MOCK_SESSION);

    const { container } = await renderSetup();
    await userEvent.type(screen.getByLabelText('Target Role'), 'Engineer');
    await userEvent.type(
      screen.getByLabelText('Job Description'),
      'A Python backend engineering role with FastAPI.',
    );
    await userEvent.click(screen.getByText('Start Interview'));
    await waitFor(() => screen.getByTestId('current-question'));

    expect(container.querySelector('main')).toBeNull();
    expect(container.querySelector('#main-content')).toBeNull();
  });

  describe('resuming an interview in progress', () => {
    const TURN_2 = {
      ...MOCK_SESSION.turns[0],
      id: 'turn-2',
      turn_number: 2,
      question_text: 'What would you do differently?',
      difficulty_level: 2,
    };
    const ACTIVE = {
      ...MOCK_SESSION,
      current_turn: 2,
      turns: [{ ...MOCK_SESSION.turns[0], response_text: 'My first answer.' }, TURN_2],
      current_question: TURN_2,
    };

    function beforeUnloadIsBlocked() {
      const ev = new Event('beforeunload', { cancelable: true });
      window.dispatchEvent(ev);
      return ev.defaultPrevented;
    }

    it('restores the active interview after a reload without creating turns', async () => {
      const active = vi.spyOn(client, 'getActiveLiveInterview').mockResolvedValue(ACTIVE);
      const start = vi.spyOn(client, 'startLiveInterview');
      const next = vi.spyOn(client, 'nextLiveQuestion');

      renderPage();

      expect(await screen.findByText(/Resumed your interview in progress/)).toBeTruthy();
      expect(screen.getByTestId('current-question').textContent).toBe(
        'What would you do differently?',
      );
      expect(screen.getByText('My first answer.')).toBeTruthy();
      expect(screen.getByText(/Question 2 of 3/)).toBeTruthy();
      expect(screen.queryByLabelText('Target Role')).toBeNull();
      expect(active).toHaveBeenCalledTimes(1);
      expect(start).not.toHaveBeenCalled();
      expect(next).not.toHaveBeenCalled();
    });

    it('keeps an answer already saved on the current question', async () => {
      vi.spyOn(client, 'getActiveLiveInterview').mockResolvedValue({
        ...ACTIVE,
        current_question: { ...TURN_2, response_text: 'Saved answer.' },
      });

      renderPage();

      await screen.findByText(/Resumed your interview in progress/);
      expect((screen.getByLabelText('Your answer') as HTMLTextAreaElement).value).toBe(
        'Saved answer.',
      );
    });

    it('warns before unload while the interview is active', async () => {
      vi.spyOn(client, 'getActiveLiveInterview').mockResolvedValue(ACTIVE);
      renderPage();
      await screen.findByText(/Resumed your interview in progress/);

      expect(beforeUnloadIsBlocked()).toBe(true);
    });

    it('stops warning once the interview has ended', async () => {
      vi.spyOn(client, 'getActiveLiveInterview').mockResolvedValue(ACTIVE);
      vi.spyOn(client, 'endLiveInterview').mockResolvedValue({
        session_id: 'sess-1',
        status: 'completed',
        total_turns: 2,
        summary: 'Great performance overall!',
        turns: ACTIVE.turns,
      });
      renderPage();
      await screen.findByText(/Resumed your interview in progress/);
      expect(beforeUnloadIsBlocked()).toBe(true);

      await userEvent.click(screen.getAllByText('End Interview')[0]);
      await screen.findByText('Interview Complete');

      expect(beforeUnloadIsBlocked()).toBe(false);
    });

    it('does not warn when there is no interview in progress', async () => {
      await renderSetup();
      expect(beforeUnloadIsBlocked()).toBe(false);
    });

    it('shows a retryable error, not the setup form, when the check fails', async () => {
      vi.spyOn(client, 'getActiveLiveInterview')
        .mockRejectedValueOnce(new client.ApiError(0, 'Cannot connect to the backend.'))
        .mockResolvedValueOnce(ACTIVE);
      const start = vi.spyOn(client, 'startLiveInterview');

      renderPage();

      expect(await screen.findByText(/Cannot connect to the backend\./)).toBeTruthy();
      expect(screen.getByText(/nothing was started or discarded/)).toBeTruthy();
      expect(screen.queryByLabelText('Target Role')).toBeNull();

      await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
      expect(await screen.findByText(/Resumed your interview in progress/)).toBeTruthy();
      expect(start).not.toHaveBeenCalled();
    });
  });
});
