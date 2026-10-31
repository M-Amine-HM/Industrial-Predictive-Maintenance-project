"""Interactive load test.

    locust -f benchmarks/locustfile.py --host http://localhost:8000
    # headless: locust -f benchmarks/locustfile.py --host http://localhost:8000 -u 50 -r 10 -t 1m --headless
"""
import random

from locust import HttpUser, between, task

TYPES = ["L", "M", "H"]


def reading():
    air = random.uniform(295.5, 304.5)
    return {"Type": random.choice(TYPES), "Air temperature": round(air, 1),
            "Process temperature": round(air + random.uniform(8, 12), 1),
            "Rotational speed": random.randint(1200, 2800), "Torque": round(random.uniform(10, 70), 1),
            "Tool wear": random.randint(0, 250)}


class Operator(HttpUser):
    wait_time = between(0.05, 0.3)

    @task(10)
    def predict_fast(self):
        self.client.post("/api/predict?explain=false", json=reading(), name="/api/predict (no SHAP)")

    @task(3)
    def predict_explained(self):
        self.client.post("/api/predict", json=reading(), name="/api/predict (SHAP)")

    @task(1)
    def batch(self):
        self.client.post("/api/predict/batch", json=[reading() for _ in range(200)], name="/api/predict/batch (200)")

    @task(1)
    def invalid(self):
        with self.client.post("/api/predict", json={**reading(), "Torque": "high"},
                              name="/api/predict (invalid -> 400)", catch_response=True) as r:
            if r.status_code == 400:
                r.success()
