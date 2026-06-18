import { useEffect, useState } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getAnalyticsOverview, getAnalyticsTrends } from '../api/client';
import type { AnalyticsOverviewResponse, SessionTrendResponse } from '../api/types';
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([
      getAnalyticsOverview(token),
      getAnalyticsTrends(token),
    ])
      .then(([ov, tr]) => {
        setOverview(ov);
        setTrends(tr);
      })
      .catch(() => setError('Unable to load analytics. Please try again.'))
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) {
    return (
      <div className="page-container">
        <div className="spinner" aria-label="Loading analytics" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-container">
        <p className="error-message">{error}</p>
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

      {chartData.length > 1 && (
        <div className="chart-card">
          <h2>Score Trends</h2>
          <ResponsiveContainer width="100%" height={320}>
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

      {chartData.length <= 1 && overview?.total_responses_analyzed === 0 && (
        <p className="empty-state">
          Complete your first interview to see score trends here.
        </p>
      )}
    </div>
  );
}
