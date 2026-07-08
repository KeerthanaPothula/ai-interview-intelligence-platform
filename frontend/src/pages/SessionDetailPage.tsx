import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { FileBarChart2 } from 'lucide-react';
import { ApiError, generateQuestions, getSession, listResponses } from '../api/client';
import { QuestionCard } from '../components/QuestionCard';
import { SessionReportCard } from '../components/SessionReportCard';
import { Skeleton } from '../components/Skeleton';
import { ErrorState } from '../components/StateMessage';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import type { AudioResponseResponse, SessionDetailResponse, SessionReportResponse } from '../api/types';

export function SessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const { token } = useAuth();
  const { showToast } = useToast();

  const [session, setSession] = useState<SessionDetailResponse | null>(null);
  const [responses, setResponses] = useState<AudioResponseResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  const [report, setReport] = useState<SessionReportResponse | null>(null);

  // Precompute once per responses change (O(R)) instead of re-filtering per
  // question on every render (O(Q×R)).
  const responsesByQuestion = useMemo(() => {
    const map = new Map<string, AudioResponseResponse[]>();
    for (const r of responses) {
      const bucket = map.get(r.question_id);
      if (bucket) {
        bucket.push(r);
      } else {
        map.set(r.question_id, [r]);
      }
    }
    return map;
  }, [responses]);

  const loadSession = useCallback(() => {
    if (!token || !sessionId) return;

    setLoading(true);
    setLoadError(null);
    Promise.all([getSession(sessionId, token), listResponses(sessionId, token)])
      .then(([sessionData, responseData]) => {
        setSession(sessionData);
        setResponses(responseData);
      })
      .catch(() => setLoadError('Unable to load this interview session right now.'))
      .finally(() => setLoading(false));
  }, [token, sessionId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard data-fetching pattern
    loadSession();
  }, [loadSession]);

  async function handleGenerateQuestions() {
    if (!token || !sessionId) return;

    setGenerating(true);
    setGenerateError(null);
    try {
      const questions = await generateQuestions(sessionId, token);
      setSession((prev) => (prev ? { ...prev, questions } : prev));
      showToast('Questions generated.', 'success');
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
    showToast('Recording uploaded.', 'success');
  }

  if (loading) {
    return (
      <div className="session-detail-page" aria-busy="true" aria-label="Loading session">
        <header className="session-detail-header">
          <Skeleton width="40%" height="1.6rem" />
          <Skeleton width="25%" height="1rem" className="skeleton-spaced" />
          <Skeleton width="60%" height="0.9rem" className="skeleton-spaced" />
        </header>
        <Skeleton width="100%" height="6rem" />
      </div>
    );
  }
  if (loadError) return <ErrorState message={loadError} onRetry={loadSession} />;
  if (!session) return null;

  return (
    <div className="session-detail-page">
      <header className="session-detail-header">
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
          <div>
            <h1>{session.title}</h1>
            <p className="session-job-role">{session.job_role}</p>
            <p className="session-job-description">{session.job_description}</p>
            <span className={`session-status status-${session.status}`}>{session.status}</span>
          </div>
          <Link
            to={`/sessions/${session.id}/report`}
            className="btn btn-ghost btn-sm"
            style={{ flexShrink: 0, alignSelf: 'flex-start', marginTop: '0.25rem' }}
          >
            <FileBarChart2 size={14} aria-hidden="true" />
            View Report
          </Link>
        </div>
      </header>

      {session.questions.length === 0 ? (
        <section className="generate-questions">
          <p>No questions yet for this session.</p>
          <button type="button" onClick={handleGenerateQuestions} disabled={generating}>
            {generating ? 'Generating…' : 'Generate Questions'}
          </button>
          {generateError && (
            <p className="status-error-text" role="alert">
              {generateError}
            </p>
          )}
        </section>
      ) : (
        <>
          <section className="questions-list">
            {session.questions.map((question) => (
              <QuestionCard
                key={question.id}
                question={question}
                sessionId={session.id}
                responses={responsesByQuestion.get(question.id) ?? []}
                onUploaded={handleUploaded}
              />
            ))}
          </section>

          <SessionReportCard sessionId={session.id} report={report} onGenerated={setReport} />
        </>
      )}
    </div>
  );
}
