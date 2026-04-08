from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Legacy top-level smoke scripts are not stable pytest targets.
collect_ignore = ["test_agent.py", "test_supervisor_hybrid.py"]
