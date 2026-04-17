import { createServer } from 'node:http'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { afterAll, beforeAll, describe, expect, test } from 'vitest'
import { resolvePredictionCliPath } from './helpers/prediction-cli-path'

const execFileAsync = promisify(execFile)
const CLI = resolvePredictionCliPath()

describe('prediction markets CLI research signal injection', () => {
  let baseUrl = ''
  let server: ReturnType<typeof createServer>

  function makePredictionRun(input: { blocksForecast: boolean; recommendation: 'wait' | 'bet' | 'no_trade' }) {
    return {
      ok: true,
      prediction_run: {
        run_id: input.blocksForecast ? 'run-research-blocked-001' : 'run-research-001',
        recommendation: input.recommendation,
        research_pipeline_id: 'polymarket-research-pipeline',
        research_pipeline_version: 'poly-025-research-v1',
        research_forecaster_count: 2,
        research_weighted_probability_yes: 0.62,
        research_weighted_coverage: 0.85,
        research_compare_preferred_mode: input.blocksForecast ? 'abstention' : 'aggregate',
        research_compare_summary: input.blocksForecast ? 'Preferred mode: abstention.' : 'Preferred mode: aggregate.',
        research_abstention_policy_version: 'structured-abstention-v1',
        research_abstention_policy_blocks_forecast: input.blocksForecast,
        research_forecast_probability_yes_hint: 0.62,
        research_runtime_summary: input.blocksForecast
          ? 'research: mode=research_driven pipeline=polymarket-research-pipeline version=poly-025-research-v1 forecasters=2 weighted_yes=0.62 coverage=0.85 preferred=abstention abstention=structured-abstention-v1 blocks_forecast=yes forecast_hint=0.62'
          : 'research: mode=research_driven pipeline=polymarket-research-pipeline version=poly-025-research-v1 forecasters=2 weighted_yes=0.62 coverage=0.85 preferred=aggregate abstention=structured-abstention-v1 blocks_forecast=no forecast_hint=0.62',
        research_benchmark_gate_status: 'preview_only',
        research_benchmark_promotion_status: 'unproven',
        research_benchmark_promotion_ready: false,
        research_benchmark_preview_available: true,
        research_benchmark_promotion_evidence: 'unproven',
        research_promotion_gate_kind: 'preview_only',
        research_benchmark_gate_blockers: ['out_of_sample_unproven'],
        research_benchmark_gate_reasons: ['out_of_sample_unproven'],
        research_benchmark_gate_summary:
          'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no blockers=out_of_sample_unproven out_of_sample=unproven',
        research_benchmark_uplift_bps: 1100,
        timesfm_requested_mode: 'auto',
        timesfm_effective_mode: 'auto',
        timesfm_selected_lane: 'microstructure',
        timesfm_health: 'healthy',
        timesfm_summary: 'timesfm: mode=auto health=healthy selected=microstructure backend=vendor_torch summary="TimesFM requested auto on microstructure, event_probability; selected=microstructure; TimesFM healthy; ready_lanes=2/2 backend=vendor_torch dependency=vendor_import_available."',
      },
    }
  }

  beforeAll(async () => {
    server = createServer((req, res) => {
      const chunks: Buffer[] = []

      req.on('data', (chunk: Buffer) => {
        chunks.push(chunk)
      })

      req.on('end', () => {
        const bodyText = Buffer.concat(chunks).toString('utf8')
        const body = bodyText ? JSON.parse(bodyText) : undefined

        ;(server as any).lastRequest = {
          method: req.method,
          url: req.url,
          headers: req.headers,
          body,
        }

        const predictionRun =
          body?.market_id === '540817'
            ? makePredictionRun({ blocksForecast: true, recommendation: 'wait' })
            : makePredictionRun({ blocksForecast: false, recommendation: 'bet' })

        const requestContract = {
          request_mode: body?.request_mode ?? 'predict',
          response_variant: body?.response_variant ?? 'standard',
          request_variant_tags: body?.variant_tags ?? [],
        }

        if (
          req.method === 'POST' &&
          (req.url === '/api/v1/prediction-markets/advise' || req.url === '/api/v1/prediction-markets/replay')
        ) {
          res.writeHead(200, { 'content-type': 'application/json' })
          res.end(JSON.stringify({
            ...requestContract,
            ...predictionRun,
            prediction_run: {
              ...predictionRun.prediction_run,
              ...requestContract,
            },
          }))
          return
        }

        res.writeHead(404, { 'content-type': 'application/json' })
        res.end(JSON.stringify({ error: 'not_found' }))
      })
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
    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) reject(error)
        else resolve()
      })
    })
  })

  test('injects research_signals into the advise body and prints the opt-in summaries', async () => {
    const firstSignal = {
      kind: 'news',
      title: 'Wire update',
      summary: 'Fresh cross-check',
    }
    const secondSignal = {
      kind: 'manual_note',
      note: 'Desk stays constructive',
    }

    const run = execFileAsync(
      'node',
      [
        CLI,
        'prediction-markets',
        'advise',
        '--market-id',
        '540816',
        '--request-mode',
        'predict-deep',
        '--response-variant',
        'research-heavy',
        '--variant-tags',
        JSON.stringify(['polfish', 'mirofish-pm']),
        '--research-signals',
        JSON.stringify([firstSignal]),
        '--research-signal',
        JSON.stringify(secondSignal),
        '--research-signals-summary',
        '--research-summary',
        '--url',
        baseUrl,
      ],
      {
        env: {
          ...process.env,
          MC_URL: baseUrl,
        },
        timeout: 10000,
      },
    )

    const { stdout } = await run
    const lastRequest = (server as any).lastRequest

    expect(lastRequest).toBeDefined()
    expect(lastRequest.method).toBe('POST')
    expect(lastRequest.url).toBe('/api/v1/prediction-markets/advise')
    expect(lastRequest.body).toMatchObject({
      market_id: '540816',
      request_mode: 'predict-deep',
      response_variant: 'research-heavy',
      variant_tags: ['polfish', 'mirofish-pm'],
    })
    expect(lastRequest.body.research_signals).toEqual([firstSignal, secondSignal])
    expect(stdout).toContain('Injected research signals: 2')
    expect(stdout).toContain(
      'research: mode=research_driven pipeline=polymarket-research-pipeline v=poly-025-research-v1 forecasters=2 weighted=0.62 coverage=0.85 compare=aggregate abstention=structured-abstention-v1 blocks=no forecast=0.62 summary="Preferred mode: aggregate."',
    )
    expect(stdout).toContain('research_origin: origin=research_driven recommendation=bet abstention_effect=clear')
    expect(stdout).toContain('timesfm: requested=auto effective=auto lane=microstructure health=healthy')
    expect(stdout).toContain(
      'benchmark: status=preview_only promotion=unproven ready=no uplift=1100bps blockers=out_of_sample_unproven reasons=out_of_sample_unproven',
    )
    expect(stdout).toContain(
      'benchmark_evidence: preview=yes promotion_evidence=unproven promotion_status=unproven ready=no out_of_sample=unproven',
    )
    expect(stdout).toContain(
      'benchmark_state: verdict=preview_only promotion_gate_kind=preview_only ready=no evidence_level=benchmark_preview promotion_blocker_summary=out_of_sample_unproven',
    )
    expect(stdout).toContain(
      'request_contract: request_mode=predict-deep response_variant=research-heavy variant_tags=polfish|mirofish-pm',
    )
    expect(stdout).toContain('"ok": true')
  })

  test('prints the abstention flip explicitly when the policy blocks the forecast', async () => {
    const run = execFileAsync(
      'node',
      [
        CLI,
        'prediction-markets',
        'advise',
        '--market-id',
        '540817',
        '--research-signals',
        JSON.stringify([{ kind: 'manual_note', note: 'Hold until review clears' }]),
        '--research-summary',
        '--url',
        baseUrl,
      ],
      {
        env: {
          ...process.env,
          MC_URL: baseUrl,
        },
        timeout: 10000,
      },
    )

    const { stdout } = await run
    expect(stdout).toContain('research_origin: origin=research_driven recommendation=wait abstention_effect=flipped_to_wait')
  })

  test('prints the benchmark gate summary on replay with the dedicated flag', async () => {
    const run = await execFileAsync(
      'node',
      [
        CLI,
        'prediction-markets',
        'replay',
        '--run-id',
        'run-research-001',
        '--benchmark-summary',
        '--url',
        baseUrl,
      ],
      {
        env: {
          ...process.env,
          MC_URL: baseUrl,
        },
        timeout: 10000,
      },
    )

    expect(run.stdout).toContain(
      'benchmark: status=preview_only promotion=unproven ready=no uplift=1100bps blockers=out_of_sample_unproven reasons=out_of_sample_unproven',
    )
    expect(run.stdout).toContain(
      'benchmark_evidence: preview=yes promotion_evidence=unproven promotion_status=unproven ready=no out_of_sample=unproven',
    )
    expect(run.stdout).toContain(
      'benchmark_state: verdict=preview_only promotion_gate_kind=preview_only ready=no evidence_level=benchmark_preview promotion_blocker_summary=out_of_sample_unproven',
    )
  })
})
