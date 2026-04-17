import { existsSync } from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { PredictionMarketsError } from '@/lib/prediction-markets/errors'
import type {
  MarketSnapshot,
  PredictionMarketAdviceRequestMode,
  PredictionMarketTimesFMLane,
  PredictionMarketTimesFMMode,
} from '@/lib/prediction-markets/schemas'

export type PredictionMarketTimesFMSidecarLaneStatus = 'ready' | 'abstained' | 'ineligible'
export type PredictionMarketTimesFMSidecarHealthStatus = 'healthy' | 'degraded' | 'blocked'

export type PredictionMarketTimesFMSidecarLane = {
  lane: PredictionMarketTimesFMLane
  status: PredictionMarketTimesFMSidecarLaneStatus
  eligible: boolean
  influences_research_aggregate: boolean
  comparator_id: string
  comparator_kind: string
  basis: string
  model_family: string
  pipeline_id: string
  pipeline_version: string
  probability_yes: number | null
  confidence: number | null
  probability_band?: {
    low?: number
    center?: number
    high?: number
  } | null
  quantiles?: Record<string, number> | null
  horizon: number | null
  summary: string
  rationale: string
  reasons: string[]
  source_refs: string[]
  metadata: {
    features_used?: string[]
    content_hash?: string
    provenance?: Record<string, unknown>
  } & Record<string, unknown>
}

export type PredictionMarketTimesFMSidecar = {
  schema_version: string
  sidecar_name: 'timesfm_sidecar'
  run_id: string
  market_id: string
  venue: string
  question: string
  requested_mode: PredictionMarketTimesFMMode
  effective_mode: PredictionMarketTimesFMMode
  requested_lanes: PredictionMarketTimesFMLane[]
  selected_lane: PredictionMarketTimesFMLane | null
  generated_at: string
  health: {
    healthy: boolean
    status: PredictionMarketTimesFMSidecarHealthStatus
    backend: string
    dependency_status: string
    issues: string[]
    summary: string
  }
  vendor: Record<string, unknown>
  lanes: Partial<Record<PredictionMarketTimesFMLane, PredictionMarketTimesFMSidecarLane>>
  summary: string
  metadata: {
    content_hash?: string
    cross_venue_gap_bps?: number | null
  } & Record<string, unknown>
}

export type ResolvedPredictionMarketTimesFMOptions = {
  mode: PredictionMarketTimesFMMode
  lanes: PredictionMarketTimesFMLane[]
}

export function resolvePredictionMarketTimesFMOptions(input: {
  requestMode: PredictionMarketAdviceRequestMode
  requestedMode?: PredictionMarketTimesFMMode | null
  requestedLanes?: readonly PredictionMarketTimesFMLane[] | null
}): ResolvedPredictionMarketTimesFMOptions {
  const mode = input.requestedMode ?? (input.requestMode === 'predict_deep' ? 'auto' : 'off')
  const lanes = (input.requestedLanes && input.requestedLanes.length > 0)
    ? [...new Set(input.requestedLanes)]
    : ['microstructure', 'event_probability'] satisfies PredictionMarketTimesFMLane[]
  return { mode, lanes }
}

export function shouldRunPredictionMarketTimesFM(input: {
  mode: PredictionMarketTimesFMMode
  lanes: readonly PredictionMarketTimesFMLane[]
}): boolean {
  return input.mode !== 'off' && input.lanes.length > 0
}

export function getPredictionMarketTimesFMLane(
  sidecar: PredictionMarketTimesFMSidecar | null | undefined,
  lane: PredictionMarketTimesFMLane,
): PredictionMarketTimesFMSidecarLane | null {
  const candidate = sidecar?.lanes?.[lane]
  return candidate ?? null
}

export function summarizePredictionMarketTimesFMSidecar(
  sidecar: PredictionMarketTimesFMSidecar | null | undefined,
): string | null {
  if (!sidecar) return null
  const parts = [
    `mode=${sidecar.requested_mode}`,
    `health=${sidecar.health.status}`,
    `selected=${sidecar.selected_lane ?? 'none'}`,
    sidecar.health.backend ? `backend=${sidecar.health.backend}` : null,
  ].filter(Boolean)
  return `timesfm: ${parts.join(' ')} summary="${sidecar.summary}"`
}

function resolveRepoRootCandidates(): string[] {
  const cwd = process.cwd()
  return [
    path.resolve(cwd),
    path.resolve(cwd, '..'),
    path.resolve(cwd, '..', '..'),
  ]
}

function resolveTimesFMScriptPath(): string {
  for (const candidateRoot of resolveRepoRootCandidates()) {
    const candidate = path.resolve(candidateRoot, 'prediction_markets', 'timesfm_sidecar_cli.py')
    if (existsSync(candidate)) return candidate
  }
  return path.resolve(process.cwd(), 'prediction_markets', 'timesfm_sidecar_cli.py')
}

function resolveRepoRootForScript(scriptPath: string): string {
  return path.resolve(path.dirname(scriptPath), '..')
}

function safeNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function extractCatalystDueAt(snapshot: MarketSnapshot): string | null {
  return typeof snapshot.market.end_at === 'string' && snapshot.market.end_at.length > 0
    ? snapshot.market.end_at
    : null
}

export function runPredictionMarketTimesFMSidecar(input: {
  runId: string
  requestMode: PredictionMarketAdviceRequestMode
  mode: PredictionMarketTimesFMMode
  lanes: readonly PredictionMarketTimesFMLane[]
  snapshot: MarketSnapshot
  regime?: string | null
  crossVenueGapBps?: number | null
}): PredictionMarketTimesFMSidecar {
  const scriptPath = resolveTimesFMScriptPath()
  const repoRoot = resolveRepoRootForScript(scriptPath)
  const pythonBinary = process.env.SWARM_TIMESFM_PYTHON || 'python3'
  const timeoutMs = Number(process.env.SWARM_TIMESFM_TIMEOUT_MS || '8000')
  const requestPayload = {
    run_id: input.runId,
    market_id: input.snapshot.market.market_id,
    venue: input.snapshot.venue,
    question: input.snapshot.market.question,
    request_mode: input.requestMode,
    timesfm_mode: input.mode,
    timesfm_lanes: input.lanes,
    history: input.snapshot.history ?? [],
    midpoint_yes: input.snapshot.midpoint_yes ?? null,
    yes_price: input.snapshot.yes_price ?? null,
    spread_bps: input.snapshot.spread_bps ?? null,
    depth_near_touch: safeNumber(input.snapshot.book?.depth_near_touch),
    liquidity_usd: safeNumber(input.snapshot.market.liquidity_usd),
    volume_24h_usd: safeNumber(input.snapshot.market.volume_24h_usd),
    cross_venue_gap_bps: safeNumber(input.crossVenueGapBps),
    catalyst_due_at: extractCatalystDueAt(input.snapshot),
    regime: input.regime ?? null,
    force_fixture_backend: process.env.SWARM_TIMESFM_FIXTURE_BACKEND === '1',
  }
  const result = spawnSync(pythonBinary, [scriptPath], {
    cwd: repoRoot,
    input: JSON.stringify(requestPayload),
    encoding: 'utf-8',
    timeout: Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : 8000,
    maxBuffer: 1024 * 1024 * 4,
  })

  if (result.error) {
    throw new PredictionMarketsError(`TimesFM sidecar failed: ${result.error.message}`, {
      status: 503,
      code: 'timesfm_sidecar_failed',
    })
  }
  if (result.status !== 0) {
    throw new PredictionMarketsError(
      `TimesFM sidecar exited with code ${result.status}: ${(result.stderr || '').trim() || 'unknown error'}`,
      {
        status: 503,
        code: 'timesfm_sidecar_failed',
      },
    )
  }

  let parsed: PredictionMarketTimesFMSidecar
  try {
    parsed = JSON.parse(result.stdout) as PredictionMarketTimesFMSidecar
  } catch (error) {
    throw new PredictionMarketsError('TimesFM sidecar returned invalid JSON', {
      status: 503,
      code: 'timesfm_sidecar_invalid_json',
    })
  }
  return parsed
}
