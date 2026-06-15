import type { InterviewAnalysisResponse } from '../api/types';

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

function ScoreRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="score-row">
      <span className="score-label">{label}</span>
      <span className="score-value">{Number(value).toFixed(1)} / 10</span>
    </div>
  );
}

export function AnalysisCard({ analysis }: { analysis: InterviewAnalysisResponse }) {
  const strengths = parseStringList(analysis.strengths);
  const weaknesses = parseStringList(analysis.weaknesses);

  return (
    <div className="analysis-card" data-testid="analysis-card">
      <h3>AI Analysis</h3>

      <div className="scores">
        <ScoreRow label="Overall Score" value={analysis.overall_score} />
        <ScoreRow label="Communication Score" value={analysis.communication_score} />
        <ScoreRow label="Technical Score" value={analysis.technical_score} />
        <ScoreRow label="Problem Solving Score" value={analysis.problem_solving_score} />
        <ScoreRow label="Confidence Score" value={analysis.confidence_score} />
      </div>

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

      {analysis.detailed_feedback && (
        <div className="analysis-section">
          <h4>Detailed Feedback</h4>
          <p>{analysis.detailed_feedback}</p>
        </div>
      )}
    </div>
  );
}
