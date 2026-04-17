import { clamp, round, sum, uniqueStrings } from './helpers'
import type { ParityLeg } from './types'

export type ParityAssessment = {
  read_only: true
  kind: 'binary_parity' | 'multi_outcome_parity'
  viable: boolean
  market_group_id: string | null
  market_ids: string[]
  leg_count: number
  gross_cost: number
  fee_cost: number
  net_cost: number
  locked_profit: number
  edge_bps: number
  blockers: string[]
  reasons: string[]
  summary: string
}

type ParityInput = {
  market_group_id?: string | null
  legs: readonly ParityLeg[]
  min_edge_bps?: number | null
}

function legWeight(leg: ParityLeg): number {
  const weight = Number(leg.weight ?? 1)
  return Number.isFinite(weight) && weight > 0 ? weight : 1
}

export function assessMultiOutcomeParity(input: ParityInput): ParityAssessment {
  const legs = input.legs.filter((leg) => Number.isFinite(leg.yes_price))
  const marketIds = uniqueStrings(legs.map((leg) => leg.market_id ?? null))
  const grossCost = sum(legs.map((leg) => clamp(Number(leg.yes_price), 0, 1) * legWeight(leg)))
  const feeCost = sum(legs.map((leg) => clamp(Number(leg.fee_rate ?? 0.02), 0, 0.5) * legWeight(leg)))
  const netCost = grossCost + feeCost
  const lockedProfit = Math.max(0, 1 - netCost)
  const edgeBps = round(lockedProfit * 10_000, 1)
  const blockers = uniqueStrings([
    legs.length < 2 ? 'insufficient_legs' : null,
    lockedProfit <= 0 ? 'no_locked_profit' : null,
    typeof input.min_edge_bps === 'number' && edgeBps < input.min_edge_bps ? 'edge_below_minimum' : null,
  ])
  const reasons = uniqueStrings([
    `gross_cost=${round(grossCost, 4)}`,
    `fee_cost=${round(feeCost, 4)}`,
    `net_cost=${round(netCost, 4)}`,
    `locked_profit=${round(lockedProfit, 4)}`,
  ])

  return {
    read_only: true,
    kind: 'multi_outcome_parity',
    viable: blockers.length === 0,
    market_group_id: input.market_group_id ?? null,
    market_ids: marketIds,
    leg_count: legs.length,
    gross_cost: round(grossCost, 4),
    fee_cost: round(feeCost, 4),
    net_cost: round(netCost, 4),
    locked_profit: round(lockedProfit, 4),
    edge_bps: edgeBps,
    blockers,
    reasons,
    summary: blockers.length > 0
      ? `No parity opportunity: net_cost=${round(netCost, 4)}`
      : `Parity opportunity: locked_profit=${round(lockedProfit, 4)} (${edgeBps}bps) across ${legs.length} legs`,
  }
}

export function assessBinaryParity(input: {
  market_group_id?: string | null
  market_id?: string | null
  yes_price: number
  no_price: number
  fee_rate?: number | null
  min_edge_bps?: number | null
}): ParityAssessment {
  const report = assessMultiOutcomeParity({
    market_group_id: input.market_group_id ?? input.market_id ?? null,
    min_edge_bps: input.min_edge_bps,
    legs: [
      { market_id: `${input.market_id ?? 'binary'}:yes`, yes_price: input.yes_price, fee_rate: input.fee_rate },
      { market_id: `${input.market_id ?? 'binary'}:no`, yes_price: input.no_price, fee_rate: input.fee_rate },
    ],
  })

  return {
    ...report,
    kind: 'binary_parity',
  }
}
