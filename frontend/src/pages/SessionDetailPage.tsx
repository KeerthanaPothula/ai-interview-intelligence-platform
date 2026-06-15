import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { ApiError, generateQuestions, getSession, listResponses } from '../api/client';
import { QuestionCard } from '../components/QuestionCard';
import { useAuth } from '../context/AuthContext';
import type { AudioResponseResponse, SessionDetailResponse } from '../api/types';

export function SessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const { token } = useAuth();

  const [session, setSession] = useState<SessionDetailResponse | null>(null);
  const [responses, setResponses] = useState<AudioResponseResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !sessionId) return;

    setLoading(true);
    Promise.all([getSession(sessionId, token), listResponses(sessionId, token)])
      .then(([sessionData, responseData]) => {
        setSession(sessionData);
        setResponses(responseData);
      })
      .catch(() => setLoadError('Unable to load this interview session right now.'))
      .finally(() => setLoading(false));
  }, [token, sessionId]);

  async function handleGenerateQuestions() {
    if (!token || !sessionId) return;

    setGenerating(true);
    setGenerateError(null);
    try {
      const questions = await generateQuestions(sessionId, token);
      setSession((prev) => (prev ? { ...prev, questions } : prev));
    } catch (err) {
      setGenerateError(
        err instanceof ApiError
          ? err.message
          : 'Unable to generate questions right now. Please try again.',
      );
    } finally {
      setGenerating(false);
    }
  }

  function handleUploaded(response: AudioResponseResponse) {
    setResponses((prev) => [response, ...prev]);
  }

  if (loading) return <p>Loading session…</p>;
  if (loadError) return <p className="status-error-text">{loadError}</p>;
  if (!session) return null;

  return (
    <div className="session-detail-page">
      <header className="session-detail-header">
        <h1>{session.title}</h1>
        <p className="session-job-role">{session.job_role}</p>
        <p className="session-job-description">{session.job_description}</p>
        <span className={`session-status status-${session.status}`}>{session.status}</span>
      </header>

      {session.questions.length === 0 ? (
        <section className="generate-questions">
          <p>No questions yet for this session.</p>
          <button type="button" onClick={handleGenerateQuestions} disabled={generating}>
            {generating ? 'Generating…' : 'Generate Questions'}
          </button>
          {generateError && <p className="status-error-text">{generateError}</p>}
        </section>
      ) : (
        <section className="questions-list">
          {session.questions.map((question) => (
            <QuestionCard
              key={question.id}
              question={question}
              sessionId={session.id}
              responses={responses.filter((response) => response.question_id === question.id)}
              onUploaded={handleUploaded}
            />
          ))}
        </section>
      )}
    </div>
  );
}
