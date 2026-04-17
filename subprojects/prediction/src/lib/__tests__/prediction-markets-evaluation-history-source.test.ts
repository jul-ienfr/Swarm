import { beforeEach, describe, expect, it, vi } from 'vitest'

const storeMocks = vi.hoisted(() => ({
  listPredictionMarketRuns: vi.fn(),
  getPredictionMarketRunDetails: vi.fn(),
}))

vi.mock('@/lib/prediction-markets/store', () => ({
  listPredictionMarketRuns: storeMocks.listPredictionMarketRuns,
  getPredictionMarketRunDetails: storeMocks.getPredictionMarketRunDetails,
}))

import {
  extractForecastEvaluationHistoryFromArtifacts,
  resolvePredictionMarketEvaluationHistory,
} from '@/lib/prediction-markets/evaluation-history-source'

function makeResolvedHistoryArtifact(input: {
  runId: string
  marketId: string
  evaluationId: string
  questionId?: string
  forecastProbability: number
  marketBaselineProbability: number
  resolvedOutcome: boolean
  cutoffAt: string
}): Array<{ artifact_type: string; payload: unknown }> {
  return [
    {
      artifact_type: 'resolved_history',
      payload: {
        artifact_kind: 'resolved_history',
        run_id: input.runId,
        market_id: input.marketId,
        venue: 'polymarket',
        generated_at: '2026-04-08T00:00:00.000Z',
        points: [
          {
            point_id: `${input.evaluationId}:point`,
            evaluation_id: input.evaluationId,
            question_id: input.questionId ?? `${input.evaluationId}:question`,
            market_id: input.marketId,
            venue: 'polymarket',
            cutoff_at: input.cutoffAt,
            forecast_probability: input.forecastProbability,
            market_baseline_probability: input.marketBaselineProbability,
            resolved_outcome: input.resolvedOutcome,
            brier_score: Math.pow(input.forecastProbability - (input.resolvedOutcome ? 1 : 0), 2),
            log_loss: input.resolvedOutcome
              ? -Math.log(Math.max(input.forecastProbability, 1e-6))
              : -Math.log(Math.max(1 - input.forecastProbability, 1e-6)),
            ece_bucket: 'resolved_history',
            basis: 'manual_thesis',
            comparator_id: 'candidate_manual_thesis',
            comparator_kind: 'candidate_model',
            comparator_role: 'candidate',
            pipeline_id: 'forecast-market',
            pipeline_version: 'baseline-v0',
            category: 'crypto',
            spread_bps: 120,
            liquidity_usd: 100_000,
            volume_24h_usd: 45_000,
          },
        ],
      },
    },
  ]
}

describe('prediction markets evaluation history source', () => {
  beforeEach(() => {
    storeMocks.listPredictionMarketRuns.mockReset()
    storeMocks.getPredictionMarketRunDetails.mockReset()
  })

  it('extracts forecast evaluation records from resolved_history artifacts', () => {
    const records = extractForecastEvaluationHistoryFromArtifacts(makeResolvedHistoryArtifact({
      runId: 'run-artifact-001',
      marketId: 'BTC / Jun 2026',
      evaluationId: 'eval-001',
      forecastProbability: 0.72,
      marketBaselineProbability: 0.61,
      resolvedOutcome: true,
      cutoffAt: '2026-04-01T00:00:00.000Z',
    }))

    expect(records).toEqual([
      expect.objectContaining({
        evaluation_id: 'eval-001',
        market_id: 'BTC / Jun 2026',
        forecast_probability: 0.72,
        market_baseline_probability: 0.61,
        resolved_outcome: true,
      }),
    ])
  })

  it('prefers same-market, then same-category, then same-venue stored history', () => {
    storeMocks.listPredictionMarketRuns.mockReturnValue([
      { run_id: 'run-1', market_id: 'BTC / Jun 2026' },
      { run_id: 'run-2', market_id: 'ETH / Jun 2026' },
      { run_id: 'run-3', market_id: 'Election / Nov 2026' },
    ])
    storeMocks.getPredictionMarketRunDetails.mockImplementation((runId: string) => {
      if (runId === 'run-1') {
        return {
          artifacts: makeResolvedHistoryArtifact({
            runId,
            marketId: 'BTC / Jun 2026',
            evaluationId: 'eval-001',
            forecastProbability: 0.74,
            marketBaselineProbability: 0.63,
            resolvedOutcome: true,
            cutoffAt: '2026-04-01T00:00:00.000Z',
          }),
        }
      }
      if (runId === 'run-2') {
        return {
          artifacts: makeResolvedHistoryArtifact({
            runId,
            marketId: 'ETH / Jun 2026',
            evaluationId: 'eval-002',
            forecastProbability: 0.68,
            marketBaselineProbability: 0.58,
            resolvedOutcome: true,
            cutoffAt: '2026-04-02T00:00:00.000Z',
          }),
        }
      }
      return {
        artifacts: makeResolvedHistoryArtifact({
          runId,
          marketId: 'Election / Nov 2026',
          evaluationId: 'eval-003',
          forecastProbability: 0.41,
          marketBaselineProbability: 0.49,
          resolvedOutcome: false,
          cutoffAt: '2026-04-03T00:00:00.000Z',
        }),
      }
    })

    const resolution = resolvePredictionMarketEvaluationHistory({
      workspaceId: 1,
      venue: 'polymarket',
      marketId: 'BTC / Jun 2026',
      targetRecords: 10,
    })

    expect(resolution.source).toBe('stored_runs')
    expect(resolution.evaluation_history).toHaveLength(3)
    expect(resolution.same_market_records).toBe(1)
    expect(resolution.same_category_records).toBe(1)
    expect(resolution.same_venue_records).toBe(1)
    expect(resolution.source_summary).toContain('same_market=1')
    expect(resolution.source_summary).toContain('same_category=1')
    expect(resolution.source_summary).toContain('same_venue=1')
  })
})
