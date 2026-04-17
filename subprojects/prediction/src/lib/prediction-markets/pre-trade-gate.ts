import type { MarketRecommendationPacket } from '@/lib/prediction-markets/schemas'
import type { CrossVenueOpsSummary } from '@/lib/prediction-markets/cross-venue'
import type { MicrostructureLabReport } from '@/lib/prediction-markets/microstructure-lab'
import type { ShadowArbitrageSimulationReport } from '@/lib/prediction-markets/shadow-arbitrage'

export type PredictionMarketPreTradeGateMode = 'paper' | 'shadow' | 'live'
export type PredictionMarketPreTradeEdgeBucket =
  | 'forecast_alpha'
  | 'execution_alpha'
  | 'arbitrage_alpha'
  | 'no_trade'
export type PredictionMarketPreTradeGateVerdict = 'pass' | 'fail' | 'not_applicable'
export type PredictionMarketPreTradeSimulationStaleQuoteRisk = 'low' | 'medium' | 'high'

export type PredictionMarketPreTradeGate = {
  gate_name: 'hard_no_trade'
  verdict: PredictionMarketPreTradeGateVerdict
  recommendation_action: MarketRecommendationPacket['action']
  edge_bucket: PredictionMarketPreTradeEdgeBucket
  gross_edge_bps: number
  spread_bps: number
  expected_slippage_bps: number
  microstructure_deterioration_bps: number
  confidence_haircut_bps: number
  latency_haircut_bps: number
  conservative_friction_bps: number
  net_edge_bps: number
  minimum_net_edge_bps: number
  pass_margin_bps: number
  notes: string[]
  summary: string
}

type PredictionMarketPreTradeGateReadiness = {
  cross_venue_summary?: CrossVenueOpsSummary | null
  microstructure_lab?: MicrostructureLabReport | null
}

type PredictionMarketPreTradeGateSimulation = {
  expected_slippage_bps: number
  stale_quote_risk: PredictionMarketPreTradeSimulationStaleQuoteRisk
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

function nonNegativeInt(value: number | null | undefined): number {
  if (!Number.isFinite(value ?? Number.NaN)) return 0
  return Math.max(0, Math.round(value ?? 0))
}

function clampProbability(value: number): number {
  return Math.max(0, Math.min(1, value))
}

function normalizeStrategyEdgeLabel(input: {
  strategyName?: string | null
  marketRegimeSummary?: string | null
  strategySummary?: string | null
}): string {
  return [
    input.strategyName ?? '',
    input.marketRegimeSummary ?? '',
    input.strategySummary ?? '',
  ].join(' ').toLowerCase()
}

function getHighestConfidenceExecutableEdgeBps(
  summary: CrossVenueOpsSummary | null | undefined,
): number {
  const candidate = summary?.highest_confidence_candidate ?? null
  if (!candidate || !candidate.executable) return 0
  return nonNegativeInt(candidate.executable_edge.executable_edge_bps)
}

export function resolvePredictionMarketPreTradeEdgeBucket(input: {
  recommendation: MarketRecommendationPacket
  readiness: PredictionMarketPreTradeGateReadiness
  strategyName?: string | null
  marketRegimeSummary?: string | null
  strategySummary?: string | null
  shadowArbitrage?: ShadowArbitrageSimulationReport | null
}): PredictionMarketPreTradeEdgeBucket {
  if (input.recommendation.action !== 'bet') {
    return 'no_trade'
  }

  const shadowArbitrageEdgeBps =
    input.shadowArbitrage?.summary.shadow_edge_bps
    ?? getHighestConfidenceExecutableEdgeBps(input.readiness.cross_venue_summary)
  if (shadowArbitrageEdgeBps > 0) {
    return 'arbitrage_alpha'
  }

  const normalizedStrategyLabel = normalizeStrategyEdgeLabel({
    strategyName: input.strategyName,
    marketRegimeSummary: input.marketRegimeSummary,
    strategySummary: input.strategySummary,
  })
  if (
    normalizedStrategyLabel.includes('maker') ||
    normalizedStrategyLabel.includes('spread_capture') ||
    normalizedStrategyLabel.includes('execution') ||
    normalizedStrategyLabel.includes('quote')
  ) {
    return 'execution_alpha'
  }

  return 'forecast_alpha'
}

function estimateLatencyHaircutBps(input: {
  mode: PredictionMarketPreTradeGateMode
  staleQuoteRisk: PredictionMarketPreTradeSimulationStaleQuoteRisk
}): number {
  switch (input.staleQuoteRisk) {
    case 'high':
      return input.mode === 'live' ? 24 : input.mode === 'shadow' ? 16 : 8
    case 'medium':
      return input.mode === 'live' ? 12 : input.mode === 'shadow' ? 8 : 4
    case 'low':
      return input.mode === 'live' ? 4 : 0
  }
}

export function buildPredictionMarketPreTradeGate(input: {
  mode: PredictionMarketPreTradeGateMode
  recommendation: MarketRecommendationPacket
  readiness: PredictionMarketPreTradeGateReadiness
  simulation: PredictionMarketPreTradeGateSimulation
  strategyName?: string | null
  marketRegimeSummary?: string | null
  strategySummary?: string | null
  shadowArbitrage?: ShadowArbitrageSimulationReport | null
}): PredictionMarketPreTradeGate {
  const edgeBucket = resolvePredictionMarketPreTradeEdgeBucket({
    recommendation: input.recommendation,
    readiness: input.readiness,
    strategyName: input.strategyName,
    marketRegimeSummary: input.marketRegimeSummary,
    strategySummary: input.strategySummary,
    shadowArbitrage: input.shadowArbitrage,
  })
  if (input.recommendation.action !== 'bet') {
    const summary = `No-trade gate stays inactive because recommendation=${input.recommendation.action}.`
    return {
      gate_name: 'hard_no_trade',
      verdict: 'not_applicable',
      recommendation_action: input.recommendation.action,
      edge_bucket: edgeBucket,
      gross_edge_bps: 0,
      spread_bps: nonNegativeInt(input.recommendation.spread_bps ?? 0),
      expected_slippage_bps: 0,
      microstructure_deterioration_bps: 0,
      confidence_haircut_bps: 0,
      latency_haircut_bps: 0,
      conservative_friction_bps: 0,
      net_edge_bps: 0,
      minimum_net_edge_bps: 0,
      pass_margin_bps: 0,
      notes: [summary],
      summary,
    }
  }

  const shadowArbitrageEdgeBps =
    input.shadowArbitrage?.summary.shadow_edge_bps
    ?? getHighestConfidenceExecutableEdgeBps(input.readiness.cross_venue_summary)
  const grossEdgeBps = edgeBucket === 'arbitrage_alpha'
    ? Math.max(
      nonNegativeInt(input.recommendation.edge_bps ?? 0),
      nonNegativeInt(shadowArbitrageEdgeBps),
    )
    : nonNegativeInt(input.recommendation.edge_bps ?? 0)
  const spreadBps = nonNegativeInt(input.recommendation.spread_bps ?? 0)
  const expectedSlippageBps = nonNegativeInt(input.simulation.expected_slippage_bps)
  const microstructureDeteriorationBps = nonNegativeInt(
    input.readiness.microstructure_lab?.summary.executable_deterioration_bps,
  )
  const confidenceHaircutBps = Math.max(6, Math.round((1 - clampProbability(input.recommendation.confidence)) * 100))
  const latencyHaircutBps = estimateLatencyHaircutBps({
    mode: input.mode,
    staleQuoteRisk: input.simulation.stale_quote_risk,
  })
  const conservativeFrictionBps =
    expectedSlippageBps +
    microstructureDeteriorationBps +
    confidenceHaircutBps +
    latencyHaircutBps
  const netEdgeBps = grossEdgeBps - conservativeFrictionBps
  const minimumNetEdgeBps = Math.max(25, conservativeFrictionBps * 2)
  const passMarginBps = netEdgeBps - minimumNetEdgeBps
  const verdict: PredictionMarketPreTradeGateVerdict = passMarginBps >= 0 ? 'pass' : 'fail'
  const notes = uniqueStrings([
    `Edge bucket ${edgeBucket}.`,
    shadowArbitrageEdgeBps > 0 && edgeBucket === 'arbitrage_alpha'
      ? `Cross-venue executable edge contributes ${nonNegativeInt(shadowArbitrageEdgeBps)} bps.`
      : null,
    spreadBps > 0 ? `Quoted spread is ${spreadBps} bps.` : null,
    `Expected execution slippage is ${expectedSlippageBps} bps.`,
    microstructureDeteriorationBps > 0
      ? `Microstructure deterioration adds ${microstructureDeteriorationBps} bps.`
      : null,
    `Confidence haircut adds ${confidenceHaircutBps} bps.`,
    latencyHaircutBps > 0 ? `Latency haircut adds ${latencyHaircutBps} bps.` : null,
    verdict === 'pass'
      ? `Net edge ${netEdgeBps} bps clears the minimum ${minimumNetEdgeBps} bps threshold.`
      : `Net edge ${netEdgeBps} bps fails the minimum ${minimumNetEdgeBps} bps threshold.`,
  ])
  const summary = [
    `Hard no-trade gate ${verdict}.`,
    `bucket=${edgeBucket}`,
    `gross=${grossEdgeBps}bps`,
    `frictions=${conservativeFrictionBps}bps`,
    `net=${netEdgeBps}bps`,
    `minimum=${minimumNetEdgeBps}bps`,
  ].join(' ')

  return {
    gate_name: 'hard_no_trade',
    verdict,
    recommendation_action: input.recommendation.action,
    edge_bucket: edgeBucket,
    gross_edge_bps: grossEdgeBps,
    spread_bps: spreadBps,
    expected_slippage_bps: expectedSlippageBps,
    microstructure_deterioration_bps: microstructureDeteriorationBps,
    confidence_haircut_bps: confidenceHaircutBps,
    latency_haircut_bps: latencyHaircutBps,
    conservative_friction_bps: conservativeFrictionBps,
    net_edge_bps: netEdgeBps,
    minimum_net_edge_bps: minimumNetEdgeBps,
    pass_margin_bps: passMarginBps,
    notes,
    summary,
  }
}
