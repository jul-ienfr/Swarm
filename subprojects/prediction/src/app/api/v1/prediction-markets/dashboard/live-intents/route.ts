import { NextRequest, NextResponse } from 'next/server'

import { requireRole } from '@/lib/auth'
import { readLimiter, heavyLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import {
  createDashboardLiveIntent,
  listDashboardLiveIntents,
  resolveDashboardActor,
} from '@/lib/prediction-markets/dashboard-live-intents'

export async function GET(request: NextRequest) {
  const auth = requireRole(request, 'viewer')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = readLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { searchParams } = new URL(request.url)
    const runId = searchParams.get('run_id') || undefined
    return NextResponse.json(
      {
        live_intents: listDashboardLiveIntents(runId, auth.user.workspace_id ?? 1),
      },
      { headers: { 'X-Prediction-Markets-API': 'v1' } },
    )
  } catch (error) {
    logger.error({ err: error }, 'GET /api/v1/prediction-markets/dashboard/live-intents error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to list dashboard live intents')
    return NextResponse.json(response.body, { status: response.status })
  }
}

export async function POST(request: NextRequest) {
  const auth = requireRole(request, 'operator')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = heavyLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const body = await request.json().catch(() => null)
    const runId = typeof body?.run_id === 'string' ? body.run_id.trim() : ''
    const note = typeof body?.note === 'string' ? body.note.trim() : undefined
    if (!runId) {
      return NextResponse.json({ error: 'run_id is required' }, { status: 400 })
    }

    const actor = resolveDashboardActor(request, auth.user.username || 'operator')
    const intent = createDashboardLiveIntent({
      runId,
      workspaceId: auth.user.workspace_id ?? 1,
      actor,
      note,
    })

    return NextResponse.json(
      { live_intent: intent },
      {
        status: 201,
        headers: { 'X-Prediction-Markets-API': 'v1' },
      },
    )
  } catch (error) {
    logger.error({ err: error }, 'POST /api/v1/prediction-markets/dashboard/live-intents error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to create dashboard live intent')
    return NextResponse.json(response.body, { status: response.status })
  }
}
