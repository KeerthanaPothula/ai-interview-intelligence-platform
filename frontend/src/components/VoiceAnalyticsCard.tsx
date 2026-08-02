import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { TranscriptResponse, VoiceAnalysisResponse } from '../api/types';

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

const CHART_COLORS: Record<string, string> = {
  Pace: '#3D7EFF',
  Energy: '#22C55E',
  Confidence: '#EC4899',
  Fluency: '#F59E0B',
  Steadiness: '#8B5CF6',
};

// Each axis is a linear normalization of a single raw metric onto a 0-100
// display scale so the five differently-unitted metrics (WPM, count,
// ratio, score) can share one chart. These are presentation-only —
// the exact figures remain visible in the metric rows below.
function buildChartData(v: VoiceAnalysisResponse) {
  const clamp = (n: number) => Math.max(0, Math.min(100, n));
  const rows: { metric: string; value: number }[] = [];

  if (v.speaking_rate != null) {
    rows.push({ metric: 'Pace', value: Math.round(clamp(((v.speaking_rate - 60) / (220 - 60)) * 100)) });
  }
  if (v.energy_consistency != null) {
    rows.push({ metric: 'Energy', value: Math.round(clamp(v.energy_consistency * 100)) });
  }
  if (v.confidence_score != null) {
    rows.push({ metric: 'Confidence', value: Math.round(clamp(v.confidence_score)) });
  }
  if (v.filler_word_count != null) {
    rows.push({ metric: 'Fluency', value: Math.round(clamp(100 - v.filler_word_count * 8)) });
  }
  if (v.long_pause_count != null) {
    rows.push({ metric: 'Steadiness', value: Math.round(clamp(100 - v.long_pause_count * 15)) });
  }
  return rows;
}

function buildExplanation(v: VoiceAnalysisResponse): string[] {
  const notes: string[] = [];

  if (v.speaking_rate != null) {
    if (v.speaking_rate < 110) notes.push('Your pace was slower than typical conversational speech — a few more words per minute would help you sound more engaged.');
    else if (v.speaking_rate > 165) notes.push('You spoke faster than the ideal interview pace — slowing down slightly would give answers more weight.');
    else notes.push('Your speaking pace sat comfortably in the ideal conversational range.');
  }

  if (v.filler_word_count != null) {
    if (v.filler_word_count >= 7) notes.push('Filler words ("um", "like", "you know") came up frequently, which can dilute how confident you sound.');
    else if (v.filler_word_count >= 3) notes.push('A moderate number of filler words appeared — worth trimming with practice.');
  }

  if (v.long_pause_count != null && v.long_pause_count >= 3) {
    notes.push('Several long pauses suggest you may have been searching for words — rehearsing key talking points can smooth this out.');
  }

  if (v.energy_consistency != null) {
    if (v.energy_consistency >= 0.7) notes.push('Your vocal energy stayed steady throughout, which reads as composed and confident.');
    else if (v.energy_consistency < 0.4) notes.push('Your vocal energy varied quite a bit — steadier delivery would strengthen your tone.');
  }

  return notes;
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: { metric: string; value: number } }[] }) {
  if (!active || !payload?.length) return null;
  const { metric, value } = payload[0].payload;
  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border-strong)', borderRadius: 8, padding: '0.5rem 0.75rem', fontSize: '0.8rem' }}>
      {metric}: <strong>{value}</strong>
    </div>
  );
}

interface VoiceAnalyticsCardProps {
  voiceAnalysis: VoiceAnalysisResponse;
  transcript?: TranscriptResponse | null;
}

export function VoiceAnalyticsCard({ voiceAnalysis: v, transcript }: VoiceAnalyticsCardProps) {
  const fmt = (n: number | null | undefined, decimals = 1, unit = '') =>
    n != null ? `${n.toFixed(decimals)}${unit}` : '—';

  const chartData = buildChartData(v);
  const explanation = buildExplanation(v);

  return (
    <div className="voice-analytics-card" data-testid="voice-analytics-card">
      <h3>Voice Analytics</h3>

      {v.confidence_score != null && (
        <ConfidenceBadge score={v.confidence_score} />
      )}

      {chartData.length > 0 && (
        <div
          style={{ height: 28 * chartData.length + 20, marginBottom: '0.75rem' }}
          role="img"
          aria-label={`Bar chart of normalized voice metrics: ${chartData.map((r) => `${r.metric} ${r.value}`).join(', ')}`}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 4 }}>
              <XAxis type="number" domain={[0, 100]} hide />
              <YAxis
                type="category"
                dataKey="metric"
                width={80}
                tick={{ fontSize: 12, fill: 'var(--muted)' }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--surface-2)' }} />
              <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={14}>
                {chartData.map((row) => (
                  <Cell key={row.metric} fill={CHART_COLORS[row.metric] ?? 'var(--primary)'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
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
        {transcript && (
          <MetricRow
            label="Response Length"
            value={
              transcript.duration_seconds != null
                ? `${transcript.word_count} words · ${transcript.duration_seconds}s`
                : `${transcript.word_count} words`
            }
          />
        )}
      </div>

      {explanation.length > 0 && (
        <div className="voice-explanation">
          {explanation.map((note, i) => (
            <p key={i}>{note}</p>
          ))}
        </div>
      )}
    </div>
  );
}
