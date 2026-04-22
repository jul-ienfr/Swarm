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

import { NextRequest, NextResponse } from 'next/server'

const mocks = vi.hoisted(() => ({
  requireRole: vi.fn(),
  readLimiter: vi.fn(),
  buildMeteoPricingReportFromProviders: vi.fn(),
  buildMeteoBestBetsSummary: vi.fn(),
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

vi.mock('@/lib/prediction-markets/meteo', () => ({
  buildMeteoPricingReportFromProviders: mocks.buildMeteoPricingReportFromProviders,
  buildMeteoBestBetsSummary: mocks.buildMeteoBestBetsSummary,
}))

describe('prediction markets météo route', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.requireRole.mockReset()
    mocks.readLimiter.mockReset()
    mocks.buildMeteoPricingReportFromProviders.mockReset()
    mocks.buildMeteoBestBetsSummary.mockReset()
    mocks.loggerError.mockReset()

    mocks.requireRole.mockReturnValue({ user: { workspace_id: 7, username: 'viewer' } })
    mocks.readLimiter.mockReturnValue(null)
    mocks.buildMeteoBestBetsSummary.mockReturnValue({
      summary: 'Top météo bet: YES 68-69F',
      actionableCount: 1,
      strongestOpportunity: null,
      topOpportunities: [],
      recommendedSideCounts: { yes: 1, no: 0, pass: 0 },
      noTradeLabels: [],
    })
  })

  it('returns a météo pricing payload for the requested question and coordinates', async () => {
    mocks.buildMeteoPricingReportFromProviders.mockResolvedValue({
      spec: {
        question: 'What will the highest temperature in Los Angeles, CA on Apr 21, 2026 be: 66F-67F, 68F-69F, or 70F+?',
        city: 'Los Angeles',
        countryOrRegion: 'CA',
        marketDate: 'Apr 21, 2026',
        kind: 'high',
        unit: 'f',
        bins: [{ label: '68-69F', unit: 'f', lower: { value: 68, inclusive: true }, upper: { value: 69, inclusive: true } }],
      },
      forecastPoints: [{ provider: 'open-meteo:ecmwf', mean: 68.8, stddev: 1.4, weight: 1 }],
      report: {
        mean: 68.8,
        stddev: 1.4,
        unit: 'f',
        bins: [],
        opportunities: [],
        marketSnapshot: { pricedBinCount: 1, yesPriceSum: 0.33, overround: -0.67 },
        provenance: {
          providerCount: 1,
          providers: ['open-meteo:ecmwf'],
          contributions: [],
        },
      },
    })

    const { GET } = await import('@/app/api/v1/prediction-markets/meteo/route')
    const request = new NextRequest(
      'http://localhost/api/v1/prediction-markets/meteo?question=What%20will%20the%20highest%20temperature%20in%20Los%20Angeles,%20CA%20on%20Apr%2021,%202026%20be:%2066F-67F,%2068F-69F,%20or%2070F%2B%3F&latitude=34.05&longitude=-118.25&open_meteo_models=ecmwf,gfs&include_nws=false&cache_ttl_ms=60000&retry_count=2&market_prices=%7B%2268-69F%22%3A0.33%7D',
    )

    const response = await GET(request)
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(response.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(mocks.requireRole).toHaveBeenCalledWith(request, 'viewer')
    expect(mocks.readLimiter).toHaveBeenCalledWith(request)
    expect(mocks.buildMeteoPricingReportFromProviders).toHaveBeenCalledWith({
      question: 'What will the highest temperature in Los Angeles, CA on Apr 21, 2026 be: 66F-67F, 68F-69F, or 70F+?',
      latitude: 34.05,
      longitude: -118.25,
      openMeteoModels: ['ecmwf', 'gfs'],
      includeNws: false,
      includeMeteostat: undefined,
      meteostatStart: undefined,
      meteostatEnd: undefined,
      meteostatApiKey: undefined,
      cacheTtlMs: 60000,
      retryCount: 2,
      marketPrices: { '68-69F': 0.33 },
      userAgent: 'swarm-prediction/1.0 (+meteo-route)',
    })
    expect(body).toMatchObject({
      spec: {
        city: 'Los Angeles',
        kind: 'high',
      },
      forecast_points: [
        { provider: 'open-meteo:ecmwf', mean: 68.8 },
      ],
      best_bets: {
        summary: 'Top météo bet: YES 68-69F',
      },
    })
  })

  it('short-circuits on auth errors before touching the limiter or builder', async () => {
    mocks.requireRole.mockReturnValue({ error: 'Forbidden', status: 403 })

    const { GET } = await import('@/app/api/v1/prediction-markets/meteo/route')
    const response = await GET(new NextRequest('http://localhost/api/v1/prediction-markets/meteo'))
    const body = await response.json()

    expect(response.status).toBe(403)
    expect(body).toEqual({ error: 'Forbidden' })
    expect(mocks.readLimiter).not.toHaveBeenCalled()
    expect(mocks.buildMeteoPricingReportFromProviders).not.toHaveBeenCalled()
  })

  it('returns the limiter response before invoking the météo builder', async () => {
    const limited = NextResponse.json({ error: 'Too Many Requests' }, { status: 429 })
    mocks.readLimiter.mockReturnValue(limited)

    const { GET } = await import('@/app/api/v1/prediction-markets/meteo/route')
    const response = await GET(
      new NextRequest('http://localhost/api/v1/prediction-markets/meteo?question=q&latitude=1&longitude=2'),
    )
    const body = await response.json()

    expect(response.status).toBe(429)
    expect(body).toEqual({ error: 'Too Many Requests' })
    expect(mocks.buildMeteoPricingReportFromProviders).not.toHaveBeenCalled()
  })

  it('returns a structured error payload on invalid query params and logs the failure', async () => {
    const { GET } = await import('@/app/api/v1/prediction-markets/meteo/route')
    const response = await GET(
      new NextRequest('http://localhost/api/v1/prediction-markets/meteo?question=q&latitude=abc&longitude=-118.25'),
    )
    const body = await response.json()

    expect(response.status).toBe(500)
    expect(body).toEqual({
      error: 'Invalid numeric query parameter: latitude',
      code: 'internal_error',
    })
    expect(mocks.loggerError).toHaveBeenCalledTimes(1)
    expect(mocks.buildMeteoPricingReportFromProviders).not.toHaveBeenCalled()
  })

  it('passes meteostat toggles through when explicitly enabled', async () => {
    mocks.buildMeteoPricingReportFromProviders.mockResolvedValue({
      spec: {
        question: 'q',
        city: null,
        countryOrRegion: null,
        marketDate: null,
        kind: 'high',
        unit: 'f',
        bins: [],
      },
      forecastPoints: [],
      report: {
        mean: 0,
        stddev: 1,
        unit: 'f',
        bins: [],
        opportunities: [],
        marketSnapshot: { pricedBinCount: 0, yesPriceSum: null, overround: null },
        provenance: { providerCount: 0, providers: [], contributions: [] },
      },
    })

    const { GET } = await import('@/app/api/v1/prediction-markets/meteo/route')
    await GET(
      new NextRequest(
        'http://localhost/api/v1/prediction-markets/meteo?question=q&latitude=40.7&longitude=-74.0&include_meteostat=true&meteostat_start=2026-04-01&meteostat_end=2026-04-10',
      ),
    )

    expect(mocks.buildMeteoPricingReportFromProviders).toHaveBeenCalledWith(
      expect.objectContaining({
        includeMeteostat: true,
        meteostatStart: '2026-04-01',
        meteostatEnd: '2026-04-10',
      }),
    )
  })
})
