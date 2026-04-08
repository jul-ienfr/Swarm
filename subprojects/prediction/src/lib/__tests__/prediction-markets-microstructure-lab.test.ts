import { describe, expect, it } from 'vitest'
import { buildMicrostructureLabReport } from '@/lib/prediction-markets/microstructure-lab'
import {
  marketDescriptorSchema,
  marketRecommendationPacketSchema,
  marketSnapshotSchema,
  tradeIntentSchema,
  type MarketDescriptor,
  type MarketSnapshot,
} from '@/lib/prediction-markets/schemas'

function makeDescriptor(overrides: Partial<MarketDescriptor> = {}): MarketDescriptor {
  return marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: 'microstructure-lab-market',
    slug: 'microstructure-lab-market',
    question: 'Will the microstructure lab remain deterministic?',
    outcomes: ['Yes', 'No'],
    active: true,
    closed: false,
    accepting_orders: true,
    restricted: false,
    liquidity_usd: 220_000,
    volume_usd: 1_200_000,
    volume_24h_usd: 140_000,
    best_bid: 0.48,
    best_ask: 0.5,
    last_trade_price: 0.49,
    tick_size: 0.01,
    min_order_size: 5,
    is_binary_yes_no: true,
    end_at: '2026-12-31T23:59:59.000Z',
    source_urls: ['https://example.com/microstructure-lab-market'],
    ...overrides,
  })
}

function makeSnapshot(
  overrides: Omit<Partial<MarketSnapshot>, 'market'> & { market?: Partial<MarketDescriptor> } = {},
): MarketSnapshot {
  const { market: marketOverrides, ...snapshotOverrides } = overrides
  const market = makeDescriptor(marketOverrides ?? {})

  return marketSnapshotSchema.parse({
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
      bids: [{ price: 0.48, size: 600 }],
      asks: [{ price: 0.5, size: 520 }],
      depth_near_touch: 1_800,
    },
    history: [
      { timestamp: 1712534400, price: 0.47 },
      { timestamp: 1712538000, price: 0.49 },
    ],
    source_urls: [
      'https://example.com/microstructure-lab-market',
      'https://example.com/microstructure-lab-market/book',
    ],
    ...snapshotOverrides,
    venue: market.venue,
    market,
  })
}

function makeRecommendation(snapshot: MarketSnapshot, overrides = {}) {
  return marketRecommendationPacketSchema.parse({
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    action: 'bet',
    side: 'yes',
    confidence: 0.78,
    fair_value_yes: 0.68,
    market_price_yes: snapshot.yes_price ?? 0.49,
    market_bid_yes: snapshot.best_bid_yes ?? 0.48,
    market_ask_yes: snapshot.best_ask_yes ?? 0.5,
    edge_bps: 1_800,
    spread_bps: snapshot.spread_bps ?? 200,
    reasons: ['microstructure lab fixture'],
    risk_flags: [],
    produced_at: '2026-04-08T00:00:00.000Z',
    ...overrides,
  })
}

describe('prediction markets microstructure lab', () => {
  it('simulates deterministic deterioration across the five failure modes', () => {
    const snapshot = makeSnapshot()
    const recommendation = makeRecommendation(snapshot)
    const tradeIntent = tradeIntentSchema.parse({
      intent_id: 'microstructure-intent-001',
      run_id: 'microstructure-run-001',
      venue: snapshot.venue,
      market_id: snapshot.market.market_id,
      side: 'yes',
      size_usd: 100,
      limit_price: 0.5,
      max_slippage_bps: 40,
      max_unhedged_leg_ms: 2_000,
      time_in_force: 'day',
      forecast_ref: 'forecast:microstructure-lab-market:2026-04-08T00:00:00.000Z',
      risk_checks_passed: true,
      created_at: '2026-04-08T00:00:00.000Z',
    })

    const report = buildMicrostructureLabReport({
      snapshot,
      recommendation,
      trade_intent: tradeIntent,
      generated_at: '2026-04-08T00:00:00.000Z',
    })

    expect(report.market_id).toBe('microstructure-lab-market')
    expect(report.venue).toBe('polymarket')
    expect(report.generated_at).toBe('2026-04-08T00:00:00.000Z')
    expect(report.scenarios.map((scenario) => scenario.kind)).toEqual([
      'partial_fill',
      'one_leg_fill',
      'cancel_replace',
      'queue_miss',
      'hedge_delay',
      'stale_book',
      'spread_collapse',
    ])
    expect(report.scenarios.map((scenario) => scenario.impact_bps)).toEqual([10, 18, 7, 15, 15, 17, 21])
    expect(report.scenarios.map((scenario) => scenario.executable_edge_after_impact_bps)).toEqual([
      1790,
      1782,
      1793,
      1785,
      1785,
      1783,
      1779,
    ])
    expect(report.scenarios.find((scenario) => scenario.kind === 'partial_fill')).toMatchObject({
      severity: 'low',
      status: 'stable',
      legs_required: 2,
      legs_filled: 1,
      fill_ratio: 0.5,
    })
    expect(report.scenarios.find((scenario) => scenario.kind === 'one_leg_fill')).toMatchObject({
      severity: 'medium',
      status: 'degraded',
      legs_required: 2,
      legs_filled: 1,
      fill_ratio: 0.5,
    })
    expect(report.scenarios.find((scenario) => scenario.kind === 'hedge_delay')).toMatchObject({
      severity: 'medium',
      status: 'degraded',
      hedge_delay_ms: 2000,
    })
    expect(report.scenarios.find((scenario) => scenario.kind === 'stale_book')).toMatchObject({
      severity: 'medium',
      status: 'degraded',
      book_age_ms: 0,
    })
    expect(report.summary).toMatchObject({
      base_executable_edge_bps: 1800,
      worst_case_kind: 'spread_collapse',
      worst_case_severity: 'medium',
      worst_case_executable_edge_bps: 1779,
      executable_deterioration_bps: 21,
      recommended_mode: 'paper',
      event_counts: {
        partial_fill: 1,
        one_leg_fill: 1,
        cancel_replace: 1,
        queue_miss: 1,
        hedge_delay: 1,
        stale_book: 1,
        spread_collapse: 1,
      },
    })
    expect(report.summary.execution_quality_score).toBeGreaterThan(0.7)
    expect(report.summary.notes.join(' ')).toContain('Base executable edge is 1800 bps.')
    expect(report.summary.notes.join(' ')).toContain('Scenario overview:')
  })

  it('downgrades to wait when a thin book destroys the executable edge', () => {
    const snapshot = makeSnapshot({
      market: {
        market_id: 'microstructure-lab-thin',
        slug: 'microstructure-lab-thin',
        question: 'Will the thin book destroy the edge?',
        liquidity_usd: 20_000,
        best_bid: 0.35,
        best_ask: 0.39,
        last_trade_price: 0.37,
      },
      yes_price: 0.37,
      no_price: 0.63,
      midpoint_yes: 0.37,
      best_bid_yes: 0.35,
      best_ask_yes: 0.39,
      spread_bps: 400,
      book: {
        token_id: 'microstructure-lab-thin:yes',
        market_condition_id: 'microstructure-lab-thin:cond',
        fetched_at: '2026-04-08T00:00:00.000Z',
        best_bid: 0.35,
        best_ask: 0.39,
        last_trade_price: 0.37,
        tick_size: 0.01,
        min_order_size: 5,
        bids: [{ price: 0.35, size: 80 }],
        asks: [{ price: 0.39, size: 70 }],
        depth_near_touch: 300,
      },
    })
    const recommendation = makeRecommendation(snapshot, {
      confidence: 0.44,
      fair_value_yes: 0.46,
      market_price_yes: 0.37,
      market_bid_yes: 0.35,
      market_ask_yes: 0.39,
      edge_bps: 30,
      spread_bps: 400,
    })
    const tradeIntent = tradeIntentSchema.parse({
      intent_id: 'microstructure-intent-002',
      run_id: 'microstructure-run-002',
      venue: snapshot.venue,
      market_id: snapshot.market.market_id,
      side: 'yes',
      size_usd: 25,
      limit_price: 0.39,
      max_slippage_bps: 80,
      max_unhedged_leg_ms: 250,
      time_in_force: 'ioc',
      forecast_ref: 'forecast:microstructure-lab-thin:2026-04-08T00:00:00.000Z',
      risk_checks_passed: true,
      created_at: '2026-04-08T00:00:00.000Z',
    })

    const report = buildMicrostructureLabReport({
      snapshot,
      recommendation,
      trade_intent: tradeIntent,
      generated_at: '2026-04-08T00:00:00.000Z',
    })

    expect(report.scenarios.find((scenario) => scenario.kind === 'one_leg_fill')).toMatchObject({
      severity: 'high',
      status: 'blocked',
      impact_bps: 48,
      executable_edge_after_impact_bps: 0,
    })
    expect(report.summary).toMatchObject({
      base_executable_edge_bps: 30,
      worst_case_kind: 'one_leg_fill',
      worst_case_severity: 'high',
      worst_case_executable_edge_bps: 0,
      executable_deterioration_bps: 30,
      recommended_mode: 'wait',
    })
    expect(report.summary.execution_quality_score).toBeLessThan(0.4)
    expect(report.summary.notes.join(' ')).toContain('Recommended mode is wait.')
  })
})
