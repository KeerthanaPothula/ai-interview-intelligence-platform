# Troubleshooting

For local dev/runtime issues (env vars, CORS, stuck processing, etc.), see
[DEVELOPMENT.md § Debugging guide](./DEVELOPMENT.md#debugging-guide) first
— this page covers CI, Docker, and deployment-specific failures.

## CI (GitHub Actions)

| Symptom | Likely cause | Fix |
|---|---|---|
| `backend-lint` fails on `black --check .` | Code wasn't formatted before commit | Run `black .` locally and commit the result |
| `backend-lint` fails on `ruff check .` | A lint rule violation | Run `ruff check . --fix` for auto-fixable issues; fix the rest by hand |
| `backend-test` fails only in CI, passes locally | A real env var (e.g. `DATABASE_URL`) is set in your local shell and masks a default `conftest.py` would otherwise apply | Run `pytest` in a clean shell/Docker container to match CI |
| `backend-test` fails on an `openai-whisper`/`pkg_resources` import error | An unpinned transitive dependency shipped a breaking release | Check `backend/requirements.txt` pins; this exact failure was fixed once already — see [CHANGELOG.md § 2026-06-29](./CHANGELOG.md) |
| `docker-build` fails but `backend-test` passes | A `Dockerfile`-specific issue (missing system package, build-context file not copied) rather than a Python issue | Reproduce locally: `cd backend && docker build -t aiip-backend .` |
| `pip-audit`/`npm-audit` (in `security.yml`) reports a new advisory | A transitive dependency has a newly published CVE | These jobs use `continue-on-error: true` (informational, not blocking) — triage per [SECURITY.md § Dependency Security](../SECURITY.md#dependency-security) and bump when convenient |
| A job is "stuck" / never starts | `concurrency.cancel-in-progress` canceled it because a newer commit was pushed to the same branch/PR | Expected behavior — only the latest commit's run completes; check the latest run, not an older one |

## Docker

| Symptom | Likely cause | Fix |
|---|---|---|
| `docker-compose up` — backend exits immediately | Missing/invalid required env var (see [DEVELOPMENT.md § Environment variables](./DEVELOPMENT.md#environment-variables)) | `docker-compose logs backend` for the `Settings` validation error |
| `docker-compose ps` shows backend `unhealthy` | The app started but `/health` isn't responding within the health-check window, or hasn't started yet (`start_period: 40s`) | Wait past `start_period`; if still unhealthy, `docker-compose logs backend` |
| Uploaded files disappear after `docker-compose down` | Used `-v` (removes volumes, including `uploads_data`) | Use `docker-compose down` without `-v` to preserve volumes between runs |
| `alembic upgrade head` inside the container fails with "relation already exists" | Migrations were already applied to that volume by a previous run | Expected if re-running — `alembic upgrade head` is idempotent for an up-to-date database; this error means something else applied schema out-of-band (e.g. manual SQL) |

## Render deployment

See [RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md) for the full setup guide
and its own troubleshooting section. Most common issues:

| Symptom | Likely cause | Fix |
|---|---|---|
| Fresh deploy: every request touching the DB 500s | `backend/Dockerfile`'s `CMD` migration step failed at boot (bad `DATABASE_URL`, unreachable DB) — check that deploy's boot logs, before the "Uvicorn running on..." line | Fix `DATABASE_URL`/network access and redeploy; see [DEPLOYMENT.md § 1](./DEPLOYMENT.md#1-database-migrations-alembic) |
| Login/register show "Cannot connect to the backend" but `/health` returns healthy | An unhandled 500 (often the migration issue above) has no CORS header, so the browser blocks it and the frontend reports a generic network error instead of the real 500 | Check the backend's own logs for the actual exception — don't trust "cannot connect" as a literal network diagnosis; see [RENDER_DEPLOYMENT.md § 9](./RENDER_DEPLOYMENT.md) |
| Uploaded audio disappears after a redeploy | No Render Disk attached at `/app/uploads` (Render's filesystem is ephemeral by default) | Attach a Render Disk — see [DEPLOYMENT.md § 2](./DEPLOYMENT.md#2-persistent-storage) |
| Frontend loads but every API call fails with a CORS error | The deployed frontend's origin isn't in the backend's `CORS_ORIGINS` | Update `CORS_ORIGINS` on the backend service to include the exact deployed frontend URL |
| `DEBUG=true is not permitted when ENVIRONMENT=production` at boot | Both env vars set inconsistently on the Render service | Set `DEBUG=false` alongside `ENVIRONMENT=production` |

## Railway / Vercel

| Symptom | Likely cause | Fix |
|---|---|---|
| Railway: uploaded audio disappears after redeploy | No Railway Volume attached at `/app/uploads` | Attach one — see [DEPLOYMENT.md § Railway](./DEPLOYMENT.md#railway-backend--alternative) |
| Vercel: frontend builds but can't reach the API | `VITE_API_BASE_URL` wasn't set as a Vercel environment variable, or points at the wrong backend URL | Set it in the Vercel project's environment variables and redeploy |
| Vercel: deploying the backend itself fails / times out | Vercel serverless functions aren't a fit for this backend (long-lived in-process Whisper model + a `threading.Semaphore(1)` singleton) | Deploy the backend to Render or Railway instead; Vercel is for the frontend only — see [DEPLOYMENT.md § Vercel](./DEPLOYMENT.md#vercel-frontend-only) |

## Related documentation

- [DEVELOPMENT.md](./DEVELOPMENT.md) — local dev debugging guide.
- [DEPLOYMENT.md](./DEPLOYMENT.md) / [RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md) — deployment setup.
- [INFRASTRUCTURE.md](./INFRASTRUCTURE.md) — CI/CD pipeline detail.
- [SECURITY.md](./SECURITY.md) — dependency-audit triage.
