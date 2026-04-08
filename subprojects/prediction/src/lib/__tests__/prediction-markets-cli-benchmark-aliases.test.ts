import { createServer } from 'node:http'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { resolvePredictionCliPath } from './helpers/prediction-cli-path'

const execFileAsync = promisify(execFile)
const CLI = resolvePredictionCliPath()

function makeBenchmarkOnlyPayload() {
  return {
    run_id: 'run-benchmark-001',
    workspace_id: 1,
    venue: 'polymarket',
    mode: 'advise',
    market_id: 'mkt-benchmark-001',
    market_slug: 'mkt-benchmark-001',
    status: 'completed',
    recommendation: 'bet',
    benchmark_gate_summary:
      'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
    benchmark_uplift_bps: 1100,
    benchmark_gate_status: 'preview_only',
    benchmark_promotion_status: 'unproven',
    benchmark_promotion_ready: false,
    benchmark_preview_available: true,
    benchmark_promotion_evidence: 'unproven',
    benchmark_promotion_gate_kind: 'preview_only',
    benchmark_gate_blockers: ['out_of_sample_unproven'],
    benchmark_gate_reasons: ['out_of_sample_unproven'],
    research_benchmark_gate_summary:
      'benchmark gate: market_only=0.4000 aggregate=0.4100 forecast=0.4200 uplift_vs_market_only=200bps uplift_vs_aggregate=100bps status=blocked_by_abstention promotion=blocked ready=no preview=no evidence=local_benchmark blockers=research_blocker out_of_sample=local_benchmark',
    research_benchmark_uplift_bps: 200,
    research_benchmark_gate_status: 'blocked_by_abstention',
    research_benchmark_promotion_status: 'blocked',
    research_benchmark_promotion_ready: true,
    research_benchmark_preview_available: false,
    research_benchmark_promotion_evidence: 'local_benchmark',
    research_promotion_gate_kind: 'local_benchmark',
    research_benchmark_gate_blockers: ['research_blocker'],
    research_benchmark_gate_reasons: ['research_reason'],
  }
}

function makeCanonicalSummaryPriorityPayload() {
  return {
    run_id: 'run-benchmark-summary-priority-001',
    workspace_id: 1,
    venue: 'polymarket',
    mode: 'advise',
    market_id: 'mkt-benchmark-summary-priority-001',
    market_slug: 'mkt-benchmark-summary-priority-001',
    status: 'completed',
    recommendation: 'bet',
    benchmark_promotion_summary: 'benchmark-only canonical summary should win',
    research_benchmark_gate_status: 'blocked_by_abstention',
    research_benchmark_promotion_status: 'blocked',
    research_benchmark_promotion_ready: false,
    research_benchmark_preview_available: true,
    research_benchmark_promotion_evidence: 'unproven',
    research_benchmark_evidence_level: 'benchmark_preview',
    research_promotion_gate_kind: 'preview_only',
    research_benchmark_promotion_blocker_summary: 'research blocker should not win',
    research_benchmark_promotion_summary: 'research blocker should not win',
    research_benchmark_gate_blockers: ['research_blocker'],
    research_benchmark_gate_reasons: ['research_reason'],
    research_benchmark_verdict: 'blocked_by_abstention',
  }
}

describe('prediction markets CLI benchmark aliases', () => {
  let server: ReturnType<typeof createServer>
  let baseUrl = ''
  const payload = makeBenchmarkOnlyPayload()
  const canonicalSummaryPayload = makeCanonicalSummaryPriorityPayload()

  beforeAll(async () => {
    server = createServer((req, res) => {
      const url = new URL(req.url ?? '/', 'http://127.0.0.1')

      if (req.method === 'GET' && url.pathname === '/api/v1/prediction-markets/runs/run-benchmark-001') {
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(JSON.stringify(payload))
        return
      }

      if (req.method === 'GET' && url.pathname === '/api/v1/prediction-markets/runs/run-benchmark-summary-priority-001') {
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(JSON.stringify(canonicalSummaryPayload))
        return
      }

      if (req.method === 'GET' && url.pathname === '/api/v1/prediction-markets/runs') {
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(JSON.stringify({ runs: [payload] }))
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

  it('reads benchmark aliases on run and runs while preferring benchmark_* over research_* aliases', async () => {
    const runResult = await execFileAsync(
      process.execPath,
      [
        CLI,
        'prediction-markets',
        'run',
        '--run-id',
        'run-benchmark-001',
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

    expect(runResult.stdout).toContain(
      'benchmark: status=preview_only promotion=unproven ready=no uplift=1100bps blockers=out_of_sample_unproven reasons=out_of_sample_unproven',
    )
    expect(runResult.stdout).toContain(
      'benchmark_evidence: preview=yes promotion_evidence=unproven promotion_status=unproven ready=no out_of_sample=unproven',
    )
    expect(runResult.stdout).toContain(
      'benchmark_state: verdict=preview_only promotion_gate_kind=preview_only ready=no evidence_level=benchmark_preview promotion_blocker_summary=out_of_sample_unproven',
    )
    expect(runResult.stdout).not.toContain('research:')
    expect(runResult.stdout).not.toContain('promotion=blocked')
    expect(runResult.stdout).not.toContain('verdict=blocked_by_abstention')

    const runsResult = await execFileAsync(
      process.execPath,
      [
        CLI,
        'prediction-markets',
        'runs',
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

    expect(runsResult.stdout).toContain(
      'benchmark: status=preview_only promotion=unproven ready=no uplift=1100bps blockers=out_of_sample_unproven reasons=out_of_sample_unproven',
    )
    expect(runsResult.stdout).toContain(
      'benchmark_evidence: preview=yes promotion_evidence=unproven promotion_status=unproven ready=no out_of_sample=unproven',
    )
    expect(runsResult.stdout).toContain(
      'benchmark_state: verdict=preview_only promotion_gate_kind=preview_only ready=no evidence_level=benchmark_preview promotion_blocker_summary=out_of_sample_unproven',
    )
    expect(runsResult.stdout).not.toContain('research:')
    expect(runsResult.stdout).not.toContain('promotion=blocked')
    expect(runsResult.stdout).not.toContain('verdict=blocked_by_abstention')
  })

  it('prefers benchmark_promotion_summary over conflicting research blocker summaries in benchmark_state', async () => {
    const runResult = await execFileAsync(
      process.execPath,
      [
        CLI,
        'prediction-markets',
        'run',
        '--run-id',
        'run-benchmark-summary-priority-001',
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

    expect(runResult.stdout).toContain(
      'benchmark_state: verdict=blocked_by_abstention promotion_gate_kind=preview_only ready=no evidence_level=benchmark_preview promotion_blocker_summary=benchmark-only canonical summary should win',
    )
    expect(runResult.stdout).not.toContain('promotion_blocker_summary=research blocker should not win')
  })
})
