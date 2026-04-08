import { createServer } from 'node:http'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { resolvePredictionCliPath } from './helpers/prediction-cli-path'

const execFileAsync = promisify(execFile)
const CLI = resolvePredictionCliPath()

function makeShadowArbitrageReport() {
  return {
    read_only: true,
    generated_at: '2026-04-08T00:00:00.000Z',
    as_of_at: '2026-04-08T00:00:00.000Z',
    executable_edge: {
      edge_id: 'edge:shadow-arb-001',
      canonical_event_id: 'cve:shadow-arb-001',
      opportunity_type: 'true_arbitrage',
      buy_ref: { venue: 'polymarket', market_id: 'shadow-arb-poly' },
      sell_ref: { venue: 'kalshi', market_id: 'shadow-arb-kalshi' },
      buy_price_yes: 0.43,
      sell_price_yes: 0.58,
      gross_spread_bps: 1_500,
      fee_bps: 60,
      slippage_bps: 40,
      hedge_risk_bps: 25,
      executable_edge_bps: 1_375,
      confidence_score: 0.88,
      executable: true,
      evaluated_at: '2026-04-08T00:00:00.000Z',
      notes: ['stale_edge_expired:false'],
    },
    sizing: {
      requested_size_usd: null,
      base_size_usd: 100,
      recommended_size_usd: 40,
      simulated_size_usd: 40,
      size_multiplier: 0.4,
    },
    summary: {
      base_executable_edge_bps: 1_375,
      shadow_edge_bps: 1_210,
      base_size_usd: 100,
      recommended_size_usd: 40,
      hedge_success_probability: 0.72,
      estimated_net_pnl_bps: 88,
      estimated_net_pnl_usd: 0.88,
      worst_case_kind: 'hedge_delay',
      failure_case_count: 3,
    },
    failure_cases: [],
  }
}

function makeCanonicalExecutionProjectionGate() {
  return {
    gate_name: 'execution_projection',
    single_runtime_gate: true,
    enforced_for_modes: ['paper', 'shadow', 'live'],
  }
}

function makeSizingSignal(input: {
  canonicalSizeUsd: number
  source: 'trade_intent_preview' | 'trade_intent_preview+shadow_arbitrage' | 'shadow_arbitrage'
  previewSizeUsd?: number | null
  shadowRecommendedSizeUsd?: number | null
  maxUnhedgedLegMs?: number | null
}) {
  return {
    preview_size_usd: input.previewSizeUsd ?? input.canonicalSizeUsd,
    base_size_usd: 100,
    recommended_size_usd: input.canonicalSizeUsd,
    max_size_usd: 100,
    canonical_size_usd: input.canonicalSizeUsd,
    shadow_recommended_size_usd: input.shadowRecommendedSizeUsd ?? null,
    limit_price: 0.51,
    max_slippage_bps: 50,
    max_unhedged_leg_ms: input.maxUnhedgedLegMs ?? 1_000,
    time_in_force: 'ioc',
    multiplier: input.canonicalSizeUsd / 100,
    sizing_source: 'default',
    source: input.source,
    notes: [],
  }
}

function makeShadowArbitrageSignal() {
  return {
    read_only: true,
    market_id: 'shadow-arb-poly',
    venue: 'polymarket',
    base_executable_edge_bps: 1_375,
    shadow_edge_bps: 1_210,
    recommended_size_usd: 40,
    hedge_success_probability: 0.72,
    estimated_net_pnl_bps: 88,
    estimated_net_pnl_usd: 0.88,
    worst_case_kind: 'hedge_delay',
    failure_case_count: 3,
  }
}

function makeTradeIntentPreview(input: {
  sizeUsd: number
  maxUnhedgedLegMs?: number
}) {
  return {
    intent_id: `preview-${input.sizeUsd}`,
    venue: 'polymarket',
    market_id: 'shadow-arb-poly',
    side: 'yes',
    size_usd: input.sizeUsd,
    limit_price: 0.51,
    max_slippage_bps: 50,
    max_unhedged_leg_ms: input.maxUnhedgedLegMs ?? 1_000,
    time_in_force: 'ioc',
    forecast_ref: 'forecast:shadow-arb-poly:2026-04-08T00:00:00.000Z',
    risk_checks_passed: true,
    created_at: '2026-04-08T00:00:00.000Z',
    notes: 'shadow preview intent',
  }
}

function makeTradeIntentGuard(input: {
  selectedPath: 'paper' | 'shadow' | 'live'
  preview: ReturnType<typeof makeTradeIntentPreview>
  previewSource?: string
}) {
  return {
    gate_name: 'trade_intent_guard',
    selected_path: input.selectedPath,
    highest_safe_mode: input.selectedPath,
    trade_intent_preview: input.preview,
    metadata: {
      trade_intent_preview_source: input.previewSource ?? 'execution_projection',
    },
  }
}

function makeResearchHints() {
  return {
    research_pipeline_id: 'research-pipeline-runtime',
    research_pipeline_version: 'v3',
    research_forecaster_count: 2,
    research_weighted_probability_yes: 0.67,
    research_weighted_coverage: 0.83,
    research_compare_preferred_mode: 'aggregate',
    research_compare_summary: 'Preferred mode: aggregate.',
    research_abstention_policy_version: 'structured-abstention-v1',
    research_abstention_policy_blocks_forecast: false,
    research_forecast_probability_yes_hint: 0.69,
    research_benchmark_gate_status: 'preview_only',
    research_benchmark_promotion_status: 'unproven',
    research_benchmark_promotion_ready: false,
    research_benchmark_gate_blockers: ['out_of_sample_unproven'],
    research_benchmark_gate_reasons: ['out_of_sample_unproven'],
    research_benchmark_gate_summary:
      'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no blockers=out_of_sample_unproven out_of_sample=unproven',
    research_benchmark_uplift_bps: 1100,
  }
}

describe('prediction markets CLI execution pathways', () => {
  let server: ReturnType<typeof createServer>
  let baseUrl = ''

  beforeAll(async () => {
    server = createServer((req, res) => {
      const url = new URL(req.url ?? '/', 'http://127.0.0.1')

      if (req.method === 'GET' && url.pathname === '/api/v1/prediction-markets/runs') {
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(JSON.stringify({
          runs: [
            {
              run_id: 'run-pathways-001',
              workspace_id: 1,
              venue: 'polymarket',
              mode: 'advise',
              market_id: 'mkt-pathways-001',
              market_slug: 'mkt-pathways-001',
              status: 'completed',
              recommendation: 'wait',
              ...makeResearchHints(),
              execution_pathways: {
                highest_actionable_mode: 'paper',
                pathways: [
                  { mode: 'paper', status: 'ready' },
                  { mode: 'shadow', status: 'blocked' },
                ],
                summary: 'paper is currently the highest actionable execution pathway.',
              },
            },
            {
              run_id: 'run-pathways-002',
              workspace_id: 1,
              venue: 'polymarket',
              mode: 'advise',
              market_id: 'mkt-pathways-002',
              market_slug: 'mkt-pathways-002',
              status: 'completed',
              recommendation: 'bet',
              ...makeResearchHints(),
              execution_projection: {
                gate_name: 'execution_projection',
                preflight_only: true,
                requested_path: 'live',
                selected_path: 'shadow',
                verdict: 'downgraded',
                manual_review_required: true,
                ttl_ms: 30000,
                highest_safe_requested_mode: 'shadow',
                recommended_effective_mode: 'shadow',
                basis: {
                  uses_execution_readiness: true,
                  uses_compliance: true,
                  uses_capital: true,
                  uses_reconciliation: true,
                  canonical_gate: makeCanonicalExecutionProjectionGate(),
                },
                summary: 'requested live, selected shadow; gate execution_projection; preflight only. requested live, selected shadow, recommended shadow',
                projected_paths: {
                  paper: { status: 'ready', effective_mode: 'paper' },
                  shadow: {
                    status: 'degraded',
                    effective_mode: 'shadow',
                    simulation: {
                      shadow_arbitrage: makeShadowArbitrageReport(),
                    },
                    trade_intent_preview: makeTradeIntentPreview({
                      sizeUsd: 50,
                    }),
                    canonical_trade_intent_preview: makeTradeIntentPreview({
                      sizeUsd: 40,
                    }),
                    sizing_signal: makeSizingSignal({
                      canonicalSizeUsd: 40,
                      previewSizeUsd: 50,
                      shadowRecommendedSizeUsd: 40,
                      source: 'trade_intent_preview+shadow_arbitrage',
                    }),
                    shadow_arbitrage_signal: makeShadowArbitrageSignal(),
                  },
                  live: { status: 'blocked', effective_mode: 'shadow' },
                },
                microstructure_lab: {
                  market_id: 'mkt-pathways-002',
                  venue: 'polymarket',
                  summary: {
                    base_executable_edge_bps: 1800,
                    worst_case_kind: 'spread_collapse',
                    worst_case_severity: 'medium',
                    worst_case_executable_edge_bps: 1779,
                    executable_deterioration_bps: 21,
                    execution_quality_score: 0.8125,
                    recommended_mode: 'paper',
                    event_counts: {
                      partial_fill: 1,
                      one_leg_fill: 1,
                      cancel_replace: 1,
                      queue_miss: 1,
                      hedge_delay: 1,
                      stale_book: 1,
                      spread_collapse: 1,
                    },
                  },
                },
              },
              execution_projection_selected_preview: makeTradeIntentPreview({
                sizeUsd: 40,
              }),
              execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
              trade_intent_guard: makeTradeIntentGuard({
                selectedPath: 'shadow',
                preview: makeTradeIntentPreview({
                  sizeUsd: 40,
                }),
              }),
              shadow_arbitrage: makeShadowArbitrageReport(),
            },
            {
              run_id: 'run-pathways-003',
              workspace_id: 1,
              venue: 'polymarket',
              mode: 'advise',
              market_id: 'mkt-pathways-003',
              market_slug: 'mkt-pathways-003',
              status: 'completed',
              recommendation: 'bet',
              ...makeResearchHints(),
              execution_pathways_highest_actionable_mode: 'paper',
              execution_projection_gate_name: 'execution_projection',
              execution_projection_preflight_only: true,
              execution_projection_requested_path: 'live',
              execution_projection_selected_path: 'paper',
              execution_projection_selected_path_status: 'ready',
              execution_projection_selected_path_effective_mode: 'paper',
              execution_projection_selected_path_reason_summary:
                'paper remains the safest mode while execution stays informational only.',
              execution_projection_verdict: 'downgraded',
              execution_projection_highest_safe_requested_mode: 'paper',
              execution_projection_recommended_effective_mode: 'paper',
              execution_projection_manual_review_required: true,
              execution_projection_ttl_ms: 30000,
              execution_projection_expires_at: '2026-04-08T00:00:30.000Z',
              execution_projection_blocking_reasons: [],
              execution_projection_downgrade_reasons: [
                'capital_ledger_unavailable',
                'reconciliation_unavailable',
              ],
              execution_projection_summary:
                'requested live, selected paper; gate execution_projection; preflight only. requested live, selected paper, recommended paper',
              execution_projection_preflight_summary: {
                gate_name: 'execution_projection',
                preflight_only: true,
                requested_path: 'live',
                selected_path: 'paper',
                verdict: 'downgraded',
                highest_safe_requested_mode: 'paper',
                recommended_effective_mode: 'paper',
                manual_review_required: true,
                ttl_ms: 30000,
                expires_at: '2026-04-08T00:00:30.000Z',
                counts: {
                  total: 3,
                  eligible: 1,
                  ready: 1,
                  degraded: 0,
                  blocked: 2,
                },
                basis: {
                  uses_execution_readiness: true,
                  uses_compliance: true,
                  uses_capital: false,
                  uses_reconciliation: false,
                  capital_status: 'unavailable',
                  reconciliation_status: 'unavailable',
                },
                source_refs: ['run-pathways-003:pipeline_guard'],
                blockers: [],
                downgrade_reasons: [
                  'capital_ledger_unavailable',
                  'reconciliation_unavailable',
                ],
                summary:
                  'gate=execution_projection preflight=yes verdict=downgraded requested=live selected=paper highest_safe=paper recommended=paper manual_review=yes ttl_ms=30000 eligible=1/3 counts=ready:1|degraded:0|blocked:2 basis=readiness,compliance refs=1 blockers=0 downgrades=2',
              },
              execution_projection_capital_status: 'unavailable',
              execution_projection_reconciliation_status: 'unavailable',
              execution_projection_selected_preview: {
                intent_id: 'preview-paper-35',
                venue: 'polymarket',
                market_id: 'mkt-pathways-003',
                side: 'yes',
                size_usd: 35,
                limit_price: 0.48,
                max_slippage_bps: 30,
                max_unhedged_leg_ms: 0,
                time_in_force: 'day',
                forecast_ref: 'forecast:mkt-pathways-003:2026-04-08T00:00:00.000Z',
                risk_checks_passed: true,
                created_at: '2026-04-08T00:00:00.000Z',
                notes: 'paper canonical preview intent',
              },
              execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
              execution_projection_selected_path_canonical_size_usd: 35,
              execution_projection_selected_path_shadow_signal_present: false,
              trade_intent_guard: {
                gate_name: 'trade_intent_guard',
                selected_path: 'paper',
                highest_safe_mode: 'paper',
                trade_intent_preview: {
                  intent_id: 'preview-paper-35',
                  venue: 'polymarket',
                  market_id: 'mkt-pathways-003',
                  side: 'yes',
                  size_usd: 35,
                  limit_price: 0.48,
                  max_slippage_bps: 30,
                  max_unhedged_leg_ms: 0,
                  time_in_force: 'day',
                  forecast_ref: 'forecast:mkt-pathways-003:2026-04-08T00:00:00.000Z',
                  risk_checks_passed: true,
                  created_at: '2026-04-08T00:00:00.000Z',
                  notes: 'paper canonical preview intent',
                },
                metadata: {
                  trade_intent_preview_source: 'canonical_trade_intent_preview',
                },
              },
            },
          ],
          total: 3,
        }))
        return
      }

      if (req.method === 'GET' && url.pathname === '/api/v1/prediction-markets/runs/run-pathways-001') {
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(JSON.stringify({
          run_id: 'run-pathways-001',
          workspace_id: 1,
          venue: 'polymarket',
          mode: 'advise',
          market_id: 'mkt-pathways-001',
          market_slug: 'mkt-pathways-001',
          status: 'completed',
          recommendation: 'wait',
          ...makeResearchHints(),
          execution_projection: {
            gate_name: 'execution_projection',
            preflight_only: true,
            requested_path: 'live',
            selected_path: 'paper',
            verdict: 'downgraded',
            manual_review_required: true,
            ttl_ms: 30000,
            highest_safe_requested_mode: 'paper',
            recommended_effective_mode: 'paper',
            modes: {
              paper: { requested_mode: 'paper', effective_mode: 'paper' },
              shadow: { requested_mode: 'shadow', effective_mode: 'paper' },
              live: { requested_mode: 'live', effective_mode: 'paper' },
            },
            basis: {
              uses_execution_readiness: true,
              uses_compliance: true,
              uses_capital: false,
              uses_reconciliation: false,
              canonical_gate: makeCanonicalExecutionProjectionGate(),
            },
            preflight_summary: {
              gate_name: 'execution_projection',
              preflight_only: true,
              requested_path: 'live',
              selected_path: 'paper',
              verdict: 'downgraded',
              highest_safe_requested_mode: 'paper',
              recommended_effective_mode: 'paper',
              manual_review_required: true,
              ttl_ms: 30000,
              expires_at: '2026-04-08T00:00:30.000Z',
              counts: {
                total: 3,
                eligible: 1,
                ready: 1,
                degraded: 0,
                blocked: 2,
              },
              basis: {
                uses_execution_readiness: true,
                uses_compliance: true,
                uses_capital: false,
                uses_reconciliation: false,
                capital_status: 'unavailable',
                reconciliation_status: 'unavailable',
              },
              source_refs: ['run-pathways-001:pipeline_guard', 'run-pathways-001:compliance_report', 'run-pathways-001:execution_readiness'],
              blockers: ['manual_review_required_for_execution', 'capital_ledger_unavailable', 'reconciliation_unavailable'],
              downgrade_reasons: ['manual_review_required_for_execution', 'capital_ledger_unavailable', 'reconciliation_unavailable'],
              summary: 'gate=execution_projection preflight=yes verdict=downgraded requested=live selected=paper highest_safe=paper recommended=paper manual_review=yes ttl_ms=30000 eligible=1/3 counts=ready:1|degraded:0|blocked:2 basis=readiness,compliance refs=3 blockers=3 downgrades=3',
            },
            summary: 'requested live, selected paper; gate execution_projection; preflight only. requested live, selected paper, recommended paper',
          },
        }))
        return
      }

      if (req.method === 'GET' && url.pathname === '/api/v1/prediction-markets/runs/run-pathways-002') {
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(JSON.stringify({
          run_id: 'run-pathways-002',
          workspace_id: 1,
          venue: 'polymarket',
          mode: 'advise',
          market_id: 'mkt-pathways-002',
          market_slug: 'mkt-pathways-002',
          status: 'completed',
          recommendation: 'bet',
          ...makeResearchHints(),
          research_runtime_summary:
            'research: mode=research_driven pipeline=polymarket-research-pipeline version=poly-025-research-v1 forecasters=3 weighted_yes=0.72 coverage=0.9 preferred=aggregate abstention=structured-abstention-v1 blocks_forecast=no forecast_hint=0.72',
          execution_projection: {
            gate_name: 'execution_projection',
            preflight_only: true,
            requested_path: 'live',
            selected_path: 'shadow',
            verdict: 'downgraded',
            manual_review_required: true,
            ttl_ms: 30000,
            highest_safe_requested_mode: 'shadow',
            recommended_effective_mode: 'shadow',
            modes: {
              paper: { requested_mode: 'paper', effective_mode: 'paper' },
              shadow: { requested_mode: 'shadow', effective_mode: 'shadow' },
              live: { requested_mode: 'live', effective_mode: 'shadow' },
            },
            basis: {
              uses_execution_readiness: true,
              uses_compliance: true,
              uses_capital: true,
              uses_reconciliation: true,
              capital_status: 'attached',
              reconciliation_status: 'degraded',
              canonical_gate: makeCanonicalExecutionProjectionGate(),
            },
            preflight_summary: {
              gate_name: 'execution_projection',
              preflight_only: true,
              requested_path: 'live',
              selected_path: 'shadow',
              verdict: 'downgraded',
              highest_safe_requested_mode: 'shadow',
              recommended_effective_mode: 'shadow',
              manual_review_required: true,
              ttl_ms: 30000,
              expires_at: '2026-04-08T00:00:30.000Z',
              counts: {
                total: 3,
                eligible: 2,
                ready: 1,
                degraded: 1,
                blocked: 1,
              },
              basis: {
                uses_execution_readiness: true,
                uses_compliance: true,
                uses_capital: true,
                uses_reconciliation: true,
                capital_status: 'attached',
                reconciliation_status: 'degraded',
              },
              source_refs: ['run-pathways-002:pipeline_guard', 'run-pathways-002:compliance_report', 'run-pathways-002:execution_readiness', 'run-pathways-002:execution_readiness#capital_ledger'],
              blockers: ['manual_review_required_for_execution', 'reconciliation_unavailable'],
              downgrade_reasons: ['manual_review_required_for_execution', 'reconciliation_unavailable'],
              summary: 'gate=execution_projection preflight=yes verdict=downgraded requested=live selected=shadow highest_safe=shadow recommended=shadow manual_review=yes ttl_ms=30000 eligible=2/3 counts=ready:1|degraded:1|blocked:1 basis=readiness,compliance,capital,reconciliation refs=4 blockers=2 downgrades=2',
            },
            projected_paths: {
              paper: { status: 'ready', effective_mode: 'paper' },
              shadow: {
                status: 'degraded',
                effective_mode: 'shadow',
                simulation: {
                  shadow_arbitrage: makeShadowArbitrageReport(),
                },
                trade_intent_preview: makeTradeIntentPreview({
                  sizeUsd: 50,
                }),
                canonical_trade_intent_preview: makeTradeIntentPreview({
                  sizeUsd: 40,
                }),
                sizing_signal: makeSizingSignal({
                  canonicalSizeUsd: 40,
                  previewSizeUsd: 50,
                  shadowRecommendedSizeUsd: 40,
                  source: 'trade_intent_preview+shadow_arbitrage',
                }),
                shadow_arbitrage_signal: makeShadowArbitrageSignal(),
              },
              live: { status: 'blocked', effective_mode: 'shadow' },
            },
            summary: 'requested live, selected shadow; gate execution_projection; preflight only. requested live, selected shadow, recommended shadow',
            microstructure_lab: {
              market_id: 'mkt-pathways-002',
              venue: 'polymarket',
              summary: {
                base_executable_edge_bps: 1800,
                worst_case_kind: 'spread_collapse',
                worst_case_severity: 'medium',
                worst_case_executable_edge_bps: 1779,
                executable_deterioration_bps: 21,
                execution_quality_score: 0.8125,
                recommended_mode: 'paper',
                event_counts: {
                  partial_fill: 1,
                  one_leg_fill: 1,
                  cancel_replace: 1,
                  queue_miss: 1,
                  hedge_delay: 1,
                  stale_book: 1,
                  spread_collapse: 1,
                },
              },
              projected_paths: {
                paper: { status: 'ready', effective_mode: 'paper' },
              shadow: {
                status: 'degraded',
                effective_mode: 'shadow',
                simulation: {
                  shadow_arbitrage: makeShadowArbitrageReport(),
                },
                trade_intent_preview: makeTradeIntentPreview({
                  sizeUsd: 50,
                }),
                sizing_signal: makeSizingSignal({
                  canonicalSizeUsd: 40,
                  previewSizeUsd: 50,
                  shadowRecommendedSizeUsd: 40,
                  source: 'trade_intent_preview+shadow_arbitrage',
                }),
                shadow_arbitrage_signal: makeShadowArbitrageSignal(),
              },
              live: { status: 'blocked', effective_mode: 'shadow' },
            },
            },
          },
          execution_projection_selected_preview: makeTradeIntentPreview({
            sizeUsd: 40,
          }),
          execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
          trade_intent_guard: makeTradeIntentGuard({
            selectedPath: 'shadow',
            preview: makeTradeIntentPreview({
              sizeUsd: 40,
            }),
          }),
        }))
        return
      }

      if (req.method === 'GET' && url.pathname === '/api/v1/prediction-markets/runs/run-pathways-003') {
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(JSON.stringify({
          run_id: 'run-pathways-003',
          workspace_id: 1,
          venue: 'polymarket',
          mode: 'advise',
          market_id: 'mkt-pathways-003',
          market_slug: 'mkt-pathways-003',
          status: 'completed',
          recommendation: 'bet',
          ...makeResearchHints(),
          research_runtime_summary:
            'research: mode=research_driven pipeline=polymarket-research-pipeline version=poly-025-research-v1 forecasters=2 weighted_yes=0.61 coverage=1 preferred=aggregate abstention=structured-abstention-v1 blocks_forecast=no forecast_hint=0.69',
          execution_pathways: {
            highest_actionable_mode: 'live',
            pathways: [
              { mode: 'paper', status: 'ready' },
              { mode: 'shadow', status: 'ready' },
              { mode: 'live', status: 'ready' },
            ],
            summary: 'live is currently the highest actionable execution pathway.',
          },
          execution_projection: {
            gate_name: 'execution_projection',
            preflight_only: true,
            requested_path: 'live',
            selected_path: 'live',
            verdict: 'allowed',
            manual_review_required: false,
            ttl_ms: 30000,
            highest_safe_requested_mode: 'live',
            recommended_effective_mode: 'live',
            modes: {
              paper: { requested_mode: 'paper', effective_mode: 'paper' },
              shadow: { requested_mode: 'shadow', effective_mode: 'shadow' },
              live: { requested_mode: 'live', effective_mode: 'live' },
            },
            basis: {
              uses_execution_readiness: true,
              uses_compliance: true,
              uses_capital: true,
              uses_reconciliation: true,
              capital_status: 'attached',
              reconciliation_status: 'attached',
              canonical_gate: makeCanonicalExecutionProjectionGate(),
            },
            projected_paths: {
              paper: { status: 'ready', effective_mode: 'paper' },
              shadow: { status: 'ready', effective_mode: 'shadow' },
              live: {
                status: 'ready',
                effective_mode: 'live',
                trade_intent_preview: makeTradeIntentPreview({
                  sizeUsd: 25,
                  maxUnhedgedLegMs: 250,
                }),
                canonical_trade_intent_preview: makeTradeIntentPreview({
                  sizeUsd: 25,
                  maxUnhedgedLegMs: 250,
                }),
                sizing_signal: makeSizingSignal({
                  canonicalSizeUsd: 25,
                  previewSizeUsd: 25,
                  maxUnhedgedLegMs: 250,
                  source: 'trade_intent_preview',
                }),
              },
            },
            preflight_summary: {
              gate_name: 'execution_projection',
              preflight_only: true,
              requested_path: 'live',
              selected_path: 'live',
              verdict: 'allowed',
              highest_safe_requested_mode: 'live',
              recommended_effective_mode: 'live',
              manual_review_required: false,
              ttl_ms: 30000,
              expires_at: '2026-04-08T00:00:30.000Z',
              counts: {
                total: 3,
                eligible: 3,
                ready: 3,
                degraded: 0,
                blocked: 0,
              },
              basis: {
                uses_execution_readiness: true,
                uses_compliance: true,
                uses_capital: true,
                uses_reconciliation: true,
                capital_status: 'attached',
                reconciliation_status: 'attached',
              },
              source_refs: [
                'run-pathways-003:pipeline_guard',
                'run-pathways-003:compliance_report',
                'run-pathways-003:execution_readiness',
                'run-pathways-003:pipeline_guard#venue_health',
                'run-pathways-003:execution_readiness#capital_ledger',
                'run-pathways-003:execution_readiness#reconciliation',
              ],
              blockers: [],
              downgrade_reasons: [],
              summary: 'gate=execution_projection preflight=yes verdict=allowed requested=live selected=live highest_safe=live recommended=live manual_review=no ttl_ms=30000 eligible=3/3 counts=ready:3|degraded:0|blocked:0 basis=readiness,compliance,capital,reconciliation refs=6 blockers=0 downgrades=0',
            },
            summary: 'Requested live; selected live; gate execution_projection; preflight only. Requested live, selected live, recommended live',
          },
          execution_projection_selected_preview: makeTradeIntentPreview({
            sizeUsd: 25,
            maxUnhedgedLegMs: 250,
          }),
          execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
          trade_intent_guard: makeTradeIntentGuard({
            selectedPath: 'live',
            preview: makeTradeIntentPreview({
              sizeUsd: 25,
              maxUnhedgedLegMs: 250,
            }),
          }),
          shadow_arbitrage: makeShadowArbitrageReport(),
        }))
        return
      }

      res.writeHead(404, { 'content-type': 'application/json' })
      res.end(JSON.stringify({ error: 'not_found' }))
    })

    await new Promise<void>((resolve) => {
      server.listen(0, '127.0.0.1', () => {
        const address = server.address()
        if (address && typeof address === 'object') {
          baseUrl = `http://127.0.0.1:${address.port}`
        }
        resolve()
      })
    })
  })

  afterAll(async () => {
    await new Promise<void>((resolve) => {
      server.close(() => resolve())
    })
  })

  it('prints a compact execution_pathways summary for run and runs in text mode', async () => {
    const runResult = await execFileAsync(
      'node',
      [
        CLI,
        'prediction-markets',
        'run',
        '--run-id',
        'run-pathways-001',
        '--execution-pathways-summary',
        '--url',
        baseUrl,
      ],
      {
        env: {
          ...process.env,
          MC_URL: baseUrl,
        },
        timeout: 10_000,
      },
    )

    expect(runResult.stdout).toContain(
      'execution_projection: requested=live selected=paper verdict=downgraded highest_safe=paper recommended=paper manual_review=yes gate=execution_projection preflight=yes ttl_ms=30000 modes=3 basis=readiness,compliance summary="requested live, selected paper; gate execution_projection; preflight only. requested live, selected paper, recommended paper"',
    )
    expect(runResult.stdout).toContain(
      'execution_projection preflight: gate=execution_projection verdict=downgraded requested=live selected=paper highest_safe=paper recommended=paper manual_review=yes ttl_ms=30000',
    )
    expect(runResult.stdout).toContain(
      'execution_projection preflight details: eligible=1/3 counts=ready:1|degraded:0|blocked:2 basis=readiness,compliance refs=3 blockers=3 downgrades=3',
    )
    expect(runResult.stdout).toContain(
      'execution_projection selected: mode=paper status=n/a effective=paper shadow_sim=no',
    )
    expect(runResult.stdout).not.toContain('execution_projection selected preview:')
    expect(runResult.stdout).not.toContain('execution_projection selected ops:')
    expect(runResult.stdout).toContain(
      'research: mode=research_driven pipeline=research-pipeline-runtime v=v3 forecasters=2 weighted=0.67 coverage=0.83 compare=aggregate abstention=structured-abstention-v1 blocks=no forecast=0.69 summary="Preferred mode: aggregate."',
    )
    expect(runResult.stdout).toContain('research_origin: origin=research_driven recommendation=wait abstention_effect=clear')
    expect(runResult.stdout).toContain(
      'benchmark: status=preview_only promotion=unproven ready=no uplift=1100bps blockers=out_of_sample_unproven reasons=out_of_sample_unproven',
    )
    expect(runResult.stdout).toContain(
      'benchmark_evidence: preview=yes promotion_evidence=unproven promotion_status=unproven ready=no out_of_sample=unproven',
    )
    expect(runResult.stdout).toContain(
      'execution_projection source: canonical gate=execution_projection recalc=no modes=paper|shadow|live',
    )

    const runsResult = await execFileAsync(
      'node',
      [
        CLI,
        'prediction-markets',
        'runs',
        '--execution-pathways-summary',
        '--url',
        baseUrl,
      ],
      {
        env: {
          ...process.env,
          MC_URL: baseUrl,
        },
        timeout: 10_000,
      },
    )

    expect(runsResult.stdout).toContain(
      'run run-pathways-001 | execution_pathways: highest_actionable_mode=paper count=2 entries=paper:ready | shadow:blocked',
    )
    expect(runsResult.stdout).toContain(
      'research: mode=research_driven pipeline=research-pipeline-runtime v=v3 forecasters=2 weighted=0.67 coverage=0.83 compare=aggregate abstention=structured-abstention-v1 blocks=no forecast=0.69 summary="Preferred mode: aggregate."',
    )
    expect(runsResult.stdout).toContain('research_origin: origin=research_driven recommendation=wait abstention_effect=clear')
    expect(runsResult.stdout).toContain(
      'benchmark: status=preview_only promotion=unproven ready=no uplift=1100bps blockers=out_of_sample_unproven reasons=out_of_sample_unproven',
    )
    expect(runsResult.stdout).toContain(
      'benchmark_evidence: preview=yes promotion_evidence=unproven promotion_status=unproven ready=no out_of_sample=unproven',
    )
    expect(runsResult.stdout).toContain(
      'run run-pathways-002 | execution_projection: requested=live selected=shadow verdict=downgraded highest_safe=shadow recommended=shadow manual_review=yes gate=execution_projection preflight=yes ttl_ms=30000 basis=readiness,compliance,capital,reconciliation projected_paths=paper:ready|shadow:degraded|live:blocked summary="requested live, selected shadow; gate execution_projection; preflight only. requested live, selected shadow, recommended shadow"',
    )
    expect(runsResult.stdout).toContain(
      'research: mode=research_driven pipeline=research-pipeline-runtime v=v3 forecasters=2 weighted=0.67 coverage=0.83 compare=aggregate abstention=structured-abstention-v1 blocks=no forecast=0.69 summary="Preferred mode: aggregate."',
    )
    expect(runsResult.stdout).toContain('research_origin: origin=research_driven recommendation=bet abstention_effect=clear')
    expect(runsResult.stdout).toContain(
      'benchmark: status=preview_only promotion=unproven ready=no uplift=1100bps blockers=out_of_sample_unproven reasons=out_of_sample_unproven',
    )
    expect(runsResult.stdout).toContain(
      '  execution_projection selected: mode=shadow status=degraded effective=shadow shadow_sim=yes',
    )
    expect(runsResult.stdout).toContain(
      '  execution_projection selected preview: size=40 via=runtime_hint source=canonical_trade_intent_preview limit=0.51 tif=ioc slip=50bps',
    )
    expect(runsResult.stdout).toContain(
      '  execution_projection selected ops: canonical_size=40 capped_from=50 source=trade_intent_preview+shadow_arbitrage tif=ioc shadow_signal=edge=1210|size=40|pnl=88bps|worst=hedge_delay',
    )
    expect(runsResult.stdout).toContain(
      '  execution_projection source: canonical gate=execution_projection recalc=no modes=paper|shadow|live',
    )
    expect(runsResult.stdout).toContain(
      '  microstructure_lab: market=mkt-pathways-002 venue=polymarket base_edge=1800 worst=spread_collapse:medium:1779 deterioration=21 recommended=paper quality=0.8125 events=partial_fill:1|one_leg_fill:1|cancel_replace:1|queue_miss:1',
    )
    expect(runsResult.stdout).toContain(
      '  shadow_arbitrage: market=shadow-arb-poly venue=polymarket base_edge=1375 shadow_edge=1210 hedge_success=0.72 net_pnl=88bps/0.88usd size=40 penalized_from=100 x=0.40 worst=hedge_delay failure_cases=3',
    )
    expect(runsResult.stdout).toContain(
      'run run-pathways-003 | execution_projection: requested=live selected=paper verdict=downgraded highest_safe=paper recommended=paper manual_review=yes gate=execution_projection preflight=yes ttl_ms=30000 basis=readiness,compliance capital=unavailable reconciliation=unavailable projected_paths=paper:ready summary="requested live, selected paper; gate execution_projection; preflight only. requested live, selected paper, recommended paper"',
    )
    expect(runsResult.stdout).toContain(
      'research: mode=research_driven pipeline=research-pipeline-runtime v=v3 forecasters=2 weighted=0.67 coverage=0.83 compare=aggregate abstention=structured-abstention-v1 blocks=no forecast=0.69 summary="Preferred mode: aggregate."',
    )
    expect(runsResult.stdout).toContain(
      '  execution_projection selected: mode=paper status=ready effective=paper shadow_sim=no',
    )
    expect(runsResult.stdout).toContain(
      '  execution_projection selected preview: size=35 via=runtime_hint source=canonical_trade_intent_preview limit=0.48 tif=day slip=30bps',
    )
    expect(runsResult.stdout).toContain(
      '  execution_projection selected ops: canonical_size=35 source=trade_intent_preview tif=day',
    )
    expect(runsResult.stdout).toContain(
      '  execution_projection preflight: gate=execution_projection verdict=downgraded requested=live selected=paper highest_safe=paper recommended=paper manual_review=yes ttl_ms=30000',
    )
  })

  it('prints benchmark summaries on run and runs without requiring the full execution summary', async () => {
    const runResult = await execFileAsync(
      'node',
      [
        CLI,
        'prediction-markets',
        'run',
        '--run-id',
        'run-pathways-002',
        '--benchmark-summary',
        '--url',
        baseUrl,
      ],
      {
        env: {
          ...process.env,
          MC_URL: baseUrl,
        },
        timeout: 10_000,
      },
    )

    expect(runResult.stdout).toContain(
      'benchmark: status=preview_only promotion=unproven ready=no uplift=1100bps blockers=out_of_sample_unproven reasons=out_of_sample_unproven',
    )
    expect(runResult.stdout).toContain(
      'benchmark_evidence: preview=yes promotion_evidence=unproven promotion_status=unproven ready=no out_of_sample=unproven',
    )
    expect(runResult.stdout).toContain(
      'benchmark_state: verdict=preview_only promotion_gate_kind=preview_only ready=no evidence_level=benchmark_preview promotion_blocker_summary=out_of_sample_unproven',
    )
    expect(runResult.stdout).not.toContain('research:')

    const runsResult = await execFileAsync(
      'node',
      [
        CLI,
        'prediction-markets',
        'runs',
        '--benchmark-summary',
        '--url',
        baseUrl,
      ],
      {
        env: {
          ...process.env,
          MC_URL: baseUrl,
        },
        timeout: 10_000,
      },
    )

    const benchmarkLines = runsResult.stdout
      .split('\n')
      .filter((line) => line.startsWith('benchmark: '))
    expect(benchmarkLines).toHaveLength(3)
    expect(runsResult.stdout).toContain(
      'benchmark: status=preview_only promotion=unproven ready=no uplift=1100bps blockers=out_of_sample_unproven reasons=out_of_sample_unproven',
    )
    expect(runsResult.stdout).toContain(
      'benchmark_evidence: preview=yes promotion_evidence=unproven promotion_status=unproven ready=no out_of_sample=unproven',
    )
    expect(runsResult.stdout).not.toContain('research:')
  })

  it('includes new execution_projection production signals when they exist', async () => {
    const runResult = await execFileAsync(
      'node',
      [
        CLI,
        'prediction-markets',
        'run',
        '--run-id',
        'run-pathways-002',
        '--execution-pathways-summary',
        '--url',
        baseUrl,
      ],
      {
        env: {
          ...process.env,
          MC_URL: baseUrl,
        },
        timeout: 10_000,
      },
    )

    expect(runResult.stdout).toContain(
      'execution_projection: requested=live selected=shadow verdict=downgraded highest_safe=shadow recommended=shadow manual_review=yes gate=execution_projection preflight=yes ttl_ms=30000 modes=3 basis=readiness,compliance,capital,reconciliation capital=attached reconciliation=degraded projected_paths=paper:ready|shadow:degraded|live:blocked summary="requested live, selected shadow; gate execution_projection; preflight only. requested live, selected shadow, recommended shadow"',
    )
    expect(runResult.stdout).toContain(
      'execution_projection preflight: gate=execution_projection verdict=downgraded requested=live selected=shadow highest_safe=shadow recommended=shadow manual_review=yes ttl_ms=30000',
    )
    expect(runResult.stdout).toContain(
      'execution_projection preflight details: eligible=2/3 counts=ready:1|degraded:1|blocked:1 basis=readiness,compliance,capital,reconciliation refs=4 blockers=2 downgrades=2',
    )
    expect(runResult.stdout).toContain(
      'execution_projection selected: mode=shadow status=degraded effective=shadow shadow_sim=yes',
    )
    expect(runResult.stdout).toContain(
      'execution_projection selected preview: size=40 via=runtime_hint source=canonical_trade_intent_preview limit=0.51 tif=ioc slip=50bps',
    )
    expect(runResult.stdout).toContain(
      'execution_projection selected ops: canonical_size=40 capped_from=50 source=trade_intent_preview+shadow_arbitrage tif=ioc shadow_signal=edge=1210|size=40|pnl=88bps|worst=hedge_delay',
    )
    expect(runResult.stdout).toContain(
      'research: mode=research_driven pipeline=research-pipeline-runtime v=v3 forecasters=2 weighted=0.67 coverage=0.83 compare=aggregate abstention=structured-abstention-v1 blocks=no forecast=0.69 summary="Preferred mode: aggregate."',
    )
    expect(runResult.stdout).toContain(
      'benchmark: status=preview_only promotion=unproven ready=no uplift=1100bps blockers=out_of_sample_unproven reasons=out_of_sample_unproven',
    )
    expect(runResult.stdout).toContain(
      'execution_projection source: canonical gate=execution_projection recalc=no modes=paper|shadow|live',
    )
    expect(runResult.stdout).toContain(
      'microstructure_lab: market=mkt-pathways-002 venue=polymarket base_edge=1800 worst=spread_collapse:medium:1779 deterioration=21 recommended=paper quality=0.8125 events=partial_fill:1|one_leg_fill:1|cancel_replace:1|queue_miss:1',
    )
    expect(runResult.stdout).toContain(
      'shadow_arbitrage: market=shadow-arb-poly venue=polymarket base_edge=1375 shadow_edge=1210 hedge_success=0.72 net_pnl=88bps/0.88usd size=40 penalized_from=100 x=0.40 worst=hedge_delay failure_cases=3',
    )
  })

  it('surfaces a live-ready execution projection with a compact preflight summary', async () => {
    const runResult = await execFileAsync(
      'node',
      [
        CLI,
        'prediction-markets',
        'run',
        '--run-id',
        'run-pathways-003',
        '--execution-pathways-summary',
        '--url',
        baseUrl,
      ],
      {
        env: {
          ...process.env,
          MC_URL: baseUrl,
        },
        timeout: 10_000,
      },
    )

    expect(runResult.stdout).toContain(
      'execution_pathways: highest_actionable_mode=live count=3 entries=paper:ready | shadow:ready | live:ready',
    )
    expect(runResult.stdout).toContain(
      'execution_projection: requested=live selected=live verdict=allowed highest_safe=live recommended=live manual_review=no gate=execution_projection preflight=yes ttl_ms=30000',
    )
    expect(runResult.stdout).toContain(
      'basis=readiness,compliance,capital,reconciliation capital=attached reconciliation=attached',
    )
    expect(runResult.stdout).toContain(
      'projected_paths=paper:ready|shadow:ready|live:ready',
    )
    expect(runResult.stdout).toContain(
      'summary="Requested live; selected live; gate execution_projection; preflight only. Requested live, selected live, recommended live"',
    )
    expect(runResult.stdout).toContain(
      'research: mode=research_driven pipeline=research-pipeline-runtime v=v3 forecasters=2 weighted=0.67 coverage=0.83 compare=aggregate abstention=structured-abstention-v1 blocks=no forecast=0.69 summary="Preferred mode: aggregate."',
    )
    expect(runResult.stdout).toContain(
      'execution_projection preflight: gate=execution_projection verdict=allowed requested=live selected=live highest_safe=live recommended=live manual_review=no ttl_ms=30000',
    )
    expect(runResult.stdout).toContain(
      'execution_projection preflight details: eligible=3/3 counts=ready:3|degraded:0|blocked:0 basis=readiness,compliance,capital,reconciliation refs=6 blockers=0 downgrades=0',
    )
    expect(runResult.stdout).toContain(
      'execution_projection selected: mode=live status=ready effective=live shadow_sim=no',
    )
    expect(runResult.stdout).toContain(
      'execution_projection selected preview: size=25 via=runtime_hint source=canonical_trade_intent_preview limit=0.51 tif=ioc slip=50bps',
    )
    expect(runResult.stdout).toContain(
      'execution_projection selected ops: canonical_size=25 source=trade_intent_preview tif=ioc',
    )
    expect(runResult.stdout).toContain(
      'execution_projection source: canonical gate=execution_projection recalc=no modes=paper|shadow|live',
    )
    expect(runResult.stdout).toContain(
      'shadow_arbitrage: market=shadow-arb-poly venue=polymarket base_edge=1375 shadow_edge=1210 hedge_success=0.72 net_pnl=88bps/0.88usd size=40 penalized_from=100 x=0.40 worst=hedge_delay failure_cases=3',
    )
  })
})
