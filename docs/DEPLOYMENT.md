# Deployment Guide

Operational steps required when deploying the backend that are **not**
handled automatically by the Docker image build: running database
migrations and provisioning persistent storage for uploaded audio. See
[§3](#3-platform-options) for how this maps onto Render, Railway, and
Vercel specifically, and [ARCHITECTURE.md § 5](./ARCHITECTURE.md#5-deployment-architecture)
for the overall deployment diagram.

## 1. Database migrations (Alembic)

### Current state

`backend/alembic/env.py` and the migration chain under
`backend/alembic/versions/` are correct and PostgreSQL-compatible, but
nothing in the Docker image, docker-compose, or the application's startup
code runs `alembic upgrade head`. A freshly provisioned PostgreSQL database
has no tables until this command is run.

### Recommended approach: pre-deploy command, not startup-time migration

Run migrations as a separate, one-time step that completes **before** the
new application code receives traffic — not inside `app.main`'s startup
lifespan, and not as part of the container's `CMD`.

Why not run migrations at application startup:

- Render (and most platforms) can start multiple instances, or restart a
  crashed instance independently. If `alembic upgrade head` ran inside
  `main.py`'s lifespan, every instance start would race to apply the same
  migration — unnecessary contention and a source of hard-to-diagnose
  startup failures.
- A failed migration would crash the entire app on boot, and a restart loop
  would repeatedly retry a partially-applied migration.
- Decoupling "deploy new code" from "migrate schema" makes each step
  independently observable and retryable.

### Render: Pre-Deploy Command

Render web services support a **Pre-Deploy Command**, which runs to
completion — using the same image and environment variables as the service
— *before* the new deploy is promoted and starts receiving traffic.

Set the Pre-Deploy Command to:

```
alembic upgrade head
```

This runs from the image's `WORKDIR` (`/app`), where `alembic.ini` and the
`alembic/` directory are present (copied in by `COPY . .` in the
Dockerfile). `backend/alembic/env.py` reads `DATABASE_URL` from the
environment at runtime, so no extra configuration is needed beyond the
`DATABASE_URL` env var the app already requires.

`alembic upgrade head` is idempotent — if the database is already at the
latest revision, it's a no-op. This makes it safe to run on every deploy,
including the very first one against a brand-new database.

### Local development (docker-compose)

`docker-compose.yml` does not run migrations automatically either. After
`docker-compose up` against a fresh `postgres` volume, apply migrations once:

```
docker-compose exec backend alembic upgrade head
```

This is unchanged by this phase — documented here for completeness.

## 2. Persistent storage

### What must survive a restart/redeploy

`UPLOAD_DIR` (default `uploads`, resolved to `/app/uploads` inside the
container) stores the audio files referenced by `AudioResponse.file_path`.
These files:

- Are required to re-run transcription (e.g. retrying via
  `POST /responses/{id}/process` after a failure).
- Are not duplicated anywhere else — the transcript and evaluation
  *results* are persisted in PostgreSQL, but the source audio is not.

On Render, a web service's filesystem is **ephemeral**: it resets on every
deploy and on every restart (crash, scale event, manual restart). Without
attached persistent storage, every deploy silently deletes all previously
uploaded audio files, even though the database rows referencing them remain.

### What can be regenerated (no persistence required)

The Whisper model weights cache (`~/.cache/whisper`, populated on first
transcription by `transcription_service.get_model()`) does **not** need to
survive a restart. It is re-downloaded automatically the next time a model
is loaded. Losing it only adds latency (a one-time ~74MB download for the
`base` model) to the first transcription after a cold start — it is not a
data-loss or correctness concern.

### Recommendation: Render Disk mounted at `/app/uploads`

Attach a [Render Disk](https://render.com/docs/disks) to the backend
service, mounted at `/app/uploads` — the same path the Dockerfile already
creates (`RUN mkdir -p /app/uploads`) and the same path docker-compose mounts
its `uploads_data` named volume onto for local development. No code or
environment variable changes are required: `UPLOAD_DIR=uploads` (relative to
`WORKDIR /app`) continues to resolve to this path.

Notes / constraints:

- Render Disks are only available to services running a **single instance**
  (no horizontal scaling while a disk is attached). This matches the current
  single-worker design — see the Dockerfile comments on the Whisper model
  singleton and `threading.Semaphore(1)`, which already assume one process.
- Size: start small (1 GB) and monitor. `MAX_UPLOAD_SIZE_MB=50` per file is
  the only existing bound; there is no automatic cleanup of old files yet.
- Do not mount the Whisper cache (`~/.cache/whisper`) on the disk — it's
  regenerable (see above), so persisting it only saves a one-time download
  per cold start and isn't required.

### Out of scope for this phase

Migrating audio storage to S3/R2 (or any object storage) is not covered
here. A Render Disk is sufficient for the current single-instance deployment
and addresses the data-loss risk identified in the Phase 8 audit. Object
storage would be revisited if/when the service needs to scale beyond a
single instance.

## 3. Platform options

The backend is a single Docker image (`backend/Dockerfile`) and the frontend
is a static Vite build (`frontend/dist/`) — they deploy independently and
only need to agree on two values: the frontend's `VITE_API_BASE_URL` (where
the backend lives) and the backend's `CORS_ORIGINS` (which frontend origin
may call it).

### Render (backend — primary/documented target)

Already covered in detail above and in
[RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md). Summary: Docker-based Web
Service, a Render Disk mounted at `/app/uploads`, managed PostgreSQL, and
`alembic upgrade head` as the Pre-Deploy Command.

### Railway (backend — alternative)

Railway builds directly from `backend/Dockerfile`, so no extra build
configuration is needed.

1. Create a new project, add a service pointing at this repo with **Root
   Directory** set to `backend`.
2. Add a **PostgreSQL** plugin from Railway's database catalog — it injects
   `DATABASE_URL` into the service's environment automatically.
3. Set the remaining required environment variables (see
   [DEVELOPMENT.md § Environment Variables](./DEVELOPMENT.md#environment-variables)):
   `JWT_SECRET_KEY`, `GEMINI_API_KEY`, `CORS_ORIGINS`, `ENVIRONMENT=production`.
4. Railway has no separate "pre-deploy command" primitive — run migrations
   as a **Railway one-off command** (`railway run alembic upgrade head`,
   from the `backend` directory, against the same environment) before
   promoting a release that includes new migrations, or wire it into a
   **deploy hook** if one is configured.
5. **Persistent storage**: attach a [Railway
   Volume](https://docs.railway.com/reference/volumes) mounted at
   `/app/uploads` — same role as the Render Disk in [§2](#2-persistent-storage);
   without it, uploaded audio is lost on every redeploy.

### Vercel (frontend only)

Vercel is suitable for the static React/Vite frontend; it does not run the
Python/Docker backend (Vercel's serverless functions are not a fit for an
in-process Whisper model and a `threading.Semaphore(1)`-guarded singleton —
the backend needs a long-lived process, which points at Render or Railway
instead).

1. Import the repo, set **Root Directory** to `frontend`.
2. Framework preset: Vite. Build command `npm run build`, output directory
   `dist` (Vercel detects these automatically from `frontend/package.json`).
3. Set the environment variable `VITE_API_BASE_URL` to the deployed
   backend's URL (e.g. `https://<service>.onrender.com`).
4. On the backend, add the resulting Vercel domain
   (`https://<project>.vercel.app`) to `CORS_ORIGINS` — without this, the
   browser blocks every API call with a CORS error even though the request
   itself would have succeeded.

### Choosing between Render and Railway for the backend

Both support Docker images, managed PostgreSQL, and persistent volumes —
the trade-off is mainly familiarity and pricing tier, not capability. This
project documents Render in the most detail ([RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md))
because that's the platform it has actually been deployed to; the Railway
steps above are the direct equivalent for the same Docker image.

## Related documentation

- [RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md) — step-by-step Render setup.
- [ARCHITECTURE.md](./ARCHITECTURE.md) — deployment diagram and request flow.
- [INFRASTRUCTURE.md](./INFRASTRUCTURE.md) — CI/CD pipeline that builds and validates the image deployed here.
- [DEVELOPMENT.md](./DEVELOPMENT.md) — full environment variable reference.
