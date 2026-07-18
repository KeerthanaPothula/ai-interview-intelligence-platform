import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { motion } from 'framer-motion';
import { FileText, RefreshCw, Search } from 'lucide-react';
import { ApiError, createSession, listSessions } from '../api/client';
import { ResumeUploadCard } from '../components/ResumeUploadCard';
import { SessionCard } from '../components/SessionCard';
import { SessionListSkeleton } from '../components/Skeleton';
import { EmptyState, ErrorState } from '../components/StateMessage';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import type { SessionListResponse } from '../api/types';

const ease = [0.4, 0, 0.2, 1] as [number, number, number, number];
type StatusFilter = 'all' | 'draft' | 'in_progress' | 'completed';
const STATUS_LABELS: Record<StatusFilter, string> = {
  all: 'All',
  draft: 'Draft',
  in_progress: 'In Progress',
  completed: 'Completed',
};

export function SessionsListPage() {
  const { token } = useAuth();
  const { showToast } = useToast();
  const [sessions, setSessions] = useState<SessionListResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

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
      showToast('Interview session created.', 'success');
    } catch (err) {
      setCreateError(
        err instanceof ApiError ? err.message : 'Unable to create the session. Please try again.',
      );
    } finally {
      setCreating(false);
    }
  }

  const statusCounts = useMemo(() => ({
    all: sessions.length,
    draft: sessions.filter((s) => s.status === 'draft').length,
    in_progress: sessions.filter((s) => s.status === 'in_progress').length,
    completed: sessions.filter((s) => s.status === 'completed').length,
  }), [sessions]);

  const filtered = useMemo(() => {
    let list = sessions;
    if (statusFilter !== 'all') list = list.filter((s) => s.status === statusFilter);
    if (filter.trim()) {
      const q = filter.toLowerCase();
      list = list.filter(
        (s) => s.title.toLowerCase().includes(q) || s.job_role?.toLowerCase().includes(q),
      );
    }
    return list;
  }, [sessions, statusFilter, filter]);

  return (
    <motion.div
      className="page-container"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease }}
    >
      {/* Page header */}
      <div className="page-hd">
        <div className="page-hd-text">
          <h1>Interviews</h1>
          <p>
            {sessions.length > 0
              ? `${sessions.length} session${sessions.length === 1 ? '' : 's'} · ${statusCounts.completed} completed`
              : 'No sessions yet — create your first below'}
          </p>
        </div>
      </div>

      {/* 2-column dashboard layout */}
      <div className="sessions-dashboard">

        {/* ── Left: Create Interview ── */}
        <div className="sessions-create-panel">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.4rem' }}>
              <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--primary-dim)', color: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <FileText size={15} aria-hidden="true" />
              </div>
              <h2 className="sessions-create-heading">New Interview</h2>
            </div>
            <p className="sessions-create-sub">
              Set up a practice session tailored to your target role and job description.
            </p>
          </div>

          <form className="sessions-create-form" onSubmit={handleCreate} noValidate>
            <label htmlFor="sess-title">
              Session title
              <input
                id="sess-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Amazon SDE Prep"
                required
              />
            </label>
            <label htmlFor="sess-role">
              Target role
              <input
                id="sess-role"
                value={jobRole}
                onChange={(e) => setJobRole(e.target.value)}
                placeholder="e.g. Software Engineer"
                required
              />
            </label>
            <label htmlFor="sess-desc">
              Job description
              <textarea
                id="sess-desc"
                value={jobDescription}
                onChange={(e) => setJobDescription(e.target.value)}
                placeholder="Paste the job description here (at least 20 characters)…"
                required
                minLength={20}
                rows={4}
              />
              <span className="field-hint">At least 20 characters — used to generate tailored questions.</span>
            </label>

            {createError && (
              <p className="error-banner" role="alert">{createError}</p>
            )}

            <button
              type="submit"
              className="btn btn-primary"
              disabled={creating}
              aria-busy={creating}
            >
              {creating ? (
                <>
                  <span className="spinner" aria-hidden="true" />
                  Creating…
                </>
              ) : (
                'Create Interview'
              )}
            </button>
          </form>

          <ResumeUploadCard />
        </div>

        {/* ── Right: Session list ── */}
        <div className="sessions-list-panel" aria-label="Your interview sessions">

          {/* Toolbar: search + refresh */}
          <div className="sessions-toolbar">
            <div className="sessions-search-wrap">
              <Search size={13} style={{ color: 'var(--muted)', flexShrink: 0 }} aria-hidden="true" />
              <input
                type="search"
                className="sessions-search-input"
                placeholder="Search by title or role…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                aria-label="Search sessions by title or role"
              />
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={loadSessions}
              aria-label="Refresh sessions"
            >
              <RefreshCw size={14} aria-hidden="true" />
            </button>
          </div>

          {/* Status filter chips */}
          {sessions.length > 0 && (
            <div className="sessions-filter-chips" role="group" aria-label="Filter sessions by status">
              {(Object.keys(STATUS_LABELS) as StatusFilter[]).map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`sessions-filter-chip${statusFilter === s ? ' active' : ''}`}
                  onClick={() => setStatusFilter(s)}
                  aria-pressed={statusFilter === s}
                >
                  {STATUS_LABELS[s]} ({statusCounts[s]})
                </button>
              ))}
            </div>
          )}

          {/* Meta row */}
          {sessions.length > 0 && (
            <div className="sessions-meta-row" aria-live="polite">
              <span><strong>{filtered.length}</strong> shown</span>
              <span><strong>{statusCounts.completed}</strong> completed</span>
              <span><strong>{statusCounts.draft}</strong> drafts</span>
            </div>
          )}

          {/* Content */}
          {loading && <SessionListSkeleton />}
          {!loading && loadError && <ErrorState message={loadError} onRetry={loadSessions} />}
          {!loading && !loadError && sessions.length === 0 && (
            <EmptyState
              title="No interview sessions yet"
              description="Fill out the form on the left to create your first session."
            />
          )}
          {!loading && !loadError && sessions.length > 0 && filtered.length === 0 && (
            <EmptyState
              title="No matching sessions"
              description={
                statusFilter !== 'all'
                  ? `No ${STATUS_LABELS[statusFilter].toLowerCase()} sessions found.`
                  : `No sessions match "${filter}".`
              }
            />
          )}
          {!loading && !loadError && filtered.length > 0 && (
            <div className="session-grid">
              {filtered.map((session) => (
                <SessionCard key={session.id} session={session} />
              ))}
            </div>
          )}
        </div>

      </div>
    </motion.div>
  );
}
