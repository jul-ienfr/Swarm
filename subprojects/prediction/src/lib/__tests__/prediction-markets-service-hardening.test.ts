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

import {
  advisePredictionMarket,
  listPredictionMarketRuns as listPredictionMarketRunsService,
  replayPredictionMarketRun,
} from '@/lib/prediction-markets/service'
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
})
