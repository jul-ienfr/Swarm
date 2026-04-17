import { PREDICTION_MARKETS_SCHEMA_VERSION, type PredictionMarketVenue } from '@/lib/prediction-markets/schemas'
import type { ResolvedHistoryPoint } from '@/lib/prediction-markets/resolved-history'

export type PredictionMarketCostModelAssumptions = {
  entry_fee_bps?: number | null
  exit_fee_bps?: number | null
  half_spread_fraction?: number | null
  base_slippage_bps?: number | null
  fill_probability?: number | null
  missed_trade_penalty_ratio?: number | null
  minimum_net_edge_bps?: number | null
}

export type PredictionMarketTradeCostBreakdown = {
  fee_bps: number
  spread_cost_bps: number
  slippage_bps: number
  liquidity_impact_bps: number
  missed_fill_penalty_bps: number
  total_cost_bps: number
}

export type PredictionMarketCostModelPoint = {
  point_id: string
  gross_edge_bps: number | null
  expected_cost_bps: number
  net_edge_bps: number | null
  viable: boolean
  breakdown: PredictionMarketTradeCostBreakdown
}

export type PredictionMarketCostModelReport = {
  schema_version: string
  artifact_kind: 'cost_model_report'
  run_id: string
  venue: PredictionMarketVenue
  market_id: string
  generated_at: string
  assumptions: Required<PredictionMarketCostModelAssumptions>
  total_points: number
  viable_point_count: number
  viable_point_rate: number | null
  average_gross_edge_bps: number | null
  average_cost_bps: number | null
  average_net_edge_bps: number | null
  notes: string[]
  summary: string
  points: PredictionMarketCostModelPoint[]
}

export type BuildPredictionMarketCostModelReportInput = {
  runId: string
  venue: PredictionMarketVenue
  marketId: string
  points: readonly ResolvedHistoryPoint[]
  generatedAt?: string
  assumptions?: PredictionMarketCostModelAssumptions
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function round(value: number, digits = 6): number {
  return Number(value.toFixed(digits))
}

function average(values: Array<number | null | undefined>): number | null {
  const filtered = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  if (filtered.length === 0) return null
  return round(filtered.reduce((sum, value) => sum + value, 0) / filtered.length)
}

function withDefaults(
  assumptions: PredictionMarketCostModelAssumptions | undefined,
): Required<PredictionMarketCostModelAssumptions> {
  return {
    entry_fee_bps: Math.max(0, asNumber(assumptions?.entry_fee_bps) ?? 60),
    exit_fee_bps: Math.max(0, asNumber(assumptions?.exit_fee_bps) ?? 0),
    half_spread_fraction: Math.min(1, Math.max(0, asNumber(assumptions?.half_spread_fraction) ?? 0.5)),
    base_slippage_bps: Math.max(0, asNumber(assumptions?.base_slippage_bps) ?? 6),
    fill_probability: Math.min(1, Math.max(0, asNumber(assumptions?.fill_probability) ?? 0.92)),
    missed_trade_penalty_ratio: Math.min(1, Math.max(0, asNumber(assumptions?.missed_trade_penalty_ratio) ?? 0.1)),
    minimum_net_edge_bps: Math.max(0, asNumber(assumptions?.minimum_net_edge_bps) ?? 0),
  }
}

export function estimatePredictionMarketTradeCostBreakdown(input: {
  point?: Pick<ResolvedHistoryPoint, 'spread_bps' | 'fee_bps' | 'size_usd' | 'liquidity_usd' | 'forecast_probability' | 'market_baseline_probability'> | null
  assumptions?: PredictionMarketCostModelAssumptions
}): PredictionMarketTradeCostBreakdown {
  const assumptions = withDefaults(input.assumptions)
  const point = input.point ?? null
  const grossEdgeBps = point != null && point.market_baseline_probability != null
    ? Math.abs(point.forecast_probability - point.market_baseline_probability) * 10_000
    : null
  const feeBps = Math.max(0, point?.fee_bps ?? assumptions.entry_fee_bps) + assumptions.exit_fee_bps
  const spreadCostBps = Math.max(0, point?.spread_bps ?? 0) * assumptions.half_spread_fraction
  const slippageBps = assumptions.base_slippage_bps
  const liquidityImpactBps = point?.size_usd != null && point?.liquidity_usd != null && point.liquidity_usd > 0
    ? Math.min(150, (point.size_usd / point.liquidity_usd) * 2_500)
    : 0
  const missedFillPenaltyBps = grossEdgeBps == null
    ? 0
    : Math.max(0, grossEdgeBps * (1 - assumptions.fill_probability) * assumptions.missed_trade_penalty_ratio)
  const totalCostBps = feeBps + spreadCostBps + slippageBps + liquidityImpactBps + missedFillPenaltyBps

  return {
    fee_bps: round(feeBps),
    spread_cost_bps: round(spreadCostBps),
    slippage_bps: round(slippageBps),
    liquidity_impact_bps: round(liquidityImpactBps),
    missed_fill_penalty_bps: round(missedFillPenaltyBps),
    total_cost_bps: round(totalCostBps),
  }
}

export function buildPredictionMarketCostModelReport(
  input: BuildPredictionMarketCostModelReportInput,
): PredictionMarketCostModelReport {
  const assumptions = withDefaults(input.assumptions)
  const points = input.points.map((point) => {
    const breakdown = estimatePredictionMarketTradeCostBreakdown({
      point,
      assumptions,
    })
    const grossEdgeBps = point.market_baseline_probability == null
      ? null
      : Math.abs(point.forecast_probability - point.market_baseline_probability) * 10_000
    const netEdgeBps = grossEdgeBps == null ? null : grossEdgeBps - breakdown.total_cost_bps
    const viable = netEdgeBps != null && netEdgeBps >= assumptions.minimum_net_edge_bps

    return {
      point_id: point.point_id,
      gross_edge_bps: grossEdgeBps == null ? null : round(grossEdgeBps),
      expected_cost_bps: breakdown.total_cost_bps,
      net_edge_bps: netEdgeBps == null ? null : round(netEdgeBps),
      viable,
      breakdown,
    }
  })
  const viablePointCount = points.filter((point) => point.viable).length
  const totalPoints = points.length
  const viablePointRate = totalPoints > 0 ? round(viablePointCount / totalPoints) : null
  const averageGrossEdgeBps = average(points.map((point) => point.gross_edge_bps))
  const averageCostBps = average(points.map((point) => point.expected_cost_bps))
  const averageNetEdgeBps = average(points.map((point) => point.net_edge_bps))
  const notes: string[] = []

  if (totalPoints === 0) {
    notes.push('empty_cost_model_history')
  }
  if (points.every((point) => point.gross_edge_bps == null)) {
    notes.push('gross_edge_missing')
  }
  if ((averageNetEdgeBps ?? 0) < 0) {
    notes.push('negative_average_net_edge')
  }

  const summary = totalPoints > 0
    ? `Cost model evaluated ${totalPoints} resolved points; average net edge=${averageNetEdgeBps ?? 'n/a'} bps, viable rate=${viablePointRate ?? 'n/a'}.`
    : 'Cost model has no resolved points to evaluate yet.'

  return {
    schema_version: PREDICTION_MARKETS_SCHEMA_VERSION,
    artifact_kind: 'cost_model_report',
    run_id: input.runId,
    venue: input.venue,
    market_id: input.marketId,
    generated_at: input.generatedAt ?? new Date().toISOString(),
    assumptions,
    total_points: totalPoints,
    viable_point_count: viablePointCount,
    viable_point_rate: viablePointRate,
    average_gross_edge_bps: averageGrossEdgeBps,
    average_cost_bps: averageCostBps,
    average_net_edge_bps: averageNetEdgeBps,
    notes,
    summary,
    points,
  }
}
