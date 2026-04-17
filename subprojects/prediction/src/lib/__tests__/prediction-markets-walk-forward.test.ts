import { describe, expect, it } from 'vitest'
import type { ForecastEvaluationRecord } from '@/lib/prediction-markets/schemas'
import {
  buildResolvedHistoryDataset,
  toCalibrationPointsFromResolvedHistory,
} from '@/lib/prediction-markets/resolved-history'
import { buildCalibrationReport } from '@/lib/prediction-markets/calibration'
import { buildPredictionMarketCostModelReport } from '@/lib/prediction-markets/cost-model'
import { buildPredictionMarketWalkForwardReport } from '@/lib/prediction-markets/walk-forward'

function makeEvaluationRecord(
  index: number,
  forecastProbability: number,
  marketBaselineProbability: number,
  resolvedOutcome: boolean,
): ForecastEvaluationRecord {
  return {
    schema_version: '1.0.0',
    evaluation_id: `eval-${index + 1}`,
    question_id: `question-${Math.floor(index / 2) + 1}`,
    market_id: 'BTC / Jun 2026',
    venue: 'polymarket',
    cutoff_at: `2026-04-${String(index + 1).padStart(2, '0')}T00:00:00.000Z`,
    forecast_probability: forecastProbability,
    market_baseline_probability: marketBaselineProbability,
    resolved_outcome: resolvedOutcome,
    brier_score: Math.pow(forecastProbability - (resolvedOutcome ? 1 : 0), 2),
    log_loss: resolvedOutcome
      ? -Math.log(Math.max(1e-6, forecastProbability))
      : -Math.log(Math.max(1e-6, 1 - forecastProbability)),
    ece_bucket: forecastProbability >= 0.5 ? '50_100' : '0_50',
    abstain_flag: false,
    basis: 'manual_thesis',
    comparison_label: 'candidate_vs_market',
    comparator_id: 'candidate_manual_thesis',
    comparator_kind: 'candidate_model',
    comparator_role: 'candidate',
    pipeline_id: 'forecast-market',
    pipeline_version: 'baseline-v0',
  }
}

describe('prediction markets resolved history and walk-forward modules', () => {
  it('builds resolved history datasets from evaluation history and feeds calibration', () => {
    const evaluationHistory = [
      makeEvaluationRecord(0, 0.1, 0.18, false),
      makeEvaluationRecord(1, 0.2, 0.25, false),
      makeEvaluationRecord(2, 0.8, 0.71, true),
      makeEvaluationRecord(3, 0.9, 0.82, true),
    ]
    const dataset = buildResolvedHistoryDataset({
      runId: 'run-history-001',
      venue: 'polymarket',
      marketId: 'BTC / Jun 2026',
      evaluationHistory,
      defaults: {
        liquidity_usd: 120_000,
        volume_24h_usd: 45_000,
        spread_bps: 120,
      },
    })
    const calibrationReport = buildCalibrationReport(
      toCalibrationPointsFromResolvedHistory(dataset.points, {
        weight_by_liquidity: true,
      }),
      {
        bin_count: 4,
      },
    )

    expect(dataset.resolved_records).toBe(4)
    expect(dataset.unresolved_records).toBe(0)
    expect(dataset.summary).toContain('Resolved history built')
    expect(calibrationReport.total_points).toBe(4)
    expect(calibrationReport.brier_score).not.toBeNull()
  })

  it('computes cost-model and walk-forward reports from resolved history', () => {
    const evaluationHistory = [
      makeEvaluationRecord(0, 0.08, 0.15, false),
      makeEvaluationRecord(1, 0.15, 0.22, false),
      makeEvaluationRecord(2, 0.22, 0.3, false),
      makeEvaluationRecord(3, 0.78, 0.68, true),
      makeEvaluationRecord(4, 0.82, 0.73, true),
      makeEvaluationRecord(5, 0.88, 0.79, true),
      makeEvaluationRecord(6, 0.3, 0.4, false),
      makeEvaluationRecord(7, 0.7, 0.6, true),
    ]
    const dataset = buildResolvedHistoryDataset({
      runId: 'run-history-002',
      venue: 'polymarket',
      marketId: 'BTC / Jun 2026',
      evaluationHistory,
      defaults: {
        liquidity_usd: 180_000,
        volume_24h_usd: 80_000,
        spread_bps: 100,
        size_usd: 50,
      },
    })
    const costModel = buildPredictionMarketCostModelReport({
      runId: 'run-history-002',
      venue: 'polymarket',
      marketId: 'BTC / Jun 2026',
      points: dataset.points,
    })
    const walkForward = buildPredictionMarketWalkForwardReport({
      runId: 'run-history-002',
      venue: 'polymarket',
      marketId: 'BTC / Jun 2026',
      points: dataset.points,
      options: {
        train_window_points: 4,
        test_window_points: 2,
        step_points: 2,
        minimum_train_points: 4,
        bin_count: 4,
      },
    })

    expect(costModel.total_points).toBe(8)
    expect(costModel.average_cost_bps).toBeGreaterThan(0)
    expect(costModel.points).toHaveLength(8)
    expect(walkForward.total_windows).toBeGreaterThan(0)
    expect(walkForward.mean_raw_brier_score).not.toBeNull()
    expect(walkForward.mean_calibrated_brier_score).not.toBeNull()
    expect(walkForward.summary).toContain('Walk-forward ran')
  })

  it('stays explicit when no resolved history is available', () => {
    const dataset = buildResolvedHistoryDataset({
      runId: 'run-history-empty',
      venue: 'polymarket',
      marketId: 'BTC / Jun 2026',
      evaluationHistory: [],
    })
    const walkForward = buildPredictionMarketWalkForwardReport({
      runId: 'run-history-empty',
      venue: 'polymarket',
      marketId: 'BTC / Jun 2026',
      points: dataset.points,
    })

    expect(dataset.notes).toContain('empty_evaluation_history')
    expect(dataset.notes).toContain('no_resolved_records')
    expect(walkForward.notes).toContain('empty_walk_forward_history')
    expect(walkForward.total_windows).toBe(0)
    expect(walkForward.promotion_ready).toBe(false)
  })
})
