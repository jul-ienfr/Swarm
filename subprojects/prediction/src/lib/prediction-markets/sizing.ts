export type PredictionMarketSizingSignals = {
  confidence: number
  calibration_ece?: number | null
  liquidity_usd?: number | null
  depth_near_touch?: number | null
  portfolio_correlation?: number | null
}

export type ConservativePredictionMarketSizingInput = {
  baseSizeUsd: number
  minSizeUsd?: number
  maxSizeUsd?: number
  signals: PredictionMarketSizingSignals
}

export type ConservativePredictionMarketSizingResult = {
  base_size_usd: number
  size_usd: number
  multiplier: number
  factors: {
    confidence_factor: number
    calibration_factor: number
    liquidity_factor: number
    depth_factor: number
    portfolio_correlation_factor: number
    conservatism_cap_factor: number
  }
  notes: string[]
}

const DEFAULT_CONSERVATISM_CAP_FACTOR = 0.85
const DEFAULT_MISSING_CALIBRATION_FACTOR = 0.8
const DEFAULT_MISSING_LIQUIDITY_FACTOR = 0.82
const DEFAULT_MISSING_DEPTH_FACTOR = 0.82
const DEFAULT_MISSING_PORTFOLIO_CORRELATION_FACTOR = 0.88

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function requireFinitePositive(value: number, label: string): number {
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`${label} must be a positive finite number`)
  }

  return value
}

function confidenceFactor(confidence: number): number {
  return clamp(0.45 + (0.55 * clamp(confidence, 0, 1)), 0.45, 1)
}

function calibrationFactor(calibrationEce: number | null | undefined): number {
  if (calibrationEce == null) return DEFAULT_MISSING_CALIBRATION_FACTOR
  return clamp(1 - (0.28 * clamp(calibrationEce, 0, 1)), 0.72, 1)
}

function liquidityFactor(liquidityUsd: number | null | undefined): number {
  if (liquidityUsd == null) return DEFAULT_MISSING_LIQUIDITY_FACTOR

  const normalized = clamp(liquidityUsd / 100_000, 0, 1)
  return clamp(0.55 + (0.45 * Math.sqrt(normalized)), 0.55, 1)
}

function depthFactor(depthNearTouch: number | null | undefined): number {
  if (depthNearTouch == null) return DEFAULT_MISSING_DEPTH_FACTOR

  const normalized = clamp(depthNearTouch / 5_000, 0, 1)
  return clamp(0.55 + (0.45 * Math.sqrt(normalized)), 0.55, 1)
}

function portfolioCorrelationFactor(portfolioCorrelation: number | null | undefined): number {
  if (portfolioCorrelation == null) return DEFAULT_MISSING_PORTFOLIO_CORRELATION_FACTOR

  const normalizedCorrelation = clamp(Math.abs(portfolioCorrelation), 0, 1)
  return clamp(1 - (0.4 * normalizedCorrelation), 0.6, 1)
}

function formatPercent(value: number): string {
  return `${Math.round(value * 1000) / 10}%`
}

export function buildConservativePredictionMarketSizing(
  input: ConservativePredictionMarketSizingInput,
): ConservativePredictionMarketSizingResult {
  const baseSizeUsd = requireFinitePositive(input.baseSizeUsd, 'baseSizeUsd')
  const minSizeUsd = input.minSizeUsd == null ? 0 : Math.max(0, input.minSizeUsd)
  const maxSizeUsd = input.maxSizeUsd == null ? Number.POSITIVE_INFINITY : requireFinitePositive(input.maxSizeUsd, 'maxSizeUsd')

  if (minSizeUsd > maxSizeUsd) {
    throw new Error('minSizeUsd cannot be greater than maxSizeUsd')
  }

  const confidence = clamp(input.signals.confidence, 0, 1)
  const confidence_factor = confidenceFactor(confidence)
  const calibration_factor = calibrationFactor(input.signals.calibration_ece)
  const liquidity_factor = liquidityFactor(input.signals.liquidity_usd)
  const depth_factor = depthFactor(input.signals.depth_near_touch)
  const portfolio_correlation_factor = portfolioCorrelationFactor(input.signals.portfolio_correlation)

  const rawMultiplier =
    confidence_factor *
    calibration_factor *
    liquidity_factor *
    depth_factor *
    portfolio_correlation_factor

  const conservatism_cap_factor = DEFAULT_CONSERVATISM_CAP_FACTOR
  const multiplier = clamp(rawMultiplier, 0.05, conservatism_cap_factor)
  const unclampedSizeUsd = baseSizeUsd * multiplier
  const clampedSizeUsd = clamp(unclampedSizeUsd, minSizeUsd, maxSizeUsd)
  const size_usd = Number(clampedSizeUsd.toFixed(2))

  const notes: string[] = [
    `Base size ${baseSizeUsd.toFixed(2)} USD scaled by multiplier ${formatPercent(multiplier)}.`,
  ]

  if (confidence < 0.75) {
    notes.push(`Confidence ${formatPercent(confidence)} is below the conservative comfort band.`)
  }

  if (input.signals.calibration_ece == null) {
    notes.push('Calibration unavailable, applying a default haircut.')
  } else if (input.signals.calibration_ece > 0.2) {
    notes.push(`Calibration ECE ${formatPercent(input.signals.calibration_ece)} indicates weak historical reliability.`)
  }

  if (input.signals.liquidity_usd == null) {
    notes.push('Liquidity unavailable, keeping a conservative liquidity haircut.')
  } else if (input.signals.liquidity_usd < 25_000) {
    notes.push(`Liquidity ${input.signals.liquidity_usd.toFixed(2)} USD is thin.`)
  }

  if (input.signals.depth_near_touch == null) {
    notes.push('Depth unavailable, keeping a conservative depth haircut.')
  } else if (input.signals.depth_near_touch < 1_000) {
    notes.push(`Near-touch depth ${input.signals.depth_near_touch.toFixed(2)} is shallow.`)
  }

  if (input.signals.portfolio_correlation == null) {
    notes.push('Portfolio correlation unavailable, using a cautious default.')
  } else if (Math.abs(input.signals.portfolio_correlation) > 0.5) {
    notes.push(`Portfolio correlation ${formatPercent(Math.abs(input.signals.portfolio_correlation))} is elevated.`)
  }

  return {
    base_size_usd: Number(baseSizeUsd.toFixed(2)),
    size_usd,
    multiplier: Number(multiplier.toFixed(4)),
    factors: {
      confidence_factor: Number(confidence_factor.toFixed(4)),
      calibration_factor: Number(calibration_factor.toFixed(4)),
      liquidity_factor: Number(liquidity_factor.toFixed(4)),
      depth_factor: Number(depth_factor.toFixed(4)),
      portfolio_correlation_factor: Number(portfolio_correlation_factor.toFixed(4)),
      conservatism_cap_factor: conservatism_cap_factor,
    },
    notes,
  }
}
