import type {
  MeteoBestBetsSummary,
  MeteoBinFairValue,
  MeteoForecastPoint,
  MeteoPricingOpportunity,
  MeteoPricingInput,
  MeteoPricingReport,
  MeteoTemperatureBin,
} from '@/lib/prediction-markets/meteo/types'
import { buildMeteoForecastConsensus } from '@/lib/prediction-markets/meteo/sources'

const SQRT_TWO = Math.sqrt(2)

export function buildMeteoPricingReport(input: MeteoPricingInput): MeteoPricingReport {
  if (!input.spec.unit) {
    throw new Error('Cannot price meteo market without a temperature unit')
  }
  if (!input.spec.bins.length) {
    throw new Error('Cannot price meteo market without parsed bins')
  }

  const consensus = buildMeteoForecastConsensus(input.forecastPoints)
  const bins = input.spec.bins.map((bin) => toBinFairValue(bin, consensus, input.marketPrices ?? {}))

  return {
    mean: consensus.mean,
    stddev: consensus.stddev,
    unit: input.spec.unit,
    bins,
    opportunities: buildPricingOpportunities(bins),
    marketSnapshot: buildMarketSnapshot(bins),
    provenance: {
      providerCount: consensus.providers.length,
      providers: consensus.providers,
      contributions: consensus.contributions,
    },
  }
}

export function blendForecastPoints(points: MeteoForecastPoint[]): { mean: number; stddev: number } {
  const consensus = buildMeteoForecastConsensus(points)
  return {
    mean: consensus.mean,
    stddev: consensus.stddev,
  }
}

export function buildMeteoBestBetsSummary(
  report: MeteoPricingReport,
  options?: { limit?: number },
): MeteoBestBetsSummary {
  const limit = Math.max(1, options?.limit ?? 3)
  const topOpportunities = report.opportunities.slice(0, limit)
  const strongestOpportunity = topOpportunities[0] ?? null
  const recommendedSideCounts = report.bins.reduce(
    (counts, bin) => {
      counts[bin.recommendedSide] += 1
      return counts
    },
    { yes: 0, no: 0, pass: 0 },
  )
  const noTradeLabels = report.bins
    .filter((bin) => bin.recommendedSide === 'pass')
    .map((bin) => bin.label)

  return {
    summary: strongestOpportunity
      ? `Top météo bet: ${strongestOpportunity.side.toUpperCase()} ${strongestOpportunity.label} at ${formatPrice(strongestOpportunity.marketPrice)} vs fair ${formatPrice(strongestOpportunity.fairPrice)} (edge ${formatSignedPercent(strongestOpportunity.edge)}, ROI ${formatSignedPercent(strongestOpportunity.expectedRoi)}).`
      : `No actionable météo edge found across ${report.bins.length} bins.`,
    actionableCount: report.opportunities.length,
    strongestOpportunity,
    topOpportunities,
    recommendedSideCounts,
    noTradeLabels,
  }
}

function toBinFairValue(
  bin: MeteoTemperatureBin,
  distribution: { mean: number; stddev: number },
  marketPrices: Record<string, number>,
): MeteoBinFairValue {
  const lower = bin.lower ? adjustBound(bin.lower.value, bin.lower.inclusive, 'lower') : Number.NEGATIVE_INFINITY
  const upper = bin.upper ? adjustBound(bin.upper.value, bin.upper.inclusive, 'upper') : Number.POSITIVE_INFINITY
  const probability = clamp(normalCdf(upper, distribution.mean, distribution.stddev) - normalCdf(lower, distribution.mean, distribution.stddev))
  const fairYesPrice = round4(probability)
  const marketYesPrice = Number.isFinite(marketPrices[bin.label]) ? marketPrices[bin.label] : null
  return buildBinFairValue({
    label: bin.label,
    probability: fairYesPrice,
    fairYesPrice,
    marketYesPrice,
  })
}

function buildBinFairValue(input: {
  label: string
  probability: number
  fairYesPrice: number
  marketYesPrice: number | null
}): MeteoBinFairValue {
  const fairYesPrice = round4(input.fairYesPrice)
  const fairNoPrice = round4(1 - fairYesPrice)
  const marketYesPrice = input.marketYesPrice === null ? null : round4(input.marketYesPrice)
  const marketNoPrice = marketYesPrice === null ? null : round4(1 - marketYesPrice)
  const yesEdge = marketYesPrice === null ? null : round4(fairYesPrice - marketYesPrice)
  const noEdge = marketNoPrice === null ? null : round4(fairNoPrice - marketNoPrice)

  return {
    label: input.label,
    probability: round4(input.probability),
    fairYesPrice,
    fairNoPrice,
    marketYesPrice,
    marketNoPrice,
    edge: yesEdge,
    yesEdge,
    noEdge,
    expectedValueYes: yesEdge,
    expectedValueNo: noEdge,
    expectedRoiYes: yesEdge === null || marketYesPrice === null || marketYesPrice <= 0 ? null : round4(yesEdge / marketYesPrice),
    expectedRoiNo: noEdge === null || marketNoPrice === null || marketNoPrice <= 0 ? null : round4(noEdge / marketNoPrice),
    recommendedSide: yesEdge === null || noEdge === null
      ? 'pass'
      : yesEdge > 0
        ? 'yes'
        : noEdge > 0
          ? 'no'
          : 'pass',
  }
}

function buildPricingOpportunities(bins: MeteoBinFairValue[]): MeteoPricingOpportunity[] {
  return bins
    .flatMap((bin) => {
      const opportunities: MeteoPricingOpportunity[] = []
      if (bin.marketYesPrice !== null && (bin.yesEdge ?? 0) > 0) {
        opportunities.push({
          label: bin.label,
          side: 'yes',
          edge: bin.yesEdge ?? 0,
          expectedValue: bin.expectedValueYes ?? 0,
          expectedRoi: bin.expectedRoiYes,
          fairPrice: bin.fairYesPrice,
          marketPrice: bin.marketYesPrice,
        })
      }
      if (bin.marketNoPrice !== null && (bin.noEdge ?? 0) > 0) {
        opportunities.push({
          label: bin.label,
          side: 'no',
          edge: bin.noEdge ?? 0,
          expectedValue: bin.expectedValueNo ?? 0,
          expectedRoi: bin.expectedRoiNo,
          fairPrice: bin.fairNoPrice,
          marketPrice: bin.marketNoPrice,
        })
      }
      return opportunities
    })
    .sort((left, right) => right.edge - left.edge)
}

function buildMarketSnapshot(bins: MeteoBinFairValue[]): MeteoPricingReport['marketSnapshot'] {
  const pricedBins = bins.filter((bin) => bin.marketYesPrice !== null)
  if (!pricedBins.length) {
    return {
      pricedBinCount: 0,
      yesPriceSum: null,
      overround: null,
    }
  }

  const yesPriceSum = round4(pricedBins.reduce((sum, bin) => sum + (bin.marketYesPrice ?? 0), 0))
  return {
    pricedBinCount: pricedBins.length,
    yesPriceSum,
    overround: round4(yesPriceSum - 1),
  }
}

function adjustBound(value: number, inclusive: boolean, side: 'lower' | 'upper'): number {
  if (inclusive) {
    return side === 'lower' ? value - 0.5 : value + 0.5
  }
  return value
}

function normalCdf(value: number, mean: number, stddev: number): number {
  const z = (value - mean) / (stddev * SQRT_TWO)
  return 0.5 * (1 + erf(z))
}

function erf(value: number): number {
  const sign = value < 0 ? -1 : 1
  const x = Math.abs(value)
  const a1 = 0.254829592
  const a2 = -0.284496736
  const a3 = 1.421413741
  const a4 = -1.453152027
  const a5 = 1.061405429
  const p = 0.3275911
  const t = 1 / (1 + p * x)
  const y = 1 - (((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * Math.exp(-x * x))
  return sign * y
}

function clamp(value: number): number {
  return Math.min(1, Math.max(0, value))
}

function round4(value: number): number {
  return Math.round(value * 10_000) / 10_000
}

function formatPrice(value: number): string {
  return value.toFixed(2)
}

function formatSignedPercent(value: number | null): string {
  if (value === null) return 'n/a'
  const percent = round4(value * 100)
  return `${percent > 0 ? '+' : ''}${percent.toFixed(2)}%`
}
