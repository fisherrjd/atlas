# Stage 1 — build the Vue SPA
# pinned to the devshell's bun — vue-tsc 3 mis-resolves .vue modules under
# some newer bun runtimes
FROM oven/bun:1.3.13 AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/bun.lock* ./
RUN bun install --frozen-lockfile
COPY frontend/ .
RUN bun run build

# Stage 2 — Python app
FROM python:3.13-slim

# gh: sync shells out to the GitHub CLI (auth comes from a mounted config or
# GH_TOKEN). tzdata: scheduler cron times.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gh tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies (cached layer — only reruns when lock file changes)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Application code
COPY atlas/ ./atlas/
COPY main.py ./

# Built SPA from the first stage
COPY --from=frontend-build /build/dist ./frontend/dist/

# uid 1001 matches jade on eldo — hostPath data dir and the read-only gh
# config mount are owned by that uid
RUN adduser --disabled-password --gecos "" --uid 1001 appuser && chown -R appuser /app
USER appuser

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 3040

CMD ["uvicorn", "atlas.main:app", "--host", "0.0.0.0", "--port", "3040"]
