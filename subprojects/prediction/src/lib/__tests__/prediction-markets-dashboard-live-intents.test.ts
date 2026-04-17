import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getPredictionMarketRunDetails: vi.fn(),
  preparePredictionMarketRunLive: vi.fn(),
  executePredictionMarketRunLive: vi.fn(),
  publishPredictionDashboardEvent: vi.fn(),
}))

vi.mock('@/lib/prediction-markets/service', () => ({
  getPredictionMarketRunDetails: mocks.getPredictionMarketRunDetails,
  preparePredictionMarketRunLive: mocks.preparePredictionMarketRunLive,
  executePredictionMarketRunLive: mocks.executePredictionMarketRunLive,
}))

vi.mock('@/lib/prediction-markets/dashboard-events', () => ({
  publishPredictionDashboardEvent: mocks.publishPredictionDashboardEvent,
}))

describe('prediction markets dashboard live intents', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.getPredictionMarketRunDetails.mockReset()
    mocks.preparePredictionMarketRunLive.mockReset()
    mocks.executePredictionMarketRunLive.mockReset()
    mocks.publishPredictionDashboardEvent.mockReset()

    mocks.getPredictionMarketRunDetails.mockReturnValue({
      run_id: 'run-live-dashboard-1',
      workspace_id: 7,
      venue: 'polymarket',
      market_id: 'market-live-dashboard-1',
    })
    mocks.preparePredictionMarketRunLive.mockReturnValue({
      gate_name: 'execution_projection_live',
      preflight_only: true,
      run_id: 'run-live-dashboard-1',
      workspace_id: 7,
      surface_mode: 'live',
      live_route_allowed: true,
      live_status: 'ready',
      live_blocking_reasons: [],
      benchmark_surface_blocking_reasons: [],
      benchmark_promotion_blockers: [],
      benchmark_promotion_ready: true,
      benchmark_gate_blocks_live: false,
      benchmark_gate_live_block_reason: null,
      summary: 'Live surface is ready for governed routing.',
      execution_projection_selected_path: 'live',
      live_path: {
        path: 'live',
        status: 'ready',
        effective_mode: 'live',
      },
      live_trade_intent_preview: {
        size_usd: 25,
        limit_price: 0.51,
      },
      live_trade_intent_preview_source: 'canonical_trade_intent_preview',
      execution_pathways: {
        venue: 'polymarket',
        market_id: 'market-live-dashboard-1',
        recommendation_action: 'bet',
        recommendation_side: 'yes',
        highest_actionable_mode: 'live',
        pathways: [],
        approval_ticket: {
          ticket_id: 'run-live-dashboard-1:approval_ticket',
          required: true,
          status: 'pending_live_approval',
          reasons: [
            'operator_thesis_source:decision_packet',
            'research_preferred_mode:aggregate',
            'highest_actionable_mode:live',
          ],
          summary: 'Governed live execution requires an approval ticket before the live pathway can be materialized.',
        },
        operator_thesis: {
          present: true,
          source: 'decision_packet',
          probability_yes: 0.74,
          rationale: 'Operator thesis now moves the fair value away from the midpoint.',
          evidence_refs: ['decision:execution-preview'],
          summary: 'Decision packet favors a 74% Yes thesis.',
        },
        research_pipeline_trace: {
          pipeline_id: 'pipeline-execution-preview',
          pipeline_version: 'v2',
          preferred_mode: 'aggregate',
          oracle_family: 'llm_superforecaster',
          forecaster_count: 5,
          evidence_count: 8,
          source_refs: ['research:execution-preview'],
          summary: 'Aggregate research trace with five forecasters and eight evidence refs.',
        },
        market_regime_summary: 'Stable live regime.',
        primary_strategy_summary: 'Spread capture with operator approval.',
        strategy_summary: 'Compact strategy summary for live dashboard.',
        no_trade_baseline_summary: 'No-trade only wins if the edge collapses.',
      },
      source_refs: {
        run_detail: 'run-live-dashboard-1',
        execution_projection: 'run-live-dashboard-1:execution_projection',
        live_projected_path: 'run-live-dashboard-1:execution_projection#live',
        trade_intent_guard: 'run-live-dashboard-1:trade_intent_guard',
        multi_venue_execution: 'run-live-dashboard-1:multi_venue_execution',
      },
    })
  })

  it('requires two distinct approvals before materializing governed live execution', async () => {
    mocks.executePredictionMarketRunLive.mockReturnValue({
      gate_name: 'execution_projection_live_materialization',
      execution_mode: 'live',
      source_run_id: 'run-live-dashboard-1',
      materialized_run_id: 'run-live-dashboard-1__live_abcd1234',
      approved_intent_id: 'intent-live-dashboard-1',
      approved_by: ['approver-a', 'approver-b'],
      transport_mode: 'live',
      performed_live: true,
      live_execution_status: 'filled',
      receipt_summary: 'Live execution materialized from run-live-dashboard-1.',
      preflight_surface: {
        run_id: 'run-live-dashboard-1',
        live_status: 'ready',
        benchmark_promotion_ready: true,
        benchmark_promotion_blockers: [],
        benchmark_gate_blocks_live: false,
        benchmark_gate_live_block_reason: null,
        live_blocking_reasons: [],
        live_trade_intent_preview: {
          size_usd: 25,
        },
      },
      order_trace_audit: {
        transport_mode: 'live',
        live_submission_performed: true,
      },
    })

    const mod = await import('@/lib/prediction-markets/dashboard-live-intents')
    const created = mod.createPredictionDashboardLiveIntent({
      runId: 'run-live-dashboard-1',
      workspaceId: 7,
      actor: 'creator-a',
    })

    expect(created.approval_ticket).toMatchObject({
      ticket_id: 'run-live-dashboard-1:approval_ticket',
      status: 'pending_live_approval',
    })
    expect(created.operator_thesis).toMatchObject({
      present: true,
      source: 'decision_packet',
      probability_yes: 0.74,
    })
    expect(created.research_pipeline_trace).toMatchObject({
      pipeline_id: 'pipeline-execution-preview',
      preferred_mode: 'aggregate',
      oracle_family: 'llm_superforecaster',
      forecaster_count: 5,
    })
    expect(created.summary).toContain('Artifacts: Approval ticket: pending_live_approval.')
    expect(created.summary).toContain('Operator thesis: 74% yes via decision_packet.')
    expect(created.summary).toContain('Research pipeline trace: aggregate/llm_superforecaster.')

    const firstApproval = mod.approvePredictionDashboardLiveIntent({
      intentId: created.intent_id,
      workspaceId: 7,
      actor: 'approver-a',
    })
    expect(firstApproval.status).toBe('pending_second_approval')
    expect(firstApproval.summary).toContain('Artifacts: Approval ticket: pending_live_approval.')
    expect(mocks.executePredictionMarketRunLive).not.toHaveBeenCalled()

    const secondApproval = mod.approvePredictionDashboardLiveIntent({
      intentId: created.intent_id,
      workspaceId: 7,
      actor: 'approver-b',
    })

    expect(mocks.executePredictionMarketRunLive).toHaveBeenCalledWith({
      runId: 'run-live-dashboard-1',
      workspaceId: 7,
      actor: 'approver-b',
      approvedIntentId: created.intent_id,
      approvedBy: ['approver-a', 'approver-b'],
    })
    expect(secondApproval.status).toBe('executed_live')
    expect(secondApproval.execution_result).toMatchObject({
      status: 'executed_live',
      transport_mode: 'live',
      performed_live: true,
      live_execution_status: 'filled',
      receipt_summary: 'Live execution materialized from run-live-dashboard-1.',
    })
  })

  it('marks the intent as failed when governed live execution does not actually submit to the venue', async () => {
    mocks.executePredictionMarketRunLive.mockReturnValue({
      gate_name: 'execution_projection_live_materialization',
      execution_mode: 'live',
      source_run_id: 'run-live-dashboard-1',
      materialized_run_id: 'run-live-dashboard-1__live_failed',
      approved_intent_id: 'intent-live-dashboard-2',
      approved_by: ['approver-a', 'approver-b'],
      transport_mode: 'live',
      performed_live: false,
      live_execution_status: 'attempted_live_not_performed',
      receipt_summary: 'Live execution request was processed, but venue submission was not performed.',
      preflight_surface: {
        run_id: 'run-live-dashboard-1',
        live_status: 'ready',
        benchmark_promotion_ready: true,
        benchmark_promotion_blockers: [],
        benchmark_gate_blocks_live: false,
        benchmark_gate_live_block_reason: null,
        live_blocking_reasons: [],
      },
      order_trace_audit: {
        transport_mode: 'live',
        live_submission_performed: false,
      },
    })

    const mod = await import('@/lib/prediction-markets/dashboard-live-intents')
    const created = mod.createPredictionDashboardLiveIntent({
      runId: 'run-live-dashboard-1',
      workspaceId: 7,
      actor: 'creator-a',
    })

    expect(created.approval_ticket?.status).toBe('pending_live_approval')
    expect(created.operator_thesis?.summary).toContain('Decision packet favors a 74% Yes thesis.')
    expect(created.research_pipeline_trace?.summary).toContain('Aggregate research trace')

    mod.approvePredictionDashboardLiveIntent({
      intentId: created.intent_id,
      workspaceId: 7,
      actor: 'approver-a',
    })
    const finalized = mod.approvePredictionDashboardLiveIntent({
      intentId: created.intent_id,
      workspaceId: 7,
      actor: 'approver-b',
    })

    expect(finalized.status).toBe('execution_failed')
    expect(finalized.execution_result).toMatchObject({
      status: 'execution_failed',
      performed_live: false,
      live_execution_status: 'attempted_live_not_performed',
      receipt_summary: 'Live execution request was processed, but venue submission was not performed.',
    })
  })
})
