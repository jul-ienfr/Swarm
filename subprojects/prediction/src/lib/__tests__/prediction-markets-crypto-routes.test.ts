import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/server', () => {
  class MockHeaders {
    private readonly values = new Map<string, string>()

    constructor(init?: HeadersInit) {
      if (!init) return
      if (init instanceof Headers) {
        init.forEach((value, key) => this.values.set(key.toLowerCase(), value))
        return
      }
      if (Array.isArray(init)) {
        for (const [key, value] of init) {
          this.values.set(key.toLowerCase(), String(value))
        }
        return
      }
      for (const [key, value] of Object.entries(init)) {
        this.values.set(key.toLowerCase(), String(value))
      }
    }

    get(name: string) {
      return this.values.get(name.toLowerCase()) ?? null
    }
  }

  class MockNextResponse {
    constructor(
      private readonly bodyValue: unknown,
      public readonly status: number,
      public readonly headers: MockHeaders,
    ) {}

    async json() {
      return this.bodyValue
    }
  }

  class MockNextRequest extends Request {}

  return {
    NextRequest: MockNextRequest,
    NextResponse: {
      json: (body: unknown, init?: { status?: number; headers?: HeadersInit }) =>
        new MockNextResponse(body, init?.status ?? 200, new MockHeaders(init?.headers)),
    },
  }
})

import { NextRequest } from 'next/server'

const mocks = vi.hoisted(() => ({
  requireRole: vi.fn(),
  readLimiter: vi.fn(),
  listPredictionMarketUniverse: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({
  requireRole: mocks.requireRole,
}))

vi.mock('@/lib/rate-limit', () => ({
  readLimiter: mocks.readLimiter,
}))

vi.mock('@/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
  },
}))

vi.mock('@/lib/prediction-markets/service', () => ({
  listPredictionMarketUniverse: mocks.listPredictionMarketUniverse,
}))

describe('prediction markets CRYPTO screener routes', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.requireRole.mockReset()
    mocks.readLimiter.mockReset()
    mocks.listPredictionMarketUniverse.mockReset()

    mocks.requireRole.mockReturnValue({ user: { workspace_id: 7, username: 'viewer' } })
    mocks.readLimiter.mockReturnValue(null)
    mocks.listPredictionMarketUniverse.mockImplementation(async ({ venue, search }: { venue: string; search: string }) => {
      if (venue === 'kalshi' && (search === 'BTC' || search === 'Bitcoin')) {
        return {
          markets: [
            {
              market_id: 'KXBTC-2026-DEC',
              slug: 'bitcoin-above-120k-december',
              question: 'Will Bitcoin reach $120,000 by December 31, 2026?',
              end_at: '2026-12-31T23:59:59.000Z',
              liquidity_usd: 220000,
              volume_24h_usd: 48000,
              last_trade_price: 0.64,
              best_bid: 0.63,
              best_ask: 0.65,
              source_urls: ['https://example.test/kalshi/btc-120k'],
            },
          ],
        }
      }

      return { markets: [] }
    })
  })

  it('returns a live-enriched screener payload by default', async () => {
    const { GET } = await import('@/app/api/v1/prediction-markets/crypto/screener/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/crypto/screener?venue=kalshi&asset=BTC&limit=5')
    const response = await GET(request)
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(response.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(mocks.requireRole).toHaveBeenCalledWith(request, 'viewer')
    expect(mocks.readLimiter).toHaveBeenCalledWith(request)
    expect(body).toMatchObject({
      screener: {
        snapshot_id: 'crypto-screener-live-v1',
        total: 1,
        opportunities: [
          {
            opportunity_id: 'crypto:kalshi:btc:cross-venue-crypto-dislocations',
            source_mode: 'live',
            matched_market_count: 1,
          },
        ],
      },
    })
  })

  it('returns a live-enriched opportunity detail payload and 404s when missing', async () => {
    const { GET } = await import('@/app/api/v1/prediction-markets/crypto/opportunities/[opportunity_id]/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/crypto/opportunities/crypto:kalshi:btc:cross-venue-crypto-dislocations')
    const response = await GET(request, {
      params: Promise.resolve({ opportunity_id: 'crypto:kalshi:btc:cross-venue-crypto-dislocations' }),
    })
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(response.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(body).toMatchObject({
      opportunity: {
        label: 'BTC cross-venue dislocation watch',
        conviction: 'high',
        source_mode: 'live',
        top_market: {
          market_id: 'KXBTC-2026-DEC',
        },
      },
    })

    const missingResponse = await GET(request, {
      params: Promise.resolve({ opportunity_id: 'crypto:missing' }),
    })
    const missingBody = await missingResponse.json()

    expect(missingResponse.status).toBe(404)
    expect(missingBody).toMatchObject({
      error: 'CRYPTO screener opportunity not found',
      code: 'crypto_opportunity_not_found',
    })
  })

  it('can force the seeded fallback explicitly', async () => {
    const { GET } = await import('@/app/api/v1/prediction-markets/crypto/screener/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/crypto/screener?venue=kalshi&asset=BTC&limit=5&source_mode=seeded')
    const response = await GET(request)
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(body).toMatchObject({
      screener: {
        snapshot_id: 'crypto-screener-seeded-v1',
        opportunities: [
          {
            source_mode: 'seeded',
            matched_market_count: 0,
          },
        ],
      },
    })
  })
})
