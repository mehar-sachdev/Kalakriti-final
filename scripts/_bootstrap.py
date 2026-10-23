"""Lets the scripts run as `python scripts/xxx.py` from anywhere (adds the repo root to sys.path)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
