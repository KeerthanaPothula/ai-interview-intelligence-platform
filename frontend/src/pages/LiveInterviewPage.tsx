import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
  endLiveInterview,
  nextLiveQuestion,
  startLiveInterview,
} from '../api/client';
import type {
  EndInterviewResponse,
  LiveInterviewSessionResponse,
} from '../api/types';
import { useAuth } from '../context/AuthContext';

const ease = [0.4, 0, 0.2, 1] as [number, number, number, number];

const DIFFICULTY_LABELS = ['', 'Warm-up', 'Moderate', 'Intermediate', 'Challenging', 'Advanced'];
const DIFFICULTY_COLORS = ['', '#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#7c3aed'];

function DifficultyBadge({ level }: { level: number }) {
  return (
    <span
      className="difficulty-badge"
      style={{ backgroundColor: DIFFICULTY_COLORS[level] ?? '#6b7280' }}
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

type PageState = 'setup' | 'interviewing' | 'ended';

export function LiveInterviewPage() {
  const { token } = useAuth();
  const navigate = useNavigate();

  const [pageState, setPageState] = useState<PageState>('setup');
  const [jobRole, setJobRole] = useState('');
  const [jobDescription, setJobDescription] = useState('');
  const [maxTurns, setMaxTurns] = useState(5);
  const [session, setSession] = useState<LiveInterviewSessionResponse | null>(null);
  const [result, setResult] = useState<EndInterviewResponse | null>(null);
  const [responseText, setResponseText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsedSecs, setElapsedSecs] = useState(0);

  const responseRef = useRef<HTMLTextAreaElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const currentQuestion = session?.current_question ?? null;
  const previousTurns = session ? session.turns.slice(0, -1) : [];
  const atLastTurn = session != null && session.current_turn >= session.max_turns;
  const wordCount = responseText.trim() ? responseText.trim().split(/\s+/).length : 0;

  const startTimer = useCallback(() => {
    setElapsedSecs(0);
    timerRef.current = setInterval(() => setElapsedSecs((s) => s + 1), 1000);
  }, []);

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => () => stopTimer(), [stopTimer]);

  const handleStart = async () => {
    if (!token) return;
    if (!jobRole.trim() || jobDescription.trim().length < 20) {
      setError('Please fill in the job role and a description of at least 20 characters.');
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
    } catch {
      setError('Failed to start the interview. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleNext = async () => {
    if (!token || !session) return;
    setLoading(true);
    setError(null);
    try {
      const updated = await nextLiveQuestion(
        session.id,
        { response_text: responseText || undefined },
        token,
      );
      setSession(updated);
      setResponseText('');
      setTimeout(() => responseRef.current?.focus(), 80);
    } catch {
      setError('Failed to get next question. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleEnd = async () => {
    if (!token || !session) return;
    setLoading(true);
    setError(null);
    stopTimer();
    try {
      const endResult = await endLiveInterview(session.id, token);
      setResult(endResult);
      setPageState('ended');
    } catch {
      setError('Failed to end the interview. Please try again.');
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
  };

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
              <label>Number of Questions</label>
              <div className="li-turn-options">
                {TURN_OPTIONS.map((n) => (
                  <button
                    key={n}
                    type="button"
                    className={`li-turn-opt${maxTurns === n ? ' selected' : ''}`}
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
          <main className="li-center" id="main-content">
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
          </main>

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
