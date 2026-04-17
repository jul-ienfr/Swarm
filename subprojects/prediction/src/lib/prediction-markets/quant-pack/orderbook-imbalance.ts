import { clamp, round, uniqueStrings } from './helpers'
import type { OrderbookSnapshot } from './types'

export type OrderbookImbalanceAssessment = {
  read_only: true
  kind: 'orderbook_imbalance'
  viable: boolean
  market_id: string | null
  question: string | null
  token_id: string | null
  side: 'yes' | 'no' | 'neutral'
  imbalance_ratio: number
  bid_depth: number
  ask_depth: number
  total_depth: number
  depth_window: number
  best_bid: number
  best_ask: number
  spread: number
  market_yes_price: number
  fair_value: number
  fee_rate: number
  edge: number
  edge_bps: number
  blockers: string[]
  reasons: string[]
  summary: string
}

export type OrderbookImbalanceScanInput = OrderbookSnapshot & {
  market_yes_price?: number | null
  fee_rate?: number | null
  min_liquidity_usd?: number | null
  min_volume_24h_usd?: number | null
  max_spread?: number | null
  min_edge?: number | null
}

function bestBidFromLevels(levels: readonly { price: number }[] | undefined, fallback: number): number {
  if (!levels || levels.length === 0) return fallback
  const best = Math.max(...levels.map((level) => Number(level.price)).filter((price) => Number.isFinite(price)))
  return Number.isFinite(best) ? best : fallback
}

function bestAskFromLevels(levels: readonly { price: number }[] | undefined, fallback: number): number {
  if (!levels || levels.length === 0) return fallback
  const best = Math.min(...levels.map((level) => Number(level.price)).filter((price) => Number.isFinite(price)))
  return Number.isFinite(best) ? best : fallback
}

function sumDepth(
  levels: readonly { price: number; size: number }[] | undefined,
  reference: number,
  side: 'bid' | 'ask',
  window: number,
): number {
  if (!levels || levels.length === 0) return 0
  let total = 0
  for (const level of levels) {
    const price = Number(level.price)
    const size = Number(level.size)
    if (!Number.isFinite(price) || !Number.isFinite(size)) continue
    if (side === 'bid') {
      if (price >= reference - window && price <= reference) total += size
    } else if (price <= reference + window && price >= reference) {
      total += size
    }
  }
  return total
}

export function assessOrderbookImbalance(input: OrderbookImbalanceScanInput): OrderbookImbalanceAssessment {
  const bestBid = bestBidFromLevels(input.bids, Number(input.best_bid ?? 0))
  const bestAsk = bestAskFromLevels(input.asks, Number(input.best_ask ?? 0))
  const spread = Number.isFinite(Number(input.spread)) ? Number(input.spread) : Math.max(0, bestAsk - bestBid)
  const marketYesPrice = Number.isFinite(Number(input.market_yes_price))
    ? Number(input.market_yes_price)
    : clamp((bestBid + bestAsk) / 2, 0, 1)
  const feeRate = clamp(Number(input.fee_rate ?? 0.02), 0, 0.5)
  const depthWindow = Math.max(0.03, spread > 0 ? spread / 2 : 0.03)
  const bidDepth = sumDepth(input.bids, bestBid, 'bid', depthWindow)
  const askDepth = sumDepth(input.asks, bestAsk, 'ask', depthWindow)
  const totalDepth = bidDepth + askDepth
  const imbalanceRatio = totalDepth > 0 ? bidDepth / totalDepth : 0.5
  const yesSide = imbalanceRatio >= 0.7
  const noSide = imbalanceRatio <= 0.3
  const side = yesSide ? 'yes' : noSide ? 'no' : 'neutral'
  const fairValue = side === 'yes'
    ? clamp(marketYesPrice + (imbalanceRatio - 0.5) * 0.15, 0, 1)
    : side === 'no'
      ? clamp((1 - marketYesPrice) + ((0.5 - imbalanceRatio) * 0.15), 0, 1)
      : marketYesPrice
  const edge = side === 'yes'
    ? fairValue - marketYesPrice - feeRate
    : side === 'no'
      ? fairValue - (1 - marketYesPrice) - feeRate
      : 0
  const blockers = uniqueStrings([
    totalDepth <= 0 ? 'empty_depth' : null,
    spread > 0.25 ? 'spread_too_wide' : null,
    marketYesPrice <= 0 || marketYesPrice >= 1 ? 'invalid_price' : null,
    side === 'neutral' ? 'no_clear_imbalance' : null,
    edge <= 0 ? 'edge_below_fee' : null,
  ])
  const reasons = uniqueStrings([
    `bid_depth=${round(bidDepth, 2)}`,
    `ask_depth=${round(askDepth, 2)}`,
    `imbalance_ratio=${round(imbalanceRatio, 4)}`,
    `depth_window=${round(depthWindow, 4)}`,
    side !== 'neutral' ? `side=${side}` : null,
  ])

  return {
    read_only: true,
    kind: 'orderbook_imbalance',
    viable: blockers.length === 0,
    market_id: input.market_id ?? null,
    question: input.question ?? null,
    token_id: input.token_id ?? null,
    side,
    imbalance_ratio: round(imbalanceRatio, 4),
    bid_depth: round(bidDepth, 4),
    ask_depth: round(askDepth, 4),
    total_depth: round(totalDepth, 4),
    depth_window: round(depthWindow, 4),
    best_bid: round(bestBid, 4),
    best_ask: round(bestAsk, 4),
    spread: round(spread, 4),
    market_yes_price: round(marketYesPrice, 4),
    fair_value: round(fairValue, 4),
    fee_rate: round(feeRate, 4),
    edge: round(edge, 4),
    edge_bps: round(edge * 10_000, 1),
    blockers,
    reasons,
    summary: side === 'neutral'
      ? `No actionable imbalance: bid_depth=${round(bidDepth, 2)} ask_depth=${round(askDepth, 2)}`
      : `${side.toUpperCase()} imbalance with edge=${round(edge * 10_000, 1)}bps and ratio=${round(imbalanceRatio, 3)}`,
  }
}

export function scanOrderbookImbalances(markets: readonly OrderbookImbalanceScanInput[]): OrderbookImbalanceAssessment[] {
  return markets.map((market) => assessOrderbookImbalance(market))
}

