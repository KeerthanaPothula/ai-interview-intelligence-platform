# Development Guide

Everything needed to get the project running locally, the commands you'll
run day-to-day, every environment variable, and how to debug the common
failure modes.

## One-command setup

```bash
git clone https://github.com/KeerthanaPothula/ai-interview-intelligence-platform.git
cd ai-interview-intelligence-platform
cp .env.example .env   # fill in JWT_SECRET_KEY and GEMINI_API_KEY at minimum
docker-compose up --build
docker-compose exec backend alembic upgrade head   # first run only
```

That's the entire backend + PostgreSQL stack, running at
`http://localhost:8000`. For the frontend (not in `docker-compose.yml`):

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

App at `http://localhost:5173`. See [§ Without Docker](#without-docker) below
for running the backend directly on the host instead.

## Without Docker

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp ../.env.example ../.env
# Point DATABASE_URL at a Postgres instance you control, or run one via
# `docker-compose up postgres` and keep DATABASE_URL pointed at localhost.
alembic upgrade head
uvicorn app.main:app --reload
```

`ffmpeg` must be installed on the host for Whisper to decode non-WAV audio
(`apt install ffmpeg` / `brew install ffmpeg` / on Windows, via
[the ffmpeg website](https://ffmpeg.org/download.html) and added to `PATH`).

## Development workflow

1. Branch off `main` — see [CONTRIBUTING.md](./CONTRIBUTING.md) for the full
   PR workflow.
2. Make your change. Add or update a migration if you touched
   `app/models/` — see [§ Migration guide](#migration-guide).
3. Run lint + tests locally (below) before opening a PR — the same checks
   run in CI and will block merge otherwise.
4. Update the relevant `docs/*.md` file if you changed an endpoint, table,
   env var, or deployment step.

## Common commands

### Backend (`cd backend`)

| Command | Does |
|---|---|
| `uvicorn app.main:app --reload` | Run the dev server with auto-reload |
| `pytest` | Run the full test suite (250 tests) |
| `pytest -k test_name` | Run a single test by name |
| `pytest --cov=app --cov-report=term-missing` | Run tests with a coverage report |
| `ruff check .` | Lint |
| `ruff check . --fix` | Lint and auto-fix what's safe to fix |
| `black .` | Auto-format |
| `black --check .` | Check formatting without changing files (what CI runs) |
| `alembic revision --autogenerate -m "description"` | Generate a new migration from model changes |
| `alembic upgrade head` | Apply all pending migrations |
| `alembic downgrade -1` | Revert the most recent migration (local only) |
| `pip-audit -r requirements.txt` | Check dependencies for known vulnerabilities |

### Frontend (`cd frontend`)

| Command | Does |
|---|---|
| `npm run dev` | Run the Vite dev server |
| `npm run build` | Type-check (`tsc -b`) and build for production |
| `npm run test` | Run the Vitest suite (31 tests) |
| `npm run coverage` | Run tests with a coverage report |
| `npm run lint` | ESLint |
| `npm run preview` | Preview the production build locally |
| `npm audit --omit=dev` | Check dependencies for known vulnerabilities |

### Docker

| Command | Does |
|---|---|
| `docker-compose up --build` | Build and start PostgreSQL + backend |
| `docker-compose exec backend alembic upgrade head` | Apply migrations inside the running container |
| `docker-compose exec backend bash` | Shell into the running backend container |
| `docker-compose ps` | Show container status, including health-check state |
| `docker-compose down -v` | Stop and remove containers + volumes (⚠ deletes the local Postgres data and uploaded files) |

## Environment variables

All settings are typed fields on `Settings` (`backend/app/config.py`),
validated at startup — an invalid value (e.g. an unsupported
`WHISPER_MODEL`, or `DEBUG=true` with `ENVIRONMENT=production`) fails fast
with a clear error instead of misbehaving at runtime. Full template with
inline comments: [`.env.example`](../.env.example).

| Variable | Default | Required | Purpose |
|---|---|---|---|
| `ENVIRONMENT` | `development` | No | `development` \| `production`; gates debug behavior |
| `DEBUG` | `true` | No | Full tracebacks + `/docs`/`/redoc`; must be `false` in production |
| `DATABASE_URL` | — | **Yes** | SQLAlchemy connection string |
| `JWT_SECRET_KEY` | — | **Yes** | HMAC signing secret, ≥32 chars (`openssl rand -hex 32`) |
| `JWT_ALGORITHM` | `HS256` | No | `HS256` \| `HS384` \| `HS512` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | No | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | No | Refresh token lifetime |
| `GEMINI_API_KEY` | — | **Yes** | [Google AI Studio](https://aistudio.google.com/app/apikey) key |
| `GEMINI_MODEL` | `gemini-2.0-flash` | No | Model name used by every AI service |
| `MAX_QUESTIONS_PER_SESSION` | `10` | No | 1–20 |
| `GEMINI_TIMEOUT_SECONDS` | `30` | No | Per-call HTTP timeout |
| `GEMINI_MAX_RETRIES` | `3` | No | Including the first attempt |
| `GEMINI_RETRY_BACKOFF_SECONDS` | `1.0` | No | Exponential backoff base |
| `WHISPER_MODEL` | `base` | No | `tiny`\|`base`\|`small`\|`medium`\|`large-v2`\|`large-v3` |
| `ENABLE_AUDIO_PROCESSING` | `true` | No | Master switch for the Whisper/Gemini pipeline |
| `MAX_TRANSCRIPT_CHARS` | `20000` | No | Truncation length before sending to Gemini |
| `WHISPER_TIMEOUT_SECONDS` | `300` | No | Per-job transcription timeout |
| `RAG_CHUNK_SIZE` | `200` | No | Words per RAG chunk |
| `RAG_CHUNK_OVERLAP` | `50` | No | Must be `<` `RAG_CHUNK_SIZE` |
| `UPLOAD_DIR` | `uploads` | No | Audio storage path |
| `MAX_UPLOAD_SIZE_MB` | `10` | No | Audio upload ceiling |
| `MAX_RESUME_UPLOAD_SIZE_MB` | `5` | No | Resume/JD upload ceiling |
| `CORS_ORIGINS` | `` (empty) | No | Comma-separated exact origins; empty disables cross-origin requests |
| `RATE_LIMIT_LOGIN_ATTEMPTS` | `5` | No | Per-IP, per window |
| `RATE_LIMIT_LOGIN_WINDOW_SECONDS` | `60` | No | Window width |
| `ACCOUNT_LOCKOUT_THRESHOLD` | `5` | No | Failed attempts before lockout |
| `ACCOUNT_LOCKOUT_DURATION_MINUTES` | `15` | No | Base duration, doubles per lockout |
| `ACCOUNT_LOCKOUT_MAX_DURATION_MINUTES` | `1440` | No | Doubling ceiling |
| `CSP_POLICY` | `default-src 'self'; frame-ancestors 'none'` | No | Content-Security-Policy header |
| `HSTS_MAX_AGE_SECONDS` | `31536000` | No | Only sent when `ENVIRONMENT=production` |
| `PERMISSIONS_POLICY` | `geolocation=(), microphone=(), camera=(), payment=()` | No | Permissions-Policy header |
| `LOG_LEVEL` | `INFO` | No | `DEBUG`\|`INFO`\|`WARNING`\|`ERROR`\|`CRITICAL` |
| `LOG_FORMAT` | `json` | No | `json` \| `text` |
| `REQUEST_ID_HEADER` | `X-Request-ID` | No | Correlation header name |
| `SLOW_REQUEST_THRESHOLD_MS` | `1000` | No | Logs `WARNING` above this latency |
| `ENABLE_METRICS` | `true` | No | Master switch for `/metrics` |
| `ENABLE_TRACING` | `false` | No | Master switch for OpenTelemetry |
| `OTEL_SERVICE_NAME` | `ai-interview-intelligence-platform` | No | Span `service.name` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | No | OTLP/HTTP collector; console export if unset |
| `OTEL_TRACES_SAMPLE_RATE` | `1.0` | No | 0.0–1.0 |
| `READINESS_DB_TIMEOUT_SECONDS` | `2.0` | No | `/ready` DB-check timeout |

Frontend (`frontend/.env`):

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend base URL the SPA calls |

## Migration guide

When you change a model in `backend/app/models/`:

```bash
cd backend
alembic revision --autogenerate -m "add foo column to bar table"
# review the generated file under alembic/versions/ — autogenerate
# does not always detect every change correctly (e.g. column renames
# look like drop+add unless you edit the migration by hand)
alembic upgrade head      # apply it locally
pytest                    # confirm nothing broke
```

Commit the generated migration file alongside your model change in the
same PR. See [DATABASE.md § Migration history](./DATABASE.md#migration-history)
for the full revision chain, and
[DEPLOYMENT.md § Database migrations](./DEPLOYMENT.md#1-database-migrations-alembic)
for why migrations run as a pre-deploy step rather than at application
startup.

## Debugging guide

| Symptom | Likely cause | Fix |
|---|---|---|
| App won't start: `pydantic_core.ValidationError` for `Settings` | A required env var (`DATABASE_URL`, `JWT_SECRET_KEY`, `GEMINI_API_KEY`) is missing, or `JWT_SECRET_KEY` is under 32 chars | Check `.env` against `.env.example`; generate a key with `openssl rand -hex 32` |
| `DEBUG=true is not permitted when ENVIRONMENT=production` at startup | Both set in the same `.env` | Set `DEBUG=false` for any `ENVIRONMENT=production` deployment |
| `405`/CORS error in the browser console | The frontend's origin isn't in `CORS_ORIGINS` | Add it (e.g. `http://localhost:5173`) — see [.env.example](../.env.example) for the format |
| Audio upload succeeds but never leaves `uploaded` | `ENABLE_AUDIO_PROCESSING=false`, or `ffmpeg` isn't on `PATH` (Whisper needs it to decode) | Set the flag to `true`; verify `ffmpeg -version` runs |
| A response is stuck in `processing` after a crash/restart | Expected — startup recovery resets it to `failed` on the *next* boot, not instantly | Restart the backend, or call `POST /responses/{id}/process` again once it's `failed` |
| `pytest` fails with a database connection error | Tests use in-memory SQLite by default (`conftest.py` sets `DATABASE_URL` via `setdefault`) — a real `DATABASE_URL` already exported in your shell overrides that | `unset DATABASE_URL` before running `pytest`, or run inside a clean shell/Docker container |
| Gemini calls fail with `403`/`429` | Invalid/missing `GEMINI_API_KEY`, or quota exceeded | Verify the key at [Google AI Studio](https://aistudio.google.com/app/apikey); `GEMINI_MAX_RETRIES`/`GEMINI_RETRY_BACKOFF_SECONDS` only help with transient `429`s, not an exhausted quota |
| Whisper transcription is very slow on first request | The model is lazy-loaded on first use, not at process startup | Expected for the first request only; subsequent requests reuse the loaded model (see [AI_PIPELINE.md](./AI_PIPELINE.md)) |
| `npm run build` fails with a TypeScript error CI didn't seem to catch before | `tsc -b` is part of `npm run build`, not `npm run dev` (dev uses esbuild's faster, looser transpile-only path) | Run `npm run build` locally before pushing, not just `npm run dev` |

For anything not covered here, see [TROUBLESHOOTING.md](./TROUBLESHOOTING.md).

## Related documentation

- [TESTING.md](./TESTING.md) — test suite structure and coverage.
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) — deployment/runtime issues.
- [DEPLOYMENT.md](./DEPLOYMENT.md) — production migration and storage strategy.
- [CONTRIBUTING.md](./CONTRIBUTING.md) — PR workflow and code style.
