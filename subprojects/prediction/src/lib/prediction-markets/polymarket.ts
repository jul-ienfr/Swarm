import { logger } from '@/lib/logger'
import { PredictionMarketsError } from '@/lib/prediction-markets/errors'
import {
  type MarketDescriptor,
  type MarketSnapshot,
  marketDescriptorSchema,
  marketSnapshotSchema,
  PREDICTION_MARKETS_SCHEMA_VERSION,
} from '@/lib/prediction-markets/schemas'

type RawJson = Record<string, unknown>

type ListMarketsInput = {
  limit?: number
  search?: string
  active?: boolean
  closed?: boolean
}

type GetMarketInput = {
  marketId?: string
  slug?: string
}

type BuildSnapshotInput = GetMarketInput & {
  historyLimit?: number
}

const DEFAULT_GAMMA_URL = 'https://gamma-api.polymarket.com'
const DEFAULT_CLOB_URL = 'https://clob.polymarket.com'
const DEFAULT_TIMEOUT_MS = 8_000
const DEFAULT_HISTORY_LIMIT = 120
const POLYMARKET_VENUE = 'polymarket'
const POLYMARKET_DEFAULT_BUDGETS = {
  venue: POLYMARKET_VENUE,
  default_list_limit: 20,
  max_list_limit: 100,
  default_history_limit: DEFAULT_HISTORY_LIMIT,
  max_history_limit: 500,
  timeout_ms: DEFAULT_TIMEOUT_MS,
  max_http_requests_per_snapshot: 3,
  max_search_pages: 1,
  max_parallel_requests: 2,
  conservative: true,
} as const

function getConfig() {
  const timeoutMs = Number(process.env.PREDICTION_MARKETS_HTTP_TIMEOUT_MS || DEFAULT_TIMEOUT_MS)

  return {
    gammaUrl: (process.env.PREDICTION_MARKETS_POLYMARKET_GAMMA_URL || DEFAULT_GAMMA_URL).replace(/\/+$/, ''),
    clobUrl: (process.env.PREDICTION_MARKETS_POLYMARKET_CLOB_URL || DEFAULT_CLOB_URL).replace(/\/+$/, ''),
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
  return typeof value === 'string' && value.trim().length > 0 ? value : undefined
}

function parseStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
  }

  if (typeof value !== 'string' || value.trim().length === 0) return []

  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      : []
  } catch {
    return []
  }
}

function normalizeOutcomeLabel(value: string): string {
  return value.trim().toLowerCase()
}

function inferYesOutcomeIndex(outcomes: string[]): number {
  const explicitYesIndex = outcomes.findIndex((outcome) => normalizeOutcomeLabel(outcome) === 'yes')
  return explicitYesIndex >= 0 ? explicitYesIndex : 0
}

function isBinaryYesNoMarket(outcomes: string[]): boolean {
  if (outcomes.length !== 2) return false
  const normalized = outcomes.map(normalizeOutcomeLabel).sort()
  return normalized[0] === 'no' && normalized[1] === 'yes'
}

function safeFirst<T>(items: T[]): T | undefined {
  return items.length > 0 ? items[0] : undefined
}

async function fetchJson<T>(url: string): Promise<T> {
  const { timeoutMs } = getConfig()
  const response = await fetch(url, {
    headers: { Accept: 'application/json' },
    signal: AbortSignal.timeout(timeoutMs),
    cache: 'no-store',
  })

  if (!response.ok) {
    throw new Error(`Polymarket request failed: ${response.status} ${response.statusText}`)
  }

  return response.json() as Promise<T>
}

function normalizeMarket(raw: RawJson, sourceUrl: string): MarketDescriptor {
  const outcomes = parseStringArray(raw.outcomes)
  const outcomeTokenIds = parseStringArray(raw.clobTokenIds)
  const market: MarketDescriptor = {
    schema_version: PREDICTION_MARKETS_SCHEMA_VERSION,
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: String(raw.id ?? ''),
    event_id: Array.isArray(raw.events) ? asString((safeFirst(raw.events) as RawJson | undefined)?.id) : undefined,
    condition_id: asString(raw.conditionId),
    question_id: asString(raw.questionID),
    slug: asString(raw.slug),
    question: asString(raw.question) || 'Untitled market',
    description: asString(raw.description),
    outcomes,
    outcome_token_ids: outcomeTokenIds.length > 0 ? outcomeTokenIds : undefined,
    start_at: asString(raw.startDate),
    end_at: asString(raw.endDate),
    active: raw.active === true,
    closed: raw.closed === true,
    accepting_orders: raw.acceptingOrders === true,
    restricted: raw.restricted === true,
    liquidity_usd: asNumber(raw.liquidityNum ?? raw.liquidity),
    volume_usd: asNumber(raw.volumeNum ?? raw.volumeClob ?? raw.volume),
    volume_24h_usd: asNumber(raw.volume24hrClob ?? raw.volume24hr),
    best_bid: asNumber(raw.bestBid),
    best_ask: asNumber(raw.bestAsk),
    last_trade_price: asNumber(raw.lastTradePrice),
    tick_size: asNumber(raw.orderPriceMinTickSize),
    min_order_size: asNumber(raw.orderMinSize),
    is_binary_yes_no: isBinaryYesNoMarket(outcomes),
    source_urls: [sourceUrl],
  }

  return marketDescriptorSchema.parse(market)
}

function maxPrice(levels: Array<{ price: number }>): number | null {
  if (levels.length === 0) return null
  return Math.max(...levels.map((level) => level.price))
}

function minPrice(levels: Array<{ price: number }>): number | null {
  if (levels.length === 0) return null
  return Math.min(...levels.map((level) => level.price))
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

function buildHistoryUrl(tokenId: string): string {
  const { clobUrl } = getConfig()
  return `${clobUrl}/prices-history?market=${encodeURIComponent(tokenId)}&interval=max&fidelity=60`
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

export function getPolymarketVenueCapabilities() {
  return {
    venue: 'polymarket' as const,
    label: 'Polymarket',
    venue_type: 'execution-equivalent' as const,
    market_shape: 'binary_or_multi_outcome' as const,
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
      binary_only: false,
      max_list_limit: POLYMARKET_DEFAULT_BUDGETS.max_list_limit,
      max_history_limit: POLYMARKET_DEFAULT_BUDGETS.max_history_limit,
    },
    notes: [
      'Gamma metadata plus CLOB book/history are available through the adapter.',
      'Snapshot generation is read-only and conservative.',
    ],
  }
}

export function getPolymarketVenueHealthSnapshot() {
  const { gammaUrl, clobUrl } = getConfig()
  const configuredEndpoints = [gammaUrl, clobUrl]
  const invalidEndpoints = configuredEndpoints.filter((endpoint) => !isValidUrl(endpoint))

  return {
    venue: 'polymarket' as const,
    status: invalidEndpoints.length === 0 ? 'ready' as const : 'degraded' as const,
    checked_at: new Date().toISOString(),
    network_checked: false as const,
    read_only: true as const,
    configured_endpoints: configuredEndpoints,
    reasons: invalidEndpoints.length === 0
      ? []
      : ['one or more configured endpoints failed URL validation'],
  }
}

export function getPolymarketDefaultBudgets() {
  return { ...POLYMARKET_DEFAULT_BUDGETS }
}

export async function listPolymarketMarkets(input: ListMarketsInput = {}): Promise<MarketDescriptor[]> {
  const { gammaUrl } = getConfig()
  const limit = Math.max(1, Math.min(input.limit ?? 20, 100))
  const fetchLimit = input.search ? Math.max(limit * 3, 50) : limit

  const searchParams = new URLSearchParams({
    limit: String(fetchLimit),
    active: String(input.active ?? true),
    closed: String(input.closed ?? false),
  })

  const url = `${gammaUrl}/markets?${searchParams.toString()}`
  const rawMarkets = await fetchJson<RawJson[]>(url)
  let normalized = rawMarkets.map((market) => normalizeMarket(market, url))

  if (input.search) {
    const query = input.search.trim().toLowerCase()
    normalized = normalized.filter((market) =>
      market.question.toLowerCase().includes(query) ||
      (market.slug || '').toLowerCase().includes(query),
    )
  }

  return normalized.slice(0, limit)
}

export async function getPolymarketMarket(input: GetMarketInput): Promise<{ raw: RawJson; market: MarketDescriptor }> {
  const { gammaUrl } = getConfig()
  const searchParams = new URLSearchParams()

  if (input.marketId) searchParams.set('id', input.marketId)
  if (input.slug) searchParams.set('slug', input.slug)

  const url = `${gammaUrl}/markets?${searchParams.toString()}`
  const rawMarkets = await fetchJson<RawJson[]>(url)
  const raw = safeFirst(rawMarkets)

  if (!raw) {
    throw new PredictionMarketsError('Polymarket market not found', {
      status: 404,
      code: 'market_not_found',
    })
  }

  return {
    raw,
    market: normalizeMarket(raw, url),
  }
}

export async function buildPolymarketSnapshot(input: BuildSnapshotInput): Promise<MarketSnapshot> {
  const { clobUrl } = getConfig()
  const historyLimit = Math.max(0, Math.min(input.historyLimit ?? DEFAULT_HISTORY_LIMIT, 500))
  const { raw, market } = await getPolymarketMarket(input)

  const outcomes = market.outcomes
  const yesOutcomeIndex = inferYesOutcomeIndex(outcomes)
  const yesTokenId = market.outcome_token_ids?.[yesOutcomeIndex]
  const sourceUrls = [...market.source_urls]

  let book: MarketSnapshot['book'] = null
  let bestBidYes = market.best_bid ?? null
  let bestAskYes = market.best_ask ?? null
  let midpointYes: number | null = null
  let yesPrice = asNumber(parseStringArray(raw.outcomePrices)[yesOutcomeIndex]) ?? market.last_trade_price ?? null
  let history: MarketSnapshot['history'] = []

  if (yesTokenId) {
    const bookUrl = `${clobUrl}/book?token_id=${encodeURIComponent(yesTokenId)}`
    sourceUrls.push(bookUrl)
    try {
      const rawBook = await fetchJson<RawJson>(bookUrl)
      const bids = Array.isArray(rawBook.bids)
        ? rawBook.bids
            .map((level) => ({
              price: asNumber((level as RawJson).price),
              size: asNumber((level as RawJson).size),
            }))
            .filter((level): level is { price: number; size: number } => level.price != null && level.size != null)
        : []
      const asks = Array.isArray(rawBook.asks)
        ? rawBook.asks
            .map((level) => ({
              price: asNumber((level as RawJson).price),
              size: asNumber((level as RawJson).size),
            }))
            .filter((level): level is { price: number; size: number } => level.price != null && level.size != null)
        : []

      bestBidYes = maxPrice(bids)
      bestAskYes = minPrice(asks)
      midpointYes = bestBidYes != null && bestAskYes != null
        ? Number(((bestBidYes + bestAskYes) / 2).toFixed(6))
        : yesPrice
      yesPrice = midpointYes ?? asNumber(rawBook.last_trade_price) ?? yesPrice

      book = {
        token_id: String(rawBook.asset_id ?? yesTokenId),
        market_condition_id: asString(rawBook.market),
        fetched_at: new Date().toISOString(),
        best_bid: bestBidYes,
        best_ask: bestAskYes,
        last_trade_price: asNumber(rawBook.last_trade_price),
        tick_size: asNumber(rawBook.tick_size),
        min_order_size: asNumber(rawBook.min_order_size),
        bids,
        asks,
        depth_near_touch: computeDepthNearTouch(
          bids,
          asks,
          bestBidYes,
          bestAskYes,
          asNumber(rawBook.tick_size),
        ),
      }
    } catch (error) {
      logger.warn({ err: error, marketId: market.market_id }, 'Failed to fetch Polymarket order book')
    }

    if (historyLimit > 0) {
      const historyUrl = buildHistoryUrl(yesTokenId)
      sourceUrls.push(historyUrl)
      try {
        const rawHistory = await fetchJson<{ history?: Array<{ t?: number; p?: number }> }>(historyUrl)
        history = (rawHistory.history || [])
          .map((point) => ({ timestamp: point.t ?? 0, price: point.p ?? 0 }))
          .filter((point) => Number.isFinite(point.timestamp) && Number.isFinite(point.price))
          .slice(-historyLimit)
      } catch (error) {
        logger.warn({ err: error, marketId: market.market_id }, 'Failed to fetch Polymarket price history')
      }
    }
  }

  if (midpointYes == null && bestBidYes != null && bestAskYes != null) {
    midpointYes = Number(((bestBidYes + bestAskYes) / 2).toFixed(6))
  }
  if (yesPrice == null) {
    yesPrice = midpointYes ?? market.last_trade_price ?? null
  }

  const noPrice = yesPrice == null ? null : Number((1 - yesPrice).toFixed(6))
  const spreadBps = bestBidYes != null && bestAskYes != null
    ? Number(((bestAskYes - bestBidYes) * 10_000).toFixed(2))
    : null

  return marketSnapshotSchema.parse({
    schema_version: PREDICTION_MARKETS_SCHEMA_VERSION,
    venue: POLYMARKET_VENUE,
    market,
    captured_at: new Date().toISOString(),
    yes_outcome_index: yesOutcomeIndex,
    yes_token_id: yesTokenId,
    yes_price: yesPrice,
    no_price: noPrice,
    midpoint_yes: midpointYes,
    best_bid_yes: bestBidYes,
    best_ask_yes: bestAskYes,
    spread_bps: spreadBps,
    book,
    history,
    source_urls: [...new Set(sourceUrls)],
  })
}
