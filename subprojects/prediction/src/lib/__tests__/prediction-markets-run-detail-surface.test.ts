import { describe, expect, it, vi } from 'vitest'

const storeMocks = vi.hoisted(() => ({
  getPredictionMarketRunDetails: vi.fn(),
}))

vi.mock('@/lib/prediction-markets/store', () => ({
  getPredictionMarketRunDetails: storeMocks.getPredictionMarketRunDetails,
}))

import { getPredictionMarketRunDetails } from '@/lib/prediction-markets/service'
import {
  predictionMarketArtifactRefSchema,
  runManifestSchema,
} from '@/lib/prediction-markets/schemas'

const manifestArtifactRefs = [
  predictionMarketArtifactRefSchema.parse({
    artifact_id: 'run-456:market_descriptor',
    artifact_type: 'market_descriptor',
    sha256: 'sha-market-descriptor',
  }),
  predictionMarketArtifactRefSchema.parse({
    artifact_id: 'run-456:run_manifest',
    artifact_type: 'run_manifest',
    sha256: 'sha-run-manifest',
  }),
]

const runManifest = runManifestSchema.parse({
  run_id: 'run-456',
  mode: 'replay',
  venue: 'polymarket',
  market_id: 'mkt-456',
  market_slug: 'mkt-456',
  actor: 'operator',
  started_at: '2026-04-08T00:00:00.000Z',
  completed_at: '2026-04-08T00:01:00.000Z',
  status: 'completed',
  config_hash: 'cfg-456',
  artifact_refs: manifestArtifactRefs,
})

function mockStoredRunDetails() {
  const storedRunDetails = {
    run_id: 'run-456',
    source_run_id: null,
    workspace_id: 1,
    venue: 'polymarket',
    mode: 'replay',
    market_id: 'mkt-456',
    market_slug: 'mkt-456',
    status: 'completed',
    recommendation: 'wait',
    side: null,
    confidence: 0.62,
    probability_yes: 0.53,
    market_price_yes: 0.49,
    edge_bps: 400,
    research_benchmark_gate_summary:
      'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
    research_benchmark_uplift_bps: 1100,
    research_benchmark_gate_status: 'preview_only',
    research_benchmark_promotion_status: 'unproven',
    research_benchmark_promotion_ready: false,
    research_benchmark_preview_available: true,
    research_benchmark_promotion_evidence: 'unproven',
    research_benchmark_evidence_level: 'benchmark_preview',
    research_promotion_gate_kind: 'preview_only',
    research_benchmark_gate_blockers: ['out_of_sample_unproven'],
    research_benchmark_gate_reasons: ['out_of_sample_unproven'],
    created_at: 1712534400,
    updated_at: 1712534460,
    manifest: runManifest,
    artifact_refs: manifestArtifactRefs,
    artifacts: [
      {
        artifact_id: 'run-456:forecast_packet',
        artifact_type: 'forecast_packet',
        sha256: 'sha-forecast-packet',
        payload: {
          market_id: 'mkt-456',
          venue: 'polymarket',
          basis: 'manual_thesis',
          probability_yes: 0.53,
          confidence: 0.62,
          rationale: 'Stored forecast packet.',
          evidence_refs: ['run-456:evidence'],
          produced_at: '2026-04-08T00:00:00.000Z',
        },
      },
      {
        artifact_id: 'run-456:market_descriptor',
        artifact_type: 'market_descriptor',
        sha256: 'sha-market-descriptor',
        payload: { market_id: 'mkt-456', venue: 'polymarket', question: 'Will BTC break out?', outcomes: ['Yes', 'No'], active: true, closed: false, is_binary_yes_no: true, source_urls: [] },
      },
      {
        artifact_id: 'run-456:market_snapshot',
        artifact_type: 'market_snapshot',
        sha256: 'sha-market-snapshot',
        payload: {
          venue: 'polymarket',
          market: {
            market_id: 'mkt-456',
            venue: 'polymarket',
            venue_type: 'execution-equivalent',
            question: 'Will BTC break out?',
            outcomes: ['Yes', 'No'],
            active: true,
            closed: false,
            is_binary_yes_no: true,
            end_at: '2026-12-31T23:59:59.000Z',
            source_urls: [],
          },
          book: null,
          history: [],
        },
      },
      {
        artifact_id: 'run-456:resolution_policy',
        artifact_type: 'resolution_policy',
        sha256: 'sha-resolution-policy',
        payload: {
          market_id: 'mkt-456',
          venue: 'polymarket',
          status: 'eligible',
          manual_review_required: false,
          reasons: [],
          primary_sources: [],
          evaluated_at: '2026-04-08T00:00:00.000Z',
        },
      },
      {
        artifact_id: 'run-456:evidence_bundle',
        artifact_type: 'evidence_bundle',
        sha256: 'sha-evidence-bundle',
        payload: [{
          evidence_id: 'run-456:evidence',
          market_id: 'mkt-456',
          venue: 'polymarket',
          type: 'manual_thesis',
          title: 'Stored evidence',
          summary: 'Stored evidence packet.',
          captured_at: '2026-04-08T00:00:00.000Z',
          content_hash: 'sha-evidence',
          metadata: {},
        }],
      },
      {
        artifact_id: 'run-456:recommendation_packet',
        artifact_type: 'recommendation_packet',
        sha256: 'sha-recommendation-packet',
        payload: {
          market_id: 'mkt-456',
          venue: 'polymarket',
          action: 'wait',
          side: null,
          confidence: 0.62,
          fair_value_yes: 0.53,
          market_price_yes: 0.49,
          market_bid_yes: 0.48,
          market_ask_yes: 0.5,
          edge_bps: 400,
          spread_bps: 200,
          reasons: [],
          risk_flags: [],
          produced_at: '2026-04-08T00:00:00.000Z',
        },
      },
      {
        artifact_id: 'run-456:run_manifest',
        artifact_type: 'run_manifest',
        sha256: 'sha-run-manifest',
        payload: runManifest,
      },
      {
        artifact_id: 'run-456:shadow_arbitrage',
        artifact_type: 'shadow_arbitrage',
        sha256: 'sha-shadow-arbitrage',
        payload: {
          read_only: true,
          generated_at: '2026-04-08T00:01:30.000Z',
          as_of_at: '2026-04-08T00:00:00.000Z',
          executable_edge: { edge_id: 'edge-1' },
          microstructure_summary: { recommended_mode: 'shadow' },
          sizing: {
            requested_size_usd: null,
            base_size_usd: 100,
            recommended_size_usd: 75,
          simulated_size_usd: 75,
          size_multiplier: 0.75,
        },
        failure_cases: [],
        summary: {
          base_executable_edge_bps: 112,
          microstructure_deterioration_bps: 30,
          shadow_drag_bps: 37,
          shadow_edge_bps: 75,
          base_size_usd: 100,
          recommended_size_usd: 75,
          hedge_success_probability: 0.82,
          hedge_success_expected: true,
          estimated_net_pnl_bps: 68,
          estimated_net_pnl_usd: 51,
          worst_case_kind: 'stale_edge',
          failure_case_count: 0,
          scenario_overview: ['shadow:baseline'],
          notes: ['read-only'],
        },
      },
    },
  ],
  }
  storeMocks.getPredictionMarketRunDetails.mockReturnValue(storedRunDetails)
  return storedRunDetails
}

describe('prediction market run detail surface', () => {
  it('exposes artifact_readback and artifact_audit additively with stable canonical ordering', () => {
    mockStoredRunDetails()

    const first = getPredictionMarketRunDetails('run-456', 1)
    const second = getPredictionMarketRunDetails('run-456', 1)

    expect(first).toMatchObject({
      run_id: 'run-456',
      workspace_id: 1,
      manifest: runManifest,
      artifact_refs: manifestArtifactRefs,
      benchmark_gate_summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'unproven',
      benchmark_evidence_level: 'benchmark_preview',
      benchmark_promotion_gate_kind: 'preview_only',
    })
    expect(first).toHaveProperty('artifacts')
    expect(first).toHaveProperty('artifact_readback')
    expect(first).toHaveProperty('artifact_audit')
    expect(first?.artifact_readback?.canonical_artifact_refs.map((ref) => ref.artifact_id)).toEqual([
      'run-456:market_descriptor',
      'run-456:run_manifest',
      'run-456:forecast_packet',
      'run-456:market_snapshot',
      'run-456:resolution_policy',
      'run-456:evidence_bundle',
      'run-456:recommendation_packet',
      'run-456:shadow_arbitrage',
    ])
    expect(first?.artifact_audit).toEqual({
      manifest_ref_count: 2,
      observed_ref_count: 8,
      canonical_ref_count: 8,
      run_manifest_present: true,
      duplicate_artifact_ids: [],
      manifest_only_artifact_ids: [],
      observed_only_artifact_ids: [
        'run-456:forecast_packet',
        'run-456:market_snapshot',
        'run-456:resolution_policy',
        'run-456:evidence_bundle',
        'run-456:recommendation_packet',
        'run-456:shadow_arbitrage',
      ],
    })
    expect(first?.shadow_arbitrage).toMatchObject({
      read_only: true,
      summary: {
        shadow_edge_bps: 75,
        recommended_size_usd: 75,
      },
      sizing: {
        requested_size_usd: null,
        recommended_size_usd: 75,
        simulated_size_usd: 75,
      },
    })

    expect(second?.artifact_readback).toEqual(first?.artifact_readback)
    expect(second?.artifact_audit).toEqual(first?.artifact_audit)
    expect(second?.artifact_readback?.canonical_artifact_refs.map((ref) => ref.artifact_id)).toEqual([
      'run-456:market_descriptor',
      'run-456:run_manifest',
      'run-456:forecast_packet',
      'run-456:market_snapshot',
      'run-456:resolution_policy',
      'run-456:evidence_bundle',
      'run-456:recommendation_packet',
      'run-456:shadow_arbitrage',
    ])
  })

  it('surfaces resolved history, cost model, and walk-forward summaries from stored artifacts', () => {
    const stored = mockStoredRunDetails()
    storeMocks.getPredictionMarketRunDetails.mockReturnValue({
      ...stored,
      artifacts: [
        ...stored.artifacts,
        {
          artifact_id: 'run-456:resolved_history',
          artifact_type: 'resolved_history',
          sha256: 'sha-resolved-history',
          payload: {
            artifact_kind: 'resolved_history',
            summary: 'Resolved history built from 14/14 evaluation records spanning 2026-01-01T00:00:00.000Z -> 2026-04-01T00:00:00.000Z.',
            resolved_records: 14,
            source_summary: 'Resolved 14 local evaluation records from 3 stored runs.',
            first_cutoff_at: '2026-01-01T00:00:00.000Z',
            last_cutoff_at: '2026-04-01T00:00:00.000Z',
          },
        },
        {
          artifact_id: 'run-456:cost_model_report',
          artifact_type: 'cost_model_report',
          sha256: 'sha-cost-model',
          payload: {
            artifact_kind: 'cost_model_report',
            summary: 'Cost model evaluated 14 resolved points; average net edge=118 bps, viable rate=0.642857.',
            total_points: 14,
            viable_point_count: 9,
            viable_point_rate: 0.642857,
            average_cost_bps: 47,
            average_net_edge_bps: 118,
          },
        },
        {
          artifact_id: 'run-456:walk_forward_report',
          artifact_type: 'walk_forward_report',
          sha256: 'sha-walk-forward',
          payload: {
            artifact_kind: 'walk_forward_report',
            summary: 'Walk-forward ran 4 windows; mean brier improvement=0.012, mean net edge=118 bps.',
            total_points: 14,
            total_windows: 4,
            stable_window_rate: 0.75,
            mean_calibrated_brier_score: 0.171,
            mean_calibrated_log_loss: 0.438,
            mean_brier_improvement: 0.012,
            mean_log_loss_improvement: 0.017,
            mean_net_edge_bps: 118,
            promotion_ready: true,
            notes: ['stable_windows'],
          },
        },
      ],
    })

    const detail = getPredictionMarketRunDetails('run-456', 1)

    expect(detail).toMatchObject({
      resolved_history_points: 14,
      resolved_history_source_summary: 'Resolved 14 local evaluation records from 3 stored runs.',
      resolved_history_first_cutoff_at: '2026-01-01T00:00:00.000Z',
      resolved_history_last_cutoff_at: '2026-04-01T00:00:00.000Z',
      cost_model_summary: 'Cost model evaluated 14 resolved points; average net edge=118 bps, viable rate=0.642857.',
      cost_model_total_points: 14,
      cost_model_viable_point_count: 9,
      cost_model_viable_point_rate: 0.642857,
      cost_model_average_cost_bps: 47,
      cost_model_average_net_edge_bps: 118,
      walk_forward_windows: 4,
      walk_forward_total_points: 14,
      walk_forward_stable_window_rate: 0.75,
      walk_forward_mean_brier_improvement: 0.012,
      walk_forward_mean_log_loss_improvement: 0.017,
      walk_forward_mean_net_edge_bps: 118,
      walk_forward_promotion_ready: true,
      walk_forward_summary: {
        summary: 'Walk-forward ran 4 windows; mean brier improvement=0.012, mean net edge=118 bps.',
        sample_count: 14,
        window_count: 4,
        win_rate: 0.75,
        brier_score: 0.171,
        log_loss: 0.438,
        uplift_bps: 118,
        promotion_ready: true,
        notes: ['stable_windows'],
      },
    })
  })
})
