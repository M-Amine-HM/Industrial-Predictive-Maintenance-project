# Build context: repository root  (docker build -f backend/Dockerfile .)
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
# LightGBM needs the OpenMP runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

# Artifacts the service needs at runtime
COPY src/ src/
COPY models/ models/
COPY data/ data/
COPY reports/figures/ reports/figures/
COPY backend/app/ backend/app/

# ---- test stage: docker build --target test -f backend/Dockerfile .
FROM base AS test
RUN pip install pytest httpx
COPY backend/tests/ backend/tests/
WORKDIR /app/backend
RUN PM_LOG_LEVEL=WARNING python -m pytest -q -p no:cacheprovider

# ---- runtime stage (default)
FROM base AS runtime
RUN useradd --create-home --uid 1000 appuser
USER appuser
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
# PM_WORKERS uvicorn processes (4 workers measured at ~2.8x the throughput of 1).
# Prometheus multiprocess mode aggregates /metrics across workers; the drift window is
# per worker, so /api/drift reports a random subsample of traffic (still representative).
ENV PM_WORKERS=1 PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
CMD ["sh", "-c", "rm -rf \"$PROMETHEUS_MULTIPROC_DIR\" && mkdir -p \"$PROMETHEUS_MULTIPROC_DIR\" && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers \"$PM_WORKERS\" --proxy-headers --forwarded-allow-ips '*'"]
