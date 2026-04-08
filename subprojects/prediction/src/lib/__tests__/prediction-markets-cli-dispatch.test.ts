import { createServer } from 'node:http'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { resolvePredictionCliPath } from './helpers/prediction-cli-path'

const execFileAsync = promisify(execFile)
const CLI = resolvePredictionCliPath()

function makeResearchHints() {
  return {
    research_pipeline_id: 'research-pipeline-runtime',
    research_pipeline_version: 'v3',
    research_forecaster_count: 2,
    research_weighted_probability_yes: 0.67,
    research_weighted_coverage: 0.83,
    research_compare_preferred_mode: 'aggregate',
    research_compare_summary: 'Preferred mode: aggregate.',
    research_abstention_policy_version: 'structured-abstention-v1',
    research_abstention_policy_blocks_forecast: false,
    research_forecast_probability_yes_hint: 0.69,
    research_benchmark_gate_summary:
      'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no blockers=out_of_sample_unproven out_of_sample=unproven',
    research_benchmark_uplift_bps: 1100,
    research_benchmark_gate_status: 'preview_only',
    research_benchmark_promotion_status: 'unproven',
    research_benchmark_promotion_ready: false,
    research_benchmark_preview_available: true,
    research_benchmark_promotion_evidence: 'unproven',
    research_promotion_gate_kind: 'preview_only',
    research_benchmark_gate_blockers: ['out_of_sample_unproven'],
    research_benchmark_gate_reasons: ['out_of_sample_unproven'],
  }
}

describe('prediction markets CLI dispatch', () => {
  let server: ReturnType<typeof createServer>
  let baseUrl = ''

  beforeAll(async () => {
    server = createServer((req, res) => {
      const url = new URL(req.url ?? '/', 'http://127.0.0.1')

      if (req.method === 'POST' && url.pathname === '/api/v1/prediction-markets/runs/run-dispatch-001/dispatch') {
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(JSON.stringify({
          gate_name: 'execution_projection_dispatch',
          preflight_only: true,
          run_id: 'run-dispatch-001',
          workspace_id: 1,
          dispatch_status: 'ready',
          dispatch_blocking_reasons: [],
          summary: 'Dispatch preflight is ready for paper using the canonical execution_projection preview.',
          ...makeResearchHints(),
          source_refs: {
            run_detail: 'run-dispatch-001',
            execution_projection: 'run-dispatch-001:execution_projection',
            trade_intent_guard: 'run-dispatch-001:trade_intent_guard',
            multi_venue_execution: null,
          },
          execution_projection_requested_path: 'live',
          execution_projection_selected_path: 'paper',
          execution_projection_selected_path_status: 'ready',
          execution_projection_selected_path_effective_mode: 'paper',
          execution_projection_selected_path_reason_summary: 'paper remains the safest mode.',
          execution_projection_verdict: 'downgraded',
          execution_projection_highest_safe_requested_mode: 'paper',
          execution_projection_recommended_effective_mode: 'paper',
          execution_projection_manual_review_required: true,
          execution_projection_ttl_ms: 30000,
          execution_projection_expires_at: '2026-04-08T00:00:30.000Z',
          execution_projection_blocking_reasons: [],
          execution_projection_downgrade_reasons: ['capital_ledger_unavailable'],
          execution_projection_summary: 'requested live, selected paper; gate execution_projection; preflight only. requested live, selected paper, recommended paper',
          ...makeResearchHints(),
          execution_projection_preflight_summary: {
            gate_name: 'execution_projection',
            preflight_only: true,
            requested_path: 'live',
            selected_path: 'paper',
            verdict: 'downgraded',
            highest_safe_requested_mode: 'paper',
            recommended_effective_mode: 'paper',
            manual_review_required: true,
            ttl_ms: 30000,
            expires_at: '2026-04-08T00:00:30.000Z',
            counts: { total: 3, eligible: 1, ready: 1, degraded: 0, blocked: 2 },
            basis: {
              uses_execution_readiness: true,
              uses_compliance: true,
              uses_capital: false,
              uses_reconciliation: false,
              capital_status: 'unavailable',
              reconciliation_status: 'unavailable',
            },
            source_refs: ['run-dispatch-001:pipeline_guard'],
            blockers: [],
            downgrade_reasons: ['capital_ledger_unavailable'],
            summary: 'Requested live; selected paper.',
          },
          execution_projection_selected_preview: {
            size_usd: 35,
            limit_price: 0.48,
            time_in_force: 'day',
            max_slippage_bps: 30,
          },
          execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
          execution_projection_selected_path_canonical_size_usd: 35,
          execution_projection_selected_path_shadow_signal_present: false,
          execution_projection: {
            gate_name: 'execution_projection',
            preflight_only: true,
            requested_path: 'live',
            selected_path: 'paper',
            verdict: 'downgraded',
            highest_safe_requested_mode: 'paper',
            recommended_effective_mode: 'paper',
            manual_review_required: true,
            ttl_ms: 30000,
            basis: {
              uses_execution_readiness: true,
              uses_compliance: true,
              uses_capital: false,
              uses_reconciliation: false,
              capital_status: 'unavailable',
              reconciliation_status: 'unavailable',
              canonical_gate: {
                gate_name: 'execution_projection',
                single_runtime_gate: true,
                enforced_for_modes: ['paper', 'shadow', 'live'],
              },
            },
            projected_paths: {
              paper: {
                status: 'ready',
                effective_mode: 'paper',
                canonical_trade_intent_preview: {
                  size_usd: 35,
                  limit_price: 0.48,
                  time_in_force: 'day',
                  max_slippage_bps: 30,
                },
                sizing_signal: {
                  canonical_size_usd: 35,
                  preview_size_usd: 35,
                  source: 'trade_intent_preview',
                  time_in_force: 'day',
                },
              },
            },
            preflight_summary: {
              gate_name: 'execution_projection',
              preflight_only: true,
              requested_path: 'live',
              selected_path: 'paper',
              verdict: 'downgraded',
              highest_safe_requested_mode: 'paper',
              recommended_effective_mode: 'paper',
              manual_review_required: true,
              ttl_ms: 30000,
              expires_at: '2026-04-08T00:00:30.000Z',
              counts: { total: 3, eligible: 1, ready: 1, degraded: 0, blocked: 2 },
              basis: {
                uses_execution_readiness: true,
                uses_compliance: true,
                uses_capital: false,
                uses_reconciliation: false,
                capital_status: 'unavailable',
                reconciliation_status: 'unavailable',
              },
              source_refs: ['run-dispatch-001:pipeline_guard'],
              blockers: [],
              downgrade_reasons: ['capital_ledger_unavailable'],
              summary: 'Requested live; selected paper.',
            },
            summary: 'requested live, selected paper; gate execution_projection; preflight only. requested live, selected paper, recommended paper',
          },
        }))
        return
      }

      res.writeHead(404, { 'content-type': 'application/json' })
      res.end(JSON.stringify({ error: 'not_found' }))
    })

    await new Promise<void>((resolve) => {
      server.listen(0, '127.0.0.1', () => {
        const address = server.address()
        if (address && typeof address === 'object') {
          baseUrl = `http://127.0.0.1:${address.port}`
        }
        resolve()
      })
    })
  })

  afterAll(async () => {
    await new Promise<void>((resolve) => {
      server.close(() => resolve())
    })
  })

  it('calls the dispatch route and prints execution projection summaries', async () => {
    const result = await execFileAsync(
      process.execPath,
      [
        CLI,
        'prediction-markets',
        'dispatch',
        '--run-id',
        'run-dispatch-001',
        '--execution-pathways-summary',
        '--url',
        baseUrl,
      ],
      {
        env: {
          ...process.env,
          MC_URL: baseUrl,
        },
        timeout: 10_000,
      },
    )

    expect(result.stdout).toContain('OK 200 POST')
    expect(result.stdout).toContain('dispatch_preflight: status=ready')
    expect(result.stdout).toContain(
      'research: mode=research_driven pipeline=research-pipeline-runtime v=v3 forecasters=2 weighted=0.67 coverage=0.83 compare=aggregate abstention=structured-abstention-v1 blocks=no forecast=0.69 summary="Preferred mode: aggregate."',
    )
    expect(result.stdout).toContain('research_origin: origin=research_driven abstention_effect=clear')
    expect(result.stdout).toContain('dispatch_surface: status=ready gate=execution_projection_dispatch preflight=yes run_id=run-dispatch-001 requested=live path_status=ready effective_mode=paper selected=paper research_mode=research_driven research_origin=research_driven blockers=0')
    expect(result.stdout).toContain(
      'benchmark: status=preview_only promotion=unproven ready=no uplift=1100bps blockers=out_of_sample_unproven reasons=out_of_sample_unproven',
    )
    expect(result.stdout).toContain(
      'benchmark_evidence: preview=yes promotion_evidence=unproven promotion_status=unproven ready=no out_of_sample=unproven',
    )
    expect(result.stdout).toContain(
      'benchmark_state: verdict=preview_only promotion_gate_kind=preview_only ready=no evidence_level=benchmark_preview promotion_blocker_summary=out_of_sample_unproven',
    )
    expect(result.stdout).toContain('execution_projection: requested=live selected=paper verdict=downgraded')
    expect(result.stdout).toContain('highest_safe=paper recommended=paper manual_review=yes')
    expect(result.stdout).toContain('basis=readiness,compliance capital=unavailable reconciliation=unavailable')
    expect(result.stdout).toContain('projected_paths=paper:ready')
    expect(result.stdout).toContain('execution_projection selected preview: size=35')
    expect(result.stdout).toContain('source=canonical_trade_intent_preview')
    expect(result.stdout).toContain('limit=0.48 tif=day slip=30bps')
    expect(result.stdout).toContain('execution_projection preflight: gate=execution_projection verdict=downgraded requested=live selected=paper')
    expect(result.stdout).toContain('highest_safe=paper recommended=paper manual_review=yes ttl_ms=30000')
  })
})
