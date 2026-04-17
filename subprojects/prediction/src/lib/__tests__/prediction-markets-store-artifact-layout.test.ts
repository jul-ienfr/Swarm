import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type StoredRunRow = {
  run_id: string
  source_run_id: string | null
  workspace_id: number
  venue: 'polymarket' | 'kalshi'
  mode: 'advise' | 'replay'
  market_id: string
  market_slug: string | null
  status: 'running' | 'completed' | 'failed'
  recommendation: 'bet' | 'no_trade' | 'wait' | null
  side: 'yes' | 'no' | null
  confidence: number | null
  probability_yes: number | null
  market_price_yes: number | null
  edge_bps: number | null
  manifest_json: string
  artifact_index_json: string
  created_at: number
  updated_at: number
}

type StoredArtifactRow = {
  artifact_id: string
  workspace_id: number
  run_id: string
  artifact_type: string
  sha256: string
  payload_json: string
  created_at: number
}

const dbMocks = vi.hoisted(() => {
  const state = {
    runs: new Map<string, StoredRunRow>(),
    artifacts: [] as StoredArtifactRow[],
    nextArtifactCreatedAt: 1,
  }

  const mockDb = {
    prepare: vi.fn((sql: string) => {
      if (sql.includes('INSERT OR REPLACE INTO prediction_market_artifacts')) {
        return {
          run: (
            artifact_id: string,
            workspace_id: number,
            run_id: string,
            artifact_type: string,
            sha256: string,
            payload_json: string,
          ) => {
            state.artifacts.push({
              artifact_id,
              workspace_id,
              run_id,
              artifact_type,
              sha256,
              payload_json,
              created_at: state.nextArtifactCreatedAt++,
            })
            return { changes: 1 }
          },
        }
      }

      if (sql.includes('INSERT INTO prediction_market_runs')) {
        return {
          run: (
            run_id: string,
            source_run_id: string | null,
            workspace_id: number,
            venue: 'polymarket' | 'kalshi',
            mode: 'advise' | 'replay',
            market_id: string,
            market_slug: string | null,
            status: 'running' | 'completed' | 'failed',
            recommendation: 'bet' | 'no_trade' | 'wait' | null,
            side: 'yes' | 'no' | null,
            confidence: number | null,
            probability_yes: number | null,
            market_price_yes: number | null,
            edge_bps: number | null,
            manifest_json: string,
            artifact_index_json: string,
            created_at: number,
            updated_at: number,
          ) => {
            state.runs.set(`${run_id}:${workspace_id}`, {
              run_id,
              source_run_id,
              workspace_id,
              venue,
              mode,
              market_id,
              market_slug,
              status,
              recommendation,
              side,
              confidence,
              probability_yes,
              market_price_yes,
              edge_bps,
              manifest_json,
              artifact_index_json,
              created_at,
              updated_at,
            })
            return { changes: 1 }
          },
        }
      }

      if (sql.includes('SELECT *') && sql.includes('FROM prediction_market_runs')) {
        return {
          get: (run_id: string, workspace_id: number) => state.runs.get(`${run_id}:${workspace_id}`),
          all: () => [],
        }
      }

      if (sql.includes('SELECT artifact_id, artifact_type, sha256, payload_json')) {
        return {
          all: (run_id: string, workspace_id: number) =>
            state.artifacts
              .filter((row) => row.run_id === run_id && row.workspace_id === workspace_id)
              .slice()
              .sort((left, right) => left.created_at - right.created_at),
        }
      }

      return {
        run: vi.fn(() => ({ changes: 0 })),
        get: vi.fn(() => undefined),
        all: vi.fn(() => []),
      }
    }),
    transaction: vi.fn((fn: () => unknown) => () => fn()),
  }

  return { state, mockDb }
})

vi.mock('@/lib/db', () => ({
  getDatabase: () => dbMocks.mockDb,
}))

import {
  PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT,
  buildPredictionMarketArtifactLayout,
} from '@/lib/prediction-markets/artifact-layout'
import {
  getPredictionMarketRunDetails,
  persistPredictionMarketArtifact,
  persistPredictionMarketExecution,
  upsertPredictionMarketRun,
} from '@/lib/prediction-markets/store'
import {
  evidencePacketSchema,
  forecastPacketSchema,
  marketDescriptorSchema,
  marketRecommendationPacketSchema,
  marketSnapshotSchema,
  predictionMarketArtifactRefSchema,
  predictionMarketProvenanceBundleSchema,
  resolutionPolicySchema,
  runManifestSchema,
  type MarketSnapshot,
} from '@/lib/prediction-markets/schemas'

function resetDbState() {
  dbMocks.state.runs.clear()
  dbMocks.state.artifacts.length = 0
  dbMocks.state.nextArtifactCreatedAt = 1
  dbMocks.mockDb.prepare.mockClear()
  dbMocks.mockDb.transaction.mockClear()
}

function makeMarketSnapshot(): MarketSnapshot {
  const market = marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: 'BTC / Apr 2026',
    slug: 'btc-apr-2026',
    question: 'Will BTC close above 100k in Apr 2026?',
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
    source_urls: ['https://example.com/markets/btc-apr-2026'],
  })

  return marketSnapshotSchema.parse({
    venue: 'polymarket',
    market,
    captured_at: '2026-04-08T00:00:00.000Z',
    yes_outcome_index: 0,
    yes_token_id: 'btc-apr-2026:yes',
    yes_price: 0.49,
    no_price: 0.51,
    midpoint_yes: 0.49,
    best_bid_yes: 0.48,
    best_ask_yes: 0.5,
    spread_bps: 200,
    book: {
      token_id: 'btc-apr-2026:yes',
      market_condition_id: 'btc-apr-2026:cond',
      fetched_at: '2026-04-08T00:00:00.000Z',
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
      { timestamp: 1775605200, price: 0.47 },
      { timestamp: 1775608800, price: 0.49 },
    ],
    source_urls: ['https://example.com/markets/btc-apr-2026/snapshot'],
  })
}

function makeEvidencePacket(snapshot: MarketSnapshot, evidenceId: string) {
  return evidencePacketSchema.parse({
    evidence_id: evidenceId,
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    type: 'market_data',
    title: 'Live market snapshot',
    summary: 'Compact evidence packet for persistence coverage.',
    source_url: snapshot.source_urls[0],
    captured_at: snapshot.captured_at,
    content_hash: `sha256:${evidenceId}`,
    metadata: {
      venue: snapshot.venue,
    },
  })
}

describe('prediction markets store artifact layout alignment', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-08T00:00:00.000Z'))
    resetDbState()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('persists artifact refs and manifest keys that follow artifact-layout naming conventions', () => {
    const snapshot = makeMarketSnapshot()
    const resolutionPolicy = resolutionPolicySchema.parse({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      status: 'eligible',
      manual_review_required: false,
      reasons: [],
      primary_sources: snapshot.source_urls,
      evaluated_at: '2026-04-08T00:00:05.000Z',
    })
    const evidencePackets = [
      makeEvidencePacket(snapshot, 'evidence-btc-apr-2026-001'),
      makeEvidencePacket(snapshot, 'evidence-btc-apr-2026-002'),
    ]
    const forecast = forecastPacketSchema.parse({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      basis: 'market_midpoint',
      probability_yes: 0.53,
      confidence: 0.61,
      rationale: 'Market midpoint with slight positive drift.',
      evidence_refs: evidencePackets.map((packet) => packet.evidence_id),
      produced_at: '2026-04-08T00:00:10.000Z',
    })
    const recommendation = marketRecommendationPacketSchema.parse({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      action: 'wait',
      side: null,
      confidence: 0.61,
      fair_value_yes: 0.53,
      market_price_yes: 0.49,
      market_bid_yes: 0.48,
      market_ask_yes: 0.5,
      edge_bps: 400,
      spread_bps: 200,
      reasons: ['Edge is positive but not strong enough to cross the spread.'],
      risk_flags: [],
      produced_at: '2026-04-08T00:00:12.000Z',
    })
    const manifest = runManifestSchema.parse({
      run_id: 'pm-run-003',
      source_run_id: 'pm-run-002',
      mode: 'advise',
      venue: snapshot.venue,
      market_id: snapshot.market.market_id,
      market_slug: snapshot.market.slug,
      actor: 'operator',
      started_at: '2026-04-08T00:00:00.000Z',
      completed_at: '2026-04-08T00:00:15.000Z',
      status: 'completed',
      config_hash: 'cfg-store-layout-001',
    })

    const execution = persistPredictionMarketExecution({
      workspaceId: 7,
      runId: manifest.run_id,
      sourceRunId: manifest.source_run_id,
      venue: manifest.venue,
      mode: manifest.mode,
      snapshot,
      resolutionPolicy,
      evidencePackets,
      forecast,
      recommendation,
      researchSidecar: {
        market_id: snapshot.market.market_id,
        venue: snapshot.venue,
        generated_at: '2026-04-08T00:00:13.000Z',
        note: 'research sidecar',
      },
      runtimeGuard: {
        venue: snapshot.venue,
        mode: 'paper',
        verdict: 'allowed',
        reasons: [],
        constraints: ['mode=paper'],
        fallback_actions: [],
        capabilities: {},
        health: {},
        budgets: {},
      },
      executionReadiness: {
        venue: snapshot.venue,
        highest_safe_mode: 'paper',
        overall_verdict: 'degraded',
        summary: 'Highest safe mode is paper.',
      },
      executionPathways: {
        venue: snapshot.venue,
        market_id: snapshot.market.market_id,
        recommendation_action: 'wait',
        recommendation_side: null,
        highest_actionable_mode: null,
        pathways: [
          { mode: 'paper', effective_mode: 'paper', status: 'inactive', actionable: false, blockers: [], warnings: [], reason_summary: 'inactive', trade_intent_preview: null },
        ],
        summary: 'Current recommendation is wait; execution pathways remain inactive.',
      },
      executionProjection: {
        requested_path: 'paper',
        selected_path: 'paper',
        eligible_paths: ['paper'],
        verdict: 'allowed',
        blocking_reasons: [],
        downgrade_reasons: [],
        manual_review_required: false,
        generated_at: '2026-04-08T00:00:12.000Z',
        ttl_ms: 30_000,
        expires_at: '2026-04-08T00:00:42.000Z',
        projected_paths: {},
        summary: 'Requested paper; selected paper; verdict allowed.',
      },
      manifest,
    })

    expect(execution.summary.run_id).toBe('pm-run-003')
    expect(execution.summary.market_id).toBe('BTC / Apr 2026')
    expect(execution.summary.manifest.run_id).toBe('pm-run-003')
    expect(execution.summary.manifest.artifact_refs).toHaveLength(11)
    expect(execution.summary.artifact_refs).toHaveLength(12)
    expect(execution.summary.manifest.artifact_refs.some((ref) => ref.artifact_type === 'run_manifest')).toBe(false)
    const manifestArtifactRef = execution.summary.artifact_refs.at(-1)
    expect(manifestArtifactRef).toMatchObject({
      artifact_id: 'pm-run-003:run_manifest',
      artifact_type: 'run_manifest',
    })
    expect(manifestArtifactRef?.sha256).toEqual(expect.any(String))

    for (const ref of execution.summary.manifest.artifact_refs) {
      expect(ref.artifact_id).toBe(`pm-run-003:${ref.artifact_type}`)
      expect(predictionMarketArtifactRefSchema.parse(ref)).toEqual(ref)
    }
    expect(execution.summary.manifest.artifact_refs.map((ref) => ref.artifact_type)).toEqual(expect.arrayContaining([
      'execution_readiness',
      'execution_pathways',
      'execution_projection',
    ]))

    const manifestLayout = buildPredictionMarketArtifactLayout({
      run_id: execution.summary.run_id,
      venue: execution.summary.venue,
      market_id: execution.summary.market_id,
      artifact_type: 'run_manifest',
    })

    expect(manifestLayout.artifact_id).toBe('pm-run-003:run_manifest')
    expect(manifestLayout.file_name).toBe('run_manifest.json')
    expect(manifestLayout.run_key).toBe(manifestLayout.manifest_keys.run_key)
    expect(manifestLayout.market_key).toBe(manifestLayout.manifest_keys.market_key)
    expect(manifestLayout.latest_key).toBe(manifestLayout.manifest_keys.latest_key)
    expect(manifestLayout.run_path).toBe(
      `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/runs/pm-run-003/runs/run_manifest.json`,
    )
    expect(manifestLayout.market_path).toContain('/venues/polymarket/markets/BTC%20%2F%20Apr%202026/runs/pm-run-003--run_manifest.json')
    expect(manifestLayout.latest_path).toContain('/venues/polymarket/markets/BTC%20%2F%20Apr%202026/runs/latest--run_manifest.json')
  })

  it('persists microstructure_lab as a canonical run-scoped artifact', () => {
    const snapshot = makeMarketSnapshot()
    const manifest = runManifestSchema.parse({
      run_id: 'pm-run-003a',
      mode: 'advise',
      venue: snapshot.venue,
      market_id: snapshot.market.market_id,
      market_slug: snapshot.market.slug,
      actor: 'operator',
      started_at: '2026-04-08T00:00:00.000Z',
      completed_at: '2026-04-08T00:00:20.000Z',
      status: 'completed',
      config_hash: 'cfg-store-layout-microstructure',
    })

    upsertPredictionMarketRun({
      workspaceId: 7,
      runId: manifest.run_id,
      venue: manifest.venue,
      mode: manifest.mode,
      marketId: snapshot.market.market_id,
      marketSlug: snapshot.market.slug,
      status: manifest.status,
      recommendation: 'wait',
      side: null,
      confidence: 0.5,
      probabilityYes: 0.5,
      marketPriceYes: 0.49,
      edgeBps: 0,
      manifest,
      artifactRefs: [],
    })

    const microstructureLabLayout = persistPredictionMarketArtifact({
      workspaceId: 7,
      runId: manifest.run_id,
      venue: snapshot.venue,
      marketId: snapshot.market.market_id,
      artifactType: 'microstructure_lab',
      payload: {
        market_id: snapshot.market.market_id,
        venue: snapshot.venue,
        generated_at: '2026-04-08T00:00:21.000Z',
        summary: 'microstructure lab canonical payload',
      },
    })

    expect(microstructureLabLayout).toMatchObject({
      artifact_id: 'pm-run-003a:microstructure_lab',
      artifact_type: 'microstructure_lab',
      bucket: 'runs',
      file_name: 'microstructure_lab.json',
    })
    expect(microstructureLabLayout.run_key).toBe(
      `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/runs/pm-run-003a/runs/microstructure_lab.json`,
    )
    expect(microstructureLabLayout.market_key).toBe(
      `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket/markets/BTC%20%2F%20Apr%202026/runs/pm-run-003a--microstructure_lab.json`,
    )
    expect(microstructureLabLayout.latest_key).toBe(
      `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket/markets/BTC%20%2F%20Apr%202026/runs/latest--microstructure_lab.json`,
    )

    const details = getPredictionMarketRunDetails('pm-run-003a', 7)
    expect(details).not.toBeNull()
    if (!details) return

    expect(details.artifacts).toHaveLength(1)
    expect(details.artifacts[0]).toMatchObject({
      artifact_id: 'pm-run-003a:microstructure_lab',
      artifact_type: 'microstructure_lab',
    })
    expect(details.artifacts[0].payload).toMatchObject({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      summary: 'microstructure lab canonical payload',
    })
  })

  it('persists resolved history, cost model, and walk-forward artifacts', () => {
    const snapshot = makeMarketSnapshot()
    const resolutionPolicy = resolutionPolicySchema.parse({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      status: 'eligible',
      evaluated_at: '2026-04-08T00:00:00.000Z',
      resolution_text: 'Resolves to yes if BTC closes above 100k during Apr 2026.',
      reasons: ['Uses market close data from the official exchange feed.'],
      primary_sources: ['https://example.com/resolution/btc-apr-2026'],
      manual_review_required: false,
    })
    const evidencePackets = [makeEvidencePacket(snapshot, 'evidence-history')]
    const forecast = forecastPacketSchema.parse({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      probability_yes: 0.64,
      confidence: 0.71,
      basis: 'manual_thesis',
      rationale: 'Historical stack says the market is underpricing yes.',
      reasons: ['Calibration and walk-forward agree on the long side.'],
      evidence_refs: ['evidence-history'],
      produced_at: '2026-04-08T00:00:10.000Z',
    })
    const recommendation = marketRecommendationPacketSchema.parse({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      action: 'bet',
      side: 'yes',
      confidence: 0.71,
      market_price_yes: 0.49,
      market_bid_yes: 0.48,
      market_ask_yes: 0.5,
      fair_value_yes: 0.64,
      edge_bps: 1500,
      spread_bps: 200,
      rationale: 'Validation stack clears the edge after costs.',
      reasons: ['resolved history present', 'walk forward positive'],
      risk_flags: [],
      produced_at: '2026-04-08T00:00:11.000Z',
      next_review_at: '2026-04-08T02:00:00.000Z',
    })
    const manifest = runManifestSchema.parse({
      run_id: 'pm-run-batch1',
      mode: 'advise',
      venue: snapshot.venue,
      market_id: snapshot.market.market_id,
      market_slug: snapshot.market.slug,
      actor: 'operator',
      started_at: '2026-04-08T00:00:00.000Z',
      completed_at: '2026-04-08T00:00:20.000Z',
      status: 'completed',
      config_hash: 'cfg-store-layout-batch1',
    })

    const execution = persistPredictionMarketExecution({
      workspaceId: 7,
      runId: manifest.run_id,
      venue: manifest.venue,
      mode: manifest.mode,
      snapshot,
      resolutionPolicy,
      evidencePackets,
      forecast,
      recommendation,
      resolvedHistory: {
        artifact_kind: 'resolved_history',
        run_id: manifest.run_id,
        resolved_records: 4,
        points: [],
        summary: 'resolved history ready',
      },
      costModelReport: {
        artifact_kind: 'cost_model_report',
        run_id: manifest.run_id,
        total_points: 4,
        average_net_edge_bps: 125,
        summary: 'cost model ready',
      },
      walkForwardReport: {
        artifact_kind: 'walk_forward_report',
        run_id: manifest.run_id,
        total_windows: 2,
        promotion_ready: true,
        summary: 'walk forward ready',
      },
      manifest,
    })

    expect(execution.summary.manifest.artifact_refs.map((ref) => ref.artifact_type)).toEqual(expect.arrayContaining([
      'resolved_history',
      'cost_model_report',
      'walk_forward_report',
    ]))

    const details = getPredictionMarketRunDetails('pm-run-batch1', 7)
    expect(details?.artifacts.map((artifact) => artifact.artifact_type)).toEqual(expect.arrayContaining([
      'resolved_history',
      'cost_model_report',
      'walk_forward_report',
    ]))
  })

  it('persists shadow_arbitrage as a canonical run-scoped json artifact', () => {
    const snapshot = makeMarketSnapshot()
    const manifest = runManifestSchema.parse({
      run_id: 'pm-run-003b',
      mode: 'replay',
      venue: snapshot.venue,
      market_id: snapshot.market.market_id,
      market_slug: snapshot.market.slug,
      actor: 'operator',
      started_at: '2026-04-08T00:00:00.000Z',
      completed_at: '2026-04-08T00:00:30.000Z',
      status: 'completed',
      config_hash: 'cfg-store-layout-shadow-arb',
    })

    upsertPredictionMarketRun({
      workspaceId: 7,
      runId: manifest.run_id,
      venue: manifest.venue,
      mode: manifest.mode,
      marketId: snapshot.market.market_id,
      marketSlug: snapshot.market.slug,
      status: manifest.status,
      recommendation: 'wait',
      side: null,
      confidence: 0.5,
      probabilityYes: 0.5,
      marketPriceYes: 0.49,
      edgeBps: 0,
      manifest,
      artifactRefs: [],
    })

    const shadowArbitrageLayout = persistPredictionMarketArtifact({
      workspaceId: 7,
      runId: manifest.run_id,
      venue: snapshot.venue,
      marketId: snapshot.market.market_id,
      artifactType: 'shadow_arbitrage',
      payload: {
        market_id: snapshot.market.market_id,
        venue: snapshot.venue,
        generated_at: '2026-04-08T00:00:31.000Z',
        summary: 'shadow arbitrage runtime payload',
        status: 'shadow_only',
      },
    })

    expect(shadowArbitrageLayout).toMatchObject({
      artifact_id: 'pm-run-003b:shadow_arbitrage',
      artifact_type: 'shadow_arbitrage',
      bucket: 'runs',
      file_name: 'shadow_arbitrage.json',
    })
    expect(shadowArbitrageLayout.run_key).toBe(
      `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/runs/pm-run-003b/runs/shadow_arbitrage.json`,
    )
    expect(shadowArbitrageLayout.market_key).toBe(
      `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket/markets/BTC%20%2F%20Apr%202026/runs/pm-run-003b--shadow_arbitrage.json`,
    )
    expect(shadowArbitrageLayout.latest_key).toBe(
      `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket/markets/BTC%20%2F%20Apr%202026/runs/latest--shadow_arbitrage.json`,
    )

    const details = getPredictionMarketRunDetails('pm-run-003b', 7)
    expect(details).not.toBeNull()
    if (!details) return

    expect(details.artifacts).toHaveLength(1)
    expect(details.artifacts[0]).toMatchObject({
      artifact_id: 'pm-run-003b:shadow_arbitrage',
      artifact_type: 'shadow_arbitrage',
    })
    expect(details.artifacts[0].payload).toMatchObject({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      summary: 'shadow arbitrage runtime payload',
      status: 'shadow_only',
    })
  })

  it('hydrates stored artifacts so their persisted types stay coherent with layout keys', () => {
    const snapshot = makeMarketSnapshot()
    const resolutionPolicy = resolutionPolicySchema.parse({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      status: 'eligible',
      manual_review_required: false,
      reasons: [],
      primary_sources: snapshot.source_urls,
      evaluated_at: '2026-04-08T00:00:05.000Z',
    })
    const evidencePackets = [makeEvidencePacket(snapshot, 'evidence-btc-apr-2026-003')]
    const forecast = forecastPacketSchema.parse({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      basis: 'manual_thesis',
      probability_yes: 0.57,
      confidence: 0.64,
      rationale: 'Manual thesis with stronger evidence.',
      evidence_refs: evidencePackets.map((packet) => packet.evidence_id),
      produced_at: '2026-04-08T00:00:10.000Z',
    })
    const recommendation = marketRecommendationPacketSchema.parse({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      action: 'bet',
      side: 'yes',
      confidence: 0.64,
      fair_value_yes: 0.57,
      market_price_yes: 0.49,
      market_bid_yes: 0.48,
      market_ask_yes: 0.5,
      edge_bps: 800,
      spread_bps: 200,
      reasons: ['Manual thesis justifies entry.'],
      risk_flags: [],
      produced_at: '2026-04-08T00:00:12.000Z',
    })
    const manifest = runManifestSchema.parse({
      run_id: 'pm-run-004',
      mode: 'replay',
      venue: snapshot.venue,
      market_id: snapshot.market.market_id,
      market_slug: snapshot.market.slug,
      actor: 'operator',
      started_at: '2026-04-08T00:01:00.000Z',
      completed_at: '2026-04-08T00:01:20.000Z',
      status: 'completed',
      config_hash: 'cfg-store-layout-002',
    })

    const execution = persistPredictionMarketExecution({
      workspaceId: 8,
      runId: manifest.run_id,
      venue: manifest.venue,
      mode: manifest.mode,
      snapshot,
      resolutionPolicy,
      evidencePackets,
      forecast,
      recommendation,
      complianceReport: {
        market_id: snapshot.market.market_id,
        venue: snapshot.venue,
        generated_at: '2026-04-08T00:00:15.000Z',
        status: 'ok',
      },
      pipelineGuard: {
        market_id: snapshot.market.market_id,
        venue: snapshot.venue,
        generated_at: '2026-04-08T00:00:15.000Z',
        status: 'ok',
      },
      executionReadiness: {
        venue: snapshot.venue,
        highest_safe_mode: 'paper',
        overall_verdict: 'degraded',
        summary: 'Highest safe mode is paper.',
      },
      executionPathways: {
        venue: snapshot.venue,
        market_id: snapshot.market.market_id,
        recommendation_action: 'bet',
        recommendation_side: 'yes',
        highest_actionable_mode: 'paper',
        pathways: [
          { mode: 'paper', effective_mode: 'paper', status: 'ready', actionable: true, blockers: [], warnings: [], reason_summary: 'paper ready', trade_intent_preview: null },
        ],
        summary: 'paper is currently the highest actionable execution pathway.',
      },
      executionProjection: {
        requested_path: 'live',
        selected_path: 'paper',
        eligible_paths: ['paper'],
        verdict: 'downgraded',
        blocking_reasons: [],
        downgrade_reasons: ['manual_review_required_for_execution'],
        manual_review_required: true,
        generated_at: '2026-04-08T00:00:12.000Z',
        ttl_ms: 30_000,
        expires_at: '2026-04-08T00:00:42.000Z',
        projected_paths: {},
        summary: 'Requested live; selected paper; verdict downgraded.',
      },
      manifest,
    })

    const details = getPredictionMarketRunDetails('pm-run-004', 8)
    expect(details).not.toBeNull()
    if (!details) return

    expect(details.artifacts).toHaveLength(execution.summary.artifact_refs.length)
    expect(details.artifacts.map((artifact) => artifact.artifact_id)).toEqual(
      execution.summary.artifact_refs.map((ref) => ref.artifact_id),
    )

    for (const artifact of details.artifacts) {
      const layout = buildPredictionMarketArtifactLayout({
        run_id: details.run_id,
        venue: details.venue,
        market_id: details.market_id,
        artifact_type: artifact.artifact_type as Parameters<typeof buildPredictionMarketArtifactLayout>[0]['artifact_type'],
      })

      expect(layout.artifact_id).toBe(artifact.artifact_id)
      expect(layout.run_key).toBe(layout.manifest_keys.run_key)
      expect(layout.market_key).toBe(layout.manifest_keys.market_key)
      expect(layout.latest_key).toBe(layout.manifest_keys.latest_key)
      expect(layout.file_name).toMatch(/\.json$/)
      expect(layout.run_path).toContain(`${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/runs/pm-run-004`)
      expect(layout.market_path).toContain('/venues/polymarket/markets/BTC%20%2F%20Apr%202026/')
      expect(layout.latest_path).toContain('/venues/polymarket/markets/BTC%20%2F%20Apr%202026/')
    }

    const manifestArtifact = details.artifacts.find((artifact) => artifact.artifact_type === 'run_manifest')
    expect(manifestArtifact).toBeDefined()
    if (!manifestArtifact) return

    const storedManifest = runManifestSchema.parse(manifestArtifact.payload)
    expect(storedManifest.artifact_refs).toHaveLength(11)
    expect(storedManifest.artifact_refs.map((ref) => ref.artifact_type)).toContain('pipeline_guard')
    expect(storedManifest.artifact_refs.map((ref) => ref.artifact_type)).toContain('compliance_report')
    expect(storedManifest.artifact_refs.map((ref) => ref.artifact_type)).toEqual(expect.arrayContaining([
      'execution_readiness',
      'execution_pathways',
      'execution_projection',
    ]))
  })

  it('persists market events and positions as run-scoped json artifacts', () => {
    const snapshot = makeMarketSnapshot()
    const resolutionPolicy = resolutionPolicySchema.parse({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      status: 'eligible',
      manual_review_required: false,
      reasons: [],
      primary_sources: snapshot.source_urls,
      evaluated_at: '2026-04-08T00:00:05.000Z',
    })
    const evidencePackets = [makeEvidencePacket(snapshot, 'evidence-btc-apr-2026-005')]
    const forecast = forecastPacketSchema.parse({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      basis: 'manual_thesis',
      probability_yes: 0.63,
      confidence: 0.58,
      rationale: 'Manual thesis with signal artifacts.',
      evidence_refs: evidencePackets.map((packet) => packet.evidence_id),
      produced_at: '2026-04-08T00:02:10.000Z',
    })
    const recommendation = marketRecommendationPacketSchema.parse({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      action: 'bet',
      side: 'yes',
      confidence: 0.58,
      fair_value_yes: 0.63,
      market_price_yes: 0.49,
      market_bid_yes: 0.48,
      market_ask_yes: 0.5,
      edge_bps: 1400,
      spread_bps: 200,
      reasons: ['Signal artifacts justify surfacing events and positions.'],
      risk_flags: [],
      produced_at: '2026-04-08T00:02:12.000Z',
    })
    const manifest = runManifestSchema.parse({
      run_id: 'pm-run-005',
      mode: 'advise',
      venue: snapshot.venue,
      market_id: snapshot.market.market_id,
      market_slug: snapshot.market.slug,
      actor: 'operator',
      started_at: '2026-04-08T00:02:00.000Z',
      completed_at: '2026-04-08T00:02:20.000Z',
      status: 'completed',
      config_hash: 'cfg-store-layout-003',
    })

    const execution = persistPredictionMarketExecution({
      workspaceId: 9,
      runId: manifest.run_id,
      venue: manifest.venue,
      mode: manifest.mode,
      snapshot,
      resolutionPolicy,
      evidencePackets,
      forecast,
      recommendation,
      marketEvents: {
        feed: 'rtds',
        events: [{ id: 'evt-001', kind: 'market_tick', price: 0.5 }],
      },
      marketPositions: {
        source: 'positions',
        positions: [{ market_id: snapshot.market.market_id, side: 'yes', size_usd: 25 }],
      },
      complianceReport: {
        market_id: snapshot.market.market_id,
        venue: snapshot.venue,
        generated_at: '2026-04-08T00:02:15.000Z',
        status: 'ok',
      },
      pipelineGuard: {
        market_id: snapshot.market.market_id,
        venue: snapshot.venue,
        generated_at: '2026-04-08T00:02:15.000Z',
        status: 'ok',
      },
      executionReadiness: {
        venue: snapshot.venue,
        highest_safe_mode: 'paper',
        overall_verdict: 'degraded',
        summary: 'Highest safe mode is paper.',
      },
      executionPathways: {
        venue: snapshot.venue,
        market_id: snapshot.market.market_id,
        recommendation_action: 'bet',
        recommendation_side: 'yes',
        highest_actionable_mode: 'paper',
        pathways: [
          { mode: 'paper', effective_mode: 'paper', status: 'ready', actionable: true, blockers: [], warnings: [], reason_summary: 'paper ready', trade_intent_preview: null },
        ],
        summary: 'paper is currently the highest actionable execution pathway.',
      },
      executionProjection: {
        requested_path: 'live',
        selected_path: 'paper',
        eligible_paths: ['paper'],
        verdict: 'downgraded',
        blocking_reasons: [],
        downgrade_reasons: ['manual_review_required_for_execution'],
        manual_review_required: true,
        generated_at: '2026-04-08T00:02:12.000Z',
        ttl_ms: 30_000,
        expires_at: '2026-04-08T00:02:42.000Z',
        projected_paths: {},
        summary: 'Requested live; selected paper; verdict downgraded.',
      },
      manifest,
    })

    const details = getPredictionMarketRunDetails('pm-run-005', 9)
    expect(details).not.toBeNull()
    if (!details) return

    expect(details.artifacts.map((artifact) => artifact.artifact_type)).toEqual(expect.arrayContaining([
      'market_events',
      'market_positions',
    ]))

    const storedManifest = runManifestSchema.parse(
      details.artifacts.find((artifact) => artifact.artifact_type === 'run_manifest')?.payload,
    )
    expect(storedManifest.artifact_refs.map((ref) => ref.artifact_type)).toEqual(expect.arrayContaining([
      'market_events',
      'market_positions',
    ]))
    expect(execution.summary.artifact_refs.map((ref) => ref.artifact_type)).toEqual(expect.arrayContaining([
      'market_events',
      'market_positions',
    ]))
  })

  it('persists provenance bundles as evidence artifacts with stable layout refs', () => {
    const snapshot = makeMarketSnapshot()
    const resolutionPolicy = resolutionPolicySchema.parse({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      status: 'eligible',
      manual_review_required: false,
      reasons: [],
      primary_sources: snapshot.source_urls,
      evaluated_at: '2026-04-08T00:03:05.000Z',
    })
    const evidencePackets = [makeEvidencePacket(snapshot, 'evidence-btc-apr-2026-006')]
    const forecast = forecastPacketSchema.parse({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      basis: 'market_midpoint',
      probability_yes: 0.56,
      confidence: 0.6,
      rationale: 'Provenance bundle coverage.',
      evidence_refs: evidencePackets.map((packet) => packet.evidence_id),
      produced_at: '2026-04-08T00:03:10.000Z',
    })
    const recommendation = marketRecommendationPacketSchema.parse({
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      action: 'wait',
      side: null,
      confidence: 0.6,
      fair_value_yes: 0.56,
      market_price_yes: 0.49,
      market_bid_yes: 0.48,
      market_ask_yes: 0.5,
      edge_bps: 200,
      spread_bps: 200,
      reasons: ['Provenance bundle should round-trip.'],
      risk_flags: [],
      produced_at: '2026-04-08T00:03:12.000Z',
    })
    const manifest = runManifestSchema.parse({
      run_id: 'pm-run-006',
      mode: 'advise',
      venue: snapshot.venue,
      market_id: snapshot.market.market_id,
      market_slug: snapshot.market.slug,
      actor: 'operator',
      started_at: '2026-04-08T00:03:00.000Z',
      completed_at: '2026-04-08T00:03:20.000Z',
      status: 'completed',
      config_hash: 'cfg-store-layout-004',
    })
    const provenanceBundle = predictionMarketProvenanceBundleSchema.parse({
      run_id: manifest.run_id,
      venue: snapshot.venue,
      market_id: snapshot.market.market_id,
      generated_at: '2026-04-08T00:03:14.000Z',
      provenance_refs: ['run:pm-run-006', 'evidence:evidence-btc-apr-2026-006'],
      evidence_refs: evidencePackets.map((packet) => packet.evidence_id),
      artifact_refs: [],
      links: [
        {
          ref: 'run:pm-run-006',
          kind: 'artifact',
          label: 'run manifest lineage',
        },
      ],
      summary: 'Provenance bundle for the persisted prediction market run.',
    })

    const execution = persistPredictionMarketExecution({
      workspaceId: 10,
      runId: manifest.run_id,
      venue: manifest.venue,
      mode: manifest.mode,
      snapshot,
      resolutionPolicy,
      evidencePackets,
      forecast,
      recommendation,
      provenanceBundle,
      manifest,
    })

    const details = getPredictionMarketRunDetails('pm-run-006', 10)
    expect(details).not.toBeNull()
    if (!details) return

    expect(details.artifacts.map((artifact) => artifact.artifact_type)).toContain('provenance_bundle')

    const storedProvenance = details.artifacts.find((artifact) => artifact.artifact_type === 'provenance_bundle')
    expect(storedProvenance).toBeDefined()
    expect(storedProvenance?.payload).toMatchObject({
      provenance_refs: ['run:pm-run-006', 'evidence:evidence-btc-apr-2026-006'],
      summary: 'Provenance bundle for the persisted prediction market run.',
    })

    const storedManifest = runManifestSchema.parse(
      details.artifacts.find((artifact) => artifact.artifact_type === 'run_manifest')?.payload,
    )
    expect(storedManifest.artifact_refs.map((ref) => ref.artifact_type)).toContain('provenance_bundle')
    expect(execution.summary.artifact_refs.map((ref) => ref.artifact_type)).toContain('provenance_bundle')
    expect(execution.summary.manifest.artifact_refs.map((ref) => ref.artifact_type)).toContain('provenance_bundle')
  })
})
