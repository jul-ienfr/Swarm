import { describe, expect, it } from 'vitest'
import {
  marketDescriptorSchema,
  marketSnapshotSchema,
  type MarketDescriptor,
  type MarketSnapshot,
} from '@/lib/prediction-markets/schemas'
import {
  buildCanonicalCrossVenueEventKey,
  detectCrossVenueArbitrageCandidates,
  evaluateCrossVenuePair,
  findCrossVenueMatches,
} from '@/lib/prediction-markets/cross-venue'

function makeDescriptor(overrides: Partial<MarketDescriptor> = {}): MarketDescriptor {
  return marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: 'market-1',
    slug: 'market-1',
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
    start_at: '2026-12-01T00:00:00.000Z',
    end_at: '2026-12-31T23:59:59.000Z',
    source_urls: ['https://example.com/markets/market-1'],
    ...overrides,
  })
}

function makeSnapshot(
  market: MarketDescriptor,
  overrides: Partial<MarketSnapshot> = {},
): MarketSnapshot {
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
    ...overrides,
  })
}

describe('prediction markets cross-venue matching', () => {
  it('builds a high-confidence cross-venue match with a read-only arbitrage candidate', () => {
    const asOfAt = '2026-04-08T00:05:00.000Z'
    const polymarket = makeDescriptor({
      venue: 'polymarket',
      market_id: 'poly-btc-100k',
      slug: 'poly-btc-100k',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      best_bid: 0.43,
      best_ask: 0.44,
      last_trade_price: 0.435,
      source_urls: ['https://example.com/polymarket/btc-100k'],
    })
    const kalshi = makeDescriptor({
      venue: 'kalshi',
      market_id: 'kalshi-btc-100k',
      slug: 'kalshi-btc-100k',
      question: 'Will Bitcoin be above 100000 on 2026-12-31?',
      best_bid: 0.58,
      best_ask: 0.59,
      last_trade_price: 0.585,
      source_urls: ['https://example.com/kalshi/btc-100k'],
    })

    const evaluation = evaluateCrossVenuePair({
      left: polymarket,
      right: kalshi,
      leftSnapshot: makeSnapshot(polymarket),
      rightSnapshot: makeSnapshot(kalshi),
      asOfAt,
    })

    expect(evaluation.compatible).toBe(true)
    expect(evaluation.confidence_score).toBeGreaterThan(0.9)
    expect(evaluation.opportunity_type).toBe('true_arbitrage')
    expect(evaluation.match.manual_review_required).toBe(false)
    expect(evaluation.canonical_event_id).toContain('cve:')
    expect(evaluation.canonical_event_key).toContain('2026-12-31')
    expect(evaluation.mismatch_reasons).toEqual([])
    expect(evaluation.executable_edge).not.toBeNull()
    expect(evaluation.executable_edge).toMatchObject({
      opportunity_type: 'true_arbitrage',
      executable: true,
    })
    expect(evaluation.market_equivalence_proof).toMatchObject({
      proof_status: 'proven',
    })
    expect(evaluation.arbitrage_candidate).not.toBeNull()
    expect(evaluation.arbitrage_candidate).toMatchObject({
      candidate_type: 'yes_yes_spread',
      opportunity_type: 'true_arbitrage',
      buy_ref: { venue: 'polymarket', market_id: 'poly-btc-100k' },
      sell_ref: { venue: 'kalshi', market_id: 'kalshi-btc-100k' },
      executable: true,
    })
    expect(evaluation.arbitrage_candidate?.gross_spread_bps).toBe(1400)
    expect(evaluation.arbitrage_candidate?.executable_edge.executable_edge_bps).toBeGreaterThan(0)
    expect(evaluation.arbitrage_candidate?.arb_plan.legs).toHaveLength(2)
  })

  it('applies explicit fragmentation, latency, and confidence penalties to executable edges', () => {
    const asOfAt = '2026-04-08T00:10:00.000Z'
    const polymarket = makeDescriptor({
      venue: 'polymarket',
      market_id: 'poly-btc-100k-fast',
      slug: 'poly-btc-100k-fast',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      best_bid: 0.43,
      best_ask: 0.44,
      last_trade_price: 0.435,
      source_urls: ['https://example.com/polymarket/btc-100k-fast'],
    })
    const kalshi = makeDescriptor({
      venue: 'kalshi',
      market_id: 'kalshi-btc-100k-fast',
      slug: 'kalshi-btc-100k-fast',
      question: 'Will Bitcoin be above 100000 on 2026-12-31?',
      best_bid: 0.58,
      best_ask: 0.59,
      last_trade_price: 0.585,
      source_urls: ['https://example.com/kalshi/btc-100k-fast'],
    })

    const evaluation = evaluateCrossVenuePair({
      left: polymarket,
      right: kalshi,
      leftSnapshot: makeSnapshot(polymarket, { captured_at: '2026-04-08T00:00:00.000Z' }),
      rightSnapshot: makeSnapshot(kalshi, { captured_at: '2026-04-08T00:00:00.000Z' }),
      asOfAt,
    })

    expect(evaluation.executable_edge).not.toBeNull()
    expect(evaluation.executable_edge?.executable).toBe(true)
    expect(evaluation.executable_edge?.notes).toEqual(
      expect.arrayContaining([
        'stale_edge_expired:false',
        'capital_fragmentation_penalty_bps:8',
        'transfer_latency_penalty_bps:2',
      ]),
    )
    expect(
      evaluation.executable_edge?.notes.some((note) => note.startsWith('low_confidence_penalty_bps:')),
    ).toBe(true)
    expect(evaluation.executable_edge?.executable_edge_bps).toBeLessThan(
      evaluation.executable_edge?.gross_spread_bps ?? 0,
    )
  })

  it('expires stale executable edges and suppresses arbitrage candidates after the freshness budget', () => {
    const asOfAt = '2026-04-08T00:20:00.000Z'
    const polymarket = makeDescriptor({
      venue: 'polymarket',
      market_id: 'poly-btc-100k-stale',
      slug: 'poly-btc-100k-stale',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      best_bid: 0.43,
      best_ask: 0.44,
      last_trade_price: 0.435,
      source_urls: ['https://example.com/polymarket/btc-100k-stale'],
    })
    const kalshi = makeDescriptor({
      venue: 'kalshi',
      market_id: 'kalshi-btc-100k-stale',
      slug: 'kalshi-btc-100k-stale',
      question: 'Will Bitcoin be above 100000 on 2026-12-31?',
      best_bid: 0.58,
      best_ask: 0.59,
      last_trade_price: 0.585,
      source_urls: ['https://example.com/kalshi/btc-100k-stale'],
    })

    const evaluation = evaluateCrossVenuePair({
      left: polymarket,
      right: kalshi,
      leftSnapshot: makeSnapshot(polymarket, { captured_at: '2026-04-08T00:00:00.000Z' }),
      rightSnapshot: makeSnapshot(kalshi, { captured_at: '2026-04-08T00:00:00.000Z' }),
      asOfAt,
    })

    expect(evaluation.executable_edge).not.toBeNull()
    expect(evaluation.executable_edge?.executable).toBe(false)
    expect(evaluation.executable_edge?.notes).toContain('stale_edge_expired:true')
    expect(evaluation.executable_edge?.notes.some((note) => note.startsWith('stale_edge_penalty_bps:'))).toBe(true)
    expect(evaluation.arbitrage_candidate).toBeNull()
    expect(evaluation.opportunity_type).toBe('relative_value')
  })

  it('flags opposite propositions as mismatches even when event context overlaps', () => {
    const alice = makeDescriptor({
      venue: 'polymarket',
      market_id: 'alice-race',
      slug: 'alice-race',
      question: 'Will Alice win the 2026 mayoral race?',
      end_at: '2026-11-01T00:00:00.000Z',
      source_urls: ['https://example.com/polymarket/alice-race'],
    })
    const bob = makeDescriptor({
      venue: 'kalshi',
      market_id: 'bob-race',
      slug: 'bob-race',
      question: 'Will Bob win the 2026 mayoral race?',
      end_at: '2026-11-01T00:00:00.000Z',
      source_urls: ['https://example.com/kalshi/bob-race'],
    })

    const evaluation = evaluateCrossVenuePair({
      left: alice,
      right: bob,
    })

    expect(evaluation.compatible).toBe(false)
    expect(evaluation.opportunity_type).toBe('comparison_only')
    expect(evaluation.match.manual_review_required).toBe(true)
    expect(evaluation.mismatch_reasons).toContain('proposition_subject_mismatch')
    expect(evaluation.mismatch_reasons).toContain('low_semantic_similarity')
    expect(evaluation.market_equivalence_proof.proof_status).toBe('blocked')
    expect(evaluation.arbitrage_candidate).toBeNull()
  })

  it('finds only cross-venue pairs by default and keeps canonical keys stable', () => {
    const asOfAt = '2026-04-08T00:05:00.000Z'
    const polymarket = makeDescriptor({
      venue: 'polymarket',
      market_id: 'poly-btc-100k',
      slug: 'poly-btc-100k',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      source_urls: ['https://example.com/polymarket/btc-100k'],
    })
    const kalshi = makeDescriptor({
      venue: 'kalshi',
      market_id: 'kalshi-btc-100k',
      slug: 'kalshi-btc-100k',
      question: 'Will Bitcoin be above 100000 on 2026-12-31?',
      source_urls: ['https://example.com/kalshi/btc-100k'],
    })
    const sameVenueNoise = makeDescriptor({
      venue: 'polymarket',
      market_id: 'poly-eth-10k',
      slug: 'poly-eth-10k',
      question: 'Will Ethereum exceed 10000 by 2026-12-31?',
      source_urls: ['https://example.com/polymarket/eth-10k'],
    })

    const matches = findCrossVenueMatches({
      markets: [polymarket, kalshi, sameVenueNoise],
      snapshots: [
        makeSnapshot(polymarket),
        makeSnapshot(kalshi),
        makeSnapshot(sameVenueNoise),
      ],
      asOfAt,
    })

    expect(matches).toHaveLength(1)
    expect(matches[0].match.left_market_ref.venue).not.toBe(matches[0].match.right_market_ref.venue)

    const directKey = buildCanonicalCrossVenueEventKey([polymarket, kalshi])
    const reverseKey = buildCanonicalCrossVenueEventKey([kalshi, polymarket])
    expect(directKey).toBe(reverseKey)
    expect(matches[0].canonical_event_key).toBe(directKey)
  })

  it('extracts and sorts arbitrage candidates from evaluated matches', () => {
    const asOfAt = '2026-04-08T00:05:00.000Z'
    const cheap = makeDescriptor({
      venue: 'polymarket',
      market_id: 'cheap',
      slug: 'cheap',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      best_bid: 0.39,
      best_ask: 0.4,
      last_trade_price: 0.395,
      source_urls: ['https://example.com/polymarket/cheap'],
    })
    const rich = makeDescriptor({
      venue: 'kalshi',
      market_id: 'rich',
      slug: 'rich',
      question: 'Will Bitcoin be above 100000 on 2026-12-31?',
      best_bid: 0.61,
      best_ask: 0.62,
      last_trade_price: 0.615,
      source_urls: ['https://example.com/kalshi/rich'],
    })
    const secondPoly = makeDescriptor({
      venue: 'polymarket',
      market_id: 'second-poly',
      slug: 'second-poly',
      question: 'Will Solana exceed 500 by 2026-12-31?',
      best_bid: 0.2,
      best_ask: 0.21,
      last_trade_price: 0.205,
      source_urls: ['https://example.com/polymarket/sol-500'],
    })
    const secondKalshi = makeDescriptor({
      venue: 'kalshi',
      market_id: 'second-kalshi',
      slug: 'second-kalshi',
      question: 'Will Solana be above 500 on 2026-12-31?',
      best_bid: 0.29,
      best_ask: 0.3,
      last_trade_price: 0.295,
      source_urls: ['https://example.com/kalshi/sol-500'],
    })

    const matches = findCrossVenueMatches({
      markets: [cheap, rich, secondPoly, secondKalshi],
      snapshots: [
        makeSnapshot(cheap),
        makeSnapshot(rich),
        makeSnapshot(secondPoly),
        makeSnapshot(secondKalshi),
      ],
      asOfAt,
    })
    const candidates = detectCrossVenueArbitrageCandidates(matches)

    expect(candidates).toHaveLength(2)
    expect(candidates[0].gross_spread_bps).toBeGreaterThan(candidates[1].gross_spread_bps)
    expect(candidates[0]).toMatchObject({
      opportunity_type: 'true_arbitrage',
      buy_ref: { market_id: 'cheap' },
      sell_ref: { market_id: 'rich' },
    })
  })
})
