import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  predictionMarketsFrozenBenchmarkCases,
  runPredictionMarketsBenchmarkCase,
} from '@/lib/prediction-markets/benchmark'

describe('prediction markets benchmark pipeline invariants', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-08T00:00:00.000Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it.each(predictionMarketsFrozenBenchmarkCases)('keeps expected invariants for $id', (fixture) => {
    const result = runPredictionMarketsBenchmarkCase(fixture)

    expect(result.resolutionPolicy.status).toBe(fixture.expected.resolutionStatus)
    expect(result.resolutionPolicy.manual_review_required).toBe(fixture.expected.manualReviewRequired)
    expect(result.forecast.basis).toBe(fixture.expected.forecastBasis)
    expect(result.recommendation.action).toBe(fixture.expected.action)
    expect(result.recommendation.side).toBe(fixture.expected.side)
    expect(result.recommendation.risk_flags).toEqual(fixture.expected.riskFlags)
    expect(result.evidencePackets.map((packet) => packet.type)).toEqual(fixture.expected.evidenceTypes)

    for (const expectedReason of fixture.expected.resolutionReasonsInclude || []) {
      expect(result.resolutionPolicy.reasons.some((reason) => reason.includes(expectedReason))).toBe(true)
    }

    for (const expectedReason of fixture.expected.recommendationReasonsInclude || []) {
      expect(result.recommendation.reasons.some((reason) => reason.includes(expectedReason))).toBe(true)
    }
  })

  it('degrades a positive-edge manual thesis to wait when replay history is missing', () => {
    const fixture = predictionMarketsFrozenBenchmarkCases.find(
      (candidate) => candidate.id === 'kalshi-wait-missing-history',
    )

    expect(fixture).toBeDefined()
    if (!fixture) return

    const result = runPredictionMarketsBenchmarkCase(fixture)

    expect(result.recommendation.edge_bps).toBeGreaterThan(150)
    expect(result.recommendation.action).toBe('wait')
    expect(result.recommendation.side).toBeNull()
    expect(result.recommendation.risk_flags).toContain('missing_history')
    expect(result.recommendation.reasons.some((reason) => reason.includes('frozen price history'))).toBe(true)
  })

  it('keeps ambiguous markets behind the resolution guard', () => {
    const fixture = predictionMarketsFrozenBenchmarkCases.find(
      (candidate) => candidate.id === 'polymarket-ambiguous-multi-outcome',
    )

    expect(fixture).toBeDefined()
    if (!fixture) return

    const result = runPredictionMarketsBenchmarkCase(fixture)

    expect(result.resolutionPolicy.status).toBe('ambiguous')
    expect(result.recommendation.action).toBe('wait')
    expect(result.recommendation.side).toBeNull()
    expect(result.recommendation.risk_flags).toEqual(['resolution_guard'])
    expect(result.resolutionPolicy.reasons).toContain('market is not a binary yes/no contract')
  })

  it('tracks market-only drift and edge improvement for each frozen case', () => {
    const results = predictionMarketsFrozenBenchmarkCases.map(runPredictionMarketsBenchmarkCase)
    const byId = Object.fromEntries(results.map((result) => [result.fixture.id, result]))

    expect(byId['polymarket-bet-yes']?.comparison).toMatchObject({
      market_only_action: 'no_trade',
      market_only_edge_bps: 0,
      forecast_drift_bps: 1700,
      calibration_gap_bps: 1700,
      closing_line_quality_bps: 1600,
      edge_improvement_bps: 1600,
    })
    expect(byId['kalshi-wait-missing-history']?.comparison).toMatchObject({
      market_only_action: 'no_trade',
      market_only_edge_bps: 0,
      forecast_drift_bps: 1200,
      calibration_gap_bps: 1200,
      closing_line_quality_bps: 1100,
      edge_improvement_bps: 1100,
    })
    expect(byId['polymarket-ambiguous-multi-outcome']?.comparison).toMatchObject({
      market_only_action: 'wait',
      market_only_edge_bps: 0,
      forecast_drift_bps: 0,
      calibration_gap_bps: 0,
      closing_line_quality_bps: 0,
      edge_improvement_bps: 0,
    })
  })
})
