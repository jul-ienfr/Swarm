import { EventEmitter } from 'node:events'
import { randomUUID } from 'node:crypto'

import { PredictionMarketsError } from '@/lib/prediction-markets/errors'
import {
  getPredictionMarketRunDetails,
  preparePredictionMarketRunLive,
} from '@/lib/prediction-markets/service'
import type { PredictionMarketVenue } from '@/lib/prediction-markets/schemas'

export type PredictionDashboardLiveIntentStatus =
  | 'pending_approval'
  | 'approved'
  | 'rejected'

export type PredictionDashboardApprovalState = {
  required: 1
  current: number
  approvers: string[]
  status: 'pending' | 'approved' | 'rejected'
  requested_by: string
  requested_at: string
  approved_at: string | null
  rejected_at: string | null
}

export type PredictionDashboardEvent = {
  event_id: string
  event_type:
    | 'snapshot'
    | 'run_created'
    | 'run_updated'
    | 'venue_changed'
    | 'benchmark_changed'
    | 'live_intent_created'
    | 'live_intent_approved'
    | 'live_intent_rejected'
    | 'live_intent_prepared'
    | 'live_intent_failed'
    | 'health_changed'
    | 'reconciliation_drift'
    | 'capital_blocker'
  created_at: string
  workspace_id: number
  venue?: PredictionMarketVenue
  run_id?: string
  intent_id?: string
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical'
  summary: string
  payload: Record<string, unknown>
}

export type PredictionDashboardLiveIntent = {
  intent_id: string
  workspace_id: number
  run_id: string
  venue: PredictionMarketVenue
  requested_by: string
  requested_at: string
  updated_at: string
  requested_path: string | null
  selected_path: string | null
  selected_preview: unknown
  selected_preview_source: string | null
  live_surface: unknown
  execution_request: unknown
  benchmark_state: {
    ready: boolean
    gate_kind: string | null
    evidence_level: string | null
    status: string | null
    blockers: string[]
    summary: string | null
  }
  approval_state: PredictionDashboardApprovalState
  execution_state: {
    status: 'not_requested' | 'prepared' | 'failed'
    requested_at: string | null
    requested_by: string | null
    receipt: unknown | null
    error: string | null
  }
  audit: Array<{
    actor: string
    action: 'created' | 'approved' | 'rejected' | 'prepared' | 'failed'
    at: string
    note?: string
  }>
  notes: string[]
}

type DashboardControlState = {
  intents: Map<string, PredictionDashboardLiveIntent>
  events: PredictionDashboardEvent[]
  emitter: EventEmitter
}

const GLOBAL_KEY = Symbol.for('prediction-markets.dashboard-control')

function getState(): DashboardControlState {
  const globalScope = globalThis as typeof globalThis & {
    [GLOBAL_KEY]?: DashboardControlState
  }

  if (!globalScope[GLOBAL_KEY]) {
    globalScope[GLOBAL_KEY] = {
      intents: new Map<string, PredictionDashboardLiveIntent>(),
      events: [],
      emitter: new EventEmitter(),
    }
  }

  return globalScope[GLOBAL_KEY]
}

function nowIso() {
  return new Date().toISOString()
}

function pushEvent(event: PredictionDashboardEvent) {
  const state = getState()
  state.events.push(event)
  if (state.events.length > 200) {
    state.events.splice(0, state.events.length - 200)
  }
  state.emitter.emit('event', event)
}

function summarizeBenchmarkState(detail: Awaited<ReturnType<typeof getPredictionMarketRunDetails>>) {
  return {
    ready: detail?.benchmark_promotion_ready === true,
    gate_kind: detail?.benchmark_promotion_gate_kind ?? detail?.research_promotion_gate_kind ?? null,
    evidence_level: detail?.benchmark_evidence_level ?? detail?.research_benchmark_evidence_level ?? null,
    status: detail?.benchmark_promotion_status ?? detail?.research_benchmark_promotion_status ?? null,
    blockers: [
      ...(detail?.benchmark_gate_blockers ?? []),
      ...(detail?.benchmark_gate_reasons ?? []),
      ...(detail?.research_benchmark_gate_blockers ?? []),
    ],
    summary:
      detail?.benchmark_promotion_blocker_summary ??
      detail?.benchmark_promotion_summary ??
      detail?.research_benchmark_promotion_blocker_summary ??
      detail?.research_benchmark_promotion_summary ??
      null,
  }
}

function buildApprovalState(requestedBy: string, requestedAt: string): PredictionDashboardApprovalState {
  return {
    required: 1,
    current: 0,
    approvers: [],
    status: 'pending',
    requested_by: requestedBy,
    requested_at: requestedAt,
    approved_at: null,
    rejected_at: null,
  }
}

function recalculateApprovalState(intent: PredictionDashboardLiveIntent): PredictionDashboardApprovalState {
  const approvers = intent.approval_state.approvers
  const rejected = intent.audit.some((entry) => entry.action === 'rejected')
  const approvedAt = intent.audit.find((entry) => entry.action === 'approved')?.at ?? null
  const rejectedAt = intent.audit.find((entry) => entry.action === 'rejected')?.at ?? null

  return {
    required: 1,
    current: approvers.length,
    approvers,
    requested_by: intent.approval_state.requested_by,
    requested_at: intent.approval_state.requested_at,
    approved_at: approvedAt,
    rejected_at: rejectedAt,
    status: rejected
      ? 'rejected'
      : approvers.length >= 1
        ? 'approved'
        : 'pending',
  }
}

export function resolveDashboardActor(request: Request, fallback = 'local-operator'): string {
  const candidates = [
    request.headers.get('x-prediction-dashboard-actor'),
    request.headers.get('x-prediction-actor'),
    request.headers.get('x-dashboard-actor'),
    request.headers.get('x-operator-name'),
    request.headers.get('x-user'),
  ]

  for (const candidate of candidates) {
    const normalized = candidate?.trim()
    if (normalized) return normalized
  }

  return fallback
}

export function listDashboardLiveIntents(runId?: string, workspaceId = 1): PredictionDashboardLiveIntent[] {
  const state = getState()
  return [...state.intents.values()]
    .filter((intent) => intent.workspace_id === workspaceId && (runId == null || intent.run_id === runId))
    .sort((a, b) => b.requested_at.localeCompare(a.requested_at))
}

export function getDashboardLiveIntent(intentId: string, workspaceId = 1): PredictionDashboardLiveIntent | null {
  const intent = getState().intents.get(intentId)
  if (!intent || intent.workspace_id !== workspaceId) return null
  return structuredClone(intent)
}

export function createDashboardLiveIntent(input: {
  runId: string
  workspaceId: number
  actor: string
  note?: string
}) {
  const detail = getPredictionMarketRunDetails(input.runId, input.workspaceId)
  if (!detail) {
    throw new PredictionMarketsError('Prediction market run not found', {
      status: 404,
      code: 'run_not_found',
    })
  }

  const liveSurface = preparePredictionMarketRunLive({
    runId: input.runId,
    workspaceId: input.workspaceId,
  })

  if (liveSurface.live_status !== 'ready' || liveSurface.live_route_allowed !== true) {
    throw new PredictionMarketsError('Live intent cannot be created because the live surface is not ready', {
      status: 409,
      code: 'live_not_ready',
    })
  }

  const requestedAt = nowIso()
  const intent: PredictionDashboardLiveIntent = {
    intent_id: `live-intent-${randomUUID()}`,
    workspace_id: input.workspaceId,
    run_id: input.runId,
    venue: detail.venue,
    requested_by: input.actor,
    requested_at: requestedAt,
    updated_at: requestedAt,
    requested_path: liveSurface.execution_projection_selected_path ?? liveSurface.live_path?.path ?? null,
    selected_path: liveSurface.execution_projection_selected_path ?? liveSurface.live_path?.path ?? null,
    selected_preview: liveSurface.execution_projection_selected_preview ?? liveSurface.live_trade_intent_preview ?? null,
    selected_preview_source:
      liveSurface.execution_projection_selected_preview_source ??
      liveSurface.live_trade_intent_preview_source ??
      null,
    live_surface: liveSurface,
    execution_request: null,
    benchmark_state: summarizeBenchmarkState(detail),
    approval_state: buildApprovalState(input.actor, requestedAt),
    execution_state: {
      status: 'not_requested',
      requested_at: null,
      requested_by: null,
      receipt: null,
      error: null,
    },
    audit: [
      {
        actor: input.actor,
        action: 'created',
        at: requestedAt,
        note: input.note,
      },
    ],
    notes: input.note ? [input.note] : [],
  }

  getState().intents.set(intent.intent_id, intent)
  pushEvent({
    event_id: `evt-${randomUUID()}`,
    event_type: 'live_intent_created',
    created_at: requestedAt,
    workspace_id: input.workspaceId,
    venue: detail.venue,
    run_id: input.runId,
    intent_id: intent.intent_id,
    severity: 'high',
    summary: `Live intent created for run ${input.runId}`,
    payload: {
      intent_id: intent.intent_id,
      run_id: input.runId,
      venue: detail.venue,
      requested_by: input.actor,
      benchmark_state: intent.benchmark_state,
    },
  })

  return structuredClone(intent)
}

export function approveDashboardLiveIntent(input: {
  intentId: string
  workspaceId: number
  actor: string
  note?: string
}) {
  const state = getState()
  const intent = state.intents.get(input.intentId)
  if (!intent || intent.workspace_id !== input.workspaceId) {
    throw new PredictionMarketsError('Live intent not found', {
      status: 404,
      code: 'live_intent_not_found',
    })
  }

  if (intent.approval_state.status === 'rejected') {
    throw new PredictionMarketsError('Rejected live intent cannot be approved', {
      status: 409,
      code: 'live_intent_rejected',
    })
  }

  if (intent.approval_state.requested_by === input.actor || intent.approval_state.approvers.includes(input.actor)) {
    throw new PredictionMarketsError('Live intent requires a distinct second approver', {
      status: 409,
      code: 'self_approval_not_allowed',
    })
  }

  const approvedAt = nowIso()
  intent.approval_state.approvers = [...intent.approval_state.approvers, input.actor]
  intent.approval_state = recalculateApprovalState(intent)
  intent.audit.push({
    actor: input.actor,
    action: 'approved',
    at: approvedAt,
    note: input.note,
  })
  intent.updated_at = approvedAt

  if (intent.approval_state.status === 'approved') {
    try {
      const liveSurface = preparePredictionMarketRunLive({
        runId: intent.run_id,
        workspaceId: intent.workspace_id,
      })
      intent.live_surface = liveSurface
      intent.execution_request = {
        requested_at: approvedAt,
        requested_by: input.actor,
        transport_mode: 'preflight_only',
        live_status: liveSurface.live_status,
        live_route_allowed: liveSurface.live_route_allowed,
        live_blocking_reasons: liveSurface.live_blocking_reasons,
        summary: liveSurface.summary,
      }
      intent.execution_state = {
        status: 'prepared',
        requested_at: approvedAt,
        requested_by: input.actor,
        receipt: intent.execution_request,
        error: null,
      }
      intent.audit.push({
        actor: input.actor,
        action: 'prepared',
        at: approvedAt,
        note: 'Execution request prepared from the canonical live surface.',
      })
      pushEvent({
        event_id: `evt-${randomUUID()}`,
        event_type: 'live_intent_prepared',
        created_at: approvedAt,
        workspace_id: input.workspaceId,
        venue: intent.venue,
        run_id: intent.run_id,
        intent_id: intent.intent_id,
        severity: 'high',
        summary: `Live intent approved and prepared for run ${intent.run_id}`,
        payload: {
          intent_id: intent.intent_id,
          run_id: intent.run_id,
          venue: intent.venue,
          requested_by: intent.requested_by,
          approvers: intent.approval_state.approvers,
          execution_request: intent.execution_request,
        },
      })
    } catch (error) {
      intent.execution_state = {
        status: 'failed',
        requested_at: approvedAt,
        requested_by: input.actor,
        receipt: null,
        error: error instanceof Error ? error.message : String(error),
      }
      intent.audit.push({
        actor: input.actor,
        action: 'failed',
        at: approvedAt,
        note: error instanceof Error ? error.message : String(error),
      })
      pushEvent({
        event_id: `evt-${randomUUID()}`,
        event_type: 'live_intent_failed',
        created_at: approvedAt,
        workspace_id: input.workspaceId,
        venue: intent.venue,
        run_id: intent.run_id,
        intent_id: intent.intent_id,
        severity: 'critical',
        summary: `Live intent failed to prepare for run ${intent.run_id}`,
        payload: {
          intent_id: intent.intent_id,
          run_id: intent.run_id,
          venue: intent.venue,
          error: intent.execution_state.error,
        },
      })
      throw error
    }
  }

  pushEvent({
    event_id: `evt-${randomUUID()}`,
    event_type: 'live_intent_approved',
    created_at: approvedAt,
    workspace_id: input.workspaceId,
    venue: intent.venue,
    run_id: intent.run_id,
    intent_id: intent.intent_id,
    severity: 'high',
    summary: `Live intent approved for run ${intent.run_id}`,
    payload: {
      intent_id: intent.intent_id,
      run_id: intent.run_id,
      venue: intent.venue,
      approvers: intent.approval_state.approvers,
      approval_state: intent.approval_state,
    },
  })

  return structuredClone(intent)
}

export function rejectDashboardLiveIntent(input: {
  intentId: string
  workspaceId: number
  actor: string
  note?: string
}) {
  const state = getState()
  const intent = state.intents.get(input.intentId)
  if (!intent || intent.workspace_id !== input.workspaceId) {
    throw new PredictionMarketsError('Live intent not found', {
      status: 404,
      code: 'live_intent_not_found',
    })
  }

  const rejectedAt = nowIso()
  intent.approval_state = {
    ...intent.approval_state,
    status: 'rejected',
    rejected_at: rejectedAt,
  }
  intent.updated_at = rejectedAt
  intent.audit.push({
    actor: input.actor,
    action: 'rejected',
    at: rejectedAt,
    note: input.note,
  })

  pushEvent({
    event_id: `evt-${randomUUID()}`,
    event_type: 'live_intent_rejected',
    created_at: rejectedAt,
    workspace_id: input.workspaceId,
    venue: intent.venue,
    run_id: intent.run_id,
    intent_id: intent.intent_id,
    severity: 'medium',
    summary: `Live intent rejected for run ${intent.run_id}`,
    payload: {
      intent_id: intent.intent_id,
      run_id: intent.run_id,
      venue: intent.venue,
      actor: input.actor,
      note: input.note ?? null,
    },
  })

  return structuredClone(intent)
}

export function getDashboardEvents(limit = 100): PredictionDashboardEvent[] {
  return structuredClone(getState().events.slice(-Math.max(1, Math.min(limit, 200))))
}

export function subscribeDashboardEvents(listener: (event: PredictionDashboardEvent) => void) {
  const state = getState()
  state.emitter.on('event', listener)
  return () => state.emitter.off('event', listener)
}
