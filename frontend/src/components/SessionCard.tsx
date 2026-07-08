import { Link } from 'react-router-dom';
import { FileBarChart2 } from 'lucide-react';
import type { SessionListResponse } from '../api/types';

export function SessionCard({ session }: { session: SessionListResponse }) {
  const isCompleted = session.status === 'completed';
  const date = new Date(session.created_at).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <div className="session-card-wrapper">
      <Link to={`/sessions/${session.id}`} className="session-card">
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.5rem' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h3 style={{ margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {session.title}
            </h3>
            <p className="session-job-role" style={{ margin: '0.2rem 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {session.job_role}
            </p>
          </div>
          <span className={`session-status status-${session.status}`} style={{ flexShrink: 0 }}>
            {session.status}
          </span>
        </div>
        <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '0.75rem' }}>
          {date}
        </div>
      </Link>

      {isCompleted && (
        <div style={{
          padding: '0.5rem 0.875rem',
          borderTop: '1px solid var(--border)',
          display: 'flex',
          gap: '0.5rem',
        }}>
          <Link
            to={`/sessions/${session.id}/report`}
            className="btn btn-ghost btn-sm"
            style={{ fontSize: '0.78rem', gap: '0.3rem' }}
            aria-label={`View report for ${session.title}`}
            onClick={(e) => e.stopPropagation()}
          >
            <FileBarChart2 size={12} aria-hidden="true" />
            View Report
          </Link>
        </div>
      )}
    </div>
  );
}
