import { describe, expect, it } from 'vitest'
import {
  marketDescriptorSchema,
  type MarketDescriptor,
} from '@/lib/prediction-markets/schemas'
import {
  evaluateCrossVenuePair,
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
    start_at: '2026-12-01T00:00:00.000Z',
    end_at: '2026-12-31T23:59:59.000Z',
    source_urls: [`https://example.com/markets/${marketId}`],
    ...overrides,
  })
}

describe('prediction markets cross-venue compatibility mismatches', () => {
  it('flags resolution horizon drift without inventing payout or currency mismatches', () => {
    const left = makeDescriptor({
      venue: 'polymarket',
      market_id: 'resolution-left',
      slug: 'resolution-left',
      question: 'Will the city council approve the 2026 budget?',
      end_at: '2026-12-31T23:59:59.000Z',
    })
    const right = makeDescriptor({
      venue: 'kalshi',
      market_id: 'resolution-right',
      slug: 'resolution-right',
      question: 'Will the city council approve the 2026 budget?',
      end_at: '2027-02-15T23:59:59.000Z',
    })

    const evaluation = evaluateCrossVenuePair({ left, right })

    expect(evaluation.compatible).toBe(false)
    expect(evaluation.match.manual_review_required).toBe(true)
    expect(evaluation.match.resolution_compatibility_score).toBeLessThan(1)
    expect(evaluation.match.payout_compatibility_score).toBe(1)
    expect(evaluation.match.currency_compatibility_score).toBe(1)
    expect(evaluation.mismatch_reasons).toContain('time_horizon_mismatch')
    expect(evaluation.mismatch_reasons).not.toContain('payout_shape_mismatch')
  })

  it('flags payout-shape divergence when one side is non-binary', () => {
    const left = makeDescriptor({
      venue: 'polymarket',
      market_id: 'payout-left',
      slug: 'payout-left',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      end_at: '2026-12-31T23:59:59.000Z',
    })
    const right = makeDescriptor({
      venue: 'kalshi',
      market_id: 'payout-right',
      slug: 'payout-right',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      outcomes: ['Yes', 'No', 'Maybe'],
      is_binary_yes_no: false,
      end_at: '2026-12-31T23:59:59.000Z',
    })

    const evaluation = evaluateCrossVenuePair({ left, right })

    expect(evaluation.compatible).toBe(false)
    expect(evaluation.match.manual_review_required).toBe(true)
    expect(evaluation.match.resolution_compatibility_score).toBeLessThan(1)
    expect(evaluation.match.payout_compatibility_score).toBe(0.3)
    expect(evaluation.match.currency_compatibility_score).toBe(1)
    expect(evaluation.mismatch_reasons).toContain('non_binary_contract')
    expect(evaluation.mismatch_reasons).toContain('payout_shape_mismatch')
  })

  it('keeps currency compatibility neutral on an aligned cross-venue pair', () => {
    const left = makeDescriptor({
      venue: 'polymarket',
      market_id: 'currency-left',
      slug: 'currency-left',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
    })
    const right = makeDescriptor({
      venue: 'kalshi',
      market_id: 'currency-right',
      slug: 'currency-right',
      question: 'Will Bitcoin be above 100000 on 2026-12-31?',
    })

    const evaluation = evaluateCrossVenuePair({ left, right })

    expect(evaluation.compatible).toBe(true)
    expect(evaluation.match.manual_review_required).toBe(false)
    expect(evaluation.match.resolution_compatibility_score).toBe(1)
    expect(evaluation.match.payout_compatibility_score).toBe(1)
    expect(evaluation.match.currency_compatibility_score).toBe(1)
    expect(evaluation.mismatch_reasons).toEqual([])
  })
})
