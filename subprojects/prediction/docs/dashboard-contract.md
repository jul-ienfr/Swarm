# Prediction Markets Dashboard Contract

This note is a smoke-test anchor for the dashboard surfaces exposed by the `prediction-markets` subproject.

- The dashboard is a same-origin operator view and an `advisor-first` validation surface; `live` stays `preflight-first` until a double-approved live intent materializes governed venue execution.
- The dashboard surfaces `dispatch`, `paper`, `shadow`, and `live` from the same canonical run detail.
- The dashboard makes the proof chain visible end to end: predictive edge, executable edge, capturable edge, and durable edge.
- Promotion gates are explicit in the dashboard: out-of-sample benchmark, positive executable edge after friction, stable `paper` vs `shadow`, and valid runbooks / kill-switch / rollback.
- Research validation is explicit too: `resolved_history`, `cost_model`, and `walk_forward` must surface both readiness badges and human-readable blockers when a run stays in `thin` or `preview`.
- kill criteria are explicit too: no robust uplift, edge decay after friction, material `paper` vs `shadow` divergence, or repeated ops incidents.
- The live-intent flow keeps a `double approval` invariant before a live intent can progress.
- Governed live-intent previews are canonical today through `execution_projection_selected_preview`, `live_trade_intent_preview`, `paper_trade_intent_preview`, `shadow_trade_intent_preview`, and `trade_intent_guard`.
- `approval_ticket`, `operator_thesis`, and `research_pipeline_trace` are documented as optional companion fields around `execution_pathways`; the dashboard may render them when present but must not require them.
- The dashboard must not treat `approval_ticket` as the canonical approval source for `live` yet; the existing approved live-intent flow remains the source of truth until the main service layer is fully wired.
- `research_pipeline_trace` should be rendered as lineage/context only; its absence is valid and must not degrade the core operator workflow.
- Dashboard refresh is HTTP-based; SSE/events remain a separate operator concern and are documented alongside event streaming helpers.

Canonical dashboard entry points:

- `/prediction-markets/dashboard`
- `/api/v1/prediction-markets/runs/:run_id`
- `/api/v1/prediction-markets/runs/:run_id/dispatch`
- `/api/v1/prediction-markets/runs/:run_id/paper`
- `/api/v1/prediction-markets/runs/:run_id/shadow`
- `/api/v1/prediction-markets/runs/:run_id/live`
