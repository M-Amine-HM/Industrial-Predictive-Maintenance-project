import io
from contextlib import asynccontextmanager
from typing import Literal

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
from .schemas import BatchResponse, Prediction, SensorReading
from .service import ModelService
from features import RAW_COLUMNS

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["svc"] = ModelService()
    state["data"] = pd.read_csv(config.DATA_PATH) if config.DATA_PATH.exists() else None
    yield
    state.clear()


app = FastAPI(
    title="Industrial Predictive Maintenance API",
    description="Failure-type classification tuned for a low False Discovery Rate, "
                "plus remaining-useful-life estimation (AI4I 2020).",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
if config.FIG_DIR.exists():
    app.mount("/figures", StaticFiles(directory=config.FIG_DIR), name="figures")


def svc() -> ModelService:
    return state["svc"]


@app.get("/api/health")
def health():
    return {"status": "ok", "model_loaded": "svc" in state}


@app.get("/api/model-info")
def model_info():
    s = svc()
    ranges = {}
    data = state.get("data")
    if data is not None:
        for c in RAW_COLUMNS[1:]:
            ranges[c] = {"min": float(data[c].min()), "max": float(data[c].max()),
                         "median": float(data[c].median())}
    return {
        "classes": s.classes,
        "threshold": s.threshold,
        "fdr_target": s.cfg["fdr_target"],
        "twf_advisory_wear_min": s.cfg["twf_advisory_wear_min"],
        "features": s.cfg["features"],
        "metrics": s.metrics,
        "sensor_ranges": ranges,
    }


@app.post("/api/predict", response_model=Prediction)
def predict(reading: SensorReading, explain: bool = True):
    return svc().predict_one(reading.to_raw(), explain=explain)


@app.post("/api/predict/batch", response_model=BatchResponse)
def predict_batch(readings: list[SensorReading]):
    if not readings:
        raise HTTPException(422, "Empty batch")
    if len(readings) > config.MAX_BATCH_ROWS:
        raise HTTPException(413, f"Batch limited to {config.MAX_BATCH_ROWS} rows")
    return _batch_response(pd.DataFrame([r.to_raw() for r in readings]))


@app.post("/api/predict/csv", response_model=BatchResponse)
async def predict_csv(file: UploadFile = File(...)):
    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
        df = svc().normalise_columns(df)
    except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as e:
        raise HTTPException(422, f"Invalid CSV: {e}")
    if df.empty:
        raise HTTPException(422, "CSV has no rows")
    if len(df) > config.MAX_BATCH_ROWS:
        raise HTTPException(413, f"CSV limited to {config.MAX_BATCH_ROWS} rows")
    return _batch_response(df)


def _batch_response(raw: pd.DataFrame) -> dict:
    out = svc().predict_frame(raw.reset_index(drop=True))
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


@app.get("/api/samples", response_model=SensorReading, response_model_by_alias=False)
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
    return SensorReading.model_validate({c: row[c] for c in RAW_COLUMNS})


@app.get("/api/figures")
def figures():
    if not config.FIG_DIR.exists():
        return []
    return [{"name": p.stem, "url": f"/figures/{p.name}"} for p in sorted(config.FIG_DIR.glob("*.png"))]
