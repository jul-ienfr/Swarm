import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  buildPolymarketSnapshot: vi.fn(),
  listPolymarketMarkets: vi.fn(),
  buildKalshiSnapshot: vi.fn(),
  listKalshiMarkets: vi.fn(),
  findRecentPredictionMarketRunByConfig: vi.fn(),
  getStoredPredictionMarketRunDetails: vi.fn(),
  listPredictionMarketRuns: vi.fn(),
  persistPredictionMarketExecution: vi.fn(),
  createRun: vi.fn(),
  updateRun: vi.fn(),
  computeConfigHash: vi.fn(() => 'cfg-hash'),
  getRun: vi.fn(),
  getVenueCapabilitiesContract: vi.fn(),
  getVenueCoverageContract: vi.fn(),
  getVenueHealthSnapshotContract: vi.fn(),
  getVenueFeedSurfaceContract: vi.fn(),
  getVenueBudgetsContract: vi.fn(),
  listPredictionMarketVenues: vi.fn(),
  evaluatePredictionMarketCompliance: vi.fn(),
  evaluatePredictionMarketRuntimeGuard: vi.fn(),
  runPredictionMarketTimesFMSidecar: vi.fn(),
  resolvePredictionMarketEvaluationHistory: vi.fn(),
  extractForecastEvaluationHistoryFromArtifacts: vi.fn(() => []),
}))

vi.mock('@/lib/prediction-markets/polymarket', () => ({
  buildPolymarketSnapshot: mocks.buildPolymarketSnapshot,
  listPolymarketMarkets: mocks.listPolymarketMarkets,
}))

vi.mock('@/lib/prediction-markets/kalshi', () => ({
  buildKalshiSnapshot: mocks.buildKalshiSnapshot,
  listKalshiMarkets: mocks.listKalshiMarkets,
}))

vi.mock('@/lib/prediction-markets/store', () => ({
  findRecentPredictionMarketRunByConfig: mocks.findRecentPredictionMarketRunByConfig,
  getPredictionMarketRunDetails: mocks.getStoredPredictionMarketRunDetails,
  listPredictionMarketRuns: mocks.listPredictionMarketRuns,
  persistPredictionMarketExecution: mocks.persistPredictionMarketExecution,
}))

vi.mock('@/lib/runs', () => ({
  createRun: mocks.createRun,
  updateRun: mocks.updateRun,
  computeConfigHash: mocks.computeConfigHash,
  getRun: mocks.getRun,
}))

vi.mock('@/lib/prediction-markets/venue-ops', () => ({
  getVenueCapabilitiesContract: mocks.getVenueCapabilitiesContract,
  getVenueCoverageContract: mocks.getVenueCoverageContract,
  getVenueHealthSnapshotContract: mocks.getVenueHealthSnapshotContract,
  getVenueFeedSurfaceContract: mocks.getVenueFeedSurfaceContract,
  getVenueBudgetsContract: mocks.getVenueBudgetsContract,
  listPredictionMarketVenues: mocks.listPredictionMarketVenues,
}))

vi.mock('@/lib/prediction-markets/compliance', () => ({
  evaluatePredictionMarketCompliance: mocks.evaluatePredictionMarketCompliance,
}))

vi.mock('@/lib/prediction-markets/runtime-guard', () => ({
  evaluatePredictionMarketRuntimeGuard: mocks.evaluatePredictionMarketRuntimeGuard,
}))

vi.mock('@/lib/prediction-markets/timesfm', async () => {
  const actual = await vi.importActual('@/lib/prediction-markets/timesfm') as typeof import('@/lib/prediction-markets/timesfm')

  return {
    ...actual,
    runPredictionMarketTimesFMSidecar: mocks.runPredictionMarketTimesFMSidecar,
  }
})

vi.mock('@/lib/prediction-markets/evaluation-history-source', () => ({
  resolvePredictionMarketEvaluationHistory: mocks.resolvePredictionMarketEvaluationHistory,
  extractForecastEvaluationHistoryFromArtifacts: mocks.extractForecastEvaluationHistoryFromArtifacts,
}))

import {
  advisePredictionMarket,
  listPredictionMarketRuns as listPredictionMarketRunsService,
  replayPredictionMarketRun,
  buildStrategyExecutionIntentArtifacts,
} from '@/lib/prediction-markets/service'
import { resetPredictionMarketResearchMemoryRuntimeForTests } from '@/lib/prediction-markets/memory/runtime'
import {
  decisionPacketSchema,
  evidencePacketSchema,
  forecastPacketSchema,
  marketDescriptorSchema,
  marketRecommendationPacketSchema,
  marketSnapshotSchema,
  resolutionPolicySchema,
  runManifestSchema,
  type MarketDescriptor,
  type MarketSnapshot,
} from '@/lib/prediction-markets/schemas'

function makeDescriptor(overrides: Partial<MarketDescriptor> = {}): MarketDescriptor {
  return marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: 'service-hardening-market',
    slug: 'service-hardening-market',
    question: 'Will the service hardening test stay stable?',
    outcomes: ['Yes', 'No'],
    active: true,
    closed: false,
    accepting_orders: true,
    restricted: false,
    liquidity_usd: 90_000,
    volume_usd: 700_000,
    volume_24h_usd: 40_000,
    best_bid: 0.49,
    best_ask: 0.51,
    last_trade_price: 0.5,
    tick_size: 0.01,
    min_order_size: 5,
    is_binary_yes_no: true,
    end_at: '2026-12-31T23:59:59.000Z',
    source_urls: ['https://example.com/service-hardening-market'],
    ...overrides,
  })
}

function makeSnapshot(overrides: Partial<MarketSnapshot> = {}): MarketSnapshot {
  const market = makeDescriptor(overrides.market ? overrides.market : {})

  return marketSnapshotSchema.parse({
    venue: market.venue,
    market,
    captured_at: '2026-04-07T23:59:00.000Z',
    yes_outcome_index: 0,
    yes_token_id: `${market.market_id}:yes`,
    yes_price: 0.5,
    no_price: 0.5,
    midpoint_yes: 0.5,
    best_bid_yes: 0.49,
    best_ask_yes: 0.51,
    spread_bps: 200,
    book: {
      token_id: `${market.market_id}:yes`,
      market_condition_id: `${market.market_id}:cond`,
      fetched_at: '2026-04-07T23:59:00.000Z',
      best_bid: 0.49,
      best_ask: 0.51,
      last_trade_price: 0.5,
      tick_size: 0.01,
      min_order_size: 5,
      bids: [{ price: 0.49, size: 400 }],
      asks: [{ price: 0.51, size: 400 }],
      depth_near_touch: 800,
    },
    history: [
      { timestamp: 1712534400, price: 0.48 },
      { timestamp: 1712538000, price: 0.5 },
    ],
    source_urls: [
      'https://example.com/service-hardening-market',
      'https://example.com/service-hardening-market/book',
    ],
    ...overrides,
  })
}

function makeTimesFMSidecar(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: 'v1',
    sidecar_name: 'timesfm_sidecar',
    run_id: 'run-timesfm',
    market_id: 'service-hardening-market',
    venue: 'polymarket',
    question: 'Will the service hardening test stay stable?',
    requested_mode: 'auto',
    effective_mode: 'auto',
    requested_lanes: ['microstructure', 'event_probability'],
    selected_lane: 'microstructure',
    generated_at: '2026-04-08T00:00:00.000Z',
    health: {
      healthy: true,
      status: 'healthy',
      backend: 'fixture',
      dependency_status: 'fixture_backend',
      issues: [],
      summary: 'fixture backend ready',
    },
    vendor: {
      source: 'master_snapshot',
    },
    lanes: {
      microstructure: {
        lane: 'microstructure',
        status: 'ready',
        eligible: true,
        influences_research_aggregate: true,
        comparator_id: 'candidate_timesfm_microstructure',
        comparator_kind: 'candidate_model',
        basis: 'timesfm_microstructure',
        model_family: 'timesfm-2.5',
        pipeline_id: 'timesfm-master-snapshot',
        pipeline_version: 'd720daa67865',
        probability_yes: 0.56,
        confidence: 0.62,
        probability_band: { low: 0.5, center: 0.56, high: 0.62 },
        quantiles: { p10: 0.5, p50: 0.56, p90: 0.62 },
        horizon: 24,
        summary: 'microstructure lane ready',
        rationale: 'fixture backend forecast',
        reasons: [],
        source_refs: ['commit:d720daa6786539c2566a44464fbda1019c0a82c0'],
        metadata: {},
      },
    },
    summary: 'TimesFM ready',
    metadata: {},
    ...overrides,
  }
}

function makeDecisionPacket() {
  return decisionPacketSchema.parse({
    correlation_id: 'decision-bridge-001',
    question: 'Will the deliberation bridge stay stable?',
    topic: 'prediction_markets',
    objective: 'Carry committee output into the execution advisor.',
    probability_estimate: 0.67,
    confidence_band: [0.62, 0.71],
    scenarios: ['base case'],
    risks: ['stale_data'],
    recommendation: 'bet yes only if runtime guard remains conservative',
    rationale_summary: 'Committee sees modest upside over the market midpoint.',
    artifacts: ['decision-artifact-1'],
    mode_used: 'committee',
    engine_used: 'oaswarm',
    runtime_used: 'prediction_markets',
  })
}

function makeStoredRunDetails(runId: string, snapshot: MarketSnapshot) {
  const resolutionPolicy = resolutionPolicySchema.parse({
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    status: 'eligible',
    manual_review_required: false,
    reasons: [],
    primary_sources: snapshot.source_urls,
    evaluated_at: '2026-04-08T00:00:00.000Z',
  })
  const evidencePackets = [
    evidencePacketSchema.parse({
      evidence_id: `${snapshot.market.market_id}:manual-thesis`,
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      type: 'manual_thesis',
      title: 'Manual thesis override',
      summary: 'Stored manual thesis for replay.',
      captured_at: '2026-04-08T00:00:00.000Z',
      content_hash: 'sha256:manual-thesis',
      metadata: {
        thesis_probability: 0.7,
        thesis_rationale: 'Stored manual thesis for replay.',
      },
    }),
  ]
  const forecast = forecastPacketSchema.parse({
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    basis: 'manual_thesis',
    probability_yes: 0.7,
    confidence: 0.55,
    rationale: 'Stored forecast',
    evidence_refs: evidencePackets.map((packet) => packet.evidence_id),
    produced_at: '2026-04-08T00:00:00.000Z',
  })
  const recommendation = marketRecommendationPacketSchema.parse({
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    action: 'bet',
    side: 'yes',
    confidence: 0.55,
    fair_value_yes: 0.7,
    market_price_yes: 0.5,
    market_bid_yes: 0.49,
    market_ask_yes: 0.51,
    edge_bps: 1900,
    spread_bps: 200,
    reasons: ['Stored recommendation'],
    risk_flags: [],
    produced_at: '2026-04-08T00:00:00.000Z',
  })
  const manifest = runManifestSchema.parse({
    run_id: runId,
    mode: 'advise',
    venue: snapshot.venue,
    market_id: snapshot.market.market_id,
    market_slug: snapshot.market.slug,
    actor: 'operator',
    started_at: '2026-04-08T00:00:00.000Z',
    completed_at: '2026-04-08T00:00:02.000Z',
    status: 'completed',
    config_hash: 'stored-config-hash',
  })

  return {
    run: { id: runId, status: 'completed' },
    summary: {
      run_id: runId,
      workspace_id: 1,
      venue: snapshot.venue,
      mode: 'advise',
      market_id: snapshot.market.market_id,
      market_slug: snapshot.market.slug ?? null,
      status: 'completed',
      recommendation: 'bet',
      side: 'yes',
      confidence: 0.55,
      probability_yes: 0.7,
      market_price_yes: 0.5,
      edge_bps: 1900,
    },
    artifacts: [
      { artifact_type: 'market_snapshot', payload: snapshot },
      { artifact_type: 'resolution_policy', payload: resolutionPolicy },
      { artifact_type: 'evidence_bundle', payload: evidencePackets },
      { artifact_type: 'forecast_packet', payload: forecast },
      { artifact_type: 'recommendation_packet', payload: recommendation },
      {
        artifact_type: 'paper_surface',
        payload: {
          schema_version: '1.0.0',
          no_trade_zone_count: 1,
          no_trade_zone_rate: 0.5,
          fill_rate: 0.75,
          partial_fill_rate: 0.25,
        },
      },
      {
        artifact_type: 'replay_surface',
        payload: {
          schema_version: '1.0.0',
          no_trade_leg_count: 1,
          no_trade_leg_rate: 0.5,
          fill_rate: 0.6,
          partial_fill_rate: 0.4,
        },
      },
      { artifact_type: 'run_manifest', payload: manifest },
    ],
  }
}

describe('prediction markets service hardening', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-08T00:00:00.000Z'))

    mocks.findRecentPredictionMarketRunByConfig.mockReset()
    mocks.getStoredPredictionMarketRunDetails.mockReset()
    mocks.listPredictionMarketRuns.mockReset()
    mocks.persistPredictionMarketExecution.mockReset()
    mocks.createRun.mockReset()
    mocks.updateRun.mockReset()
    mocks.computeConfigHash.mockReset()
    mocks.getRun.mockReset()
    mocks.buildPolymarketSnapshot.mockReset()
    mocks.listPolymarketMarkets.mockReset()
    mocks.buildKalshiSnapshot.mockReset()
    mocks.listKalshiMarkets.mockReset()
    mocks.getVenueCapabilitiesContract.mockReset()
    mocks.getVenueCoverageContract.mockReset()
    mocks.getVenueHealthSnapshotContract.mockReset()
    mocks.getVenueFeedSurfaceContract.mockReset()
    mocks.getVenueBudgetsContract.mockReset()
    mocks.listPredictionMarketVenues.mockReset()
    mocks.evaluatePredictionMarketCompliance.mockReset()
    mocks.evaluatePredictionMarketRuntimeGuard.mockReset()
    mocks.runPredictionMarketTimesFMSidecar.mockReset()
    mocks.resolvePredictionMarketEvaluationHistory.mockReset()
    mocks.extractForecastEvaluationHistoryFromArtifacts.mockReset()

    mocks.computeConfigHash.mockImplementation(() => 'cfg-hash')
    mocks.createRun.mockImplementation((run) => run)
    mocks.getRun.mockImplementation((runId: string) => ({ id: runId, status: 'completed' }))
    mocks.findRecentPredictionMarketRunByConfig.mockReturnValue(null)
    mocks.listPredictionMarketVenues.mockReturnValue(['polymarket', 'kalshi'])
    mocks.getVenueCapabilitiesContract.mockReturnValue({
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      supports_discovery: true,
      supports_metadata: true,
      supports_orderbook: true,
      supports_trades: true,
      supports_positions: false,
      supports_execution: false,
      supports_websocket: false,
      supports_paper_mode: false,
      api_access: ['source_of_truth:official_docs'],
      supported_order_types: ['limit'],
      planned_order_types: ['limit'],
      rate_limit_notes: '',
      automation_constraints: [],
    })
    mocks.getVenueCoverageContract.mockReturnValue({
      schema_version: '1.0.0',
      venue_count: 2,
      execution_capable_count: 0,
      paper_capable_count: 1,
      read_only_count: 2,
      degraded_venue_count: 0,
      degraded_venue_rate: 0,
      execution_equivalent_count: 2,
      execution_like_count: 0,
      reference_only_count: 0,
      watchlist_only_count: 0,
      metadata_gap_count: 0,
      metadata_gap_rate: 0,
      execution_surface_rate: 0,
      availability_by_venue: {
        polymarket: {
          venue: 'polymarket',
          health_status: 'ready',
          degraded: false,
          supports_execution: false,
          supports_paper_mode: false,
          planned_order_types: ['limit'],
          supported_order_types: ['limit'],
        },
        kalshi: {
          venue: 'kalshi',
          health_status: 'ready',
          degraded: false,
          supports_execution: false,
          supports_paper_mode: true,
          planned_order_types: ['limit'],
          supported_order_types: ['limit'],
        },
      },
    })
    mocks.getVenueHealthSnapshotContract.mockReturnValue({
      venue: 'polymarket',
      captured_at: '2026-04-08T00:00:00.000Z',
      health_score: 0.65,
      api_status: 'degraded',
      stream_status: 'unknown',
      staleness_ms: 0,
      degraded_mode: 'degraded',
      incident_flags: ['upstream_partial'],
      notes: 'degraded for test',
    })
    mocks.getVenueFeedSurfaceContract.mockReturnValue({
      schema_version: '1.0.0',
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      backend_mode: 'read_only',
      ingestion_mode: 'read_only',
      market_feed_kind: 'market_snapshot',
      user_feed_kind: 'position_snapshot',
      supports_discovery: true,
      supports_orderbook: true,
      supports_trades: true,
      supports_execution: false,
      supports_paper_mode: false,
      supports_market_feed: true,
      supports_user_feed: true,
      supports_events: true,
      supports_positions: true,
      supports_websocket: false,
      supports_rtds: false,
      live_streaming: false,
      api_access: ['source_of_truth:official_docs'],
      planned_order_types: ['limit'],
      supported_order_types: ['limit'],
      rate_limit_notes: ['read-only advisory mode only'],
      automation_constraints: ['read-only advisory mode only'],
      market_feed_transport: 'local_cache',
      user_feed_transport: 'local_cache',
      market_feed_status: 'local_cache',
      user_feed_status: 'local_cache',
      rtds_status: 'unavailable',
      events_source: 'snapshot_polling',
      positions_source: 'local_position_cache',
      market_feed_source: 'snapshot_polling',
      user_feed_source: 'local_position_cache',
      configured_endpoints: {
        market_feed_source: 'snapshot_polling',
        user_feed_source: 'local_position_cache',
      },
      summary: 'read-only feed surface',
      runbook: {},
      notes: [],
      metadata_gap_count: 0,
      metadata_gap_rate: 0,
      metadata_completeness: 1,
      metadata: {},
    })
    mocks.getVenueBudgetsContract.mockReturnValue({
      fetch_latency_budget_ms: 1,
      snapshot_freshness_budget_ms: 1,
      decision_latency_budget_ms: 1,
      stream_reconnect_budget_ms: 10,
      cache_ttl_ms: 1,
      max_retries: 0,
      backpressure_policy: 'degrade-to-wait',
    })
    mocks.evaluatePredictionMarketRuntimeGuard.mockImplementation((input: { venue: string; mode: string }) => ({
      venue: input.venue,
      mode: input.mode,
      verdict: 'degraded',
      reasons: ['runtime guard degraded for test'],
      constraints: ['mode=discovery'],
      fallback_actions: ['keep_read_only'],
      capabilities: mocks.getVenueCapabilitiesContract(),
      health: mocks.getVenueHealthSnapshotContract(),
      budgets: mocks.getVenueBudgetsContract(),
    }))
    mocks.evaluatePredictionMarketCompliance.mockReturnValue({
      status: 'degraded',
      summary: 'Compliance degraded for service hardening test.',
      effective_mode: 'discovery',
    })
    mocks.resolvePredictionMarketEvaluationHistory.mockReturnValue({
      evaluation_history: [],
      source: 'none',
      source_summary: 'No local resolved history was available from stored runs.',
      considered_runs: 0,
      used_runs: 0,
      same_market_records: 0,
      same_category_records: 0,
      same_venue_records: 0,
    })
    mocks.extractForecastEvaluationHistoryFromArtifacts.mockReturnValue([])
    mocks.persistPredictionMarketExecution.mockImplementation(({ runId, sourceRunId, venue, mode, snapshot, recommendation }: any) => ({
      artifactRefs: [
        { artifact_id: `${runId}:run_manifest`, artifact_type: 'run_manifest', sha256: 'sha-run-manifest' },
      ],
      summary: {
        run_id: runId,
        source_run_id: sourceRunId ?? null,
        workspace_id: 1,
        venue,
        mode,
        market_id: snapshot.market.market_id,
        market_slug: snapshot.market.slug ?? null,
        status: 'completed',
        recommendation: recommendation.action,
        side: recommendation.side,
        confidence: recommendation.confidence,
        probability_yes: recommendation.fair_value_yes,
        market_price_yes: recommendation.market_price_yes,
        edge_bps: recommendation.edge_bps,
      },
    }))
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    resetPredictionMarketResearchMemoryRuntimeForTests()
  })

  it('returns a stable advise payload when research is absent and cross-venue discovery fails best-effort', async () => {
    const snapshot = makeSnapshot()

    mocks.buildPolymarketSnapshot.mockImplementation(async () => {
      vi.advanceTimersByTime(5)
      return snapshot
    })
    mocks.listKalshiMarkets.mockRejectedValue(new Error('kalshi discovery offline'))

    const result = await advisePredictionMarket({
      venue: 'polymarket',
      market_id: snapshot.market.market_id,
      thesis_probability: 0.7,
      thesis_rationale: 'Manual thesis without research sidecar.',
      workspaceId: 1,
      actor: 'operator',
    })

    expect(result.research_sidecar).toBeNull()
    expect(result.pipeline_guard.status).toBe('degraded')
    expect(result.pipeline_guard.breached_budgets).toEqual(
      expect.arrayContaining(['fetch_latency_budget_ms', 'decision_latency_budget_ms']),
    )
    expect(result.runtime_guard.verdict).toBe('degraded')
    expect(result.compliance.status).toBe('degraded')
    expect(result.cross_venue_intelligence.errors).toEqual([
      'cross-venue discovery failed for kalshi: kalshi discovery offline',
    ])
    expect(result.recommendation.action).toBe('wait')
    expect(result.recommendation.risk_flags).toEqual(
      expect.arrayContaining(['venue_degraded', 'budget_breach']),
    )
    expect(mocks.persistPredictionMarketExecution).toHaveBeenCalledTimes(1)
    expect(mocks.persistPredictionMarketExecution.mock.calls[0]?.[0].recommendation.action).toBe('wait')
  })

  it('bridges decision packets into a manual thesis, evidence bundle, and config hash', async () => {
    const snapshot = makeSnapshot()
    const decisionPacket = makeDecisionPacket()

    mocks.buildPolymarketSnapshot.mockResolvedValue(snapshot)
    mocks.listKalshiMarkets.mockRejectedValue(new Error('kalshi discovery offline'))

    const result = await advisePredictionMarket({
      venue: 'polymarket',
      market_id: snapshot.market.market_id,
      decision_packet: decisionPacket,
      workspaceId: 1,
      actor: 'operator',
    })

    expect(result.forecast.basis).toBe('manual_thesis')
    expect(result.forecast.probability_yes).toBe(0.67)
    expect(result.forecast.rationale).toContain('Committee sees modest upside over the market midpoint.')
    expect(result.evidence_packets.map((packet) => packet.type)).toEqual([
      'market_data',
      'orderbook',
      'history',
      'system_note',
      'manual_thesis',
    ])
    expect(result.evidence_packets.find((packet) => packet.type === 'system_note')).toMatchObject({
      metadata: expect.objectContaining({
        correlation_id: 'decision-bridge-001',
        probability_estimate: 0.67,
      }),
    })
    expect(result.run).not.toBeNull()
    expect(result.packet_bundle).toMatchObject({
      bundle_id: `${result.run!.id}:packet_bundle`,
      run_id: result.run!.id,
      venue: 'polymarket',
      market_id: snapshot.market.market_id,
      advisor_architecture: expect.objectContaining({
        architecture_id: `${result.run!.id}:advisor_architecture`,
        architecture_kind: 'reference_agentic',
        social_bridge_state: 'available',
      }),
      decision_packet: decisionPacket,
      forecast_packet: expect.objectContaining({
        probability_yes: 0.67,
        packet_kind: 'forecast',
      }),
      recommendation_packet: expect.objectContaining({
        action: result.recommendation.action,
        packet_kind: 'recommendation',
      }),
    })
    expect(result.packet_bundle?.advisor_architecture.stages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          stage_kind: 'execution_preflight',
          metadata: expect.objectContaining({
            trade_intent_guard_verdict: result.trade_intent_guard?.verdict ?? null,
            trade_intent_guard_blocked_reasons: result.trade_intent_guard?.blocked_reasons ?? [],
            benchmark_promotion_ready: false,
            benchmark_promotion_gate_kind: 'preview_only',
            benchmark_gate_blocks_live: false,
            benchmark_gate_live_block_reason: null,
          }),
        }),
      ]),
    )
    expect(result.packet_bundle?.evidence_packets.map((packet) => packet.type)).toEqual([
      'market_data',
      'orderbook',
      'history',
      'system_note',
      'manual_thesis',
    ])
    expect(mocks.computeConfigHash.mock.calls.some((call) => {
      const value = call.at(0)
      return (
        value != null &&
        typeof value === 'object' &&
        'decision_packet_correlation_id' in value &&
        (value as Record<string, unknown>).decision_packet_correlation_id === 'decision-bridge-001'
      )
    })).toBe(true)
    expect(mocks.persistPredictionMarketExecution.mock.calls[0]?.[0].evidencePackets).toEqual(expect.arrayContaining([
      expect.objectContaining({ type: 'system_note' }),
      expect.objectContaining({ type: 'manual_thesis' }),
    ]))
  })

  it('returns a stable replay payload when budgets breach and cross-venue discovery fails best-effort', async () => {
    const snapshot = makeSnapshot()
    const stored = makeStoredRunDetails('source-run', snapshot)

    mocks.getStoredPredictionMarketRunDetails.mockImplementation(() => {
      vi.advanceTimersByTime(5)
      return stored
    })
    mocks.listKalshiMarkets.mockRejectedValue(new Error('kalshi discovery offline'))

    const result = await replayPredictionMarketRun({
      runId: 'source-run',
      workspaceId: 1,
      actor: 'operator',
    })

    expect(result.pipeline_guard.status).toBe('degraded')
    expect(result.pipeline_guard.breached_budgets).toContain('decision_latency_budget_ms')
    expect(result.runtime_guard.verdict).toBe('degraded')
    expect(result.compliance.status).toBe('degraded')
    expect(result.cross_venue_intelligence.errors).toEqual([
      'cross-venue discovery failed for kalshi: kalshi discovery offline',
    ])
    expect(result.paper_surface).toMatchObject({
      no_trade_zone_count: 1,
      no_trade_zone_rate: 0.5,
    })
    expect(result.replay_surface).toMatchObject({
      no_trade_leg_count: 1,
      no_trade_leg_rate: 0.5,
    })
    expect(result.paper_no_trade_zone_count).toBe(1)
    expect(result.paper_no_trade_zone_rate).toBe(0.5)
    expect(result.replay_no_trade_leg_count).toBe(1)
    expect(result.replay_no_trade_leg_rate).toBe(0.5)
    expect(result.recommendation.action).toBe('wait')
    expect(result.recommendation.risk_flags).toEqual(
      expect.arrayContaining(['budget_breach']),
    )
    expect(mocks.persistPredictionMarketExecution).toHaveBeenCalledTimes(1)
    expect(mocks.persistPredictionMarketExecution.mock.calls[0]?.[0].sourceRunId).toBe('source-run')
    expect(mocks.persistPredictionMarketExecution.mock.calls[0]?.[0].recommendation.action).toBe('wait')
    expect(mocks.updateRun).toHaveBeenCalled()
  })

  it('enriches maker spread capture previews with bounded inventory, adverse selection, and quote transport summaries', () => {
    const snapshot = marketSnapshotSchema.parse({
      ...structuredClone(makeSnapshot()),
      captured_at: '2026-04-07T23:59:34.000Z',
      book: {
        ...structuredClone(makeSnapshot().book),
        fetched_at: '2026-04-07T23:59:34.000Z',
      },
    })
    const makerCandidate = {
      kind: 'maker_spread_capture',
      summary: 'Maker spread capture candidate with bounded inventory.',
      related_market_ids: [],
      metrics: {
        spread_bps: 200,
        quote_age_ms: 26_000,
        maker_quote_freshness_budget_ms: 30_000,
        maker_quote_state: 'viable',
        quote_freshness_score: 0.1333,
        liquidity_usd: 90_000,
      },
      metadata: {
        maker_quote_freshness_budget_ms: 30_000,
        maker_quote_state: 'viable',
        quote_freshness_score: 0.1333,
      },
    } as any
    const makerDiagnostics = {
      inventory_summary: 'inventory: preview size 25.00 USD; liquidity 90,000.00 USD; depth near touch 800.00 USD; quote state viable',
      adverse_selection_summary: 'adverse selection: spread 200 bps; freshness score 0.13; quote age 26000 ms / budget 30000 ms; freshness state fresh; latency state fresh',
      quote_transport_summary: 'quote transport: orderbook_snapshot; fetched_at 2026-04-07T23:59:34.000Z; source refs 2; observed age 26000 ms',
      blockers: ['quote_transport_near_freshness_limit'],
      risk_caps: [
        'recommended_size_usd:25.00',
        'max_slippage_bps:50',
        'quote_freshness_budget_ms:30000',
        'quote_age_ms:26000',
      ],
    }

    const artifacts = buildStrategyExecutionIntentArtifacts({
      runId: 'source-run',
      snapshot,
      forecast: forecastPacketSchema.parse({
        market_id: snapshot.market.market_id,
        venue: snapshot.venue,
        basis: 'manual_thesis',
        probability_yes: 0.62,
        confidence: 0.56,
        rationale: 'Maker spread capture research preview.',
        evidence_refs: [],
        produced_at: '2026-04-08T00:00:00.000Z',
      }),
      recommendation: marketRecommendationPacketSchema.parse({
        market_id: snapshot.market.market_id,
        venue: snapshot.venue,
        action: 'bet',
        side: 'yes',
        confidence: 0.56,
        fair_value_yes: 0.62,
        market_price_yes: 0.5,
        market_bid_yes: 0.49,
        market_ask_yes: 0.51,
        edge_bps: 1200,
        spread_bps: 200,
        reasons: ['Maker spread capture bounded preview.'],
        risk_flags: [],
        produced_at: '2026-04-08T00:00:00.000Z',
      }),
      strategyProfile: 'hybrid',
      primaryCandidate: makerCandidate,
      strategySummary: 'maker spread capture strategy decision',
      shadowSummary: {
        schema_version: '1.0.0',
        shadow_id: 'source-run:strategy-shadow',
        run_id: 'source-run',
        venue: snapshot.venue,
        market_id: snapshot.market.market_id,
        strategy_profile: 'hybrid',
        strategy_family: 'maker_spread_capture',
        candidate_count: 1,
        decision_count: 1,
        disagreement_count: 0,
        alignment_rate: 1,
        summary: 'Shadow summary for maker spread capture.',
        metadata: {},
      } as any,
      makerSpreadCaptureDiagnostics: makerDiagnostics,
    })

    expect(artifacts.quote_pair_intent_preview).toMatchObject({
      preview_kind: 'quote_pair',
      strategy_family: 'maker_spread_capture',
      summary: expect.stringContaining('inventory: preview size'),
      metadata: expect.objectContaining({
        maker_spread_capture_inventory_summary: expect.stringContaining('inventory: preview size'),
        maker_spread_capture_adverse_selection_summary: expect.stringContaining('adverse selection:'),
        maker_spread_capture_quote_transport_summary: expect.stringContaining('quote transport:'),
        maker_spread_capture_blockers: expect.arrayContaining(['quote_transport_near_freshness_limit']),
        maker_spread_capture_risk_caps: expect.arrayContaining([
          expect.stringMatching(/^recommended_size_usd:/),
          expect.stringMatching(/^max_slippage_bps:/),
          expect.stringMatching(/^quote_freshness_budget_ms:/),
        ]),
      }),
    })
    expect(artifacts.maker_spread_capture_inventory_summary).toContain('inventory: preview size')
    expect(artifacts.maker_spread_capture_adverse_selection_summary).toContain('adverse selection:')
    expect(artifacts.maker_spread_capture_quote_transport_summary).toContain('quote transport:')
    expect(artifacts.maker_spread_capture_blockers).toContain('quote_transport_near_freshness_limit')
    expect(artifacts.maker_spread_capture_risk_caps).toEqual(expect.arrayContaining([
      expect.stringMatching(/^recommended_size_usd:/),
      expect.stringMatching(/^max_slippage_bps:/),
      expect.stringMatching(/^quote_freshness_budget_ms:/),
    ]))
  })

  it('keeps benchmark summaries canonical in listPredictionMarketRuns when runtime hints carry conflicting research aliases', () => {
    const snapshot = makeSnapshot()
    const stored = makeStoredRunDetails('run-list-benchmark-001', snapshot)
    const manifest = stored.artifacts.at(-1)?.payload
    const storedSummary = {
      ...structuredClone(stored.summary),
      artifact_refs: [
        { artifact_id: 'run-list-benchmark-001:run_manifest', artifact_type: 'run_manifest', sha256: 'sha-run-manifest' },
        { artifact_id: 'run-list-benchmark-001:execution_projection', artifact_type: 'execution_projection', sha256: 'sha-execution-projection' },
      ],
      manifest,
      benchmark_gate_summary: 'benchmark gate: canonical promotion',
      benchmark_uplift_bps: 111,
      benchmark_verdict: 'local_benchmark_ready',
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'eligible',
      benchmark_promotion_ready: true,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'local_benchmark',
      benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_promotion_blocker_summary: 'canonical promotion satisfied',
      benchmark_promotion_summary: 'canonical promotion satisfied',
      benchmark_gate_blocks_live: false,
      benchmark_gate_live_block_reason: null,
      benchmark_gate_blockers: [],
      benchmark_gate_reasons: ['canonical promotion'],
    } as never
    const storedBenchmarkDetails = {
      ...structuredClone(stored),
      research_benchmark_gate_summary: 'research benchmark gate: blocked',
      research_benchmark_uplift_bps: 111,
      research_benchmark_verdict: 'blocked_by_abstention',
      research_benchmark_gate_status: 'blocked_by_abstention',
      research_benchmark_promotion_status: 'blocked',
      research_benchmark_promotion_ready: false,
      research_benchmark_preview_available: true,
      research_benchmark_promotion_evidence: 'blocked',
      research_benchmark_evidence_level: 'benchmark_preview',
      research_promotion_gate_kind: 'preview_only',
      research_benchmark_promotion_blocker_summary: 'research alias blocker',
      research_benchmark_promotion_summary: 'research alias blocker',
      research_benchmark_gate_blockers: ['research_alias_blocker'],
      research_benchmark_gate_reasons: ['research_alias_blocker'],
      research_benchmark_live_block_reason: 'research alias blocker',
      benchmark_gate_summary: undefined,
      benchmark_uplift_bps: undefined,
      benchmark_verdict: undefined,
      benchmark_gate_status: undefined,
      benchmark_promotion_status: undefined,
      benchmark_promotion_ready: undefined,
      benchmark_preview_available: undefined,
      benchmark_promotion_evidence: undefined,
      benchmark_evidence_level: undefined,
      benchmark_promotion_gate_kind: undefined,
      benchmark_promotion_blocker_summary: undefined,
      benchmark_promotion_summary: undefined,
      benchmark_gate_blocks_live: undefined,
      benchmark_gate_live_block_reason: undefined,
      benchmark_gate_blockers: undefined,
      benchmark_gate_reasons: undefined,
    } as never

    mocks.listPredictionMarketRuns.mockReturnValue([storedSummary])
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(storedBenchmarkDetails)

    const runs = listPredictionMarketRunsService({
      workspaceId: 1,
      venue: 'polymarket',
      recommendation: undefined,
      limit: 10,
    })

    expect(runs).toHaveLength(1)
    expect(runs[0]).toMatchObject({
      run_id: 'run-list-benchmark-001',
      artifact_audit: expect.objectContaining({
        run_manifest_present: true,
      }),
      benchmark_gate_summary: 'benchmark gate: canonical promotion',
      benchmark_promotion_ready: true,
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_gate_blocks_live: false,
      benchmark_gate_live_block_reason: null,
      research_benchmark_gate_summary: 'benchmark gate: canonical promotion',
      research_benchmark_promotion_ready: true,
    })
  })

  it('hydrates validation summaries from resolved history, cost model, and walk-forward artifacts in listPredictionMarketRuns', () => {
    const snapshot = makeSnapshot()
    const stored = makeStoredRunDetails('run-list-validation-001', snapshot)
    const manifest = stored.artifacts.find((artifact) => artifact.artifact_type === 'run_manifest')?.payload
    const storedSummary = {
      ...structuredClone(stored.summary),
      artifact_refs: [
        { artifact_id: 'run-list-validation-001:run_manifest', artifact_type: 'run_manifest', sha256: 'sha-run-manifest' },
        { artifact_id: 'run-list-validation-001:resolved_history', artifact_type: 'resolved_history', sha256: 'sha-resolved-history' },
        { artifact_id: 'run-list-validation-001:cost_model_report', artifact_type: 'cost_model_report', sha256: 'sha-cost-model' },
        { artifact_id: 'run-list-validation-001:walk_forward_report', artifact_type: 'walk_forward_report', sha256: 'sha-walk-forward' },
      ],
      manifest,
    } as never
    const storedDetails = {
      ...structuredClone(stored),
      artifacts: [
        ...structuredClone(stored.artifacts),
        {
          artifact_type: 'resolved_history',
          payload: {
            artifact_kind: 'resolved_history',
            summary: 'Resolved history built from 18/18 evaluation records spanning 2026-01-01T00:00:00.000Z -> 2026-04-01T00:00:00.000Z.',
            resolved_records: 18,
            source_summary: 'Resolved 18 local evaluation records from 4 stored runs.',
            first_cutoff_at: '2026-01-01T00:00:00.000Z',
            last_cutoff_at: '2026-04-01T00:00:00.000Z',
          },
        },
        {
          artifact_type: 'cost_model_report',
          payload: {
            artifact_kind: 'cost_model_report',
            summary: 'Cost model evaluated 18 resolved points; average net edge=142 bps, viable rate=0.666667.',
            total_points: 18,
            viable_point_count: 12,
            viable_point_rate: 0.666667,
            average_cost_bps: 39,
            average_net_edge_bps: 142,
          },
        },
        {
          artifact_type: 'walk_forward_report',
          payload: {
            artifact_kind: 'walk_forward_report',
            summary: 'Walk-forward ran 5 windows; mean brier improvement=0.015, mean net edge=142 bps.',
            total_points: 18,
            total_windows: 5,
            stable_window_rate: 0.8,
            mean_calibrated_brier_score: 0.166,
            mean_calibrated_log_loss: 0.421,
            mean_brier_improvement: 0.015,
            mean_log_loss_improvement: 0.022,
            mean_net_edge_bps: 142,
            promotion_ready: true,
            notes: ['stable_windows', 'net_edge_positive'],
          },
        },
      ],
    } as never

    mocks.listPredictionMarketRuns.mockReturnValue([storedSummary])
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(storedDetails)

    const runs = listPredictionMarketRunsService({
      workspaceId: 1,
      venue: 'polymarket',
      recommendation: undefined,
      limit: 10,
    })

    expect(runs).toHaveLength(1)
    expect(runs[0]).toMatchObject({
      run_id: 'run-list-validation-001',
      resolved_history_points: 18,
      resolved_history_source_summary: 'Resolved 18 local evaluation records from 4 stored runs.',
      cost_model_total_points: 18,
      cost_model_average_net_edge_bps: 142,
      walk_forward_total_points: 18,
      walk_forward_windows: 5,
      walk_forward_stable_window_rate: 0.8,
      walk_forward_mean_brier_improvement: 0.015,
      walk_forward_mean_log_loss_improvement: 0.022,
      walk_forward_mean_net_edge_bps: 142,
      walk_forward_promotion_ready: true,
      walk_forward_summary: {
        summary: 'Walk-forward ran 5 windows; mean brier improvement=0.015, mean net edge=142 bps.',
        sample_count: 18,
        window_count: 5,
        win_rate: 0.8,
        brier_score: 0.166,
        log_loss: 0.421,
        uplift_bps: 142,
        promotion_ready: true,
        notes: ['stable_windows', 'net_edge_positive'],
      },
    })
  })

  it('records the research pipeline trace in the runtime memory adapter when research is present', async () => {
    const snapshot = makeSnapshot()

    mocks.buildPolymarketSnapshot.mockResolvedValue(snapshot)
    mocks.listKalshiMarkets.mockRejectedValue(new Error('kalshi discovery offline'))

    const result = await advisePredictionMarket({
      venue: 'polymarket',
      market_id: snapshot.market.market_id,
      research_signals: [
        {
          signal_type: 'manual_note',
          headline: 'Desk thesis',
          note: 'Research-driven deep mode keeps the forecast lane active.',
          thesis_probability: 0.63,
          thesis_rationale: 'Desk evidence points to a modest yes edge.',
          captured_at: '2026-04-08T10:00:00.000Z',
          tags: ['desk', 'deep'],
          stance: 'supportive',
        },
      ],
      workspaceId: 1,
      actor: 'operator',
    })

    expect(result.research_memory).toMatchObject({
      provider_kind: 'memory',
      subject_id: `polymarket:${snapshot.market.market_id}:polymarket-research-pipeline`,
    })
    expect(result.research_sidecar?.synthesis.pipeline_trace.trace_id).toBeTruthy()
  })

  it('hydrates resolved history artifacts from the automatic local history source', async () => {
    const snapshot = makeSnapshot({
      market: makeDescriptor({
        market_id: 'BTC / Jun 2026',
        slug: 'btc-jun-2026',
        question: 'Will BTC finish June 2026 above 100k?',
      }),
    })
    mocks.buildPolymarketSnapshot.mockResolvedValue(snapshot)
    mocks.resolvePredictionMarketEvaluationHistory.mockReturnValue({
      evaluation_history: [
        {
          evaluation_id: 'eval-001',
          question_id: 'question-001',
          market_id: 'BTC / Jun 2026',
          venue: 'polymarket',
          cutoff_at: '2026-04-01T00:00:00.000Z',
          forecast_probability: 0.72,
          market_baseline_probability: 0.61,
          resolved_outcome: true,
          brier_score: 0.0784,
          log_loss: 0.328504,
          ece_bucket: '60_80',
          abstain_flag: false,
          basis: 'manual_thesis',
          comparator_id: 'candidate_manual_thesis',
          comparator_kind: 'candidate_model',
          comparator_role: 'candidate',
          pipeline_id: 'forecast-market',
          pipeline_version: 'baseline-v0',
        },
        {
          evaluation_id: 'eval-002',
          question_id: 'question-002',
          market_id: 'ETH / Jun 2026',
          venue: 'polymarket',
          cutoff_at: '2026-04-02T00:00:00.000Z',
          forecast_probability: 0.68,
          market_baseline_probability: 0.57,
          resolved_outcome: true,
          brier_score: 0.1024,
          log_loss: 0.385662,
          ece_bucket: '60_80',
          abstain_flag: false,
          basis: 'manual_thesis',
          comparator_id: 'candidate_manual_thesis',
          comparator_kind: 'candidate_model',
          comparator_role: 'candidate',
          pipeline_id: 'forecast-market',
          pipeline_version: 'baseline-v0',
        },
      ],
      source: 'stored_runs',
      source_summary: 'Resolved 2 local evaluation records from 1 stored run (same_category=2).',
      considered_runs: 1,
      used_runs: 1,
      same_market_records: 0,
      same_category_records: 2,
      same_venue_records: 0,
    })

    await advisePredictionMarket({
      workspaceId: 1,
      venue: 'polymarket',
      market_id: 'BTC / Jun 2026',
      actor: 'hardening-test',
    })

    const persistCall = mocks.persistPredictionMarketExecution.mock.calls[0]?.[0]
    expect(persistCall?.resolvedHistory).toMatchObject({
      artifact_kind: 'resolved_history',
      resolved_records: 2,
      source_summary: 'Resolved 2 local evaluation records from 1 stored run (same_category=2).',
    })
    expect(Array.isArray(persistCall?.resolvedHistory?.points)).toBe(true)
    expect(persistCall?.resolvedHistory?.points).toHaveLength(2)
    expect(mocks.computeConfigHash.mock.calls.some((call) => {
      const value = call.at(0)
      return (
        value != null
        && typeof value === 'object'
        && 'evaluation_history_source' in value
        && (value as Record<string, unknown>).evaluation_history_source === 'stored_runs'
      )
    })).toBe(true)
  })

  it('persists TimesFM sidecar artifacts on predict_deep requests', async () => {
    const snapshot = makeSnapshot({
      history: Array.from({ length: 24 }, (_, index) => ({
        timestamp: 1712534400 + (index * 3600),
        price: Number((0.45 + (index * 0.004)).toFixed(4)),
      })),
    })
    mocks.buildPolymarketSnapshot.mockResolvedValue(snapshot)
    mocks.runPredictionMarketTimesFMSidecar.mockReturnValue(makeTimesFMSidecar({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      question: snapshot.market.question,
    }))

    const result = await advisePredictionMarket({
      workspaceId: 1,
      venue: 'polymarket',
      market_id: snapshot.market.market_id,
      request_mode: 'predict_deep',
      actor: 'hardening-test',
    })

    const persistCall = mocks.persistPredictionMarketExecution.mock.calls.at(0)?.[0]

    expect(mocks.runPredictionMarketTimesFMSidecar).toHaveBeenCalledTimes(1)
    expect(persistCall?.timesfmSidecar).toMatchObject({
      sidecar_name: 'timesfm_sidecar',
      selected_lane: 'microstructure',
    })
    expect(result.prediction_run.timesfm_requested_mode).toBe('auto')
    expect(result.prediction_run.timesfm_selected_lane).toBe('microstructure')
    expect(result.prediction_run.timesfm_summary).toContain('timesfm:')
    expect(result.timesfm_sidecar).toMatchObject({
      selected_lane: 'microstructure',
    })
  })

  it('fails cleanly when TimesFM required mode has no ready lanes', async () => {
    const snapshot = makeSnapshot({
      history: Array.from({ length: 24 }, (_, index) => ({
        timestamp: 1712534400 + (index * 3600),
        price: Number((0.45 + (index * 0.004)).toFixed(4)),
      })),
    })
    mocks.buildPolymarketSnapshot.mockResolvedValue(snapshot)
    mocks.runPredictionMarketTimesFMSidecar.mockReturnValue(makeTimesFMSidecar({
      requested_mode: 'required',
      effective_mode: 'required',
      selected_lane: null,
      health: {
        healthy: false,
        status: 'blocked',
        backend: 'fixture',
        dependency_status: 'fixture_backend',
        issues: ['required_no_ready_lane'],
        summary: 'required mode produced no ready lanes',
      },
      lanes: {},
      summary: 'TimesFM unavailable',
    }))

    await expect(advisePredictionMarket({
      workspaceId: 1,
      venue: 'polymarket',
      market_id: snapshot.market.market_id,
      request_mode: 'predict_deep',
      timesfm_mode: 'required',
      actor: 'hardening-test',
    })).rejects.toMatchObject({
      code: 'timesfm_required_unavailable',
    })
  })
})
