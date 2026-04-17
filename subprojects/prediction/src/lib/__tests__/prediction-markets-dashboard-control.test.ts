import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getPredictionMarketRunDetails: vi.fn(),
  preparePredictionMarketRunLive: vi.fn(),
}))

vi.mock('@/lib/prediction-markets/service', () => ({
  getPredictionMarketRunDetails: mocks.getPredictionMarketRunDetails,
  preparePredictionMarketRunLive: mocks.preparePredictionMarketRunLive,
}))

import {
  approveDashboardLiveIntent,
  createDashboardLiveIntent,
  getDashboardEvents,
  getDashboardLiveIntent,
  rejectDashboardLiveIntent,
} from '@/lib/prediction-markets/dashboard-control'

function makeRunDetail() {
  return {
    run_id: 'run-dashboard-1',
    workspace_id: 9,
    venue: 'polymarket',
    benchmark_promotion_ready: true,
    benchmark_promotion_gate_kind: 'local_benchmark',
    benchmark_evidence_level: 'out_of_sample_promotion_evidence',
    benchmark_promotion_status: 'eligible',
    benchmark_gate_blockers: [],
    benchmark_gate_reasons: [],
    benchmark_promotion_summary: 'benchmark promotion ready',
    benchmark_promotion_blocker_summary: 'benchmark promotion ready',
    benchmark_gate_blocks_live: false,
    benchmark_gate_live_block_reason: null,
    research_runtime_mode: 'research_driven',
    research_recommendation_origin: 'research_driven',
    research_pipeline_id: 'pipeline-dashboard',
    research_pipeline_version: 'v1',
    research_compare_preferred_mode: 'aggregate',
    research_weighted_probability_yes: 0.58,
    research_weighted_coverage: 0.88,
    research_abstention_policy_blocks_forecast: false,
    execution_projection_selected_path: 'live',
    execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
    execution_projection_selected_preview: { size_usd: 25 },
    execution_projection_summary: 'ready',
    execution_projection_requested_path: 'live',
    execution_projection_selected_path_status: 'ready',
    execution_projection_selected_path_effective_mode: 'live',
    execution_projection_recommended_effective_mode: 'live',
    execution_projection_capital_status: 'attached',
    execution_projection_reconciliation_status: 'attached',
    execution_projection_blocking_reasons: [],
    execution_projection_downgrade_reasons: [],
    trade_intent_guard: null,
    paper_surface: null,
    shadow_arbitrage: null,
    live_path: { path: 'live', status: 'ready', effective_mode: 'live' },
    live_trade_intent_preview: { size_usd: 25, limit_price: 0.58, time_in_force: 'ioc' },
    live_trade_intent_preview_source: 'canonical_trade_intent_preview',
    benchmark_gate_summary: 'benchmark gate: ready',
  }
}

function makeLivePlan() {
  return {
    gate_name: 'execution_projection_live',
    preflight_only: true,
    run_id: 'run-dashboard-1',
    workspace_id: 9,
    surface_mode: 'live',
    live_route_allowed: true,
    live_status: 'ready',
    live_blocking_reasons: [],
    summary: 'live ready',
    source_refs: {
      run_detail: 'run-dashboard-1',
      execution_projection: 'run-dashboard-1:execution_projection',
      live_projected_path: 'run-dashboard-1:execution_projection#live',
      trade_intent_guard: 'run-dashboard-1:trade_intent_guard',
      multi_venue_execution: 'run-dashboard-1:multi_venue_execution',
    },
    execution_readiness: null,
    execution_pathways: null,
    execution_projection: {
      selected_path: 'live',
      selected_preview: { size_usd: 25 },
    },
    shadow_arbitrage: null,
    trade_intent_guard: null,
    multi_venue_execution: null,
    venue_feed_surface: {
      venue: 'polymarket',
      backend_mode: 'read_only',
      market_feed_status: 'local_cache',
      user_feed_status: 'local_cache',
      rtds_status: 'unavailable',
    },
    live_path: { path: 'live', status: 'ready', effective_mode: 'live' },
    live_trade_intent_preview: { size_usd: 25, limit_price: 0.58, time_in_force: 'ioc' },
    live_trade_intent_preview_source: 'canonical_trade_intent_preview',
    benchmark_surface_blocking_reasons: [],
    benchmark_promotion_blockers: [],
    benchmark_promotion_ready: true,
    paper_surface: null,
    replay_surface: null,
    paper_no_trade_zone_count: 0,
    paper_no_trade_zone_rate: 0,
    replay_no_trade_leg_count: 0,
    replay_no_trade_leg_rate: 0,
  }
}

describe('prediction markets dashboard live intent control', () => {
  beforeEach(() => {
    mocks.getPredictionMarketRunDetails.mockReset()
    mocks.preparePredictionMarketRunLive.mockReset()
    mocks.getPredictionMarketRunDetails.mockReturnValue(makeRunDetail())
    mocks.preparePredictionMarketRunLive.mockReturnValue(makeLivePlan())
  })

  it('creates, approves, and retrieves a live intent with distinct actors', () => {
    const created = createDashboardLiveIntent({
      runId: 'run-dashboard-1',
      workspaceId: 9,
      actor: 'creator-a',
      note: 'please approve',
    })

    expect(created.intent_id).toContain('live-intent-')
    expect(created.approval_state.status).toBe('pending')
    expect(created.approval_state.requested_by).toBe('creator-a')
    expect(created.approval_state.current).toBe(0)
    expect(created.audit.at(0)).toMatchObject({
      actor: 'creator-a',
      action: 'created',
    })

    expect(() =>
      approveDashboardLiveIntent({
        intentId: created.intent_id,
        workspaceId: 9,
        actor: 'creator-a',
      }),
    ).toThrowError(/distinct second approver/)

    const approved = approveDashboardLiveIntent({
      intentId: created.intent_id,
      workspaceId: 9,
      actor: 'approver-b',
      note: 'approved',
    })

    expect(approved.approval_state.status).toBe('approved')
    expect(approved.approval_state.current).toBe(1)
    expect(approved.approval_state.approvers).toEqual(['approver-b'])
    expect(approved.execution_state.status).toBe('prepared')
    expect(approved.execution_state.receipt).toEqual(expect.objectContaining({
      live_status: 'ready',
      live_route_allowed: true,
    }))

    const fetched = getDashboardLiveIntent(created.intent_id, 9)
    expect(fetched).toMatchObject({
      intent_id: created.intent_id,
      approval_state: {
        status: 'approved',
        approvers: ['approver-b'],
      },
    })

    expect(getDashboardEvents()).toEqual(expect.arrayContaining([
      expect.objectContaining({
        event_type: 'live_intent_created',
      }),
      expect.objectContaining({
        event_type: 'live_intent_approved',
      }),
    ]))
  })

  it('rejects a live intent and keeps it rejected', () => {
    const created = createDashboardLiveIntent({
      runId: 'run-dashboard-1',
      workspaceId: 9,
      actor: 'creator-a',
    })

    const rejected = rejectDashboardLiveIntent({
      intentId: created.intent_id,
      workspaceId: 9,
      actor: 'approver-b',
      note: 'not ready',
    })

    expect(rejected.approval_state.status).toBe('rejected')
    expect(rejected.approval_state.rejected_at).not.toBeNull()
    expect(rejected.audit.some((entry) => entry.action === 'rejected')).toBe(true)
  })
})
