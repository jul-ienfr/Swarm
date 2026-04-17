import { describe, expect, it } from 'vitest'
import {
  assessBinaryParity,
  assessMultiOutcomeParity,
  assessOddsDivergence,
  assessOrderbookImbalance,
  assessSpreadCapture,
  calculateKellySizing,
} from '@/lib/prediction-markets/quant-pack'

describe('quant pack', () => {
  it('detects orderbook imbalance on the bid side', () => {
    const report = assessOrderbookImbalance({
      market_id: 'mkt-1',
      question: 'Will the market stay stable?',
      token_id: 'token-1',
      market_yes_price: 0.48,
      best_bid: 0.47,
      best_ask: 0.50,
      spread: 0.03,
      fee_rate: 0.02,
      bids: [
        { price: 0.47, size: 800 },
        { price: 0.46, size: 500 },
      ],
      asks: [
        { price: 0.50, size: 100 },
        { price: 0.51, size: 120 },
      ],
    })

    expect(report.kind).toBe('orderbook_imbalance')
    expect(report.side).toBe('yes')
    expect(report.viable).toBe(true)
    expect(report.edge_bps).toBeGreaterThan(0)
    expect(report.summary).toContain('YES imbalance')
  })

  it('treats weak or stale spread capture as blocked and strong spread as viable', () => {
    const blocked = assessSpreadCapture({
      market_id: 'mkt-2',
      question: 'Will the spread narrow?',
      best_bid: 0.48,
      best_ask: 0.50,
      fee_rate: 0.02,
      freshness_gap_ms: 500,
      freshness_budget_ms: 250,
    })
    expect(blocked.kind).toBe('spread_capture')
    expect(blocked.viable).toBe(false)
    expect(blocked.blockers).toContain('quote_stale')

    const viable = assessSpreadCapture({
      market_id: 'mkt-2',
      question: 'Will the spread narrow?',
      best_bid: 0.44,
      best_ask: 0.56,
      fee_rate: 0.02,
      freshness_gap_ms: 50,
      freshness_budget_ms: 250,
    })
    expect(viable.viable).toBe(true)
    expect(viable.net_spread_bps).toBeGreaterThan(0)
  })

  it('detects bookmaker divergence versus the market price', () => {
    const report = assessOddsDivergence({
      market_id: 'mkt-3',
      question: 'Will the ruling pass?',
      market_yes_price: 0.54,
      fee_rate: 0.02,
      bookmaker_quotes: [
        { bookmaker: 'pinnacle', outcome: 'yes', decimal_odds: 2.2, implied_prob: 0.455, is_sharp: true },
        { bookmaker: 'betfair', outcome: 'yes', decimal_odds: 2.1, implied_prob: 0.476, is_sharp: true },
        { bookmaker: 'draftkings', outcome: 'yes', decimal_odds: 2.0, implied_prob: 0.5, is_sharp: false },
      ],
    })

    expect(report.kind).toBe('odds_divergence')
    expect(report.side).toBe('no')
    expect(report.viable).toBe(true)
    expect(report.sharp_books).toEqual(expect.arrayContaining(['pinnacle', 'betfair']))
    expect(report.edge_bps).toBeGreaterThan(0)
  })

  it('finds parity in binary and multi-outcome baskets', () => {
    const binary = assessBinaryParity({
      market_id: 'mkt-4',
      yes_price: 0.41,
      no_price: 0.42,
      fee_rate: 0.02,
    })
    expect(binary.kind).toBe('binary_parity')
    expect(binary.viable).toBe(true)
    expect(binary.locked_profit).toBeGreaterThan(0)

    const basket = assessMultiOutcomeParity({
      market_group_id: 'group-1',
      legs: [
        { market_id: 'a', yes_price: 0.21, fee_rate: 0.02 },
        { market_id: 'b', yes_price: 0.28, fee_rate: 0.02 },
        { market_id: 'c', yes_price: 0.32, fee_rate: 0.02 },
      ],
      min_edge_bps: 100,
    })
    expect(basket.kind).toBe('multi_outcome_parity')
    expect(basket.market_ids).toEqual(expect.arrayContaining(['a', 'b', 'c']))
    expect(basket.viable).toBe(true)
    expect(basket.edge_bps).toBeGreaterThan(100)
  })

  it('sizes Kelly positions conservatively and respects the preferred side', () => {
    const report = calculateKellySizing({
      market_id: 'mkt-5',
      question: 'Will BTC finish above the range?',
      probability_yes: 0.62,
      market_yes_price: 0.5,
      bankroll_usd: 1_000,
      fractional_kelly: 0.25,
      max_position_usd: 250,
      fee_rate: 0.02,
    })

    expect(report.kind).toBe('kelly_sizing')
    expect(report.recommended_side).toBe('yes')
    expect(report.viable).toBe(true)
    expect(report.position_usd).toBeGreaterThan(0)
    expect(report.position_usd).toBeLessThanOrEqual(250)
  })
})
