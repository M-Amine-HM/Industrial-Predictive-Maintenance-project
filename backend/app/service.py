import json

import joblib
import numpy as np
import pandas as pd
import shap

from . import config  # noqa: F401  (puts src/ on sys.path)
from features import (HDF_RPM, HDF_TEMP_DIFF, OSF_LIMIT, PWF_HIGH, PWF_LOW,
                      TWF_WEAR, build_features)


class ModelService:
    """Loads the trained artifacts once and turns raw sensor readings into decisions."""

    def __init__(self, model_dir=config.MODEL_DIR):
        self.clf = joblib.load(model_dir / "classifier.joblib")
        self.rul = joblib.load(model_dir / "rul_model.joblib")
        self.cfg = json.loads((model_dir / "config.json").read_text())
        self.metrics = json.loads((model_dir / "metrics.json").read_text())
        self.classes = self.cfg["classes"]
        self.threshold = float(self.cfg["threshold"])
        self.explainer = shap.TreeExplainer(self.clf)
        self.version = str(self.cfg.get("model_version", "1.0.0"))
        self.lineage = self.cfg.get("mlflow", {})

    # ------------------------------------------------------------------ core
    def predict_frame(self, raw: pd.DataFrame) -> pd.DataFrame:
        X = build_features(raw)
        proba = self.clf.predict_proba(X[self.cfg["features"]])
        p_fail = 1 - proba[:, 0]
        alarm = p_fail >= self.threshold
        likely = np.array(self.classes)[proba[:, 1:].argmax(1) + 1]
        advisory = raw["Tool wear"].to_numpy() >= self.cfg["twf_advisory_wear_min"]
        rul = np.clip(self.rul.predict(X[self.cfg["rul_features"]]), 0, None)
        return pd.DataFrame({
            "alarm": alarm,
            "status": np.where(alarm, "alarm", np.where(advisory, "advisory", "ok")),
            "failure_probability": p_fail.round(4),
            "predicted_failure": np.where(alarm, likely, "No Failure"),
            "most_likely_failure": likely,
            "rul_minutes": rul.round(1),
            "tool_replacement_advised": advisory,
        }).join(pd.DataFrame(proba.round(4), columns=self.classes))

    def predict_one(self, raw: dict, explain: bool = True) -> dict:
        frame = pd.DataFrame([raw])
        out = self.predict_frame(frame).iloc[0]
        result = {k: out[k].item() if hasattr(out[k], "item") else out[k]
                  for k in ["alarm", "status", "failure_probability", "predicted_failure",
                            "most_likely_failure", "rul_minutes", "tool_replacement_advised"]}
        result["class_probabilities"] = {c: float(out[c]) for c in self.classes}
        result["threshold"] = self.threshold
        result["mechanisms"] = self.mechanisms(raw)
        result["drivers"] = self.drivers(frame, result["most_likely_failure"]) if explain else []
        return result

    # ------------------------------------------------------------ explanations
    def drivers(self, frame: pd.DataFrame, failure_class: str, top: int = 6) -> list[dict]:
        X = build_features(frame)[self.cfg["features"]]
        sv = self.explainer.shap_values(X)
        sv = np.stack(sv, axis=-1) if isinstance(sv, list) else sv  # (n, features, classes)
        contrib = sv[0, :, self.classes.index(failure_class)]
        order = np.argsort(-np.abs(contrib))[:top]
        return [{"feature": self.cfg["features"][i], "value": float(X.iloc[0, i]),
                 "contribution": float(contrib[i])} for i in order]

    @staticmethod
    def mechanisms(raw: dict) -> list[dict]:
        """Distance of the reading to each documented physical failure limit."""
        dT = raw["Process temperature"] - raw["Air temperature"]
        rpm, torque, wear = raw["Rotational speed"], raw["Torque"], raw["Tool wear"]
        power = torque * rpm * 2 * np.pi / 60
        strain, osf_lim = wear * torque, OSF_LIMIT[raw["Type"]]
        # HDF needs both conditions; utilisation = how close the *less* violated one is
        hdf_util = min(HDF_TEMP_DIFF / max(dT, 1e-6), HDF_RPM / rpm)
        pwr_util = max(PWF_LOW / max(power, 1e-6), power / PWF_HIGH)
        return [
            {"mode": "HDF", "label": "Heat dissipation", "value": round(dT, 2), "unit": "K ΔT",
             "limit": f"ΔT < {HDF_TEMP_DIFF} K and rpm < {HDF_RPM}",
             "utilisation": round(hdf_util, 3), "breached": bool(dT < HDF_TEMP_DIFF and rpm < HDF_RPM)},
            {"mode": "PWF", "label": "Power", "value": round(power, 0), "unit": "W",
             "limit": f"{PWF_LOW:,} – {PWF_HIGH:,} W",
             "utilisation": round(pwr_util, 3), "breached": bool(power < PWF_LOW or power > PWF_HIGH)},
            {"mode": "OSF", "label": "Overstrain", "value": round(strain, 0), "unit": "min·Nm",
             "limit": f"< {osf_lim:,} min·Nm (type {raw['Type']})",
             "utilisation": round(strain / osf_lim, 3), "breached": bool(strain > osf_lim)},
            {"mode": "TWF", "label": "Tool wear", "value": round(wear, 0), "unit": "min",
             "limit": f"replace from {TWF_WEAR} min",
             "utilisation": round(wear / TWF_WEAR, 3), "breached": bool(wear >= TWF_WEAR)},
        ]

