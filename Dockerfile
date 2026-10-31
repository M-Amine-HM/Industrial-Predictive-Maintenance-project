# All-in-one image: React dashboard + FastAPI in one container (for Render / HF Spaces / Fly.io).
# Local multi-container setup lives in docker-compose.yml.
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PM_SERVE_UI=1 PM_STATIC_DIR=/app/ui PORT=8000 PM_WORKERS=2 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY src/ src/
COPY models/ models/
COPY data/ data/
COPY reports/figures/ reports/figures/
COPY backend/app/ backend/app/
COPY --from=ui /ui/dist /app/ui
RUN useradd --create-home --uid 1000 appuser
USER appuser
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, sys, urllib.request; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=4).status == 200 else 1)"
# Hosts inject $PORT (Render, Fly); HF Spaces expects 7860 -> set PORT=7860 there
CMD ["sh", "-c", "rm -rf \"$PROMETHEUS_MULTIPROC_DIR\" && mkdir -p \"$PROMETHEUS_MULTIPROC_DIR\" && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${PM_WORKERS} --proxy-headers --forwarded-allow-ips '*'"]
