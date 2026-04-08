import { createServer } from 'node:http'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { resolvePredictionCliPath } from './helpers/prediction-cli-path'

const execFileAsync = promisify(execFile)
const CLI = resolvePredictionCliPath()

describe('prediction markets CLI audit ops', () => {
  let server: ReturnType<typeof createServer>
  let baseUrl = ''

  const artifactAudit = {
    manifest_ref_count: 3,
    observed_ref_count: 4,
    canonical_ref_count: 4,
    run_manifest_present: true,
    duplicate_artifact_ids: ['run-ops-001:forecast_packet'],
    manifest_only_artifact_ids: [],
    observed_only_artifact_ids: ['run-ops-001:recommendation_packet'],
  }

  const artifactReadback = {
    run_manifest_ref: { artifact_id: 'run-ops-001:run_manifest' },
    manifest_artifact_refs: [
      { artifact_id: 'run-ops-001:market_descriptor' },
      { artifact_id: 'run-ops-001:forecast_packet' },
      { artifact_id: 'run-ops-001:run_manifest' },
    ],
    observed_artifact_refs: [
      { artifact_id: 'run-ops-001:market_descriptor' },
      { artifact_id: 'run-ops-001:forecast_packet' },
      { artifact_id: 'run-ops-001:run_manifest' },
      { artifact_id: 'run-ops-001:recommendation_packet' },
    ],
    canonical_artifact_refs: [
      { artifact_id: 'run-ops-001:market_descriptor' },
      { artifact_id: 'run-ops-001:forecast_packet' },
      { artifact_id: 'run-ops-001:run_manifest' },
      { artifact_id: 'run-ops-001:recommendation_packet' },
    ],
    manifest_index: {
      'run-ops-001:market_descriptor': { artifact_id: 'run-ops-001:market_descriptor' },
    },
    observed_index: {
      'run-ops-001:recommendation_packet': { artifact_id: 'run-ops-001:recommendation_packet' },
    },
    canonical_index: {
      'run-ops-001:run_manifest': { artifact_id: 'run-ops-001:run_manifest' },
    },
    manifest_only_artifact_ids: [],
    observed_only_artifact_ids: ['run-ops-001:recommendation_packet'],
  }

  beforeAll(async () => {
    server = createServer((req, res) => {
      const url = new URL(req.url ?? '/', 'http://127.0.0.1')

      if (req.method === 'GET' && url.pathname === '/api/v1/prediction-markets/runs') {
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(JSON.stringify({
          runs: [
            {
              run_id: 'run-ops-001',
              workspace_id: 1,
              venue: 'polymarket',
              mode: 'advise',
              market_id: 'mkt-ops-001',
              market_slug: 'mkt-ops-001',
              status: 'completed',
              recommendation: 'bet',
              side: 'yes',
              confidence: 0.81,
              probability_yes: 0.74,
              market_price_yes: 0.51,
              edge_bps: 2300,
              artifact_audit: artifactAudit,
            },
          ],
          total: 1,
        }))
        return
      }

      if (req.method === 'GET' && url.pathname === '/api/v1/prediction-markets/runs/run-ops-001') {
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(JSON.stringify({
          run_id: 'run-ops-001',
          workspace_id: 1,
          venue: 'polymarket',
          mode: 'advise',
          market_id: 'mkt-ops-001',
          market_slug: 'mkt-ops-001',
          status: 'completed',
          recommendation: 'bet',
          side: 'yes',
          confidence: 0.81,
          probability_yes: 0.74,
          market_price_yes: 0.51,
          edge_bps: 2300,
          artifact_audit: artifactAudit,
          artifact_readback: artifactReadback,
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

  it('prints compact artifact audit/readback lines for run and runs in text mode', async () => {
    const runResult = await execFileAsync(
      'node',
      [
        CLI,
        'prediction-markets',
        'run',
        '--run-id',
        'run-ops-001',
        '--artifact-audit-summary',
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

    expect(runResult.stdout).toContain('artifact_audit: manifest=3 observed=4 canonical=4 duplicates=1 manifest_only=0 observed_only=1')
    expect(runResult.stdout).toContain('artifact_readback: run_manifest=run-ops-001:run_manifest manifest=3 observed=4 canonical=4')

    const runsResult = await execFileAsync(
      'node',
      [
        CLI,
        'prediction-markets',
        'runs',
        '--artifact-audit-summary',
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

    expect(runsResult.stdout).toContain('run run-ops-001 | artifact_audit: manifest=3 observed=4 canonical=4 duplicates=1 manifest_only=0 observed_only=1')
  })
})
