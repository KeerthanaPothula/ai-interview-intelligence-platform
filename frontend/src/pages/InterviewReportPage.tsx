import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Award, BookOpen, Calendar, RefreshCw, TrendingUp } from 'lucide-react';
import {
  ApiError,
  generateCoachingPlan,
  generateReadiness,
  generateReport,
  getCoachingPlan,
  getReadiness,
  getReport,
  getSession,
} from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import type {
  CoachingPlanResponse,
  InterviewReadinessResponse,
  SessionDetailResponse,
  SessionReportResponse,
} from '../api/types';
import { StatGridSkeleton } from '../components/Skeleton';
import { ErrorState } from '../components/StateMessage';

function parseList(val: string | null | undefined): string[] {
  if (!val) return [];
  try {
    const p = JSON.parse(val);
    return Array.isArray(p) ? p.map(String) : [];
  } catch {
    return val.split('\n').filter(Boolean);
  }
}

function ScoreCircle({ label, value, color }: { label: string; value: string | number | null; color: string }) {
  const num = value != null ? parseFloat(String(value)) : null;
  const pct = num != null ? (num / 10) * 100 : 0;
  const r = 32;
  const circ = 2 * Math.PI * r;
  const arc = (pct / 100) * circ * 0.75;
  const gap = circ - arc;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.4rem' }}>
      <svg width={82} height={82} viewBox="0 0 82 82" role="img" aria-label={`${label}: ${value ?? '—'}`}>
        <circle cx={41} cy={41} r={r} fill="none" strokeWidth={7} stroke="var(--border)" />
        <circle
          cx={41}
          cy={41}
          r={r}
          fill="none"
          strokeWidth={7}
          strokeLinecap="round"
          stroke={color}
          strokeDasharray={`${arc} ${gap}`}
          strokeDashoffset={circ * 0.125}
          style={{ transform: 'rotate(-135deg)', transformOrigin: '50% 50%' }}
        />
        <text x={41} y={46} textAnchor="middle" fontSize={15} fontWeight={700} fill="var(--text)">
          {num != null ? num.toFixed(1) : '—'}
        </text>
      </svg>
      <span style={{ fontSize: '0.75rem', color: 'var(--muted)', textAlign: 'center', lineHeight: 1.3 }}>{label}</span>
    </div>
  );
}

function ReadinessBadge({ level, score }: { level: string | null; score: number | null }) {
  const color =
    level === 'High' ? 'var(--success)' :
    level === 'Medium' ? 'var(--warning)' :
    'var(--error-text)';
  return (
    <div style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '0.5rem',
      padding: '0.5rem 1rem',
      borderRadius: 'var(--radius)',
      background: 'var(--surface-2)',
      border: `1px solid ${color}40`,
    }}>
      <Award size={16} style={{ color }} aria-hidden="true" />
      <span style={{ fontSize: '0.875rem', fontWeight: 700, color }}>
        {level ?? 'Unknown'} Readiness
      </span>
      {score != null && (
        <span style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>
          ({score.toFixed(0)}%)
        </span>
      )}
    </div>
  );
}

type PlanTab = '7' | '14' | '30';

function CoachingPlanSection({ plan }: { plan: CoachingPlanResponse }) {
  const [tab, setTab] = useState<PlanTab>('7');
  const items: Record<PlanTab, string[]> = {
    '7': plan.plan_7_day ?? [],
    '14': plan.plan_14_day ?? [],
    '30': plan.plan_30_day ?? [],
  };
  const labels: Record<PlanTab, string> = { '7': '7-Day', '14': '14-Day', '30': '30-Day' };

  return (
    <div className="section-panel">
      <div className="card-header-row" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Calendar size={16} style={{ color: 'var(--primary)' }} aria-hidden="true" />
          <h2 className="card-header-title">Coaching Plan</h2>
        </div>
        <div className="time-range-tabs" role="group" aria-label="Plan duration">
          {(['7', '14', '30'] as PlanTab[]).map((t) => (
            <button
              key={t}
              type="button"
              className={`time-range-tab${tab === t ? ' active' : ''}`}
              onClick={() => setTab(t)}
              aria-pressed={tab === t}
            >
              {labels[t]}
            </button>
          ))}
        </div>
      </div>
      {items[tab].length > 0 ? (
        <ol style={{ margin: 0, paddingLeft: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
          {items[tab].map((item, i) => (
            <li key={i} style={{ fontSize: '0.875rem', color: 'var(--text-2)', lineHeight: 1.55 }}>
              {item}
            </li>
          ))}
        </ol>
      ) : (
        <p style={{ color: 'var(--muted)', fontSize: '0.875rem' }}>No plan items for this period.</p>
      )}
      {plan.focus_areas && plan.focus_areas.length > 0 && (
        <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border)' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.5rem' }}>
            Focus Areas
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
            {plan.focus_areas.map((fa) => (
              <span key={fa} className="skills-chip">{fa}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const ease = [0.4, 0, 0.2, 1] as [number, number, number, number];

function FadeUp({ delay = 0, children }: { delay?: number; children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, delay, ease }}
    >
      {children}
    </motion.div>
  );
}

export function InterviewReportPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const { token } = useAuth();
  const { showToast } = useToast();

  const [session, setSession] = useState<SessionDetailResponse | null>(null);
  const [report, setReport] = useState<SessionReportResponse | null>(null);
  const [readiness, setReadiness] = useState<InterviewReadinessResponse | null>(null);
  const [coaching, setCoaching] = useState<CoachingPlanResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [generatingReadiness, setGeneratingReadiness] = useState(false);
  const [generatingCoaching, setGeneratingCoaching] = useState(false);

  const load = useCallback(async () => {
    if (!token || !sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const [s, r, ri, cp] = await Promise.allSettled([
        getSession(sessionId, token),
        getReport(sessionId, token),
        getReadiness(sessionId, token),
        getCoachingPlan(sessionId, token),
      ]);
      if (s.status === 'fulfilled') setSession(s.value);
      else { setError('Unable to load this session.'); setLoading(false); return; }
      if (r.status === 'fulfilled') setReport(r.value);
      if (ri.status === 'fulfilled') setReadiness(ri.value);
      if (cp.status === 'fulfilled') setCoaching(cp.value);
    } finally {
      setLoading(false);
    }
  }, [token, sessionId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard data-fetching pattern
    load();
  }, [load]);

  async function handleGenerateReport() {
    if (!token || !sessionId) return;
    setGeneratingReport(true);
    try {
      const r = await generateReport(sessionId, token);
      setReport(r);
      showToast('Report generated.', 'success');
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : 'Unable to generate report.', 'error');
    } finally {
      setGeneratingReport(false);
    }
  }

  async function handleGenerateReadiness() {
    if (!token || !sessionId) return;
    setGeneratingReadiness(true);
    try {
      const r = await generateReadiness(sessionId, token);
      setReadiness(r);
      showToast('Readiness assessment ready.', 'success');
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : 'Unable to generate readiness assessment.', 'error');
    } finally {
      setGeneratingReadiness(false);
    }
  }

  async function handleGenerateCoaching() {
    if (!token || !sessionId) return;
    setGeneratingCoaching(true);
    try {
      const r = await generateCoachingPlan(sessionId, token);
      setCoaching(r);
      showToast('Coaching plan ready.', 'success');
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : 'Unable to generate coaching plan.', 'error');
    } finally {
      setGeneratingCoaching(false);
    }
  }

  if (loading) return (
    <div className="page-container">
      <div style={{ marginBottom: '1.5rem' }}><BackLink sessionId={sessionId} /></div>
      <StatGridSkeleton />
    </div>
  );

  if (error) return (
    <div className="page-container">
      <BackLink sessionId={sessionId} />
      <ErrorState message={error} onRetry={load} />
    </div>
  );

  const strengths = parseList(report?.strengths);
  const weaknesses = parseList(report?.weaknesses);
  const improvementPlan = parseList(report?.improvement_plan);

  const scoreColors: Record<string, string> = {
    Overall: 'var(--primary)',
    Communication: 'var(--success)',
    Technical: 'var(--warning)',
    'Problem Solving': 'var(--accent)',
    Confidence: '#EC4899',
  };

  return (
    <div className="page-container">
      {/* Header */}
      <FadeUp delay={0}>
        <div style={{ marginBottom: '1.5rem' }}>
          <BackLink sessionId={sessionId} />
          <h1 style={{ margin: '0.75rem 0 0.2rem', fontSize: '1.4rem' }}>
            {session?.title ?? 'Interview Report'}
          </h1>
          <p style={{ margin: 0, color: 'var(--muted)', fontSize: '0.875rem' }}>
            {session?.job_role} · {session ? new Date(session.created_at).toLocaleDateString() : ''}
          </p>
          {readiness && (
            <div style={{ marginTop: '0.75rem' }}>
              <ReadinessBadge level={readiness.readiness_level} score={readiness.readiness_score} />
            </div>
          )}
        </div>
      </FadeUp>

      {/* Score gauges */}
      <FadeUp delay={0.08}>
        {report ? (
          <div className="section-panel" style={{ marginBottom: '1.25rem' }}>
            <div className="card-header-row" style={{ marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <TrendingUp size={16} style={{ color: 'var(--primary)' }} aria-hidden="true" />
                <h2 className="card-header-title">Performance Scores</h2>
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={handleGenerateReport}
                disabled={generatingReport}
                aria-label="Regenerate report"
              >
                <RefreshCw size={13} aria-hidden="true" />
                {generatingReport ? 'Regenerating…' : 'Regenerate'}
              </button>
            </div>
            <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap', justifyContent: 'center' }}>
              <ScoreCircle label="Overall" value={report.final_score} color={scoreColors.Overall} />
              <ScoreCircle label="Communication" value={report.communication_score} color={scoreColors.Communication} />
              <ScoreCircle label="Technical" value={report.technical_score} color={scoreColors.Technical} />
              <ScoreCircle label="Problem Solving" value={report.problem_solving_score} color={scoreColors['Problem Solving']} />
              <ScoreCircle label="Confidence" value={report.confidence_score} color={scoreColors.Confidence} />
            </div>
          </div>
        ) : (
          <div className="section-panel" style={{ marginBottom: '1.25rem', textAlign: 'center', padding: '2.5rem' }}>
            <BookOpen size={32} style={{ color: 'var(--muted)', marginBottom: '0.75rem' }} aria-hidden="true" />
            <p style={{ margin: '0 0 1rem', color: 'var(--muted)' }}>No report yet. Generate a comprehensive AI report for this session.</p>
            <button type="button" className="btn btn-primary" onClick={handleGenerateReport} disabled={generatingReport}>
              {generatingReport ? 'Generating…' : 'Generate Report'}
            </button>
          </div>
        )}
      </FadeUp>

      <FadeUp delay={0.16}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem', marginBottom: '1.25rem' }}>
          {/* Strengths */}
          {(report || strengths.length > 0) && (
            <div className="section-panel">
              <h2 className="card-header-title" style={{ marginBottom: '0.75rem', color: 'var(--success)' }}>Strengths</h2>
              {strengths.length > 0 ? (
                <ul style={{ margin: 0, paddingLeft: '1.2rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  {strengths.map((s, i) => (
                    <li key={i} style={{ fontSize: '0.875rem', color: 'var(--text-2)', lineHeight: 1.5 }}>{s}</li>
                  ))}
                </ul>
              ) : (
                <p style={{ color: 'var(--muted)', fontSize: '0.875rem' }}>No strengths data — generate a report first.</p>
              )}
            </div>
          )}

          {/* Weaknesses */}
          {(report || weaknesses.length > 0) && (
            <div className="section-panel">
              <h2 className="card-header-title" style={{ marginBottom: '0.75rem', color: 'var(--warning)' }}>Areas to Improve</h2>
              {weaknesses.length > 0 ? (
                <ul style={{ margin: 0, paddingLeft: '1.2rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  {weaknesses.map((w, i) => (
                    <li key={i} style={{ fontSize: '0.875rem', color: 'var(--text-2)', lineHeight: 1.5 }}>{w}</li>
                  ))}
                </ul>
              ) : (
                <p style={{ color: 'var(--muted)', fontSize: '0.875rem' }}>No weaknesses data — generate a report first.</p>
              )}
            </div>
          )}
        </div>
      </FadeUp>

      {/* Overall Performance */}
      {report?.overall_performance && (
        <FadeUp delay={0.22}>
          <div className="section-panel" style={{ marginBottom: '1.25rem' }}>
            <h2 className="card-header-title" style={{ marginBottom: '0.75rem' }}>Overall Performance</h2>
            <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-2)', lineHeight: 1.7 }}>
              {report.overall_performance}
            </p>
          </div>
        </FadeUp>
      )}

      {/* Improvement Plan */}
      {improvementPlan.length > 0 && (
        <FadeUp delay={0.28}>
          <div className="section-panel" style={{ marginBottom: '1.25rem' }}>
            <h2 className="card-header-title" style={{ marginBottom: '0.75rem' }}>Improvement Plan</h2>
            <ol style={{ margin: 0, paddingLeft: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {improvementPlan.map((item, i) => (
                <li key={i} style={{ fontSize: '0.875rem', color: 'var(--text-2)', lineHeight: 1.55 }}>{item}</li>
              ))}
            </ol>
          </div>
        </FadeUp>
      )}

      {/* Readiness */}
      <FadeUp delay={0.34}>
        <div style={{ marginBottom: '1.25rem' }}>
          {readiness ? (
            <div className="section-panel">
              <div className="card-header-row" style={{ marginBottom: '0.75rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Award size={15} style={{ color: 'var(--primary)' }} aria-hidden="true" />
                  <h2 className="card-header-title">Readiness Assessment</h2>
                </div>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={handleGenerateReadiness}
                  disabled={generatingReadiness}
                  aria-label="Refresh readiness assessment"
                >
                  <RefreshCw size={13} aria-hidden="true" />
                  {generatingReadiness ? '…' : 'Refresh'}
                </button>
              </div>
              <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.25rem' }}>Level</div>
                  <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text)' }}>{readiness.readiness_level ?? '—'}</div>
                </div>
                {readiness.readiness_score != null && (
                  <div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.25rem' }}>Score</div>
                    <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--primary)' }}>{readiness.readiness_score.toFixed(0)}%</div>
                  </div>
                )}
                {readiness.percentile_rank != null && (
                  <div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.25rem' }}>Percentile</div>
                    <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--success)' }}>Top {(100 - readiness.percentile_rank).toFixed(0)}%</div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="section-panel" style={{ textAlign: 'center', padding: '1.5rem' }}>
              <p style={{ margin: '0 0 0.75rem', color: 'var(--muted)', fontSize: '0.875rem' }}>No readiness assessment yet.</p>
              <button type="button" className="btn btn-ghost btn-sm" onClick={handleGenerateReadiness} disabled={generatingReadiness}>
                {generatingReadiness ? 'Generating…' : 'Generate Readiness Assessment'}
              </button>
            </div>
          )}
        </div>
      </FadeUp>

      {/* Coaching Plan */}
      <FadeUp delay={0.40}>
        {coaching ? (
          <CoachingPlanSection plan={coaching} />
        ) : (
          <div className="section-panel" style={{ textAlign: 'center', padding: '1.5rem' }}>
            <p style={{ margin: '0 0 0.75rem', color: 'var(--muted)', fontSize: '0.875rem' }}>No coaching plan yet.</p>
            <button type="button" className="btn btn-ghost btn-sm" onClick={handleGenerateCoaching} disabled={generatingCoaching}>
              {generatingCoaching ? 'Generating…' : 'Generate Coaching Plan'}
            </button>
          </div>
        )}
      </FadeUp>
    </div>
  );
}

function BackLink({ sessionId }: { sessionId: string | undefined }) {
  return (
    <Link
      to={sessionId ? `/sessions/${sessionId}` : '/sessions'}
      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.85rem', color: 'var(--muted)', textDecoration: 'none' }}
    >
      <ArrowLeft size={14} aria-hidden="true" />
      Back to session
    </Link>
  );
}
