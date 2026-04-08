import { describe, expect, it, vi } from 'vitest'

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
      return new MockNextResponse(
        body,
        init?.status ?? 200,
        new MockHeaders(init?.headers),
      )
    }
  }

  return {
    NextResponse: MockNextResponse,
  }
})

describe('api index prediction markets entries', () => {
  it('labels prediction-markets advise and replay as operator access', async () => {
    const { GET } = await import('@/app/api/index/route')
    const response = await GET()
    expect(response.status).toBe(200)

    const payload = await response.json()
    const entries = payload.endpoints.filter((entry: { path: string }) =>
      entry.path.startsWith('/api/prediction-markets/') || entry.path.startsWith('/api/v1/prediction-markets/'),
    )

    const advise = entries.find((entry: { path: string }) => entry.path === '/api/prediction-markets/advise')
    const replay = entries.find((entry: { path: string }) => entry.path === '/api/prediction-markets/replay')
    const live = entries.find((entry: { path: string }) => entry.path === '/api/v1/prediction-markets/runs/:run_id/live')
    const runs = entries.find((entry: { path: string }) => entry.path === '/api/prediction-markets/runs')

    expect(advise).toMatchObject({ auth: 'operator' })
    expect(replay).toMatchObject({ auth: 'operator' })
    expect(live).toMatchObject({ auth: 'operator', method: 'POST' })
    expect(runs).toMatchObject({ auth: 'viewer' })
    expect(entries).toEqual(expect.arrayContaining([
      { path: '/api/v1/prediction-markets/dashboard/overview', auth: 'viewer', method: 'GET' },
      { path: '/api/v1/prediction-markets/dashboard/runs', auth: 'viewer', method: 'GET' },
      { path: '/api/v1/prediction-markets/dashboard/runs/:run_id', auth: 'viewer', method: 'GET' },
      { path: '/api/v1/prediction-markets/dashboard/benchmark', auth: 'viewer', method: 'GET' },
      { path: '/api/v1/prediction-markets/dashboard/arbitrage', auth: 'viewer', method: 'GET' },
      { path: '/api/v1/prediction-markets/dashboard/venues/:venue', auth: 'viewer', method: 'GET' },
      { path: '/api/v1/prediction-markets/dashboard/events', auth: 'viewer', method: 'GET' },
      { path: '/api/v1/prediction-markets/dashboard/live-intents', auth: 'viewer', method: 'GET' },
      { path: '/api/v1/prediction-markets/dashboard/live-intents', auth: 'operator', method: 'POST' },
      { path: '/api/v1/prediction-markets/dashboard/live-intents/:intent_id', auth: 'viewer', method: 'GET' },
      { path: '/api/v1/prediction-markets/dashboard/live-intents/:intent_id/approve', auth: 'operator', method: 'POST' },
      { path: '/api/v1/prediction-markets/dashboard/live-intents/:intent_id/reject', auth: 'operator', method: 'POST' },
    ]))
  })
})
