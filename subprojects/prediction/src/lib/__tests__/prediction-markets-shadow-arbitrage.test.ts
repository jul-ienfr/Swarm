import { describe, expect, it } from 'vitest'
import { buildMicrostructureLabReport } from '@/lib/prediction-markets/microstructure-lab'
import { buildShadowArbitrageSimulation } from '@/lib/prediction-markets/shadow-arbitrage'
import {
  executableEdgeSchema,
  marketDescriptorSchema,
  marketRecommendationPacketSchema,
  marketSnapshotSchema,
  tradeIntentSchema,
  type MarketDescriptor,
  type MarketSnapshot,
} from '@/lib/prediction-markets/schemas'
import { type MicrostructureLabSummary } from '@/lib/prediction-markets/microstructure-lab'

function makeDescriptor(overrides: Partial<MarketDescriptor> = {}): MarketDescriptor {
  return marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: 'shadow-arb-market',
    slug: 'shadow-arb-market',
    question: 'Will the shadow arbitrage simulation stay read-only?',
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
    source_urls: ['https://example.com/shadow-arb-market'],
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
      'https://example.com/shadow-arb-market',
      'https://example.com/shadow-arb-market/book',
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
    reasons: ['shadow arbitrage fixture'],
    risk_flags: [],
    produced_at: '2026-04-08T00:00:00.000Z',
    ...overrides,
  })
}

function makeTradeIntent(snapshot: MarketSnapshot) {
  return tradeIntentSchema.parse({
    intent_id: 'shadow-arb-intent-001',
    run_id: 'shadow-arb-run-001',
    venue: snapshot.venue,
    market_id: snapshot.market.market_id,
    side: 'yes',
    size_usd: 100,
    limit_price: 0.5,
    max_slippage_bps: 40,
    max_unhedged_leg_ms: 2_000,
    time_in_force: 'day',
    forecast_ref: 'forecast:shadow-arb-market:2026-04-08T00:00:00.000Z',
    risk_checks_passed: true,
    created_at: '2026-04-08T00:00:00.000Z',
  })
}

function makeExecutableEdge(overrides = {}) {
  return executableEdgeSchema.parse({
    edge_id: 'edge:shadow-arb-001',
    canonical_event_id: 'cve:shadow-arb-001',
    opportunity_type: 'true_arbitrage',
    buy_ref: { venue: 'polymarket', market_id: 'shadow-arb-market' },
    sell_ref: { venue: 'kalshi', market_id: 'shadow-arb-hedge' },
    buy_price_yes: 0.43,
    sell_price_yes: 0.58,
    gross_spread_bps: 1_500,
    fee_bps: 60,
    slippage_bps: 40,
    hedge_risk_bps: 25,
    executable_edge_bps: 1_375,
    confidence_score: 0.88,
    executable: true,
    evaluated_at: '2026-04-08T00:00:00.000Z',
    notes: ['stale_edge_expired:false'],
    ...overrides,
  })
}

function makeStaleSummary(baseSummary: MicrostructureLabSummary): MicrostructureLabSummary {
  return {
    ...baseSummary,
    worst_case_kind: 'stale_book',
    worst_case_severity: 'critical',
    worst_case_executable_edge_bps: 0,
    executable_deterioration_bps: baseSummary.base_executable_edge_bps,
    execution_quality_score: 0.18,
    recommended_mode: 'wait',
    scenario_overview: [
      ...baseSummary.scenario_overview,
      'stale_book:critical/blocked impact=180bps edge_after=0bps book_age=30000ms',
    ],
    notes: [
      ...baseSummary.notes,
      'Scenario overview: stale_book:critical/blocked impact=180bps edge_after=0bps book_age=30000ms.',
      'This fixture intentionally stresses stale-edge handling.',
    ],
  }
}

function makeSpreadCollapseSummary(baseSummary: MicrostructureLabSummary): MicrostructureLabSummary {
  return {
    ...baseSummary,
    worst_case_kind: 'spread_collapse',
    worst_case_severity: 'high',
    worst_case_executable_edge_bps: 12,
    executable_deterioration_bps: Math.max(0, baseSummary.base_executable_edge_bps - 12),
    execution_quality_score: 0.34,
    recommended_mode: 'wait',
    scenario_overview: [
      ...baseSummary.scenario_overview,
      'spread_collapse:high/blocked impact=145bps edge_after=12bps',
    ],
    notes: [
      ...baseSummary.notes,
      'Scenario overview: spread_collapse:high/blocked impact=145bps edge_after=12bps.',
      'This fixture intentionally stresses edge-collapse handling.',
    ],
  }
}

describe('prediction markets shadow arbitrage simulator', () => {
  it('estimates net pnl, keeps the three failure modes normalized, and reflects the dominant microstructure stress', () => {
    const snapshot = makeSnapshot()
    const recommendation = makeRecommendation(snapshot)
    const tradeIntent = makeTradeIntent(snapshot)
    const microstructureReport = buildMicrostructureLabReport({
      snapshot,
      recommendation,
      trade_intent: tradeIntent,
      generated_at: '2026-04-08T00:00:00.000Z',
    })
    const executableEdge = makeExecutableEdge({
      evaluated_at: '2026-04-08T00:00:00.000Z',
      executable_edge_bps: 1_275,
      notes: ['stale_edge_expired:false'],
    })

    const report = buildShadowArbitrageSimulation({
      executable_edge: executableEdge,
      microstructure_summary: microstructureReport.summary,
      generated_at: '2026-04-08T00:05:00.000Z',
      as_of_at: '2026-04-08T00:00:00.000Z',
    })

    expect(report.read_only).toBe(true)
    expect(report.summary.base_executable_edge_bps).toBe(1_275)
    expect(report.summary.failure_case_count).toBe(3)
    expect(report.sizing.requested_size_usd).toBeNull()
    expect(report.sizing.simulated_size_usd).toBe(report.sizing.recommended_size_usd)
    expect(report.sizing.recommended_size_usd).toBeLessThanOrEqual(report.sizing.base_size_usd)
    expect(report.summary.hedge_success_probability).toBeGreaterThan(0.5)
    expect(report.summary.estimated_net_pnl_bps).toBeGreaterThan(0)
    expect(report.summary.estimated_net_pnl_usd).toBeGreaterThan(0)
    expect(report.failure_cases.map((failureCase) => failureCase.kind)).toEqual([
      'one_leg_fill',
      'hedge_delay',
      'stale_edge',
    ])

    const probabilitySum = report.failure_cases.reduce((sum, failureCase) => sum + failureCase.probability, 0)
    const oneLegFillProbability = report.failure_cases.find((failureCase) => failureCase.kind === 'one_leg_fill')?.probability ?? 0
    const hedgeDelayProbability = report.failure_cases.find((failureCase) => failureCase.kind === 'hedge_delay')?.probability ?? 0
    const staleEdgeProbability = report.failure_cases.find((failureCase) => failureCase.kind === 'stale_edge')?.probability ?? 0
    expect(probabilitySum).toBeCloseTo(1 - report.summary.hedge_success_probability, 4)
    if (
      microstructureReport.summary.worst_case_kind === 'stale_book' ||
      microstructureReport.summary.worst_case_kind === 'spread_collapse'
    ) {
      expect(staleEdgeProbability).toBeGreaterThanOrEqual(Math.max(oneLegFillProbability, hedgeDelayProbability))
    } else if (microstructureReport.summary.worst_case_kind === 'hedge_delay') {
      expect(hedgeDelayProbability).toBeGreaterThanOrEqual(Math.max(oneLegFillProbability, staleEdgeProbability))
    } else {
      expect(oneLegFillProbability).toBeGreaterThanOrEqual(Math.max(hedgeDelayProbability, staleEdgeProbability))
    }
    expect(report.summary.notes.join(' ')).toContain('Read-only shadow arbitrage simulation')
    expect(report.summary.notes.join(' ')).toContain('Failure modes modelled: one_leg_fill, hedge_delay, stale_edge.')
  })

  it('pushes sizing down and makes stale_edge the dominant loss case when freshness collapses', () => {
    const thinSnapshot = makeSnapshot({
      market: {
        market_id: 'shadow-arb-thin',
        slug: 'shadow-arb-thin',
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
        token_id: 'shadow-arb-thin:yes',
        market_condition_id: 'shadow-arb-thin:cond',
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
    const thinRecommendation = makeRecommendation(thinSnapshot, {
      confidence: 0.44,
      fair_value_yes: 0.46,
      market_price_yes: 0.37,
      market_bid_yes: 0.35,
      market_ask_yes: 0.39,
      edge_bps: 30,
      spread_bps: 400,
    })
    const tradeIntent = makeTradeIntent(thinSnapshot)
    const microstructureReport = buildMicrostructureLabReport({
      snapshot: thinSnapshot,
      recommendation: thinRecommendation,
      trade_intent: tradeIntent,
      generated_at: '2026-04-08T00:00:00.000Z',
    })
    const staleSummary = makeStaleSummary(microstructureReport.summary)
    const staleEdge = makeExecutableEdge({
      evaluated_at: '2026-04-07T23:30:00.000Z',
      executable_edge_bps: 18,
      confidence_score: 0.31,
      notes: ['stale_edge_expired:true'],
    })

    const report = buildShadowArbitrageSimulation({
      executable_edge: staleEdge,
      microstructure_summary: staleSummary,
      generated_at: '2026-04-08T00:30:00.000Z',
      as_of_at: '2026-04-08T00:30:00.000Z',
    })

    expect(report.summary.hedge_success_probability).toBeLessThan(0.5)
    expect(report.summary.estimated_net_pnl_bps).toBeLessThan(0)
    expect(report.sizing.recommended_size_usd).toBeLessThan(report.sizing.base_size_usd)
    expect(report.summary.worst_case_kind).toBe('stale_edge')
    expect(report.failure_cases.find((failureCase) => failureCase.kind === 'stale_edge')?.probability).toBeGreaterThan(
      report.failure_cases.find((failureCase) => failureCase.kind === 'one_leg_fill')?.probability ?? 0,
    )
    expect(report.failure_cases.find((failureCase) => failureCase.kind === 'stale_edge')?.net_pnl_bps).toBeLessThan(0)
    expect(report.summary.notes.join(' ')).toContain('Worst-case failure mode is stale_edge.')
  })

  it('caps the simulated shadow size to the conservative recommendation when the requested preview size is larger', () => {
    const snapshot = makeSnapshot()
    const recommendation = makeRecommendation(snapshot)
    const tradeIntent = makeTradeIntent(snapshot)
    const microstructureReport = buildMicrostructureLabReport({
      snapshot,
      recommendation,
      trade_intent: tradeIntent,
      generated_at: '2026-04-08T00:00:00.000Z',
    })
    const staleSummary = makeStaleSummary(microstructureReport.summary)
    const staleEdge = makeExecutableEdge({
      evaluated_at: '2026-04-07T23:30:00.000Z',
      executable_edge_bps: 18,
      confidence_score: 0.31,
      notes: ['stale_edge_expired:true'],
    })

    const report = buildShadowArbitrageSimulation({
      executable_edge: staleEdge,
      microstructure_summary: staleSummary,
      size_usd: 250,
      generated_at: '2026-04-08T00:30:00.000Z',
      as_of_at: '2026-04-08T00:30:00.000Z',
    })
    const oneLegFill = report.failure_cases.find((failureCase) => failureCase.kind === 'one_leg_fill')

    expect(report.sizing.requested_size_usd).toBe(250)
    expect(report.sizing.recommended_size_usd).toBeLessThan(250)
    expect(report.sizing.simulated_size_usd).toBe(Math.min(
      report.sizing.requested_size_usd ?? Number.POSITIVE_INFINITY,
      report.sizing.recommended_size_usd,
    ))
    expect(report.sizing.simulated_size_usd).toBe(report.sizing.recommended_size_usd)
    expect(report.sizing.simulated_size_usd).toBeLessThan(report.sizing.requested_size_usd ?? Number.POSITIVE_INFINITY)
    expect(report.summary.estimated_net_pnl_usd).toBe(
      Number(((report.summary.estimated_net_pnl_bps * report.sizing.simulated_size_usd) / 10_000).toFixed(2)),
    )
    for (const failureCase of report.failure_cases) {
      expect(failureCase.net_pnl_usd).toBe(
        Number(((failureCase.net_pnl_bps * report.sizing.simulated_size_usd) / 10_000).toFixed(2)),
      )
    }
    expect(oneLegFill?.net_pnl_usd).toBe(
      Number((((oneLegFill?.net_pnl_bps ?? 0) * report.sizing.simulated_size_usd) / 10_000).toFixed(2)),
    )
    expect(report.summary.notes.join(' ')).toContain(
      'Requested size of 250 USD exceeds the conservative shadow recommendation',
    )
  })

  it('keeps a smaller requested size as-is instead of upsizing shadow pnl to the recommendation', () => {
    const snapshot = makeSnapshot()
    const recommendation = makeRecommendation(snapshot)
    const tradeIntent = makeTradeIntent(snapshot)
    const microstructureReport = buildMicrostructureLabReport({
      snapshot,
      recommendation,
      trade_intent: tradeIntent,
      generated_at: '2026-04-08T00:00:00.000Z',
    })
    const staleSummary = makeStaleSummary(microstructureReport.summary)
    const staleEdge = makeExecutableEdge({
      evaluated_at: '2026-04-07T23:30:00.000Z',
      executable_edge_bps: 18,
      confidence_score: 0.31,
      notes: ['stale_edge_expired:true'],
    })

    const report = buildShadowArbitrageSimulation({
      executable_edge: staleEdge,
      microstructure_summary: staleSummary,
      size_usd: 12,
      generated_at: '2026-04-08T00:30:00.000Z',
      as_of_at: '2026-04-08T00:30:00.000Z',
    })

    expect(report.sizing.requested_size_usd).toBe(12)
    expect(report.sizing.recommended_size_usd).toBeGreaterThan(12)
    expect(report.sizing.simulated_size_usd).toBe(12)
    expect(report.summary.estimated_net_pnl_usd).toBe(
      Number(((report.summary.estimated_net_pnl_bps * 12) / 10_000).toFixed(2)),
    )
    expect(report.summary.notes.join(' ')).not.toContain('exceeds the conservative shadow recommendation')
  })

  it('maps spread collapse into stale-edge risk and surfaces explicit ops notes', () => {
    const snapshot = makeSnapshot()
    const recommendation = makeRecommendation(snapshot, {
      confidence: 0.58,
      edge_bps: 140,
      spread_bps: 260,
    })
    const tradeIntent = makeTradeIntent(snapshot)
    const microstructureReport = buildMicrostructureLabReport({
      snapshot,
      recommendation,
      trade_intent: tradeIntent,
      generated_at: '2026-04-08T00:00:00.000Z',
    })
    const spreadCollapseSummary = makeSpreadCollapseSummary(microstructureReport.summary)
    const executableEdge = makeExecutableEdge({
      evaluated_at: '2026-04-08T00:00:00.000Z',
      executable_edge_bps: 160,
      confidence_score: 0.57,
      notes: ['stale_edge_expired:false'],
    })

    const report = buildShadowArbitrageSimulation({
      executable_edge: executableEdge,
      microstructure_summary: spreadCollapseSummary,
      generated_at: '2026-04-08T00:00:00.000Z',
      as_of_at: '2026-04-08T00:00:00.000Z',
    })

    expect(report.failure_cases.find((failureCase) => failureCase.kind === 'stale_edge')?.probability).toBeGreaterThan(
      report.failure_cases.find((failureCase) => failureCase.kind === 'one_leg_fill')?.probability ?? 0,
    )
    expect(report.failure_cases.find((failureCase) => failureCase.kind === 'stale_edge')?.probability).toBeGreaterThan(
      report.failure_cases.find((failureCase) => failureCase.kind === 'hedge_delay')?.probability ?? 0,
    )
    expect(report.summary.notes.join(' ')).toContain(
      'Spread collapse is folded into stale_edge risk because the quoted edge can vanish before the hedge locks.',
    )
    expect(report.summary.notes.join(' ')).toContain(
      'Microstructure lab recommends wait, so shadow sizing stays informational and conservative.',
    )
  })
})
