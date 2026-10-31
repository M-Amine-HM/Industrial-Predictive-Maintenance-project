"""Shared feature engineering for the AI4I 2020 predictive-maintenance project.

Used by both the training notebook and the (future) FastAPI service so that
features are computed identically at train and inference time.
"""
import numpy as np
import pandas as pd

RAW_COLUMNS = [
    "Type", "Air temperature", "Process temperature",
    "Rotational speed", "Torque", "Tool wear",
]

# Physical limits from the AI4I data-generation process (Matzka, 2020)
OSF_LIMIT = {"L": 11_000, "M": 12_000, "H": 13_000}  # tool wear [min] x torque [Nm]
HDF_TEMP_DIFF = 8.6    # K
HDF_RPM = 1380         # rpm
PWF_LOW, PWF_HIGH = 3_500, 9_000  # W
TWF_WEAR = 200         # min (tool replaced / fails between 200 and 240 min)

FAILURE_CLASSES = ["No Failure", "TWF", "HDF", "PWF", "OSF"]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return the model feature matrix built from the raw sensor columns."""
    X = pd.DataFrame(index=df.index)
    air, proc = df["Air temperature"], df["Process temperature"]
    rpm, torque, wear = df["Rotational speed"], df["Torque"], df["Tool wear"]

    X["air_temp"] = air
    X["process_temp"] = proc
    X["rpm"] = rpm
    X["torque"] = torque
    X["tool_wear"] = wear

    # Physics-informed features
    X["temp_diff"] = proc - air
    X["power_W"] = torque * rpm * 2 * np.pi / 60
    X["wear_x_torque"] = wear * torque
    osf_limit = df["Type"].map(OSF_LIMIT).astype(float)
    X["osf_margin"] = osf_limit - X["wear_x_torque"]
    X["power_margin_low"] = X["power_W"] - PWF_LOW
    X["power_margin_high"] = PWF_HIGH - X["power_W"]
    X["hdf_temp_margin"] = X["temp_diff"] - HDF_TEMP_DIFF
    X["hdf_rpm_margin"] = rpm - HDF_RPM
    X["tool_wear_margin"] = TWF_WEAR - wear

    # Product quality variant (ordinal: L < M < H)
    X["type_ord"] = df["Type"].map({"L": 0, "M": 1, "H": 2})
    return X
