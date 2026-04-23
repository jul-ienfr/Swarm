import type {
  MeteoExecutionCandidate,
  MeteoExecutionSummary,
  MeteoForecastPoint,
  MeteoMarketAnomaly,
  MeteoPricingReport,
} from '@/lib/prediction-markets/meteo/types'

export function buildMeteoExecutionCandidates(input: {
  report: MeteoPricingReport
  forecastPoints: MeteoForecastPoint[]
  minEdgeBps?: number
}): MeteoExecutionCandidate[] {
  const minEdgeBps = input.minEdgeBps ?? 0

  return input.report.opportunities
    .map((opportunity) => {
      const edgeBps = Math.round(opportunity.edge * 10_000)
      const confidence = edgeBps >= 1_500 ? 'high' : edgeBps >= 500 ? 'medium' : 'low'
      const priority = edgeBps >= 2_000 ? 'high' : edgeBps >= 1_000 ? 'medium' : 'low'
      const tradeable = edgeBps >= minEdgeBps

      return {
        label: opportunity.label,
        side: opportunity.side,
        marketPrice: opportunity.marketPrice,
        fairPrice: opportunity.fairPrice,
        edge: opportunity.edge,
        edgeBps,
        expectedValue: opportunity.expectedValue,
        expectedRoi: opportunity.expectedRoi,
        confidence,
        priority,
        tradeable,
        maxEntryPrice: opportunity.fairPrice,
        noTradeAbove: opportunity.fairPrice,
        reasonCodes: [tradeable ? 'raw_edge' : 'below_min_edge_bps'],
      } satisfies MeteoExecutionCandidate
    })
    .sort((left, right) => right.edgeBps - left.edgeBps)
}

export function detectMeteoMarketAnomalies(report: MeteoPricingReport): MeteoMarketAnomaly[] {
  const anomalies: MeteoMarketAnomaly[] = []

  for (let index = 0; index < report.bins.length - 1; index += 1) {
    const current = report.bins[index]
    const next = report.bins[index + 1]
    if (
      current.marketYesPrice !== null
      && next.marketYesPrice !== null
      && current.fairYesPrice < next.fairYesPrice
      && current.marketYesPrice > next.marketYesPrice
    ) {
      const severity = Math.abs(current.marketYesPrice - next.marketYesPrice) >= 0.1 ? 'high' : 'medium'
      anomalies.push({
        type: 'adjacent_gap',
        label: `${current.label}|${next.label}`,
        severity,
        details: 'Adjacent bins invert market pricing relative to fair values.',
      })
    }
  }

  return anomalies
}

export function buildMeteoExecutionSummary(input: {
  candidates: MeteoExecutionCandidate[]
  anomalies: MeteoMarketAnomaly[]
}): MeteoExecutionSummary {
  return {
    candidateCount: input.candidates.length,
    tradeableCount: input.candidates.filter((candidate) => candidate.tradeable).length,
    highPriorityCount: input.candidates.filter((candidate) => candidate.priority === 'high').length,
    anomalyCount: input.anomalies.length,
  }
}