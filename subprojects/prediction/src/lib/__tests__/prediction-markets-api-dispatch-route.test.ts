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

    set(name: string, value: string) {
      this.values.set(name.toLowerCase(), value)
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
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  requireRole: vi.fn(),
  heavyLimiter: vi.fn(),
  preparePredictionMarketRunDispatch: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({
  requireRole: mocks.requireRole,
}))

vi.mock('@/lib/rate-limit', () => ({
  heavyLimiter: mocks.heavyLimiter,
}))

vi.mock('@/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
  },
}))

vi.mock('@/lib/prediction-markets/service', () => ({
  preparePredictionMarketRunDispatch: mocks.preparePredictionMarketRunDispatch,
}))

describe('prediction markets v1 dispatch route', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.requireRole.mockReset()
    mocks.heavyLimiter.mockReset()
    mocks.preparePredictionMarketRunDispatch.mockReset()
    mocks.requireRole.mockReturnValue({ user: { workspace_id: 7, username: 'operator' } })
    mocks.heavyLimiter.mockReturnValue(null)
  })

  it('returns a preflight dispatch payload with v1 header', async () => {
    mocks.preparePredictionMarketRunDispatch.mockReturnValue({
      gate_name: 'execution_projection_dispatch',
      preflight_only: true,
      run_id: 'run-dispatch-1',
      workspace_id: 7,
      dispatch_status: 'ready',
      dispatch_blocking_reasons: [],
      summary: 'Dispatch preflight is ready for shadow using the canonical execution_projection preview.',
      source_refs: {
        run_detail: 'run-dispatch-1',
        execution_projection: 'run-dispatch-1:execution_projection',
        trade_intent_guard: 'run-dispatch-1:trade_intent_guard',
        multi_venue_execution: 'run-dispatch-1:multi_venue_execution',
      },
      execution_projection_requested_path: 'live',
      execution_projection_selected_path: 'shadow',
      execution_projection_selected_path_status: 'degraded',
      execution_projection_selected_path_effective_mode: 'shadow',
      execution_projection_selected_preview: {
        size_usd: 40,
        limit_price: 0.51,
        time_in_force: 'ioc',
        max_slippage_bps: 50,
      },
      execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
      execution_projection_selected_path_canonical_size_usd: 40,
      execution_projection_selected_path_shadow_signal_present: true,
      execution_projection_verdict: 'downgraded',
      execution_projection_preflight_summary: {
        gate_name: 'execution_projection',
        requested_path: 'live',
        selected_path: 'shadow',
      },
      benchmark_gate_summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
      benchmark_uplift_bps: 1100,
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'unproven',
      benchmark_promotion_ready: false,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'unproven',
      benchmark_evidence_level: 'benchmark_preview',
      benchmark_promotion_gate_kind: 'preview_only',
      benchmark_gate_blockers: ['out_of_sample_unproven'],
      benchmark_gate_reasons: ['out_of_sample_unproven'],
      execution_projection: {
        gate_name: 'execution_projection',
        selected_path: 'shadow',
      },
      execution_readiness: null,
      execution_pathways: null,
      shadow_arbitrage: null,
      trade_intent_guard: null,
      multi_venue_execution: null,
    })

    const { POST } = await import('@/app/api/v1/prediction-markets/runs/[run_id]/dispatch/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-dispatch-1/dispatch', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-dispatch-1' }),
    })
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(response.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(mocks.requireRole).toHaveBeenCalledWith(request, 'operator')
    expect(mocks.heavyLimiter).toHaveBeenCalledWith(request)
    expect(mocks.preparePredictionMarketRunDispatch).toHaveBeenCalledWith({
      runId: 'run-dispatch-1',
      workspaceId: 7,
    })
    expect(body).toMatchObject({
      gate_name: 'execution_projection_dispatch',
      preflight_only: true,
      run_id: 'run-dispatch-1',
      dispatch_status: 'ready',
      execution_projection_requested_path: 'live',
      execution_projection_selected_path: 'shadow',
      execution_projection_selected_preview: expect.objectContaining({
        size_usd: 40,
      }),
      benchmark_gate_summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
      benchmark_promotion_evidence: 'unproven',
      benchmark_evidence_level: 'benchmark_preview',
      benchmark_promotion_gate_kind: 'preview_only',
    })
  })

  it('short-circuits on auth errors before rate limiting or service calls', async () => {
    mocks.requireRole.mockReturnValue({ error: 'Forbidden', status: 403 })

    const { POST } = await import('@/app/api/v1/prediction-markets/runs/[run_id]/dispatch/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-dispatch-2/dispatch', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-dispatch-2' }),
    })
    const body = await response.json()

    expect(response.status).toBe(403)
    expect(body).toEqual({ error: 'Forbidden' })
    expect(mocks.heavyLimiter).not.toHaveBeenCalled()
    expect(mocks.preparePredictionMarketRunDispatch).not.toHaveBeenCalled()
  })

  it('returns the limiter response before calling the dispatch service', async () => {
    mocks.heavyLimiter.mockReturnValue(
      NextResponse.json({ error: 'Too Many Requests' }, { status: 429 }),
    )

    const { POST } = await import('@/app/api/v1/prediction-markets/runs/[run_id]/dispatch/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-dispatch-3/dispatch', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-dispatch-3' }),
    })
    const body = await response.json()

    expect(response.status).toBe(429)
    expect(body).toEqual({ error: 'Too Many Requests' })
    expect(mocks.preparePredictionMarketRunDispatch).not.toHaveBeenCalled()
  })

  it('maps service exceptions through the prediction markets error formatter', async () => {
    mocks.preparePredictionMarketRunDispatch.mockImplementation(() => {
      throw new Error('dispatch exploded')
    })

    const { POST } = await import('@/app/api/v1/prediction-markets/runs/[run_id]/dispatch/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-dispatch-4/dispatch', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-dispatch-4' }),
    })
    const body = await response.json()

    expect(response.status).toBe(500)
    expect(body).toEqual({
      error: 'dispatch exploded',
      code: 'internal_error',
    })
  })
})
