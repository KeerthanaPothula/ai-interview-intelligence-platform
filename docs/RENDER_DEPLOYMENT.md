# Render Deployment Guide

Step-by-step instructions for deploying the AI Interview Intelligence
Platform to [Render](https://render.com) for the first time: a managed
PostgreSQL database, a Dockerized FastAPI backend (Web Service), and a
static React frontend (Static Site).

This guide assumes:

- The repository is pushed to GitHub (or GitLab) and Render has access to it.
- The repo root contains `backend/` and `frontend/` (this is a monorepo —
  every "Root Directory" setting below matters).
- You have a [Google AI Studio](https://aistudio.google.com/app/apikey) API
  key for `GEMINI_API_KEY`.

For the *why* behind the migration and storage strategy used in steps 4 and
5, see [DEPLOYMENT.md](./DEPLOYMENT.md).

## Architecture on Render

```
┌─────────────────────────┐      ┌──────────────────────────┐
│ Static Site (frontend)   │ ───▶ │ Web Service (backend)     │
│ React + Vite build       │ HTTP │ Docker: FastAPI + Uvicorn │
│ https://<fe>.onrender.com│      │ https://<be>.onrender.com │
└─────────────────────────┘      └─────────────┬────────────┘
                                                 │
                                                 ▼
                                  ┌──────────────────────────┐
                                  │ PostgreSQL (Render)        │
                                  └──────────────────────────┘
```

The backend service also gets a Render Disk mounted at `/app/uploads` for
persisted audio files (step 5).

---

## 1. Create the PostgreSQL database

1. Render Dashboard → **New** → **PostgreSQL**.
2. Name: `aiip-db` (any name; used only for display).
3. Database, User: leave defaults or customize — note them either way.
4. Region: pick the region you'll deploy the backend to (must match for
   internal networking).
5. Plan: Starter is sufficient to begin.
6. Click **Create Database** and wait for it to become **Available**.
7. On the database's page, copy the **Internal Database URL** — it looks
   like:

   ```
   postgresql://aiip_user:************@dpg-xxxxxxxx-a/aiip_db
   ```

   This is the value for `DATABASE_URL` in step 3. Use the *internal* URL
   (not the external one) since the backend service will run in the same
   region — internal traffic is free and lower-latency. The driver
   (`psycopg2-binary`) accepts `postgresql://` directly, so no
   `+psycopg2` suffix is needed.

---

## 2. Create the backend web service

1. Render Dashboard → **New** → **Web Service**.
2. Connect the GitHub repository.
3. Configure:
   - **Root Directory**: `backend`
   - **Environment**: `Docker`
   - **Dockerfile Path**: `Dockerfile` (relative to the Root Directory
     above, i.e. `backend/Dockerfile`)
   - **Docker Build Context Directory**: `backend` (leave as Root
     Directory's default — this matches `docker-compose.yml`'s
     `context: ./backend`)
   - **Region**: same region as the database from step 1.
   - **Instance Type**: at least **Starter** — `torch` + `openai-whisper`
     need more than the free tier's 512 MB RAM/build memory.
4. **Health Check Path**: `/health` (matches the route in
   `backend/app/main.py`, returns 200 without touching the database).
5. Do not click **Create Web Service** yet — first add the environment
   variables in step 3 (Render lets you fill these in on the same create
   form before the first deploy).

---

## 3. Configure backend environment variables

Add the following on the service's **Environment** tab (or the create
form). These mirror [`.env.example`](../.env.example):

| Variable | Value | Notes |
|---|---|---|
| `ENVIRONMENT` | `production` | Disables `/docs`, `/redoc`, `/openapi.json` (gated on `DEBUG`, see below). |
| `DEBUG` | `false` | **Required** when `ENVIRONMENT=production` — the app refuses to start otherwise (`config.py` validator). |
| `DATABASE_URL` | the Internal Database URL from step 1 | No `+psycopg2` suffix needed. |
| `JWT_SECRET_KEY` | output of `openssl rand -hex 32` | Must be ≥ 32 chars. Generate a fresh value — do not reuse the `.env.example` placeholder. |
| `JWT_ALGORITHM` | `HS256` | Default; only HS256/384/512 accepted. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Or tighten for production (e.g. `60`). |
| `GEMINI_API_KEY` | your Google AI Studio key | **Required** — app fails to start if empty. |
| `MAX_QUESTIONS_PER_SESSION` | `10` | Optional, default shown. |
| `GEMINI_TIMEOUT_SECONDS` | `30` | Optional, default shown. |
| `WHISPER_MODEL` | `base` | `base` fits Starter-tier CPU/RAM. Larger models need more memory. |
| `ENABLE_AUDIO_PROCESSING` | `true` | Enables the Whisper + Gemini pipeline. |
| `MAX_TRANSCRIPT_CHARS` | `20000` | Optional, default shown. |
| `WHISPER_TIMEOUT_SECONDS` | `300` | Optional, default shown. |
| `UPLOAD_DIR` | `uploads` | Relative path, resolves to `/app/uploads` — matches the Disk mount path in step 5. |
| `MAX_UPLOAD_SIZE_MB` | `50` | Optional, default shown. |
| `CORS_ORIGINS` | *(placeholder for now)* | Set to the frontend's exact origin, e.g. `https://aiip-frontend.onrender.com`. **You won't know this URL until step 6** — set it to anything for now (e.g. `https://placeholder.onrender.com`) and come back to update it after the frontend is deployed (step 7 includes a reminder). |

Do **not** set `PORT` — Render injects it automatically, and the updated
`backend/Dockerfile` CMD (`--port ${PORT:-8000}`) reads it.

Click **Create Web Service**. The first build installs `torch`,
`openai-whisper`, and `ffmpeg`, so it can take 5–10 minutes.

---

## 4. Configure the pre-deploy migration command

The Docker image does not run migrations on boot (see
[DEPLOYMENT.md § 1](./DEPLOYMENT.md#1-database-migrations-alembic) for why).
On Render:

1. Open the backend service → **Settings** → **Build & Deploy**.
2. Set **Pre-Deploy Command** to:

   ```
   alembic upgrade head
   ```

3. Save changes.

This runs `alembic upgrade head` from `/app` (the image's `WORKDIR`, where
`alembic.ini` and `alembic/` live) using the same `DATABASE_URL` as the
service, **before** each deploy starts receiving traffic. It is idempotent,
so it's safe on every deploy including the first one against an empty
database.

---

## 5. Attach a persistent disk for uploaded audio

`UPLOAD_DIR=uploads` resolves to `/app/uploads` inside the container.
Render's filesystem is ephemeral — without a Disk, every deploy/restart
deletes previously uploaded audio (the DB rows referencing them remain,
breaking re-transcription). See
[DEPLOYMENT.md § 2](./DEPLOYMENT.md#2-persistent-storage) for full rationale.

1. Backend service → **Disks** tab → **Add Disk**.
2. **Name**: `uploads`.
3. **Mount Path**: `/app/uploads`.
4. **Size**: start with `1 GB` (monitor usage; `MAX_UPLOAD_SIZE_MB=50` per
   file is the only existing bound).
5. Save.

Attaching a Disk restricts the service to a single instance — this already
matches the app's design (single Uvicorn worker, in-process Whisper model
singleton).

---

## 6. Create the frontend static site

1. Render Dashboard → **New** → **Static Site**.
2. Connect the same GitHub repository.
3. Configure:
   - **Root Directory**: `frontend`
   - **Build Command**: `npm install && npm run build`
   - **Publish Directory**: `dist`
4. Add the environment variable from step 7 below *before* the first
   build, since Vite bakes it in at build time.
5. **Add a rewrite rule for client-side routing** (the app uses React
   Router's `BrowserRouter`, so direct navigation/refresh on routes like
   `/login` or `/sessions/<id>` must be served `index.html`, not a 404):
   - **Redirects/Rewrites** tab → **Add Rule**:
     - Source: `/*`
     - Destination: `/index.html`
     - Action: `Rewrite`
6. Click **Create Static Site**.

---

## 7. Configure frontend environment variables

On the Static Site's **Environment** tab, add:

| Variable | Value | Notes |
|---|---|---|
| `VITE_API_BASE_URL` | the backend's public URL from step 2, e.g. `https://aiip-backend.onrender.com` | No trailing slash. Build-time only — changing it triggers (or requires) a rebuild. |

After this builds and you have the frontend's URL (e.g.
`https://aiip-frontend.onrender.com`):

**Go back to the backend service (step 3) and update `CORS_ORIGINS`** to
this exact origin, then save — Render redeploys the backend automatically.
Without this, the browser blocks all API calls from the deployed frontend
with a CORS error.

---

## 8. Verify the deployment

1. **Backend health**: `curl https://<backend>.onrender.com/health` →
   ```json
   {"status": "healthy", "environment": "production", "version": "0.2.0", "audio_processing_enabled": true}
   ```
2. **Docs disabled**: `https://<backend>.onrender.com/docs` → 404 (expected
   in production, since `DEBUG=false`).
3. **Migrations applied**: check the Pre-Deploy Command logs (Render →
   service → **Events**/**Logs**) for `alembic upgrade head` output ending
   in the latest revision, with no errors.
4. **Frontend loads**: open `https://<frontend>.onrender.com` → login/register
   page renders.
5. **End-to-end**: register a user, log in, create a session, generate
   questions, upload an audio response, and confirm the processing status
   card polls and eventually shows the transcript and analysis. This
   exercises CORS, JWT auth, the database, the Disk-backed upload path, and
   the Whisper/Gemini pipeline together.

---

## 9. Troubleshooting

**Backend won't start: `ValidationError` for `Settings`**
One of `DATABASE_URL`, `JWT_SECRET_KEY` (≥ 32 chars), or `GEMINI_API_KEY` is
missing/empty, or `ENVIRONMENT=production` with `DEBUG=true`. Check the
deploy logs — pydantic prints the exact field that failed. Fix the env var
and redeploy.

**Frontend shows "Unable to reach the server"**
`VITE_API_BASE_URL` was unset/wrong at *build* time (it's baked into the
JS bundle). Set/correct it on the Static Site's Environment tab and trigger
a new deploy (Manual Deploy → Deploy latest commit).

**Browser console shows a CORS error**
`CORS_ORIGINS` on the backend doesn't include the frontend's exact origin
(scheme + host, no trailing slash, no path). Update it and save — Render
redeploys the backend automatically. Multiple origins can be comma-separated.

**Refreshing `/login` or `/sessions/<id>` on the frontend returns a 404**
The Static Site's rewrite rule (step 6.5) is missing. Add `/* → /index.html`
(Rewrite).

**`alembic upgrade head` fails in the Pre-Deploy step**
Usually a `DATABASE_URL` mismatch (wrong host/credentials) or the database
isn't reachable from the backend's region. Confirm you used the *Internal*
Database URL and that the database and web service are in the same region.

**Uploaded audio "disappears" after a redeploy / re-transcription fails with a missing file**
The Disk from step 5 isn't attached, or its mount path doesn't match
`UPLOAD_DIR` (`/app/uploads`). Check **Disks** tab and `UPLOAD_DIR`.

**First transcription is very slow**
Expected — the Whisper model (`base`, ~74 MB) downloads to
`~/.cache/whisper` on first use after each cold start/deploy (this cache is
intentionally not persisted; see
[DEPLOYMENT.md § 2](./DEPLOYMENT.md#what-can-be-regenerated-no-persistence-required)).
Subsequent transcriptions in the same running instance are fast.

**Build fails on `torch`/`openai-whisper` install (OOM or timeout)**
The backend's Instance Type is too small. Upgrade from Starter to a plan
with more build memory/CPU.

**502/503 immediately after deploy, then recovers**
Normal — the container is still installing dependencies/starting Uvicorn.
Render retries the health check (`/health`) until the service responds.
