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
  buildPredictionDashboardArbitrageSnapshot: vi.fn(),
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

vi.mock('@/lib/prediction-markets/dashboard-read-models', () => ({
  buildPredictionDashboardArbitrageSnapshot: mocks.buildPredictionDashboardArbitrageSnapshot,
}))

describe('prediction markets dashboard arbitrage route', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.requireRole.mockReset()
    mocks.readLimiter.mockReset()
    mocks.buildPredictionDashboardArbitrageSnapshot.mockReset()

    mocks.requireRole.mockReturnValue({ user: { workspace_id: 7, username: 'viewer' } })
    mocks.readLimiter.mockReturnValue(null)
    mocks.buildPredictionDashboardArbitrageSnapshot.mockResolvedValue({
      generated_at: '2026-04-08T00:00:00.000Z',
      freshness: 'fresh',
      transport: 'polling',
      workspace_id: 7,
      venue_pair: ['polymarket', 'kalshi'],
      filters: {
        limit_per_venue: 12,
        max_pairs: 24,
        min_arbitrage_spread_bps: 35,
        shadow_candidates: 6,
      },
      overview: {
        pairs_compared: 1,
        compatible_pairs: 1,
        candidate_count: 1,
        manual_review_count: 0,
        comparison_only_count: 0,
        best_shadow_edge_bps: 80,
        best_net_spread_bps: 92,
        best_executable_edge_bps: 88,
        best_candidate_id: 'arb:btc-2026',
        summary: 'Shadow-only scan found one candidate.',
        errors: [],
      },
      candidates: [],
    })
  })

  it('returns a stable arbitrage payload', async () => {
    const { GET } = await import('@/app/api/v1/prediction-markets/dashboard/arbitrage/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/dashboard/arbitrage?limit_per_venue=12&max_pairs=24&min_arbitrage_spread_bps=35&shadow_candidates=6')
    const response = await GET(request)
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(response.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(mocks.requireRole).toHaveBeenCalledWith(request, 'viewer')
    expect(mocks.readLimiter).toHaveBeenCalledWith(request)
    expect(mocks.buildPredictionDashboardArbitrageSnapshot).toHaveBeenCalledWith(7, {
      limitPerVenue: 12,
      maxPairs: 24,
      minArbitrageSpreadBps: 35,
      shadowCandidateLimit: 6,
      forceRefresh: true,
    })
    expect(body).toMatchObject({
      arbitrage: {
        workspace_id: 7,
        filters: { limit_per_venue: 12, max_pairs: 24 },
      },
    })
  })

  it('accepts the dashboard limit alias used by the UI', async () => {
    const { GET } = await import('@/app/api/v1/prediction-markets/dashboard/arbitrage/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/dashboard/arbitrage?limit=9&max_pairs=18')
    const response = await GET(request)

    expect(response.status).toBe(200)
    expect(mocks.buildPredictionDashboardArbitrageSnapshot).toHaveBeenCalledWith(7, {
      limitPerVenue: 9,
      maxPairs: 18,
      minArbitrageSpreadBps: 25,
      shadowCandidateLimit: 8,
      forceRefresh: true,
    })
  })
})
