import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
  ApiError,
  endLiveInterview,
  getActiveLiveInterview,
  getLiveConversation,
  nextLiveQuestion,
  startLiveInterview,
} from '../api/client';
import type {
  EndInterviewResponse,
  LiveInterviewSessionResponse,
} from '../api/types';
import { ErrorState } from '../components/StateMessage';
import { useAuth } from '../context/AuthContext';

const ease = [0.4, 0, 0.2, 1] as [number, number, number, number];

const DIFFICULTY_LABELS = ['', 'Warm-up', 'Moderate', 'Intermediate', 'Challenging', 'Advanced'];
const DIFFICULTY_COLORS = ['', 'var(--diff-1)', 'var(--diff-2)', 'var(--diff-3)', 'var(--diff-4)', 'var(--diff-5)'];

function DifficultyBadge({ level }: { level: number }) {
  return (
    <span
      className="difficulty-badge"
      style={{ backgroundColor: DIFFICULTY_COLORS[level] ?? 'var(--muted)' }}
    >
      {DIFFICULTY_LABELS[level] ?? `Level ${level}`}
    </span>
  );
}

function formatTime(secs: number) {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// Whole seconds since a server timestamp. Server times are UTC, so one with
// no zone suffix (SQLite returns those) must not be read as local time.
// Never negative: a client clock running behind the server clamps to 0.
function secondsSince(iso: string) {
  const ms = Date.parse(/(Z|[+-]\d\d:?\d\d)$/i.test(iso) ? iso : `${iso}Z`);
  return Number.isNaN(ms) ? 0 : Math.max(0, Math.floor((Date.now() - ms) / 1000));
}

type PageState = 'checking' | 'resumeError' | 'setup' | 'interviewing' | 'ended';

export function LiveInterviewPage() {
  const { token } = useAuth();
  const navigate = useNavigate();

  const [pageState, setPageState] = useState<PageState>('checking');
  const [jobRole, setJobRole] = useState('');
  const [jobDescription, setJobDescription] = useState('');
  const [maxTurns, setMaxTurns] = useState(5);
  const [session, setSession] = useState<LiveInterviewSessionResponse | null>(null);
  const [result, setResult] = useState<EndInterviewResponse | null>(null);
  const [responseText, setResponseText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsedSecs, setElapsedSecs] = useState(0);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [resumed, setResumed] = useState(false);
  const resumeCheckedRef = useRef(false);

  const responseRef = useRef<HTMLTextAreaElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const currentQuestion = session?.current_question ?? null;
  const previousTurns = session ? session.turns.slice(0, -1) : [];
  const atLastTurn = session != null && session.current_turn >= session.max_turns;
  const wordCount = responseText.trim() ? responseText.trim().split(/\s+/).length : 0;

  const startTimer = useCallback((fromSecs = 0) => {
    setElapsedSecs(fromSecs);
    timerRef.current = setInterval(() => setElapsedSecs((s) => s + 1), 1000);
  }, []);

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => () => stopTimer(), [stopTimer]);

  // Resume an interview still in progress (after a refresh or navigating
  // away) instead of showing the setup form and silently starting a new one.
  // Read-only on the backend: no turns are created, nothing is completed.
  const checkForActive = useCallback(async () => {
    if (!token) return;
    setPageState('checking');
    setResumeError(null);
    try {
      const active = await getActiveLiveInterview(token);
      if (!active) {
        setPageState('setup');
        return;
      }
      setSession(active);
      setJobRole(active.job_role);
      setJobDescription(active.job_description);
      // An answer saved before a failed next-question stays on the current turn.
      setResponseText(active.current_question?.response_text ?? '');
      setResumed(true);
      setPageState('interviewing');
      // Count from when the interview really started, not from this resume.
      startTimer(secondsSince(active.created_at));
    } catch (err) {
      setResumeError(err instanceof ApiError ? err.message : 'Something went wrong.');
      setPageState('resumeError');
    }
  }, [token, startTimer]);

  // Once per mount: a later silent token refresh changes `token`, and must not
  // re-restore over what the candidate is typing.
  useEffect(() => {
    if (resumeCheckedRef.current || !token) return;
    resumeCheckedRef.current = true;
    checkForActive();
  }, [token, checkForActive]);

  // Warn before a refresh / tab close while an interview is in progress.
  // Removed as soon as it ends (or the page unmounts).
  useEffect(() => {
    if (pageState !== 'interviewing') return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = ''; // required by older Chromium to show the prompt
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [pageState]);

  const handleStart = async () => {
    if (!token) return;
    // Mirrors StartLiveInterviewRequest: job_role min 2, job_description min 20.
    if (jobRole.trim().length < 2 || jobDescription.trim().length < 20) {
      setError('Please enter a job role (at least 2 characters) and a description of at least 20 characters.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const s = await startLiveInterview(
        { job_role: jobRole, job_description: jobDescription, max_turns: maxTurns },
        token,
      );
      setSession(s);
      setPageState('interviewing');
      startTimer();
      setTimeout(() => responseRef.current?.focus(), 100);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to start the interview. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleNext = async () => {
    if (!token || !session || !currentQuestion) return;
    const turnNumber = currentQuestion.turn_number;
    setLoading(true);
    setError(null);
    try {
      const updated = await nextLiveQuestion(
        session.id,
        { response_text: responseText || undefined, turn_number: turnNumber },
        token,
      );
      setSession(updated);
      setResponseText('');
      setTimeout(() => responseRef.current?.focus(), 80);
    } catch (err) {
      if (!(err instanceof ApiError)) {
        setError('Failed to get next question. Please try again.');
      } else if (err.status !== 409) {
        setError(err.message);
      } else {
        // The server already moved past this question (e.g. an earlier
        // attempt succeeded but its response was lost). Show the real
        // state, and keep the unsent text in the box — never resubmit it.
        let moved = false;
        try {
          const fresh = await getLiveConversation(session.id, token);
          setSession(fresh);
          moved = fresh.current_question?.turn_number !== turnNumber;
        } catch {
          // Keep the current view; the error below still explains.
        }
        setError(
          moved
            ? `${err.message} The interview has moved on to the question shown; your text below was not submitted, so review it before answering.`
            : err.message,
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const handleEnd = async () => {
    if (!token || !session) return;
    setLoading(true);
    setError(null);
    try {
      // Submits whatever the candidate typed for the current (possibly
      // final) question — next-question is hidden once atLastTurn is
      // true, so this is the only chance to record that answer.
      const endResult = await endLiveInterview(session.id, token, {
        response_text: responseText || undefined,
      });
      stopTimer();
      setResult(endResult);
      setPageState('ended');
    } catch (err) {
      // A 409 can mean an earlier End succeeded but its response was lost.
      // Recover read-only, and only if the server confirms completion.
      const fresh =
        err instanceof ApiError && err.status === 409
          ? await getLiveConversation(session.id, token).catch(() => null)
          : null;
      if (fresh?.status === 'completed') {
        stopTimer();
        setResult({
          session_id: fresh.id,
          status: fresh.status,
          total_turns: fresh.turns.length,
          // The AI summary is only returned by End itself and is not stored.
          summary: 'Your interview was completed and saved. Its summary could not be shown because the connection dropped.',
          turns: fresh.turns,
        });
        setPageState('ended');
      } else {
        setError(err instanceof ApiError ? err.message : 'Failed to end the interview. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      if (!loading) {
        if (atLastTurn) handleEnd();
        else handleNext();
      }
    }
  };

  const handleReset = () => {
    stopTimer();
    setElapsedSecs(0);
    setPageState('setup');
    setSession(null);
    setResult(null);
    setResponseText('');
    setJobRole('');
    setJobDescription('');
    setError(null);
    setResumed(false);
  };

  if (pageState === 'checking') {
    return (
      <div className="page-container live-interview-page">
        <p className="li-thinking" role="status">Checking for an interview in progress…</p>
      </div>
    );
  }

  if (pageState === 'resumeError') {
    return (
      <div className="page-container live-interview-page">
        <ErrorState
          message={`We couldn't check for an interview in progress, so nothing was started or discarded. ${resumeError}`}
          onRetry={checkForActive}
        />
      </div>
    );
  }

  /* ── SETUP ── */
  if (pageState === 'setup') {
    const TURN_OPTIONS = [3, 5, 7, 10];
    return (
      <div className="page-container live-interview-page">
        <div className="li-setup">
          <div className="li-setup-header">
            <div className="li-setup-icon" aria-hidden="true">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
            <h1 className="li-setup-title">Live AI Interview</h1>
            <p className="li-setup-sub">
              Practice with an adaptive AI interviewer that responds to your answers in real time.
            </p>
          </div>

          <div className="li-setup-card">
            <div className="form-group">
              <label htmlFor="job-role">Target Role</label>
              <input
                id="job-role"
                type="text"
                placeholder="e.g. Software Engineer, Product Manager"
                value={jobRole}
                onChange={(e) => setJobRole(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label htmlFor="job-desc">Job Description</label>
              <textarea
                id="job-desc"
                rows={4}
                placeholder="Paste the job description here (at least 20 characters)…"
                value={jobDescription}
                onChange={(e) => setJobDescription(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label id="turn-count-label">Number of Questions</label>
              <div className="li-turn-options" role="group" aria-labelledby="turn-count-label">
                {TURN_OPTIONS.map((n) => (
                  <button
                    key={n}
                    type="button"
                    className={`li-turn-opt${maxTurns === n ? ' selected' : ''}`}
                    aria-pressed={maxTurns === n}
                    onClick={() => setMaxTurns(n)}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>

            {error && (
              <p className="error-message" role="alert">{error}</p>
            )}

            <button
              type="button"
              className="btn btn-primary"
              onClick={handleStart}
              disabled={loading}
            >
              {loading ? 'Starting…' : 'Start Interview'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  /* ── ENDED ── */
  if (pageState === 'ended' && result) {
    const totalMins = Math.round(elapsedSecs / 60);
    return (
      <div className="page-container live-interview-page">
        <motion.div
          className="li-ended"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease }}
        >
          <div className="li-summary-hero">
            <div className="li-summary-emoji">🎯</div>
            <h1 className="li-summary-title">Interview Complete</h1>
            <p className="li-summary-text">{result.summary}</p>
            <div className="li-stats-row-summary">
              <div className="li-stat-pill">
                <span className="li-stat-pill-val">{result.total_turns}</span>
                <span className="li-stat-pill-key">Questions</span>
              </div>
              <div className="li-stat-pill">
                <span className="li-stat-pill-val">{totalMins > 0 ? `${totalMins}m` : `${elapsedSecs}s`}</span>
                <span className="li-stat-pill-key">Duration</span>
              </div>
              <div className="li-stat-pill">
                <span className="li-stat-pill-val">{jobRole || 'Custom'}</span>
                <span className="li-stat-pill-key">Role</span>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
            <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Conversation Review</h2>
            <span style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>{result.turns.length} question{result.turns.length !== 1 ? 's' : ''}</span>
          </div>

          <div className="li-turn-timeline">
            {result.turns.map((t, i) => (
              <motion.div
                key={t.id}
                className="li-turn-card"
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.28, delay: i * 0.06, ease }}
              >
                <div className="li-tc-num">
                  <span>Q{t.turn_number}</span>
                  <DifficultyBadge level={t.difficulty_level} />
                </div>
                <p className="li-tc-q">{t.question_text}</p>
                {t.response_text ? (
                  <>
                    <div className="li-tc-a-label">Your Answer</div>
                    <p className="li-tc-a">{t.response_text}</p>
                  </>
                ) : (
                  <p className="li-tc-no-answer">No answer recorded.</p>
                )}
              </motion.div>
            ))}
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <button type="button" className="btn btn-secondary" onClick={handleReset}>
              New Interview
            </button>
            <button type="button" className="btn btn-primary" onClick={() => navigate('/sessions')}>
              View Sessions
            </button>
          </div>
        </motion.div>
      </div>
    );
  }

  /* ── INTERVIEWING — 3-column workspace ── */
  const totalTurns = session?.max_turns ?? maxTurns;
  const currentTurn = session?.current_turn ?? 1;

  return (
    <div className="page-container live-interview-page">
      <div className="li-workspace">
        {resumed && (
          <p
            role="status"
            style={{
              margin: 0,
              padding: '0.6rem 0.875rem',
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.84rem',
              color: 'var(--text-2)',
            }}
          >
            Resumed your interview in progress. Your earlier answers are saved.
          </p>
        )}
        {/* Top bar: progress dots + timer + end button */}
        <div className="li-topbar-row">
          <div className="li-progress-dots" role="progressbar" aria-valuenow={currentTurn} aria-valuemax={totalTurns} aria-label={`Question ${currentTurn} of ${totalTurns}`}>
            {Array.from({ length: totalTurns }, (_, i) => (
              <div
                key={i}
                className={`li-dot${i < currentTurn - 1 ? ' done' : i === currentTurn - 1 ? ' current' : ''}`}
                aria-hidden="true"
              />
            ))}
          </div>
          <span style={{ flex: 1 }} />
          <span className="li-timer" aria-label={`Elapsed time: ${formatTime(elapsedSecs)}`}>
            {formatTime(elapsedSecs)}
          </span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={handleEnd}
            disabled={loading}
            style={{ color: 'var(--error-text)', borderColor: 'var(--error)' }}
          >
            End Interview
          </button>
        </div>

        {/* Three columns */}
        <div className="li-columns">
          {/* LEFT — current question brief + history */}
          <aside className="li-left" aria-label="Question overview">
            {currentQuestion && (
              <div className="li-question-panel">
                <div className="li-question-num">
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor" aria-hidden="true"><circle cx="5" cy="5" r="5"/></svg>
                  Question {currentQuestion.turn_number} of {totalTurns}
                </div>
                <div className="li-badge-row">
                  <DifficultyBadge level={currentQuestion.difficulty_level} />
                </div>
                <p className="li-question-preview">{currentQuestion.question_text}</p>
              </div>
            )}

            {previousTurns.length > 0 && (
              <div className="li-history-panel" aria-label="Previous questions">
                <div className="li-history-header">Previous</div>
                {previousTurns.map((t) => (
                  <div key={t.id} className="li-history-entry">
                    <p className="li-he-q">{t.question_text}</p>
                    {t.response_text && (
                      <p className="li-he-a">{t.response_text}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </aside>

          {/* CENTER — question + response */}
          <section className="li-center" aria-label="Current question">
            <AnimatePresence mode="wait">
              {currentQuestion && (
                <motion.div
                  key={currentQuestion.turn_number}
                  className="li-question-body"
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.28, ease }}
                >
                  <div className="li-q-meta">
                    <span className="li-q-pulse" aria-hidden="true" />
                    AI is ready
                  </div>
                  <p className="li-q-text" data-testid="current-question">
                    {currentQuestion.question_text}
                  </p>
                </motion.div>
              )}
            </AnimatePresence>

            {loading && !session && (
              <div className="li-thinking" aria-live="polite">
                <div className="li-thinking-dots" aria-hidden="true">
                  <div className="li-thinking-dot" />
                  <div className="li-thinking-dot" />
                  <div className="li-thinking-dot" />
                </div>
                Generating next question…
              </div>
            )}

            <div className="li-response-box">
              <div className="li-response-label">Your Answer</div>
              <textarea
                ref={responseRef}
                className="li-response-ta"
                placeholder="Type your answer here… (Ctrl+Enter to submit)"
                value={responseText}
                onChange={(e) => setResponseText(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={loading}
                aria-label="Your answer"
                rows={7}
              />
              <div className="li-response-footer">
                <span>{wordCount} word{wordCount !== 1 ? 's' : ''}</span>
                <span>
                  <kbd className="li-kbd">Ctrl</kbd>+<kbd className="li-kbd">Enter</kbd> to submit
                </span>
              </div>
            </div>

            {error && (
              <p className="error-message" role="alert">{error}</p>
            )}

            <div className="li-actions-row">
              {!atLastTurn ? (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleNext}
                  disabled={loading}
                >
                  {loading ? 'Generating…' : 'Next Question →'}
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-success"
                  onClick={handleEnd}
                  disabled={loading}
                >
                  {loading ? 'Finishing…' : 'Finish Interview'}
                </button>
              )}
              {!atLastTurn && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={handleNext}
                  disabled={loading || !!responseText}
                  aria-label="Skip this question"
                >
                  Skip
                </button>
              )}
            </div>
          </section>

          {/* RIGHT — live stats */}
          <aside className="li-right" aria-label="Session statistics">
            <div className="li-panel">
              <div className="li-panel-hd">Session Progress</div>
              <div className="li-stat-row">
                <span className="li-stat-k">Current Question</span>
                <span className="li-stat-v">{currentTurn} / {totalTurns}</span>
              </div>
              <div className="li-stat-row">
                <span className="li-stat-k">Answered</span>
                <span className="li-stat-v">{previousTurns.length}</span>
              </div>
              <div className="li-stat-row">
                <span className="li-stat-k">Remaining</span>
                <span className="li-stat-v">{totalTurns - currentTurn}</span>
              </div>
              <div className="li-stat-row">
                <span className="li-stat-k">Elapsed</span>
                <span className="li-stat-v">{formatTime(elapsedSecs)}</span>
              </div>
              <div className="li-stat-row">
                <span className="li-stat-k">Current Words</span>
                <span className="li-stat-v">{wordCount}</span>
              </div>
            </div>

            <div className="li-panel">
              <div className="li-panel-hd">Tips</div>
              <div className="li-tip-item">
                <div className="li-tip-dot" aria-hidden="true" />
                Structure answers with situation, action, and result.
              </div>
              <div className="li-tip-item">
                <div className="li-tip-dot" aria-hidden="true" />
                Aim for 100–200 words per answer for depth without rambling.
              </div>
              <div className="li-tip-item">
                <div className="li-tip-dot" aria-hidden="true" />
                Use specific examples from past experience.
              </div>
            </div>

            <div className="li-panel">
              <div className="li-panel-hd">Shortcuts</div>
              <div className="li-shortcut-row">
                <span>Submit answer</span>
                <span><kbd className="li-kbd">Ctrl</kbd>+<kbd className="li-kbd">↵</kbd></span>
              </div>
              <div className="li-shortcut-row">
                <span>Role</span>
                <span style={{ color: 'var(--text-2)', fontSize: '0.75rem', maxWidth: '100px', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{jobRole || '—'}</span>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
