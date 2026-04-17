import {
  type ApprovalTradeTicket,
  type ForecastPacket,
  type MarketRecommendationPacket,
  type MarketSnapshot,
  type TradeIntent,
} from '@/lib/prediction-markets/schemas'
import { type PredictionMarketExecutionReadinessReport } from '@/lib/prediction-markets/execution-readiness'
import {
  buildKellyCappedPredictionMarketSizing,
  type ConservativePredictionMarketSizingResult,
} from '@/lib/prediction-markets/sizing'

export type PredictionMarketExecutionPreviewMode = 'paper' | 'shadow' | 'live'

export type PredictionMarketExecutionSizingSummary = {
  requested_mode: PredictionMarketExecutionPreviewMode
  source: 'capital_ledger' | 'default'
  base_size_usd: number
  recommended_size_usd: number
  max_size_usd: number | null
  conservative_cap_usd: number | null
  effective_cap_usd: number | null
  multiplier: number | null
  kelly_fraction: number | null
  kelly_cap_usd: number | null
  kelly_edge_bps: number | null
  kelly_applicable: boolean
  kelly_reason: string | null
  market_probability_yes: number | null
  forecast_probability_yes: number | null
  factors: ConservativePredictionMarketSizingResult['factors'] | null
  notes: string[]
}

export type PredictionMarketExecutionStrategySummaryInput = {
  strategy_name?: string | null
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
}

export type PredictionMarketNoTradeBaselineSummaryInput = PredictionMarketExecutionStrategySummaryInput & {
  recommendation_action: MarketRecommendationPacket['action']
  blocking_reasons?: Array<string | null | undefined>
}

type ExecutionPreviewReadinessInput = PredictionMarketExecutionReadinessReport & {
  calibration_ece?: number | null
  portfolio_correlation?: number | null
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function roundTwo(value: number): number {
  return Number(value.toFixed(2))
}

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

export function buildPredictionMarketStrategySummary(
  input: PredictionMarketExecutionStrategySummaryInput,
): string | null {
  const parts = uniqueStrings([
    input.strategy_name ? `Strategy ${input.strategy_name}` : null,
    input.market_regime_summary ? `Market regime: ${input.market_regime_summary}` : null,
    input.primary_strategy_summary ? `Primary strategy: ${input.primary_strategy_summary}` : null,
    input.strategy_summary ? input.strategy_summary : null,
  ])

  return parts.length > 0 ? parts.join(' | ') : null
}

export function buildPredictionMarketStrategyNotes(
  input: PredictionMarketExecutionStrategySummaryInput,
): string[] {
  return uniqueStrings([
    input.strategy_name ? `Strategy name is ${input.strategy_name}.` : null,
    input.market_regime_summary ? `Market regime summary: ${input.market_regime_summary}.` : null,
    input.primary_strategy_summary ? `Primary strategy summary: ${input.primary_strategy_summary}.` : null,
    input.strategy_summary ? `Strategy summary: ${input.strategy_summary}.` : null,
  ])
}

export function buildPredictionMarketNoTradeBaselineSummary(
  input: PredictionMarketNoTradeBaselineSummaryInput,
): string | null {
  const actionSummary = input.recommendation_action === 'no_trade'
    ? 'Recommendation remains no_trade.'
    : input.recommendation_action === 'wait'
      ? 'Recommendation remains wait.'
      : `Recommendation ${input.recommendation_action} falls back to the no-trade baseline.`

  const parts = uniqueStrings([
    'No-trade baseline:',
    actionSummary,
    input.market_regime_summary ? `Market regime: ${input.market_regime_summary}.` : null,
    input.primary_strategy_summary ? `Primary strategy: ${input.primary_strategy_summary}.` : null,
    input.strategy_summary ? `Strategy context: ${input.strategy_summary}.` : null,
    input.blocking_reasons && input.blocking_reasons.length > 0
      ? `Blocking reasons: ${uniqueStrings(input.blocking_reasons).join(', ')}.`
      : null,
  ])

  return parts.length > 0 ? parts.join(' ') : null
}

export function buildPredictionMarketNoTradeBaselineNotes(
  input: PredictionMarketNoTradeBaselineSummaryInput,
): string[] {
  const notes = buildPredictionMarketStrategyNotes(input)
  const baselineSummary = buildPredictionMarketNoTradeBaselineSummary(input)

  return uniqueStrings([
    baselineSummary ? baselineSummary.replace(/^No-trade baseline:\s*/i, '') : null,
    ...notes,
  ])
}

function estimatePortfolioCorrelationProxy(input: {
  readiness: ExecutionPreviewReadinessInput
}): number | null {
  if (input.readiness.portfolio_correlation != null) {
    return clamp(input.readiness.portfolio_correlation, 0, 1)
  }

  const capital = input.readiness.capital_ledger
  if (!capital) return null

  const totalCapital = capital.cash_available_usd + capital.cash_locked_usd + capital.open_exposure_usd
  if (totalCapital <= 0) return 0

  const exposureShare = clamp(capital.open_exposure_usd / totalCapital, 0, 1)
  const utilization = clamp(capital.utilization_ratio, 0, 1)
  const concentrationProxy = Math.max(exposureShare, utilization)

  return clamp(0.25 + (0.75 * concentrationProxy), 0, 1)
}

function estimateSizingSignals(input: {
  snapshot: MarketSnapshot
  forecast: ForecastPacket
  recommendation: MarketRecommendationPacket
  readiness: ExecutionPreviewReadinessInput
}) {
  const confidence = clamp(Math.min(input.forecast.confidence, input.recommendation.confidence), 0, 1)
  const calibration_ece = input.readiness.calibration_ece != null
    ? clamp(input.readiness.calibration_ece, 0, 1)
    : clamp(1 - input.forecast.confidence, 0, 1)

  return {
    confidence,
    calibration_ece,
    liquidity_usd: input.snapshot.market.liquidity_usd ?? null,
    depth_near_touch: input.snapshot.book?.depth_near_touch ?? null,
    portfolio_correlation: estimatePortfolioCorrelationProxy({
      readiness: input.readiness,
    }),
  }
}

function estimateCapitalTimeHaircut(input: {
  capital: NonNullable<ExecutionPreviewReadinessInput['capital_ledger']>
}): {
  factor: number
  latency_factor: number
  utilization_factor: number
  adjusted_cash_available_usd: number
  note: string | null
} {
  const transferLatencyEstimateMs = Math.max(input.capital.transfer_latency_estimate_ms, 0)
  const utilizationRatio = clamp(input.capital.utilization_ratio, 0, 1)
  const latencyFactor = transferLatencyEstimateMs < 30_000
    ? 1
    : transferLatencyEstimateMs < 60_000
      ? 0.9
      : transferLatencyEstimateMs < 120_000
        ? 0.8
        : 0.65
  const utilizationFactor = utilizationRatio < 0.7
    ? 1
    : utilizationRatio < 0.8
      ? 0.9
      : utilizationRatio < 0.9
        ? 0.8
        : 0.65
  const factor = Math.min(latencyFactor, utilizationFactor)

  return {
    factor,
    latency_factor: latencyFactor,
    utilization_factor: utilizationFactor,
    adjusted_cash_available_usd: roundTwo(input.capital.cash_available_usd * factor),
    note: factor < 1
      ? `Capital-time haircut factor=${formatPercent(factor)} (latency=${formatPercent(latencyFactor)}, utilization=${formatPercent(utilizationFactor)}) from transfer_latency_estimate_ms=${transferLatencyEstimateMs} and utilization_ratio=${formatPercent(utilizationRatio)}.`
      : null,
  }
}

function estimateCorrelationCapUsd(input: {
  modeMaxSize: number
  portfolioCorrelation: number | null
}): {
  factor: number
  cap_usd: number
  binding: boolean
  note: string | null
} {
  const portfolioCorrelation = input.portfolioCorrelation == null
    ? null
    : clamp(Math.abs(input.portfolioCorrelation), 0, 1)
  const factor = portfolioCorrelation == null || portfolioCorrelation < 0.65
    ? 1
    : portfolioCorrelation < 0.85
      ? 0.65
      : 0.4
  const capUsd = roundTwo(input.modeMaxSize * factor)

  return {
    factor,
    cap_usd: capUsd,
    binding: factor < 1,
    note: factor < 1 && portfolioCorrelation != null
      ? `Correlation cap factor=${formatPercent(factor)} trims max size to ${capUsd.toFixed(2)} USD at portfolio_correlation=${formatPercent(portfolioCorrelation)}.`
      : null,
  }
}

export function buildPredictionMarketExecutionSizingSummary(input: {
  mode: PredictionMarketExecutionPreviewMode
  snapshot: MarketSnapshot
  forecast: ForecastPacket
  recommendation: MarketRecommendationPacket
  readiness: ExecutionPreviewReadinessInput
}): PredictionMarketExecutionSizingSummary {
  const capital = input.readiness.capital_ledger
  if (capital) {
    const capitalFraction = input.mode === 'paper'
      ? 0.1
      : input.mode === 'shadow'
        ? 0.05
        : 0.02
    const modeMaxSize = input.mode === 'paper'
      ? 250
      : input.mode === 'shadow'
        ? 150
        : 100
    const signals = estimateSizingSignals({
      snapshot: input.snapshot,
      forecast: input.forecast,
      recommendation: input.recommendation,
      readiness: input.readiness,
    })
    const capitalTimeHaircut = estimateCapitalTimeHaircut({ capital })
    const liquidityUsd = input.snapshot.market.liquidity_usd
    const depthNearTouch = input.snapshot.book?.depth_near_touch ?? null
    const liquidityCap = liquidityUsd == null
      ? modeMaxSize
      : clamp(liquidityUsd * 0.001, 25, modeMaxSize)
    const depthCap = depthNearTouch == null
      ? modeMaxSize
      : clamp(depthNearTouch * 0.06, 20, modeMaxSize)
    const correlationCap = estimateCorrelationCapUsd({
      modeMaxSize,
      portfolioCorrelation: signals.portfolio_correlation,
    })
    const conservativeCap = Math.min(modeMaxSize, liquidityCap, depthCap, correlationCap.cap_usd)
    const baseSizeUsd = Math.max(capitalTimeHaircut.adjusted_cash_available_usd * capitalFraction, 10)
    const sizing = buildKellyCappedPredictionMarketSizing({
      baseSizeUsd,
      maxSizeUsd: conservativeCap,
      signals,
      side: input.recommendation.action === 'bet'
        ? (input.recommendation.side ?? 'yes')
        : null,
      market_probability_yes: input.recommendation.market_price_yes ?? input.snapshot.midpoint_yes ?? input.snapshot.yes_price ?? input.snapshot.best_bid_yes ?? input.snapshot.best_ask_yes ?? null,
      forecast_probability_yes: input.forecast.probability_yes,
      capital_available_usd: capitalTimeHaircut.adjusted_cash_available_usd,
    })
    const correlationCapNote = correlationCap.binding && conservativeCap === correlationCap.cap_usd
      ? correlationCap.note
      : null

    return {
      requested_mode: input.mode,
      source: 'capital_ledger',
      base_size_usd: sizing.base_size_usd,
      recommended_size_usd: sizing.size_usd,
      max_size_usd: sizing.max_size_usd,
      conservative_cap_usd: sizing.conservative_cap_usd,
      effective_cap_usd: sizing.effective_cap_usd,
      multiplier: sizing.multiplier,
      kelly_fraction: sizing.kelly_fraction,
      kelly_cap_usd: sizing.kelly_cap_usd,
      kelly_edge_bps: sizing.kelly_edge_bps,
      kelly_applicable: sizing.kelly_applicable,
      kelly_reason: sizing.kelly_reason,
      market_probability_yes: sizing.market_probability_yes,
      forecast_probability_yes: sizing.forecast_probability_yes,
      factors: sizing.factors,
      notes: uniqueStrings([
        `preview sized from capital ledger cash_available_usd=${capital.cash_available_usd.toFixed(2)} using liquidity/depth-aware conservative sizing`,
        capitalTimeHaircut.note,
        ...sizing.notes,
        correlationCapNote,
      ]),
    }
  }

  const fallbackSize = input.mode === 'paper'
    ? 100
    : input.mode === 'shadow'
      ? 50
      : 25

  return {
    requested_mode: input.mode,
    source: 'default',
    base_size_usd: fallbackSize,
    recommended_size_usd: fallbackSize,
    max_size_usd: null,
    conservative_cap_usd: null,
    effective_cap_usd: null,
    multiplier: null,
    kelly_fraction: null,
    kelly_cap_usd: null,
    kelly_edge_bps: null,
    kelly_applicable: false,
    kelly_reason: 'Kelly overlay unavailable because no capital ledger is attached.',
    market_probability_yes: input.recommendation.market_price_yes ?? input.snapshot.midpoint_yes ?? input.snapshot.yes_price ?? input.snapshot.best_bid_yes ?? input.snapshot.best_ask_yes ?? null,
    forecast_probability_yes: input.forecast.probability_yes,
    factors: null,
    notes: ['preview sized from conservative default stake because no capital ledger is attached', 'Kelly overlay unavailable because no capital ledger is attached.'],
  }
}

export function buildPredictionMarketCanonicalTradeIntentPreview(input: {
  tradeIntentPreview: TradeIntent | null
  canonicalSizeUsd: number | null | undefined
}): TradeIntent | null {
  if (!input.tradeIntentPreview) return null

  if (
    input.canonicalSizeUsd == null ||
    !Number.isFinite(input.canonicalSizeUsd) ||
    input.canonicalSizeUsd <= 0 ||
    input.canonicalSizeUsd >= input.tradeIntentPreview.size_usd
  ) {
    return input.tradeIntentPreview
  }

  return {
    ...input.tradeIntentPreview,
    size_usd: input.canonicalSizeUsd,
    notes: uniqueStrings([
      input.tradeIntentPreview.notes,
      `Canonical execution sizing caps preview size to ${input.canonicalSizeUsd} USD.`,
    ]).join(' '),
  }
}

export type PredictionMarketExecutionApprovalTicketInput = PredictionMarketExecutionStrategySummaryInput & {
  run_id: string
  mode: PredictionMarketExecutionPreviewMode
  snapshot: MarketSnapshot
  forecast: ForecastPacket
  recommendation: MarketRecommendationPacket
  readiness: ExecutionPreviewReadinessInput
  trade_intent_preview?: TradeIntent | null
  canonical_trade_intent_preview?: TradeIntent | null
  source_bundle_id?: string | null
  source_packet_refs?: Array<string | null | undefined>
  social_context_refs?: Array<string | null | undefined>
  market_context_refs?: Array<string | null | undefined>
  no_trade_baseline_summary?: string | null
  generated_at?: string
  ticket_id?: string
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function formatSignedBps(value: number): string {
  const rounded = Math.round(value)
  return `${rounded >= 0 ? '+' : ''}${rounded} bps`
}

function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`
}

function safeTicketPart(value: string): string {
  return value
    .trim()
    .replace(/[^a-zA-Z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}

function resolveExecutionApprovalTradeIntentPreview(input: PredictionMarketExecutionApprovalTicketInput): TradeIntent | null {
  return input.canonical_trade_intent_preview ?? input.trade_intent_preview ?? null
}

function resolveExecutionApprovalStatus(input: {
  recommendation: MarketRecommendationPacket
  readiness: ExecutionPreviewReadinessInput
}): 'pending' | 'blocked' {
  if (input.recommendation.action !== 'bet') return 'blocked'
  if (input.readiness.overall_verdict === 'blocked') return 'blocked'
  if (input.readiness.blockers.length > 0) return 'blocked'
  return 'pending'
}

function resolveTicketSide(
  recommendation: MarketRecommendationPacket,
  tradeIntentPreview: TradeIntent | null,
): MarketRecommendationPacket['side'] {
  return tradeIntentPreview?.side ?? recommendation.side
}

function resolveTicketMarketPriceYes(
  snapshot: MarketSnapshot,
  recommendation: MarketRecommendationPacket,
): number | null {
  const candidate = recommendation.market_price_yes
    ?? snapshot.midpoint_yes
    ?? snapshot.yes_price
    ?? snapshot.best_bid_yes
    ?? snapshot.best_ask_yes
    ?? snapshot.market.last_trade_price

  return candidate != null && Number.isFinite(candidate) ? clamp(candidate, 0, 1) : null
}

function resolveTicketSelectedPrice(
  side: MarketRecommendationPacket['side'],
  marketPriceYes: number | null,
  tradeIntentPreview: TradeIntent | null,
): number | null {
  if (tradeIntentPreview) {
    return clamp(tradeIntentPreview.limit_price, 0, 1)
  }

  if (side == null || marketPriceYes == null) return null
  return side === 'yes' ? marketPriceYes : clamp(1 - marketPriceYes, 0, 1)
}

function resolveTicketSelectedFairValue(
  side: MarketRecommendationPacket['side'],
  recommendation: MarketRecommendationPacket,
): number {
  return side === 'no'
    ? clamp(1 - recommendation.fair_value_yes, 0, 1)
    : recommendation.fair_value_yes
}

function resolveTicketSelectedEdgeBps(
  side: MarketRecommendationPacket['side'],
  recommendation: MarketRecommendationPacket,
): number {
  if (side === 'no') {
    return -recommendation.edge_bps
  }

  return recommendation.edge_bps
}

function buildExecutionApprovalTicketSummary(input: {
  status: 'pending' | 'blocked'
  mode: PredictionMarketExecutionPreviewMode
  snapshot: MarketSnapshot
  recommendation: MarketRecommendationPacket
  side: MarketRecommendationPacket['side']
  selectedEdgeBps: number
  selectedFairValue: number
  selectedPrice: number | null
  sizingSummary: PredictionMarketExecutionSizingSummary
}): string {
  const sideLabel = input.side === 'no' ? 'NO' : input.side === 'yes' ? 'YES' : 'NO_TRADE'
  const priceLabel = input.selectedPrice == null ? 'unknown entry price' : `${formatPercent(input.selectedPrice)} entry`
  const fairLabel = formatPercent(input.selectedFairValue)
  const edgeLabel = input.selectedEdgeBps === 0
    ? 'flat edge'
    : `${formatSignedBps(input.selectedEdgeBps)} edge`

  return uniqueStrings([
    `${input.status === 'pending' ? 'Approval' : 'Blocked'} ticket for ${input.snapshot.market.question}.`,
    `${sideLabel} ${edgeLabel} against fair value ${fairLabel} and ${priceLabel}.`,
    `Mode ${input.mode}; proposed size ${formatUsd(input.sizingSummary.recommended_size_usd)}.`,
  ]).join(' ')
}

function buildExecutionApprovalTicketRationale(input: {
  strategySummary: string | null
  noTradeBaselineSummary: string | null
  readiness: ExecutionPreviewReadinessInput
  recommendation: MarketRecommendationPacket
  forecast: ForecastPacket
  marketPriceYes: number | null
  selectedEdgeBps: number
  selectedFairValue: number
  selectedPrice: number | null
  sizeUsd: number
  sizingSummary: PredictionMarketExecutionSizingSummary
  side: MarketRecommendationPacket['side']
  tradeIntentPreview: TradeIntent | null
}): string {
  const sideLabel = input.side === 'no' ? 'NO' : input.side === 'yes' ? 'YES' : 'NO_TRADE'
  const marketPriceLabel = input.marketPriceYes == null ? 'unknown market price' : formatPercent(input.marketPriceYes)
  const entryPriceLabel = input.selectedPrice == null ? 'unknown entry price' : formatPercent(input.selectedPrice)
  const thesisLines = uniqueStrings([
    `${sideLabel} appears ${input.selectedEdgeBps >= 0 ? 'underpriced' : 'overpriced'} by ${Math.abs(input.selectedEdgeBps / 100).toFixed(1)} pts relative to fair value ${formatPercent(input.selectedFairValue)} and market ${marketPriceLabel}.`,
    `Entry preview is ${entryPriceLabel}; expected value remains ${formatSignedBps(input.selectedEdgeBps)} per share.`,
    `Forecast anchors at ${formatPercent(input.forecast.probability_yes)} with confidence ${formatPercent(input.forecast.confidence)}; recommendation confidence is ${formatPercent(input.recommendation.confidence)}.`,
    `Proposed size is ${formatUsd(input.sizeUsd)} from ${input.sizingSummary.source}.`,
    `Readiness verdict: ${input.readiness.overall_verdict}; highest safe mode: ${input.readiness.highest_safe_mode ?? 'none'}.`,
    input.recommendation.action !== 'bet'
      ? `Recommendation is ${input.recommendation.action}; approval remains blocked until a trade recommendation is produced.`
      : null,
    input.strategySummary ? `Strategy context: ${input.strategySummary}.` : null,
    input.noTradeBaselineSummary ? `Baseline: ${input.noTradeBaselineSummary}` : null,
    input.tradeIntentPreview?.notes ? `Trade intent notes: ${input.tradeIntentPreview.notes}.` : null,
    input.recommendation.rationale ? `Recommendation rationale: ${input.recommendation.rationale}.` : null,
  ])

  return thesisLines.join(' ')
}

function buildExecutionApprovalTicketNotes(input: {
  strategySummary: string | null
  strategyNotes: string[]
  recommendation: MarketRecommendationPacket
  readiness: ExecutionPreviewReadinessInput
  sizingSummary: PredictionMarketExecutionSizingSummary
  approvalStateSummary: string
  noTradeBaselineSummary: string | null
  tradeIntentPreview: TradeIntent | null
}): string[] {
  return uniqueStrings([
    input.strategySummary ? `Strategy context: ${input.strategySummary}.` : null,
    ...input.strategyNotes,
    input.noTradeBaselineSummary ? `Baseline: ${input.noTradeBaselineSummary}` : null,
    input.recommendation.reasons.length > 0
      ? `Recommendation reasons: ${uniqueStrings(input.recommendation.reasons).join(', ')}.`
      : null,
    input.recommendation.risk_flags.length > 0
      ? `Risk flags: ${uniqueStrings(input.recommendation.risk_flags).join(', ')}.`
      : null,
    input.recommendation.why_now.length > 0
      ? `Why now: ${uniqueStrings(input.recommendation.why_now).join(' | ')}.`
      : null,
    input.recommendation.why_not_now.length > 0
      ? `Why not now: ${uniqueStrings(input.recommendation.why_not_now).join(' | ')}.`
      : null,
    input.recommendation.watch_conditions.length > 0
      ? `Watch conditions: ${uniqueStrings(input.recommendation.watch_conditions).join(' | ')}.`
      : null,
    input.tradeIntentPreview?.notes ? `Trade intent notes: ${input.tradeIntentPreview.notes}.` : null,
    ...input.sizingSummary.notes.map((note) => `Sizing: ${note}`),
    `Readiness: ${input.readiness.summary}.`,
    `Approval workflow: ${input.approvalStateSummary}`,
  ])
}

export function buildPredictionMarketExecutionApprovalTicket(
  input: PredictionMarketExecutionApprovalTicketInput,
): ApprovalTradeTicket {
  const generatedAt = input.generated_at ?? input.recommendation.produced_at
  const ticketId = input.ticket_id
    ?? `approval-${safeTicketPart(input.run_id)}-${safeTicketPart(input.snapshot.market.market_id)}-${safeTicketPart(input.mode)}-${safeTicketPart(input.recommendation.action)}`
  const strategySummary = buildPredictionMarketStrategySummary(input)
  const strategyNotes = buildPredictionMarketStrategyNotes(input)
  const noTradeBaselineSummary = input.no_trade_baseline_summary ?? (
    input.recommendation.action === 'bet'
      ? null
      : buildPredictionMarketNoTradeBaselineSummary({
        recommendation_action: input.recommendation.action,
        ...input,
      })
  )
  const sizingSummary = buildPredictionMarketExecutionSizingSummary({
    mode: input.mode,
    snapshot: input.snapshot,
    forecast: input.forecast,
    recommendation: input.recommendation,
    readiness: input.readiness,
  })
  const tradeIntentPreview = resolveExecutionApprovalTradeIntentPreview(input)
  const side = resolveTicketSide(input.recommendation, tradeIntentPreview)
  const marketPriceYes = resolveTicketMarketPriceYes(input.snapshot, input.recommendation)
  const selectedPrice = resolveTicketSelectedPrice(side, marketPriceYes, tradeIntentPreview)
  const selectedFairValue = resolveTicketSelectedFairValue(side, input.recommendation)
  const selectedEdgeBps = resolveTicketSelectedEdgeBps(side, input.recommendation)
  const sizeUsd = tradeIntentPreview?.size_usd ?? sizingSummary.recommended_size_usd
  const status = resolveExecutionApprovalStatus({
    recommendation: input.recommendation,
    readiness: input.readiness,
  })
  const workflowStage = status === 'pending' ? 'approval' : 'blocked'
  const approvalStateSummary = status === 'pending'
    ? `Pending operator review for ${side === 'no' ? 'NO' : side === 'yes' ? 'YES' : 'no-trade'} execution.`
    : `Blocked: ${input.recommendation.action !== 'bet'
      ? `recommendation is ${input.recommendation.action}`
      : input.readiness.blockers[0] ?? 'execution readiness is blocked'
    }.`
  const summary = buildExecutionApprovalTicketSummary({
    status,
    mode: input.mode,
    snapshot: input.snapshot,
    recommendation: input.recommendation,
    side,
    selectedEdgeBps,
    selectedFairValue,
    selectedPrice,
    sizingSummary,
  })
  const rationale = buildExecutionApprovalTicketRationale({
    strategySummary,
    noTradeBaselineSummary,
    readiness: input.readiness,
    recommendation: input.recommendation,
    forecast: input.forecast,
    marketPriceYes,
    selectedEdgeBps,
    selectedFairValue,
    selectedPrice,
    sizeUsd,
    sizingSummary,
    side,
    tradeIntentPreview,
  })
  const notes = buildExecutionApprovalTicketNotes({
    strategySummary,
    strategyNotes,
    recommendation: input.recommendation,
    readiness: input.readiness,
    sizingSummary,
    approvalStateSummary,
    noTradeBaselineSummary,
    tradeIntentPreview,
  })
  const sourceBundleId = input.source_bundle_id
    ?? input.forecast.source_bundle_id
    ?? input.recommendation.source_bundle_id
    ?? null
  const sourcePacketRefs = uniqueStrings([
    ...(input.source_packet_refs ?? []),
    ...input.forecast.source_packet_refs,
    ...input.recommendation.source_packet_refs,
    tradeIntentPreview?.forecast_ref,
  ])
  const socialContextRefs = uniqueStrings([
    ...(input.social_context_refs ?? []),
    ...input.forecast.social_context_refs,
    ...input.recommendation.social_context_refs,
  ])
  const marketContextRefs = uniqueStrings([
    ...(input.market_context_refs ?? []),
    ...input.forecast.market_context_refs,
    ...input.recommendation.market_context_refs,
  ])

  return {
    schema_version: input.forecast.schema_version,
    ticket_id: ticketId,
    ticket_kind: 'approval_trade_ticket',
    workflow_stage: workflowStage,
    run_id: input.run_id,
    venue: input.snapshot.venue,
    market_id: input.snapshot.market.market_id,
    market_slug: input.snapshot.market.slug,
    source_bundle_id: sourceBundleId ?? undefined,
    source_packet_refs: sourcePacketRefs,
    social_context_refs: socialContextRefs,
    market_context_refs: marketContextRefs,
    recommendation: input.recommendation.action,
    side,
    size_usd: sizeUsd,
    limit_price: selectedPrice ?? undefined,
    edge_bps: input.recommendation.edge_bps,
    spread_bps: input.recommendation.spread_bps,
    confidence: clamp(Math.min(input.forecast.confidence, input.recommendation.confidence), 0, 1),
    rationale,
    summary,
    approval_state: {
      status: status,
      requested_by: 'execution-preview',
      requested_at: generatedAt,
      required_approvals: 2,
      current: 0,
      approvers: [],
      rejections: [],
      approved_at: null,
      rejected_at: null,
      summary: approvalStateSummary,
      metadata: {
        mode: input.mode,
        market_question: input.snapshot.market.question,
        market_midpoint_yes: input.snapshot.midpoint_yes,
        market_price_yes: marketPriceYes,
        fair_value_yes: input.recommendation.fair_value_yes,
        selected_side: side,
        selected_side_price: selectedPrice,
        selected_side_fair_value: selectedFairValue,
        selected_side_edge_bps: selectedEdgeBps,
        approval_checks: uniqueStrings([
          `Readiness verdict: ${input.readiness.overall_verdict}.`,
          `Highest safe mode: ${input.readiness.highest_safe_mode ?? 'none'}.`,
          `Recommendation action: ${input.recommendation.action}.`,
          `Forecast probability: ${formatPercent(input.forecast.probability_yes)}.`,
          `Recommendation confidence: ${formatPercent(input.recommendation.confidence)}.`,
          `Sizing source: ${sizingSummary.source}.`,
        ]),
        blockers: input.readiness.blockers,
        warnings: input.readiness.warnings,
        strategy_summary: strategySummary,
        no_trade_baseline_summary: noTradeBaselineSummary,
      },
    },
    trade_intent_preview: tradeIntentPreview ?? undefined,
    approved_trade_intent_ref: undefined,
    approved_by: [],
    rejected_by: [],
    notes,
    created_at: generatedAt,
    updated_at: generatedAt,
    metadata: {
      ticket_source: 'execution_preview',
      requested_mode: input.mode,
      market_question: input.snapshot.market.question,
      market_regime_summary: input.market_regime_summary ?? null,
      primary_strategy_summary: input.primary_strategy_summary ?? null,
      strategy_summary: strategySummary,
      no_trade_baseline_summary: noTradeBaselineSummary,
      approval_thesis: rationale,
      approval_checks: uniqueStrings([
        `market_id:${input.snapshot.market.market_id}`,
        `ticket_status:${status}`,
        `approval_state:${approvalStateSummary}`,
      ]),
      sizing_summary: sizingSummary,
      readiness_summary: input.readiness.summary,
      readiness_blockers: input.readiness.blockers,
      readiness_warnings: input.readiness.warnings,
      source_bundle_id: sourceBundleId,
      source_packet_refs: sourcePacketRefs,
      social_context_refs: socialContextRefs,
      market_context_refs: marketContextRefs,
      trade_intent_preview_available: tradeIntentPreview != null,
    },
  }
}
