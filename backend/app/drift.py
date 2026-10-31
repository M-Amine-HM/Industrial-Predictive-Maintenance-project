"""Data-drift monitoring: Population Stability Index of live inputs vs the training data."""
import threading
from collections import deque

import numpy as np
import pandas as pd

SENSORS = ["Air temperature", "Process temperature", "Rotational speed", "Torque", "Tool wear"]
PSI_MODERATE, PSI_SIGNIFICANT = 0.1, 0.25


def psi(ref_frac: np.ndarray, cur_frac: np.ndarray, eps: float = 1e-4) -> float:
    ref, cur = np.clip(ref_frac, eps, None), np.clip(cur_frac, eps, None)
    return float(np.sum((cur - ref) * np.log(cur / ref)))


def level(value: float) -> str:
    return "significant" if value >= PSI_SIGNIFICANT else "moderate" if value >= PSI_MODERATE else "stable"


class DriftMonitor:
    def __init__(self, reference: pd.DataFrame, window: int = 5000, min_samples: int = 100, bins: int = 10):
        self.min_samples = min_samples
        self.buffer: deque = deque(maxlen=window)
        self.lock = threading.Lock()
        self.ref = {}
        for s in SENSORS:
            edges = np.unique(np.quantile(reference[s], np.linspace(0, 1, bins + 1)))
            edges[0], edges[-1] = -np.inf, np.inf
            counts = np.histogram(reference[s], edges)[0]
            self.ref[s] = {"edges": edges, "frac": counts / counts.sum(), "mean": float(reference[s].mean())}

    def observe(self, raw: pd.DataFrame) -> None:
        with self.lock:
            self.buffer.extend(raw[SENSORS].to_numpy(dtype=float))

    def reset(self) -> None:
        with self.lock:
            self.buffer.clear()

    def report(self, current: pd.DataFrame | None = None) -> dict:
        if current is None:
            with self.lock:
                current = pd.DataFrame(list(self.buffer), columns=SENSORS)
        n = len(current)
        if n < self.min_samples:
            return {"status": "insufficient_data", "n_samples": n, "min_samples": self.min_samples, "sensors": []}
        sensors = []
        for s in SENSORS:
            r = self.ref[s]
            counts = np.histogram(current[s], r["edges"])[0]
            value = psi(r["frac"], counts / counts.sum())
            sensors.append({"sensor": s, "psi": round(value, 4), "status": level(value),
                            "reference_mean": round(r["mean"], 3), "current_mean": round(float(current[s].mean()), 3)})
        worst = max(x["psi"] for x in sensors)
        return {"status": level(worst), "n_samples": n, "min_samples": self.min_samples, "sensors": sensors}
