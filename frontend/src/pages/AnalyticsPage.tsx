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
import { RefreshCw } from 'lucide-react';

const ease = [0.4, 0, 0.2, 1] as [number, number, number, number];
import { getAnalyticsOverview, getAnalyticsTrends, getBenchmarks } from '../api/client';
import { useAuth } from '../context/AuthContext';
import type { AnalyticsOverviewResponse, BenchmarkResponse, SessionTrendResponse } from '../api/types';
import { ChartTooltip } from '../components/ChartTooltip';
import { ErrorState } from '../components/StateMessage';
import { StatGridSkeleton } from '../components/Skeleton';

type Range = '7d' | '30d' | '90d' | 'all';

const RANGE_LABELS: Record<Range, string> = { '7d': '7 days', '30d': '30 days', '90d': '90 days', all: 'All time' };
const RANGE_DAYS: Record<Range, number> = { '7d': 7, '30d': 30, '90d': 90, all: Infinity };

function filterByRange(trends: SessionTrendResponse[], range: Range): SessionTrendResponse[] {
  if (range === 'all') return trends;
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - RANGE_DAYS[range]);
  return trends.filter((t) => new Date(t.created_at) >= cutoff);
}


export function AnalyticsPage() {
  const { token } = useAuth();
  const [range, setRange] = useState<Range>('30d');
  const [overview, setOverview] = useState<AnalyticsOverviewResponse | null>(null);
  const [trends, setTrends] = useState<SessionTrendResponse[]>([]);
  const [benchmark, setBenchmark] = useState<BenchmarkResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    Promise.all([getAnalyticsOverview(token), getAnalyticsTrends(token), getBenchmarks(token)])
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
    load();
  }, [load]);

  const filtered = useMemo(() => filterByRange(trends, range), [trends, range]);

  const chartData = filtered.map((t) => ({
    name: t.session_title.length > 16 ? t.session_title.slice(0, 16) + '…' : t.session_title,
    Overall: t.average_overall_score,
    Communication: t.average_communication_score,
    Technical: t.average_technical_score,
    Confidence: t.average_confidence_score,
  }));

  const avgBySkill = useMemo(() => {
    if (!filtered.length) return null;
    const sum = { comm: 0, tech: 0, ps: 0, conf: 0, count: 0 };
    for (const t of filtered) {
      if (t.average_overall_score != null) {
        sum.comm += t.average_communication_score ?? 0;
        sum.tech += t.average_technical_score ?? 0;
        sum.ps += t.average_problem_solving_score ?? 0;
        sum.conf += t.average_confidence_score ?? 0;
        sum.count++;
      }
    }
    if (!sum.count) return null;
    return {
      Communication: +(sum.comm / sum.count).toFixed(1),
      Technical: +(sum.tech / sum.count).toFixed(1),
      'Problem Solving': +(sum.ps / sum.count).toFixed(1),
      Confidence: +(sum.conf / sum.count).toFixed(1),
    };
  }, [filtered]);

  const radarData = avgBySkill
    ? Object.entries(avgBySkill).map(([skill, score]) => ({ skill, score }))
    : null;

  if (loading) return (
    <div className="page-container">
      <PageHeader range={range} onRange={setRange} onRefresh={load} />
      <StatGridSkeleton />
    </div>
  );

  if (error) return (
    <div className="page-container">
      <PageHeader range={range} onRange={setRange} onRefresh={load} />
      <ErrorState message={error} onRetry={load} />
    </div>
  );

  return (
    <motion.div
      className="page-container"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease }}
    >
      <PageHeader range={range} onRange={setRange} onRefresh={load} />

      {/* Summary stat row */}
      {overview && (
        <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', marginBottom: '1.5rem' }}>
          <StatTile label="Total Sessions" value={overview.total_sessions} />
          <StatTile label="Completed" value={overview.completed_sessions} accent="var(--success)" />
          <StatTile label="Avg Score" value={overview.average_overall_score != null ? `${overview.average_overall_score}/10` : null} accent="var(--accent)" />
          <StatTile label="Responses" value={overview.total_responses_analyzed} accent="var(--warning)" />
          {benchmark?.percentile_rank != null && (
            <StatTile label="Percentile" value={`Top ${(100 - benchmark.percentile_rank).toFixed(0)}%`} accent="var(--success)" />
          )}
        </div>
      )}

      {/* Score trend chart */}
      {chartData.length > 1 && (
        <div className="section-panel" style={{ marginBottom: '1.25rem' }}>
          <div className="card-header-row">
            <h2 className="card-header-title">Score Trends</h2>
            <span style={{ fontSize: '0.78rem', color: 'var(--muted)' }}>
              {filtered.length} session{filtered.length !== 1 ? 's' : ''}
            </span>
          </div>
          <div role="img" aria-label={`Line chart of overall, communication, technical, and confidence scores across ${filtered.length} session${filtered.length !== 1 ? 's' : ''}`}>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartData} margin={{ top: 4, right: 16, left: -20, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'var(--muted)' }} />
                <YAxis domain={[0, 10]} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
                <Tooltip content={<ChartTooltip decimals={1} />} />
                <Legend wrapperStyle={{ fontSize: '0.8rem' }} />
                <Line type="monotone" dataKey="Overall" stroke="#3D7EFF" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Communication" stroke="#22C55E" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Technical" stroke="#F59E0B" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Confidence" stroke="#8B5CF6" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className="analytics-grid">
        {/* Skill breakdown radar */}
        {radarData && (
          <div className="section-panel">
            <h2 className="card-header-title" style={{ marginBottom: '1rem' }}>Skill Breakdown</h2>
            <div role="img" aria-label="Radar chart of average scores by skill dimension">
              <ResponsiveContainer width="100%" height={250}>
                <RadarChart data={radarData}>
                  <PolarGrid stroke="var(--border)" />
                  <PolarAngleAxis dataKey="skill" tick={{ fontSize: 11, fill: 'var(--muted)' }} />
                  <Radar name="Average" dataKey="score" stroke="#3D7EFF" fill="#3D7EFF" fillOpacity={0.2} />
                  <Tooltip content={<ChartTooltip decimals={1} />} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Skill score distribution */}
        {avgBySkill && (
          <div className="section-panel">
            <h2 className="card-header-title" style={{ marginBottom: '1rem' }}>Average Scores</h2>
            <div className="skill-bar-list">
              {Object.entries(avgBySkill).map(([name, val], i) => {
                const colors = ['var(--primary)', 'var(--success)', 'var(--warning)', 'var(--accent)'];
                return (
                  <div key={name} className="skill-bar-row">
                    <span className="skill-bar-name">{name}</span>
                    <div className="skill-bar-track">
                      <div className="skill-bar-fill" style={{ width: `${(val / 10) * 100}%`, background: colors[i % colors.length] }} />
                    </div>
                    <span className="skill-bar-val">{val}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Benchmark comparison */}
        {benchmark && (
          <div className="section-panel">
            <h2 className="card-header-title" style={{ marginBottom: '1rem' }}>Benchmark</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <BenchmarkRow label="Your avg score" value={benchmark.user_average_score != null ? `${benchmark.user_average_score}/10` : '—'} accent="var(--primary)" />
              <BenchmarkRow label="Percentile rank" value={benchmark.percentile_rank != null ? `Top ${(100 - benchmark.percentile_rank).toFixed(0)}%` : '—'} accent="var(--success)" />
              <BenchmarkRow label="Platform responses" value={benchmark.total_platform_responses ?? 0} />
              <BenchmarkRow label="Your responses" value={benchmark.user_responses_analyzed ?? 0} />
            </div>
          </div>
        )}

        {/* Strongest / Weakest */}
        {overview && (overview.strongest_skill || overview.weakest_skill) && (
          <div className="section-panel">
            <h2 className="card-header-title" style={{ marginBottom: '1rem' }}>Skills Summary</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {overview.strongest_skill && (
                <div style={{ padding: '0.75rem', background: 'rgba(34,197,94,0.07)', border: '1px solid rgba(34,197,94,0.18)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--success)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.3rem' }}>Strongest</div>
                  <div style={{ fontWeight: 700, color: 'var(--text)' }}>{overview.strongest_skill}</div>
                </div>
              )}
              {overview.weakest_skill && (
                <div style={{ padding: '0.75rem', background: 'rgba(245,158,11,0.07)', border: '1px solid rgba(245,158,11,0.18)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--warning)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.3rem' }}>Needs Work</div>
                  <div style={{ fontWeight: 700, color: 'var(--text)' }}>{overview.weakest_skill}</div>
                </div>
              )}
              {overview.improvement_score != null && (
                <div style={{ fontSize: '0.85rem', color: 'var(--muted)', padding: '0.5rem 0.75rem', background: 'var(--surface-2)', borderRadius: 'var(--radius-sm)' }}>
                  Overall improvement: <strong style={{ color: overview.improvement_score >= 0 ? 'var(--success-text)' : 'var(--error-text)' }}>
                    {overview.improvement_score > 0 ? '+' : ''}{overview.improvement_score}
                  </strong> pts from first to latest session
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Empty state */}
      {!overview?.total_sessions && (
        <div className="empty-state" style={{ marginTop: '2rem' }}>
          <div className="empty-illustration blue" aria-hidden="true">📊</div>
          <p className="empty-state-title">No analytics data yet</p>
          <p className="empty-state-description">
            Complete interview sessions and submit audio responses to see your performance trends here.
          </p>
        </div>
      )}
    </motion.div>
  );
}

function StatTile({ label, value, accent = 'var(--primary)' }: { label: string; value: string | number | null; accent?: string }) {
  return (
    <div className="stat-card" style={{ padding: '1rem 1.25rem' }}>
      <div className="stat-label" style={{ marginTop: 0, marginBottom: '0.35rem' }}>{label}</div>
      <div className="stat-value" style={{ fontSize: '1.5rem', color: accent }}>{value ?? '—'}</div>
    </div>
  );
}

function BenchmarkRow({ label, value, accent = 'var(--text)' }: { label: string; value: string | number; accent?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ fontSize: '0.84rem', color: 'var(--muted)' }}>{label}</span>
      <span style={{ fontWeight: 700, fontSize: '0.9rem', color: accent }}>{value}</span>
    </div>
  );
}

function PageHeader({ range, onRange, onRefresh }: { range: Range; onRange: (r: Range) => void; onRefresh: () => void }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', gap: '1rem', flexWrap: 'wrap' }}>
      <div>
        <h1 style={{ margin: 0, fontSize: '1.35rem' }}>Analytics Center</h1>
        <p style={{ margin: '0.2rem 0 0', color: 'var(--muted)', fontSize: '0.875rem' }}>
          Deep-dive into your interview performance
        </p>
      </div>
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <div className="time-range-tabs" role="group" aria-label="Time range">
          {(Object.keys(RANGE_LABELS) as Range[]).map((r) => (
            <button
              key={r}
              type="button"
              className={`time-range-tab${range === r ? ' active' : ''}`}
              onClick={() => onRange(r)}
              aria-pressed={range === r}
            >
              {RANGE_LABELS[r]}
            </button>
          ))}
        </div>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onRefresh} aria-label="Refresh analytics">
          <RefreshCw size={14} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
