import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  Activity,
  Award,
  BarChart2,
  BrainCircuit,
  RefreshCw,
  TrendingUp,
} from 'lucide-react';
import {
  getActivityTimeline,
  getAnalyticsOverview,
  getAnalyticsTrends,
  getBenchmarks,
  getInsights,
} from '../api/client';
import { StatGridSkeleton } from '../components/Skeleton';
import { ErrorState } from '../components/StateMessage';
import type {
  ActivityEvent,
  AnalyticsOverviewResponse,
  BenchmarkResponse,
  InsightItem,
  SessionTrendResponse,
} from '../api/types';
import { useAuth } from '../context/AuthContext';

// ─── Stat card ────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: string | number | null;
  icon?: React.ReactNode;
  accent?: string;
  sub?: string;
}

function StatCard({ label, value, icon, accent = 'var(--primary)', sub }: StatCardProps) {
  return (
    <div className="stat-card" style={{ textAlign: 'left', padding: '1.25rem 1.25rem 1rem' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '0.75rem',
        }}
      >
        <span className="stat-label" style={{ marginTop: 0 }}>
          {label}
        </span>
        {icon && (
          <span
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 32,
              height: 32,
              borderRadius: 8,
              background: `${accent}20`,
              color: accent,
              flexShrink: 0,
            }}
          >
            {icon}
          </span>
        )}
      </div>
      <div className="stat-value" style={{ fontSize: '1.6rem' }}>
        {value ?? '—'}
      </div>
      {sub && <div className="stat-trend">{sub}</div>}
    </div>
  );
}

// ─── Recharts tooltip ─────────────────────────────────────────────────────────

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--border-strong)',
        borderRadius: 8,
        padding: '0.6rem 0.9rem',
        fontSize: '0.82rem',
        boxShadow: 'var(--shadow)',
      }}
    >
      <p style={{ margin: '0 0 0.4rem', color: 'var(--muted)', fontWeight: 600 }}>{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ margin: '0.15rem 0', color: p.color }}>
          {p.name}: <strong>{p.value?.toFixed(1)}</strong>
        </p>
      ))}
    </div>
  );
}

// ─── Readiness gauge ──────────────────────────────────────────────────────────

function ReadinessGauge({ score }: { score: number }) {
  const r = 56;
  const circ = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, score));
  const arcLen = (clamped / 100) * circ * 0.75;
  const color =
    clamped >= 75 ? 'var(--success)' : clamped >= 50 ? 'var(--primary)' : 'var(--warning)';

  return (
    <div className="readiness-gauge-wrap">
      <svg
        width={140}
        height={140}
        viewBox="0 0 140 140"
        className="readiness-gauge-svg"
        role="img"
        aria-label={`Readiness score: ${clamped}`}
      >
        <circle cx={70} cy={70} r={r} className="readiness-gauge-track" />
        <circle
          cx={70}
          cy={70}
          r={r}
          fill="none"
          strokeWidth={10}
          strokeLinecap="round"
          stroke={color}
          strokeDasharray={`${arcLen} ${circ - arcLen}`}
          strokeDashoffset={circ * 0.125}
          style={{
            transform: 'rotate(-135deg)',
            transformOrigin: '50% 50%',
            transition: 'stroke-dasharray 1s ease',
          }}
        />
        <text x={70} y={65} className="readiness-gauge-score">
          {clamped}
        </text>
        <text x={70} y={84} className="readiness-gauge-label">
          READINESS
        </text>
      </svg>
      <div style={{ fontSize: '0.78rem', color: 'var(--muted)', textAlign: 'center' }}>
        {clamped >= 75
          ? '✓ Interview ready'
          : clamped >= 50
            ? '⚡ Getting there'
            : '⚠ Needs practice'}
      </div>
    </div>
  );
}

// ─── Insights ─────────────────────────────────────────────────────────────────

const KIND_ICON: Record<string, string> = {
  positive: '✓',
  warning: '⚠',
  info: 'ℹ',
};

function InsightsCard({ insights }: { insights: InsightItem[] }) {
  if (!insights.length) return null;
  return (
    <div className="section-panel">
      <div className="card-header-row">
        <h2 className="card-header-title">AI Insights</h2>
        <BrainCircuit size={16} style={{ color: 'var(--accent)' }} aria-hidden="true" />
      </div>
      <ul className="insights-list" aria-label="Personalized insights" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {insights.map((item, i) => (
          <li key={i} className={`insight-item ${item.kind}`}>
            <span className="insight-icon" aria-hidden="true">
              {KIND_ICON[item.kind] ?? 'ℹ'}
            </span>
            {item.text}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ─── Activity timeline ────────────────────────────────────────────────────────

const EVENT_ICON: Record<string, string> = {
  session_created: '📝',
  session_completed: '✅',
  report_generated: '📊',
  resume_uploaded: '📄',
};

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function ActivityTimeline({ events }: { events: ActivityEvent[] }) {
  if (!events.length) return (
    <div style={{ color: 'var(--muted)', fontSize: '0.85rem', textAlign: 'center', padding: '1.5rem 0' }}>
      No recent activity
    </div>
  );
  return (
    <ol
      className="activity-timeline"
      aria-label="Activity timeline"
      style={{ listStyle: 'none', padding: 0, margin: 0 }}
    >
      {events.slice(0, 8).map((ev, i) => (
        <li key={i} className="activity-event">
          <div className="activity-event-track">
            <div className={`activity-event-dot type-${ev.event_type}`} aria-hidden="true">
              {EVENT_ICON[ev.event_type] ?? '•'}
            </div>
            <div className="activity-event-line" aria-hidden="true" />
          </div>
          <div className="activity-event-body">
            <p className="activity-event-title">{ev.title}</p>
            {ev.subtitle && <p className="activity-event-sub">{ev.subtitle}</p>}
            <p className="activity-event-time">{relativeTime(ev.created_at)}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

// ─── Weekly goal ──────────────────────────────────────────────────────────────

function WeeklyGoalCard({ completed, total }: { completed: number; total: number }) {
  const pct = Math.min(100, Math.round((completed / total) * 100));
  return (
    <div className="goal-card">
      <div className="card-header-row" style={{ marginBottom: 0 }}>
        <h2 className="card-header-title">Weekly Goal</h2>
        <span style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--primary)' }}>
          {completed}/{total}
        </span>
      </div>
      <div
        className="goal-progress-bar"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${completed} of ${total} interviews completed`}
      >
        <div className="goal-progress-fill" style={{ width: `${pct}%` }} />
      </div>
      <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--muted)' }}>
        {pct >= 100
          ? '🎉 Goal achieved this week!'
          : `${total - completed} more interview${total - completed !== 1 ? 's' : ''} to reach your weekly goal`}
      </p>
    </div>
  );
}

// ─── Time range tabs ──────────────────────────────────────────────────────────

type Range = '7d' | '30d' | '90d' | 'all';
const RANGE_DAYS: Record<Range, number> = { '7d': 7, '30d': 30, '90d': 90, all: Infinity };
const RANGE_LABELS: Record<Range, string> = { '7d': '7d', '30d': '30d', '90d': '90d', all: 'All' };

function filterTrends(trends: SessionTrendResponse[], range: Range): SessionTrendResponse[] {
  if (range === 'all') return trends;
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - RANGE_DAYS[range]);
  return trends.filter((t) => new Date(t.created_at) >= cutoff);
}

const ease = [0.4, 0, 0.2, 1] as [number, number, number, number];

// ─── Main page ────────────────────────────────────────────────────────────────

export function DashboardPage() {
  const { token } = useAuth();
  const [overview, setOverview] = useState<AnalyticsOverviewResponse | null>(null);
  const [trends, setTrends] = useState<SessionTrendResponse[]>([]);
  const [benchmark, setBenchmark] = useState<BenchmarkResponse | null>(null);
  const [insights, setInsights] = useState<InsightItem[]>([]);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<Range>('30d');

  const loadAnalytics = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    Promise.all([
      getAnalyticsOverview(token),
      getAnalyticsTrends(token),
      getBenchmarks(token),
      getInsights(token).catch(() => ({ insights: [] as InsightItem[] })),
      getActivityTimeline(token).catch(() => ({ events: [] as ActivityEvent[] })),
    ])
      .then(([ov, tr, bm, ins, act]) => {
        setOverview(ov);
        setTrends(tr);
        setBenchmark(bm);
        setInsights(ins.insights ?? []);
        setEvents(act.events ?? []);
      })
      .catch(() => setError('Unable to load analytics. Please try again.'))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard data-fetching pattern
    loadAnalytics();
  }, [loadAnalytics]);

  const filteredTrends = useMemo(() => filterTrends(trends, range), [trends, range]);

  const chartData = filteredTrends.map((t) => ({
    name: t.session_title.length > 16 ? t.session_title.slice(0, 16) + '…' : t.session_title,
    Overall: t.average_overall_score,
    Communication: t.average_communication_score,
    Technical: t.average_technical_score,
    'Problem Solving': t.average_problem_solving_score,
  }));

  const latestTrend = filteredTrends.at(-1);
  const radarData = latestTrend
    ? [
        { skill: 'Overall', score: latestTrend.average_overall_score ?? 0 },
        { skill: 'Communication', score: latestTrend.average_communication_score ?? 0 },
        { skill: 'Technical', score: latestTrend.average_technical_score ?? 0 },
        { skill: 'Problem Solving', score: latestTrend.average_problem_solving_score ?? 0 },
        { skill: 'Confidence', score: latestTrend.average_confidence_score ?? 0 },
      ]
    : null;

  const hasActivity = (overview?.total_responses_analyzed ?? 0) > 0;

  const readinessScore = useMemo(() => {
    if (!overview?.average_overall_score) return 0;
    return Math.min(100, Math.round(overview.average_overall_score * 10));
  }, [overview]);

  const weeklyCompleted = useMemo(() => {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - 7);
    return trends.filter((t) => new Date(t.created_at) >= cutoff).length;
  }, [trends]);

  if (loading) {
    return (
      <div className="page-container">
        <PageHeader />
        <StatGridSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-container">
        <PageHeader />
        <ErrorState message={error} onRetry={loadAnalytics} />
      </div>
    );
  }

  return (
    <motion.div
      className="page-container"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease }}
    >
      <PageHeader onRefresh={loadAnalytics} />

      {/* Primary stat row */}
      {overview && (
        <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
          <StatCard label="Total Sessions" value={overview.total_sessions} icon={<Activity size={16} />} />
          <StatCard label="Completed" value={overview.completed_sessions} icon={<BarChart2 size={16} />} accent="var(--success)" />
          <StatCard
            label="Avg Score"
            value={overview.average_overall_score != null ? `${overview.average_overall_score} / 10` : null}
            icon={<TrendingUp size={16} />}
            accent="var(--accent)"
          />
          <StatCard label="Responses Analysed" value={overview.total_responses_analyzed} icon={<BrainCircuit size={16} />} accent="#F59E0B" />
          <StatCard label="Strongest Skill" value={overview.strongest_skill} icon={<Award size={16} />} accent="var(--success)" />
          <StatCard label="Weakest Skill" value={overview.weakest_skill} icon={<Award size={16} />} accent="var(--error)" />
          {overview.improvement_score != null && (
            <StatCard
              label="Improvement"
              value={`${overview.improvement_score > 0 ? '+' : ''}${overview.improvement_score}`}
              icon={<TrendingUp size={16} />}
              accent={overview.improvement_score >= 0 ? 'var(--success)' : 'var(--error)'}
            />
          )}
        </div>
      )}

      {/* Benchmark row */}
      {benchmark && benchmark.user_average_score != null && (
        <div
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderLeft: '3px solid var(--primary)',
            borderRadius: 'var(--radius)',
            padding: '1rem 1.25rem',
            display: 'flex',
            gap: '2rem',
            flexWrap: 'wrap',
            alignItems: 'center',
            marginBottom: '1.5rem',
          }}
        >
          <div>
            <div className="stat-label" style={{ marginTop: 0, marginBottom: '0.2rem' }}>Your Avg Score</div>
            <div style={{ fontWeight: 800, fontSize: '1.25rem', color: 'var(--primary)' }}>
              {benchmark.user_average_score} / 10
            </div>
          </div>
          {benchmark.percentile_rank != null && (
            <div>
              <div className="stat-label" style={{ marginTop: 0, marginBottom: '0.2rem' }}>Percentile Rank</div>
              <div style={{ fontWeight: 800, fontSize: '1.25rem', color: 'var(--success-text)' }}>
                Top {(100 - benchmark.percentile_rank).toFixed(0)}%
              </div>
            </div>
          )}
          <div>
            <div className="stat-label" style={{ marginTop: 0, marginBottom: '0.2rem' }}>Platform Responses</div>
            <div style={{ fontWeight: 700, fontSize: '1.1rem', color: 'var(--text)' }}>
              {benchmark.total_platform_responses ?? '—'}
            </div>
          </div>
        </div>
      )}

      {/* Readiness gauge + Insights */}
      {hasActivity && (
        <div className="dashboard-widgets-row">
          <div className="section-panel">
            <div className="card-header-row">
              <h2 className="card-header-title">Interview Readiness</h2>
            </div>
            <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-start', flexWrap: 'wrap', marginBottom: '1rem' }}>
              <ReadinessGauge score={readinessScore} />
              {radarData && (
                <div style={{ flex: 1, minWidth: 140 }}>
                  <div className="skill-bar-list" style={{ gap: '0.55rem' }}>
                    {radarData.map((item, i) => {
                      const pct = Math.round((item.score / 10) * 100);
                      const colors = ['#3D7EFF', '#22C55E', '#F59E0B', '#EF4444', '#8B5CF6'];
                      return (
                        <div key={item.skill} className="skill-bar-row" style={{ gridTemplateColumns: '100px 1fr 32px' }}>
                          <span className="skill-bar-name" style={{ fontSize: '0.77rem' }}>{item.skill}</span>
                          <div className="skill-bar-track">
                            <div className="skill-bar-fill" style={{ width: `${pct}%`, background: colors[i % colors.length] }} />
                          </div>
                          <span className="skill-bar-val" style={{ fontSize: '0.74rem' }}>{item.score ?? '—'}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
            <WeeklyGoalCard completed={weeklyCompleted} total={3} />
          </div>

          <InsightsCard insights={insights} />
        </div>
      )}

      {/* Time range + trend charts */}
      {hasActivity && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
            <h2 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700 }}>Score Trends</h2>
            <div className="time-range-tabs" role="group" aria-label="Time range filter">
              {(Object.keys(RANGE_LABELS) as Range[]).map((r) => (
                <button
                  key={r}
                  type="button"
                  className={`time-range-tab${range === r ? ' active' : ''}`}
                  onClick={() => setRange(r)}
                  aria-pressed={range === r}
                >
                  {RANGE_LABELS[r]}
                </button>
              ))}
            </div>
          </div>

          <div className="charts-row">
            {chartData.length > 1 && (
              <div className="chart-card">
                <h2>Per-Session Scores</h2>
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={chartData} margin={{ top: 8, right: 16, left: -16, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'var(--muted)' }} />
                    <YAxis domain={[0, 10]} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
                    <Tooltip content={<ChartTooltip />} />
                    <Legend wrapperStyle={{ fontSize: '0.8rem' }} />
                    <Line type="monotone" dataKey="Overall" stroke="#3D7EFF" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="Communication" stroke="#22C55E" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="Technical" stroke="#F59E0B" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="Problem Solving" stroke="#EF4444" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            {radarData && (
              <div className="chart-card radar-chart-card">
                <h2>Skill Breakdown</h2>
                <ResponsiveContainer width="100%" height={280}>
                  <RadarChart data={radarData}>
                    <PolarGrid stroke="var(--border)" />
                    <PolarAngleAxis dataKey="skill" tick={{ fontSize: 11, fill: 'var(--muted)' }} />
                    <Radar name="Latest Session" dataKey="score" stroke="#3D7EFF" fill="#3D7EFF" fillOpacity={0.2} />
                    <Tooltip content={<ChartTooltip />} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </>
      )}

      {/* Activity timeline */}
      {events.length > 0 && (
        <div className="section-panel" style={{ marginTop: '1.25rem' }}>
          <div className="card-header-row">
            <h2 className="card-header-title">Recent Activity</h2>
          </div>
          <ActivityTimeline events={events} />
        </div>
      )}

      {/* Empty state */}
      {!hasActivity && (
        <div className="empty-state" style={{ marginTop: '1.5rem' }}>
          <div className="empty-illustration blue" aria-hidden="true">
            <BrainCircuit size={36} style={{ color: 'var(--primary)' }} />
          </div>
          <p className="empty-state-title">No interview data yet</p>
          <p className="empty-state-description">
            Complete your first interview session to see score trends, readiness score, and AI insights here.
          </p>
        </div>
      )}
    </motion.div>
  );
}

function PageHeader({ onRefresh }: { onRefresh?: () => void }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '1.5rem',
        gap: '1rem',
        flexWrap: 'wrap',
      }}
    >
      <div>
        <h1 style={{ margin: 0, fontSize: '1.35rem' }}>Dashboard</h1>
        <p style={{ margin: '0.2rem 0 0', color: 'var(--muted)', fontSize: '0.875rem' }}>
          Your interview readiness at a glance
        </p>
      </div>
      {onRefresh && (
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={onRefresh}
          aria-label="Refresh analytics"
        >
          <RefreshCw size={14} aria-hidden="true" />
          Refresh
        </button>
      )}
    </div>
  );
}
