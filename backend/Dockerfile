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

# Default start command.
# docker-compose overrides this with its own `command:` key in dev,
# but this makes the image runnable standalone with:
#   docker run --env-file .env aiip-backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
