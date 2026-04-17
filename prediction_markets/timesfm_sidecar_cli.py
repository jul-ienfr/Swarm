from __future__ import annotations

import sys
from pathlib import Path

if __package__:
    from .timesfm_sidecar import main
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from prediction_markets.timesfm_sidecar import main


if __name__ == "__main__":
    raise SystemExit(main())
