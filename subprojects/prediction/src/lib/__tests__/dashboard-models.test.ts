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
    execution_projection_selected_edge_bucket: 'forecast_alpha',
    execution_projection_selected_pre_trade_gate_verdict: 'pass',
    execution_projection_selected_pre_trade_gate_summary: 'Hard no-trade gate pass. bucket=forecast_alpha gross=2300bps frictions=400bps net=1900bps minimum=800bps',
    execution_projection_selected_path_net_edge_bps: 1900,
    execution_projection_selected_path_minimum_net_edge_bps: 800,
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
    backtest_summary: {
      summary: 'Backtest over 120 samples remains profitable after frictions.',
      sample_count: 120,
      win_rate: 0.61,
      brier_score: 0.182,
      log_loss: 0.491,
      uplift_bps: 220,
    },
    resolved_history_summary: 'Resolved history built from 18/18 evaluation records spanning 2026-01-01T00:00:00.000Z -> 2026-04-01T00:00:00.000Z.',
    resolved_history_source_summary: 'Resolved 18 local evaluation records from 4 stored runs.',
    resolved_history_points: 18,
    cost_model_summary: 'Cost model evaluated 18 resolved points; average net edge=142 bps, viable rate=0.666667.',
    cost_model_total_points: 18,
    cost_model_viable_point_rate: 0.666667,
    cost_model_average_net_edge_bps: 142,
    walk_forward_summary: {
      summary: 'Walk-forward split is stable across 8 windows.',
      window_count: 8,
      win_rate: 0.58,
      brier_score: 0.191,
      uplift_bps: 145,
      promotion_ready: true,
    },
    monte_carlo_summary: {
      summary: 'Monte Carlo drawdowns stay within guardrails.',
      trial_count: 1000,
      win_rate: 0.63,
      uplift_bps: 175,
    },
    paper_validation_summary: {
      summary: 'Paper captures the same directionality as backtest.',
      sample_count: 80,
      win_rate: 0.59,
      uplift_bps: 130,
    },
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
    metadata: {
      p0_a_lineage: {
        adapter_lineage: {
          typescript_reference: 'Polymarket/clob-client',
          python_reference: 'Polymarket/py-clob-client',
          canonical_gate: 'execution_projection',
        },
      },
    },
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
    metadata: {
      p0_a_lineage: {
        canonical_gate: 'execution_projection',
      },
    },
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
    expect(runList.items[0]?.selected_edge_bucket).toBe('forecast_alpha')
    expect(runList.items[0]?.pre_trade_gate_verdict).toBe('pass')
    expect(runList.items[0]?.pre_trade_gate_summary).toContain('Hard no-trade gate pass')
    expect(runList.items[0]?.selected_path_minimum_net_edge_bps).toBe(800)
    expect(runList.items[0]?.validation?.resolved_history?.status).toBe('ready')
    expect(runList.items[0]?.validation?.resolved_history?.summary).toContain('Resolved 18 local evaluation records')
    expect(runList.items[0]?.validation?.cost_model?.summary).toContain('Cost model evaluated 18 resolved points')
    expect(runList.items[0]?.validation?.backtest?.summary).toContain('Backtest over 120 samples')
    expect(runList.items[0]?.validation?.blockers).toEqual([])
    expect(runList.items[0]?.validation?.blocker_summary).toBeNull()
    expect(runDetail?.benchmark.ready).toBe(true)
    expect(runDetail?.benchmark.status).toBe('eligible')
    expect(runDetail?.benchmark.gate_kind).toBe('local_benchmark')
    expect(runDetail?.benchmark.evidence_level).toBe('out_of_sample_promotion_evidence')
    expect(runDetail?.benchmark.summary).toContain('canonical blocker')
    expect(runDetail?.validation?.resolved_history?.sample_count).toBe(18)
    expect(runDetail?.validation?.resolved_history?.status).toBe('ready')
    expect(runDetail?.validation?.cost_model?.uplift_bps).toBe(142)
    expect(runDetail?.validation?.cost_model?.promotion_ready).toBe(true)
    expect(runDetail?.validation?.walk_forward?.summary).toContain('Walk-forward split is stable')
    expect(runDetail?.validation?.walk_forward?.promotion_ready).toBe(true)
    expect(runDetail?.validation?.blockers).toEqual([])
    expect(runDetail?.validation?.blocker_summary).toBeNull()
    expect(runDetail?.validation?.operator_summary).toContain('resolved_history:Resolved 18 local evaluation records from 4 stored runs.')
    expect(runDetail?.validation?.operator_summary).toContain('cost_model:Cost model evaluated 18 resolved points; average net edge=142 bps, viable rate=0.666667.')
    expect(runDetail?.execution.live_promotable).toBe(true)
    expect(runDetail?.execution.selected_edge_bucket).toBe('forecast_alpha')
    expect(runDetail?.execution.pre_trade_gate_verdict).toBe('pass')
    expect(runDetail?.execution.pre_trade_gate_summary).toContain('Hard no-trade gate pass')
    expect(runDetail?.execution.selected_path_net_edge_bps).toBe(1900)
    expect(runDetail?.execution.selected_path_minimum_net_edge_bps).toBe(800)
    expect(benchmark.comparison.benchmark_gate_blocks_live).toBe(false)
    expect(benchmark.comparison.benchmark_gate_live_block_reason).toBeNull()
  })

  it('falls back to nested execution projection selection fields and raises a fail alert', async () => {
    const {
      buildPredictionDashboardRunDetail,
      buildPredictionDashboardRunList,
    } = await import('@/lib/prediction-markets/dashboard-models')

    const nestedGate = {
      gate_name: 'hard_no_trade',
      verdict: 'fail',
      edge_bucket: 'arbitrage_alpha',
      net_edge_bps: 120,
      minimum_net_edge_bps: 220,
      summary: 'Hard no-trade gate fail. bucket=arbitrage_alpha gross=310bps frictions=190bps net=120bps minimum=220bps',
    }
    const nestedProjection = {
      selected_path: 'shadow',
      selected_edge_bucket: 'arbitrage_alpha',
      selected_pre_trade_gate: nestedGate,
      preflight_summary: {
        selected_edge_bucket: 'arbitrage_alpha',
        selected_pre_trade_gate: nestedGate,
      },
      projected_paths: {
        shadow: {
          edge_bucket: 'arbitrage_alpha',
          pre_trade_gate: nestedGate,
        },
      },
    }
    const nestedFixture = makeRunFixture({
      execution_projection_selected_edge_bucket: null,
      execution_projection_selected_pre_trade_gate_verdict: null,
      execution_projection_selected_pre_trade_gate_summary: null,
      execution_projection_selected_path_net_edge_bps: null,
      execution_projection_selected_path_minimum_net_edge_bps: null,
      resolved_history_points: 4,
      resolved_history_source_summary: 'Resolved 4 local evaluation records from 1 stored run.',
      execution_projection: nestedProjection,
    })

    mocks.listPredictionMarketRuns.mockReturnValueOnce([nestedFixture])
    mocks.getPredictionMarketRunDetails.mockReturnValueOnce(nestedFixture)

    const runList = buildPredictionDashboardRunList(7, 'polymarket', 10)
    const runDetail = buildPredictionDashboardRunDetail(7, 'run-1')

    expect(runList.items[0]?.selected_edge_bucket).toBe('arbitrage_alpha')
    expect(runList.items[0]?.pre_trade_gate_verdict).toBe('fail')
    expect(runList.items[0]?.selected_path_net_edge_bps).toBe(120)
    expect(runList.items[0]?.selected_path_minimum_net_edge_bps).toBe(220)
    expect(runList.items[0]?.validation?.resolved_history?.status).toBe('thin')
    expect(runList.items[0]?.validation?.blockers).toEqual([
      'resolved history thin (4 < 12 samples)',
    ])
    expect(runList.items[0]?.validation?.blocker_summary).toBe('resolved history thin (4 < 12 samples)')
    expect(runDetail?.execution.selected_edge_bucket).toBe('arbitrage_alpha')
    expect(runDetail?.execution.pre_trade_gate_verdict).toBe('fail')
    expect(runDetail?.execution.pre_trade_gate_summary).toContain('Hard no-trade gate fail')
    expect(runDetail?.validation?.resolved_history?.status).toBe('thin')
    expect(runDetail?.validation?.blockers).toEqual([
      'resolved history thin (4 < 12 samples)',
    ])
    expect(runDetail?.validation?.blocker_summary).toBe('resolved history thin (4 < 12 samples)')
    expect(runDetail?.alerts.map((alert) => alert.code)).toContain('pre_trade_gate_failed')
  })

  it('derives preview blockers when cost model and walk-forward are not promotion-ready', async () => {
    const {
      buildPredictionDashboardRunDetail,
      buildPredictionDashboardRunList,
    } = await import('@/lib/prediction-markets/dashboard-models')

    const previewFixture = makeRunFixture({
      resolved_history_points: 3,
      resolved_history_source_summary: 'Resolved 3 local evaluation records from 1 stored run.',
      cost_model_summary: 'Cost model still preview.',
      cost_model_total_points: 3,
      cost_model_viable_point_rate: 0.42,
      cost_model_average_net_edge_bps: -12,
      walk_forward_summary: {
        summary: 'Walk-forward still preview.',
        window_count: 1,
        win_rate: 0.41,
        uplift_bps: -8,
        promotion_ready: false,
      },
    })

    mocks.listPredictionMarketRuns.mockReturnValueOnce([previewFixture])
    mocks.getPredictionMarketRunDetails.mockReturnValueOnce(previewFixture)

    const runList = buildPredictionDashboardRunList(7, 'polymarket', 10)
    const runDetail = buildPredictionDashboardRunDetail(7, 'run-1')

    expect(runList.items[0]?.validation?.blockers).toEqual([
      'resolved history thin (3 < 12 samples)',
      'cost model viable rate 42.0% < 50.0%',
      'cost model mean net edge -12bps <= 0bps',
      'walk-forward only 1 window',
    ])
    expect(runList.items[0]?.validation?.blocker_summary).toBe(
      'resolved history thin (3 < 12 samples); cost model viable rate 42.0% < 50.0%; cost model mean net edge -12bps <= 0bps; walk-forward only 1 window',
    )
    expect(runDetail?.validation?.blockers).toEqual([
      'resolved history thin (3 < 12 samples)',
      'cost model viable rate 42.0% < 50.0%',
      'cost model mean net edge -12bps <= 0bps',
      'walk-forward only 1 window',
    ])
    expect(runDetail?.validation?.blocker_summary).toBe(
      'resolved history thin (3 < 12 samples); cost model viable rate 42.0% < 50.0%; cost model mean net edge -12bps <= 0bps; walk-forward only 1 window',
    )
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
    expect(overview.validation?.resolved_history?.summary).toContain('Resolved 18 local evaluation records')
    expect(overview.validation?.cost_model?.win_rate).toBeCloseTo(0.666667)
    expect(overview.validation?.monte_carlo?.summary).toContain('Monte Carlo drawdowns')
    expect(overview.crypto).toMatchObject({
      subproject_id: 'crypto',
      subproject_name: 'CRYPTO',
      venue: 'polymarket',
      venue_supported: true,
      seeded_markets_total: 4,
      seeded_markets_for_venue: 3,
      focus_assets: ['BTC', 'ETH', 'SOL'],
      execution_profiles: ['manual-research', 'semi-systematic', 'systematic-monitoring'],
    })
    expect(overview.crypto.highlighted_markets.map((market) => market.label)).toEqual([
      'BTC monthly strike map',
      'ETH expiry structure harvest',
      'SOL range bucket monitor',
    ])
    expect(overview.crypto.summary).toContain('CRYPTO tracks 3 seeded polymarket markets across 3 focus assets')
    expect(overview.subprojects.map((subproject) => subproject.id)).toEqual(['crypto', 'sport', 'meteo'])
    expect(overview.subprojects.find((subproject) => subproject.id === 'sport')).toMatchObject({
      name: 'Sport',
      venue_supported: true,
      seeded_markets_total: 4,
      seeded_markets_for_venue: 3,
      focus: ['football', 'basketball', 'tennis', 'combat'],
    })
    expect(overview.subprojects.find((subproject) => subproject.id === 'meteo')).toMatchObject({
      name: 'Météo',
      venue_supported: true,
      seeded_markets_total: 0,
      seeded_markets_for_venue: 0,
      focus: ['temperature', 'weather'],
      execution_profiles: ['manual-research', 'semi-systematic', 'systematic-monitoring'],
    })
    expect(overview.external_integrations.source_scope).toBe('conversation_registry')
    expect(overview.external_integrations.integration.profile_ids).toEqual(
      expect.arrayContaining(['polymarket-clob-client', 'geomapdata-cn']),
    )
    expect(overview.external_integrations.runtime_batches).toMatchObject({
      p0_a: expect.stringContaining('P0-A runtime summary'),
      p1_a: expect.stringContaining('P1-A runtime summary'),
      p1_b: expect.stringContaining('P1-B runtime summary'),
      p1_c: expect.stringContaining('P1-C runtime summary'),
      p2_b: expect.stringContaining('P2-B runtime summary'),
      p2_c: expect.stringContaining('P2-C runtime summary'),
    })
    expect(overview.venue_snapshot.capabilities.metadata.p0_a_lineage.adapter_lineage).toMatchObject({
      typescript_reference: 'Polymarket/clob-client',
      python_reference: 'Polymarket/py-clob-client',
      canonical_gate: 'execution_projection',
    })
    expect(overview.venue_snapshot.health.metadata.p0_a_lineage.canonical_gate).toBe('execution_projection')
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
