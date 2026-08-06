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
`backend/alembic/versions/` are correct and PostgreSQL-compatible.
`backend/Dockerfile`'s `CMD` runs `alembic upgrade head && uvicorn ...` on
every container start, so migrations are applied automatically — a freshly
provisioned PostgreSQL database gets all tables on first boot, and every
subsequent deploy picks up only the new revisions.

### Why startup-time migration, not a separate pre-deploy step

An earlier version of this doc recommended a **Pre-Deploy Command** instead
(a separate step that runs before the new deploy is promoted) and argued
against running migrations in `CMD`, for two reasons: multiple instances
could race to apply the same migration concurrently, and a failed migration
would crash the app in a restart loop instead of failing a separate,
observable pre-deploy step.

Both concerns are real in general, but don't apply to how this app is
actually deployed:

- **No concurrent instances.** Render's Free plan runs exactly one
  instance, and the app's own design (single Uvicorn worker, in-process
  Whisper singleton, a Disk that "restricts the service to a single
  instance" — see [RENDER_DEPLOYMENT.md § 5](./RENDER_DEPLOYMENT.md))
  never scales horizontally. There is nothing to race against.
- **A failed migration crashing the boot is the correct outcome, not a
  risk.** `alembic upgrade head` exits non-zero on a genuine failure, so
  `&&` never invokes uvicorn — the container never binds to its port, so
  Render's health check never passes, so **Render fails the deploy and
  keeps the previous, still-running version live and serving traffic**,
  exactly like a failed pre-deploy step would. The alembic error is in the
  deploy's boot logs either way. A restart loop only happens if the
  underlying cause (bad `DATABASE_URL`, an unreachable database) doesn't
  resolve itself — the same as it would for any other startup dependency
  check.

The actual reason this was changed: **Render's Free plan supports neither
a Pre-Deploy Command nor a Shell tab** — the previously-recommended
approach is simply unavailable without a paid plan, and running migrations
by hand isn't optional-but-nicer here, it's impossible. `CMD`-time
migration is the option that exists on every Render plan.

If this deployment ever moves to multiple instances (a paid plan with
autoscaling, or a job queue worker fleet), move the `alembic upgrade head`
step back out to a Pre-Deploy Command or a dedicated one-off CI job at that
point — the migration files and `env.py` don't change either way, only
where `alembic upgrade head` is invoked from.

### Render: Pre-Deploy Command (optional, paid plans only)

If you're on a paid Render plan and prefer to decouple migration from
startup (e.g. once you do run multiple instances), you can still set a
**Pre-Deploy Command**:

```
alembic upgrade head
```

This runs from the image's `WORKDIR` (`/app`), where `alembic.ini` and the
`alembic/` directory are present (copied in by `COPY . .` in the
Dockerfile). `backend/alembic/env.py` reads `DATABASE_URL` from the
environment at runtime, so no extra configuration is needed beyond the
`DATABASE_URL` env var the app already requires.

`alembic upgrade head` is idempotent — if the database is already at the
latest revision, it's a no-op. Running it both here and in `CMD` is
harmless (the second run is just a no-op check against `alembic_version`);
you don't need to remove the `CMD` step if you also configure this.

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
