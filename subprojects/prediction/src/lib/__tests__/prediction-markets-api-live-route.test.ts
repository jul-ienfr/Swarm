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

    set(name: string, value: string) {
      this.values.set(name.toLowerCase(), value)
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
  requireRole: vi.fn(),
  heavyLimiter: vi.fn(),
  preparePredictionMarketRunLive: vi.fn(),
  executePredictionMarketRunLive: vi.fn(),
  listDashboardLiveIntents: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({
  requireRole: mocks.requireRole,
}))

vi.mock('@/lib/rate-limit', () => ({
  heavyLimiter: mocks.heavyLimiter,
}))

vi.mock('@/lib/prediction-markets/dashboard-live-intents', () => ({
  listDashboardLiveIntents: mocks.listDashboardLiveIntents,
}))

vi.mock('@/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
  },
}))

vi.mock('@/lib/prediction-markets/errors', () => ({
  PredictionMarketsError: class PredictionMarketsError extends Error {
    status: number
    code: string

    constructor(message: string, options?: { status?: number; code?: string }) {
      super(message)
      this.name = 'PredictionMarketsError'
      this.status = options?.status ?? 500
      this.code = options?.code ?? 'prediction_markets_error'
    }
  },
  toPredictionMarketsErrorResponse: (error: unknown, fallbackMessage: string) => {
    if (
      error != null &&
      typeof error === 'object' &&
      'status' in error &&
      'code' in error &&
      'message' in error
    ) {
      const typedError = error as { status: number; code: string; message: string }
      return {
        status: typedError.status,
        body: {
          error: typedError.message,
          code: typedError.code,
        },
      }
    }

    return {
      status: 500,
      body: {
        error: error instanceof Error ? error.message : fallbackMessage,
        code: 'internal_error',
      },
    }
  },
}))

vi.mock('@/lib/prediction-markets/service', () => ({
  preparePredictionMarketRunLive: mocks.preparePredictionMarketRunLive,
  executePredictionMarketRunLive: mocks.executePredictionMarketRunLive,
}))

describe('prediction markets v1 live route', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.requireRole.mockReset()
    mocks.heavyLimiter.mockReset()
    mocks.preparePredictionMarketRunLive.mockReset()
    mocks.executePredictionMarketRunLive.mockReset()
    mocks.listDashboardLiveIntents.mockReset()
    mocks.requireRole.mockReturnValue({ user: { workspace_id: 7, username: 'operator' } })
    mocks.heavyLimiter.mockReturnValue(null)
    mocks.listDashboardLiveIntents.mockReturnValue([
      {
        intent_id: 'intent-live-1',
        workspace_id: 7,
        run_id: 'run-live-1',
        approval_state: {
          status: 'approved',
          requested_by: 'creator',
          approvers: ['reviewer'],
          required: 1,
          current: 1,
          requested_at: '2026-04-08T00:00:00.000Z',
          approved_at: '2026-04-08T00:01:00.000Z',
          rejected_at: null,
        },
      },
    ])
  })

  it('returns a live surface payload with v1 header', async () => {
    mocks.preparePredictionMarketRunLive.mockReturnValue({
      gate_name: 'execution_projection_live',
      preflight_only: true,
      run_id: 'run-live-1',
      workspace_id: 7,
      surface_mode: 'live',
      live_route_allowed: true,
      live_status: 'ready',
      live_blocking_reasons: [],
      summary: 'Live surface is ready using the canonical execution_projection preview.',
      source_refs: {
        run_detail: 'run-live-1',
        execution_projection: 'run-live-1:execution_projection',
        live_projected_path: 'run-live-1:execution_projection#live',
        trade_intent_guard: 'run-live-1:trade_intent_guard',
        multi_venue_execution: 'run-live-1:multi_venue_execution',
      },
      live_path: {
        path: 'live',
        status: 'ready',
        effective_mode: 'live',
      },
      live_trade_intent_preview: {
        size_usd: 20,
        limit_price: 0.53,
        time_in_force: 'ioc',
      },
      live_trade_intent_preview_source: 'canonical_trade_intent_preview',
      venue_feed_surface_summary: 'Read-only market and user feed surface; live websocket unavailable.',
      venue_pathway_summary: 'Live pathway is preflight-only and remains benchmark-gated.',
      venue_pathway_highest_actionable_mode: 'live',
      venue_feed_surface: {
        venue: 'polymarket',
        backend_mode: 'read_only',
        market_feed_status: 'local_cache',
        user_feed_status: 'local_cache',
        rtds_status: 'unavailable',
      },
      execution_projection_requested_path: 'live',
      execution_projection_selected_path: 'live',
      execution_projection_selected_preview: {
        size_usd: 20,
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
      benchmark_gate_blocks_live: false,
      benchmark_gate_live_block_reason: null,
      execution_readiness: null,
      execution_pathways: null,
      execution_projection: null,
      shadow_arbitrage: null,
      trade_intent_guard: null,
      multi_venue_execution: null,
    })

    const { POST } = await import('../../app/api/v1/prediction-markets/runs/[run_id]/live/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-live-1/live', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-live-1' }),
    })
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(response.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(mocks.requireRole).toHaveBeenCalledWith(request, 'operator')
    expect(mocks.heavyLimiter).toHaveBeenCalledWith(request)
    expect(mocks.listDashboardLiveIntents).toHaveBeenCalledWith('run-live-1', 7)
    expect(mocks.preparePredictionMarketRunLive).toHaveBeenCalledWith({
      runId: 'run-live-1',
      workspaceId: 7,
    })
    expect(body).toMatchObject({
      gate_name: 'execution_projection_live',
      preflight_only: true,
      run_id: 'run-live-1',
      live_status: 'ready',
      live_path: {
        path: 'live',
      },
      live_trade_intent_preview: expect.objectContaining({
        size_usd: 20,
      }),
      venue_feed_surface: expect.objectContaining({
        backend_mode: 'read_only',
        market_feed_status: 'local_cache',
        user_feed_status: 'local_cache',
      }),
      venue_feed_surface_summary: 'Read-only market and user feed surface; live websocket unavailable.',
      venue_pathway_summary: 'Live pathway is preflight-only and remains benchmark-gated.',
      venue_pathway_highest_actionable_mode: 'live',
      benchmark_gate_summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
      benchmark_promotion_evidence: 'unproven',
      benchmark_evidence_level: 'benchmark_preview',
      benchmark_promotion_gate_kind: 'preview_only',
      benchmark_gate_blocks_live: false,
      benchmark_gate_live_block_reason: null,
    })
  })

  it('executes the live transport when execution_mode=live is requested', async () => {
    mocks.executePredictionMarketRunLive.mockReturnValue({
      gate_name: 'execution_projection_live_materialization',
      execution_mode: 'live',
      source_run_id: 'run-live-1',
      materialized_run_id: 'run-live-1__live_abcd1234',
      approved_intent_id: 'intent-live-1',
      approved_by: ['reviewer'],
      transport_mode: 'live',
      performed_live: true,
      live_execution_status: 'filled',
      receipt_summary: 'Live execution materialized from run-live-1 as run-live-1__live_abcd1234.',
      preflight_surface: {
        gate_name: 'execution_projection_live',
        run_id: 'run-live-1',
        live_status: 'ready',
      },
      order_trace_audit: {
        transport_mode: 'live',
        live_submission_performed: true,
        live_execution_status: 'filled',
      },
      live_execution: {
        execution_id: 'live-exec-1',
        status: 'filled',
        dry_run: false,
      },
      market_execution: {
        execution_id: 'market-exec-1',
      },
      manifest: {
        mode: 'live_execution',
      },
    })

    const { POST } = await import('../../app/api/v1/prediction-markets/runs/[run_id]/live/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-live-1/live', {
      method: 'POST',
      body: JSON.stringify({
        execution_mode: 'live',
        decision_packet: {
          correlation_id: 'decision-live-1',
          probability_estimate: 0.68,
          topic: 'live execution validation',
          objective: 'preserve governance context',
          mode_used: 'hybrid',
          engine_used: 'agentsociety',
          runtime_used: 'structured',
        },
        research_runtime_summary: 'research: mode=research_driven pipeline=polymarket-research-pipeline',
        research_benchmark_gate_summary: 'benchmark gate: ready',
        research_benchmark_live_block_reason: 'research stale blocker',
        governance_note: 'approved under canonical live gate',
      }),
      headers: {
        'content-type': 'application/json',
      },
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-live-1' }),
    })
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(mocks.preparePredictionMarketRunLive).not.toHaveBeenCalled()
    expect(mocks.executePredictionMarketRunLive).toHaveBeenCalledWith({
      runId: 'run-live-1',
      workspaceId: 7,
      actor: 'operator',
      approvedIntentId: 'intent-live-1',
      approvedBy: ['reviewer'],
    })
    expect(body).toMatchObject({
      gate_name: 'execution_projection_live_materialization',
      execution_mode: 'live',
      source_run_id: 'run-live-1',
      materialized_run_id: 'run-live-1__live_abcd1234',
      transport_mode: 'live',
      performed_live: true,
      live_execution_status: 'filled',
      live_execution: {
        execution_id: 'live-exec-1',
      },
      request_context: {
        decision_packet: {
          correlation_id: 'decision-live-1',
          probability_estimate: 0.68,
          topic: 'live execution validation',
          objective: 'preserve governance context',
          mode_used: 'hybrid',
          engine_used: 'agentsociety',
          runtime_used: 'structured',
        },
        research_runtime_summary: 'research: mode=research_driven pipeline=polymarket-research-pipeline',
        research_benchmark_gate_summary: 'benchmark gate: ready',
        research_benchmark_live_block_reason: 'research stale blocker',
        governance_note: 'approved under canonical live gate',
      },
    })
  })

  it('reuses the stored executed_live receipt instead of executing the same live intent twice', async () => {
    mocks.listDashboardLiveIntents.mockReturnValue([
      {
        intent_id: 'intent-live-1',
        workspace_id: 7,
        run_id: 'run-live-1',
        status: 'executed_live',
        approval_state: {
          approvals: [{ actor: 'reviewer-a' }, { actor: 'reviewer-b' }],
          required_approvals: 2,
        },
        execution_result: {
          status: 'executed_live',
          receipt: {
            gate_name: 'execution_projection_live_materialization',
            execution_mode: 'live',
            source_run_id: 'run-live-1',
            materialized_run_id: 'run-live-1__live_cached',
            approved_intent_id: 'intent-live-1',
            approved_by: ['reviewer-a', 'reviewer-b'],
            transport_mode: 'live',
            performed_live: true,
            live_execution_status: 'filled',
            receipt_summary: 'Stored live receipt should win.',
          },
        },
      },
    ])

    const { POST } = await import('../../app/api/v1/prediction-markets/runs/[run_id]/live/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-live-1/live', {
      method: 'POST',
      body: JSON.stringify({
        execution_mode: 'live',
      }),
      headers: {
        'content-type': 'application/json',
      },
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-live-1' }),
    })
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(mocks.executePredictionMarketRunLive).not.toHaveBeenCalled()
    expect(body).toMatchObject({
      materialized_run_id: 'run-live-1__live_cached',
      receipt_summary: 'Stored live receipt should win.',
      performed_live: true,
    })
  })

  it('does not treat failed live intents as approved execution authority', async () => {
    mocks.listDashboardLiveIntents.mockReturnValue([
      {
        intent_id: 'intent-live-1',
        workspace_id: 7,
        run_id: 'run-live-1',
        status: 'execution_failed',
        approval_state: {
          approvals: [{ actor: 'reviewer-a' }, { actor: 'reviewer-b' }],
          required_approvals: 2,
        },
        execution_result: {
          status: 'execution_failed',
          receipt: null,
        },
      },
    ])

    const { POST } = await import('../../app/api/v1/prediction-markets/runs/[run_id]/live/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-live-1/live', {
      method: 'POST',
      body: JSON.stringify({
        execution_mode: 'live',
      }),
      headers: {
        'content-type': 'application/json',
      },
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-live-1' }),
    })
    const body = await response.json()

    expect(response.status).toBe(409)
    expect(body).toMatchObject({
      error: 'Live intent approval required',
      code: 'live_intent_required',
    })
    expect(mocks.executePredictionMarketRunLive).not.toHaveBeenCalled()
  })

  it('rejects live preparation when no approved live intent exists', async () => {
    mocks.listDashboardLiveIntents.mockReturnValue([])

    const { POST } = await import('../../app/api/v1/prediction-markets/runs/[run_id]/live/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-live-1/live', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-live-1' }),
    })
    const body = await response.json()

    expect(response.status).toBe(409)
    expect(body).toMatchObject({
      error: 'Live intent approval required',
      code: 'live_intent_required',
    })
    expect(mocks.preparePredictionMarketRunLive).not.toHaveBeenCalled()
    expect(mocks.executePredictionMarketRunLive).not.toHaveBeenCalled()
  })

  it('rejects invalid execution modes before calling prediction markets services', async () => {
    const { POST } = await import('../../app/api/v1/prediction-markets/runs/[run_id]/live/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-live-1/live', {
      method: 'POST',
      body: JSON.stringify({
        execution_mode: 'rehearsal',
      }),
      headers: {
        'content-type': 'application/json',
      },
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-live-1' }),
    })
    const body = await response.json()

    expect(response.status).toBe(400)
    expect(body).toEqual({
      error: 'Invalid execution mode; expected preflight or live',
      code: 'invalid_execution_mode',
    })
    expect(mocks.preparePredictionMarketRunLive).not.toHaveBeenCalled()
    expect(mocks.executePredictionMarketRunLive).not.toHaveBeenCalled()
  })

  it('preserves canonical benchmark fields when the live payload also carries rehydrated research aliases', async () => {
    mocks.preparePredictionMarketRunLive.mockReturnValue({
      gate_name: 'execution_projection_live',
      preflight_only: true,
      run_id: 'run-live-1',
      workspace_id: 7,
      surface_mode: 'live',
      live_route_allowed: true,
      live_status: 'ready',
      live_blocking_reasons: [],
      summary: 'Live surface is ready using the canonical execution_projection preview.',
      source_refs: {
        run_detail: 'run-live-1',
        execution_projection: 'run-live-1:execution_projection',
        live_projected_path: 'run-live-1:execution_projection#live',
        trade_intent_guard: 'run-live-1:trade_intent_guard',
        multi_venue_execution: 'run-live-1:multi_venue_execution',
      },
      live_path: {
        path: 'live',
        status: 'ready',
        effective_mode: 'live',
      },
      live_trade_intent_preview: {
        size_usd: 20,
        limit_price: 0.53,
        time_in_force: 'ioc',
      },
      live_trade_intent_preview_source: 'canonical_trade_intent_preview',
      venue_feed_surface_summary: 'Read-only market and user feed surface; live websocket unavailable.',
      venue_pathway_summary: 'Live pathway is preflight-only and remains benchmark-gated.',
      venue_pathway_highest_actionable_mode: 'live',
      execution_projection_requested_path: 'live',
      execution_projection_selected_path: 'live',
      execution_projection_selected_preview: {
        size_usd: 20,
      },
      benchmark_gate_summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=ready promotion=ready ready=yes preview=yes evidence=ready blockers=none out_of_sample=ready',
      benchmark_uplift_bps: 1100,
      benchmark_gate_status: 'ready',
      benchmark_promotion_status: 'ready',
      benchmark_promotion_ready: true,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'ready',
      benchmark_evidence_level: 'benchmark_proven',
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_gate_blockers: [],
      benchmark_gate_reasons: [],
      benchmark_gate_blocks_live: false,
      benchmark_gate_live_block_reason: null,
      benchmark_promotion_summary: 'benchmark canonical summary',
      research_benchmark_gate_summary:
        'research benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 promotion=blocked ready=no',
      research_benchmark_uplift_bps: 1100,
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'blocked',
      research_benchmark_promotion_ready: false,
      research_benchmark_preview_available: true,
      research_benchmark_promotion_evidence: 'blocked',
      research_benchmark_evidence_level: 'benchmark_preview',
      research_benchmark_promotion_gate_kind: 'preview_only',
      research_benchmark_gate_blockers: ['stale_research_summary'],
      research_benchmark_gate_reasons: ['stale_research_summary'],
      research_benchmark_live_block_reason: 'research stale blocker',
      execution_readiness: null,
      execution_pathways: null,
      execution_projection: {
        selected_path: 'live',
      },
      shadow_arbitrage: null,
      trade_intent_guard: {
        selected_path: 'live',
        trade_intent_preview: {
          size_usd: 20,
          limit_price: 0.53,
          time_in_force: 'ioc',
        },
        blocked_reasons: [],
        metadata: {
          benchmark_promotion_ready: true,
          benchmark_gate_blocks_live: false,
          benchmark_gate_live_block_reason: null,
          research_benchmark_promotion_ready: false,
          research_benchmark_live_block_reason: 'research stale blocker',
        },
      },
      multi_venue_execution: null,
    })

    const { POST } = await import('../../app/api/v1/prediction-markets/runs/[run_id]/live/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-live-1/live', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-live-1' }),
    })
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(body).toMatchObject({
      run_id: 'run-live-1',
      execution_projection_selected_path: 'live',
      benchmark_promotion_ready: true,
      benchmark_gate_blocks_live: false,
      benchmark_gate_live_block_reason: null,
      benchmark_promotion_summary: 'benchmark canonical summary',
      research_benchmark_promotion_ready: false,
      research_benchmark_live_block_reason: 'research stale blocker',
      venue_feed_surface_summary: 'Read-only market and user feed surface; live websocket unavailable.',
      venue_pathway_summary: 'Live pathway is preflight-only and remains benchmark-gated.',
      venue_pathway_highest_actionable_mode: 'live',
      trade_intent_guard: {
        selected_path: 'live',
        metadata: {
          benchmark_promotion_ready: true,
          benchmark_gate_blocks_live: false,
          benchmark_gate_live_block_reason: null,
          research_benchmark_promotion_ready: false,
          research_benchmark_live_block_reason: 'research stale blocker',
        },
      },
    })
  })

  it('short-circuits on auth errors before rate limiting or service calls', async () => {
    mocks.requireRole.mockReturnValue({ error: 'Forbidden', status: 403 })

    const { POST } = await import('../../app/api/v1/prediction-markets/runs/[run_id]/live/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-live-2/live', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-live-2' }),
    })
    const body = await response.json()

    expect(response.status).toBe(403)
    expect(body).toEqual({ error: 'Forbidden' })
    expect(mocks.heavyLimiter).not.toHaveBeenCalled()
    expect(mocks.preparePredictionMarketRunLive).not.toHaveBeenCalled()
    expect(mocks.executePredictionMarketRunLive).not.toHaveBeenCalled()
  })

  it('returns the limiter response before calling the live service', async () => {
    mocks.heavyLimiter.mockReturnValue(
      NextResponse.json({ error: 'Too Many Requests' }, { status: 429 }),
    )

    const { POST } = await import('../../app/api/v1/prediction-markets/runs/[run_id]/live/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-live-3/live', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-live-3' }),
    })
    const body = await response.json()

    expect(response.status).toBe(429)
    expect(body).toEqual({ error: 'Too Many Requests' })
    expect(mocks.preparePredictionMarketRunLive).not.toHaveBeenCalled()
    expect(mocks.executePredictionMarketRunLive).not.toHaveBeenCalled()
  })

  it('maps 404 service errors through the prediction markets error formatter', async () => {
    mocks.preparePredictionMarketRunLive.mockImplementation(() => {
      throw Object.assign(new Error('Prediction market run not found'), {
        status: 404,
        code: 'run_not_found',
      })
    })

    const { POST } = await import('../../app/api/v1/prediction-markets/runs/[run_id]/live/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-live-4/live', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-live-4' }),
    })
    const body = await response.json()

    expect(response.status).toBe(404)
    expect(body).toEqual({
      error: 'Prediction market run not found',
      code: 'run_not_found',
    })
  })

  it('maps 409 service errors through the prediction markets error formatter', async () => {
    mocks.preparePredictionMarketRunLive.mockImplementation(() => {
      throw Object.assign(new Error('Prediction market run has no execution projection'), {
        status: 409,
        code: 'execution_projection_unavailable',
      })
    })

    const { POST } = await import('../../app/api/v1/prediction-markets/runs/[run_id]/live/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-live-5/live', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-live-5' }),
    })
    const body = await response.json()

    expect(response.status).toBe(409)
    expect(body).toEqual({
      error: 'Prediction market run has no execution projection',
      code: 'execution_projection_unavailable',
    })
  })

  it('maps unexpected service exceptions through the prediction markets error formatter', async () => {
    mocks.preparePredictionMarketRunLive.mockImplementation(() => {
      throw new Error('live exploded')
    })

    const { POST } = await import('../../app/api/v1/prediction-markets/runs/[run_id]/live/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-live-6/live', {
      method: 'POST',
    })

    const response = await POST(request, {
      params: Promise.resolve({ run_id: 'run-live-6' }),
    })
    const body = await response.json()

    expect(response.status).toBe(500)
    expect(body).toEqual({
      error: 'live exploded',
      code: 'internal_error',
    })
  })
})
