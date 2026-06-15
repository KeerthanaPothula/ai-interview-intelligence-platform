# -------------------------------------------------------------
# Base image — python:3.12-slim
# slim = Debian without compilers, manpages, or docs.
# Smaller attack surface and faster pulls than the full image.
# 3.12 is the current stable release (security updates until 2028).
# -------------------------------------------------------------
FROM python:3.12-slim

# Stop Python from writing .pyc bytecode files into the container.
# They waste space and cause permission noise on the bind-mounted volume.
ENV PYTHONDONTWRITEBYTECODE=1

# Force Python stdout/stderr to be unbuffered so uvicorn logs appear
# in `docker-compose logs` immediately rather than in large batches.
ENV PYTHONUNBUFFERED=1

# All subsequent commands and the running process use /app as root.
WORKDIR /app

# -------------------------------------------------------------
# System dependencies — ffmpeg
# Whisper (openai-whisper) shells out to the ffmpeg binary to decode
# uploaded audio (mp3, wav, webm, ogg, mp4, m4a) into the raw PCM
# format it operates on. Without it, every transcription fails with
# "ffmpeg is not installed or not available in PATH" — see
# requirements.txt for the corresponding note. Installed as its own
# layer, before requirements.txt is copied, so editing Python deps
# never invalidates this (rarely-changing) layer.
# --no-install-recommends keeps the apt closure minimal; the apt
# index is removed afterwards so it isn't carried in the image layer.
# -------------------------------------------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# -------------------------------------------------------------
# Dependency installation — runs as its own layer.
# Docker only rebuilds this layer when requirements.txt changes.
# Copying just requirements.txt before the source code is the
# standard technique for maximising build cache hits.
# -------------------------------------------------------------
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt
# --no-cache-dir prevents pip from writing a local HTTP cache inside
# the image layer, keeping the final image measurably smaller.

# -------------------------------------------------------------
# Uploads directory
# Created here so the path exists even before the Docker volume
# from docker-compose is mounted over it at runtime.
# -------------------------------------------------------------
RUN mkdir -p /app/uploads

# -------------------------------------------------------------
# Application source
# Copied last so that editing .py files does not invalidate the
# expensive pip install layer above.
# In dev, docker-compose mounts ./backend:/app as a bind volume,
# so this layer is effectively bypassed — it exists for production
# builds that do not use a volume mount.
# -------------------------------------------------------------
COPY . .

# Document the port the application listens on.
# Does not actually publish the port — docker-compose handles that.
EXPOSE 8000

# -------------------------------------------------------------
# Production startup command.
#
# --reload is intentionally NOT used here: it enables Uvicorn's
# file-watcher/auto-restart, which is a development-only feature and
# adds unnecessary overhead in a deployed container. Local development
# uses docker-compose's own `command:` override (with --reload and a
# bind-mounted source tree) instead — that override takes precedence
# over this CMD and is unaffected by this change.
#
# Workers: deliberately a single worker (Uvicorn's default when
# --workers is omitted). transcription_service.py loads the Whisper
# model once per process into a module-level singleton and guards
# concurrent transcriptions with a process-local
# threading.Semaphore(1). Running multiple worker processes would load
# a separate copy of the Whisper model into memory per worker
# (multiplying memory usage) and give each worker its own semaphore,
# defeating the "one transcription at a time" guarantee. Horizontal
# scaling should be done via additional service instances (or a shared
# job queue, in a future phase), not via --workers.
#
# Port: Render (and most PaaS hosts) assign the container a port at
# runtime via the PORT environment variable and route external traffic
# to it — a hardcoded --port 8000 would not be reachable. Shell-form
# CMD (rather than exec-form JSON array) is required so ${PORT:-8000}
# is expanded by the shell: it binds to Render's assigned port in
# production and falls back to 8000 for local `docker run` /
# docker-compose, where EXPOSE 8000 and the published port mapping
# still apply.
# -------------------------------------------------------------
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
