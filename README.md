# Industrial Predictive Maintenance (AI4I 2020)

This project predicts the failure type of a machine from its sensor readings. The model is tuned for a **low False Discovery Rate**: an alarm should almost always mean a real failure, because a false alarm halts production. It also estimates **remaining useful life (RUL)**, the minutes of operation left before failure.

| Held-out test set (1,999 machines) | Value |
|---|---|
| False Discovery Rate | **0.0%** (0 false alarms) |
| Alarm precision | 100% |
| Recall on heat (HDF), power (PWF) and overstrain (OSF) failures | 100% |
| Recall on all failures | 86.4% (all misses are random tool-wear failures, see notebook §4) |
| MCC / PR-AUC | 0.927 / 0.940 |
| RUL MAE | 0.17 min |

## Project layout

```
data/                 AI4I 2020 dataset
notebooks/            predictive_maintenance.ipynb  (full executed analysis)
src/features.py       feature engineering shared by the notebook and the API
models/               classifier.joblib, rul_model.joblib, config.json, metrics.json
reports/figures/      all notebook figures (served to the UI)
backend/              FastAPI service
frontend/             React + Vite dashboard
```

## 1. Notebook

```bash
pip install -r requirements.txt
jupyter nbconvert --to notebook --execute --inplace notebooks/predictive_maintenance.ipynb
```

Running the notebook regenerates `models/` and `reports/figures/`.

> LightGBM is pinned to 4.6.0 because 4.7.0 crashes inside Jupyter kernels on Windows.

## 2. Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8000        # interactive docs at http://localhost:8000/docs
pytest -q                               # 12 API tests
```

| Endpoint | Purpose |
|---|---|
| `GET  /api/health` | Liveness check |
| `GET  /api/model-info` | Classes, alarm threshold, test metrics, sensor ranges |
| `POST /api/predict` | One reading → alarm, failure type, probabilities, RUL, physics margins, SHAP drivers |
| `POST /api/predict/batch` | JSON list of readings → per-row decisions and a summary |
| `POST /api/predict/csv` | CSV upload (AI4I columns) → per-row decisions and a summary |
| `GET  /api/samples?kind=HDF` | A real reading from the dataset (`healthy`, `TWF`, `HDF`, `PWF`, `OSF`, `random`) |
| `GET  /api/figures` | List of notebook figures, served under `/figures/*` |

Example request:

```bash
curl -X POST localhost:8000/api/predict -H "Content-Type: application/json" \
  -d '{"type":"L","air_temperature":302.5,"process_temperature":310.4,"rotational_speed":1300,"torque":55,"tool_wear":80}'
```

The API accepts both snake_case fields and the original AI4I column names, such as `"Air temperature"`.

### Configuration (environment variables)

- `PM_MODEL_DIR`, `PM_FIG_DIR`, `PM_DATA_PATH`: override the artifact locations
- `PM_CORS_ORIGINS`: comma-separated list (default: the Vite dev server)
- `PM_MAX_BATCH_ROWS`: default 20000

## 3. Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173  (proxies /api and /figures to :8000)
npm run build      # production bundle in dist/
```

To point a production build at a different API host, build with `VITE_API_URL=https://api.example.com npm run build`.

The dashboard has three views:

- **Diagnose:** live scoring as you move the sensor sliders, or load a real machine. Shows the alarm decision against the threshold, class probabilities, distance to each physical failure limit, and SHAP explanation of the prediction.
- **Fleet scoring:** upload a CSV and get the alarm, advisory and healthy counts, the mix of failure modes, and a sortable, filterable table.
- **Model report:** test metrics and the full figure gallery from the notebook.

## Decision logic

1. `P(failure) = 1 − P(No Failure)`. An **alarm** fires when it is ≥ τ = 0.66. τ was chosen on cross-validation as the threshold with the highest recall subject to FDR ≤ 2%.
2. When the alarm fires, the failure type is the most probable failure class.
3. Tool-wear failures are random once wear is between 200 and 240 min, so the system does not alarm on them. Instead it shows a **tool-replacement advisory** when wear is ≥ 200 min, alongside the RUL estimate.
