import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}))

import { logger } from '@/lib/logger'
import { evaluateCrossVenuePair } from '@/lib/prediction-markets/cross-venue'
import { PredictionMarketsError } from '@/lib/prediction-markets/errors'
import { buildKalshiSnapshot } from '@/lib/prediction-markets/kalshi'
import { buildPolymarketSnapshot } from '@/lib/prediction-markets/polymarket'
import { evaluatePredictionMarketRuntimeGuard } from '@/lib/prediction-markets/runtime-guard'
import {
  marketDescriptorSchema,
  marketSnapshotSchema,
  type MarketDescriptor,
  type MarketSnapshot,
} from '@/lib/prediction-markets/schemas'
import {
  getVenueBudgetsContract,
  getVenueCapabilitiesContract,
  getVenueHealthSnapshotContract,
} from '@/lib/prediction-markets/venue-ops'

const mockedLogger = vi.mocked(logger)

function jsonResponse(payload: unknown, init: { ok?: boolean; status?: number; statusText?: string } = {}) {
  return Promise.resolve({
    ok: init.ok ?? true,
    status: init.status ?? 200,
    statusText: init.statusText ?? 'OK',
    json: async () => payload,
  } as Response)
}

function networkError(message: string) {
  const error = new Error(message)
  error.name = 'NetworkError'
  return error
}

function makePolymarketMarketPayload() {
  return [{
    id: 'poly-hardening-test',
    slug: 'poly-hardening-test',
    question: 'Will the hardening snapshot stay stable?',
    description: 'Synthetic payload for successive network failure tests.',
    outcomes: '["Yes","No"]',
    outcomePrices: '["0.47","0.53"]',
    clobTokenIds: '["poly-hardening-yes","poly-hardening-no"]',
    events: [{ id: 'poly-event-hardening' }],
    active: true,
    closed: false,
    acceptingOrders: true,
    restricted: false,
    liquidityNum: 50000,
    volumeNum: 250000,
    volume24hrClob: 5000,
    bestBid: '0.46',
    bestAsk: '0.48',
    lastTradePrice: '0.47',
    orderPriceMinTickSize: '0.01',
    orderMinSize: '5',
    endDate: '2026-12-31T23:59:59.000Z',
  }]
}

function makeDescriptor(overrides: Partial<MarketDescriptor> = {}): MarketDescriptor {
  return marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: 'descriptor-hardening',
    slug: 'descriptor-hardening',
    question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
    outcomes: ['Yes', 'No'],
    active: true,
    closed: false,
    accepting_orders: true,
    restricted: false,
    liquidity_usd: 100_000,
    volume_usd: 1_000_000,
    volume_24h_usd: 100_000,
    best_bid: null,
    best_ask: null,
    last_trade_price: null,
    tick_size: 0.01,
    min_order_size: 5,
    is_binary_yes_no: true,
    end_at: '2026-12-31T23:59:59.000Z',
    source_urls: ['https://example.com/descriptor-hardening'],
    ...overrides,
  })
}

function makeSnapshot(market: MarketDescriptor, midpointYes: number): MarketSnapshot {
  return marketSnapshotSchema.parse({
    venue: market.venue,
    market,
    captured_at: '2026-04-08T00:00:00.000Z',
    yes_outcome_index: 0,
    yes_token_id: `${market.market_id}:yes`,
    yes_price: midpointYes,
    no_price: Number((1 - midpointYes).toFixed(6)),
    midpoint_yes: midpointYes,
    best_bid_yes: null,
    best_ask_yes: null,
    spread_bps: null,
    book: null,
    history: [],
    source_urls: market.source_urls,
  })
}

describe('prediction markets system hardening', () => {
  const originalEnv = process.env
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    process.env = { ...originalEnv }
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-08T00:00:00.000Z'))
    mockedLogger.warn.mockReset()
    mockedLogger.error.mockReset()
    mockedLogger.info.mockReset()
    mockedLogger.debug.mockReset()
  })

  afterEach(() => {
    process.env = originalEnv
    globalThis.fetch = originalFetch
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('survives successive secondary network failures and returns a metadata-only Polymarket snapshot', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => jsonResponse(makePolymarketMarketPayload()))
      .mockRejectedValueOnce(networkError('orderbook offline'))
      .mockRejectedValueOnce(networkError('history offline'))
    globalThis.fetch = fetchMock as typeof fetch

    const snapshot = await buildPolymarketSnapshot({ marketId: 'poly-hardening-test', historyLimit: 20 })

    expect(snapshot.market.market_id).toBe('poly-hardening-test')
    expect(snapshot.book).toBeNull()
    expect(snapshot.history).toEqual([])
    expect(snapshot.best_bid_yes).toBe(0.46)
    expect(snapshot.best_ask_yes).toBe(0.48)
    expect(snapshot.midpoint_yes).toBe(0.47)
    expect(snapshot.yes_price).toBe(0.47)
    expect(snapshot.spread_bps).toBe(200)
    expect(mockedLogger.warn).toHaveBeenCalledTimes(2)
  })

  it('raises a clean PredictionMarketsError when Kalshi returns an invalid market payload', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => jsonResponse({}))
    globalThis.fetch = fetchMock as typeof fetch

    await expect(buildKalshiSnapshot({ marketId: 'KXINVALID' })).rejects.toMatchObject({
      name: 'PredictionMarketsError',
      status: 502,
      code: 'invalid_market_payload',
      message: 'Kalshi market payload missing market object',
    } satisfies Partial<PredictionMarketsError>)
  })

  it('keeps cross-venue arbitrage evaluation stable when only midpoint prices are available', () => {
    const polymarket = makeDescriptor({
      venue: 'polymarket',
      market_id: 'poly-midpoint-only',
      slug: 'poly-midpoint-only',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      source_urls: ['https://example.com/poly-midpoint-only'],
    })
    const kalshi = makeDescriptor({
      venue: 'kalshi',
      market_id: 'kalshi-midpoint-only',
      slug: 'kalshi-midpoint-only',
      question: 'Will Bitcoin be above 100000 on 2026-12-31?',
      source_urls: ['https://example.com/kalshi-midpoint-only'],
    })

    const evaluation = evaluateCrossVenuePair({
      left: polymarket,
      right: kalshi,
      leftSnapshot: makeSnapshot(polymarket, 0.4),
      rightSnapshot: makeSnapshot(kalshi, 0.58),
    })

    expect(evaluation.compatible).toBe(true)
    expect(evaluation.arbitrage_candidate).not.toBeNull()
    expect(evaluation.arbitrage_candidate?.executable).toBe(false)
    expect(evaluation.arbitrage_candidate?.gross_spread_bps).toBe(1800)
    expect(evaluation.arbitrage_candidate?.reasons).toContain('insufficient_orderbook_for_executable_spread')
  })

  it('blocks live mode on degraded venue health and keeps the no-retry-loop fallback explicit', () => {
    const result = evaluatePredictionMarketRuntimeGuard({
      venue: 'kalshi',
      mode: 'live',
      capabilities: {
        ...getVenueCapabilitiesContract('kalshi'),
        supports_paper_mode: true,
        supports_execution: true,
        supports_positions: true,
        automation_constraints: [],
      },
      health: {
        ...getVenueHealthSnapshotContract('kalshi'),
        api_status: 'degraded',
        stream_status: 'degraded',
        degraded_mode: 'degraded',
        health_score: 0.7,
        incident_flags: ['consecutive_http_failures'],
      },
      budgets: {
        ...getVenueBudgetsContract('kalshi'),
        max_retries: 0,
      },
    })

    expect(result.verdict).toBe('blocked')
    expect(result.reasons).toEqual(
      expect.arrayContaining([
        'venue health has incident flags: consecutive_http_failures',
        'budgets exceed the conservative envelope for live mode',
      ]),
    )
    expect(result.fallback_actions).toEqual(
      expect.arrayContaining([
        'avoid_retry_loops',
        'prefer_cached_snapshots',
        'reduce_polling_cadence',
        'downgrade_mode_to_shadow',
      ]),
    )
  })
})
