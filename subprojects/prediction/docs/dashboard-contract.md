# Prediction Markets Dashboard Contract

This note is a smoke-test anchor for the dashboard surfaces exposed by the `prediction-markets` subproject.

- The dashboard is a `preflight-only` operator view and an `advisor-first` validation surface.
- The dashboard surfaces `dispatch`, `paper`, `shadow`, and `live` from the same canonical run detail.
- The dashboard makes the proof chain visible end to end: predictive edge, executable edge, capturable edge, and durable edge.
- Promotion gates are explicit in the dashboard: out-of-sample benchmark, positive executable edge after friction, stable `paper` vs `shadow`, and valid runbooks / kill-switch / rollback.
- kill criteria are explicit too: no robust uplift, edge decay after friction, material `paper` vs `shadow` divergence, or repeated ops incidents.
- The live-intent flow keeps a `double approval` invariant before a live intent can progress.
- Dashboard refresh is HTTP-based; SSE/events remain a separate operator concern and are documented alongside event streaming helpers.

Canonical dashboard entry points:

- `/prediction-markets/dashboard`
- `/api/v1/prediction-markets/runs/:run_id`
- `/api/v1/prediction-markets/runs/:run_id/dispatch`
- `/api/v1/prediction-markets/runs/:run_id/paper`
- `/api/v1/prediction-markets/runs/:run_id/shadow`
- `/api/v1/prediction-markets/runs/:run_id/live`
