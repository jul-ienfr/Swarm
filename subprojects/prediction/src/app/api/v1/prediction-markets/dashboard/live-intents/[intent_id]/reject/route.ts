import { NextRequest, NextResponse } from 'next/server'

import { requireRole } from '@/lib/auth'
import { heavyLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import { rejectDashboardLiveIntent, resolveDashboardActor } from '@/lib/prediction-markets/dashboard-live-intents'

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ intent_id: string }> },
) {
  const auth = requireRole(request, 'operator')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = heavyLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { intent_id } = await params
    const body = await request.json().catch(() => null)
    const note = typeof body?.note === 'string' ? body.note.trim() : undefined
    const actor = resolveDashboardActor(request, auth.user.username || 'operator')

    const liveIntent = rejectDashboardLiveIntent({
      intentId: intent_id,
      workspaceId: auth.user.workspace_id ?? 1,
      actor,
      note,
    })

    return NextResponse.json(
      { live_intent: liveIntent },
      { headers: { 'X-Prediction-Markets-API': 'v1' } },
    )
  } catch (error) {
    logger.error({ err: error }, 'POST /api/v1/prediction-markets/dashboard/live-intents/[intent_id]/reject error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to reject dashboard live intent')
    return NextResponse.json(response.body, { status: response.status })
  }
}

