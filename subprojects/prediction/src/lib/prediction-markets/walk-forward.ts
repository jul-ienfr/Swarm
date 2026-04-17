import { applyCalibrationCurve, buildCalibrationReport } from '@/lib/prediction-markets/calibration'
import { PREDICTION_MARKETS_SCHEMA_VERSION, type PredictionMarketVenue } from '@/lib/prediction-markets/schemas'
import {
  buildPredictionMarketCostModelReport,
  estimatePredictionMarketTradeCostBreakdown,
  type PredictionMarketCostModelAssumptions,
} from '@/lib/prediction-markets/cost-model'
import {
  toCalibrationPointsFromResolvedHistory,
  type ResolvedHistoryPoint,
} from '@/lib/prediction-markets/resolved-history'
import { getPredictionMarketP1BRuntimeSummary } from '@/lib/prediction-markets/external-runtime'

export type PredictionMarketWalkForwardOptions = {
  train_window_points?: number
  test_window_points?: number
  step_points?: number
  bin_count?: number
  minimum_train_points?: number
  minimum_points_for_summary?: number
  weight_by_liquidity?: boolean
  cost_model?: PredictionMarketCostModelAssumptions
}

export type PredictionMarketWalkForwardWindow = {
  window_id: string
  train_start_at: string
  train_end_at: string
  test_start_at: string
  test_end_at: string
  train_points: number
  test_points: number
  raw_brier_score: number | null
  calibrated_brier_score: number | null
  raw_log_loss: number | null
  calibrated_log_loss: number | null
  brier_improvement: number | null
  log_loss_improvement: number | null
  average_cost_bps: number | null
  average_net_edge_bps: number | null
  calibration_error: number | null
}

export type PredictionMarketWalkForwardReport = {
  schema_version: string
  artifact_kind: 'walk_forward_report'
  run_id: string
  venue: PredictionMarketVenue
  market_id: string
  generated_at: string
  options: Required<Omit<PredictionMarketWalkForwardOptions, 'cost_model'>> & {
    cost_model: Required<PredictionMarketCostModelAssumptions>
  }
  total_points: number
  total_windows: number
  stable_window_rate: number | null
  mean_raw_brier_score: number | null
  mean_calibrated_brier_score: number | null
  mean_brier_improvement: number | null
  mean_raw_log_loss: number | null
  mean_calibrated_log_loss: number | null
  mean_log_loss_improvement: number | null
  mean_cost_bps: number | null
  mean_net_edge_bps: number | null
  promotion_ready: boolean
  notes: string[]
  summary: string
  windows: PredictionMarketWalkForwardWindow[]
}

export type BuildPredictionMarketWalkForwardReportInput = {
  runId: string
  venue: PredictionMarketVenue
  marketId: string
  points: readonly ResolvedHistoryPoint[]
  generatedAt?: string
  options?: PredictionMarketWalkForwardOptions
}

function clampProbability(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.min(1 - 1e-6, Math.max(1e-6, value))
}

function round(value: number, digits = 6): number {
  return Number(value.toFixed(digits))
}

function average(values: Array<number | null | undefined>): number | null {
  const filtered = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  if (filtered.length === 0) return null
  return round(filtered.reduce((sum, value) => sum + value, 0) / filtered.length)
}

function compareIso(left: string, right: string): number {
  const leftTs = Date.parse(left)
  const rightTs = Date.parse(right)
  if (Number.isFinite(leftTs) && Number.isFinite(rightTs)) return leftTs - rightTs
  return left.localeCompare(right)
}

function meanBrier(points: Array<{ probability: number; actual: boolean }>): number | null {
  if (points.length === 0) return null
  const total = points.reduce((sum, point) => sum + Math.pow(point.probability - (point.actual ? 1 : 0), 2), 0)
  return round(total / points.length)
}

function meanLogLoss(points: Array<{ probability: number; actual: boolean }>): number | null {
  if (points.length === 0) return null
  const total = points.reduce((sum, point) => {
    const probability = clampProbability(point.probability)
    return sum + (point.actual ? -Math.log(probability) : -Math.log(1 - probability))
  }, 0)
  return round(total / points.length)
}

export function buildPredictionMarketWalkForwardReport(
  input: BuildPredictionMarketWalkForwardReportInput,
): PredictionMarketWalkForwardReport {
  const sortedPoints = [...input.points].sort((left, right) => compareIso(left.cutoff_at, right.cutoff_at))
  const baseOptions = {
    train_window_points: Math.max(1, Math.floor(input.options?.train_window_points ?? 24)),
    test_window_points: Math.max(1, Math.floor(input.options?.test_window_points ?? 12)),
    step_points: Math.max(1, Math.floor(input.options?.step_points ?? Math.max(1, input.options?.test_window_points ?? 12))),
    bin_count: Math.max(1, Math.floor(input.options?.bin_count ?? 10)),
    minimum_train_points: Math.max(1, Math.floor(input.options?.minimum_train_points ?? 12)),
    minimum_points_for_summary: Math.max(1, Math.floor(input.options?.minimum_points_for_summary ?? 3)),
    weight_by_liquidity: input.options?.weight_by_liquidity ?? false,
  }
  const baseCostModel = buildPredictionMarketCostModelReport({
    runId: input.runId,
    venue: input.venue,
    marketId: input.marketId,
    points: sortedPoints,
    generatedAt: input.generatedAt,
    assumptions: input.options?.cost_model,
  })
  const windows: PredictionMarketWalkForwardWindow[] = []
  const notes: string[] = []

  if (sortedPoints.length === 0) {
    notes.push('empty_walk_forward_history')
  }

  for (
    let testStart = baseOptions.train_window_points;
    testStart < sortedPoints.length;
    testStart += baseOptions.step_points
  ) {
    const train = sortedPoints.slice(
      Math.max(0, testStart - baseOptions.train_window_points),
      testStart,
    )
    const test = sortedPoints.slice(testStart, testStart + baseOptions.test_window_points)
    if (train.length < baseOptions.minimum_train_points || test.length === 0) {
      continue
    }

    const calibrationReport = buildCalibrationReport(
      toCalibrationPointsFromResolvedHistory(train, {
        weight_by_liquidity: baseOptions.weight_by_liquidity,
      }),
      {
        bin_count: baseOptions.bin_count,
        minimum_points_for_summary: baseOptions.minimum_points_for_summary,
      },
    )
    const rawPoints = test.map((point) => ({
      probability: point.forecast_probability,
      actual: point.resolved_outcome,
    }))
    const calibratedPoints = test.map((point) => ({
      probability: applyCalibrationCurve(point.forecast_probability, calibrationReport).output_probability,
      actual: point.resolved_outcome,
    }))
    const windowCosts = test.map((point) => {
      const breakdown = estimatePredictionMarketTradeCostBreakdown({
        point,
        assumptions: input.options?.cost_model,
      })
      const grossEdgeBps = point.market_baseline_probability == null
        ? null
        : Math.abs(point.forecast_probability - point.market_baseline_probability) * 10_000
      return {
        cost_bps: breakdown.total_cost_bps,
        net_edge_bps: grossEdgeBps == null ? null : grossEdgeBps - breakdown.total_cost_bps,
      }
    })

    const rawBrier = meanBrier(rawPoints)
    const calibratedBrier = meanBrier(calibratedPoints)
    const rawLogLoss = meanLogLoss(rawPoints)
    const calibratedLogLoss = meanLogLoss(calibratedPoints)

    windows.push({
      window_id: `${input.runId}:wf:${windows.length + 1}`,
      train_start_at: train[0]!.cutoff_at,
      train_end_at: train.at(-1)!.cutoff_at,
      test_start_at: test[0]!.cutoff_at,
      test_end_at: test.at(-1)!.cutoff_at,
      train_points: train.length,
      test_points: test.length,
      raw_brier_score: rawBrier,
      calibrated_brier_score: calibratedBrier,
      raw_log_loss: rawLogLoss,
      calibrated_log_loss: calibratedLogLoss,
      brier_improvement: rawBrier != null && calibratedBrier != null ? round(rawBrier - calibratedBrier) : null,
      log_loss_improvement: rawLogLoss != null && calibratedLogLoss != null ? round(rawLogLoss - calibratedLogLoss) : null,
      average_cost_bps: average(windowCosts.map((entry) => entry.cost_bps)),
      average_net_edge_bps: average(windowCosts.map((entry) => entry.net_edge_bps)),
      calibration_error: calibrationReport.calibration_error,
    })
  }

  if (windows.length === 0 && sortedPoints.length > 0) {
    notes.push('insufficient_history_for_walk_forward')
  }

  const stableWindowRate = windows.length > 0
    ? round(windows.filter((window) => (window.brier_improvement ?? -Infinity) >= 0).length / windows.length)
    : null
  const meanRawBrier = average(windows.map((window) => window.raw_brier_score))
  const meanCalibratedBrier = average(windows.map((window) => window.calibrated_brier_score))
  const meanBrierImprovement = average(windows.map((window) => window.brier_improvement))
  const meanRawLogLoss = average(windows.map((window) => window.raw_log_loss))
  const meanCalibratedLogLoss = average(windows.map((window) => window.calibrated_log_loss))
  const meanLogLossImprovement = average(windows.map((window) => window.log_loss_improvement))
  const meanCostBps = average(windows.map((window) => window.average_cost_bps))
  const meanNetEdgeBps = average(windows.map((window) => window.average_net_edge_bps))
  const p1bRuntime = getPredictionMarketP1BRuntimeSummary({
    operator_thesis_present: false,
    research_pipeline_trace_present: windows.length > 0,
  })
  const promotionReady =
    windows.length >= 2
    && (stableWindowRate ?? 0) >= 0.5
    && (meanBrierImprovement ?? 0) >= 0
    && (meanNetEdgeBps ?? -Infinity) >= 0

  if (windows.length > 0) {
    notes.push(`external_governance:${p1bRuntime.summary}`)
  }

  const summary = windows.length > 0
    ? `Walk-forward ran ${windows.length} windows; mean brier improvement=${meanBrierImprovement ?? 'n/a'}, mean net edge=${meanNetEdgeBps ?? 'n/a'} bps.`
    : 'Walk-forward has insufficient resolved history to produce train/test windows.'

  return {
    schema_version: PREDICTION_MARKETS_SCHEMA_VERSION,
    artifact_kind: 'walk_forward_report',
    run_id: input.runId,
    venue: input.venue,
    market_id: input.marketId,
    generated_at: input.generatedAt ?? new Date().toISOString(),
    options: {
      ...baseOptions,
      cost_model: baseCostModel.assumptions,
    },
    total_points: sortedPoints.length,
    total_windows: windows.length,
    stable_window_rate: stableWindowRate,
    mean_raw_brier_score: meanRawBrier,
    mean_calibrated_brier_score: meanCalibratedBrier,
    mean_brier_improvement: meanBrierImprovement,
    mean_raw_log_loss: meanRawLogLoss,
    mean_calibrated_log_loss: meanCalibratedLogLoss,
    mean_log_loss_improvement: meanLogLossImprovement,
    mean_cost_bps: meanCostBps,
    mean_net_edge_bps: meanNetEdgeBps,
    promotion_ready: promotionReady,
    notes,
    summary,
    windows,
  }
}
