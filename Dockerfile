# Multi-stage build: Frontend + Backend
# Optimized for 4GB memory environments (Zeabur)

# ────────────────────────────────────────────────────────────────
# Stage 1: Build Next.js frontend (memory-constrained)
# ────────────────────────────────────────────────────────────────
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
    NPM_CONFIG_FUND=false \
    NODE_OPTIONS="--max-old-space-size=512"
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
COPY web/ ./
RUN npm run build:zeabur \
    && test -d .next/standalone \
    && test -d .next/static \
    && test -d public

# ────────────────────────────────────────────────────────────────
# Stage 2: Build Python backend (split pip installs to save memory)
# ────────────────────────────────────────────────────────────────
FROM node:22-bookworm-slim AS backend-builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv build-essential curl git ca-certificates \
    && python3 -m venv /opt/venv \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_NO_BUILD_ISOLATION=1 \
    MALLOC_ARENA_MAX=2

ARG KRONOS_REPO_URL=https://github.com/shiyu-coder/Kronos.git
ARG KRONOS_REPO_REF=67b630e67f6a18c9e9be918d9b4337c960db1e9a
ARG INSTALL_KRONOS_RUNTIME=1
ARG PYTORCH_CPU_VERSION=2.3.1+cpu

COPY pyproject.toml requirements.txt ./
COPY src/ src/

# Step 1: Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Step 2: Install PyTorch CPU FIRST (separate from resolver to save memory)
RUN if [ "$INSTALL_KRONOS_RUNTIME" = "1" ]; then \
        pip install --no-cache-dir --no-deps \
            --index-url https://download.pytorch.org/whl/cpu \
            "torch==${PYTORCH_CPU_VERSION}" ; \
    fi

# Step 3: Install project deps (torch already present, resolver skips it)
RUN if [ "$INSTALL_KRONOS_RUNTIME" = "1" ]; then \
        pip install --no-cache-dir \
            --extra-index-url https://download.pytorch.org/whl/cpu \
            -e ".[deploy,kronos]" ; \
    else \
        pip install --no-cache-dir -e ".[deploy]" ; \
    fi

# Step 4: Clone Kronos model code (shallow, no git history kept)
RUN mkdir -p external/Kronos \
    && git -c http.sslVerify=false -C external/Kronos init \
    && git -c http.sslVerify=false -C external/Kronos remote add origin "$KRONOS_REPO_URL" \
    && git -C external/Kronos fetch --depth=1 origin "$KRONOS_REPO_REF" \
    && git -c http.sslVerify=false -C external/Kronos checkout --detach FETCH_HEAD \
    && test "$(git -C external/Kronos rev-parse HEAD)" = "$KRONOS_REPO_REF" \
    && test -f external/Kronos/model/__init__.py \
    && rm -rf external/Kronos/.git

# Step 5: Clone GenericAgent (shallow, for runtime AI agent capabilities)
ARG GENERICAGENT_REPO_URL=https://github.com/lsdefine/GenericAgent.git
ARG GENERICAGENT_REPO_REF=main
RUN mkdir -p external/genericagent \
    && git -c http.sslVerify=false -C external/genericagent init \
    && git -c http.sslVerify=false -C external/genericagent remote add origin "$GENERICAGENT_REPO_URL" \
    && git -C external/genericagent fetch --depth=1 origin "$GENERICAGENT_REPO_REF" \
    && git -c http.sslVerify=false -C external/genericagent checkout --detach FETCH_HEAD \
    && test -f external/genericagent/ga.py \
    && rm -rf external/genericagent/.git \
    && pip install --no-cache-dir openai requests pydantic prompt_toolkit rich

# Step 6: Generate GA mykey.py — reads from Kronos env vars at runtime (no secrets baked into image!)
RUN printf '%s\n' \
    'import os' \
    '' \
    'native_oai_config = {' \
    "    'name': 'minimax'," \
    "    'apikey': os.getenv('LLM_API_KEY', '')," \
    "    'apibase': os.getenv('LLM_BASE_URL', 'https://api.minimaxi.com/v1')," \
    "    'model': os.getenv('LLM_MODEL', 'MiniMax-M3')," \
    "    'api_mode': 'chat_completions'," \
    '}' \
    '' \
    'native_oai_backup_1 = {' \
    "    'name': 'kimi'," \
    "    'apikey': os.getenv('LLM_FALLBACK_1_API_KEY', '')," \
    "    'apibase': os.getenv('LLM_FALLBACK_1_BASE_URL', 'https://api.moonshot.cn/v1')," \
    "    'model': os.getenv('LLM_FALLBACK_1_MODEL', 'kimi-for-coding')," \
    "    'api_mode': 'chat_completions'," \
    '}' \
    '' \
    'native_oai_backup_2 = {' \
    "    'name': 'mimo'," \
    "    'apikey': os.getenv('LLM_FALLBACK_2_API_KEY', '')," \
    "    'apibase': os.getenv('LLM_FALLBACK_2_BASE_URL', '')," \
    "    'model': os.getenv('LLM_FALLBACK_2_MODEL', '')," \
    "    'api_mode': 'chat_completions'," \
    '}' \
    '' \
    'mixin_config = {' \
    "    'llm_nos': ['minimax', 'kimi', 'mimo']," \
    "    'max_retries': 3," \
    "    'base_delay': 0.5," \
    '}' \
    > external/genericagent/mykey.py

# ────────────────────────────────────────────────────────────────
# Stage 3: Python backend + Next standalone runtime. Keep build tools out.
# ────────────────────────────────────────────────────────────────
FROM node:22-bookworm-slim AS backend
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Override Node.js entrypoint to prevent it from interpreting .sh files
ENTRYPOINT []

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src:/app/external/genericagent \
    GENERICAGENT_HOME=/app/external/genericagent \
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
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_MAX_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1 \
    TOKENIZERS_PARALLELISM=false

# Low-memory deployments can override KRONOS_PREWARM_ON_STARTUP=0 at runtime.

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
COPY --from=backend-builder /app/external/genericagent external/genericagent

# Copy frontend build
COPY --from=frontend-builder /app/web/.next/standalone web/
COPY --from=frontend-builder /app/web/.next/static web/.next/static
COPY --from=frontend-builder /app/web/public web/public

COPY scripts/zeabur_start.sh scripts/zeabur_start.sh
COPY scripts/ga scripts/ga
RUN tr -d "\r" < scripts/zeabur_start.sh > scripts/_tmp.sh && \
    mv scripts/_tmp.sh scripts/zeabur_start.sh && \
    chmod +x scripts/zeabur_start.sh && \
    tr -d "\r" < scripts/ga > scripts/_tmp_ga.sh && \
    mv scripts/_tmp_ga.sh scripts/ga && \
    chmod +x scripts/ga

EXPOSE 3000

CMD ["./scripts/zeabur_start.sh"]
