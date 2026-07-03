# Testing

## Backend

**Stack**: pytest + httpx (`TestClient`), in-memory SQLite (no PostgreSQL
needed to run the suite), 250 tests across 24 files under `backend/tests/`
(248 passed, 2 skipped as of the last local run).

```bash
cd backend
pytest                                          # run everything
pytest -k test_account_lockout                  # run one file/test by name
pytest --cov=app --cov-report=term-missing      # with a coverage breakdown
```

`backend/tests/conftest.py` sets `DATABASE_URL` (in-memory SQLite),
`JWT_SECRET_KEY`, and `GEMINI_API_KEY` via `os.environ.setdefault(...)`
before the app is imported, so the suite needs **no real secrets** and
**no running database** to pass — this is also what makes
`backend-test` in CI fast and self-contained (see
[INFRASTRUCTURE.md § CI/CD](./INFRASTRUCTURE.md#cicd-github-actions)).
`ENABLE_AUDIO_PROCESSING` is forced to `false` in tests so uploads don't
trigger a real Whisper/Gemini call from a background task; tests that need
the pipeline call `processing_service` functions directly and mock the
Whisper/Gemini boundary.

### Coverage (measured locally, 2026-06-29)

```
TOTAL    2841 statements   528 missed   81%
```

| Area | Coverage | Notes |
|---|---|---|
| Routers, schemas, core (auth, deps, security headers, observability) | High (>85% on most files) | Exercised directly by most test files |
| `rag_service.py` | ~24% | Resume RAG pipeline — only the chunking/embedding happy path is covered; similarity-search edge cases are not |
| `report_service.py` | ~31% | Session report generation — Gemini-call branches under-tested |
| `transcription_service.py` | ~30% | Whisper invocation itself is mocked in most tests; the real model-loading path is not exercised in CI |

Run `pytest --cov=app --cov-report=term-missing` for the full per-file
breakdown — the table above is illustrative of the *kind* of gap, not
exhaustive.

### What's tested well

Auth (registration, login, lockout, refresh-token rotation), interview
session CRUD and state transitions, audio upload validation (size, MIME,
magic bytes), the full processing pipeline state machine (`uploaded →
processing → completed/failed`, including startup recovery and atomic
claiming), rate limiting, CORS configuration, security headers, structured
logging/observability middleware, and CI workflow-file structure itself
(`test_ci_config.py` parses `.github/workflows/*.yml`).

## Frontend

**Stack**: Vitest + React Testing Library + jsdom, 31 tests across 6 files
under `frontend/src/**/*.test.tsx`.

```bash
cd frontend
npm run test        # run everything
npm run coverage     # with a coverage report
```

### Coverage (measured locally, 2026-06-29)

```
Statements   24.93%  (100/401)
Branches     30.76%  (84/273)
Functions    22.40%  (28/125)
Lines        25.60%  (96/375)
```

### Known gap — this is the honest state, not a target

Frontend coverage is low and concentrated on a handful of components
(`AnalysisCard`, `VoiceAnalyticsCard`, `useProcessingStatus`,
`LiveInterviewPage`) that were built with tests alongside them. Pages built
later (`LoginPage`, `RegisterPage`, `SessionsListPage`,
`SessionDetailPage`, `DashboardPage`) and `AuthContext`/`client.ts` have
**no test coverage at all**. This is a real gap, not an oversight to paper
over — if you're picking up a "good first issue" from this repo, writing
tests for any of the zero-coverage files above is a high-value, well-scoped
contribution (see [CONTRIBUTING.md](./CONTRIBUTING.md)).

## CI enforcement

Both suites run on every push/PR via `backend-test` and `frontend-test` in
`.github/workflows/ci.yml`; coverage reports are uploaded as workflow
artifacts (`backend/coverage.xml`, `frontend/coverage/`) rather than pushed
to an external coverage service. Neither job currently enforces a minimum
coverage percentage — a regression in coverage doesn't fail the build today
(see [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) if you're investigating a
CI failure on either job).

## End-to-end (Playwright)

**Stack**: Playwright 1.x with Chromium, 1 test in `frontend/e2e/full-flow.spec.ts`.

The E2E suite drives a real browser against the real frontend dev server, real
FastAPI backend, real PostgreSQL database, real Whisper transcription, and real
Gemini API calls. There is **no network mocking** — this is an integration check
of the entire deployed stack, not a unit test.

### What the suite covers

Register → Login → Upload Resume → Create Session → Generate Questions →
Upload Audio Response → Wait for Whisper Transcription + Gemini Analysis →
Generate Report → Navigate to Dashboard.

### Prerequisites (local only — not in CI)

| Requirement | Value |
|---|---|
| Frontend dev server | `http://localhost:5173` (`npm run dev` in `frontend/`) |
| Backend (uvicorn) | `http://localhost:8000` (host venv or Docker) |
| PostgreSQL | Reachable at `DATABASE_URL` in `backend/.env` |
| `CORS_ORIGINS` | Defaults to `http://localhost:5173,http://localhost:3000` when `ENVIRONMENT=development` — no explicit setting needed for local runs |
| `GEMINI_API_KEY` | A real key — placeholder value causes question/report steps to fail |
| `WHISPER_MODEL` | `base` is sufficient for the 2-second fixture WAV |

The test fixture files are committed to the repository:

- `frontend/e2e/fixtures/sample-resume.pdf` — minimal valid PDF (3-page placeholder)
- `frontend/e2e/fixtures/sample-response.wav` — 2-second 16 kHz mono sine tone, passes backend MIME/magic-byte validation

### Running locally

```bash
# 1. Start the full stack (see docs/DEVELOPMENT.md for details)
cd backend && uvicorn app.main:app --port 8000 --reload   # in one terminal
cd frontend && npm run dev                                 # in another

# 2. Run the suite
cd frontend
npx playwright test                   # or: npm run test:e2e
npx playwright test --headed          # watch mode
npx playwright show-report            # HTML report after a run
```

### Why E2E is not in the CI gate

CI (`ci.yml`) intentionally excludes the Playwright suite:

1. `GEMINI_API_KEY` is not available as a CI secret — any step that calls Gemini
   (generate questions, analyze response, generate report) would fail.
2. Whisper model download at CI startup would exceed the job time budget.
3. The backend pytest suite and frontend Vitest suite already run in CI and gate
   every merge; E2E is an additional **local confidence check**, not a
   replacement.

If you add a `GEMINI_API_KEY` secret to the repository and provision a Postgres
service in the CI workflow, the suite is ready to run — no test changes needed.

## Related documentation

- [INFRASTRUCTURE.md](./INFRASTRUCTURE.md) — full CI/CD job breakdown.
- [DEVELOPMENT.md](./DEVELOPMENT.md) — common test commands.
- [CONTRIBUTING.md](./CONTRIBUTING.md) — what a test-bearing PR should look like.
