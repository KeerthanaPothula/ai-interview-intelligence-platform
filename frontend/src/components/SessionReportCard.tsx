import { useState } from 'react';
import { ApiError, generateReport } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import type { SessionReportResponse } from '../api/types';

function parseStringList(value: string | null): string[] {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    if (Array.isArray(parsed)) {
      return parsed.map((item) => String(item));
    }
    return [];
  } catch {
    return [];
  }
}

interface SessionReportCardProps {
  sessionId: string;
  report: SessionReportResponse | null;
  onGenerated: (report: SessionReportResponse) => void;
}

export function SessionReportCard({ sessionId, report, onGenerated }: SessionReportCardProps) {
  const { token } = useAuth();
  const { showToast } = useToast();
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    if (!token) return;
    setGenerating(true);
    setError(null);
    try {
      const result = await generateReport(sessionId, token);
      onGenerated(result);
      showToast('Report generated.', 'success');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to generate the report right now.');
    } finally {
      setGenerating(false);
    }
  }

  const strengths = parseStringList(report?.strengths ?? null);
  const weaknesses = parseStringList(report?.weaknesses ?? null);
  const improvementPlan = parseStringList(report?.improvement_plan ?? null);

  return (
    <section className="session-report-card" data-testid="session-report-card">
      <h2>Session Report</h2>
      <button type="button" onClick={handleGenerate} disabled={generating}>
        {generating ? 'Generating…' : report ? 'Regenerate Report' : 'Generate Report'}
      </button>
      {error && (
        <p className="status-error-text" role="alert">
          {error}
        </p>
      )}

      {report && (
        <div className="report-body">
          {report.final_score != null && (
            <div className="score-row">
              <span className="score-label">Final Score</span>
              <span className="score-value">{report.final_score.toFixed(1)} / 10</span>
            </div>
          )}
          {report.readiness_level && (
            <div className="score-row">
              <span className="score-label">Readiness Level</span>
              <span className="score-value">{report.readiness_level}</span>
            </div>
          )}
          {report.overall_performance && (
            <div className="analysis-section">
              <h4>Overall Performance</h4>
              <p>{report.overall_performance}</p>
            </div>
          )}
          {strengths.length > 0 && (
            <div className="analysis-section">
              <h4>Strengths</h4>
              <ul>
                {strengths.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {weaknesses.length > 0 && (
            <div className="analysis-section">
              <h4>Weaknesses</h4>
              <ul>
                {weaknesses.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {improvementPlan.length > 0 && (
            <div className="analysis-section">
              <h4>Improvement Plan</h4>
              <ul>
                {improvementPlan.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
