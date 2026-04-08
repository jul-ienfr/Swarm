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

  class MockResponse {
    constructor(
      private readonly bodyValue: unknown,
      public readonly status: number,
      public readonly headers: MockHeaders,
    ) {}

    async json() {
      return this.bodyValue
    }
  }

  class MockNextResponse extends MockResponse {
    static json(body: unknown, init?: { status?: number; headers?: HeadersInit }) {
      return new MockNextResponse(
        body,
        init?.status ?? 200,
        new MockHeaders(init?.headers),
      )
    }
  }

  class MockNextRequest extends Request {}

  return {
    NextRequest: MockNextRequest,
    NextResponse: MockNextResponse,
  }
})

import { NextRequest, NextResponse } from 'next/server'

const mocks = vi.hoisted(() => ({
  readLimiter: vi.fn(),
  heavyLimiter: vi.fn(),
  getPredictionMarketRunDetails: vi.fn(),
  listPredictionMarketRuns: vi.fn(),
  loggerError: vi.fn(),
}))

vi.mock('@/lib/rate-limit', () => ({
  readLimiter: mocks.readLimiter,
  heavyLimiter: mocks.heavyLimiter,
}))

vi.mock('@/lib/logger', () => ({
  logger: {
    error: mocks.loggerError,
    info: vi.fn(),
    warn: vi.fn(),
  },
}))

vi.mock('@/lib/prediction-markets/service', () => ({
  getPredictionMarketRunDetails: mocks.getPredictionMarketRunDetails,
  listPredictionMarketRuns: mocks.listPredictionMarketRuns,
}))

describe('dashboard compat routes', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.readLimiter.mockReset()
    mocks.heavyLimiter.mockReset()
    mocks.getPredictionMarketRunDetails.mockReset()
    mocks.listPredictionMarketRuns.mockReset()
    mocks.loggerError.mockReset()
    mocks.readLimiter.mockReturnValue(null)
    mocks.heavyLimiter.mockReturnValue(null)
  })

  it('honors dashboard auth overrides in requireRole', async () => {
    const { requireRole } = await import('@/lib/auth')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/dashboard/live-intents', {
      headers: {
        'x-dashboard-role': 'admin',
        'x-dashboard-actor': 'Dashboard Admin',
        'x-workspace-id': '11',
      },
    })

    expect(requireRole(request, 'operator')).toEqual({
      user: {
        workspace_id: 11,
        username: 'Dashboard Admin',
        role: 'admin',
      },
    })
  })

  it('prefers canonical benchmark fields in dashboard run list items', async () => {
    mocks.listPredictionMarketRuns.mockReturnValue([
      {
        run_id: 'run-compat-002',
        workspace_id: 7,
        venue: 'polymarket',
        market_id: 'mkt-compat-002',
        market_slug: 'mkt-compat-002',
        recommendation: 'bet',
        status: 'completed',
        created_at: 1712534400,
        updated_at: 1712534460,
        confidence: 0.72,
        probability_yes: 0.63,
        edge_bps: 700,
        benchmark_state: 'ready',
        benchmark_promotion_ready: true,
        benchmark_promotion_status: 'ready',
        benchmark_promotion_gate_kind: 'local_benchmark',
        benchmark_evidence_level: 'benchmark_proven',
        benchmark_gate_blockers: [],
        benchmark_gate_reasons: [],
        research_benchmark_promotion_ready: false,
        research_benchmark_promotion_status: 'blocked',
        research_promotion_gate_kind: 'preview_only',
        research_benchmark_evidence_level: 'benchmark_preview',
        research_benchmark_gate_blockers: ['stale_research'],
        research_benchmark_gate_reasons: ['stale_research'],
        execution_projection_selected_path: 'live',
        execution_projection_selected_path_status: 'ready',
        execution_projection_selected_path_effective_mode: 'live',
        execution_projection_recommended_effective_mode: 'live',
        research_runtime_mode: 'research_driven',
        execution_summary: 'dashboard list item',
      },
    ])

    const { buildPredictionDashboardRunList } = await import('@/lib/prediction-markets/dashboard-models')
    const result = buildPredictionDashboardRunList(7, 'polymarket', 20)

    expect(result.total).toBe(1)
    expect(result.items[0]).toMatchObject({
      benchmark_state: 'ready',
      benchmark_ready: true,
      benchmark_gate_kind: 'local_benchmark',
      benchmark_evidence_level: 'benchmark_proven',
      selected_path: 'live',
      selected_path_status: 'ready',
      selected_path_effective_mode: 'live',
      research_origin: 'research_driven',
    })
  })
})
