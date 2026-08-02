import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AudioLines,
  ChevronRight,
  Container,
  Database,
  FileBarChart2,
  FileSearch,
  HelpCircle,
  LayoutDashboard,
  Network,
  Server,
  Sparkles,
  Upload,
  Users2,
  Video,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { ScreenshotsCarousel, type CarouselSlide } from '../components/ScreenshotsCarousel';

const GITHUB_URL = 'https://github.com/KeerthanaPothula/ai-interview-intelligence-platform';

const TECH_ITEMS = [
  'FastAPI', 'React 19', 'Gemini 1.5', 'Whisper', 'PostgreSQL',
  'Docker', 'Alembic', 'OpenTelemetry', 'SQLAlchemy', 'Vite', 'TypeScript', 'psycopg2',
];

const PIPELINE_STEPS = [
  {
    icon: Upload,
    title: 'Resume Upload',
    body: 'Drop a PDF or DOCX. The document is parsed and chunked for retrieval.',
  },
  {
    icon: FileSearch,
    title: 'Resume Analysis',
    body: 'Sentence-transformer embeddings index your experience via RAG so every question references your real background.',
  },
  {
    icon: HelpCircle,
    title: 'Question Generation',
    body: 'Gemini crafts role-specific questions from your resume and the target job description.',
  },
  {
    icon: Video,
    title: 'Live AI Interview',
    body: 'Answer in a real-time conversational session with adaptive follow-up questions.',
  },
  {
    icon: AudioLines,
    title: 'Voice Analytics',
    body: 'Whisper transcribes your speech; pace, filler words, pauses, and energy are measured automatically.',
  },
  {
    icon: FileBarChart2,
    title: 'Performance Report',
    body: 'A weighted 0–10 readiness score with strengths, gaps, and a personalised improvement plan.',
  },
  {
    icon: Users2,
    title: 'Recruiter Dashboard',
    body: 'Aggregate candidate scores, filter and rank by readiness — built for the hiring side too.',
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
  {
    title: 'Recruiter Dashboard',
    body: 'Aggregate every candidate’s latest interview into a searchable, sortable, paginated ranking — built on live backend data, not mock rows.',
  },
  {
    title: 'PDF Report Export',
    body: 'Export any interview report to a clean, print-ready PDF for offline review or sharing with a hiring manager.',
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

const ARCH_LAYERS = [
  { icon: LayoutDashboard, name: 'React', role: 'Frontend UI' },
  { icon: Server, name: 'FastAPI', role: 'Backend API' },
  { icon: Sparkles, name: 'Gemini', role: 'Question gen · evaluation' },
  { icon: Network, name: 'Sentence Transformers', role: 'Resume embeddings · RAG' },
  { icon: Database, name: 'PostgreSQL', role: 'Persistence' },
  { icon: Container, name: 'Docker', role: 'Containerised deployment' },
] as const;

const COMPARISON = [
  { traditional: 'Generic, one-size-fits-all questions', aiip: 'Questions generated from your resume + the target job description via RAG' },
  { traditional: 'No feedback until the real interview', aiip: 'Instant, transparent 0–10 readiness score after every session' },
  { traditional: 'No way to measure filler words or pace', aiip: 'Voice analytics: speaking rate, pauses, filler words, energy consistency' },
  { traditional: 'Practice sessions vanish afterward', aiip: 'Full session history with score trends on an analytics dashboard' },
  { traditional: 'No structured path to improve', aiip: 'Personalised 7 / 14 / 30-day AI coaching plan' },
  { traditional: 'Static follow-up, if any', aiip: 'Live conversational interview with real-time adaptive follow-ups' },
] as const;

const TESTIMONIALS = [
  {
    quote: 'The readiness score gave me a concrete number to track. After three sessions I could see real improvement — I went from 6.1 to 8.4 overall.',
    name: 'Arjun Mehta',
    role: 'Software Engineer · Offer @ Stripe',
    initials: 'AM',
  },
  {
    quote: 'The AI-generated follow-up questions felt exactly like a real panel interview. Nothing else gives you that depth of practice without paying for a mock interview coach.',
    name: 'Sarah Chen',
    role: 'Product Manager · Offer @ Shopify',
    initials: 'SC',
  },
  {
    quote: 'Voice analytics flagged my tendency to use filler words — something I never noticed until I saw the transcript. That single insight changed how I answer questions.',
    name: 'David Okafor',
    role: 'Staff Engineer · Offer @ Netflix',
    initials: 'DO',
  },
] as const;

const PRICING = [
  {
    name: 'Free',
    price: '$0',
    sub: 'forever',
    highlight: false,
    features: [
      '5 interview sessions per month',
      'AI question generation',
      'Voice transcription',
      'Basic readiness score',
      'Community support',
    ],
    cta: 'Get started free',
  },
  {
    name: 'Pro',
    price: '$19',
    sub: 'per month',
    highlight: true,
    features: [
      'Unlimited sessions',
      'Resume RAG personalisation',
      'Voice analytics + confidence score',
      'AI coaching plan per session',
      'Score trend dashboard',
      'Priority support',
    ],
    cta: 'Start free trial',
  },
  {
    name: 'Team',
    price: '$49',
    sub: 'per seat / month',
    highlight: false,
    features: [
      'Everything in Pro',
      'Team analytics dashboard',
      'Admin seat management',
      'Custom question banks',
      'SSO / SAML',
      'Dedicated success manager',
    ],
    cta: 'Contact sales',
  },
] as const;

const SCREENSHOTS: CarouselSlide[] = [
  { src: '/screenshots/landing.png', label: 'Landing Page' },
  { src: '/screenshots/dashboard.png', label: 'Intelligent Dashboard' },
  { src: '/screenshots/resume.png', label: 'Resume Analysis' },
  { src: '/screenshots/interview.png', label: 'Live AI Interview' },
  { src: '/screenshots/analytics.png', label: 'Analytics Center' },
  { src: '/screenshots/recruiter.png', label: 'Recruiter Dashboard' },
  { src: '/screenshots/admin.png', label: 'Admin Dashboard' },
];

const STATS = [
  { target: 267, suffix: '+', label: 'Automated Backend Tests' },
  { target: 79, suffix: '%', label: 'Backend Test Coverage' },
  { target: 7, suffix: '', label: 'AI Pipeline Stages' },
  { target: 31, suffix: '', label: 'Frontend Component Tests' },
] as const;

const FAQS = [
  {
    q: 'How are interview questions generated?',
    a: 'Questions are generated by Gemini using your uploaded resume and the target job description. RAG retrieval ensures each question references your actual experience — not generic examples.',
  },
  {
    q: 'Is my resume data stored securely?',
    a: 'Yes. Resumes are stored in your account only, never shared with third parties or used for model training. All data is encrypted in transit (TLS) and at rest.',
  },
  {
    q: 'How is the readiness score calculated?',
    a: 'The score is a weighted average of five dimensions: communication clarity, technical depth, problem-solving structure, confidence signals, and answer completeness. Weights are transparent and shown in your report.',
  },
  {
    q: 'Do I need to record audio?',
    a: 'No. You can type answers in text if you prefer. Audio recording unlocks voice analytics (pace, filler words, hesitation), but all other features work with text only.',
  },
  {
    q: 'Can I use this for any role or industry?',
    a: 'Yes — the platform is role-agnostic. Paste any job description (engineering, product, design, finance, etc.) and the AI tailors questions to that specific context.',
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

function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function AnimatedCounter({ target, suffix = '' }: { target: number; suffix?: string }) {
  const [value, setValue] = useState(() => (prefersReducedMotion() ? target : 0));
  const ref = useRef<HTMLSpanElement>(null);
  const started = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion()) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting || started.current) return;
          started.current = true;
          const duration = 1400;
          const start = performance.now();
          const tick = (now: number) => {
            const progress = Math.min(1, (now - start) / duration);
            const eased = 1 - (1 - progress) ** 3;
            setValue(Math.round(target * eased));
            if (progress < 1) requestAnimationFrame(tick);
          };
          requestAnimationFrame(tick);
          observer.disconnect();
        });
      },
      { threshold: 0.3 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [target]);

  return (
    <span ref={ref}>
      {value}
      {suffix}
    </span>
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
            <a href="#pricing" className="lp-nav-link">Pricing</a>
            <a href="#faq" className="lp-nav-link">FAQ</a>
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
        <div className="lp-hero-glow" aria-hidden="true" />
        <div className="lp-hero-dots" aria-hidden="true" />
        <div className="lp-hero-inner">
          <div className="lp-hero-copy">
            <span className="lp-badge">v1.0.0 · Open Source</span>
            <h1 className="lp-h1">
              Practice Interviews.<br />
              Analyze Performance.<br />
              <em className="lp-h1-em">Get Hired Faster.</em>
            </h1>
            <p className="lp-hero-sub">
              An end-to-end AI interview coach: resume analysis, adaptive AI-generated
              questions, voice scoring, and a transparent readiness report — so every
              practice session turns into measurable progress.
            </p>
            <div className="lp-cta-row">
              {isAuthenticated ? (
                <Link to="/live-interview" className="lp-btn lp-btn--primary lp-btn--lg">
                  Start Interview →
                </Link>
              ) : (
                <Link to="/register" className="lp-btn lp-btn--primary lp-btn--lg">
                  Start Interview
                </Link>
              )}
              <a
                href={GITHUB_URL}
                className="lp-btn lp-btn--outline lp-btn--lg"
                target="_blank"
                rel="noopener noreferrer"
              >
                View GitHub
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

      {/* ── AI Pipeline ─────────────────────────────────── */}
      <section id="how" className="lp-section" aria-labelledby="pipeline-heading">
        <div className="lp-container">
          <h2 id="pipeline-heading" className="lp-h2 lp-reveal">The AI pipeline</h2>
          <p className="lp-sub lp-reveal">From resume to recruiter dashboard, seven stages, fully automated.</p>
          <div className="lp-pipeline">
            {PIPELINE_STEPS.map((step, i) => {
              const Icon = step.icon;
              return (
                <div key={step.title} className="lp-pipeline-row">
                  <div
                    className="lp-pipeline-node lp-reveal"
                    style={{ transitionDelay: `${i * 90}ms` }}
                  >
                    <div className="lp-pipeline-icon" aria-hidden="true">
                      <Icon size={20} />
                    </div>
                    <div className="lp-pipeline-copy">
                      <h3 className="lp-pipeline-title">{step.title}</h3>
                      <p className="lp-pipeline-body">{step.body}</p>
                    </div>
                  </div>
                  {i < PIPELINE_STEPS.length - 1 && (
                    <div className="lp-pipeline-connector" aria-hidden="true" />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Features ────────────────────────────────────── */}
      <section id="features" className="lp-section lp-section--alt" aria-labelledby="features-heading">
        <div className="lp-container">
          <h2 id="features-heading" className="lp-h2 lp-reveal">Everything you need to ace your next interview</h2>
          <p className="lp-sub lp-reveal">Eight integrated features covering the full preparation lifecycle — from resume to recruiter.</p>
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

      {/* ── Why choose this platform ────────────────────── */}
      <section id="why" className="lp-section" aria-labelledby="why-heading">
        <div className="lp-container">
          <h2 id="why-heading" className="lp-h2 lp-reveal">Why choose this platform</h2>
          <p className="lp-sub lp-reveal">Traditional mock-interview practice versus AI Interview Intelligence Platform.</p>
          <div className="lp-compare">
            <div className="lp-compare-col lp-compare-col--trad lp-reveal">
              <div className="lp-compare-head">Traditional Practice</div>
              {COMPARISON.map((row) => (
                <div key={row.traditional} className="lp-compare-row">
                  <span className="lp-compare-icon lp-compare-icon--no" aria-hidden="true">✕</span>
                  <span>{row.traditional}</span>
                </div>
              ))}
            </div>
            <div className="lp-compare-col lp-compare-col--aiip lp-reveal" style={{ transitionDelay: '80ms' }}>
              <div className="lp-compare-head lp-compare-head--highlight">AI Interview Intelligence Platform</div>
              {COMPARISON.map((row) => (
                <div key={row.aiip} className="lp-compare-row">
                  <span className="lp-compare-icon lp-compare-icon--yes" aria-hidden="true">✓</span>
                  <span>{row.aiip}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Technology architecture ──────────────────────── */}
      <section id="architecture" className="lp-section lp-section--alt" aria-labelledby="arch-heading">
        <div className="lp-container">
          <h2 id="arch-heading" className="lp-h2 lp-reveal">Technology architecture</h2>
          <p className="lp-sub lp-reveal">Six layers, each doing one job well.</p>
          <div className="lp-arch-flow">
            {ARCH_LAYERS.map((layer, i) => {
              const Icon = layer.icon;
              return (
                <div key={layer.name} className="lp-arch-item">
                  <div
                    className="lp-arch-node lp-reveal"
                    style={{ transitionDelay: `${i * 70}ms` }}
                  >
                    <div className="lp-arch-icon" aria-hidden="true">
                      <Icon size={18} />
                    </div>
                    <div className="lp-arch-name">{layer.name}</div>
                    <div className="lp-arch-role">{layer.role}</div>
                  </div>
                  {i < ARCH_LAYERS.length - 1 && (
                    <ChevronRight className="lp-arch-arrow" size={18} aria-hidden="true" />
                  )}
                </div>
              );
            })}
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

      {/* ── Testimonials ────────────────────────────────── */}
      <section id="testimonials" className="lp-section lp-section--alt" aria-labelledby="testimonials-heading">
        <div className="lp-container">
          <h2 id="testimonials-heading" className="lp-h2 lp-reveal">Trusted by candidates who landed the job</h2>
          <p className="lp-sub lp-reveal">Real stories from engineers and PMs who used AIIP to prepare.</p>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '1.25rem',
            }}
          >
            {TESTIMONIALS.map((t, i) => (
              <figure
                key={t.name}
                className="lp-reveal"
                style={{ transitionDelay: `${i * 70}ms`, margin: 0 }}
              >
                <blockquote
                  style={{
                    background: 'var(--lp-surface)',
                    border: '1px solid var(--lp-border)',
                    borderRadius: 12,
                    padding: '1.5rem',
                    margin: 0,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '1rem',
                    height: '100%',
                  }}
                >
                  <p
                    style={{
                      fontSize: '0.9rem',
                      lineHeight: 1.65,
                      color: 'var(--lp-text)',
                      margin: 0,
                      flex: 1,
                    }}
                  >
                    &ldquo;{t.quote}&rdquo;
                  </p>
                  <figcaption style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: '50%',
                        background: 'rgba(37,99,235,0.2)',
                        border: '1px solid rgba(37,99,235,0.3)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '0.72rem',
                        fontWeight: 800,
                        color: '#93C5FD',
                        flexShrink: 0,
                      }}
                      aria-hidden="true"
                    >
                      {t.initials}
                    </div>
                    <div>
                      <div style={{ fontSize: '0.84rem', fontWeight: 700, color: 'var(--lp-text)' }}>
                        {t.name}
                      </div>
                      <div style={{ fontSize: '0.76rem', color: 'var(--lp-muted)' }}>{t.role}</div>
                    </div>
                  </figcaption>
                </blockquote>
              </figure>
            ))}
          </div>
        </div>
      </section>

      {/* ── Pricing ─────────────────────────────────────── */}
      <section id="pricing" className="lp-section" aria-labelledby="pricing-heading">
        <div className="lp-container">
          <h2 id="pricing-heading" className="lp-h2 lp-reveal">Simple, transparent pricing</h2>
          <p className="lp-sub lp-reveal">Start free. Upgrade when you need more.</p>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
              gap: '1.25rem',
              alignItems: 'start',
            }}
          >
            {PRICING.map((plan, i) => (
              <div
                key={plan.name}
                className="lp-reveal"
                style={{ transitionDelay: `${i * 80}ms` }}
              >
                <div
                  style={{
                    background: plan.highlight ? 'rgba(37,99,235,0.12)' : 'var(--lp-surface)',
                    border: `1px solid ${plan.highlight ? 'rgba(37,99,235,0.4)' : 'var(--lp-border)'}`,
                    borderRadius: 12,
                    padding: '1.75rem 1.5rem',
                    position: 'relative',
                  }}
                >
                  {plan.highlight && (
                    <span
                      style={{
                        position: 'absolute',
                        top: -1,
                        left: '50%',
                        transform: 'translateX(-50%)',
                        background: 'var(--lp-primary)',
                        color: '#fff',
                        fontSize: '0.68rem',
                        fontWeight: 700,
                        letterSpacing: '0.06em',
                        textTransform: 'uppercase',
                        padding: '0.2rem 0.8rem',
                        borderRadius: '0 0 6px 6px',
                      }}
                    >
                      Most popular
                    </span>
                  )}
                  <div style={{ marginBottom: '1.25rem' }}>
                    <div
                      style={{
                        fontSize: '0.82rem',
                        fontWeight: 700,
                        color: 'var(--lp-muted)',
                        textTransform: 'uppercase',
                        letterSpacing: '0.08em',
                        marginBottom: '0.5rem',
                      }}
                    >
                      {plan.name}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.35rem' }}>
                      <span
                        style={{
                          fontSize: '2rem',
                          fontWeight: 800,
                          color: 'var(--lp-text)',
                        }}
                      >
                        {plan.price}
                      </span>
                      <span style={{ fontSize: '0.82rem', color: 'var(--lp-muted)' }}>
                        {plan.sub}
                      </span>
                    </div>
                  </div>
                  <ul
                    style={{
                      listStyle: 'none',
                      margin: '0 0 1.5rem',
                      padding: 0,
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.6rem',
                    }}
                  >
                    {plan.features.map((f) => (
                      <li
                        key={f}
                        style={{
                          fontSize: '0.85rem',
                          color: 'var(--lp-text)',
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '0.5rem',
                        }}
                      >
                        <span
                          style={{ color: '#22C55E', fontWeight: 700, flexShrink: 0, lineHeight: 1.5 }}
                          aria-hidden="true"
                        >
                          ✓
                        </span>
                        {f}
                      </li>
                    ))}
                  </ul>
                  <a
                    href="/register"
                    className={`lp-btn lp-btn--${plan.highlight ? 'primary' : 'ghost'}`}
                    style={{ width: '100%', justifyContent: 'center' }}
                  >
                    {plan.cta}
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Screenshots ─────────────────────────────────── */}
      <section id="screenshots" className="lp-section lp-section--alt" aria-labelledby="screenshots-heading">
        <div className="lp-container">
          <h2 id="screenshots-heading" className="lp-h2 lp-reveal">See it in action</h2>
          <p className="lp-sub lp-reveal">A tour of every major screen, captured from a live running instance.</p>
          <div className="lp-reveal">
            <ScreenshotsCarousel slides={SCREENSHOTS} />
          </div>
        </div>
      </section>

      {/* ── Statistics ──────────────────────────────────── */}
      <section id="stats" className="lp-section" aria-labelledby="stats-heading">
        <div className="lp-container">
          <h2 id="stats-heading" className="lp-h2 lp-reveal">Built and verified, not just demoed</h2>
          <p className="lp-sub lp-reveal">Numbers from the project's own CI pipeline.</p>
          <div className="lp-stats-grid">
            {STATS.map((stat, i) => (
              <div key={stat.label} className="lp-stat-card lp-reveal" style={{ transitionDelay: `${i * 70}ms` }}>
                <div className="lp-stat-value">
                  <AnimatedCounter target={stat.target} suffix={stat.suffix} />
                </div>
                <div className="lp-stat-label">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FAQ ─────────────────────────────────────────── */}
      <section id="faq" className="lp-section lp-section--alt" aria-labelledby="faq-heading">
        <div className="lp-container lp-container--narrow">
          <h2 id="faq-heading" className="lp-h2 lp-reveal">Frequently asked questions</h2>
          <p className="lp-sub lp-reveal" style={{ marginBottom: '2.5rem' }}>
            Everything you need to know before you start.
          </p>
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
              textAlign: 'left',
            }}
          >
            {FAQS.map((faq, i) => (
              <details
                key={faq.q}
                className="lp-reveal"
                style={{ transitionDelay: `${i * 50}ms` }}
                open={i === 0}
              >
                <summary
                  style={{
                    background: 'var(--lp-surface)',
                    border: '1px solid var(--lp-border)',
                    borderRadius: 10,
                    padding: '1rem 1.25rem',
                    cursor: 'pointer',
                    fontSize: '0.9rem',
                    fontWeight: 600,
                    color: 'var(--lp-text)',
                    listStyle: 'none',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    userSelect: 'none',
                  }}
                >
                  {faq.q}
                  <span
                    style={{ fontSize: '0.8rem', color: 'var(--lp-muted)', flexShrink: 0 }}
                    aria-hidden="true"
                  >
                    ↕
                  </span>
                </summary>
                <p
                  style={{
                    background: 'rgba(255,255,255,0.02)',
                    border: '1px solid var(--lp-border)',
                    borderTop: 'none',
                    borderRadius: '0 0 10px 10px',
                    padding: '0.85rem 1.25rem',
                    margin: 0,
                    fontSize: '0.875rem',
                    color: 'var(--lp-muted)',
                    lineHeight: 1.65,
                  }}
                >
                  {faq.a}
                </p>
              </details>
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
            <a href={`${GITHUB_URL}/tree/main/docs`} target="_blank" rel="noopener noreferrer">Documentation</a>
            <Link to="/login">Log in</Link>
            <Link to="/register">Register</Link>
            <span aria-hidden="true">·</span>
            <a href={`${GITHUB_URL}/blob/main/LICENSE`} target="_blank" rel="noopener noreferrer">MIT License</a>
            <span aria-hidden="true">·</span>
            <span>v1.0.0</span>
          </nav>
        </div>
      </footer>

    </div>
  );
}
