import { PredictionMarketsError } from '@/lib/prediction-markets/errors'
import {
  getPredictionMarketRunDetails,
  preparePredictionMarketRunLive,
} from '@/lib/prediction-markets/service'
import type { PredictionMarketVenueId } from '@/lib/prediction-markets/venue-ops'
import {
  publishPredictionDashboardEvent,
  type PredictionDashboardEventSeverity,
} from '@/lib/prediction-markets/dashboard-events'

export type PredictionDashboardApprovalDecision = {
  actor: string
  decided_at: string
  note: string | null
  decision: 'approved' | 'rejected'
}

export type PredictionDashboardApprovalState = {
  required_approvals: 2
  approvals: PredictionDashboardApprovalDecision[]
  rejections: PredictionDashboardApprovalDecision[]
  distinct_actor_count: number
  creator_cannot_self_approve: true
}

export type PredictionDashboardLiveIntentExecutionResult = {
  status: 'executed_preflight' | 'execution_failed'
  executed_at: string
  transport_mode: 'dashboard_bounded_preflight'
  performed_live: false
  live_execution_status: 'attempted_live_not_performed' | 'attempted_live_failed'
  receipt_summary: string
  order_trace_audit: Record<string, unknown>
}

export type PredictionDashboardLiveIntent = {
  intent_id: string
  workspace_id: number
  run_id: string
  venue: PredictionMarketVenueId | 'unknown'
  market_id: string
  created_at: string
  created_by: string
  status:
    | 'pending_approval'
    | 'pending_second_approval'
    | 'rejected'
    | 'executed_preflight'
    | 'execution_failed'
  summary: string
  selected_path: string | null
  live_status: string
  benchmark_promotion_ready: boolean
  benchmark_promotion_blockers: string[]
  benchmark_gate_blocks_live: boolean
  benchmark_gate_live_block_reason: string | null
  live_blocking_reasons: string[]
  selected_preview: Record<string, unknown> | null
  live_surface: Record<string, unknown>
  approval_state: PredictionDashboardApprovalState
  execution_result: PredictionDashboardLiveIntentExecutionResult | null
}

type CreatePredictionDashboardLiveIntentInput = {
  workspaceId: number
  runId: string
  actor: string
  note?: string | null
}

type DecisionPredictionDashboardLiveIntentInput = {
  workspaceId: number
  intentId: string
  actor: string
  note?: string | null
}

const intents = new Map<string, PredictionDashboardLiveIntent>()

function buildIntentId(runId: string): string {
  return `live-intent:${runId}:${Date.now()}:${Math.random().toString(36).slice(2, 10)}`
}

function sanitizeActor(actor: string | null | undefined): string {
  const normalized = String(actor ?? '').trim()
  return normalized.length > 0 ? normalized : 'local-operator'
}

function buildApprovalState(
  approvals: PredictionDashboardApprovalDecision[],
  rejections: PredictionDashboardApprovalDecision[],
): PredictionDashboardApprovalState {
  const distinctActors = new Set<string>()
  for (const decision of [...approvals, ...rejections]) {
    distinctActors.add(decision.actor)
  }

  return {
    required_approvals: 2,
    approvals,
    rejections,
    distinct_actor_count: distinctActors.size,
    creator_cannot_self_approve: true,
  }
}

function buildDecision(
  actor: string,
  decision: 'approved' | 'rejected',
  note?: string | null,
): PredictionDashboardApprovalDecision {
  return {
    actor: sanitizeActor(actor),
    decision,
    decided_at: new Date().toISOString(),
    note: typeof note === 'string' && note.trim().length > 0 ? note.trim() : null,
  }
}

function toRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function snapshotLiveSurface(runId: string, workspaceId: number) {
  const liveSurface = preparePredictionMarketRunLive({
    runId,
    workspaceId,
  })
  const details = getPredictionMarketRunDetails(runId, workspaceId)

  return {
    liveSurface,
    details,
  }
}

function emitLiveIntentEvent(
  type:
    | 'live_intent_created'
    | 'live_intent_approved'
    | 'live_intent_rejected'
    | 'live_intent_executed'
    | 'live_intent_failed',
  severity: PredictionDashboardEventSeverity,
  intent: PredictionDashboardLiveIntent,
  summary: string,
) {
  publishPredictionDashboardEvent({
    type,
    severity,
    summary,
    workspace_id: intent.workspace_id,
    venue: intent.venue === 'unknown' ? null : intent.venue,
    run_id: intent.run_id,
    intent_id: intent.intent_id,
    source: 'workflow',
    payload: {
      status: intent.status,
      benchmark_promotion_ready: intent.benchmark_promotion_ready,
      benchmark_gate_blocks_live: intent.benchmark_gate_blocks_live,
      live_status: intent.live_status,
    },
  })
}

export function listPredictionDashboardLiveIntents(input: {
  workspaceId: number
  runId?: string | null
  limit?: number
}): PredictionDashboardLiveIntent[] {
  const items = [...intents.values()]
    .filter((intent) =>
      intent.workspace_id === input.workspaceId
      && (input.runId == null || intent.run_id === input.runId))
    .sort((left, right) => right.created_at.localeCompare(left.created_at))

  return items.slice(0, Math.max(1, Math.min(100, input.limit ?? 20)))
}

export function getPredictionDashboardLiveIntent(input: {
  workspaceId: number
  intentId: string
}): PredictionDashboardLiveIntent | null {
  const intent = intents.get(input.intentId)
  if (!intent || intent.workspace_id !== input.workspaceId) return null
  return intent
}

export function createPredictionDashboardLiveIntent(
  input: CreatePredictionDashboardLiveIntentInput,
): PredictionDashboardLiveIntent {
  const actor = sanitizeActor(input.actor)
  const { liveSurface, details } = snapshotLiveSurface(input.runId, input.workspaceId)

  if (liveSurface.live_status !== 'ready' || liveSurface.live_route_allowed !== true) {
    throw new PredictionMarketsError('Live intent cannot be created while the live surface is blocked', {
      status: 409,
      code: 'live_surface_blocked',
    })
  }

  const intentId = buildIntentId(input.runId)
  const approvals: PredictionDashboardApprovalDecision[] = []
  const rejections: PredictionDashboardApprovalDecision[] = []
  const intent: PredictionDashboardLiveIntent = {
    intent_id: intentId,
    workspace_id: input.workspaceId,
    run_id: liveSurface.run_id,
    venue: (details?.venue ?? liveSurface.venue_feed_surface?.venue ?? 'unknown') as PredictionMarketVenueId | 'unknown',
    market_id: details?.market_id ?? liveSurface.run_id,
    created_at: new Date().toISOString(),
    created_by: actor,
    status: 'pending_approval',
    summary: input.note?.trim()
      ? `Live intent created by ${actor}: ${input.note.trim()}`
      : `Live intent created by ${actor} for ${liveSurface.run_id}.`,
    selected_path: liveSurface.execution_projection_selected_path ?? liveSurface.live_path?.path ?? null,
    live_status: liveSurface.live_status,
    benchmark_promotion_ready: liveSurface.benchmark_promotion_ready === true,
    benchmark_promotion_blockers: [...(liveSurface.benchmark_promotion_blockers ?? [])],
    benchmark_gate_blocks_live: liveSurface.benchmark_gate_blocks_live === true,
    benchmark_gate_live_block_reason: liveSurface.benchmark_gate_live_block_reason ?? null,
    live_blocking_reasons: [...(liveSurface.live_blocking_reasons ?? [])],
    selected_preview: toRecord(
      liveSurface.live_trade_intent_preview
      ?? liveSurface.execution_projection_selected_preview
      ?? null,
    ),
    live_surface: liveSurface as unknown as Record<string, unknown>,
    approval_state: buildApprovalState(approvals, rejections),
    execution_result: null,
  }

  intents.set(intent.intent_id, intent)
  emitLiveIntentEvent('live_intent_created', 'info', intent, intent.summary)
  return intent
}

function finalizeApprovedIntent(intent: PredictionDashboardLiveIntent): PredictionDashboardLiveIntent {
  const refreshed = snapshotLiveSurface(intent.run_id, intent.workspace_id).liveSurface
  const executedAt = new Date().toISOString()
  const stillReady = refreshed.live_status === 'ready' && refreshed.live_route_allowed === true
  const refreshedRecord = refreshed as Record<string, unknown>
  const orderTraceAudit = {
    ...(toRecord(refreshedRecord.order_trace_audit) ?? {}),
    transport_mode: 'dashboard_bounded_preflight',
    live_execution_status: stillReady ? 'attempted_live_not_performed' : 'attempted_live_failed',
    venue_order_status: stillReady ? 'approval_complete_preflight_only' : 'blocked_after_approval',
    place_auditable: true,
    cancel_auditable: false,
    market_execution_status: stillReady ? 'attempted_live_not_performed' : 'attempted_live_failed',
  }

  intent.live_surface = refreshed as unknown as Record<string, unknown>
  intent.live_status = refreshed.live_status
  intent.benchmark_promotion_ready = refreshed.benchmark_promotion_ready === true
  intent.benchmark_promotion_blockers = [...(refreshed.benchmark_promotion_blockers ?? [])]
  intent.benchmark_gate_blocks_live = refreshed.benchmark_gate_blocks_live === true
  intent.benchmark_gate_live_block_reason = refreshed.benchmark_gate_live_block_reason ?? null
  intent.live_blocking_reasons = [...(refreshed.live_blocking_reasons ?? [])]
  intent.selected_preview = toRecord(
    refreshed.live_trade_intent_preview
    ?? refreshed.execution_projection_selected_preview
    ?? null,
  )

  if (!stillReady) {
    intent.status = 'execution_failed'
    intent.execution_result = {
      status: 'execution_failed',
      executed_at: executedAt,
      transport_mode: 'dashboard_bounded_preflight',
      performed_live: false,
      live_execution_status: 'attempted_live_failed',
      receipt_summary:
        refreshed.summary
        ?? refreshed.benchmark_gate_live_block_reason
        ?? 'Live execution failed after approval because the canonical live surface is no longer ready.',
      order_trace_audit: orderTraceAudit,
    }
    emitLiveIntentEvent(
      'live_intent_failed',
      'error',
      intent,
      intent.execution_result.receipt_summary,
    )
    return intent
  }

  intent.status = 'executed_preflight'
  intent.execution_result = {
    status: 'executed_preflight',
    executed_at: executedAt,
    transport_mode: 'dashboard_bounded_preflight',
    performed_live: false,
    live_execution_status: 'attempted_live_not_performed',
    receipt_summary:
      'Double approval completed. The dashboard emitted a bounded preflight receipt from the canonical live surface, but venue transport remains preflight-only in this subproject.',
    order_trace_audit: orderTraceAudit,
  }
  emitLiveIntentEvent(
    'live_intent_executed',
    'warn',
    intent,
    intent.execution_result.receipt_summary,
  )
  return intent
}

export function approvePredictionDashboardLiveIntent(
  input: DecisionPredictionDashboardLiveIntentInput,
): PredictionDashboardLiveIntent {
  const intent = getPredictionDashboardLiveIntent({
    workspaceId: input.workspaceId,
    intentId: input.intentId,
  })
  if (!intent) {
    throw new PredictionMarketsError('Live intent not found', {
      status: 404,
      code: 'live_intent_not_found',
    })
  }

  if (intent.status === 'rejected' || intent.status === 'executed_preflight' || intent.status === 'execution_failed') {
    throw new PredictionMarketsError('Live intent is already finalized', {
      status: 409,
      code: 'live_intent_finalized',
    })
  }

  const actor = sanitizeActor(input.actor)
  if (actor === intent.created_by) {
    throw new PredictionMarketsError('Live intent creator cannot approve their own live request', {
      status: 409,
      code: 'live_intent_self_approval_forbidden',
    })
  }

  if (intent.approval_state.approvals.some((approval) => approval.actor === actor)) {
    throw new PredictionMarketsError('This actor already approved the live intent', {
      status: 409,
      code: 'live_intent_duplicate_approval',
    })
  }

  const nextApproval = buildDecision(actor, 'approved', input.note)
  const approvals = [...intent.approval_state.approvals, nextApproval]
  intent.approval_state = buildApprovalState(approvals, intent.approval_state.rejections)

  if (approvals.length < intent.approval_state.required_approvals) {
    intent.status = 'pending_second_approval'
    intent.summary = `Live intent approved by ${actor}; waiting for a second distinct approver.`
    emitLiveIntentEvent('live_intent_approved', 'info', intent, intent.summary)
    return intent
  }

  intent.summary = `Live intent approved by ${approvals.length} distinct operators; generating the live receipt.`
  emitLiveIntentEvent('live_intent_approved', 'warn', intent, intent.summary)
  return finalizeApprovedIntent(intent)
}

export function rejectPredictionDashboardLiveIntent(
  input: DecisionPredictionDashboardLiveIntentInput,
): PredictionDashboardLiveIntent {
  const intent = getPredictionDashboardLiveIntent({
    workspaceId: input.workspaceId,
    intentId: input.intentId,
  })
  if (!intent) {
    throw new PredictionMarketsError('Live intent not found', {
      status: 404,
      code: 'live_intent_not_found',
    })
  }

  if (intent.status === 'rejected' || intent.status === 'executed_preflight' || intent.status === 'execution_failed') {
    throw new PredictionMarketsError('Live intent is already finalized', {
      status: 409,
      code: 'live_intent_finalized',
    })
  }

  const rejection = buildDecision(input.actor, 'rejected', input.note)
  const rejections = [...intent.approval_state.rejections, rejection]
  intent.approval_state = buildApprovalState(intent.approval_state.approvals, rejections)
  intent.status = 'rejected'
  intent.summary = `Live intent rejected by ${rejection.actor}.`
  emitLiveIntentEvent('live_intent_rejected', 'warn', intent, intent.summary)
  return intent
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

  return sanitizeActor(fallback)
}

export function listDashboardLiveIntents(runId?: string, workspaceId = 1): PredictionDashboardLiveIntent[] {
  return listPredictionDashboardLiveIntents({
    workspaceId,
    runId,
  })
}

export function getDashboardLiveIntent(intentId: string, workspaceId = 1): PredictionDashboardLiveIntent | null {
  return getPredictionDashboardLiveIntent({
    workspaceId,
    intentId,
  })
}

export function createDashboardLiveIntent(input: {
  runId: string
  workspaceId: number
  actor: string
  note?: string | null
}): PredictionDashboardLiveIntent {
  return createPredictionDashboardLiveIntent(input)
}

export function approveDashboardLiveIntent(input: {
  intentId: string
  workspaceId: number
  actor: string
  note?: string | null
}): PredictionDashboardLiveIntent {
  return approvePredictionDashboardLiveIntent(input)
}

export function rejectDashboardLiveIntent(input: {
  intentId: string
  workspaceId: number
  actor: string
  note?: string | null
}): PredictionDashboardLiveIntent {
  return rejectPredictionDashboardLiveIntent(input)
}
