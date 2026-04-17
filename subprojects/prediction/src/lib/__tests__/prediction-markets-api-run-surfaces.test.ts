import { describe, expect, it, vi } from 'vitest'

const storeMocks = vi.hoisted(() => ({
  getPredictionMarketRunDetails: vi.fn(),
  listPredictionMarketRuns: vi.fn(),
}))

vi.mock('@/lib/prediction-markets/store', () => ({
  getPredictionMarketRunDetails: storeMocks.getPredictionMarketRunDetails,
  listPredictionMarketRuns: storeMocks.listPredictionMarketRuns,
}))

import {
  getPredictionMarketRunDetails,
  listPredictionMarketRuns,
} from '@/lib/prediction-markets/service'
import {
  evidencePacketSchema,
  forecastPacketSchema,
  predictionMarketArtifactRefSchema,
  marketDescriptorSchema,
  marketSnapshotSchema,
  marketRecommendationPacketSchema,
  resolutionPolicySchema,
  runManifestSchema,
} from '@/lib/prediction-markets/schemas'

type FutureTopLevelTradeIntentPreviewSurface = {
  selected_trade_intent_preview?: unknown | null
  canonical_trade_intent_preview?: unknown | null
  execution_projection_selected_preview?: unknown | null
  execution_projection_selected_preview_source?: unknown | null
  trade_intent_guard?: {
    trade_intent_preview?: unknown | null
  } | null
  execution_projection?: {
    selected_path?: string | null
    projected_paths?: Record<string, {
      canonical_trade_intent_preview?: unknown | null
      trade_intent_preview?: unknown | null
    }>
  } | null
}

type FutureTradeIntentPreview = {
  size_usd: number
  notes?: string
}

function asFutureTradeIntentPreview(value: unknown): FutureTradeIntentPreview | null {
  const record = value as Record<string, unknown> | null
  return record && typeof record.size_usd === 'number'
    ? value as FutureTradeIntentPreview
    : null
}

function expectFutureTopLevelTradeIntentPreviewAlignment(
  surface: FutureTopLevelTradeIntentPreviewSurface,
) {
  const projectedPaths = surface.execution_projection?.projected_paths ?? {}
  const selectedPath = surface.execution_projection?.selected_path ?? null
  const selectedProjectionPath = selectedPath ? projectedPaths[selectedPath] ?? null : null
  const candidateProjectionSelectedPreview =
    selectedProjectionPath?.canonical_trade_intent_preview ??
    selectedProjectionPath?.trade_intent_preview ??
    null
  const rawProjectionSelectedPreview = asFutureTradeIntentPreview(candidateProjectionSelectedPreview)
  const projectionCanonicalSizeUsd = selectedProjectionPath &&
    typeof selectedProjectionPath === 'object' &&
    'sizing_signal' in selectedProjectionPath &&
    selectedProjectionPath.sizing_signal &&
    typeof selectedProjectionPath.sizing_signal === 'object' &&
    'canonical_size_usd' in (selectedProjectionPath.sizing_signal as Record<string, unknown>)
      ? ((selectedProjectionPath.sizing_signal as Record<string, unknown>).canonical_size_usd as number | null | undefined) ?? null
      : null
  const expectedProjectionSelectedPreview = rawProjectionSelectedPreview != null &&
    projectionCanonicalSizeUsd != null &&
    projectionCanonicalSizeUsd < rawProjectionSelectedPreview.size_usd
    ? {
      ...rawProjectionSelectedPreview,
      size_usd: projectionCanonicalSizeUsd,
      notes: [
        rawProjectionSelectedPreview.notes,
        `Canonical execution sizing caps preview size to ${projectionCanonicalSizeUsd} USD.`,
      ].filter(Boolean).join(' '),
    }
    : rawProjectionSelectedPreview
  const expectedTradeIntentPreview = surface.trade_intent_guard?.trade_intent_preview
    ?? expectedProjectionSelectedPreview
    ?? null
  const expectedTradeIntentPreviewSource = selectedProjectionPath?.canonical_trade_intent_preview != null
    ? 'canonical_trade_intent_preview'
    : selectedProjectionPath?.trade_intent_preview != null
      ? 'trade_intent_preview'
      : null

  for (const fieldName of ['selected_trade_intent_preview', 'canonical_trade_intent_preview'] as const) {
    const topLevelTradeIntentPreview = surface[fieldName]
    if (topLevelTradeIntentPreview != null) {
      expect(topLevelTradeIntentPreview).toEqual(expectedTradeIntentPreview)
    }
  }

  if (surface.execution_projection_selected_preview != null) {
    expect(surface.execution_projection_selected_preview).toEqual(expectedProjectionSelectedPreview)
  }

  if (surface.execution_projection_selected_preview_source != null) {
    expect(surface.execution_projection_selected_preview_source).toBe(expectedTradeIntentPreviewSource)
  }
}

function makeArtifactRef(input: {
  runId: string
  artifactType:
    | 'market_descriptor'
    | 'market_snapshot'
    | 'resolution_policy'
    | 'evidence_bundle'
    | 'forecast_packet'
  | 'recommendation_packet'
  | 'execution_pathways'
  | 'execution_projection'
  | 'pipeline_guard'
  | 'shadow_arbitrage'
  | 'cross_venue_intelligence'
  | 'multi_venue_execution'
  | 'run_manifest'
  sha256: string
}) {
  return predictionMarketArtifactRefSchema.parse({
    artifact_id: `${input.runId}:${input.artifactType}`,
    artifact_type: input.artifactType,
    sha256: input.sha256,
  })
}

function makeShadowArbitrageArtifact(recommendedSizeUsd: number) {
  return {
    read_only: true,
    generated_at: '2026-04-08T00:00:00.000Z',
    as_of_at: '2026-04-08T00:00:00.000Z',
    executable_edge: {
      executable: true,
    },
    microstructure_summary: {
      recommended_mode: 'shadow',
      worst_case_severity: 'medium',
      executable_deterioration_bps: 18,
      execution_quality_score: 0.78,
      scenario_overview: [
        'shadow_arbitrage: liquidity and depth stay constrained',
      ],
      notes: [
        'shadow sizing stays conservative when depth or liquidity is thin.',
      ],
    },
    sizing: {
      requested_size_usd: 100,
      base_size_usd: 100,
      recommended_size_usd: recommendedSizeUsd,
      simulated_size_usd: recommendedSizeUsd,
      size_multiplier: 0.75,
    },
    failure_cases: [],
    summary: {
      base_executable_edge_bps: 120,
      microstructure_deterioration_bps: 18,
      shadow_drag_bps: 22,
      shadow_edge_bps: 98,
      base_size_usd: 100,
      recommended_size_usd: recommendedSizeUsd,
      hedge_success_probability: 0.91,
      hedge_success_expected: true,
      estimated_net_pnl_bps: 44,
      estimated_net_pnl_usd: 7.5,
      worst_case_kind: 'hedge_delay',
      failure_case_count: 3,
      scenario_overview: [
        'hedge_delay:liquidity and depth keep the shadow leg conservative',
      ],
      notes: [
        'shadow_arbitrage sizing is reduced by liquidity, depth, and correlation signals',
      ],
    },
  }
}

function makeExecutionProjectionArtifact(input: {
  runId: string
  requestedPath: 'paper' | 'shadow' | 'live'
  selectedPath: 'paper' | 'shadow' | 'live'
  shadowRecommendedSizeUsd: number
  shadowPreviewSizeUsd?: number
}) {
  const preTradeByPath = {
    paper: {
      gate_name: 'hard_no_trade',
      verdict: 'pass',
      edge_bucket: 'forecast_alpha',
      net_edge_bps: 640,
      minimum_net_edge_bps: 180,
      summary: 'Hard no-trade gate pass. bucket=forecast_alpha gross=880bps frictions=240bps net=640bps minimum=180bps',
    },
    shadow: {
      gate_name: 'hard_no_trade',
      verdict: 'pass',
      edge_bucket: 'arbitrage_alpha',
      net_edge_bps: 980,
      minimum_net_edge_bps: 240,
      summary: 'Hard no-trade gate pass. bucket=arbitrage_alpha gross=1240bps frictions=260bps net=980bps minimum=240bps',
    },
    live: {
      gate_name: 'hard_no_trade',
      verdict: 'pass',
      edge_bucket: 'execution_alpha',
      net_edge_bps: 1210,
      minimum_net_edge_bps: 320,
      summary: 'Hard no-trade gate pass. bucket=execution_alpha gross=1480bps frictions=270bps net=1210bps minimum=320bps',
    },
  } as const
  const selectedPreTradeGate = preTradeByPath[input.selectedPath]
  const selectedEdgeBucket = selectedPreTradeGate.edge_bucket
  const microstructure = {
    recommended_mode: 'shadow',
    worst_case_severity: 'medium',
    executable_deterioration_bps: 18,
    execution_quality_score: 0.78,
  }
  const tradeIntentPreview = {
    schema_version: '1.0.0',
    intent_id: `${input.runId}:shadow-preview`,
    run_id: input.runId,
    venue: 'polymarket',
    market_id: `${input.runId}-market`,
    side: 'yes',
    size_usd: input.shadowPreviewSizeUsd ?? input.shadowRecommendedSizeUsd,
    limit_price: 0.51,
    max_slippage_bps: 50,
    max_unhedged_leg_ms: 1_000,
    time_in_force: 'ioc',
    forecast_ref: `forecast:${input.runId}:2026-04-08T00:00:00.000Z`,
    risk_checks_passed: true,
    created_at: '2026-04-08T00:00:00.000Z',
    notes: 'shadow preview intent',
  }

  return {
    gate_name: 'execution_projection',
    preflight_only: true,
    requested_path: input.requestedPath,
    selected_path: input.selectedPath,
    eligible_paths: ['paper', 'shadow', 'live'],
    verdict: input.requestedPath === input.selectedPath ? 'allowed' : 'downgraded',
    blocking_reasons: [],
    downgrade_reasons: input.requestedPath === input.selectedPath
      ? []
      : [`selected_path:${input.requestedPath}->${input.selectedPath}`],
    manual_review_required: false,
    generated_at: '2026-04-08T00:00:00.000Z',
    ttl_ms: 30_000,
    expires_at: '2026-04-08T00:00:30.000Z',
    highest_safe_requested_mode: input.selectedPath,
    recommended_effective_mode: input.selectedPath,
    selected_edge_bucket: selectedEdgeBucket,
    selected_pre_trade_gate: selectedPreTradeGate,
    basis: {
      uses_execution_readiness: true,
      uses_compliance: true,
      uses_capital: true,
      uses_reconciliation: false,
      uses_microstructure: true,
      capital_status: 'attached',
      reconciliation_status: 'unavailable',
      source_refs: {
        pipeline_guard: `${input.runId}:pipeline_guard`,
        compliance_report: `${input.runId}:compliance_report`,
        execution_readiness: `${input.runId}:execution_readiness`,
        venue_health: `${input.runId}:pipeline_guard#venue_health`,
        capital_ledger: `${input.runId}:execution_readiness#capital_ledger`,
        reconciliation: null,
        microstructure_lab: `${input.runId}:microstructure_lab`,
      },
      canonical_gate: {
        gate_name: 'execution_projection',
        single_runtime_gate: true,
        enforced_for_modes: ['paper', 'shadow', 'live'],
      },
    },
    microstructure_summary: microstructure,
    modes: {
      paper: {
        requested_mode: 'paper',
        verdict: 'ready',
        effective_mode: 'paper',
        blockers: [],
        warnings: [],
        summary: 'paper ready',
      },
      shadow: {
        requested_mode: 'shadow',
        verdict: 'ready',
        effective_mode: 'shadow',
        blockers: [],
        warnings: [],
        summary: 'shadow ready',
      },
      live: {
        requested_mode: 'live',
        verdict: input.selectedPath === 'live' ? 'ready' : 'blocked',
        effective_mode: input.selectedPath,
        blockers: input.selectedPath === 'live' ? [] : ['selected_path_downgraded'],
        warnings: [],
        summary: input.selectedPath === 'live' ? 'live ready' : 'live downgraded',
      },
    },
    projected_paths: {
      paper: {
        path: 'paper',
        requested_mode: 'paper',
        effective_mode: 'paper',
        status: 'ready',
        allowed: true,
        blockers: [],
        warnings: [],
        reason_summary: 'Paper projection is ready.',
        edge_bucket: preTradeByPath.paper.edge_bucket,
        pre_trade_gate: preTradeByPath.paper,
        simulation: {
          expected_fill_confidence: 0.97,
          expected_slippage_bps: 0,
          stale_quote_risk: 'low',
          quote_age_ms: 0,
          notes: [],
          shadow_arbitrage: null,
        },
        trade_intent_preview: null,
      },
      shadow: {
        path: 'shadow',
        requested_mode: 'shadow',
        effective_mode: 'shadow',
        status: 'ready',
        allowed: true,
        blockers: [],
        warnings: [],
        reason_summary: 'Shadow projection is ready.',
        edge_bucket: preTradeByPath.shadow.edge_bucket,
        pre_trade_gate: preTradeByPath.shadow,
        simulation: {
          expected_fill_confidence: 0.88,
          expected_slippage_bps: 12,
          stale_quote_risk: 'low',
          quote_age_ms: 0,
          notes: ['Shadow arbitrage simulation is attached.'],
          shadow_arbitrage: makeShadowArbitrageArtifact(input.shadowRecommendedSizeUsd),
        },
        trade_intent_preview: tradeIntentPreview,
        canonical_trade_intent_preview: {
          ...tradeIntentPreview,
          size_usd: input.shadowRecommendedSizeUsd,
          notes: `shadow preview intent Canonical execution sizing caps preview size to ${input.shadowRecommendedSizeUsd} USD.`,
        },
        sizing_signal: {
          preview_size_usd: input.shadowPreviewSizeUsd ?? input.shadowRecommendedSizeUsd,
          base_size_usd: 100,
          recommended_size_usd: input.shadowPreviewSizeUsd ?? input.shadowRecommendedSizeUsd,
          max_size_usd: 100,
          canonical_size_usd: input.shadowRecommendedSizeUsd,
          shadow_recommended_size_usd: input.shadowRecommendedSizeUsd,
          limit_price: 0.51,
          max_slippage_bps: 50,
          max_unhedged_leg_ms: 1_000,
          time_in_force: 'ioc',
          multiplier: 0.75,
          sizing_source: 'default',
          source: 'trade_intent_preview+shadow_arbitrage',
          notes: ['Shadow canonical sizing stays conservative.'],
        },
        shadow_arbitrage_signal: {
          read_only: true,
          market_id: `${input.runId}-market`,
          venue: 'polymarket',
          base_executable_edge_bps: 120,
          shadow_edge_bps: 98,
          recommended_size_usd: input.shadowRecommendedSizeUsd,
          hedge_success_probability: 0.91,
          estimated_net_pnl_bps: 44,
          estimated_net_pnl_usd: 7.5,
          worst_case_kind: 'hedge_delay',
          failure_case_count: 3,
        },
      },
      live: {
        path: 'live',
        requested_mode: 'live',
        effective_mode: input.selectedPath,
        status: input.selectedPath === 'live' ? 'ready' : 'blocked',
        allowed: input.selectedPath === 'live',
        blockers: input.selectedPath === 'live' ? [] : ['selected_path_downgraded'],
        warnings: [],
        reason_summary: input.selectedPath === 'live' ? 'Live projection is ready.' : 'Live projection is downgraded.',
        edge_bucket: preTradeByPath.live.edge_bucket,
        pre_trade_gate: preTradeByPath.live,
        simulation: {
          expected_fill_confidence: 0.74,
          expected_slippage_bps: 25,
          stale_quote_risk: 'low',
          quote_age_ms: 0,
          notes: [],
          shadow_arbitrage: null,
        },
        trade_intent_preview: input.selectedPath === 'live'
          ? {
            ...tradeIntentPreview,
            intent_id: `${input.runId}:live-preview`,
            size_usd: Math.max(25, input.shadowRecommendedSizeUsd / 2),
          }
          : null,
        canonical_trade_intent_preview: input.selectedPath === 'live'
          ? {
            ...tradeIntentPreview,
            intent_id: `${input.runId}:live-preview`,
            size_usd: Math.max(25, input.shadowRecommendedSizeUsd / 2),
          }
          : null,
        sizing_signal: input.selectedPath === 'live'
          ? {
            preview_size_usd: Math.max(25, input.shadowRecommendedSizeUsd / 2),
            base_size_usd: 100,
            recommended_size_usd: Math.max(25, input.shadowRecommendedSizeUsd / 2),
            max_size_usd: 100,
            canonical_size_usd: Math.max(25, input.shadowRecommendedSizeUsd / 2),
            shadow_recommended_size_usd: null,
            limit_price: 0.51,
            max_slippage_bps: 50,
            max_unhedged_leg_ms: 250,
            time_in_force: 'ioc',
            multiplier: 0.5,
            sizing_source: 'default',
            source: 'trade_intent_preview',
            notes: ['Live sizing remains preview-only in this fixture.'],
          }
          : null,
        shadow_arbitrage_signal: null,
      },
    },
    preflight_summary: {
      gate_name: 'execution_projection',
      preflight_only: true,
      requested_path: input.requestedPath,
      selected_path: input.selectedPath,
      verdict: input.requestedPath === input.selectedPath ? 'allowed' : 'downgraded',
      highest_safe_requested_mode: input.selectedPath,
      recommended_effective_mode: input.selectedPath,
      manual_review_required: false,
      ttl_ms: 30_000,
      expires_at: '2026-04-08T00:00:30.000Z',
      counts: {
        total: 3,
        eligible: 3,
        ready: input.selectedPath === 'live' ? 3 : 2,
        degraded: 0,
        blocked: input.selectedPath === 'live' ? 0 : 1,
      },
      basis: {
        uses_execution_readiness: true,
        uses_compliance: true,
        uses_capital: true,
        uses_reconciliation: false,
        uses_microstructure: true,
        capital_status: 'attached',
        reconciliation_status: 'unavailable',
      },
      source_refs: [
        `${input.runId}:pipeline_guard`,
        `${input.runId}:compliance_report`,
        `${input.runId}:execution_readiness`,
        `${input.runId}:pipeline_guard#venue_health`,
        `${input.runId}:execution_readiness#capital_ledger`,
        `${input.runId}:microstructure_lab`,
      ],
      blockers: [],
      downgrade_reasons: input.requestedPath === input.selectedPath
        ? []
        : [`selected_path:${input.requestedPath}->${input.selectedPath}`],
      selected_edge_bucket: selectedEdgeBucket,
      selected_pre_trade_gate: selectedPreTradeGate,
      microstructure,
      summary: `gate=execution_projection preflight=yes verdict=${input.requestedPath === input.selectedPath ? 'allowed' : 'downgraded'} requested=${input.requestedPath} selected=${input.selectedPath}`,
    },
  }
}

function makeRunManifest(input: {
  runId: string
  artifactRefs: Array<ReturnType<typeof makeArtifactRef>>
}) {
  return runManifestSchema.parse({
    run_id: input.runId,
    mode: 'advise',
    venue: 'polymarket',
    market_id: 'mkt-api-001',
    market_slug: 'mkt-api-001',
    actor: 'operator',
    started_at: '2026-04-08T00:00:00.000Z',
    completed_at: '2026-04-08T00:01:00.000Z',
    status: 'completed',
    config_hash: `cfg-${input.runId}`,
    artifact_refs: input.artifactRefs,
  })
}

function makeMarketDescriptor(runId: string) {
  return marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: `${runId}-market`,
    slug: `${runId}-market`,
    question: 'Will the API detail surface stay stable?',
    outcomes: ['Yes', 'No'],
    active: true,
    closed: false,
    accepting_orders: true,
    restricted: false,
    liquidity_usd: 120_000,
    volume_usd: 900_000,
    volume_24h_usd: 55_000,
    best_bid: 0.49,
    best_ask: 0.51,
    last_trade_price: 0.5,
    tick_size: 0.01,
    min_order_size: 5,
    is_binary_yes_no: true,
    source_urls: ['https://example.com/api-detail-surface'],
  })
}

describe('prediction markets API run surfaces', () => {
  it('keeps listPredictionMarketRuns additive with artifact_audit and existing summary fields', () => {
    const runId = 'run-api-001'
    const marketDescriptor = makeArtifactRef({
      runId,
      artifactType: 'market_descriptor',
      sha256: 'sha-market-descriptor',
    })
    const forecastPacket = makeArtifactRef({
      runId,
      artifactType: 'forecast_packet',
      sha256: 'sha-forecast-packet',
    })
    const executionProjectionRef = makeArtifactRef({
      runId,
      artifactType: 'execution_projection',
      sha256: 'sha-execution-projection',
    })
    const runManifestRef = makeArtifactRef({
      runId,
      artifactType: 'run_manifest',
      sha256: 'sha-run-manifest',
    })
    const runManifest = makeRunManifest({
      runId,
      artifactRefs: [marketDescriptor, forecastPacket, executionProjectionRef, runManifestRef],
    })

    storeMocks.listPredictionMarketRuns.mockReturnValueOnce([
      {
        run_id: runId,
        source_run_id: null,
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: 'mkt-api-001',
        market_slug: 'mkt-api-001',
        status: 'completed',
        recommendation: 'wait',
        side: null,
        confidence: 0.62,
        probability_yes: 0.53,
        market_price_yes: 0.49,
        edge_bps: 400,
        research_pipeline_id: 'polymarket-research-pipeline',
        research_pipeline_version: 'poly-025-research-v1',
        research_forecaster_count: 3,
        research_weighted_probability_yes: 0.67,
        research_weighted_coverage: 0.82,
        research_compare_preferred_mode: 'aggregate',
        research_compare_summary: 'Preferred mode: aggregate. Base rate and manual notes are aligned.',
        research_abstention_policy_version: 'structured-abstention-v1',
        research_abstention_policy_blocks_forecast: false,
        research_forecast_probability_yes_hint: 0.65,
        created_at: 1712534400,
        updated_at: 1712534460,
        manifest: runManifest,
        artifact_refs: [marketDescriptor, forecastPacket, executionProjectionRef, runManifestRef],
      },
    ])
    storeMocks.getPredictionMarketRunDetails.mockReturnValueOnce({
      benchmark_gate_summary: 'benchmark gate: list-summary canonical propagation',
      benchmark_uplift_bps: 280,
      benchmark_verdict: 'local_benchmark_ready',
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'eligible',
      benchmark_promotion_ready: true,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'local_benchmark',
      benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_promotion_blocker_summary: 'promotion gate satisfied',
      benchmark_promotion_summary: 'promotion gate satisfied',
      benchmark_gate_blocks_live: false,
      benchmark_gate_live_block_reason: null,
      benchmark_gate_blockers: [],
      benchmark_gate_reasons: ['promotion gate satisfied'],
      artifacts: [
        {
          artifact_type: 'execution_projection',
          payload: makeExecutionProjectionArtifact({
            runId,
            requestedPath: 'live',
            selectedPath: 'shadow',
            shadowRecommendedSizeUsd: 75,
          }),
        },
      ],
    })

    const runs = listPredictionMarketRuns({ workspaceId: 1, venue: 'polymarket', limit: 20 })

    expect(runs).toHaveLength(1)
    expect(runs[0]).toMatchObject({
      run_id: runId,
      workspace_id: 1,
      venue: 'polymarket',
      mode: 'advise',
      market_id: 'mkt-api-001',
      market_slug: 'mkt-api-001',
      status: 'completed',
      recommendation: 'wait',
      confidence: 0.62,
      probability_yes: 0.53,
      market_price_yes: 0.49,
      edge_bps: 400,
      research_pipeline_id: 'polymarket-research-pipeline',
      research_pipeline_version: 'poly-025-research-v1',
      research_forecaster_count: 3,
      research_weighted_probability_yes: 0.67,
      research_weighted_coverage: 0.82,
      research_compare_preferred_mode: 'aggregate',
      research_compare_summary: 'Preferred mode: aggregate. Base rate and manual notes are aligned.',
      research_abstention_policy_version: 'structured-abstention-v1',
      research_abstention_policy_blocks_forecast: false,
      research_forecast_probability_yes_hint: 0.65,
      benchmark_gate_summary: 'benchmark gate: list-summary canonical propagation',
      benchmark_uplift_bps: 280,
      benchmark_verdict: 'local_benchmark_ready',
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'eligible',
      benchmark_promotion_ready: true,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'local_benchmark',
      benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_promotion_blocker_summary: 'promotion gate satisfied',
      benchmark_promotion_summary: 'promotion gate satisfied',
      benchmark_gate_blocks_live: false,
      benchmark_gate_live_block_reason: null,
    })
    expect(runs[0]?.artifact_audit).toEqual({
      manifest_ref_count: 4,
      observed_ref_count: 4,
      canonical_ref_count: 4,
      run_manifest_present: true,
      duplicate_artifact_ids: [],
      manifest_only_artifact_ids: [],
      observed_only_artifact_ids: [],
    })
    expect(runs[0]).toMatchObject({
      execution_pathways_highest_actionable_mode: 'shadow',
      execution_projection_selected_path: 'shadow',
      execution_projection_selected_path_status: 'ready',
      execution_projection_verdict: 'downgraded',
      execution_projection_capital_status: 'attached',
      execution_projection_reconciliation_status: 'unavailable',
      execution_projection_selected_edge_bucket: 'arbitrage_alpha',
      execution_projection_selected_pre_trade_gate: expect.objectContaining({
        gate_name: 'hard_no_trade',
        verdict: 'pass',
        edge_bucket: 'arbitrage_alpha',
      }),
      execution_projection_selected_pre_trade_gate_verdict: 'pass',
      execution_projection_selected_pre_trade_gate_summary:
        'Hard no-trade gate pass. bucket=arbitrage_alpha gross=1240bps frictions=260bps net=980bps minimum=240bps',
      execution_projection_selected_path_net_edge_bps: 980,
      execution_projection_selected_path_minimum_net_edge_bps: 240,
      execution_projection_selected_preview: expect.objectContaining({
        size_usd: 75,
      }),
      execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
      execution_projection_selected_path_canonical_size_usd: 75,
      execution_projection_selected_path_shadow_signal_present: true,
      research_pipeline_id: 'polymarket-research-pipeline',
      research_pipeline_version: 'poly-025-research-v1',
      research_forecaster_count: 3,
      research_weighted_probability_yes: 0.67,
      research_weighted_coverage: 0.82,
      research_compare_preferred_mode: 'aggregate',
      research_compare_summary: 'Preferred mode: aggregate. Base rate and manual notes are aligned.',
      research_abstention_policy_version: 'structured-abstention-v1',
      research_abstention_policy_blocks_forecast: false,
      research_forecast_probability_yes_hint: 0.65,
      shadow_arbitrage_present: true,
      shadow_arbitrage_recommended_size_usd: 75,
      shadow_arbitrage: {
        summary: {
          recommended_size_usd: 75,
          shadow_edge_bps: 98,
        },
      },
    })
  })

  it('keeps listPredictionMarketRuns benchmark blockers and live gate fallback canonical when detail aliases conflict', () => {
    const runId = 'run-api-benchmark-fallback-001'
    const marketDescriptor = makeArtifactRef({
      runId,
      artifactType: 'market_descriptor',
      sha256: 'sha-market-descriptor',
    })
    const executionProjectionRef = makeArtifactRef({
      runId,
      artifactType: 'execution_projection',
      sha256: 'sha-execution-projection',
    })
    const runManifestRef = makeArtifactRef({
      runId,
      artifactType: 'run_manifest',
      sha256: 'sha-run-manifest',
    })
    const runManifest = makeRunManifest({
      runId,
      artifactRefs: [marketDescriptor, executionProjectionRef, runManifestRef],
    })

    storeMocks.listPredictionMarketRuns.mockReturnValueOnce([
      {
        run_id: runId,
        source_run_id: null,
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: 'mkt-api-benchmark-fallback-001',
        market_slug: 'mkt-api-benchmark-fallback-001',
        status: 'completed',
        recommendation: 'bet',
        side: 'yes',
        confidence: 0.71,
        probability_yes: 0.62,
        market_price_yes: 0.51,
        edge_bps: 1100,
        benchmark_gate_summary: 'benchmark gate: canonical blocked propagation',
        benchmark_uplift_bps: 280,
        benchmark_verdict: 'preview_only',
        benchmark_gate_status: 'preview_only',
        benchmark_promotion_status: 'unproven',
        benchmark_promotion_ready: false,
        benchmark_preview_available: true,
        benchmark_promotion_evidence: 'unproven',
        benchmark_evidence_level: 'benchmark_preview',
        benchmark_promotion_gate_kind: 'preview_only',
        benchmark_promotion_summary: 'benchmark-only list summary blocker should win',
        benchmark_gate_blockers: ['out_of_sample_unproven'],
        benchmark_gate_reasons: ['out_of_sample_unproven'],
        created_at: 1712534400,
        updated_at: 1712534460,
        manifest: runManifest,
        artifact_refs: [marketDescriptor, executionProjectionRef, runManifestRef],
      },
    ])
    storeMocks.getPredictionMarketRunDetails.mockReturnValueOnce({
      research_benchmark_gate_summary: 'research benchmark gate: blocked',
      research_benchmark_promotion_ready: false,
      research_benchmark_promotion_blocker_summary: 'research list blocker should not win',
      research_benchmark_promotion_summary: 'research list blocker should not win',
      research_benchmark_gate_blockers: ['research_alias_blocker'],
      research_benchmark_gate_reasons: ['research_alias_blocker'],
      research_benchmark_live_block_reason: 'research live blocker should not win',
      artifacts: [
        {
          artifact_type: 'execution_projection',
          payload: makeExecutionProjectionArtifact({
            runId,
            requestedPath: 'live',
            selectedPath: 'live',
            shadowRecommendedSizeUsd: 75,
          }),
        },
      ],
    })

    const runs = listPredictionMarketRuns({ workspaceId: 1, venue: 'polymarket', limit: 20 })

    expect(runs).toHaveLength(1)
    expect(runs[0]).toMatchObject({
      run_id: runId,
      benchmark_gate_summary: 'benchmark gate: canonical blocked propagation',
      benchmark_promotion_ready: false,
      benchmark_promotion_blocker_summary: 'benchmark-only list summary blocker should win',
      benchmark_promotion_summary: 'benchmark-only list summary blocker should win',
      benchmark_gate_blockers: ['out_of_sample_unproven'],
      benchmark_gate_reasons: ['out_of_sample_unproven'],
      benchmark_gate_blocks_live: true,
      benchmark_gate_live_block_reason: 'benchmark-only list summary blocker should win',
      research_benchmark_live_block_reason: 'benchmark-only list summary blocker should win',
    })
  })

  it('keeps getPredictionMarketRunDetails additive with artifact_readback, artifact_audit and existing detail fields', () => {
    const runId = 'run-api-002'
    const marketDescriptor = makeArtifactRef({
      runId,
      artifactType: 'market_descriptor',
      sha256: 'sha-market-descriptor',
    })
    const forecastPacket = makeArtifactRef({
      runId,
      artifactType: 'forecast_packet',
      sha256: 'sha-forecast-packet',
    })
    const runManifestRef = makeArtifactRef({
      runId,
      artifactType: 'run_manifest',
      sha256: 'sha-run-manifest',
    })
    const marketSnapshotRef = makeArtifactRef({
      runId,
      artifactType: 'market_snapshot',
      sha256: 'sha-market-snapshot',
    })
    const resolutionPolicyRef = makeArtifactRef({
      runId,
      artifactType: 'resolution_policy',
      sha256: 'sha-resolution-policy',
    })
    const evidenceBundleRef = makeArtifactRef({
      runId,
      artifactType: 'evidence_bundle',
      sha256: 'sha-evidence-bundle',
    })
    const recommendationPacketRef = makeArtifactRef({
      runId,
      artifactType: 'recommendation_packet',
      sha256: 'sha-recommendation-packet',
    })
    const executionProjectionRef = makeArtifactRef({
      runId,
      artifactType: 'execution_projection',
      sha256: 'sha-execution-projection',
    })
    const shadowArbitrageRef = makeArtifactRef({
      runId,
      artifactType: 'shadow_arbitrage',
      sha256: 'sha-shadow-arbitrage',
    })
    const pipelineGuardRef = makeArtifactRef({
      runId,
      artifactType: 'pipeline_guard',
      sha256: 'sha-pipeline-guard',
    })
    const crossVenueIntelligenceRef = makeArtifactRef({
      runId,
      artifactType: 'cross_venue_intelligence',
      sha256: 'sha-cross-venue-intelligence',
    })
    const multiVenueExecutionRef = makeArtifactRef({
      runId,
      artifactType: 'multi_venue_execution',
      sha256: 'sha-multi-venue-execution',
    })
    const researchResolutionPolicy = resolutionPolicySchema.parse({
      market_id: 'mkt-api-003',
      venue: 'polymarket',
      status: 'eligible',
      manual_review_required: false,
      reasons: [],
      primary_sources: ['https://example.com/run-api-003'],
      evaluated_at: '2026-04-08T00:00:00.000Z',
    })
    const runManifest = makeRunManifest({
      runId,
      artifactRefs: [
        marketDescriptor,
        marketSnapshotRef,
        resolutionPolicyRef,
        evidenceBundleRef,
        forecastPacket,
        recommendationPacketRef,
        executionProjectionRef,
        shadowArbitrageRef,
        runManifestRef,
        pipelineGuardRef,
      ],
    })
    const resolutionPolicy = resolutionPolicySchema.parse({
      market_id: 'mkt-api-002',
      venue: 'polymarket',
      status: 'eligible',
      manual_review_required: false,
      reasons: [],
      primary_sources: ['https://example.com/run-api-002'],
      evaluated_at: '2026-04-08T00:00:00.000Z',
    })
    const evidenceBundle = [
      evidencePacketSchema.parse({
        evidence_id: `${runId}:manual-thesis`,
        market_id: 'mkt-api-002',
        venue: 'polymarket',
        type: 'manual_thesis',
        title: 'Manual thesis override',
        summary: 'Replay-ready thesis override.',
        captured_at: '2026-04-08T00:00:00.000Z',
        content_hash: 'sha-evidence-manual-thesis',
        metadata: {
          thesis_probability: 0.71,
          thesis_rationale: 'Replay-ready thesis override.',
        },
      }),
    ]
    const forecastPacketPayload = forecastPacketSchema.parse({
      market_id: 'mkt-api-002',
      venue: 'polymarket',
      basis: 'manual_thesis',
      probability_yes: 0.71,
      confidence: 0.64,
      rationale: 'Stored forecast',
      evidence_refs: evidenceBundle.map((packet) => packet.evidence_id),
      produced_at: '2026-04-08T00:00:00.000Z',
    })
    const recommendationPacket = marketRecommendationPacketSchema.parse({
      market_id: 'mkt-api-002',
      venue: 'polymarket',
      action: 'bet',
      side: 'yes',
      confidence: 0.64,
      fair_value_yes: 0.71,
      market_price_yes: 0.5,
      market_bid_yes: 0.49,
      market_ask_yes: 0.51,
      edge_bps: 2100,
      spread_bps: 200,
      reasons: ['Stored recommendation'],
      risk_flags: [],
      produced_at: '2026-04-08T00:00:00.000Z',
    })
    const executionProjectionArtifact = makeExecutionProjectionArtifact({
      runId,
      requestedPath: 'live',
      selectedPath: 'shadow',
      shadowRecommendedSizeUsd: 60,
      shadowPreviewSizeUsd: 100,
    })
    const shadowArbitrageArtifact = makeShadowArbitrageArtifact(75)
    const marketDescriptorPayload = makeMarketDescriptor(runId)
    const marketSnapshotPayload = marketSnapshotSchema.parse({
      venue: 'polymarket',
      market: marketDescriptorPayload,
      captured_at: '2026-04-08T00:00:00.000Z',
      yes_outcome_index: 0,
      yes_token_id: `${marketDescriptorPayload.market_id}:yes`,
      yes_price: 0.5,
      no_price: 0.5,
      midpoint_yes: 0.5,
      best_bid_yes: 0.49,
      best_ask_yes: 0.51,
      spread_bps: 200,
      book: {
        token_id: `${marketDescriptorPayload.market_id}:yes`,
        market_condition_id: `${marketDescriptorPayload.market_id}:cond`,
        fetched_at: '2026-04-08T00:00:00.000Z',
        best_bid: 0.49,
        best_ask: 0.51,
        last_trade_price: 0.5,
        tick_size: 0.01,
        min_order_size: 5,
        bids: [{ price: 0.49, size: 400 }],
        asks: [{ price: 0.51, size: 400 }],
        depth_near_touch: 800,
      },
      history: [
        { timestamp: 1712534400, price: 0.48 },
        { timestamp: 1712538000, price: 0.5 },
      ],
      source_urls: ['https://example.com/api-detail-surface/book'],
    })

    storeMocks.getPredictionMarketRunDetails.mockReturnValueOnce({
      run_id: runId,
      source_run_id: null,
      workspace_id: 1,
      venue: 'polymarket',
      mode: 'advise',
      market_id: 'mkt-api-002',
      market_slug: 'mkt-api-002',
      status: 'completed',
      recommendation: 'bet',
      side: 'yes',
      confidence: 0.78,
      probability_yes: 0.72,
      market_price_yes: 0.49,
      edge_bps: 2300,
      research_pipeline_id: 'polymarket-research-pipeline',
      research_pipeline_version: 'poly-025-research-v1',
      research_forecaster_count: 3,
      research_weighted_probability_yes: 0.72,
      research_weighted_coverage: 0.9,
      research_compare_preferred_mode: 'aggregate',
      research_compare_summary: 'Preferred mode: aggregate. Base rate and manual notes are aligned.',
      research_abstention_policy_version: 'structured-abstention-v1',
      research_abstention_policy_blocks_forecast: false,
      research_forecast_probability_yes_hint: 0.72,
      created_at: 1712534400,
      updated_at: 1712534460,
      manifest: runManifest,
      artifact_refs: [
        marketDescriptor,
        marketSnapshotRef,
        resolutionPolicyRef,
        evidenceBundleRef,
        forecastPacket,
        recommendationPacketRef,
        executionProjectionRef,
        shadowArbitrageRef,
        runManifestRef,
        pipelineGuardRef,
      ],
      artifacts: [
        {
          artifact_id: `${runId}:forecast_packet`,
          artifact_type: 'forecast_packet',
          sha256: 'sha-forecast-packet',
          payload: forecastPacketPayload,
        },
        {
          artifact_id: `${runId}:market_descriptor`,
          artifact_type: 'market_descriptor',
          sha256: 'sha-market-descriptor',
          payload: marketDescriptorPayload,
        },
        {
          artifact_id: `${runId}:market_snapshot`,
          artifact_type: 'market_snapshot',
          sha256: 'sha-market-snapshot',
          payload: marketSnapshotPayload,
        },
        {
          artifact_id: `${runId}:resolution_policy`,
          artifact_type: 'resolution_policy',
          sha256: 'sha-resolution-policy',
          payload: researchResolutionPolicy,
        },
        {
          artifact_id: `${runId}:evidence_bundle`,
          artifact_type: 'evidence_bundle',
          sha256: 'sha-evidence-bundle',
          payload: evidenceBundle,
        },
        {
          artifact_id: `${runId}:recommendation_packet`,
          artifact_type: 'recommendation_packet',
          sha256: 'sha-recommendation-packet',
          payload: recommendationPacket,
        },
        {
          artifact_id: `${runId}:execution_projection`,
          artifact_type: 'execution_projection',
          sha256: 'sha-execution-projection',
          payload: executionProjectionArtifact,
        },
        {
          artifact_id: `${runId}:shadow_arbitrage`,
          artifact_type: 'shadow_arbitrage',
          sha256: 'sha-shadow-arbitrage',
          payload: shadowArbitrageArtifact,
        },
        {
          artifact_id: `${runId}:run_manifest`,
          artifact_type: 'run_manifest',
          sha256: 'sha-run-manifest',
          payload: runManifest,
        },
        {
          artifact_id: `${runId}:pipeline_guard`,
          artifact_type: 'pipeline_guard',
          sha256: 'sha-pipeline-guard',
          payload: {
            mode: 'advise',
            venue: 'polymarket',
            status: 'normal',
            reasons: [],
            breached_budgets: [],
            metrics: {
              fetch_latency_ms: 100,
              decision_latency_ms: 50,
              snapshot_staleness_ms: 1000,
            },
            venue_capabilities: {
              schema_version: '1.0.0',
              venue: 'polymarket',
              venue_type: 'execution-equivalent',
              supports_discovery: true,
              supports_metadata: true,
              supports_orderbook: true,
              supports_trades: true,
              supports_positions: true,
              supports_execution: true,
              supports_websocket: true,
              supports_paper_mode: true,
              automation_constraints: [],
              last_verified_at: '2026-04-08T00:00:00.000Z',
            },
            venue_health: {
              schema_version: '1.0.0',
              venue: 'polymarket',
              captured_at: '2026-04-08T00:00:00.000Z',
              health_score: 1,
              api_status: 'healthy',
              stream_status: 'healthy',
              staleness_ms: 0,
              degraded_mode: 'normal',
              incident_flags: [],
            },
            budgets: {
              venue: 'polymarket',
              fetch_latency_budget_ms: 4_000,
              snapshot_freshness_budget_ms: 4_000,
              decision_latency_budget_ms: 2_000,
              stream_reconnect_budget_ms: 4_000,
              cache_ttl_ms: 1_000,
              max_retries: 0,
              backpressure_policy: 'degrade-to-wait',
            },
          },
        },
        {
          artifact_id: `${runId}:paper_surface`,
          artifact_type: 'paper_surface',
          sha256: 'sha-paper-surface',
          payload: {
            schema_version: '1.0.0',
            no_trade_zone_count: 1,
            no_trade_zone_rate: 0.333333,
            fill_rate: 0.75,
            partial_fill_rate: 0.25,
            order_trace_audit: {
              schema_version: '1.0.0',
              trace_id: `${runId}:paper-trace`,
              venue_order_status: 'acknowledged',
              venue_order_flow: 'place->ack',
              transport_mode: 'local_cache',
              venue_order_trace_kind: 'paper_surface',
              place_auditable: true,
              cancel_auditable: true,
              live_execution_status: 'inactive',
              market_execution_status: 'paper',
              metadata: {
                source: 'fixture',
              },
            },
          },
        },
        {
          artifact_id: `${runId}:replay_surface`,
          artifact_type: 'replay_surface',
          sha256: 'sha-replay-surface',
          payload: {
            schema_version: '1.0.0',
            no_trade_leg_count: 1,
            no_trade_leg_rate: 0.5,
            fill_rate: 0.66,
            partial_fill_rate: 0.5,
          },
        },
      ],
    })

    const details = getPredictionMarketRunDetails(runId, 1)

    expect(details).not.toBeNull()
    expect(details).toMatchObject({
      run_id: runId,
      workspace_id: 1,
      venue: 'polymarket',
      mode: 'advise',
      market_id: 'mkt-api-002',
      market_slug: 'mkt-api-002',
      status: 'completed',
      recommendation: 'bet',
      side: 'yes',
      confidence: 0.78,
      probability_yes: 0.72,
      market_price_yes: 0.49,
      edge_bps: 2300,
      research_pipeline_id: 'polymarket-research-pipeline',
      research_pipeline_version: 'poly-025-research-v1',
      research_forecaster_count: 3,
      research_weighted_probability_yes: 0.72,
      research_weighted_coverage: 0.9,
      research_compare_preferred_mode: 'aggregate',
      research_compare_summary: 'Preferred mode: aggregate. Base rate and manual notes are aligned.',
      research_abstention_policy_version: 'structured-abstention-v1',
      research_abstention_policy_blocks_forecast: false,
      research_forecast_probability_yes_hint: 0.72,
      manifest: runManifest,
      artifact_refs: [
        marketDescriptor,
        marketSnapshotRef,
        resolutionPolicyRef,
        evidenceBundleRef,
        forecastPacket,
        recommendationPacketRef,
        executionProjectionRef,
        shadowArbitrageRef,
        runManifestRef,
        pipelineGuardRef,
      ],
    })
    expect(details?.artifact_readback).toBeDefined()
    expect(details?.artifact_readback?.run_manifest_ref?.artifact_id).toBe(`${runId}:run_manifest`)
    expect(details?.artifact_readback?.canonical_artifact_refs.map((ref) => ref.artifact_id)).toEqual([
      `${runId}:market_descriptor`,
      `${runId}:market_snapshot`,
      `${runId}:resolution_policy`,
      `${runId}:evidence_bundle`,
      `${runId}:forecast_packet`,
      `${runId}:recommendation_packet`,
      `${runId}:execution_projection`,
      `${runId}:shadow_arbitrage`,
      `${runId}:run_manifest`,
      `${runId}:pipeline_guard`,
      `${runId}:paper_surface`,
      `${runId}:replay_surface`,
    ])
    expect(details?.artifact_audit).toEqual({
      manifest_ref_count: 10,
      observed_ref_count: 12,
      canonical_ref_count: 12,
      run_manifest_present: true,
      duplicate_artifact_ids: [],
      manifest_only_artifact_ids: [],
      observed_only_artifact_ids: [
        `${runId}:paper_surface`,
        `${runId}:replay_surface`,
      ],
    })
    expect(details?.paper_surface).toMatchObject({
      no_trade_zone_count: 1,
      no_trade_zone_rate: 0.333333,
    })
    expect(details?.order_trace_audit).toMatchObject({
      trace_id: `${runId}:paper-trace`,
      venue_order_status: 'acknowledged',
      venue_order_flow: 'place->ack',
      venue_order_trace_kind: 'paper_surface',
      place_auditable: true,
      cancel_auditable: true,
      live_execution_status: 'inactive',
      market_execution_status: 'paper',
    })
    expect(details?.replay_surface).toMatchObject({
      no_trade_leg_count: 1,
      no_trade_leg_rate: 0.5,
    })
    expect(details).toMatchObject({
      paper_no_trade_zone_count: 1,
      paper_no_trade_zone_rate: 0.333333,
      replay_no_trade_leg_count: 1,
      replay_no_trade_leg_rate: 0.5,
    })
    expect(details?.venue_coverage).toMatchObject({
      venue_count: 2,
      degraded_venue_count: 2,
      degraded_venue_rate: 1,
      execution_equivalent_count: 2,
      execution_like_count: 0,
      execution_surface_rate: 0,
    })
    expect(details?.shadow_arbitrage).toMatchObject({
      read_only: true,
      summary: {
        recommended_size_usd: 60,
      },
      sizing: {
        recommended_size_usd: 60,
      },
    })
    expect(details?.execution_readiness).toBeDefined()
    expect(details?.execution_pathways).toBeDefined()
    expect(details?.execution_projection).toBeDefined()
    expect(details?.execution_pathways?.highest_actionable_mode).toBeDefined()
    expect(details?.execution_projection?.requested_path).toBe('live')
    expect(details?.execution_projection).toMatchObject({
      selected_edge_bucket: 'arbitrage_alpha',
      selected_pre_trade_gate: expect.objectContaining({
        gate_name: 'hard_no_trade',
        verdict: 'pass',
        edge_bucket: 'arbitrage_alpha',
      }),
      preflight_summary: expect.objectContaining({
        selected_edge_bucket: 'arbitrage_alpha',
        selected_pre_trade_gate: expect.objectContaining({
          gate_name: 'hard_no_trade',
          verdict: 'pass',
          edge_bucket: 'arbitrage_alpha',
        }),
      }),
    })
    expect(details?.execution_projection?.projected_paths.shadow.trade_intent_preview?.size_usd).toBe(100)
    expect(details?.execution_projection?.projected_paths.shadow.canonical_trade_intent_preview?.size_usd).toBe(60)
    expect(details).toMatchObject({
      execution_pathways_highest_actionable_mode: 'paper',
      execution_projection_gate_name: 'execution_projection',
      execution_projection_preflight_only: true,
      execution_projection_requested_path: 'live',
      execution_projection_selected_path: 'shadow',
      execution_projection_selected_path_status: 'ready',
      execution_projection_selected_path_effective_mode: 'shadow',
      execution_projection_selected_path_reason_summary: expect.any(String),
      execution_projection_verdict: 'downgraded',
      execution_projection_highest_safe_requested_mode: 'shadow',
      execution_projection_recommended_effective_mode: 'shadow',
      execution_projection_manual_review_required:
        details?.execution_projection?.manual_review_required ?? false,
      execution_projection_ttl_ms: 30000,
      execution_projection_expires_at: expect.any(String),
      execution_projection_blocking_reasons: [],
      execution_projection_downgrade_reasons: expect.any(Array),
      execution_projection_summary: details?.execution_projection?.summary ?? null,
      execution_projection_preflight_summary: expect.objectContaining({
        gate_name: 'execution_projection',
        requested_path: 'live',
        selected_path: 'shadow',
      }),
      execution_projection_capital_status: 'attached',
      execution_projection_reconciliation_status: 'unavailable',
      execution_projection_selected_preview: expect.objectContaining({
        size_usd: 60,
      }),
      execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
      execution_projection_selected_edge_bucket: 'arbitrage_alpha',
      execution_projection_selected_pre_trade_gate: expect.objectContaining({
        gate_name: 'hard_no_trade',
        verdict: 'pass',
        edge_bucket: 'arbitrage_alpha',
      }),
      execution_projection_selected_pre_trade_gate_verdict: 'pass',
      execution_projection_selected_pre_trade_gate_summary:
        'Hard no-trade gate pass. bucket=arbitrage_alpha gross=1240bps frictions=260bps net=980bps minimum=240bps',
      execution_projection_selected_path_net_edge_bps: 980,
      execution_projection_selected_path_minimum_net_edge_bps: 240,
      execution_projection_selected_path_canonical_size_usd: 60,
      execution_projection_selected_path_shadow_signal_present: true,
    })
    expect(details?.trade_intent_guard).toMatchObject({
      gate_name: 'trade_intent_guard',
      summary: expect.any(String),
      trade_intent_preview: expect.objectContaining({
        size_usd: 60,
      }),
      metadata: expect.objectContaining({
        trade_intent_preview_source: 'canonical_trade_intent_preview',
        trade_intent_preview_via: 'execution_projection_selected_preview',
        trade_intent_preview_uses_projection_selected_preview: true,
        execution_projection_selected_preview_available: true,
        execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
        trade_intent_preview_capped_to_canonical_size: false,
        selected_projection_path_status: 'ready',
        selected_projection_sizing_signal_present: true,
        selected_projection_shadow_arbitrage_signal_present: true,
        selected_projection_canonical_size_usd: 60,
      }),
    })
    expect(details?.trade_intent_guard?.trade_intent_preview?.notes).toContain(
      'Canonical execution sizing caps preview size to 60 USD.',
    )
    expectFutureTopLevelTradeIntentPreviewAlignment(
      details as FutureTopLevelTradeIntentPreviewSurface,
    )
    expect(details?.multi_venue_execution).toMatchObject({
      gate_name: 'multi_venue_execution',
      summary: expect.any(String),
      metadata: expect.objectContaining({
        execution_projection_selected_path: 'shadow',
        execution_projection_selected_path_status: 'ready',
        execution_projection_selected_path_shadow_signal_present: true,
        execution_projection_selected_path_canonical_size_usd: 60,
        execution_projection_selected_preview_available: true,
        execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
        execution_projection_selected_preview_size_usd: 60,
        execution_surface_preview_via: 'execution_projection_selected_preview',
        execution_surface_preview_source: 'canonical_trade_intent_preview',
        execution_surface_preview_size_usd: 60,
        execution_surface_preview_uses_projection_selected_preview: true,
      }),
    })
  })

  it('surfaces annotated research sidecars with external references and deltas', () => {
    const runId = 'run-api-003'
    const marketDescriptor = makeArtifactRef({
      runId,
      artifactType: 'market_descriptor',
      sha256: 'sha-market-descriptor',
    })
    const forecastPacket = makeArtifactRef({
      runId,
      artifactType: 'forecast_packet',
      sha256: 'sha-forecast-packet',
    })
    const runManifestRef = makeArtifactRef({
      runId,
      artifactType: 'run_manifest',
      sha256: 'sha-run-manifest',
    })
    const marketSnapshotRef = makeArtifactRef({
      runId,
      artifactType: 'market_snapshot',
      sha256: 'sha-market-snapshot',
    })
    const resolutionPolicyRef = makeArtifactRef({
      runId,
      artifactType: 'resolution_policy',
      sha256: 'sha-resolution-policy',
    })
    const evidenceBundleRef = makeArtifactRef({
      runId,
      artifactType: 'evidence_bundle',
      sha256: 'sha-evidence-bundle',
    })
    const recommendationPacketRef = makeArtifactRef({
      runId,
      artifactType: 'recommendation_packet',
      sha256: 'sha-recommendation-packet',
    })
    const pipelineGuardRef = makeArtifactRef({
      runId,
      artifactType: 'pipeline_guard',
      sha256: 'sha-pipeline-guard',
    })
    const crossVenueIntelligenceRef = makeArtifactRef({
      runId,
      artifactType: 'cross_venue_intelligence',
      sha256: 'sha-cross-venue-intelligence',
    })
    const multiVenueExecutionRef = makeArtifactRef({
      runId,
      artifactType: 'multi_venue_execution',
      sha256: 'sha-multi-venue-execution',
    })
    const researchResolutionPolicy = resolutionPolicySchema.parse({
      market_id: 'mkt-api-003',
      venue: 'polymarket',
      status: 'eligible',
      manual_review_required: false,
      reasons: [],
      primary_sources: ['https://example.com/run-api-003'],
      evaluated_at: '2026-04-08T00:00:00.000Z',
    })
    const runManifest = makeRunManifest({
      runId,
      artifactRefs: [
        marketDescriptor,
        marketSnapshotRef,
        resolutionPolicyRef,
        evidenceBundleRef,
        forecastPacket,
        recommendationPacketRef,
        runManifestRef,
        pipelineGuardRef,
        crossVenueIntelligenceRef,
        multiVenueExecutionRef,
      ],
    })
    const marketDescriptorPayload = makeMarketDescriptor(runId)
    const marketSnapshotPayload = marketSnapshotSchema.parse({
      venue: 'polymarket',
      market: marketDescriptorPayload,
      captured_at: '2026-04-08T00:00:00.000Z',
      yes_outcome_index: 0,
      yes_token_id: `${marketDescriptorPayload.market_id}:yes`,
      yes_price: 0.52,
      no_price: 0.48,
      midpoint_yes: 0.52,
      best_bid_yes: 0.51,
      best_ask_yes: 0.53,
      spread_bps: 200,
      book: {
        token_id: `${marketDescriptorPayload.market_id}:yes`,
        market_condition_id: `${marketDescriptorPayload.market_id}:cond`,
        fetched_at: '2026-04-08T00:00:00.000Z',
        best_bid: 0.51,
        best_ask: 0.53,
        last_trade_price: 0.52,
        tick_size: 0.01,
        min_order_size: 5,
        bids: [{ price: 0.51, size: 400 }],
        asks: [{ price: 0.53, size: 400 }],
        depth_near_touch: 800,
      },
      history: [
        { timestamp: 1712534400, price: 0.5 },
      ],
      source_urls: ['https://example.com/api-detail-surface/book'],
    })
    const crossVenueIntelligencePayload = {
      evaluations: [
        {
          canonical_event_id: 'cve:api-003:surface',
          canonical_event_key: '2026-04-08:api-detail-surface',
          confidence_score: 0.87,
          compatible: false,
          mismatch_reasons: ['manual_review_required', 'execution_like_venue'],
          match: {
            schema_version: '1.0.0',
            canonical_event_id: 'cve:api-003:surface',
            left_market_ref: {
              venue: 'polymarket',
              market_id: marketDescriptorPayload.market_id,
              venue_type: 'execution-equivalent',
              slug: marketDescriptorPayload.slug,
              question: marketDescriptorPayload.question,
              side: 'yes',
            },
            right_market_ref: {
              venue: 'kalshi',
              market_id: `${runId}-peer`,
              venue_type: 'execution-like',
              slug: `${runId}-peer`,
              question: marketDescriptorPayload.question,
              side: 'yes',
            },
            semantic_similarity_score: 0.91,
            resolution_compatibility_score: 1,
            payout_compatibility_score: 1,
            currency_compatibility_score: 1,
            manual_review_required: true,
            notes: ['manual_review_required', 'execution_like_venue'],
          },
          market_equivalence_proof: {
            proof_id: 'mep:cve:api-003:surface',
            canonical_event_id: 'cve:api-003:surface',
            left_market_ref: {
              venue: 'polymarket',
              market_id: marketDescriptorPayload.market_id,
              venue_type: 'execution-equivalent',
              slug: marketDescriptorPayload.slug,
              question: marketDescriptorPayload.question,
              side: 'yes',
            },
            right_market_ref: {
              venue: 'kalshi',
              market_id: `${runId}-peer`,
              venue_type: 'execution-like',
              slug: `${runId}-peer`,
              question: marketDescriptorPayload.question,
              side: 'yes',
            },
            proof_status: 'partial',
            resolution_compatibility_score: 1,
            payout_compatibility_score: 1,
            currency_compatibility_score: 1,
            timing_compatibility_score: 1,
            manual_review_required: true,
            mismatch_reasons: ['manual_review_required', 'execution_like_venue'],
            notes: ['canonical_event_key:2026-04-08:api-detail-surface'],
          },
          executable_edge: null,
          arbitrage_candidate: null,
          opportunity_type: 'cross_venue_signal',
        },
      ],
      arbitrage_candidates: [],
      errors: [],
      summary: {
        total_pairs: 1,
        opportunity_type_counts: {
          comparison_only: 0,
          relative_value: 0,
          cross_venue_signal: 1,
          true_arbitrage: 0,
        },
        compatible: [],
        manual_review: [],
        comparison_only: [],
        blocking_reasons: ['manual_review_required', 'execution_like_venue'],
        highest_confidence_candidate: null,
      },
    }
    const multiVenueExecutionPayload = {
      schema_version: '1.0.0',
      gate_name: 'multi_venue_execution',
      report_id: null,
      taxonomy: 'cross_venue_signal',
      execution_filter_reason_codes: ['manual_review_required', 'execution_like_venue'],
      execution_filter_reason_code_counts: {
        manual_review_required: 1,
        execution_like_venue: 1,
      },
      market_count: 2,
      comparable_group_count: 1,
      execution_candidate_count: 0,
      execution_plan_count: 1,
      tradeable_plan_count: 0,
      execution_routes: {
        comparison_only: 0,
        relative_value: 0,
        cross_venue_signal: 1,
        true_arbitrage: 0,
      },
      tradeable_market_ids: [],
      read_only_market_ids: [marketDescriptorPayload.market_id, `${runId}-peer`],
      reference_market_ids: [marketDescriptorPayload.market_id, `${runId}-peer`],
      signal_market_ids: [],
      execution_market_ids: [],
      summary: 'No tradeable cross-venue execution plans were derived; the surface remains comparison-only.',
      source_refs: {
        cross_venue_intelligence: `${runId}:cross_venue_intelligence`,
        execution_pathways: `${runId}:execution_pathways`,
        execution_projection: `${runId}:execution_projection`,
      },
      metadata: {
        run_id: runId,
        market_id: marketDescriptorPayload.market_id,
        venue: 'polymarket',
        cross_venue_report_present: true,
        execution_pathways_highest_actionable_mode: 'shadow',
        execution_projection_selected_path: 'shadow',
        execution_projection_selected_path_status: 'ready',
        execution_projection_selected_path_shadow_signal_present: true,
        execution_projection_selected_path_canonical_size_usd: 60,
        execution_projection_selected_preview_available: true,
        execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
        execution_projection_selected_preview_size_usd: 60,
        execution_surface_preview_via: 'execution_projection_selected_preview',
        execution_surface_preview_source: 'canonical_trade_intent_preview',
        execution_surface_preview_size_usd: 60,
        execution_surface_preview_uses_projection_selected_preview: true,
        execution_candidate_count: 0,
        tradeable_plan_count: 0,
        taxonomy: 'cross_venue_signal',
        execution_filter_reason_codes: ['manual_review_required', 'execution_like_venue'],
        execution_filter_reason_code_counts: {
          manual_review_required: 1,
          execution_like_venue: 1,
        },
      },
    }
    const forecastPacketPayload = forecastPacketSchema.parse({
      market_id: 'mkt-api-003',
      venue: 'polymarket',
      basis: 'manual_thesis',
      probability_yes: 0.72,
      confidence: 0.64,
      rationale: 'Stored forecast',
      evidence_refs: [`${runId}:manual-thesis`],
      produced_at: '2026-04-08T00:00:00.000Z',
    })
    const evidenceBundle = [
      evidencePacketSchema.parse({
        evidence_id: `${runId}:manual-thesis`,
        market_id: 'mkt-api-003',
        venue: 'polymarket',
        type: 'manual_thesis',
        title: 'Manual thesis override',
        summary: 'Replay-ready thesis override.',
        captured_at: '2026-04-08T00:00:00.000Z',
        content_hash: 'sha-evidence-manual-thesis',
        metadata: {
          thesis_probability: 0.72,
          thesis_rationale: 'Replay-ready thesis override.',
        },
      }),
    ]
    const recommendationPacket = marketRecommendationPacketSchema.parse({
      market_id: 'mkt-api-003',
      venue: 'polymarket',
      action: 'bet',
      side: 'yes',
      confidence: 0.64,
      fair_value_yes: 0.72,
      market_price_yes: 0.52,
      market_bid_yes: 0.51,
      market_ask_yes: 0.53,
      edge_bps: 2000,
      spread_bps: 200,
      reasons: ['Stored recommendation'],
      risk_flags: [],
      produced_at: '2026-04-08T00:00:00.000Z',
    })
    const researchSidecarPayload = {
      market_id: 'mkt-api-003',
      venue: 'polymarket',
      generated_at: '2026-04-08T00:00:00.000Z',
      signals: [
        {
          signal_id: 'sig-metaculus',
          kind: 'news',
          title: 'Metaculus consensus tightens',
          summary: 'Metaculus nudges upward.',
          source_name: 'Metaculus',
          source_url: 'https://www.metaculus.com/questions/forecast-123/',
          captured_at: '2026-04-08T00:00:00.000Z',
          tags: ['forecast'],
          stance: 'supportive',
          confidence: 0.7,
          severity: null,
          thesis_probability: undefined,
          thesis_rationale: undefined,
          payload: { probability_yes: 0.57 },
        },
        {
          signal_id: 'sig-manifold',
          kind: 'news',
          title: 'Manifold traders stay bullish',
          summary: 'Manifold stays constructive.',
          source_name: 'Manifold',
          source_url: 'https://manifold.markets/m/sample-market',
          captured_at: '2026-04-08T00:00:00.000Z',
          tags: ['forecast'],
          stance: 'supportive',
          confidence: 0.74,
          severity: null,
          thesis_probability: undefined,
          thesis_rationale: undefined,
          payload: { forecast_probability_yes: 0.63 },
        },
      ],
      evidence_packets: [
        {
          evidence_id: `${runId}:evidence:metaculus`,
          market_id: 'mkt-api-003',
          venue: 'polymarket',
          source_kind: 'news',
          claim: 'Metaculus consensus tightens',
          stance: 'supportive',
          summary: 'Metaculus nudges upward.',
          source_url: 'https://www.metaculus.com/questions/forecast-123/',
          raw_text: null,
          confidence: 0.7,
          freshness_score: 0.9,
          credibility_score: 0.8,
          provenance_refs: [],
          tags: ['forecast'],
          metadata: {
            source_name: 'Metaculus',
            payload: { probability_yes: 0.57 },
          },
          content_hash: 'sha-metaculus',
        },
        {
          evidence_id: `${runId}:evidence:manifold`,
          market_id: 'mkt-api-003',
          venue: 'polymarket',
          source_kind: 'news',
          claim: 'Manifold traders stay bullish',
          stance: 'supportive',
          summary: 'Manifold stays constructive.',
          source_url: 'https://manifold.markets/m/sample-market',
          raw_text: null,
          confidence: 0.74,
          freshness_score: 0.88,
          credibility_score: 0.79,
          provenance_refs: [],
          tags: ['forecast'],
          metadata: {
            source_name: 'Manifold',
            payload: { forecast_probability_yes: 0.63 },
          },
          content_hash: 'sha-manifold',
        },
      ],
      health: {
        status: 'healthy',
        completeness_score: 1,
        duplicate_signal_count: 0,
        issues: [],
        source_kinds: ['news'],
      },
      synthesis: {
        market_id: 'mkt-api-003',
        venue: 'polymarket',
        question: 'Will the API detail surface stay stable?',
        generated_at: '2026-04-08T00:00:00.000Z',
        signal_count: 2,
        evidence_count: 2,
        signal_kinds: ['news'],
        counts_by_kind: {
          worldmonitor: 0,
          news: 2,
          alert: 0,
          manual_note: 0,
        },
        counts_by_stance: {
          supportive: 2,
          contradictory: 0,
          neutral: 0,
          unknown: 0,
        },
        top_tags: ['forecast'],
        latest_signal_at: '2026-04-08T00:00:00.000Z',
        manual_thesis_probability_hint: undefined,
        manual_thesis_rationale_hint: undefined,
        base_rate_probability_hint: 0.5,
        base_rate_rationale_hint: 'Base rate anchored to 50% with 2 supportive and 0 contradictory signals.',
        base_rate_source: 'fallback_50',
        key_factors: ['Base rate anchor at 50% from fallback_50.'],
        counterarguments: [],
        no_trade_hints: [],
        abstention_recommended: false,
        summary: 'Research sidecar for "Will the API detail surface stay stable?"',
        key_points: ['Metaculus consensus tightens', 'Manifold traders stay bullish'],
        evidence_refs: [`${runId}:evidence:metaculus`, `${runId}:evidence:manifold`],
        external_reference_count: 2,
        external_references: [
          {
            reference_id: 'sig-metaculus',
            reference_source: 'metaculus',
            source_name: 'Metaculus',
            source_url: 'https://www.metaculus.com/questions/forecast-123/',
            source_kind: 'news',
            signal_id: 'sig-metaculus',
            captured_at: '2026-04-08T00:00:00.000Z',
            reference_probability_yes: 0.57,
            market_delta_bps: 500,
            forecast_delta_bps: -1500,
            summary: 'Metaculus nudges upward.',
          },
          {
            reference_id: 'sig-manifold',
            reference_source: 'manifold',
            source_name: 'Manifold',
            source_url: 'https://manifold.markets/m/sample-market',
            source_kind: 'news',
            signal_id: 'sig-manifold',
            captured_at: '2026-04-08T00:00:00.000Z',
            reference_probability_yes: 0.63,
            market_delta_bps: 1100,
            forecast_delta_bps: -900,
            summary: 'Manifold stays constructive.',
          },
        ],
        market_probability_yes_hint: 0.52,
        forecast_probability_yes_hint: null,
        market_delta_bps: 800,
        forecast_delta_bps: null,
      },
    }

    storeMocks.getPredictionMarketRunDetails.mockReturnValueOnce({
      run_id: runId,
      source_run_id: null,
      workspace_id: 1,
      venue: 'polymarket',
      mode: 'advise',
      market_id: 'mkt-api-003',
      market_slug: 'mkt-api-003',
      status: 'completed',
      recommendation: 'bet',
      side: 'yes',
      confidence: 0.78,
      probability_yes: 0.72,
      market_price_yes: 0.52,
      edge_bps: 2000,
      created_at: 1712534400,
      updated_at: 1712534460,
      manifest: runManifest,
      artifact_refs: [
        marketDescriptor,
        marketSnapshotRef,
        resolutionPolicyRef,
        evidenceBundleRef,
        forecastPacket,
        recommendationPacketRef,
        runManifestRef,
        pipelineGuardRef,
        crossVenueIntelligenceRef,
        multiVenueExecutionRef,
      ],
      artifacts: [
        {
          artifact_id: `${runId}:forecast_packet`,
          artifact_type: 'forecast_packet',
          sha256: 'sha-forecast-packet',
          payload: forecastPacketPayload,
        },
        {
          artifact_id: `${runId}:market_descriptor`,
          artifact_type: 'market_descriptor',
          sha256: 'sha-market-descriptor',
          payload: marketDescriptorPayload,
        },
        {
          artifact_id: `${runId}:market_snapshot`,
          artifact_type: 'market_snapshot',
          sha256: 'sha-market-snapshot',
          payload: marketSnapshotPayload,
        },
        {
          artifact_id: `${runId}:resolution_policy`,
          artifact_type: 'resolution_policy',
          sha256: 'sha-resolution-policy',
          payload: researchResolutionPolicy,
        },
        {
          artifact_id: `${runId}:evidence_bundle`,
          artifact_type: 'evidence_bundle',
          sha256: 'sha-evidence-bundle',
          payload: evidenceBundle,
        },
        {
          artifact_id: `${runId}:research_sidecar`,
          artifact_type: 'research_sidecar',
          sha256: 'sha-research-sidecar',
          payload: researchSidecarPayload,
        },
        {
          artifact_id: `${runId}:research_bridge`,
          artifact_type: 'research_bridge',
          sha256: 'sha-research-bridge',
          payload: {
            schema_version: '1.0.0',
            bundle_id: `${runId}:research_bridge`,
            packet_version: '1.0.0',
            compatibility_mode: 'social_bridge',
            market_only_compatible: true,
            sidecar_name: 'research_market_sync',
            sidecar_health: { healthy: true, source: 'research_market_sync' },
            classification: 'signal',
            classification_reasons: ['research_inputs'],
            market_id: 'mkt-api-003',
            venue: 'polymarket',
            run_id: runId,
            findings: [],
            synthesis: researchSidecarPayload.synthesis,
            pipeline: {
              schema_version: '1.0.0',
              market_id: 'mkt-api-003',
              venue: 'polymarket',
              run_id: runId,
              retrieval_policy: 'sidecar_findings',
              input_count: 2,
              evidence_count: 2,
              applied: true,
              evidence_refs: [`${runId}:evidence:metaculus`, `${runId}:evidence:manifold`],
              signal_count: 2,
              health: { healthy: true, completeness_score: 1 },
              abstention_policy: { abstain: false, rationale: 'not needed' },
              public_metrics: {},
              pipeline_summary: 'research bridge test',
            },
            abstention_policy: {
              schema_version: '1.0.0',
              abstain: false,
              reason: 'not needed',
            },
            signal_packets: [],
            artifact_refs: [`${runId}:evidence:metaculus`, `${runId}:evidence:manifold`],
            evidence_refs: [`${runId}:evidence:metaculus`, `${runId}:evidence:manifold`],
            provenance_refs: [`${runId}:evidence:metaculus`, `${runId}:evidence:manifold`],
            social_context_refs: [],
            provenance_bundle: {
              schema_version: '1.0.0',
              bundle_id: `${runId}:provenance_bundle`,
              run_id: runId,
              venue: 'polymarket',
              market_id: 'mkt-api-003',
              generated_at: '2026-04-08T00:00:00.000Z',
              freshness_score: 0.9,
              content_hash: 'sha-provenance-bundle',
              provenance_refs: [`${runId}:evidence:metaculus`, `${runId}:evidence:manifold`],
              evidence_refs: [`${runId}:evidence:metaculus`, `${runId}:evidence:manifold`],
              artifact_refs: [`${runId}:evidence:metaculus`, `${runId}:evidence:manifold`],
              links: [],
              summary: 'research provenance bundle test',
              metadata: { source: 'test' },
            },
            packet_refs: {},
            created_at: '2026-04-08T00:00:00.000Z',
            freshness_score: 0.9,
            content_hash: 'sha-research-bridge',
            metadata: { source: 'test' },
          },
        },
        {
          artifact_id: `${runId}:cross_venue_intelligence`,
          artifact_type: 'cross_venue_intelligence',
          sha256: 'sha-cross-venue-intelligence',
          payload: crossVenueIntelligencePayload,
        },
        {
          artifact_id: `${runId}:multi_venue_execution`,
          artifact_type: 'multi_venue_execution',
          sha256: 'sha-multi-venue-execution',
          payload: multiVenueExecutionPayload,
        },
        {
          artifact_id: `${runId}:recommendation_packet`,
          artifact_type: 'recommendation_packet',
          sha256: 'sha-recommendation-packet',
          payload: recommendationPacket,
        },
        {
          artifact_id: `${runId}:run_manifest`,
          artifact_type: 'run_manifest',
          sha256: 'sha-run-manifest',
          payload: runManifest,
        },
        {
          artifact_id: `${runId}:pipeline_guard`,
          artifact_type: 'pipeline_guard',
          sha256: 'sha-pipeline-guard',
          payload: {
            mode: 'advise',
            venue: 'polymarket',
            status: 'normal',
            reasons: [],
            breached_budgets: [],
            metrics: {
              fetch_latency_ms: 100,
              decision_latency_ms: 50,
              snapshot_staleness_ms: 1000,
            },
            venue_capabilities: {
              schema_version: '1.0.0',
              venue: 'polymarket',
              venue_type: 'execution-equivalent',
              supports_discovery: true,
              supports_metadata: true,
              supports_orderbook: true,
              supports_trades: true,
              supports_positions: true,
              supports_execution: true,
              supports_websocket: true,
              supports_paper_mode: true,
              automation_constraints: [],
              last_verified_at: '2026-04-08T00:00:00.000Z',
            },
            venue_health: {
              schema_version: '1.0.0',
              venue: 'polymarket',
              captured_at: '2026-04-08T00:00:00.000Z',
              health_score: 1,
              api_status: 'healthy',
              stream_status: 'healthy',
              staleness_ms: 0,
              degraded_mode: 'normal',
              incident_flags: [],
            },
            budgets: {
              venue: 'polymarket',
              fetch_latency_budget_ms: 4_000,
              snapshot_freshness_budget_ms: 4_000,
              decision_latency_budget_ms: 2_000,
              stream_reconnect_budget_ms: 4_000,
              cache_ttl_ms: 1_000,
              max_retries: 0,
              backpressure_policy: 'degrade-to-wait',
            },
          },
        },
      ],
    })

    const details = getPredictionMarketRunDetails(runId, 1)

    expect(details).not.toBeNull()
    expect(details?.research_sidecar).toBeDefined()
    expect(details?.research_sidecar?.synthesis.external_reference_count).toBe(2)
    expect(details?.research_sidecar?.synthesis.external_references.map((reference) => reference.reference_source)).toEqual(
      expect.arrayContaining(['metaculus', 'manifold']),
    )
    expect(details?.research_sidecar?.synthesis.market_probability_yes_hint).toBe(0.52)
    expect(details?.research_sidecar?.synthesis.forecast_probability_yes_hint).toBe(0.72)
    expect(details?.research_sidecar?.synthesis.market_delta_bps).toBe(800)
    expect(details?.research_sidecar?.synthesis.forecast_delta_bps).toBe(-1200)
    expect(details?.research_bridge?.bundle_id).toBe(`${runId}:research_bridge`)
    expect(details?.research_bridge?.provenance_bundle?.bundle_id).toBe(`${runId}:provenance_bundle`)
    expect(details?.venue_feed_surface).toMatchObject({
      backend_mode: 'read_only',
      ingestion_mode: 'read_only',
      supports_market_feed: true,
      supports_user_feed: true,
      tradeable: true,
      manual_review_required: true,
    })
    expect(details?.venue_coverage).toMatchObject({
      venue_count: 2,
      degraded_venue_count: 2,
      degraded_venue_rate: 1,
      execution_equivalent_count: 2,
      execution_like_count: 0,
      execution_surface_rate: 0,
    })
    expect(details?.multi_venue_execution).toMatchObject({
      gate_name: 'multi_venue_execution',
      taxonomy: 'cross_venue_signal',
      execution_filter_reason_codes: expect.arrayContaining(['manual_review_required', 'execution_like_venue']),
      execution_filter_reason_code_counts: {
        manual_review_required: 1,
        execution_like_venue: 1,
      },
    })
    expect(details?.market_graph).toMatchObject({
      schema_version: 'v1',
      nodes: expect.arrayContaining([
        expect.objectContaining({
          market_id: marketDescriptorPayload.market_id,
          role: 'reference',
        }),
      ]),
      edges: expect.arrayContaining([
        expect.objectContaining({
          relation: 'same_question',
        }),
      ]),
      comparable_groups: expect.arrayContaining([
        expect.objectContaining({
          canonical_event_id: 'cve:api-003:surface',
          relation_kind: 'same_question',
        }),
      ]),
      metadata: expect.objectContaining({
        taxonomy: 'cross_venue_signal',
        execution_filter_reason_codes: expect.arrayContaining(['manual_review_required', 'execution_like_venue']),
      }),
    })
  })

  it('caps trade_intent_guard preview size to the canonical selected-path size when shadow sizing is lower', () => {
    const runId = 'run-api-canonical-size'
    const marketDescriptor = makeArtifactRef({
      runId,
      artifactType: 'market_descriptor',
      sha256: 'sha-market-descriptor',
    })
    const marketSnapshotRef = makeArtifactRef({
      runId,
      artifactType: 'market_snapshot',
      sha256: 'sha-market-snapshot',
    })
    const resolutionPolicyRef = makeArtifactRef({
      runId,
      artifactType: 'resolution_policy',
      sha256: 'sha-resolution-policy',
    })
    const evidenceBundleRef = makeArtifactRef({
      runId,
      artifactType: 'evidence_bundle',
      sha256: 'sha-evidence-bundle',
    })
    const forecastPacket = makeArtifactRef({
      runId,
      artifactType: 'forecast_packet',
      sha256: 'sha-forecast-packet',
    })
    const recommendationPacketRef = makeArtifactRef({
      runId,
      artifactType: 'recommendation_packet',
      sha256: 'sha-recommendation-packet',
    })
    const executionProjectionRef = makeArtifactRef({
      runId,
      artifactType: 'execution_projection',
      sha256: 'sha-execution-projection',
    })
    const shadowArbitrageRef = makeArtifactRef({
      runId,
      artifactType: 'shadow_arbitrage',
      sha256: 'sha-shadow-arbitrage',
    })
    const pipelineGuardRef = makeArtifactRef({
      runId,
      artifactType: 'pipeline_guard',
      sha256: 'sha-pipeline-guard',
    })
    const runManifestRef = makeArtifactRef({
      runId,
      artifactType: 'run_manifest',
      sha256: 'sha-run-manifest',
    })
    const runManifest = makeRunManifest({
      runId,
      artifactRefs: [
        marketDescriptor,
        marketSnapshotRef,
        resolutionPolicyRef,
        evidenceBundleRef,
        forecastPacket,
        recommendationPacketRef,
        executionProjectionRef,
        shadowArbitrageRef,
        pipelineGuardRef,
        runManifestRef,
      ],
    })
    const marketDescriptorPayload = makeMarketDescriptor(runId)
    const marketSnapshotPayload = marketSnapshotSchema.parse({
      venue: 'polymarket',
      market: marketDescriptorPayload,
      captured_at: '2026-04-08T00:00:00.000Z',
      yes_outcome_index: 0,
      yes_token_id: `${marketDescriptorPayload.market_id}:yes`,
      yes_price: 0.5,
      no_price: 0.5,
      midpoint_yes: 0.5,
      best_bid_yes: 0.49,
      best_ask_yes: 0.51,
      spread_bps: 200,
      book: {
        token_id: `${marketDescriptorPayload.market_id}:yes`,
        market_condition_id: `${marketDescriptorPayload.market_id}:cond`,
        fetched_at: '2026-04-08T00:00:00.000Z',
        best_bid: 0.49,
        best_ask: 0.51,
        last_trade_price: 0.5,
        tick_size: 0.01,
        min_order_size: 5,
        bids: [{ price: 0.49, size: 400 }],
        asks: [{ price: 0.51, size: 400 }],
        depth_near_touch: 800,
      },
      history: [
        { timestamp: 1712534400, price: 0.48 },
        { timestamp: 1712538000, price: 0.5 },
      ],
      source_urls: ['https://example.com/api-canonical-size/book'],
    })
    const resolutionPolicy = resolutionPolicySchema.parse({
      market_id: marketDescriptorPayload.market_id,
      venue: 'polymarket',
      status: 'eligible',
      manual_review_required: false,
      reasons: [],
      primary_sources: ['https://example.com/api-canonical-size'],
      evaluated_at: '2026-04-08T00:00:00.000Z',
    })
    const evidenceBundle = [
      evidencePacketSchema.parse({
        evidence_id: `${runId}:manual-thesis`,
        market_id: marketDescriptorPayload.market_id,
        venue: 'polymarket',
        type: 'manual_thesis',
        title: 'Manual thesis override',
        summary: 'Canonical sizing test thesis override.',
        captured_at: '2026-04-08T00:00:00.000Z',
        content_hash: 'sha-evidence-manual-thesis',
        metadata: {
          thesis_probability: 0.71,
          thesis_rationale: 'Canonical sizing test thesis override.',
        },
      }),
    ]
    const forecastPacketPayload = forecastPacketSchema.parse({
      market_id: marketDescriptorPayload.market_id,
      venue: 'polymarket',
      basis: 'manual_thesis',
      probability_yes: 0.71,
      confidence: 0.64,
      rationale: 'Stored forecast',
      evidence_refs: evidenceBundle.map((packet) => packet.evidence_id),
      produced_at: '2026-04-08T00:00:00.000Z',
    })
    const recommendationPacket = marketRecommendationPacketSchema.parse({
      market_id: marketDescriptorPayload.market_id,
      venue: 'polymarket',
      action: 'bet',
      side: 'yes',
      confidence: 0.64,
      fair_value_yes: 0.71,
      market_price_yes: 0.5,
      market_bid_yes: 0.49,
      market_ask_yes: 0.51,
      edge_bps: 2100,
      spread_bps: 200,
      reasons: ['Stored recommendation'],
      risk_flags: [],
      produced_at: '2026-04-08T00:00:00.000Z',
    })
    const executionProjectionArtifact = makeExecutionProjectionArtifact({
      runId,
      requestedPath: 'live',
      selectedPath: 'shadow',
      shadowRecommendedSizeUsd: 60,
    })
    executionProjectionArtifact.projected_paths.shadow.trade_intent_preview = {
      ...executionProjectionArtifact.projected_paths.shadow.trade_intent_preview,
      size_usd: 90,
      notes: 'shadow preview intent before canonical cap',
    }
    executionProjectionArtifact.projected_paths.shadow.sizing_signal = {
      ...executionProjectionArtifact.projected_paths.shadow.sizing_signal,
      preview_size_usd: 90,
      recommended_size_usd: 90,
      canonical_size_usd: 60,
      shadow_recommended_size_usd: 60,
      notes: ['Canonical size is capped to 60 USD by the read-only shadow arbitrage sizing check.'],
    }
    const shadowArbitrageArtifact = makeShadowArbitrageArtifact(60)

    storeMocks.getPredictionMarketRunDetails.mockReturnValueOnce({
      run_id: runId,
      source_run_id: null,
      workspace_id: 1,
      venue: 'polymarket',
      mode: 'advise',
      market_id: marketDescriptorPayload.market_id,
      market_slug: marketDescriptorPayload.slug,
      status: 'completed',
      recommendation: 'bet',
      side: 'yes',
      confidence: 0.78,
      probability_yes: 0.72,
      market_price_yes: 0.49,
      edge_bps: 2300,
      created_at: 1712534400,
      updated_at: 1712534460,
      manifest: runManifest,
      artifact_refs: [
        marketDescriptor,
        marketSnapshotRef,
        resolutionPolicyRef,
        evidenceBundleRef,
        forecastPacket,
        recommendationPacketRef,
        executionProjectionRef,
        shadowArbitrageRef,
        pipelineGuardRef,
        runManifestRef,
      ],
      artifacts: [
        {
          artifact_id: `${runId}:forecast_packet`,
          artifact_type: 'forecast_packet',
          sha256: 'sha-forecast-packet',
          payload: forecastPacketPayload,
        },
        {
          artifact_id: `${runId}:market_descriptor`,
          artifact_type: 'market_descriptor',
          sha256: 'sha-market-descriptor',
          payload: marketDescriptorPayload,
        },
        {
          artifact_id: `${runId}:market_snapshot`,
          artifact_type: 'market_snapshot',
          sha256: 'sha-market-snapshot',
          payload: marketSnapshotPayload,
        },
        {
          artifact_id: `${runId}:resolution_policy`,
          artifact_type: 'resolution_policy',
          sha256: 'sha-resolution-policy',
          payload: resolutionPolicy,
        },
        {
          artifact_id: `${runId}:evidence_bundle`,
          artifact_type: 'evidence_bundle',
          sha256: 'sha-evidence-bundle',
          payload: evidenceBundle,
        },
        {
          artifact_id: `${runId}:recommendation_packet`,
          artifact_type: 'recommendation_packet',
          sha256: 'sha-recommendation-packet',
          payload: recommendationPacket,
        },
        {
          artifact_id: `${runId}:execution_projection`,
          artifact_type: 'execution_projection',
          sha256: 'sha-execution-projection',
          payload: executionProjectionArtifact,
        },
        {
          artifact_id: `${runId}:shadow_arbitrage`,
          artifact_type: 'shadow_arbitrage',
          sha256: 'sha-shadow-arbitrage',
          payload: shadowArbitrageArtifact,
        },
        {
          artifact_id: `${runId}:pipeline_guard`,
          artifact_type: 'pipeline_guard',
          sha256: 'sha-pipeline-guard',
          payload: {
            mode: 'advise',
            venue: 'polymarket',
            status: 'normal',
            reasons: [],
            breached_budgets: [],
            metrics: {
              fetch_latency_ms: 100,
              decision_latency_ms: 50,
              snapshot_staleness_ms: 1000,
            },
            venue_capabilities: {
              schema_version: '1.0.0',
              venue: 'polymarket',
              venue_type: 'execution-equivalent',
              supports_discovery: true,
              supports_metadata: true,
              supports_orderbook: true,
              supports_trades: true,
              supports_positions: true,
              supports_execution: true,
              supports_websocket: true,
              supports_paper_mode: true,
              automation_constraints: [],
              last_verified_at: '2026-04-08T00:00:00.000Z',
            },
            venue_health: {
              schema_version: '1.0.0',
              venue: 'polymarket',
              captured_at: '2026-04-08T00:00:00.000Z',
              health_score: 1,
              api_status: 'healthy',
              stream_status: 'healthy',
              staleness_ms: 0,
              degraded_mode: 'normal',
              incident_flags: [],
            },
            budgets: {
              venue: 'polymarket',
              fetch_latency_budget_ms: 4_000,
              snapshot_freshness_budget_ms: 4_000,
              decision_latency_budget_ms: 2_000,
              stream_reconnect_budget_ms: 4_000,
              cache_ttl_ms: 1_000,
              max_retries: 0,
              backpressure_policy: 'degrade-to-wait',
            },
          },
        },
        {
          artifact_id: `${runId}:run_manifest`,
          artifact_type: 'run_manifest',
          sha256: 'sha-run-manifest',
          payload: runManifest,
        },
      ],
    })

    const details = getPredictionMarketRunDetails(runId, 1)

    expect(details?.execution_projection?.selected_path).toBe('shadow')
    expect(details?.execution_projection?.projected_paths.shadow.trade_intent_preview?.size_usd).toBe(90)
    expect(details?.execution_projection?.projected_paths.shadow.sizing_signal?.canonical_size_usd).toBe(60)
    expect(details?.trade_intent_guard?.metadata).toMatchObject({
      trade_intent_preview_source: 'canonical_trade_intent_preview',
      trade_intent_preview_via: 'execution_projection_selected_preview',
      selected_projection_canonical_size_usd: 60,
    })
    expect(details?.trade_intent_guard?.trade_intent_preview?.size_usd).toBe(60)
    expectFutureTopLevelTradeIntentPreviewAlignment(
      details as FutureTopLevelTradeIntentPreviewSurface,
    )
  })
})
