import { useCallback, useEffect, useState } from 'react';
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
import { getAnalyticsOverview, getAnalyticsTrends, getBenchmarks } from '../api/client';
import { StatGridSkeleton } from '../components/Skeleton';
import { ErrorState } from '../components/StateMessage';
import type {
  AnalyticsOverviewResponse,
  BenchmarkResponse,
  SessionTrendResponse,
} from '../api/types';
import { useAuth } from '../context/AuthContext';

// --- Stat card with icon + optional trend ---

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

// --- Recharts custom tooltip ---

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string }) {
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

// --- Main page ---

export function DashboardPage() {
  const { token } = useAuth();
  const [overview, setOverview] = useState<AnalyticsOverviewResponse | null>(null);
  const [trends, setTrends] = useState<SessionTrendResponse[]>([]);
  const [benchmark, setBenchmark] = useState<BenchmarkResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAnalytics = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    Promise.all([
      getAnalyticsOverview(token),
      getAnalyticsTrends(token),
      getBenchmarks(token),
    ])
      .then(([ov, tr, bm]) => {
        setOverview(ov);
        setTrends(tr);
        setBenchmark(bm);
      })
      .catch(() => setError('Unable to load analytics. Please try again.'))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard data-fetching pattern
    loadAnalytics();
  }, [loadAnalytics]);

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

  const chartData = trends.map((t) => ({
    name: t.session_title.length > 18 ? t.session_title.slice(0, 18) + '…' : t.session_title,
    Overall: t.average_overall_score,
    Communication: t.average_communication_score,
    Technical: t.average_technical_score,
    'Problem Solving': t.average_problem_solving_score,
  }));

  const latestTrend = trends.at(-1);
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

  return (
    <div className="page-container">
      <PageHeader onRefresh={loadAnalytics} />

      {/* Primary stat row */}
      {overview && (
        <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
          <StatCard
            label="Total Sessions"
            value={overview.total_sessions}
            icon={<Activity size={16} />}
          />
          <StatCard
            label="Completed"
            value={overview.completed_sessions}
            icon={<BarChart2 size={16} />}
            accent="var(--success)"
          />
          <StatCard
            label="Avg Score"
            value={
              overview.average_overall_score != null
                ? `${overview.average_overall_score} / 10`
                : null
            }
            icon={<TrendingUp size={16} />}
            accent="var(--accent)"
          />
          <StatCard
            label="Responses Analysed"
            value={overview.total_responses_analyzed}
            icon={<BrainCircuit size={16} />}
            accent="#F59E0B"
          />
          <StatCard
            label="Strongest Skill"
            value={overview.strongest_skill}
            icon={<Award size={16} />}
            accent="var(--success)"
          />
          <StatCard
            label="Weakest Skill"
            value={overview.weakest_skill}
            icon={<Award size={16} />}
            accent="var(--error)"
          />
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
            <div className="stat-label" style={{ marginTop: 0, marginBottom: '0.2rem' }}>
              Your Avg Score
            </div>
            <div style={{ fontWeight: 800, fontSize: '1.25rem', color: 'var(--primary)' }}>
              {benchmark.user_average_score} / 10
            </div>
          </div>
          {benchmark.percentile_rank != null && (
            <div>
              <div className="stat-label" style={{ marginTop: 0, marginBottom: '0.2rem' }}>
                Percentile Rank
              </div>
              <div style={{ fontWeight: 800, fontSize: '1.25rem', color: 'var(--success-text)' }}>
                Top {(100 - benchmark.percentile_rank).toFixed(0)}%
              </div>
            </div>
          )}
          <div>
            <div className="stat-label" style={{ marginTop: 0, marginBottom: '0.2rem' }}>
              Platform Responses
            </div>
            <div style={{ fontWeight: 700, fontSize: '1.1rem', color: 'var(--text)' }}>
              {benchmark.total_platform_responses ?? '—'}
            </div>
          </div>
        </div>
      )}

      {/* Charts row */}
      {hasActivity && (
        <div className="charts-row">
          {chartData.length > 1 && (
            <div className="chart-card">
              <h2>Score Trends</h2>
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
                  <Radar
                    name="Latest Session"
                    dataKey="score"
                    stroke="#3D7EFF"
                    fill="#3D7EFF"
                    fillOpacity={0.2}
                  />
                  <Tooltip content={<ChartTooltip />} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {!hasActivity && (
        <div className="empty-state" style={{ marginTop: '1.5rem' }}>
          <BrainCircuit
            size={36}
            style={{ color: 'var(--muted)', marginBottom: '0.75rem' }}
            aria-hidden="true"
          />
          <p className="empty-state-title">No interview data yet</p>
          <p className="empty-state-description">
            Complete your first interview session to see score trends and analytics here.
          </p>
        </div>
      )}
    </div>
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
        <h1 style={{ margin: 0, fontSize: '1.35rem' }}>Analytics Dashboard</h1>
        <p style={{ margin: '0.2rem 0 0', color: 'var(--muted)', fontSize: '0.875rem' }}>
          Track your interview performance over time
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
