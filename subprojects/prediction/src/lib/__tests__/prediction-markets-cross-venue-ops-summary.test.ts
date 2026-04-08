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

describe('prediction markets cross-venue ops summary', () => {
  it('groups cross-venue evaluations into compatible, manual review, and comparison-only buckets', () => {
    const asOfAt = '2026-04-08T00:05:00.000Z'
    const compatibleLeft = makeDescriptor({
      venue: 'polymarket',
      market_id: 'btc-left',
      slug: 'btc-left',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      best_bid: 0.43,
      best_ask: 0.44,
      last_trade_price: 0.435,
    })
    const compatibleRight = makeDescriptor({
      venue: 'kalshi',
      market_id: 'btc-right',
      slug: 'btc-right',
      question: 'Will Bitcoin be above 100000 on 2026-12-31?',
      best_bid: 0.58,
      best_ask: 0.59,
      last_trade_price: 0.585,
    })

    const manualReviewLeft = makeDescriptor({
      venue: 'polymarket',
      market_id: 'payout-left',
      slug: 'payout-left',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
    })
    const manualReviewRight = makeDescriptor({
      venue: 'kalshi',
      market_id: 'payout-right',
      slug: 'payout-right',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      outcomes: ['Yes', 'No', 'Maybe'],
      is_binary_yes_no: false,
    })

    const relativeValueLeft = makeDescriptor({
      venue: 'polymarket',
      market_id: 'rv-left',
      slug: 'rv-left',
      question: 'Will CPI be above 3 percent in 2026?',
      best_bid: 0.43,
      best_ask: 0.44,
      last_trade_price: 0.435,
    })
    const relativeValueRight = makeDescriptor({
      venue: 'kalshi',
      market_id: 'rv-right',
      slug: 'rv-right',
      question: 'Will CPI be above 3 percent in 2026?',
      best_bid: 0.45,
      best_ask: 0.46,
      last_trade_price: 0.455,
    })
    const signalLeft = makeDescriptor({
      venue: 'polymarket',
      market_id: 'signal-left',
      slug: 'signal-left',
      question: 'Will the city council approve the 2026 budget?',
      end_at: '2026-12-31T23:59:59.000Z',
    })
    const signalRight = makeDescriptor({
      venue: 'kalshi',
      market_id: 'signal-right',
      slug: 'signal-right',
      question: 'Will the city council approve the 2026 budget?',
      venue_type: 'experimental',
      end_at: '2026-12-31T23:59:59.000Z',
    })

    const compatibleEvaluation = evaluateCrossVenuePair({
      left: compatibleLeft,
      right: compatibleRight,
      leftSnapshot: makeSnapshot(compatibleLeft),
      rightSnapshot: makeSnapshot(compatibleRight),
      asOfAt,
    })
    const manualReviewEvaluation = evaluateCrossVenuePair({
      left: manualReviewLeft,
      right: manualReviewRight,
    })
    const relativeValueEvaluation = evaluateCrossVenuePair({
      left: relativeValueLeft,
      right: relativeValueRight,
      minArbitrageSpreadBps: 150,
      asOfAt,
    })
    const signalEvaluation = evaluateCrossVenuePair({
      left: signalLeft,
      right: signalRight,
    })

    const summary = summarizeCrossVenueIntelligence([
      compatibleEvaluation,
      manualReviewEvaluation,
      relativeValueEvaluation,
      signalEvaluation,
    ])

    expect(summary.total_pairs).toBe(4)
    expect(summary.compatible).toHaveLength(2)
    expect(summary.manual_review).toHaveLength(1)
    expect(summary.comparison_only).toHaveLength(1)
    expect(summary.opportunity_type_counts).toEqual({
      comparison_only: 1,
      relative_value: 1,
      cross_venue_signal: 1,
      true_arbitrage: 1,
    })
    expect(summary.blocking_reasons).toEqual(['non_binary_contract', 'payout_shape_mismatch'])
    expect(summary.highest_confidence_candidate).toMatchObject({
      candidate_type: 'yes_yes_spread',
      opportunity_type: 'true_arbitrage',
      buy_ref: { venue: 'polymarket', market_id: 'btc-left' },
      sell_ref: { venue: 'kalshi', market_id: 'btc-right' },
      executable: true,
    })
    expect(summary.compatible[0]?.canonical_event_id).toBe(compatibleEvaluation.canonical_event_id)
    expect(summary.manual_review[0]?.mismatch_reasons).toContain('non_binary_contract')
    expect(summary.comparison_only[0]?.opportunity_type).toBe('cross_venue_signal')
    expect(summary.compatible[1]?.opportunity_type).toBe('relative_value')
  })
})
