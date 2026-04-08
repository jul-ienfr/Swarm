import { NextRequest, NextResponse } from 'next/server'
import { requireRole } from '@/lib/auth'
import { heavyLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { PredictionMarketsError, toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import { listDashboardLiveIntents } from '@/lib/prediction-markets/dashboard-live-intents'
import { executePredictionMarketRunLive, preparePredictionMarketRunLive } from '@/lib/prediction-markets/service'

function hasApprovedLiveIntent(intent: Record<string, unknown>) {
  const approvalState = (
    intent.approval_state && typeof intent.approval_state === 'object'
      ? intent.approval_state
      : null
  ) as Record<string, unknown> | null
  const status = typeof intent.status === 'string' ? intent.status : null
  const legacyStatus = typeof approvalState?.status === 'string' ? approvalState.status : null
  const approvals = Array.isArray(approvalState?.approvals) ? approvalState.approvals.length : 0
  const requiredApprovals = typeof approvalState?.required_approvals === 'number'
    ? approvalState.required_approvals
    : typeof approvalState?.required === 'number'
      ? approvalState.required
      : 1

  return legacyStatus === 'approved'
    || status === 'executed_preflight'
    || status === 'executed_live'
    || approvals >= requiredApprovals
}

function extractApprovedIntentId(intent: Record<string, unknown>): string | null {
  return typeof intent.intent_id === 'string' && intent.intent_id.trim().length > 0
    ? intent.intent_id
    : null
}

function extractApprovedActors(intent: Record<string, unknown>): string[] {
  const approvalState = (
    intent.approval_state && typeof intent.approval_state === 'object'
      ? intent.approval_state
      : null
  ) as Record<string, unknown> | null

  const actors = new Set<string>()
  const approvals = Array.isArray(approvalState?.approvals) ? approvalState.approvals : []
  for (const approval of approvals) {
    if (!approval || typeof approval !== 'object' || Array.isArray(approval)) continue
    const actorValue = (approval as Record<string, unknown>).actor
    const actor = typeof actorValue === 'string'
      ? actorValue.trim()
      : ''
    if (actor) actors.add(actor)
  }

  const legacyApprovers = Array.isArray(approvalState?.approvers) ? approvalState.approvers : []
  for (const actor of legacyApprovers) {
    const normalized = typeof actor === 'string' ? actor.trim() : ''
    if (normalized) actors.add(normalized)
  }

  return [...actors]
}

async function parseLiveRequestBody(request: NextRequest): Promise<Record<string, unknown>> {
  const raw = await request.text()
  if (!raw.trim()) return {}

  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new PredictionMarketsError('Invalid prediction markets request', {
        status: 400,
        code: 'invalid_request',
      })
    }
    return parsed as Record<string, unknown>
  } catch (error) {
    if (error instanceof PredictionMarketsError) throw error
    throw new PredictionMarketsError('Invalid prediction markets request', {
      status: 400,
      code: 'invalid_request',
    })
  }
}

function resolveExecutionMode(
  request: NextRequest,
  body: Record<string, unknown>,
): 'preflight' | 'live' {
  const fromBody = typeof body.execution_mode === 'string'
    ? body.execution_mode.trim()
    : typeof body.mode === 'string'
      ? body.mode.trim()
      : ''
  const fromQuery = new URL(request.url).searchParams.get('execution_mode')?.trim() ?? ''
  const mode = (fromBody || fromQuery || 'preflight').toLowerCase()

  if (mode === 'preflight' || mode === 'live') {
    return mode
  }

  throw new PredictionMarketsError('Invalid execution mode; expected preflight or live', {
    status: 400,
    code: 'invalid_execution_mode',
  })
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ run_id: string }> },
) {
  const auth = requireRole(request, 'operator')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = heavyLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const body = await parseLiveRequestBody(request)
    const executionMode = resolveExecutionMode(request, body)
    const { run_id } = await params
    const approvedIntent = listDashboardLiveIntents(run_id, auth.user.workspace_id ?? 1)
      .find((intent) => hasApprovedLiveIntent(intent as Record<string, unknown>))

    if (!approvedIntent) {
      return NextResponse.json(
        {
          error: 'Live intent approval required',
          code: 'live_intent_required',
        },
        { status: 409 },
      )
    }

    const payload = executionMode === 'live'
      ? executePredictionMarketRunLive({
        runId: run_id,
        workspaceId: auth.user.workspace_id ?? 1,
        actor: auth.user.username ?? 'operator',
        approvedIntentId: extractApprovedIntentId(approvedIntent as Record<string, unknown>),
        approvedBy: extractApprovedActors(approvedIntent as Record<string, unknown>),
      })
      : preparePredictionMarketRunLive({
        runId: run_id,
        workspaceId: auth.user.workspace_id ?? 1,
      })

    return NextResponse.json(payload, {
      status: 200,
      headers: { 'X-Prediction-Markets-API': 'v1' },
    })
  } catch (error) {
    logger.error({ err: error }, 'POST /api/v1/prediction-markets/runs/[run_id]/live error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to prepare prediction market live surface')
    return NextResponse.json(response.body, { status: response.status })
  }
}
