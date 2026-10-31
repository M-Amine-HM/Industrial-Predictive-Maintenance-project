import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = Path(os.getenv("PM_MODEL_DIR", ROOT / "models"))
FIG_DIR = Path(os.getenv("PM_FIG_DIR", ROOT / "reports" / "figures"))
DATA_PATH = Path(os.getenv("PM_DATA_PATH", ROOT / "data" / "predictive_maintenance.csv"))
CORS_ORIGINS = os.getenv("PM_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
MAX_BATCH_ROWS = int(os.getenv("PM_MAX_BATCH_ROWS", "20000"))

# Feature engineering lives in src/ and is shared with the training notebook
sys.path.insert(0, str(ROOT / "src"))
