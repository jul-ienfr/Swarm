import {
  PREDICTION_MARKETS_SCHEMA_VERSION,
  forecastEvaluationRecordSchema,
  type ForecastEvaluationRecord,
  type PredictionMarketVenue,
} from '@/lib/prediction-markets/schemas'
import type { CalibrationPoint } from '@/lib/prediction-markets/calibration'

export type ResolvedHistoryPoint = {
  point_id: string
  evaluation_id: string
  question_id: string
  market_id: string
  venue: PredictionMarketVenue
  cutoff_at: string
  resolved_outcome: boolean
  forecast_probability: number
  market_baseline_probability: number | null
  brier_score: number | null
  log_loss: number | null
  ece_bucket: string | null
  basis: string | null
  comparator_id: string | null
  comparator_kind: string | null
  comparator_role: string | null
  pipeline_id: string | null
  pipeline_version: string | null
  category: string | null
  horizon_bucket: string | null
  liquidity_usd: number | null
  volume_24h_usd: number | null
  spread_bps: number | null
  fee_bps: number | null
  size_usd: number | null
}

export type ResolvedHistoryDataset = {
  schema_version: string
  artifact_kind: 'resolved_history'
  run_id: string
  venue: PredictionMarketVenue
  market_id: string
  generated_at: string
  source_summary?: string | null
  total_records: number
  resolved_records: number
  unresolved_records: number
  first_cutoff_at: string | null
  last_cutoff_at: string | null
  comparator_ids: string[]
  pipeline_ids: string[]
  notes: string[]
  summary: string
  points: ResolvedHistoryPoint[]
}

export type BuildResolvedHistoryDatasetInput = {
  runId: string
  venue: PredictionMarketVenue
  marketId: string
  evaluationHistory?: readonly ForecastEvaluationRecord[]
  generatedAt?: string
  defaults?: {
    liquidity_usd?: number | null
    volume_24h_usd?: number | null
    spread_bps?: number | null
    fee_bps?: number | null
    size_usd?: number | null
    category?: string | null
    horizon_bucket?: string | null
  }
}

export type CalibrationPointOptions = {
  weight_by_liquidity?: boolean
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function clampProbability(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.min(1, Math.max(0, value))
}

function toTimestamp(value: string | null | undefined): number | null {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : null
}

function compareIso(left: string, right: string): number {
  const leftTs = toTimestamp(left)
  const rightTs = toTimestamp(right)
  if (leftTs != null && rightTs != null) return leftTs - rightTs
  return left.localeCompare(right)
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(values.filter((value): value is string => typeof value === 'string' && value.length > 0)))
}

export function inferPredictionMarketCategory(
  marketId: string,
  basis?: string | null,
): string | null {
  const normalized = marketId.toLowerCase()
  if (normalized.includes('election') || normalized.includes('president')) return 'politics'
  if (normalized.includes('btc') || normalized.includes('eth') || normalized.includes('crypto')) return 'crypto'
  if (normalized.includes('nba') || normalized.includes('nfl') || normalized.includes('mlb') || normalized.includes('sport')) return 'sports'
  if (basis === 'manual_thesis') return 'manual_thesis'
  return null
}

function inferCategory(record: ForecastEvaluationRecord, marketId: string): string | null {
  const basis = typeof record.basis === 'string' ? record.basis : null
  return inferPredictionMarketCategory(marketId, basis)
}

function inferHorizonBucket(cutoffAt: string): string | null {
  const cutoff = toTimestamp(cutoffAt)
  if (cutoff == null) return null
  const now = Date.now()
  const deltaDays = Math.abs(now - cutoff) / (24 * 60 * 60 * 1000)
  if (deltaDays <= 7) return '0_7d'
  if (deltaDays <= 30) return '8_30d'
  if (deltaDays <= 90) return '31_90d'
  return '90d_plus'
}

function toResolvedHistoryPoint(
  record: ForecastEvaluationRecord,
  index: number,
  defaults: BuildResolvedHistoryDatasetInput['defaults'],
): ResolvedHistoryPoint | null {
  if (record.resolved_outcome == null) return null

  return {
    point_id: `${record.evaluation_id}:resolved:${index + 1}`,
    evaluation_id: record.evaluation_id,
    question_id: record.question_id,
    market_id: record.market_id,
    venue: record.venue,
    cutoff_at: record.cutoff_at,
    resolved_outcome: record.resolved_outcome,
    forecast_probability: clampProbability(record.forecast_probability),
    market_baseline_probability: asNumber(record.market_baseline_probability),
    brier_score: asNumber(record.brier_score),
    log_loss: asNumber(record.log_loss),
    ece_bucket: record.ece_bucket ?? null,
    basis: record.basis ?? null,
    comparator_id: record.comparator_id ?? null,
    comparator_kind: record.comparator_kind ?? null,
    comparator_role: record.comparator_role ?? null,
    pipeline_id: record.pipeline_id ?? null,
    pipeline_version: record.pipeline_version ?? null,
    category: defaults?.category ?? inferCategory(record, record.market_id),
    horizon_bucket: defaults?.horizon_bucket ?? inferHorizonBucket(record.cutoff_at),
    liquidity_usd: defaults?.liquidity_usd ?? null,
    volume_24h_usd: defaults?.volume_24h_usd ?? null,
    spread_bps: defaults?.spread_bps ?? null,
    fee_bps: defaults?.fee_bps ?? null,
    size_usd: defaults?.size_usd ?? null,
  }
}

export function buildResolvedHistoryDataset(
  input: BuildResolvedHistoryDatasetInput,
): ResolvedHistoryDataset {
  const evaluationHistory = input.evaluationHistory ?? []
  const points = evaluationHistory
    .map((record, index) => toResolvedHistoryPoint(record, index, input.defaults))
    .filter((point): point is ResolvedHistoryPoint => point != null)
    .sort((left, right) => compareIso(left.cutoff_at, right.cutoff_at))
  const totalRecords = evaluationHistory.length
  const resolvedRecords = points.length
  const unresolvedRecords = Math.max(0, totalRecords - resolvedRecords)
  const firstCutoffAt = points[0]?.cutoff_at ?? null
  const lastCutoffAt = points.at(-1)?.cutoff_at ?? null
  const comparatorIds = uniqueStrings(points.map((point) => point.comparator_id))
  const pipelineIds = uniqueStrings(points.map((point) => point.pipeline_id))
  const notes: string[] = []

  if (totalRecords === 0) {
    notes.push('empty_evaluation_history')
  }
  if (resolvedRecords === 0) {
    notes.push('no_resolved_records')
  }
  if (unresolvedRecords > 0) {
    notes.push(`unresolved_records:${unresolvedRecords}`)
  }

  const summary = resolvedRecords > 0
    ? `Resolved history built from ${resolvedRecords}/${totalRecords} evaluation records spanning ${firstCutoffAt} -> ${lastCutoffAt}.`
    : 'Resolved history is empty; provide evaluation_history with resolved_outcome values to activate calibration and walk-forward.'

  return {
    schema_version: PREDICTION_MARKETS_SCHEMA_VERSION,
    artifact_kind: 'resolved_history',
    run_id: input.runId,
    venue: input.venue,
    market_id: input.marketId,
    generated_at: input.generatedAt ?? new Date().toISOString(),
    source_summary: null,
    total_records: totalRecords,
    resolved_records: resolvedRecords,
    unresolved_records: unresolvedRecords,
    first_cutoff_at: firstCutoffAt,
    last_cutoff_at: lastCutoffAt,
    comparator_ids: comparatorIds,
    pipeline_ids: pipelineIds,
    notes,
    summary,
    points,
  }
}

export function toCalibrationPointsFromResolvedHistory(
  points: readonly ResolvedHistoryPoint[],
  options: CalibrationPointOptions = {},
): CalibrationPoint[] {
  return points.map((point) => {
    const liquidityWeight = options.weight_by_liquidity
      ? Math.max(1, Math.sqrt(Math.max(1, point.liquidity_usd ?? 1)) / 10)
      : 1

    return {
      predicted_probability: point.forecast_probability,
      actual_outcome: point.resolved_outcome,
      weight: Number(liquidityWeight.toFixed(6)),
      label: point.point_id,
    }
  })
}

export function toForecastEvaluationRecordFromResolvedHistoryPoint(
  point: ResolvedHistoryPoint,
): ForecastEvaluationRecord {
  return forecastEvaluationRecordSchema.parse({
    schema_version: PREDICTION_MARKETS_SCHEMA_VERSION,
    evaluation_id: point.evaluation_id,
    question_id: point.question_id,
    market_id: point.market_id,
    venue: point.venue,
    cutoff_at: point.cutoff_at,
    forecast_probability: point.forecast_probability,
    market_baseline_probability: point.market_baseline_probability ?? point.forecast_probability,
    resolved_outcome: point.resolved_outcome,
    brier_score: point.brier_score ?? null,
    log_loss: point.log_loss ?? null,
    ece_bucket: point.ece_bucket ?? 'resolved_history',
    abstain_flag: false,
    basis: point.basis === 'manual_thesis' || point.basis === 'market_midpoint' ? point.basis : undefined,
    comparator_id: point.comparator_id ?? undefined,
    comparator_kind: point.comparator_kind === 'candidate_model'
      || point.comparator_kind === 'market_baseline'
      || point.comparator_kind === 'ensemble'
      || point.comparator_kind === 'operator_override'
      ? point.comparator_kind
      : undefined,
    comparator_role: point.comparator_role === 'candidate'
      || point.comparator_role === 'baseline'
      || point.comparator_role === 'control'
      ? point.comparator_role
      : undefined,
    pipeline_id: point.pipeline_id ?? undefined,
    pipeline_version: point.pipeline_version ?? undefined,
  })
}
