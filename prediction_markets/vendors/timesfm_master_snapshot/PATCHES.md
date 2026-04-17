Local adaptations are intentionally kept outside the vendored upstream files.

Current patch policy:
- do not edit files under `src/timesfm/` unless an upstream incompatibility blocks local loading
- keep Swarm-specific orchestration in:
  - `prediction_markets/timesfm_sidecar.py`
  - `prediction_markets/timesfm_sidecar_cli.py`

Current local patches applied directly to vendored files:
- none
