# Release Notes — v1.0.0

**Release date**: 2026-07-01  
**Semver tag**: `v1.0.0`  
**Branch**: `main`

---

## What this release is

v1.0.0 is the first production-ready tag of the AI Interview Intelligence
Platform. It marks the point where the backend architecture, security,
observability, CI/CD pipeline, and frontend UI are all stable enough for
consistent portfolio use and real user traffic (on appropriate hosting).

This is not a "feature complete" release in the sense that everything that could
ever be built is built. It is a **credible, honest, production-shaped 1.0**: the
features that are here work reliably, are well-tested, and are documented
accurately. Features that are not ready are not shipped and not claimed.

---

## What's new since the last pre-release state

### Part 1 — Interview Readiness Score (breaking rename)

The previous "ML Prediction" feature — a logistic regression model trained on
2,000 synthetically generated (formula-derived) data points — has been
**replaced** by a transparent, deterministic **Interview Readiness Score**.

**Why**: The old feature claimed (implicitly, through naming) to predict hiring
outcomes. It did not. Its "training data" was formula-generated, which means it
was circular — the model learned the formula, not a signal from real interviews.
Shipping it as a prediction of real-world outcomes would have been dishonest.

**What replaced it**: A documented, weighted average over real signals the
platform already collects:

| Signal | Weight |
|---|---|
| Average overall evaluation score | 25% |
| Average communication score | 20% |
| Average technical score | 20% |
| Average problem-solving score | 15% |
| Average confidence score | 10% |
| Voice clarity (pace + filler words) | 10% |

Output is a 0–100 score mapped to a readiness level (`not_ready` / `developing`
/ `ready` / `highly_ready`). No ML, no training step, no hiring-outcome claim.
The full formula is documented in [docs/AI_PIPELINE.md §9](docs/AI_PIPELINE.md#9-interview-readiness-scoring--benchmarking-prediction_servicepy-benchmark_servicepy).

**API change** (breaking, taken pre-1.0 — no prior tagged release):

| Before | After |
|---|---|
| `POST/GET /api/v1/interviews/{id}/predict` | `/readiness` |
| `success_probability` field | `readiness_score` |
| `predicted_outcome` field | `readiness_level` |
| `model_version` field | `scoring_method` |

`scikit-learn` removed from `requirements.txt`.

### Part 2 — Frontend polish

- **Toast notifications** — every user-initiated action (upload, generate,
  delete, error) surfaces a dismissible success/error toast rather than silent
  state changes.
- **Skeleton loaders** — loading states for session list, session detail, and
  dashboard now show content-shaped placeholders instead of blank screens.
- **Empty and error states** — consistent `EmptyState` / `ErrorState`
  components with retry affordances across all data-dependent views.
- **Accessibility** — `aria-label` on all icon/file inputs, `role="alert"` on
  inline error messages, `aria-live` on the toast region, keyboard navigation
  through all interactive elements.
- **Resume upload UI** — `ResumeUploadCard` wired into the Sessions list page,
  exposing the existing `/api/v1/documents/resume/*` endpoints which previously
  had no frontend surface.
- **Session report UI** — `SessionReportCard` wired into the Session detail
  page, exposing the existing `/api/v1/reports/*` endpoints which previously
  had no frontend surface.

### Part 3 — End-to-end test suite

Playwright 1.x suite in `frontend/e2e/full-flow.spec.ts` covering the complete
user journey: Register → Login → Upload Resume → Create Session → Generate
Questions → Upload Audio Response → Wait for Transcription + Analysis →
Generate Report → Dashboard. No network mocking — drives a real browser against
a real backend, real Postgres, real Whisper, and real Gemini.

The suite is a **local confidence check**, not a CI gate (CI has no real
`GEMINI_API_KEY`). See [docs/TESTING.md § End-to-end](docs/TESTING.md#end-to-end-playwright)
for prerequisites and how to run it.

---

## Migration notes (upgrading from pre-1.0)

1. **Database**: no schema changes in this release — existing databases and
   Alembic migration histories are unaffected. Run `alembic upgrade head` as
   usual; it will be a no-op if already current.

2. **API consumers**: the `/predict` → `/readiness` rename is a breaking
   change. If you have external tooling or scripts calling
   `/api/v1/interviews/{id}/predict`, update them to use
   `/api/v1/interviews/{id}/readiness`. Response-field names changed too (see
   table above).

3. **`scikit-learn` removed**: if your environment had `scikit-learn` installed
   from `requirements.txt`, it can be uninstalled (`pip uninstall scikit-learn`).
   No other dependencies changed in this release.

4. **`CORS_ORIGINS`**: if you run the frontend dev server and backend together
   locally, make sure `CORS_ORIGINS=http://localhost:5173` (or your frontend
   origin) is set in `backend/.env`. This was always required but is now
   explicitly called out in the documentation.

---

## Production checklist

Before deploying v1.0.0 to a public environment, verify:

- [ ] `backend/.env` (or hosting environment variables) sets `ENVIRONMENT=production`, `DEBUG=false`
- [ ] `JWT_SECRET_KEY` is a securely generated random value (not the example value)
- [ ] `POSTGRES_PASSWORD` / `DATABASE_URL` point to a real, access-controlled database
- [ ] `GEMINI_API_KEY` is a real Google AI Studio key with sufficient quota
- [ ] `CORS_ORIGINS` is the exact frontend origin (no trailing slash, no wildcard)
- [ ] `WHISPER_MODEL` is sized for your server (use `base` on CPU, `small`+ on GPU)
- [ ] TLS is terminated at the load balancer / reverse proxy (backend serves HTTP)
- [ ] File upload volume (`uploads_data` in Docker Compose) is on persistent storage
- [ ] Alembic migrations have been applied: `alembic upgrade head`
- [ ] `/health` and `/ready` return 200 before routing traffic
- [ ] Prometheus `/metrics` endpoint is firewalled from public access (or excluded via ingress rule)
- [ ] Rate-limiting values (`RATE_LIMIT_*`) are reviewed for your expected traffic

---

## Known limitations

These are real limitations, not planned-feature hedging. Each is fixable but is
out of scope for v1.0.0.

| Area | Limitation |
|---|---|
| **Interview Readiness Score** | Weighted average over the platform's own evaluation scores, which are themselves Gemini outputs. The score reflects how good your answers sounded to the AI evaluator, not how likely you are to get a specific job. |
| **Whisper transcription** | Runs synchronously in a background thread using the CPU `base` model. Long audio files or simultaneous uploads will queue. On a CPU-only server, transcription latency is proportional to audio length (roughly 1× real-time for `base`). |
| **No real-time audio recording in the frontend** | The interview UI uses a file-input for audio uploads. Live browser recording (MediaRecorder API) is not implemented — the user must record separately and upload the file. |
| **Live Interview session state not persisted** | Live Interview conversations are in-memory on the server. A server restart loses the conversation history. |
| **Single-region deployment** | No multi-region or CDN configuration is provided. The Render deployment config targets a single service. |
| **Frontend coverage is low** | 25% statement coverage. Pages built in the latter phases (`LoginPage`, `RegisterPage`, `SessionsListPage`, `SessionDetailPage`, `DashboardPage`) have no unit tests. See [docs/TESTING.md](docs/TESTING.md#known-gap--this-is-the-honest-state-not-a-target). |
| **No password reset flow** | Users who forget their password cannot reset it — there is no email integration. |
| **Docker build broken on machines with TLS-intercepting proxies** | If your network has a man-in-the-middle TLS proxy (e.g. Avast Web Shield, corporate CA), `docker build` may fail when pip tries to fetch PyTorch from `download.pytorch.org`. Run the backend via the host Python venv as a workaround, or add your CA cert to the Docker image (not done here to avoid modifying the Dockerfile for a local-machine quirk). |

---

## Roadmap (post-v1.0.0)

These are genuinely planned next steps — they are not listed to make the
release look bigger than it is. Each has a clear implementation path.

| Item | Notes |
|---|---|
| **Live audio recording in the browser** | MediaRecorder API, chunked upload, waveform visualizer |
| **Real-time transcription progress** | WebSocket or SSE streaming for Whisper output |
| **Password reset via email** | SMTP / transactional email integration (SendGrid or similar) |
| **Frontend unit test coverage** | Page-level tests for Login, Register, Sessions, Dashboard |
| **Readiness score calibration** | Collect opt-in outcome data from real users; use it to tune the formula weights once a real signal exists |
| **Multi-company JD library** | Save and reuse job descriptions; tag sessions by company/role |
| **Export session as PDF** | Shareable interview performance report |
| **Mobile-responsive layout** | Current UI targets desktop; breakpoints exist but are not fully tested at phone widths |

---

## Upgrade path

```bash
git pull origin main
cd backend
pip install -r requirements.txt        # scikit-learn is gone; nothing new added
alembic upgrade head                   # no-op if already current
```

No data migration is required.
