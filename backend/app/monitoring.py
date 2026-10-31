"""Request IDs, latency timing, structured JSON logs and Prometheus metrics."""
import json
import logging
import os
import time
import uuid
from collections import Counter as Tally

from fastapi import Request
from prometheus_client import (CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest,
                               multiprocess)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

REGISTRY = CollectorRegistry()
REQUESTS = Counter("pm_http_requests_total", "HTTP requests", ["method", "route", "status"], registry=REGISTRY)
LATENCY = Histogram("pm_http_request_duration_seconds", "Request latency", ["method", "route"], registry=REGISTRY,
                    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))
PREDICTIONS = Counter("pm_predictions_total", "Scored machines by decision", ["status", "failure"], registry=REGISTRY)
VALIDATION_ERRORS = Counter("pm_validation_errors_total", "Rejected inputs", ["source"], registry=REGISTRY)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
                   "logger": record.name, "msg": record.getMessage()}
        payload.update(getattr(record, "extra_fields", {}))
        return json.dumps(payload)


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("pm")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    logger.setLevel(level)
    return logger


log = setup_logging()


class ObservabilityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, model_version: callable):
        super().__init__(app)
        self.model_version = model_version

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            elapsed = time.perf_counter() - start
            route = getattr(request.scope.get("route"), "path", "unmatched")
            if route != "/metrics":
                REQUESTS.labels(request.method, route, str(status)).inc()
                LATENCY.labels(request.method, route).observe(elapsed)
            log.info("request", extra={"extra_fields": {
                "request_id": rid, "method": request.method, "path": request.url.path, "route": route,
                "status": status, "duration_ms": round(elapsed * 1000, 2),
                "client": request.client.host if request.client else None}})
        response.headers["X-Request-ID"] = rid
        response.headers["X-Process-Time-ms"] = f"{elapsed * 1000:.2f}"
        response.headers["X-Model-Version"] = self.model_version()
        return response


def record_predictions(frame) -> None:
    """Count decisions from a predict_frame() result (plain Counter: no pandas groupby per request)."""
    for (status, failure), n in Tally(zip(frame["status"], frame["predicted_failure"])).items():
        PREDICTIONS.labels(status, failure).inc(n)


def metrics_response() -> Response:
    # With several uvicorn workers, each process writes its samples to PROMETHEUS_MULTIPROC_DIR;
    # aggregate them so /metrics reports the whole container, not one random worker.
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
