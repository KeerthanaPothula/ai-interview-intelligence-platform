import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  endLiveInterview,
  nextLiveQuestion,
  startLiveInterview,
} from '../api/client';
import type {
  EndInterviewResponse,
  LiveConversationTurnResponse,
  LiveInterviewSessionResponse,
} from '../api/types';
import { useAuth } from '../context/AuthContext';

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

function TurnCard({ turn }: { turn: LiveConversationTurnResponse }) {
  return (
    <div className="turn-card">
      <div className="turn-header">
        <span className="turn-number">Q{turn.turn_number}</span>
        <DifficultyBadge level={turn.difficulty_level} />
      </div>
      <p className="turn-question">{turn.question_text}</p>
      {turn.response_text && (
        <div className="turn-response">
          <strong>Your answer:</strong>
          <p>{turn.response_text}</p>
        </div>
      )}
    </div>
  );
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

  const responseRef = useRef<HTMLTextAreaElement>(null);

  const currentQuestion = session?.current_question ?? null;

  const handleStart = async () => {
    if (!token) return;
    if (!jobRole.trim() || jobDescription.trim().length < 20) {
      setError('Please fill in the job role and a description of at least 20 characters.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const s = await startLiveInterview({ job_role: jobRole, job_description: jobDescription, max_turns: maxTurns }, token);
      setSession(s);
      setPageState('interviewing');
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
      responseRef.current?.focus();
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

  const atLastTurn = session != null && session.current_turn >= session.max_turns;
  const progress = session != null ? (session.current_turn / session.max_turns) * 100 : 0;

  if (pageState === 'setup') {
    return (
      <div className="page-container live-interview-page">
        <h1>Live AI Interview</h1>
        <p className="page-subtitle">
          Practice with a conversational AI interviewer that adapts to your answers.
        </p>

        <div className="interview-setup-form">
          <div className="form-group">
            <label htmlFor="job-role">Target Job Role</label>
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
            <label htmlFor="max-turns">Number of Questions: {maxTurns}</label>
            <input
              id="max-turns"
              type="range"
              min={3}
              max={10}
              value={maxTurns}
              onChange={(e) => setMaxTurns(Number(e.target.value))}
            />
          </div>

          {error && (
            <p className="error-message" role="alert">
              {error}
            </p>
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
    );
  }

  if (pageState === 'ended' && result) {
    return (
      <div className="page-container live-interview-page">
        <h1>Interview Complete</h1>

        <div className="interview-summary-card">
          <h2>AI Summary</h2>
          <p>{result.summary}</p>
          <p className="turns-count">You answered {result.total_turns} question{result.total_turns !== 1 ? 's' : ''}.</p>
        </div>

        <h2>Conversation History</h2>
        <div className="turns-list">
          {result.turns.map((t) => (
            <TurnCard key={t.id} turn={t} />
          ))}
        </div>

        <div className="interview-end-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setPageState('setup');
              setSession(null);
              setResult(null);
              setJobRole('');
              setJobDescription('');
            }}
          >
            Start New Interview
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => navigate('/')}
          >
            Back to Sessions
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container live-interview-page">
      <div className="interview-progress">
        <span>Question {session?.current_turn ?? 1} of {session?.max_turns ?? maxTurns}</span>
        <div className="progress-bar-track">
          <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
        </div>
        <button
          type="button"
          className="btn btn-danger btn-sm"
          onClick={handleEnd}
          disabled={loading}
        >
          End Interview
        </button>
      </div>

      {currentQuestion && (
        <div className="current-question-card">
          <div className="question-meta">
            <span className="question-number">Question {currentQuestion.turn_number}</span>
            <DifficultyBadge level={currentQuestion.difficulty_level} />
          </div>
          <p className="question-text" data-testid="current-question">
            {currentQuestion.question_text}
          </p>
        </div>
      )}

      <div className="response-area">
        <label htmlFor="response-text">Your Answer</label>
        <textarea
          id="response-text"
          ref={responseRef}
          rows={5}
          placeholder="Type your answer here…"
          value={responseText}
          onChange={(e) => setResponseText(e.target.value)}
          disabled={loading}
        />
      </div>

      {error && <p className="error-message">{error}</p>}

      <div className="interview-actions">
        {!atLastTurn ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleNext}
            disabled={loading}
          >
            {loading ? 'Generating next question…' : 'Next Question →'}
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
      </div>

      {session && session.turns.length > 1 && (
        <details className="conversation-history-details">
          <summary>View conversation history ({session.turns.length - 1} previous)</summary>
          <div className="turns-list">
            {session.turns.slice(0, -1).map((t) => (
              <TurnCard key={t.id} turn={t} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
