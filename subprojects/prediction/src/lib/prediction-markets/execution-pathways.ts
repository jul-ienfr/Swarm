import {
  type ForecastPacket,
  type MarketRecommendationPacket,
  type MarketSnapshot,
  type ResolutionPolicy,
  type TradeIntent,
} from '@/lib/prediction-markets/schemas'
import {
  type CrossVenueArbitrageCandidate,
  type CrossVenueOpsSummary,
} from '@/lib/prediction-markets/cross-venue'
import {
  type PredictionMarketExecutionReadinessMode,
  type PredictionMarketExecutionReadinessReport,
} from '@/lib/prediction-markets/execution-readiness'
import { buildMicrostructurePathSignals } from '@/lib/prediction-markets/microstructure-gating'
import type { MicrostructureLabReport } from '@/lib/prediction-markets/microstructure-lab'
import {
  buildPredictionMarketCanonicalTradeIntentPreview,
  buildPredictionMarketExecutionSizingSummary,
  buildPredictionMarketNoTradeBaselineSummary,
  buildPredictionMarketStrategyNotes,
  buildPredictionMarketStrategySummary,
  type PredictionMarketExecutionSizingSummary,
} from '@/lib/prediction-markets/execution-preview'
import {
  buildShadowArbitrageSimulation,
  type ShadowArbitrageSimulationReport,
} from '@/lib/prediction-markets/shadow-arbitrage'
import {
  buildPredictionMarketPreTradeGate,
  type PredictionMarketPreTradeEdgeBucket,
  type PredictionMarketPreTradeGate,
} from '@/lib/prediction-markets/pre-trade-gate'
import { getPredictionMarketP1BRuntimeSummary } from '@/lib/prediction-markets/external-runtime'

export type PredictionMarketExecutionPathwayMode = 'paper' | 'shadow' | 'live'
export type PredictionMarketExecutionPathwayStatus = 'inactive' | 'ready' | 'degraded' | 'blocked'

export type PredictionMarketExecutionPathway = {
  mode: PredictionMarketExecutionPathwayMode
  effective_mode: PredictionMarketExecutionReadinessMode
  status: PredictionMarketExecutionPathwayStatus
  actionable: boolean
  blockers: string[]
  warnings: string[]
  reason_summary: string
  sizing_summary: PredictionMarketExecutionSizingSummary | null
  trade_intent_preview: TradeIntent | null
  canonical_trade_intent_preview: TradeIntent | null
  strategy_trade_intent_preview?: TradeIntent | null
  strategy_canonical_trade_intent_preview?: TradeIntent | null
  sizing_signal: PredictionMarketExecutionPathwaySizingSignal | null
  shadow_arbitrage_signal: PredictionMarketExecutionPathwayShadowArbitrageSignal | null
  strategy_shadow_summary?: string | null
  strategy_shadow_signal?: PredictionMarketExecutionPathwayShadowArbitrageSignal | null
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
  no_trade_baseline_summary?: string | null
  edge_bucket?: PredictionMarketPreTradeEdgeBucket | null
  pre_trade_gate?: PredictionMarketPreTradeGate | null
}

export type PredictionMarketExecutionPathwaySizingSignal = {
  preview_size_usd: number | null
  canonical_size_usd: number | null
  shadow_recommended_size_usd: number | null
  limit_price: number | null
  max_slippage_bps: number | null
  max_unhedged_leg_ms: number | null
  time_in_force: TradeIntent['time_in_force'] | null
  source:
    | 'trade_intent_preview'
    | 'trade_intent_preview+shadow_arbitrage'
    | 'strategy_trade_intent_preview'
    | 'strategy_trade_intent_preview+shadow_arbitrage'
    | 'shadow_arbitrage'
  notes: string[]
}

export type PredictionMarketExecutionPathwayShadowArbitrageSignal = {
  read_only: true
  market_id: string
  venue: string
  base_executable_edge_bps: number
  shadow_edge_bps: number
  recommended_size_usd: number
  hedge_success_probability: number
  estimated_net_pnl_bps: number
  estimated_net_pnl_usd: number
  worst_case_kind: ShadowArbitrageSimulationReport['summary']['worst_case_kind']
  failure_case_count: number
}

export type PredictionMarketExecutionPathwaysOperatorThesis = {
  present: boolean
  source: 'manual_thesis' | 'decision_packet' | 'research_bridge' | 'none'
  probability_yes: number | null
  rationale: string | null
  evidence_refs: string[]
  summary: string
}

export type PredictionMarketExecutionPathwaysResearchPipelineTrace = {
  pipeline_id: string | null
  pipeline_version: string | null
  preferred_mode: 'market_only' | 'aggregate' | 'abstention' | 'unknown'
  oracle_family: 'llm_superforecaster' | 'llm_oracle' | 'manual_only' | 'unknown'
  forecaster_count: number | null
  evidence_count: number | null
  source_refs: string[]
  summary: string
}

export type PredictionMarketExecutionPathwaysApprovalTicket = {
  ticket_id: string
  required: boolean
  status: 'not_required' | 'paper_only' | 'shadow_only' | 'pending_live_approval' | 'blocked'
  reasons: string[]
  summary: string
}

export type PredictionMarketExecutionPathways = {
  venue: MarketSnapshot['venue']
  market_id: string
  recommendation_action: MarketRecommendationPacket['action']
  recommendation_side: MarketRecommendationPacket['side']
  highest_actionable_mode: PredictionMarketExecutionPathwayMode | null
  pathways: PredictionMarketExecutionPathway[]
  approval_ticket?: PredictionMarketExecutionPathwaysApprovalTicket | null
  operator_thesis?: PredictionMarketExecutionPathwaysOperatorThesis | null
  research_pipeline_trace?: PredictionMarketExecutionPathwaysResearchPipelineTrace | null
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
  no_trade_baseline_summary?: string | null
  selected_edge_bucket?: PredictionMarketPreTradeEdgeBucket | null
  selected_pre_trade_gate?: PredictionMarketPreTradeGate | null
  external_governance_summary?: string | null
  summary: string
}

type ExecutionPathwaysReadinessInput = PredictionMarketExecutionReadinessReport & {
  cross_venue_summary?: CrossVenueOpsSummary | null
  microstructure_lab?: MicrostructureLabReport | null
  calibration_ece?: number | null
  portfolio_correlation?: number | null
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
  no_trade_baseline_summary?: string | null
  strategy_name?: string | null
  strategy_trade_intent_preview?: TradeIntent | null
  strategy_canonical_trade_intent_preview?: TradeIntent | null
  strategy_shadow_arbitrage?: ShadowArbitrageSimulationReport | null
  strategy_shadow_summary?: string | null
  strategy_shadow_signal?: PredictionMarketExecutionPathwayShadowArbitrageSignal | null
}

const EXECUTION_PATHWAY_MODES: PredictionMarketExecutionPathwayMode[] = ['paper', 'shadow', 'live']

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>()
  const out: string[] = []

  for (const value of values) {
    const normalized = String(value ?? '').trim()
    if (!normalized || seen.has(normalized)) continue
    seen.add(normalized)
    out.push(normalized)
  }

  return out
}

function hasQuoteMakerExecution(capabilities: {
  supported_order_types?: string[] | null
  planned_order_types?: string[] | null
} | null | undefined): boolean {
  const orderTypes = uniqueStrings([
    ...(capabilities?.supported_order_types ?? []),
    ...(capabilities?.planned_order_types ?? []),
  ]).map((value) => value.toLowerCase())

  return orderTypes.some((orderType) =>
    orderType === 'maker' ||
    orderType === 'quote' ||
    orderType === 'quote_maker' ||
    orderType === 'post_only',
  )
}

function resolveStrategyTradeIntentPreview(input: {
  strategyTradeIntentPreview?: TradeIntent | null
  tradeIntentPreview: TradeIntent | null
}): TradeIntent | null {
  return input.strategyTradeIntentPreview ?? input.tradeIntentPreview
}

function buildStrategySummary(input: {
  strategy_name?: string | null
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
}): string | null {
  return buildPredictionMarketStrategySummary(input)
}

function buildStrategyNotes(input: {
  strategy_name?: string | null
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
}): string[] {
  return buildPredictionMarketStrategyNotes(input)
}

function buildNoTradeBaselineSummary(input: {
  recommendation_action: MarketRecommendationPacket['action']
  strategy_name?: string | null
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
  blocking_reasons?: Array<string | null | undefined>
}): string | null {
  return buildPredictionMarketNoTradeBaselineSummary(input)
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function rankMode(mode: PredictionMarketExecutionPathwayMode | null): number {
  switch (mode) {
    case 'paper':
      return 1
    case 'shadow':
      return 2
    case 'live':
      return 3
    default:
      return 0
  }
}

function staleQuoteRiskFromAge(
  quoteAgeMs: number,
  freshnessBudgetMs: number,
): 'low' | 'medium' | 'high' {
  if (quoteAgeMs <= 0) return 'low'
  if (freshnessBudgetMs <= 0) return quoteAgeMs > 0 ? 'high' : 'low'

  const ratio = quoteAgeMs / freshnessBudgetMs
  if (ratio >= 1.5) return 'high'
  if (ratio >= 0.5) return 'medium'
  return 'low'
}

function bumpStaleQuoteRisk(
  risk: 'low' | 'medium' | 'high',
  steps: number,
): 'low' | 'medium' | 'high' {
  const order: Array<'low' | 'medium' | 'high'> = ['low', 'medium', 'high']
  const current = order.indexOf(risk)
  return order[Math.min(order.length - 1, Math.max(0, current + steps))]
}

function estimatePreTradeSimulation(input: {
  mode: PredictionMarketExecutionPathwayMode
  recommendation: MarketRecommendationPacket
  readiness: ExecutionPathwaysReadinessInput
  tradeIntentPreview: TradeIntent | null
}): {
  expected_slippage_bps: number
  stale_quote_risk: 'low' | 'medium' | 'high'
} {
  const quoteAgeMs = Math.max(0, Math.round(input.readiness.health.staleness_ms ?? 0))
  const freshnessBudgetMs = Math.max(0, Math.round(input.readiness.budgets.snapshot_freshness_budget_ms ?? 0))
  const baseRisk = staleQuoteRiskFromAge(quoteAgeMs, freshnessBudgetMs)
  const staleQuoteRisk = input.mode === 'paper'
    ? baseRisk
    : input.mode === 'shadow'
      ? bumpStaleQuoteRisk(baseRisk, 1)
      : bumpStaleQuoteRisk(baseRisk, 2)
  const expectedSlippageBps = Math.max(
    0,
    Math.round(
      input.tradeIntentPreview?.max_slippage_bps
      ?? input.recommendation.spread_bps
      ?? 0,
    ),
  )

  return {
    expected_slippage_bps: expectedSlippageBps,
    stale_quote_risk: staleQuoteRisk,
  }
}

function makerExecutionFreshnessBudgetMs(snapshotFreshnessBudgetMs: number): number {
  if (snapshotFreshnessBudgetMs > 0) {
    return Math.max(1_000, Math.min(15_000, Math.round(snapshotFreshnessBudgetMs)))
  }

  return 15_000
}

function parseMakerQuoteState(
  summary: string | null | undefined,
): 'viable' | 'guarded' | 'blocked' | null {
  const normalized = String(summary ?? '').toLowerCase()
  if (normalized.includes('maker_quote=blocked') || normalized.includes('maker_quote_state:blocked')) return 'blocked'
  if (normalized.includes('maker_quote=guarded') || normalized.includes('maker_quote_state:guarded')) return 'guarded'
  if (normalized.includes('maker_quote=viable') || normalized.includes('maker_quote_state:viable')) return 'viable'
  return null
}

function buildStrategyExecutionGuardSignals(input: {
  mode: PredictionMarketExecutionPathwayMode
  strategyName?: string | null
  marketRegimeSummary?: string | null
  readiness: ExecutionPathwaysReadinessInput
}): { blockers: string[]; warnings: string[] } {
  if (input.strategyName !== 'maker_spread_capture') {
    return { blockers: [], warnings: [] }
  }

  const makerQuoteState = parseMakerQuoteState(input.marketRegimeSummary)
  const quoteAgeMs = Math.max(0, Math.round(input.readiness.health.staleness_ms ?? 0))
  const freshnessBudgetMs = makerExecutionFreshnessBudgetMs(
    Math.max(0, Math.round(input.readiness.budgets.snapshot_freshness_budget_ms ?? 0)),
  )
  const warnings = [
    `maker_quote_freshness_budget_ms:${freshnessBudgetMs}`,
  ]
  if (makerQuoteState) {
    warnings.push(`maker_quote_state:${makerQuoteState}`)
  }

  if (input.mode === 'paper') {
    if (quoteAgeMs > freshnessBudgetMs) {
      warnings.push('maker_quote_stale_for_shadow_live')
    }

    return {
      blockers: [],
      warnings,
    }
  }

  const blockers: string[] = []
  if (makerQuoteState === 'blocked') {
    blockers.push('maker_quote_regime_blocked')
  }
  if (makerQuoteState === 'guarded' && input.mode === 'live') {
    blockers.push('maker_quote_guarded_live_only_shadow')
  }
  if (input.readiness.capabilities.supports_websocket !== true) {
    blockers.push('maker_streaming_unavailable')
  }
  if (quoteAgeMs > freshnessBudgetMs) {
    blockers.push('maker_quote_stale_for_execution')
  } else if (quoteAgeMs >= Math.round(freshnessBudgetMs * 0.5)) {
    warnings.push('maker_quote_age_near_budget')
  }

  return {
    blockers,
    warnings,
  }
}

function preferredLimitPrice(input: {
  snapshot: MarketSnapshot
  recommendation: MarketRecommendationPacket
}): number {
  const side = input.recommendation.side
  const fallback = side === 'yes'
    ? input.snapshot.best_ask_yes ?? input.snapshot.yes_price ?? input.recommendation.market_price_yes ?? input.recommendation.fair_value_yes
    : input.snapshot.no_price ?? input.recommendation.market_price_yes == null
      ? 1 - input.recommendation.fair_value_yes
      : 1 - input.recommendation.market_price_yes

  return Number(clamp(fallback ?? 0.5, 0.01, 0.99).toFixed(4))
}

function buildTradeIntentPreview(input: {
  mode: PredictionMarketExecutionPathwayMode
  runId: string
  snapshot: MarketSnapshot
  forecast: ForecastPacket
  recommendation: MarketRecommendationPacket
  readiness: PredictionMarketExecutionReadinessReport
  sizingSummary: PredictionMarketExecutionSizingSummary
}): TradeIntent {
  return {
    schema_version: input.snapshot.schema_version,
    intent_id: `${input.runId}:${input.mode}:preview`,
    run_id: input.runId,
    venue: input.snapshot.venue,
    market_id: input.snapshot.market.market_id,
    side: input.recommendation.side ?? 'yes',
    size_usd: input.sizingSummary.recommended_size_usd,
    limit_price: preferredLimitPrice({
      snapshot: input.snapshot,
      recommendation: input.recommendation,
    }),
    max_slippage_bps: clamp(
      Math.round(input.snapshot.spread_bps ?? input.recommendation.spread_bps ?? 25),
      10,
      100,
    ),
    max_unhedged_leg_ms: input.mode === 'paper'
      ? 0
      : input.mode === 'shadow'
        ? 1_000
        : 250,
    time_in_force: input.mode === 'paper' ? 'day' : 'ioc',
    forecast_ref: `forecast:${input.forecast.market_id}:${input.forecast.produced_at}`,
    risk_checks_passed: true,
    created_at: input.forecast.produced_at,
    notes: `${input.mode} preview intent. ${input.sizingSummary.notes.join(' ')}`,
  }
}

function getHighestConfidenceExecutableEdge(
  summary: CrossVenueOpsSummary | null | undefined,
): CrossVenueArbitrageCandidate | null {
  const candidate = summary?.highest_confidence_candidate ?? null
  if (!candidate || !candidate.executable || candidate.executable_edge.executable_edge_bps <= 0) {
    return null
  }

  return candidate
}

function buildShadowArbitragePathwayReport(input: {
  mode: PredictionMarketExecutionPathwayMode
  recommendation: MarketRecommendationPacket
  readiness: ExecutionPathwaysReadinessInput
  actionable: boolean
  tradeIntentPreview: TradeIntent | null
  strategyShadowArbitrage?: ShadowArbitrageSimulationReport | null
}): ShadowArbitrageSimulationReport | null {
  if (input.mode !== 'shadow') {
    return null
  }

  if (input.strategyShadowArbitrage) {
    return input.strategyShadowArbitrage
  }

  if (!input.actionable || input.recommendation.action !== 'bet' || !input.recommendation.side) {
    return null
  }

  const candidate = getHighestConfidenceExecutableEdge(input.readiness.cross_venue_summary)
  if (!candidate || !input.readiness.microstructure_lab) {
    return null
  }

  return buildShadowArbitrageSimulation({
    executable_edge: candidate.executable_edge,
    microstructure_summary: input.readiness.microstructure_lab.summary,
    size_usd: input.tradeIntentPreview?.size_usd,
    generated_at: input.recommendation.produced_at,
    as_of_at: input.recommendation.produced_at,
  })
}

function buildShadowArbitrageSignal(
  report: ShadowArbitrageSimulationReport | null,
): PredictionMarketExecutionPathwayShadowArbitrageSignal | null {
  if (!report) return null

  return {
    read_only: true,
    market_id: report.executable_edge.buy_ref.market_id,
    venue: report.executable_edge.buy_ref.venue,
    base_executable_edge_bps: report.summary.base_executable_edge_bps,
    shadow_edge_bps: report.summary.shadow_edge_bps,
    recommended_size_usd: report.summary.recommended_size_usd,
    hedge_success_probability: report.summary.hedge_success_probability,
    estimated_net_pnl_bps: report.summary.estimated_net_pnl_bps,
    estimated_net_pnl_usd: report.summary.estimated_net_pnl_usd,
    worst_case_kind: report.summary.worst_case_kind,
    failure_case_count: report.summary.failure_case_count,
  }
}

function buildStrategyShadowSummary(
  report: ShadowArbitrageSimulationReport | null,
  fallbackSummary: string | null | undefined,
): string | null {
  if (fallbackSummary) return fallbackSummary
  if (!report) return null

  return uniqueStrings([
    `shadow edge ${report.summary.shadow_edge_bps} bps`,
    `recommended size ${report.summary.recommended_size_usd} USD`,
    `worst case ${report.summary.worst_case_kind}`,
  ]).join('; ')
}

function buildSizingSignal(input: {
  tradeIntentPreview: TradeIntent | null
  strategyTradeIntentPreview?: TradeIntent | null
  shadowArbitrage: ShadowArbitrageSimulationReport | null
}): PredictionMarketExecutionPathwaySizingSignal | null {
  const selectedTradeIntentPreview = resolveStrategyTradeIntentPreview({
    strategyTradeIntentPreview: input.strategyTradeIntentPreview ?? null,
    tradeIntentPreview: input.tradeIntentPreview,
  })
  const selectedIsStrategyPreview =
    input.strategyTradeIntentPreview != null &&
    selectedTradeIntentPreview === input.strategyTradeIntentPreview
  const previewSizeUsd = selectedTradeIntentPreview?.size_usd ?? null
  const shadowRecommendedSizeUsd = input.shadowArbitrage?.summary.recommended_size_usd ?? null
  const canonicalSizeUsd = previewSizeUsd != null && shadowRecommendedSizeUsd != null
    ? Math.min(previewSizeUsd, shadowRecommendedSizeUsd)
    : previewSizeUsd ?? shadowRecommendedSizeUsd

  if (canonicalSizeUsd == null) {
    return null
  }

  return {
    preview_size_usd: previewSizeUsd,
    canonical_size_usd: canonicalSizeUsd,
    shadow_recommended_size_usd: shadowRecommendedSizeUsd,
    limit_price: selectedTradeIntentPreview?.limit_price ?? null,
    max_slippage_bps: selectedTradeIntentPreview?.max_slippage_bps ?? null,
    max_unhedged_leg_ms: selectedTradeIntentPreview?.max_unhedged_leg_ms ?? null,
    time_in_force: selectedTradeIntentPreview?.time_in_force ?? null,
    source: previewSizeUsd != null && shadowRecommendedSizeUsd != null
      ? selectedIsStrategyPreview
        ? 'strategy_trade_intent_preview+shadow_arbitrage'
        : 'trade_intent_preview+shadow_arbitrage'
      : previewSizeUsd != null
        ? selectedIsStrategyPreview
          ? 'strategy_trade_intent_preview'
          : 'trade_intent_preview'
        : 'shadow_arbitrage',
    notes: uniqueStrings([
      previewSizeUsd != null ? `Preview size is ${previewSizeUsd} USD.` : null,
      shadowRecommendedSizeUsd != null ? `Shadow arbitrage recommends ${shadowRecommendedSizeUsd} USD.` : null,
      previewSizeUsd != null && shadowRecommendedSizeUsd != null && canonicalSizeUsd < previewSizeUsd
        ? `Canonical size is capped to ${canonicalSizeUsd} USD by the read-only shadow arbitrage sizing check.`
        : null,
    ]),
  }
}

function buildApprovalTicket(input: {
  runId: string
  recommendation: MarketRecommendationPacket
  highestActionableMode: PredictionMarketExecutionPathwayMode | null
  operatorThesis?: PredictionMarketExecutionPathwaysOperatorThesis | null
  researchPipelineTrace?: PredictionMarketExecutionPathwaysResearchPipelineTrace | null
}): PredictionMarketExecutionPathwaysApprovalTicket {
  const operatorSource = input.operatorThesis?.source ?? 'none'
  const preferredMode = input.researchPipelineTrace?.preferred_mode ?? 'unknown'
  const reasons = uniqueStrings([
    `operator_thesis_source:${operatorSource}`,
    `research_preferred_mode:${preferredMode}`,
    input.highestActionableMode ? `highest_actionable_mode:${input.highestActionableMode}` : 'highest_actionable_mode:none',
  ])

  if (input.recommendation.action !== 'bet' || !input.recommendation.side) {
    return {
      ticket_id: `${input.runId}:approval_ticket`,
      required: false,
      status: 'not_required',
      reasons,
      summary: 'No governed live approval ticket is required because the recommendation is not an executable bet.',
    }
  }

  if (input.highestActionableMode === 'live') {
    return {
      ticket_id: `${input.runId}:approval_ticket`,
      required: true,
      status: 'pending_live_approval',
      reasons,
      summary: 'Governed live execution requires an approval ticket before the live pathway can be materialized.',
    }
  }

  if (input.highestActionableMode === 'shadow') {
    return {
      ticket_id: `${input.runId}:approval_ticket`,
      required: false,
      status: 'shadow_only',
      reasons,
      summary: 'No live approval ticket is issued because execution remains shadow-only under the current strategy and research guardrails.',
    }
  }

  if (input.highestActionableMode === 'paper') {
    return {
      ticket_id: `${input.runId}:approval_ticket`,
      required: false,
      status: 'paper_only',
      reasons,
      summary: 'No live approval ticket is issued because execution remains paper-only under the current readiness and research state.',
    }
  }

  return {
    ticket_id: `${input.runId}:approval_ticket`,
    required: false,
    status: 'blocked',
    reasons,
    summary: 'No approval ticket can be issued because no execution pathway is currently actionable.',
  }
}

export function buildPredictionMarketExecutionPathways(input: {
  runId: string
  snapshot: MarketSnapshot
  resolutionPolicy: ResolutionPolicy
  forecast: ForecastPacket
  recommendation: MarketRecommendationPacket
  executionReadiness: ExecutionPathwaysReadinessInput
  strategy_name?: string | null
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
  strategy_trade_intent_preview?: TradeIntent | null
  strategy_canonical_trade_intent_preview?: TradeIntent | null
  strategy_shadow_arbitrage?: ShadowArbitrageSimulationReport | null
  strategy_shadow_summary?: string | null
  strategy_shadow_signal?: PredictionMarketExecutionPathwayShadowArbitrageSignal | null
  operator_thesis?: PredictionMarketExecutionPathwaysOperatorThesis | null
  research_pipeline_trace?: PredictionMarketExecutionPathwaysResearchPipelineTrace | null
}): PredictionMarketExecutionPathways {
  const p1bRuntime = getPredictionMarketP1BRuntimeSummary({
    operator_thesis_present: input.operator_thesis?.present ?? false,
    research_pipeline_trace_present: input.research_pipeline_trace != null,
  })
  const strategySummary = buildStrategySummary({
    strategy_name: input.strategy_name ?? null,
    market_regime_summary: input.market_regime_summary ?? null,
    primary_strategy_summary: input.primary_strategy_summary ?? null,
    strategy_summary: input.strategy_summary ?? null,
  })
  const strategyNotes = buildStrategyNotes({
    strategy_name: input.strategy_name ?? null,
    market_regime_summary: input.market_regime_summary ?? null,
    primary_strategy_summary: input.primary_strategy_summary ?? null,
    strategy_summary: input.strategy_summary ?? null,
  })
  const noTradeBaselineSummary = buildNoTradeBaselineSummary({
    recommendation_action: input.recommendation.action,
    strategy_name: input.strategy_name ?? null,
    market_regime_summary: input.market_regime_summary ?? null,
    primary_strategy_summary: input.primary_strategy_summary ?? null,
    strategy_summary: input.strategy_summary ?? null,
    blocking_reasons: [],
  })

  if (input.recommendation.action !== 'bet' || !input.recommendation.side) {
    const approvalTicket = buildApprovalTicket({
      runId: input.runId,
      recommendation: input.recommendation,
      highestActionableMode: null,
      operatorThesis: input.operator_thesis ?? null,
      researchPipelineTrace: input.research_pipeline_trace ?? null,
    })
    return {
      venue: input.snapshot.venue,
      market_id: input.snapshot.market.market_id,
      recommendation_action: input.recommendation.action,
      recommendation_side: input.recommendation.side,
      highest_actionable_mode: null,
      approval_ticket: approvalTicket,
      operator_thesis: input.operator_thesis ?? null,
      research_pipeline_trace: input.research_pipeline_trace ?? null,
      market_regime_summary: input.market_regime_summary ?? null,
      primary_strategy_summary: input.primary_strategy_summary ?? null,
      strategy_summary: strategySummary,
      no_trade_baseline_summary: noTradeBaselineSummary,
      pathways: EXECUTION_PATHWAY_MODES.map((mode) => ({
        mode,
        effective_mode: mode,
        status: 'inactive',
        actionable: false,
        blockers: [],
        warnings: [],
        reason_summary: uniqueStrings([
          `Current recommendation is ${input.recommendation.action}; no execution pathway is actionable.`,
          noTradeBaselineSummary,
          ...strategyNotes,
        ]).join(' '),
        sizing_summary: null,
        trade_intent_preview: null,
        canonical_trade_intent_preview: null,
        strategy_trade_intent_preview: input.strategy_trade_intent_preview ?? null,
        strategy_canonical_trade_intent_preview: input.strategy_canonical_trade_intent_preview ?? input.strategy_trade_intent_preview ?? null,
        sizing_signal: null,
        shadow_arbitrage_signal: null,
        strategy_shadow_summary: input.strategy_shadow_summary ?? null,
        strategy_shadow_signal: input.strategy_shadow_signal ?? null,
        market_regime_summary: input.market_regime_summary ?? null,
        primary_strategy_summary: input.primary_strategy_summary ?? null,
        strategy_summary: strategySummary,
        no_trade_baseline_summary: noTradeBaselineSummary,
        edge_bucket: 'no_trade',
        pre_trade_gate: buildPredictionMarketPreTradeGate({
          mode,
          recommendation: input.recommendation,
          readiness: input.executionReadiness,
          simulation: {
            expected_slippage_bps: 0,
            stale_quote_risk: 'low',
          },
          strategyName: input.strategy_name ?? null,
          marketRegimeSummary: input.market_regime_summary ?? null,
          strategySummary,
          shadowArbitrage: input.strategy_shadow_arbitrage ?? null,
        }),
      })),
      selected_edge_bucket: 'no_trade',
      selected_pre_trade_gate: buildPredictionMarketPreTradeGate({
        mode: 'paper',
        recommendation: input.recommendation,
        readiness: input.executionReadiness,
        simulation: {
          expected_slippage_bps: 0,
          stale_quote_risk: 'low',
        },
        strategyName: input.strategy_name ?? null,
        marketRegimeSummary: input.market_regime_summary ?? null,
        strategySummary,
        shadowArbitrage: input.strategy_shadow_arbitrage ?? null,
      }),
      external_governance_summary: p1bRuntime.summary,
      summary: uniqueStrings([
        `Current recommendation is ${input.recommendation.action}; execution pathways remain inactive.`,
        noTradeBaselineSummary ? `Baseline: ${noTradeBaselineSummary}` : null,
        strategySummary ? `Strategy context: ${strategySummary}.` : null,
        `External governance: ${p1bRuntime.summary}.`,
        input.operator_thesis?.summary ? `Operator thesis: ${input.operator_thesis.summary}.` : null,
        input.research_pipeline_trace?.summary ? `Research trace: ${input.research_pipeline_trace.summary}.` : null,
        approvalTicket.summary,
      ]).join(' '),
    }
  }

  const requiresManualReview = input.resolutionPolicy.manual_review_required ||
    (input.executionReadiness.cross_venue_summary?.manual_review?.length ?? 0) > 0
  const pathways = EXECUTION_PATHWAY_MODES.map((mode) => {
    const readiness = input.executionReadiness.mode_readiness.find((entry) => entry.mode === mode)
    const blockers = [...(readiness?.blockers ?? [])]
    const warnings = [...(readiness?.warnings ?? [])]
    const effectiveMode = readiness?.effective_mode ?? mode

    if (input.resolutionPolicy.status !== 'eligible') {
      blockers.push(`resolution:${input.resolutionPolicy.status}`)
    }

    if (effectiveMode !== mode) {
      blockers.push(`mode_downgraded:${mode}->${effectiveMode}`)
    }

    if (mode !== 'paper' && requiresManualReview) {
      blockers.push('manual_review_required_for_execution')
    }

    if (mode !== 'paper' && !input.executionReadiness.capital_ledger) {
      blockers.push('capital_ledger_unavailable')
    }

    if (mode === 'live' && !input.executionReadiness.reconciliation) {
      blockers.push('reconciliation_unavailable')
    }

    if (mode === 'live' && input.executionReadiness.capabilities.supports_execution !== true) {
      blockers.push('live_execution_not_supported')
    }

    if (mode === 'live' && input.executionReadiness.capabilities.supports_positions !== true) {
      blockers.push('position_support_unavailable')
    }

    if (mode === 'live' && hasQuoteMakerExecution(input.executionReadiness.capabilities)) {
      blockers.push('quote_maker_execution_not_live_ready')
    }

    const microstructureSignals = buildMicrostructurePathSignals({
      mode,
      recommendation: input.recommendation,
      microstructureLab: input.executionReadiness.microstructure_lab,
    })
    blockers.push(...microstructureSignals.blockers)
    warnings.push(...microstructureSignals.warnings)
    const strategyExecutionGuards = buildStrategyExecutionGuardSignals({
      mode,
      strategyName: input.strategy_name ?? null,
      marketRegimeSummary: input.market_regime_summary ?? null,
      readiness: input.executionReadiness,
    })
    blockers.push(...strategyExecutionGuards.blockers)
    warnings.push(...strategyExecutionGuards.warnings)

    const dedupedBlockers = uniqueStrings(blockers)
    const dedupedWarnings = uniqueStrings(warnings)
    const preTradeActionable = dedupedBlockers.length === 0

    const initialReasonSummary = preTradeActionable
      ? uniqueStrings([
        readiness?.summary ?? `${mode} mode is actionable.`,
        ...strategyNotes,
        ...microstructureSignals.warnings,
      ]).join(' ')
      : dedupedBlockers[0] ?? `${mode} mode is blocked.`
    const noTradeBaselineSummaryForPath = buildNoTradeBaselineSummary({
      recommendation_action: input.recommendation.action,
      strategy_name: input.strategy_name ?? null,
      market_regime_summary: input.market_regime_summary ?? null,
      primary_strategy_summary: input.primary_strategy_summary ?? null,
      strategy_summary: input.strategy_summary ?? null,
      blocking_reasons: dedupedBlockers,
    })

    const sizingSummary = buildPredictionMarketExecutionSizingSummary({
      mode,
      snapshot: input.snapshot,
      forecast: input.forecast,
      recommendation: input.recommendation,
      readiness: input.executionReadiness,
    })

    const tradeIntentPreview = preTradeActionable
      ? buildTradeIntentPreview({
        mode,
        runId: input.runId,
        snapshot: input.snapshot,
        forecast: input.forecast,
        recommendation: input.recommendation,
        readiness: input.executionReadiness,
        sizingSummary,
      })
      : null
    const strategyTradeIntentPreview = input.strategy_trade_intent_preview ?? null
    const selectedTradeIntentPreview = tradeIntentPreview ?? strategyTradeIntentPreview
    const shadowArbitrage = buildShadowArbitragePathwayReport({
      mode,
      recommendation: input.recommendation,
      readiness: input.executionReadiness,
      actionable: preTradeActionable,
      tradeIntentPreview: selectedTradeIntentPreview,
      strategyShadowArbitrage: input.strategy_shadow_arbitrage ?? null,
    })
    const preTradeSimulation = estimatePreTradeSimulation({
      mode,
      recommendation: input.recommendation,
      readiness: input.executionReadiness,
      tradeIntentPreview: selectedTradeIntentPreview,
    })
    const preTradeGate = buildPredictionMarketPreTradeGate({
      mode,
      recommendation: input.recommendation,
      readiness: input.executionReadiness,
      simulation: preTradeSimulation,
      strategyName: input.strategy_name ?? null,
      marketRegimeSummary: input.market_regime_summary ?? null,
      strategySummary,
      shadowArbitrage,
    })
    const finalBlockers = [...dedupedBlockers]
    if (preTradeGate.verdict === 'fail') {
      finalBlockers.push('pre_trade_gate:net_edge_below_conservative_threshold')
    }
    const normalizedFinalBlockers = uniqueStrings(finalBlockers)
    const actionable = normalizedFinalBlockers.length === 0
    const status: PredictionMarketExecutionPathwayStatus = actionable
      ? readiness?.verdict === 'degraded'
        ? 'degraded'
        : 'ready'
      : 'blocked'
    const shadowArbitrageSignal = buildShadowArbitrageSignal(shadowArbitrage)
    const strategyShadowSignal = input.strategy_shadow_signal ?? buildShadowArbitrageSignal(input.strategy_shadow_arbitrage ?? null)
    const strategyShadowSummary = buildStrategyShadowSummary(input.strategy_shadow_arbitrage ?? null, input.strategy_shadow_summary)
    const sizingSignal = buildSizingSignal({
      tradeIntentPreview: selectedTradeIntentPreview,
      strategyTradeIntentPreview,
      shadowArbitrage,
    })
    const normalizedTradeIntentPreview = tradeIntentPreview
      ? {
        ...tradeIntentPreview,
        notes: uniqueStrings([
          tradeIntentPreview.notes,
          preTradeGate.summary,
          ...strategyNotes,
          ...microstructureSignals.notes,
        ]).join(' '),
      }
      : null
    const normalizedStrategyTradeIntentPreview = strategyTradeIntentPreview
      ? {
        ...strategyTradeIntentPreview,
        notes: uniqueStrings([
          strategyTradeIntentPreview.notes,
          preTradeGate.summary,
          ...strategyNotes,
          ...microstructureSignals.notes,
        ]).join(' '),
      }
      : null
    const canonicalTradeIntentPreview = buildPredictionMarketCanonicalTradeIntentPreview({
      tradeIntentPreview: normalizedTradeIntentPreview ?? normalizedStrategyTradeIntentPreview,
      canonicalSizeUsd: sizingSignal?.canonical_size_usd ?? null,
    })
    const canonicalStrategyTradeIntentPreview = input.strategy_canonical_trade_intent_preview
      ?? normalizedStrategyTradeIntentPreview

    return {
      mode,
      effective_mode: effectiveMode,
      status,
      actionable,
      blockers: normalizedFinalBlockers,
      warnings: dedupedWarnings,
      reason_summary: actionable
        ? uniqueStrings([
          initialReasonSummary,
          preTradeGate.summary,
        ]).join(' ')
        : uniqueStrings([
          preTradeGate.verdict === 'fail' ? preTradeGate.summary : null,
          normalizedFinalBlockers[0] ?? initialReasonSummary,
        ]).join(' '),
      sizing_summary: sizingSummary,
      trade_intent_preview:
        preTradeGate.verdict === 'fail'
          ? null
          : normalizedTradeIntentPreview ?? normalizedStrategyTradeIntentPreview,
      canonical_trade_intent_preview:
        preTradeGate.verdict === 'fail'
          ? null
          : canonicalTradeIntentPreview,
      strategy_trade_intent_preview: normalizedStrategyTradeIntentPreview,
      strategy_canonical_trade_intent_preview: canonicalStrategyTradeIntentPreview,
      sizing_signal: preTradeGate.verdict === 'fail' ? null : sizingSignal,
      shadow_arbitrage_signal: shadowArbitrageSignal,
      strategy_shadow_summary: strategyShadowSummary,
      strategy_shadow_signal: strategyShadowSignal,
      market_regime_summary: input.market_regime_summary ?? null,
      primary_strategy_summary: input.primary_strategy_summary ?? null,
      strategy_summary: strategySummary,
      no_trade_baseline_summary: noTradeBaselineSummaryForPath,
      edge_bucket: preTradeGate.edge_bucket,
      pre_trade_gate: preTradeGate,
    }
  })

  const highestActionableMode = pathways
    .filter((pathway) => pathway.actionable)
    .sort((left, right) => rankMode(right.mode) - rankMode(left.mode))[0]?.mode ?? null
  const selectedPathway = highestActionableMode == null
    ? pathways.find((pathway) => pathway.mode === 'paper') ?? pathways[0] ?? null
    : pathways.find((pathway) => pathway.mode === highestActionableMode) ?? null
  const approvalTicket = buildApprovalTicket({
    runId: input.runId,
    recommendation: input.recommendation,
    highestActionableMode,
    operatorThesis: input.operator_thesis ?? null,
    researchPipelineTrace: input.research_pipeline_trace ?? null,
  })

  const summary = highestActionableMode
    ? uniqueStrings([
      `${highestActionableMode} is currently the highest actionable execution pathway.`,
      selectedPathway?.pre_trade_gate?.summary ?? null,
      strategySummary ? `Strategy context: ${strategySummary}.` : null,
      input.operator_thesis?.summary ? `Operator thesis: ${input.operator_thesis.summary}.` : null,
      input.research_pipeline_trace?.summary ? `Research trace: ${input.research_pipeline_trace.summary}.` : null,
      approvalTicket.summary,
    ]).join(' ')
    : uniqueStrings([
      `No execution pathway is actionable; ${pathways[0]?.reason_summary ?? 'manual review is still required.'}`,
      selectedPathway?.pre_trade_gate?.summary ?? null,
      strategySummary ? `Strategy context: ${strategySummary}.` : null,
      input.operator_thesis?.summary ? `Operator thesis: ${input.operator_thesis.summary}.` : null,
      input.research_pipeline_trace?.summary ? `Research trace: ${input.research_pipeline_trace.summary}.` : null,
      approvalTicket.summary,
    ]).join(' ')

  return {
    venue: input.snapshot.venue,
    market_id: input.snapshot.market.market_id,
    recommendation_action: input.recommendation.action,
    recommendation_side: input.recommendation.side,
    highest_actionable_mode: highestActionableMode,
    pathways,
    approval_ticket: approvalTicket,
    operator_thesis: input.operator_thesis ?? null,
    research_pipeline_trace: input.research_pipeline_trace ?? null,
    market_regime_summary: input.market_regime_summary ?? null,
    primary_strategy_summary: input.primary_strategy_summary ?? null,
    strategy_summary: strategySummary,
    no_trade_baseline_summary: noTradeBaselineSummary,
    selected_edge_bucket: selectedPathway?.edge_bucket ?? null,
    selected_pre_trade_gate: selectedPathway?.pre_trade_gate ?? null,
    external_governance_summary: p1bRuntime.summary,
    summary,
  }
}
