import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { listCandidates } from '../api/client';
import { useAuth } from '../context/AuthContext';
import type { CandidateResponse, CandidateStatus, CandidateSummary } from '../api/types';
import { EmptyState, ErrorState } from '../components/StateMessage';
import { Skeleton } from '../components/Skeleton';

const ease = [0.4, 0, 0.2, 1] as [number, number, number, number];

const PAGE_SIZE = 10;
const PIPELINE_STAGES = ['Applied', 'Screened', 'Technical', 'Final Round', 'Offer'];
const STATUS_FILTERS: { label: string; value: CandidateStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Shortlisted', value: 'shortlisted' },
  { label: 'Reviewing', value: 'reviewing' },
  { label: 'Pending', value: 'pending' },
  { label: 'Rejected', value: 'rejected' },
];

type SortKey = 'name' | 'resumeScore' | 'interviewScore' | 'communication' | 'technical' | 'appliedDays';

const AVATAR_COLORS = ['#7c3aed', '#2563eb', '#0891b2', '#059669', '#d97706', '#dc2626'];

function avatarColorFor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? '') + (parts[parts.length - 1]?.[0] ?? '')).toUpperCase();
}

function ScoreBar({ value }: { value: number | null }) {
  if (value == null) {
    return <span style={{ color: 'var(--muted)' }}>—</span>;
  }
  const color = value >= 85 ? '#10b981' : value >= 70 ? '#3b82f6' : '#f59e0b';
  return (
    <div className="score-with-bar">
      <span style={{ fontWeight: 700, color: 'var(--text)' }}>{value}</span>
      <div className="score-bar-mini">
        <div className="score-bar-mini-fill" style={{ width: `${value}%`, background: color }} />
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: CandidateStatus }) {
  const labels: Record<CandidateStatus, string> = {
    shortlisted: 'Shortlisted',
    reviewing: 'Reviewing',
    rejected: 'Rejected',
    pending: 'Pending',
  };
  return <span className={`cand-status ${status}`}>{labels[status]}</span>;
}

function getPipelineStage(status: CandidateStatus): number {
  if (status === 'rejected') return -1;
  if (status === 'pending') return 0;
  if (status === 'reviewing') return 2;
  if (status === 'shortlisted') return 4;
  return 0;
}

function TableSkeleton() {
  return (
    <div style={{ padding: '1.25rem' }}>
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} style={{ display: 'flex', gap: '1rem', alignItems: 'center', padding: '0.75rem 0' }}>
          <span className="skeleton" style={{ width: '2.25rem', height: '2.25rem', borderRadius: '50%', display: 'inline-block' }} aria-hidden="true" />
          <Skeleton width="140px" height="0.9rem" />
          <Skeleton width="80px" height="0.9rem" />
          <Skeleton width="80px" height="0.9rem" />
          <Skeleton width="80px" height="0.9rem" />
        </div>
      ))}
    </div>
  );
}

export function RecruiterPage() {
  const { token } = useAuth();
  const [statusFilter, setStatusFilter] = useState<CandidateStatus | 'all'>('all');
  const [sortKey, setSortKey] = useState<SortKey>('interviewScore');
  const [sortAsc, setSortAsc] = useState(false);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [items, setItems] = useState<CandidateResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<CandidateSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(0);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const sortKeyToApi: Record<SortKey, string> = {
    name: 'name',
    resumeScore: 'resumeScore',
    interviewScore: 'interviewScore',
    communication: 'communication',
    technical: 'technical',
    appliedDays: 'appliedDays',
  };

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const res = await listCandidates(token, {
        search: debouncedSearch.trim() || undefined,
        status: statusFilter === 'all' ? undefined : statusFilter,
        sortBy: sortKeyToApi[sortKey],
        sortDir: sortAsc ? 'asc' : 'desc',
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      setItems(res.items);
      setTotal(res.total);
      setSummary(res.summary);
    } catch {
      setError('Could not load candidates. Please try again.');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, debouncedSearch, statusFilter, sortKey, sortAsc, page]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard data-fetching pattern
    load();
  }, [load]);

  const selected = useMemo(
    () => (selectedId != null ? items.find((c) => c.id === selectedId) ?? null : null),
    [items, selectedId],
  );

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc((a) => !a);
    else {
      setSortKey(key);
      setSortAsc(false);
    }
    setPage(0);
  };

  const thLabel = (key: SortKey, label: string) => (
    <th
      className={sortKey === key ? 'sorted' : ''}
      onClick={() => handleSort(key)}
      aria-sort={sortKey === key ? (sortAsc ? 'ascending' : 'descending') : 'none'}
      style={{ cursor: 'pointer' }}
    >
      {label} {sortKey === key ? (sortAsc ? '↑' : '↓') : ''}
    </th>
  );

  const pipelineStage = selected ? getPipelineStage(selected.status) : -1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <motion.div
      className="page-container recruiter-page"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.35rem' }}>Recruiter Dashboard</h1>
          <p style={{ margin: '0.2rem 0 0', color: 'var(--muted)', fontSize: '0.875rem' }}>
            {total} candidate{total === 1 ? '' : 's'} · {summary?.shortlisted_count ?? 0} shortlisted
          </p>
        </div>
        <input
          type="search"
          placeholder="Search candidates…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ padding: '0.45rem 0.875rem', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text)', fontSize: '0.875rem', minWidth: '220px', width: '100%', maxWidth: '280px' }}
          aria-label="Search candidates"
        />
      </div>

      {/* Summary stats */}
      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-value">{total}</div>
          <div className="stat-label">Total Candidates</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{summary?.shortlisted_count ?? 0}</div>
          <div className="stat-label">Shortlisted</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{summary?.avg_resume_score ?? '—'}</div>
          <div className="stat-label">Avg Resume Score</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{summary?.avg_interview_score ?? '—'}</div>
          <div className="stat-label">Avg Interview Score</div>
        </div>
      </div>

      {/* Filters */}
      <div className="recruiter-filters" role="group" aria-label="Filter by status">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            className={`recruiter-filter-chip${statusFilter === f.value ? ' active' : ''}`}
            onClick={() => {
              setStatusFilter(f.value);
              setPage(0);
            }}
            aria-pressed={statusFilter === f.value}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Main layout: table + detail panel */}
      <div className={`recruiter-layout${selected ? ' has-detail' : ''}`}>
        {/* Table */}
        <div className="section-panel" style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
          {loading ? (
            <TableSkeleton />
          ) : error ? (
            <div style={{ padding: '2rem' }}>
              <ErrorState message={error} onRetry={load} />
            </div>
          ) : items.length === 0 ? (
            <div style={{ padding: '2rem' }}>
              <EmptyState
                title="No candidates found"
                description={
                  total === 0 && !debouncedSearch && statusFilter === 'all'
                    ? 'Candidates appear here once users complete an interview session.'
                    : 'No candidates match the current filters.'
                }
              />
            </div>
          ) : (
            <>
              <div className="recruiter-table-wrap">
                <table className="recruiter-table" aria-label="Candidate rankings">
                  <thead>
                    <tr>
                      {thLabel('name', 'Candidate')}
                      {thLabel('resumeScore', 'Resume')}
                      {thLabel('interviewScore', 'Interview')}
                      {thLabel('communication', 'Comm.')}
                      {thLabel('technical', 'Technical')}
                      {thLabel('appliedDays', 'Applied')}
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((c) => {
                      const color = avatarColorFor(c.name);
                      return (
                        <tr
                          key={c.id}
                          onClick={() => setSelectedId(c.id === selectedId ? null : c.id)}
                          aria-selected={c.id === selectedId}
                          style={c.id === selectedId ? { background: 'var(--primary-dim)' } : {}}
                        >
                          <td>
                            <div className="cand-name-cell">
                              <div className="cand-avatar" style={{ background: color + '22', color }}>
                                {initialsFor(c.name)}
                              </div>
                              <div>
                                <div>{c.name}</div>
                                <div className="cand-sub">{c.role}</div>
                              </div>
                            </div>
                          </td>
                          <td><ScoreBar value={c.resume_score} /></td>
                          <td><ScoreBar value={c.interview_score} /></td>
                          <td><ScoreBar value={c.communication} /></td>
                          <td><ScoreBar value={c.technical} /></td>
                          <td style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
                            {c.applied_days === 0 ? 'Today' : `${c.applied_days}d ago`}
                          </td>
                          <td><StatusBadge status={c.status} /></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.875rem 1.25rem', borderTop: '1px solid var(--border)' }}>
                <span style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>
                  Page {page + 1} of {totalPages}
                </span>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    disabled={page === 0}
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    disabled={page + 1 >= totalPages}
                    onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Candidate detail panel */}
        <AnimatePresence>
          {selected && (
            <motion.div
              key={selected.id}
              className="cand-detail"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={{ duration: 0.25, ease }}
            >
              <div className="cand-detail-hd">
                <div className="cand-detail-avatar" style={{ background: avatarColorFor(selected.name) + '22', color: avatarColorFor(selected.name) }}>
                  {initialsFor(selected.name)}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 800, fontSize: '1rem' }}>{selected.name}</div>
                  <div style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>{selected.role}</div>
                  <div style={{ marginTop: '0.35rem' }}><StatusBadge status={selected.status} /></div>
                </div>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setSelectedId(null)}
                  aria-label="Close candidate detail"
                  style={{ flexShrink: 0 }}
                >
                  ✕
                </button>
              </div>

              <div className="cand-detail-scores">
                {[
                  { label: 'Resume Score', value: selected.resume_score },
                  { label: 'Interview Score', value: selected.interview_score },
                  { label: 'Communication', value: selected.communication },
                  { label: 'Technical', value: selected.technical },
                ].map((m) => {
                  const color = m.value == null ? 'var(--muted)' : m.value >= 85 ? '#10b981' : m.value >= 70 ? '#3b82f6' : '#f59e0b';
                  return (
                    <div key={m.label} className="cand-metric">
                      <div className="cand-metric-label">{m.label}</div>
                      <div className="cand-metric-val" style={{ color }}>{m.value ?? '—'}</div>
                    </div>
                  );
                })}
              </div>

              <div style={{ padding: '0 1.5rem 1.25rem' }}>
                <div style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--muted)', marginBottom: '0.5rem' }}>
                  Hiring Pipeline
                </div>
                <div className="pipeline-bar">
                  {PIPELINE_STAGES.map((stage, i) => {
                    const isDone = pipelineStage > i;
                    const isActive = pipelineStage === i + 1;
                    return (
                      <div
                        key={stage}
                        className={`pipeline-step${isDone ? ' done' : isActive ? ' active' : ''}`}
                        title={stage}
                      >
                        {stage}
                      </div>
                    );
                  })}
                </div>
                <div style={{ marginTop: '0.6rem', fontSize: '0.75rem', color: 'var(--muted)' }}>
                  {selected.sessions_completed} interview{selected.sessions_completed === 1 ? '' : 's'} completed
                </div>
              </div>

              <div className="cand-detail-notes">
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <button type="button" className="btn btn-primary btn-sm">Schedule Interview</button>
                  <button type="button" className="btn btn-ghost btn-sm">Download Report</button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
