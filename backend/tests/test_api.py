import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402
from app.main import app  # noqa: E402
from app.security import limiter  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "data" / "predictive_maintenance.csv"
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


def upload(client, name, content, url="/api/predict/file", ctype="text/plain"):
    data = content.encode() if isinstance(content, str) else content
    return client.post(url, files={"file": (name, data, ctype)})


def assert_400(r, field=None):
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"] == "validation_error" and body["message"] and body["request_id"]
    if field:
        assert any(field in d["field"] for d in body["details"]), body
    return body


# ------------------------------------------------------------------ meta
def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["model_loaded"] is True and body["model_version"]


def test_model_info(client):
    info = client.get("/api/model-info").json()
    assert info["classes"][0] == "No Failure"
    assert 0 < info["threshold"] < 1
    assert "Torque" in info["sensor_ranges"]


def test_observability_headers(client):
    r = client.get("/api/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
    assert float(r.headers["X-Process-Time-ms"]) >= 0
    assert r.headers["X-Model-Version"]


def test_prometheus_metrics(client):
    client.post("/api/predict", json=HEALTHY)
    text = client.get("/metrics").text
    assert "pm_http_requests_total" in text and "pm_predictions_total" in text
    assert 'route="/api/predict"' in text


# ----------------------------------------------------------- predictions
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


def test_integers_accepted_for_float_fields(client):
    assert client.post("/api/predict", json={**HEALTHY, "Torque": 42}).status_code == 200


def test_batch(client):
    r = client.post("/api/predict/batch", json=[HEALTHY, *CASES.values()]).json()
    assert r["n_rows"] == 4 and r["n_alarms"] == 3
    assert r["by_failure"] == {"HDF": 1, "PWF": 1, "OSF": 1}


# ------------------------------------------------ schema validation -> 400
@pytest.mark.parametrize("field,value", [
    ("Torque", "forty"),          # text in a numeric field
    ("Torque", "42.8"),           # numeric string is still text: strict mode
    ("Tool wear", None),
    ("Rotational speed", True),   # booleans are not numbers
    ("Torque", [42.8]),
    ("Torque", -5),               # out of range
    ("Air temperature", 1000),
    ("Type", "X"),                # invalid category
    ("Type", 1),
])
def test_invalid_field_values_return_400(client, field, value):
    assert_400(client.post("/api/predict", json={**HEALTHY, field: value}), field)


def test_missing_field_returns_400(client):
    body = {k: v for k, v in HEALTHY.items() if k != "Torque"}
    assert_400(client.post("/api/predict", json=body), "Torque")


def test_unknown_field_returns_400(client):
    assert_400(client.post("/api/predict", json={**HEALTHY, "Pressure": 3.2}), "Pressure")


def test_nan_and_infinity_return_400(client):
    for token in ("NaN", "Infinity"):
        raw = json.dumps(HEALTHY).replace("42.8", token)
        r = client.post("/api/predict", content=raw, headers={"Content-Type": "application/json"})
        assert_400(r, "Torque")


def test_malformed_json_body_returns_400(client):
    r = client.post("/api/predict", content="{not json", headers={"Content-Type": "application/json"})
    assert_400(r)


def test_wrong_body_type_returns_400(client):
    assert_400(client.post("/api/predict", json=[HEALTHY]))
    assert_400(client.post("/api/predict/batch", json=HEALTHY))


def test_batch_errors_report_row(client):
    body = assert_400(client.post("/api/predict/batch", json=[HEALTHY, {**HEALTHY, "Torque": "abc"}]))
    assert body["details"][0]["field"].startswith("1.")


def test_empty_batch_returns_400(client):
    assert_400(client.post("/api/predict/batch", json=[]))


def test_invalid_query_param_returns_400(client):
    assert_400(client.get("/api/samples", params={"kind": "nope"}), "kind")


# ------------------------------------------------------------ file uploads
def test_csv_upload_full_dataset(client):
    with open(DATA, "rb") as f:
        r = client.post("/api/predict/file", files={"file": ("data.csv", f, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["n_rows"] == 10_000 and body["n_alarms"] > 200


def test_legacy_csv_endpoint(client):
    csv = "Type,Air temperature,Process temperature,Rotational speed,Torque,Tool wear\nL,302.5,310.4,1300,55,80\n"
    assert upload(client, "x.csv", csv, url="/api/predict/csv").json()["by_failure"] == {"HDF": 1}
    assert_400(upload(client, "x.json", "[]", url="/api/predict/csv"), "file")


def test_csv_headers_with_units_and_extra_columns(client):
    csv = ("UDI,Type,Air temperature [K],Process temperature [K],Rotational speed [rpm],Torque [Nm],Tool wear [min],Note\n"
           "1,M,298.1,308.6,1551,42.8,10,ok\n")
    assert upload(client, "x.csv", csv).json()["n_rows"] == 1


@pytest.mark.parametrize("payload", [
    [HEALTHY, CASES["PWF"]],
    {"readings": [HEALTHY, CASES["PWF"]]},
])
def test_json_upload(client, payload):
    r = upload(client, "readings.json", json.dumps(payload), ctype="application/json")
    assert r.status_code == 200 and r.json()["by_failure"] == {"PWF": 1}


def test_json_single_object_upload(client):
    assert upload(client, "one.json", json.dumps(CASES["OSF"])).json()["by_failure"] == {"OSF": 1}


def test_csv_missing_columns(client):
    assert_400(upload(client, "x.csv", "Type,Torque\nL,40\n"), "Air temperature")


def test_csv_text_in_numeric_column_reports_row(client):
    csv = ("Type,Air temperature,Process temperature,Rotational speed,Torque,Tool wear\n"
           "M,298.1,308.6,1551,42.8,10\nM,298.1,308.6,fast,42.8,10\nQ,298.1,308.6,1551,42.8,10\n")
    body = assert_400(upload(client, "x.csv", csv))
    rows = {(d["row"], d["field"]) for d in body["details"]}
    assert (2, "Rotational speed") in rows and (3, "Type") in rows


def test_csv_out_of_range_reports_row(client):
    csv = "Type,Air temperature,Process temperature,Rotational speed,Torque,Tool wear\nM,298.1,308.6,1551,-3,10\n"
    body = assert_400(upload(client, "x.csv", csv), "Torque")
    assert body["details"][0]["row"] == 1


@pytest.mark.parametrize("name,content", [
    ("photo.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"),   # wrong extension
    ("data.csv", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"),    # binary disguised as CSV
    ("data.csv", b""),                                       # empty
    ("data.csv", "Type,Torque\n".encode("utf-16")),          # not UTF-8
    ("data.json", b"{\"readings\": [}"),                     # malformed JSON
    ("data.json", b"\"hello\""),                             # wrong JSON shape
    ("data.json", b"[]"),                                    # no readings
    ("data", b"Type\nL\n"),                                  # no extension
])
def test_invalid_files_return_400(client, name, content):
    assert_400(upload(client, name, content))


def test_json_upload_invalid_types_report_row(client):
    body = assert_400(upload(client, "x.json", json.dumps([HEALTHY, {**HEALTHY, "Torque": "high"}])))
    assert body["details"][0]["row"] == 2


def test_oversized_upload_returns_413(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 100)
    r = upload(client, "big.csv", "x" * 200)
    assert r.status_code == 413 and r.json()["error"] == "payload_too_large"


def test_missing_file_field_returns_400(client):
    assert_400(client.post("/api/predict/file"))


# ------------------------------------------------------------------ drift
def test_drift_detects_shift(client):
    client.delete("/api/drift")
    assert client.get("/api/drift").json()["status"] == "insufficient_data"
    shifted = [{**HEALTHY, "Torque": 70.0 + i % 5, "Tool wear": 230 + i % 10} for i in range(150)]
    client.post("/api/predict/batch", json=shifted)
    report = client.get("/api/drift").json()
    assert report["status"] == "significant" and report["n_samples"] == 150
    assert {s["sensor"]: s["status"] for s in report["sensors"]}["Torque"] == "significant"


def test_drift_on_training_data_is_stable(client):
    with open(DATA, "rb") as f:
        r = client.post("/api/drift/file", files={"file": ("data.csv", f, "text/csv")})
    assert r.json()["status"] == "stable"


# --------------------------------------------------------------- security
def test_api_key_required_when_configured(client, monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "s3cret")
    r = client.post("/api/predict", json=HEALTHY)
    assert r.status_code == 401 and r.json()["error"] == "unauthorized"
    assert client.post("/api/predict", json=HEALTHY, headers={"X-API-Key": "s3cret"}).status_code == 200
    assert client.get("/api/health").status_code == 200  # health stays open


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(limiter, "per_minute", 3)
    limiter.hits.clear()
    codes = [client.post("/api/predict?explain=false", json=HEALTHY).status_code for _ in range(5)]
    assert codes[:3] == [200] * 3 and codes[3:] == [429, 429]
    limiter.hits.clear()


# ------------------------------------------------------------------- demo
def test_samples_and_figures(client):
    s = client.get("/api/samples", params={"kind": "HDF"}).json()
    assert s["type"] in {"L", "M", "H"}
    figs = client.get("/api/figures").json()
    assert len(figs) > 0
    assert client.get(figs[0]["url"]).status_code == 200
