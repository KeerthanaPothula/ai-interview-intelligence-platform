import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const GITHUB_URL = 'https://github.com/mohankrishna0089/ai-interview-intelligence-platform';

const TECH_ITEMS = [
  'FastAPI', 'React 19', 'Gemini 1.5', 'Whisper', 'PostgreSQL',
  'Docker', 'Alembic', 'OpenTelemetry', 'SQLAlchemy', 'Vite', 'TypeScript', 'psycopg2',
];

const STEPS = [
  {
    n: '01',
    title: 'Upload your resume',
    body: 'Drop a PDF or DOCX. RAG indexes your experience so every question is precisely tailored to your background.',
  },
  {
    n: '02',
    title: 'Generate questions',
    body: 'Gemini crafts interview questions matched to the target role, job description, and your resume history.',
  },
  {
    n: '03',
    title: 'Answer & record',
    body: 'Type answers or upload audio. Whisper transcribes speech; Gemini evaluates clarity, depth, and confidence.',
  },
  {
    n: '04',
    title: 'Review your score',
    body: 'Receive a detailed readiness report: a weighted 0–10 score, identified strengths, gaps, and an improvement plan.',
  },
] as const;

const FEATURES = [
  {
    title: 'AI Resume Analysis',
    body: 'Upload PDF or DOCX. The platform indexes your resume with RAG so every generated question targets your actual experience.',
  },
  {
    title: 'Readiness Score',
    body: 'Transparent weighted score (0–10) from communication, technical depth, problem-solving, and confidence — no black-box ML.',
  },
  {
    title: 'Voice Analytics',
    body: 'Submit audio recordings. Whisper transcribes locally; Gemini analyses pace, filler words, and answer clarity.',
  },
  {
    title: 'AI Career Coach',
    body: 'After each session receive a personalised plan: specific strengths, identified gaps, and concrete next steps.',
  },
  {
    title: 'Live Interview Mode',
    body: 'Practice a conversational interview with follow-up questions generated in real time from your previous answers.',
  },
  {
    title: 'Analytics Dashboard',
    body: 'Track score trends, benchmark against session history, and visualise performance across all competency dimensions.',
  },
] as const;

const PROD_FEATURES = [
  {
    title: 'Security',
    points: ['JWT auth with expiry', 'CORS origin allowlist', 'Security headers middleware', 'File-type & size validation'],
  },
  {
    title: 'Testing',
    points: ['250+ backend tests', '81% backend coverage', '31 frontend component tests', 'CI-gated test suite'],
  },
  {
    title: 'CI / CD',
    points: ['GitHub Actions pipeline', 'Lint, type-check, test gates', 'Docker Compose stack', 'Automated migration checks'],
  },
  {
    title: 'Observability',
    points: ['Structured JSON logging', 'OpenTelemetry tracing', 'Prometheus /metrics endpoint', 'Readiness & health probes'],
  },
] as const;

function radarPt(cx: number, cy: number, r: number, deg: number): [number, number] {
  const rad = ((deg - 90) * Math.PI) / 180;
  return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
}

function penPoly(cx: number, cy: number, r: number): string {
  return Array.from({ length: 5 }, (_, i) => {
    const [x, y] = radarPt(cx, cy, r, i * 72);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
}

function DashboardMock() {
  const cx = 95;
  const cy = 85;
  const rMax = 60;
  const scores = [0.81, 0.87, 0.83, 0.85, 0.79];
  const labels = ['Comm.', 'Technical', 'Problem', 'Confidence', 'Clarity'];

  const dataPoints = scores
    .map((s, i) => {
      const [x, y] = radarPt(cx, cy, rMax * s, i * 72);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  const donutR = 28;
  const donutCirc = 2 * Math.PI * donutR;
  const donutFilled = donutCirc * 0.84;

  return (
    <div className="lp-dash-mock">
      <div className="lp-dash-header">
        <span className="lp-dash-title">Interview Readiness</span>
        <span className="lp-dash-score">8.4 / 10</span>
      </div>

      <div className="lp-dash-body">
        {/* Donut chart */}
        <div className="lp-dash-donut-wrap">
          <svg viewBox="0 0 70 70" width="70" height="70" aria-hidden="true">
            <circle cx="35" cy="35" r={donutR} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="7" />
            <circle
              cx="35" cy="35" r={donutR} fill="none"
              stroke="#22C55E" strokeWidth="7"
              strokeDasharray={`${donutFilled.toFixed(1)} ${donutCirc.toFixed(1)}`}
              strokeLinecap="round"
              transform="rotate(-90 35 35)"
            />
            <text x="35" y="40" textAnchor="middle" fontSize="13" fontWeight="700" fill="#F8FAFF">84%</text>
          </svg>
          <span className="lp-dash-donut-label">Overall</span>
        </div>

        {/* Radar chart */}
        <div className="lp-dash-radar-wrap">
          <svg viewBox="0 0 190 165" width="100%" aria-hidden="true">
            {/* Grid polygons */}
            {[0.25, 0.5, 0.75, 1].map((scale) => (
              <polygon
                key={scale}
                points={penPoly(cx, cy, rMax * scale)}
                fill="none"
                stroke="rgba(255,255,255,0.07)"
                strokeWidth="0.8"
              />
            ))}
            {/* Spokes */}
            {Array.from({ length: 5 }, (_, i) => {
              const [x, y] = radarPt(cx, cy, rMax, i * 72);
              return (
                <line
                  key={i}
                  x1={cx} y1={cy}
                  x2={x.toFixed(1)} y2={y.toFixed(1)}
                  stroke="rgba(255,255,255,0.07)"
                  strokeWidth="0.8"
                />
              );
            })}
            {/* Data polygon */}
            <polygon
              points={dataPoints}
              fill="rgba(37,99,235,0.22)"
              stroke="#2563EB"
              strokeWidth="1.5"
            />
            {/* Data dots */}
            {scores.map((s, i) => {
              const [x, y] = radarPt(cx, cy, rMax * s, i * 72);
              return <circle key={i} cx={x.toFixed(1)} cy={y.toFixed(1)} r="2.5" fill="#2563EB" />;
            })}
            {/* Labels */}
            {labels.map((label, i) => {
              const [x, y] = radarPt(cx, cy, rMax + 14, i * 72);
              const anchor = x < cx - 4 ? 'end' : x > cx + 4 ? 'start' : 'middle';
              return (
                <text
                  key={i}
                  x={x.toFixed(1)}
                  y={(y + 3).toFixed(1)}
                  textAnchor={anchor}
                  fontSize="7"
                  fill="rgba(248,250,255,0.45)"
                >
                  {label}
                </text>
              );
            })}
          </svg>
        </div>
      </div>

      {/* Score rows */}
      <div className="lp-dash-rows">
        {[
          { label: 'Communication', score: 8.1 },
          { label: 'Technical depth', score: 8.7 },
          { label: 'Problem solving', score: 8.3 },
          { label: 'Confidence', score: 8.5 },
        ].map(({ label, score }) => (
          <div key={label} className="lp-dash-row">
            <span className="lp-dash-row-label">{label}</span>
            <div className="lp-dash-row-bar">
              <div className="lp-dash-row-fill" style={{ width: `${score * 10}%` }} />
            </div>
            <span className="lp-dash-row-val">{score}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function useReveal() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            (e.target as HTMLElement).classList.add('lp-revealed');
            observer.unobserve(e.target);
          }
        });
      },
      { threshold: 0.1 },
    );
    root.querySelectorAll('.lp-reveal').forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);
  return ref;
}

export function LandingPage() {
  const { isAuthenticated } = useAuth();
  const rootRef = useReveal();

  return (
    <div className="lp-root" ref={rootRef}>

      {/* ── Nav ─────────────────────────────────────────── */}
      <header className="lp-nav">
        <div className="lp-nav-inner">
          <span className="lp-nav-logo">AIIP</span>
          <nav className="lp-nav-links" aria-label="Site navigation">
            <a href="#how" className="lp-nav-link">How it works</a>
            <a href="#features" className="lp-nav-link">Features</a>
            <a href="#engineering" className="lp-nav-link">Engineering</a>
          </nav>
          <div className="lp-nav-actions">
            {isAuthenticated ? (
              <Link to="/sessions" className="lp-btn lp-btn--sm lp-btn--primary">Dashboard</Link>
            ) : (
              <>
                <Link to="/login" className="lp-nav-link">Log in</Link>
                <Link to="/register" className="lp-btn lp-btn--sm lp-btn--primary">Get Started</Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* ── Hero ────────────────────────────────────────── */}
      <section className="lp-hero" aria-label="Hero">
        <div className="lp-hero-dots" aria-hidden="true" />
        <div className="lp-hero-inner">
          <div className="lp-hero-copy">
            <span className="lp-badge">v1.0.0 · Open Source</span>
            <h1 className="lp-h1">
              Interview intelligence,<br />
              <em className="lp-h1-em">engineered.</em>
            </h1>
            <p className="lp-hero-sub">
              Full-stack AI toolkit that turns practice sessions into measurable progress.
              Resume analysis, voice scoring, readiness reports — all in one platform.
            </p>
            <div className="lp-cta-row">
              {isAuthenticated ? (
                <Link to="/sessions" className="lp-btn lp-btn--primary lp-btn--lg">
                  Go to Dashboard →
                </Link>
              ) : (
                <>
                  <Link to="/register" className="lp-btn lp-btn--primary lp-btn--lg">
                    Get Started — it's free
                  </Link>
                  <Link to="/login" className="lp-btn lp-btn--ghost lp-btn--lg">
                    Log in
                  </Link>
                </>
              )}
              <a
                href={GITHUB_URL}
                className="lp-btn lp-btn--outline lp-btn--lg"
                target="_blank"
                rel="noopener noreferrer"
              >
                ★ GitHub
              </a>
            </div>
          </div>
          <div className="lp-hero-visual" aria-hidden="true">
            <DashboardMock />
          </div>
        </div>
      </section>

      {/* ── Tech strip ──────────────────────────────────── */}
      <div className="lp-tech-strip" aria-hidden="true">
        <div className="lp-tech-track">
          {[...TECH_ITEMS, ...TECH_ITEMS].map((name, i) => (
            <span key={i} className="lp-tech-item">{name}</span>
          ))}
        </div>
      </div>

      {/* ── How it works ────────────────────────────────── */}
      <section id="how" className="lp-section" aria-labelledby="how-heading">
        <div className="lp-container">
          <h2 id="how-heading" className="lp-h2 lp-reveal">How it works</h2>
          <p className="lp-sub lp-reveal">Four steps from resume to report.</p>
          <div className="lp-steps">
            {STEPS.map((step, i) => (
              <div
                key={step.n}
                className="lp-step lp-reveal"
                style={{ transitionDelay: `${i * 80}ms` }}
              >
                <span className="lp-step-n">{step.n}</span>
                <h3 className="lp-step-title">{step.title}</h3>
                <p className="lp-step-body">{step.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features ────────────────────────────────────── */}
      <section id="features" className="lp-section lp-section--alt" aria-labelledby="features-heading">
        <div className="lp-container">
          <h2 id="features-heading" className="lp-h2 lp-reveal">Everything you need to ace your next interview</h2>
          <p className="lp-sub lp-reveal">Six integrated features covering the full preparation lifecycle.</p>
          <div className="lp-features-grid">
            {FEATURES.map((f, i) => (
              <article
                key={f.title}
                className="lp-feature-card lp-reveal"
                style={{ transitionDelay: `${i * 60}ms` }}
              >
                <h3 className="lp-feature-title">{f.title}</h3>
                <p className="lp-feature-body">{f.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ── Engineering ─────────────────────────────────── */}
      <section id="engineering" className="lp-section" aria-labelledby="eng-heading">
        <div className="lp-container">
          <h2 id="eng-heading" className="lp-h2 lp-reveal">Production-grade engineering</h2>
          <p className="lp-sub lp-reveal">
            Not just a demo. Built with the same practices used in real production systems.
          </p>
          <div className="lp-eng-grid">
            {PROD_FEATURES.map((pf, i) => (
              <article
                key={pf.title}
                className="lp-eng-card lp-reveal"
                style={{ transitionDelay: `${i * 70}ms` }}
              >
                <h3 className="lp-eng-title">{pf.title}</h3>
                <ul className="lp-eng-list">
                  {pf.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ─────────────────────────────────────────── */}
      <section className="lp-cta-section" aria-label="Call to action">
        <div className="lp-cta-glow" aria-hidden="true" />
        <div className="lp-container lp-container--narrow">
          <h2 className="lp-cta-heading lp-reveal">Ready to prepare smarter?</h2>
          <p className="lp-cta-sub lp-reveal">
            Create a free account and run your first practice interview in under 5 minutes.
          </p>
          <div className="lp-cta-row lp-cta-row--center lp-reveal">
            {isAuthenticated ? (
              <Link to="/sessions" className="lp-btn lp-btn--primary lp-btn--lg">
                Go to Dashboard →
              </Link>
            ) : (
              <>
                <Link to="/register" className="lp-btn lp-btn--primary lp-btn--lg">
                  Get Started — it's free
                </Link>
                <a
                  href={GITHUB_URL}
                  className="lp-btn lp-btn--outline lp-btn--lg"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  ★ Star on GitHub
                </a>
              </>
            )}
          </div>
        </div>
      </section>

      {/* ── Footer ──────────────────────────────────────── */}
      <footer className="lp-footer">
        <div className="lp-footer-inner lp-container">
          <span className="lp-footer-brand">AI Interview Intelligence Platform</span>
          <nav className="lp-footer-nav" aria-label="Footer links">
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">GitHub</a>
            <Link to="/login">Log in</Link>
            <Link to="/register">Register</Link>
            <span aria-hidden="true">·</span>
            <span>MIT License</span>
            <span aria-hidden="true">·</span>
            <span>v1.0.0</span>
          </nav>
        </div>
      </footer>

    </div>
  );
}
