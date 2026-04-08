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
import { buildKalshiSnapshot } from '@/lib/prediction-markets/kalshi'
import { buildPolymarketSnapshot } from '@/lib/prediction-markets/polymarket'
import { getVenueHealthSnapshotContract } from '@/lib/prediction-markets/venue-ops'

const mockedLogger = vi.mocked(logger)

function jsonResponse(payload: unknown, init: { ok?: boolean; status?: number; statusText?: string } = {}) {
  return Promise.resolve({
    ok: init.ok ?? true,
    status: init.status ?? 200,
    statusText: init.statusText ?? 'OK',
    json: async () => payload,
  } as Response)
}

function timeoutError(message: string) {
  const error = new Error(message)
  error.name = 'TimeoutError'
  return error
}

function makePolymarketMarketPayload() {
  return [{
    id: 'poly-network-test',
    slug: 'poly-network-test',
    question: 'Will the network guard test pass?',
    description: 'Synthetic market payload for degraded-mode tests.',
    outcomes: '["Yes","No"]',
    outcomePrices: '["0.45","0.55"]',
    clobTokenIds: '["poly-yes-token","poly-no-token"]',
    events: [{ id: 'poly-event-1' }],
    active: true,
    closed: false,
    acceptingOrders: true,
    restricted: false,
    liquidityNum: 100000,
    volumeNum: 800000,
    volume24hrClob: 10000,
    bestBid: '0.44',
    bestAsk: '0.46',
    lastTradePrice: '0.45',
    orderPriceMinTickSize: '0.01',
    orderMinSize: '5',
    endDate: '2026-12-31T23:59:59.000Z',
  }]
}

function makeKalshiMarketPayload() {
  return {
    market: {
      market_type: 'binary',
      ticker: 'KXNETWORK',
      event_ticker: 'KXEVENT',
      status: 'open',
      title: 'Will the network guard test pass on Kalshi?',
      rules_primary: 'Synthetic market payload for degraded-mode tests.',
      open_time: '2026-04-01T00:00:00.000Z',
      close_time: '2026-12-31T23:59:59.000Z',
      liquidity_dollars: 40000,
      volume_fp: 100000,
      volume_24h_fp: 8000,
      notional_value_dollars: 1,
      yes_bid_dollars: 0.4,
      yes_ask_dollars: 0.44,
      last_price_dollars: 0.42,
      tick_size: 1,
      response_price_units: 'usd_cent',
    },
  }
}

describe('prediction markets network guards', () => {
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

  it('propagates a hard timeout when Polymarket market metadata cannot be fetched', async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(timeoutError('metadata request timed out'))
    globalThis.fetch = fetchMock as typeof fetch

    await expect(buildPolymarketSnapshot({ marketId: 'poly-network-test' })).rejects.toThrow(
      'metadata request timed out',
    )
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('degrades a Polymarket snapshot when the orderbook times out but history remains available', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => jsonResponse(makePolymarketMarketPayload()))
      .mockRejectedValueOnce(timeoutError('orderbook request timed out'))
      .mockImplementationOnce(() => jsonResponse({
        history: [
          { t: 1712534400, p: 0.43 },
          { t: 1712538000, p: 0.45 },
        ],
      }))
    globalThis.fetch = fetchMock as typeof fetch

    const snapshot = await buildPolymarketSnapshot({ marketId: 'poly-network-test', historyLimit: 10 })

    expect(snapshot.book).toBeNull()
    expect(snapshot.history).toEqual([
      { timestamp: 1712534400, price: 0.43 },
      { timestamp: 1712538000, price: 0.45 },
    ])
    expect(snapshot.best_bid_yes).toBe(0.44)
    expect(snapshot.best_ask_yes).toBe(0.46)
    expect(snapshot.midpoint_yes).toBe(0.45)
    expect(snapshot.spread_bps).toBe(200)
    expect(snapshot.source_urls.some((url) => url.includes('/book?token_id='))).toBe(true)
    expect(snapshot.source_urls.some((url) => url.includes('/prices-history?market='))).toBe(true)
    expect(mockedLogger.warn).toHaveBeenCalledTimes(1)
  })

  it('tolerates partial Kalshi orderbook payloads and missing history by falling back to partial snapshot data', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => jsonResponse(makeKalshiMarketPayload()))
      .mockImplementationOnce(() => jsonResponse({
        orderbook_fp: {
          yes_dollars: [
            [0.4, 100],
            ['bad', 999],
          ],
          no_dollars: [
            [0.57, 80],
            [null, 20],
          ],
        },
      }))
      .mockRejectedValueOnce(new Error('candlesticks unavailable'))
    globalThis.fetch = fetchMock as typeof fetch

    const snapshot = await buildKalshiSnapshot({ marketId: 'KXNETWORK', historyLimit: 10 })

    expect(snapshot.book).not.toBeNull()
    expect(snapshot.book?.bids).toEqual([{ price: 0.4, size: 100 }])
    expect(snapshot.book?.asks).toEqual([{ price: 0.43, size: 80 }])
    expect(snapshot.best_bid_yes).toBe(0.4)
    expect(snapshot.best_ask_yes).toBe(0.43)
    expect(snapshot.midpoint_yes).toBe(0.415)
    expect(snapshot.yes_price).toBe(0.415)
    expect(snapshot.history).toEqual([])
    expect(mockedLogger.warn).toHaveBeenCalledTimes(1)
  })

  it.each([
    {
      venue: 'polymarket' as const,
      env: {
        PREDICTION_MARKETS_POLYMARKET_GAMMA_URL: 'not-a-valid-url',
      },
    },
    {
      venue: 'kalshi' as const,
      env: {
        PREDICTION_MARKETS_KALSHI_BASE_URL: 'still-not-a-valid-url',
      },
    },
  ])('marks $venue as degraded when configured endpoints are invalid', ({ venue, env }) => {
    process.env = { ...process.env, ...env }

    const contract = getVenueHealthSnapshotContract(venue)

    expect(contract.venue).toBe(venue)
    expect(contract.degraded_mode).toBe('degraded')
    expect(contract.api_status).toBe('degraded')
    expect(contract.health_score).toBe(0.65)
    expect(contract.incident_flags.length).toBeGreaterThan(0)
  })
})
