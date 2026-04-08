import {
  type ForecastPacket,
  type MarketRecommendationPacket,
  type MarketSnapshot,
  type TradeIntent,
} from '@/lib/prediction-markets/schemas'
import { type PredictionMarketExecutionReadinessReport } from '@/lib/prediction-markets/execution-readiness'
import {
  buildConservativePredictionMarketSizing,
  type ConservativePredictionMarketSizingResult,
} from '@/lib/prediction-markets/sizing'

export type PredictionMarketExecutionPreviewMode = 'paper' | 'shadow' | 'live'

export type PredictionMarketExecutionSizingSummary = {
  requested_mode: PredictionMarketExecutionPreviewMode
  source: 'capital_ledger' | 'default'
  base_size_usd: number
  recommended_size_usd: number
  max_size_usd: number | null
  multiplier: number | null
  factors: ConservativePredictionMarketSizingResult['factors'] | null
  notes: string[]
}

export type PredictionMarketExecutionStrategySummaryInput = {
  strategy_name?: string | null
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
}

type ExecutionPreviewReadinessInput = PredictionMarketExecutionReadinessReport & {
  calibration_ece?: number | null
  portfolio_correlation?: number | null
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
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
    const liquidityUsd = input.snapshot.market.liquidity_usd
    const depthNearTouch = input.snapshot.book?.depth_near_touch ?? null
    const liquidityCap = liquidityUsd == null
      ? modeMaxSize
      : clamp(liquidityUsd * 0.001, 25, modeMaxSize)
    const depthCap = depthNearTouch == null
      ? modeMaxSize
      : clamp(depthNearTouch * 0.06, 20, modeMaxSize)
    const conservativeCap = Math.min(modeMaxSize, liquidityCap, depthCap)
    const baseSizeUsd = Math.max(capital.cash_available_usd * capitalFraction, 10)
    const sizing = buildConservativePredictionMarketSizing({
      baseSizeUsd,
      maxSizeUsd: conservativeCap,
      signals: estimateSizingSignals({
        snapshot: input.snapshot,
        forecast: input.forecast,
        recommendation: input.recommendation,
        readiness: input.readiness,
      }),
    })

    return {
      requested_mode: input.mode,
      source: 'capital_ledger',
      base_size_usd: sizing.base_size_usd,
      recommended_size_usd: sizing.size_usd,
      max_size_usd: Number(conservativeCap.toFixed(2)),
      multiplier: sizing.multiplier,
      factors: sizing.factors,
      notes: [
        `preview sized from capital ledger cash_available_usd=${capital.cash_available_usd.toFixed(2)} using liquidity/depth-aware conservative sizing`,
        ...sizing.notes,
      ],
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
    multiplier: null,
    factors: null,
    notes: ['preview sized from conservative default stake because no capital ledger is attached'],
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
