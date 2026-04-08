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
  preparePredictionMarketRunShadow: vi.fn(),
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
  preparePredictionMarketRunShadow: mocks.preparePredictionMarketRunShadow,
}))

describe('prediction markets v1 shadow route', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.requireRole.mockReset()
    mocks.heavyLimiter.mockReset()
    mocks.preparePredictionMarketRunShadow.mockReset()
    mocks.requireRole.mockReturnValue({ user: { workspace_id: 7, username: 'operator' } })
    mocks.heavyLimiter.mockReturnValue(null)
  })

  it('returns a shadow surface payload with v1 header', async () => {
    mocks.preparePredictionMarketRunShadow.mockReturnValue({
      gate_name: 'execution_projection_shadow',
      preflight_only: true,
      run_id: 'run-shadow-1',
      workspace_id: 7,
      surface_mode: 'shadow',
      shadow_status: 'ready',
      shadow_blocking_reasons: [],
      summary: 'Shadow surface is ready using execution_projection.projected_paths.shadow and the canonical shadow preview.',
      source_refs: {
        run_detail: 'run-shadow-1',
        execution_projection: 'run-shadow-1:execution_projection',
        shadow_projected_path: 'run-shadow-1:execution_projection#shadow',
        shadow_arbitrage: 'run-shadow-1:shadow_arbitrage',
        trade_intent_guard: 'run-shadow-1:trade_intent_guard',
        multi_venue_execution: 'run-shadow-1:multi_venue_execution',
      },
      shadow_path: {
        path: 'shadow',
        status: 'ready',
        effective_mode: 'shadow',
      },
      shadow_trade_intent_preview: {
        size_usd: 40,
        limit_price: 0.52,
        time_in_force: 'day',
      },
      shadow_trade_intent_preview_source: 'canonical_trade_intent_preview',
      research_benchmark_gate_summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no blockers=out_of_sample_unproven out_of_sample=unproven',
      research_benchmark_uplift_bps: 1100,
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'unproven',
      research_benchmark_promotion_ready: false,
      benchmark_gate_summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
      benchmark_promotion_evidence: 'unproven',
      benchmark_evidence_level: 'benchmark_preview',
      benchmark_promotion_gate_kind: 'preview_only',
      research_benchmark_gate_blockers: ['out_of_sample_unproven'],
      research_benchmark_gate_reasons: ['out_of_sample_unproven'],
      execution_projection_selected_path: 'shadow',
      execution_projection_selected_preview: {
        size_usd: 40,
      },
      execution_readiness: null,
      execution_pathways: null,
      execution_projection: null,
      shadow_arbitrage: null,
      trade_intent_guard: null,
      multi_venue_execution: null,
    })

    const { POST } = await import('@/app/api/v1/prediction-markets/runs/[run_id]/shadow/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-shadow-1/shadow', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-shadow-1' }),
    })
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(response.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(mocks.requireRole).toHaveBeenCalledWith(request, 'operator')
    expect(mocks.heavyLimiter).toHaveBeenCalledWith(request)
    expect(mocks.preparePredictionMarketRunShadow).toHaveBeenCalledWith({
      runId: 'run-shadow-1',
      workspaceId: 7,
    })
    expect(body).toMatchObject({
      gate_name: 'execution_projection_shadow',
      preflight_only: true,
      run_id: 'run-shadow-1',
      shadow_status: 'ready',
      shadow_path: {
        path: 'shadow',
      },
      shadow_trade_intent_preview: expect.objectContaining({
        size_usd: 40,
      }),
      benchmark_gate_summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
      benchmark_promotion_evidence: 'unproven',
      benchmark_evidence_level: 'benchmark_preview',
      benchmark_promotion_gate_kind: 'preview_only',
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'unproven',
      research_benchmark_promotion_ready: false,
      research_benchmark_gate_blockers: ['out_of_sample_unproven'],
    })
  })

  it('preserves shadow blockers when benchmark promotion is not ready', async () => {
    mocks.preparePredictionMarketRunShadow.mockReturnValue({
      gate_name: 'execution_projection_shadow',
      preflight_only: true,
      run_id: 'run-shadow-blocked-1',
      workspace_id: 7,
      surface_mode: 'shadow',
      shadow_status: 'blocked',
      shadow_blocking_reasons: ['shadow_path_unavailable', 'research_benchmark:out_of_sample_unproven'],
      summary: 'Shadow surface is blocked by missing path and benchmark promotion.',
      source_refs: {
        run_detail: 'run-shadow-blocked-1',
        execution_projection: 'run-shadow-blocked-1:execution_projection',
        shadow_projected_path: null,
        shadow_arbitrage: null,
        trade_intent_guard: null,
        multi_venue_execution: null,
      },
      shadow_path: null,
      shadow_trade_intent_preview: null,
      shadow_trade_intent_preview_source: null,
      research_benchmark_gate_summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=blocked ready=no blockers=out_of_sample_unproven out_of_sample=unproven',
      research_benchmark_uplift_bps: 1100,
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'blocked',
      research_benchmark_promotion_ready: false,
      benchmark_gate_summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=blocked ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
      benchmark_uplift_bps: 1100,
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'blocked',
      benchmark_promotion_ready: false,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'unproven',
      benchmark_evidence_level: 'benchmark_preview',
      benchmark_promotion_gate_kind: 'preview_only',
      benchmark_gate_blockers: ['out_of_sample_unproven'],
      benchmark_gate_reasons: ['local benchmark promotion gate is blocked'],
      research_benchmark_gate_blockers: ['out_of_sample_unproven'],
      research_benchmark_gate_reasons: ['local benchmark promotion gate is blocked'],
      execution_projection_selected_path: 'shadow',
      execution_projection_selected_preview: null,
      execution_readiness: null,
      execution_pathways: null,
      execution_projection: null,
      shadow_arbitrage: null,
      trade_intent_guard: null,
      multi_venue_execution: null,
    })

    const { POST } = await import('@/app/api/v1/prediction-markets/runs/[run_id]/shadow/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-shadow-blocked-1/shadow', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-shadow-blocked-1' }),
    })
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(body).toMatchObject({
      shadow_status: 'blocked',
      shadow_blocking_reasons: ['shadow_path_unavailable', 'research_benchmark:out_of_sample_unproven'],
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'blocked',
      research_benchmark_promotion_ready: false,
      research_benchmark_gate_blockers: ['out_of_sample_unproven'],
    })
  })

  it('returns the limiter response before calling the shadow service', async () => {
    mocks.heavyLimiter.mockReturnValue(
      NextResponse.json({ error: 'Too Many Requests' }, { status: 429 }),
    )

    const { POST } = await import('@/app/api/v1/prediction-markets/runs/[run_id]/shadow/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-shadow-2/shadow', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-shadow-2' }),
    })
    const body = await response.json()

    expect(response.status).toBe(429)
    expect(body).toEqual({ error: 'Too Many Requests' })
    expect(mocks.preparePredictionMarketRunShadow).not.toHaveBeenCalled()
  })

  it('short-circuits on auth errors before rate limiting or service calls', async () => {
    mocks.requireRole.mockReturnValue({ error: 'Forbidden', status: 403 })

    const { POST } = await import('@/app/api/v1/prediction-markets/runs/[run_id]/shadow/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-shadow-3/shadow', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-shadow-3' }),
    })
    const body = await response.json()

    expect(response.status).toBe(403)
    expect(body).toEqual({ error: 'Forbidden' })
    expect(mocks.heavyLimiter).not.toHaveBeenCalled()
    expect(mocks.preparePredictionMarketRunShadow).not.toHaveBeenCalled()
  })

  it('maps service exceptions through the prediction markets error formatter', async () => {
    mocks.preparePredictionMarketRunShadow.mockImplementation(() => {
      throw new Error('shadow exploded')
    })

    const { POST } = await import('@/app/api/v1/prediction-markets/runs/[run_id]/shadow/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-shadow-4/shadow', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-shadow-4' }),
    })
    const body = await response.json()

    expect(response.status).toBe(500)
    expect(body).toEqual({
      error: 'shadow exploded',
      code: 'internal_error',
    })
  })
})
