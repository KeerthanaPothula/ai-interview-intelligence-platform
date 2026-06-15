import { Link } from 'react-router-dom';
import type { SessionListResponse } from '../api/types';

export function SessionCard({ session }: { session: SessionListResponse }) {
  return (
    <Link to={`/sessions/${session.id}`} className="session-card">
      <h3>{session.title}</h3>
      <p className="session-job-role">{session.job_role}</p>
      <span className={`session-status status-${session.status}`}>{session.status}</span>
    </Link>
  );
}
