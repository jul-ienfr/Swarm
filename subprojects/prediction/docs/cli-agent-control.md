# Prediction CLI for Agent-Complete Operations (v2)

This subproject includes a local first-party CLI wrapper at:

- `scripts/mc-cli.cjs` from `/home/jul/swarm/subprojects/prediction`
- `subprojects/prediction/scripts/mc-cli.cjs` from `/home/jul/swarm`
- `scripts/prediction-ops.cjs` as a local operator shortcut for `runs`, `capabilities`, `health`, `dispatch`, `paper`, `shadow`, `live`, and feed/bootstrap aliases

Designed for autonomous/headless usage first:
- API key auth support
- Profile persistence (~/.prediction/profiles/*.json)
- Stable JSON mode (`--json`) with NDJSON for streaming
- Deterministic exit code categories
- SSE streaming for real-time event watching
- Compound subcommands for memory, soul, comments

The `live` surface is still `preflight-only`: it threads `execution_readiness` and `multi_venue_execution` through the canonical `execution_projection` preview, but it does not claim a real websocket or live-execution transport in this autonomous subproject.
The same `POST /api/v1/prediction-markets/runs/:run_id/live` route now also accepts an explicit `execution_mode` of `preflight` or `live`; the safe default remains `preflight`, and `live` still requires an already approved live intent.

A same-origin operator dashboard app is now available too:
- same-origin app route: `/prediction-markets/dashboard`
- standalone local proxy: `node scripts/prediction-dashboard.cjs --upstream http://127.0.0.1:3000`
- the dashboard reads the canonical run detail, the dashboard read models (`overview`, `runs`, `run detail`, `benchmark`, `venues`), the `dispatch`/`paper`/`shadow`/`live` operator surfaces, and the live-intent previews exposed through `execution_projection_selected_preview`, `live_trade_intent_preview`, `paper_trade_intent_preview`, and `shadow_trade_intent_preview`
- the dashboard should also surface a dedicated `Cross-Venue / Arbitrage` area fed by `cross_venue_intelligence`, `cross_venue_summary`, and `shadow_arbitrage`, shadow-only at first, with Polymarket/Kalshi as the initial pair
- the dashboard itself uses HTTP refresh/proxy calls and can also consume the built-in SSE event stream at `/api/v1/prediction-markets/dashboard/events`; it does not require external websocket infrastructure in this subproject

Python entry points in this repo:
- `main.py` is the Swarm CLI entry point.
- `swarm_mcp.py` is the canonical Swarm MCP server entry point.
- `openclaw_mcp.py` remains a legacy compatibility alias for `swarm_mcp.py`.

## Quick start

1) Ensure the CLI API is running.
2) Set environment variables or use profile flags:

- MC_URL=http://127.0.0.1:3000
- MC_API_KEY=your-key
- `PREDICTION_BASE_URL=http://127.0.0.1:3000` to let `prediction-ops.cjs` inject a default local URL
- `PREDICTION_DEFAULT_VENUE=polymarket` to let `prediction-ops.cjs` inject a local default venue for feed/bootstrap surfaces

3) Run commands:

```bash
npm run cli -- prediction-markets runs --json
npm run ops -- runs --json
npm run dashboard -- --upstream http://127.0.0.1:3000
npm run dashboard:help
npm run pm:help
npm run pm:feed -- --venue polymarket --json
npm run pm:feed:summary
npm run pm:feed:request
node scripts/mc-cli.cjs prediction-markets runs --json
node scripts/prediction-ops.cjs live --run-id <run-id> --execution-pathways-summary
node scripts/prediction-ops.cjs live --run-id <run-id> --print-summary
node scripts/prediction-ops.cjs live --run-id <run-id> --print-request
node scripts/mc-cli.cjs prediction-markets live --run-id <run-id> --url http://127.0.0.1:3000
node scripts/mc-cli.cjs prediction-markets live --run-id <run-id> --execution-mode live --json --url http://127.0.0.1:3000
node scripts/mc-cli.cjs prediction-markets replay --run-id <run-id> --json
```

Local validation helpers from this subproject:

```bash
npm run test
npm run test:advisor
npm run test:ops
npm run typecheck
npm run typecheck:full
```

Local operator aliases from this subproject:

```bash
npm run pm:runs -- --json
npm run pm:capabilities -- --venue polymarket --json
npm run pm:capabilities:summary
npm run pm:health -- --venue polymarket --json
npm run pm:health:summary
npm run pm:feed -- --venue polymarket --json
npm run pm:feed:summary
npm run pm:feed:request
npm run pm:dispatch -- --run-id <run-id> --execution-pathways-summary
npm run pm:dispatch:summary -- --run-id <run-id>
npm run pm:dispatch:request -- --run-id <run-id>
npm run pm:paper -- --run-id <run-id> --execution-pathways-summary
npm run pm:paper:summary -- --run-id <run-id>
npm run pm:paper:request -- --run-id <run-id>
npm run pm:shadow -- --run-id <run-id> --execution-pathways-summary
npm run pm:shadow:summary -- --run-id <run-id>
npm run pm:shadow:request -- --run-id <run-id>
npm run pm:live -- --run-id <run-id> --execution-pathways-summary
npm run pm:live:surface -- --run-id <run-id>
npm run pm:live:summary -- --run-id <run-id>
npm run pm:live:request -- --run-id <run-id>
```

The generic helper can also be used directly:

```bash
npm run ops -- live --run-id <run-id> --execution-pathways-summary
npm run ops -- feed --venue polymarket --json
node scripts/prediction-ops.cjs capabilities --print-summary
node scripts/prediction-ops.cjs feed --print-request
node scripts/prediction-ops.cjs runs --operator-json --limit 5
node scripts/prediction-ops.cjs live --run-id <run-id> --operator-summary
node scripts/prediction-ops.cjs live --run-id <run-id> --print-summary
node scripts/prediction-ops.cjs shadow --run-id <run-id> --print-command
node scripts/prediction-dashboard.cjs --upstream http://127.0.0.1:3000
```

`--operator-summary` is the local preset for operator surfaces; it expands to:

- `--execution-pathways-summary`
- `--research-summary`
- `--benchmark-summary`

`--operator-json` adds the same operator preset and also enables `--json`.

`--print-summary` prints a compact human-readable operator/feed surface line, including:

- `surface`
- `kind`
- `method`
- `path`
- `preflight`
- `benchmark`
- `default_venue`
- `projection`
- `runtime`

It now also prints:

- `prediction_surface_semantics` with `readiness`, `promotion`, and `transport`
- `prediction_request_preview` as a single-line HTTP preview
- `prediction_surface_summary` as the operator-facing wording for the surface

`--print-request` prints the resolved HTTP request for the surface as JSON, including:

- `method`
- `path`
- `url`
- `body`

It also includes:

- `request_preview`
- `surface_summary`

`--print-command` and `--print-request` also include a `semantics` object so local tooling can distinguish:

- `operator_preflight`
- `operator_surface`
- `feed_bootstrap`
- `run_readback`

Equivalent commands from the Swarm repo root:

```bash
node subprojects/prediction/scripts/mc-cli.cjs prediction-markets runs --json
node subprojects/prediction/scripts/mc-cli.cjs prediction-markets live --run-id <run-id> --url http://127.0.0.1:3000
node subprojects/prediction/scripts/mc-cli.cjs prediction-markets replay --run-id <run-id> --json
```

## Command groups

### auth
- login --username --password
- logout
- whoami

### agents
- list
- get --id
- create --name --role [--body '{}']
- update --id [--body '{}']
- delete --id
- wake --id
- diagnostics --id
- heartbeat --id
- attribution --id [--hours 24] [--section identity,cost] [--privileged]
- memory get --id
- memory set --id --content "..." [--append]
- memory set --id --file ./memory.md
- memory clear --id
- soul get --id
- soul set --id --content "..."
- soul set --id --file ./soul.md
- soul set --id --template operator
- soul templates --id [--template name]

### tasks
- list
- get --id
- create --title [--body '{}']
- update --id [--body '{}']
- delete --id
- queue --agent <name> [--max-capacity 2]
- broadcast --id --message "..."
- comments list --id
- comments add --id --content "..." [--parent-id 5]

### sessions
- list
- control --id --action monitor|pause|terminate
- continue --kind claude-code|codex-cli --id --prompt "..."
- transcript --kind claude-code|codex-cli|hermes --id [--limit 40] [--source]

### connect
- register --tool-name --agent-name [--body '{}']
- list
- disconnect --connection-id

### tokens
- list [--timeframe hour|day|week|month|all]
- stats [--timeframe]
- by-agent [--days 30]
- agent-costs [--timeframe]
- task-costs [--timeframe]
- trends [--timeframe]
- export [--format json|csv] [--timeframe] [--limit]
- rotate (shows current key info)
- rotate --confirm (generates new key -- admin only)

### skills
- list
- content --source --name
- check --source --name
- upsert --source --name --file ./skill.md
- delete --source --name

### cron
- list
- create/update/pause/resume/remove/run [--body '{}']

### events
- watch [--types agent,task] [--timeout-ms 3600000]

  Streams SSE events to stdout. In `--json` mode, outputs NDJSON (one JSON object per line). Press Ctrl+C to stop.

### status
- health (no auth required)
- overview
- dashboard
- gateway
- models
- capabilities

### prediction-markets
- markets --venue polymarket|kalshi [--search ...] [--limit 20]
- runs --venue polymarket|kalshi [--recommendation bet|no_trade|wait] [--limit 20] [--artifact-audit-summary] [--execution-readiness-summary] [--execution-pathways-summary] [--research-summary] [--benchmark-summary]
- run --run-id <id> [--artifact-audit-summary] [--execution-readiness-summary] [--execution-pathways-summary] [--research-summary] [--benchmark-summary]
- dispatch --run-id <id> [--execution-pathways-summary] [--research-summary] [--benchmark-summary]
- paper --run-id <id> [--execution-pathways-summary] [--research-summary] [--benchmark-summary]
- shadow --run-id <id> [--execution-pathways-summary] [--research-summary] [--benchmark-summary]
- live --run-id <id> [--execution-pathways-summary] [--research-summary] [--benchmark-summary]
- benchmark-summary is a text-mode companion flag that prints only the compact benchmark/promotion gate line when benchmark hints are present.
- advise --market-id <id> [--research-signals ...]
- replay --run-id <id>
- capabilities --venue polymarket|kalshi
- health --venue polymarket|kalshi

`--artifact-audit-summary` adds compact text-mode summaries for `artifact_audit` and `artifact_readback` on `run`/`runs`.
`--execution-readiness-summary` adds compact text-mode summaries for `execution_readiness` on `run`/`runs`.
`--execution-pathways-summary` adds compact text-mode summaries for `execution_pathways`, `execution_projection`, or equivalent runtime projection fields on `run`/`runs`, `dispatch`, `paper`, `shadow`, and `live` when present. When the runtime exposes them, it also prints a compact `strategy_layer:` line covering primary strategy, market regime, strategy counts, strategy shadow summary, resolution anomalies, and execution-intent preview kind/source hints.
`--research-summary` adds compact text-mode summaries for top-level research runtime hints on `run`/`runs`, `dispatch`, `paper`, `shadow`, and `live`, and also on `advise`/`replay` when the server response carries a nested `prediction_run`. When present, it also prints the benchmark/uplift gate summary derived from the research sidecar, and the research output now includes a separate `research_origin:` line so the summary makes the baseline vs research-driven distinction and any abstention-driven flip explicit.
When present, `--research-summary` also prints a compact `benchmark:` gate line with `status`, `promotion`, `ready`, `uplift`, `blockers`, and `reasons` when the runtime exposes benchmark/uplift hints derived from the research comparative report. The CLI now also prints a sibling `benchmark_evidence:` line that makes the preview vs promotion-evidence split explicit (`preview=yes/no`, `promotion_evidence=...`, `promotion_status=...`, `ready=...`), plus a compact `benchmark_state:` line that carries the canonical verdict and blocker summary. When both canonical `benchmark_*` fields and legacy `research_benchmark_*` aliases are present, the CLI prefers the canonical `benchmark_*` values and only falls back to the research aliases when the canonical ones are absent.
`--benchmark-summary` prints only the compact `benchmark:` gate line and the matching `benchmark_evidence:` companion line when benchmark/uplift hints exist, without requiring the rest of the research runtime summary. The compact lines follow the same `status/promotion/ready/uplift` shape as the ones surfaced via `--research-summary`, and they also work on `run`/`runs`, `dispatch`, plus `paper`, `shadow`, and `live` surfaces when they expose benchmark hints. `benchmark_state:` is printed alongside them when the runtime exposes a canonical verdict or promotion blocker summary, with the same canonical-over-legacy alias preference.
`--research-signals-summary` remains the opt-in helper that only counts injected CLI research signals on `advise`.
When present, `--execution-pathways-summary` also surfaces the compact top-level `research:` runtime hints on `run`/`runs` so the CLI does not need to reparse research data from nested artifacts.
`dispatch` is an operator-only preflight surface: it does not execute on venues, and the local CLI wrapper prints a compact `dispatch_preflight` line with status, selected path, blockers, and summary text.
`paper` is the first bounded operator surface beyond generic preflight: it consumes `execution_projection.projected_paths.paper`, surfaces the canonical paper preview, stays without venue execution, and prints a compact `paper_surface` line in text mode.
`shadow` is the second bounded operator surface beyond generic preflight: it consumes `execution_projection.projected_paths.shadow`, surfaces the canonical shadow preview, stays strictly `preflight-only`, and prints a compact `shadow_surface` line in text mode.
`live` is the third bounded operator surface beyond generic preflight: it is benchmark-gated, consumes `execution_projection.projected_paths.live`, surfaces the canonical live preview, stays strictly `preflight-only`, and prints a compact `live_surface` line in text mode.
`capabilities` and `health` are the feed/operator bootstrap surfaces for this subproject: they expose the local contracts, automation constraints, budget envelopes, and feed status (`market_feed`, `user_feed`, `rtds`) without requiring the legacy workspace shape.
The `live` surface is execution_projection-first: it reads the canonical `execution_projection` preview, never recalculates venue execution on its own, and only reflects the selected live path when the benchmark gate is still open and the canonical selected path is `live`.
When benchmark promotion is still unproven or the canonical selected path is not `live`, the `live` surface stays blocked and explains that state explicitly instead of bypassing `execution_projection`.
When the runtime exposes them, the summary also surfaces the selected path state, whether the surface is consuming the canonical execution projection instead of recalculating it, a preferred canonical selected-path preview by first consuming the top-level `execution_projection_selected_preview` hint when present, then falling back to `trade_intent_guard.trade_intent_preview` or selected-path sizing signals, compact selected-path canonical sizing and `shadow_arbitrage_signal` hints, and read-only `shadow_arbitrage` sizing/simulation signals such as penalized size and shadow edge.

The production gate for prediction markets is explicitly proof-driven:

- `proof chain`: predictive edge -> executable edge -> capturable edge -> durable edge
- `gates`: out-of-sample benchmark, positive `ExecutableEdge` after fees/slippage/hedge risk, stable `paper` vs `shadow`, and valid runbooks / kill-switch / rollback
- `kill criteria`: no robust uplift, friction erases the edge, `paper` and `shadow` diverge materially, or ops incidents repeat
- `advisor-first`: until the chain is complete, `live` remains a preview surface and not a `profit engine`

### export (admin)
- audit [--format json|csv] [--since <unix>] [--until <unix>] [--limit]
- tasks [--format json|csv] [--since] [--until] [--limit]
- activities [--format json|csv] [--since] [--until] [--limit]
- pipelines [--format json|csv] [--since] [--until] [--limit]

### raw
- raw --method GET --path /api/... [--body '{}']

## Exit code contract

- 0 success
- 2 usage error
- 3 auth error (401)
- 4 permission error (403)
- 5 network/timeout
- 6 server error (5xx)

## API contract parity gate

To detect drift between Next.js route handlers and openapi.json, use:

```bash
node scripts/check-api-contract-parity.mjs \
  --root . \
  --openapi openapi.json \
  --ignore-file scripts/api-contract-parity.ignore
```

Machine output:

```bash
node scripts/check-api-contract-parity.mjs --json
```

The checker scans `src/app/api/**/route.ts(x)`, derives operations (METHOD + /api/path), compares against OpenAPI operations, and exits non-zero on mismatch.

Baseline policy in this repo:
- `scripts/api-contract-parity.ignore` currently stores a temporary baseline of known drift.
- CI enforces no regressions beyond baseline.
- When you fix a mismatch, remove its line from ignore file in the same PR.
- Goal is monotonic burn-down to an empty ignore file.

## Next steps

- Promote script to package.json bin entry (`mc`).
- Add retry/backoff for transient failures.
- Add integration tests that run the CLI against a test server fixture.
- Add richer pagination/filter flags for list commands.
