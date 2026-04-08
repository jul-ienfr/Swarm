export type PredictionMarketsBenchmarkGateComparativeReport = {
  market_only: {
    probability_yes: number | null
  }
  aggregate: {
    probability_yes: number | null
  }
  forecast: {
    forecast_probability_yes: number | null
  }
  abstention: {
    blocks_forecast: boolean
  }
}

export type PredictionMarketsBenchmarkGateEvidenceSource = 'preview_only' | 'out_of_sample'

export type PredictionMarketsBenchmarkGateSummary = {
  verdict?: 'preview_only' | 'blocked_by_abstention' | 'local_benchmark_ready' | 'local_benchmark_blocked'
  status: 'preview_only' | 'blocked_by_abstention'
  promotion_status: 'unproven' | 'eligible' | 'blocked'
  promotion_ready: boolean
  preview_available: boolean
  promotion_evidence: 'unproven' | 'local_benchmark'
  evidence_level: 'benchmark_preview' | 'out_of_sample_promotion_evidence'
  promotion_gate_kind: 'preview_only' | 'local_benchmark'
  promotion_evidence_source?: PredictionMarketsBenchmarkGateEvidenceSource
  promotion_kill_criteria?: string[]
  promotion_blocker_summary?: string | null
  market_only_probability: number | null
  aggregate_probability: number | null
  forecast_probability: number | null
  upliftBps: number | null
  forecast_uplift_bps: number | null
  aggregate_uplift_bps: number | null
  blockers: string[]
  reasons: string[]
  summary: string | null
}

export type PredictionMarketsAsOfBenchmarkComparatorSummaryLike = {
  comparator_id: string
  label: string
  status: 'available' | 'planned'
  mean_edge_delta_bps_vs_market_only: number | null
}

export type PredictionMarketsAsOfBenchmarkPromotionEligibility<
  TComparatorId extends string | null = string | null,
  TComparatorLabel extends string | null = string | null,
  TReplayMode extends string = string,
> = {
  status: 'eligible' | 'blocked'
  basis: 'local_benchmark'
  candidate_comparator_id: TComparatorId
  candidate_comparator_label: TComparatorLabel
  observed_mean_edge_improvement_bps: number
  required_mean_edge_improvement_bps: number
  observed_mean_probability_gap_bps: number
  required_case_count: number
  case_count: number
  blockers: string[]
  reasons: string[]
  source: 'local'
  replay_mode: TReplayMode
  pipeline_id: string
  pipeline_version: string
}

function formatBenchmarkProbability(value: number | null): string | null {
  return value == null ? null : value.toFixed(4)
}

function dedupeStrings(values: Iterable<string | null | undefined>): string[] {
  return Array.from(
    new Set(
      Array.from(values).filter((value): value is string => {
        if (value == null) {
          return false
        }
        const text = String(value).trim()
        return text.length > 0
      }),
    ),
  )
}

function buildPromotionKillCriteria(input: {
  comparativeReport: PredictionMarketsBenchmarkGateComparativeReport | null
  localPromotionEligibility?: Pick<PredictionMarketsAsOfBenchmarkPromotionEligibility, 'status' | 'blockers'> | null
}): string[] {
  const criteria: string[] = []
  if (!input.comparativeReport) {
    criteria.push('missing_comparative_report')
  }
  if (input.comparativeReport?.abstention.blocks_forecast) {
    criteria.push('abstention_blocks_forecast')
  }
  if (input.localPromotionEligibility?.status === 'blocked') {
    criteria.push(...input.localPromotionEligibility.blockers)
    if (input.localPromotionEligibility.blockers.length === 0) {
      criteria.push('local_benchmark_promotion_blocked')
    }
  }
  if (input.localPromotionEligibility?.status === 'eligible' && input.localPromotionEligibility.blockers.length > 0) {
    criteria.push(...input.localPromotionEligibility.blockers)
  }
  if (!input.localPromotionEligibility && !input.comparativeReport?.abstention.blocks_forecast) {
    criteria.push('out_of_sample_unproven')
  }
  return dedupeStrings(criteria)
}

export function summarizePredictionMarketsBenchmarkGate(input: {
  comparativeReport: PredictionMarketsBenchmarkGateComparativeReport | null
  forecastProbabilityYesHint: number | null
  localPromotionEligibility?: Pick<
    PredictionMarketsAsOfBenchmarkPromotionEligibility,
    'status' | 'blockers'
  > | null
}): PredictionMarketsBenchmarkGateSummary {
  const comparative = input.comparativeReport
  if (!comparative) {
    const promotionKillCriteria = buildPromotionKillCriteria(input)
    return {
      verdict: 'preview_only',
      status: 'preview_only',
      promotion_status: 'unproven',
      promotion_ready: false,
      preview_available: false,
      promotion_evidence: 'unproven',
      evidence_level: 'benchmark_preview',
      promotion_gate_kind: 'preview_only',
      promotion_evidence_source: 'preview_only',
      promotion_kill_criteria: promotionKillCriteria,
      promotion_blocker_summary: 'benchmark preview unavailable; out_of_sample_unproven',
      market_only_probability: null,
      aggregate_probability: null,
      forecast_probability: input.forecastProbabilityYesHint ?? null,
      upliftBps: null,
      forecast_uplift_bps: null,
      aggregate_uplift_bps: null,
      blockers: ['missing_comparative_report', 'out_of_sample_unproven'],
      reasons: ['benchmark preview unavailable', 'out_of_sample_unproven'],
      summary: null,
    }
  }

  const marketOnlyProbability = comparative.market_only.probability_yes
  const aggregateProbability = comparative.aggregate.probability_yes
  const forecastProbability = input.forecastProbabilityYesHint ?? comparative.forecast.forecast_probability_yes ?? null
  const forecastUpliftBps =
    marketOnlyProbability != null && forecastProbability != null
      ? Math.round((forecastProbability - marketOnlyProbability) * 10_000)
      : null
  const aggregateUpliftBps =
    marketOnlyProbability != null && aggregateProbability != null
      ? Math.round((aggregateProbability - marketOnlyProbability) * 10_000)
      : null
  const status = comparative.abstention.blocks_forecast ? 'blocked_by_abstention' : 'preview_only'
  const blockers = comparative.abstention.blocks_forecast ? ['abstention_blocks_forecast'] : []
  const reasons = comparative.abstention.blocks_forecast
    ? ['abstention policy blocks forecast']
    : []
  const promotionEvidenceSource: PredictionMarketsBenchmarkGateEvidenceSource = input.localPromotionEligibility
    ? 'out_of_sample'
    : 'preview_only'

  let promotionStatus: PredictionMarketsBenchmarkGateSummary['promotion_status'] = 'unproven'
  if (input.localPromotionEligibility?.status === 'eligible') {
    promotionStatus = 'eligible'
  } else if (comparative.abstention.blocks_forecast || input.localPromotionEligibility?.status === 'blocked') {
    promotionStatus = 'blocked'
  }
  const promotionEvidence: PredictionMarketsBenchmarkGateSummary['promotion_evidence'] =
    input.localPromotionEligibility ? 'local_benchmark' : 'unproven'
  const evidenceLevel: PredictionMarketsBenchmarkGateSummary['evidence_level'] =
    input.localPromotionEligibility ? 'out_of_sample_promotion_evidence' : 'benchmark_preview'
  const promotionGateKind: PredictionMarketsBenchmarkGateSummary['promotion_gate_kind'] =
    input.localPromotionEligibility ? 'local_benchmark' : 'preview_only'

  blockers.push(...(input.localPromotionEligibility?.blockers ?? []))
  if (promotionStatus === 'unproven') {
    blockers.push('out_of_sample_unproven')
  }

  const uniqueBlockers = Array.from(new Set(blockers))
  const promotionKillCriteria = buildPromotionKillCriteria(input)
  if (promotionStatus === 'unproven') {
    reasons.push('out_of_sample_unproven')
  }
  if (promotionStatus === 'eligible') {
    if (uniqueBlockers.length === 0) {
      reasons.push('local benchmark promotion gate is satisfied')
    } else {
      reasons.push('local benchmark promotion gate is blocked')
    }
  }
  if (promotionStatus === 'blocked' && input.localPromotionEligibility?.status === 'blocked') {
    reasons.push('local benchmark promotion gate is blocked')
  }
  const promotionReady = promotionStatus === 'eligible' && uniqueBlockers.length === 0
  const verdict: PredictionMarketsBenchmarkGateSummary['verdict'] =
    status === 'blocked_by_abstention'
      ? 'blocked_by_abstention'
      : promotionReady
        ? 'local_benchmark_ready'
        : promotionStatus === 'blocked' || (input.localPromotionEligibility?.status === 'eligible' && uniqueBlockers.length > 0)
          ? 'local_benchmark_blocked'
          : 'preview_only'
  const promotionBlockerSummary =
    uniqueBlockers.length > 0
      ? uniqueBlockers.join('; ')
      : promotionStatus === 'blocked'
        ? 'local_benchmark_promotion_blocked'
      : promotionReady
        ? 'promotion gate satisfied'
        : 'out_of_sample_unproven'

  const parts = [
    'benchmark gate:',
    marketOnlyProbability != null ? `market_only=${formatBenchmarkProbability(marketOnlyProbability)}` : null,
    aggregateProbability != null ? `aggregate=${formatBenchmarkProbability(aggregateProbability)}` : null,
    forecastProbability != null ? `forecast=${formatBenchmarkProbability(forecastProbability)}` : null,
    forecastUpliftBps != null ? `uplift_vs_market_only=${forecastUpliftBps}bps` : null,
    aggregateUpliftBps != null ? `uplift_vs_aggregate=${aggregateUpliftBps}bps` : null,
    `status=${status}`,
    `promotion=${promotionStatus}`,
    `ready=${promotionReady ? 'yes' : 'no'}`,
    `preview=${comparative ? 'yes' : 'no'}`,
    `evidence=${promotionEvidence}`,
    uniqueBlockers.length > 0 ? `blockers=${uniqueBlockers.join('|')}` : null,
    `out_of_sample=${promotionEvidence}`,
  ].filter((part): part is string => Boolean(part))

  return {
      verdict,
      status,
      promotion_status: promotionStatus,
      promotion_ready: promotionReady,
      preview_available: true,
      promotion_evidence: promotionEvidence,
      evidence_level: evidenceLevel,
      promotion_gate_kind: promotionGateKind,
      promotion_evidence_source: promotionEvidenceSource,
      promotion_kill_criteria: promotionKillCriteria,
      promotion_blocker_summary: promotionBlockerSummary,
      market_only_probability: marketOnlyProbability,
      aggregate_probability: aggregateProbability,
      forecast_probability: forecastProbability,
    upliftBps: forecastUpliftBps,
    forecast_uplift_bps: forecastUpliftBps,
    aggregate_uplift_bps: aggregateUpliftBps,
    blockers: uniqueBlockers,
    reasons,
    summary: parts.join(' '),
  }
}

export function buildPredictionMarketsLocalPromotionEligibility<
  TComparatorId extends string | null,
  TComparatorLabel extends string | null,
  TReplayMode extends string,
>(input: {
  comparatorSummaries?: PredictionMarketsAsOfBenchmarkComparatorSummaryLike[]
  bestComparatorId?: TComparatorId
  bestComparatorLabel?: TComparatorLabel
  bestComparatorEdgeDeltaBps?: number | null
  caseCount: number
  observedMeanProbabilityGapBps: number
  meanCandidateProbability?: number | null
  requiredMeanEdgeImprovementBps?: number
  requiredCaseCount?: number
  marketOnlyComparatorId?: string
  replayMode: TReplayMode
  pipelineId: string
  pipelineVersion: string
}): PredictionMarketsAsOfBenchmarkPromotionEligibility<TComparatorId, TComparatorLabel, TReplayMode> {
  const requiredMeanEdgeImprovementBps = input.requiredMeanEdgeImprovementBps ?? 1
  const requiredCaseCount = input.requiredCaseCount ?? 3

  const comparatorSummaries = input.comparatorSummaries ?? []
  const availableComparatorSummaries = comparatorSummaries.filter((summary) => summary.status === 'available')
  const eligibleComparatorCandidates = availableComparatorSummaries.filter((summary) => {
    const marketOnlyComparatorId = input.marketOnlyComparatorId ?? 'market_only'
    return summary.comparator_id !== marketOnlyComparatorId && (summary.mean_edge_delta_bps_vs_market_only ?? 0) > 0
  })
  const bestComparator = eligibleComparatorCandidates
    .slice()
    .sort((left, right) => (right.mean_edge_delta_bps_vs_market_only ?? -Infinity) - (left.mean_edge_delta_bps_vs_market_only ?? -Infinity))[0]
    ?? null

  const resolvedComparatorId = input.bestComparatorId ?? (bestComparator?.comparator_id ?? null)
  const resolvedComparatorLabel = input.bestComparatorLabel ?? (bestComparator?.label ?? null)
  const resolvedComparatorEdgeDeltaBps = input.bestComparatorEdgeDeltaBps ?? (bestComparator?.mean_edge_delta_bps_vs_market_only ?? null)
  const marketOnlyComparatorId = input.marketOnlyComparatorId ?? 'market_only'

  const blockers: string[] = []
  if (input.caseCount < requiredCaseCount) {
    blockers.push('insufficient_case_count')
  }
  if (!resolvedComparatorId || !resolvedComparatorLabel || resolvedComparatorEdgeDeltaBps == null) {
    blockers.push('no_comparator_beats_market_only')
  } else if (resolvedComparatorId === marketOnlyComparatorId) {
    blockers.push('market_only_is_not_a_candidate')
  } else if (resolvedComparatorEdgeDeltaBps < requiredMeanEdgeImprovementBps) {
    blockers.push('edge_improvement_below_threshold')
  }
  if ('meanCandidateProbability' in input && input.meanCandidateProbability == null) {
    blockers.push('missing_candidate_probabilities')
  }
  const reasons: string[] = []
  if (blockers.length === 0 && resolvedComparatorId && resolvedComparatorLabel && resolvedComparatorEdgeDeltaBps != null) {
    reasons.push(
      `best comparator ${resolvedComparatorLabel} improves mean edge by ${resolvedComparatorEdgeDeltaBps} bps over market-only`,
    )
    reasons.push(
      `mean probability gap is ${input.observedMeanProbabilityGapBps} bps across ${input.caseCount} frozen cases`,
    )
  }

  return {
    status: blockers.length === 0 ? 'eligible' : 'blocked',
    basis: 'local_benchmark',
    candidate_comparator_id: resolvedComparatorId as TComparatorId,
    candidate_comparator_label: resolvedComparatorLabel as TComparatorLabel,
    observed_mean_edge_improvement_bps: resolvedComparatorEdgeDeltaBps ?? 0,
    required_mean_edge_improvement_bps: requiredMeanEdgeImprovementBps,
    observed_mean_probability_gap_bps: input.observedMeanProbabilityGapBps,
    required_case_count: requiredCaseCount,
    case_count: input.caseCount,
    blockers,
    reasons,
    source: 'local',
    replay_mode: input.replayMode,
    pipeline_id: input.pipelineId,
    pipeline_version: input.pipelineVersion,
  }
}
