import { clamp, round, uniqueStrings } from './helpers'

export type SpreadCaptureAssessment = {
  read_only: true
  kind: 'spread_capture'
  viable: boolean
  market_id: string | null
  question: string | null
  best_bid: number
  best_ask: number
  spread: number
  fee_rate: number
  net_spread: number
  net_spread_bps: number
  freshness_gap_ms: number | null
  freshness_budget_ms: number | null
  inventory_bias: number
  blockers: string[]
  reasons: string[]
  summary: string
}

export function assessSpreadCapture(input: {
  market_id?: string | null
  question?: string | null
  best_bid: number
  best_ask: number
  fee_rate?: number | null
  min_spread?: number | null
  max_spread?: number | null
  freshness_gap_ms?: number | null
  freshness_budget_ms?: number | null
  inventory_bias?: number | null
}): SpreadCaptureAssessment {
  const bestBid = clamp(Number(input.best_bid), 0, 1)
  const bestAsk = clamp(Number(input.best_ask), 0, 1)
  const spread = Math.max(0, bestAsk - bestBid)
  const feeRate = clamp(Number(input.fee_rate ?? 0.02), 0, 0.5)
  const netSpread = spread - (2 * feeRate)
  const freshnessGapMs = typeof input.freshness_gap_ms === 'number' && Number.isFinite(input.freshness_gap_ms)
    ? Math.max(0, Math.round(input.freshness_gap_ms))
    : null
  const freshnessBudgetMs = typeof input.freshness_budget_ms === 'number' && Number.isFinite(input.freshness_budget_ms)
    ? Math.max(0, Math.round(input.freshness_budget_ms))
    : null
  const inventoryBias = clamp(Number(input.inventory_bias ?? 0), -1, 1)
  const blockers = uniqueStrings([
    spread <= 0 ? 'no_spread' : null,
    typeof input.min_spread === 'number' && spread < input.min_spread ? 'spread_below_minimum' : null,
    typeof input.max_spread === 'number' && spread > input.max_spread ? 'spread_above_maximum' : null,
    netSpread <= 0 ? 'fees_consume_spread' : null,
    freshnessGapMs != null && freshnessBudgetMs != null && freshnessGapMs > freshnessBudgetMs ? 'quote_stale' : null,
  ])
  const reasons = uniqueStrings([
    `spread=${round(spread, 4)}`,
    `fee_rate=${round(feeRate, 4)}`,
    `net_spread=${round(netSpread, 4)}`,
    freshnessGapMs != null ? `freshness_gap_ms=${freshnessGapMs}` : null,
    inventoryBias !== 0 ? `inventory_bias=${round(inventoryBias, 4)}` : null,
  ])

  return {
    read_only: true,
    kind: 'spread_capture',
    viable: blockers.length === 0,
    market_id: input.market_id ?? null,
    question: input.question ?? null,
    best_bid: round(bestBid, 4),
    best_ask: round(bestAsk, 4),
    spread: round(spread, 4),
    fee_rate: round(feeRate, 4),
    net_spread: round(netSpread, 4),
    net_spread_bps: round(netSpread * 10_000, 1),
    freshness_gap_ms: freshnessGapMs,
    freshness_budget_ms: freshnessBudgetMs,
    inventory_bias: round(inventoryBias, 4),
    blockers,
    reasons,
    summary: blockers.length > 0
      ? `Spread capture blocked: spread=${round(spread, 4)} net=${round(netSpread, 4)}`
      : `Spread capture viable: net_spread=${round(netSpread, 4)} (${round(netSpread * 10_000, 1)}bps)`,
  }
}

