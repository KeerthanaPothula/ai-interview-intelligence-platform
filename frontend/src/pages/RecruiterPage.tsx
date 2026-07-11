import { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const ease = [0.4, 0, 0.2, 1] as [number, number, number, number];

type Status = 'shortlisted' | 'reviewing' | 'rejected' | 'pending';

interface Candidate {
  id: number;
  name: string;
  role: string;
  resumeScore: number;
  interviewScore: number;
  communication: number;
  technical: number;
  experience: number;
  status: Status;
  appliedDays: number;
  initials: string;
  avatarColor: string;
}

const MOCK_CANDIDATES: Candidate[] = [
  { id: 1, name: 'Priya Sharma',    role: 'Senior Frontend Engineer',  resumeScore: 91, interviewScore: 87, communication: 90, technical: 85, experience: 6, status: 'shortlisted', appliedDays: 2, initials: 'PS', avatarColor: '#7c3aed' },
  { id: 2, name: 'Marcus Johnson',  role: 'Full Stack Developer',       resumeScore: 83, interviewScore: 79, communication: 82, technical: 77, experience: 4, status: 'reviewing',   appliedDays: 5, initials: 'MJ', avatarColor: '#2563eb' },
  { id: 3, name: 'Aiko Tanaka',     role: 'Backend Engineer',           resumeScore: 88, interviewScore: 92, communication: 78, technical: 94, experience: 7, status: 'shortlisted', appliedDays: 1, initials: 'AT', avatarColor: '#0891b2' },
  { id: 4, name: 'David Okonkwo',   role: 'Senior Frontend Engineer',   resumeScore: 74, interviewScore: 68, communication: 71, technical: 65, experience: 3, status: 'rejected',    appliedDays: 9, initials: 'DO', avatarColor: '#dc2626' },
  { id: 5, name: 'Sofia Reyes',     role: 'Full Stack Developer',       resumeScore: 79, interviewScore: 83, communication: 85, technical: 80, experience: 5, status: 'reviewing',   appliedDays: 3, initials: 'SR', avatarColor: '#059669' },
  { id: 6, name: 'Chen Wei',        role: 'Backend Engineer',           resumeScore: 95, interviewScore: 90, communication: 88, technical: 93, experience: 9, status: 'shortlisted', appliedDays: 4, initials: 'CW', avatarColor: '#d97706' },
  { id: 7, name: 'Fatima Al-Rashid','role': 'Senior Frontend Engineer', resumeScore: 82, interviewScore: 76, communication: 80, technical: 73, experience: 5, status: 'pending',     appliedDays: 7, initials: 'FA', avatarColor: '#7c3aed' },
  { id: 8, name: 'James Park',      role: 'Full Stack Developer',       resumeScore: 70, interviewScore: 72, communication: 74, technical: 70, experience: 2, status: 'pending',     appliedDays: 6, initials: 'JP', avatarColor: '#6b7280' },
];

const PIPELINE_STAGES = ['Applied', 'Screened', 'Technical', 'Final Round', 'Offer'];
const STATUS_FILTERS: { label: string; value: Status | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Shortlisted', value: 'shortlisted' },
  { label: 'Reviewing', value: 'reviewing' },
  { label: 'Pending', value: 'pending' },
  { label: 'Rejected', value: 'rejected' },
];

type SortKey = 'name' | 'resumeScore' | 'interviewScore' | 'communication' | 'technical' | 'experience';

function ScoreBar({ value }: { value: number }) {
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

function StatusBadge({ status }: { status: Status }) {
  const labels: Record<Status, string> = {
    shortlisted: 'Shortlisted',
    reviewing: 'Reviewing',
    rejected: 'Rejected',
    pending: 'Pending',
  };
  return <span className={`cand-status ${status}`}>{labels[status]}</span>;
}

function getPipelineStage(status: Status): number {
  if (status === 'rejected') return -1;
  if (status === 'pending') return 0;
  if (status === 'reviewing') return 2;
  if (status === 'shortlisted') return 4;
  return 0;
}

export function RecruiterPage() {
  const [statusFilter, setStatusFilter] = useState<Status | 'all'>('all');
  const [sortKey, setSortKey] = useState<SortKey>('interviewScore');
  const [sortAsc, setSortAsc] = useState(false);
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const filtered = useMemo(() => {
    let list = MOCK_CANDIDATES;
    if (statusFilter !== 'all') list = list.filter((c) => c.status === statusFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((c) => c.name.toLowerCase().includes(q) || c.role.toLowerCase().includes(q));
    }
    list = [...list].sort((a, b) => {
      const av = sortKey === 'name' ? a.name : a[sortKey];
      const bv = sortKey === 'name' ? b.name : b[sortKey];
      if (typeof av === 'string' && typeof bv === 'string') {
        return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      return sortAsc ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });
    return list;
  }, [statusFilter, sortKey, sortAsc, search]);

  const selected = selectedId != null ? MOCK_CANDIDATES.find((c) => c.id === selectedId) ?? null : null;

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc((a) => !a);
    else { setSortKey(key); setSortAsc(false); }
  };

  const thLabel = (key: SortKey, label: string) => (
    <th
      className={sortKey === key ? 'sorted' : ''}
      onClick={() => handleSort(key)}
      aria-sort={sortKey === key ? (sortAsc ? 'ascending' : 'descending') : 'none'}
    >
      {label} {sortKey === key ? (sortAsc ? '↑' : '↓') : ''}
    </th>
  );

  const pipelineStage = selected ? getPipelineStage(selected.status) : -1;

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
          <h1 style={{ margin: '0 0 0.3rem', fontSize: '1.5rem', fontWeight: 800 }}>Recruiter Dashboard</h1>
          <p style={{ margin: 0, color: 'var(--muted)', fontSize: '0.9rem' }}>
            {MOCK_CANDIDATES.length} candidates · {MOCK_CANDIDATES.filter((c) => c.status === 'shortlisted').length} shortlisted
          </p>
        </div>
        <input
          type="search"
          placeholder="Search candidates…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ padding: '0.45rem 0.875rem', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text)', fontSize: '0.875rem', minWidth: '220px' }}
          aria-label="Search candidates"
        />
      </div>

      {/* Filters */}
      <div className="recruiter-filters" role="group" aria-label="Filter by status">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            className={`recruiter-filter-chip${statusFilter === f.value ? ' active' : ''}`}
            onClick={() => setStatusFilter(f.value)}
            aria-pressed={statusFilter === f.value}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Main layout: table + detail panel */}
      <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 380px' : '1fr', gap: '1.25rem', alignItems: 'start' }}>
        {/* Table */}
        <div className="section-panel" style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
          <div className="recruiter-table-wrap">
            <table className="recruiter-table" aria-label="Candidate rankings">
              <thead>
                <tr>
                  {thLabel('name', 'Candidate')}
                  {thLabel('resumeScore', 'Resume')}
                  {thLabel('interviewScore', 'Interview')}
                  {thLabel('communication', 'Comm.')}
                  {thLabel('technical', 'Technical')}
                  {thLabel('experience', 'Exp.')}
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr
                    key={c.id}
                    onClick={() => setSelectedId(c.id === selectedId ? null : c.id)}
                    aria-selected={c.id === selectedId}
                    style={c.id === selectedId ? { background: 'var(--primary-dim)' } : {}}
                  >
                    <td>
                      <div className="cand-name-cell">
                        <div className="cand-avatar" style={{ background: c.avatarColor + '22', color: c.avatarColor }}>
                          {c.initials}
                        </div>
                        <div>
                          <div>{c.name}</div>
                          <div className="cand-sub">{c.role}</div>
                        </div>
                      </div>
                    </td>
                    <td><ScoreBar value={c.resumeScore} /></td>
                    <td><ScoreBar value={c.interviewScore} /></td>
                    <td><ScoreBar value={c.communication} /></td>
                    <td><ScoreBar value={c.technical} /></td>
                    <td style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>{c.experience}y</td>
                    <td><StatusBadge status={c.status} /></td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--muted)' }}>
                      No candidates match the current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
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
                <div className="cand-detail-avatar" style={{ background: selected.avatarColor + '22', color: selected.avatarColor }}>
                  {selected.initials}
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
                  { label: 'Resume Score', value: selected.resumeScore },
                  { label: 'Interview Score', value: selected.interviewScore },
                  { label: 'Communication', value: selected.communication },
                  { label: 'Technical', value: selected.technical },
                ].map((m) => {
                  const color = m.value >= 85 ? '#10b981' : m.value >= 70 ? '#3b82f6' : '#f59e0b';
                  return (
                    <div key={m.label} className="cand-metric">
                      <div className="cand-metric-label">{m.label}</div>
                      <div className="cand-metric-val" style={{ color }}>{m.value}</div>
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
