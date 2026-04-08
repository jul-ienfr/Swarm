import { describe, expect, it } from 'vitest'
import {
  marketDescriptorSchema,
  type MarketDescriptor,
} from '@/lib/prediction-markets/schemas'
import {
  evaluateCrossVenuePair,
  findCrossVenueMatches,
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
    is_binary_yes_no: true,
    start_at: '2026-01-01T00:00:00.000Z',
    end_at: '2026-12-31T23:59:59.000Z',
    source_urls: [`https://example.com/markets/${marketId}`],
    ...overrides,
  })
}

describe('prediction markets cross-venue false matches', () => {
  it.each([
    {
      label: 'numeric threshold drift',
      left: makeDescriptor({
        venue: 'polymarket',
        market_id: 'cpi-high-left',
        slug: 'cpi-high-left',
        question: 'Will CPI be above 3, 4, or 5 percent in 2026?',
        end_at: '2026-12-31T23:59:59.000Z',
      }),
      right: makeDescriptor({
        venue: 'kalshi',
        market_id: 'cpi-high-right',
        slug: 'cpi-high-right',
        question: 'Will CPI be above 9, 10, or 11 percent in 2026?',
        end_at: '2026-12-31T23:59:59.000Z',
      }),
      expectedReasons: ['numeric_threshold_mismatch', 'low_semantic_similarity'],
    },
    {
      label: 'temporal horizon drift',
      left: makeDescriptor({
        venue: 'polymarket',
        market_id: 'timing-left',
        slug: 'timing-left',
        question: 'Will the city council approve the 2026 budget?',
        end_at: '2026-12-31T23:59:59.000Z',
      }),
      right: makeDescriptor({
        venue: 'kalshi',
        market_id: 'timing-right',
        slug: 'timing-right',
        question: 'Will the city council approve the 2026 budget?',
        end_at: '2027-01-15T23:59:59.000Z',
      }),
      expectedReasons: ['time_horizon_mismatch'],
    },
    {
      label: 'subject mismatch',
      left: makeDescriptor({
        venue: 'polymarket',
        market_id: 'subject-left',
        slug: 'subject-left',
        question: 'Will Alice win the 2026 mayoral race?',
        end_at: '2026-11-01T00:00:00.000Z',
      }),
      right: makeDescriptor({
        venue: 'kalshi',
        market_id: 'subject-right',
        slug: 'subject-right',
        question: 'Will Bob win the 2026 mayoral race?',
        end_at: '2026-11-01T00:00:00.000Z',
      }),
      expectedReasons: ['proposition_subject_mismatch', 'low_semantic_similarity'],
    },
    {
      label: 'polarity mismatch',
      left: makeDescriptor({
        venue: 'polymarket',
        market_id: 'polarity-left',
        slug: 'polarity-left',
        question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
        end_at: '2026-12-31T23:59:59.000Z',
      }),
      right: makeDescriptor({
        venue: 'kalshi',
        market_id: 'polarity-right',
        slug: 'polarity-right',
        question: 'Will Bitcoin not exceed 100000 by 2026-12-31?',
        end_at: '2026-12-31T23:59:59.000Z',
      }),
      expectedReasons: ['polarity_mismatch'],
    },
  ])('rejects $label cross-venue pairs', ({ left, right, expectedReasons }) => {
    const evaluation = evaluateCrossVenuePair({
      left,
      right,
      minSemanticScore: 0.7,
    })

    expect(evaluation.compatible).toBe(false)
    expect(evaluation.match.manual_review_required).toBe(true)
    expect(evaluation.arbitrage_candidate).toBeNull()
    for (const reason of expectedReasons) {
      expect(evaluation.mismatch_reasons).toContain(reason)
    }
  })

  it('keeps false matches out of discovery while still returning the one genuine cross-venue pair', () => {
    const numericFalseMatch = {
      left: makeDescriptor({
        venue: 'polymarket',
        market_id: 'cpi-high-left',
        slug: 'cpi-high-left',
        question: 'Will CPI be above 3, 4, or 5 percent in 2026?',
      }),
      right: makeDescriptor({
        venue: 'kalshi',
        market_id: 'cpi-high-right',
        slug: 'cpi-high-right',
        question: 'Will CPI be above 9, 10, or 11 percent in 2026?',
      }),
    }
    const temporalFalseMatch = {
      left: makeDescriptor({
        venue: 'polymarket',
        market_id: 'timing-left',
        slug: 'timing-left',
        question: 'Will the city council approve the 2026 budget?',
        end_at: '2026-12-31T23:59:59.000Z',
      }),
      right: makeDescriptor({
        venue: 'kalshi',
        market_id: 'timing-right',
        slug: 'timing-right',
        question: 'Will the city council approve the 2026 budget?',
        end_at: '2027-01-15T23:59:59.000Z',
      }),
    }
    const subjectFalseMatch = {
      left: makeDescriptor({
        venue: 'polymarket',
        market_id: 'subject-left',
        slug: 'subject-left',
        question: 'Will Alice win the 2026 mayoral race?',
        end_at: '2026-11-01T00:00:00.000Z',
      }),
      right: makeDescriptor({
        venue: 'kalshi',
        market_id: 'subject-right',
        slug: 'subject-right',
        question: 'Will Bob win the 2026 mayoral race?',
        end_at: '2026-11-01T00:00:00.000Z',
      }),
    }
    const genuineMatchLeft = makeDescriptor({
      venue: 'polymarket',
      market_id: 'btc-left',
      slug: 'btc-left',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      end_at: '2026-12-31T23:59:59.000Z',
      best_bid: 0.43,
      best_ask: 0.44,
      last_trade_price: 0.435,
      source_urls: ['https://example.com/markets/btc-left'],
    })
    const genuineMatchRight = makeDescriptor({
      venue: 'kalshi',
      market_id: 'btc-right',
      slug: 'btc-right',
      question: 'Will Bitcoin be above 100000 on 2026-12-31?',
      end_at: '2026-12-31T23:59:59.000Z',
      best_bid: 0.58,
      best_ask: 0.59,
      last_trade_price: 0.585,
      source_urls: ['https://example.com/markets/btc-right'],
    })

    const matches = findCrossVenueMatches({
      markets: [
        numericFalseMatch.left,
        numericFalseMatch.right,
        temporalFalseMatch.left,
        temporalFalseMatch.right,
        subjectFalseMatch.left,
        subjectFalseMatch.right,
        genuineMatchLeft,
        genuineMatchRight,
      ],
      minSemanticScore: 0.7,
    })

    expect(matches).toHaveLength(1)
    expect(matches[0].match.left_market_ref.market_id).toBe('btc-left')
    expect(matches[0].match.right_market_ref.market_id).toBe('btc-right')
    expect(matches[0].compatible).toBe(true)
    expect(matches[0].mismatch_reasons).toEqual([])
  })
})
