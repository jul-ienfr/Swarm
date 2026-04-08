import { createServer } from 'node:http'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { listPredictionMarketRuns, persistPredictionMarketArtifact } from '@/lib/prediction-markets/store'
import { resolvePredictionCliPath } from './helpers/prediction-cli-path'

const execFileAsync = promisify(execFile)
const CLI = resolvePredictionCliPath()

const mocks = vi.hoisted(() => ({
  buildPolymarketSnapshot: vi.fn(),
  listPolymarketMarkets: vi.fn(),
  buildKalshiSnapshot: vi.fn(),
  listKalshiMarkets: vi.fn(),
}))

vi.mock('@/lib/prediction-markets/polymarket', async () => {
  const actual = await vi.importActual('@/lib/prediction-markets/polymarket') as typeof import('@/lib/prediction-markets/polymarket')

  return {
    ...actual,
    buildPolymarketSnapshot: mocks.buildPolymarketSnapshot,
    listPolymarketMarkets: mocks.listPolymarketMarkets,
  }
})

vi.mock('@/lib/prediction-markets/kalshi', async () => {
  const actual = await vi.importActual('@/lib/prediction-markets/kalshi') as typeof import('@/lib/prediction-markets/kalshi')

  return {
    ...actual,
    buildKalshiSnapshot: mocks.buildKalshiSnapshot,
    listKalshiMarkets: mocks.listKalshiMarkets,
  }
})

type ServerState = {
  lastAdviseRequest: { url: string; body: any } | null
  lastRunDetailsRequest: { url: string } | null
}

describe('prediction markets CLI persistence smoke', () => {
  let server: ReturnType<typeof createServer>
  let baseUrl = ''
  let tempDir = ''
  let serverState: ServerState
  let schemas: typeof import('@/lib/prediction-markets/schemas')
  let advisePredictionMarket: typeof import('@/lib/prediction-markets/service').advisePredictionMarket
  let getPredictionMarketRunDetails: typeof import('@/lib/prediction-markets/service').getPredictionMarketRunDetails
  let snapshot: import('@/lib/prediction-markets/schemas').MarketSnapshot

  beforeAll(async () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'prediction-markets-cli-smoke-'))
    process.env.PREDICTION_TEST_MODE = '1'
    process.env.PREDICTION_DB_PATH = path.join(tempDir, 'prediction.db')
    process.env.PREDICTION_DATA_DIR = tempDir

    schemas = await import('@/lib/prediction-markets/schemas')

    const market = schemas.marketDescriptorSchema.parse({
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      market_id: 'smoke-market-001',
      slug: 'smoke-market-001',
      question: 'Will the smoke test persist a prediction market run?',
      outcomes: ['Yes', 'No'],
      active: true,
      closed: false,
      accepting_orders: true,
      restricted: false,
      liquidity_usd: 125_000,
      volume_usd: 2_500_000,
      volume_24h_usd: 75_000,
      best_bid: 0.48,
      best_ask: 0.5,
      last_trade_price: 0.49,
      tick_size: 0.01,
      min_order_size: 1,
      is_binary_yes_no: true,
      source_urls: ['https://example.com/prediction-markets/smoke-market-001'],
    })

    snapshot = schemas.marketSnapshotSchema.parse({
      venue: 'polymarket',
      market,
      captured_at: new Date().toISOString(),
      yes_outcome_index: 0,
      yes_token_id: 'smoke-market-001:yes',
      yes_price: 0.49,
      no_price: 0.51,
      midpoint_yes: 0.49,
      best_bid_yes: 0.48,
      best_ask_yes: 0.5,
      spread_bps: 200,
      book: {
        token_id: 'smoke-market-001:yes',
        market_condition_id: 'smoke-market-001:condition',
        fetched_at: new Date().toISOString(),
        best_bid: 0.48,
        best_ask: 0.5,
        last_trade_price: 0.49,
        tick_size: 0.01,
        min_order_size: 1,
        bids: [{ price: 0.48, size: 120 }],
        asks: [{ price: 0.5, size: 140 }],
        depth_near_touch: 260,
      },
      history: [
        { timestamp: Math.floor(Date.now() / 1000) - 600, price: 0.47 },
        { timestamp: Math.floor(Date.now() / 1000) - 60, price: 0.49 },
      ],
      source_urls: ['https://example.com/prediction-markets/smoke-market-001/snapshot'],
    })

    mocks.buildPolymarketSnapshot.mockResolvedValue(snapshot)
    mocks.buildKalshiSnapshot.mockResolvedValue(snapshot)
    mocks.listPolymarketMarkets.mockResolvedValue([])
    mocks.listKalshiMarkets.mockResolvedValue([])

    ;({ advisePredictionMarket, getPredictionMarketRunDetails } = await import('@/lib/prediction-markets/service'))

    serverState = {
      lastAdviseRequest: null,
      lastRunDetailsRequest: null,
    }

    server = createServer(async (req, res) => {
      const url = new URL(req.url ?? '/', 'http://127.0.0.1')
      const chunks: Buffer[] = []

      req.on('data', (chunk: Buffer) => {
        chunks.push(chunk)
      })

      req.on('end', async () => {
        try {
          const bodyText = Buffer.concat(chunks).toString('utf8')
          const body = bodyText ? JSON.parse(bodyText) : undefined

          if (req.method === 'POST' && url.pathname === '/api/v1/prediction-markets/advise') {
            serverState.lastAdviseRequest = { url: url.pathname, body }
            const payload = await advisePredictionMarket({
              ...body,
              workspaceId: 1,
              actor: 'cli-smoke',
            })
            res.writeHead(201, { 'content-type': 'application/json', 'X-Prediction-Markets-API': 'v1' })
            res.end(JSON.stringify(payload))
            return
          }

          if (req.method === 'GET' && url.pathname.startsWith('/api/v1/prediction-markets/runs/')) {
            const runId = url.pathname.split('/').pop() || ''
            serverState.lastRunDetailsRequest = { url: url.pathname }
            const details = getPredictionMarketRunDetails(runId, 1)
            if (!details) {
              res.writeHead(404, { 'content-type': 'application/json' })
              res.end(JSON.stringify({ error: 'Prediction market run not found' }))
              return
            }

            res.writeHead(200, { 'content-type': 'application/json', 'X-Prediction-Markets-API': 'v1' })
            res.end(JSON.stringify(details))
            return
          }

          res.writeHead(404, { 'content-type': 'application/json' })
          res.end(JSON.stringify({ error: 'not_found' }))
        } catch (error) {
          res.writeHead(500, { 'content-type': 'application/json' })
          res.end(JSON.stringify({
            error: error instanceof Error ? error.message : 'Unknown error',
          }))
        }
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
    await new Promise<void>((resolve) => {
      server.close(() => resolve())
    })
    fs.rmSync(tempDir, { recursive: true, force: true })
  })

  it('persists a CLI advise run and exposes artifact audit/readback through run details', async () => {
    const researchSignals = [
      {
        signal_type: 'world_monitor',
        headline: 'Desk smoke signal',
        message: 'Smoke test feed confirms the run should persist.',
      },
    ]

    const adviseResult = await execFileAsync(
      'node',
      [
        CLI,
        'prediction-markets',
        'advise',
        '--venue',
        'polymarket',
        '--market-id',
        'smoke-market-001',
        '--research-signals',
        JSON.stringify(researchSignals),
        '--json',
        '--url',
        baseUrl,
      ],
      {
        env: {
          ...process.env,
          PREDICTION_TEST_MODE: '1',
          PREDICTION_DB_PATH: path.join(tempDir, 'prediction.db'),
          PREDICTION_DATA_DIR: tempDir,
        },
        timeout: 30_000,
        maxBuffer: 10 * 1024 * 1024,
      },
    )

    const adviseJson = JSON.parse(adviseResult.stdout)
    const runId =
      adviseJson.data?.prediction_run?.run_id ??
      adviseJson.data?.run?.id ??
      listPredictionMarketRuns({ workspaceId: 1, venue: 'polymarket', limit: 5 }).find(
        (run) => run.market_id === 'smoke-market-001',
      )?.run_id

    expect(runId).toBeTypeOf('string')
    expect(serverState.lastAdviseRequest?.url).toBe('/api/v1/prediction-markets/advise')
    expect(serverState.lastAdviseRequest?.body).toMatchObject({
      venue: 'polymarket',
      market_id: 'smoke-market-001',
      research_signals: researchSignals,
    })
    expect(schemas.forecastPacketSchema.parse(adviseJson.data.forecast)).toMatchObject({
      market_id: 'smoke-market-001',
      venue: 'polymarket',
    })
    expect(schemas.evidencePacketSchema.array().parse(adviseJson.data.evidence_packets)).not.toHaveLength(0)

    const runResult = await execFileAsync(
      'node',
      [
        CLI,
        'prediction-markets',
        'run',
        '--run-id',
        String(runId),
        '--json',
        '--url',
        baseUrl,
      ],
      {
        env: {
          ...process.env,
          PREDICTION_TEST_MODE: '1',
          PREDICTION_DB_PATH: path.join(tempDir, 'prediction.db'),
          PREDICTION_DATA_DIR: tempDir,
        },
        timeout: 30_000,
        maxBuffer: 10 * 1024 * 1024,
      },
    )

    const runJson = JSON.parse(runResult.stdout)

    expect(serverState.lastRunDetailsRequest?.url).toBe(`/api/v1/prediction-markets/runs/${runId}`)
    expect(runJson.data.run_id).toBe(runId)
    expect(runJson.data.artifact_audit).toMatchObject({
      run_manifest_present: true,
    })
    expect(runJson.data.artifact_readback).toBeDefined()
    expect(runJson.data.artifact_readback.run_manifest_ref.artifact_id).toBe(`${runId}:run_manifest`)
    expect(runJson.data.artifact_readback.canonical_artifact_refs.length).toBeGreaterThan(0)

    const microstructureLabLayout = persistPredictionMarketArtifact({
      workspaceId: 1,
      runId,
      venue: 'polymarket',
      marketId: 'smoke-market-001',
      artifactType: 'microstructure_lab',
      payload: {
        run_id: runId,
        market_id: 'smoke-market-001',
        venue: 'polymarket',
        generated_at: new Date().toISOString(),
        summary: 'smoke test microstructure lab artifact',
      },
    })

    expect(microstructureLabLayout).toMatchObject({
      artifact_id: `${runId}:microstructure_lab`,
      artifact_type: 'microstructure_lab',
      bucket: 'runs',
      file_name: 'microstructure_lab.json',
    })

    const runDetailsWithMicrostructureLab = getPredictionMarketRunDetails(runId, 1)
    expect(runDetailsWithMicrostructureLab?.artifacts.map((artifact) => artifact.artifact_type)).toContain(
      'microstructure_lab',
    )
    expect(
      runDetailsWithMicrostructureLab?.artifacts.find((artifact) => artifact.artifact_type === 'microstructure_lab')?.payload,
    ).toMatchObject({
      run_id: runId,
      market_id: 'smoke-market-001',
      venue: 'polymarket',
      summary: 'smoke test microstructure lab artifact',
    })
  })
})
