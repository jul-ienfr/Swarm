export function toPolymarketQuoteMarketEvent(snapshot: unknown): Record<string, unknown> {
  const input = (snapshot && typeof snapshot === 'object' ? snapshot : {}) as Record<string, unknown>
  const market = (input.market && typeof input.market === 'object' && !Array.isArray(input.market)
    ? input.market
    : {}) as Record<string, unknown>
  const book = (input.book && typeof input.book === 'object' && !Array.isArray(input.book)
    ? input.book
    : {}) as Record<string, unknown>

  return {
    event_id: asString(book.market_condition_id) ?? asString(market.market_id) ?? 'polymarket-quote',
    ts: asString(book.fetched_at) ?? asString(input.captured_at) ?? new Date(0).toISOString(),
    venue: 'polymarket',
    market_id: asString(market.market_id),
    event_type: 'quote',
    best_bid: asNumber(book.best_bid) ?? asNumber(market.best_bid),
    best_ask: asNumber(book.best_ask) ?? asNumber(market.best_ask),
    last_trade_price: asNumber(book.last_trade_price) ?? asNumber(market.last_trade_price),
    bid_size: firstLevelSize(book.bids),
    ask_size: firstLevelSize(book.asks),
    quote_age_ms: quoteAgeMs(input),
  }
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function firstLevelSize(value: unknown): number | null {
  if (!Array.isArray(value) || value.length === 0) return null
  const first = value[0]
  if (!first || typeof first !== 'object') return null
  return asNumber((first as Record<string, unknown>).size)
}

function quoteAgeMs(input: Record<string, unknown>): number | null {
  const capturedAt = asString(input.captured_at)
  const fetchedAt = input.book && typeof input.book === 'object' && !Array.isArray(input.book)
    ? asString((input.book as Record<string, unknown>).fetched_at)
    : null

  if (!capturedAt || !fetchedAt) return null

  const delta = Date.parse(capturedAt) - Date.parse(fetchedAt)
  return Number.isFinite(delta) ? delta : null
}