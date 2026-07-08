import { useCallback, useEffect, useRef, useState } from 'react';
import { FileText, RefreshCw, Trash2, Upload } from 'lucide-react';
import {
  ApiError,
  analyzeResume,
  deleteResume,
  getCurrentResume,
  uploadResume,
} from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import type { ResumeAnalysisResponse, ResumeDocumentResponse } from '../api/types';

function AtsGauge({ score }: { score: number }) {
  const r = 52;
  const circ = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, score));
  // Use 75% of circle (270 deg) for visual gauge
  const arcLen = (clamped / 100) * circ * 0.75;
  const gap = circ - arcLen;
  const offset = circ * 0.125; // start at -135deg offset

  const color =
    clamped >= 80 ? 'var(--success)' : clamped >= 60 ? 'var(--primary)' : 'var(--warning)';

  return (
    <div className="readiness-gauge-wrap">
      <svg width={132} height={132} viewBox="0 0 132 132" className="readiness-gauge-svg" role="img" aria-label={`ATS score: ${score}`}>
        <circle cx={66} cy={66} r={r} className="readiness-gauge-track" />
        <circle
          cx={66}
          cy={66}
          r={r}
          fill="none"
          strokeWidth={10}
          strokeLinecap="round"
          stroke={color}
          strokeDasharray={`${arcLen} ${gap}`}
          strokeDashoffset={offset}
          style={{ transform: 'rotate(-135deg)', transformOrigin: '50% 50%', transition: 'stroke-dasharray 0.8s ease' }}
        />
        <text x={66} y={60} className="readiness-gauge-score" style={{ fontSize: '1.5rem' }}>
          {clamped}
        </text>
        <text x={66} y={80} className="readiness-gauge-label">
          ATS Score
        </text>
      </svg>
      <div style={{ fontSize: '0.78rem', color: 'var(--muted)', textAlign: 'center' }}>
        {clamped >= 80 ? '✓ Strong ATS compatibility' : clamped >= 60 ? '⚡ Good, room to improve' : '⚠ Low — needs work'}
      </div>
    </div>
  );
}

export function ResumePage() {
  const { token } = useAuth();
  const { showToast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);

  const [resume, setResume] = useState<ResumeDocumentResponse | null>(null);
  const [analysis, setAnalysis] = useState<ResumeAnalysisResponse | null>(null);
  const [loadingResume, setLoadingResume] = useState(true);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const loadResume = useCallback(async () => {
    if (!token) return;
    setLoadingResume(true);
    try {
      const r = await getCurrentResume(token);
      setResume(r);
    } catch {
      setResume(null);
    } finally {
      setLoadingResume(false);
    }
  }, [token]);

  const runAnalysis = useCallback(async () => {
    if (!token) return;
    setLoadingAnalysis(true);
    setAnalysisError(null);
    try {
      const a = await analyzeResume(token);
      setAnalysis(a);
    } catch (err) {
      setAnalysisError(
        err instanceof ApiError ? err.message : 'Unable to analyze resume. Please try again.',
      );
    } finally {
      setLoadingAnalysis(false);
    }
  }, [token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard data-fetching pattern
    loadResume();
  }, [loadResume]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- trigger analysis after resume loads
    if (resume) runAnalysis();
  }, [resume, runAnalysis]);

  async function handleFile(file: File) {
    if (!token) return;
    setUploading(true);
    try {
      const r = await uploadResume(file, token);
      setResume(r);
      setAnalysis(null);
      showToast('Resume uploaded successfully.', 'success');
    } catch (err) {
      showToast(
        err instanceof ApiError ? err.message : 'Upload failed. Please try again.',
        'error',
      );
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete() {
    if (!token) return;
    setDeleting(true);
    try {
      await deleteResume(token);
      setResume(null);
      setAnalysis(null);
      showToast('Resume deleted.', 'success');
    } catch (err) {
      showToast(
        err instanceof ApiError ? err.message : 'Unable to delete resume.',
        'error',
      );
    } finally {
      setDeleting(false);
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  if (loadingResume) {
    return (
      <div className="page-container">
        <PageHeader />
        <div className="section-panel" style={{ height: 200, animation: 'pulse 1.5s ease-in-out infinite' }} />
      </div>
    );
  }

  return (
    <div className="page-container">
      <PageHeader />

      {/* Upload zone (always visible) */}
      <div
        className={`resume-upload-zone${dragOver ? ' drag-over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Upload resume"
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') fileRef.current?.click(); }}
        style={{ marginBottom: '1.25rem' }}
      >
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx"
          style={{ display: 'none' }}
          onChange={handleInputChange}
          aria-hidden="true"
        />
        {uploading ? (
          <>
            <span className="spinner" aria-hidden="true" style={{ width: 28, height: 28, borderWidth: 3 }} />
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: '0.9rem' }}>Uploading…</p>
          </>
        ) : (
          <>
            <Upload size={28} style={{ color: 'var(--primary)' }} aria-hidden="true" />
            <p style={{ margin: 0, fontWeight: 600, color: 'var(--text)', fontSize: '0.95rem' }}>
              {resume ? 'Replace Resume' : 'Upload Resume'}
            </p>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: '0.82rem' }}>
              Drag &amp; drop or click to browse · PDF or DOCX · Max 5 MB
            </p>
          </>
        )}
      </div>

      {/* Current resume metadata */}
      {resume && (
        <div
          className="section-panel"
          style={{ display: 'flex', alignItems: 'center', gap: '0.875rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}
        >
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: 8,
              background: 'var(--primary-dim)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <FileText size={18} style={{ color: 'var(--primary)' }} aria-hidden="true" />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontSize: '0.9rem',
                fontWeight: 600,
                color: 'var(--text)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {resume.filename}
            </div>
            <div style={{ fontSize: '0.78rem', color: 'var(--muted)' }}>
              Uploaded {new Date(resume.created_at).toLocaleDateString()} · {resume.chunk_count} sections indexed
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0 }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={runAnalysis}
              disabled={loadingAnalysis}
              aria-label="Re-analyze resume"
            >
              <RefreshCw size={13} aria-hidden="true" />
              {loadingAnalysis ? 'Analyzing…' : 'Re-analyze'}
            </button>
            <button
              type="button"
              className="btn btn-sm"
              style={{ background: 'var(--error-bg)', color: 'var(--error-text)', border: '1px solid rgba(239,68,68,0.2)' }}
              onClick={handleDelete}
              disabled={deleting}
              aria-label="Delete resume"
            >
              <Trash2 size={13} aria-hidden="true" />
              {deleting ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        </div>
      )}

      {/* Analysis results */}
      {resume && (
        <>
          {loadingAnalysis && (
            <div className="section-panel" style={{ textAlign: 'center', padding: '3rem', color: 'var(--muted)' }}>
              <span className="spinner" aria-hidden="true" style={{ width: 28, height: 28, borderWidth: 3, margin: '0 auto 1rem' }} />
              <p style={{ margin: 0 }}>Analyzing your resume with AI…</p>
            </div>
          )}

          {analysisError && !loadingAnalysis && (
            <div
              className="section-panel"
              role="alert"
              style={{
                textAlign: 'center',
                color: 'var(--error-text)',
                background: 'var(--error-bg)',
                border: '1px solid rgba(239,68,68,0.2)',
              }}
            >
              {analysisError}
            </div>
          )}

          {analysis && !loadingAnalysis && (
            <div className="resume-analysis-grid">
              {/* Left: ATS gauge + word count */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div className="ats-gauge-card">
                  <AtsGauge score={analysis.ats_score} />
                  <div
                    style={{
                      fontSize: '0.8rem',
                      color: 'var(--muted)',
                      borderTop: '1px solid var(--border)',
                      paddingTop: '0.75rem',
                      width: '100%',
                      textAlign: 'center',
                    }}
                  >
                    {analysis.word_count.toLocaleString()} words
                  </div>
                </div>

                {/* Keywords */}
                {analysis.keywords.length > 0 && (
                  <div className="section-panel">
                    <h3 className="card-header-title" style={{ marginBottom: '0.75rem' }}>
                      Top Keywords
                    </h3>
                    <ul className="skills-chip-list" aria-label="Keywords found in resume">
                      {analysis.keywords.map((kw) => (
                        <li key={kw}>
                          <span className="skills-chip" style={{ background: 'var(--surface-2)', color: 'var(--text-2)', border: '1px solid var(--border)' }}>
                            {kw}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Right: skills + suggestions */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {/* Detected skills */}
                {analysis.skills.length > 0 && (
                  <div className="section-panel">
                    <h3 className="card-header-title" style={{ marginBottom: '0.75rem' }}>
                      Detected Skills ({analysis.skills.length})
                    </h3>
                    <ul className="skills-chip-list" aria-label="Skills detected in resume">
                      {analysis.skills.map((s) => (
                        <li key={s}>
                          <span className="skills-chip">{s}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Missing skills */}
                {analysis.missing_skills.length > 0 && (
                  <div className="section-panel">
                    <h3 className="card-header-title" style={{ marginBottom: '0.75rem' }}>
                      Consider Adding ({analysis.missing_skills.length})
                    </h3>
                    <ul className="skills-chip-list" aria-label="Skills to consider adding">
                      {analysis.missing_skills.map((s) => (
                        <li key={s}>
                          <span className="skills-chip missing">{s}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Suggestions */}
                {analysis.suggestions.length > 0 && (
                  <div className="section-panel">
                    <h3 className="card-header-title" style={{ marginBottom: '0.75rem' }}>
                      AI Suggestions
                    </h3>
                    <ul className="suggestions-list" aria-label="AI improvement suggestions">
                      {analysis.suggestions.map((s) => (
                        <li key={s} className="suggestion-item">
                          {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* No resume empty state */}
      {!resume && !loadingResume && (
        <div className="empty-state" style={{ marginTop: '2rem' }}>
          <div className="empty-illustration blue" aria-hidden="true">📄</div>
          <p className="empty-state-title">No resume uploaded yet</p>
          <p className="empty-state-description">
            Upload your resume to get an ATS score, skill analysis, and personalized improvement suggestions.
          </p>
        </div>
      )}
    </div>
  );
}

function PageHeader() {
  return (
    <div style={{ marginBottom: '1.5rem' }}>
      <h1 style={{ margin: 0, fontSize: '1.35rem' }}>Resume Analyzer</h1>
      <p style={{ margin: '0.2rem 0 0', color: 'var(--muted)', fontSize: '0.875rem' }}>
        AI-powered ATS analysis, skill detection, and improvement suggestions
      </p>
    </div>
  );
}
