import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getPredictionMarketRunDetails: vi.fn(),
  listDashboardLiveIntents: vi.fn(() => []),
}))

vi.mock('@/lib/prediction-markets/service', () => ({
  getPredictionMarketRunDetails: mocks.getPredictionMarketRunDetails,
}))

vi.mock('@/lib/prediction-markets/dashboard-live-intents', () => ({
  listDashboardLiveIntents: mocks.listDashboardLiveIntents,
}))

import {
  buildPredictionDashboardRunDetail,
  buildPredictionDashboardVenueSnapshot,
} from '@/lib/prediction-markets/dashboard-models'

function makeLiveBlockedRunDetail() {
  return {
    run_id: 'run-service-compat-live-blocked',
    workspace_id: 9,
    venue: 'polymarket',
    market_id: 'service-compat-market',
    benchmark_promotion_ready: false,
    benchmark_promotion_status: 'preview_only',
    benchmark_promotion_gate_kind: 'preview_only',
    benchmark_evidence_level: 'out_of_sample_promotion_evidence',
    benchmark_promotion_summary: 'benchmark promotion remains blocked',
    benchmark_promotion_blocker_summary: 'benchmark promotion remains blocked',
    benchmark_gate_blockers: [],
    benchmark_gate_reasons: [],
    benchmark_gate_live_block_reason: 'out_of_sample_unproven',
    benchmark_gate_blocks_live: true,
    research_runtime_mode: 'research_driven',
    research_recommendation_origin: 'research_driven',
    research_pipeline_id: 'pipeline-service-compat',
    research_pipeline_version: 'v1',
    research_compare_preferred_mode: 'aggregate',
    research_weighted_probability_yes: 0.58,
    research_weighted_coverage: 0.88,
    research_abstention_policy_blocks_forecast: false,
    execution_projection_selected_path: 'live',
    execution_projection_selected_path_status: 'ready',
    execution_projection_selected_path_effective_mode: 'live',
    execution_projection_recommended_effective_mode: 'live',
    execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
    execution_projection_selected_preview: {
      size_usd: 25,
      limit_price: 0.58,
      time_in_force: 'ioc',
    },
    execution_projection_requested_path: 'live',
    execution_projection_summary: 'live path is ready but not promotable',
    execution_projection_capital_status: 'attached',
    execution_projection_reconciliation_status: 'attached',
    execution_projection_blocking_reasons: [],
    execution_projection_downgrade_reasons: [],
    trade_intent_guard: null,
    paper_surface: null,
    shadow_arbitrage: null,
    live_path: {
      path: 'live',
      status: 'ready',
      effective_mode: 'live',
    },
    live_trade_intent_preview: {
      size_usd: 25,
      limit_price: 0.58,
      time_in_force: 'ioc',
    },
    live_trade_intent_preview_source: 'canonical_trade_intent_preview',
    benchmark_gate_summary: 'benchmark gate summary',
  }
}

function makeLegacyRunDetail() {
  return {
    run_id: 'run-service-compat-legacy',
    workspace_id: 9,
    venue: 'kalshi',
    market_id: 'service-compat-legacy-market',
    benchmark_promotion_ready: true,
    benchmark_promotion_status: 'eligible',
    benchmark_promotion_gate_kind: null,
    benchmark_evidence_level: null,
    benchmark_promotion_summary: null,
    benchmark_promotion_blocker_summary: null,
    benchmark_gate_blockers: [],
    benchmark_gate_reasons: [],
    benchmark_gate_live_block_reason: null,
    benchmark_gate_blocks_live: false,
    research_runtime_mode: null,
    research_recommendation_origin: null,
    research_pipeline_id: null,
    research_pipeline_version: null,
    research_compare_preferred_mode: null,
    research_weighted_probability_yes: null,
    research_weighted_coverage: null,
    research_abstention_policy_blocks_forecast: null,
    execution_projection_selected_path: 'paper',
    execution_projection_selected_path_status: 'ready',
    execution_projection_selected_path_effective_mode: 'paper',
    execution_projection_recommended_effective_mode: 'paper',
    execution_projection_selected_preview_source: null,
    execution_projection_selected_preview: null,
    execution_projection_requested_path: 'paper',
    execution_projection_summary: 'legacy detail',
    execution_projection_capital_status: null,
    execution_projection_reconciliation_status: null,
    execution_projection_blocking_reasons: [],
    execution_projection_downgrade_reasons: [],
    trade_intent_guard: null,
    paper_surface: null,
    shadow_arbitrage: null,
    live_path: null,
    live_trade_intent_preview: null,
    live_trade_intent_preview_source: null,
    benchmark_gate_summary: 'legacy detail',
  }
}

describe('prediction markets strategy service compatibility', () => {
  beforeEach(() => {
    mocks.getPredictionMarketRunDetails.mockReset()
    mocks.listDashboardLiveIntents.mockReset()
    mocks.listDashboardLiveIntents.mockReturnValue([])
  })

  it('keeps maker quote previews on the advisory side when live promotion is blocked', () => {
    mocks.getPredictionMarketRunDetails.mockReturnValue(makeLiveBlockedRunDetail())

    const detail = buildPredictionDashboardRunDetail(9, 'run-service-compat-live-blocked')

    expect(detail).not.toBeNull()
    expect(detail?.execution.live_promotable).toBe(false)
    expect(detail?.execution.selected_preview).toMatchObject({
      size_usd: 25,
      limit_price: 0.58,
      time_in_force: 'ioc',
    })
    expect(detail?.benchmark.live_block_reason).toBe('out_of_sample_unproven')
    expect(detail?.alerts.map((alert) => alert.code)).toContain('live_blocked_by_benchmark')
  })

  it('still renders dashboard details when stored run data omits strategy fields', () => {
    mocks.getPredictionMarketRunDetails.mockReturnValue(makeLegacyRunDetail())

    const detail = buildPredictionDashboardRunDetail(9, 'run-service-compat-legacy')

    expect(detail).not.toBeNull()
    expect(detail?.run).not.toHaveProperty('strategy')
    expect(buildPredictionDashboardVenueSnapshot('kalshi').strategy).toMatchObject({
      venue: 'kalshi',
      source_of_truth: 'official_docs',
      execution_eligible: true,
    })
    expect(detail?.execution.selected_path).toBe('paper')
    expect(detail?.execution.live_promotable).toBe(false)
  })
})
