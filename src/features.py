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
    """Return the model feature matrix built from the raw sensor columns.

    Computed on NumPy arrays and assembled once: a single-row call stays well under
    a millisecond, which matters for API latency.
    """
    air, proc = df["Air temperature"].to_numpy(), df["Process temperature"].to_numpy()
    rpm, torque, wear = df["Rotational speed"].to_numpy(), df["Torque"].to_numpy(), df["Tool wear"].to_numpy()
    type_ord = df["Type"].map({"L": 0, "M": 1, "H": 2}).to_numpy()
    osf_limit = np.array([OSF_LIMIT["L"], OSF_LIMIT["M"], OSF_LIMIT["H"]], dtype=float)[type_ord]

    # Physics-informed features
    temp_diff = proc - air
    power = torque * rpm * 2 * np.pi / 60
    strain = wear * torque
    return pd.DataFrame({
        "air_temp": air, "process_temp": proc, "rpm": rpm, "torque": torque, "tool_wear": wear,
        "temp_diff": temp_diff,
        "power_W": power,
        "wear_x_torque": strain,
        "osf_margin": osf_limit - strain,
        "power_margin_low": power - PWF_LOW,
        "power_margin_high": PWF_HIGH - power,
        "hdf_temp_margin": temp_diff - HDF_TEMP_DIFF,
        "hdf_rpm_margin": rpm - HDF_RPM,
        "tool_wear_margin": TWF_WEAR - wear,
        "type_ord": type_ord,   # product quality variant (ordinal: L < M < H)
    }, index=df.index)
