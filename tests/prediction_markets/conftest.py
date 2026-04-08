from __future__ import annotations

import importlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Force the real package to be loaded before any legacy test shim can
# register a namespace-only placeholder module named `prediction_markets`.
importlib.import_module("prediction_markets")
