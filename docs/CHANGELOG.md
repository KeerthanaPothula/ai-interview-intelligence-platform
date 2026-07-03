# Changelog

All notable changes to this project, grouped by date. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
See [CONTRIBUTING.md § Versioning](./CONTRIBUTING.md#versioning--releases)
for the semantic-versioning scheme.

## 2026-07-02 — v1.0.1

- **fix**: CORS connection — backend config now searches `[".env", "../.env"]`
  so the standard `cp .env.example .env` (at repo root) works without a
  separate `backend/.env`. Added a `model_validator` that auto-populates
  `CORS_ORIGINS` with `localhost:5173` and `localhost:3000` when
  `ENVIRONMENT=development` and no explicit value is set — local dev now
  works out-of-the-box from a clean clone.
- **fix**: improved network-error message in `client.ts` to include the
  actual backend URL and actionable guidance instead of a generic string.
- **feat**: public landing page at `/` — hero section with readiness score
  mock, feature highlights grid, tech-stack badges, production-features
  breakdown, screenshot mockups, CTA banner, and footer. Matches existing
  design-language CSS variables; fully responsive.
- **chore**: routing — `SessionsListPage` moved from `/` to `/sessions`;
  `/login` and `/register` redirect authenticated users to `/sessions`;
  `Layout` nav links updated accordingly.

## 2026-07-01 — v1.0.0

First production release.

- **feat**: frontend polish — `ToastProvider`/`useToast` for user-action
  feedback, `Skeleton` loader components, `EmptyState`/`ErrorState`
  components with retry affordances, `aria-label` / `role="alert"` /
  `aria-live` accessibility improvements across all pages.
- **feat**: `ResumeUploadCard` — exposes the existing resume upload backend
  endpoints (`POST/GET /api/v1/documents/resume/*`) which previously had no
  frontend UI; wired into the Sessions list page.
- **feat**: `SessionReportCard` — exposes the existing session report backend
  endpoints (`POST/GET /api/v1/reports/*`) which previously had no frontend
  UI; wired into the Session detail page.
- **test**: Playwright end-to-end suite (`frontend/e2e/full-flow.spec.ts`)
  covering the complete Register → Login → Upload Resume → Generate Questions
  → Interview → Generate Report → Dashboard flow. Drives a real browser
  against a real backend (no network mocking). Local/manual only — not in CI
  gate (CI has no `GEMINI_API_KEY`). See
  [docs/TESTING.md](./TESTING.md#end-to-end-playwright) for prerequisites.
- **docs**: `RELEASE.md` — v1.0.0 release notes, migration checklist,
  known limitations, roadmap. `docs/TESTING.md` extended with E2E section.
  `docs/screenshots.md` updated with 4 real captured screenshots.
- **chore**: backend test count updated to 251; README updated to reflect
  v1.0.0 completion, real screenshots, and E2E test suite.

## 2026-06-30

- **refactor!**: renamed the "interview prediction" feature to **Interview
  Readiness Score** and replaced its scikit-learn `LogisticRegression`
  (trained on 2,000 synthetic, formula-generated samples) with a fully
  transparent, deterministic weighted-average formula over existing
  evaluation/voice signals — no training step, no ML dependency, no claim of
  predicting real-world hiring outcomes. `POST/GET
  /api/v1/interviews/{id}/predict` and `/prediction` are now `/readiness`;
  response fields renamed `success_probability`→`readiness_score`,
  `predicted_outcome`→`readiness_level`, `model_version`→`scoring_method`.
  Breaking change, taken pre-v1.0.0 (no tagged release, no existing frontend
  consumer of the old contract). `scikit-learn` removed from
  `requirements.txt`. See [AI_PIPELINE.md §9](./AI_PIPELINE.md#9-interview-readiness-scoring--benchmarking-prediction_servicepy-benchmark_servicepy)
  for the exact formula and weights.

## 2026-06-29

- **fix**: resolved GitHub Actions CI failures (`openai-whisper` build
  failure from an unpinned `pkg_resources` transitive dependency; an
  ineffective `cache: "pip"` step) — all six CI jobs green.
- **feat**: production infrastructure, observability, and CI/CD — GitHub
  Actions (`ci.yml`, `security.yml`), structured JSON logging with
  request-ID correlation, Prometheus metrics (`/metrics`), optional
  OpenTelemetry tracing, `/health` + `/ready` endpoints, hardened
  multi-stage non-root Docker build. See [INFRASTRUCTURE.md](./INFRASTRUCTURE.md).

## 2026-06-28

- **feat**: production security hardening — see [SECURITY.md](./SECURITY.md)
  and the root [SECURITY.md](../SECURITY.md) for the full set of controls
  (account lockout, refresh-token rotation, security headers, file upload
  validation).

## 2026-06-27

- **feat**: backend architecture refactor and reliability improvements —
  atomic response claiming, a process-wide Whisper inference semaphore,
  idempotent processing retries, and startup recovery for responses stuck
  in `processing`. See [AI_PIPELINE.md § 1](./AI_PIPELINE.md#1-audio-response-pipeline-whisper--gemini--librosa).

## 2026-06-18

- **feat**: live conversational AI interviews, resume/JD RAG question
  generation, predictive analytics (success probability + percentile
  benchmarking), and AI career coaching (7/14/30-day plans). See
  [AI_PIPELINE.md §§ 6–10](./AI_PIPELINE.md).
- **feat**: voice analytics engine (librosa), AI follow-up interviewer,
  analytics dashboard, and session-level final reports. See
  [AI_PIPELINE.md §§ 4–5, 8](./AI_PIPELINE.md).

## 2026-06-15

- **docs**: repository presentation pass — career/portfolio assets, Render
  deployment preparation.
- **feat**: integrated transcript and analysis views into the frontend
  (the first version of the polling-based processing UI).

## 2026-06-12

- **feat**: Week 3 audio processing and AI evaluation pipeline — Whisper
  transcription, Gemini evaluation, transcript/analysis retrieval and
  processing-status endpoints, interview-session state-transition
  enforcement.
- **fix**: corrected session-completion criteria.
- **security**: hardened the transcript-evaluation prompt (prompt-injection
  resistance) and the CORS configuration (exact-origin allowlist, no
  wildcard).
- **chore**: production logging configuration; backend deployment
  preparation.

## 2026-06-09

- Week 2 complete — stable baseline ahead of the Whisper pipeline (auth,
  interview sessions, question generation).

## 2026-06-07

- Initial commit; Week 1 backend foundation (FastAPI app skeleton, user
  auth, interview-session CRUD).

## Related documentation

- [CONTRIBUTING.md](./CONTRIBUTING.md) — versioning scheme for future releases.
- [ARCHITECTURE.md](./ARCHITECTURE.md) / [AI_PIPELINE.md](./AI_PIPELINE.md) — what the current architecture looks like after all entries above.
