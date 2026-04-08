import { describe, expect, it, vi } from 'vitest'

vi.mock('next/server', () => {
  class MockHeaders {
    private readonly values = new Map<string, string>()

    constructor(init?: HeadersInit) {
      if (!init) return
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

    static json(body: unknown, init?: { status?: number; headers?: HeadersInit }) {
      return new MockNextResponse(body, init?.status ?? 200, new MockHeaders(init?.headers))
    }
  }

  return { NextResponse: MockNextResponse }
})

describe('dashboard index api discoverability', () => {
  it('lists the dashboard and run-surface routes in the public index', async () => {
    const { GET } = await import('@/app/api/index/route')
    const response = await GET()
    const body = await response.json() as { endpoints: Array<{ path: string; auth: string; method: string }> }

    expect(body.endpoints).toEqual(expect.arrayContaining([
      { path: '/prediction-markets/dashboard', auth: 'viewer', method: 'GET' },
      { path: '/api/v1/prediction-markets/runs/:run_id', auth: 'viewer', method: 'GET' },
      { path: '/api/v1/prediction-markets/dashboard/arbitrage', auth: 'viewer', method: 'GET' },
      { path: '/api/v1/prediction-markets/runs/:run_id/dispatch', auth: 'operator', method: 'POST' },
      { path: '/api/v1/prediction-markets/runs/:run_id/paper', auth: 'operator', method: 'POST' },
      { path: '/api/v1/prediction-markets/runs/:run_id/shadow', auth: 'operator', method: 'POST' },
      { path: '/api/v1/prediction-markets/runs/:run_id/live', auth: 'operator', method: 'POST' },
    ]))
  })
})
