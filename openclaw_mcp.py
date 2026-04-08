from __future__ import annotations

import importlib
import sys


_impl = importlib.import_module("swarm_mcp")

if __name__ == "__main__":
    _impl.mcp.run(transport="stdio")
else:
    sys.modules[__name__] = _impl
