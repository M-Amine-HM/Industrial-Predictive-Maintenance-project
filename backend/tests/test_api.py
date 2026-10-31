import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app  # noqa: E402

HEALTHY = {"Type": "M", "Air temperature": 298.1, "Process temperature": 308.6,
           "Rotational speed": 1551, "Torque": 42.8, "Tool wear": 10}
CASES = {
    "HDF": {"Type": "L", "Air temperature": 302.5, "Process temperature": 310.4, "Rotational speed": 1300, "Torque": 55.0, "Tool wear": 80},
    "PWF": {"Type": "L", "Air temperature": 299.0, "Process temperature": 309.5, "Rotational speed": 2800, "Torque": 8.0, "Tool wear": 50},
    "OSF": {"Type": "L", "Air temperature": 299.0, "Process temperature": 309.5, "Rotational speed": 1400, "Torque": 58.0, "Tool wear": 210},
}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok", "model_loaded": True}


def test_model_info(client):
    info = client.get("/api/model-info").json()
    assert info["classes"][0] == "No Failure"
    assert 0 < info["threshold"] < 1
    assert "Torque" in info["sensor_ranges"]


def test_healthy_reading_raises_no_alarm(client):
    r = client.post("/api/predict", json=HEALTHY).json()
    assert r["alarm"] is False and r["status"] == "ok"
    assert r["predicted_failure"] == "No Failure"
    assert r["rul_minutes"] > 100
    assert len(r["mechanisms"]) == 4 and len(r["drivers"]) > 0


@pytest.mark.parametrize("mode", list(CASES))
def test_failure_modes_detected(client, mode):
    r = client.post("/api/predict", json=CASES[mode]).json()
    assert r["alarm"] is True
    assert r["predicted_failure"] == mode
    assert next(m for m in r["mechanisms"] if m["mode"] == mode)["breached"]


def test_snake_case_input(client):
    body = {"type": "M", "air_temperature": 298.1, "process_temperature": 308.6,
            "rotational_speed": 1551, "torque": 42.8, "tool_wear": 10}
    assert client.post("/api/predict", json=body).status_code == 200


def test_validation_rejects_bad_input(client):
    assert client.post("/api/predict", json={**HEALTHY, "Type": "X"}).status_code == 422
    assert client.post("/api/predict", json={**HEALTHY, "Torque": -5}).status_code == 422


def test_batch(client):
    r = client.post("/api/predict/batch", json=[HEALTHY, *CASES.values()]).json()
    assert r["n_rows"] == 4 and r["n_alarms"] == 3
    assert r["by_failure"] == {"HDF": 1, "PWF": 1, "OSF": 1}


def test_csv_upload_full_dataset(client):
    path = Path(__file__).resolve().parents[2] / "data" / "predictive_maintenance.csv"
    with open(path, "rb") as f:
        r = client.post("/api/predict/csv", files={"file": ("data.csv", f, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["n_rows"] == 10_000
    assert body["n_alarms"] > 200


def test_csv_missing_columns(client):
    r = client.post("/api/predict/csv", files={"file": ("x.csv", b"Type,Torque\nL,40\n", "text/csv")})
    assert r.status_code == 422


def test_samples_and_figures(client):
    s = client.get("/api/samples", params={"kind": "HDF"}).json()
    assert s["type"] in {"L", "M", "H"}
    figs = client.get("/api/figures").json()
    assert len(figs) > 0
    assert client.get(figs[0]["url"]).status_code == 200
