import { createHash } from 'node:crypto'
import {
  asOfEvidenceSetSchema,
  calibrationSnapshotSchema,
  decisionPacketSchema,
  PREDICTION_MARKETS_BASELINE_MODEL,
  PREDICTION_MARKETS_SCHEMA_VERSION,
  forecastEvaluationRecordSchema,
  type EvidencePacket,
  type DecisionPacket,
  type ForecastPacket,
  type ForecastEvaluationRecord,
  type AsOfEvidenceSet,
  type CalibrationSnapshot,
  type MarketRecommendationPacket,
  type MarketSnapshot,
  type PredictionMarketSide,
  type PredictionMarketVenue,
  type ResolutionPolicy,
  marketSnapshotSchema,
} from '@/lib/prediction-markets/schemas'
import {
  buildEvidencePackets,
  buildForecastPacket,
  buildRecommendationPacket,
  buildResolutionPolicy,
} from '@/lib/prediction-markets/service'
import {
  buildPredictionMarketsLocalPromotionEligibility,
} from '@/lib/prediction-markets/benchmark-gate'

const PREDICTION_MARKETS_AS_OF_BENCHMARK_DATASET_ID = 'prediction-markets-as-of-benchmark'
const PREDICTION_MARKETS_AS_OF_BENCHMARK_DATASET_VERSION = 'poly-024-asof-v1'
const PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_ID = 'prediction-markets-as-of-benchmark-pipeline'
const PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_VERSION = 'poly-024-asof-v1'
const PREDICTION_MARKETS_AS_OF_BENCHMARK_REPLAY_MODE = 'local_frozen_replay'

export type PredictionMarketsFrozenBenchmarkCase = {
  id: string
  label: string
  snapshot: MarketSnapshot
  thesisProbability?: number
  thesisRationale?: string
  minEdgeBps?: number
  maxSpreadBps?: number
  expected: {
    resolutionStatus: ResolutionPolicy['status']
    manualReviewRequired: boolean
    forecastBasis: ForecastPacket['basis']
    action: MarketRecommendationPacket['action']
    side: PredictionMarketSide | null
    riskFlags: string[]
    evidenceTypes: EvidencePacket['type'][]
    resolutionReasonsInclude?: string[]
    recommendationReasonsInclude?: string[]
  }
}

export type PredictionMarketsFrozenBenchmarkResult = {
  fixture: PredictionMarketsFrozenBenchmarkCase
  resolutionPolicy: ResolutionPolicy
  evidencePackets: EvidencePacket[]
  forecast: ForecastPacket
  recommendation: MarketRecommendationPacket
  marketOnly: {
    evidencePackets: EvidencePacket[]
    forecast: ForecastPacket
    recommendation: MarketRecommendationPacket
  }
  comparison: {
    market_only_action: MarketRecommendationPacket['action']
    market_only_edge_bps: number
    forecast_drift_bps: number
    calibration_gap_bps: number
    closing_line_quality_bps: number
    edge_improvement_bps: number
  }
  as_of?: PredictionMarketsAsOfBenchmarkResult
}

export type PredictionMarketsAsOfBenchmarkResult = {
  cutoff_at: string
  comparison_label: string
  evaluation_record: ForecastEvaluationRecord
  evidence_set: AsOfEvidenceSet
  comparators: PredictionMarketsAsOfBenchmarkComparator[]
  metadata: PredictionMarketsAsOfBenchmarkCaseMetadata
}

export type PredictionMarketsAsOfBenchmarkDatasetMetadata = {
  dataset_id: string
  dataset_version: string
  dataset_revision: string
  replay_mode: typeof PREDICTION_MARKETS_AS_OF_BENCHMARK_REPLAY_MODE
  pipeline_id: string
  pipeline_version: string
  comparator_ids: PredictionMarketsAsOfBenchmarkComparatorId[]
  comparator_labels: PredictionMarketsAsOfBenchmarkComparatorLabel[]
}

export type PredictionMarketsAsOfBenchmarkCaseMetadata = PredictionMarketsAsOfBenchmarkDatasetMetadata & {
  fixture_id: string
  market_id: string
  comparison_label: string
  cutoff_at: string
}

export type PredictionMarketsAsOfBenchmarkRunMetadata = PredictionMarketsAsOfBenchmarkDatasetMetadata & {
  run_id: string
  generated_at: string
  fixture_ids: string[]
  case_count: number
  cutoff_window: {
    start: string
    end: string
  }
}

export type PredictionMarketsAsOfBenchmarkSummary = {
  summary_version: 'as_of_benchmark_summary_v1'
  case_count: number
  mean_forecast_probability_gap_bps: number
  mean_market_only_probability: number
  mean_candidate_probability: number
  mean_market_only_edge_bps: number
  available_comparators: PredictionMarketsAsOfBenchmarkComparatorLabel[]
  planned_comparators: PredictionMarketsAsOfBenchmarkComparatorLabel[]
  comparator_summaries: PredictionMarketsAsOfBenchmarkComparatorSummary[]
  local_promotion_eligibility: PredictionMarketsAsOfBenchmarkPromotionEligibility
  calibration_snapshot: CalibrationSnapshot
  metadata: PredictionMarketsAsOfBenchmarkRunMetadata
}

export type PredictionMarketsAsOfBenchmarkRun = {
  results: PredictionMarketsFrozenBenchmarkResult[]
  summary: PredictionMarketsAsOfBenchmarkSummary
  metadata: PredictionMarketsAsOfBenchmarkRunMetadata
}

export type PredictionMarketsAsOfBenchmarkComparatorId =
  | 'market_only'
  | 'timesfm_microstructure'
  | 'timesfm_event_probability'
  | 'single_llm'
  | 'ensemble'
  | 'decision_packet_assisted'

export type PredictionMarketsAsOfBenchmarkComparatorLabel =
  | 'market-only'
  | 'TimesFM microstructure'
  | 'TimesFM event probability'
  | 'single-LLM'
  | 'ensemble'
  | 'DecisionPacket-assisted'

export type PredictionMarketsAsOfBenchmarkComparatorStatus = 'available' | 'planned'

export type PredictionMarketsAsOfBenchmarkComparator = {
  comparator_id: PredictionMarketsAsOfBenchmarkComparatorId
  label: PredictionMarketsAsOfBenchmarkComparatorLabel
  status: PredictionMarketsAsOfBenchmarkComparatorStatus
  basis: ForecastPacket['basis'] | null
  probability_yes: number | null
  action: MarketRecommendationPacket['action'] | null
  edge_bps: number | null
  evidence_ref_count: number
  notes: string[]
  source: 'local'
  replay_mode: typeof PREDICTION_MARKETS_AS_OF_BENCHMARK_REPLAY_MODE
  pipeline_id: string
  pipeline_version: string
}

export type PredictionMarketsAsOfBenchmarkComparatorSummary = {
  comparator_id: PredictionMarketsAsOfBenchmarkComparatorId
  label: PredictionMarketsAsOfBenchmarkComparatorLabel
  status: PredictionMarketsAsOfBenchmarkComparatorStatus
  available_case_count: number
  mean_probability_yes: number | null
  mean_probability_delta_bps_vs_market_only: number | null
  mean_edge_bps: number | null
  mean_edge_delta_bps_vs_market_only: number | null
  notes: string[]
  source: 'local'
  replay_mode: typeof PREDICTION_MARKETS_AS_OF_BENCHMARK_REPLAY_MODE
  pipeline_id: string
  pipeline_version: string
}

export type PredictionMarketsAsOfBenchmarkPromotionEligibility = {
  status: 'eligible' | 'blocked'
  basis: 'local_benchmark'
  candidate_comparator_id: PredictionMarketsAsOfBenchmarkComparatorId | null
  candidate_comparator_label: PredictionMarketsAsOfBenchmarkComparatorLabel | null
  observed_mean_edge_improvement_bps: number
  required_mean_edge_improvement_bps: number
  observed_mean_probability_gap_bps: number
  required_case_count: number
  case_count: number
  blockers: string[]
  reasons: string[]
  source: 'local'
  replay_mode: typeof PREDICTION_MARKETS_AS_OF_BENCHMARK_REPLAY_MODE
  pipeline_id: string
  pipeline_version: string
}

export type PredictionMarketsFrozenBenchmarkAggregate = {
  case_count: number
  actual_action_counts: Record<MarketRecommendationPacket['action'], number>
  market_only_action_counts: Record<MarketRecommendationPacket['action'], number>
  mean_forecast_drift_bps: number
  mean_calibration_gap_bps: number
  mean_closing_line_quality_bps: number
  mean_edge_improvement_bps: number
}

function buildSnapshot(input: {
  venue: PredictionMarketVenue
  marketId: string
  slug: string
  question: string
  venueType?: 'execution-equivalent' | 'reference-only' | 'experimental'
  outcomes: string[]
  isBinaryYesNo: boolean
  active?: boolean
  closed?: boolean
  acceptingOrders?: boolean
  restricted?: boolean
  liquidityUsd?: number | null
  volumeUsd?: number | null
  volume24hUsd?: number | null
  bestBid?: number | null
  bestAsk?: number | null
  lastTradePrice?: number | null
  tickSize?: number | null
  minOrderSize?: number | null
  endAt?: string
  yesPrice?: number | null
  noPrice?: number | null
  midpointYes?: number | null
  bestBidYes?: number | null
  bestAskYes?: number | null
  spreadBps?: number | null
  book?: MarketSnapshot['book']
  history?: Array<{ timestamp: number; price: number }>
}) {
  const baseUrl = `https://example.com/${input.venue}/${input.slug}`
  const sourceUrls = [baseUrl]
  if (input.book) sourceUrls.push(`${baseUrl}/book`)
  if ((input.history || []).length > 0) sourceUrls.push(`${baseUrl}/prices-history`)

  return marketSnapshotSchema.parse({
    venue: input.venue,
    market: {
      venue: input.venue,
      venue_type: input.venueType ?? 'execution-equivalent',
      market_id: input.marketId,
      slug: input.slug,
      question: input.question,
      outcomes: input.outcomes,
      active: input.active ?? true,
      closed: input.closed ?? false,
      accepting_orders: input.acceptingOrders ?? true,
      restricted: input.restricted ?? false,
      liquidity_usd: input.liquidityUsd ?? null,
      volume_usd: input.volumeUsd ?? null,
      volume_24h_usd: input.volume24hUsd ?? null,
      best_bid: input.bestBid ?? null,
      best_ask: input.bestAsk ?? null,
      last_trade_price: input.lastTradePrice ?? null,
      tick_size: input.tickSize ?? null,
      min_order_size: input.minOrderSize ?? null,
      is_binary_yes_no: input.isBinaryYesNo,
      end_at: input.endAt,
      source_urls: [baseUrl],
    },
    captured_at: '2026-04-08T00:00:00.000Z',
    yes_outcome_index: 0,
    yes_token_id: `${input.marketId}-yes`,
    yes_price: input.yesPrice ?? null,
    no_price: input.noPrice ?? null,
    midpoint_yes: input.midpointYes ?? null,
    best_bid_yes: input.bestBidYes ?? null,
    best_ask_yes: input.bestAskYes ?? null,
    spread_bps: input.spreadBps ?? null,
    book: input.book,
    history: input.history ?? [],
    source_urls: sourceUrls,
  })
}

function buildActionCounts(): Record<MarketRecommendationPacket['action'], number> {
  return {
    bet: 0,
    no_trade: 0,
    wait: 0,
  }
}

function roundToBps(value: number): number {
  return Math.round(value)
}

function computeProbabilityDriftBps(actual: number, baseline: number): number {
  return roundToBps((actual - baseline) * 10_000)
}

function computeClosingLineQualityBps(recommendation: MarketRecommendationPacket): number {
  return roundToBps(recommendation.edge_bps)
}

function buildComparisonLabel(fixture: PredictionMarketsFrozenBenchmarkCase): string {
  return fixture.thesisProbability != null
    ? 'manual_thesis_vs_market_only'
    : 'market_midpoint_vs_market_only'
}

function buildAsOfDatasetMetadata(fixtures: PredictionMarketsFrozenBenchmarkCase[]): PredictionMarketsAsOfBenchmarkDatasetMetadata {
  const comparatorIds = predictionMarketsAsOfComparatorCatalog.map((comparator) => comparator.comparator_id)
  const comparatorLabels = predictionMarketsAsOfComparatorCatalog.map((comparator) => comparator.label)
  const datasetRevision = createHash('sha256').update(JSON.stringify({
    dataset_id: PREDICTION_MARKETS_AS_OF_BENCHMARK_DATASET_ID,
    dataset_version: PREDICTION_MARKETS_AS_OF_BENCHMARK_DATASET_VERSION,
    pipeline_id: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_ID,
    pipeline_version: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_VERSION,
    replay_mode: PREDICTION_MARKETS_AS_OF_BENCHMARK_REPLAY_MODE,
    fixtures: fixtures.map((fixture) => ({
      fixture_id: fixture.id,
      market_id: fixture.snapshot.market.market_id,
      venue: fixture.snapshot.venue,
      captured_at: fixture.snapshot.captured_at,
      comparison_label: buildComparisonLabel(fixture),
      thesis_probability: fixture.thesisProbability ?? null,
      thesis_rationale: fixture.thesisRationale ?? null,
      expected_action: fixture.expected.action,
      expected_resolution_status: fixture.expected.resolutionStatus,
      expected_risk_flags: fixture.expected.riskFlags,
    })),
    comparators: predictionMarketsAsOfComparatorCatalog,
  })).digest('hex')

  return {
    dataset_id: PREDICTION_MARKETS_AS_OF_BENCHMARK_DATASET_ID,
    dataset_version: PREDICTION_MARKETS_AS_OF_BENCHMARK_DATASET_VERSION,
    dataset_revision: datasetRevision,
    replay_mode: PREDICTION_MARKETS_AS_OF_BENCHMARK_REPLAY_MODE,
    pipeline_id: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_ID,
    pipeline_version: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_VERSION,
    comparator_ids: comparatorIds,
    comparator_labels: comparatorLabels,
  }
}

function buildAsOfCaseMetadata(input: {
  fixture: PredictionMarketsFrozenBenchmarkCase
  cutoffAt: string
  datasetMetadata: PredictionMarketsAsOfBenchmarkDatasetMetadata
}): PredictionMarketsAsOfBenchmarkCaseMetadata {
  return {
    ...input.datasetMetadata,
    fixture_id: input.fixture.id,
    market_id: input.fixture.snapshot.market.market_id,
    comparison_label: buildComparisonLabel(input.fixture),
    cutoff_at: input.cutoffAt,
  }
}

function buildAsOfRunMetadata(input: {
  results: PredictionMarketsFrozenBenchmarkResult[]
  datasetMetadata: PredictionMarketsAsOfBenchmarkDatasetMetadata
  windowStart: string
  windowEnd: string
  generatedAt: string
}): PredictionMarketsAsOfBenchmarkRunMetadata {
  return {
    ...input.datasetMetadata,
    run_id: `as-of:${input.windowStart}:${input.windowEnd}:${input.results.length}`,
    generated_at: input.generatedAt,
    fixture_ids: input.results.map((result) => result.fixture.id),
    case_count: input.results.length,
    cutoff_window: {
      start: input.windowStart,
      end: input.windowEnd,
    },
  }
}

const predictionMarketsAsOfComparatorCatalog: Array<{
  comparator_id: PredictionMarketsAsOfBenchmarkComparatorId
  label: PredictionMarketsAsOfBenchmarkComparatorLabel
}> = [
  {
    comparator_id: 'market_only',
    label: 'market-only',
  },
  {
    comparator_id: 'timesfm_microstructure',
    label: 'TimesFM microstructure',
  },
  {
    comparator_id: 'timesfm_event_probability',
    label: 'TimesFM event probability',
  },
  {
    comparator_id: 'single_llm',
    label: 'single-LLM',
  },
  {
    comparator_id: 'ensemble',
    label: 'ensemble',
  },
  {
    comparator_id: 'decision_packet_assisted',
    label: 'DecisionPacket-assisted',
  },
]

function uniqueEvidenceRefs(...evidenceRefGroups: string[][]): string[] {
  return [...new Set(evidenceRefGroups.flat())]
}

function clampProbability(value: number): number {
  return Math.min(1, Math.max(0, value))
}

function buildComparatorForecastPacket(input: {
  comparatorId: Exclude<PredictionMarketsAsOfBenchmarkComparatorId, 'market_only'>
  fixture: PredictionMarketsFrozenBenchmarkCase
  result: Omit<PredictionMarketsFrozenBenchmarkResult, 'as_of'>
  basis: ForecastPacket['basis']
  probabilityYes: number
  confidence?: number
  evidenceRefs: string[]
  rationale: string
  comparatorKind: ForecastPacket['comparator_kind']
}): ForecastPacket {
  return {
    schema_version: PREDICTION_MARKETS_SCHEMA_VERSION,
    market_id: input.fixture.snapshot.market.market_id,
    venue: input.fixture.snapshot.venue,
    basis: input.basis,
    model: PREDICTION_MARKETS_BASELINE_MODEL,
    probability_yes: Number(clampProbability(input.probabilityYes).toFixed(6)),
    confidence: Number((input.confidence ?? input.result.forecast.confidence).toFixed(4)),
    rationale: input.rationale,
    evidence_refs: input.evidenceRefs,
    comparator_id: input.comparatorId,
    comparator_kind: input.comparatorKind,
    pipeline_id: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_ID,
    pipeline_version: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_VERSION,
    produced_at: input.result.forecast.produced_at,
  }
}

function extractDecisionPacketFromEvidencePackets(
  evidencePackets: EvidencePacket[],
): DecisionPacket | null {
  for (const packet of evidencePackets) {
    if (packet.type !== 'system_note') continue
    const maybeDecisionPacket = packet.metadata.decision_packet
    const parsed = decisionPacketSchema.safeParse(maybeDecisionPacket)
    if (parsed.success) return parsed.data
  }

  return null
}

function buildComparatorRecommendation(input: {
  fixture: PredictionMarketsFrozenBenchmarkCase
  resolutionPolicy: ResolutionPolicy
  forecast: ForecastPacket
  minEdgeBps?: number
  maxSpreadBps?: number
}) {
  return buildRecommendationPacket({
    snapshot: input.fixture.snapshot,
    resolutionPolicy: input.resolutionPolicy,
    forecast: input.forecast,
    minEdgeBps: input.minEdgeBps ?? input.fixture.minEdgeBps,
    maxSpreadBps: input.maxSpreadBps ?? input.fixture.maxSpreadBps,
  })
}

function buildAvailableComparator(input: {
  comparatorId: Exclude<PredictionMarketsAsOfBenchmarkComparatorId, 'market_only'>
  fixture: PredictionMarketsFrozenBenchmarkCase
  result: Omit<PredictionMarketsFrozenBenchmarkResult, 'as_of'>
}): PredictionMarketsAsOfBenchmarkComparator {
  const marketOnlyEvidenceRefs = input.result.marketOnly.evidencePackets.map((packet) => packet.evidence_id)
  const candidateEvidenceRefs = input.result.evidencePackets.map((packet) => packet.evidence_id)
  const decisionPacket = extractDecisionPacketFromEvidencePackets(input.result.evidencePackets)

  switch (input.comparatorId) {
    case 'single_llm': {
      const forecast = buildComparatorForecastPacket({
        comparatorId: input.comparatorId,
        fixture: input.fixture,
        result: input.result,
        basis: input.result.forecast.basis,
        probabilityYes: input.result.forecast.probability_yes,
        confidence: input.result.forecast.confidence,
        evidenceRefs: candidateEvidenceRefs,
        rationale: 'Frozen candidate forecast replayed locally as a single-model proxy.',
        comparatorKind: 'single_llm',
      })
      const recommendation = buildComparatorRecommendation({
        fixture: input.fixture,
        resolutionPolicy: input.result.resolutionPolicy,
        forecast,
      })

      return {
        comparator_id: input.comparatorId,
        label: 'single-LLM',
        status: 'available',
        basis: forecast.basis,
        probability_yes: forecast.probability_yes,
        action: recommendation.action,
        edge_bps: roundToBps(recommendation.edge_bps),
        evidence_ref_count: forecast.evidence_refs.length,
        notes: ['available now via deterministic local single-model proxy over the frozen candidate replay'],
        source: 'local',
        replay_mode: PREDICTION_MARKETS_AS_OF_BENCHMARK_REPLAY_MODE,
        pipeline_id: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_ID,
        pipeline_version: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_VERSION,
      }
    }
    case 'timesfm_microstructure': {
      const forecast = buildComparatorForecastPacket({
        comparatorId: input.comparatorId,
        fixture: input.fixture,
        result: input.result,
        basis: 'timesfm_microstructure',
        probabilityYes: input.result.forecast.basis === 'timesfm_microstructure'
          ? input.result.forecast.probability_yes
          : input.result.forecast.probability_yes,
        confidence: input.result.forecast.confidence,
        evidenceRefs: candidateEvidenceRefs,
        rationale: 'Local replay of the TimesFM microstructure candidate stored on the frozen candidate path.',
        comparatorKind: 'candidate_model',
      })
      const recommendation = buildComparatorRecommendation({
        fixture: input.fixture,
        resolutionPolicy: input.result.resolutionPolicy,
        forecast,
      })

      return {
        comparator_id: input.comparatorId,
        label: 'TimesFM microstructure',
        status: 'available',
        basis: forecast.basis,
        probability_yes: forecast.probability_yes,
        action: recommendation.action,
        edge_bps: roundToBps(recommendation.edge_bps),
        evidence_ref_count: forecast.evidence_refs.length,
        notes: ['available now via the locally persisted TimesFM microstructure candidate replay'],
        source: 'local',
        replay_mode: PREDICTION_MARKETS_AS_OF_BENCHMARK_REPLAY_MODE,
        pipeline_id: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_ID,
        pipeline_version: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_VERSION,
      }
    }
    case 'timesfm_event_probability': {
      const probabilityYes = input.result.forecast.probability_yes
      const forecast = buildComparatorForecastPacket({
        comparatorId: input.comparatorId,
        fixture: input.fixture,
        result: input.result,
        basis: 'timesfm_event_probability',
        probabilityYes,
        confidence: input.result.forecast.confidence,
        evidenceRefs: candidateEvidenceRefs,
        rationale: 'Bench-only replay surface for the TimesFM event probability lane.',
        comparatorKind: 'candidate_model',
      })
      const recommendation = buildComparatorRecommendation({
        fixture: input.fixture,
        resolutionPolicy: input.result.resolutionPolicy,
        forecast,
      })

      return {
        comparator_id: input.comparatorId,
        label: 'TimesFM event probability',
        status: 'available',
        basis: forecast.basis,
        probability_yes: forecast.probability_yes,
        action: recommendation.action,
        edge_bps: roundToBps(recommendation.edge_bps),
        evidence_ref_count: forecast.evidence_refs.length,
        notes: ['bench-only comparator for the TimesFM event lane; fair value remains unchanged in v1'],
        source: 'local',
        replay_mode: PREDICTION_MARKETS_AS_OF_BENCHMARK_REPLAY_MODE,
        pipeline_id: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_ID,
        pipeline_version: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_VERSION,
      }
    }
    case 'ensemble': {
      const ensembleProbability = (input.result.forecast.probability_yes + input.result.marketOnly.forecast.probability_yes) / 2
      const forecast = buildComparatorForecastPacket({
        comparatorId: input.comparatorId,
        fixture: input.fixture,
        result: input.result,
        basis: input.result.forecast.basis,
        probabilityYes: ensembleProbability,
        confidence: (input.result.forecast.confidence + input.result.marketOnly.forecast.confidence) / 2,
        evidenceRefs: uniqueEvidenceRefs(candidateEvidenceRefs, marketOnlyEvidenceRefs),
        rationale: 'Deterministic local ensemble of the frozen candidate and market-only replays.',
        comparatorKind: 'ensemble',
      })
      const recommendation = buildComparatorRecommendation({
        fixture: input.fixture,
        resolutionPolicy: input.result.resolutionPolicy,
        forecast,
      })

      return {
        comparator_id: input.comparatorId,
        label: 'ensemble',
        status: 'available',
        basis: forecast.basis,
        probability_yes: forecast.probability_yes,
        action: recommendation.action,
        edge_bps: roundToBps(recommendation.edge_bps),
        evidence_ref_count: forecast.evidence_refs.length,
        notes: ['available now via deterministic local ensemble over frozen candidate and market-only replays'],
        source: 'local',
        replay_mode: PREDICTION_MARKETS_AS_OF_BENCHMARK_REPLAY_MODE,
        pipeline_id: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_ID,
        pipeline_version: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_VERSION,
      }
    }
    case 'decision_packet_assisted': {
      const comparatorKind = 'decision_packet_assisted'
      const probabilityYes = decisionPacket?.probability_estimate ??
        ((input.result.forecast.probability_yes * 0.7) + (input.result.marketOnly.forecast.probability_yes * 0.3))
      const forecast = buildComparatorForecastPacket({
        comparatorId: input.comparatorId,
        fixture: input.fixture,
        result: input.result,
        basis: input.result.forecast.basis,
        probabilityYes,
        confidence: decisionPacket
          ? Number(((decisionPacket.confidence_band.low + decisionPacket.confidence_band.high) / 2).toFixed(4))
          : (input.result.forecast.confidence + input.result.marketOnly.forecast.confidence) / 2,
        evidenceRefs: decisionPacket
          ? uniqueEvidenceRefs(candidateEvidenceRefs, marketOnlyEvidenceRefs, [`${input.fixture.snapshot.market.market_id}:decision-packet`])
          : uniqueEvidenceRefs(candidateEvidenceRefs, marketOnlyEvidenceRefs),
        rationale: decisionPacket
          ? decisionPacket.rationale_summary
          : 'No frozen DecisionPacket artifact is present, so a deterministic local DecisionPacket-assisted proxy is used.',
        comparatorKind,
      })
      const recommendation = buildComparatorRecommendation({
        fixture: input.fixture,
        resolutionPolicy: input.result.resolutionPolicy,
        forecast,
      })

      return {
        comparator_id: input.comparatorId,
        label: 'DecisionPacket-assisted',
        status: 'available',
        basis: forecast.basis,
        probability_yes: forecast.probability_yes,
        action: recommendation.action,
        edge_bps: roundToBps(recommendation.edge_bps),
        evidence_ref_count: forecast.evidence_refs.length,
        notes: decisionPacket
          ? ['available now via frozen DecisionPacket replay']
          : ['available now via deterministic local DecisionPacket-assisted proxy; no frozen DecisionPacket artifact is present in this benchmark'],
        source: 'local',
        replay_mode: PREDICTION_MARKETS_AS_OF_BENCHMARK_REPLAY_MODE,
        pipeline_id: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_ID,
        pipeline_version: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_VERSION,
      }
    }
  }
}

function buildAsOfComparators(input: {
  fixture: PredictionMarketsFrozenBenchmarkCase
  result: Omit<PredictionMarketsFrozenBenchmarkResult, 'as_of'>
}): PredictionMarketsAsOfBenchmarkComparator[] {
  return predictionMarketsAsOfComparatorCatalog.map((comparator) => {
    if (comparator.comparator_id === 'market_only') {
      return {
        comparator_id: comparator.comparator_id,
        label: comparator.label,
        status: 'available',
        basis: input.result.marketOnly.forecast.basis,
        probability_yes: input.result.marketOnly.forecast.probability_yes,
        action: input.result.marketOnly.recommendation.action,
        edge_bps: roundToBps(input.result.marketOnly.recommendation.edge_bps),
        evidence_ref_count: input.result.marketOnly.evidencePackets.length,
        notes: ['available now via frozen market replay baseline'],
        source: 'local',
        replay_mode: PREDICTION_MARKETS_AS_OF_BENCHMARK_REPLAY_MODE,
        pipeline_id: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_ID,
        pipeline_version: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_VERSION,
      }
    }

    return buildAvailableComparator({
      comparatorId: comparator.comparator_id,
      fixture: input.fixture,
      result: input.result,
    })
  })
}

function buildAsOfEvidenceSet(input: {
  fixture: PredictionMarketsFrozenBenchmarkCase
  result: PredictionMarketsFrozenBenchmarkResult
  cutoffAt: string
  datasetMetadata: PredictionMarketsAsOfBenchmarkDatasetMetadata
}): AsOfEvidenceSet {
  const fallbackComparatorId = input.result.forecast.basis === 'manual_thesis'
    ? 'candidate_manual_thesis'
    : 'candidate_market_midpoint'
  return asOfEvidenceSetSchema.parse({
    evidence_set_id: `${input.fixture.id}:as-of:${input.cutoffAt}`,
    market_id: input.fixture.snapshot.market.market_id,
    cutoff_at: input.cutoffAt,
    evidence_refs: input.result.evidencePackets.map((packet) => packet.evidence_id),
    market_only_evidence_refs: input.result.marketOnly.evidencePackets.map((packet) => packet.evidence_id),
    candidate_evidence_refs: input.result.evidencePackets.map((packet) => packet.evidence_id),
    retrieval_policy: 'frozen_as_of_replay',
    freshness_summary: [
      `cutoff=${input.cutoffAt}`,
      `candidate_basis=${input.result.forecast.basis}`,
      `market_only_basis=${input.result.marketOnly.forecast.basis}`,
    ].join('; '),
    provenance_summary: [
      `candidate_refs=${input.result.evidencePackets.map((packet) => packet.evidence_id).join(',') || 'none'}`,
      `market_only_refs=${input.result.marketOnly.evidencePackets.map((packet) => packet.evidence_id).join(',') || 'none'}`,
    ].join('; '),
    comparison_label: buildComparisonLabel(input.fixture),
    comparator_id: input.result.forecast.comparator_id ?? fallbackComparatorId,
    pipeline_id: input.datasetMetadata.pipeline_id,
    pipeline_version: input.datasetMetadata.pipeline_version,
  })
}

function buildForecastEvaluationRecord(input: {
  fixture: PredictionMarketsFrozenBenchmarkCase
  result: PredictionMarketsFrozenBenchmarkResult
  cutoffAt: string
  datasetMetadata: PredictionMarketsAsOfBenchmarkDatasetMetadata
}): ForecastEvaluationRecord {
  const fallbackComparatorId = input.result.forecast.basis === 'manual_thesis'
    ? 'candidate_manual_thesis'
    : 'candidate_market_midpoint'
  return forecastEvaluationRecordSchema.parse({
    evaluation_id: `${input.fixture.id}:forecast:${input.cutoffAt}`,
    question_id: input.fixture.id,
    market_id: input.fixture.snapshot.market.market_id,
    venue: input.fixture.snapshot.venue,
    cutoff_at: input.cutoffAt,
    forecast_probability: input.result.forecast.probability_yes,
    market_baseline_probability: input.result.marketOnly.forecast.probability_yes,
    resolved_outcome: null,
    brier_score: null,
    log_loss: null,
    ece_bucket: 'unresolved_as_of',
    abstain_flag: input.result.recommendation.action !== 'bet',
    basis: input.result.forecast.basis,
    comparison_label: buildComparisonLabel(input.fixture),
    comparator_id: input.result.forecast.comparator_id ?? fallbackComparatorId,
    comparator_kind: input.result.forecast.comparator_kind ?? 'candidate_model',
    comparator_role: 'candidate',
    pipeline_id: input.datasetMetadata.pipeline_id,
    pipeline_version: input.datasetMetadata.pipeline_version,
  })
}

function buildAsOfBenchmarkResult(input: {
  fixture: PredictionMarketsFrozenBenchmarkCase
  result: Omit<PredictionMarketsFrozenBenchmarkResult, 'as_of'>
  cutoffAt?: string
  datasetMetadata: PredictionMarketsAsOfBenchmarkDatasetMetadata
}): PredictionMarketsAsOfBenchmarkResult {
  const cutoffAt = input.cutoffAt ?? input.fixture.snapshot.captured_at
  return {
    cutoff_at: cutoffAt,
    comparison_label: buildComparisonLabel(input.fixture),
    evaluation_record: buildForecastEvaluationRecord({
      fixture: input.fixture,
      result: input.result,
      cutoffAt,
      datasetMetadata: input.datasetMetadata,
    }),
    evidence_set: buildAsOfEvidenceSet({
      fixture: input.fixture,
      result: input.result,
      cutoffAt,
      datasetMetadata: input.datasetMetadata,
    }),
    comparators: buildAsOfComparators({
      fixture: input.fixture,
      result: input.result,
    }),
    metadata: buildAsOfCaseMetadata({
      fixture: input.fixture,
      cutoffAt,
      datasetMetadata: input.datasetMetadata,
    }),
  }
}

export function summarizePredictionMarketsAsOfBenchmark(
  results: PredictionMarketsFrozenBenchmarkResult[] = runPredictionMarketsFrozenBenchmark(),
): PredictionMarketsAsOfBenchmarkSummary {
  const datasetMetadata = buildAsOfDatasetMetadata(results.map((result) => result.fixture))
  const asOfResults = results.map((result) =>
    result.as_of ?? buildAsOfBenchmarkResult({
      fixture: result.fixture,
      result,
      datasetMetadata,
    }),
  )
  const evaluationRecords = asOfResults.map((result) => result.evaluation_record)
  const probabilityGaps = evaluationRecords.map((record) =>
    Math.abs(record.forecast_probability - record.market_baseline_probability),
  )
  const mean = (values: number[]) => (
    values.length > 0
      ? values.reduce((sum, value) => sum + value, 0) / values.length
      : 0
  )
  const meanOrNull = (values: number[]) => (
    values.length > 0
      ? Number(mean(values).toFixed(6))
      : null
  )
  const meanOrRoundedBps = (values: number[]) => (
    values.length > 0
      ? roundToBps(mean(values))
      : 0
  )
  const windowStart = results
    .map((result) => result.as_of?.cutoff_at ?? result.fixture.snapshot.captured_at)
    .sort()[0] ?? results[0]?.fixture.snapshot.captured_at ?? new Date().toISOString()
  const windowEndCandidates = results
    .map((result) => result.as_of?.cutoff_at ?? result.fixture.snapshot.captured_at)
    .sort()
  const windowEnd = windowEndCandidates[windowEndCandidates.length - 1]
    ?? results[0]?.fixture.snapshot.captured_at
    ?? new Date().toISOString()
  const generatedAt = new Date().toISOString()
  const runMetadata = buildAsOfRunMetadata({
    results,
    datasetMetadata,
    windowStart,
    windowEnd,
    generatedAt,
  })
  const marketOnlyComparatorId: PredictionMarketsAsOfBenchmarkComparatorId = 'market_only'
  const marketOnlyComparatorSummary = asOfResults
    .map((result) => result.comparators.find((comparator) => comparator.comparator_id === marketOnlyComparatorId))
    .filter((comparator): comparator is PredictionMarketsAsOfBenchmarkComparator => comparator != null)
  const marketOnlyMeanProbabilityYes = meanOrNull(
    marketOnlyComparatorSummary
      .map((comparator) => comparator.probability_yes)
      .filter((value): value is number => value != null),
  ) ?? 0
  const marketOnlyMeanEdgeBps = meanOrRoundedBps(
    marketOnlyComparatorSummary
      .map((comparator) => comparator.edge_bps ?? 0)
      .filter((value): value is number => value != null),
  )
  const comparatorSummaries = predictionMarketsAsOfComparatorCatalog.map((catalogEntry) => {
    const comparatorEntries = asOfResults
      .map((result) => result.comparators.find((comparator) => comparator.comparator_id === catalogEntry.comparator_id))
      .filter((comparator): comparator is PredictionMarketsAsOfBenchmarkComparator => comparator != null)
    const availableEntries = comparatorEntries.filter((comparator) => comparator.status === 'available')
    const meanProbabilityYes = meanOrNull(
      availableEntries
        .map((comparator) => comparator.probability_yes)
        .filter((value): value is number => value != null),
    )
    const meanEdgeBps = meanOrNull(
      availableEntries
        .map((comparator) => comparator.edge_bps)
        .filter((value): value is number => value != null),
    )
    const meanProbabilityDeltaBpsVsMarketOnly = meanProbabilityYes != null
      ? roundToBps((meanProbabilityYes - marketOnlyMeanProbabilityYes) * 10_000)
      : null
    const meanEdgeDeltaBpsVsMarketOnly = meanEdgeBps != null
      ? roundToBps(meanEdgeBps - marketOnlyMeanEdgeBps)
      : null

    return {
      comparator_id: catalogEntry.comparator_id,
      label: catalogEntry.label,
      status: availableEntries.length > 0 ? 'available' : 'planned',
      available_case_count: availableEntries.length,
      mean_probability_yes: meanProbabilityYes,
      mean_probability_delta_bps_vs_market_only: meanProbabilityDeltaBpsVsMarketOnly,
      mean_edge_bps: meanEdgeBps,
      mean_edge_delta_bps_vs_market_only: meanEdgeDeltaBpsVsMarketOnly,
      notes: availableEntries[0]?.notes ?? comparatorEntries[0]?.notes ?? [],
      source: 'local',
      replay_mode: PREDICTION_MARKETS_AS_OF_BENCHMARK_REPLAY_MODE,
      pipeline_id: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_ID,
      pipeline_version: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_VERSION,
    } satisfies PredictionMarketsAsOfBenchmarkComparatorSummary
  })
  const observedMeanProbabilityGapBps = roundToBps(mean(
    evaluationRecords.map((record) => Math.abs(record.forecast_probability - record.market_baseline_probability) * 10_000),
  ))
  const localPromotionEligibility = buildPredictionMarketsLocalPromotionEligibility({
    comparatorSummaries,
    caseCount: results.length,
    observedMeanProbabilityGapBps,
    meanCandidateProbability: meanOrNull(evaluationRecords.map((record) => record.forecast_probability)),
    requiredMeanEdgeImprovementBps: 1,
    requiredCaseCount: 3,
    marketOnlyComparatorId,
    replayMode: PREDICTION_MARKETS_AS_OF_BENCHMARK_REPLAY_MODE,
    pipelineId: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_ID,
    pipelineVersion: PREDICTION_MARKETS_AS_OF_BENCHMARK_PIPELINE_VERSION,
  }) as PredictionMarketsAsOfBenchmarkPromotionEligibility

  return {
    summary_version: 'as_of_benchmark_summary_v1',
    case_count: results.length,
    mean_forecast_probability_gap_bps: roundToBps(mean(probabilityGaps) * 10_000),
    mean_market_only_probability: Number(mean(evaluationRecords.map((record) => record.market_baseline_probability)).toFixed(6)),
    mean_candidate_probability: Number(mean(evaluationRecords.map((record) => record.forecast_probability)).toFixed(6)),
    mean_market_only_edge_bps: marketOnlyMeanEdgeBps,
    available_comparators: comparatorSummaries
      .filter((summary) => summary.status === 'available')
      .map((summary) => summary.label),
    planned_comparators: comparatorSummaries
      .filter((summary) => summary.status === 'planned')
      .map((summary) => summary.label),
    comparator_summaries: comparatorSummaries,
    local_promotion_eligibility: localPromotionEligibility,
    calibration_snapshot: calibrationSnapshotSchema.parse({
      snapshot_id: `as-of:${windowStart}:${windowEnd}:${results.length}`,
      model_family: PREDICTION_MARKETS_BASELINE_MODEL,
      market_family: 'binary_yes_no',
      horizon_bucket: 'frozen_as_of',
      window_start: windowStart,
      window_end: windowEnd,
      calibration_method: 'as_of_proxy',
      ece: results.length > 0
        ? Math.min(1, probabilityGaps.reduce((sum, gap) => sum + gap, 0) / results.length)
        : 0,
      sharpness: results.length > 0
        ? Math.min(1, evaluationRecords.reduce((sum, record) => sum + Math.abs(record.forecast_probability - 0.5) * 2, 0) / results.length)
        : 0,
      coverage: results.length > 0
        ? evaluationRecords.filter((record) => record.basis === 'manual_thesis').length / results.length
        : 0,
      sample_size: results.length,
      comparator_id: datasetMetadata.comparator_ids[0],
      pipeline_id: datasetMetadata.pipeline_id,
      pipeline_version: datasetMetadata.pipeline_version,
    }),
    metadata: runMetadata,
  }
}

export function runPredictionMarketsAsOfBenchmark(
  results: PredictionMarketsFrozenBenchmarkResult[] = runPredictionMarketsFrozenBenchmark(),
): PredictionMarketsAsOfBenchmarkRun {
  const summary = summarizePredictionMarketsAsOfBenchmark(results)
  return {
    results,
    summary,
    metadata: summary.metadata,
  }
}

function buildMarketOnlyBenchmark(input: {
  snapshot: MarketSnapshot
  resolutionPolicy: ResolutionPolicy
  minEdgeBps?: number
  maxSpreadBps?: number
}) {
  const evidencePackets = buildEvidencePackets({
    snapshot: input.snapshot,
  })
  const forecast = buildForecastPacket({
    snapshot: input.snapshot,
    evidencePackets,
  })
  const recommendation = buildRecommendationPacket({
    snapshot: input.snapshot,
    resolutionPolicy: input.resolutionPolicy,
    forecast,
    minEdgeBps: input.minEdgeBps,
    maxSpreadBps: input.maxSpreadBps,
  })

  return {
    evidencePackets,
    forecast,
    recommendation,
  }
}

export function comparePredictionMarketsBenchmarkResult(
  result: Pick<PredictionMarketsFrozenBenchmarkResult, 'forecast' | 'recommendation' | 'marketOnly'>,
): PredictionMarketsFrozenBenchmarkResult['comparison'] {
  const forecastDriftBps = computeProbabilityDriftBps(
    result.forecast.probability_yes,
    result.marketOnly.forecast.probability_yes,
  )
  const calibrationGapBps = Math.abs(forecastDriftBps)
  const closingLineQualityBps = computeClosingLineQualityBps(result.recommendation)
  const marketOnlyClosingLineQualityBps = computeClosingLineQualityBps(result.marketOnly.recommendation)

  return {
    market_only_action: result.marketOnly.recommendation.action,
    market_only_edge_bps: roundToBps(result.marketOnly.recommendation.edge_bps),
    forecast_drift_bps: forecastDriftBps,
    calibration_gap_bps: calibrationGapBps,
    closing_line_quality_bps: closingLineQualityBps,
    edge_improvement_bps: closingLineQualityBps - marketOnlyClosingLineQualityBps,
  }
}

export const predictionMarketsFrozenBenchmarkCases: PredictionMarketsFrozenBenchmarkCase[] = [
  {
    id: 'polymarket-bet-yes',
    label: 'Polymarket manual thesis with executable Yes edge',
    snapshot: buildSnapshot({
      venue: 'polymarket',
      marketId: 'poly-bet-yes',
      slug: 'will-sample-benchmark-resolve-yes',
      question: 'Will the sample benchmark resolve Yes?',
      outcomes: ['Yes', 'No'],
      isBinaryYesNo: true,
      liquidityUsd: 220_000,
      volumeUsd: 1_200_000,
      volume24hUsd: 150_000,
      bestBid: 0.5,
      bestAsk: 0.52,
      lastTradePrice: 0.51,
      tickSize: 0.01,
      minOrderSize: 5,
      endAt: '2026-12-31T23:59:59.000Z',
      yesPrice: 0.51,
      noPrice: 0.49,
      midpointYes: 0.51,
      bestBidYes: 0.5,
      bestAskYes: 0.52,
      spreadBps: 200,
      book: {
        token_id: 'poly-bet-yes-token',
        market_condition_id: 'poly-cond-bet-yes',
        fetched_at: '2026-04-08T00:00:00.000Z',
        best_bid: 0.5,
        best_ask: 0.52,
        last_trade_price: 0.51,
        tick_size: 0.01,
        min_order_size: 5,
        bids: [
          { price: 0.5, size: 450 },
          { price: 0.49, size: 350 },
        ],
        asks: [
          { price: 0.52, size: 300 },
          { price: 0.53, size: 180 },
        ],
        depth_near_touch: 1_200,
      },
      history: [
        { timestamp: 1712530800, price: 0.48 },
        { timestamp: 1712534400, price: 0.5 },
        { timestamp: 1712538000, price: 0.51 },
      ],
    }),
    thesisProbability: 0.68,
    thesisRationale: 'Independent evidence justifies a materially higher Yes probability.',
    expected: {
      resolutionStatus: 'eligible',
      manualReviewRequired: false,
      forecastBasis: 'manual_thesis',
      action: 'bet',
      side: 'yes',
      riskFlags: [],
      evidenceTypes: ['market_data', 'orderbook', 'history', 'manual_thesis'],
      recommendationReasonsInclude: ['Manual thesis shows +1600 bps edge on Yes'],
    },
  },
  {
    id: 'kalshi-wait-missing-history',
    label: 'Kalshi manual thesis degrades to wait when replay history is missing',
    snapshot: buildSnapshot({
      venue: 'kalshi',
      marketId: 'KXBENCH-YES',
      slug: 'kalshi-benchmark-missing-history',
      question: 'Will the missing-history benchmark stay a no-trade?',
      outcomes: ['Yes', 'No'],
      isBinaryYesNo: true,
      liquidityUsd: 50_000,
      volumeUsd: 400_000,
      volume24hUsd: 80_000,
      bestBid: 0.45,
      bestAsk: 0.47,
      lastTradePrice: 0.46,
      tickSize: 0.01,
      minOrderSize: 1,
      endAt: '2026-11-05T15:00:00.000Z',
      yesPrice: 0.46,
      noPrice: 0.54,
      midpointYes: 0.46,
      bestBidYes: 0.45,
      bestAskYes: 0.47,
      spreadBps: 100,
      book: {
        token_id: 'kalshi-benchmark-token',
        market_condition_id: 'kalshi-cond-wait',
        fetched_at: '2026-04-08T00:00:00.000Z',
        best_bid: 0.45,
        best_ask: 0.47,
        last_trade_price: 0.46,
        tick_size: 0.01,
        min_order_size: 1,
        bids: [
          { price: 0.45, size: 400 },
          { price: 0.44, size: 250 },
        ],
        asks: [
          { price: 0.47, size: 220 },
          { price: 0.48, size: 130 },
        ],
        depth_near_touch: 1_000,
      },
      history: [],
    }),
    thesisProbability: 0.58,
    thesisRationale: 'There may be an edge, but replay evidence is intentionally missing.',
    expected: {
      resolutionStatus: 'eligible',
      manualReviewRequired: false,
      forecastBasis: 'manual_thesis',
      action: 'wait',
      side: null,
      riskFlags: ['missing_history'],
      evidenceTypes: ['market_data', 'orderbook', 'manual_thesis'],
      recommendationReasonsInclude: ['Manual thesis runs require a frozen price history'],
    },
  },
  {
    id: 'polymarket-ambiguous-multi-outcome',
    label: 'Polymarket ambiguous multi-outcome market stays guarded',
    snapshot: buildSnapshot({
      venue: 'polymarket',
      marketId: 'poly-ambiguous',
      slug: 'which-outcome-wins',
      question: 'Which outcome wins the ambiguous market?',
      outcomes: ['Alpha', 'Beta', 'Gamma'],
      isBinaryYesNo: false,
      liquidityUsd: 20_000,
      volumeUsd: 160_000,
      volume24hUsd: 15_000,
      bestBid: 0.33,
      bestAsk: 0.35,
      lastTradePrice: 0.34,
      tickSize: 0.01,
      minOrderSize: 5,
      yesPrice: 0.34,
      noPrice: 0.66,
      midpointYes: 0.34,
      bestBidYes: 0.33,
      bestAskYes: 0.35,
      spreadBps: 240,
      history: [
        { timestamp: 1712534400, price: 0.31 },
        { timestamp: 1712538000, price: 0.34 },
      ],
    }),
    expected: {
      resolutionStatus: 'ambiguous',
      manualReviewRequired: true,
      forecastBasis: 'market_midpoint',
      action: 'wait',
      side: null,
      riskFlags: ['resolution_guard'],
      evidenceTypes: ['market_data', 'history'],
      resolutionReasonsInclude: [
        'market is not a binary yes/no contract',
        'market has no explicit end date',
      ],
    },
  },
]

function buildPredictionMarketsBenchmarkCaseBase(
  fixture: PredictionMarketsFrozenBenchmarkCase,
): Omit<PredictionMarketsFrozenBenchmarkResult, 'as_of'> {
  const resolutionPolicy = buildResolutionPolicy(fixture.snapshot)
  const marketOnly = buildMarketOnlyBenchmark({
    snapshot: fixture.snapshot,
    resolutionPolicy,
    minEdgeBps: fixture.minEdgeBps,
    maxSpreadBps: fixture.maxSpreadBps,
  })
  const evidencePackets = buildEvidencePackets({
    snapshot: fixture.snapshot,
    thesisProbability: fixture.thesisProbability,
    thesisRationale: fixture.thesisRationale,
  })
  const forecast = buildForecastPacket({
    snapshot: fixture.snapshot,
    evidencePackets,
    thesisProbability: fixture.thesisProbability,
    thesisRationale: fixture.thesisRationale,
  })
  const recommendation = buildRecommendationPacket({
    snapshot: fixture.snapshot,
    resolutionPolicy,
    forecast,
    minEdgeBps: fixture.minEdgeBps,
    maxSpreadBps: fixture.maxSpreadBps,
  })

  return {
    fixture,
    resolutionPolicy,
    evidencePackets,
    forecast,
    recommendation,
    marketOnly,
    comparison: comparePredictionMarketsBenchmarkResult({
      forecast,
      recommendation,
      marketOnly,
    }),
  }
}

export function runPredictionMarketsBenchmarkCase(
  fixture: PredictionMarketsFrozenBenchmarkCase,
): PredictionMarketsFrozenBenchmarkResult {
  const result = buildPredictionMarketsBenchmarkCaseBase(fixture)

  return {
    ...result,
    as_of: buildAsOfBenchmarkResult({
      fixture,
      result,
      datasetMetadata: buildAsOfDatasetMetadata([fixture]),
    }),
  }
}

export function runPredictionMarketsFrozenBenchmark() {
  const baseResults = predictionMarketsFrozenBenchmarkCases.map(buildPredictionMarketsBenchmarkCaseBase)
  const datasetMetadata = buildAsOfDatasetMetadata(predictionMarketsFrozenBenchmarkCases)

  return baseResults.map((result) => ({
    ...result,
    as_of: buildAsOfBenchmarkResult({
      fixture: result.fixture,
      result,
      datasetMetadata,
    }),
  }))
}

export function summarizePredictionMarketsFrozenBenchmark(
  results: PredictionMarketsFrozenBenchmarkResult[] = runPredictionMarketsFrozenBenchmark(),
): PredictionMarketsFrozenBenchmarkAggregate {
  const actualActionCounts = buildActionCounts()
  const marketOnlyActionCounts = buildActionCounts()
  const forecastDriftBps: number[] = []
  const calibrationGapBps: number[] = []
  const closingLineQualityBps: number[] = []
  const edgeImprovementBps: number[] = []

  for (const result of results) {
    actualActionCounts[result.recommendation.action] += 1
    marketOnlyActionCounts[result.marketOnly.recommendation.action] += 1
    forecastDriftBps.push(result.comparison.forecast_drift_bps)
    calibrationGapBps.push(result.comparison.calibration_gap_bps)
    closingLineQualityBps.push(result.comparison.closing_line_quality_bps)
    edgeImprovementBps.push(result.comparison.edge_improvement_bps)
  }

  const mean = (values: number[]) => (
    values.length > 0
      ? roundToBps(values.reduce((sum, value) => sum + value, 0) / values.length)
      : 0
  )

  return {
    case_count: results.length,
    actual_action_counts: actualActionCounts,
    market_only_action_counts: marketOnlyActionCounts,
    mean_forecast_drift_bps: mean(forecastDriftBps),
    mean_calibration_gap_bps: mean(calibrationGapBps),
    mean_closing_line_quality_bps: mean(closingLineQualityBps),
    mean_edge_improvement_bps: mean(edgeImprovementBps),
  }
}

export function summarizePredictionMarketsBenchmarkResult(
  result: PredictionMarketsFrozenBenchmarkResult,
) {
  return {
    id: result.fixture.id,
    venue: result.fixture.snapshot.venue,
    resolution_status: result.resolutionPolicy.status,
    manual_review_required: result.resolutionPolicy.manual_review_required,
    forecast_basis: result.forecast.basis,
    probability_yes: result.forecast.probability_yes,
    confidence: result.forecast.confidence,
    action: result.recommendation.action,
    side: result.recommendation.side,
    edge_bps: result.recommendation.edge_bps,
    risk_flags: result.recommendation.risk_flags,
    evidence_types: result.evidencePackets.map((packet) => packet.type),
    market_only_action: result.marketOnly.recommendation.action,
    market_only_probability_yes: result.marketOnly.forecast.probability_yes,
    market_only_confidence: result.marketOnly.forecast.confidence,
    market_only_edge_bps: result.comparison.market_only_edge_bps,
    forecast_drift_bps: result.comparison.forecast_drift_bps,
    calibration_gap_bps: result.comparison.calibration_gap_bps,
    closing_line_quality_bps: result.comparison.closing_line_quality_bps,
    edge_improvement_bps: result.comparison.edge_improvement_bps,
  }
}
