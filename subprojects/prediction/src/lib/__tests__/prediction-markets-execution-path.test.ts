import { describe, expect, it } from 'vitest'
import { reconcileCapitalLedger } from '@/lib/prediction-markets/reconciliation'
import { type CapitalLedgerSourceInput } from '@/lib/prediction-markets/capital-ledger'
import { buildPredictionMarketExecutionReadiness } from '@/lib/prediction-markets/execution-readiness'
import { projectPredictionMarketExecutionPath } from '@/lib/prediction-markets/execution-path'
import { evaluateCrossVenuePair } from '@/lib/prediction-markets/cross-venue'
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
import { evaluatePredictionMarketComplianceMatrix } from '@/lib/prediction-markets/compliance'
import { type CrossVenueOpsSummary } from '@/lib/prediction-markets/cross-venue'

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
    rate_limit_notes: 'execution projection test fixture',
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
    market_id: 'mkt-execution-path-001',
    slug: 'mkt-execution-path-001',
    question: 'Will execution path projection stay aligned?',
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
    source_urls: ['https://example.com/mkt-execution-path-001'],
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
      'https://example.com/mkt-execution-path-001',
      'https://example.com/mkt-execution-path-001/book',
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
    rationale: 'Synthetic forecast for execution projection.',
    evidence_refs: ['evidence:execution-path'],
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
    leftSnapshot: leftSnapshot,
    rightSnapshot: rightSnapshot,
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

describe('prediction market execution projection', () => {
  it('projects live when readiness is healthy and the recommendation is a bet', () => {
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

    const projection = projectPredictionMarketExecutionPath({
      run_id: 'run-execution-path-001',
      recommendation: makeRecommendation('bet', 'yes'),
      execution_readiness: readiness,
    })

    expect(projection).toMatchObject({
      gate_name: 'execution_projection',
      preflight_only: true,
      requested_path: 'live',
      selected_path: 'live',
      selected_edge_bucket: 'forecast_alpha',
      verdict: 'allowed',
      manual_review_required: false,
      ttl_ms: 30_000,
      generated_at: '2026-04-08T00:00:00.000Z',
      expires_at: '2026-04-08T00:00:30.000Z',
      eligible_paths: ['paper', 'shadow', 'live'],
    })
    expect(projection.projected_paths.live).toMatchObject({
      status: 'ready',
      allowed: true,
      blockers: [],
      edge_bucket: 'forecast_alpha',
      pre_trade_gate: expect.objectContaining({
        gate_name: 'hard_no_trade',
        verdict: 'pass',
        edge_bucket: 'forecast_alpha',
      }),
    })
    expect(projection.selected_pre_trade_gate).toMatchObject({
      gate_name: 'hard_no_trade',
      verdict: 'pass',
      edge_bucket: 'forecast_alpha',
    })
    expect(projection.projected_paths.live.simulation.expected_fill_confidence).toBeCloseTo(0.68, 2)
    expect(projection.projected_paths.live.simulation.expected_slippage_bps).toBe(114)
    expect(projection.projected_paths.live.simulation.stale_quote_risk).toBe('high')
    expect(projection.projected_paths.live.simulation.quote_age_ms).toBe(0)
    expect(projection.projected_paths.live.trade_intent_preview).toMatchObject({
      run_id: 'run-execution-path-001',
      side: 'yes',
      time_in_force: 'ioc',
    })
    expect(projection.projected_paths.paper.canonical_trade_intent_preview).toMatchObject({
      size_usd: projection.projected_paths.paper.trade_intent_preview?.size_usd,
      time_in_force: 'day',
    })
    expect(projection.projected_paths.shadow.canonical_trade_intent_preview).toMatchObject({
      size_usd: projection.projected_paths.shadow.trade_intent_preview?.size_usd,
      time_in_force: 'ioc',
    })
    expect(projection.projected_paths.live.canonical_trade_intent_preview).toMatchObject({
      size_usd: projection.projected_paths.live.trade_intent_preview?.size_usd,
      time_in_force: 'ioc',
    })
    expect(projection.projected_paths.paper.sizing_signal).toMatchObject({
      preview_size_usd: 100,
      canonical_size_usd: 100,
      source: 'trade_intent_preview',
    })
    expect(projection.projected_paths.shadow.sizing_signal).toMatchObject({
      preview_size_usd: 50,
      canonical_size_usd: 50,
      source: 'trade_intent_preview',
    })
    expect(projection.projected_paths.live.sizing_signal).toMatchObject({
      preview_size_usd: 25,
      canonical_size_usd: 25,
      source: 'trade_intent_preview',
    })
    expect(projection.projected_paths.shadow.shadow_arbitrage_signal).toBeNull()
    expect(projection.projected_paths.paper.simulation).toMatchObject({
      expected_fill_confidence: 0.97,
      expected_slippage_bps: 24,
      stale_quote_risk: 'low',
      quote_age_ms: 0,
    })
    expect(projection.projected_paths.shadow.simulation).toMatchObject({
      expected_fill_confidence: 0.85,
      expected_slippage_bps: 64,
      stale_quote_risk: 'medium',
      quote_age_ms: 0,
    })
    expect(projection.blocking_reasons).toEqual([])
    expect(projection.downgrade_reasons).toEqual([])
  })

  it('widens the microstructure signal across paper, shadow, and live when the quote is older and the spread is wider', () => {
    const capitalLedger = makeCapitalLedger()
    const reconciliation = reconcileCapitalLedger({
      theoretical: capitalLedger,
      observed: capitalLedger,
    })
    const readiness = buildPredictionMarketExecutionReadiness({
      capabilities: makeCapabilities(),
      health: venueHealthSnapshotSchema.parse({
        ...makeHealth(),
        staleness_ms: 1_500,
      }),
      budgets: makeBudgets(),
      compliance_matrix: makeComplianceMatrix(),
      capital_ledger: capitalLedger,
      reconciliation,
    })

    const projection = projectPredictionMarketExecutionPath({
      run_id: 'run-execution-path-006',
      recommendation: marketRecommendationPacketSchema.parse({
        ...makeRecommendation('bet', 'yes'),
        spread_bps: 600,
      }),
      execution_readiness: readiness,
    })

    expect(projection.projected_paths.paper).toMatchObject({
      status: 'ready',
      allowed: true,
    })
    expect(projection.projected_paths.paper.simulation).toMatchObject({
      expected_fill_confidence: 0.97,
      expected_slippage_bps: 72,
      stale_quote_risk: 'low',
      quote_age_ms: 1_500,
    })
    expect(projection.projected_paths.shadow.simulation).toMatchObject({
      expected_fill_confidence: 0.85,
      expected_slippage_bps: 184,
      stale_quote_risk: 'medium',
      quote_age_ms: 1_500,
    })
    expect(projection.projected_paths.live.simulation).toMatchObject({
      expected_fill_confidence: 0.6799999999999999,
      expected_slippage_bps: 306,
      stale_quote_risk: 'high',
      quote_age_ms: 1_500,
    })
    expect(projection.projected_paths.paper.trade_intent_preview?.time_in_force).toBe('day')
    expect(projection.projected_paths.shadow.trade_intent_preview?.time_in_force).toBe('ioc')
    expect(projection.projected_paths.live.trade_intent_preview?.time_in_force).toBe('ioc')
    expect(projection.projected_paths.paper.simulation.expected_slippage_bps).toBeLessThan(
      projection.projected_paths.shadow.simulation.expected_slippage_bps,
    )
    expect(projection.projected_paths.shadow.simulation.expected_slippage_bps).toBeLessThan(
      projection.projected_paths.live.simulation.expected_slippage_bps,
    )
    expect(projection.projected_paths.paper.simulation.expected_fill_confidence).toBeGreaterThan(
      projection.projected_paths.shadow.simulation.expected_fill_confidence,
    )
    expect(projection.projected_paths.shadow.simulation.expected_fill_confidence).toBeGreaterThan(
      projection.projected_paths.live.simulation.expected_fill_confidence,
    )
  })

  it('falls back to shadow when live is blocked by capital pressure and reconciliation drift', () => {
    const capitalLedger = makeCapitalLedger({
      cash_available: 500,
      cash_locked: 0,
      open_exposure_usd: 480,
      withdrawable_amount: 500,
    })
    const reconciliation = reconcileCapitalLedger({
      theoretical: makeCapitalLedger({
        cash_available: 540,
        cash_locked: 0,
        open_exposure_usd: 460,
        withdrawable_amount: 540,
      }),
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

    const projection = projectPredictionMarketExecutionPath({
      run_id: 'run-execution-path-002',
      recommendation: makeRecommendation('bet', 'yes'),
      execution_readiness: readiness,
    })

    expect(projection.requested_path).toBe('live')
    expect(projection.selected_path).toBe('shadow')
    expect(projection.verdict).toBe('downgraded')
    expect(projection.eligible_paths).toEqual(['paper', 'shadow'])
    expect(projection.projected_paths.live).toMatchObject({
      allowed: false,
      blockers: expect.arrayContaining([
        'capital:live_mode_capacity_exhausted',
        'reconciliation:high:live_mode_blocked',
      ]),
    })
    expect(projection.projected_paths.shadow).toMatchObject({
      allowed: true,
    })
    expect(projection.projected_paths.shadow.simulation.expected_fill_confidence).toBeGreaterThan(
      projection.projected_paths.live.simulation.expected_fill_confidence,
    )
    expect(projection.projected_paths.live.simulation.stale_quote_risk).toBe('high')
    expect(projection.downgrade_reasons).toEqual(expect.arrayContaining([
      'capital:live_mode_capacity_exhausted',
      'reconciliation:high:live_mode_blocked',
    ]))
    expect(projection.projected_paths.shadow.warnings.join(' ')).toContain('reconciliation:')
    expect(projection.summary).toContain('shadow')
    expect(projection.summary).toContain('gate execution_projection')
    expect(projection.summary).toContain('preflight only')
  })

  it('requests paper and keeps shadow/live inactive for wait recommendations', () => {
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

    const projection = projectPredictionMarketExecutionPath({
      run_id: 'run-execution-path-003',
      recommendation: makeRecommendation('wait'),
      execution_readiness: readiness,
    })

    expect(projection.requested_path).toBe('paper')
    expect(projection.selected_path).toBe('paper')
    expect(projection.selected_edge_bucket).toBe('no_trade')
    expect(projection.verdict).toBe('allowed')
    expect(projection.eligible_paths).toEqual(['paper'])
    expect(projection.no_trade_baseline_summary).toContain('No-trade baseline')
    expect(projection.no_trade_baseline_summary).toContain('Recommendation remains wait.')
    expect(projection.projected_paths.paper.no_trade_baseline_summary).toContain('No-trade baseline')
    expect(projection.projected_paths.paper.status).toBe('ready')
    expect(projection.projected_paths.paper.edge_bucket).toBe('no_trade')
    expect(projection.projected_paths.paper.pre_trade_gate).toMatchObject({
      gate_name: 'hard_no_trade',
      verdict: 'not_applicable',
      edge_bucket: 'no_trade',
    })
    expect(projection.projected_paths.paper.simulation).toMatchObject({
      expected_fill_confidence: 0,
      expected_slippage_bps: 0,
      stale_quote_risk: 'low',
      quote_age_ms: 0,
    })
    expect(projection.projected_paths.shadow.blockers).toEqual(expect.arrayContaining([
      'recommendation:wait',
    ]))
    expect(projection.projected_paths.live.blockers).toEqual(expect.arrayContaining([
      'recommendation:wait',
    ]))
  })

  it('caps bet projections at paper when manual review is open and no capital ledger is attached', () => {
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

    const projection = projectPredictionMarketExecutionPath({
      run_id: 'run-execution-path-004',
      recommendation: makeRecommendation('bet', 'yes'),
      execution_readiness: {
        ...readiness,
        cross_venue_summary: {
          total_pairs: 1,
          opportunity_type_counts: {
            comparison_only: 0,
            relative_value: 0,
            cross_venue_signal: 0,
            true_arbitrage: 0,
          },
          compatible: [],
          manual_review: [makeShadowArbitrageCrossVenueSummary().compatible[0]!],
          comparison_only: [],
          blocking_reasons: ['time_horizon_mismatch'],
          highest_confidence_candidate: null,
        },
      },
      resolution_policy: resolutionPolicySchema.parse({
        ...makeResolutionPolicy(),
        manual_review_required: true,
        reasons: ['manual review pending'],
      }),
    })

    expect(projection.requested_path).toBe('live')
    expect(projection.selected_path).toBe('paper')
    expect(projection.verdict).toBe('downgraded')
    expect(projection.manual_review_required).toBe(true)
    expect(projection.eligible_paths).toEqual(['paper'])
    expect(projection.projected_paths.shadow).toMatchObject({
      allowed: false,
      blockers: expect.arrayContaining([
        'manual_review_required_for_execution',
        'capital_ledger_unavailable',
      ]),
    })
    expect(projection.projected_paths.live).toMatchObject({
      allowed: false,
      blockers: expect.arrayContaining([
        'manual_review_required_for_execution',
        'capital_ledger_unavailable',
        'reconciliation_unavailable',
      ]),
    })
  })

  it('blocks every execution projection when resolution is not eligible', () => {
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

    const projection = projectPredictionMarketExecutionPath({
      run_id: 'run-execution-path-005',
      recommendation: makeRecommendation('bet', 'yes'),
      execution_readiness: readiness,
      resolution_policy: resolutionPolicySchema.parse({
        ...makeResolutionPolicy(),
        status: 'ambiguous',
        manual_review_required: true,
        reasons: ['resolution text remains ambiguous'],
      }),
    })

    expect(projection.selected_path).toBeNull()
    expect(projection.verdict).toBe('blocked')
    expect(projection.gate_name).toBe('execution_projection')
    expect(projection.preflight_only).toBe(true)
    expect(projection.eligible_paths).toEqual([])
    expect(projection.no_trade_baseline_summary).toContain('No-trade baseline')
    expect(projection.summary).toContain('Baseline:')
    expect(projection.projected_paths.paper).toMatchObject({
      allowed: false,
      blockers: expect.arrayContaining(['resolution:ambiguous']),
    })
    expect(projection.projected_paths.shadow).toMatchObject({
      allowed: false,
      blockers: expect.arrayContaining([
        'resolution:ambiguous',
        'manual_review_required_for_execution',
      ]),
    })
    expect(projection.blocking_reasons).toEqual(expect.arrayContaining(['resolution:ambiguous']))
    expect(projection.summary).toContain('no execution path is currently safe')
    expect(projection.summary).toContain('gate execution_projection')
  })

  it('attaches a read-only shadow arbitrage simulation only on the shadow path when a cross-venue edge is exploitable', () => {
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
        run_id: 'run-execution-path-shadow-arb',
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
    const projection = projectPredictionMarketExecutionPath({
      run_id: 'run-execution-path-shadow-arb',
      recommendation: makeRecommendation('bet', 'yes'),
      execution_readiness: {
        ...readiness,
        cross_venue_summary: makeShadowArbitrageCrossVenueSummary(),
        microstructure_lab: microstructureLab,
      },
    })

    expect(projection.projected_paths.shadow.simulation.shadow_arbitrage).not.toBeNull()
    expect(projection.projected_paths.shadow.simulation.shadow_arbitrage).toMatchObject({
      read_only: true,
      executable_edge: {
        executable: true,
      },
      summary: {
        failure_case_count: 3,
      },
    })
    expect(projection.projected_paths.shadow.simulation.shadow_arbitrage?.sizing.requested_size_usd).toBe(
      projection.projected_paths.shadow.trade_intent_preview?.size_usd,
    )
    expect(projection.projected_paths.shadow.shadow_arbitrage_signal).toMatchObject({
      read_only: true,
      failure_case_count: 3,
    })
    expect(projection.projected_paths.shadow.edge_bucket).toBe('arbitrage_alpha')
    expect(projection.projected_paths.shadow.pre_trade_gate).toMatchObject({
      gate_name: 'hard_no_trade',
      verdict: 'pass',
      edge_bucket: 'arbitrage_alpha',
    })
    expect(projection.projected_paths.shadow.sizing_signal?.source).toBe('trade_intent_preview+shadow_arbitrage')
    expect(projection.projected_paths.shadow.sizing_signal?.preview_size_usd).toBe(
      projection.projected_paths.shadow.trade_intent_preview?.size_usd,
    )
    expect(projection.projected_paths.shadow.sizing_signal?.shadow_recommended_size_usd).toBe(
      projection.projected_paths.shadow.simulation.shadow_arbitrage?.summary.recommended_size_usd,
    )
    expect(projection.projected_paths.shadow.sizing_signal?.canonical_size_usd).toBe(
      Math.min(
        projection.projected_paths.shadow.trade_intent_preview?.size_usd ?? Number.POSITIVE_INFINITY,
        projection.projected_paths.shadow.simulation.shadow_arbitrage?.summary.recommended_size_usd ?? Number.POSITIVE_INFINITY,
      ),
    )
    expect(projection.projected_paths.shadow.canonical_trade_intent_preview?.size_usd).toBe(
      projection.projected_paths.shadow.sizing_signal?.canonical_size_usd,
    )
    expect(projection.projected_paths.shadow.canonical_trade_intent_preview?.size_usd).toBeLessThanOrEqual(
      projection.projected_paths.shadow.trade_intent_preview?.size_usd ?? Number.POSITIVE_INFINITY,
    )
    if (
      (projection.projected_paths.shadow.canonical_trade_intent_preview?.size_usd ?? Number.POSITIVE_INFINITY) <
      (projection.projected_paths.shadow.trade_intent_preview?.size_usd ?? Number.POSITIVE_INFINITY)
    ) {
      expect(projection.projected_paths.shadow.canonical_trade_intent_preview?.notes ?? '').toContain(
        'Canonical execution projection preview caps size',
      )
    }
    expect(projection.projected_paths.shadow.simulation.shadow_arbitrage?.summary.base_executable_edge_bps).toBeGreaterThan(0)
    expect(projection.projected_paths.shadow.simulation.notes.join(' ')).toContain('Shadow arbitrage simulation is attached')
    expect(projection.projected_paths.paper.simulation.shadow_arbitrage).toBeNull()
    expect(projection.projected_paths.live.simulation.shadow_arbitrage).toBeNull()
    expect(projection.projected_paths.paper.shadow_arbitrage_signal).toBeNull()
    expect(projection.projected_paths.live.shadow_arbitrage_signal).toBeNull()
    expect(projection.projected_paths.paper.canonical_trade_intent_preview?.size_usd).toBe(
      projection.projected_paths.paper.trade_intent_preview?.size_usd,
    )
    expect(projection.projected_paths.live.canonical_trade_intent_preview?.size_usd).toBe(
      projection.projected_paths.live.trade_intent_preview?.size_usd,
    )
  })

  it('keeps maker spread capture paper-only when quote freshness is too stale for shadow and live execution', () => {
    const capitalLedger = makeCapitalLedger()
    const reconciliation = reconcileCapitalLedger({
      theoretical: capitalLedger,
      observed: capitalLedger,
    })
    const readiness = buildPredictionMarketExecutionReadiness({
      capabilities: makeCapabilities(),
      health: venueHealthSnapshotSchema.parse({
        ...makeHealth(),
        staleness_ms: 6_500,
      }),
      budgets: makeBudgets(),
      compliance_matrix: makeComplianceMatrix(),
      capital_ledger: capitalLedger,
      reconciliation,
    })

    const projection = projectPredictionMarketExecutionPath({
      run_id: 'run-execution-path-maker-stale',
      recommendation: makeRecommendation('bet', 'yes'),
      execution_readiness: readiness,
      strategy_name: 'maker_spread_capture',
    })

    expect(projection.selected_path).toBe('paper')
    expect(projection.verdict).toBe('downgraded')
    expect(projection.projected_paths.paper).toMatchObject({
      allowed: true,
      warnings: expect.arrayContaining([
        'maker_quote_stale_for_shadow_live',
      ]),
    })
    expect(projection.projected_paths.shadow).toMatchObject({
      allowed: false,
      blockers: expect.arrayContaining([
        'maker_quote_stale_for_execution',
      ]),
    })
    expect(projection.projected_paths.live).toMatchObject({
      allowed: false,
      blockers: expect.arrayContaining([
        'maker_quote_stale_for_execution',
      ]),
    })
  })

  it('keeps maker spread capture out of live when the market regime says quoting is only guarded', () => {
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

    const projection = projectPredictionMarketExecutionPath({
      run_id: 'run-execution-path-maker-guarded',
      recommendation: makeRecommendation('bet', 'yes'),
      execution_readiness: readiness,
      strategy_name: 'maker_spread_capture',
      market_regime_summary: 'maker-regime-market is in stress regime; price=wide; freshness=fresh; resolution=watch; research=supportive; latency=lagging; maker_quote=guarded',
    })

    expect(projection.selected_path).toBe('shadow')
    expect(projection.projected_paths.shadow.allowed).toBe(true)
    expect(projection.projected_paths.live).toMatchObject({
      allowed: false,
      blockers: expect.arrayContaining([
        'maker_quote_guarded_live_only_shadow',
      ]),
      warnings: expect.arrayContaining([
        'maker_quote_state:guarded',
      ]),
    })
  })

  it('blocks all bet projections when the net edge does not clear the hard no-trade gate', () => {
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

    const projection = projectPredictionMarketExecutionPath({
      run_id: 'run-execution-path-low-edge',
      recommendation: marketRecommendationPacketSchema.parse({
        ...makeRecommendation('bet', 'yes'),
        edge_bps: 150,
        spread_bps: 120,
        confidence: 0.58,
      }),
      execution_readiness: readiness,
    })

    expect(projection.selected_path).toBeNull()
    expect(projection.selected_edge_bucket).toBe('forecast_alpha')
    expect(projection.selected_pre_trade_gate).toMatchObject({
      gate_name: 'hard_no_trade',
      verdict: 'fail',
      edge_bucket: 'forecast_alpha',
    })
    expect(projection.projected_paths.paper).toMatchObject({
      allowed: false,
      blockers: expect.arrayContaining([
        'pre_trade_gate:net_edge_below_conservative_threshold',
      ]),
      trade_intent_preview: null,
      canonical_trade_intent_preview: null,
      sizing_signal: null,
    })
    expect(projection.projected_paths.paper.pre_trade_gate?.net_edge_bps ?? 0).toBeLessThan(
      projection.projected_paths.paper.pre_trade_gate?.minimum_net_edge_bps ?? Number.POSITIVE_INFINITY,
    )
    expect(projection.summary).toContain('Hard no-trade gate fail')
  })
})
