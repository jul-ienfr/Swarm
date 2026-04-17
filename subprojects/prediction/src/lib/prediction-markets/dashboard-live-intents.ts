import { PredictionMarketsError } from '@/lib/prediction-markets/errors'
import {
  executePredictionMarketRunLive,
  getPredictionMarketRunDetails,
  preparePredictionMarketRunLive,
} from '@/lib/prediction-markets/service'
import type {
  PredictionMarketExecutionPathwaysApprovalTicket,
  PredictionMarketExecutionPathwaysOperatorThesis,
  PredictionMarketExecutionPathwaysResearchPipelineTrace,
} from '@/lib/prediction-markets/execution-pathways'
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
  status: 'executed_live' | 'executed_preflight' | 'execution_failed'
  executed_at: string
  transport_mode: string
  performed_live: boolean
  live_execution_status: string
  receipt_summary: string
  order_trace_audit: Record<string, unknown>
  receipt: Record<string, unknown> | null
}

export type PredictionDashboardLiveIntentApprovalTicket = PredictionMarketExecutionPathwaysApprovalTicket

export type PredictionDashboardLiveIntentOperatorThesis = PredictionMarketExecutionPathwaysOperatorThesis

export type PredictionDashboardLiveIntentResearchPipelineTrace = PredictionMarketExecutionPathwaysResearchPipelineTrace

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
    | 'executed_live'
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
  approval_ticket: PredictionDashboardLiveIntentApprovalTicket | null
  operator_thesis: PredictionDashboardLiveIntentOperatorThesis | null
  research_pipeline_trace: PredictionDashboardLiveIntentResearchPipelineTrace | null
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

function toStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : []
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>()
  const out: string[] = []

  for (const value of values) {
    const normalized = String(value ?? '').trim()
    if (!normalized || seen.has(normalized)) continue
    seen.add(normalized)
    out.push(normalized)
  }

  return out
}

function firstDefined<T>(...values: Array<T | null | undefined>): T | undefined {
  for (const value of values) {
    if (value !== undefined && value !== null) return value
  }
  return undefined
}

function toNumberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function recordString(record: Record<string, unknown> | null | undefined, key: string, fallback: string): string {
  const value = record?.[key]
  return typeof value === 'string' && value.trim().length > 0 ? value : fallback
}

function recordBoolean(record: Record<string, unknown> | null | undefined, key: string): boolean {
  return record?.[key] === true
}

function recordStringList(record: Record<string, unknown> | null | undefined, key: string): string[] {
  const value = record?.[key]
  return Array.isArray(value)
    ? value.filter((entry): entry is string => typeof entry === 'string' && entry.trim().length > 0)
    : []
}

function extractExecutionPathwaysArtifacts(input: {
  liveSurface: Record<string, unknown> | null
  details: Record<string, unknown> | null
}): {
  approval_ticket: PredictionDashboardLiveIntentApprovalTicket | null
  operator_thesis: PredictionDashboardLiveIntentOperatorThesis | null
  research_pipeline_trace: PredictionDashboardLiveIntentResearchPipelineTrace | null
} {
  const liveExecutionPathways = toRecord(input.liveSurface?.execution_pathways)
  const detailExecutionPathways = toRecord(input.details?.execution_pathways)
  const executionPathways = liveExecutionPathways ?? detailExecutionPathways

  const approvalTicketRaw = toRecord(
    executionPathways?.approval_ticket
    ?? input.liveSurface?.approval_ticket
    ?? input.details?.approval_ticket,
  )
  const operatorThesisRaw = toRecord(
    executionPathways?.operator_thesis
    ?? input.liveSurface?.operator_thesis
    ?? input.details?.operator_thesis,
  )
  const researchPipelineTraceRaw = toRecord(
    executionPathways?.research_pipeline_trace
    ?? input.liveSurface?.research_pipeline_trace
    ?? input.details?.research_pipeline_trace,
  )

  const approval_ticket = approvalTicketRaw
    ? {
      ticket_id: String(approvalTicketRaw.ticket_id ?? ''),
      required: approvalTicketRaw.required === true,
      status: String(approvalTicketRaw.status ?? 'blocked') as PredictionDashboardLiveIntentApprovalTicket['status'],
      reasons: toStringList(approvalTicketRaw.reasons),
      summary: String(approvalTicketRaw.summary ?? 'Approval ticket artifact is available.'),
    }
    : null

  const operator_thesis = operatorThesisRaw
    ? {
      present: operatorThesisRaw.present === true,
      source: String(operatorThesisRaw.source ?? 'none') as PredictionDashboardLiveIntentOperatorThesis['source'],
      probability_yes: toNumberOrNull(operatorThesisRaw.probability_yes),
      rationale: typeof operatorThesisRaw.rationale === 'string' && operatorThesisRaw.rationale.trim().length > 0
        ? operatorThesisRaw.rationale.trim()
        : null,
      evidence_refs: toStringList(operatorThesisRaw.evidence_refs),
      summary: String(operatorThesisRaw.summary ?? 'Operator thesis artifact is available.'),
    }
    : null

  const research_pipeline_trace = researchPipelineTraceRaw
    ? {
      pipeline_id: typeof researchPipelineTraceRaw.pipeline_id === 'string' && researchPipelineTraceRaw.pipeline_id.trim().length > 0
        ? researchPipelineTraceRaw.pipeline_id.trim()
        : null,
      pipeline_version: typeof researchPipelineTraceRaw.pipeline_version === 'string' && researchPipelineTraceRaw.pipeline_version.trim().length > 0
        ? researchPipelineTraceRaw.pipeline_version.trim()
        : null,
      preferred_mode: String(researchPipelineTraceRaw.preferred_mode ?? 'unknown') as PredictionDashboardLiveIntentResearchPipelineTrace['preferred_mode'],
      oracle_family: String(researchPipelineTraceRaw.oracle_family ?? 'unknown') as PredictionDashboardLiveIntentResearchPipelineTrace['oracle_family'],
      forecaster_count: toNumberOrNull(researchPipelineTraceRaw.forecaster_count),
      evidence_count: toNumberOrNull(researchPipelineTraceRaw.evidence_count),
      source_refs: toStringList(researchPipelineTraceRaw.source_refs),
      summary: String(researchPipelineTraceRaw.summary ?? 'Research pipeline trace artifact is available.'),
    }
    : null

  return {
    approval_ticket,
    operator_thesis,
    research_pipeline_trace,
  }
}

function buildArtifactHintSummary(input: {
  approval_ticket: PredictionDashboardLiveIntentApprovalTicket | null
  operator_thesis: PredictionDashboardLiveIntentOperatorThesis | null
  research_pipeline_trace: PredictionDashboardLiveIntentResearchPipelineTrace | null
}): string | null {
  return uniqueStrings([
    input.approval_ticket ? `Approval ticket: ${input.approval_ticket.status}.` : null,
    input.operator_thesis
      ? input.operator_thesis.probability_yes != null
        ? `Operator thesis: ${Math.round(input.operator_thesis.probability_yes * 100)}% yes via ${input.operator_thesis.source}.`
        : `Operator thesis: ${input.operator_thesis.source}.`
      : null,
    input.research_pipeline_trace
      ? `Research pipeline trace: ${input.research_pipeline_trace.preferred_mode}/${input.research_pipeline_trace.oracle_family}.`
      : null,
  ]).join(' ')
}

function snapshotLiveSurface(runId: string, workspaceId: number) {
  const liveSurface = preparePredictionMarketRunLive({
    runId,
    workspaceId,
  })
  const details = toRecord(getPredictionMarketRunDetails(runId, workspaceId))

  return {
    liveSurface: toRecord(liveSurface) ?? (liveSurface as Record<string, unknown>),
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

function isIntentFinalized(intent: PredictionDashboardLiveIntent): boolean {
  return intent.status === 'rejected'
    || intent.status === 'executed_live'
    || intent.status === 'executed_preflight'
    || intent.status === 'execution_failed'
}

function approvalsForIntent(intent: PredictionDashboardLiveIntent): string[] {
  return intent.approval_state.approvals.map((approval) => approval.actor)
}

function asLiveExecutionReceipt(value: unknown): Record<string, unknown> | null {
  return toRecord(value)
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
  const executionPathwayArtifacts = extractExecutionPathwaysArtifacts({ liveSurface, details })
  const artifactSummary = buildArtifactHintSummary(executionPathwayArtifacts)

  if (recordString(liveSurface, 'live_status', 'unknown') !== 'ready' || !recordBoolean(liveSurface, 'live_route_allowed')) {
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
    run_id: recordString(liveSurface, 'run_id', input.runId),
    venue: (recordString(details, 'venue', recordString(toRecord(liveSurface.venue_feed_surface), 'venue', 'unknown')) ?? 'unknown') as PredictionMarketVenueId | 'unknown',
    market_id: recordString(details, 'market_id', recordString(liveSurface, 'run_id', input.runId)),
    created_at: new Date().toISOString(),
    created_by: actor,
    status: 'pending_approval',
    summary: input.note?.trim()
      ? `Live intent created by ${actor}: ${input.note.trim()}`
      : `Live intent created by ${actor} for ${recordString(liveSurface, 'run_id', input.runId)}.`,
    selected_path: recordString(liveSurface, 'execution_projection_selected_path', recordString(toRecord(liveSurface.live_path), 'path', null)),
    live_status: recordString(liveSurface, 'live_status', 'unknown'),
    benchmark_promotion_ready: recordBoolean(liveSurface, 'benchmark_promotion_ready'),
    benchmark_promotion_blockers: recordStringList(liveSurface, 'benchmark_promotion_blockers'),
    benchmark_gate_blocks_live: recordBoolean(liveSurface, 'benchmark_gate_blocks_live'),
    benchmark_gate_live_block_reason: recordString(liveSurface, 'benchmark_gate_live_block_reason', null),
    live_blocking_reasons: recordStringList(liveSurface, 'live_blocking_reasons'),
    approval_ticket: executionPathwayArtifacts.approval_ticket,
    operator_thesis: executionPathwayArtifacts.operator_thesis,
    research_pipeline_trace: executionPathwayArtifacts.research_pipeline_trace,
    selected_preview: toRecord(
      firstDefined(
        liveSurface.live_trade_intent_preview,
        liveSurface.execution_projection_selected_preview,
        null,
      ),
    ),
    live_surface: liveSurface as unknown as Record<string, unknown>,
    approval_state: buildApprovalState(approvals, rejections),
    execution_result: null,
  }
  const summaryParts = uniqueStrings([
    intent.summary,
    artifactSummary ? `Artifacts: ${artifactSummary}` : null,
  ])
  intent.summary = summaryParts.join(' ')

  intents.set(intent.intent_id, intent)
  emitLiveIntentEvent('live_intent_created', 'info', intent, intent.summary)
  return intent
}

function finalizeApprovedIntent(
  intent: PredictionDashboardLiveIntent,
  actor: string,
): PredictionDashboardLiveIntent {
  const refreshed = snapshotLiveSurface(intent.run_id, intent.workspace_id).liveSurface
  const refreshedArtifacts = extractExecutionPathwaysArtifacts({
    liveSurface: refreshed,
    details: toRecord(getPredictionMarketRunDetails(intent.run_id, intent.workspace_id)),
  })
  const artifactSummary = buildArtifactHintSummary(refreshedArtifacts)
  const executedAt = new Date().toISOString()
  const stillReady = recordString(refreshed, 'live_status', 'unknown') === 'ready'
    && recordBoolean(refreshed, 'live_route_allowed')

  intent.live_surface = refreshed as unknown as Record<string, unknown>
  intent.approval_ticket = refreshedArtifacts.approval_ticket
  intent.operator_thesis = refreshedArtifacts.operator_thesis
  intent.research_pipeline_trace = refreshedArtifacts.research_pipeline_trace
  intent.live_status = recordString(refreshed, 'live_status', 'unknown')
  intent.benchmark_promotion_ready = recordBoolean(refreshed, 'benchmark_promotion_ready')
  intent.benchmark_promotion_blockers = recordStringList(refreshed, 'benchmark_promotion_blockers')
  intent.benchmark_gate_blocks_live = recordBoolean(refreshed, 'benchmark_gate_blocks_live')
  intent.benchmark_gate_live_block_reason = recordString(refreshed, 'benchmark_gate_live_block_reason', null)
  intent.live_blocking_reasons = recordStringList(refreshed, 'live_blocking_reasons')
    intent.selected_preview = toRecord(
      firstDefined(
        refreshed.live_trade_intent_preview,
        refreshed.execution_projection_selected_preview,
        null,
      ),
    )

  if (!stillReady) {
    intent.status = 'execution_failed'
    intent.execution_result = {
      status: 'execution_failed',
      executed_at: executedAt,
      transport_mode: 'dashboard_live_execution_blocked',
      performed_live: false,
      live_execution_status: 'attempted_live_failed',
      receipt_summary:
        recordString(refreshed, 'summary', null)
        ?? recordString(refreshed, 'benchmark_gate_live_block_reason', null)
        ?? 'Live execution failed after approval because the canonical live surface is no longer ready.',
      order_trace_audit: {
        transport_mode: 'dashboard_live_execution_blocked',
        live_execution_status: 'attempted_live_failed',
        venue_order_status: 'blocked_after_approval',
        place_auditable: true,
        cancel_auditable: false,
        market_execution_status: 'attempted_live_failed',
      },
      receipt: null,
    }
    intent.summary = intent.execution_result.receipt_summary
    if (artifactSummary) {
      intent.summary = `${intent.summary} Artifacts: ${artifactSummary}`
    }
    emitLiveIntentEvent(
      'live_intent_failed',
      'error',
      intent,
      intent.execution_result.receipt_summary,
    )
    return intent
  }

  try {
    const receipt = executePredictionMarketRunLive({
      runId: intent.run_id,
      workspaceId: intent.workspace_id,
      actor,
      approvedIntentId: intent.intent_id,
      approvedBy: approvalsForIntent(intent),
    }) as unknown as Record<string, unknown>
    const receiptRecord = asLiveExecutionReceipt(receipt)
    const receiptSurface = toRecord(receiptRecord?.preflight_surface) ?? (refreshed as unknown as Record<string, unknown>)
    const orderTraceAudit = toRecord(receiptRecord?.order_trace_audit) ?? {}
    const performedLive = receiptRecord?.performed_live === true

    intent.live_surface = receiptSurface
    intent.live_status = recordString(receiptSurface, 'live_status', recordString(refreshed, 'live_status', 'unknown'))
    intent.benchmark_promotion_ready = recordBoolean(receiptSurface, 'benchmark_promotion_ready')
    intent.benchmark_promotion_blockers = recordStringList(receiptSurface, 'benchmark_promotion_blockers').length > 0
      ? recordStringList(receiptSurface, 'benchmark_promotion_blockers')
      : recordStringList(refreshed, 'benchmark_promotion_blockers')
    intent.benchmark_gate_blocks_live = recordBoolean(receiptSurface, 'benchmark_gate_blocks_live')
    intent.benchmark_gate_live_block_reason =
      recordString(receiptSurface, 'benchmark_gate_live_block_reason', recordString(refreshed, 'benchmark_gate_live_block_reason', ''))
        || recordString(refreshed, 'benchmark_gate_live_block_reason', null)
    intent.live_blocking_reasons = recordStringList(receiptSurface, 'live_blocking_reasons').length > 0
      ? recordStringList(receiptSurface, 'live_blocking_reasons')
      : recordStringList(refreshed, 'live_blocking_reasons')
    intent.selected_preview = toRecord(
      firstDefined(
        receiptSurface.live_trade_intent_preview,
        receiptSurface.execution_projection_selected_preview,
        null,
      ),
    )

    if (!performedLive) {
      intent.status = 'execution_failed'
      intent.execution_result = {
        status: 'execution_failed',
        executed_at: executedAt,
        transport_mode: recordString(receiptRecord, 'transport_mode', 'live_transport_unbound'),
        performed_live: false,
        live_execution_status: recordString(receiptRecord, 'live_execution_status', 'attempted_live_not_performed'),
        receipt_summary: recordString(
          receiptRecord,
          'receipt_summary',
          'Live execution was attempted after approval, but the venue submission was not performed.',
        ),
        order_trace_audit: orderTraceAudit,
        receipt: receiptRecord,
      }
      intent.summary = intent.execution_result.receipt_summary
      emitLiveIntentEvent(
        'live_intent_failed',
        'error',
        intent,
        intent.execution_result.receipt_summary,
      )
      return intent
    }

    intent.status = 'executed_live'
    intent.execution_result = {
      status: 'executed_live',
      executed_at: executedAt,
      transport_mode: recordString(receiptRecord, 'transport_mode', 'live'),
      performed_live: true,
      live_execution_status: recordString(receiptRecord, 'live_execution_status', 'live_submission_performed'),
      receipt_summary: recordString(
        receiptRecord,
        'receipt_summary',
        'Live execution materialized from the approved live intent.',
      ),
      order_trace_audit: orderTraceAudit,
      receipt: receiptRecord,
    }
    intent.summary = intent.execution_result.receipt_summary
    emitLiveIntentEvent(
      'live_intent_executed',
      'warn',
      intent,
      intent.execution_result.receipt_summary,
    )
    return intent
  } catch (error) {
    intent.status = 'execution_failed'
    intent.execution_result = {
      status: 'execution_failed',
      executed_at: executedAt,
      transport_mode: 'live_execution_bridge_failed',
      performed_live: false,
      live_execution_status: 'attempted_live_failed',
      receipt_summary: error instanceof Error ? error.message : 'Live execution failed after approval.',
      order_trace_audit: {
        transport_mode: 'live_execution_bridge_failed',
        live_execution_status: 'attempted_live_failed',
        venue_order_status: 'live_execution_bridge_failed',
      },
      receipt: null,
    }
    intent.summary = intent.execution_result.receipt_summary
    emitLiveIntentEvent(
      'live_intent_failed',
      'error',
      intent,
      intent.execution_result.receipt_summary,
    )
    return intent
  }
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

  if (isIntentFinalized(intent)) {
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
    const artifactSummary = buildArtifactHintSummary({
      approval_ticket: intent.approval_ticket,
      operator_thesis: intent.operator_thesis,
      research_pipeline_trace: intent.research_pipeline_trace,
    })
    intent.summary = uniqueStrings([
      `Live intent approved by ${actor}; waiting for a second distinct approver.`,
      artifactSummary ? `Artifacts: ${artifactSummary}` : null,
    ]).join(' ')
    emitLiveIntentEvent('live_intent_approved', 'info', intent, intent.summary)
    return intent
  }

  const artifactSummary = buildArtifactHintSummary({
    approval_ticket: intent.approval_ticket,
    operator_thesis: intent.operator_thesis,
    research_pipeline_trace: intent.research_pipeline_trace,
  })
  intent.summary = uniqueStrings([
    `Live intent approved by ${approvals.length} distinct operators; executing the governed live route.`,
    artifactSummary ? `Artifacts: ${artifactSummary}` : null,
  ]).join(' ')
  emitLiveIntentEvent('live_intent_approved', 'warn', intent, intent.summary)
  return finalizeApprovedIntent(intent, actor)
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

  if (isIntentFinalized(intent)) {
    throw new PredictionMarketsError('Live intent is already finalized', {
      status: 409,
      code: 'live_intent_finalized',
    })
  }

  const rejection = buildDecision(input.actor, 'rejected', input.note)
  const rejections = [...intent.approval_state.rejections, rejection]
  intent.approval_state = buildApprovalState(intent.approval_state.approvals, rejections)
  intent.status = 'rejected'
  const artifactSummary = buildArtifactHintSummary({
    approval_ticket: intent.approval_ticket,
    operator_thesis: intent.operator_thesis,
    research_pipeline_trace: intent.research_pipeline_trace,
  })
  intent.summary = uniqueStrings([
    `Live intent rejected by ${rejection.actor}.`,
    artifactSummary ? `Artifacts: ${artifactSummary}` : null,
  ]).join(' ')
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
