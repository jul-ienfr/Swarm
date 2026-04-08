import { describe, expect, it, vi } from 'vitest'

const storeMocks = vi.hoisted(() => ({
  findRecentPredictionMarketRunByConfig: vi.fn(),
  getPredictionMarketRunDetails: vi.fn(),
  listPredictionMarketRuns: vi.fn(),
  persistPredictionMarketExecution: vi.fn(),
}))

vi.mock('@/lib/prediction-markets/store', () => ({
  findRecentPredictionMarketRunByConfig: storeMocks.findRecentPredictionMarketRunByConfig,
  getPredictionMarketRunDetails: storeMocks.getPredictionMarketRunDetails,
  listPredictionMarketRuns: storeMocks.listPredictionMarketRuns,
  persistPredictionMarketExecution: storeMocks.persistPredictionMarketExecution,
}))

import {
  getPredictionMarketRunDetails,
  listPredictionMarketRuns,
} from '@/lib/prediction-markets/service'
import {
  decisionPacketSchema,
  evidencePacketSchema,
  forecastPacketSchema,
  marketDescriptorSchema,
  marketRecommendationPacketSchema,
  marketSnapshotSchema,
  predictionMarketArtifactRefSchema,
  resolutionPolicySchema,
  runManifestSchema,
} from '@/lib/prediction-markets/schemas'

const baseArtifactRefs = [
  predictionMarketArtifactRefSchema.parse({
    artifact_id: 'run-123:market_descriptor',
    artifact_type: 'market_descriptor',
    sha256: 'sha-market-descriptor',
  }),
  predictionMarketArtifactRefSchema.parse({
    artifact_id: 'run-123:forecast_packet',
    artifact_type: 'forecast_packet',
    sha256: 'sha-forecast-packet',
  }),
]

const runManifest = runManifestSchema.parse({
  run_id: 'run-123',
  mode: 'advise',
  venue: 'polymarket',
  market_id: 'mkt-123',
  market_slug: 'mkt-123',
  actor: 'operator',
  started_at: '2026-04-08T00:00:00.000Z',
  completed_at: '2026-04-08T00:01:00.000Z',
  status: 'completed',
  config_hash: 'cfg-123',
  artifact_refs: baseArtifactRefs,
})

describe('prediction markets service artifact audit surfaces', () => {
  it('adds a compact artifact_audit summary to listPredictionMarketRuns', () => {
    storeMocks.listPredictionMarketRuns.mockReturnValueOnce([
      {
        run_id: 'run-123',
        source_run_id: null,
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: 'mkt-123',
        market_slug: 'mkt-123',
        status: 'completed',
        recommendation: 'wait',
        side: null,
        confidence: 0.62,
        probability_yes: 0.53,
        market_price_yes: 0.49,
        edge_bps: 400,
        created_at: 1712534400,
        updated_at: 1712534460,
        manifest: runManifest,
        artifact_refs: [
          ...baseArtifactRefs,
          predictionMarketArtifactRefSchema.parse({
            artifact_id: 'run-123:run_manifest',
            artifact_type: 'run_manifest',
            sha256: 'sha-run-manifest',
          }),
        ],
      },
    ])

    const runs = listPredictionMarketRuns({ workspaceId: 1, venue: 'polymarket', limit: 20 })

    expect(runs).toHaveLength(1)
    expect(runs[0]?.artifact_audit).toEqual({
      manifest_ref_count: 2,
      observed_ref_count: 3,
      canonical_ref_count: 3,
      run_manifest_present: true,
      duplicate_artifact_ids: [],
      manifest_only_artifact_ids: [],
      observed_only_artifact_ids: [],
    })
  })

  it('keeps benchmark aliases canonical on listPredictionMarketRuns even when only research benchmark hints are stored', () => {
    storeMocks.listPredictionMarketRuns.mockReturnValueOnce([
      {
        run_id: 'run-456',
        source_run_id: null,
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: 'mkt-456',
        market_slug: 'mkt-456',
        status: 'completed',
        recommendation: 'bet',
        side: 'yes',
        confidence: 0.71,
        probability_yes: 0.66,
        market_price_yes: 0.52,
        edge_bps: 1400,
        research_benchmark_gate_summary: 'research benchmark gate summary',
        research_benchmark_uplift_bps: 321,
        research_benchmark_verdict: 'preview_only',
        research_benchmark_gate_status: 'preview_only',
        research_benchmark_promotion_status: 'eligible',
        research_benchmark_promotion_ready: true,
        research_benchmark_preview_available: true,
        research_benchmark_promotion_evidence: 'local_benchmark',
        research_benchmark_evidence_level: 'out_of_sample_promotion_evidence',
        research_promotion_gate_kind: 'local_benchmark',
        research_benchmark_promotion_blocker_summary: 'benchmark promotion satisfied',
        research_benchmark_promotion_summary: 'benchmark promotion satisfied',
        research_benchmark_gate_blocks_live: false,
        research_benchmark_gate_blockers: [],
        research_benchmark_gate_reasons: ['benchmark-ready'],
        created_at: 1712534400,
        updated_at: 1712534460,
        manifest: runManifest,
        artifact_refs: [
          ...baseArtifactRefs,
          predictionMarketArtifactRefSchema.parse({
            artifact_id: 'run-456:run_manifest',
            artifact_type: 'run_manifest',
            sha256: 'sha-run-manifest',
          }),
        ],
      },
    ])

    const runs = listPredictionMarketRuns({ workspaceId: 1, venue: 'polymarket', limit: 20 })

    expect(runs[0]).toMatchObject({
      benchmark_gate_summary: 'research benchmark gate summary',
      benchmark_uplift_bps: 321,
      benchmark_verdict: 'preview_only',
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'eligible',
      benchmark_promotion_ready: true,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'local_benchmark',
      benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_promotion_blocker_summary: 'benchmark promotion satisfied',
      benchmark_promotion_summary: 'benchmark promotion satisfied',
      benchmark_gate_blocks_live: false,
      benchmark_gate_live_block_reason: null,
      benchmark_gate_blockers: [],
      benchmark_gate_reasons: ['benchmark-ready'],
    })
  })

  it('adds artifact_readback and artifact_audit to getPredictionMarketRunDetails', () => {
    storeMocks.getPredictionMarketRunDetails.mockReturnValueOnce({
      run_id: 'run-123',
      source_run_id: null,
      workspace_id: 1,
      venue: 'polymarket',
      mode: 'advise',
      market_id: 'mkt-123',
      market_slug: 'mkt-123',
      status: 'completed',
      recommendation: 'wait',
      side: null,
      confidence: 0.62,
      probability_yes: 0.53,
      market_price_yes: 0.49,
      edge_bps: 400,
      created_at: 1712534400,
      updated_at: 1712534460,
      manifest: runManifest,
      artifact_refs: [
        ...baseArtifactRefs,
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-123:run_manifest',
          artifact_type: 'run_manifest',
          sha256: 'sha-run-manifest',
        }),
      ],
      artifacts: [
        {
          artifact_id: 'run-123:market_descriptor',
          artifact_type: 'market_descriptor',
          sha256: 'sha-market-descriptor',
          payload: { market_id: 'mkt-123' },
        },
        {
          artifact_id: 'run-123:forecast_packet',
          artifact_type: 'forecast_packet',
          sha256: 'sha-forecast-packet',
          payload: { market_id: 'mkt-123' },
        },
        {
          artifact_id: 'run-123:run_manifest',
          artifact_type: 'run_manifest',
          sha256: 'sha-run-manifest',
          payload: runManifest,
        },
      ],
    })

    const details = getPredictionMarketRunDetails('run-123', 1)

    expect(details).not.toBeNull()
    expect(details?.artifact_audit).toEqual({
      manifest_ref_count: 2,
      observed_ref_count: 3,
      canonical_ref_count: 3,
      run_manifest_present: true,
      duplicate_artifact_ids: [],
      manifest_only_artifact_ids: [],
      observed_only_artifact_ids: [],
    })
    expect(details?.artifact_readback).toBeDefined()
    expect(details?.artifact_readback?.run_manifest_ref?.artifact_id).toBe('run-123:run_manifest')
    expect(details?.artifact_readback?.canonical_artifact_refs.map((ref) => ref.artifact_id)).toEqual([
      'run-123:market_descriptor',
      'run-123:forecast_packet',
      'run-123:run_manifest',
    ])
  })

  it('surfaces market events and positions when stored artifacts include them', () => {
    const marketDescriptor = marketDescriptorSchema.parse({
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      market_id: 'mkt-124',
      slug: 'mkt-124',
      question: 'Will the detail surface include market events and positions?',
      outcomes: ['Yes', 'No'],
      active: true,
      closed: false,
      accepting_orders: true,
      restricted: false,
      source_urls: ['https://example.com/mkt-124'],
      is_binary_yes_no: true,
    })
    const snapshot = marketSnapshotSchema.parse({
      venue: 'polymarket',
      market: marketDescriptor,
      captured_at: '2026-04-08T00:00:00.000Z',
      yes_outcome_index: 0,
      yes_token_id: 'mkt-124:yes',
      yes_price: 0.49,
      no_price: 0.51,
      midpoint_yes: 0.5,
      best_bid_yes: 0.49,
      best_ask_yes: 0.51,
      spread_bps: 200,
      book: null,
      history: [],
      source_urls: ['https://example.com/mkt-124/snapshot'],
    })
    const resolutionPolicy = resolutionPolicySchema.parse({
      market_id: 'mkt-124',
      venue: 'polymarket',
      status: 'eligible',
      manual_review_required: false,
      reasons: [],
      primary_sources: ['https://example.com/mkt-124/rules'],
      evaluated_at: '2026-04-08T00:00:00.000Z',
    })
    const evidencePacket = evidencePacketSchema.parse({
      evidence_id: 'run-124:manual-thesis',
      market_id: 'mkt-124',
      venue: 'polymarket',
      type: 'manual_thesis',
      title: 'Manual thesis',
      summary: 'Manual thesis used for replay.',
      captured_at: '2026-04-08T00:00:00.000Z',
      content_hash: 'sha-manual-thesis',
      metadata: {},
    })
    const forecast = forecastPacketSchema.parse({
      market_id: 'mkt-124',
      venue: 'polymarket',
      basis: 'manual_thesis',
      probability_yes: 0.55,
      confidence: 0.61,
      rationale: 'Replay-ready forecast.',
      evidence_refs: [evidencePacket.evidence_id],
      produced_at: '2026-04-08T00:00:00.000Z',
    })
    const recommendation = marketRecommendationPacketSchema.parse({
      market_id: 'mkt-124',
      venue: 'polymarket',
      action: 'wait',
      side: null,
      confidence: 0.61,
      fair_value_yes: 0.55,
      market_price_yes: 0.49,
      market_bid_yes: 0.48,
      market_ask_yes: 0.5,
      edge_bps: 100,
      spread_bps: 200,
      reasons: ['Replay-ready recommendation.'],
      risk_flags: [],
      produced_at: '2026-04-08T00:00:00.000Z',
    })
    const runManifestForRun124 = runManifestSchema.parse({
      ...runManifest,
      run_id: 'run-124',
      market_id: 'mkt-124',
      market_slug: 'mkt-124',
      artifact_refs: [
        ...baseArtifactRefs,
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-124:market_snapshot',
          artifact_type: 'market_snapshot',
          sha256: 'sha-market-snapshot',
        }),
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-124:resolution_policy',
          artifact_type: 'resolution_policy',
          sha256: 'sha-resolution-policy',
        }),
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-124:evidence_bundle',
          artifact_type: 'evidence_bundle',
          sha256: 'sha-evidence-bundle',
        }),
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-124:forecast_packet',
          artifact_type: 'forecast_packet',
          sha256: 'sha-forecast-packet',
        }),
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-124:recommendation_packet',
          artifact_type: 'recommendation_packet',
          sha256: 'sha-recommendation-packet',
        }),
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-124:market_events',
          artifact_type: 'market_events',
          sha256: 'sha-market-events',
        }),
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-124:market_positions',
          artifact_type: 'market_positions',
          sha256: 'sha-market-positions',
        }),
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-124:shadow_arbitrage',
          artifact_type: 'shadow_arbitrage',
          sha256: 'sha-shadow-arbitrage',
        }),
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-124:run_manifest',
          artifact_type: 'run_manifest',
          sha256: 'sha-run-manifest',
        }),
      ],
    })
    storeMocks.getPredictionMarketRunDetails.mockReturnValueOnce({
      run_id: 'run-124',
      source_run_id: null,
      workspace_id: 1,
      venue: 'polymarket',
      mode: 'advise',
      market_id: 'mkt-124',
      market_slug: 'mkt-124',
      status: 'completed',
      recommendation: 'wait',
      side: null,
      confidence: 0.62,
      probability_yes: 0.53,
      market_price_yes: 0.49,
      edge_bps: 400,
      created_at: 1712534400,
      updated_at: 1712534460,
      manifest: runManifestForRun124,
      artifact_refs: runManifestForRun124.artifact_refs,
      artifacts: [
        {
          artifact_id: 'run-124:market_descriptor',
          artifact_type: 'market_descriptor',
          sha256: 'sha-market-descriptor',
          payload: marketDescriptor,
        },
        {
          artifact_id: 'run-124:market_snapshot',
          artifact_type: 'market_snapshot',
          sha256: 'sha-market-snapshot',
          payload: snapshot,
        },
        {
          artifact_id: 'run-124:resolution_policy',
          artifact_type: 'resolution_policy',
          sha256: 'sha-resolution-policy',
          payload: resolutionPolicy,
        },
        {
          artifact_id: 'run-124:evidence_bundle',
          artifact_type: 'evidence_bundle',
          sha256: 'sha-evidence-bundle',
          payload: [evidencePacket],
        },
        {
          artifact_id: 'run-124:forecast_packet',
          artifact_type: 'forecast_packet',
          sha256: 'sha-forecast-packet',
          payload: forecast,
        },
        {
          artifact_id: 'run-124:recommendation_packet',
          artifact_type: 'recommendation_packet',
          sha256: 'sha-recommendation-packet',
          payload: recommendation,
        },
        {
          artifact_id: 'run-124:market_events',
          artifact_type: 'market_events',
          sha256: 'sha-market-events',
          payload: { feed: 'rtds', events: [{ id: 'evt-1' }] },
        },
        {
          artifact_id: 'run-124:market_positions',
          artifact_type: 'market_positions',
          sha256: 'sha-market-positions',
          payload: { source: 'positions', positions: [] },
        },
        {
          artifact_id: 'run-124:shadow_arbitrage',
          artifact_type: 'shadow_arbitrage',
          sha256: 'sha-shadow-arbitrage',
          payload: {
            read_only: true,
            generated_at: '2026-04-08T00:00:00.000Z',
            as_of_at: '2026-04-08T00:00:00.000Z',
            sizing: {
              requested_size_usd: null,
              base_size_usd: 100,
              recommended_size_usd: 75,
              simulated_size_usd: 75,
              size_multiplier: 0.75,
            },
            summary: {
              shadow_edge_bps: 112,
              recommended_size_usd: 75,
            },
          },
        },
        {
          artifact_id: 'run-124:run_manifest',
          artifact_type: 'run_manifest',
          sha256: 'sha-run-manifest',
          payload: runManifestForRun124,
        },
      ],
    })

    const details = getPredictionMarketRunDetails('run-124', 1)

    expect(details).not.toBeNull()
    expect(details?.market_events).toEqual({ feed: 'rtds', events: [{ id: 'evt-1' }] })
    expect(details?.market_positions).toEqual({ source: 'positions', positions: [] })
    expect(details?.shadow_arbitrage).toMatchObject({
      read_only: true,
      summary: {
        shadow_edge_bps: 112,
        recommended_size_usd: 75,
      },
      sizing: {
        requested_size_usd: null,
        base_size_usd: 100,
        recommended_size_usd: 75,
        simulated_size_usd: 75,
        size_multiplier: 0.75,
      },
    })
  })

  it('derives a canonical packet_bundle from replay/postmortem stored artifacts', () => {
    const marketDescriptor = marketDescriptorSchema.parse({
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      market_id: 'mkt-125',
      slug: 'mkt-125',
      question: 'Will the packet bundle include replay surfaces?',
      outcomes: ['Yes', 'No'],
      active: true,
      closed: false,
      accepting_orders: true,
      restricted: false,
      source_urls: ['https://example.com/mkt-125'],
      is_binary_yes_no: true,
    })
    const snapshot = marketSnapshotSchema.parse({
      venue: 'polymarket',
      market: marketDescriptor,
      captured_at: '2026-04-08T00:00:00.000Z',
      yes_outcome_index: 0,
      yes_token_id: 'mkt-125:yes',
      yes_price: 0.47,
      no_price: 0.53,
      midpoint_yes: 0.5,
      best_bid_yes: 0.46,
      best_ask_yes: 0.48,
      spread_bps: 200,
      book: null,
      history: [],
      source_urls: ['https://example.com/mkt-125/snapshot'],
    })
    const resolutionPolicy = resolutionPolicySchema.parse({
      market_id: 'mkt-125',
      venue: 'polymarket',
      status: 'eligible',
      manual_review_required: false,
      reasons: [],
      primary_sources: ['https://example.com/mkt-125/rules'],
      evaluated_at: '2026-04-08T00:00:00.000Z',
    })
    const decisionPacket = decisionPacketSchema.parse({
      correlation_id: 'decision-125',
      question: 'Will the packet bundle include replay surfaces?',
      topic: 'packet bundle coverage',
      objective: 'Exercise the canonical packet bundle surface.',
      probability_estimate: 0.64,
      confidence_band: { low: 0.59, high: 0.69 },
      scenarios: ['Baseline replay', 'Replay with audit bundle'],
      risks: ['Surface drift'],
      recommendation: 'Use the bundle for replay/postmortem inspection.',
      rationale_summary: 'Replay surfaces should be directly inspectable.',
      artifacts: ['run-125:decision-note'],
      mode_used: 'advise',
      engine_used: 'agentsociety',
      runtime_used: 'live',
    })
    const evidencePacket = evidencePacketSchema.parse({
      evidence_id: 'run-125:decision-note',
      market_id: 'mkt-125',
      venue: 'polymarket',
      type: 'system_note',
      title: 'Decision note',
      summary: 'Decision packet note.',
      captured_at: '2026-04-08T00:00:00.000Z',
      content_hash: 'sha-decision-note',
      metadata: {
        decision_packet: decisionPacket,
      },
    })
    const forecast = forecastPacketSchema.parse({
      market_id: 'mkt-125',
      venue: 'polymarket',
      basis: 'manual_thesis',
      probability_yes: 0.64,
      confidence: 0.69,
      rationale: 'Replay bundle forecast.',
      evidence_refs: [evidencePacket.evidence_id],
      produced_at: '2026-04-08T00:00:00.000Z',
    })
    const recommendation = marketRecommendationPacketSchema.parse({
      market_id: 'mkt-125',
      venue: 'polymarket',
      action: 'wait',
      side: null,
      confidence: 0.69,
      fair_value_yes: 0.64,
      market_price_yes: 0.47,
      market_bid_yes: 0.46,
      market_ask_yes: 0.48,
      edge_bps: 170,
      spread_bps: 200,
      reasons: ['Replay bundle recommendation.'],
      risk_flags: [],
      produced_at: '2026-04-08T00:00:00.000Z',
    })
    const runManifestForRun125 = runManifestSchema.parse({
      ...runManifest,
      run_id: 'run-125',
      market_id: 'mkt-125',
      market_slug: 'mkt-125',
      artifact_refs: [
        ...baseArtifactRefs,
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-125:market_snapshot',
          artifact_type: 'market_snapshot',
          sha256: 'sha-market-snapshot-125',
        }),
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-125:resolution_policy',
          artifact_type: 'resolution_policy',
          sha256: 'sha-resolution-policy-125',
        }),
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-125:evidence_bundle',
          artifact_type: 'evidence_bundle',
          sha256: 'sha-evidence-bundle-125',
        }),
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-125:forecast_packet',
          artifact_type: 'forecast_packet',
          sha256: 'sha-forecast-packet-125',
        }),
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-125:recommendation_packet',
          artifact_type: 'recommendation_packet',
          sha256: 'sha-recommendation-packet-125',
        }),
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-125:paper_surface',
          artifact_type: 'paper_surface',
          sha256: 'sha-paper-surface-125',
        }),
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-125:replay_surface',
          artifact_type: 'replay_surface',
          sha256: 'sha-replay-surface-125',
        }),
        predictionMarketArtifactRefSchema.parse({
          artifact_id: 'run-125:run_manifest',
          artifact_type: 'run_manifest',
          sha256: 'sha-run-manifest-125',
        }),
      ],
    })
    storeMocks.getPredictionMarketRunDetails.mockReturnValueOnce({
      run_id: 'run-125',
      source_run_id: null,
      workspace_id: 1,
      venue: 'polymarket',
      mode: 'replay',
      market_id: 'mkt-125',
      market_slug: 'mkt-125',
      status: 'completed',
      recommendation: 'wait',
      side: null,
      confidence: 0.69,
      probability_yes: 0.64,
      market_price_yes: 0.47,
      edge_bps: 170,
      created_at: 1712534400,
      updated_at: 1712534460,
      manifest: runManifestForRun125,
      artifact_refs: runManifestForRun125.artifact_refs,
      artifacts: [
        {
          artifact_id: 'run-125:market_descriptor',
          artifact_type: 'market_descriptor',
          sha256: 'sha-market-descriptor-125',
          payload: marketDescriptor,
        },
        {
          artifact_id: 'run-125:market_snapshot',
          artifact_type: 'market_snapshot',
          sha256: 'sha-market-snapshot-125',
          payload: snapshot,
        },
        {
          artifact_id: 'run-125:resolution_policy',
          artifact_type: 'resolution_policy',
          sha256: 'sha-resolution-policy-125',
          payload: resolutionPolicy,
        },
        {
          artifact_id: 'run-125:evidence_bundle',
          artifact_type: 'evidence_bundle',
          sha256: 'sha-evidence-bundle-125',
          payload: [evidencePacket],
        },
        {
          artifact_id: 'run-125:forecast_packet',
          artifact_type: 'forecast_packet',
          sha256: 'sha-forecast-packet-125',
          payload: forecast,
        },
        {
          artifact_id: 'run-125:recommendation_packet',
          artifact_type: 'recommendation_packet',
          sha256: 'sha-recommendation-packet-125',
          payload: recommendation,
        },
        {
          artifact_id: 'run-125:paper_surface',
          artifact_type: 'paper_surface',
          sha256: 'sha-paper-surface-125',
          payload: {
            no_trade_zone_count: 1,
            no_trade_zone_rate: 0.5,
            order_trace_audit: {
              trace_id: 'trace-125',
              place_auditable: true,
              cancel_auditable: true,
              live_execution_status: 'ready',
              market_execution_status: 'ready',
              metadata: { source: 'paper_surface' },
            },
          },
        },
        {
          artifact_id: 'run-125:replay_surface',
          artifact_type: 'replay_surface',
          sha256: 'sha-replay-surface-125',
          payload: {
            no_trade_leg_count: 2,
            no_trade_leg_rate: 0.4,
            summary: 'Replay surface for postmortem.',
          },
        },
        {
          artifact_id: 'run-125:run_manifest',
          artifact_type: 'run_manifest',
          sha256: 'sha-run-manifest-125',
          payload: runManifestForRun125,
        },
      ],
    })

    const details = getPredictionMarketRunDetails('run-125', 1)

    expect(details).not.toBeNull()
    expect(details?.packet_bundle).toMatchObject({
      bundle_id: 'run-125:packet_bundle',
      run_id: 'run-125',
      venue: 'polymarket',
      market_id: 'mkt-125',
      advisor_architecture: expect.objectContaining({
        architecture_id: 'run-125:advisor_architecture',
        architecture_kind: 'reference_agentic',
      }),
      decision_packet: decisionPacket,
      forecast_packet: expect.objectContaining({
        probability_yes: 0.64,
        packet_kind: 'forecast',
      }),
      recommendation_packet: expect.objectContaining({
        action: 'wait',
        packet_kind: 'recommendation',
      }),
      paper_surface: expect.objectContaining({
        no_trade_zone_count: 1,
      }),
      replay_surface: expect.objectContaining({
        no_trade_leg_count: 2,
      }),
      order_trace_audit: expect.objectContaining({
        trace_id: 'trace-125',
        place_auditable: true,
      }),
    })
  })
})
