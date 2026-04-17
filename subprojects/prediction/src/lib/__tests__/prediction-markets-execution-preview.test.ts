import { describe, expect, it } from 'vitest'
import { evaluatePredictionMarketComplianceMatrix } from '@/lib/prediction-markets/compliance'
import { buildPredictionMarketExecutionReadiness } from '@/lib/prediction-markets/execution-readiness'
import {
  buildPredictionMarketExecutionApprovalTicket,
  buildPredictionMarketExecutionSizingSummary,
} from '@/lib/prediction-markets/execution-preview'
import { type CapitalLedgerSourceInput } from '@/lib/prediction-markets/capital-ledger'
import {
  approvalTradeTicketSchema,
  forecastPacketSchema,
  marketDescriptorSchema,
  marketRecommendationPacketSchema,
  marketSnapshotSchema,
  predictionMarketBudgetsSchema,
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
    rate_limit_notes: 'execution preview test fixture',
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
    snapshot_freshness_budget_ms: 4_000,
    decision_latency_budget_ms: 2_000,
    fetch_latency_budget_ms: 4_000,
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
    market_id: 'mkt-execution-preview-001',
    slug: 'mkt-execution-preview-001',
    question: 'Will the execution preview remain operator friendly?',
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
    source_urls: ['https://example.com/mkt-execution-preview-001'],
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
      'https://example.com/mkt-execution-preview-001',
      'https://example.com/mkt-execution-preview-001/book',
    ],
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
    rationale: 'Synthetic forecast for execution preview.',
    evidence_refs: ['evidence:execution-preview'],
    source_bundle_id: 'bundle:execution-preview',
    source_packet_refs: ['packet:forecast'],
    social_context_refs: ['social:execution-preview'],
    market_context_refs: ['market:execution-preview'],
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
    risk_flags: ['execution_friction'],
    rationale: 'Synthetic recommendation for execution preview.',
    why_now: ['Spread remains within the operator review band.'],
    why_not_now: ['Wait if the order book moves materially.'],
    watch_conditions: ['Confirm the best ask stays inside the expected band.'],
    source_bundle_id: 'bundle:execution-preview',
    source_packet_refs: ['packet:recommendation'],
    social_context_refs: ['social:execution-preview'],
    market_context_refs: ['market:execution-preview'],
    produced_at: '2026-04-08T00:00:00.000Z',
  })
}

function makeCapitalLedger(): CapitalLedgerSourceInput {
  return {
    venue: 'polymarket',
    captured_at: '2026-04-08T00:00:00.000Z',
    cash_available: 2_000,
    cash_locked: 100,
    collateral_currency: 'USD',
    open_exposure_usd: 150,
    withdrawable_amount: 1_850,
    transfer_latency_estimate_ms: 15_000,
  }
}

function makeReadiness() {
  return buildPredictionMarketExecutionReadiness({
    capabilities: makeCapabilities(),
    health: makeHealth(),
    budgets: makeBudgets(),
    compliance_matrix: evaluatePredictionMarketComplianceMatrix({
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
    }),
    capital_ledger: makeCapitalLedger(),
  })
}

function makeTradeIntent() {
  const snapshot = makeSnapshot()
  return tradeIntentSchema.parse({
    intent_id: 'intent-execution-preview-001',
    run_id: 'run-execution-preview-001',
    venue: snapshot.venue,
    market_id: snapshot.market.market_id,
    side: 'yes',
    size_usd: 120,
    limit_price: 0.47,
    max_slippage_bps: 25,
    max_unhedged_leg_ms: 750,
    time_in_force: 'day',
    forecast_ref: 'forecast:execution-preview',
    risk_checks_passed: true,
    created_at: '2026-04-08T00:00:00.000Z',
    notes: 'Canonical trade intent preview for approval tickets.',
  })
}

describe('prediction market execution approval ticket', () => {
  it('builds an operator-friendly pending approval ticket that preserves the trade intent preview', () => {
    const snapshot = makeSnapshot()
    const forecast = makeForecast()
    const recommendation = makeRecommendation('bet', 'yes')
    const readiness = makeReadiness()
    const tradeIntentPreview = makeTradeIntent()

    const ticket = buildPredictionMarketExecutionApprovalTicket({
      run_id: 'run-execution-preview-001',
      mode: 'live',
      snapshot,
      forecast,
      recommendation,
      readiness,
      strategy_name: 'maker_spread_capture',
      market_regime_summary: 'Stable, liquid, operator-review-friendly regime.',
      primary_strategy_summary: 'Spread capture with conservative sizing.',
      strategy_summary: 'Ticket should highlight edge, size, and approval checks.',
      no_trade_baseline_summary: 'No-trade baseline only wins if the spread widens or the book turns stale.',
      trade_intent_preview: tradeIntentPreview,
      canonical_trade_intent_preview: tradeIntentPreview,
    })

    expect(() => approvalTradeTicketSchema.parse(ticket)).not.toThrow()
    expect(ticket.ticket_kind).toBe('approval_trade_ticket')
    expect(ticket.workflow_stage).toBe('approval')
    expect(ticket.approval_state.status).toBe('pending')
    expect(ticket.approval_state.summary).toContain('Pending operator review')
    expect(ticket.summary).toContain('Approval ticket')
    expect(ticket.summary).toContain('YES')
    expect(ticket.rationale).toContain('YES appears underpriced')
    expect(ticket.rationale).toContain('Readiness verdict')
    expect(ticket.limit_price).toBe(tradeIntentPreview.limit_price)
    expect(ticket.size_usd).toBe(tradeIntentPreview.size_usd)
    expect(ticket.trade_intent_preview?.intent_id).toBe(tradeIntentPreview.intent_id)
    expect(ticket.notes.join(' ')).toContain('Strategy context')
    expect(ticket.notes.join(' ')).toContain('Readiness:')
    expect(ticket.notes.join(' ')).toContain('Approval workflow:')
    expect(ticket.metadata.ticket_source).toBe('execution_preview')
    expect((ticket.metadata.approval_checks as Array<string>)).toEqual(
      expect.arrayContaining([
        expect.stringContaining('ticket_status:pending'),
        expect.stringContaining('approval_state:Pending operator review'),
      ]),
    )
  })

  it('marks non-bet recommendations as blocked review tickets', () => {
    const snapshot = makeSnapshot()
    const forecast = makeForecast()
    const recommendation = makeRecommendation('wait')
    const readiness = makeReadiness()

    const ticket = buildPredictionMarketExecutionApprovalTicket({
      run_id: 'run-execution-preview-002',
      mode: 'paper',
      snapshot,
      forecast,
      recommendation,
      readiness,
    })

    expect(() => approvalTradeTicketSchema.parse(ticket)).not.toThrow()
    expect(ticket.workflow_stage).toBe('blocked')
    expect(ticket.approval_state.status).toBe('blocked')
    expect(ticket.approval_state.summary).toContain('Blocked')
    expect(ticket.summary).toContain('Blocked ticket')
    expect(ticket.rationale).toContain('Recommendation is wait')
    expect(ticket.notes.join(' ')).toContain('Risk flags:')
    expect(ticket.metadata.ticket_source).toBe('execution_preview')
    expect((ticket.metadata.approval_checks as Array<string>)).toEqual(
      expect.arrayContaining([
        expect.stringContaining('ticket_status:blocked'),
        expect.stringContaining('approval_state:Blocked: recommendation is wait.'),
      ]),
    )
  })

  it('applies a Kelly overlay cap when the edge is positive but modest relative to capital', () => {
    const baseSnapshot = makeSnapshot()
    const snapshot = marketSnapshotSchema.parse({
      ...baseSnapshot,
      market: {
        ...baseSnapshot.market,
        liquidity_usd: 1_000_000,
      },
      book: {
        ...baseSnapshot.book,
        depth_near_touch: 100_000,
        bids: [{ price: 0.48, size: 5_000 }],
        asks: [{ price: 0.5, size: 5_000 }],
      },
    })
    const forecast = forecastPacketSchema.parse({
      ...makeForecast(),
      probability_yes: 0.51,
    })
    const recommendation = marketRecommendationPacketSchema.parse({
      ...makeRecommendation('bet', 'yes'),
      fair_value_yes: 0.51,
      edge_bps: 200,
    })
    const readiness = makeReadiness()

    const sizing = buildPredictionMarketExecutionSizingSummary({
      mode: 'paper',
      snapshot,
      forecast,
      recommendation,
      readiness,
    })

    expect(sizing.source).toBe('capital_ledger')
    expect(sizing.kelly_applicable).toBe(true)
    expect(sizing.kelly_fraction).toBeCloseTo(0.0392, 3)
    expect(sizing.kelly_cap_usd).toBe(78.43)
    expect(sizing.effective_cap_usd).toBe(78.43)
    expect(sizing.recommended_size_usd).toBe(78.43)
    expect(sizing.max_size_usd).toBe(250)
    expect(sizing.conservative_cap_usd).toBe(250)
    expect(sizing.notes.join(' ')).toContain('Kelly overlay caps the recommended size')
  })

  it('applies capital-time haircut before conservative sizing', () => {
    const baseSnapshot = makeSnapshot()
    const snapshot = marketSnapshotSchema.parse({
      ...baseSnapshot,
      market: {
        ...baseSnapshot.market,
        liquidity_usd: 1_000_000,
      },
      book: {
        ...baseSnapshot.book,
        depth_near_touch: 100_000,
        bids: [{ price: 0.48, size: 5_000 }],
        asks: [{ price: 0.5, size: 5_000 }],
      },
    })
    const forecast = forecastPacketSchema.parse({
      ...makeForecast(),
      confidence: 0.95,
    })
    const recommendation = marketRecommendationPacketSchema.parse({
      ...makeRecommendation('wait'),
      confidence: 0.95,
    })
    const baseReadiness = makeReadiness()
    const readiness = {
      ...baseReadiness,
      calibration_ece: 0.02,
      portfolio_correlation: 0.1,
      capital_ledger: {
        ...baseReadiness.capital_ledger!,
        cash_available_usd: 2_000,
        cash_locked_usd: 100,
        open_exposure_usd: 1_700,
        utilization_ratio: 0.809524,
        transfer_latency_estimate_ms: 90_000,
      },
    }

    const sizing = buildPredictionMarketExecutionSizingSummary({
      mode: 'paper',
      snapshot,
      forecast,
      recommendation,
      readiness,
    })

    expect(sizing.base_size_usd).toBe(160)
    expect(sizing.recommended_size_usd).toBe(136)
    expect(sizing.notes).toContain(
      'Capital-time haircut factor=80.0% (latency=80.0%, utilization=80.0%) from transfer_latency_estimate_ms=90000 and utilization_ratio=81.0%.',
    )
  })

  it('binds sizing to a hard correlation cap when overlap is extreme', () => {
    const baseSnapshot = makeSnapshot()
    const snapshot = marketSnapshotSchema.parse({
      ...baseSnapshot,
      market: {
        ...baseSnapshot.market,
        liquidity_usd: 1_000_000,
      },
      book: {
        ...baseSnapshot.book,
        depth_near_touch: 100_000,
        bids: [{ price: 0.48, size: 5_000 }],
        asks: [{ price: 0.5, size: 5_000 }],
      },
    })
    const forecast = forecastPacketSchema.parse({
      ...makeForecast(),
      confidence: 0.95,
    })
    const recommendation = marketRecommendationPacketSchema.parse({
      ...makeRecommendation('wait'),
      confidence: 0.95,
    })
    const baseReadiness = makeReadiness()
    const readiness = {
      ...baseReadiness,
      calibration_ece: 0.02,
      portfolio_correlation: 0.9,
      capital_ledger: {
        ...baseReadiness.capital_ledger!,
        cash_available_usd: 3_000,
        cash_locked_usd: 100,
        open_exposure_usd: 150,
        utilization_ratio: 0.048387,
        transfer_latency_estimate_ms: 15_000,
      },
    }

    const sizing = buildPredictionMarketExecutionSizingSummary({
      mode: 'shadow',
      snapshot,
      forecast,
      recommendation,
      readiness,
    })

    expect(sizing.max_size_usd).toBe(60)
    expect(sizing.conservative_cap_usd).toBe(60)
    expect(sizing.effective_cap_usd).toBe(60)
    expect(sizing.recommended_size_usd).toBe(60)
    expect(sizing.notes).toContain(
      'Correlation cap factor=40.0% trims max size to 60.00 USD at portfolio_correlation=90.0%.',
    )
  })
})
