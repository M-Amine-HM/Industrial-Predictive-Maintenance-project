from contextlib import asynccontextmanager
from typing import Literal

import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, errors
from .drift import DriftMonitor
from .errors import InputError
from .monitoring import ObservabilityMiddleware, log, metrics_response, record_predictions, setup_logging
from .schemas import BatchResponse, DriftResponse, ErrorResponse, Prediction, SensorReading
from .security import protect
from .service import ModelService
from .uploads import parse_upload
from features import RAW_COLUMNS

state: dict = {}
ERRORS = {400: {"model": ErrorResponse, "description": "Invalid input (wrong types, ranges, file format)"},
          413: {"model": ErrorResponse, "description": "Payload too large"}}


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(config.LOG_LEVEL)
    state["svc"] = ModelService()
    data = pd.read_csv(config.DATA_PATH) if config.DATA_PATH.exists() else None
    state["data"] = data
    state["drift"] = DriftMonitor(data, config.DRIFT_WINDOW, config.DRIFT_MIN_SAMPLES) if data is not None else None
    log.info("startup", extra={"extra_fields": {"model_version": state["svc"].version,
                                                "auth": bool(config.API_KEY), "rate_limit": config.RATE_LIMIT_PER_MIN}})
    yield
    state.clear()


app = FastAPI(
    title="Industrial Predictive Maintenance API",
    description="Failure-type classification tuned for a low False Discovery Rate, "
                "plus remaining-useful-life estimation (AI4I 2020). Invalid input is rejected with 400.",
    version="1.1.0",
    lifespan=lifespan,
)
errors.register(app)
app.add_middleware(ObservabilityMiddleware, model_version=lambda: state["svc"].version if "svc" in state else "unloaded")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-Request-ID", "X-Process-Time-ms", "X-Model-Version"])
if config.FIG_DIR.exists():
    app.mount("/figures", StaticFiles(directory=config.FIG_DIR), name="figures")


def svc() -> ModelService:
    return state["svc"]


def _observe(raw: pd.DataFrame, out: pd.DataFrame) -> None:
    record_predictions(out)
    if state.get("drift") is not None:
        state["drift"].observe(raw)


# ------------------------------------------------------------------ meta
@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "model_loaded": "svc" in state,
            "model_version": state["svc"].version if "svc" in state else None}


@app.get("/metrics", tags=["meta"], include_in_schema=False)
def metrics():
    return metrics_response()


@app.get("/api/model-info", tags=["meta"])
def model_info():
    s = svc()
    ranges = {}
    data = state.get("data")
    if data is not None:
        for c in RAW_COLUMNS[1:]:
            ranges[c] = {"min": float(data[c].min()), "max": float(data[c].max()),
                         "median": float(data[c].median())}
    return {
        "model_version": s.version,
        "mlflow": s.lineage,
        "classes": s.classes,
        "threshold": s.threshold,
        "fdr_target": s.cfg["fdr_target"],
        "twf_advisory_wear_min": s.cfg["twf_advisory_wear_min"],
        "features": s.cfg["features"],
        "metrics": s.metrics,
        "sensor_ranges": ranges,
        "limits": {"max_batch_rows": config.MAX_BATCH_ROWS, "max_upload_mb": config.MAX_UPLOAD_BYTES / 1e6},
    }


# ------------------------------------------------------------- predictions
@app.post("/api/predict", response_model=Prediction, responses=ERRORS, tags=["predict"],
          dependencies=[Depends(protect)])
def predict(reading: SensorReading, explain: bool = True):
    raw = reading.to_raw()
    result = svc().predict_one(raw, explain=explain)
    _observe(pd.DataFrame([raw]), pd.DataFrame([{k: result[k] for k in ("status", "predicted_failure")}]))
    return result


@app.post("/api/predict/batch", response_model=BatchResponse, responses=ERRORS, tags=["predict"],
          dependencies=[Depends(protect)])
def predict_batch(readings: list[SensorReading]):
    if not readings:
        raise InputError("Batch is empty", [{"field": "body", "message": "expected at least one reading"}])
    if len(readings) > config.MAX_BATCH_ROWS:
        raise InputError(f"Batch limited to {config.MAX_BATCH_ROWS:,} rows", status_code=413)
    return _batch_response(pd.DataFrame([r.to_raw() for r in readings]))


@app.post("/api/predict/file", response_model=BatchResponse, responses=ERRORS, tags=["predict"],
          dependencies=[Depends(protect)])
async def predict_file(file: UploadFile = File(..., description="CSV or JSON file of readings")):
    """Score a .csv (AI4I columns) or .json (list of readings, or {"readings": [...]}) file."""
    return _batch_response(parse_upload(file.filename, await file.read()))


@app.post("/api/predict/csv", response_model=BatchResponse, responses=ERRORS, tags=["predict"],
          dependencies=[Depends(protect)])
async def predict_csv(file: UploadFile = File(...)):
    return _batch_response(parse_upload(file.filename, await file.read(), expect="csv"))


def _batch_response(raw: pd.DataFrame) -> dict:
    raw = raw.reset_index(drop=True)
    out = svc().predict_frame(raw)
    _observe(raw, out)
    alarms = out[out["alarm"]]
    rows = out[["alarm", "status", "failure_probability", "predicted_failure", "rul_minutes",
                "tool_replacement_advised"]].assign(row=out.index).to_dict("records")
    return {
        "n_rows": len(out),
        "n_alarms": int(out["alarm"].sum()),
        "n_advisories": int((out["status"] == "advisory").sum()),
        "by_failure": {k: int(v) for k, v in alarms["predicted_failure"].value_counts().items()},
        "rows": rows,
    }


# ------------------------------------------------------------------ drift
@app.get("/api/drift", response_model=DriftResponse, tags=["monitoring"], dependencies=[Depends(protect)])
def drift():
    """PSI of recently scored inputs vs the training distribution (rolling window)."""
    if state.get("drift") is None:
        raise HTTPException(404, "Reference data not available")
    return state["drift"].report()


@app.post("/api/drift/file", response_model=DriftResponse, responses=ERRORS, tags=["monitoring"],
          dependencies=[Depends(protect)])
async def drift_file(file: UploadFile = File(...)):
    """PSI of an uploaded batch vs the training distribution (does not touch the rolling window)."""
    if state.get("drift") is None:
        raise HTTPException(404, "Reference data not available")
    return state["drift"].report(parse_upload(file.filename, await file.read()))


@app.delete("/api/drift", tags=["monitoring"], dependencies=[Depends(protect)])
def drift_reset():
    if state.get("drift") is not None:
        state["drift"].reset()
    return {"status": "reset"}


# -------------------------------------------------------------- demo data
@app.get("/api/samples", response_model=SensorReading, response_model_by_alias=False, tags=["demo"])
def sample(kind: Literal["healthy", "TWF", "HDF", "PWF", "OSF", "random"] = Query("random")):
    """A real reading from the AI4I dataset, for demos."""
    data = state.get("data")
    if data is None:
        raise HTTPException(404, "Dataset not available")
    if kind == "healthy":
        pool = data[data["Machine failure"] == 0]
    elif kind == "random":
        pool = data
    else:
        pool = data[data[kind] == 1]
    row = pool.sample(1).iloc[0]
    return SensorReading.model_validate({"Type": str(row["Type"]),
                                         **{c: float(row[c]) for c in RAW_COLUMNS[1:]}})


@app.get("/api/figures", tags=["demo"])
def figures():
    if not config.FIG_DIR.exists():
        return []
    return [{"name": p.stem, "url": f"/figures/{p.name}"} for p in sorted(config.FIG_DIR.glob("*.png"))]


# Single-container mode: serve the built dashboard at "/" (mounted last so API routes win)
if config.SERVE_UI and (config.STATIC_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="ui")
