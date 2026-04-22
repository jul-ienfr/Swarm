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

import { NextRequest, NextResponse } from 'next/server'

const mocks = vi.hoisted(() => ({
  requireRole: vi.fn(),
  readLimiter: vi.fn(),
  buildMeteoPricingReportFromProviders: vi.fn(),
  buildMeteoBestBetsSummary: vi.fn(),
  buildMeteoExecutionCandidates: vi.fn(),
  detectMeteoMarketAnomalies: vi.fn(),
  buildMeteoExecutionSummary: vi.fn(),
  extractMeteoResolutionSource: vi.fn(),
  buildMeteoStationMetadata: vi.fn(),
  analyzeMeteoResolutionSource: vi.fn(),
  toPolymarketQuoteMarketEvent: vi.fn(),
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

vi.mock('@/lib/prediction-markets/meteo', () => ({
  buildMeteoPricingReportFromProviders: mocks.buildMeteoPricingReportFromProviders,
  buildMeteoBestBetsSummary: mocks.buildMeteoBestBetsSummary,
  buildMeteoExecutionCandidates: mocks.buildMeteoExecutionCandidates,
  detectMeteoMarketAnomalies: mocks.detectMeteoMarketAnomalies,
  buildMeteoExecutionSummary: mocks.buildMeteoExecutionSummary,
  extractMeteoResolutionSource: mocks.extractMeteoResolutionSource,
  buildMeteoStationMetadata: mocks.buildMeteoStationMetadata,
  analyzeMeteoResolutionSource: mocks.analyzeMeteoResolutionSource,
}))

vi.mock('@/lib/prediction-markets/polymarket-market-event', () => ({
  toPolymarketQuoteMarketEvent: mocks.toPolymarketQuoteMarketEvent,
}))

describe('prediction markets météo route', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.requireRole.mockReset()
    mocks.readLimiter.mockReset()
    mocks.buildMeteoPricingReportFromProviders.mockReset()
    mocks.buildMeteoBestBetsSummary.mockReset()
    mocks.buildMeteoExecutionCandidates.mockReset()
    mocks.detectMeteoMarketAnomalies.mockReset()
    mocks.buildMeteoExecutionSummary.mockReset()
    mocks.extractMeteoResolutionSource.mockReset()
    mocks.buildMeteoStationMetadata.mockReset()
    mocks.analyzeMeteoResolutionSource.mockReset()
    mocks.toPolymarketQuoteMarketEvent.mockReset()
    mocks.loggerError.mockReset()

    mocks.requireRole.mockReturnValue({ user: { workspace_id: 7, username: 'viewer' } })
    mocks.readLimiter.mockReturnValue(null)
    mocks.extractMeteoResolutionSource.mockReturnValue({ provider: 'unknown', sourceUrl: null, stationName: null, stationCode: null, stationType: 'unknown', measurementField: null, measurementKind: 'unknown', unit: 'f', precision: 'unknown', finalizationRule: null, revisionRule: null, extractedFrom: [], confidence: 0.2 })
    mocks.buildMeteoStationMetadata.mockReturnValue({ stationName: null, stationCode: null, stationType: 'unknown', countryOrRegion: null, city: null, sourceProvider: 'unknown', sourceUrl: null, sourceNetwork: null, notes: [] })
    mocks.analyzeMeteoResolutionSource.mockReturnValue({ isOfficialSourceIdentified: false, needsManualReview: true, confidence: 0.2 })
    mocks.buildMeteoBestBetsSummary.mockReturnValue({
      summary: 'Top météo bet: YES 68-69F',
      actionableCount: 1,
      strongestOpportunity: null,
      topOpportunities: [],
      recommendedSideCounts: { yes: 1, no: 0, pass: 0 },
      noTradeLabels: [],
    })
    mocks.buildMeteoExecutionCandidates.mockReturnValue([])
    mocks.detectMeteoMarketAnomalies.mockReturnValue([])
    mocks.buildMeteoExecutionSummary.mockReturnValue({
      candidateCount: 0,
      tradeableCount: 0,
      highPriorityCount: 0,
      anomalyCount: 0,
    })
  })

  it('returns a météo pricing payload for the requested question and coordinates', async () => {
    mocks.buildMeteoPricingReportFromProviders.mockResolvedValue({
      spec: {
        question: 'What will the highest temperature in Los Angeles, CA on Apr 21, 2026 be: 66F-67F, 68F-69F, or 70F+?',
        city: 'Los Angeles',
        countryOrRegion: 'CA',
        marketDate: 'Apr 21, 2026',
        kind: 'high',
        unit: 'f',
        bins: [{ label: '68-69F', unit: 'f', lower: { value: 68, inclusive: true }, upper: { value: 69, inclusive: true } }],
      },
      forecastPoints: [{ provider: 'open-meteo:ecmwf', mean: 68.8, stddev: 1.4, weight: 1 }],
      report: {
        mean: 68.8,
        stddev: 1.4,
        unit: 'f',
        bins: [],
        opportunities: [],
        marketSnapshot: { pricedBinCount: 1, yesPriceSum: 0.33, overround: -0.67 },
        provenance: {
          providerCount: 1,
          providers: ['open-meteo:ecmwf'],
          contributions: [],
        },
      },
    })
    mocks.extractMeteoResolutionSource.mockReturnValue({
      provider: 'wunderground',
      sourceUrl: 'https://www.wunderground.com/history/daily/us/ca/los-angeles/KLAX',
      stationName: 'Los Angeles Airport Station',
      stationCode: 'KLAX',
      stationType: 'airport',
      measurementField: 'Daily Maximum Temperature',
      measurementKind: 'high_temperature',
      unit: 'f',
      precision: 'whole-degree',
      finalizationRule: 'once information is finalized',
      revisionRule: 'post-finalization revisions ignored',
      extractedFrom: ['resolution_source', 'rules'],
      confidence: 0.98,
    })
    mocks.buildMeteoStationMetadata.mockReturnValue({
      stationName: 'Los Angeles Airport Station',
      stationCode: 'KLAX',
      stationType: 'airport',
      countryOrRegion: 'CA',
      city: 'Los Angeles',
      sourceProvider: 'wunderground',
      sourceUrl: 'https://www.wunderground.com/history/daily/us/ca/los-angeles/KLAX',
      sourceNetwork: 'wunderground',
      notes: ['Parsed from explicit resolution URL suffix'],
    })
    mocks.analyzeMeteoResolutionSource.mockReturnValue({
      isOfficialSourceIdentified: true,
      needsManualReview: false,
      confidence: 0.98,
      matchedSignals: ['provider', 'station', 'precision'],
    })

    const { GET } = await import('@/app/api/v1/prediction-markets/meteo/route')
    const request = new NextRequest(
      'http://localhost/api/v1/prediction-markets/meteo?question=What%20will%20the%20highest%20temperature%20in%20Los%20Angeles,%20CA%20on%20Apr%2021,%202026%20be:%2066F-67F,%2068F-69F,%20or%2070F%2B%3F&latitude=34.05&longitude=-118.25&open_meteo_models=ecmwf,gfs&include_nws=false&cache_ttl_ms=60000&retry_count=2&market_prices=%7B%2268-69F%22%3A0.33%7D',
    )

    const response = await GET(request)
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(response.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(mocks.requireRole).toHaveBeenCalledWith(request, 'viewer')
    expect(mocks.readLimiter).toHaveBeenCalledWith(request)
    expect(mocks.buildMeteoPricingReportFromProviders).toHaveBeenCalledWith({
      question: 'What will the highest temperature in Los Angeles, CA on Apr 21, 2026 be: 66F-67F, 68F-69F, or 70F+?',
      latitude: 34.05,
      longitude: -118.25,
      openMeteoModels: ['ecmwf', 'gfs'],
      includeNws: false,
      includeMeteostat: undefined,
      meteostatStart: undefined,
      meteostatEnd: undefined,
      meteostatApiKey: undefined,
      cacheTtlMs: 60000,
      retryCount: 2,
      marketPrices: { '68-69F': 0.33 },
      userAgent: 'swarm-prediction/1.0 (+meteo-route)',
    })
    expect(body).toMatchObject({
      spec: {
        city: 'Los Angeles',
        kind: 'high',
      },
      forecast_points: [
        { provider: 'open-meteo:ecmwf', mean: 68.8 },
      ],
      resolution_source: {
        provider: 'wunderground',
        stationCode: 'KLAX',
        stationName: 'Los Angeles Airport Station',
        precision: 'whole-degree',
      },
      station_metadata: {
        stationCode: 'KLAX',
        stationName: 'Los Angeles Airport Station',
        sourceProvider: 'wunderground',
      },
      resolution_analysis: {
        isOfficialSourceIdentified: true,
        needsManualReview: false,
        confidence: 0.98,
      },
      best_bets: {
        summary: 'Top météo bet: YES 68-69F',
      },
    })
    expect(mocks.extractMeteoResolutionSource).toHaveBeenCalledWith({
      question: 'What will the highest temperature in Los Angeles, CA on Apr 21, 2026 be: 66F-67F, 68F-69F, or 70F+?',
      spec: expect.objectContaining({ city: 'Los Angeles', kind: 'high' }),
      resolutionSource: undefined,
      description: undefined,
      rules: undefined,
    })
    expect(mocks.buildMeteoStationMetadata).toHaveBeenCalledWith({
      question: 'What will the highest temperature in Los Angeles, CA on Apr 21, 2026 be: 66F-67F, 68F-69F, or 70F+?',
      spec: expect.objectContaining({ city: 'Los Angeles', kind: 'high' }),
      resolutionSource: undefined,
      description: undefined,
      rules: undefined,
    })
    expect(mocks.analyzeMeteoResolutionSource).toHaveBeenCalledWith({
      question: 'What will the highest temperature in Los Angeles, CA on Apr 21, 2026 be: 66F-67F, 68F-69F, or 70F+?',
      spec: expect.objectContaining({ city: 'Los Angeles', kind: 'high' }),
      resolutionSource: undefined,
      description: undefined,
      rules: undefined,
    })
  })

  it('short-circuits on auth errors before touching the limiter or builder', async () => {
    mocks.requireRole.mockReturnValue({ error: 'Forbidden', status: 403 })

    const { GET } = await import('@/app/api/v1/prediction-markets/meteo/route')
    const response = await GET(new NextRequest('http://localhost/api/v1/prediction-markets/meteo'))
    const body = await response.json()

    expect(response.status).toBe(403)
    expect(body).toEqual({ error: 'Forbidden' })
    expect(mocks.readLimiter).not.toHaveBeenCalled()
    expect(mocks.buildMeteoPricingReportFromProviders).not.toHaveBeenCalled()
  })

  it('returns the limiter response before invoking the météo builder', async () => {
    const limited = NextResponse.json({ error: 'Too Many Requests' }, { status: 429 })
    mocks.readLimiter.mockReturnValue(limited)

    const { GET } = await import('@/app/api/v1/prediction-markets/meteo/route')
    const response = await GET(
      new NextRequest('http://localhost/api/v1/prediction-markets/meteo?question=q&latitude=1&longitude=2'),
    )
    const body = await response.json()

    expect(response.status).toBe(429)
    expect(body).toEqual({ error: 'Too Many Requests' })
    expect(mocks.buildMeteoPricingReportFromProviders).not.toHaveBeenCalled()
  })

  it('returns a structured error payload on invalid query params and logs the failure', async () => {
    const { GET } = await import('@/app/api/v1/prediction-markets/meteo/route')
    const response = await GET(
      new NextRequest('http://localhost/api/v1/prediction-markets/meteo?question=q&latitude=abc&longitude=-118.25'),
    )
    const body = await response.json()

    expect(response.status).toBe(500)
    expect(body).toEqual({
      error: 'Invalid numeric query parameter: latitude',
      code: 'internal_error',
    })
    expect(mocks.loggerError).toHaveBeenCalledTimes(1)
    expect(mocks.buildMeteoPricingReportFromProviders).not.toHaveBeenCalled()
  })

  it('passes meteostat toggles through when explicitly enabled', async () => {
    mocks.buildMeteoPricingReportFromProviders.mockResolvedValue({
      spec: {
        question: 'q',
        city: null,
        countryOrRegion: null,
        marketDate: null,
        kind: 'high',
        unit: 'f',
        bins: [],
      },
      forecastPoints: [],
      report: {
        mean: 0,
        stddev: 1,
        unit: 'f',
        bins: [],
        opportunities: [],
        marketSnapshot: { pricedBinCount: 0, yesPriceSum: null, overround: null },
        provenance: { providerCount: 0, providers: [], contributions: [] },
      },
    })

    const { GET } = await import('@/app/api/v1/prediction-markets/meteo/route')
    await GET(
      new NextRequest(
        'http://localhost/api/v1/prediction-markets/meteo?question=q&latitude=40.7&longitude=-74.0&include_meteostat=true&meteostat_start=2026-04-01&meteostat_end=2026-04-10',
      ),
    )

    expect(mocks.buildMeteoPricingReportFromProviders).toHaveBeenCalledWith(
      expect.objectContaining({
        includeMeteostat: true,
        meteostatStart: '2026-04-01',
        meteostatEnd: '2026-04-10',
      }),
    )
  })

  it('derives meteo resolution inputs from a polymarket snapshot via the canonical quote-event bridge', async () => {
    mocks.buildMeteoPricingReportFromProviders.mockResolvedValue({
      spec: {
        question: 'q',
        city: 'Singapore',
        countryOrRegion: null,
        marketDate: '2026-04-22',
        kind: 'high',
        unit: 'c',
        bins: [],
      },
      forecastPoints: [],
      report: {
        mean: 33.4,
        stddev: 0.9,
        unit: 'c',
        bins: [],
        opportunities: [],
        marketSnapshot: { pricedBinCount: 0, yesPriceSum: null, overround: null },
        provenance: { providerCount: 0, providers: [], contributions: [] },
      },
    })
    mocks.toPolymarketQuoteMarketEvent.mockReturnValue({
      event_id: 'evt-1',
      ts: '2026-04-21T23:00:00.000Z',
      venue: 'polymarket',
      market_id: 'mkt-singapore',
      event_type: 'quote',
      best_bid: 0.41,
      best_ask: 0.43,
      last_trade_price: 0.42,
      bid_size: 120,
      ask_size: 90,
      quote_age_ms: 500,
    })

    const polymarketSnapshot = {
      venue: 'polymarket',
      market: {
        venue: 'polymarket',
        venue_type: 'execution-equivalent',
        market_id: 'mkt-singapore',
        question: 'Highest temperature in Singapore on April 22?',
        outcomes: ['Yes', 'No'],
        active: true,
        closed: false,
        accepting_orders: true,
        restricted: false,
        liquidity_usd: 10000,
        volume_usd: 50000,
        volume_24h_usd: 1000,
        best_bid: 0.41,
        best_ask: 0.43,
        last_trade_price: 0.42,
        tick_size: 0.01,
        min_order_size: 5,
        is_binary_yes_no: true,
        source_urls: ['https://example.com/market'],
      },
      captured_at: '2026-04-21T23:00:00.500Z',
      yes_outcome_index: 0,
      yes_token_id: 'token-yes',
      yes_price: 0.42,
      no_price: 0.58,
      midpoint_yes: 0.42,
      best_bid_yes: 0.41,
      best_ask_yes: 0.43,
      spread_bps: 200,
      book: {
        token_id: 'token-yes',
        market_condition_id: 'cond-123',
        fetched_at: '2026-04-21T23:00:00.000Z',
        best_bid: 0.41,
        best_ask: 0.43,
        last_trade_price: 0.42,
        tick_size: 0.01,
        min_order_size: 5,
        bids: [{ price: 0.41, size: 120 }],
        asks: [{ price: 0.43, size: 90 }],
        depth_near_touch: 210,
      },
      history: [],
      source_urls: ['https://example.com/market', 'https://example.com/book'],
      event: {
        title: 'Highest temperature in Singapore on April 22?',
        description: 'Recorded at Singapore Changi Airport Station in degrees Celsius.',
        rules: 'Temperatures measured to whole degrees Celsius.',
        resolution_source: 'https://www.wunderground.com/history/daily/sg/singapore/WSSS',
      },
    }
    const snapshotJson = encodeURIComponent(JSON.stringify(polymarketSnapshot))

    const { GET } = await import('@/app/api/v1/prediction-markets/meteo/route')
    await GET(
      new NextRequest(
        `http://localhost/api/v1/prediction-markets/meteo?question=q&latitude=1.35&longitude=103.99&snapshot_json=${snapshotJson}`,
      ),
    )

    expect(mocks.toPolymarketQuoteMarketEvent).toHaveBeenCalledWith(expect.objectContaining({
      venue: 'polymarket',
      market: expect.objectContaining({ market_id: 'mkt-singapore' }),
      captured_at: '2026-04-21T23:00:00.500Z',
    }))
    expect(mocks.extractMeteoResolutionSource).toHaveBeenCalledWith({
      question: 'q',
      spec: expect.objectContaining({ city: 'Singapore', kind: 'high' }),
      resolutionSource: 'https://www.wunderground.com/history/daily/sg/singapore/WSSS',
      description: 'Recorded at Singapore Changi Airport Station in degrees Celsius.',
      rules: 'Temperatures measured to whole degrees Celsius.',
      polymarketEvent: expect.objectContaining({
        title: 'Highest temperature in Singapore on April 22?',
        description: 'Recorded at Singapore Changi Airport Station in degrees Celsius.',
        rules: 'Temperatures measured to whole degrees Celsius.',
        resolution_source: 'https://www.wunderground.com/history/daily/sg/singapore/WSSS',
        market_id: 'mkt-singapore',
        quote_event: expect.objectContaining({
          event_id: 'evt-1',
          market_id: 'mkt-singapore',
          quote_age_ms: 500,
        }),
      }),
    })
    expect(mocks.buildMeteoStationMetadata).toHaveBeenCalledWith(expect.objectContaining({
      resolutionSource: 'https://www.wunderground.com/history/daily/sg/singapore/WSSS',
      polymarketEvent: expect.objectContaining({
        market_id: 'mkt-singapore',
        quote_event: expect.objectContaining({ event_id: 'evt-1' }),
      }),
    }))
    expect(mocks.analyzeMeteoResolutionSource).toHaveBeenCalledWith(expect.objectContaining({
      resolutionSource: 'https://www.wunderground.com/history/daily/sg/singapore/WSSS',
      polymarketEvent: expect.objectContaining({
        market_id: 'mkt-singapore',
        quote_event: expect.objectContaining({ quote_age_ms: 500 }),
      }),
    }))
  })

  it('optionally adds execution candidates anomalies and summary when include_execution is enabled', async () => {
    mocks.buildMeteoPricingReportFromProviders.mockResolvedValue({
      spec: {
        question: 'q',
        city: 'Los Angeles',
        countryOrRegion: 'CA',
        marketDate: '2026-04-21',
        kind: 'high',
        unit: 'f',
        bins: [{ label: '70+F', unit: 'f', lower: { value: 70, inclusive: true }, upper: null }],
      },
      forecastPoints: [{ provider: 'open-meteo:ecmwf', mean: 68.8, stddev: 1.4, weight: 1 }],
      report: {
        mean: 68.8,
        stddev: 1.4,
        unit: 'f',
        bins: [{
          label: '70+F',
          probability: 0.29,
          fairYesPrice: 0.29,
          fairNoPrice: 0.71,
          marketYesPrice: 0.09,
          marketNoPrice: 0.91,
          edge: 0.2,
          yesEdge: 0.2,
          noEdge: -0.2,
          expectedValueYes: 0.2,
          expectedValueNo: -0.2,
          expectedRoiYes: 2.2222,
          expectedRoiNo: -0.2198,
          recommendedSide: 'yes',
        }],
        opportunities: [{
          label: '70+F',
          side: 'yes',
          edge: 0.2,
          expectedValue: 0.2,
          expectedRoi: 2.2222,
          fairPrice: 0.29,
          marketPrice: 0.09,
        }],
        marketSnapshot: { pricedBinCount: 1, yesPriceSum: 0.09, overround: -0.91 },
        provenance: { providerCount: 1, providers: ['open-meteo:ecmwf'], contributions: [] },
      },
    })
    mocks.buildMeteoExecutionCandidates.mockReturnValue([{ label: '70+F', side: 'yes', edge: 0.2, edgeBps: 2000, tradeable: true, confidence: 'high', priority: 'high', marketPrice: 0.09, fairPrice: 0.29, expectedValue: 0.2, expectedRoi: 2.2222, maxEntryPrice: 0.29, noTradeAbove: 0.29, reasonCodes: ['raw_edge'] }])
    mocks.detectMeteoMarketAnomalies.mockReturnValue([{ type: 'adjacent_gap', label: '66-67F|68-69F', severity: 'medium', details: 'Adjacent bins invert market pricing.' }])
    mocks.buildMeteoExecutionSummary.mockReturnValue({ candidateCount: 1, tradeableCount: 1, highPriorityCount: 1, anomalyCount: 1 })

    const { GET } = await import('@/app/api/v1/prediction-markets/meteo/route')
    const response = await GET(
      new NextRequest('http://localhost/api/v1/prediction-markets/meteo?question=q&latitude=34.05&longitude=-118.25&include_execution=true&min_edge_bps=1500'),
    )
    const body = await response.json()

    expect(mocks.buildMeteoExecutionCandidates).toHaveBeenCalledWith({
      report: expect.objectContaining({ mean: 68.8, unit: 'f' }),
      forecastPoints: [{ provider: 'open-meteo:ecmwf', mean: 68.8, stddev: 1.4, weight: 1 }],
      minEdgeBps: 1500,
    })
    expect(mocks.detectMeteoMarketAnomalies).toHaveBeenCalledWith(expect.objectContaining({ mean: 68.8, unit: 'f' }))
    expect(mocks.buildMeteoExecutionSummary).toHaveBeenCalledWith({
      candidates: [{ label: '70+F', side: 'yes', edge: 0.2, edgeBps: 2000, tradeable: true, confidence: 'high', priority: 'high', marketPrice: 0.09, fairPrice: 0.29, expectedValue: 0.2, expectedRoi: 2.2222, maxEntryPrice: 0.29, noTradeAbove: 0.29, reasonCodes: ['raw_edge'] }],
      anomalies: [{ type: 'adjacent_gap', label: '66-67F|68-69F', severity: 'medium', details: 'Adjacent bins invert market pricing.' }],
    })
    expect(body).toMatchObject({
      execution_candidates: [{ label: '70+F', side: 'yes', tradeable: true, edgeBps: 2000 }],
      anomalies: [{ type: 'adjacent_gap', severity: 'medium' }],
      execution_summary: { candidateCount: 1, tradeableCount: 1, highPriorityCount: 1, anomalyCount: 1 },
    })
  })
})
