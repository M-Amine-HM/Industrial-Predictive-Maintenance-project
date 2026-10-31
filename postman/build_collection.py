"""Generate the Postman collection (v2.1). Run: python postman/build_collection.py

Newman (from the repo root):
    npx newman run postman/predictive-maintenance.postman_collection.json \
        -e postman/local.postman_environment.json --working-dir postman/fixtures
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
HEALTHY = {"Type": "M", "Air temperature": 298.1, "Process temperature": 308.6,
           "Rotational speed": 1551, "Torque": 42.8, "Tool wear": 10}
HDF = {"Type": "L", "Air temperature": 302.5, "Process temperature": 310.4,
       "Rotational speed": 1300, "Torque": 55.0, "Tool wear": 80}

COMMON_400 = """
pm.test("Status is 400 Bad Request", () => pm.response.to.have.status(400));
const body = pm.response.json();
pm.test("Error envelope", () => {
  pm.expect(body.error).to.eql("validation_error");
  pm.expect(body.message).to.be.a("string").and.not.empty;
  pm.expect(body.request_id).to.be.a("string");
});
"""


def field_check(field):
    return f'pm.test("Points at field \'{field}\'", () => pm.expect(body.details.map(d => d.field).join("|")).to.include("{field}"));'


def tests(*lines):
    return [{"listen": "test", "script": {"type": "text/javascript", "exec": "\n".join(lines).strip().split("\n")}}]


def json_req(name, method, path, body=None, test="", query=None, desc=""):
    url = {"raw": "{{baseUrl}}" + path, "host": ["{{baseUrl}}"], "path": [p for p in path.split("?")[0].split("/") if p]}
    if query:
        url["query"] = [{"key": k, "value": v} for k, v in query.items()]
        url["raw"] += "?" + "&".join(f"{k}={v}" for k, v in query.items())
    req = {"method": method, "header": [{"key": "X-API-Key", "value": "{{apiKey}}", "disabled": False}], "url": url,
           "description": desc}
    if body is not None:
        raw = body if isinstance(body, str) else json.dumps(body, indent=2)
        req["header"].append({"key": "Content-Type", "value": "application/json"})
        req["body"] = {"mode": "raw", "raw": raw, "options": {"raw": {"language": "json"}}}
    return {"name": name, "request": req, "event": tests(test)}


def file_req(name, path, filename, test, desc=""):
    return {"name": name, "event": tests(test), "request": {
        "method": "POST", "description": desc,
        "header": [{"key": "X-API-Key", "value": "{{apiKey}}"}],
        "url": {"raw": "{{baseUrl}}" + path, "host": ["{{baseUrl}}"], "path": [p for p in path.split("/") if p]},
        "body": {"mode": "formdata", "formdata": [{"key": "file", "type": "file", "src": filename}]}}}


meta = [
    json_req("Health", "GET", "/api/health", test="""
pm.test("200 OK", () => pm.response.to.have.status(200));
pm.test("Model loaded", () => pm.expect(pm.response.json().model_loaded).to.be.true);
pm.test("Request ID header", () => pm.expect(pm.response.headers.get("X-Request-ID")).to.be.a("string"));
pm.test("Model version header", () => pm.expect(pm.response.headers.get("X-Model-Version")).to.be.a("string"));
"""),
    json_req("Model info", "GET", "/api/model-info", test="""
pm.test("200 OK", () => pm.response.to.have.status(200));
const b = pm.response.json();
pm.test("Threshold in (0,1)", () => pm.expect(b.threshold).to.be.within(0, 1));
pm.test("Five classes", () => pm.expect(b.classes).to.have.length(5));
"""),
    json_req("Prometheus metrics", "GET", "/metrics", test="""
pm.test("200 OK", () => pm.response.to.have.status(200));
pm.test("Exposes request counter", () => pm.expect(pm.response.text()).to.include("pm_http_requests_total"));
"""),
]

predict = [
    json_req("Predict - healthy machine", "POST", "/api/predict", HEALTHY, test="""
pm.test("200 OK", () => pm.response.to.have.status(200));
const b = pm.response.json();
pm.test("No alarm", () => pm.expect(b.alarm).to.be.false);
pm.test("RUL returned", () => pm.expect(b.rul_minutes).to.be.above(0));
pm.test("Responds in < 500 ms", () => pm.expect(pm.response.responseTime).to.be.below(500));
"""),
    json_req("Predict - heat dissipation failure", "POST", "/api/predict", HDF, test="""
pm.test("200 OK", () => pm.response.to.have.status(200));
const b = pm.response.json();
pm.test("Alarm raised", () => pm.expect(b.alarm).to.be.true);
pm.test("Failure type is HDF", () => pm.expect(b.predicted_failure).to.eql("HDF"));
pm.test("SHAP drivers returned", () => pm.expect(b.drivers.length).to.be.above(0));
"""),
    json_req("Predict - snake_case fields, no SHAP", "POST", "/api/predict",
             {"type": "M", "air_temperature": 298.1, "process_temperature": 308.6,
              "rotational_speed": 1551, "torque": 42.8, "tool_wear": 10},
             query={"explain": "false"}, test="""
pm.test("200 OK", () => pm.response.to.have.status(200));
pm.test("No drivers when explain=false", () => pm.expect(pm.response.json().drivers).to.have.length(0));
"""),
    json_req("Predict batch (JSON list)", "POST", "/api/predict/batch", [HEALTHY, HDF], test="""
pm.test("200 OK", () => pm.response.to.have.status(200));
const b = pm.response.json();
pm.test("Two rows, one alarm", () => { pm.expect(b.n_rows).to.eql(2); pm.expect(b.n_alarms).to.eql(1); });
"""),
    file_req("Upload CSV file", "/api/predict/file", "valid_readings.csv", """
pm.test("200 OK", () => pm.response.to.have.status(200));
const b = pm.response.json();
pm.test("Scored 4 rows", () => pm.expect(b.n_rows).to.eql(4));
pm.test("Three alarms (HDF, PWF, OSF)", () => pm.expect(b.n_alarms).to.eql(3));
"""),
    file_req("Upload JSON file", "/api/predict/file", "valid_readings.json", """
pm.test("200 OK", () => pm.response.to.have.status(200));
pm.test("Scored 2 rows", () => pm.expect(pm.response.json().n_rows).to.eql(2));
"""),
]

validation = [
    json_req("400 - text in numeric field", "POST", "/api/predict", {**HEALTHY, "Torque": "forty"},
             test=COMMON_400 + field_check("Torque")),
    json_req("400 - numeric string (strict mode)", "POST", "/api/predict", {**HEALTHY, "Torque": "42.8"},
             test=COMMON_400 + field_check("Torque"),
             desc="Strict schema: a number sent as a string is rejected, not silently coerced."),
    json_req("400 - boolean in numeric field", "POST", "/api/predict", {**HEALTHY, "Rotational speed": True},
             test=COMMON_400 + field_check("Rotational speed")),
    json_req("400 - null value", "POST", "/api/predict", {**HEALTHY, "Tool wear": None},
             test=COMMON_400 + field_check("Tool wear")),
    json_req("400 - out of range", "POST", "/api/predict", {**HEALTHY, "Torque": -5},
             test=COMMON_400 + field_check("Torque")),
    json_req("400 - invalid product type", "POST", "/api/predict", {**HEALTHY, "Type": "X"},
             test=COMMON_400 + field_check("Type")),
    json_req("400 - missing field", "POST", "/api/predict", {k: v for k, v in HEALTHY.items() if k != "Torque"},
             test=COMMON_400 + field_check("Torque")),
    json_req("400 - unknown field", "POST", "/api/predict", {**HEALTHY, "Pressure": 3.1},
             test=COMMON_400 + field_check("Pressure")),
    json_req("400 - NaN value", "POST", "/api/predict", json.dumps(HEALTHY).replace("42.8", "NaN"),
             test=COMMON_400 + field_check("Torque")),
    json_req("400 - malformed JSON body", "POST", "/api/predict", '{"Type": "M", "Torque": ', test=COMMON_400),
    json_req("400 - batch row with bad type", "POST", "/api/predict/batch", [HEALTHY, {**HEALTHY, "Torque": "abc"}],
             test=COMMON_400 + 'pm.test("Reports row index 1", () => pm.expect(body.details[0].field).to.match(/^1\\./));'),
    json_req("400 - empty batch", "POST", "/api/predict/batch", [], test=COMMON_400),
    json_req("400 - invalid query parameter", "GET", "/api/samples", query={"kind": "unknown"},
             test=COMMON_400 + field_check("kind")),
    file_req("400 - image instead of dataset", "/api/predict/file", "not_a_dataset.png",
             COMMON_400 + 'pm.test("Mentions file type", () => pm.expect(body.message).to.include(".png"));'),
    file_req("400 - CSV with text in numeric columns", "/api/predict/file", "invalid_types.csv",
             COMMON_400 + 'pm.test("Row-level details", () => pm.expect(body.details.map(d => d.row)).to.include.members([1, 2]));'),
    file_req("400 - CSV missing columns", "/api/predict/file", "missing_columns.csv",
             COMMON_400 + field_check("Air temperature")),
    file_req("400 - malformed JSON file", "/api/predict/file", "malformed.json", COMMON_400),
]

monitoring = [
    json_req("Drift - rolling window", "GET", "/api/drift", test="""
pm.test("200 OK", () => pm.response.to.have.status(200));
pm.test("Has status", () => pm.expect(["insufficient_data", "stable", "moderate", "significant"]).to.include(pm.response.json().status));
"""),
    json_req("Demo sample (overstrain)", "GET", "/api/samples", query={"kind": "OSF"}, test="""
pm.test("200 OK", () => pm.response.to.have.status(200));
pm.test("Valid reading", () => pm.expect(["L", "M", "H"]).to.include(pm.response.json().type));
"""),
]

collection = {
    "info": {
        "name": "Industrial Predictive Maintenance API",
        "description": "Happy paths, Pydantic schema validation (every invalid input -> 400) and monitoring endpoints.",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "item": [
        {"name": "Meta", "item": meta},
        {"name": "Predictions", "item": predict},
        {"name": "Validation (400 Bad Request)", "item": validation},
        {"name": "Monitoring & demo", "item": monitoring},
    ],
    "variable": [{"key": "baseUrl", "value": "http://localhost:8000"}, {"key": "apiKey", "value": ""}],
}
environment = {
    "name": "Local (docker compose)",
    "values": [{"key": "baseUrl", "value": "http://localhost:8000", "enabled": True},
               {"key": "apiKey", "value": "", "enabled": True}],
}

(HERE / "predictive-maintenance.postman_collection.json").write_text(json.dumps(collection, indent=2))
(HERE / "local.postman_environment.json").write_text(json.dumps(environment, indent=2))
n = sum(len(f["item"]) for f in collection["item"])
print(f"Wrote collection with {n} requests")
