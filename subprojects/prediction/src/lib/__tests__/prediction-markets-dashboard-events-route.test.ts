import { randomUUID } from 'node:crypto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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

import { NextRequest } from 'next/server'

const mocks = vi.hoisted(() => ({
  requireRole: vi.fn(),
  readLimiter: vi.fn(),
  listPredictionMarketRuns: vi.fn(),
  getPredictionMarketRunDetails: vi.fn(),
  getVenueCapabilities: vi.fn(),
  getVenueHealthSnapshot: vi.fn(),
  listPredictionMarketVenues: vi.fn(),
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

vi.mock('@/lib/prediction-markets/service', () => ({
  listPredictionMarketRuns: mocks.listPredictionMarketRuns,
  getPredictionMarketRunDetails: mocks.getPredictionMarketRunDetails,
}))

vi.mock('@/lib/prediction-markets/venue-ops', () => ({
  getVenueCapabilities: mocks.getVenueCapabilities,
  getVenueHealthSnapshot: mocks.getVenueHealthSnapshot,
  listPredictionMarketVenues: mocks.listPredictionMarketVenues,
}))

import {
  publishPredictionDashboardArbitrageSnapshot,
  publishPredictionDashboardEvent,
  publishPredictionDashboardLiveIntentEvent,
  resetPredictionDashboardEventStateForTests,
} from '@/lib/prediction-markets/dashboard-events'

function makeRun(overrides: Record<string, unknown> = {}) {
  return {
    run_id: 'run-1',
    workspace_id: 7,
    venue: 'polymarket',
    market_id: 'market-1',
    market_slug: 'market-1',
    status: 'completed',
    recommendation: 'bet',
    side: 'yes',
    confidence: 0.77,
    probability_yes: 0.68,
    market_price_yes: 0.52,
    edge_bps: 1400,
    updated_at: 10,
    benchmark_promotion_ready: false,
    benchmark_promotion_gate_kind: 'preview_only',
    benchmark_gate_status: 'preview_only',
    benchmark_evidence_level: 'benchmark_preview',
    benchmark_promotion_status: 'blocked',
    benchmark_promotion_blocker_summary: 'blocked by out_of_sample_unproven',
    benchmark_gate_live_block_reason: 'benchmark_promotion_not_ready_for_live',
    benchmark_gate_blockers: ['out_of_sample_unproven'],
    benchmark_gate_summary: 'benchmark gate blocked',
    research_benchmark_gate_summary: 'benchmark gate blocked',
    execution_projection_selected_path: 'shadow',
    execution_projection_selected_path_status: 'ready',
    execution_projection_selected_path_effective_mode: 'shadow',
    execution_projection_recommended_effective_mode: 'shadow',
    benchmark_gate_blocks_live: false,
    ...overrides,
  }
}

describe('prediction markets dashboard SSE route', () => {
  const previousDbPath = process.env.PREDICTION_DB_PATH

  beforeEach(() => {
    process.env.PREDICTION_DB_PATH = `prediction-dashboard-events-route-${randomUUID()}`
    resetPredictionDashboardEventStateForTests()
    mocks.requireRole.mockReset()
    mocks.readLimiter.mockReset()
    mocks.listPredictionMarketRuns.mockReset()
    mocks.getPredictionMarketRunDetails.mockReset()
    mocks.getVenueCapabilities.mockReset()
    mocks.getVenueHealthSnapshot.mockReset()
    mocks.listPredictionMarketVenues.mockReset()
    mocks.loggerError.mockReset()
    mocks.requireRole.mockReturnValue({ user: { workspace_id: 7, username: 'viewer' } })
    mocks.readLimiter.mockReturnValue(null)
    mocks.listPredictionMarketVenues.mockReturnValue(['polymarket'])
    mocks.listPredictionMarketRuns.mockReturnValue([makeRun()])
    mocks.getPredictionMarketRunDetails.mockReturnValue(makeRun({ updated_at: 10 }))
    mocks.getVenueCapabilities.mockReturnValue({
      venue: 'polymarket',
      label: 'Polymarket',
      venue_type: 'execution-equivalent',
      market_shape: 'binary_only',
      supports: {
        list_markets: true,
        get_market: true,
        build_snapshot: true,
        orderbook: true,
        history: true,
        search: false,
        replay: true,
      },
      limits: {
        binary_only: true,
        max_list_limit: 50,
        max_history_limit: 100,
      },
      notes: ['read only'],
      supports_execution: false,
      supports_paper_mode: false,
    })
    mocks.getVenueHealthSnapshot.mockReturnValue({
      venue: 'polymarket',
      status: 'ready',
      checked_at: '2026-04-08T00:00:00.000Z',
      network_checked: false,
      read_only: true,
      configured_endpoints: ['https://example.com'],
      reasons: [],
    })
  })

  afterEach(() => {
    resetPredictionDashboardEventStateForTests()
    if (previousDbPath == null) {
      delete process.env.PREDICTION_DB_PATH
    } else {
      process.env.PREDICTION_DB_PATH = previousDbPath
    }
  })

  it('streams replay mode with bootstrap snapshots and stored events', async () => {
    publishPredictionDashboardArbitrageSnapshot({
      generated_at: '2026-04-08T00:01:00.000Z',
      freshness: 'fresh',
      transport: 'polling',
      workspace_id: 7,
      venue_pair: ['polymarket', 'kalshi'],
      compared_pairs: 3,
      candidate_count: 1,
      manual_review_count: 0,
      best_shadow_edge_bps: 175,
      candidates: [
        {
          candidate_id: 'arb-1',
          canonical_event_key: 'event-1',
          buy_venue: 'polymarket',
          sell_venue: 'kalshi',
          gross_spread_bps: 200,
          net_spread_bps: 150,
          shadow_edge_bps: 140,
          recommended_size_usd: 125,
          confidence_score: 0.92,
          freshness_ms: 2_000,
          blocking_reasons: [],
          manual_review_required: false,
          opportunity_type: 'true_arbitrage',
        },
      ],
    })
    publishPredictionDashboardEvent({
      type: 'benchmark_gate_changed',
      severity: 'warn',
      workspace_id: 7,
      venue: 'polymarket',
      run_id: 'run-1',
      intent_id: null,
      source: 'poller',
      summary: 'Benchmark gate changed for polymarket.',
      payload: {
        previous: { ready: false },
        next: { ready: true },
      },
    })
    publishPredictionDashboardLiveIntentEvent({
      workspaceId: 7,
      venue: 'polymarket',
      liveIntentId: 'intent-1',
      runId: 'run-1',
      type: 'live_intent_created',
      summary: 'Live intent created for run-1',
      severity: 'error',
      payload: { approval_state: { status: 'pending_approval' } },
    })

    const { GET } = await import('@/app/api/v1/prediction-markets/dashboard/events/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/dashboard/events?mode=replay', {
      method: 'GET',
    })

    const response = await GET(request)
    const text = await response.text()

    expect(response.status).toBe(200)
    expect(response.headers.get('content-type')).toContain('text/event-stream')
    expect(response.headers.get('cache-control')).toContain('no-cache')
    expect(response.headers.get('x-prediction-markets-api')).toBe('v1')
    expect(text).toContain('event: dashboard_snapshot')
    expect(text).toContain('event: runs_refresh_hint')
    expect(text).toContain('event: arbitrage_candidate_opened')
    expect(text).toContain('event: benchmark_gate_changed')
    expect(text).toContain('event: live_intent_created')
    expect(text).toContain('Dashboard snapshot captured for polymarket.')
  })

  it('opens a live stream and emits the initial bootstrap chunk', async () => {
    const { GET } = await import('@/app/api/v1/prediction-markets/dashboard/events/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/dashboard/events?mode=live&heartbeat_ms=1000', {
      method: 'GET',
    })

    const response = await GET(request)
    expect(response.status).toBe(200)
    expect(response.headers.get('content-type')).toContain('text/event-stream')
    expect(response.headers.get('x-accel-buffering')).toBe('no')

    const reader = response.body?.getReader()
    expect(reader).toBeTruthy()

    const first = await reader!.read()
    const chunk = new TextDecoder().decode(first.value)
    expect(first.done).toBe(false)
    expect(chunk).toContain('prediction-markets dashboard events connected')

    const second = await reader!.read()
    const secondChunk = new TextDecoder().decode(second.value)
    expect(second.done).toBe(false)
    expect(secondChunk).toContain('event: dashboard_snapshot')

    await reader!.cancel()
  })
})
