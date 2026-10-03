import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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
      // The server says the interview is still active: a genuine error.
      vi.spyOn(client, 'getLiveConversation').mockResolvedValue(MOCK_SESSION);

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

  describe('Next question (retry safety)', () => {
    const TURN_2 = {
      ...MOCK_SESSION.turns[0],
      id: 'turn-2',
      turn_number: 2,
      question_text: 'What would you do differently?',
      difficulty_level: 2,
    };
    const ADVANCED = {
      ...MOCK_SESSION,
      current_turn: 2,
      turns: [{ ...MOCK_SESSION.turns[0], response_text: 'My answer.' }, TURN_2],
      current_question: TURN_2,
    };

    async function renderAtQuestion1(answer: string) {
      vi.spyOn(client, 'getActiveLiveInterview').mockResolvedValue(MOCK_SESSION);
      renderPage();
      await screen.findByTestId('current-question');
      await userEvent.type(screen.getByLabelText('Your answer'), answer);
    }

    const answerBox = () => screen.getByLabelText('Your answer') as HTMLTextAreaElement;

    it('sends the question number and clears the answer after a successful Next', async () => {
      const next = vi.spyOn(client, 'nextLiveQuestion').mockResolvedValue(ADVANCED);
      await renderAtQuestion1('My answer.');

      await userEvent.click(screen.getByText('Next Question →'));

      await waitFor(() =>
        expect(screen.getByTestId('current-question').textContent).toBe(
          'What would you do differently?',
        ),
      );
      expect(next).toHaveBeenCalledWith(
        'sess-1',
        { response_text: 'My answer.', turn_number: 1 },
        'test-token',
      );
      expect(answerBox().value).toBe('');
    });

    it('retries a failed Next for the same question, keeping the answer meanwhile', async () => {
      const next = vi
        .spyOn(client, 'nextLiveQuestion')
        .mockRejectedValueOnce(new TypeError('Failed to fetch'))
        .mockResolvedValueOnce(ADVANCED);
      await renderAtQuestion1('My answer.');

      await userEvent.click(screen.getByText('Next Question →'));
      expect(await screen.findByText(/Failed to get next question/)).toBeTruthy();
      expect(answerBox().value).toBe('My answer.');

      await userEvent.click(screen.getByText('Next Question →'));
      await waitFor(() => expect(answerBox().value).toBe(''));
      expect(next).toHaveBeenCalledTimes(2);
      for (const call of next.mock.calls) {
        expect(call[1]).toEqual({ response_text: 'My answer.', turn_number: 1 });
      }
    });

    it('on "already answered", shows the real question and keeps the unsent text without resubmitting it', async () => {
      const next = vi
        .spyOn(client, 'nextLiveQuestion')
        .mockRejectedValue(
          new client.ApiError(
            409,
            'Question 1 already has a different saved answer, so this answer was not saved.',
          ),
        );
      const refresh = vi.spyOn(client, 'getLiveConversation').mockResolvedValue(ADVANCED);
      await renderAtQuestion1('Edited answer.');

      await userEvent.click(screen.getByText('Next Question →'));

      expect(await screen.findByText(/your text below was not submitted/)).toBeTruthy();
      await waitFor(() =>
        expect(screen.getByTestId('current-question').textContent).toBe(
          'What would you do differently?',
        ),
      );
      expect(answerBox().value).toBe('Edited answer.');
      expect(refresh).toHaveBeenCalledWith('sess-1', 'test-token');
      expect(next).toHaveBeenCalledTimes(1);
      expect(next.mock.calls[0][1]).toEqual({ response_text: 'Edited answer.', turn_number: 1 });
    });

    describe('when an earlier answer to the same question is already saved', () => {
      // Question generation failed after the answer was saved: still on Q1.
      const SAVED_Q1 = { ...MOCK_SESSION.turns[0], response_text: 'Saved answer.' };
      const SAVED = { ...MOCK_SESSION, turns: [SAVED_Q1], current_question: SAVED_Q1 };
      const DIFFERENT = new client.ApiError(
        409,
        'Question 1 already has a different saved answer, so this answer was not saved.',
      );

      async function submitEdit() {
        vi.spyOn(client, 'getActiveLiveInterview').mockResolvedValue(SAVED);
        const refresh = vi.spyOn(client, 'getLiveConversation').mockResolvedValue(SAVED);
        const next = vi.spyOn(client, 'nextLiveQuestion').mockRejectedValueOnce(DIFFERENT);
        renderPage();
        await screen.findByTestId('current-question');
        await userEvent.clear(answerBox());
        await userEvent.type(answerBox(), 'Edited answer.');
        await userEvent.click(screen.getByText('Next Question →'));
        await screen.findByText(/earlier answer to this question was already saved/);
        return { next, refresh };
      }

      it("restores the server's saved answer, not the rejected edit", async () => {
        const { refresh } = await submitEdit();

        expect(answerBox().value).toBe('Saved answer.');
        expect(screen.getByText(/edited answer was not submitted/)).toBeTruthy();
        expect(screen.getByTestId('current-question').textContent).toBe('Tell me about yourself.');
        expect(refresh).toHaveBeenCalledWith('sess-1', 'test-token');
      });

      it('does not resubmit anything automatically', async () => {
        const { next } = await submitEdit();
        await new Promise((r) => setTimeout(r, 200));

        expect(next).toHaveBeenCalledTimes(1);
        expect(next.mock.calls[0][1]).toEqual({ response_text: 'Edited answer.', turn_number: 1 });
      });

      it('continues with the saved answer only when the candidate presses Next', async () => {
        const { next } = await submitEdit();
        next.mockResolvedValueOnce(ADVANCED);

        await userEvent.click(screen.getByText('Next Question →'));

        await waitFor(() =>
          expect(screen.getByTestId('current-question').textContent).toBe(
            'What would you do differently?',
          ),
        );
        expect(next).toHaveBeenCalledTimes(2);
        expect(next.mock.calls[1][1]).toEqual({ response_text: 'Saved answer.', turn_number: 1 });
        expect(answerBox().value).toBe('');
      });
    });

    it('shows other 409s on the same question unchanged, keeping the typed text', async () => {
      vi.spyOn(client, 'nextLiveQuestion').mockRejectedValue(
        new client.ApiError(409, 'All questions have been asked. Call end-interview to finish.'),
      );
      vi.spyOn(client, 'getLiveConversation').mockResolvedValue(MOCK_SESSION);
      await renderAtQuestion1('My answer.');

      await userEvent.click(screen.getByText('Next Question →'));

      expect(await screen.findByText('All questions have been asked. Call end-interview to finish.')).toBeTruthy();
      expect(answerBox().value).toBe('My answer.');
      expect(screen.queryByText(/already saved/)).toBeNull();
    });
  });

  describe('End Interview after a lost response', () => {
    const COMPLETED = {
      ...MOCK_SESSION,
      status: 'completed' as const,
      completed_at: '2026-06-18T10:20:00Z',
      turns: [{ ...MOCK_SESSION.turns[0], response_text: 'My saved answer.' }],
      current_question: { ...MOCK_SESSION.turns[0], response_text: 'My saved answer.' },
    };
    const ALREADY_COMPLETED = new client.ApiError(409, 'Interview session is already completed');

    async function renderInterview() {
      vi.spyOn(client, 'getActiveLiveInterview').mockResolvedValue(MOCK_SESSION);
      const spies = {
        start: vi.spyOn(client, 'startLiveInterview'),
        next: vi.spyOn(client, 'nextLiveQuestion'),
        end: vi.spyOn(client, 'endLiveInterview'),
        conversation: vi.spyOn(client, 'getLiveConversation'),
      };
      renderPage();
      await screen.findByTestId('current-question');
      return spies;
    }

    const clickEnd = () => userEvent.click(screen.getAllByText('End Interview')[0]);

    it('a normal End shows the summary without any recovery read', async () => {
      const { end, conversation } = await renderInterview();
      end.mockResolvedValue({
        session_id: 'sess-1',
        status: 'completed',
        total_turns: 1,
        summary: 'Great performance overall!',
        turns: MOCK_SESSION.turns,
      });

      await clickEnd();

      expect(await screen.findByText('Great performance overall!')).toBeTruthy();
      expect(conversation).not.toHaveBeenCalled();
    });

    it('recovers the completed interview when End returns already-completed', async () => {
      const { start, next, end, conversation } = await renderInterview();
      end.mockRejectedValue(ALREADY_COMPLETED);
      conversation.mockResolvedValue(COMPLETED);

      await clickEnd();

      expect(await screen.findByText('Interview Complete')).toBeTruthy();
      expect(screen.getByText(/completed and saved/)).toBeTruthy();
      expect(screen.getByText('My saved answer.')).toBeTruthy();
      expect(screen.getByRole('button', { name: 'View Sessions' })).toBeTruthy();
      expect(screen.queryByRole('alert')).toBeNull();
      expect(end).toHaveBeenCalledTimes(1);
      expect(conversation).toHaveBeenCalledTimes(1);
      expect(conversation).toHaveBeenCalledWith('sess-1', 'test-token');
      expect(start).not.toHaveBeenCalled();
      expect(next).not.toHaveBeenCalled();
    });

    it('shows the 409 normally when the interview is not actually completed', async () => {
      const { end, conversation } = await renderInterview();
      end.mockRejectedValue(new client.ApiError(409, 'Some other conflict'));
      conversation.mockResolvedValue(MOCK_SESSION);

      await clickEnd();

      expect(await screen.findByText('Some other conflict')).toBeTruthy();
      expect(screen.getByTestId('current-question')).toBeTruthy();
      expect(screen.queryByText('Interview Complete')).toBeNull();
    });

    it('shows the original error when the recovery read itself fails', async () => {
      const { end, conversation } = await renderInterview();
      end.mockRejectedValue(ALREADY_COMPLETED);
      conversation.mockRejectedValue(new client.ApiError(0, 'Cannot connect to the backend.'));

      await clickEnd();

      expect(await screen.findByText('Interview session is already completed')).toBeTruthy();
      expect(screen.getByTestId('current-question')).toBeTruthy();
    });

    it('does not attempt recovery for non-409 errors', async () => {
      const { end, conversation } = await renderInterview();
      end.mockRejectedValue(new client.ApiError(502, 'The AI service is temporarily unavailable.'));

      await clickEnd();

      expect(await screen.findByText('The AI service is temporarily unavailable.')).toBeTruthy();
      expect(conversation).not.toHaveBeenCalled();
      expect(screen.getByTestId('current-question')).toBeTruthy();
    });

    describe('when a different final answer is already saved', () => {
      // Summary generation failed after the final answer was saved: still active.
      const SAVED_Q = { ...MOCK_SESSION.turns[0], response_text: 'Saved final answer.' };
      const SAVED = { ...MOCK_SESSION, turns: [SAVED_Q], current_question: SAVED_Q };
      const DIFFERENT = new client.ApiError(
        409,
        'Question 1 already has a different saved answer, so this answer was not saved.',
      );
      const answerBox = () => screen.getByLabelText('Your answer') as HTMLTextAreaElement;

      async function endWithEdit() {
        vi.spyOn(client, 'getActiveLiveInterview').mockResolvedValue(SAVED);
        const spies = {
          start: vi.spyOn(client, 'startLiveInterview'),
          next: vi.spyOn(client, 'nextLiveQuestion'),
          end: vi.spyOn(client, 'endLiveInterview').mockRejectedValueOnce(DIFFERENT),
          conversation: vi.spyOn(client, 'getLiveConversation').mockResolvedValue(SAVED),
        };
        renderPage();
        await screen.findByTestId('current-question');
        await userEvent.clear(answerBox());
        await userEvent.type(answerBox(), 'Edited final.');
        await clickEnd();
        await screen.findByText(/earlier final answer was already saved/);
        return spies;
      }

      it("restores the server's saved final answer, not the rejected edit", async () => {
        const { conversation, start, next } = await endWithEdit();

        expect(answerBox().value).toBe('Saved final answer.');
        expect(screen.getByText(/edited answer was not submitted/)).toBeTruthy();
        expect(screen.getByTestId('current-question')).toBeTruthy();
        expect(screen.queryByText('Interview Complete')).toBeNull();
        expect(conversation).toHaveBeenCalledWith('sess-1', 'test-token');
        expect(start).not.toHaveBeenCalled();
        expect(next).not.toHaveBeenCalled();
      });

      it('does not call End again automatically', async () => {
        const { end } = await endWithEdit();
        await new Promise((r) => setTimeout(r, 200));

        expect(end).toHaveBeenCalledTimes(1);
        expect(end).toHaveBeenCalledWith('sess-1', 'test-token', { response_text: 'Edited final.' });
      });

      it('ending again with the restored answer completes normally', async () => {
        const { end } = await endWithEdit();
        end.mockResolvedValueOnce({
          session_id: 'sess-1',
          status: 'completed',
          total_turns: 1,
          summary: 'Great performance overall!',
          turns: SAVED.turns,
        });

        await clickEnd();

        expect(await screen.findByText('Great performance overall!')).toBeTruthy();
        expect(end).toHaveBeenCalledTimes(2);
        expect(end.mock.calls[1][2]).toEqual({ response_text: 'Saved final answer.' });
      });

      it('keeps the existing error when the saved answer is audio-only', async () => {
        const AUDIO_Q = { ...MOCK_SESSION.turns[0], audio_response_id: 'audio-1' };
        vi.spyOn(client, 'getActiveLiveInterview').mockResolvedValue(MOCK_SESSION);
        vi.spyOn(client, 'endLiveInterview').mockRejectedValue(DIFFERENT);
        vi.spyOn(client, 'getLiveConversation').mockResolvedValue({
          ...MOCK_SESSION,
          turns: [AUDIO_Q],
          current_question: AUDIO_Q,
        });
        renderPage();
        await screen.findByTestId('current-question');
        await userEvent.type(answerBox(), 'Typed answer.');

        await clickEnd();

        expect(await screen.findByText(DIFFERENT.message)).toBeTruthy();
        expect(answerBox().value).toBe('Typed answer.');
      });
    });
  });

  describe('interview timer', () => {
    // Exact clock control; setTimeout stays real for Testing Library.
    beforeEach(() => {
      vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
      vi.setSystemTime(new Date('2026-06-18T10:12:30Z'));
    });
    afterEach(() => vi.useRealTimers());

    const timer = () => screen.getByLabelText(/Elapsed time/).textContent;

    async function resumeStartedAt(created_at: string) {
      vi.spyOn(client, 'getActiveLiveInterview').mockResolvedValue({ ...MOCK_SESSION, created_at });
      renderPage();
      await screen.findByText(/Resumed your interview in progress/);
    }

    it('a resumed interview counts from the server start time, then keeps ticking', async () => {
      await resumeStartedAt('2026-06-18T10:00:00Z');
      expect(timer()).toBe('12:30');

      await act(() => vi.advanceTimersByTimeAsync(2000));
      expect(timer()).toBe('12:32');
    });

    it.each([
      ['an explicit offset', '2026-06-18T12:00:00+02:00', '12:30'],
      ['no zone suffix, read as UTC', '2026-06-18T10:00:00', '12:30'],
      // 0.123s later than 10:00:00, so whole seconds floor to 12:29.
      ['microseconds and a +00:00 offset', '2026-06-18T10:00:00.123456+00:00', '12:29'],
    ])('parses a start time with %s', async (_label, created_at, expected) => {
      await resumeStartedAt(created_at);
      expect(timer()).toBe(expected);
    });

    it('never goes negative when the server clock is ahead', async () => {
      await resumeStartedAt('2026-06-18T10:13:00Z'); // 30s in the client's future
      expect(timer()).toBe('00:00');

      await act(() => vi.advanceTimersByTimeAsync(1000));
      expect(timer()).toBe('00:01');
    });

    it('falls back to 00:00 for an unparsable start time', async () => {
      await resumeStartedAt('not a timestamp');
      expect(timer()).toBe('00:00');
    });

    it('a newly started interview still starts at 00:00', async () => {
      // created_at is irrelevant here: a fresh start is timed from the click.
      vi.spyOn(client, 'startLiveInterview').mockResolvedValue({
        ...MOCK_SESSION,
        created_at: '2026-06-18T09:00:00Z',
      });
      await renderSetup();
      await userEvent.type(screen.getByLabelText('Target Role'), 'Engineer');
      await userEvent.type(
        screen.getByLabelText('Job Description'),
        'A Python backend engineering role with FastAPI.',
      );
      await userEvent.click(screen.getByText('Start Interview'));
      await screen.findByTestId('current-question');
      expect(timer()).toBe('00:00');

      await act(() => vi.advanceTimersByTimeAsync(3000));
      expect(timer()).toBe('00:03');
    });

    it('stops counting once the interview has ended', async () => {
      vi.spyOn(client, 'endLiveInterview').mockResolvedValue({
        session_id: 'sess-1',
        status: 'completed',
        total_turns: 1,
        summary: 'Great performance overall!',
        turns: MOCK_SESSION.turns,
      });
      await resumeStartedAt('2026-06-18T10:12:10Z'); // 20s ago
      await userEvent.click(screen.getAllByText('End Interview')[0]);
      await screen.findByText('Interview Complete');
      expect(screen.getByText('20s')).toBeTruthy();

      await act(() => vi.advanceTimersByTimeAsync(120_000));
      expect(screen.getByText('20s')).toBeTruthy();
    });
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
