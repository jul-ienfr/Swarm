import { describe, expect, it } from 'vitest'
import {
  buildPredictionMarketExecutionPathways,
} from '@/lib/prediction-markets/execution-pathways'
import {
  detectStrategyCandidates,
} from '@/lib/prediction-markets/strategy-engine'
import {
  buildPredictionMarketExecutionReadiness,
} from '@/lib/prediction-markets/execution-readiness'
import {
  evaluatePredictionMarketComplianceMatrix,
} from '@/lib/prediction-markets/compliance'
import {
  buildRecommendationPacket,
} from '@/lib/prediction-markets/service'
import {
  enrichPredictionMarketPreflightSummary,
} from '@/lib/prediction-markets/preflight-ops'
import {
  buildConservativePredictionMarketSizing,
} from '@/lib/prediction-markets/sizing'
import {
  evaluateCrossVenuePair,
  findCrossVenueMatches,
} from '@/lib/prediction-markets/cross-venue'
import {
  getPredictionMarketVenueStrategy,
} from '@/lib/prediction-markets/venue-strategy'
import {
  forecastPacketSchema,
  marketDescriptorSchema,
  marketSnapshotSchema,
  predictionMarketBudgetsSchema,
  resolutionPolicySchema,
  type MarketDescriptor,
  type MarketSnapshot,
  type PredictionMarketVenue,
  type PredictionMarketVenueType,
  venueCapabilitiesSchema,
  venueHealthSnapshotSchema,
} from '@/lib/prediction-markets/schemas'

function makeDescriptor(overrides: Partial<MarketDescriptor> = {}): MarketDescriptor {
  const marketId = overrides.market_id ?? 'strategy-engine-market'

  return marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: marketId,
    slug: marketId,
    question: 'Will the strategy engine stay stable by 2026-12-31?',
    outcomes: ['Yes', 'No'],
    active: true,
    closed: false,
    accepting_orders: true,
    restricted: false,
    liquidity_usd: 120_000,
    volume_usd: 1_200_000,
    volume_24h_usd: 65_000,
    best_bid: 0.48,
    best_ask: 0.5,
    last_trade_price: 0.49,
    tick_size: 0.01,
    min_order_size: 5,
    is_binary_yes_no: true,
    start_at: '2026-01-01T00:00:00.000Z',
    end_at: '2026-12-31T23:59:59.000Z',
    source_urls: [`https://example.com/${marketId}`],
    ...overrides,
  })
}

function makeSnapshot(market: MarketDescriptor): MarketSnapshot {
  return marketSnapshotSchema.parse({
    venue: market.venue,
    market,
    captured_at: '2026-04-08T00:00:00.000Z',
    yes_outcome_index: 0,
    yes_token_id: `${market.market_id}:yes`,
    yes_price: 0.49,
    no_price: 0.51,
    midpoint_yes: 0.49,
    best_bid_yes: 0.48,
    best_ask_yes: 0.5,
    spread_bps: 200,
    book: {
      token_id: `${market.market_id}:yes`,
      market_condition_id: `${market.market_id}:cond`,
      fetched_at: '2026-04-08T00:00:00.000Z',
      best_bid: 0.48,
      best_ask: 0.5,
      last_trade_price: 0.49,
      tick_size: 0.01,
      min_order_size: 5,
      bids: [{ price: 0.48, size: 500 }],
      asks: [{ price: 0.5, size: 450 }],
      depth_near_touch: 950,
    },
    history: [
      { timestamp: 1712534400, price: 0.47 },
      { timestamp: 1712538000, price: 0.49 },
    ],
    source_urls: market.source_urls,
  })
}

function makeResolutionPolicy(market: MarketDescriptor) {
  return resolutionPolicySchema.parse({
    market_id: market.market_id,
    venue: market.venue,
    status: 'eligible',
    manual_review_required: false,
    reasons: [],
    primary_sources: market.source_urls,
    evaluated_at: '2026-04-08T00:00:00.000Z',
  })
}

function makeForecast(market: MarketDescriptor) {
  return forecastPacketSchema.parse({
    market_id: market.market_id,
    venue: market.venue,
    basis: 'manual_thesis',
    probability_yes: 0.66,
    confidence: 0.62,
    rationale: 'Synthetic strategy test forecast.',
    evidence_refs: ['evidence:strategy-engine'],
    abstention_reason: 'manual_review',
    requires_manual_review: true,
    produced_at: '2026-04-08T00:00:00.000Z',
  })
}

function makeCapabilities(venue: PredictionMarketVenue, venueType: PredictionMarketVenueType) {
  return venueCapabilitiesSchema.parse({
    venue,
    venue_type: venueType,
    supports_discovery: true,
    supports_metadata: true,
    supports_orderbook: true,
    supports_trades: true,
    supports_positions: true,
    supports_execution: true,
    supports_websocket: true,
    supports_paper_mode: true,
    automation_constraints: [],
    rate_limit_notes: 'Synthetic strategy engine contract.',
    last_verified_at: '2026-04-08T00:00:00.000Z',
  })
}

function makeHealth(venue: PredictionMarketVenue) {
  return venueHealthSnapshotSchema.parse({
    venue,
    captured_at: '2026-04-08T00:00:00.000Z',
    health_score: 1,
    api_status: 'healthy',
    stream_status: 'healthy',
    staleness_ms: 0,
    degraded_mode: 'normal',
    incident_flags: [],
  })
}

function makeBudgets() {
  return predictionMarketBudgetsSchema.parse({
    fetch_latency_budget_ms: 4_000,
    snapshot_freshness_budget_ms: 4_000,
    decision_latency_budget_ms: 2_000,
    stream_reconnect_budget_ms: 4_000,
    cache_ttl_ms: 1_000,
    max_retries: 0,
    backpressure_policy: 'degrade-to-wait',
  })
}

function makeReadiness(venue: PredictionMarketVenue = 'polymarket') {
  const capabilities = makeCapabilities(venue, 'execution-equivalent')
  const health = makeHealth(venue)
  const budgets = makeBudgets()
  const complianceMatrix = evaluatePredictionMarketComplianceMatrix({
    venue,
    venue_type: 'execution-equivalent',
    capabilities: {
      supports_discovery: true,
      supports_metadata: true,
      supports_orderbook: true,
      supports_trades: true,
      supports_execution: true,
      supports_paper_mode: true,
      automation_constraints: [],
    },
    jurisdiction: 'us',
    account_type: 'trading',
    kyc_status: 'approved',
    api_key_present: true,
    trading_enabled: true,
  })

  return buildPredictionMarketExecutionReadiness({
    capabilities,
    health,
    budgets,
    compliance_matrix: complianceMatrix,
  })
}

describe('prediction markets strategy engine', () => {
  it('treats same-venue parity scans as manual-review-only and keeps them out of arbitrage candidacy', () => {
    const left = makeDescriptor({
      venue: 'polymarket',
      market_id: 'intramarket-left',
      slug: 'intramarket-left',
      question: 'Will the same venue parity scan stay blocked?',
    })
    const right = makeDescriptor({
      venue: 'polymarket',
      market_id: 'intramarket-right',
      slug: 'intramarket-right',
      question: 'Will the same venue parity scan stay blocked?',
    })

    const evaluation = evaluateCrossVenuePair({ left, right })
    const scanned = findCrossVenueMatches({
      markets: [left, right],
      includeManualReview: true,
    })

    expect(evaluation.compatible).toBe(false)
    expect(evaluation.mismatch_reasons).toContain('same_venue_pair')
    expect(evaluation.arbitrage_candidate).toBeNull()
    expect(scanned).toHaveLength(0)
  })

  it('keeps resolution-watch recommendations in defense-only wait mode and surfaces the anomaly flags', () => {
    const market = makeDescriptor()
    const snapshot = makeSnapshot(market)
    const resolutionPolicy = makeResolutionPolicy(market)
    const forecast = makeForecast(market)

    const recommendation = buildRecommendationPacket({
      snapshot,
      resolutionPolicy,
      forecast,
    })
    const pathways = buildPredictionMarketExecutionPathways({
      runId: 'run-strategy-engine-001',
      snapshot,
      resolutionPolicy,
      forecast,
      recommendation,
      executionReadiness: makeReadiness(snapshot.venue),
    })

    expect(recommendation.action).toBe('wait')
    expect(recommendation.side).toBeNull()
    expect(recommendation.risk_flags).toEqual(expect.arrayContaining([
      'forecast_abstention',
      'forecast_manual_review',
    ]))
    expect(recommendation.why_not_now).toEqual(expect.arrayContaining([
      'Forecast abstention policy is holding this packet at manual_review.',
      'Forecast still requires manual review before it can claim an executable edge.',
    ]))
    expect(recommendation.watch_conditions.length).toBeGreaterThan(0)
    expect(pathways.highest_actionable_mode).toBeNull()
    expect(pathways.pathways.every((pathway) => pathway.status === 'inactive')).toBe(true)
    expect(pathways.summary).toContain('execution pathways remain inactive')
  })

  it('downgrades stale latency references in preflight summaries when the edge and microstructure disagree', () => {
    const preflight = enrichPredictionMarketPreflightSummary(
      { summary: 'baseline preflight summary' },
      {
        venue_strategy: getPredictionMarketVenueStrategy('kalshi'),
        cross_venue: {
          executable_edge: {
            notes: [
              'stale_edge_expired:false',
              'stale_edge_penalty_bps:33',
              'transfer_latency_penalty_bps:18',
            ],
            executable: true,
            executable_edge_bps: 120,
            gross_spread_bps: 200,
            fee_bps: 5,
            slippage_bps: 10,
            hedge_risk_bps: 15,
          },
          arbitrage_candidate: null,
        },
        microstructure_summary: {
          recommended_mode: 'wait',
          worst_case_severity: 'critical',
          executable_deterioration_bps: 47,
          execution_quality_score: 0.19,
        },
      },
    )

    expect(preflight.stale_edge_status).toMatchObject({
      state: 'stale',
      expired: false,
      source: 'microstructure',
    })
    expect(preflight.stale_edge_status.reasons).toEqual(expect.arrayContaining([
      'stale_edge_expired:false',
      'stale_edge_penalty_bps:33',
      'microstructure:wait:critical',
    ]))
    expect(preflight.penalties).toMatchObject({
      stale_edge_penalty_bps: 33,
      microstructure_deterioration_bps: 47,
      microstructure_execution_quality_score: 0.19,
    })
  })

  it('keeps negative correlation basket sizing positive, bounded, and shape-safe', () => {
    const sizing = buildConservativePredictionMarketSizing({
      baseSizeUsd: 1_000,
      maxSizeUsd: 300,
      signals: {
        confidence: 0.72,
        calibration_ece: 0.12,
        liquidity_usd: 40_000,
        depth_near_touch: 2_500,
        portfolio_correlation: -0.8,
      },
    })

    expect(sizing.base_size_usd).toBe(1_000)
    expect(sizing.size_usd).toBeGreaterThan(0)
    expect(sizing.size_usd).toBeLessThanOrEqual(300)
    expect(sizing.factors.portfolio_correlation_factor).toBeLessThan(1)
    expect(sizing.notes).toEqual(expect.arrayContaining([
      'Portfolio correlation 80% is elevated.',
    ]))
  })

  it('suppresses maker spread capture when quote freshness is stale enough to invite adverse selection', () => {
    const market = makeDescriptor({
      market_id: 'maker-spread-capture-market',
      slug: 'maker-spread-capture-market',
      best_bid: 0.44,
      best_ask: 0.5,
      last_trade_price: 0.47,
    })
    const snapshot = marketSnapshotSchema.parse({
      ...makeSnapshot(market),
      yes_price: 0.47,
      midpoint_yes: 0.47,
      best_bid_yes: 0.44,
      best_ask_yes: 0.5,
      spread_bps: 600,
      book: {
        ...makeSnapshot(market).book!,
        best_bid: 0.44,
        best_ask: 0.5,
        last_trade_price: 0.47,
      },
    })

    const freshCandidates = detectStrategyCandidates({
      snapshot,
      as_of_at: '2026-04-08T00:00:05.000Z',
    })
    const staleCandidates = detectStrategyCandidates({
      snapshot,
      as_of_at: '2026-04-08T00:10:00.000Z',
    })

    const freshMakerCandidate = freshCandidates.find((candidate) => candidate.kind === 'maker_spread_capture')
    expect(freshMakerCandidate).toBeTruthy()
    expect(freshMakerCandidate?.reasons).toEqual(expect.arrayContaining([
      'maker_quote_freshness_budget_ms:15000',
      'maker_quote_state:guarded',
      'freshness_state:fresh',
      'latency_state:fresh',
    ]))
    expect(freshMakerCandidate?.metrics).toMatchObject({
      maker_quote_freshness_budget_ms: 15_000,
      maker_quote_state: 'guarded',
      freshness_state: 'fresh',
      latency_state: 'fresh',
    })
    expect(staleCandidates.some((candidate) => candidate.kind === 'maker_spread_capture')).toBe(false)
  })
})
