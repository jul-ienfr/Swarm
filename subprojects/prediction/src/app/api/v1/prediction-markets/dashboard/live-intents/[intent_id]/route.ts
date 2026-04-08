import { NextRequest, NextResponse } from 'next/server'

import { requireRole } from '@/lib/auth'
import { readLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import { getDashboardLiveIntent } from '@/lib/prediction-markets/dashboard-live-intents'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ intent_id: string }> },
) {
  const auth = requireRole(request, 'viewer')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = readLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { intent_id } = await params
    return NextResponse.json(
      {
        live_intent: getDashboardLiveIntent(intent_id, auth.user.workspace_id ?? 1),
      },
      { headers: { 'X-Prediction-Markets-API': 'v1' } },
    )
  } catch (error) {
    logger.error({ err: error }, 'GET /api/v1/prediction-markets/dashboard/live-intents/[intent_id] error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to load dashboard live intent')
    return NextResponse.json(response.body, { status: response.status })
  }
}

