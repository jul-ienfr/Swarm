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

export type KellyCappedPredictionMarketSizingInput = ConservativePredictionMarketSizingInput & {
  side?: 'yes' | 'no' | null
  market_probability_yes?: number | null
  forecast_probability_yes?: number | null
  capital_available_usd?: number | null
}

export type ConservativePredictionMarketSizingResult = {
  base_size_usd: number
  size_usd: number
  multiplier: number
  max_size_usd: number | null
  conservative_cap_usd: number | null
  kelly_cap_usd: number | null
  effective_cap_usd: number | null
  kelly_fraction: number | null
  kelly_edge_bps: number | null
  kelly_applicable: boolean
  kelly_reason: string | null
  market_probability_yes: number | null
  forecast_probability_yes: number | null
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
  return clamp(1 - (0.55 * normalizedCorrelation), 0.5, 1)
}

function formatPercent(value: number): string {
  return `${Math.round(value * 1000) / 10}%`
}

function roundTwo(value: number): number {
  return Number(value.toFixed(2))
}

function normalizeProbability(value: number | null | undefined): number | null {
  if (typeof value !== 'number' || Number.isNaN(value)) return null
  return clamp(value, 0, 1)
}

function formatKellyFraction(value: number): string {
  return `${Math.round(value * 1000) / 10}% Kelly`
}

function computeKellyOverlay(input: KellyCappedPredictionMarketSizingInput): {
  market_probability_yes: number | null
  forecast_probability_yes: number | null
  kelly_fraction: number | null
  kelly_cap_usd: number | null
  kelly_edge_bps: number | null
  kelly_applicable: boolean
  kelly_reason: string | null
} {
  const side = input.side ?? null
  const marketProbabilityYes = normalizeProbability(input.market_probability_yes)
  const forecastProbabilityYes = normalizeProbability(input.forecast_probability_yes)
  const capitalAvailableUsd = typeof input.capital_available_usd === 'number' && Number.isFinite(input.capital_available_usd) && input.capital_available_usd > 0
    ? input.capital_available_usd
    : null

  if (!side || marketProbabilityYes == null || forecastProbabilityYes == null || capitalAvailableUsd == null) {
    return {
      market_probability_yes: marketProbabilityYes,
      forecast_probability_yes: forecastProbabilityYes,
      kelly_fraction: null,
      kelly_cap_usd: null,
      kelly_edge_bps: null,
      kelly_applicable: false,
      kelly_reason: !side
        ? 'Kelly overlay unavailable because no bet side was selected.'
        : marketProbabilityYes == null || forecastProbabilityYes == null
          ? 'Kelly overlay unavailable because forecast or market probability is missing.'
          : 'Kelly overlay unavailable because no capital ledger is attached.',
    }
  }

  const directionalForecastProbability = side === 'no' ? 1 - forecastProbabilityYes : forecastProbabilityYes
  const directionalMarketProbability = side === 'no' ? 1 - marketProbabilityYes : marketProbabilityYes
  const edge = directionalForecastProbability - directionalMarketProbability
  const denominator = Math.max(1 - directionalMarketProbability, 0.0001)
  const rawKellyFraction = clamp(edge / denominator, 0, 1)
  const kellyCapUsd = roundTwo(capitalAvailableUsd * rawKellyFraction)

  return {
    market_probability_yes: marketProbabilityYes,
    forecast_probability_yes: forecastProbabilityYes,
    kelly_fraction: Number(rawKellyFraction.toFixed(4)),
    kelly_cap_usd: kellyCapUsd,
    kelly_edge_bps: Math.round(edge * 10_000),
    kelly_applicable: rawKellyFraction > 0,
    kelly_reason: rawKellyFraction > 0
      ? `Kelly overlay recommends ${formatKellyFraction(rawKellyFraction)} before conservative caps.`
      : 'Kelly overlay sees no positive edge and does not increase the stake.',
  }
}

export function buildKellyCappedPredictionMarketSizing(
  input: KellyCappedPredictionMarketSizingInput,
): ConservativePredictionMarketSizingResult {
  const conservative = buildConservativePredictionMarketSizing(input)
  const overlay = computeKellyOverlay(input)
  const conservativeCapUsd = conservative.max_size_usd
  const effectiveCapUsd = overlay.kelly_cap_usd == null
    ? conservativeCapUsd
    : overlay.kelly_cap_usd > 0
      ? Math.min(conservativeCapUsd, overlay.kelly_cap_usd)
      : conservativeCapUsd

  const isKellyBinding = overlay.kelly_cap_usd != null && overlay.kelly_cap_usd > 0 && effectiveCapUsd < conservative.size_usd
  const size_usd = isKellyBinding ? roundTwo(effectiveCapUsd) : conservative.size_usd
  const multiplier = roundTwo(size_usd / conservative.base_size_usd)

  const notes = [
    ...conservative.notes,
    overlay.kelly_reason,
    overlay.kelly_fraction != null
      ? `Kelly overlay: market=${overlay.market_probability_yes == null ? 'n/a' : formatPercent(overlay.market_probability_yes)} forecast=${overlay.forecast_probability_yes == null ? 'n/a' : formatPercent(overlay.forecast_probability_yes)} edge=${overlay.kelly_edge_bps ?? 0}bps cap=${overlay.kelly_cap_usd?.toFixed(2) ?? 'n/a'} USD.`
      : null,
    isKellyBinding
      ? `Kelly overlay caps the recommended size to ${size_usd.toFixed(2)} USD from ${conservative.size_usd.toFixed(2)} USD.`
      : null,
  ].filter((note): note is string => typeof note === 'string' && note.trim().length > 0)

  return {
    ...conservative,
    size_usd,
    multiplier,
    max_size_usd: conservative.max_size_usd,
    conservative_cap_usd: conservativeCapUsd,
    kelly_cap_usd: overlay.kelly_cap_usd,
    effective_cap_usd: effectiveCapUsd,
    kelly_fraction: overlay.kelly_fraction,
    kelly_edge_bps: overlay.kelly_edge_bps,
    kelly_applicable: overlay.kelly_applicable,
    kelly_reason: overlay.kelly_reason,
    market_probability_yes: overlay.market_probability_yes,
    forecast_probability_yes: overlay.forecast_probability_yes,
    notes,
  }
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
    max_size_usd: Number.isFinite(maxSizeUsd) ? Number(maxSizeUsd.toFixed(2)) : null,
    conservative_cap_usd: Number.isFinite(maxSizeUsd) ? Number(maxSizeUsd.toFixed(2)) : null,
    kelly_cap_usd: null,
    effective_cap_usd: Number(clampedSizeUsd.toFixed(2)),
    kelly_fraction: null,
    kelly_edge_bps: null,
    kelly_applicable: false,
    kelly_reason: null,
    market_probability_yes: null,
    forecast_probability_yes: null,
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
