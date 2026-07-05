import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Plus, RefreshCw, Search } from 'lucide-react';
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
  const [filter, setFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);

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
      setShowCreate(false);
      showToast('Interview session created.', 'success');
    } catch (err) {
      setCreateError(
        err instanceof ApiError ? err.message : 'Unable to create the session. Please try again.',
      );
    } finally {
      setCreating(false);
    }
  }

  const filtered = filter.trim()
    ? sessions.filter(
        (s) =>
          s.title.toLowerCase().includes(filter.toLowerCase()) ||
          s.job_role?.toLowerCase().includes(filter.toLowerCase()),
      )
    : sessions;

  return (
    <div className="page-container">
      {/* Page header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          flexWrap: 'wrap',
          marginBottom: '1.5rem',
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: '1.35rem' }}>Interviews</h1>
          <p style={{ margin: '0.2rem 0 0', color: 'var(--muted)', fontSize: '0.875rem' }}>
            {sessions.length > 0
              ? `${sessions.length} session${sessions.length === 1 ? '' : 's'}`
              : 'No sessions yet'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={loadSessions}
            aria-label="Refresh sessions"
          >
            <RefreshCw size={14} aria-hidden="true" />
          </button>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => setShowCreate((v) => !v)}
            aria-expanded={showCreate}
          >
            <Plus size={14} aria-hidden="true" />
            New Interview
          </button>
        </div>
      </div>

      {/* Resume upload */}
      <ResumeUploadCard />

      {/* Create form (collapsible) */}
      {showCreate && (
        <section
          className="create-session"
          aria-label="Create new interview session"
          style={{ marginBottom: '1rem' }}
        >
          <h2 style={{ margin: '0 0 1.25rem', fontSize: '1rem' }}>New Interview Session</h2>
          <form onSubmit={handleCreate}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: '0.75rem',
                marginBottom: '0.75rem',
              }}
            >
              <label>
                Title
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Amazon SDE Prep"
                  required
                />
              </label>
              <label>
                Job role
                <input
                  value={jobRole}
                  onChange={(e) => setJobRole(e.target.value)}
                  placeholder="e.g. Software Engineer"
                  required
                />
              </label>
            </div>
            <label>
              Job description
              <textarea
                value={jobDescription}
                onChange={(e) => setJobDescription(e.target.value)}
                placeholder="Paste the job description here (at least 20 characters)…"
                required
                minLength={20}
                rows={4}
              />
              <span className="field-hint">At least 20 characters — used to generate questions.</span>
            </label>

            {createError && (
              <p
                role="alert"
                style={{
                  color: 'var(--error-text)',
                  background: 'var(--error-bg)',
                  border: '1px solid rgba(239,68,68,0.2)',
                  padding: '0.55rem 0.75rem',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.84rem',
                  margin: '0.5rem 0',
                }}
              >
                {createError}
              </p>
            )}

            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem' }}>
              <button
                type="submit"
                className="btn btn-primary btn-sm"
                disabled={creating}
                aria-busy={creating}
              >
                {creating ? (
                  <>
                    <span className="spinner" aria-hidden="true" />
                    Creating…
                  </>
                ) : (
                  'Create Session'
                )}
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setShowCreate(false)}
              >
                Cancel
              </button>
            </div>
          </form>
        </section>
      )}

      {/* Session list */}
      <section className="sessions-list" aria-label="Your interview sessions">
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '1rem',
            gap: '0.75rem',
            flexWrap: 'wrap',
          }}
        >
          <h2 style={{ margin: 0, fontSize: '1rem' }}>Your Sessions</h2>

          {sessions.length > 0 && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                padding: '0.3rem 0.65rem',
                minWidth: 200,
              }}
            >
              <Search size={13} style={{ color: 'var(--muted)', flexShrink: 0 }} aria-hidden="true" />
              <input
                type="search"
                placeholder="Filter sessions…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  padding: 0,
                  fontSize: '0.84rem',
                  color: 'var(--text)',
                  outline: 'none',
                  boxShadow: 'none',
                  width: '100%',
                }}
                aria-label="Filter sessions by title or role"
              />
            </div>
          )}
        </div>

        {loading && <SessionListSkeleton />}
        {!loading && loadError && <ErrorState message={loadError} onRetry={loadSessions} />}
        {!loading && !loadError && sessions.length === 0 && (
          <EmptyState
            title="No interview sessions yet"
            description="Click 'New Interview' above to create your first session and start preparing."
          />
        )}
        {!loading && !loadError && sessions.length > 0 && filtered.length === 0 && (
          <EmptyState
            title="No matching sessions"
            description={`No sessions match "${filter}". Try a different search term.`}
          />
        )}
        {!loading && !loadError && filtered.length > 0 && (
          <div className="session-grid">
            {filtered.map((session) => (
              <SessionCard key={session.id} session={session} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
