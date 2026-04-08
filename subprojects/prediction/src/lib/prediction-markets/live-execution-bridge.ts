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
    json.dump({"ok": True, "payload": to_jsonable(result)}, sys.stdout, sort_keys=True)


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
