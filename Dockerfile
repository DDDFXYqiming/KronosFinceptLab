# Multi-stage build: Frontend + Backend
# Stage 1: Build Next.js frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /app/web
ARG NPM_REGISTRY=https://registry.npmjs.org/
ENV NEXT_IGNORE_INCORRECT_LOCKFILE=1 \
    NEXT_TELEMETRY_DISABLED=1 \
    INTERNAL_API_URL=http://127.0.0.1:8000 \
    NPM_CONFIG_REGISTRY=${NPM_REGISTRY} \
    NPM_CONFIG_FETCH_RETRIES=5 \
    NPM_CONFIG_FETCH_RETRY_FACTOR=2 \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=20000 \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=120000 \
    NPM_CONFIG_FETCH_TIMEOUT=300000 \
    NPM_CONFIG_AUDIT=false \
    NPM_CONFIG_FUND=false
COPY web/package.json web/package-lock.json ./
RUN set -eux; \
    npm config set registry "$NPM_CONFIG_REGISTRY"; \
    for registry in "$NPM_CONFIG_REGISTRY" "https://registry.npmmirror.com"; do \
        npm config set registry "$registry"; \
        for attempt in 1 2 3; do \
            if npm ci --include=optional --no-audit --no-fund; then \
                exit 0; \
            fi; \
            if [ "$registry" = "https://registry.npmmirror.com" ] && [ "$attempt" = "3" ]; then \
                exit 1; \
            fi; \
            sleep $((attempt * 10)); \
        done; \
    done
COPY web/ .
RUN npm run build:zeabur \
    && test -d .next/standalone \
    && test -d .next/static \
    && test -d public \
    && find .next -maxdepth 2 -type d | sort

# Stage 2: Build Python backend runtime with CPU-only Kronos deps.
FROM node:22-bookworm-slim AS backend-builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv build-essential curl git ca-certificates \
    && python3 -m venv /opt/venv \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

ARG KRONOS_REPO_URL=https://github.com/shiyu-coder/Kronos.git
ARG KRONOS_REPO_REF=67b630e67f6a18c9e9be918d9b4337c960db1e9a
ARG INSTALL_KRONOS_RUNTIME=1
ARG PYTORCH_CPU_VERSION=2.3.1+cpu

COPY pyproject.toml requirements.txt ./
COPY src/ src/
RUN pip install --no-cache-dir --upgrade pip \
    && if [ "$INSTALL_KRONOS_RUNTIME" = "1" ]; then \
        pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==$PYTORCH_CPU_VERSION"; \
        pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -e ".[deploy,kronos]"; \
    else \
        pip install --no-cache-dir -e ".[deploy]"; \
    fi

RUN mkdir -p external/Kronos \
    && git -C external/Kronos init \
    && git -C external/Kronos remote add origin "$KRONOS_REPO_URL" \
    && git -C external/Kronos fetch --depth=1 origin "$KRONOS_REPO_REF" \
    && git -C external/Kronos checkout --detach FETCH_HEAD \
    && test "$(git -C external/Kronos rev-parse HEAD)" = "$KRONOS_REPO_REF" \
    && test -f external/Kronos/model/__init__.py \
    && rm -rf external/Kronos/.git

# Stage 3: Python backend + Next standalone runtime. Keep build tools out.
FROM node:22-bookworm-slim AS backend
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# KRONOS_MODEL_ID options: NeoQuasar/Kronos-base (default), NeoQuasar/Kronos-mini (fastest)
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    NEXT_TELEMETRY_DISABLED=1 \
    INTERNAL_API_URL=http://127.0.0.1:8000 \
    API_HOST=127.0.0.1 \
    API_PORT=8000 \
    KRONOS_REPO_PATH=/app/external/Kronos \
    HF_HOME=/app/.cache/huggingface \
    KRONOS_MODEL_ID=NeoQuasar/Kronos-base \
    KRONOS_ENABLE_REAL_MODEL=1 \
    KRONOS_ALLOW_DRY_RUN=0 \
    KRONOS_PREWARM_ON_STARTUP=1 \
    KRONOS_LOG_FORMAT=json \
    KRONOS_LOG_ENABLE_FILE=0 \
    MALLOC_ARENA_MAX=2 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_MAX_THREADS=1 \
    TOKENIZERS_PARALLELISM=false

ARG KRONOS_APP_VERSION=v10.9.0
ARG KRONOS_BUILD_COMMIT=unknown
ARG KRONOS_BUILD_REF=unknown
ARG KRONOS_BUILD_SOURCE=docker

ENV KRONOS_APP_VERSION=$KRONOS_APP_VERSION \
    KRONOS_BUILD_COMMIT=$KRONOS_BUILD_COMMIT \
    KRONOS_BUILD_REF=$KRONOS_BUILD_REF \
    KRONOS_BUILD_SOURCE=$KRONOS_BUILD_SOURCE

COPY --from=backend-builder /opt/venv /opt/venv
COPY --from=backend-builder /app/src src/
COPY --from=backend-builder /app/external/Kronos external/Kronos

# Copy frontend build
COPY --from=frontend-builder /app/web/.next/standalone web/
COPY --from=frontend-builder /app/web/.next/static web/.next/static
COPY --from=frontend-builder /app/web/public web/public

COPY scripts/zeabur_start.sh scripts/zeabur_start.sh
RUN chmod +x scripts/zeabur_start.sh

EXPOSE 3000

CMD ["./scripts/zeabur_start.sh"]
