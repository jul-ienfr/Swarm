import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  runPredictionMarketsAsOfBenchmark,
  runPredictionMarketsFrozenBenchmark,
} from '@/lib/prediction-markets/benchmark'
import {
  asOfEvidenceSetSchema,
  calibrationSnapshotSchema,
  forecastEvaluationRecordSchema,
} from '@/lib/prediction-markets/schemas'

describe('prediction markets as-of benchmark harness', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-08T00:00:00.000Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('attaches explicit market-only vs candidate as-of comparisons to every frozen case', () => {
    const results = runPredictionMarketsFrozenBenchmark()
    const byId = Object.fromEntries(results.map((result) => [result.fixture.id, result]))

    expect(byId['polymarket-bet-yes']?.as_of?.comparison_label).toBe('manual_thesis_vs_market_only')
    expect(byId['kalshi-wait-missing-history']?.as_of?.comparison_label).toBe('manual_thesis_vs_market_only')
    expect(byId['polymarket-ambiguous-multi-outcome']?.as_of?.comparison_label).toBe('market_midpoint_vs_market_only')

    const first = byId['polymarket-bet-yes']
    expect(first?.as_of).toBeDefined()
    if (!first?.as_of) return

    expect(forecastEvaluationRecordSchema.parse(first.as_of.evaluation_record)).toMatchObject({
      evaluation_id: 'polymarket-bet-yes:forecast:2026-04-08T00:00:00.000Z',
      question_id: 'polymarket-bet-yes',
      market_id: 'poly-bet-yes',
      venue: 'polymarket',
      cutoff_at: '2026-04-08T00:00:00.000Z',
      forecast_probability: 0.68,
      market_baseline_probability: 0.51,
      resolved_outcome: null,
      brier_score: null,
      log_loss: null,
      ece_bucket: 'unresolved_as_of',
      abstain_flag: false,
      basis: 'manual_thesis',
      comparison_label: 'manual_thesis_vs_market_only',
      comparator_id: 'candidate_manual_thesis',
      comparator_kind: 'candidate_model',
      comparator_role: 'candidate',
      pipeline_id: 'prediction-markets-as-of-benchmark-pipeline',
      pipeline_version: 'poly-024-asof-v1',
    })

    expect(asOfEvidenceSetSchema.parse(first.as_of.evidence_set)).toMatchObject({
      evidence_set_id: 'polymarket-bet-yes:as-of:2026-04-08T00:00:00.000Z',
      market_id: 'poly-bet-yes',
      cutoff_at: '2026-04-08T00:00:00.000Z',
      retrieval_policy: 'frozen_as_of_replay',
      comparison_label: 'manual_thesis_vs_market_only',
      market_only_evidence_refs: expect.arrayContaining([
        'poly-bet-yes:market-data',
        'poly-bet-yes:orderbook',
        'poly-bet-yes:history',
      ]),
      candidate_evidence_refs: expect.arrayContaining([
        'poly-bet-yes:market-data',
        'poly-bet-yes:orderbook',
        'poly-bet-yes:history',
        expect.stringContaining('manual-thesis'),
      ]),
      comparator_id: 'candidate_manual_thesis',
      pipeline_id: 'prediction-markets-as-of-benchmark-pipeline',
      pipeline_version: 'poly-024-asof-v1',
    })
    expect(first.as_of.metadata).toMatchObject({
      dataset_id: 'prediction-markets-as-of-benchmark',
      dataset_version: 'poly-024-asof-v1',
      replay_mode: 'local_frozen_replay',
      pipeline_id: 'prediction-markets-as-of-benchmark-pipeline',
      pipeline_version: 'poly-024-asof-v1',
      fixture_id: 'polymarket-bet-yes',
      market_id: 'poly-bet-yes',
      comparison_label: 'manual_thesis_vs_market_only',
      cutoff_at: '2026-04-08T00:00:00.000Z',
      comparator_ids: ['market_only', 'single_llm', 'ensemble', 'decision_packet_assisted'],
      comparator_labels: ['market-only', 'single-LLM', 'ensemble', 'DecisionPacket-assisted'],
    })
    expect(first.as_of.metadata.dataset_revision).toMatch(/^[a-f0-9]{64}$/)
    expect(first.as_of.comparators).toEqual([
      {
        comparator_id: 'market_only',
        label: 'market-only',
        status: 'available',
        basis: 'market_midpoint',
        probability_yes: 0.51,
        action: 'no_trade',
        edge_bps: 0,
        evidence_ref_count: 3,
        notes: ['available now via frozen market replay baseline'],
        source: 'local',
        replay_mode: 'local_frozen_replay',
        pipeline_id: 'prediction-markets-as-of-benchmark-pipeline',
        pipeline_version: 'poly-024-asof-v1',
      },
      {
        comparator_id: 'single_llm',
        label: 'single-LLM',
        status: 'available',
        basis: 'manual_thesis',
        probability_yes: 0.68,
        action: 'bet',
        edge_bps: 1600,
        evidence_ref_count: 4,
        notes: ['available now via deterministic local single-model proxy over the frozen candidate replay'],
        source: 'local',
        replay_mode: 'local_frozen_replay',
        pipeline_id: 'prediction-markets-as-of-benchmark-pipeline',
        pipeline_version: 'poly-024-asof-v1',
      },
      {
        comparator_id: 'ensemble',
        label: 'ensemble',
        status: 'available',
        basis: 'manual_thesis',
        probability_yes: 0.595,
        action: 'bet',
        edge_bps: 750,
        evidence_ref_count: 4,
        notes: ['available now via deterministic local ensemble over frozen candidate and market-only replays'],
        source: 'local',
        replay_mode: 'local_frozen_replay',
        pipeline_id: 'prediction-markets-as-of-benchmark-pipeline',
        pipeline_version: 'poly-024-asof-v1',
      },
      {
        comparator_id: 'decision_packet_assisted',
        label: 'DecisionPacket-assisted',
        status: 'available',
        basis: 'manual_thesis',
        probability_yes: 0.629,
        action: 'bet',
        edge_bps: 1090,
        evidence_ref_count: 4,
        notes: ['available now via deterministic local DecisionPacket-assisted proxy; no frozen DecisionPacket artifact is present in this benchmark'],
        source: 'local',
        replay_mode: 'local_frozen_replay',
        pipeline_id: 'prediction-markets-as-of-benchmark-pipeline',
        pipeline_version: 'poly-024-asof-v1',
      },
    ])

    const asOfRun = runPredictionMarketsAsOfBenchmark(results)
    const summary = asOfRun.summary
    expect(asOfRun.results).toHaveLength(3)
    expect(asOfRun.metadata).toEqual(summary.metadata)
    const calibrationSnapshot = calibrationSnapshotSchema.parse(summary.calibration_snapshot)
    expect(calibrationSnapshot).toMatchObject({
      snapshot_id: 'as-of:2026-04-08T00:00:00.000Z:2026-04-08T00:00:00.000Z:3',
      model_family: 'baseline-v0',
      market_family: 'binary_yes_no',
      horizon_bucket: 'frozen_as_of',
      window_start: '2026-04-08T00:00:00.000Z',
      window_end: '2026-04-08T00:00:00.000Z',
      calibration_method: 'as_of_proxy',
      coverage: 0.6666666666666666,
      sample_size: 3,
      comparator_id: 'market_only',
      pipeline_id: 'prediction-markets-as-of-benchmark-pipeline',
      pipeline_version: 'poly-024-asof-v1',
    })
    expect(calibrationSnapshot.ece).toBeCloseTo(0.09666666666666668, 12)
    expect(calibrationSnapshot.sharpness).toBeCloseTo(0.28, 12)
    expect(summary).toMatchObject({
      summary_version: 'as_of_benchmark_summary_v1',
      case_count: 3,
      mean_forecast_probability_gap_bps: 967,
      mean_market_only_probability: 0.436667,
      mean_candidate_probability: 0.533333,
      mean_market_only_edge_bps: 0,
      available_comparators: ['market-only', 'single-LLM', 'ensemble', 'DecisionPacket-assisted'],
      planned_comparators: [],
      local_promotion_eligibility: {
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
      },
    })
    expect(summary.metadata).toMatchObject({
      dataset_id: 'prediction-markets-as-of-benchmark',
      dataset_version: 'poly-024-asof-v1',
      replay_mode: 'local_frozen_replay',
      pipeline_id: 'prediction-markets-as-of-benchmark-pipeline',
      pipeline_version: 'poly-024-asof-v1',
      run_id: 'as-of:2026-04-08T00:00:00.000Z:2026-04-08T00:00:00.000Z:3',
      generated_at: '2026-04-08T00:00:00.000Z',
      case_count: 3,
      fixture_ids: [
        'polymarket-bet-yes',
        'kalshi-wait-missing-history',
        'polymarket-ambiguous-multi-outcome',
      ],
      cutoff_window: {
        start: '2026-04-08T00:00:00.000Z',
        end: '2026-04-08T00:00:00.000Z',
      },
      comparator_ids: ['market_only', 'single_llm', 'ensemble', 'decision_packet_assisted'],
      comparator_labels: ['market-only', 'single-LLM', 'ensemble', 'DecisionPacket-assisted'],
    })
    expect(summary.metadata.dataset_revision).toMatch(/^[a-f0-9]{64}$/)
    expect(summary.comparator_summaries).toEqual([
      {
        comparator_id: 'market_only',
        label: 'market-only',
        status: 'available',
        available_case_count: 3,
        mean_probability_yes: 0.436667,
        mean_probability_delta_bps_vs_market_only: 0,
        mean_edge_bps: 0,
        mean_edge_delta_bps_vs_market_only: 0,
        notes: ['available now via frozen market replay baseline'],
        source: 'local',
        replay_mode: 'local_frozen_replay',
        pipeline_id: 'prediction-markets-as-of-benchmark-pipeline',
        pipeline_version: 'poly-024-asof-v1',
      },
      {
        comparator_id: 'single_llm',
        label: 'single-LLM',
        status: 'available',
        available_case_count: 3,
        mean_probability_yes: 0.533333,
        mean_probability_delta_bps_vs_market_only: 967,
        mean_edge_bps: 900,
        mean_edge_delta_bps_vs_market_only: 900,
        notes: ['available now via deterministic local single-model proxy over the frozen candidate replay'],
        source: 'local',
        replay_mode: 'local_frozen_replay',
        pipeline_id: 'prediction-markets-as-of-benchmark-pipeline',
        pipeline_version: 'poly-024-asof-v1',
      },
      {
        comparator_id: 'ensemble',
        label: 'ensemble',
        status: 'available',
        available_case_count: 3,
        mean_probability_yes: 0.485,
        mean_probability_delta_bps_vs_market_only: 483,
        mean_edge_bps: 416.666667,
        mean_edge_delta_bps_vs_market_only: 417,
        notes: ['available now via deterministic local ensemble over frozen candidate and market-only replays'],
        source: 'local',
        replay_mode: 'local_frozen_replay',
        pipeline_id: 'prediction-markets-as-of-benchmark-pipeline',
        pipeline_version: 'poly-024-asof-v1',
      },
      {
        comparator_id: 'decision_packet_assisted',
        label: 'DecisionPacket-assisted',
        status: 'available',
        available_case_count: 3,
        mean_probability_yes: 0.504333,
        mean_probability_delta_bps_vs_market_only: 677,
        mean_edge_bps: 610,
        mean_edge_delta_bps_vs_market_only: 610,
        notes: ['available now via deterministic local DecisionPacket-assisted proxy; no frozen DecisionPacket artifact is present in this benchmark'],
        source: 'local',
        replay_mode: 'local_frozen_replay',
        pipeline_id: 'prediction-markets-as-of-benchmark-pipeline',
        pipeline_version: 'poly-024-asof-v1',
      },
    ])
  })
})
