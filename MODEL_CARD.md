# Model Card: AI4I Failure Classifier & RUL Regressor

| | |
|---|---|
| **Models** | `pm-failure-classifier` (LightGBM, 5-class) and `pm-rul-regressor` (LightGBM regression) |
| **Registry** | MLflow Model Registry, alias `champion`. The version is reported by `/api/model-info` and the `X-Model-Version` header. |
| **Training code** | [`notebooks/predictive_maintenance.ipynb`](notebooks/predictive_maintenance.ipynb) and [`src/features.py`](src/features.py) |
| **Serving** | FastAPI ([`backend/`](backend/)), Docker |

## Intended use
- **Use it for:** decision support for maintenance teams. It flags machines likely to fail now (an *alarm*), says which failure mode is involved, and estimates the remaining tool life.
- **Users:** maintenance engineers and plant operators, through the dashboard or the REST API.
- **Do not use it** to shut machines down automatically without human confirmation. Do not use it on machines whose sensors or operating ranges differ from the training data (check `/api/drift` first).

## Data
- **Source:** [AI4I 2020 Predictive Maintenance Dataset](https://archive.ics.uci.edu/dataset/601) (UCI). It is **synthetic** and reflects real industrial machines.
- **Size:** 10,000 rows. After cleaning, 9,991 rows with 330 failures (3.3%).
- **Inputs:** product quality type (L/M/H), air temperature [K], process temperature [K], rotational speed [rpm], torque [Nm], tool wear [min].
- **Cleaning:**
  - dropped 9 rows labelled as failures that had no failure mode
  - excluded random failures (RNF, 0.1%, unrelated to the sensors) from the target
  - gave rows with several failure flags one label, with priority PWF > HDF > OSF > TWF
- **Split:** stratified 80/20 (7,992 train / 1,999 test, seed 42). The test set was used **once**.

## Decision rule
1. `P(failure) = 1 − P(No Failure)`. An **alarm** fires when it is ≥ **0.66**. This threshold was chosen on 5-fold out-of-fold training predictions as the highest-recall threshold with FDR ≤ 2%.
2. When the alarm fires, the failure type is the most probable failure class.
3. **Tool replacement advisory** when tool wear is ≥ 200 min. This is not an alarm (see the limitations).

## Performance (held-out test set, 1,999 machines, 66 failures)
| Metric | Value |
|---|---|
| False Discovery Rate | **0.000** (0 false alarms) |
| Precision / Recall / F1 (binary alarm) | 1.000 / 0.864 / 0.927 |
| Recall on HDF, PWF and OSF failures | 1.000 (57 of 57) |
| Recall on TWF | 0.000 (0 of 9; by design) |
| MCC / PR-AUC | 0.927 / 0.940 |
| Macro-F1 (5 classes) | 0.800 |
| RUL MAE / RMSE / R² | 0.17 min / 1.20 min / 0.9996 |

API latency and throughput are measured separately in [`benchmarks/`](benchmarks/).

## Limitations and risks
- **Tool-wear failures (TWF) are not alarmed.** They occur at a random point in a 200–240 min wear window, and only about 5% of tools in that window fail. Alarming on them would multiply false stoppages. They are covered by the advisory and the RUL estimate.
- **The RUL target is calculated, not observed.** The dataset has no run-to-failure time series, so RUL is computed from the documented failure physics. A naive baseline (200 − wear) already reaches R² 0.997. Retrain on real run-to-failure logs before relying on it.
- **Synthetic data.** The failure mechanisms are deterministic rules, which is why the deterministic modes can be separated perfectly. Real sensors add noise, gradual drift and unseen failure modes, so expect lower performance in production.
- **Distribution shift.** Inputs outside the training ranges are rejected by the schema. Shifts within those ranges are monitored with the Population Stability Index (`/api/drift`; PSI ≥ 0.25 means significant).
- **Cost assumptions.** The tuning objective used assumed costs: 10 k€ per false alarm and 30 k€ per missed failure. Retune with the plant's real costs.

## Ethical considerations
The model has no personal data and makes no decisions about people. The main risk is over-trusting the model: a missed failure (most likely a tool-wear failure) can still happen, so keep scheduled inspections in place.
