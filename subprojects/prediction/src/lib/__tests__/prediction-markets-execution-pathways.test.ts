import { describe, expect, it } from 'vitest'
import { buildPredictionMarketExecutionPathways } from '@/lib/prediction-markets/execution-pathways'
import { buildPredictionMarketExecutionReadiness } from '@/lib/prediction-markets/execution-readiness'
import { evaluatePredictionMarketComplianceMatrix } from '@/lib/prediction-markets/compliance'
import { type CapitalLedgerSourceInput } from '@/lib/prediction-markets/capital-ledger'
import {
  evaluateCrossVenuePair,
  type CrossVenueEvaluation,
  type CrossVenueOpsSummary,
} from '@/lib/prediction-markets/cross-venue'
import { reconcileCapitalLedger } from '@/lib/prediction-markets/reconciliation'
import { buildMicrostructureLabReport } from '@/lib/prediction-markets/microstructure-lab'
import {
  forecastPacketSchema,
  marketDescriptorSchema,
  marketRecommendationPacketSchema,
  marketSnapshotSchema,
  predictionMarketBudgetsSchema,
  resolutionPolicySchema,
  tradeIntentSchema,
  venueCapabilitiesSchema,
  venueHealthSnapshotSchema,
} from '@/lib/prediction-markets/schemas'

function makeCapabilities() {
  return venueCapabilitiesSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    supports_discovery: true,
    supports_metadata: true,
    supports_orderbook: true,
    supports_trades: true,
    supports_positions: true,
    supports_execution: true,
    supports_websocket: true,
    supports_paper_mode: true,
    automation_constraints: [],
    rate_limit_notes: 'synthetic execution pathways contract',
    last_verified_at: '2026-04-08T00:00:00.000Z',
  })
}

function makeHealth() {
  return venueHealthSnapshotSchema.parse({
    venue: 'polymarket',
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
    venue: 'polymarket',
    fetch_latency_budget_ms: 4_000,
    snapshot_freshness_budget_ms: 4_000,
    decision_latency_budget_ms: 2_000,
    stream_reconnect_budget_ms: 4_000,
    cache_ttl_ms: 1_000,
    max_retries: 0,
    backpressure_policy: 'degrade-to-wait',
  })
}

function makeMarket() {
  return marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: 'mkt-pathways-001',
    slug: 'mkt-pathways-001',
    question: 'Will execution pathways stay deterministic?',
    outcomes: ['Yes', 'No'],
    active: true,
    closed: false,
    accepting_orders: true,
    restricted: false,
    liquidity_usd: 100_000,
    volume_usd: 850_000,
    volume_24h_usd: 45_000,
    best_bid: 0.48,
    best_ask: 0.5,
    last_trade_price: 0.49,
    tick_size: 0.01,
    min_order_size: 5,
    is_binary_yes_no: true,
    end_at: '2026-12-31T23:59:59.000Z',
    source_urls: ['https://example.com/mkt-pathways-001'],
  })
}

function makeSnapshot() {
  const market = makeMarket()
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
    source_urls: [
      'https://example.com/mkt-pathways-001',
      'https://example.com/mkt-pathways-001/book',
    ],
  })
}

function makeResolutionPolicy() {
  const snapshot = makeSnapshot()
  return resolutionPolicySchema.parse({
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    status: 'eligible',
    manual_review_required: false,
    reasons: [],
    primary_sources: snapshot.source_urls,
    evaluated_at: '2026-04-08T00:00:00.000Z',
  })
}

function makeForecast() {
  const snapshot = makeSnapshot()
  return forecastPacketSchema.parse({
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    basis: 'manual_thesis',
    probability_yes: 0.71,
    confidence: 0.64,
    rationale: 'Synthetic forecast for execution pathways.',
    evidence_refs: ['evidence:pathways'],
    produced_at: '2026-04-08T00:00:00.000Z',
  })
}

function makeRecommendation(action: 'bet' | 'wait' | 'no_trade', side: 'yes' | 'no' | null = 'yes') {
  const snapshot = makeSnapshot()
  return marketRecommendationPacketSchema.parse({
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    action,
    side: action === 'bet' ? side : null,
    confidence: 0.64,
    fair_value_yes: 0.71,
    market_price_yes: 0.49,
    market_bid_yes: 0.48,
    market_ask_yes: 0.5,
    edge_bps: action === 'bet' ? 2200 : 0,
    spread_bps: 200,
    reasons: ['synthetic recommendation'],
    risk_flags: [],
    produced_at: '2026-04-08T00:00:00.000Z',
  })
}

function makeComplianceMatrix() {
  return evaluatePredictionMarketComplianceMatrix({
    venue: 'polymarket',
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
}

function makeCapitalLedger(overrides: Partial<CapitalLedgerSourceInput> = {}): CapitalLedgerSourceInput {
  return {
    venue: 'polymarket',
    captured_at: '2026-04-08T00:00:00.000Z',
    cash_available: 2_000,
    cash_locked: 100,
    collateral_currency: 'USD',
    open_exposure_usd: 150,
    withdrawable_amount: 1_850,
    transfer_latency_estimate_ms: 15_000,
    ...overrides,
  } satisfies CapitalLedgerSourceInput
}

function makeEmptyCrossVenueSummary(): CrossVenueOpsSummary {
  return {
    total_pairs: 0,
    opportunity_type_counts: {
      comparison_only: 0,
      relative_value: 0,
      cross_venue_signal: 0,
      true_arbitrage: 0,
    },
    compatible: [],
    manual_review: [],
    comparison_only: [],
    blocking_reasons: [],
    highest_confidence_candidate: null,
  }
}

function makeManualReviewEvaluation(): CrossVenueEvaluation {
  return {
    canonical_event_id: 'evt-1',
    canonical_event_key: 'evt-1',
    compatible: false,
    confidence_score: 0.6,
    opportunity_type: 'comparison_only',
    market_equivalence_proof: {
      schema_version: '1.0.0',
      proof_id: 'proof:evt-1',
      canonical_event_id: 'evt-1',
      left_market_ref: { venue: 'polymarket', market_id: 'mkt-pathways-001' },
      right_market_ref: { venue: 'kalshi', market_id: 'k-pathways-001' },
      proof_status: 'partial',
      resolution_compatibility_score: 0.5,
      payout_compatibility_score: 1,
      currency_compatibility_score: 1,
      timing_compatibility_score: 0.5,
      manual_review_required: true,
      mismatch_reasons: ['time_horizon_mismatch'],
      notes: ['time_horizon_mismatch'],
    },
    executable_edge: null,
    mismatch_reasons: ['time_horizon_mismatch'],
    match: {
      schema_version: '1.0.0',
      canonical_event_id: 'evt-1',
      left_market_ref: { venue: 'polymarket', market_id: 'mkt-pathways-001' },
      right_market_ref: { venue: 'kalshi', market_id: 'k-pathways-001' },
      semantic_similarity_score: 0.9,
      resolution_compatibility_score: 0.5,
      payout_compatibility_score: 1,
      currency_compatibility_score: 1,
      manual_review_required: true,
      notes: ['time_horizon_mismatch'],
    },
    arbitrage_candidate: null,
  }
}

function makeShadowArbitrageCrossVenueSummary(): CrossVenueOpsSummary {
  const polymarket = marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: 'shadow-arb-poly',
    slug: 'shadow-arb-poly',
    question: 'Will the shadow arbitrage edge remain exploitable?',
    outcomes: ['Yes', 'No'],
    active: true,
    closed: false,
    accepting_orders: true,
    restricted: false,
    liquidity_usd: 150_000,
    volume_usd: 900_000,
    volume_24h_usd: 60_000,
    best_bid: 0.43,
    best_ask: 0.44,
    last_trade_price: 0.435,
    tick_size: 0.01,
    min_order_size: 5,
    is_binary_yes_no: true,
    end_at: '2026-12-31T23:59:59.000Z',
    source_urls: ['https://example.com/shadow-arb-poly'],
  })
  const kalshi = marketDescriptorSchema.parse({
    venue: 'kalshi',
    venue_type: 'execution-equivalent',
    market_id: 'shadow-arb-kalshi',
    slug: 'shadow-arb-kalshi',
    question: 'Will the shadow arbitrage edge remain exploitable?',
    outcomes: ['Yes', 'No'],
    active: true,
    closed: false,
    accepting_orders: true,
    restricted: false,
    liquidity_usd: 150_000,
    volume_usd: 900_000,
    volume_24h_usd: 60_000,
    best_bid: 0.58,
    best_ask: 0.59,
    last_trade_price: 0.585,
    tick_size: 0.01,
    min_order_size: 5,
    is_binary_yes_no: true,
    end_at: '2026-12-31T23:59:59.000Z',
    source_urls: ['https://example.com/shadow-arb-kalshi'],
  })

  const leftSnapshot = marketSnapshotSchema.parse({
    venue: polymarket.venue,
    market: polymarket,
    captured_at: '2026-04-08T00:00:00.000Z',
    yes_outcome_index: 0,
    yes_token_id: `${polymarket.market_id}:yes`,
    yes_price: 0.435,
    no_price: 0.565,
    midpoint_yes: 0.435,
    best_bid_yes: 0.43,
    best_ask_yes: 0.44,
    spread_bps: 100,
    book: {
      token_id: `${polymarket.market_id}:yes`,
      market_condition_id: `${polymarket.market_id}:cond`,
      fetched_at: '2026-04-08T00:00:00.000Z',
      best_bid: 0.43,
      best_ask: 0.44,
      last_trade_price: 0.435,
      tick_size: 0.01,
      min_order_size: 5,
      bids: [{ price: 0.43, size: 500 }],
      asks: [{ price: 0.44, size: 450 }],
      depth_near_touch: 1_200,
    },
    history: [],
    source_urls: polymarket.source_urls,
  })

  const rightSnapshot = marketSnapshotSchema.parse({
    venue: kalshi.venue,
    market: kalshi,
    captured_at: '2026-04-08T00:00:00.000Z',
    yes_outcome_index: 0,
    yes_token_id: `${kalshi.market_id}:yes`,
    yes_price: 0.585,
    no_price: 0.415,
    midpoint_yes: 0.585,
    best_bid_yes: 0.58,
    best_ask_yes: 0.59,
    spread_bps: 100,
    book: {
      token_id: `${kalshi.market_id}:yes`,
      market_condition_id: `${kalshi.market_id}:cond`,
      fetched_at: '2026-04-08T00:00:00.000Z',
      best_bid: 0.58,
      best_ask: 0.59,
      last_trade_price: 0.585,
      tick_size: 0.01,
      min_order_size: 5,
      bids: [{ price: 0.58, size: 520 }],
      asks: [{ price: 0.59, size: 460 }],
      depth_near_touch: 1_100,
    },
    history: [],
    source_urls: kalshi.source_urls,
  })

  const evaluation = evaluateCrossVenuePair({
    left: polymarket,
    right: kalshi,
    leftSnapshot,
    rightSnapshot,
    asOfAt: '2026-04-08T00:00:00.000Z',
  })

  if (!evaluation.arbitrage_candidate) {
    throw new Error('expected an executable arbitrage candidate in the test fixture')
  }

  return {
    total_pairs: 1,
    opportunity_type_counts: {
      comparison_only: 0,
      relative_value: 0,
      cross_venue_signal: 0,
      true_arbitrage: 1,
    },
    compatible: [evaluation],
    manual_review: [],
    comparison_only: [],
    blocking_reasons: [],
    highest_confidence_candidate: evaluation.arbitrage_candidate,
  }
}

describe('prediction markets execution pathways', () => {
  it('keeps live actionable when readiness, capital, and reconciliation are healthy', () => {
    const capitalLedger = makeCapitalLedger()
    const reconciliation = reconcileCapitalLedger({
      theoretical: capitalLedger,
      observed: capitalLedger,
    })
    const readiness = buildPredictionMarketExecutionReadiness({
      capabilities: makeCapabilities(),
      health: makeHealth(),
      budgets: makeBudgets(),
      compliance_matrix: makeComplianceMatrix(),
      capital_ledger: capitalLedger,
      reconciliation,
    })

    const pathways = buildPredictionMarketExecutionPathways({
      runId: 'run-pathways-001',
      snapshot: makeSnapshot(),
      resolutionPolicy: makeResolutionPolicy(),
      forecast: makeForecast(),
      recommendation: makeRecommendation('bet', 'yes'),
      executionReadiness: {
        ...readiness,
        cross_venue_summary: makeEmptyCrossVenueSummary(),
      },
    })

    expect(pathways.highest_actionable_mode).toBe('live')
    expect(pathways.pathways.find((pathway) => pathway.mode === 'live')).toMatchObject({
      actionable: true,
      status: 'ready',
    })
    expect(pathways.pathways.find((pathway) => pathway.mode === 'live')?.trade_intent_preview).toMatchObject({
      run_id: 'run-pathways-001',
      side: 'yes',
      time_in_force: 'ioc',
    })
    expect(pathways.pathways.find((pathway) => pathway.mode === 'live')?.canonical_trade_intent_preview).toMatchObject({
      run_id: 'run-pathways-001',
      side: 'yes',
      time_in_force: 'ioc',
    })
    expect(pathways.pathways.find((pathway) => pathway.mode === 'paper')?.trade_intent_preview?.size_usd).toBeGreaterThan(
      pathways.pathways.find((pathway) => pathway.mode === 'shadow')?.trade_intent_preview?.size_usd ?? 0,
    )
    expect(pathways.pathways.find((pathway) => pathway.mode === 'shadow')?.trade_intent_preview?.size_usd).toBeGreaterThan(
      pathways.pathways.find((pathway) => pathway.mode === 'live')?.trade_intent_preview?.size_usd ?? 0,
    )
    expect(pathways.pathways.find((pathway) => pathway.mode === 'paper')?.trade_intent_preview?.size_usd).toBeLessThanOrEqual(60)
    expect(pathways.pathways.find((pathway) => pathway.mode === 'shadow')?.trade_intent_preview?.size_usd).toBeLessThanOrEqual(50)
    expect(pathways.pathways.find((pathway) => pathway.mode === 'live')?.trade_intent_preview?.size_usd).toBeLessThanOrEqual(25)
    expect(pathways.pathways.find((pathway) => pathway.mode === 'shadow')?.sizing_signal).toMatchObject({
      source: 'trade_intent_preview',
    })
    expect(pathways.pathways.find((pathway) => pathway.mode === 'live')?.trade_intent_preview?.notes ?? '').toContain(
      'liquidity/depth-aware conservative sizing',
    )
    expect(pathways.pathways.find((pathway) => pathway.mode === 'live')?.trade_intent_preview?.notes ?? '').toContain(
      'Calibration ECE',
    )
    expect(pathways.pathways.find((pathway) => pathway.mode === 'paper')?.sizing_summary).toMatchObject({
      source: 'capital_ledger',
    })
    expect(pathways.pathways.find((pathway) => pathway.mode === 'live')?.sizing_summary?.recommended_size_usd).toBe(
      pathways.pathways.find((pathway) => pathway.mode === 'live')?.trade_intent_preview?.size_usd,
    )
    expect(pathways.summary).toContain('live')
  })

  it('caps execution at paper when manual review and missing capital block higher modes', () => {
    const readiness = buildPredictionMarketExecutionReadiness({
      capabilities: {
        ...makeCapabilities(),
        supports_execution: false,
        automation_constraints: ['read-only advisory mode only'],
      },
      health: makeHealth(),
      budgets: makeBudgets(),
      compliance_matrix: makeComplianceMatrix(),
    })

    const pathways = buildPredictionMarketExecutionPathways({
      runId: 'run-pathways-002',
      snapshot: makeSnapshot(),
      resolutionPolicy: resolutionPolicySchema.parse({
        ...makeResolutionPolicy(),
        manual_review_required: true,
        reasons: ['manual review pending'],
      }),
      forecast: makeForecast(),
      recommendation: makeRecommendation('bet', 'no'),
      executionReadiness: {
        ...readiness,
        cross_venue_summary: {
          ...makeEmptyCrossVenueSummary(),
          total_pairs: 1,
          manual_review: [makeManualReviewEvaluation()],
          comparison_only: [],
          blocking_reasons: ['time_horizon_mismatch'],
          highest_confidence_candidate: null,
        },
      },
    })

    expect(pathways.highest_actionable_mode).toBe('paper')
    expect(pathways.pathways.find((pathway) => pathway.mode === 'paper')).toMatchObject({
      actionable: true,
    })
    expect(pathways.pathways.find((pathway) => pathway.mode === 'paper')?.trade_intent_preview?.size_usd).toBe(100)
    expect(pathways.pathways.find((pathway) => pathway.mode === 'paper')?.sizing_summary).toMatchObject({
      source: 'default',
      recommended_size_usd: 100,
    })
    expect(pathways.pathways.find((pathway) => pathway.mode === 'shadow')).toMatchObject({
      actionable: false,
      status: 'blocked',
      blockers: expect.arrayContaining([
        'manual_review_required_for_execution',
        'capital_ledger_unavailable',
      ]),
    })
    expect(pathways.pathways.find((pathway) => pathway.mode === 'live')).toMatchObject({
      actionable: false,
      status: 'blocked',
      blockers: expect.arrayContaining([
        'manual_review_required_for_execution',
        'capital_ledger_unavailable',
      ]),
    })
  })

  it('adds canonical shadow arbitrage and sizing signals on the shadow pathway when an exploitable edge exists', () => {
    const capitalLedger = makeCapitalLedger()
    const reconciliation = reconcileCapitalLedger({
      theoretical: capitalLedger,
      observed: capitalLedger,
    })
    const microstructureSnapshot = makeSnapshot()
    const microstructureRecommendation = makeRecommendation('bet', 'yes')
    const microstructureLab = buildMicrostructureLabReport({
      snapshot: microstructureSnapshot,
      recommendation: microstructureRecommendation,
      trade_intent: tradeIntentSchema.parse({
        intent_id: 'shadow-arb-trade-intent',
        run_id: 'run-pathways-shadow-arb',
        venue: microstructureSnapshot.venue,
        market_id: microstructureSnapshot.market.market_id,
        side: 'yes',
        size_usd: 100,
        limit_price: 0.5,
        max_slippage_bps: 40,
        max_unhedged_leg_ms: 2_000,
        time_in_force: 'day',
        forecast_ref: 'forecast:shadow-arb-market:2026-04-08T00:00:00.000Z',
        risk_checks_passed: true,
        created_at: '2026-04-08T00:00:00.000Z',
      }),
      generated_at: '2026-04-08T00:00:00.000Z',
    })
    const readiness = buildPredictionMarketExecutionReadiness({
      capabilities: makeCapabilities(),
      health: makeHealth(),
      budgets: makeBudgets(),
      compliance_matrix: makeComplianceMatrix(),
      capital_ledger: capitalLedger,
      reconciliation,
    })

    const pathways = buildPredictionMarketExecutionPathways({
      runId: 'run-pathways-shadow-arb',
      snapshot: makeSnapshot(),
      resolutionPolicy: makeResolutionPolicy(),
      forecast: makeForecast(),
      recommendation: makeRecommendation('bet', 'yes'),
      executionReadiness: {
        ...readiness,
        cross_venue_summary: makeShadowArbitrageCrossVenueSummary(),
        microstructure_lab: microstructureLab,
      },
    })

    const shadowPathway = pathways.pathways.find((pathway) => pathway.mode === 'shadow')
    expect(shadowPathway?.trade_intent_preview?.size_usd).toBe(shadowPathway?.sizing_summary?.recommended_size_usd)
    expect(shadowPathway?.canonical_trade_intent_preview?.size_usd).toBe(shadowPathway?.sizing_signal?.canonical_size_usd)
    expect(shadowPathway?.canonical_trade_intent_preview?.size_usd).toBeLessThanOrEqual(
      shadowPathway?.trade_intent_preview?.size_usd ?? Number.POSITIVE_INFINITY,
    )
    expect(shadowPathway?.shadow_arbitrage_signal).toMatchObject({
      read_only: true,
      failure_case_count: 3,
    })
    expect(shadowPathway?.shadow_arbitrage_signal?.base_executable_edge_bps).toBeGreaterThan(0)
    expect(shadowPathway?.sizing_signal?.source).toBe('trade_intent_preview+shadow_arbitrage')
    expect(shadowPathway?.sizing_signal?.preview_size_usd).toBe(shadowPathway?.trade_intent_preview?.size_usd)
    expect(shadowPathway?.sizing_signal?.shadow_recommended_size_usd).toBe(
      shadowPathway?.shadow_arbitrage_signal?.recommended_size_usd,
    )
    expect(shadowPathway?.sizing_signal?.canonical_size_usd).toBe(
      Math.min(
        shadowPathway?.trade_intent_preview?.size_usd ?? Number.POSITIVE_INFINITY,
        shadowPathway?.shadow_arbitrage_signal?.recommended_size_usd ?? Number.POSITIVE_INFINITY,
      ),
    )
    if (
      (shadowPathway?.canonical_trade_intent_preview?.size_usd ?? Number.POSITIVE_INFINITY) <
      (shadowPathway?.trade_intent_preview?.size_usd ?? Number.POSITIVE_INFINITY)
    ) {
      expect(shadowPathway?.canonical_trade_intent_preview?.notes ?? '').toContain(
        'Canonical execution sizing caps preview size',
      )
    }
    expect(pathways.pathways.find((pathway) => pathway.mode === 'paper')?.shadow_arbitrage_signal).toBeNull()
    expect(pathways.pathways.find((pathway) => pathway.mode === 'live')?.shadow_arbitrage_signal).toBeNull()
  })

  it('keeps all execution pathways inactive for wait recommendations', () => {
    const readiness = buildPredictionMarketExecutionReadiness({
      capabilities: makeCapabilities(),
      health: makeHealth(),
      budgets: makeBudgets(),
      compliance_matrix: makeComplianceMatrix(),
      capital_ledger: makeCapitalLedger(),
    })

    const pathways = buildPredictionMarketExecutionPathways({
      runId: 'run-pathways-003',
      snapshot: makeSnapshot(),
      resolutionPolicy: makeResolutionPolicy(),
      forecast: makeForecast(),
      recommendation: makeRecommendation('wait'),
      executionReadiness: readiness,
    })

    expect(pathways.highest_actionable_mode).toBeNull()
    expect(pathways.pathways.every((pathway) => pathway.status === 'inactive')).toBe(true)
    expect(pathways.summary).toContain('inactive')
  })
})
