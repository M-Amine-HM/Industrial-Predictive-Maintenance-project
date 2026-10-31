# Industrial Predictive Maintenance (AI4I 2020)

[![CI](https://github.com/M-Amine-HM/Industrial-Predictive-Maintenance-project/actions/workflows/ci.yml/badge.svg)](https://github.com/M-Amine-HM/Industrial-Predictive-Maintenance-project/actions/workflows/ci.yml)

This project predicts the failure type of a machine from its sensor readings. The model is tuned for a **low False Discovery Rate**: an alarm should almost always mean a real failure, because a false alarm halts production. It also estimates **remaining useful life (RUL)**, the minutes of operation left before failure. The model is served as a **containerised FastAPI service** with strict input validation, monitoring and a React dashboard.

| Model (held-out test set, 1,999 machines) | Value |
|---|---|
| False Discovery Rate | **0.0%** (0 false alarms) |
| Alarm precision | 100% |
| Recall on heat (HDF), power (PWF) and overstrain (OSF) failures | 100% |
| Recall on all failures | 86.4% (all misses are random tool-wear failures, see the [model card](MODEL_CARD.md)) |
| MCC / PR-AUC | 0.927 / 0.940 |
| RUL MAE | 0.17 min |

| Service (Docker, measured inside the compose network) | Value |
|---|---|
| `/api/predict` latency, 1 client | p50 **11–13 ms**, p95 **14–20 ms** |
| `/api/predict` with SHAP explanation | p50 ≈ 20 ms |
| Batch of 1,000 rows | ≈ 160 ms (≈ 6k rows/s) |
| Throughput, 16 concurrent clients, 4 workers | **176–210 req/s**, 0 failed requests |

The ranges cover repeated runs on a 12-CPU laptop (Docker Desktop, WSL2). See [benchmarks](#benchmarks).

## Architecture

```
            ┌──────────── docker compose ─────────────┐
 browser ──▶│ web: nginx (React build) :8080          │
            │   /api, /docs, /metrics ──▶ api :8000   │──▶ models/ (registered in MLflow)
            │ api: FastAPI + uvicorn (PM_WORKERS)     │
            └─────────────────────────────────────────┘
```

```
data/                  AI4I 2020 dataset
notebooks/             predictive_maintenance.ipynb: EDA → features → models → tuning → evaluation → MLflow
src/features.py        feature engineering shared by the notebook and the API (no train/serve skew)
models/                classifier.joblib, rul_model.joblib, config.json (threshold, registry version), metrics.json
backend/app/           FastAPI: schemas, validation errors, uploads, monitoring, drift, security
backend/tests/         53 pytest tests
frontend/              React + Vite + TypeScript dashboard
postman/               Postman collection (28 requests, 78 assertions) + upload fixtures
benchmarks/            latency.py, load_test.sh (ApacheBench), locustfile.py, results/
Dockerfile             all-in-one image (API + dashboard) for single-container hosting
docker-compose.yml     api + web (nginx)
MODEL_CARD.md          intended use, data, metrics, limitations
```

## Quick start (Docker)

```bash
docker compose up -d --build --wait
```

| URL | |
|---|---|
| http://localhost:8080 | Dashboard |
| http://localhost:8080/docs | Interactive API docs (Swagger) |
| http://localhost:8000/metrics | Prometheus metrics |

Images:
- **`api`:** `python:3.12-slim`, runs as a non-root user, has a `HEALTHCHECK`, and runs `PM_WORKERS` uvicorn workers (4 in compose).
- **`web`:** a multi-stage Node build served by unprivileged nginx. It proxies the API on the same origin, so the browser needs no CORS.
- **Test stage:** `docker build --target test -f backend/Dockerfile .` runs the full test suite inside the image.

## Input validation → 400 Bad Request

Requests are validated by **Pydantic in strict mode**. Every invalid input gets a **400** with the same error format:

```json
{"error": "validation_error",
 "message": "Invalid value for 'Torque': Input should be a valid number",
 "details": [{"field": "Torque", "message": "Input should be a valid number", "row": null}],
 "request_id": "4647472a67c8424a"}
```

| Rejected input | Example |
|---|---|
| Text in a numeric field, including numeric strings | `"Torque": "forty"`, `"Torque": "42.8"` |
| Booleans, nulls, lists in numeric fields | `"Rotational speed": true` |
| Out-of-range values | `"Torque": -5`, `"Air temperature": 1000` |
| Invalid category | `"Type": "X"` |
| Missing or unknown fields | no `Torque`; `"Pressure": 3.1` |
| `NaN` / `Infinity` | `"Torque": NaN` |
| Malformed JSON, wrong body shape, empty batch | `{"Type": `, `[]` |
| Invalid upload | `.png` or other extensions, binary files, empty files, non-UTF-8 text, malformed CSV/JSON, missing columns |
| Bad cells in an upload | Reported **per row and field**: `{"row": 2, "field": "Rotational speed", "message": "not a number: 'fast'"}` |

Oversized uploads return **413**. When enabled, a missing API key returns **401** and the rate limit returns **429**.

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/predict` | One reading → alarm, failure type, probabilities, RUL, physics margins, SHAP drivers (`?explain=false` to skip SHAP) |
| `POST /api/predict/batch` | JSON list of readings → per-row decisions and a summary |
| `POST /api/predict/file` | Upload a **.csv** (AI4I columns) or **.json** (list or `{"readings": [...]}`) |
| `POST /api/predict/csv` | CSV-only upload (kept for compatibility) |
| `GET  /api/drift` · `POST /api/drift/file` · `DELETE /api/drift` | Data drift (PSI) of recent traffic or of an uploaded batch, measured against the training data; reset the window |
| `GET  /api/model-info` | Model version and MLflow lineage, threshold, test metrics, sensor ranges, limits |
| `GET  /api/health` | Liveness check and model version |
| `GET  /metrics` | Prometheus metrics: requests, latency histogram, predictions by decision, validation errors |
| `GET  /api/samples?kind=HDF` | A real reading from the dataset (`healthy`, `TWF`, `HDF`, `PWF`, `OSF`, `random`) |

Every response carries the `X-Request-ID`, `X-Process-Time-ms` and `X-Model-Version` headers. Each request is logged as one line of structured JSON.

```bash
curl -X POST localhost:8000/api/predict -H "Content-Type: application/json" \
  -d '{"type":"L","air_temperature":302.5,"process_temperature":310.4,"rotational_speed":1300,"torque":55,"tool_wear":80}'
```

### Configuration

| Variable | Default | |
|---|---|---|
| `PM_WORKERS` | 1 (compose: 4) | Number of uvicorn workers. `/metrics` aggregates them through Prometheus multiprocess mode. |
| `PM_API_KEY` | empty (off) | When set, prediction and drift routes require the `X-API-Key` header |
| `PM_RATE_LIMIT_PER_MIN` | 0 (off) | Per-IP limit on prediction and drift routes |
| `PM_MAX_BATCH_ROWS` / `PM_MAX_UPLOAD_MB` | 20000 / 5 | Request size limits |
| `PM_DRIFT_WINDOW` / `PM_DRIFT_MIN_SAMPLES` | 5000 / 100 | Size of the rolling drift window |
| `PM_CORS_ORIGINS`, `PM_LOG_LEVEL`, `PM_MODEL_DIR`, `PM_DATA_PATH`, `PM_FIG_DIR` | | |

## Postman

Import `postman/predictive-maintenance.postman_collection.json` and `postman/local.postman_environment.json`. The collection has:
- the happy paths
- **17 validation cases that expect a 400**
- file uploads using the fixtures in `postman/fixtures/`

From the command line:

```bash
npx newman run postman/predictive-maintenance.postman_collection.json \
  --env-var baseUrl=http://localhost:8080 --working-dir postman/fixtures
```

To regenerate the collection after API changes, run `python postman/build_collection.py`.

## MLflow: experiment tracking and model registry

The notebook logs a parent run with **53 nested runs** to `mlflow.db`:
- 8 baselines
- 3 imbalance strategies
- 40 Optuna trials
- 2 final models, with test metrics, figures, signatures and input examples

Both final models are registered (`pm-failure-classifier`, `pm-rul-regressor`) under the alias `champion`. They are saved with **skops** (safer than pickle), with the LightGBM types explicitly trusted. The registry version is written to `models/config.json`, so the API reports which version it serves.

```bash
mlflow ui --backend-store-uri sqlite:///mlflow.db     # http://localhost:5000
```

## Benchmarks

```bash
docker compose up -d --wait
sh benchmarks/load_test.sh 16 3000                     # ApacheBench throughput, inside the compose network
docker run --rm --network predictive-maintenance_default -v "$PWD/benchmarks:/b" python:3.12-slim \
  sh -c "pip install -q httpx && python /b/latency.py --url http://api:8000 --label docker-network"
locust -f benchmarks/locustfile.py --host http://localhost:8000   # interactive load test
```

Results are saved in [`benchmarks/results/`](benchmarks/results/). Two measurement notes:
- **Measure from inside the compose network.** On Docker Desktop for Windows, the host port relay adds about 40 ms to every POST: an instant 400 response takes 45 ms through the relay versus 2 ms directly.
- **Use ApacheBench for throughput.** A single Python client saturates before the server does.

Profiling also led to a NumPy rewrite of `build_features` (4.8 → 0.75 ms per row, output identical on all 10,000 rows) and to the multi-worker setup (≈ 2.8× the throughput of one worker).

## Development without Docker

```bash
pip install -r requirements.txt                       # notebook + training
jupyter nbconvert --to notebook --execute --inplace notebooks/predictive_maintenance.ipynb

cd backend && pip install -r requirements-dev.txt
uvicorn app.main:app --port 8000                      # API (docs at /docs)
pytest -q                                             # 53 tests

cd frontend && npm install && npm run dev             # http://localhost:5173 (proxies /api to :8000)
```

> LightGBM is pinned to 4.6.0 because 4.7.0 crashes inside Jupyter kernels on Windows.

## CI

GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs on every push:
1. the backend tests
2. the frontend type-check and build
3. the Docker images build, the stack starts, the **Newman contract tests** run through nginx, and **both benchmarks** run, with results uploaded as artifacts

## Deployment (single container)

The root [`Dockerfile`](Dockerfile) builds the React app and serves it from FastAPI, so one container runs everything.
- **Render:** New → Blueprint → select this repo. [`render.yaml`](render.yaml) configures the free plan.
- **Hugging Face Spaces (Docker):** set `PORT=7860`.
- **Fly.io / any container host:** `docker build -t pm . && docker run -p 8000:8000 pm`.

## The dashboard

- **Diagnose:** live scoring as you move the sensor sliders, or load a real machine. Shows the alarm decision against the threshold, class probabilities, distance to each physical failure limit, and SHAP drivers.
- **Fleet scoring:** upload a **CSV or JSON** file and get the alarm, advisory and healthy counts, the mix of failure modes, **data drift per sensor**, and a sortable table. Rejected files show the exact row, field and problem. CSV and JSON templates are available to download.
- **Model report:** test metrics and the full figure gallery from the notebook.

## Decision logic

1. `P(failure) = 1 − P(No Failure)`. An **alarm** fires when it is ≥ τ = 0.66. τ was chosen on cross-validation as the threshold with the highest recall subject to FDR ≤ 2%.
2. When the alarm fires, the failure type is the most probable failure class.
3. Tool-wear failures are random once wear is between 200 and 240 min, so the system does not alarm on them. Instead it shows a **tool-replacement advisory** when wear is ≥ 200 min, alongside the RUL estimate.

See [MODEL_CARD.md](MODEL_CARD.md) for intended use and limitations.
