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

import { NextRequest, NextResponse } from 'next/server'

const mocks = vi.hoisted(() => ({
  requireRole: vi.fn(),
  readLimiter: vi.fn(),
  heavyLimiter: vi.fn(),
  resolveDashboardActor: vi.fn(),
  createDashboardLiveIntent: vi.fn(),
  listDashboardLiveIntents: vi.fn(),
  getDashboardLiveIntent: vi.fn(),
  approveDashboardLiveIntent: vi.fn(),
  rejectDashboardLiveIntent: vi.fn(),
  buildPredictionDashboardVenueSnapshot: vi.fn(),
  comparePredictionDashboardVenueSnapshots: vi.fn(),
  ensurePredictionDashboardVenuePolling: vi.fn(),
  formatPredictionDashboardEventAsSse: vi.fn(),
  formatPredictionDashboardSseComment: vi.fn(),
  getPredictionDashboardEventHistory: vi.fn(),
  subscribePredictionDashboardEvents: vi.fn(),
  listPredictionMarketVenues: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({
  requireRole: mocks.requireRole,
}))

vi.mock('@/lib/rate-limit', () => ({
  readLimiter: mocks.readLimiter,
  heavyLimiter: mocks.heavyLimiter,
}))

vi.mock('@/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
  },
}))

vi.mock('@/lib/prediction-markets/errors', () => ({
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
        body: { error: typedError.message, code: typedError.code },
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

vi.mock('@/lib/prediction-markets/dashboard-live-intents', () => ({
  resolveDashboardActor: mocks.resolveDashboardActor,
  createDashboardLiveIntent: mocks.createDashboardLiveIntent,
  listDashboardLiveIntents: mocks.listDashboardLiveIntents,
  getDashboardLiveIntent: mocks.getDashboardLiveIntent,
  approveDashboardLiveIntent: mocks.approveDashboardLiveIntent,
  rejectDashboardLiveIntent: mocks.rejectDashboardLiveIntent,
}))

vi.mock('@/lib/prediction-markets/dashboard-events', () => ({
  buildPredictionDashboardVenueSnapshot: mocks.buildPredictionDashboardVenueSnapshot,
  comparePredictionDashboardVenueSnapshots: mocks.comparePredictionDashboardVenueSnapshots,
  ensurePredictionDashboardVenuePolling: mocks.ensurePredictionDashboardVenuePolling,
  formatPredictionDashboardEventAsSse: mocks.formatPredictionDashboardEventAsSse,
  formatPredictionDashboardSseComment: mocks.formatPredictionDashboardSseComment,
  getPredictionDashboardEventHistory: mocks.getPredictionDashboardEventHistory,
  subscribePredictionDashboardEvents: mocks.subscribePredictionDashboardEvents,
}))

vi.mock('@/lib/prediction-markets/venue-ops', () => ({
  listPredictionMarketVenues: mocks.listPredictionMarketVenues,
}))

describe('prediction markets dashboard live-intent routes', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.requireRole.mockReset()
    mocks.readLimiter.mockReset()
    mocks.heavyLimiter.mockReset()
    mocks.resolveDashboardActor.mockReset()
    mocks.createDashboardLiveIntent.mockReset()
    mocks.listDashboardLiveIntents.mockReset()
    mocks.getDashboardLiveIntent.mockReset()
    mocks.approveDashboardLiveIntent.mockReset()
    mocks.rejectDashboardLiveIntent.mockReset()
    mocks.buildPredictionDashboardVenueSnapshot.mockReset()
    mocks.comparePredictionDashboardVenueSnapshots.mockReset()
    mocks.ensurePredictionDashboardVenuePolling.mockReset()
    mocks.formatPredictionDashboardEventAsSse.mockReset()
    mocks.formatPredictionDashboardSseComment.mockReset()
    mocks.getPredictionDashboardEventHistory.mockReset()
    mocks.subscribePredictionDashboardEvents.mockReset()
    mocks.listPredictionMarketVenues.mockReset()
    mocks.requireRole.mockReturnValue({ user: { workspace_id: 7, username: 'operator' } })
    mocks.readLimiter.mockReturnValue(null)
    mocks.heavyLimiter.mockReturnValue(null)
    mocks.resolveDashboardActor.mockImplementation((request: Request, fallback: string) => {
      return request.headers.get('x-prediction-dashboard-actor') || fallback
    })
    mocks.createDashboardLiveIntent.mockReturnValue({
      intent_id: 'live-intent-1',
      run_id: 'run-1',
      approval_state: { status: 'pending', approvers: [] },
    })
    mocks.listDashboardLiveIntents.mockReturnValue([])
    mocks.getDashboardLiveIntent.mockReturnValue({
      intent_id: 'live-intent-1',
      run_id: 'run-1',
    })
    mocks.approveDashboardLiveIntent.mockReturnValue({
      intent_id: 'live-intent-1',
      approval_state: { status: 'approved', approvers: ['approver-b'] },
    })
    mocks.rejectDashboardLiveIntent.mockReturnValue({
      intent_id: 'live-intent-1',
      approval_state: { status: 'rejected', approvers: [] },
    })
    mocks.buildPredictionDashboardVenueSnapshot.mockResolvedValue({
      workspace_id: 7,
      venue: 'polymarket',
      captured_at: '2026-04-08T00:00:00.000Z',
      runs_total: 0,
      latest_run_id: null,
      latest_run_updated_at: null,
      latest_recommendation: null,
      latest_selected_path: null,
      latest_selected_path_status: null,
      latest_live_route_allowed: null,
      benchmark_state: {
        ready: false,
        gate_kind: null,
        status: null,
        evidence_level: null,
        promotion_status: null,
        blocker_summary: null,
        live_block_reason: null,
        blockers: [],
        summary: null,
      },
      venue_health_status: 'ready',
      venue_feed_status: 'healthy',
      venue_user_feed_status: 'healthy',
      venue_rtds_status: 'healthy',
      venue_capabilities: 'read_only',
      venue_supports_execution: false,
      venue_supports_paper_mode: true,
      venue_notes: [],
    })
    mocks.comparePredictionDashboardVenueSnapshots.mockReturnValue([])
    mocks.ensurePredictionDashboardVenuePolling.mockReturnValue(() => {})
    mocks.formatPredictionDashboardEventAsSse.mockImplementation((event: { type?: string; summary?: string }) =>
      `event: ${event.type ?? 'unknown'}\ndata: ${JSON.stringify(event)}\n\n`)
    mocks.formatPredictionDashboardSseComment.mockImplementation((comment: string) => `: ${comment}\n\n`)
    mocks.getPredictionDashboardEventHistory.mockReturnValue([])
    mocks.subscribePredictionDashboardEvents.mockReturnValue(() => {})
    mocks.listPredictionMarketVenues.mockReturnValue(['polymarket'])
  })

  it('creates, approves, rejects, and fetches live intents', async () => {
    const { POST: createLiveIntent } = await import('../../app/api/v1/prediction-markets/dashboard/live-intents/route')
    const { GET: getLiveIntent } = await import('../../app/api/v1/prediction-markets/dashboard/live-intents/[intent_id]/route')
    const { POST: approveLiveIntent } = await import('../../app/api/v1/prediction-markets/dashboard/live-intents/[intent_id]/approve/route')
    const { POST: rejectLiveIntent } = await import('../../app/api/v1/prediction-markets/dashboard/live-intents/[intent_id]/reject/route')

    const createRequest = new NextRequest('http://localhost/api/v1/prediction-markets/dashboard/live-intents', {
      method: 'POST',
      headers: { 'x-prediction-dashboard-actor': 'creator-a' },
      body: JSON.stringify({
        run_id: 'run-1',
        note: 'please review',
      }),
    })
    const createResponse = await createLiveIntent(createRequest)
    const createBody = await createResponse.json()

    expect(createResponse.status).toBe(201)
    expect(createBody).toMatchObject({
      live_intent: {
        intent_id: 'live-intent-1',
      },
    })
    expect(mocks.createDashboardLiveIntent).toHaveBeenCalledWith(expect.objectContaining({
      runId: 'run-1',
      actor: 'creator-a',
      workspaceId: 7,
    }))

    const getRequest = new NextRequest('http://localhost/api/v1/prediction-markets/dashboard/live-intents/live-intent-1')
    const getResponse = await getLiveIntent(getRequest, { params: Promise.resolve({ intent_id: 'live-intent-1' }) })
    expect(getResponse.status).toBe(200)
    expect(await getResponse.json()).toMatchObject({
      live_intent: {
        intent_id: 'live-intent-1',
      },
    })

    const approveRequest = new NextRequest('http://localhost/api/v1/prediction-markets/dashboard/live-intents/live-intent-1/approve', {
      method: 'POST',
      headers: { 'x-prediction-dashboard-actor': 'approver-b' },
    })
    const approveResponse = await approveLiveIntent(approveRequest, { params: Promise.resolve({ intent_id: 'live-intent-1' }) })
    expect(approveResponse.status).toBe(200)
    expect(mocks.approveDashboardLiveIntent).toHaveBeenCalledWith(expect.objectContaining({
      intentId: 'live-intent-1',
      actor: 'approver-b',
      workspaceId: 7,
    }))

    const rejectRequest = new NextRequest('http://localhost/api/v1/prediction-markets/dashboard/live-intents/live-intent-1/reject', {
      method: 'POST',
      headers: { 'x-prediction-dashboard-actor': 'approver-b' },
    })
    const rejectResponse = await rejectLiveIntent(rejectRequest, { params: Promise.resolve({ intent_id: 'live-intent-1' }) })
    expect(rejectResponse.status).toBe(200)
    expect(mocks.rejectDashboardLiveIntent).toHaveBeenCalledWith(expect.objectContaining({
      intentId: 'live-intent-1',
      actor: 'approver-b',
      workspaceId: 7,
    }))
  })

})
