import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = Path(os.getenv("PM_MODEL_DIR", ROOT / "models"))
FIG_DIR = Path(os.getenv("PM_FIG_DIR", ROOT / "reports" / "figures"))
DATA_PATH = Path(os.getenv("PM_DATA_PATH", ROOT / "data" / "predictive_maintenance.csv"))
CORS_ORIGINS = os.getenv("PM_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
MAX_BATCH_ROWS = int(os.getenv("PM_MAX_BATCH_ROWS", "20000"))
MAX_UPLOAD_BYTES = int(float(os.getenv("PM_MAX_UPLOAD_MB", "5")) * 1_000_000)
API_KEY = os.getenv("PM_API_KEY", "")                       # empty = auth disabled
RATE_LIMIT_PER_MIN = int(os.getenv("PM_RATE_LIMIT_PER_MIN", "0"))  # 0 = disabled
DRIFT_WINDOW = int(os.getenv("PM_DRIFT_WINDOW", "5000"))
DRIFT_MIN_SAMPLES = int(os.getenv("PM_DRIFT_MIN_SAMPLES", "100"))
LOG_LEVEL = os.getenv("PM_LOG_LEVEL", "INFO")
# Built React app; when present the API also serves the UI (single-container deploy)
STATIC_DIR = Path(os.getenv("PM_STATIC_DIR", ROOT / "frontend" / "dist"))
SERVE_UI = os.getenv("PM_SERVE_UI", "0") == "1"

# Feature engineering lives in src/ and is shared with the training notebook
sys.path.insert(0, str(ROOT / "src"))
