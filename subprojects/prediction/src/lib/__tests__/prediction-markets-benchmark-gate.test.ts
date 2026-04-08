import { describe, expect, it } from 'vitest'
import {
  buildPredictionMarketsLocalPromotionEligibility,
  summarizePredictionMarketsBenchmarkGate,
} from '@/lib/prediction-markets/benchmark-gate'

describe('prediction markets benchmark gate', () => {
  it('falls back to a preview verdict when no comparative report exists', () => {
    const result = summarizePredictionMarketsBenchmarkGate({
      comparativeReport: null,
      forecastProbabilityYesHint: 0.62,
    })

    expect(result).toMatchObject({
      verdict: 'preview_only',
      status: 'preview_only',
      promotion_status: 'unproven',
      promotion_ready: false,
      preview_available: false,
      promotion_evidence: 'unproven',
      promotion_evidence_source: 'preview_only',
      promotion_kill_criteria: ['missing_comparative_report', 'out_of_sample_unproven'],
      promotion_blocker_summary: 'benchmark preview unavailable; out_of_sample_unproven',
      blockers: ['missing_comparative_report', 'out_of_sample_unproven'],
      summary: null,
    })
  })

  it('summarizes the benchmark gate consistently for runtime and reporting', () => {
    const result = summarizePredictionMarketsBenchmarkGate({
      comparativeReport: {
        market_only: { probability_yes: 0.51 },
        aggregate: { probability_yes: 0.595 },
        forecast: { forecast_probability_yes: 0.62 },
        abstention: { blocks_forecast: false },
      },
      forecastProbabilityYesHint: 0.62,
    })

    expect(result).toMatchObject({
      verdict: 'preview_only',
      status: 'preview_only',
      promotion_status: 'unproven',
      promotion_ready: false,
      preview_available: true,
      promotion_evidence: 'unproven',
      promotion_evidence_source: 'preview_only',
      promotion_kill_criteria: ['out_of_sample_unproven'],
      promotion_blocker_summary: 'out_of_sample_unproven',
      blockers: ['out_of_sample_unproven'],
      market_only_probability: 0.51,
      aggregate_probability: 0.595,
      forecast_probability: 0.62,
      forecast_uplift_bps: 1100,
      aggregate_uplift_bps: 850,
      summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
    })
  })

  it('promotes the gate to eligible when local benchmark evidence says so', () => {
    const result = summarizePredictionMarketsBenchmarkGate({
      comparativeReport: {
        market_only: { probability_yes: 0.51 },
        aggregate: { probability_yes: 0.595 },
        forecast: { forecast_probability_yes: 0.62 },
        abstention: { blocks_forecast: false },
      },
      forecastProbabilityYesHint: 0.62,
      localPromotionEligibility: {
        status: 'eligible',
        blockers: [],
      },
    })

    expect(result).toMatchObject({
      verdict: 'local_benchmark_ready',
      status: 'preview_only',
      promotion_status: 'eligible',
      promotion_ready: true,
      preview_available: true,
      promotion_evidence: 'local_benchmark',
      promotion_evidence_source: 'out_of_sample',
      promotion_kill_criteria: [],
      promotion_blocker_summary: 'promotion gate satisfied',
      blockers: [],
      market_only_probability: 0.51,
      aggregate_probability: 0.595,
      forecast_probability: 0.62,
      forecast_uplift_bps: 1100,
      aggregate_uplift_bps: 850,
      summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=eligible ready=yes preview=yes evidence=local_benchmark out_of_sample=local_benchmark',
    })
  })

  it('keeps a local benchmark blocked verdict when eligibility is present but blockers remain', () => {
    const result = summarizePredictionMarketsBenchmarkGate({
      comparativeReport: {
        market_only: { probability_yes: 0.51 },
        aggregate: { probability_yes: 0.595 },
        forecast: { forecast_probability_yes: 0.62 },
        abstention: { blocks_forecast: false },
      },
      forecastProbabilityYesHint: 0.62,
      localPromotionEligibility: {
        status: 'eligible',
        blockers: ['insufficient_case_count'],
      },
    })

    expect(result).toMatchObject({
      verdict: 'local_benchmark_blocked',
      status: 'preview_only',
      promotion_status: 'eligible',
      promotion_ready: false,
      preview_available: true,
      promotion_evidence: 'local_benchmark',
      promotion_evidence_source: 'out_of_sample',
      promotion_kill_criteria: ['insufficient_case_count'],
      promotion_blocker_summary: 'insufficient_case_count',
      blockers: ['insufficient_case_count'],
      reasons: ['local benchmark promotion gate is blocked'],
      summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=eligible ready=no preview=yes evidence=local_benchmark blockers=insufficient_case_count out_of_sample=local_benchmark',
    })
  })

  it('records a blocked verdict when abstention blocks the forecast', () => {
    const result = summarizePredictionMarketsBenchmarkGate({
      comparativeReport: {
        market_only: { probability_yes: 0.51 },
        aggregate: { probability_yes: 0.595 },
        forecast: { forecast_probability_yes: 0.62 },
        abstention: { blocks_forecast: true },
      },
      forecastProbabilityYesHint: 0.62,
    })

    expect(result).toMatchObject({
      verdict: 'blocked_by_abstention',
      status: 'blocked_by_abstention',
      promotion_status: 'blocked',
      promotion_ready: false,
      preview_available: true,
      promotion_evidence: 'unproven',
      promotion_evidence_source: 'preview_only',
      promotion_kill_criteria: ['abstention_blocks_forecast'],
      promotion_blocker_summary: 'abstention_blocks_forecast',
      blockers: ['abstention_blocks_forecast'],
      summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=blocked_by_abstention promotion=blocked ready=no preview=yes evidence=unproven blockers=abstention_blocks_forecast out_of_sample=unproven',
    })
  })

  it('uses an explicit blocked summary when promotion is blocked without structured blockers', () => {
    const result = summarizePredictionMarketsBenchmarkGate({
      comparativeReport: {
        market_only: { probability_yes: 0.51 },
        aggregate: { probability_yes: 0.595 },
        forecast: { forecast_probability_yes: 0.62 },
        abstention: { blocks_forecast: false },
      },
      forecastProbabilityYesHint: 0.62,
      localPromotionEligibility: {
        status: 'blocked',
        blockers: [],
      },
    })

    expect(result).toMatchObject({
      verdict: 'local_benchmark_blocked',
      status: 'preview_only',
      promotion_status: 'blocked',
      promotion_ready: false,
      preview_available: true,
      promotion_evidence: 'local_benchmark',
      promotion_evidence_source: 'out_of_sample',
      promotion_kill_criteria: ['local_benchmark_promotion_blocked'],
      promotion_blocker_summary: 'local_benchmark_promotion_blocked',
      blockers: [],
      reasons: ['local benchmark promotion gate is blocked'],
      summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=blocked ready=no preview=yes evidence=local_benchmark out_of_sample=local_benchmark',
    })
  })

  it('builds the local promotion eligibility payload from shared inputs', () => {
    const eligibility = buildPredictionMarketsLocalPromotionEligibility({
      caseCount: 3,
      requiredCaseCount: 3,
      bestComparatorId: 'single_llm',
      bestComparatorLabel: 'single-LLM',
      bestComparatorEdgeDeltaBps: 900,
      observedMeanProbabilityGapBps: 967,
      requiredMeanEdgeImprovementBps: 1,
      replayMode: 'local_frozen_replay',
      pipelineId: 'prediction-markets-as-of-benchmark-pipeline',
      pipelineVersion: 'poly-024-asof-v1',
    })

    expect(eligibility).toEqual({
      status: 'eligible',
      basis: 'local_benchmark',
      candidate_comparator_id: 'single_llm',
      candidate_comparator_label: 'single-LLM',
      observed_mean_edge_improvement_bps: 900,
      required_mean_edge_improvement_bps: 1,
      observed_mean_probability_gap_bps: 967,
      required_case_count: 3,
      case_count: 3,
      blockers: [],
      reasons: [
        'best comparator single-LLM improves mean edge by 900 bps over market-only',
        'mean probability gap is 967 bps across 3 frozen cases',
      ],
      source: 'local',
      replay_mode: 'local_frozen_replay',
      pipeline_id: 'prediction-markets-as-of-benchmark-pipeline',
      pipeline_version: 'poly-024-asof-v1',
    })
  })

  it('rejects market-only as a candidate comparator even when it is supplied explicitly', () => {
    const eligibility = buildPredictionMarketsLocalPromotionEligibility({
      caseCount: 3,
      requiredCaseCount: 3,
      bestComparatorId: 'market_only',
      bestComparatorLabel: 'market-only',
      bestComparatorEdgeDeltaBps: 0,
      observedMeanProbabilityGapBps: 0,
      requiredMeanEdgeImprovementBps: 1,
      replayMode: 'local_frozen_replay',
      pipelineId: 'prediction-markets-as-of-benchmark-pipeline',
      pipelineVersion: 'poly-024-asof-v1',
    })

    expect(eligibility).toEqual({
      status: 'blocked',
      basis: 'local_benchmark',
      candidate_comparator_id: 'market_only',
      candidate_comparator_label: 'market-only',
      observed_mean_edge_improvement_bps: 0,
      required_mean_edge_improvement_bps: 1,
      observed_mean_probability_gap_bps: 0,
      required_case_count: 3,
      case_count: 3,
      blockers: ['market_only_is_not_a_candidate'],
      reasons: [],
      source: 'local',
      replay_mode: 'local_frozen_replay',
      pipeline_id: 'prediction-markets-as-of-benchmark-pipeline',
      pipeline_version: 'poly-024-asof-v1',
    })
  })
})
