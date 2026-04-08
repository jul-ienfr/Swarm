import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getPredictionMarketRunDetails: vi.fn(),
  listPredictionMarketRuns: vi.fn(),
  getVenueCapabilitiesContract: vi.fn(),
  getVenueFeedSurfaceContract: vi.fn(),
  getVenueHealthSnapshotContract: vi.fn(),
  getVenueStrategyContract: vi.fn(),
  getVenueBudgetsContract: vi.fn(),
  listDashboardLiveIntents: vi.fn(),
  listRecentPredictionDashboardEvents: vi.fn(),
  getPredictionDashboardArbitrageSnapshot: vi.fn(),
}))

vi.mock('@/lib/prediction-markets/service', () => ({
  getPredictionMarketRunDetails: mocks.getPredictionMarketRunDetails,
  listPredictionMarketRuns: mocks.listPredictionMarketRuns,
}))

vi.mock('@/lib/prediction-markets/venue-ops', () => ({
  getVenueCapabilitiesContract: mocks.getVenueCapabilitiesContract,
  getVenueFeedSurfaceContract: mocks.getVenueFeedSurfaceContract,
  getVenueHealthSnapshotContract: mocks.getVenueHealthSnapshotContract,
  getVenueStrategyContract: mocks.getVenueStrategyContract,
  getVenueBudgetsContract: mocks.getVenueBudgetsContract,
  listPredictionMarketVenues: vi.fn(() => ['polymarket', 'kalshi']),
}))

vi.mock('@/lib/prediction-markets/dashboard-live-intents', () => ({
  getDashboardLiveIntent: vi.fn(),
  listDashboardLiveIntents: mocks.listDashboardLiveIntents,
}))

vi.mock('@/lib/prediction-markets/dashboard-events', () => ({
  listRecentPredictionDashboardEvents: mocks.listRecentPredictionDashboardEvents,
}))

vi.mock('@/lib/prediction-markets/arbitrage-scanner', () => ({
  getPredictionDashboardArbitrageSnapshot: mocks.getPredictionDashboardArbitrageSnapshot,
}))

function makeRunFixture(overrides: Record<string, unknown> = {}) {
  return {
    run_id: 'run-1',
    source_run_id: null,
    workspace_id: 7,
    venue: 'polymarket',
    mode: 'advise',
    market_id: 'mkt-1',
    market_slug: 'market-1',
    status: 'completed',
    recommendation: 'bet',
    side: 'yes',
    confidence: 0.82,
    probability_yes: 0.74,
    market_price_yes: 0.51,
    edge_bps: 2300,
    created_at: 1712534400,
    updated_at: 1712534460,
    benchmark_promotion_ready: true,
    benchmark_promotion_status: 'eligible',
    benchmark_promotion_gate_kind: 'local_benchmark',
    benchmark_evidence_level: 'out_of_sample_promotion_evidence',
    benchmark_promotion_blocker_summary: 'canonical blocker',
    benchmark_gate_blockers: ['canonical:blocker'],
    benchmark_gate_reasons: ['canonical:reason'],
    benchmark_gate_blocks_live: false,
    benchmark_gate_live_block_reason: null,
    research_benchmark_promotion_ready: false,
    research_benchmark_promotion_status: 'blocked',
    research_promotion_gate_kind: 'preview_only',
    research_benchmark_evidence_level: 'benchmark_preview',
    research_benchmark_promotion_blocker_summary: 'research blocker',
    research_benchmark_gate_blockers: ['research:blocker'],
    research_benchmark_gate_reasons: ['research:reason'],
    research_benchmark_live_block_reason: 'research live block',
    research_runtime_mode: 'research_driven',
    research_recommendation_origin: 'research_driven',
    research_recommendation_origin_summary: 'Research-driven with canonical benchmark override.',
    research_pipeline_id: 'pipeline-1',
    research_pipeline_version: 'v1',
    research_compare_preferred_mode: 'aggregate',
    research_weighted_probability_yes: 0.73,
    research_weighted_coverage: 0.89,
    research_abstention_policy_version: 'abstention-v1',
    research_abstention_policy_blocks_forecast: false,
    research_forecast_probability_yes_hint: 0.74,
    execution_projection_gate_name: 'execution_projection',
    execution_projection_preflight_only: true,
    execution_projection_requested_path: 'live',
    execution_projection_selected_path: 'live',
    execution_projection_selected_path_status: 'ready',
    execution_projection_selected_path_effective_mode: 'live',
    execution_projection_selected_path_reason_summary: 'selected live path is ready.',
    execution_projection_highest_safe_requested_mode: 'live',
    execution_projection_recommended_effective_mode: 'live',
    execution_projection_verdict: 'allowed',
    execution_projection_manual_review_required: false,
    execution_projection_ttl_ms: 30000,
    execution_projection_expires_at: '2026-04-08T00:00:30.000Z',
    execution_projection_blocking_reasons: [],
    execution_projection_downgrade_reasons: [],
    execution_projection_selected_preview: {
      size_usd: 75,
      limit_price: 0.51,
      time_in_force: 'ioc',
      max_slippage_bps: 50,
    },
    execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
    execution_projection_selected_path_canonical_size_usd: 75,
    execution_pathways_highest_actionable_mode: 'live',
    execution_projection_summary: 'Requested live; selected live.',
    execution_projection_preflight_summary: {
      summary: 'Requested live; selected live.',
    },
    execution_projection_capital_status: 'attached',
    execution_projection_reconciliation_status: 'available',
    trade_intent_guard: {
      selected_path: 'live',
      verdict: 'allowed',
      blocked_reasons: [],
    },
    multi_venue_execution: {
      selected_path: 'live',
    },
    paper_surface: { surface: 'paper' },
    replay_surface: { surface: 'replay' },
    market_events: { kind: 'events' },
    market_positions: { kind: 'positions' },
    venue_feed_surface: { market_feed_status: 'local_cache', user_feed_status: 'local_cache' },
    microstructure_lab: { kind: 'microstructure' },
    order_trace_audit: { kind: 'order-trace' },
    market_graph: { kind: 'graph' },
    artifact_refs: [],
    artifact_readback: { run_id: 'run-1' },
    artifact_audit: { manifest_ref_count: 1, observed_ref_count: 1, canonical_ref_count: 1 },
    manifest: { run_id: 'run-1' },
    packet_bundle: { bundle_id: 'bundle-1' },
    research_bridge: { bridge: true },
    research_sidecar: {
      synthesis: {},
    },
    shadow_arbitrage: {
      summary: {
        base_executable_edge_bps: 120,
      },
    },
    ...overrides,
  }
}

beforeEach(() => {
  vi.resetModules()
  mocks.getPredictionMarketRunDetails.mockReset()
  mocks.listPredictionMarketRuns.mockReset()
  mocks.getVenueCapabilitiesContract.mockReset()
  mocks.getVenueFeedSurfaceContract.mockReset()
  mocks.getVenueHealthSnapshotContract.mockReset()
  mocks.getVenueStrategyContract.mockReset()
  mocks.getVenueBudgetsContract.mockReset()
  mocks.listDashboardLiveIntents.mockReset()
  mocks.listRecentPredictionDashboardEvents.mockReset()
  mocks.getPredictionDashboardArbitrageSnapshot.mockReset()

  mocks.getPredictionMarketRunDetails.mockImplementation((runId: string) =>
    runId === 'run-1' ? makeRunFixture() : null,
  )
  mocks.listPredictionMarketRuns.mockReturnValue([makeRunFixture()])
  mocks.getVenueCapabilitiesContract.mockReturnValue({
    venue: 'polymarket',
    supports_execution: false,
    supports_orderbook: true,
    supports_trades: true,
    supported_order_types: ['limit'],
    automation_constraints: ['read-only advisory mode only'],
  })
  mocks.getVenueFeedSurfaceContract.mockReturnValue({
    venue: 'polymarket',
    backend_mode: 'read_only',
    market_feed_status: 'local_cache',
    user_feed_status: 'local_cache',
    summary: 'Read-only feed surface.',
  })
  mocks.getVenueHealthSnapshotContract.mockReturnValue({
    venue: 'polymarket',
    api_status: 'ok',
    stream_status: 'unknown',
    staleness_ms: 0,
    degraded_mode: 'normal',
    incident_flags: [],
    notes: 'healthy',
  })
  mocks.getVenueStrategyContract.mockReturnValue({
    source_of_truth: 'polymarket',
    execution_eligible: false,
    source_hierarchy: [],
    community_reference: {
      source: 'community',
      priority: 2,
    },
  })
  mocks.getVenueBudgetsContract.mockReturnValue({
    fetch_latency_budget_ms: 100,
    snapshot_freshness_ms: 100,
    decision_latency_ms: 100,
    stream_reconnect_ms: 200,
    cache_ttl_ms: 100,
    max_retries: 0,
    backpressure_policy: 'degrade-to-wait',
  })
  mocks.listDashboardLiveIntents.mockReturnValue([])
  mocks.listRecentPredictionDashboardEvents.mockReturnValue([])
  mocks.getPredictionDashboardArbitrageSnapshot.mockResolvedValue({
    generated_at: '2026-04-08T00:00:00.000Z',
    freshness: 'fresh',
    transport: 'polling',
    workspace_id: 7,
    venue_pair: ['polymarket', 'kalshi'],
    filters: {
      limit_per_venue: 16,
      max_pairs: 40,
      min_arbitrage_spread_bps: 25,
      shadow_candidates: 8,
    },
    overview: {
      pairs_compared: 1,
      compatible_pairs: 1,
      candidate_count: 1,
      manual_review_count: 0,
      comparison_only_count: 0,
      best_shadow_edge_bps: 92,
      best_net_spread_bps: 104,
      best_executable_edge_bps: 88,
      best_candidate_id: 'arb:btc:polymarket-kalshi',
      summary: 'Cross-venue arbitrage scan found 1 candidate.',
      errors: [],
    },
    candidates: [
      {
        candidate_id: 'arb:btc:polymarket-kalshi',
        canonical_event_id: 'btc',
        canonical_event_key: 'btc',
        opportunity_type: 'true_arbitrage',
        buy_venue: 'polymarket',
        sell_venue: 'kalshi',
        buy_market_id: 'btc-buy',
        sell_market_id: 'btc-sell',
        buy_question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
        sell_question: 'Will Bitcoin be above 100000 on 2026-12-31?',
        buy_price_yes: 0.43,
        sell_price_yes: 0.54,
        gross_spread_bps: 1100,
        net_spread_bps: 92,
        executable_edge_bps: 88,
        confidence_score: 0.93,
        manual_review_required: false,
        shadow_ready: true,
        shadow_edge_bps: 92,
        shadow_recommended_size_usd: 500,
        shadow_hedge_success_probability: 0.94,
        shadow_estimated_net_pnl_bps: 76,
        shadow_estimated_net_pnl_usd: 38,
        freshness_ms: 12_000,
        blocking_reasons: [],
        notes: [],
      },
    ],
  })
})

describe('prediction markets dashboard models', () => {
  it('prefers canonical benchmark fields over research fallbacks', async () => {
    const {
      buildPredictionDashboardBenchmarkSnapshot,
      buildPredictionDashboardRunDetail,
      buildPredictionDashboardRunList,
    } = await import('@/lib/prediction-markets/dashboard-models')

    const runList = buildPredictionDashboardRunList(7, 'polymarket', 10)
    const runDetail = buildPredictionDashboardRunDetail(7, 'run-1')
    const benchmark = buildPredictionDashboardBenchmarkSnapshot(7, 'polymarket', 'run-1')

    expect(runList.items[0]?.benchmark_state).toBe('eligible')
    expect(runList.items[0]?.benchmark_ready).toBe(true)
    expect(runList.items[0]?.selected_path).toBe('live')
    expect(runDetail?.benchmark.ready).toBe(true)
    expect(runDetail?.benchmark.status).toBe('eligible')
    expect(runDetail?.benchmark.gate_kind).toBe('local_benchmark')
    expect(runDetail?.benchmark.evidence_level).toBe('out_of_sample_promotion_evidence')
    expect(runDetail?.benchmark.summary).toContain('canonical blocker')
    expect(runDetail?.execution.live_promotable).toBe(true)
    expect(benchmark.comparison.benchmark_gate_blocks_live).toBe(false)
    expect(benchmark.comparison.benchmark_gate_live_block_reason).toBeNull()
  })

  it('builds overview and venue snapshots with stable polling payloads', async () => {
    const { buildPredictionDashboardArbitrageSnapshot, buildPredictionDashboardOverview, buildPredictionDashboardVenueSnapshot } = await import('@/lib/prediction-markets/dashboard-models')

    const overview = buildPredictionDashboardOverview(7, 'polymarket', 10)
    const venue = buildPredictionDashboardVenueSnapshot('polymarket')
    const arbitrage = await buildPredictionDashboardArbitrageSnapshot(7, ['polymarket', 'kalshi'], 16)

    expect(overview.transport).toBe('polling')
    expect(overview.metrics.runs).toBe(1)
    expect(overview.metrics.live_promotable).toBe(1)
    expect(overview.venue_snapshot.venue).toBe('polymarket')
    expect(overview.benchmark?.benchmark.ready).toBe(true)
    expect(venue.transport).toBe('polling')
    expect(venue.capabilities.venue).toBe('polymarket')
    expect(venue.health.api_status).toBe('ok')
    expect(mocks.getPredictionDashboardArbitrageSnapshot).toHaveBeenCalledWith({
      workspaceId: 7,
      limitPerVenue: 16,
      maxPairs: 40,
      minArbitrageSpreadBps: 25,
      shadowCandidateLimit: 8,
      forceRefresh: true,
    })
    expect(arbitrage.overview.best_candidate_id).toBe('arb:btc:polymarket-kalshi')
    expect(arbitrage.candidates).toHaveLength(1)
  })
})
