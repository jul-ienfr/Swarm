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

const liveSurfaceSummary =
  'Live surface is ready using execution_projection.selected_path=live; it remains preflight-only and threads execution_readiness plus multi_venue_execution through the canonical execution_projection preview.'

describe('prediction markets CLI live', () => {
  let server: ReturnType<typeof createServer>
  let baseUrl = ''
  let lastRequestBody: Record<string, unknown> | null = null

  beforeAll(async () => {
    server = createServer(async (req, res) => {
      const url = new URL(req.url ?? '/', 'http://127.0.0.1')

      if (req.method === 'POST' && url.pathname === '/api/v1/prediction-markets/runs/run-live-001/live') {
        const body = await new Promise<string>((resolve) => {
          let raw = ''
          req.setEncoding('utf8')
          req.on('data', (chunk) => {
            raw += chunk
          })
          req.on('end', () => resolve(raw))
        })
        lastRequestBody = body ? JSON.parse(body) as Record<string, unknown> : null
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(JSON.stringify({
          gate_name: 'execution_projection_live',
          preflight_only: true,
          run_id: 'run-live-001',
          workspace_id: 1,
          surface_mode: 'live',
          live_status: 'ready',
          live_blocking_reasons: [],
          summary: liveSurfaceSummary,
          ...makeResearchHints(),
          source_refs: {
            run_detail: 'run-live-001',
            execution_projection: 'run-live-001:execution_projection',
            live_projected_path: 'run-live-001:execution_projection#live',
            trade_intent_guard: 'run-live-001:trade_intent_guard',
            multi_venue_execution: 'run-live-001:multi_venue_execution',
          },
          live_path: {
            path: 'live',
            requested_mode: 'live',
            effective_mode: 'live',
            status: 'ready',
            allowed: true,
            blockers: [],
            warnings: [],
            reason_summary: 'Live projection is ready using the canonical execution_projection preview.',
            simulation: {
              expected_fill_confidence: 0.94,
              expected_slippage_bps: 15,
              stale_quote_risk: 'low',
              quote_age_ms: 120,
              notes: [],
              shadow_arbitrage: null,
            },
            trade_intent_preview: {
              size_usd: 20,
              limit_price: 0.46,
              time_in_force: 'ioc',
              max_slippage_bps: 15,
            },
            canonical_trade_intent_preview: {
              size_usd: 20,
              limit_price: 0.46,
              time_in_force: 'ioc',
              max_slippage_bps: 15,
            },
            sizing_signal: {
              canonical_size_usd: 20,
              preview_size_usd: 20,
              source: 'trade_intent_preview',
              time_in_force: 'ioc',
            },
            shadow_arbitrage_signal: null,
          },
          live_trade_intent_preview: {
            size_usd: 20,
            limit_price: 0.46,
            time_in_force: 'ioc',
            max_slippage_bps: 15,
          },
          live_trade_intent_preview_source: 'canonical_trade_intent_preview',
          execution_projection_selected_preview: {
            size_usd: 20,
          },
          execution_projection_requested_path: 'live',
          execution_projection_selected_path: 'live',
          execution_projection_selected_path_status: 'ready',
          execution_projection_selected_path_effective_mode: 'live',
          execution_projection_verdict: 'allowed',
          execution_projection_highest_safe_requested_mode: 'live',
          execution_projection_recommended_effective_mode: 'live',
          execution_projection_manual_review_required: false,
          execution_projection_ttl_ms: 30000,
          execution_projection_expires_at: '2026-04-08T00:00:30.000Z',
          execution_projection_blocking_reasons: [],
          execution_projection_downgrade_reasons: [],
          execution_projection_summary:
            'requested live, selected live; gate execution_projection; preflight only. live is benchmark-gated and execution_projection-first.',
          execution_projection_preflight_summary: {
            gate_name: 'execution_projection',
            preflight_only: true,
            requested_path: 'live',
            selected_path: 'live',
            verdict: 'allowed',
            highest_safe_requested_mode: 'live',
            recommended_effective_mode: 'live',
            manual_review_required: false,
            ttl_ms: 30000,
            expires_at: '2026-04-08T00:00:30.000Z',
            counts: { total: 3, eligible: 3, ready: 3, degraded: 0, blocked: 0 },
            basis: {
              uses_execution_readiness: true,
              uses_compliance: true,
              uses_capital: true,
              uses_reconciliation: true,
              capital_status: 'attached',
              reconciliation_status: 'attached',
            },
            source_refs: ['run-live-001:pipeline_guard'],
            blockers: [],
            downgrade_reasons: [],
            summary: 'Requested live; selected live. live is benchmark-gated and execution_projection-first.',
          },
          execution_projection: {
            gate_name: 'execution_projection',
            preflight_only: true,
            requested_path: 'live',
            selected_path: 'live',
            verdict: 'allowed',
            highest_safe_requested_mode: 'live',
            recommended_effective_mode: 'live',
            manual_review_required: false,
            ttl_ms: 30000,
            basis: {
              uses_execution_readiness: true,
              uses_compliance: true,
              uses_capital: true,
              uses_reconciliation: true,
              capital_status: 'attached',
              reconciliation_status: 'attached',
              canonical_gate: {
                gate_name: 'execution_projection',
                single_runtime_gate: true,
                enforced_for_modes: ['paper', 'shadow', 'live'],
              },
            },
            projected_paths: {
              live: {
                status: 'ready',
                effective_mode: 'live',
                canonical_trade_intent_preview: {
                  size_usd: 20,
                  limit_price: 0.46,
                  time_in_force: 'ioc',
                  max_slippage_bps: 15,
                },
                sizing_signal: {
                  canonical_size_usd: 20,
                  preview_size_usd: 20,
                  source: 'trade_intent_preview',
                  time_in_force: 'ioc',
                },
              },
            },
            preflight_summary: {
              gate_name: 'execution_projection',
              preflight_only: true,
              requested_path: 'live',
              selected_path: 'live',
              verdict: 'allowed',
              highest_safe_requested_mode: 'live',
              recommended_effective_mode: 'live',
              manual_review_required: false,
              ttl_ms: 30000,
              expires_at: '2026-04-08T00:00:30.000Z',
              counts: { total: 3, eligible: 3, ready: 3, degraded: 0, blocked: 0 },
              basis: {
                uses_execution_readiness: true,
                uses_compliance: true,
                uses_capital: true,
                uses_reconciliation: true,
                capital_status: 'attached',
                reconciliation_status: 'attached',
              },
              source_refs: ['run-live-001:pipeline_guard'],
              blockers: [],
              downgrade_reasons: [],
              summary: 'Requested live; selected live. live is benchmark-gated and execution_projection-first.',
            },
            summary:
              'requested live, selected live; gate execution_projection; preflight only. live is benchmark-gated and execution_projection-first.',
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

  it('calls the live route and prints the compact live surface summary', async () => {
    const result = await execFileAsync(
      process.execPath,
      [
        CLI,
        'prediction-markets',
        'live',
        '--run-id',
        'run-live-001',
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
    expect(result.stdout).toContain('live_surface: status=ready')
    expect(result.stdout).toContain('live_surface: status=ready gate=execution_projection_live preflight=yes run_id=run-live-001 requested=live path_status=ready effective_mode=live selected=live research_mode=research_driven research_origin=research_driven blockers=0 size=20')
    expect(result.stdout).toContain('source=canonical_trade_intent_preview')
    expect(result.stdout).toContain(`summary="${liveSurfaceSummary}"`)
    expect(result.stdout).toContain(
      'research: mode=research_driven pipeline=research-pipeline-runtime v=v3 forecasters=2 weighted=0.67 coverage=0.83 compare=aggregate abstention=structured-abstention-v1 blocks=no forecast=0.69 summary="Preferred mode: aggregate."',
    )
    expect(result.stdout).toContain('research_origin: origin=research_driven abstention_effect=clear')
    expect(result.stdout).toContain(
      'benchmark: status=preview_only promotion=unproven ready=no uplift=1100bps blockers=out_of_sample_unproven reasons=out_of_sample_unproven',
    )
    expect(result.stdout).toContain(
      'benchmark_evidence: preview=yes promotion_evidence=unproven promotion_status=unproven ready=no out_of_sample=unproven',
    )
    expect(result.stdout).toContain(
      'benchmark_state: verdict=preview_only promotion_gate_kind=preview_only ready=no evidence_level=benchmark_preview promotion_blocker_summary=out_of_sample_unproven',
    )
    expect(result.stdout).toContain('execution_projection: requested=live selected=live verdict=allowed')
    expect(result.stdout).toContain('live:ready')
  })

  it('prints the benchmark gate summary with the dedicated flag', async () => {
    const result = await execFileAsync(
      process.execPath,
      [
        CLI,
        'prediction-markets',
        'live',
        '--run-id',
        'run-live-001',
        '--benchmark-summary',
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

    expect(result.stdout).toContain(
      'benchmark: status=preview_only promotion=unproven ready=no uplift=1100bps blockers=out_of_sample_unproven reasons=out_of_sample_unproven',
    )
    expect(result.stdout).toContain(
      'benchmark_evidence: preview=yes promotion_evidence=unproven promotion_status=unproven ready=no out_of_sample=unproven',
    )
    expect(result.stdout).toContain(
      'benchmark_state: verdict=preview_only promotion_gate_kind=preview_only ready=no evidence_level=benchmark_preview promotion_blocker_summary=out_of_sample_unproven',
    )
  })

  it('sends execution_mode=live when requested explicitly', async () => {
    lastRequestBody = null

    await execFileAsync(
      process.execPath,
      [
        CLI,
        'prediction-markets',
        'live',
        '--run-id',
        'run-live-001',
        '--execution-mode',
        'live',
        '--json',
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

    expect(lastRequestBody).toMatchObject({
      run_id: 'run-live-001',
      execution_mode: 'live',
    })
  })

  it('returns live_status under data in json mode', async () => {
    const result = await execFileAsync(
      process.execPath,
      [
        CLI,
        'prediction-markets',
        'live',
        '--run-id',
        'run-live-001',
        '--json',
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

    const parsed = JSON.parse(result.stdout)
    expect(parsed.ok).toBe(true)
    expect(parsed.status).toBe(200)
    expect(parsed.data).toMatchObject({
      gate_name: 'execution_projection_live',
      surface_mode: 'live',
      live_status: 'ready',
      execution_projection_selected_preview: expect.objectContaining({
        size_usd: 20,
      }),
      live_trade_intent_preview: expect.objectContaining({
        size_usd: 20,
      }),
    })
  })
})
