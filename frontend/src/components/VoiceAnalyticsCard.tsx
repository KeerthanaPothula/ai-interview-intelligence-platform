import type { VoiceAnalysisResponse } from '../api/types';

interface MetricRowProps {
  label: string;
  value: string;
}

function MetricRow({ label, value }: MetricRowProps) {
  return (
    <div className="voice-metric-row">
      <span className="voice-metric-label">{label}</span>
      <span className="voice-metric-value">{value}</span>
    </div>
  );
}

interface ConfidenceBadgeProps {
  score: number;
}

function ConfidenceBadge({ score }: ConfidenceBadgeProps) {
  const level = score >= 80 ? 'high' : score >= 55 ? 'mid' : 'low';
  const label = score >= 80 ? 'High Confidence' : score >= 55 ? 'Moderate' : 'Needs Work';
  return (
    <div className={`confidence-badge confidence-badge--${level}`} data-testid="confidence-badge">
      {score} / 100 — {label}
    </div>
  );
}

interface VoiceAnalyticsCardProps {
  voiceAnalysis: VoiceAnalysisResponse;
}

export function VoiceAnalyticsCard({ voiceAnalysis: v }: VoiceAnalyticsCardProps) {
  const fmt = (n: number | null | undefined, decimals = 1, unit = '') =>
    n != null ? `${n.toFixed(decimals)}${unit}` : '—';

  return (
    <div className="voice-analytics-card" data-testid="voice-analytics-card">
      <h3>Voice Analytics</h3>

      {v.confidence_score != null && (
        <ConfidenceBadge score={v.confidence_score} />
      )}

      <div className="voice-metrics">
        <MetricRow label="Speaking Rate" value={fmt(v.speaking_rate, 0, ' WPM')} />
        <MetricRow label="Avg Pause Duration" value={fmt(v.average_pause_duration, 1, 's')} />
        <MetricRow label="Total Pause Time" value={fmt(v.total_pause_time, 1, 's')} />
        <MetricRow label="Long Pauses (>2s)" value={v.long_pause_count != null ? String(v.long_pause_count) : '—'} />
        <MetricRow label="Filler Words" value={v.filler_word_count != null ? String(v.filler_word_count) : '—'} />
        <MetricRow
          label="Energy Consistency"
          value={v.energy_consistency != null ? `${Math.round(v.energy_consistency * 100)}%` : '—'}
        />
      </div>
    </div>
  );
}
