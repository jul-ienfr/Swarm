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

import { NextRequest } from 'next/server'

const mocks = vi.hoisted(() => ({
  requireRole: vi.fn(),
  readLimiter: vi.fn(),
  buildPredictionDashboardOverview: vi.fn(),
  buildPredictionDashboardRunList: vi.fn(),
  buildPredictionDashboardRunDetail: vi.fn(),
  buildPredictionDashboardBenchmarkSnapshot: vi.fn(),
  buildPredictionDashboardArbitrageSnapshot: vi.fn(),
  buildPredictionDashboardVenueSnapshot: vi.fn(),
  getPredictionDashboardArbitrageCandidateSnapshot: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({
  requireRole: mocks.requireRole,
}))

vi.mock('@/lib/rate-limit', () => ({
  readLimiter: mocks.readLimiter,
}))

vi.mock('@/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
  },
}))

vi.mock('@/lib/prediction-markets/dashboard-models', () => ({
  buildPredictionDashboardOverview: mocks.buildPredictionDashboardOverview,
  buildPredictionDashboardRunList: mocks.buildPredictionDashboardRunList,
  buildPredictionDashboardRunDetail: mocks.buildPredictionDashboardRunDetail,
  buildPredictionDashboardBenchmarkSnapshot: mocks.buildPredictionDashboardBenchmarkSnapshot,
  buildPredictionDashboardArbitrageSnapshot: mocks.buildPredictionDashboardArbitrageSnapshot,
  buildPredictionDashboardVenueSnapshot: mocks.buildPredictionDashboardVenueSnapshot,
  getPredictionDashboardArbitrageCandidateSnapshot: mocks.getPredictionDashboardArbitrageCandidateSnapshot,
}))

describe('prediction markets dashboard routes', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.requireRole.mockReset()
    mocks.readLimiter.mockReset()
    mocks.buildPredictionDashboardOverview.mockReset()
    mocks.buildPredictionDashboardRunList.mockReset()
    mocks.buildPredictionDashboardRunDetail.mockReset()
    mocks.buildPredictionDashboardBenchmarkSnapshot.mockReset()
    mocks.buildPredictionDashboardArbitrageSnapshot.mockReset()
    mocks.buildPredictionDashboardVenueSnapshot.mockReset()
    mocks.getPredictionDashboardArbitrageCandidateSnapshot.mockReset()

    mocks.requireRole.mockReturnValue({ user: { workspace_id: 7, username: 'viewer' } })
    mocks.readLimiter.mockReturnValue(null)
  })

  it('returns a stable overview payload', async () => {
    mocks.buildPredictionDashboardOverview.mockReturnValue({
      schema_version: '1.0.0',
      freshness: { generated_at: '2026-04-08T00:00:00.000Z', captured_at: '2026-04-08T00:00:00.000Z', freshness_ms: 0 },
      workspace_id: 7,
      venue: 'polymarket',
      filters: { recommendation: null, selected_path: null, benchmark_state: null, surface_status: null, date_window: null },
      metrics: { runs: 1, bet: 1, wait: 0, no_trade: 0, benchmark_ready: 1, live_promotable: 1, live_blocked: 0, degraded_venues: 0 },
      alerts: [],
      runs: [],
      benchmark: null,
      venue_snapshot: { venue: 'polymarket' },
      recent_events: [],
      live_intents: [],
    })

    const { GET } = await import('@/app/api/v1/prediction-markets/dashboard/overview/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/dashboard/overview?venue=polymarket')
    const response = await GET(request)
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(response.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(mocks.requireRole).toHaveBeenCalledWith(request, 'viewer')
    expect(mocks.readLimiter).toHaveBeenCalledWith(request)
    expect(mocks.buildPredictionDashboardOverview).toHaveBeenCalledWith(7, 'polymarket', 20)
    expect(body).toMatchObject({
      workspace_id: 7,
      venue: 'polymarket',
      metrics: { live_promotable: 1 },
    })
  })

  it('returns a stable runs payload', async () => {
    mocks.buildPredictionDashboardRunList.mockReturnValue({
      generated_at: '2026-04-08T00:00:00.000Z',
      freshness: 'fresh',
      transport: 'polling',
      workspace_id: 7,
      venue: 'kalshi',
      total: 1,
      items: [{ run_id: 'run-1' }],
    })

    const { GET } = await import('@/app/api/v1/prediction-markets/dashboard/runs/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/dashboard/runs?venue=kalshi&limit=5')
    const response = await GET(request)
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(response.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(mocks.buildPredictionDashboardRunList).toHaveBeenCalledWith(7, 'kalshi', 5)
    expect(body).toMatchObject({
      venue: 'kalshi',
      total: 1,
      items: [{ run_id: 'run-1' }],
    })
  })

  it('returns a run detail payload and 404s when missing', async () => {
    mocks.buildPredictionDashboardRunDetail.mockReturnValue({
      generated_at: '2026-04-08T00:00:00.000Z',
      freshness: 'fresh',
      transport: 'polling',
      provenance: {
        workspace_id: 7,
        run_id: 'run-1',
        venue: 'polymarket',
        source: 'prediction-markets',
      },
      run: { run_id: 'run-1' },
      benchmark: { ready: true, status: 'eligible', gate_kind: 'local_benchmark', evidence_level: 'out_of_sample_promotion_evidence', summary: 'ready', blockers: [], live_block_reason: null },
      research: { origin: 'research_driven', pipeline_id: null, pipeline_version: null, compare_preferred_mode: null, weighted_probability_yes: null, weighted_coverage: null, abstention_blocks: null },
      execution: { selected_path: 'live', selected_path_status: 'ready', selected_path_effective_mode: 'live', selected_preview_source: 'canonical', selected_preview: null, requested_path: 'live', ready: true, blockers: [], capital_status: 'attached', reconciliation_status: 'available' },
      surfaces: {},
      live_intents: [],
      alerts: [],
    })

    const { GET } = await import('@/app/api/v1/prediction-markets/dashboard/runs/[run_id]/route')
    const okRequest = new NextRequest('http://localhost/api/v1/prediction-markets/dashboard/runs/run-1')
    const okResponse = await GET(okRequest, { params: Promise.resolve({ run_id: 'run-1' }) })
    const okBody = await okResponse.json()

    expect(okResponse.status).toBe(200)
    expect(okResponse.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(mocks.buildPredictionDashboardRunDetail).toHaveBeenCalledWith(7, 'run-1')
    expect(okBody).toMatchObject({
      provenance: { run_id: 'run-1' },
      benchmark: { ready: true },
    })

    mocks.buildPredictionDashboardRunDetail.mockReturnValue(null)
    const missingResponse = await GET(okRequest, { params: Promise.resolve({ run_id: 'missing' }) })
    const missingBody = await missingResponse.json()

    expect(missingResponse.status).toBe(404)
    expect(missingBody).toMatchObject({ error: 'Prediction market run not found' })
  })

  it('returns benchmark and venue snapshots', async () => {
    mocks.buildPredictionDashboardBenchmarkSnapshot.mockReturnValue({
      generated_at: '2026-04-08T00:00:00.000Z',
      freshness: 'warm',
      transport: 'polling',
      provenance: { workspace_id: 7, venue: 'polymarket', run_id: 'run-1', source: 'prediction-markets' },
      benchmark: { ready: true, status: 'eligible', gate_kind: 'local_benchmark', evidence_level: 'out_of_sample_promotion_evidence', summary: 'ready', blockers: [], live_block_reason: null },
      comparison: { selected_path: 'live', selected_path_status: 'ready', selected_path_effective_mode: 'live', benchmark_gate_blocks_live: false, benchmark_gate_live_block_reason: null, benchmark_gate_summary: 'ready' },
      run: { run_id: 'run-1' },
    })
    mocks.buildPredictionDashboardVenueSnapshot.mockReturnValue({
      generated_at: '2026-04-08T00:00:00.000Z',
      freshness: 'fresh',
      transport: 'polling',
      venue: 'polymarket',
      provenance: { source: 'prediction-markets', venue: 'polymarket' },
      capabilities: { venue: 'polymarket' },
      health: { api_status: 'ok' },
      feed: { market_feed_status: 'local_cache' },
      budgets: { timeout_ms: 100 },
      strategy: { source_of_truth: 'polymarket' },
    })
    mocks.buildPredictionDashboardArbitrageSnapshot.mockResolvedValue({
      generated_at: '2026-04-08T00:00:00.000Z',
      freshness: 'fresh',
      transport: 'polling',
      provenance: {
        workspace_id: 7,
        source: 'prediction-markets',
        venue_pair: ['polymarket', 'kalshi'],
        source_run_ids: ['run-1'],
        latest_source_run_id: 'run-1',
      },
      overview: {
        generated_at: '2026-04-08T00:00:00.000Z',
        freshness: 'fresh',
        transport: 'polling',
        workspace_id: 7,
        venue_pair: ['polymarket', 'kalshi'],
        source_runs_total: 1,
        source_run_ids: ['run-1'],
        compared_pairs: 1,
        candidate_count: 1,
        true_arbitrage_count: 1,
        relative_value_count: 0,
        manual_review_count: 0,
        benchmark_ready_runs: 1,
        live_promotable_runs: 1,
        best_shadow_edge_bps: 88,
        best_net_spread_bps: 92,
        best_candidate_id: 'arb:btc:polymarket-kalshi',
        alerts: [],
      },
      summary: {
        run_id: 'run-1',
        compared_pairs: 1,
        candidate_count: 1,
        manual_review_count: 0,
        best_shadow_edge_bps: 88,
        best_shadow_size_usd: 500,
        live_promotable: true,
        summary: 'Cross-venue arbitrage scan found 1 candidate.',
      },
      candidates: [
        {
          candidate_id: 'arb:btc:polymarket-kalshi',
          canonical_event_key: 'btc',
          opportunity_type: 'true_arbitrage',
          buy_venue: 'polymarket',
          buy_market_id: 'btc-buy',
          sell_venue: 'kalshi',
          sell_market_id: 'btc-sell',
          gross_spread_bps: 1100,
          net_spread_bps: 92,
          shadow_edge_bps: 88,
          recommended_size_usd: 500,
          confidence_score: 0.93,
          manual_review_required: false,
          blocking_reasons: [],
          source_run_id: 'run-1',
          source_run_ids: ['run-1'],
          benchmark_state: {
            ready: true,
            status: 'eligible',
            gate_kind: 'local_benchmark',
            evidence_level: 'out_of_sample_promotion_evidence',
            summary: 'ready',
            blockers: [],
            live_block_reason: null,
          },
          live_promotable: true,
          freshness: 'fresh',
          freshness_ms: 12000,
          summary: 'Shadow-ready candidate for polymarket → kalshi.',
        },
      ],
    })
    mocks.getPredictionDashboardArbitrageCandidateSnapshot.mockResolvedValue({
      candidate_id: 'arb:btc:polymarket-kalshi',
      canonical_event_key: 'btc',
      opportunity_type: 'true_arbitrage',
      buy_venue: 'polymarket',
      buy_market_id: 'btc-buy',
      sell_venue: 'kalshi',
      sell_market_id: 'btc-sell',
      gross_spread_bps: 1100,
      net_spread_bps: 92,
      shadow_edge_bps: 88,
      recommended_size_usd: 500,
      confidence_score: 0.93,
      manual_review_required: false,
      blocking_reasons: [],
      source_run_id: 'run-1',
      source_run_ids: ['run-1'],
      benchmark_state: {
        ready: true,
        status: 'eligible',
        gate_kind: 'local_benchmark',
        evidence_level: 'out_of_sample_promotion_evidence',
        summary: 'ready',
        blockers: [],
        live_block_reason: null,
      },
      live_promotable: true,
      freshness: 'fresh',
      freshness_ms: 12000,
      summary: 'Shadow-ready candidate for polymarket → kalshi.',
    })

    const benchmarkRoute = await import('@/app/api/v1/prediction-markets/dashboard/benchmark/route')
    const venueRoute = await import('@/app/api/v1/prediction-markets/dashboard/venues/[venue]/route')

    const benchmarkResponse = await benchmarkRoute.GET(
      new NextRequest('http://localhost/api/v1/prediction-markets/dashboard/benchmark?venue=polymarket&run_id=run-1'),
    )
    const benchmarkBody = await benchmarkResponse.json()
    expect(benchmarkResponse.status).toBe(200)
    expect(benchmarkResponse.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(benchmarkBody).toMatchObject({
      provenance: { run_id: 'run-1' },
      benchmark: { ready: true },
    })

    const venueResponse = await venueRoute.GET(
      new NextRequest('http://localhost/api/v1/prediction-markets/dashboard/venues/polymarket'),
      { params: Promise.resolve({ venue: 'polymarket' }) },
    )
    const venueBody = await venueResponse.json()
    expect(venueResponse.status).toBe(200)
    expect(venueResponse.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(venueBody).toMatchObject({
      venue: 'polymarket',
      freshness: 'fresh',
    })

    const arbitrageRoute = await import('@/app/api/v1/prediction-markets/dashboard/arbitrage/route')
    const arbitrageResponse = await arbitrageRoute.GET(
      new NextRequest(
        'http://localhost/api/v1/prediction-markets/dashboard/arbitrage?limit_per_venue=16&max_pairs=12&min_arbitrage_spread_bps=75&shadow_candidates=3',
      ),
    )
    const arbitrageBody = await arbitrageResponse.json()
    expect(arbitrageResponse.status).toBe(200)
    expect(arbitrageResponse.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(mocks.buildPredictionDashboardArbitrageSnapshot).toHaveBeenCalledWith(7, {
      limitPerVenue: 16,
      maxPairs: 12,
      minArbitrageSpreadBps: 75,
      shadowCandidateLimit: 3,
      forceRefresh: true,
    })
    expect(arbitrageBody).toMatchObject({
      arbitrage: {
      overview: { best_candidate_id: 'arb:btc:polymarket-kalshi' },
      candidates: [{ candidate_id: 'arb:btc:polymarket-kalshi' }],
      },
    })

    const arbitrageCandidateRoute = await import('@/app/api/v1/prediction-markets/dashboard/arbitrage/[candidate_id]/route')
    const arbitrageCandidateResponse = await arbitrageCandidateRoute.GET(
      new NextRequest('http://localhost/api/v1/prediction-markets/dashboard/arbitrage/arb:btc:polymarket-kalshi'),
      { params: Promise.resolve({ candidate_id: 'arb:btc:polymarket-kalshi' }) },
    )
    const arbitrageCandidateBody = await arbitrageCandidateResponse.json()
    expect(arbitrageCandidateResponse.status).toBe(200)
    expect(mocks.getPredictionDashboardArbitrageCandidateSnapshot).toHaveBeenCalledWith(7, 'arb:btc:polymarket-kalshi', ['polymarket', 'kalshi'], 16)
    expect(arbitrageCandidateBody).toMatchObject({
      candidate_id: 'arb:btc:polymarket-kalshi',
      benchmark_state: { ready: true },
    })
  })
})
