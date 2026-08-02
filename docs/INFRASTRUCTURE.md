# Infrastructure & Observability

Production infrastructure added in Phase 4: CI/CD, container hardening,
health/readiness checks, structured logging, metrics, and tracing. This
complements [DEPLOYMENT.md](DEPLOYMENT.md) (database/storage strategy) and
[RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md) (step-by-step Render setup) —
this document focuses on what runs in CI and what an operator sees once the
service is deployed.

---

## CI/CD (GitHub Actions)

Two workflows under `.github/workflows/`, both triggered on `push` to `main`
and on every `pull_request`:

### `ci.yml`

| Job | What it does |
|---|---|
| `backend-lint` | `ruff check .` + `black --check .` against `backend/` |
| `frontend-lint` | `eslint .` against `frontend/` |
| `backend-test` | `pytest --cov=app --cov-report=xml --cov-fail-under=75` (in-memory SQLite — no database service needed) |
| `frontend-test` | `vitest run --coverage` — gated at a low 7-8% tripwire per metric (`vite.config.ts`), not a quality bar |
| `frontend-build` | `tsc -b && vite build` — catches type errors and build breaks |
| `docker-build` | Builds the backend image (`docker/build-push-action`, not pushed) to confirm the Dockerfile builds |

Backend and frontend dependencies are cached (`actions/setup-python` /
`actions/setup-node` with `cache:`), and `docker-build` uses the GitHub
Actions cache backend (`cache-from/to: type=gha`) for Docker layer caching.
Coverage reports (`backend/coverage.xml`, `frontend/coverage/`) are uploaded
as workflow artifacts rather than pushed to an external service, so no
third-party coverage account or token is required.

### `security.yml`

| Job | What it does |
|---|---|
| `pip-audit` | `pip-audit -r backend/requirements.txt` against the PyPA Advisory Database |
| `npm-audit` | `npm audit --omit=dev` against `frontend/` |
| `secrets-scan` | `gitleaks/gitleaks-action@v2` — scans the diff (PRs) or full history (pushes) for likely committed secrets |
| `codeql` | GitHub CodeQL static analysis for Python and JavaScript/TypeScript |

`pip-audit`, `npm-audit`, and `secrets-scan` run with
`continue-on-error: true` — they are informational (surface advisories/hits
for manual triage per [SECURITY.md](../SECURITY.md)) rather than
merge-blocking, since a new advisory against an already-pinned, otherwise-
fine transitive dependency (or a gitleaks false positive on a test fixture)
shouldn't halt unrelated PRs. `codeql` is not soft-failed; it requires the
`security-events: write` permission to upload results, declared explicitly
in the job.

`backend/tests/test_ci_config.py` parses both workflow files and asserts the
expected jobs/triggers exist, so a malformed or accidentally-renamed job is
caught by the regular test suite, not just by a failed push.

---

## Docker

### Multi-stage build

`backend/Dockerfile` builds in two stages:

1. **`builder`** — installs Python dependencies via
   `pip install --prefix=/install -r requirements.txt`.
2. **runtime** — starts fresh from `python:3.12-slim`, installs only
   `ffmpeg` (required by Whisper), and copies `/install` from the builder
   stage. None of pip's cache, the wheel build tools, or the apt package
   index end up in the final image.

### Non-root user

The runtime stage creates a fixed-UID (`1000`) `appuser` and switches to it
with `USER appuser` before the app starts. `/app/uploads` is created and
`chown`'d to `appuser` *before* the user switch, so a fresh named volume
mounted over it (e.g. `uploads_data` in `docker-compose.yml`) inherits that
ownership — Docker initialises a new volume's permissions from whatever
already exists at the mount point in the image.

### Health check

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1
```

Uses Python's stdlib (`urllib`) instead of installing `curl`/`wget` just for
this. Targets `/health`, not `/ready` — container liveness should reflect
"is the process alive," not "is the database reachable right now" (see
[Health vs. readiness](#health-vs-readiness) below). The `docker-compose.yml`
`backend` service declares the same check explicitly so `docker compose ps`
shows health status without needing to inspect the image.

### Verifying the build

```bash
cd backend
docker build -t aiip-backend .
docker build --check .          # structural/lint check only, no install
```

---

## Health vs. readiness

| Endpoint | Touches the DB? | Calls the AI provider? | Use for |
|---|---|---|---|
| `GET /health` | No | No | Liveness — "is the process up?" Always returns `200`. |
| `GET /ready` | Yes (`SELECT 1`, bounded by `READINESS_DB_TIMEOUT_SECONDS`) | No — checks `bool(GEMINI_API_KEY)` only, never makes a live call | Readiness — "can this instance serve traffic?" Returns `503` if not. |

```json
// GET /ready (200, ready)
{
  "status": "ready",
  "checks": {
    "database": {"ok": true, "error": null},
    "ai_provider_configured": {"ok": true}
  }
}
```

If the database check fails or times out, `database.ok` is `false`, `error`
holds a short message, and the response status is `503` — orchestrators
(Kubernetes, Render, Docker Swarm) should point liveness probes at `/health`
and readiness probes at `/ready` so a transient DB blip removes the instance
from the load balancer without restarting it.

---

## Logging

Structured JSON logs (`LOG_FORMAT=json`, the default) — one JSON object per
line:

```json
{"timestamp": "2026-06-27T10:15:32Z", "level": "INFO", "logger": "app.request", "message": "Request completed", "request_id": "3f9c2a1e...", "method": "GET", "path": "/api/v1/interviews/", "status_code": 200, "duration_ms": 42.3}
```

- `LOG_FORMAT=text` switches to a human-readable line format for local
  terminals.
- Every log record carries `request_id` (when one is active), via a
  `contextvars.ContextVar` set by `ObservabilityMiddleware` at the start of
  each request and propagated automatically through any code the request
  touches — no need to pass a request object down through service calls.
- Requests slower than `SLOW_REQUEST_THRESHOLD_MS` (default `1000`) are
  logged at `WARNING` as `"Slow request"`; everything else logs at `INFO`
  as `"Request completed"`.
- **Never logged**: API keys, JWTs, passwords, or raw request/response
  bodies. Log fields are limited to method, route template, status code,
  timing, and the request ID — see [SECURITY.md](../SECURITY.md#logging--audit)
  for the equivalent guarantee on the existing `app.security` logger.

The `X-Request-ID` request header (configurable via `REQUEST_ID_HEADER`) is
honoured if the caller supplies one (useful for correlating a request across
a frontend → backend → log pipeline) and is always echoed back on the
response, generating a new ID if none was supplied.

---

## Metrics

`GET /metrics` (enabled by default, `ENABLE_METRICS=true`) exposes
Prometheus text-format metrics:

| Metric | Type | Labels | What it measures |
|---|---|---|---|
| `http_requests_total` | Counter | `method`, `path`, `status_code` | All HTTP requests |
| `http_request_duration_seconds` | Histogram | `method`, `path` | Request latency |
| `http_errors_total` | Counter | `method`, `path`, `status_code` | 4xx/5xx responses |
| `ai_requests_total` | Counter | `provider`, `operation`, `status` | Gemini/Whisper calls |
| `ai_request_duration_seconds` | Histogram | `provider`, `operation` | AI call latency |
| `db_query_duration_seconds` | Histogram | — | Per-query duration (SQLAlchemy event hook) |
| `background_tasks_total` | Counter | `task_type`, `status` | Background processing outcomes |

`path` is always the route **template** (e.g. `/api/v1/interviews/{session_id}`),
never the raw resolved path — this keeps the label cardinality bounded
regardless of how many distinct session/response IDs are requested, which
is what makes the endpoint cheap to scrape.

Point Prometheus at `<base-url>/metrics`; no authentication is applied to
the endpoint today, so in production restrict access at the network/ingress
level (the same way most Prometheus exporters expect to be firewalled
rather than authenticated at the application layer).

---

## Tracing (OpenTelemetry)

Disabled by default (`ENABLE_TRACING=false`) — the OpenTelemetry SDK,
exporter, and FastAPI/SQLAlchemy auto-instrumentation are only imported and
initialised when explicitly enabled, so there is zero added latency or
dependency weight for deployments that don't use it.

```bash
ENABLE_TRACING=true
OTEL_SERVICE_NAME=ai-interview-intelligence-platform   # default shown
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces  # optional
OTEL_TRACES_SAMPLE_RATE=1.0                            # 0.0–1.0
```

When `OTEL_EXPORTER_OTLP_ENDPOINT` is unset, spans are printed to the
console instead of exported — useful to see tracing working locally without
standing up a collector (Jaeger, Tempo, Honeycomb, etc.).

Once enabled, every inbound HTTP request and SQLAlchemy statement gets a
span automatically (via `FastAPIInstrumentor` / `SQLAlchemyInstrumentor`),
plus manual spans around:

- `gemini.<operation>` — every Gemini call routed through
  `call_gemini_with_retry()` (covers question generation, follow-ups, live
  interview turns, RAG questions, and session reports — one instrumentation
  point covers all five call sites)
- `whisper.transcribe` — audio transcription
- `resume.extract_text` — resume/JD document parsing
- `rag.retrieve_relevant_chunks` — RAG retrieval
- `report.generate_session_report` — final report generation

`get_tracer(__name__)` is always safe to call from any module: before
`configure_tracing()` runs (or when tracing is disabled), the OpenTelemetry
API returns a no-op tracer, so instrumented code doesn't need its own
`if ENABLE_TRACING` guard at each call site.

---

## Configuration reference

All Phase 4 settings are typed fields on `Settings`
(`backend/app/config.py`), validated at startup, and documented with
defaults in `.env.example`:

| Setting | Default | Purpose |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Root logger level |
| `LOG_FORMAT` | `json` | `json` or `text` |
| `REQUEST_ID_HEADER` | `X-Request-ID` | Correlation header name |
| `SLOW_REQUEST_THRESHOLD_MS` | `1000` | Logs a `WARNING` above this latency |
| `ENABLE_METRICS` | `true` | Master switch for `/metrics` + HTTP/DB metrics |
| `ENABLE_TRACING` | `false` | Master switch for OpenTelemetry |
| `OTEL_SERVICE_NAME` | `ai-interview-intelligence-platform` | Span `service.name` resource attribute |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | OTLP/HTTP collector URL; console export if unset |
| `OTEL_TRACES_SAMPLE_RATE` | `1.0` | Fraction of traces sampled |
| `READINESS_DB_TIMEOUT_SECONDS` | `2.0` | Hard timeout for the `/ready` DB check |

---

## Local development

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
```

Or via Docker Compose (also starts PostgreSQL):

```bash
docker-compose up --build
docker-compose ps                  # shows backend health status
```

## Production deployment

No additional infrastructure is required to deploy Phase 4 — it builds on
the existing Render setup ([RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md)):

- `/health` is the right target for Render's health check path (it's what
  Render already polls to decide whether to route traffic to an instance).
- `/ready` is available for any orchestrator that distinguishes startup
  probes from liveness probes (Render itself only has one health-check
  concept today; Kubernetes deployments should use `/health` for
  `livenessProbe` and `/ready` for `readinessProbe`).
- Metrics and tracing are both opt-in and additive — enabling them requires
  only setting the corresponding environment variables; no code or schema
  changes.
