# Multi-stage build: Frontend + Backend
# Stage 1: Build Next.js frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /app/web
ENV NEXT_IGNORE_INCORRECT_LOCKFILE=1 \
    NEXT_TELEMETRY_DISABLED=1 \
    INTERNAL_API_URL=http://localhost:8000
COPY web/package.json web/package-lock.json ./
RUN npm ci --include=optional
COPY web/ .
RUN npm run build:zeabur \
    && test -d .next/standalone \
    && test -d .next/static \
    && test -d public \
    && find .next -maxdepth 2 -type d | sort

# Stage 2: Python backend + Next standalone runtime
FROM node:22-bookworm-slim AS backend
WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv build-essential curl git ca-certificates \
    && python3 -m venv /opt/venv \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    NEXT_TELEMETRY_DISABLED=1 \
    INTERNAL_API_URL=http://localhost:8000 \
    API_PORT=8000 \
    KRONOS_REPO_PATH=/app/external/Kronos \
    HF_HOME=/app/.cache/huggingface \
    KRONOS_MODEL_ID=NeoQuasar/Kronos-small \
    KRONOS_ENABLE_REAL_MODEL=0 \
    MALLOC_ARENA_MAX=2 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_MAX_THREADS=1 \
    TOKENIZERS_PARALLELISM=false

ARG KRONOS_REPO_URL=https://github.com/shiyu-coder/Kronos.git
ARG INSTALL_KRONOS_RUNTIME=0

# Install Python deps
COPY pyproject.toml requirements.txt ./
COPY src/ src/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e ".[deploy]" \
    && if [ "$INSTALL_KRONOS_RUNTIME" = "1" ]; then pip install --no-cache-dir -e ".[kronos]"; fi

# Fetch upstream Kronos source code for real inference. Model weights stay out of git/image.
RUN mkdir -p external \
    && git clone --depth=1 "$KRONOS_REPO_URL" external/Kronos \
    && test -f external/Kronos/model/__init__.py

# Copy frontend build
COPY --from=frontend-builder /app/web/.next/standalone web/
COPY --from=frontend-builder /app/web/.next/static web/.next/static
COPY --from=frontend-builder /app/web/public web/public

COPY scripts/zeabur_start.sh scripts/zeabur_start.sh
RUN chmod +x scripts/zeabur_start.sh

EXPOSE 8000 3000

CMD ["./scripts/zeabur_start.sh"]
