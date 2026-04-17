import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { PredictionMarketsError } from '@/lib/prediction-markets/errors'

export type PredictionMarketLiveExecutionBridgeInput = {
  sourceRunId: string
  executionRunId: string
  marketId?: string | null
  marketSlug?: string | null
  decisionPacket?: Record<string, unknown> | null
  governanceContext?: Record<string, unknown> | null
  researchContext?: Record<string, unknown> | null
  stake: number
  actor: string
  approvedIntentId?: string | null
  approvedBy?: string[]
  persist?: boolean
  dryRun?: boolean
  allowLiveExecution?: boolean
  authorized?: boolean
  complianceApproved?: boolean
  scopes?: string[]
}

export type PredictionMarketLiveExecutionBridgeStatus = {
  venue: string
  selected_backend_mode: string
  live_execution_supported: boolean
  live_transport_ready: boolean
  live_order_endpoint: string | null
  cancel_order_endpoint: string | null
  blockers: string[]
  summary: string
}

function readEnvText(...names: string[]): string | null {
  for (const name of names) {
    const value = process.env[name]
    const normalized = typeof value === 'string' ? value.trim() : ''
    if (normalized) return normalized
  }
  return null
}

function readEnvTruthy(...names: string[]): boolean {
  for (const name of names) {
    const value = process.env[name]
    const normalized = typeof value === 'string' ? value.trim().toLowerCase() : ''
    if (['1', 'true', 'yes', 'on', 'enabled', 'mock'].includes(normalized)) {
      return true
    }
  }
  return false
}

function resolveExecutionEndpoint(pathOrUrl: string | null, baseUrl: string | null): string | null {
  const candidate = pathOrUrl?.trim() ?? ''
  if (!candidate) return null

  try {
    const direct = new URL(candidate)
    if (direct.protocol === 'http:' || direct.protocol === 'https:') {
      return direct.toString()
    }
  } catch {
    // Keep going: a relative path may still be resolvable from an execution base URL.
  }

  if (!baseUrl) return null

  try {
    return new URL(candidate.replace(/^\/+/, ''), `${baseUrl.replace(/\/+$/, '')}/`).toString()
  } catch {
    return null
  }
}

function resolvePolymarketSelectedBackendMode(): string {
  const requestedMode = readEnvText('POLYMARKET_EXECUTION_BACKEND', 'POLYMARKET_EXECUTION_MODE')
  if (requestedMode) return requestedMode.toLowerCase()
  if (readEnvTruthy('POLYMARKET_EXECUTION_MOCK', 'POLYMARKET_MOCK_EXECUTION')) return 'mock'

  const authToken = readEnvText(
    'POLYMARKET_EXECUTION_AUTH_TOKEN',
    'POLYMARKET_AUTH_TOKEN',
    'POLYMARKET_API_KEY',
    'POLYMARKET_CLOB_API_KEY',
  )
  const liveOrderPath = readEnvText('POLYMARKET_EXECUTION_LIVE_ORDER_PATH', 'POLYMARKET_ORDER_PATH')
  const cancelOrderPath = readEnvText('POLYMARKET_EXECUTION_CANCEL_PATH', 'POLYMARKET_CANCEL_PATH')
  if (authToken && liveOrderPath && cancelOrderPath) return 'live'

  const genericMode = readEnvText('PREDICTION_MARKETS_BACKEND')
  return genericMode ? genericMode.toLowerCase() : 'auto'
}

export function resolvePredictionMarketLiveExecutionBridgeStatus(
  venue: string | null | undefined,
): PredictionMarketLiveExecutionBridgeStatus {
  const normalizedVenue = String(venue ?? 'unknown').trim().toLowerCase() || 'unknown'
  if (normalizedVenue !== 'polymarket') {
    return {
      venue: normalizedVenue,
      selected_backend_mode: 'unsupported',
      live_execution_supported: false,
      live_transport_ready: false,
      live_order_endpoint: null,
      cancel_order_endpoint: null,
      blockers: [`live_execution_unsupported:${normalizedVenue}`],
      summary: `Live execution transport is unsupported for ${normalizedVenue}.`,
    }
  }

  const selectedBackendMode = resolvePolymarketSelectedBackendMode()
  const authToken = readEnvText(
    'POLYMARKET_EXECUTION_AUTH_TOKEN',
    'POLYMARKET_AUTH_TOKEN',
    'POLYMARKET_API_KEY',
    'POLYMARKET_CLOB_API_KEY',
  )
  const executionBaseUrl = readEnvText(
    'POLYMARKET_EXECUTION_BASE_URL',
    'POLYMARKET_EXECUTION_API_BASE_URL',
  )
  const liveOrderEndpoint = resolveExecutionEndpoint(
    readEnvText('POLYMARKET_EXECUTION_LIVE_ORDER_PATH', 'POLYMARKET_ORDER_PATH'),
    executionBaseUrl,
  )
  const cancelOrderEndpoint = resolveExecutionEndpoint(
    readEnvText('POLYMARKET_EXECUTION_CANCEL_PATH', 'POLYMARKET_CANCEL_PATH'),
    executionBaseUrl,
  )
  const mockTransport = selectedBackendMode === 'mock' || readEnvTruthy('POLYMARKET_EXECUTION_MOCK', 'POLYMARKET_MOCK_EXECUTION')
  const liveTransportReady = Boolean(
    selectedBackendMode === 'live'
    && authToken
    && liveOrderEndpoint
    && cancelOrderEndpoint
    && !mockTransport
  )

  const blockers = [] as string[]
  if (mockTransport) blockers.push('live_transport_mock_mode')
  if (selectedBackendMode !== 'live') blockers.push('live_transport_not_configured')
  if (!authToken) blockers.push('live_transport_missing_auth_token')
  if (!liveOrderEndpoint || !cancelOrderEndpoint) blockers.push('live_transport_missing_endpoint')

  return {
    venue: normalizedVenue,
    selected_backend_mode: selectedBackendMode,
    live_execution_supported: true,
    live_transport_ready: liveTransportReady,
    live_order_endpoint: liveOrderEndpoint,
    cancel_order_endpoint: cancelOrderEndpoint,
    blockers: liveTransportReady ? [] : Array.from(new Set(blockers)),
    summary: liveTransportReady
      ? 'Polymarket live transport is configured and can materialize governed live execution.'
      : 'Polymarket live transport is not configured yet; the canonical live surface remains preflight-first until the execution endpoints and credentials are bound.',
  }
}

const PYTHON_BRIDGE_SCRIPT = String.raw`
import dataclasses
import json
import sys
import traceback
from datetime import date, datetime
from enum import Enum
from pathlib import Path

REPO_ROOT = Path.cwd()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from prediction_markets.compat import PredictionMarketAdvisor


def to_jsonable(value):
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump(mode="json"))
    if dataclasses.is_dataclass(value):
        return to_jsonable(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def enrich_result(result, payload):
    jsonable = to_jsonable(result)
    if not isinstance(jsonable, dict):
        return jsonable

    jsonable["governance_context"] = to_jsonable(payload.get("governance_context") or {})
    jsonable["research_context"] = to_jsonable(payload.get("research_context") or {})
    jsonable["bridge_trace"] = {
        "source_run_id": payload.get("source_run_id"),
        "execution_run_id": payload.get("execution_run_id"),
        "approved_intent_id": payload.get("approved_intent_id"),
        "decision_packet_present": bool(payload.get("decision_packet")),
    }
    return jsonable


def main():
    payload = json.load(sys.stdin)
    advisor = PredictionMarketAdvisor(
        backend_mode=payload.get("backend_mode"),
        base_dir=payload.get("base_dir"),
    )
    result = advisor.live_execute(
        market_id=payload.get("market_id"),
        slug=payload.get("slug"),
        decision_packet=payload.get("decision_packet"),
        evidence_inputs=list(payload.get("evidence_inputs") or []),
        stake=float(payload.get("stake") or 10.0),
        persist=bool(payload.get("persist", True)),
        run_id=payload.get("execution_run_id"),
        dry_run=bool(payload.get("dry_run", True)),
        allow_live_execution=bool(payload.get("allow_live_execution", False)),
        authorized=bool(payload.get("authorized", False)),
        compliance_approved=bool(payload.get("compliance_approved", False)),
        principal=str(payload.get("principal") or ""),
        scopes=list(payload.get("scopes") or []),
        require_human_approval_before_live=True,
        human_approval_passed=True,
        human_approval_actor=str(payload.get("human_approval_actor") or ""),
        human_approval_reason=str(payload.get("human_approval_reason") or ""),
    )
    json.dump({"ok": True, "payload": enrich_result(result, payload)}, sys.stdout, sort_keys=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        json.dump(
            {
                "ok": False,
                "error": str(exc),
                "error_type": exc.__class__.__name__,
            },
            sys.stdout,
            sort_keys=True,
        )
        sys.exit(1)
`

function resolvePredictionMarketsRepoRoot(): string {
  const configuredRoot = process.env.PREDICTION_MARKETS_REPO_ROOT?.trim()
  const candidates = [
    configuredRoot,
    process.cwd(),
    path.resolve(process.cwd(), '..'),
    path.resolve(process.cwd(), '../..'),
    path.resolve(process.cwd(), '../../..'),
  ].filter((candidate): candidate is string => Boolean(candidate))

  for (const candidate of candidates) {
    if (existsSync(path.resolve(candidate, 'main.py'))) {
      return candidate
    }
  }

  throw new PredictionMarketsError('Prediction market live execution bridge could not resolve the swarm repo root', {
    status: 500,
    code: 'live_execution_repo_root_unavailable',
  })
}

function resolvePredictionMarketsPython(repoRoot: string): string {
  const configuredPython = process.env.PREDICTION_MARKETS_PYTHON?.trim()
  if (configuredPython) return configuredPython

  const venvPython = path.resolve(repoRoot, '.venv/bin/python')
  if (existsSync(venvPython)) return venvPython

  const venvPython3 = path.resolve(repoRoot, '.venv/bin/python3')
  if (existsSync(venvPython3)) return venvPython3

  return 'python3'
}

function parseBridgeResponse(stdout: string): Record<string, unknown> {
  const normalized = stdout.trim()
  if (!normalized) {
    throw new PredictionMarketsError('Prediction market live execution bridge returned no payload', {
      status: 502,
      code: 'live_execution_bridge_empty_response',
    })
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(normalized)
  } catch {
    throw new PredictionMarketsError('Prediction market live execution bridge returned invalid JSON', {
      status: 502,
      code: 'live_execution_bridge_invalid_json',
    })
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new PredictionMarketsError('Prediction market live execution bridge returned an invalid envelope', {
      status: 502,
      code: 'live_execution_bridge_invalid_envelope',
    })
  }

  return parsed as Record<string, unknown>
}

function stableSerialize(value: unknown): string {
  if (value == null || typeof value !== 'object') {
    return JSON.stringify(value)
  }

  if (Array.isArray(value)) {
    return `[${value.map((item) => stableSerialize(item)).join(',')}]`
  }

  return `{${Object.entries(value as Record<string, unknown>)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, item]) => `${JSON.stringify(key)}:${stableSerialize(item)}`)
    .join(',')}}`
}

function hashText(value: string): string {
  return createHash('sha256').update(value).digest('hex')
}

function buildGovernanceContext(input: PredictionMarketLiveExecutionBridgeInput): Record<string, unknown> {
  return {
    source_run_id: input.sourceRunId,
    execution_run_id: input.executionRunId,
    approved_intent_id: input.approvedIntentId ?? null,
    approved_by: input.approvedBy ?? [],
    actor: input.actor,
    persist: input.persist ?? true,
    dry_run: input.dryRun ?? false,
    allow_live_execution: input.allowLiveExecution ?? true,
    authorized: input.authorized ?? true,
    compliance_approved: input.complianceApproved ?? true,
    scopes: input.scopes ?? ['prediction_markets:execute'],
    governance_hash: hashText(stableSerialize({
      source_run_id: input.sourceRunId,
      execution_run_id: input.executionRunId,
      approved_intent_id: input.approvedIntentId ?? null,
      approved_by: input.approvedBy ?? [],
      actor: input.actor,
      persist: input.persist ?? true,
      dry_run: input.dryRun ?? false,
      allow_live_execution: input.allowLiveExecution ?? true,
      authorized: input.authorized ?? true,
      compliance_approved: input.complianceApproved ?? true,
      scopes: input.scopes ?? ['prediction_markets:execute'],
    })).slice(0, 16),
  }
}

function buildResearchContext(input: PredictionMarketLiveExecutionBridgeInput): Record<string, unknown> {
  const decisionPacket = input.decisionPacket
  const record = decisionPacket && typeof decisionPacket === 'object' && !Array.isArray(decisionPacket)
    ? decisionPacket as Record<string, unknown>
    : null

  const refs = [
    ...(Array.isArray(record?.source_packet_refs) ? record.source_packet_refs : []),
    ...(Array.isArray(record?.social_context_refs) ? record.social_context_refs : []),
    ...(Array.isArray(record?.market_context_refs) ? record.market_context_refs : []),
    ...(Array.isArray(record?.comparable_market_refs) ? record.comparable_market_refs : []),
  ].filter((value): value is string => typeof value === 'string' && value.trim().length > 0)

  return {
    decision_packet_present: record != null,
    decision_packet_correlation_id: typeof record?.correlation_id === 'string' ? record.correlation_id : null,
    decision_packet_probability_estimate: typeof record?.probability_estimate === 'number' ? record.probability_estimate : null,
    decision_packet_topic: typeof record?.topic === 'string' ? record.topic : null,
    decision_packet_objective: typeof record?.objective === 'string' ? record.objective : null,
    decision_packet_mode_used: typeof record?.mode_used === 'string' ? record.mode_used : null,
    decision_packet_engine_used: typeof record?.engine_used === 'string' ? record.engine_used : null,
    decision_packet_runtime_used: typeof record?.runtime_used === 'string' ? record.runtime_used : null,
    decision_packet_requires_manual_review: typeof record?.requires_manual_review === 'boolean' ? record.requires_manual_review : null,
    decision_packet_research_refs: refs,
    research_context: input.researchContext ?? null,
  }
}

export function executePredictionMarketLiveExecutionBridge(
  input: PredictionMarketLiveExecutionBridgeInput,
): Record<string, unknown> {
  const repoRoot = resolvePredictionMarketsRepoRoot()
  const pythonExecutable = resolvePredictionMarketsPython(repoRoot)
  const bridgePayload = {
    source_run_id: input.sourceRunId,
    execution_run_id: input.executionRunId,
    market_id: input.marketId ?? null,
    slug: input.marketSlug ?? null,
    decision_packet: input.decisionPacket ?? null,
    governance_context: input.governanceContext ?? buildGovernanceContext(input),
    research_context: input.researchContext ?? buildResearchContext(input),
    evidence_inputs: [],
    stake: input.stake,
    persist: input.persist ?? true,
    dry_run: input.dryRun ?? false,
    allow_live_execution: input.allowLiveExecution ?? true,
    authorized: input.authorized ?? true,
    compliance_approved: input.complianceApproved ?? true,
    principal: input.actor,
    scopes: input.scopes ?? ['prediction_markets:execute'],
    human_approval_actor: input.approvedBy?.length ? input.approvedBy.join(',') : input.actor,
    human_approval_reason: input.approvedIntentId
      ? `approved_live_intent:${input.approvedIntentId};source_run_id:${input.sourceRunId}`
      : `source_run_id:${input.sourceRunId}`,
  }

  const child = spawnSync(pythonExecutable, ['-c', PYTHON_BRIDGE_SCRIPT], {
    cwd: repoRoot,
    encoding: 'utf-8',
    input: JSON.stringify(bridgePayload),
    env: {
      ...process.env,
      PYTHONPATH: [repoRoot, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
    },
    maxBuffer: 10 * 1024 * 1024,
  })

  if (child.error) {
    throw new PredictionMarketsError(
      `Prediction market live execution bridge failed to start: ${child.error.message}`,
      {
        status: 502,
        code: 'live_execution_bridge_spawn_failed',
      },
    )
  }

  const envelope = parseBridgeResponse(child.stdout ?? '')
  const ok = envelope.ok === true

  if (child.status !== 0 || !ok) {
    const error = typeof envelope.error === 'string' && envelope.error.trim().length > 0
      ? envelope.error.trim()
      : (child.stderr ?? '').trim()
      || 'unknown live execution bridge failure'

    throw new PredictionMarketsError(
      `Prediction market live execution bridge failed: ${error}`,
      {
        status: 502,
        code: 'live_execution_bridge_failed',
      },
    )
  }

  const payload = envelope.payload
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new PredictionMarketsError('Prediction market live execution bridge returned no payload body', {
      status: 502,
      code: 'live_execution_bridge_missing_payload',
    })
  }

  return payload as Record<string, unknown>
}
