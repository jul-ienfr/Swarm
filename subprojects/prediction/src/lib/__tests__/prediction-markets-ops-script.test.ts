import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const scriptPath = resolve(process.cwd(), 'scripts/prediction-ops.cjs')

function runOpsScript(args: string[], env?: NodeJS.ProcessEnv) {
  return spawnSync(process.execPath, [scriptPath, ...args], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      ...env,
    },
    encoding: 'utf8',
  })
}

describe('prediction-ops script', () => {
  it('prints help and exits cleanly', () => {
    const result = runOpsScript(['--help'])

    expect(result.status).toBe(0)
    expect(result.stdout).toContain('prediction-ops usage:')
    expect(result.stdout).toContain('live')
    expect(result.stdout).toContain('capabilities')
  })

  it('resolves live to the local mc-cli wrapper with the configured base URL', () => {
    const result = runOpsScript(
      ['live', '--print-command', '--run-id', 'run-live-123', '--execution-pathways-summary'],
      { PREDICTION_BASE_URL: 'http://127.0.0.1:4010' },
    )

    expect(result.status).toBe(0)
    const payload = JSON.parse(result.stdout)

    expect(payload.surface).toBe('live')
    expect(payload.args).toEqual([
      scriptPath.replace('prediction-ops.cjs', 'mc-cli.cjs'),
      'prediction-markets',
      'live',
      '--run-id',
      'run-live-123',
      '--execution-pathways-summary',
      '--url',
      'http://127.0.0.1:4010',
    ])
  })

  it('does not inject a second url when one is already provided', () => {
    const result = runOpsScript(
      ['dispatch', '--print-command', '--run-id', 'run-dispatch-123', '--url', 'http://127.0.0.1:4020'],
      { PREDICTION_BASE_URL: 'http://127.0.0.1:4010' },
    )

    expect(result.status).toBe(0)
    const payload = JSON.parse(result.stdout)

    expect(payload.surface).toBe('dispatch')
    expect(payload.args.filter((value: string) => value === '--url')).toHaveLength(1)
    expect(payload.args.at(-1)).toBe('http://127.0.0.1:4020')
  })

  it('maps feed to the health surface for local operator bootstrap', () => {
    const result = runOpsScript(['feed', '--print-command', '--venue', 'polymarket'])

    expect(result.status).toBe(0)
    const payload = JSON.parse(result.stdout)

    expect(payload.surface).toBe('health')
    expect(payload.args).toContain('health')
    expect(payload.args).toContain('--venue')
    expect(payload.args).toContain('polymarket')
  })

  it('expands --operator-summary into the canonical execution and research summary flags', () => {
    const result = runOpsScript(
      ['shadow', '--print-command', '--run-id', 'run-shadow-123', '--operator-summary'],
      { PREDICTION_BASE_URL: 'http://127.0.0.1:4010' },
    )

    expect(result.status).toBe(0)
    const payload = JSON.parse(result.stdout)

    expect(payload.surface).toBe('shadow')
    expect(payload.args).toEqual(
      expect.arrayContaining([
        '--execution-pathways-summary',
        '--research-summary',
        '--benchmark-summary',
        '--validation-summary',
      ]),
    )
    expect(payload.args).toEqual(
      expect.arrayContaining([
        '--run-id',
        'run-shadow-123',
        '--url',
        'http://127.0.0.1:4010',
      ]),
    )
  })

  it('expands --operator-json into operator summaries plus json mode', () => {
    const result = runOpsScript(
      ['runs', '--print-command', '--operator-json', '--limit', '5'],
      { PREDICTION_BASE_URL: 'http://127.0.0.1:4010' },
    )

    expect(result.status).toBe(0)
    const payload = JSON.parse(result.stdout)

    expect(payload.surface).toBe('runs')
    expect(payload.args).toEqual(
      expect.arrayContaining([
        '--execution-pathways-summary',
        '--research-summary',
        '--benchmark-summary',
        '--validation-summary',
        '--json',
        '--limit',
        '5',
      ]),
    )
  })

  it('injects the default venue for feed bootstrap surfaces when none is provided', () => {
    const result = runOpsScript(
      ['capabilities', '--print-command'],
      { PREDICTION_DEFAULT_VENUE: 'kalshi' },
    )

    expect(result.status).toBe(0)
    const payload = JSON.parse(result.stdout)

    expect(payload.surface).toBe('capabilities')
    expect(payload.args).toEqual(
      expect.arrayContaining([
        '--venue',
        'kalshi',
      ]),
    )
  })

  it('prints the resolved request for a live operator surface', () => {
    const result = runOpsScript(
      ['live', '--print-request', '--run-id', 'run-live-456'],
      { PREDICTION_BASE_URL: 'http://127.0.0.1:4030' },
    )

    expect(result.status).toBe(0)
    const payload = JSON.parse(result.stdout)

    expect(payload.surface).toBe('live')
    expect(payload.semantics).toMatchObject({
      surface_kind: 'operator_surface',
      preflight_only: true,
      benchmark_gated: true,
      readiness_semantics: 'blocked_until_live_path_benchmark_and_transport_ready',
      execution_projection_path: 'live',
      promotion_semantics: 'benchmark_gated_governed_live_materialization',
    })
    expect(payload.request_preview).toBe('POST /api/v1/prediction-markets/runs/run-live-456/live')
    expect(payload.surface_summary).toBe(
      'Live remains the canonical preflight surface for governed routing; it stays benchmark-gated by default, and real venue execution can be materialized with execution_mode=live after an approved live intent.',
    )
    expect(payload.request).toEqual({
      method: 'POST',
      path: '/api/v1/prediction-markets/runs/run-live-456/live',
      url: 'http://127.0.0.1:4030/api/v1/prediction-markets/runs/run-live-456/live',
      body: null,
    })
  })

  it('prints the resolved request for feed bootstrap surfaces with the default venue', () => {
    const result = runOpsScript(
      ['feed', '--print-request'],
      { PREDICTION_BASE_URL: 'http://127.0.0.1:4040', PREDICTION_DEFAULT_VENUE: 'kalshi' },
    )

    expect(result.status).toBe(0)
    const payload = JSON.parse(result.stdout)

    expect(payload.surface).toBe('health')
    expect(payload.semantics).toMatchObject({
      surface_kind: 'feed_bootstrap',
      default_venue_applies: true,
      readiness_semantics: 'read_only_feed_bootstrap',
      feed_transport_semantics: 'market_and_user_feed_via_local_cache_rtds_unavailable',
    })
    expect(payload.request_preview).toBe('GET /api/v1/prediction-markets/health?venue=kalshi')
    expect(payload.request).toEqual({
      method: 'GET',
      path: '/api/v1/prediction-markets/health',
      url: 'http://127.0.0.1:4040/api/v1/prediction-markets/health?venue=kalshi',
      body: null,
    })
  })

  it('prints a compact surface summary for live operator semantics', () => {
    const result = runOpsScript(
      ['live', '--print-summary', '--run-id', 'run-live-789'],
      { PREDICTION_BASE_URL: 'http://127.0.0.1:4050' },
    )

    expect(result.status).toBe(0)
    expect(result.stdout).toContain(
      'prediction_surface: surface=live kind=operator_surface method=POST path=/api/v1/prediction-markets/runs/run-live-789/live preflight=yes benchmark=yes default_venue=no projection=live runtime=execution_projection_first',
    )
    expect(result.stdout).toContain(
      'prediction_surface_semantics: readiness=blocked_until_live_path_benchmark_and_transport_ready promotion=benchmark_gated_governed_live_materialization transport=none',
    )
    expect(result.stdout).toContain(
      'prediction_request_preview: POST /api/v1/prediction-markets/runs/run-live-789/live',
    )
    expect(result.stdout).toContain(
      'prediction_surface_summary: Live remains the canonical preflight surface for governed routing; it stays benchmark-gated by default, and real venue execution can be materialized with execution_mode=live after an approved live intent.',
    )
  })

  it('prints a readable feed bootstrap summary with transport semantics', () => {
    const result = runOpsScript(
      ['feed', '--print-summary'],
      { PREDICTION_BASE_URL: 'http://127.0.0.1:4060', PREDICTION_DEFAULT_VENUE: 'kalshi' },
    )

    expect(result.status).toBe(0)
    expect(result.stdout).toContain(
      'prediction_surface: surface=health kind=feed_bootstrap method=GET path=/api/v1/prediction-markets/health preflight=no benchmark=no default_venue=yes runtime=read_only_bootstrap',
    )
    expect(result.stdout).toContain(
      'prediction_surface_semantics: readiness=read_only_feed_bootstrap promotion=not_applicable transport=market_and_user_feed_via_local_cache_rtds_unavailable',
    )
    expect(result.stdout).toContain(
      'prediction_request_preview: GET /api/v1/prediction-markets/health?venue=kalshi',
    )
    expect(result.stdout).toContain(
      'prediction_surface_summary: Health/feed stays read-only and reflects local market/user feed transport state plus RTDS availability for operator bootstrap.',
    )
  })
})
