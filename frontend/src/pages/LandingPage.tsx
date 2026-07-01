import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const FEATURES = [
  {
    icon: '📄',
    title: 'AI Resume Analysis',
    description:
      'Upload your PDF or DOCX resume. The platform indexes it with RAG so every generated question is tailored to your actual experience.',
  },
  {
    icon: '🎯',
    title: 'Interview Readiness Score',
    description:
      'A transparent weighted score (0–10) computed from your communication, technical depth, problem-solving, and confidence signals — no black-box ML.',
  },
  {
    icon: '🎙️',
    title: 'Voice Analytics',
    description:
      'Submit audio recordings for each question. Whisper transcribes them locally; Gemini analyses pace, filler words, and clarity.',
  },
  {
    icon: '🤖',
    title: 'AI Career Coach',
    description:
      'After each session, receive a personalised improvement plan: specific strengths, identified gaps, and concrete next steps.',
  },
  {
    icon: '💬',
    title: 'Live Interview Mode',
    description:
      'Practice a fully conversational interview with follow-up questions generated in real time based on your previous answers.',
  },
  {
    icon: '📊',
    title: 'Recruiter Dashboard',
    description:
      'Track score trends, benchmark yourself against session history, and visualise performance across all competency dimensions.',
  },
] as const;

const TECH_STACK = [
  { name: 'FastAPI', desc: 'Backend API' },
  { name: 'React 19', desc: 'Frontend UI' },
  { name: 'Gemini', desc: 'LLM / AI' },
  { name: 'Whisper', desc: 'Speech-to-text' },
  { name: 'PostgreSQL', desc: 'Database' },
  { name: 'Docker', desc: 'Containerisation' },
  { name: 'Alembic', desc: 'Migrations' },
  { name: 'OpenTelemetry', desc: 'Observability' },
] as const;

const PROD_FEATURES = [
  {
    icon: '🔒',
    title: 'Security',
    points: ['JWT auth with expiry', 'CORS origin allowlist', 'Security headers middleware', 'File-type & size validation'],
  },
  {
    icon: '✅',
    title: 'Testing',
    points: ['250+ backend tests', '81% backend coverage', '31 frontend component tests', 'End-to-end Playwright suite'],
  },
  {
    icon: '⚙️',
    title: 'CI/CD',
    points: ['GitHub Actions pipeline', 'Lint, type-check, test gates', 'Docker Compose stack', 'Automated migration checks'],
  },
  {
    icon: '📡',
    title: 'Observability',
    points: ['Structured JSON logging', 'OpenTelemetry tracing', 'Prometheus /metrics endpoint', 'Readiness & health probes'],
  },
] as const;

export function LandingPage() {
  const { isAuthenticated } = useAuth();
  const githubUrl = 'https://github.com/mohankrishna0089/ai-interview-intelligence-platform';

  return (
    <div className="landing-page">
      {/* ---------------------------------------------------------------- */}
      {/* Hero                                                              */}
      {/* ---------------------------------------------------------------- */}
      <section className="landing-hero" aria-label="Hero">
        <div className="landing-hero-content">
          <div className="landing-badge">v1.0.0 · Open Source</div>
          <h1 className="landing-headline">
            AI Interview
            <br />
            Intelligence Platform
          </h1>
          <p className="landing-tagline">
            Prepare smarter. Interview better.
            <br />
            Full-stack AI toolkit that turns practice sessions into measurable progress.
          </p>
          <div className="landing-cta-row">
            {isAuthenticated ? (
              <Link to="/sessions" className="cta-btn cta-btn--primary">
                Go to Dashboard →
              </Link>
            ) : (
              <>
                <Link to="/register" className="cta-btn cta-btn--primary">
                  Get Started — it's free
                </Link>
                <Link to="/login" className="cta-btn cta-btn--ghost">
                  Log in
                </Link>
              </>
            )}
            <a
              href={githubUrl}
              className="cta-btn cta-btn--outline"
              target="_blank"
              rel="noopener noreferrer"
            >
              ★ View on GitHub
            </a>
          </div>
        </div>
        <div className="landing-hero-visual" aria-hidden="true">
          <div className="hero-card-mock">
            <div className="hero-mock-label">Interview Readiness Score</div>
            <div className="hero-mock-score">8.4 / 10</div>
            <div className="hero-mock-bar">
              <div className="hero-mock-bar-fill" style={{ width: '84%' }} />
            </div>
            <div className="hero-mock-level">Level: Strong Candidate</div>
            <div className="hero-mock-row">
              <span>Communication</span><strong>8.1</strong>
            </div>
            <div className="hero-mock-row">
              <span>Technical depth</span><strong>8.7</strong>
            </div>
            <div className="hero-mock-row">
              <span>Problem solving</span><strong>8.3</strong>
            </div>
            <div className="hero-mock-row">
              <span>Confidence</span><strong>8.5</strong>
            </div>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Features                                                          */}
      {/* ---------------------------------------------------------------- */}
      <section className="landing-section" aria-labelledby="features-heading">
        <div className="landing-container">
          <h2 id="features-heading" className="section-heading">Everything you need to ace your next interview</h2>
          <p className="section-subheading">
            Six integrated features that cover the full preparation lifecycle — from upload to offer.
          </p>
          <div className="features-grid">
            {FEATURES.map((f) => (
              <article key={f.title} className="feature-card">
                <div className="feature-icon" aria-hidden="true">{f.icon}</div>
                <h3 className="feature-title">{f.title}</h3>
                <p className="feature-desc">{f.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Tech Stack                                                        */}
      {/* ---------------------------------------------------------------- */}
      <section className="landing-section landing-section--alt" aria-labelledby="tech-heading">
        <div className="landing-container">
          <h2 id="tech-heading" className="section-heading">Built on proven technology</h2>
          <p className="section-subheading">
            A modern full-stack architecture using production-grade open-source tools.
          </p>
          <div className="tech-grid">
            {TECH_STACK.map((t) => (
              <div key={t.name} className="tech-badge">
                <span className="tech-name">{t.name}</span>
                <span className="tech-desc">{t.desc}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Production Features                                               */}
      {/* ---------------------------------------------------------------- */}
      <section className="landing-section" aria-labelledby="prod-heading">
        <div className="landing-container">
          <h2 id="prod-heading" className="section-heading">Production-grade engineering</h2>
          <p className="section-subheading">
            Not just a demo. Built with the same practices used in real production systems.
          </p>
          <div className="prod-grid">
            {PROD_FEATURES.map((pf) => (
              <article key={pf.title} className="prod-card">
                <div className="prod-icon" aria-hidden="true">{pf.icon}</div>
                <h3 className="prod-title">{pf.title}</h3>
                <ul className="prod-list">
                  {pf.points.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Screenshots                                                       */}
      {/* ---------------------------------------------------------------- */}
      <section className="landing-section landing-section--alt" aria-labelledby="screenshots-heading">
        <div className="landing-container">
          <h2 id="screenshots-heading" className="section-heading">See it in action</h2>
          <p className="section-subheading">
            Clone the repo and run <code className="inline-code">docker compose up</code> to explore locally in minutes.
          </p>
          <div className="screenshots-placeholder">
            <div className="screenshot-mock">
              <div className="screenshot-mock-bar" />
              <div className="screenshot-mock-body">
                <div className="screenshot-mock-line" style={{ width: '60%' }} />
                <div className="screenshot-mock-line" style={{ width: '45%' }} />
                <div className="screenshot-mock-line screenshot-mock-line--card" />
                <div className="screenshot-mock-line screenshot-mock-line--card" />
              </div>
              <p className="screenshot-caption">Sessions Dashboard</p>
            </div>
            <div className="screenshot-mock">
              <div className="screenshot-mock-bar" />
              <div className="screenshot-mock-body">
                <div className="screenshot-mock-line" style={{ width: '50%' }} />
                <div className="screenshot-mock-line screenshot-mock-line--score" />
                <div className="screenshot-mock-line" style={{ width: '70%' }} />
                <div className="screenshot-mock-line" style={{ width: '55%' }} />
              </div>
              <p className="screenshot-caption">Readiness Score Report</p>
            </div>
            <div className="screenshot-mock">
              <div className="screenshot-mock-bar" />
              <div className="screenshot-mock-body">
                <div className="screenshot-mock-line screenshot-mock-line--chart" />
                <div className="screenshot-mock-line" style={{ width: '40%' }} />
                <div className="screenshot-mock-line" style={{ width: '60%' }} />
              </div>
              <p className="screenshot-caption">Analytics Dashboard</p>
            </div>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* CTA Banner                                                        */}
      {/* ---------------------------------------------------------------- */}
      <section className="landing-cta-banner" aria-label="Call to action">
        <div className="landing-container landing-container--narrow">
          <h2 className="cta-banner-heading">Ready to prepare smarter?</h2>
          <p className="cta-banner-sub">
            Create a free account and run your first practice interview in under 5 minutes.
          </p>
          <div className="landing-cta-row landing-cta-row--center">
            {isAuthenticated ? (
              <Link to="/sessions" className="cta-btn cta-btn--primary cta-btn--lg">
                Go to Dashboard →
              </Link>
            ) : (
              <>
                <Link to="/register" className="cta-btn cta-btn--primary cta-btn--lg">
                  Get Started — it's free
                </Link>
                <a
                  href={githubUrl}
                  className="cta-btn cta-btn--outline cta-btn--lg"
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

      {/* ---------------------------------------------------------------- */}
      {/* Footer                                                            */}
      {/* ---------------------------------------------------------------- */}
      <footer className="landing-footer">
        <div className="landing-container landing-footer-inner">
          <span className="footer-brand">AI Interview Intelligence Platform</span>
          <nav className="footer-nav" aria-label="Footer">
            <a href={githubUrl} target="_blank" rel="noopener noreferrer">GitHub</a>
            <Link to="/login">Log in</Link>
            <Link to="/register">Register</Link>
            <span className="footer-sep" aria-hidden="true">·</span>
            <span>MIT License</span>
            <span className="footer-sep" aria-hidden="true">·</span>
            <span>v1.0.0</span>
          </nav>
        </div>
      </footer>
    </div>
  );
}
