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
import { getAnalyticsOverview, getAnalyticsTrends, getBenchmarks } from '../api/client';
import { StatGridSkeleton } from '../components/Skeleton';
import { ErrorState } from '../components/StateMessage';
import type {
  AnalyticsOverviewResponse,
  BenchmarkResponse,
  SessionTrendResponse,
} from '../api/types';
import { useAuth } from '../context/AuthContext';

function StatCard({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value ?? '—'}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

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
        <h1>Analytics Dashboard</h1>
        <StatGridSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-container">
        <h1>Analytics Dashboard</h1>
        <ErrorState message={error} onRetry={loadAnalytics} />
      </div>
    );
  }

  const chartData = trends.map((t) => ({
    name: t.session_title.length > 20 ? t.session_title.slice(0, 20) + '…' : t.session_title,
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

  return (
    <div className="page-container">
      <h1>Analytics Dashboard</h1>

      {overview && (
        <div className="stat-grid">
          <StatCard label="Total Sessions" value={overview.total_sessions} />
          <StatCard label="Completed Sessions" value={overview.completed_sessions} />
          <StatCard
            label="Avg Overall Score"
            value={overview.average_overall_score != null ? `${overview.average_overall_score} / 10` : null}
          />
          <StatCard label="Responses Analysed" value={overview.total_responses_analyzed} />
          <StatCard label="Strongest Skill" value={overview.strongest_skill} />
          <StatCard label="Weakest Skill" value={overview.weakest_skill} />
          <StatCard
            label="Improvement"
            value={
              overview.improvement_score != null
                ? `${overview.improvement_score > 0 ? '+' : ''}${overview.improvement_score}`
                : null
            }
          />
        </div>
      )}

      {benchmark && benchmark.user_average_score != null && (
        <div className="stat-grid benchmark-grid">
          <StatCard
            label="Your Avg Score"
            value={`${benchmark.user_average_score} / 10`}
          />
          <StatCard
            label="Percentile Rank"
            value={
              benchmark.percentile_rank != null
                ? `Top ${(100 - benchmark.percentile_rank).toFixed(0)}%`
                : null
            }
          />
          <StatCard
            label="Platform Responses"
            value={benchmark.total_platform_responses}
          />
        </div>
      )}

      <div className="charts-row">
        {chartData.length > 1 && (
          <div className="chart-card">
            <h2>Score Trends</h2>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData} margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #e0e0e0)" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis domain={[0, 10]} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="Overall" stroke="#2f5dd4" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Communication" stroke="#10b981" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Technical" stroke="#f59e0b" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Problem Solving" stroke="#ef4444" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {radarData && (
          <div className="chart-card radar-chart-card">
            <h2>Skill Breakdown</h2>
            <ResponsiveContainer width="100%" height={300}>
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="skill" tick={{ fontSize: 12 }} />
                <Radar
                  name="Latest Session"
                  dataKey="score"
                  stroke="#2f5dd4"
                  fill="#2f5dd4"
                  fillOpacity={0.25}
                />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {chartData.length <= 1 && overview?.total_responses_analyzed === 0 && (
        <p className="empty-state">
          Complete your first interview to see score trends here.
        </p>
      )}
    </div>
  );
}
