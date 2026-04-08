import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/server', () => {
  class MockHeaders {
    private readonly values = new Map<string, string>()

    constructor(init?: HeadersInit) {
      if (!init) return
      if (init instanceof Headers) {
        init.forEach((value, key) => {
          this.values.set(key.toLowerCase(), value)
        })
        return
      }

      if (Array.isArray(init)) {
        for (const [key, value] of init) {
          this.values.set(key.toLowerCase(), String(value))
        }
        return
      }

      for (const [key, value] of Object.entries(init)) {
        this.values.set(key.toLowerCase(), String(value))
      }
    }

    get(name: string) {
      return this.values.get(name.toLowerCase()) ?? null
    }

    set(name: string, value: string) {
      this.values.set(name.toLowerCase(), value)
    }
  }

  class MockNextResponse {
    constructor(
      private readonly bodyValue: unknown,
      public readonly status: number,
      public readonly headers: MockHeaders,
    ) {}

    async json() {
      return this.bodyValue
    }
  }

  class MockNextRequest extends Request {}

  return {
    NextRequest: MockNextRequest,
    NextResponse: {
      json: (body: unknown, init?: { status?: number; headers?: HeadersInit }) =>
        new MockNextResponse(body, init?.status ?? 200, new MockHeaders(init?.headers)),
    },
  }
})

import { NextRequest } from 'next/server'

const mocks = vi.hoisted(() => ({
  requireRole: vi.fn(),
  readLimiter: vi.fn(),
  listPredictionMarketRuns: vi.fn(),
  getPredictionMarketRunDetails: vi.fn(),
}))

function makeShadowArbitrageFixture(recommendedSizeUsd: number) {
  return {
    read_only: true,
    generated_at: '2026-04-08T00:00:00.000Z',
    as_of_at: '2026-04-08T00:00:00.000Z',
    executable_edge: {
      executable: true,
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

vi.mock('@/lib/auth', () => ({
  requireRole: mocks.requireRole,
}))

vi.mock('@/lib/rate-limit', () => ({
  readLimiter: mocks.readLimiter,
}))

vi.mock('@/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
  },
}))

vi.mock('@/lib/prediction-markets/service', () => ({
  listPredictionMarketRuns: mocks.listPredictionMarketRuns,
  getPredictionMarketRunDetails: mocks.getPredictionMarketRunDetails,
}))

describe('prediction markets v1 run routes', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.requireRole.mockReset()
    mocks.readLimiter.mockReset()
    mocks.listPredictionMarketRuns.mockReset()
    mocks.getPredictionMarketRunDetails.mockReset()
    mocks.requireRole.mockReturnValue({ user: { workspace_id: 7 } })
    mocks.readLimiter.mockReturnValue(null)
  })

  it('lists runs with additive artifact_audit and the v1 header', async () => {
    mocks.listPredictionMarketRuns.mockReturnValue([
      {
        run_id: 'run-1',
        source_run_id: null,
        workspace_id: 7,
        venue: 'polymarket',
        mode: 'advise',
        market_id: 'mkt-1',
        market_slug: 'mkt-1',
        status: 'completed',
        recommendation: 'bet',
        side: 'yes',
        confidence: 0.81,
        probability_yes: 0.74,
        market_price_yes: 0.51,
        edge_bps: 2300,
        research_pipeline_id: 'polymarket-research-pipeline',
        research_pipeline_version: 'poly-025-research-v1',
        research_runtime_mode: 'research_driven',
        research_forecaster_count: 3,
        research_weighted_probability_yes: 0.74,
        research_weighted_coverage: 0.88,
        research_compare_preferred_mode: 'aggregate',
        research_compare_summary: 'Preferred mode: aggregate. Base rate and manual notes are aligned.',
        research_abstention_policy_version: 'structured-abstention-v1',
        research_abstention_policy_blocks_forecast: false,
        research_forecast_probability_yes_hint: 0.74,
        benchmark_gate_summary:
          'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
        benchmark_uplift_bps: 1100,
        benchmark_gate_status: 'preview_only',
        benchmark_promotion_status: 'unproven',
        benchmark_promotion_ready: false,
        benchmark_preview_available: true,
        benchmark_promotion_evidence: 'unproven',
        benchmark_evidence_level: 'benchmark_preview',
        benchmark_promotion_gate_kind: 'preview_only',
        benchmark_gate_blockers: ['out_of_sample_unproven'],
        benchmark_gate_reasons: ['out_of_sample_unproven'],
        execution_pathways_highest_actionable_mode: 'shadow',
        execution_projection_gate_name: 'execution_projection',
        execution_projection_preflight_only: true,
        execution_projection_requested_path: 'live',
        execution_projection_selected_path: 'shadow',
        execution_projection_selected_path_status: 'ready',
        execution_projection_selected_path_effective_mode: 'shadow',
        execution_projection_selected_path_reason_summary: 'shadow remains the best allowed mode.',
        execution_projection_verdict: 'downgraded',
        execution_projection_highest_safe_requested_mode: 'shadow',
        execution_projection_recommended_effective_mode: 'shadow',
        execution_projection_manual_review_required: true,
        execution_projection_ttl_ms: 30000,
        execution_projection_expires_at: '2026-04-08T00:00:30.000Z',
        execution_projection_blocking_reasons: [],
        execution_projection_downgrade_reasons: ['manual_review_required_for_execution'],
        execution_projection_summary: 'Requested live; selected shadow.',
        execution_projection_preflight_summary: {
          gate_name: 'execution_projection',
          requested_path: 'live',
          selected_path: 'shadow',
          verdict: 'downgraded',
          highest_safe_requested_mode: 'shadow',
          recommended_effective_mode: 'shadow',
          manual_review_required: true,
          ttl_ms: 30000,
          expires_at: '2026-04-08T00:00:30.000Z',
          counts: { total: 3, eligible: 2, ready: 1, degraded: 1, blocked: 1 },
          basis: {
            uses_execution_readiness: true,
            uses_compliance: true,
            uses_capital: true,
            uses_reconciliation: false,
            capital_status: 'attached',
            reconciliation_status: 'unavailable',
          },
          source_refs: ['run-1:pipeline_guard'],
          blockers: [],
          downgrade_reasons: ['manual_review_required_for_execution'],
          summary: 'Requested live; selected shadow.',
        },
        execution_projection_capital_status: 'attached',
        execution_projection_reconciliation_status: 'unavailable',
        execution_projection_selected_preview: {
          size_usd: 75,
          limit_price: 0.51,
          time_in_force: 'ioc',
          max_slippage_bps: 50,
        },
        execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
        execution_projection_selected_path_canonical_size_usd: 75,
        execution_projection_selected_path_shadow_signal_present: true,
        shadow_arbitrage_present: true,
        shadow_arbitrage_recommended_size_usd: 75,
        created_at: 1712534400,
        updated_at: 1712534460,
        manifest: {
          run_id: 'run-1',
          mode: 'advise',
          venue: 'polymarket',
          market_id: 'mkt-1',
          actor: 'operator',
          started_at: '2026-04-08T00:00:00.000Z',
          completed_at: '2026-04-08T00:01:00.000Z',
          status: 'completed',
          config_hash: 'cfg-1',
          artifact_refs: [],
        },
        artifact_refs: [],
        artifact_audit: {
          manifest_ref_count: 0,
          observed_ref_count: 0,
          canonical_ref_count: 0,
          run_manifest_present: true,
          duplicate_artifact_ids: [],
          manifest_only_artifact_ids: [],
          observed_only_artifact_ids: [],
        },
        shadow_arbitrage: makeShadowArbitrageFixture(75),
      },
    ])

    const { GET } = await import('@/app/api/v1/prediction-markets/runs/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs?venue=polymarket&limit=10', {
      method: 'GET',
    })

    const response = await GET(request)
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(response.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(mocks.requireRole).toHaveBeenCalledWith(request, 'viewer')
    expect(mocks.readLimiter).toHaveBeenCalledWith(request)
    expect(mocks.listPredictionMarketRuns).toHaveBeenCalledWith({
      workspaceId: 7,
      venue: 'polymarket',
      recommendation: undefined,
      limit: 10,
    })
    expect(body).toEqual({
      runs: [
        expect.objectContaining({
          run_id: 'run-1',
          artifact_audit: expect.objectContaining({
            run_manifest_present: true,
          }),
          execution_pathways_highest_actionable_mode: 'shadow',
          execution_projection_gate_name: 'execution_projection',
          execution_projection_preflight_only: true,
          execution_projection_requested_path: 'live',
          execution_projection_selected_path: 'shadow',
          execution_projection_selected_path_status: 'ready',
          execution_projection_selected_path_effective_mode: 'shadow',
          execution_projection_selected_path_reason_summary: 'shadow remains the best allowed mode.',
          execution_projection_verdict: 'downgraded',
          execution_projection_highest_safe_requested_mode: 'shadow',
          execution_projection_recommended_effective_mode: 'shadow',
          execution_projection_manual_review_required: true,
          execution_projection_ttl_ms: 30000,
          execution_projection_expires_at: '2026-04-08T00:00:30.000Z',
          execution_projection_blocking_reasons: [],
          execution_projection_downgrade_reasons: ['manual_review_required_for_execution'],
          execution_projection_summary: 'Requested live; selected shadow.',
          execution_projection_preflight_summary: expect.objectContaining({
            gate_name: 'execution_projection',
            requested_path: 'live',
            selected_path: 'shadow',
          }),
          execution_projection_capital_status: 'attached',
          execution_projection_reconciliation_status: 'unavailable',
          execution_projection_selected_preview: expect.objectContaining({
            size_usd: 75,
          }),
          execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
          execution_projection_selected_path_canonical_size_usd: 75,
          execution_projection_selected_path_shadow_signal_present: true,
          shadow_arbitrage_present: true,
          shadow_arbitrage_recommended_size_usd: 75,
          research_pipeline_id: 'polymarket-research-pipeline',
          research_pipeline_version: 'poly-025-research-v1',
          research_runtime_mode: 'research_driven',
          research_forecaster_count: 3,
          research_weighted_probability_yes: 0.74,
          research_weighted_coverage: 0.88,
          research_compare_preferred_mode: 'aggregate',
          research_compare_summary: 'Preferred mode: aggregate. Base rate and manual notes are aligned.',
          research_abstention_policy_version: 'structured-abstention-v1',
          research_abstention_policy_blocks_forecast: false,
          research_forecast_probability_yes_hint: 0.74,
          benchmark_gate_summary:
            'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
          benchmark_uplift_bps: 1100,
          benchmark_gate_status: 'preview_only',
          benchmark_promotion_status: 'unproven',
          benchmark_promotion_ready: false,
          benchmark_preview_available: true,
          benchmark_promotion_evidence: 'unproven',
          benchmark_evidence_level: 'benchmark_preview',
          benchmark_promotion_gate_kind: 'preview_only',
          benchmark_gate_blockers: ['out_of_sample_unproven'],
          benchmark_gate_reasons: ['out_of_sample_unproven'],
          shadow_arbitrage: expect.objectContaining({
            summary: expect.objectContaining({
              recommended_size_usd: 75,
            }),
          }),
        }),
      ],
      total: 1,
    })
  })

  it('keeps canonical benchmark summary fields on the runs route when research aliases conflict', async () => {
    mocks.listPredictionMarketRuns.mockReturnValue([
      {
        run_id: 'run-benchmark-route-1',
        source_run_id: null,
        workspace_id: 7,
        venue: 'polymarket',
        mode: 'advise',
        market_id: 'mkt-benchmark-route-1',
        market_slug: 'mkt-benchmark-route-1',
        status: 'completed',
        recommendation: 'bet',
        side: 'yes',
        confidence: 0.81,
        probability_yes: 0.74,
        market_price_yes: 0.51,
        edge_bps: 2300,
        benchmark_gate_summary: 'benchmark gate: canonical promotion',
        benchmark_uplift_bps: 111,
        benchmark_verdict: 'local_benchmark_ready',
        benchmark_gate_status: 'preview_only',
        benchmark_promotion_status: 'eligible',
        benchmark_promotion_ready: true,
        benchmark_preview_available: true,
        benchmark_promotion_evidence: 'local_benchmark',
        benchmark_evidence_level: 'out_of_sample_promotion_evidence',
        benchmark_promotion_gate_kind: 'local_benchmark',
        benchmark_promotion_blocker_summary: 'canonical promotion satisfied',
        benchmark_promotion_summary: 'canonical promotion satisfied',
        benchmark_gate_blocks_live: false,
        benchmark_gate_live_block_reason: null,
        benchmark_gate_blockers: [],
        benchmark_gate_reasons: ['canonical promotion'],
        research_benchmark_gate_summary: 'research benchmark gate: blocked',
        research_benchmark_verdict: 'blocked_by_abstention',
        research_benchmark_gate_status: 'blocked_by_abstention',
        research_benchmark_promotion_status: 'blocked',
        research_benchmark_promotion_ready: false,
        research_benchmark_preview_available: true,
        research_benchmark_promotion_evidence: 'blocked',
        research_benchmark_evidence_level: 'benchmark_preview',
        research_promotion_gate_kind: 'preview_only',
        research_benchmark_promotion_blocker_summary: 'research alias blocker',
        research_benchmark_promotion_summary: 'research alias blocker',
        research_benchmark_gate_blockers: ['research_alias_blocker'],
        research_benchmark_gate_reasons: ['research_alias_blocker'],
        research_benchmark_gate_blocks_live: true,
        research_benchmark_live_block_reason: 'research alias blocker',
        created_at: 1712534400,
        updated_at: 1712534460,
        manifest: {
          run_id: 'run-benchmark-route-1',
          mode: 'advise',
          venue: 'polymarket',
          market_id: 'mkt-benchmark-route-1',
          actor: 'operator',
          started_at: '2026-04-08T00:00:00.000Z',
          completed_at: '2026-04-08T00:01:00.000Z',
          status: 'completed',
          config_hash: 'cfg-benchmark-route-1',
          artifact_refs: [],
        },
        artifact_refs: [],
        artifact_audit: {
          manifest_ref_count: 0,
          observed_ref_count: 0,
          canonical_ref_count: 0,
          run_manifest_present: true,
          duplicate_artifact_ids: [],
          manifest_only_artifact_ids: [],
          observed_only_artifact_ids: [],
        },
      },
    ])

    const { GET } = await import('@/app/api/v1/prediction-markets/runs/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs?venue=polymarket&limit=10', {
      method: 'GET',
    })

    const response = await GET(request)
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(body).toEqual({
      runs: [
        expect.objectContaining({
          run_id: 'run-benchmark-route-1',
          artifact_audit: expect.objectContaining({
            run_manifest_present: true,
          }),
          benchmark_gate_summary: 'benchmark gate: canonical promotion',
          benchmark_uplift_bps: 111,
          benchmark_verdict: 'local_benchmark_ready',
          benchmark_gate_status: 'preview_only',
          benchmark_promotion_status: 'eligible',
          benchmark_promotion_ready: true,
          benchmark_preview_available: true,
          benchmark_promotion_evidence: 'local_benchmark',
          benchmark_evidence_level: 'out_of_sample_promotion_evidence',
          benchmark_promotion_gate_kind: 'local_benchmark',
          benchmark_promotion_blocker_summary: 'canonical promotion satisfied',
          benchmark_promotion_summary: 'canonical promotion satisfied',
          benchmark_gate_blocks_live: false,
          benchmark_gate_live_block_reason: null,
          research_benchmark_gate_summary: 'research benchmark gate: blocked',
          research_benchmark_promotion_ready: false,
        }),
      ],
      total: 1,
    })
  })

  it('returns the run detail with artifact_readback and artifact_audit', async () => {
    mocks.getPredictionMarketRunDetails.mockReturnValue({
      run_id: 'run-2',
      source_run_id: null,
      workspace_id: 7,
      venue: 'polymarket',
      mode: 'replay',
      market_id: 'mkt-2',
      market_slug: 'mkt-2',
      status: 'completed',
      recommendation: 'wait',
      side: null,
      confidence: 0.62,
      probability_yes: 0.53,
      market_price_yes: 0.49,
      edge_bps: 400,
      research_pipeline_id: 'polymarket-research-pipeline',
      research_pipeline_version: 'poly-025-research-v1',
      research_runtime_mode: 'research_driven',
      research_forecaster_count: 3,
      research_weighted_probability_yes: 0.66,
      research_weighted_coverage: 0.8,
      research_compare_preferred_mode: 'aggregate',
      research_compare_summary: 'Preferred mode: aggregate. Base rate and manual notes are aligned.',
      research_abstention_policy_version: 'structured-abstention-v1',
      research_abstention_policy_blocks_forecast: false,
      research_forecast_probability_yes_hint: 0.66,
      benchmark_gate_summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
      benchmark_uplift_bps: 1100,
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'unproven',
      benchmark_promotion_ready: false,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'unproven',
      benchmark_evidence_level: 'benchmark_preview',
      benchmark_promotion_gate_kind: 'preview_only',
      benchmark_gate_blockers: ['out_of_sample_unproven'],
      benchmark_gate_reasons: ['out_of_sample_unproven'],
      execution_projection_selected_path: 'paper',
      execution_projection_selected_path_status: 'ready',
      execution_projection_verdict: 'allowed',
      execution_projection_capital_status: null,
      execution_projection_reconciliation_status: null,
      execution_projection_selected_preview: null,
      execution_projection_selected_preview_source: null,
      execution_projection_selected_path_canonical_size_usd: null,
      execution_projection_selected_path_shadow_signal_present: false,
      shadow_arbitrage: makeShadowArbitrageFixture(75),
      created_at: 1712534400,
      updated_at: 1712534460,
      manifest: {
        run_id: 'run-2',
        mode: 'replay',
        venue: 'polymarket',
        market_id: 'mkt-2',
        actor: 'operator',
        started_at: '2026-04-08T00:00:00.000Z',
        completed_at: '2026-04-08T00:01:00.000Z',
        status: 'completed',
        config_hash: 'cfg-2',
        artifact_refs: [],
      },
      artifact_refs: [],
      artifacts: [],
      artifact_readback: {
        run_manifest_ref: { artifact_id: 'run-2:run_manifest' },
        manifest_artifact_refs: [],
        observed_artifact_refs: [],
        canonical_artifact_refs: [],
        manifest_index: {},
        observed_index: {},
        canonical_index: {},
        manifest_only_artifact_ids: [],
        observed_only_artifact_ids: [],
      },
      artifact_audit: {
        manifest_ref_count: 0,
        observed_ref_count: 0,
        canonical_ref_count: 0,
        run_manifest_present: true,
        duplicate_artifact_ids: [],
        manifest_only_artifact_ids: [],
        observed_only_artifact_ids: [],
      },
      execution_readiness: {
        venue: 'polymarket',
        highest_safe_mode: 'paper',
        overall_verdict: 'degraded',
        summary: 'Highest safe mode is paper.',
      },
      execution_pathways: {
        highest_actionable_mode: 'paper',
        pathways: [
          { mode: 'paper', status: 'ready', actionable: true },
          { mode: 'shadow', status: 'blocked', actionable: false },
        ],
        summary: 'paper is currently the highest actionable execution pathway.',
      },
      execution_projection: {
        requested_path: 'paper',
        selected_path: 'paper',
        eligible_paths: ['paper'],
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
            trade_intent_preview: null,
          },
          shadow: {
            path: 'shadow',
            requested_mode: 'shadow',
            effective_mode: 'shadow',
            status: 'blocked',
            allowed: false,
            blockers: ['recommendation:wait'],
            warnings: [],
            reason_summary: 'recommendation:wait',
            trade_intent_preview: null,
          },
          live: {
            path: 'live',
            requested_mode: 'live',
            effective_mode: 'live',
            status: 'blocked',
            allowed: false,
            blockers: ['recommendation:wait'],
            warnings: [],
            reason_summary: 'recommendation:wait',
            trade_intent_preview: null,
          },
        },
        summary: 'Requested paper; selected paper. Paper projection is ready.',
      },
      cross_venue_intelligence: {
        evaluations: [],
        arbitrage_candidates: [],
        errors: [],
        summary: {
          total_pairs: 0,
          compatible: [],
          manual_review: [],
          comparison_only: [],
          blocking_reasons: [],
          highest_confidence_candidate: null,
        },
      },
    })

    const { GET } = await import('@/app/api/v1/prediction-markets/runs/[run_id]/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-2', {
      method: 'GET',
    })

    const response = await GET(request, { params: Promise.resolve({ run_id: 'run-2' }) })
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(response.headers.get('X-Prediction-Markets-API')).toBe('v1')
    expect(mocks.requireRole).toHaveBeenCalledWith(request, 'viewer')
    expect(mocks.readLimiter).toHaveBeenCalledWith(request)
    expect(mocks.getPredictionMarketRunDetails).toHaveBeenCalledWith('run-2', 7)
    expect(body).toMatchObject({
      run_id: 'run-2',
      artifact_readback: {
        run_manifest_ref: { artifact_id: 'run-2:run_manifest' },
      },
      artifact_audit: {
        run_manifest_present: true,
      },
      shadow_arbitrage: {
        read_only: true,
        summary: {
          recommended_size_usd: 75,
          shadow_edge_bps: 98,
        },
      },
      execution_readiness: {
        highest_safe_mode: 'paper',
        overall_verdict: 'degraded',
      },
      execution_pathways: {
        highest_actionable_mode: 'paper',
      },
      execution_projection: {
        requested_path: 'paper',
        selected_path: 'paper',
      },
      execution_projection_selected_path: 'paper',
      execution_projection_selected_path_status: 'ready',
      execution_projection_verdict: 'allowed',
      execution_projection_selected_preview: null,
      execution_projection_selected_preview_source: null,
      execution_projection_selected_path_shadow_signal_present: false,
      research_pipeline_id: 'polymarket-research-pipeline',
      research_pipeline_version: 'poly-025-research-v1',
      research_runtime_mode: 'research_driven',
      research_forecaster_count: 3,
      research_weighted_probability_yes: 0.66,
      research_weighted_coverage: 0.8,
      research_compare_preferred_mode: 'aggregate',
      research_compare_summary: 'Preferred mode: aggregate. Base rate and manual notes are aligned.',
      research_abstention_policy_version: 'structured-abstention-v1',
      research_abstention_policy_blocks_forecast: false,
      research_forecast_probability_yes_hint: 0.66,
      benchmark_gate_summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
      benchmark_uplift_bps: 1100,
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'unproven',
      benchmark_promotion_ready: false,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'unproven',
      benchmark_evidence_level: 'benchmark_preview',
      benchmark_promotion_gate_kind: 'preview_only',
      benchmark_gate_blockers: ['out_of_sample_unproven'],
      benchmark_gate_reasons: ['out_of_sample_unproven'],
      cross_venue_intelligence: {
        summary: {
          total_pairs: 0,
        },
      },
    })
  })

  it('returns a canonical trade_intent_guard preview when the selected-path canonical size is lower than the raw preview', async () => {
    mocks.getPredictionMarketRunDetails.mockReturnValue({
      run_id: 'run-2b',
      source_run_id: null,
      workspace_id: 7,
      venue: 'polymarket',
      mode: 'replay',
      market_id: 'mkt-2b',
      market_slug: 'mkt-2b',
      status: 'completed',
      recommendation: 'bet',
      side: 'yes',
      confidence: 0.72,
      probability_yes: 0.68,
      market_price_yes: 0.5,
      edge_bps: 1800,
      execution_pathways_highest_actionable_mode: 'paper',
      execution_projection_selected_path: 'shadow',
      execution_projection_selected_path_status: 'ready',
      execution_projection_verdict: 'downgraded',
      execution_projection_capital_status: 'attached',
      execution_projection_reconciliation_status: 'unavailable',
      execution_projection_selected_preview: {
        schema_version: '1.0.0',
        intent_id: 'run-2b:shadow-preview',
        run_id: 'run-2b',
        venue: 'polymarket',
        market_id: 'mkt-2b',
        side: 'yes',
        size_usd: 60,
        limit_price: 0.51,
        max_slippage_bps: 50,
        max_unhedged_leg_ms: 1_000,
        time_in_force: 'ioc',
        forecast_ref: 'forecast:run-2b:2026-04-08T00:00:00.000Z',
        risk_checks_passed: true,
        created_at: '2026-04-08T00:00:00.000Z',
        notes: 'shadow preview intent before canonical cap Canonical execution sizing caps preview size to 60 USD.',
      },
      execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
      execution_projection_selected_path_canonical_size_usd: 60,
      execution_projection_selected_path_shadow_signal_present: true,
      shadow_arbitrage: makeShadowArbitrageFixture(60),
      created_at: 1712534400,
      updated_at: 1712534460,
      manifest: {
        run_id: 'run-2b',
        mode: 'replay',
        venue: 'polymarket',
        market_id: 'mkt-2b',
        actor: 'operator',
        started_at: '2026-04-08T00:00:00.000Z',
        completed_at: '2026-04-08T00:01:00.000Z',
        status: 'completed',
        config_hash: 'cfg-2b',
        artifact_refs: [],
      },
      artifact_refs: [],
      artifacts: [],
      artifact_readback: {
        run_manifest_ref: { artifact_id: 'run-2b:run_manifest' },
        manifest_artifact_refs: [],
        observed_artifact_refs: [],
        canonical_artifact_refs: [],
        manifest_index: {},
        observed_index: {},
        canonical_index: {},
        manifest_only_artifact_ids: [],
        observed_only_artifact_ids: [],
      },
      artifact_audit: {
        manifest_ref_count: 0,
        observed_ref_count: 0,
        canonical_ref_count: 0,
        run_manifest_present: true,
        duplicate_artifact_ids: [],
        manifest_only_artifact_ids: [],
        observed_only_artifact_ids: [],
      },
      execution_readiness: {
        venue: 'polymarket',
        highest_safe_mode: 'paper',
        overall_verdict: 'degraded',
        summary: 'Highest safe mode is paper.',
      },
      execution_pathways: {
        highest_actionable_mode: 'paper',
        pathways: [
          { mode: 'paper', status: 'ready', actionable: true },
          { mode: 'shadow', status: 'degraded', actionable: true },
          { mode: 'live', status: 'blocked', actionable: false },
        ],
        summary: 'paper is currently the highest actionable execution pathway.',
      },
      execution_projection: {
        requested_path: 'live',
        selected_path: 'shadow',
        eligible_paths: ['paper', 'shadow'],
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
            trade_intent_preview: {
              schema_version: '1.0.0',
              intent_id: 'run-2b:shadow-preview',
              run_id: 'run-2b',
              venue: 'polymarket',
              market_id: 'mkt-2b',
              side: 'yes',
              size_usd: 100,
              limit_price: 0.51,
              max_slippage_bps: 50,
              max_unhedged_leg_ms: 1_000,
              time_in_force: 'ioc',
              forecast_ref: 'forecast:run-2b:2026-04-08T00:00:00.000Z',
              risk_checks_passed: true,
              created_at: '2026-04-08T00:00:00.000Z',
              notes: 'shadow preview intent before canonical cap',
            },
            canonical_trade_intent_preview: {
              schema_version: '1.0.0',
              intent_id: 'run-2b:shadow-preview',
              run_id: 'run-2b',
              venue: 'polymarket',
              market_id: 'mkt-2b',
              side: 'yes',
              size_usd: 60,
              limit_price: 0.51,
              max_slippage_bps: 50,
              max_unhedged_leg_ms: 1_000,
              time_in_force: 'ioc',
              forecast_ref: 'forecast:run-2b:2026-04-08T00:00:00.000Z',
              risk_checks_passed: true,
              created_at: '2026-04-08T00:00:00.000Z',
              notes: 'shadow preview intent before canonical cap Canonical execution sizing caps preview size to 60 USD.',
            },
          },
          live: {
            path: 'live',
            requested_mode: 'live',
            effective_mode: 'shadow',
            status: 'blocked',
            allowed: false,
            blockers: ['selected_path_downgraded'],
            warnings: [],
            reason_summary: 'selected_path_downgraded',
            trade_intent_preview: null,
          },
        },
        summary: 'Requested live; selected shadow. Shadow projection is ready.',
      },
      trade_intent_guard: {
        gate_name: 'trade_intent_guard',
        verdict: 'blocked',
        manual_review_required: true,
        blocked_reasons: ['manual_review_required'],
        warning_reasons: [],
        snapshot_staleness_ms: 1000,
        edge_after_fees_bps: 1800,
        venue_health_status: 'healthy',
        projection_verdict: 'downgraded',
        readiness_route: 'paper',
        selected_path: 'shadow',
        highest_safe_mode: 'shadow',
        trade_intent_preview: {
          schema_version: '1.0.0',
          intent_id: 'run-2b:shadow-preview',
          run_id: 'run-2b',
          venue: 'polymarket',
          market_id: 'mkt-2b',
          side: 'yes',
          size_usd: 60,
          limit_price: 0.51,
          max_slippage_bps: 50,
          max_unhedged_leg_ms: 1_000,
          time_in_force: 'ioc',
          forecast_ref: 'forecast:run-2b:2026-04-08T00:00:00.000Z',
          risk_checks_passed: true,
          created_at: '2026-04-08T00:00:00.000Z',
          notes: 'shadow preview intent before canonical cap Canonical execution sizing caps preview size to 60 USD.',
        },
        summary: 'blocked=manual_review_required',
        source_refs: {
          pipeline_guard: 'run-2b:pipeline_guard',
          runtime_guard: 'run-2b:runtime_guard',
          compliance_report: 'run-2b:compliance_report',
          execution_readiness: 'run-2b:execution_readiness',
          execution_pathways: 'run-2b:execution_pathways',
          execution_projection: 'run-2b:execution_projection',
          cross_venue_intelligence: 'run-2b:cross_venue_intelligence',
          recommendation_packet: 'run-2b:recommendation_packet',
        },
        metadata: {
          run_id: 'run-2b',
          market_id: 'mkt-2b',
          venue: 'polymarket',
          cross_venue_manual_review_count: 0,
          cross_venue_comparison_only_count: 0,
          execution_pathways_highest_actionable_mode: 'paper',
          trade_intent_preview_available: true,
          trade_intent_preview_source: 'canonical_trade_intent_preview',
          trade_intent_preview_via: 'execution_projection_selected_preview',
          trade_intent_preview_uses_projection_selected_preview: true,
          execution_projection_selected_preview_available: true,
          execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
          trade_intent_preview_capped_to_canonical_size: false,
          selected_projection_path_status: 'ready',
          selected_projection_path_effective_mode: 'shadow',
          selected_projection_sizing_signal_present: true,
          selected_projection_shadow_arbitrage_signal_present: true,
          selected_projection_canonical_size_usd: 60,
        },
      },
      cross_venue_intelligence: {
        evaluations: [],
        arbitrage_candidates: [],
        errors: [],
        summary: {
          total_pairs: 0,
          compatible: [],
          manual_review: [],
          comparison_only: [],
          blocking_reasons: [],
          highest_confidence_candidate: null,
        },
      },
    })

    const { GET } = await import('@/app/api/v1/prediction-markets/runs/[run_id]/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-2b', {
      method: 'GET',
    })

    const response = await GET(request, { params: Promise.resolve({ run_id: 'run-2b' }) })
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(body).toMatchObject({
      run_id: 'run-2b',
      execution_projection_selected_path: 'shadow',
      execution_projection_selected_path_status: 'ready',
      execution_projection_selected_preview: {
        size_usd: 60,
      },
      execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
      execution_projection_selected_path_canonical_size_usd: 60,
      trade_intent_guard: {
        gate_name: 'trade_intent_guard',
        trade_intent_preview: {
          size_usd: 60,
        },
        metadata: {
          trade_intent_preview_source: 'canonical_trade_intent_preview',
          trade_intent_preview_via: 'execution_projection_selected_preview',
          trade_intent_preview_uses_projection_selected_preview: true,
          execution_projection_selected_preview_available: true,
          execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
          trade_intent_preview_capped_to_canonical_size: false,
          selected_projection_canonical_size_usd: 60,
        },
      },
    })
    expect(body.execution_projection.projected_paths.shadow.trade_intent_preview.size_usd).toBe(100)
    expect(body.execution_projection.projected_paths.shadow.canonical_trade_intent_preview.size_usd).toBe(60)
    expect(body.trade_intent_guard.trade_intent_preview.notes).toContain(
      'Canonical execution sizing caps preview size to 60 USD.',
    )
  })

  it('passes through a future top-level selected or canonical preview field when the runtime exposes one', async () => {
    const canonicalTradeIntentPreview = {
      schema_version: '1.0.0',
      intent_id: 'run-2c:shadow-preview',
      run_id: 'run-2c',
      venue: 'polymarket',
      market_id: 'mkt-2c',
      side: 'yes',
      size_usd: 60,
      limit_price: 0.51,
      max_slippage_bps: 50,
      max_unhedged_leg_ms: 1_000,
      time_in_force: 'ioc',
      forecast_ref: 'forecast:run-2c:2026-04-08T00:00:00.000Z',
      risk_checks_passed: true,
      created_at: '2026-04-08T00:00:00.000Z',
      notes: 'shadow preview intent Canonical execution sizing caps preview size to 60 USD.',
    }

    mocks.getPredictionMarketRunDetails.mockReturnValue({
      run_id: 'run-2c',
      source_run_id: null,
      workspace_id: 7,
      venue: 'polymarket',
      mode: 'replay',
      market_id: 'mkt-2c',
      market_slug: 'mkt-2c',
      status: 'completed',
      recommendation: 'bet',
      side: 'yes',
      confidence: 0.72,
      probability_yes: 0.68,
      market_price_yes: 0.5,
      edge_bps: 1800,
      created_at: 1712534400,
      updated_at: 1712534460,
      execution_projection_selected_path: 'shadow',
      execution_projection_selected_path_status: 'ready',
      execution_projection_selected_path_canonical_size_usd: 60,
      execution_projection_selected_path_shadow_signal_present: true,
      execution_projection_selected_preview: canonicalTradeIntentPreview,
      execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
      selected_trade_intent_preview: canonicalTradeIntentPreview,
      canonical_trade_intent_preview: canonicalTradeIntentPreview,
      execution_projection: {
        requested_path: 'live',
        selected_path: 'shadow',
        projected_paths: {
          shadow: {
            canonical_trade_intent_preview: canonicalTradeIntentPreview,
          },
        },
      },
      trade_intent_guard: {
        gate_name: 'trade_intent_guard',
        trade_intent_preview: canonicalTradeIntentPreview,
        metadata: {
          trade_intent_preview_source: 'canonical_trade_intent_preview',
          trade_intent_preview_via: 'execution_projection_selected_preview',
          selected_projection_canonical_size_usd: 60,
        },
      },
    })

    const { GET } = await import('@/app/api/v1/prediction-markets/runs/[run_id]/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs/run-2c', {
      method: 'GET',
    })

    const response = await GET(request, { params: Promise.resolve({ run_id: 'run-2c' }) })
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(body).toMatchObject({
      run_id: 'run-2c',
      execution_projection_selected_preview: {
        size_usd: 60,
      },
      execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
      selected_trade_intent_preview: {
        size_usd: 60,
      },
      canonical_trade_intent_preview: {
        size_usd: 60,
      },
      trade_intent_guard: {
        trade_intent_preview: {
          size_usd: 60,
        },
      },
    })
    expect(body.execution_projection.projected_paths.shadow.canonical_trade_intent_preview.size_usd).toBe(60)
  })

  it('returns the non-v1 run detail with execution_pathways and execution_projection intact', async () => {
    mocks.getPredictionMarketRunDetails.mockReturnValue({
      run_id: 'run-3',
      source_run_id: null,
      workspace_id: 7,
      venue: 'polymarket',
      mode: 'replay',
      market_id: 'mkt-3',
      market_slug: 'mkt-3',
      status: 'completed',
      recommendation: 'bet',
      side: 'yes',
      confidence: 0.73,
      probability_yes: 0.69,
      market_price_yes: 0.5,
      edge_bps: 1800,
      research_runtime_mode: 'research_driven',
      execution_projection_selected_path: 'live',
      execution_projection_selected_path_status: 'ready',
      execution_projection_verdict: 'allowed',
      execution_projection_capital_status: null,
      execution_projection_reconciliation_status: null,
      execution_projection_selected_preview: {
        schema_version: '1.0.0',
        intent_id: 'run-3:live-preview',
        run_id: 'run-3',
        venue: 'polymarket',
        market_id: 'mkt-3',
        side: 'yes',
        size_usd: 25,
        limit_price: 0.51,
        max_slippage_bps: 50,
        max_unhedged_leg_ms: 250,
        time_in_force: 'ioc',
        forecast_ref: 'forecast:run-3:2026-04-08T00:00:00.000Z',
        risk_checks_passed: true,
        created_at: '2026-04-08T00:00:00.000Z',
        notes: 'live preview intent',
      },
      execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
      execution_projection_selected_path_canonical_size_usd: null,
      execution_projection_selected_path_shadow_signal_present: false,
      shadow_arbitrage: makeShadowArbitrageFixture(60),
      created_at: 1712534400,
      updated_at: 1712534460,
      manifest: {
        run_id: 'run-3',
        mode: 'replay',
        venue: 'polymarket',
        market_id: 'mkt-3',
        actor: 'operator',
        started_at: '2026-04-08T00:00:00.000Z',
        completed_at: '2026-04-08T00:01:00.000Z',
        status: 'completed',
        config_hash: 'cfg-3',
        artifact_refs: [],
      },
      artifact_refs: [],
      artifacts: [],
      artifact_readback: {
        run_manifest_ref: { artifact_id: 'run-3:run_manifest' },
        manifest_artifact_refs: [],
        observed_artifact_refs: [],
        canonical_artifact_refs: [],
        manifest_index: {},
        observed_index: {},
        canonical_index: {},
        manifest_only_artifact_ids: [],
        observed_only_artifact_ids: [],
      },
      artifact_audit: {
        manifest_ref_count: 0,
        observed_ref_count: 0,
        canonical_ref_count: 0,
        run_manifest_present: true,
        duplicate_artifact_ids: [],
        manifest_only_artifact_ids: [],
        observed_only_artifact_ids: [],
      },
      execution_readiness: {
        venue: 'polymarket',
        highest_safe_mode: 'live',
        overall_verdict: 'ready',
        summary: 'Highest safe mode is live.',
      },
      execution_pathways: {
        highest_actionable_mode: 'live',
        pathways: [
          { mode: 'paper', status: 'ready', actionable: true },
          { mode: 'shadow', status: 'ready', actionable: true },
          { mode: 'live', status: 'ready', actionable: true },
        ],
        summary: 'live is currently the highest actionable execution pathway.',
      },
      execution_projection: {
        requested_path: 'live',
        selected_path: 'live',
        eligible_paths: ['paper', 'shadow', 'live'],
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
            trade_intent_preview: null,
          },
          live: {
            path: 'live',
            requested_mode: 'live',
            effective_mode: 'live',
            status: 'ready',
            allowed: true,
            blockers: [],
            warnings: [],
            reason_summary: 'Live projection is ready.',
            trade_intent_preview: {
              schema_version: '1.0.0',
              intent_id: 'run-3:live-preview',
              run_id: 'run-3',
              venue: 'polymarket',
              market_id: 'mkt-3',
              side: 'yes',
              size_usd: 25,
              limit_price: 0.51,
              max_slippage_bps: 50,
              max_unhedged_leg_ms: 250,
              time_in_force: 'ioc',
              forecast_ref: 'forecast:run-3:2026-04-08T00:00:00.000Z',
              risk_checks_passed: true,
              created_at: '2026-04-08T00:00:00.000Z',
              notes: 'live preview intent',
            },
            canonical_trade_intent_preview: {
              schema_version: '1.0.0',
              intent_id: 'run-3:live-preview',
              run_id: 'run-3',
              venue: 'polymarket',
              market_id: 'mkt-3',
              side: 'yes',
              size_usd: 25,
              limit_price: 0.51,
              max_slippage_bps: 50,
              max_unhedged_leg_ms: 250,
              time_in_force: 'ioc',
              forecast_ref: 'forecast:run-3:2026-04-08T00:00:00.000Z',
              risk_checks_passed: true,
              created_at: '2026-04-08T00:00:00.000Z',
              notes: 'live preview intent',
            },
          },
        },
        summary: 'Requested live; selected live. Live projection is ready.',
      },
      cross_venue_intelligence: {
        evaluations: [],
        arbitrage_candidates: [],
        errors: [],
        summary: {
          total_pairs: 0,
          compatible: [],
          manual_review: [],
          comparison_only: [],
          blocking_reasons: [],
          highest_confidence_candidate: null,
        },
      },
    })

    const { GET } = await import('@/app/api/prediction-markets/runs/[run_id]/route')
    const request = new NextRequest('http://localhost/api/prediction-markets/runs/run-3', {
      method: 'GET',
    })

    const response = await GET(request, { params: Promise.resolve({ run_id: 'run-3' }) })
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(response.headers.get('X-Prediction-Markets-API')).toBeNull()
    expect(mocks.requireRole).toHaveBeenCalledWith(request, 'viewer')
    expect(mocks.readLimiter).toHaveBeenCalledWith(request)
    expect(mocks.getPredictionMarketRunDetails).toHaveBeenCalledWith('run-3', 7)
    expect(body).toMatchObject({
      run_id: 'run-3',
      shadow_arbitrage: {
        summary: {
          recommended_size_usd: 60,
        },
      },
      research_runtime_mode: 'research_driven',
      execution_readiness: {
        highest_safe_mode: 'live',
      },
      execution_pathways: {
        highest_actionable_mode: 'live',
      },
      execution_projection: {
        requested_path: 'live',
        selected_path: 'live',
      },
      execution_projection_selected_path: 'live',
      execution_projection_selected_path_status: 'ready',
      execution_projection_verdict: 'allowed',
      execution_projection_selected_preview: {
        size_usd: 25,
      },
      execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
      execution_projection_selected_path_shadow_signal_present: false,
    })
  })

  it('returns auth errors before touching the run list service', async () => {
    mocks.requireRole.mockReturnValueOnce({ error: 'Forbidden', status: 403 })

    const { GET } = await import('@/app/api/v1/prediction-markets/runs/route')
    const request = new NextRequest('http://localhost/api/v1/prediction-markets/runs', {
      method: 'GET',
    })

    const response = await GET(request)
    const body = await response.json()

    expect(response.status).toBe(403)
    expect(body).toEqual({ error: 'Forbidden' })
    expect(mocks.readLimiter).not.toHaveBeenCalled()
    expect(mocks.listPredictionMarketRuns).not.toHaveBeenCalled()
  })
})
