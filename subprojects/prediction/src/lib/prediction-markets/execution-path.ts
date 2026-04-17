import { randomUUID } from 'node:crypto'
import {
  type ForecastPacket,
  type MarketSnapshot,
  tradeIntentSchema,
  type MarketRecommendationPacket,
  type ResolutionPolicy,
  type TradeIntent,
} from '@/lib/prediction-markets/schemas'
import {
  type PredictionMarketExecutionReadinessMode,
  type PredictionMarketExecutionReadinessReport,
} from '@/lib/prediction-markets/execution-readiness'
import {
  type CrossVenueArbitrageCandidate,
  type CrossVenueOpsSummary,
} from '@/lib/prediction-markets/cross-venue'
import { buildMicrostructurePathSignals } from '@/lib/prediction-markets/microstructure-gating'
import type { MicrostructureLabReport } from '@/lib/prediction-markets/microstructure-lab'
import {
  buildShadowArbitrageSimulation,
  type ShadowArbitrageSimulationReport,
} from '@/lib/prediction-markets/shadow-arbitrage'
import {
  buildPredictionMarketExecutionSizingSummary,
  buildPredictionMarketNoTradeBaselineSummary,
  buildPredictionMarketStrategyNotes,
  buildPredictionMarketStrategySummary,
  type PredictionMarketExecutionSizingSummary,
} from '@/lib/prediction-markets/execution-preview'
import {
  buildPredictionMarketPreTradeGate,
  type PredictionMarketPreTradeEdgeBucket as PredictionMarketExecutionProjectionEdgeBucket,
  type PredictionMarketPreTradeGate as PredictionMarketExecutionProjectionPreTradeGate,
} from '@/lib/prediction-markets/pre-trade-gate'

export type PredictionMarketExecutionProjectionPath = 'paper' | 'shadow' | 'live'
export type PredictionMarketExecutionProjectionStatus = 'inactive' | 'ready' | 'degraded' | 'blocked'
export type PredictionMarketExecutionProjectionVerdict = 'allowed' | 'downgraded' | 'blocked'
export type PredictionMarketExecutionProjectionSimulationStaleQuoteRisk = 'low' | 'medium' | 'high'

export type PredictionMarketExecutionProjectionSimulation = {
  expected_fill_confidence: number
  expected_slippage_bps: number
  stale_quote_risk: PredictionMarketExecutionProjectionSimulationStaleQuoteRisk
  quote_age_ms: number
  notes: string[]
  shadow_arbitrage: ShadowArbitrageSimulationReport | null
}

export type PredictionMarketExecutionProjectionSizingSignal = {
  preview_size_usd: number | null
  base_size_usd: number | null
  recommended_size_usd: number | null
  max_size_usd: number | null
  canonical_size_usd: number | null
  shadow_recommended_size_usd: number | null
  limit_price: number | null
  max_slippage_bps: number | null
  max_unhedged_leg_ms: number | null
  time_in_force: TradeIntent['time_in_force'] | null
  multiplier: number | null
  sizing_source: 'capital_ledger' | 'default' | null
  source:
    | 'trade_intent_preview'
    | 'trade_intent_preview+shadow_arbitrage'
    | 'strategy_trade_intent_preview'
    | 'strategy_trade_intent_preview+shadow_arbitrage'
    | 'shadow_arbitrage'
  notes: string[]
}

export type PredictionMarketExecutionProjectionShadowArbitrageSignal = {
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

export type PredictionMarketExecutionProjectionPathReport = {
  path: PredictionMarketExecutionProjectionPath
  requested_mode: PredictionMarketExecutionProjectionPath
  effective_mode: PredictionMarketExecutionReadinessMode
  status: PredictionMarketExecutionProjectionStatus
  allowed: boolean
  blockers: string[]
  warnings: string[]
  reason_summary: string
  simulation: PredictionMarketExecutionProjectionSimulation
  trade_intent_preview: TradeIntent | null
  canonical_trade_intent_preview: TradeIntent | null
  strategy_trade_intent_preview?: TradeIntent | null
  strategy_canonical_trade_intent_preview?: TradeIntent | null
  sizing_signal: PredictionMarketExecutionProjectionSizingSignal | null
  shadow_arbitrage_signal: PredictionMarketExecutionProjectionShadowArbitrageSignal | null
  strategy_shadow_summary?: string | null
  strategy_shadow_signal?: PredictionMarketExecutionProjectionShadowArbitrageSignal | null
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
  no_trade_baseline_summary?: string | null
  edge_bucket?: PredictionMarketExecutionProjectionEdgeBucket | null
  pre_trade_gate?: PredictionMarketExecutionProjectionPreTradeGate | null
}

export type PredictionMarketExecutionProjection = {
  gate_name: 'execution_projection'
  preflight_only: true
  requested_path: PredictionMarketExecutionProjectionPath
  selected_path: PredictionMarketExecutionProjectionPath | null
  eligible_paths: PredictionMarketExecutionProjectionPath[]
  verdict: PredictionMarketExecutionProjectionVerdict
  blocking_reasons: string[]
  downgrade_reasons: string[]
  manual_review_required: boolean
  generated_at: string
  ttl_ms: number
  expires_at: string
  projected_paths: Record<PredictionMarketExecutionProjectionPath, PredictionMarketExecutionProjectionPathReport>
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
  no_trade_baseline_summary?: string | null
  selected_edge_bucket?: PredictionMarketExecutionProjectionEdgeBucket | null
  selected_pre_trade_gate?: PredictionMarketExecutionProjectionPreTradeGate | null
  summary: string
}

type ExecutionProjectionReadinessInput = PredictionMarketExecutionReadinessReport & {
  cross_venue_summary?: CrossVenueOpsSummary | null
  microstructure_lab?: MicrostructureLabReport | null
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
  no_trade_baseline_summary?: string | null
  strategy_name?: string | null
  strategy_trade_intent_preview?: TradeIntent | null
  strategy_canonical_trade_intent_preview?: TradeIntent | null
  strategy_shadow_arbitrage?: ShadowArbitrageSimulationReport | null
  strategy_shadow_summary?: string | null
  strategy_shadow_signal?: PredictionMarketExecutionProjectionShadowArbitrageSignal | null
}

const EXECUTION_PROJECTION_ORDER: PredictionMarketExecutionProjectionPath[] = ['paper', 'shadow', 'live']
const DEFAULT_EXECUTION_PROJECTION_TTL_MS = 30_000

function unique(values: Array<string | null | undefined>): string[] {
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
  const orderTypes = unique([
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

function rankPath(path: PredictionMarketExecutionProjectionPath | null): number {
  switch (path) {
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

function getExecutionProjectionTtlMs(): number {
  const parsed = Number(process.env.PREDICTION_MARKETS_EXECUTION_PROJECTION_TTL_MS)
  return Number.isFinite(parsed) && parsed > 0
    ? Math.round(parsed)
    : DEFAULT_EXECUTION_PROJECTION_TTL_MS
}

function addMsToIso(iso: string, deltaMs: number): string {
  const parsed = Date.parse(iso)
  if (!Number.isFinite(parsed)) return iso
  return new Date(parsed + deltaMs).toISOString()
}

function clampProbability(value: number): number {
  return Math.max(0, Math.min(1, value))
}

function clampSlippage(value: number): number {
  return Math.max(0, Math.round(value))
}

function nonNegativeInt(value: number | null | undefined): number {
  if (!Number.isFinite(value ?? NaN)) return 0
  return Math.max(0, Math.round(value ?? 0))
}

function requestedPathForRecommendation(recommendation: MarketRecommendationPacket): PredictionMarketExecutionProjectionPath {
  return recommendation.action === 'bet' ? 'live' : 'paper'
}

function bumpStaleQuoteRisk(
  risk: PredictionMarketExecutionProjectionSimulationStaleQuoteRisk,
  steps: number,
): PredictionMarketExecutionProjectionSimulationStaleQuoteRisk {
  const order: PredictionMarketExecutionProjectionSimulationStaleQuoteRisk[] = ['low', 'medium', 'high']
  const current = order.indexOf(risk)
  return order[Math.min(order.length - 1, Math.max(0, current + steps))]
}

function staleQuoteRiskFromAge(
  quoteAgeMs: number,
  freshnessBudgetMs: number,
): PredictionMarketExecutionProjectionSimulationStaleQuoteRisk {
  if (quoteAgeMs <= 0) return 'low'
  if (freshnessBudgetMs <= 0) return quoteAgeMs > 0 ? 'high' : 'low'

  const ratio = quoteAgeMs / freshnessBudgetMs
  if (ratio >= 1.5) return 'high'
  if (ratio >= 0.5) return 'medium'
  return 'low'
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
  mode: PredictionMarketExecutionProjectionPath
  strategyName?: string | null
  marketRegimeSummary?: string | null
  readiness: ExecutionProjectionReadinessInput
}): { blockers: string[]; warnings: string[] } {
  if (input.strategyName !== 'maker_spread_capture') {
    return { blockers: [], warnings: [] }
  }

  const makerQuoteState = parseMakerQuoteState(input.marketRegimeSummary)
  const quoteAgeMs = nonNegativeInt(input.readiness.health.staleness_ms)
  const freshnessBudgetMs = makerExecutionFreshnessBudgetMs(
    nonNegativeInt(input.readiness.budgets.snapshot_freshness_budget_ms),
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

function buildPathSimulation(input: {
  mode: PredictionMarketExecutionProjectionPath
  recommendation: MarketRecommendationPacket
  readiness: ExecutionProjectionReadinessInput
  allowed: boolean
  blockers: string[]
  warnings: string[]
  tradeIntentPreview: TradeIntent | null
  strategySummary?: string | null
  strategyShadowArbitrage?: ShadowArbitrageSimulationReport | null
}): PredictionMarketExecutionProjectionSimulation {
  const microstructureSignals = buildMicrostructurePathSignals({
    mode: input.mode,
    recommendation: input.recommendation,
    microstructureLab: input.readiness.microstructure_lab,
  })
  const quoteAgeMs = nonNegativeInt(input.readiness.health.staleness_ms)
  const freshnessBudgetMs = nonNegativeInt(input.readiness.budgets.snapshot_freshness_budget_ms)
  const baseRisk = staleQuoteRiskFromAge(quoteAgeMs, freshnessBudgetMs)
  const modeAdjustedRisk = input.mode === 'paper'
    ? baseRisk
    : input.mode === 'shadow'
      ? bumpStaleQuoteRisk(baseRisk, 1)
      : bumpStaleQuoteRisk(baseRisk, 2)
  const degradedRisk = input.readiness.overall_verdict === 'degraded'
    ? bumpStaleQuoteRisk(modeAdjustedRisk, 1)
    : modeAdjustedRisk
  const blockedRisk = input.readiness.overall_verdict === 'blocked'
    ? 'high'
    : degradedRisk
  const staleQuoteRisk = input.allowed
    ? blockedRisk
    : bumpStaleQuoteRisk(blockedRisk, 1)

  const spreadBps = Math.max(0, Math.round(input.recommendation.spread_bps ?? 0))
  const spreadFactor = input.mode === 'paper'
    ? 0.12
    : input.mode === 'shadow'
      ? 0.3
      : 0.48
  const modeSlippageBps = clampSlippage(spreadBps * spreadFactor)
  const riskPenaltyBps = staleQuoteRisk === 'high'
    ? (input.mode === 'live' ? 18 : 10)
    : staleQuoteRisk === 'medium'
      ? (input.mode === 'live' ? 8 : 4)
      : 0
  const expectedSlippageBps = input.recommendation.action === 'bet'
    ? modeSlippageBps + riskPenaltyBps + microstructureSignals.slippage_penalty_bps
    : 0

  const baseFillConfidence = input.recommendation.action !== 'bet'
    ? 0
    : input.mode === 'paper'
      ? 0.97
      : input.mode === 'shadow'
        ? 0.88
        : 0.74
  const blockerPenalty = Math.min(0.35, input.blockers.length * 0.09)
  const warningPenalty = Math.min(0.2, input.warnings.length * 0.04)
  const modePenalty = input.mode === 'live'
    ? 0.06
    : input.mode === 'shadow'
      ? 0.03
      : 0
  const expectedFillConfidence = clampProbability(
    baseFillConfidence - blockerPenalty - warningPenalty - modePenalty - microstructureSignals.fill_confidence_penalty,
  )

  const shadowArbitrage = buildShadowArbitrageProjection({
    mode: input.mode,
    recommendation: input.recommendation,
    readiness: input.readiness,
    allowed: input.allowed,
    tradeIntentPreview: input.tradeIntentPreview,
    strategyShadowArbitrage: input.strategyShadowArbitrage ?? null,
  })

  const notes: string[] = []
  if (input.recommendation.action !== 'bet') {
    notes.push('No order is routed for a non-bet recommendation.')
  } else if (input.mode === 'paper') {
    notes.push('Paper assumes a simulated fill at the quoted market, so slippage stays modest.')
  } else if (input.mode === 'shadow') {
    notes.push('Shadow assumes a live-data dry run with fill risk but no venue-side execution.')
  } else {
    notes.push('Live assumes actual venue execution, so fill confidence is lower and slippage is more explicit.')
  }
  if (input.strategySummary) {
    notes.push(`Strategy context: ${input.strategySummary}.`)
  }

  if (quoteAgeMs > 0) {
    notes.push(`Quote age is ${quoteAgeMs} ms against a freshness budget of ${freshnessBudgetMs || 'n/a'} ms.`)
  }
  if (input.readiness.capital_ledger == null) {
    notes.push('No capital ledger is attached, so sizing realism remains constrained.')
  }
  if (input.readiness.reconciliation == null && input.mode === 'live') {
    notes.push('Live simulation is missing reconciliation, so the path stays informational only.')
  }
  notes.push(...microstructureSignals.notes)
  if (shadowArbitrage) {
    notes.push('Shadow arbitrage simulation is attached for read-only reference only.')
  }

  return {
    expected_fill_confidence: expectedFillConfidence,
    expected_slippage_bps: expectedSlippageBps,
    stale_quote_risk: staleQuoteRisk,
    quote_age_ms: quoteAgeMs,
    notes,
    shadow_arbitrage: shadowArbitrage,
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

function buildShadowArbitrageProjection(input: {
  mode: PredictionMarketExecutionProjectionPath
  recommendation: MarketRecommendationPacket
  readiness: ExecutionProjectionReadinessInput
  allowed: boolean
  tradeIntentPreview: TradeIntent | null
  strategyShadowArbitrage?: ShadowArbitrageSimulationReport | null
}): ShadowArbitrageSimulationReport | null {
  if (input.mode !== 'shadow') {
    return null
  }

  if (input.strategyShadowArbitrage) {
    return input.strategyShadowArbitrage
  }

  if (!input.allowed || input.recommendation.action !== 'bet' || !input.recommendation.side) {
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
): PredictionMarketExecutionProjectionShadowArbitrageSignal | null {
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

  return unique([
    `shadow edge ${report.summary.shadow_edge_bps} bps`,
    `recommended size ${report.summary.recommended_size_usd} USD`,
    `worst case ${report.summary.worst_case_kind}`,
  ]).join('; ')
}

function buildSizingSignal(input: {
  sizingSummary: PredictionMarketExecutionSizingSummary | null
  tradeIntentPreview: TradeIntent | null
  strategyTradeIntentPreview?: TradeIntent | null
  shadowArbitrage: ShadowArbitrageSimulationReport | null
}): PredictionMarketExecutionProjectionSizingSignal | null {
  const selectedTradeIntentPreview = resolveStrategyTradeIntentPreview({
    strategyTradeIntentPreview: input.strategyTradeIntentPreview ?? null,
    tradeIntentPreview: input.tradeIntentPreview,
  })
  const selectedIsStrategyPreview =
    input.strategyTradeIntentPreview != null &&
    selectedTradeIntentPreview === input.strategyTradeIntentPreview
  const previewSizeUsd = selectedTradeIntentPreview?.size_usd ?? null
  const baseSizeUsd = input.sizingSummary?.base_size_usd ?? null
  const recommendedSizeUsd = input.sizingSummary?.recommended_size_usd ?? previewSizeUsd
  const maxSizeUsd = input.sizingSummary?.max_size_usd ?? null
  const shadowRecommendedSizeUsd = input.shadowArbitrage?.summary.recommended_size_usd ?? null
  const canonicalBaseSizeUsd = recommendedSizeUsd ?? previewSizeUsd
  const canonicalSizeUsd = canonicalBaseSizeUsd != null && shadowRecommendedSizeUsd != null
    ? Math.min(canonicalBaseSizeUsd, shadowRecommendedSizeUsd)
    : canonicalBaseSizeUsd ?? shadowRecommendedSizeUsd

  if (canonicalSizeUsd == null) {
    return null
  }

  return {
    preview_size_usd: previewSizeUsd,
    base_size_usd: baseSizeUsd,
    recommended_size_usd: recommendedSizeUsd,
    max_size_usd: maxSizeUsd,
    canonical_size_usd: canonicalSizeUsd,
    shadow_recommended_size_usd: shadowRecommendedSizeUsd,
    limit_price: selectedTradeIntentPreview?.limit_price ?? null,
    max_slippage_bps: selectedTradeIntentPreview?.max_slippage_bps ?? null,
    max_unhedged_leg_ms: selectedTradeIntentPreview?.max_unhedged_leg_ms ?? null,
    time_in_force: selectedTradeIntentPreview?.time_in_force ?? null,
    multiplier: input.sizingSummary?.multiplier ?? null,
    sizing_source: input.sizingSummary?.source ?? null,
    source: previewSizeUsd != null && shadowRecommendedSizeUsd != null
      ? selectedIsStrategyPreview
        ? 'strategy_trade_intent_preview+shadow_arbitrage'
        : 'trade_intent_preview+shadow_arbitrage'
      : previewSizeUsd != null
        ? selectedIsStrategyPreview
          ? 'strategy_trade_intent_preview'
          : 'trade_intent_preview'
        : 'shadow_arbitrage',
    notes: unique([
      baseSizeUsd != null ? `Base size is ${baseSizeUsd} USD.` : null,
      recommendedSizeUsd != null ? `Sizing summary recommends ${recommendedSizeUsd} USD.` : null,
      maxSizeUsd != null ? `Mode cap is ${maxSizeUsd} USD.` : null,
      input.sizingSummary?.multiplier != null ? `Conservative multiplier is ${input.sizingSummary.multiplier}.` : null,
      previewSizeUsd != null ? `Preview size is ${previewSizeUsd} USD.` : null,
      shadowRecommendedSizeUsd != null ? `Shadow arbitrage recommends ${shadowRecommendedSizeUsd} USD.` : null,
      canonicalBaseSizeUsd != null && shadowRecommendedSizeUsd != null && canonicalSizeUsd < canonicalBaseSizeUsd
        ? `Canonical size is capped to ${canonicalSizeUsd} USD by the read-only shadow arbitrage sizing check.`
        : null,
      ...(input.sizingSummary?.notes ?? []),
    ]),
  }
}

function projectedStatus(
  readinessStatus: PredictionMarketExecutionReadinessReport['mode_readiness'][number]['verdict'],
  allowed: boolean,
  blockedReasons: string[],
): PredictionMarketExecutionProjectionStatus {
  if (!allowed) return 'blocked'
  if (readinessStatus === 'degraded') return 'degraded'
  if (readinessStatus === 'ready') return 'ready'
  if (blockedReasons.length > 0) return 'blocked'
  return 'inactive'
}

function estimatePreviewSizeUsd(mode: PredictionMarketExecutionProjectionPath): number {
  switch (mode) {
    case 'paper':
      return 100
    case 'shadow':
      return 50
    case 'live':
      return 25
  }
}

function buildTradeIntentPreview(input: {
  mode: PredictionMarketExecutionProjectionPath
  runId: string
  recommendation: MarketRecommendationPacket
  sizingSummary?: PredictionMarketExecutionSizingSummary | null
}): TradeIntent {
  const referencePrice = input.recommendation.market_ask_yes ?? input.recommendation.market_bid_yes ?? input.recommendation.market_price_yes ?? input.recommendation.fair_value_yes

  return tradeIntentSchema.parse({
    schema_version: input.recommendation.schema_version,
    intent_id: `${input.runId}:${input.mode}:projection`,
    run_id: input.runId,
    venue: input.recommendation.venue,
    market_id: input.recommendation.market_id,
    side: input.recommendation.side ?? 'yes',
    size_usd: input.sizingSummary?.recommended_size_usd ?? estimatePreviewSizeUsd(input.mode),
    limit_price: referencePrice == null ? 0.5 : Math.max(0.01, Math.min(0.99, Number(referencePrice.toFixed(4)))),
    max_slippage_bps: Math.max(10, Math.min(150, Math.round(input.recommendation.spread_bps ?? 50))),
    max_unhedged_leg_ms: input.mode === 'paper' ? 0 : input.mode === 'shadow' ? 1_000 : 250,
    time_in_force: input.mode === 'paper' ? 'day' : 'ioc',
    forecast_ref: `forecast:${input.recommendation.market_id}:${input.recommendation.produced_at}`,
    risk_checks_passed: true,
    created_at: input.recommendation.produced_at,
    notes: input.sizingSummary
      ? `${input.mode} execution projection preview. ${input.sizingSummary.notes.join(' ')}`
      : `${input.mode} execution projection preview.`,
  })
}

function buildCanonicalTradeIntentPreview(input: {
  tradeIntentPreview: TradeIntent | null
  sizingSignal: PredictionMarketExecutionProjectionSizingSignal | null
}): TradeIntent | null {
  if (!input.tradeIntentPreview) return null

  const canonicalSizeUsd = input.sizingSignal?.canonical_size_usd
  if (canonicalSizeUsd == null) {
    return input.tradeIntentPreview
  }

  const normalizedCanonicalSizeUsd = Math.max(1, Math.round(canonicalSizeUsd))
  return tradeIntentSchema.parse({
    ...input.tradeIntentPreview,
    size_usd: normalizedCanonicalSizeUsd,
    notes: unique([
      input.tradeIntentPreview.notes,
      normalizedCanonicalSizeUsd < input.tradeIntentPreview.size_usd
        ? `Canonical execution projection preview caps size to ${normalizedCanonicalSizeUsd} USD from ${input.tradeIntentPreview.size_usd} USD via sizing_signal.canonical_size_usd.`
        : null,
    ]).join(' '),
  })
}

function projectPath(input: {
  mode: PredictionMarketExecutionProjectionPath
  runId: string
  recommendation: MarketRecommendationPacket
  readiness: ExecutionProjectionReadinessInput
  snapshot?: MarketSnapshot | null
  forecast?: ForecastPacket | null
  resolutionPolicy?: Pick<ResolutionPolicy, 'status' | 'manual_review_required'> | null
  strategy_name?: string | null
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
  strategy_trade_intent_preview?: TradeIntent | null
  strategy_canonical_trade_intent_preview?: TradeIntent | null
  strategy_shadow_arbitrage?: ShadowArbitrageSimulationReport | null
  strategy_shadow_summary?: string | null
  strategy_shadow_signal?: PredictionMarketExecutionProjectionShadowArbitrageSignal | null
}): PredictionMarketExecutionProjectionPathReport {
  const readiness = input.readiness.mode_readiness.find((entry) => entry.mode === input.mode)
  const blockers = [...(readiness?.blockers ?? [])]
  const warnings = [...(readiness?.warnings ?? [])]
  const effectiveMode = readiness?.effective_mode ?? input.mode
  const requiresManualReview = input.resolutionPolicy?.manual_review_required === true ||
    (input.readiness.cross_venue_summary?.manual_review?.length ?? 0) > 0
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
  const simulation = buildPathSimulation({
    mode: input.mode,
    recommendation: input.recommendation,
    readiness: input.readiness,
    allowed: true,
    blockers,
    warnings,
    tradeIntentPreview: null,
    strategySummary,
    strategyShadowArbitrage: input.strategy_shadow_arbitrage ?? null,
  })
  const simulationPreTradeGate = buildPredictionMarketPreTradeGate({
    mode: input.mode,
    recommendation: input.recommendation,
    readiness: input.readiness,
    simulation,
    strategyName: input.strategy_name ?? null,
    marketRegimeSummary: input.market_regime_summary ?? null,
    strategySummary,
    shadowArbitrage: simulation.shadow_arbitrage ?? input.strategy_shadow_arbitrage ?? null,
  })

  if (input.recommendation.action !== 'bet') {
    if (input.mode === 'paper') {
      return {
        path: input.mode,
        requested_mode: input.mode,
        effective_mode: effectiveMode,
        status: readiness?.verdict === 'degraded' ? 'degraded' : 'ready',
        allowed: true,
        blockers: unique(blockers),
        warnings: unique(warnings),
        reason_summary: unique([
          readiness?.summary ?? 'Paper projection is ready.',
          noTradeBaselineSummary,
          simulationPreTradeGate.summary,
          ...strategyNotes,
        ]).join(' '),
        simulation,
        trade_intent_preview: input.strategy_trade_intent_preview ?? null,
        canonical_trade_intent_preview: input.strategy_canonical_trade_intent_preview ?? input.strategy_trade_intent_preview ?? null,
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
        edge_bucket: simulationPreTradeGate.edge_bucket,
        pre_trade_gate: simulationPreTradeGate,
      }
    }

    blockers.push(`recommendation:${input.recommendation.action}`)
  }

  if (input.recommendation.action === 'bet' && input.resolutionPolicy && input.resolutionPolicy.status !== 'eligible') {
    blockers.push(`resolution:${input.resolutionPolicy.status}`)
  }

  if (input.recommendation.action === 'bet' && !input.recommendation.side) {
    blockers.push('recommendation:missing_side')
  }

  if (input.recommendation.action === 'bet' && input.mode !== 'paper' && requiresManualReview) {
    blockers.push('manual_review_required_for_execution')
  }

  if (input.recommendation.action === 'bet' && input.mode !== 'paper' && !input.readiness.capital_ledger) {
    blockers.push('capital_ledger_unavailable')
  }

  if (input.recommendation.action === 'bet' && input.mode === 'live' && !input.readiness.reconciliation) {
    blockers.push('reconciliation_unavailable')
  }

  if (input.recommendation.action === 'bet' && input.mode === 'live') {
    if (input.readiness.capabilities.supports_execution !== true) {
      blockers.push('live_execution_not_supported')
    }
    if (input.readiness.capabilities.supports_positions !== true) {
      blockers.push('position_support_unavailable')
    }
    if (hasQuoteMakerExecution(input.readiness.capabilities)) {
      blockers.push('quote_maker_execution_not_live_ready')
    }
  }

  const microstructureSignals = buildMicrostructurePathSignals({
    mode: input.mode,
    recommendation: input.recommendation,
    microstructureLab: input.readiness.microstructure_lab,
  })
  blockers.push(...microstructureSignals.blockers)
  warnings.push(...microstructureSignals.warnings)
  const strategyExecutionGuards = buildStrategyExecutionGuardSignals({
    mode: input.mode,
    strategyName: input.strategy_name ?? null,
    marketRegimeSummary: input.market_regime_summary ?? null,
    readiness: input.readiness,
  })
  blockers.push(...strategyExecutionGuards.blockers)
  warnings.push(...strategyExecutionGuards.warnings)

  const normalizedBlockers = unique(blockers)
  const normalizedWarnings = unique(warnings)
  const preTradeAllowed = normalizedBlockers.length === 0 && readiness?.verdict !== 'blocked'
  const strategyTradeIntentPreview = input.strategy_trade_intent_preview ?? null
  const sizingSummary = input.snapshot && input.forecast && input.recommendation.side
    ? buildPredictionMarketExecutionSizingSummary({
      mode: input.mode,
      snapshot: input.snapshot,
      forecast: input.forecast,
      recommendation: input.recommendation,
      readiness: input.readiness,
    })
    : null
  const tradeIntentPreview = preTradeAllowed && input.recommendation.action === 'bet'
    ? buildTradeIntentPreview({
      mode: input.mode,
      runId: input.runId,
      recommendation: input.recommendation,
      sizingSummary,
    })
    : null
  const selectedTradeIntentPreview = tradeIntentPreview ?? strategyTradeIntentPreview
  const preTradeSimulation = buildPathSimulation({
    mode: input.mode,
    recommendation: input.recommendation,
    readiness: input.readiness,
    allowed: preTradeAllowed,
    blockers: normalizedBlockers,
    warnings: normalizedWarnings,
    tradeIntentPreview: selectedTradeIntentPreview,
  })
  const preliminaryPreTradeGate = buildPredictionMarketPreTradeGate({
    mode: input.mode,
    recommendation: input.recommendation,
    readiness: input.readiness,
    simulation: preTradeSimulation,
    strategyName: input.strategy_name ?? null,
    marketRegimeSummary: input.market_regime_summary ?? null,
    strategySummary,
    shadowArbitrage: preTradeSimulation.shadow_arbitrage ?? input.strategy_shadow_arbitrage ?? null,
  })
  if (preliminaryPreTradeGate.verdict === 'fail') {
    normalizedBlockers.push('pre_trade_gate:net_edge_below_conservative_threshold')
  }
  const finalBlockers = unique(normalizedBlockers)
  const finalWarnings = unique(normalizedWarnings)
  const allowed = finalBlockers.length === 0 && readiness?.verdict !== 'blocked'
  const guardedSimulation = buildPathSimulation({
    mode: input.mode,
    recommendation: input.recommendation,
    readiness: input.readiness,
    allowed,
    blockers: finalBlockers,
    warnings: finalWarnings,
    tradeIntentPreview: selectedTradeIntentPreview,
  })
  const shadowArbitrageSignal = buildShadowArbitrageSignal(guardedSimulation.shadow_arbitrage)
  const strategyShadowArbitrage = input.strategy_shadow_arbitrage ?? null
  const strategyShadowSignal = input.strategy_shadow_signal ?? buildShadowArbitrageSignal(strategyShadowArbitrage)
  const strategyShadowSummary = buildStrategyShadowSummary(strategyShadowArbitrage, input.strategy_shadow_summary)
  const preTradeGate = buildPredictionMarketPreTradeGate({
    mode: input.mode,
    recommendation: input.recommendation,
    readiness: input.readiness,
    simulation: guardedSimulation,
    strategyName: input.strategy_name ?? null,
    marketRegimeSummary: input.market_regime_summary ?? null,
    strategySummary,
    shadowArbitrage: guardedSimulation.shadow_arbitrage ?? strategyShadowArbitrage,
  })
  const sizingSignal = buildSizingSignal({
    sizingSummary,
    tradeIntentPreview: selectedTradeIntentPreview,
    strategyTradeIntentPreview,
    shadowArbitrage: guardedSimulation.shadow_arbitrage,
  })
  const normalizedTradeIntentPreview = tradeIntentPreview
    ? {
      ...tradeIntentPreview,
      notes: unique([
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
      notes: unique([
        strategyTradeIntentPreview.notes,
        preTradeGate.summary,
        ...strategyNotes,
        ...microstructureSignals.notes,
      ]).join(' '),
    }
    : null
  const canonicalTradeIntentPreview = buildCanonicalTradeIntentPreview({
    tradeIntentPreview: normalizedTradeIntentPreview ?? normalizedStrategyTradeIntentPreview,
    sizingSignal,
  })
  const canonicalStrategyTradeIntentPreview = input.strategy_canonical_trade_intent_preview
    ?? normalizedStrategyTradeIntentPreview

  return {
    path: input.mode,
    requested_mode: input.mode,
    effective_mode: effectiveMode,
    status: projectedStatus(readiness?.verdict ?? 'blocked', allowed, finalBlockers),
    allowed,
    blockers: finalBlockers,
    warnings: finalWarnings,
    reason_summary: allowed
      ? unique([
        readiness?.summary ?? `${input.mode} projection is ready.`,
        preTradeGate.summary,
        ...strategyNotes,
        ...microstructureSignals.warnings,
      ]).join(' ')
      : unique([
        preTradeGate.verdict === 'fail' ? preTradeGate.summary : null,
        finalBlockers[0] ?? `${input.mode} projection is blocked.`,
      ]).join(' '),
    simulation: guardedSimulation,
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
    no_trade_baseline_summary: noTradeBaselineSummary,
    edge_bucket: preTradeGate.edge_bucket,
    pre_trade_gate: preTradeGate,
  }
}

export function projectPredictionMarketExecutionPath(input: {
  recommendation: MarketRecommendationPacket
  execution_readiness: ExecutionProjectionReadinessInput
  snapshot?: MarketSnapshot | null
  forecast?: ForecastPacket | null
  resolution_policy?: Pick<ResolutionPolicy, 'status' | 'manual_review_required'> | null
  run_id?: string
  strategy_name?: string | null
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
  strategy_trade_intent_preview?: TradeIntent | null
  strategy_canonical_trade_intent_preview?: TradeIntent | null
  strategy_shadow_arbitrage?: ShadowArbitrageSimulationReport | null
  strategy_shadow_summary?: string | null
  strategy_shadow_signal?: PredictionMarketExecutionProjectionShadowArbitrageSignal | null
}): PredictionMarketExecutionProjection {
  const requestedPath = requestedPathForRecommendation(input.recommendation)
  const runId = input.run_id ?? randomUUID()
  const projectedPaths = Object.fromEntries(
    EXECUTION_PROJECTION_ORDER.map((mode) => [mode, projectPath({
      mode,
      runId,
      recommendation: input.recommendation,
      readiness: input.execution_readiness,
      snapshot: input.snapshot,
      forecast: input.forecast,
      resolutionPolicy: input.resolution_policy,
      strategy_name: input.strategy_name,
      market_regime_summary: input.market_regime_summary,
      primary_strategy_summary: input.primary_strategy_summary,
      strategy_summary: input.strategy_summary,
      strategy_trade_intent_preview: input.strategy_trade_intent_preview,
      strategy_canonical_trade_intent_preview: input.strategy_canonical_trade_intent_preview,
      strategy_shadow_arbitrage: input.strategy_shadow_arbitrage,
      strategy_shadow_summary: input.strategy_shadow_summary,
      strategy_shadow_signal: input.strategy_shadow_signal,
    })]),
  ) as Record<PredictionMarketExecutionProjectionPath, PredictionMarketExecutionProjectionPathReport>

  const eligiblePaths = EXECUTION_PROJECTION_ORDER.filter((mode) => projectedPaths[mode].allowed)
  const selectedPath = [...eligiblePaths].sort((left, right) => rankPath(right) - rankPath(left))[0] ?? null
  const requestedPathReport = projectedPaths[requestedPath]
  const verdict: PredictionMarketExecutionProjectionVerdict = selectedPath == null
    ? 'blocked'
    : selectedPath === requestedPath
      ? 'allowed'
      : 'downgraded'
  const blockingReasons = selectedPath == null
    ? unique(requestedPathReport.blockers)
    : []
  const downgradeReasons = selectedPath != null && selectedPath !== requestedPath
    ? unique([
      ...requestedPathReport.blockers,
      ...(requestedPathReport.effective_mode !== requestedPath
        ? [`effective_mode:${requestedPath}->${requestedPathReport.effective_mode}`]
        : []),
    ])
    : []
  const manualReviewRequired = input.resolution_policy?.manual_review_required === true ||
    input.execution_readiness.compliance_matrix.account_readiness.manual_review_required === true ||
    (input.execution_readiness.cross_venue_summary?.manual_review?.length ?? 0) > 0
  const ttlMs = getExecutionProjectionTtlMs()
  const generatedAt = input.recommendation.produced_at
  const projectionStrategySummary = buildStrategySummary({
    strategy_name: input.strategy_name ?? null,
    market_regime_summary: input.market_regime_summary ?? null,
    primary_strategy_summary: input.primary_strategy_summary ?? null,
    strategy_summary: input.strategy_summary ?? null,
  })
  const projectionNoTradeBaselineSummary = requestedPathReport.no_trade_baseline_summary ?? buildNoTradeBaselineSummary({
    recommendation_action: input.recommendation.action,
    strategy_name: input.strategy_name ?? null,
    market_regime_summary: input.market_regime_summary ?? null,
    primary_strategy_summary: input.primary_strategy_summary ?? null,
    strategy_summary: input.strategy_summary ?? null,
    blocking_reasons: blockingReasons,
  })
  const canonicalProjectionPath = selectedPath == null
    ? projectedPaths[requestedPath] ?? null
    : projectedPaths[selectedPath] ?? null
  const selectedEdgeBucket = canonicalProjectionPath?.edge_bucket ?? null
  const selectedPreTradeGate = canonicalProjectionPath?.pre_trade_gate ?? null

  return {
    gate_name: 'execution_projection',
    preflight_only: true,
    requested_path: requestedPath,
    selected_path: selectedPath,
    eligible_paths: eligiblePaths,
    verdict,
    blocking_reasons: blockingReasons,
    downgrade_reasons: downgradeReasons,
    manual_review_required: manualReviewRequired,
    generated_at: generatedAt,
    ttl_ms: ttlMs,
    expires_at: addMsToIso(generatedAt, ttlMs),
    projected_paths: projectedPaths,
    market_regime_summary: input.market_regime_summary ?? null,
    primary_strategy_summary: input.primary_strategy_summary ?? null,
    strategy_summary: projectionStrategySummary,
    no_trade_baseline_summary: projectionNoTradeBaselineSummary,
    selected_edge_bucket: selectedEdgeBucket,
    selected_pre_trade_gate: selectedPreTradeGate,
    summary: selectedPath
      ? unique([
        `Requested ${requestedPath}; selected ${selectedPath}; gate execution_projection; preflight only.`,
        projectionStrategySummary ? `Strategy context: ${projectionStrategySummary}.` : null,
        selectedPreTradeGate?.summary ?? null,
        projectedPaths[selectedPath].reason_summary,
      ]).join(' ')
      : unique([
        `Requested ${requestedPath}; gate execution_projection; preflight only; no execution path is currently safe.`,
        projectionNoTradeBaselineSummary ? `Baseline: ${projectionNoTradeBaselineSummary}` : null,
        projectionStrategySummary ? `Strategy context: ${projectionStrategySummary}.` : null,
        selectedPreTradeGate?.summary ?? null,
      ]).join(' '),
  }
}
