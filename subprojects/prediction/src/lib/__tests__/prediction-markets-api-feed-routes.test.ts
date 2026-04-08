import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/server', () => {
  class MockHeaders {
    private readonly values = new Map<string, string>()

    constructor(init?: HeadersInit) {
      if (!init) return
      if (init instanceof Headers) {
        init.forEach((value, key) => {
          this.values.set(key.toLowerCase(), value)
        })
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

import { NextRequest, NextResponse } from 'next/server'

const mocks = vi.hoisted(() => ({
  requireRole: vi.fn(),
  readLimiter: vi.fn(),
  getVenueCapabilities: vi.fn(),
  getVenueCapabilitiesContract: vi.fn(),
  getVenueBudgets: vi.fn(),
  getVenueBudgetsContract: vi.fn(),
  getVenueHealthSnapshot: vi.fn(),
  getVenueHealthSnapshotContract: vi.fn(),
  loggerError: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({
  requireRole: mocks.requireRole,
}))

vi.mock('@/lib/rate-limit', () => ({
  readLimiter: mocks.readLimiter,
}))

vi.mock('@/lib/logger', () => ({
  logger: {
    error: mocks.loggerError,
    info: vi.fn(),
    warn: vi.fn(),
  },
}))

vi.mock('@/lib/prediction-markets/venue-ops', () => ({
  getVenueCapabilities: mocks.getVenueCapabilities,
  getVenueCapabilitiesContract: mocks.getVenueCapabilitiesContract,
  getVenueBudgets: mocks.getVenueBudgets,
  getVenueBudgetsContract: mocks.getVenueBudgetsContract,
  getVenueHealthSnapshot: mocks.getVenueHealthSnapshot,
  getVenueHealthSnapshotContract: mocks.getVenueHealthSnapshotContract,
}))

describe('prediction markets v1 feed routes', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.requireRole.mockReset()
    mocks.readLimiter.mockReset()
    mocks.getVenueCapabilities.mockReset()
    mocks.getVenueCapabilitiesContract.mockReset()
    mocks.getVenueBudgets.mockReset()
    mocks.getVenueBudgetsContract.mockReset()
    mocks.getVenueHealthSnapshot.mockReset()
    mocks.getVenueHealthSnapshotContract.mockReset()
    mocks.loggerError.mockReset()
    mocks.requireRole.mockReturnValue({ user: { workspace_id: 7, username: 'viewer' } })
    mocks.readLimiter.mockReturnValue(null)
  })

  it('returns the v1 capabilities payload with feed and execution contracts', async () => {
    mocks.getVenueCapabilities.mockReturnValue({
      venue: 'kalshi',
      supports_execution: true,
      supports_orderbook: true,
      supports_trades: true,
      supports_positions: true,
      supports_paper_mode: true,
      supported_order_types: ['limit'],
    })
    mocks.getVenueCapabilitiesContract.mockReturnValue({
      venue: 'kalshi',
      supports_execution: true,
      automation_constraints: ['manual_review_only'],
      supported_order_types: ['limit'],
      planned_order_types: ['market'],
    })
    mocks.getVenueBudgets.mockReturnValue({
      venue: 'kalshi',
      max_notional_usd: 500,
    })
    mocks.getVenueBudgetsContract.mockReturnValue({
      venue: 'kalshi',
      max_notional_usd: 500,
      daily_loss_limit_usd: 50,
    })

    const { GET } = await import('@/app/api/v1/prediction-markets/capabilities/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/capabilities?venue=kalshi')
    const response = await GET(request)
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(response.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(mocks.requireRole).toHaveBeenCalledWith(request, 'viewer')
    expect(mocks.readLimiter).toHaveBeenCalledWith(request)
    expect(body).toMatchObject({
      venue: 'kalshi',
      capabilities: {
        supports_execution: true,
      },
      capabilities_contract: {
        automation_constraints: ['manual_review_only'],
        supported_order_types: ['limit'],
      },
      budgets_contract: {
        daily_loss_limit_usd: 50,
      },
    })
  })

  it('returns the v1 health payload with feed surface status', async () => {
    mocks.getVenueHealthSnapshot.mockReturnValue({
      venue: 'polymarket',
      status: 'healthy',
      degraded_mode: false,
      market_feed_status: 'local_cache',
      user_feed_status: 'local_cache',
      rtds_status: 'unavailable',
    })
    mocks.getVenueHealthSnapshotContract.mockReturnValue({
      venue: 'polymarket',
      market_feed_status: 'local_cache',
      user_feed_status: 'local_cache',
      rtds_status: 'unavailable',
      supports_market_feed: true,
      supports_user_feed: true,
      supports_rtds: false,
    })
    mocks.getVenueBudgets.mockReturnValue({
      venue: 'polymarket',
      max_notional_usd: 250,
    })
    mocks.getVenueBudgetsContract.mockReturnValue({
      venue: 'polymarket',
      max_notional_usd: 250,
      max_open_positions: 3,
    })

    const { GET } = await import('@/app/api/v1/prediction-markets/health/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/health?venue=polymarket')
    const response = await GET(request)
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(response.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(body).toMatchObject({
      venue: 'polymarket',
      health: {
        status: 'healthy',
      },
      health_contract: {
        market_feed_status: 'local_cache',
        user_feed_status: 'local_cache',
        rtds_status: 'unavailable',
      },
      budgets_contract: {
        max_open_positions: 3,
      },
    })
  })

  it('short-circuits capabilities on auth errors before reading rate limits or contracts', async () => {
    mocks.requireRole.mockReturnValue({ error: 'Forbidden', status: 403 })

    const { GET } = await import('@/app/api/v1/prediction-markets/capabilities/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/capabilities')
    const response = await GET(request)
    const body = await response.json()

    expect(response.status).toBe(403)
    expect(body).toEqual({ error: 'Forbidden' })
    expect(mocks.readLimiter).not.toHaveBeenCalled()
    expect(mocks.getVenueCapabilities).not.toHaveBeenCalled()
  })

  it('returns the limiter response on health before calling venue helpers', async () => {
    const limited = NextResponse.json({ error: 'Too Many Requests' }, { status: 429 })
    mocks.readLimiter.mockReturnValue(limited)

    const { GET } = await import('@/app/api/v1/prediction-markets/health/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/health')
    const response = await GET(request)
    const body = await response.json()

    expect(response.status).toBe(429)
    expect(body).toEqual({ error: 'Too Many Requests' })
    expect(mocks.getVenueHealthSnapshot).not.toHaveBeenCalled()
    expect(mocks.getVenueHealthSnapshotContract).not.toHaveBeenCalled()
  })
})
