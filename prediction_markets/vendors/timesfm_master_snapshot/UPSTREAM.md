Repository: `https://github.com/google-research/timesfm`
Branch: `master`
Commit: `d720daa6786539c2566a44464fbda1019c0a82c0`
Snapshot date: `2026-04-16`

Vendored files:
- `LICENSE`
- `pyproject.toml`
- `src/timesfm/__init__.py`
- `src/timesfm/configs.py`
- `src/timesfm/flax/`
- `src/timesfm/torch/`
- `src/timesfm/timesfm_2p5/`
- `src/timesfm/utils/xreg_lib.py`

Intent:
- keep a minimal `master` snapshot for local TimesFM inference
- avoid relying on stale tagged releases
- let Swarm wrap upstream code without refactoring it in place
