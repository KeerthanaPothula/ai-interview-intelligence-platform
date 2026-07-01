import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ApiError, createSession, listSessions } from '../api/client';
import { ResumeUploadCard } from '../components/ResumeUploadCard';
import { SessionCard } from '../components/SessionCard';
import { SessionListSkeleton } from '../components/Skeleton';
import { EmptyState, ErrorState } from '../components/StateMessage';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import type { SessionListResponse } from '../api/types';

export function SessionsListPage() {
  const { token } = useAuth();
  const { showToast } = useToast();
  const [sessions, setSessions] = useState<SessionListResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [title, setTitle] = useState('');
  const [jobRole, setJobRole] = useState('');
  const [jobDescription, setJobDescription] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const loadSessions = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setLoadError(null);
    listSessions(token)
      .then(setSessions)
      .catch(() => setLoadError('Unable to load your interview sessions right now.'))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard data-fetching pattern
    loadSessions();
  }, [loadSessions]);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!token) return;

    setCreateError(null);
    setCreating(true);
    try {
      const session = await createSession(
        { title, job_role: jobRole, job_description: jobDescription },
        token,
      );
      setSessions((prev) => [
        {
          id: session.id,
          title: session.title,
          job_role: session.job_role,
          status: session.status,
          created_at: session.created_at,
          updated_at: session.updated_at,
        },
        ...prev,
      ]);
      setTitle('');
      setJobRole('');
      setJobDescription('');
      showToast('Session created.', 'success');
    } catch (err) {
      setCreateError(
        err instanceof ApiError ? err.message : 'Unable to create the session. Please try again.',
      );
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="sessions-page">
      <ResumeUploadCard />

      <section className="create-session">
        <h2>New Interview Session</h2>
        <form onSubmit={handleCreate}>
          <label>
            Title
            <input value={title} onChange={(event) => setTitle(event.target.value)} required />
          </label>
          <label>
            Job role
            <input value={jobRole} onChange={(event) => setJobRole(event.target.value)} required />
          </label>
          <label>
            Job description
            <textarea
              value={jobDescription}
              onChange={(event) => setJobDescription(event.target.value)}
              required
              minLength={20}
              rows={4}
            />
            <span className="field-hint">At least 20 characters — used to generate interview questions.</span>
          </label>
          {createError && (
            <p className="status-error-text" role="alert">
              {createError}
            </p>
          )}
          <button type="submit" disabled={creating}>
            {creating ? 'Creating…' : 'Create Session'}
          </button>
        </form>
      </section>

      <section className="sessions-list">
        <h2>Your Sessions</h2>
        {loading && <SessionListSkeleton />}
        {!loading && loadError && <ErrorState message={loadError} onRetry={loadSessions} />}
        {!loading && !loadError && sessions.length === 0 && (
          <EmptyState
            title="No interview sessions yet"
            description="Create one above to get started."
          />
        )}
        {!loading && !loadError && sessions.length > 0 && (
          <div className="session-grid">
            {sessions.map((session) => (
              <SessionCard key={session.id} session={session} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
