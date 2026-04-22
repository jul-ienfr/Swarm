import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const serviceMocks = vi.hoisted(() => ({
  listPredictionMarketUniverse: vi.fn(),
}))

vi.mock('@/lib/prediction-markets/service', () => ({
  listPredictionMarketUniverse: serviceMocks.listPredictionMarketUniverse,
}))

describe('prediction markets CRYPTO screener', () => {
  beforeEach(() => {
    vi.resetModules()
    serviceMocks.listPredictionMarketUniverse.mockReset()
    serviceMocks.listPredictionMarketUniverse.mockResolvedValue({ markets: [] })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('keeps the seeded screener deterministic', async () => {
    const { buildPredictionCryptoScreener } = await import('@/lib/prediction-markets/crypto')

    const result = buildPredictionCryptoScreener({ venue: 'kalshi', asset: 'BTC', limit: 5 })

    expect(result).toMatchObject({
      snapshot_id: 'crypto-screener-seeded-v1',
      total: 1,
      opportunities: [
        {
          opportunity_id: 'crypto:kalshi:btc:cross-venue-crypto-dislocations',
          score: 123,
          source_mode: 'seeded',
          matched_market_count: 0,
        },
      ],
    })
  })

  it('enriches seeded opportunities with live venue markets when available', async () => {
    serviceMocks.listPredictionMarketUniverse.mockImplementation(async ({ venue, search }: { venue: string; search: string }) => {
      if (venue === 'kalshi' && (search === 'BTC' || search === 'Bitcoin')) {
        return {
          markets: [
            {
              market_id: 'KXBTCDIP-2026-12-31',
              slug: 'bitcoin-reach-120k-by-december',
              question: 'Will Bitcoin reach $120,000 by December 31, 2026?',
              end_at: '2026-12-31T23:59:59.000Z',
              liquidity_usd: 180000,
              volume_24h_usd: 42000,
              last_trade_price: 0.61,
              best_bid: 0.6,
              best_ask: 0.62,
              source_urls: ['https://example.test/kalshi/bitcoin-reach-120k'],
            },
          ],
        }
      }

      return { markets: [] }
    })

    const { buildPredictionCryptoScreenerLive } = await import('@/lib/prediction-markets/crypto')
    const result = await buildPredictionCryptoScreenerLive({ venue: 'kalshi', asset: 'BTC', limit: 5 })

    expect(result.snapshot_id).toBe('crypto-screener-live-v1')
    expect(result.total).toBe(1)
    expect(result.opportunities[0]).toMatchObject({
      opportunity_id: 'crypto:kalshi:btc:cross-venue-crypto-dislocations',
      source_mode: 'live',
      matched_market_count: 1,
      top_market: {
        market_id: 'KXBTCDIP-2026-12-31',
        question: 'Will Bitcoin reach $120,000 by December 31, 2026?',
      },
    })
    expect(result.opportunities[0].score).toBeGreaterThan(123)
  })
})
