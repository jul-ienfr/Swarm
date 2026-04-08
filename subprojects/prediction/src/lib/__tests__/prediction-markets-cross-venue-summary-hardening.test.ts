import { describe, expect, it } from 'vitest'
import {
  marketDescriptorSchema,
  marketSnapshotSchema,
  type MarketDescriptor,
  type MarketSnapshot,
} from '@/lib/prediction-markets/schemas'
import {
  evaluateCrossVenuePair,
  summarizeCrossVenueIntelligence,
} from '@/lib/prediction-markets/cross-venue'

function makeDescriptor(overrides: Partial<MarketDescriptor> = {}): MarketDescriptor {
  const marketId = overrides.market_id ?? 'market-1'

  return marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: marketId,
    slug: marketId,
    question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
    outcomes: ['Yes', 'No'],
    active: true,
    closed: false,
    accepting_orders: true,
    restricted: false,
    liquidity_usd: 100_000,
    volume_usd: 2_000_000,
    volume_24h_usd: 120_000,
    best_bid: 0.43,
    best_ask: 0.44,
    last_trade_price: 0.435,
    tick_size: 0.01,
    min_order_size: 5,
    is_binary_yes_no: true,
    start_at: '2026-01-01T00:00:00.000Z',
    end_at: '2026-12-31T23:59:59.000Z',
    source_urls: [`https://example.com/markets/${marketId}`],
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
    yes_price: market.last_trade_price ?? null,
    no_price: market.last_trade_price != null ? Number((1 - market.last_trade_price).toFixed(6)) : null,
    midpoint_yes: market.last_trade_price ?? null,
    best_bid_yes: market.best_bid ?? null,
    best_ask_yes: market.best_ask ?? null,
    spread_bps: market.best_bid != null && market.best_ask != null
      ? Number(((market.best_ask - market.best_bid) * 10_000).toFixed(2))
      : null,
    book: null,
    history: [],
    source_urls: market.source_urls,
  })
}

describe('prediction markets cross-venue summary hardening', () => {
  it('deduplicates hard blocking reasons while keeping soft mismatches out of the blocking summary', () => {
    const hardMismatchA = evaluateCrossVenuePair({
      left: makeDescriptor({
        venue: 'polymarket',
        market_id: 'hard-left-a',
        slug: 'hard-left-a',
      }),
      right: makeDescriptor({
        venue: 'kalshi',
        market_id: 'hard-right-a',
        slug: 'hard-right-a',
        outcomes: ['Yes', 'No', 'Maybe'],
        is_binary_yes_no: false,
      }),
    })
    const hardMismatchB = evaluateCrossVenuePair({
      left: makeDescriptor({
        venue: 'polymarket',
        market_id: 'hard-left-b',
        slug: 'hard-left-b',
      }),
      right: makeDescriptor({
        venue: 'kalshi',
        market_id: 'hard-right-b',
        slug: 'hard-right-b',
        outcomes: ['Yes', 'No', 'Maybe'],
        is_binary_yes_no: false,
      }),
    })
    const softMismatch = evaluateCrossVenuePair({
      left: makeDescriptor({
        venue: 'polymarket',
        market_id: 'soft-left',
        slug: 'soft-left',
        question: 'Will CPI be above 3, 4, or 5 percent in 2026?',
      }),
      right: makeDescriptor({
        venue: 'kalshi',
        market_id: 'soft-right',
        slug: 'soft-right',
        question: 'Will CPI be above 9, 10, or 11 percent in 2026?',
      }),
      minSemanticScore: 0.7,
    })

    const summary = summarizeCrossVenueIntelligence([
      hardMismatchA,
      hardMismatchB,
      softMismatch,
    ])

    expect(summary.total_pairs).toBe(3)
    expect(summary.compatible).toHaveLength(0)
    expect(summary.manual_review).toHaveLength(2)
    expect(summary.comparison_only).toHaveLength(1)
    expect(summary.blocking_reasons).toEqual([
      'non_binary_contract',
      'payout_shape_mismatch',
    ])
    expect(summary.highest_confidence_candidate).toBeNull()
    expect(summary.comparison_only[0]?.mismatch_reasons).toContain('numeric_threshold_mismatch')
    expect(summary.blocking_reasons).not.toContain('numeric_threshold_mismatch')
  })

  it('prefers the highest-confidence compatible spread in ops summary even when another pair has a larger spread', () => {
    const asOfAt = '2026-04-08T00:05:00.000Z'
    const highConfidenceLeft = makeDescriptor({
      venue: 'polymarket',
      market_id: 'btc-high-confidence-left',
      slug: 'btc-high-confidence-left',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      best_bid: 0.43,
      best_ask: 0.44,
      last_trade_price: 0.435,
    })
    const highConfidenceRight = makeDescriptor({
      venue: 'kalshi',
      market_id: 'btc-high-confidence-right',
      slug: 'btc-high-confidence-right',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      best_bid: 0.46,
      best_ask: 0.47,
      last_trade_price: 0.465,
    })
    const widerSpreadLeft = makeDescriptor({
      venue: 'polymarket',
      market_id: 'btc-wider-spread-left',
      slug: 'btc-wider-spread-left',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      best_bid: 0.39,
      best_ask: 0.4,
      last_trade_price: 0.395,
    })
    const widerSpreadRight = makeDescriptor({
      venue: 'kalshi',
      market_id: 'btc-wider-spread-right',
      slug: 'btc-wider-spread-right',
      question: 'Will Bitcoin be above 100000 on 2026-12-31?',
      best_bid: 0.61,
      best_ask: 0.62,
      last_trade_price: 0.615,
    })

    const highConfidenceEvaluation = evaluateCrossVenuePair({
      left: highConfidenceLeft,
      right: highConfidenceRight,
      leftSnapshot: makeSnapshot(highConfidenceLeft),
      rightSnapshot: makeSnapshot(highConfidenceRight),
      asOfAt,
    })
    const widerSpreadEvaluation = evaluateCrossVenuePair({
      left: widerSpreadLeft,
      right: widerSpreadRight,
      leftSnapshot: makeSnapshot(widerSpreadLeft),
      rightSnapshot: makeSnapshot(widerSpreadRight),
      asOfAt,
    })

    const summary = summarizeCrossVenueIntelligence([
      highConfidenceEvaluation,
      widerSpreadEvaluation,
    ])

    expect(summary.compatible).toHaveLength(2)
    expect(highConfidenceEvaluation.confidence_score).toBeGreaterThan(widerSpreadEvaluation.confidence_score)
    expect(widerSpreadEvaluation.arbitrage_candidate?.net_spread_bps).toBeGreaterThan(
      highConfidenceEvaluation.arbitrage_candidate?.net_spread_bps ?? 0,
    )
    expect(summary.highest_confidence_candidate).toMatchObject({
      buy_ref: {
        venue: 'polymarket',
        market_id: 'btc-high-confidence-left',
      },
      sell_ref: {
        venue: 'kalshi',
        market_id: 'btc-high-confidence-right',
      },
      executable: true,
    })
  })
})
