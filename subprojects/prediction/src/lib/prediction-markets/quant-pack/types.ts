import type { QuantSide } from './helpers'

export type QuantMarketRef = {
  market_id?: string | null
  question?: string | null
  venue?: string | null
  token_id?: string | null
}

export type OrderbookLevel = {
  price: number
  size: number
}

export type OrderbookSnapshot = QuantMarketRef & {
  best_bid?: number | null
  best_ask?: number | null
  spread?: number | null
  liquidity_usd?: number | null
  volume_24h_usd?: number | null
  fetched_at?: string | null
  bids?: readonly OrderbookLevel[]
  asks?: readonly OrderbookLevel[]
}

export type BookmakerQuote = {
  bookmaker: string
  outcome: string
  decimal_odds: number
  implied_prob?: number | null
  is_sharp?: boolean | null
}

export type MarketQuotePack = QuantMarketRef & {
  market_yes_price: number
  fee_rate?: number | null
  bookmaker_quotes?: readonly BookmakerQuote[]
}

export type ParityLeg = QuantMarketRef & {
  yes_price: number
  fee_rate?: number | null
  weight?: number | null
}

export type KellySizingRequest = QuantMarketRef & {
  probability_yes: number
  market_yes_price: number
  bankroll_usd: number
  fractional_kelly?: number | null
  max_position_usd?: number | null
  fee_rate?: number | null
  preferred_side?: QuantSide | null
}

