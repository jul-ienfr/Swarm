import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/server', () => {
  class MockHeaders {
    private readonly values = new Map<string, string>()

    constructor(init?: HeadersInit) {
      if (!init) return
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

    static json(body: unknown, init?: { status?: number; headers?: HeadersInit }) {
      return new MockNextResponse(body, init?.status ?? 200, new MockHeaders(init?.headers))
    }
  }

  class MockNextRequest extends Request {}

  return {
    NextRequest: MockNextRequest,
    NextResponse: MockNextResponse,
  }
})

import { NextRequest } from 'next/server'

const mocks = vi.hoisted(() => ({
  requireRole: vi.fn(),
  heavyLimiter: vi.fn(),
  validateBody: vi.fn(),
  advisePredictionMarket: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({
  requireRole: mocks.requireRole,
}))

vi.mock('@/lib/rate-limit', () => ({
  heavyLimiter: mocks.heavyLimiter,
}))

vi.mock('@/lib/validation', () => ({
  validateBody: mocks.validateBody,
}))

vi.mock('@/lib/logger', () => ({
  logger: {
    error: vi.fn(),
  },
}))

vi.mock('@/lib/prediction-markets/service', () => ({
  advisePredictionMarket: mocks.advisePredictionMarket,
}))

vi.mock('@/lib/prediction-markets/errors', () => ({
  toPredictionMarketsErrorResponse: (error: unknown, fallbackMessage: string) => ({
    status: 500,
    body: {
      error: error instanceof Error ? error.message : fallbackMessage,
      code: 'internal_error',
    },
  }),
}))

describe('prediction markets predict routes', () => {
  beforeEach(() => {
    mocks.requireRole.mockReset()
    mocks.heavyLimiter.mockReset()
    mocks.validateBody.mockReset()
    mocks.advisePredictionMarket.mockReset()

    mocks.requireRole.mockReturnValue({ user: { workspace_id: 7, username: 'operator' } })
    mocks.heavyLimiter.mockReturnValue(null)
    mocks.validateBody.mockResolvedValue({
      data: {
        market_id: 'market-1',
        venue: 'polymarket',
      },
    })
    mocks.advisePredictionMarket.mockResolvedValue({ ok: true })
  })

  it('forces standard predict mode on the predict route', async () => {
    const { POST } = await import('@/app/api/v1/prediction-markets/predict/route')
    const response = await POST(new NextRequest('http://localhost/api/v1/prediction-markets/predict', { method: 'POST' }))

    expect(response.status).toBe(201)
    expect(mocks.advisePredictionMarket).toHaveBeenCalledWith(expect.objectContaining({
      market_id: 'market-1',
      venue: 'polymarket',
      request_mode: 'predict',
      response_variant: 'standard',
      workspaceId: 7,
      actor: 'operator',
    }))
  })

  it('forces deep predict mode on the predict-deep route', async () => {
    const { POST } = await import('@/app/api/v1/prediction-markets/predict-deep/route')
    const response = await POST(new NextRequest('http://localhost/api/v1/prediction-markets/predict-deep', { method: 'POST' }))

    expect(response.status).toBe(201)
    expect(mocks.advisePredictionMarket).toHaveBeenCalledWith(expect.objectContaining({
      market_id: 'market-1',
      venue: 'polymarket',
      request_mode: 'predict_deep',
      response_variant: 'research_heavy',
      workspaceId: 7,
      actor: 'operator',
    }))
  })

  it('passes TimesFM options through the predict-deep route body', async () => {
    mocks.validateBody.mockResolvedValueOnce({
      data: {
        market_id: 'market-1',
        venue: 'polymarket',
        timesfm_mode: 'required',
        timesfm_lanes: ['microstructure'],
      },
    })

    const { POST } = await import('@/app/api/v1/prediction-markets/predict-deep/route')
    const response = await POST(new NextRequest('http://localhost/api/v1/prediction-markets/predict-deep', { method: 'POST' }))

    expect(response.status).toBe(201)
    expect(mocks.advisePredictionMarket).toHaveBeenCalledWith(expect.objectContaining({
      market_id: 'market-1',
      timesfm_mode: 'required',
      timesfm_lanes: ['microstructure'],
      request_mode: 'predict_deep',
      response_variant: 'research_heavy',
    }))
  })
})
