import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  Activity,
  Building2,
  Database,
  FileBarChart2,
  HardDrive,
  ServerCog,
  UserPlus,
  Users,
} from 'lucide-react';
import {
  activateOrganization,
  activateUser,
  createOrganization,
  createRecruiter,
  deactivateOrganization,
  deactivateUser,
  getAdminOverview,
  getSystemReadiness,
  listAdminActivity,
  listAdminJobRoles,
  listAdminUsers,
  listOrganizations,
  updateUserRole,
} from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useRole } from '../context/RoleContext';
import type {
  AdminActivityEvent,
  AdminOverviewResponse,
  AdminUserResponse,
  JobRoleCount,
  OrganizationResponse,
  ReadinessResponse,
  Role as RoleType,
} from '../api/types';
import { ChartTooltip } from '../components/ChartTooltip';
import { EmptyState, ErrorState } from '../components/StateMessage';
import { StatGridSkeleton } from '../components/Skeleton';

const ROLE_LABELS: Record<RoleType, string> = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  recruiter: 'Recruiter',
  candidate: 'Candidate',
};
const ASSIGNABLE_ROLES: RoleType[] = ['candidate', 'recruiter', 'admin', 'super_admin'];

const ease = [0.4, 0, 0.2, 1] as [number, number, number, number];
const PAGE_SIZE = 8;

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 MB';
  const mb = bytes / (1024 * 1024);
  if (mb < 1) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}

function timeAgo(iso: string | null): string {
  if (!iso) return 'Never';
  const diffMs = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  return `${days}d ago`;
}


function HealthBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.6rem 0.9rem', background: 'var(--surface-2)', borderRadius: 'var(--radius-sm)' }}>
      <span style={{ fontSize: '0.85rem', color: 'var(--text-2)' }}>{label}</span>
      <span
        style={{
          fontSize: '0.75rem',
          fontWeight: 700,
          padding: '0.15rem 0.6rem',
          borderRadius: 999,
          color: ok ? 'var(--success-text)' : 'var(--error-text)',
          background: ok ? 'var(--success-bg)' : 'var(--error-bg)',
        }}
      >
        {ok ? 'OK' : 'DOWN'}
      </span>
    </div>
  );
}

export function AdminPage() {
  const { token } = useAuth();
  const { isSuperAdmin } = useRole();

  const [overview, setOverview] = useState<AdminOverviewResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [jobRoles, setJobRoles] = useState<JobRoleCount[]>([]);
  const [activity, setActivity] = useState<AdminActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [users, setUsers] = useState<AdminUserResponse[]>([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [usersLoading, setUsersLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(0);
  const [userActionError, setUserActionError] = useState<string | null>(null);

  const [organizations, setOrganizations] = useState<OrganizationResponse[]>([]);
  const [orgsLoading, setOrgsLoading] = useState(true);
  const [newOrgName, setNewOrgName] = useState('');
  const [orgActionError, setOrgActionError] = useState<string | null>(null);
  const [orgSubmitting, setOrgSubmitting] = useState(false);

  const [recruiterForm, setRecruiterForm] = useState({
    email: '', password: '', full_name: '', organization_id: '',
  });
  const [recruiterSubmitting, setRecruiterSubmitting] = useState(false);
  const [recruiterError, setRecruiterError] = useState<string | null>(null);
  const [recruiterSuccess, setRecruiterSuccess] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [ov, ready, jobs, act] = await Promise.all([
        getAdminOverview(token),
        getSystemReadiness(),
        listAdminJobRoles(token),
        listAdminActivity(token, 15),
      ]);
      setOverview(ov);
      setReadiness(ready);
      setJobRoles(jobs);
      setActivity(act);
    } catch {
      setError('Could not load the admin dashboard. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard data-fetching pattern
    load();
  }, [load]);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(0);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const loadUsers = useCallback(async () => {
    if (!token) return;
    setUsersLoading(true);
    try {
      const res = await listAdminUsers(token, {
        search: debouncedSearch.trim() || undefined,
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      setUsers(res.items);
      setUsersTotal(res.total);
    } catch {
      // Non-fatal — the overview section still renders.
    } finally {
      setUsersLoading(false);
    }
  }, [token, debouncedSearch, page]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard data-fetching pattern
    loadUsers();
  }, [loadUsers]);

  const loadOrganizations = useCallback(async () => {
    if (!token) return;
    setOrgsLoading(true);
    try {
      const res = await listOrganizations(token);
      setOrganizations(res.items);
    } catch {
      // Non-fatal — the rest of the dashboard still renders.
    } finally {
      setOrgsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard data-fetching pattern
    loadOrganizations();
  }, [loadOrganizations]);

  async function handleCreateOrganization(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !newOrgName.trim()) return;
    setOrgSubmitting(true);
    setOrgActionError(null);
    try {
      await createOrganization({ name: newOrgName.trim() }, token);
      setNewOrgName('');
      await loadOrganizations();
    } catch {
      setOrgActionError('Could not create organization. It may already exist.');
    } finally {
      setOrgSubmitting(false);
    }
  }

  async function handleToggleOrganization(org: OrganizationResponse) {
    if (!token) return;
    setOrgActionError(null);
    try {
      if (org.is_active) await deactivateOrganization(org.id, token);
      else await activateOrganization(org.id, token);
      await loadOrganizations();
    } catch {
      setOrgActionError('Could not update organization status.');
    }
  }

  async function handleCreateRecruiter(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setRecruiterSubmitting(true);
    setRecruiterError(null);
    setRecruiterSuccess(null);
    try {
      const created = await createRecruiter(recruiterForm, token);
      setRecruiterSuccess(`${created.full_name} was created and assigned to ${created.organization_name}.`);
      setRecruiterForm({ email: '', password: '', full_name: '', organization_id: '' });
      await Promise.all([loadOrganizations(), loadUsers()]);
    } catch {
      setRecruiterError('Could not create recruiter. Check the email is unique and try again.');
    } finally {
      setRecruiterSubmitting(false);
    }
  }

  async function handleToggleUserActive(u: AdminUserResponse) {
    if (!token) return;
    setUserActionError(null);
    try {
      if (u.is_active) await deactivateUser(u.id, token);
      else await activateUser(u.id, token);
      await loadUsers();
    } catch {
      setUserActionError('Could not update account status.');
    }
  }

  async function handleChangeRole(u: AdminUserResponse, role: RoleType) {
    if (!token || role === u.role) return;
    setUserActionError(null);
    try {
      await updateUserRole(u.id, { role }, token);
      await loadUsers();
    } catch {
      setUserActionError("Could not change this user's role.");
    }
  }

  // Memoized above the loading/error early returns (Rules of Hooks — hooks
  // must run unconditionally on every render) so typing in the user search
  // box doesn't re-derive these from overview/jobRoles on every keystroke.
  const trendChart = useMemo(() => {
    if (!overview) return [];
    return overview.signups_last_30_days.map((d, i) => ({
      name: d.date.slice(5),
      Signups: d.count,
      Sessions: overview.sessions_last_30_days[i]?.count ?? 0,
    }));
  }, [overview]);

  const jobsChart = useMemo(
    () => jobRoles.slice(0, 8).map((j) => ({ name: j.role, Sessions: j.session_count })),
    [jobRoles],
  );

  if (loading) {
    return (
      <div className="page-container">
        <StatGridSkeleton count={6} />
      </div>
    );
  }

  if (error || !overview) {
    return (
      <div className="page-container">
        <ErrorState message={error ?? 'No data available.'} onRetry={load} />
      </div>
    );
  }

  const totalStorage = overview.storage.audio_bytes + overview.storage.resume_bytes;
  const totalPages = Math.max(1, Math.ceil(usersTotal / PAGE_SIZE));

  return (
    <motion.div
      className="page-container"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease }}
    >
      <div>
        <h1 style={{ margin: 0, fontSize: '1.35rem' }}>Admin Dashboard</h1>
        <p style={{ margin: '0.2rem 0 0', color: 'var(--muted)', fontSize: '0.875rem' }}>
          Platform-wide usage, AI activity, and system health — live backend data.
        </p>
      </div>

      {/* Summary stats */}
      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-value">{overview.total_users}</div>
          <div className="stat-label">Total Users</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{overview.total_sessions}</div>
          <div className="stat-label">Total Interviews</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{overview.total_reports}</div>
          <div className="stat-label">Reports Generated</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{overview.avg_platform_score ?? '—'}</div>
          <div className="stat-label">Avg Platform Score</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{overview.total_resumes}</div>
          <div className="stat-label">Resumes Uploaded</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{formatBytes(totalStorage)}</div>
          <div className="stat-label">Storage Used</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.25rem' }}>
        {/* Sessions by status */}
        <div className="section-panel">
          <div className="card-header-row" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <FileBarChart2 size={16} style={{ color: 'var(--primary)' }} aria-hidden="true" />
              <h2 className="card-header-title">Interviews by Status</h2>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {Object.entries(overview.sessions_by_status).map(([status, count]) => {
              const pct = overview.total_sessions > 0 ? (count / overview.total_sessions) * 100 : 0;
              const color =
                status === 'completed' ? '#22C55E' :
                status === 'in_progress' ? '#3D7EFF' :
                status === 'processing' ? '#F59E0B' : '#5A6680';
              return (
                <div key={status}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', marginBottom: '0.25rem' }}>
                    <span style={{ color: 'var(--text-2)', textTransform: 'capitalize' }}>{status.replace('_', ' ')}</span>
                    <span style={{ fontWeight: 700 }}>{count}</span>
                  </div>
                  <div className="score-bar-mini">
                    <div className="score-bar-mini-fill" style={{ width: `${pct}%`, background: color }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Platform health */}
        <div className="section-panel">
          <div className="card-header-row" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <ServerCog size={16} style={{ color: 'var(--primary)' }} aria-hidden="true" />
              <h2 className="card-header-title">Platform Health</h2>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <HealthBadge ok={readiness?.status === 'ready'} label="Overall readiness" />
            <HealthBadge ok={readiness?.checks.database.ok ?? false} label="Database connection" />
            <HealthBadge ok={readiness?.checks.ai_provider_configured.ok ?? false} label="AI provider configured" />
          </div>
        </div>

        {/* Storage breakdown */}
        <div className="section-panel">
          <div className="card-header-row" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <HardDrive size={16} style={{ color: 'var(--primary)' }} aria-hidden="true" />
              <h2 className="card-header-title">Storage</h2>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span style={{ color: 'var(--text-2)' }}>Audio recordings</span>
              <span style={{ fontWeight: 700 }}>{formatBytes(overview.storage.audio_bytes)} · {overview.storage.audio_file_count} files</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span style={{ color: 'var(--text-2)' }}>Resumes</span>
              <span style={{ fontWeight: 700 }}>{formatBytes(overview.storage.resume_bytes)} · {overview.storage.resume_file_count} files</span>
            </div>
          </div>
        </div>
      </div>

      {/* AI usage */}
      <div className="section-panel">
        <div className="card-header-row" style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Database size={16} style={{ color: 'var(--primary)' }} aria-hidden="true" />
            <h2 className="card-header-title">AI Usage</h2>
          </div>
        </div>
        <div className="stat-grid" style={{ marginBottom: 0 }}>
          <div className="stat-card">
            <div className="stat-value">{overview.ai_usage.questions_generated}</div>
            <div className="stat-label">Questions Generated</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{overview.ai_usage.transcriptions_completed}</div>
            <div className="stat-label">Transcriptions</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{overview.ai_usage.evaluations_completed}</div>
            <div className="stat-label">Evaluations</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{overview.ai_usage.reports_generated}</div>
            <div className="stat-label">Reports</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{overview.ai_usage.coaching_plans_generated}</div>
            <div className="stat-label">Coaching Plans</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{overview.ai_usage.predictions_generated}</div>
            <div className="stat-label">Readiness Predictions</div>
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="charts-row">
        <div className="section-panel" style={{ flex: 1 }}>
          <h2 className="card-header-title" style={{ marginBottom: '1rem' }}>Signups &amp; Sessions (30 days)</h2>
          <div role="img" aria-label="Line chart of daily signups and interview sessions over the last 30 days">
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trendChart}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--muted)' }} interval={4} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
                <Tooltip content={<ChartTooltip />} />
                <Legend wrapperStyle={{ fontSize: '0.78rem' }} />
                <Line type="monotone" dataKey="Signups" stroke="#3D7EFF" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Sessions" stroke="#22C55E" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="section-panel" style={{ flex: 1 }}>
          <h2 className="card-header-title" style={{ marginBottom: '1rem' }}>Top Job Roles</h2>
          {jobsChart.length > 0 ? (
            <div role="img" aria-label="Bar chart of interview session count by job role">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={jobsChart} layout="vertical" margin={{ left: 24 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                  <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
                  <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 10, fill: 'var(--muted)' }} />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="Sessions" fill="#8B5CF6" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState title="No interviews yet" description="Job role distribution appears once users start interviews." />
          )}
        </div>
      </div>

      <div className="admin-content-grid">
        {/* Users table */}
        <div className="section-panel">
          <div className="card-header-row" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Users size={16} style={{ color: 'var(--primary)' }} aria-hidden="true" />
              <h2 className="card-header-title">Users</h2>
            </div>
            <input
              type="search"
              placeholder="Search users…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ padding: '0.4rem 0.75rem', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text)', fontSize: '0.82rem', width: '200px' }}
              aria-label="Search users"
            />
          </div>
          {userActionError && (
            <p role="alert" style={{ color: 'var(--error-text)', fontSize: '0.8rem', margin: '0 0 0.75rem' }}>
              {userActionError}
            </p>
          )}
          {usersLoading ? (
            <div style={{ padding: '1rem 0' }}>
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} style={{ height: '2.5rem', background: 'var(--surface-2)', borderRadius: 6, marginBottom: '0.5rem' }} className="skeleton" />
              ))}
            </div>
          ) : users.length === 0 ? (
            <EmptyState title="No users found" description="No users match the current search." />
          ) : (
            <>
              <div style={{ overflowX: 'auto' }}>
                <table className="recruiter-table" aria-label="All users">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Email</th>
                      <th>Role</th>
                      <th>Organization</th>
                      <th>Status</th>
                      <th>Sessions</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id}>
                        <td style={{ fontWeight: 600 }}>{u.full_name}</td>
                        <td style={{ color: 'var(--muted)' }}>{u.email}</td>
                        <td>
                          {isSuperAdmin ? (
                            <select
                              value={u.role}
                              aria-label={`Change role for ${u.full_name}`}
                              onChange={(e) => handleChangeRole(u, e.target.value as RoleType)}
                              style={{ padding: '0.25rem 0.4rem', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text)', fontSize: '0.78rem' }}
                            >
                              {ASSIGNABLE_ROLES.map((r) => (
                                <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                              ))}
                            </select>
                          ) : (
                            ROLE_LABELS[u.role]
                          )}
                        </td>
                        <td style={{ color: 'var(--muted)' }}>{u.organization_name ?? '—'}</td>
                        <td>
                          <span
                            style={{
                              fontSize: '0.72rem', fontWeight: 700, padding: '0.15rem 0.55rem', borderRadius: 999,
                              color: u.is_active ? 'var(--success-text)' : 'var(--error-text)',
                              background: u.is_active ? 'var(--success-bg)' : 'var(--error-bg)',
                            }}
                          >
                            {u.is_active ? 'Active' : 'Deactivated'}
                          </span>
                        </td>
                        <td style={{ fontVariantNumeric: 'tabular-nums' }}>{u.sessions_completed}</td>
                        <td>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            onClick={() => handleToggleUserActive(u)}
                          >
                            {u.is_active ? 'Deactivate' : 'Activate'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '0.875rem', marginTop: '0.5rem', borderTop: '1px solid var(--border)' }}>
                <span style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>Page {page + 1} of {totalPages}</span>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button type="button" className="btn btn-ghost btn-sm" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>Previous</button>
                  <button type="button" className="btn btn-ghost btn-sm" disabled={page + 1 >= totalPages} onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}>Next</button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Activity feed */}
        <div className="section-panel">
          <div className="card-header-row" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Activity size={16} style={{ color: 'var(--primary)' }} aria-hidden="true" />
              <h2 className="card-header-title">Platform Activity</h2>
            </div>
          </div>
          {activity.length === 0 ? (
            <EmptyState title="No activity yet" description="Platform-wide events will appear here." />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', maxHeight: 420, overflowY: 'auto' }}>
              {activity.map((event, i) => (
                <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
                  <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text)' }}>{event.title}</span>
                  {event.subtitle && <span style={{ fontSize: '0.76rem', color: 'var(--muted)' }}>{event.subtitle}</span>}
                  <span style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>{timeAgo(event.created_at)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="admin-content-grid">
        {/* Organizations */}
        <div className="section-panel">
          <div className="card-header-row" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Building2 size={16} style={{ color: 'var(--primary)' }} aria-hidden="true" />
              <h2 className="card-header-title">Organizations</h2>
            </div>
          </div>

          <form onSubmit={handleCreateOrganization} style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
            <input
              type="text"
              placeholder="New organization name…"
              value={newOrgName}
              onChange={(e) => setNewOrgName(e.target.value)}
              required
              style={{ flex: 1, padding: '0.4rem 0.75rem', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text)', fontSize: '0.82rem' }}
              aria-label="New organization name"
            />
            <button type="submit" className="btn btn-primary btn-sm" disabled={orgSubmitting || !newOrgName.trim()}>
              {orgSubmitting ? 'Creating…' : 'Create'}
            </button>
          </form>
          {orgActionError && (
            <p role="alert" style={{ color: 'var(--error-text)', fontSize: '0.8rem', margin: '0 0 0.75rem' }}>
              {orgActionError}
            </p>
          )}

          {orgsLoading ? (
            <div style={{ padding: '1rem 0' }}>
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} style={{ height: '2.5rem', background: 'var(--surface-2)', borderRadius: 6, marginBottom: '0.5rem' }} className="skeleton" />
              ))}
            </div>
          ) : organizations.length === 0 ? (
            <EmptyState title="No organizations yet" description="Create one above to start assigning recruiters." />
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="recruiter-table" aria-label="Organizations">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Recruiters</th>
                    <th>Candidates</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {organizations.map((org) => (
                    <tr key={org.id}>
                      <td style={{ fontWeight: 600 }}>{org.name}</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>{org.recruiter_count}</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>{org.candidate_count}</td>
                      <td>
                        <span
                          style={{
                            fontSize: '0.72rem', fontWeight: 700, padding: '0.15rem 0.55rem', borderRadius: 999,
                            color: org.is_active ? 'var(--success-text)' : 'var(--error-text)',
                            background: org.is_active ? 'var(--success-bg)' : 'var(--error-bg)',
                          }}
                        >
                          {org.is_active ? 'Active' : 'Deactivated'}
                        </span>
                      </td>
                      <td>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => handleToggleOrganization(org)}>
                          {org.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Create recruiter */}
        <div className="section-panel">
          <div className="card-header-row" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <UserPlus size={16} style={{ color: 'var(--primary)' }} aria-hidden="true" />
              <h2 className="card-header-title">Create Recruiter</h2>
            </div>
          </div>
          <form onSubmit={handleCreateRecruiter} style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
            <input
              type="text"
              placeholder="Full name"
              value={recruiterForm.full_name}
              onChange={(e) => setRecruiterForm((f) => ({ ...f, full_name: e.target.value }))}
              required
              style={{ padding: '0.5rem 0.75rem', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text)', fontSize: '0.85rem' }}
            />
            <input
              type="email"
              placeholder="Email"
              value={recruiterForm.email}
              onChange={(e) => setRecruiterForm((f) => ({ ...f, email: e.target.value }))}
              required
              style={{ padding: '0.5rem 0.75rem', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text)', fontSize: '0.85rem' }}
            />
            <input
              type="password"
              placeholder="Temporary password (min 8 characters)"
              value={recruiterForm.password}
              onChange={(e) => setRecruiterForm((f) => ({ ...f, password: e.target.value }))}
              required
              minLength={8}
              style={{ padding: '0.5rem 0.75rem', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text)', fontSize: '0.85rem' }}
            />
            <select
              value={recruiterForm.organization_id}
              onChange={(e) => setRecruiterForm((f) => ({ ...f, organization_id: e.target.value }))}
              required
              aria-label="Organization"
              style={{ padding: '0.5rem 0.75rem', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text)', fontSize: '0.85rem' }}
            >
              <option value="" disabled>Select organization…</option>
              {organizations.map((org) => (
                <option key={org.id} value={org.id}>{org.name}</option>
              ))}
            </select>
            {recruiterError && (
              <p role="alert" style={{ color: 'var(--error-text)', fontSize: '0.8rem', margin: 0 }}>{recruiterError}</p>
            )}
            {recruiterSuccess && (
              <p style={{ color: 'var(--success-text)', fontSize: '0.8rem', margin: 0 }}>{recruiterSuccess}</p>
            )}
            <button
              type="submit"
              className="btn btn-primary btn-sm"
              disabled={recruiterSubmitting || organizations.length === 0}
              style={{ alignSelf: 'flex-start' }}
            >
              {recruiterSubmitting ? 'Creating…' : 'Create Recruiter'}
            </button>
            {organizations.length === 0 && (
              <p style={{ color: 'var(--muted)', fontSize: '0.78rem', margin: 0 }}>
                Create an organization first.
              </p>
            )}
          </form>
        </div>
      </div>
    </motion.div>
  );
}
