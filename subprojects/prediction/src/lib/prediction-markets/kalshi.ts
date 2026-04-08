import { logger } from '@/lib/logger'
import { PredictionMarketsError } from '@/lib/prediction-markets/errors'
import {
  marketDescriptorSchema,
  marketSnapshotSchema,
  PREDICTION_MARKETS_SCHEMA_VERSION,
} from '@/lib/prediction-markets/schemas'
import { z } from 'zod'

type RawJson = Record<string, unknown>

export type KalshiListMarketsInput = {
  limit?: number
  search?: string
  active?: boolean
  closed?: boolean
}

export type KalshiGetMarketInput = {
  marketId?: string
  slug?: string
}

export type KalshiBuildSnapshotInput = KalshiGetMarketInput & {
  historyLimit?: number
}

const kalshiMarketDescriptorSchema = marketDescriptorSchema
  .omit({ venue: true })
  .extend({ venue: z.literal('kalshi') })

const kalshiMarketSnapshotSchema = marketSnapshotSchema
  .omit({ venue: true, market: true })
  .extend({
    venue: z.literal('kalshi'),
    market: kalshiMarketDescriptorSchema,
  })

export type KalshiMarketDescriptor = z.infer<typeof kalshiMarketDescriptorSchema>
export type KalshiMarketSnapshot = z.infer<typeof kalshiMarketSnapshotSchema>

const KALSHI_VENUE = 'kalshi'
const DEFAULT_BASE_URL = 'https://api.elections.kalshi.com/trade-api/v2'
const DEFAULT_TIMEOUT_MS = 8_000
const DEFAULT_HISTORY_LIMIT = 120
const DEFAULT_HISTORY_INTERVAL_SECONDS = 60
const DEFAULT_ORDERBOOK_DEPTH = 50
const MAX_LIMIT = 1_000
const MAX_HISTORY_LIMIT = 500
const MAX_SEARCH_PAGES = 5
const KALSHI_DEFAULT_BUDGETS = {
  venue: KALSHI_VENUE,
  default_list_limit: 20,
  max_list_limit: MAX_LIMIT,
  default_history_limit: DEFAULT_HISTORY_LIMIT,
  max_history_limit: MAX_HISTORY_LIMIT,
  timeout_ms: DEFAULT_TIMEOUT_MS,
  max_http_requests_per_snapshot: 3,
  max_search_pages: MAX_SEARCH_PAGES,
  max_parallel_requests: 2,
  conservative: true,
} as const

function getConfig() {
  const timeoutMs = Number(process.env.PREDICTION_MARKETS_HTTP_TIMEOUT_MS || DEFAULT_TIMEOUT_MS)

  return {
    baseUrl: (process.env.PREDICTION_MARKETS_KALSHI_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, ''),
    timeoutMs: Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : DEFAULT_TIMEOUT_MS,
  }
}

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : undefined
}

function toIso(value: unknown): string | undefined {
  return asString(value)
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function roundPrice(value: number): number {
  return Number(value.toFixed(6))
}

function normalizeText(value: string): string {
  return value.trim().toLowerCase()
}

function uniqueStrings(values: Array<string | undefined>): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value && value.length > 0)))]
}

async function fetchJson<T>(url: string): Promise<T> {
  const { timeoutMs } = getConfig()
  const response = await fetch(url, {
    headers: { Accept: 'application/json' },
    signal: AbortSignal.timeout(timeoutMs),
    cache: 'no-store',
  })

  if (!response.ok) {
    if (response.status === 404) {
      throw new PredictionMarketsError('Kalshi market not found', {
        status: 404,
        code: 'market_not_found',
      })
    }

    throw new PredictionMarketsError(
      `Kalshi request failed: ${response.status} ${response.statusText}`,
      {
        status: response.status,
        code: 'kalshi_request_failed',
      },
    )
  }

  return response.json() as Promise<T>
}

function isBinaryMarket(raw: RawJson): boolean {
  return asString(raw.market_type) === 'binary'
}

function isActiveStatus(status: string | undefined): boolean {
  return status === 'active' || status === 'open'
}

function isClosedStatus(status: string | undefined): boolean {
  return status === 'closed' || status === 'settled' || status === 'determined'
}

function resolveStatusFilter(input: KalshiListMarketsInput): string | undefined {
  if (input.closed === true && input.active !== true) {
    return 'closed,settled,determined'
  }

  if (input.active === false && input.closed === false) {
    return undefined
  }

  if (input.active === true || input.closed !== true) {
    return 'open'
  }

  return undefined
}

function computeNotionalVolume(contractsValue: unknown, contractValue: unknown): number | null {
  const contracts = asNumber(contractsValue)
  if (contracts == null) return null
  const notional = asNumber(contractValue) ?? 1
  return Number((contracts * notional).toFixed(4))
}

function extractTickSize(raw: RawJson): number | null {
  const priceRanges = Array.isArray(raw.price_ranges) ? raw.price_ranges : []
  const explicitStep = priceRanges
    .map((entry) => asNumber((entry as RawJson).step))
    .find((value) => value != null)

  if (explicitStep != null) return explicitStep

  const rawTickSize = asNumber(raw.tick_size)
  if (rawTickSize == null) return null

  const levelStructure = asString(raw.price_level_structure)
  if (levelStructure === 'deci_cent') return rawTickSize / 1_000

  const units = asString(raw.response_price_units)
  if (units === 'usd_cent') return rawTickSize / 100

  return rawTickSize
}

function buildDescription(raw: RawJson): string | undefined {
  const parts = [
    asString(raw.rules_primary),
    asString(raw.rules_secondary),
  ].filter((value): value is string => Boolean(value))

  if (parts.length > 0) return parts.join('\n\n')

  const yesSubtitle = asString(raw.yes_sub_title)
  return yesSubtitle && yesSubtitle !== asString(raw.title) ? yesSubtitle : undefined
}

function normalizeMarket(raw: RawJson, sourceUrl: string): KalshiMarketDescriptor {
  if (!isBinaryMarket(raw)) {
    throw new PredictionMarketsError('Kalshi adapter only supports binary markets', {
      status: 422,
      code: 'unsupported_market_type',
    })
  }

  const status = asString(raw.status)
  const ticker = asString(raw.ticker)

  if (!ticker) {
    throw new PredictionMarketsError('Kalshi market response is missing ticker', {
      status: 502,
      code: 'invalid_market_payload',
    })
  }

  return kalshiMarketDescriptorSchema.parse({
    schema_version: PREDICTION_MARKETS_SCHEMA_VERSION,
    venue: KALSHI_VENUE,
    venue_type: 'execution-equivalent',
    market_id: ticker,
    event_id: asString(raw.event_ticker),
    slug: ticker,
    question: asString(raw.title) || ticker,
    description: buildDescription(raw),
    outcomes: ['Yes', 'No'],
    start_at: toIso(raw.open_time),
    end_at: toIso(raw.close_time ?? raw.expiration_time),
    active: isActiveStatus(status),
    closed: isClosedStatus(status),
    accepting_orders: isActiveStatus(status),
    liquidity_usd: asNumber(raw.liquidity_dollars),
    volume_usd: computeNotionalVolume(raw.volume_fp, raw.notional_value_dollars),
    volume_24h_usd: computeNotionalVolume(raw.volume_24h_fp, raw.notional_value_dollars),
    best_bid: asNumber(raw.yes_bid_dollars),
    best_ask: asNumber(raw.yes_ask_dollars),
    last_trade_price: asNumber(raw.last_price_dollars),
    tick_size: extractTickSize(raw),
    is_binary_yes_no: true,
    source_urls: [sourceUrl],
  })
}

function parseOrderbookLevels(
  value: unknown,
  transformPrice?: (value: number) => number | null,
): Array<{ price: number; size: number }> {
  if (!Array.isArray(value)) return []

  return value
    .map((entry) => {
      if (!Array.isArray(entry) || entry.length < 2) return null
      const price = asNumber(entry[0])
      const size = asNumber(entry[1])
      if (price == null || size == null) return null
      const normalizedPrice = transformPrice ? transformPrice(price) : price
      if (normalizedPrice == null || normalizedPrice < 0 || normalizedPrice > 1) return null
      return {
        price: roundPrice(normalizedPrice),
        size,
      }
    })
    .filter((level): level is { price: number; size: number } => level != null)
}

function computeDepthNearTouch(
  bids: Array<{ price: number; size: number }>,
  asks: Array<{ price: number; size: number }>,
  bestBid: number | null,
  bestAsk: number | null,
  tickSize: number | null,
): number | null {
  if (bestBid == null || bestAsk == null || tickSize == null || tickSize <= 0) return null
  const bidBand = bestBid - (tickSize * 2)
  const askBand = bestAsk + (tickSize * 2)

  const bidDepth = bids
    .filter((level) => level.price >= bidBand)
    .reduce((sum, level) => sum + level.size, 0)
  const askDepth = asks
    .filter((level) => level.price <= askBand)
    .reduce((sum, level) => sum + level.size, 0)

  return bidDepth + askDepth
}

function extractCandlestickClose(raw: RawJson): number | null {
  const price = raw.price as RawJson | undefined
  if (!price) return null

  const closeDollars = asNumber(price.close_dollars)
  if (closeDollars != null) return closeDollars

  const closeCents = asNumber(price.close)
  if (closeCents != null) return closeCents / 100

  return null
}

function parseCandlestickHistory(value: unknown): KalshiMarketSnapshot['history'] {
  if (!Array.isArray(value)) return []

  return value
    .map((entry) => {
      const raw = entry as RawJson
      const timestamp = asNumber(raw.end_period_ts)
      const price = extractCandlestickClose(raw)
      if (timestamp == null || price == null || price < 0 || price > 1) return null
      return {
        timestamp,
        price: roundPrice(price),
      }
    })
    .filter((point): point is { timestamp: number; price: number } => point != null)
}

function matchesSearch(market: KalshiMarketDescriptor, query: string): boolean {
  const search = normalizeText(query)
  return [
    market.market_id,
    market.slug,
    market.question,
    market.description,
  ]
    .filter((value): value is string => Boolean(value))
    .some((value) => normalizeText(value).includes(search))
}

function buildMarketsUrl(params: URLSearchParams): string {
  const { baseUrl } = getConfig()
  return `${baseUrl}/markets?${params.toString()}`
}

function isValidUrl(value: string): boolean {
  try {
    // Read-only validation: confirm the configured endpoint is syntactically valid.
    new URL(value)
    return true
  } catch {
    return false
  }
}

export function getKalshiVenueCapabilities() {
  return {
    venue: 'kalshi' as const,
    label: 'Kalshi',
    venue_type: 'execution-equivalent' as const,
    market_shape: 'binary_only' as const,
    supports: {
      list_markets: true,
      get_market: true,
      build_snapshot: true,
      orderbook: true,
      history: true,
      search: true,
      replay: true,
    },
    limits: {
      binary_only: true,
      max_list_limit: KALSHI_DEFAULT_BUDGETS.max_list_limit,
      max_history_limit: KALSHI_DEFAULT_BUDGETS.max_history_limit,
    },
    notes: [
      'Binary contracts only; adapter normalizes the yes/no legs into a common snapshot shape.',
      'Snapshot generation is read-only and conservative.',
    ],
  }
}

export function getKalshiVenueHealthSnapshot() {
  const { baseUrl } = getConfig()
  const configuredEndpoints = [baseUrl]
  const invalidEndpoints = configuredEndpoints.filter((endpoint) => !isValidUrl(endpoint))

  return {
    venue: 'kalshi' as const,
    status: invalidEndpoints.length === 0 ? 'ready' as const : 'degraded' as const,
    checked_at: new Date().toISOString(),
    network_checked: false as const,
    read_only: true as const,
    configured_endpoints: configuredEndpoints,
    reasons: invalidEndpoints.length === 0
      ? []
      : ['configured endpoint failed URL validation'],
  }
}

export function getKalshiDefaultBudgets() {
  return { ...KALSHI_DEFAULT_BUDGETS }
}

export async function listKalshiMarkets(
  input: KalshiListMarketsInput = {},
): Promise<KalshiMarketDescriptor[]> {
  const limit = clamp(input.limit ?? 20, 1, MAX_LIMIT)
  const pageSize = clamp(input.search ? Math.max(limit * 3, 100) : limit, 1, MAX_LIMIT)
  const status = resolveStatusFilter(input)

  const results: KalshiMarketDescriptor[] = []
  let cursor: string | undefined
  let pagesFetched = 0

  while (results.length < limit && pagesFetched < MAX_SEARCH_PAGES) {
    const searchParams = new URLSearchParams({
      limit: String(pageSize),
      mve_filter: 'exclude',
    })

    if (status) searchParams.set('status', status)
    if (cursor) searchParams.set('cursor', cursor)

    const url = buildMarketsUrl(searchParams)
    const payload = await fetchJson<{ markets?: RawJson[]; cursor?: string | null }>(url)
    const rawMarkets = Array.isArray(payload.markets) ? payload.markets : []

    const normalized = rawMarkets
      .filter((market) => isBinaryMarket(market))
      .map((market) => normalizeMarket(market, url))
      .filter((market) => (input.search ? matchesSearch(market, input.search) : true))

    results.push(...normalized)
    cursor = asString(payload.cursor)
    pagesFetched += 1

    if (!cursor) break
    if (!input.search && results.length >= limit) break
  }

  return results.slice(0, limit)
}

export async function getKalshiMarket(
  input: KalshiGetMarketInput,
): Promise<{ raw: RawJson; market: KalshiMarketDescriptor }> {
  const requestedId = asString(input.marketId) || asString(input.slug)
  if (!requestedId) {
    throw new PredictionMarketsError('marketId or slug is required for Kalshi lookup', {
      status: 400,
      code: 'invalid_request',
    })
  }

  const candidates = uniqueStrings([requestedId, requestedId.toUpperCase()])
  let notFound: PredictionMarketsError | null = null

  for (const candidate of candidates) {
    const { baseUrl } = getConfig()
    const url = `${baseUrl}/markets/${encodeURIComponent(candidate)}`

    try {
      const payload = await fetchJson<{ market?: RawJson }>(url)
      const raw = payload.market
      if (!raw || typeof raw !== 'object') {
        throw new PredictionMarketsError('Kalshi market payload missing market object', {
          status: 502,
          code: 'invalid_market_payload',
        })
      }

      return {
        raw,
        market: normalizeMarket(raw, url),
      }
    } catch (error) {
      if (error instanceof PredictionMarketsError && error.status === 404) {
        notFound = error
        continue
      }
      throw error
    }
  }

  throw notFound || new PredictionMarketsError('Kalshi market not found', {
    status: 404,
    code: 'market_not_found',
  })
}

export async function buildKalshiSnapshot(
  input: KalshiBuildSnapshotInput,
): Promise<KalshiMarketSnapshot> {
  const historyLimit = clamp(input.historyLimit ?? DEFAULT_HISTORY_LIMIT, 0, MAX_HISTORY_LIMIT)
  const { baseUrl } = getConfig()
  const { raw, market } = await getKalshiMarket(input)
  const sourceUrls = [...market.source_urls]

  let book: KalshiMarketSnapshot['book'] = null
  let bestBidYes = market.best_bid ?? null
  let bestAskYes = market.best_ask ?? null
  let midpointYes: number | null = null
  let yesPrice = asNumber(raw.last_price_dollars) ?? market.last_trade_price ?? null
  let history: KalshiMarketSnapshot['history'] = []

  const orderbookUrl = `${baseUrl}/markets/${encodeURIComponent(market.market_id)}/orderbook?depth=${DEFAULT_ORDERBOOK_DEPTH}`
  sourceUrls.push(orderbookUrl)

  try {
    const rawOrderbook = await fetchJson<{
      orderbook_fp?: {
        yes_dollars?: unknown
        no_dollars?: unknown
      }
    }>(orderbookUrl)

    const bids = parseOrderbookLevels(rawOrderbook.orderbook_fp?.yes_dollars)
      .sort((left, right) => right.price - left.price)
    const asks = parseOrderbookLevels(
      rawOrderbook.orderbook_fp?.no_dollars,
      (price) => roundPrice(1 - price),
    ).sort((left, right) => left.price - right.price)

    bestBidYes = bids[0]?.price ?? bestBidYes
    bestAskYes = asks[0]?.price ?? bestAskYes
    midpointYes = bestBidYes != null && bestAskYes != null
      ? roundPrice((bestBidYes + bestAskYes) / 2)
      : null
    yesPrice = midpointYes ?? yesPrice

    book = {
      token_id: market.market_id,
      market_condition_id: market.event_id,
      fetched_at: new Date().toISOString(),
      best_bid: bestBidYes,
      best_ask: bestAskYes,
      last_trade_price: asNumber(raw.last_price_dollars),
      tick_size: market.tick_size ?? null,
      min_order_size: market.min_order_size ?? null,
      bids,
      asks,
      depth_near_touch: computeDepthNearTouch(
        bids,
        asks,
        bestBidYes,
        bestAskYes,
        market.tick_size ?? null,
      ),
    }
  } catch (error) {
    logger.warn({ err: error, marketId: market.market_id }, 'Failed to fetch Kalshi orderbook')
  }

  if (historyLimit > 0) {
    const endTs = Math.floor(Date.now() / 1_000)
    const startTs = Math.max(0, endTs - (historyLimit * DEFAULT_HISTORY_INTERVAL_SECONDS))
    const historyUrl = `${baseUrl}/markets/candlesticks?market_tickers=${encodeURIComponent(market.market_id)}&start_ts=${startTs}&end_ts=${endTs}&period_interval=${DEFAULT_HISTORY_INTERVAL_SECONDS}`
    sourceUrls.push(historyUrl)

    try {
      const rawHistory = await fetchJson<{
        markets?: Array<{
          market_ticker?: string
          candlesticks?: unknown[]
        }>
      }>(historyUrl)

      const entry = Array.isArray(rawHistory.markets)
        ? rawHistory.markets.find((marketEntry) => asString(marketEntry.market_ticker) === market.market_id)
        : undefined

      history = parseCandlestickHistory(entry?.candlesticks).slice(-historyLimit)
      if (yesPrice == null && history.length > 0) {
        yesPrice = history[history.length - 1].price
      }
    } catch (error) {
      logger.warn({ err: error, marketId: market.market_id }, 'Failed to fetch Kalshi candlesticks')
    }
  }

  if (midpointYes == null && bestBidYes != null && bestAskYes != null) {
    midpointYes = roundPrice((bestBidYes + bestAskYes) / 2)
  }

  if (yesPrice == null) {
    yesPrice = midpointYes ?? bestBidYes ?? bestAskYes ?? null
  }

  const noPrice = yesPrice == null ? null : roundPrice(1 - yesPrice)
  const spreadBps = bestBidYes != null && bestAskYes != null
    ? Number(((bestAskYes - bestBidYes) * 10_000).toFixed(2))
    : null

  return kalshiMarketSnapshotSchema.parse({
    schema_version: PREDICTION_MARKETS_SCHEMA_VERSION,
    venue: KALSHI_VENUE,
    market,
    captured_at: new Date().toISOString(),
    yes_outcome_index: 0,
    yes_token_id: `${market.market_id}:yes`,
    yes_price: yesPrice,
    no_price: noPrice,
    midpoint_yes: midpointYes,
    best_bid_yes: bestBidYes,
    best_ask_yes: bestAskYes,
    spread_bps: spreadBps,
    book,
    history,
    source_urls: uniqueStrings(sourceUrls),
  })
}
