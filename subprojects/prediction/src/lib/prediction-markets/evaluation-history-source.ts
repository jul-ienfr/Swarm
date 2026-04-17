import { getPredictionMarketRunDetails, listPredictionMarketRuns } from '@/lib/prediction-markets/store'
import type { ForecastEvaluationRecord, PredictionMarketVenue } from '@/lib/prediction-markets/schemas'
import {
  inferPredictionMarketCategory,
  toForecastEvaluationRecordFromResolvedHistoryPoint,
  type ResolvedHistoryPoint,
} from '@/lib/prediction-markets/resolved-history'

export type PredictionMarketEvaluationHistorySource = 'request' | 'stored_runs' | 'none'

export type PredictionMarketEvaluationHistoryResolution = {
  evaluation_history: ForecastEvaluationRecord[]
  source: PredictionMarketEvaluationHistorySource
  source_summary: string
  considered_runs: number
  used_runs: number
  same_market_records: number
  same_category_records: number
  same_venue_records: number
}

export type ResolvePredictionMarketEvaluationHistoryInput = {
  workspaceId: number
  venue: PredictionMarketVenue
  marketId: string
  providedHistory?: readonly ForecastEvaluationRecord[] | null
  providedSource?: 'request' | 'stored_artifact'
  excludeRunIds?: readonly string[]
  targetRecords?: number
  searchLimit?: number
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null
}

function asBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(values.filter((value): value is string => typeof value === 'string' && value.length > 0)))
}

function compareCutoff(left: ForecastEvaluationRecord, right: ForecastEvaluationRecord): number {
  const leftTs = Date.parse(left.cutoff_at)
  const rightTs = Date.parse(right.cutoff_at)
  if (Number.isFinite(leftTs) && Number.isFinite(rightTs)) return leftTs - rightTs
  return left.cutoff_at.localeCompare(right.cutoff_at)
}

function normalizeResolvedHistoryPoint(value: unknown): ResolvedHistoryPoint | null {
  if (!value || typeof value !== 'object') return null
  const point = value as Record<string, unknown>
  const pointId = asString(point.point_id)
  const evaluationId = asString(point.evaluation_id)
  const questionId = asString(point.question_id)
  const marketId = asString(point.market_id)
  const venue = point.venue === 'polymarket' || point.venue === 'kalshi' ? point.venue : null
  const cutoffAt = asString(point.cutoff_at)
  const resolvedOutcome = asBoolean(point.resolved_outcome)
  const forecastProbability = asNumber(point.forecast_probability)
  const marketBaselineProbability = asNumber(point.market_baseline_probability)

  if (
    !pointId
    || !evaluationId
    || !questionId
    || !marketId
    || !venue
    || !cutoffAt
    || resolvedOutcome == null
    || forecastProbability == null
  ) {
    return null
  }

  return {
    point_id: pointId,
    evaluation_id: evaluationId,
    question_id: questionId,
    market_id: marketId,
    venue,
    cutoff_at: cutoffAt,
    resolved_outcome: resolvedOutcome,
    forecast_probability: forecastProbability,
    market_baseline_probability: marketBaselineProbability,
    brier_score: asNumber(point.brier_score),
    log_loss: asNumber(point.log_loss),
    ece_bucket: asString(point.ece_bucket),
    basis: asString(point.basis),
    comparator_id: asString(point.comparator_id),
    comparator_kind: asString(point.comparator_kind),
    comparator_role: asString(point.comparator_role),
    pipeline_id: asString(point.pipeline_id),
    pipeline_version: asString(point.pipeline_version),
    category: asString(point.category),
    horizon_bucket: asString(point.horizon_bucket),
    liquidity_usd: asNumber(point.liquidity_usd),
    volume_24h_usd: asNumber(point.volume_24h_usd),
    spread_bps: asNumber(point.spread_bps),
    fee_bps: asNumber(point.fee_bps),
    size_usd: asNumber(point.size_usd),
  }
}

function extractResolvedHistoryPoints(artifacts: Array<{ artifact_type: string; payload: unknown }>): ResolvedHistoryPoint[] {
  const resolvedHistoryArtifact = artifacts.find((artifact) => artifact.artifact_type === 'resolved_history')
  if (!resolvedHistoryArtifact || !resolvedHistoryArtifact.payload || typeof resolvedHistoryArtifact.payload !== 'object') {
    return []
  }

  const payload = resolvedHistoryArtifact.payload as Record<string, unknown>
  const points = Array.isArray(payload.points) ? payload.points : []
  return points
    .map((point) => normalizeResolvedHistoryPoint(point))
    .filter((point): point is ResolvedHistoryPoint => point != null)
}

export function extractForecastEvaluationHistoryFromArtifacts(
  artifacts: Array<{ artifact_type: string; payload: unknown }>,
): ForecastEvaluationRecord[] {
  const deduped = new Map<string, ForecastEvaluationRecord>()
  for (const point of extractResolvedHistoryPoints(artifacts)) {
    const record = toForecastEvaluationRecordFromResolvedHistoryPoint(point)
    deduped.set(record.evaluation_id, record)
  }
  return [...deduped.values()].sort(compareCutoff)
}

export function resolvePredictionMarketEvaluationHistory(
  input: ResolvePredictionMarketEvaluationHistoryInput,
): PredictionMarketEvaluationHistoryResolution {
  const providedHistory = [...(input.providedHistory ?? [])].sort(compareCutoff)
  if (providedHistory.length > 0) {
    const source = input.providedSource === 'stored_artifact' ? 'stored_runs' : 'request'
    return {
      evaluation_history: providedHistory,
      source,
      source_summary:
        input.providedSource === 'stored_artifact'
          ? `Using ${providedHistory.length} evaluation records already embedded on the source run.`
          : `Using ${providedHistory.length} evaluation records supplied directly on the request.`,
      considered_runs: 0,
      used_runs: 0,
      same_market_records: providedHistory.filter((record) => record.market_id === input.marketId).length,
      same_category_records: 0,
      same_venue_records: 0,
    }
  }

  const searchLimit = Math.max(1, Math.min(input.searchLimit ?? 60, 200))
  const targetRecords = Math.max(1, Math.min(input.targetRecords ?? 120, 1_000))
  const excludedRunIds = new Set(input.excludeRunIds ?? [])
  const targetCategory = inferPredictionMarketCategory(input.marketId)
  const candidateRuns = listPredictionMarketRuns({
    workspaceId: input.workspaceId,
    venue: input.venue,
    limit: searchLimit,
  }).filter((run) => !excludedRunIds.has(run.run_id))

  const groupedRecords = {
    same_market: [] as ForecastEvaluationRecord[],
    same_category: [] as ForecastEvaluationRecord[],
    same_venue: [] as ForecastEvaluationRecord[],
  }
  const usedRunIds = new Set<string>()
  const recordIds = new Set<string>()

  for (const run of candidateRuns) {
    const details = getPredictionMarketRunDetails(run.run_id, input.workspaceId)
    if (!details) continue
    const evaluationHistory = extractForecastEvaluationHistoryFromArtifacts(details.artifacts)
    if (evaluationHistory.length === 0) continue

    for (const record of evaluationHistory) {
      if (recordIds.has(record.evaluation_id)) continue

      if (record.market_id === input.marketId) {
        groupedRecords.same_market.push(record)
        recordIds.add(record.evaluation_id)
        usedRunIds.add(run.run_id)
        continue
      }

      const recordCategory = inferPredictionMarketCategory(record.market_id, record.basis ?? null)
      if (targetCategory != null && recordCategory === targetCategory) {
        groupedRecords.same_category.push(record)
        recordIds.add(record.evaluation_id)
        usedRunIds.add(run.run_id)
        continue
      }

      groupedRecords.same_venue.push(record)
      recordIds.add(record.evaluation_id)
      usedRunIds.add(run.run_id)
    }
  }

  const evaluationHistory = [
    ...groupedRecords.same_market,
    ...groupedRecords.same_category,
    ...groupedRecords.same_venue,
  ]
    .sort(compareCutoff)
    .slice(-targetRecords)

  if (evaluationHistory.length === 0) {
    return {
      evaluation_history: [],
      source: 'none',
      source_summary: 'No local resolved history was available from stored runs.',
      considered_runs: candidateRuns.length,
      used_runs: 0,
      same_market_records: 0,
      same_category_records: 0,
      same_venue_records: 0,
    }
  }

  const labels = uniqueStrings([
    groupedRecords.same_market.length > 0 ? `same_market=${groupedRecords.same_market.length}` : null,
    groupedRecords.same_category.length > 0 ? `same_category=${groupedRecords.same_category.length}` : null,
    groupedRecords.same_venue.length > 0 ? `same_venue=${groupedRecords.same_venue.length}` : null,
  ]).join(', ')

  return {
    evaluation_history: evaluationHistory,
    source: 'stored_runs',
    source_summary: `Resolved ${evaluationHistory.length} local evaluation records from ${usedRunIds.size} stored runs (${labels || 'no buckets'}).`,
    considered_runs: candidateRuns.length,
    used_runs: usedRunIds.size,
    same_market_records: groupedRecords.same_market.length,
    same_category_records: groupedRecords.same_category.length,
    same_venue_records: groupedRecords.same_venue.length,
  }
}
