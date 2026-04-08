import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  predictionMarketsFrozenBenchmarkCases,
  runPredictionMarketsFrozenBenchmark,
  summarizePredictionMarketsFrozenBenchmark,
  summarizePredictionMarketsBenchmarkResult,
} from '@/lib/prediction-markets/benchmark'

describe('prediction markets frozen benchmark', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-08T00:00:00.000Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('covers a stable bet, wait, and ambiguous matrix locally', () => {
    expect(predictionMarketsFrozenBenchmarkCases.map((fixture) => fixture.id)).toEqual([
      'polymarket-bet-yes',
      'kalshi-wait-missing-history',
      'polymarket-ambiguous-multi-outcome',
    ])

    const summary = runPredictionMarketsFrozenBenchmark().map(summarizePredictionMarketsBenchmarkResult)

    expect(summary).toEqual([
      {
        id: 'polymarket-bet-yes',
        venue: 'polymarket',
        resolution_status: 'eligible',
        manual_review_required: false,
        forecast_basis: 'manual_thesis',
        probability_yes: 0.68,
        confidence: 0.518,
        action: 'bet',
        side: 'yes',
        edge_bps: 1600,
        risk_flags: [],
        evidence_types: ['market_data', 'orderbook', 'history', 'manual_thesis'],
        market_only_action: 'no_trade',
        market_only_probability_yes: 0.51,
        market_only_confidence: 0.418,
        market_only_edge_bps: 0,
        forecast_drift_bps: 1700,
        calibration_gap_bps: 1700,
        closing_line_quality_bps: 1600,
        edge_improvement_bps: 1600,
      },
      {
        id: 'kalshi-wait-missing-history',
        venue: 'kalshi',
        resolution_status: 'eligible',
        manual_review_required: false,
        forecast_basis: 'manual_thesis',
        probability_yes: 0.58,
        confidence: 0.55,
        action: 'wait',
        side: null,
        edge_bps: 1100,
        risk_flags: ['missing_history'],
        evidence_types: ['market_data', 'orderbook', 'manual_thesis'],
        market_only_action: 'no_trade',
        market_only_probability_yes: 0.46,
        market_only_confidence: 0.45,
        market_only_edge_bps: 0,
        forecast_drift_bps: 1200,
        calibration_gap_bps: 1200,
        closing_line_quality_bps: 1100,
        edge_improvement_bps: 1100,
      },
      {
        id: 'polymarket-ambiguous-multi-outcome',
        venue: 'polymarket',
        resolution_status: 'ambiguous',
        manual_review_required: true,
        forecast_basis: 'market_midpoint',
        probability_yes: 0.34,
        confidence: 0.204,
        action: 'wait',
        side: null,
        edge_bps: 0,
        risk_flags: ['resolution_guard'],
        evidence_types: ['market_data', 'history'],
        market_only_action: 'wait',
        market_only_probability_yes: 0.34,
        market_only_confidence: 0.204,
        market_only_edge_bps: 0,
        forecast_drift_bps: 0,
        calibration_gap_bps: 0,
        closing_line_quality_bps: 0,
        edge_improvement_bps: 0,
      },
    ])
  })

  it('summarizes the frozen benchmark against the market-only baseline', () => {
    expect(summarizePredictionMarketsFrozenBenchmark()).toEqual({
      case_count: 3,
      actual_action_counts: {
        bet: 1,
        no_trade: 0,
        wait: 2,
      },
      market_only_action_counts: {
        bet: 0,
        no_trade: 2,
        wait: 1,
      },
      mean_forecast_drift_bps: 967,
      mean_calibration_gap_bps: 967,
      mean_closing_line_quality_bps: 900,
      mean_edge_improvement_bps: 900,
    })
  })
})
