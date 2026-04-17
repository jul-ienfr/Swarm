import { describe, expect, it } from 'vitest'

import {
  deriveMarketRegime,
} from '@/lib/prediction-markets/strategy-regime'
import {
  marketDescriptorSchema,
  marketSnapshotSchema,
} from '@/lib/prediction-markets/schemas'

function makeSnapshot() {
  const market = marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: 'maker-regime-market',
    slug: 'maker-regime-market',
    question: 'Will the maker regime remain healthy?',
    outcomes: ['Yes', 'No'],
    active: true,
    closed: false,
    accepting_orders: true,
    restricted: false,
    liquidity_usd: 140_000,
    volume_usd: 1_000_000,
    volume_24h_usd: 50_000,
    best_bid: 0.47,
    best_ask: 0.49,
    last_trade_price: 0.48,
    tick_size: 0.01,
    min_order_size: 5,
    is_binary_yes_no: true,
    end_at: '2026-04-10T12:00:00.000Z',
    source_urls: ['https://example.com/maker-regime-market'],
  })

  return marketSnapshotSchema.parse({
    venue: market.venue,
    market,
    captured_at: '2026-04-09T00:00:00.000Z',
    yes_outcome_index: 0,
    yes_token_id: `${market.market_id}:yes`,
    yes_price: 0.48,
    no_price: 0.52,
    midpoint_yes: 0.48,
    best_bid_yes: 0.47,
    best_ask_yes: 0.49,
    spread_bps: 200,
    book: {
      token_id: `${market.market_id}:yes`,
      market_condition_id: `${market.market_id}:cond`,
      fetched_at: '2026-04-09T00:00:00.000Z',
      best_bid: 0.47,
      best_ask: 0.49,
      last_trade_price: 0.48,
      tick_size: 0.01,
      min_order_size: 5,
      bids: [{ price: 0.47, size: 500 }],
      asks: [{ price: 0.49, size: 450 }],
      depth_near_touch: 950,
    },
    history: [],
    source_urls: market.source_urls,
  })
}

describe('prediction markets strategy regime', () => {
  it('marks maker quoting as blocked when the market is too close to resolution and microstructure is critical', () => {
    const regime = deriveMarketRegime({
      snapshot: makeSnapshot(),
      as_of_at: '2026-04-10T08:30:00.000Z',
      microstructure_lab: {
        summary: {
          recommended_mode: 'wait',
          worst_case_kind: 'stale_quote',
          worst_case_severity: 'critical',
          execution_quality_score: 0.19,
          executable_deterioration_bps: 72,
          scenario_overview: ['critical quote fade'],
        },
      } as never,
    })

    expect(regime.maker_quote_state).toBe('blocked')
    expect(regime.maker_quote_freshness_budget_ms).toBe(0)
    expect(regime.summary).toContain('maker_quote=blocked')
    expect(regime.reasons).toEqual(expect.arrayContaining([
      'maker_quote_state:blocked',
      'maker_quote_freshness_budget_ms:0',
    ]))
  })
})
