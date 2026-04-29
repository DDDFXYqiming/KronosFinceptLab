# Multi-stage build: Frontend + Backend
# Stage 1: Build Next.js frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
RUN npm run build

# Stage 2: Python backend
FROM python:3.11-slim AS backend
WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml requirements.txt ./
COPY src/ src/
RUN pip install --no-cache-dir -e ".[api,astock]"

# Copy frontend build
COPY --from=frontend-builder /app/web/.next/standalone web/
COPY --from=frontend-builder /app/web/.next/static web/.next/static
COPY --from=frontend-builder /app/web/public web/public

# Copy config files
COPY docker-compose.yml ./

EXPOSE 8000 3000

CMD ["uvicorn", "kronos_fincept.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
