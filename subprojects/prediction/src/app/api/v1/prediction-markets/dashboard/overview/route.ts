import { NextRequest, NextResponse } from 'next/server'

import { requireRole } from '@/lib/auth'
import { readLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import { buildPredictionDashboardOverview } from '@/lib/prediction-markets/dashboard-models'

export async function GET(request: NextRequest) {
  const auth = requireRole(request, 'viewer')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = readLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { searchParams } = new URL(request.url)
    const venue = (searchParams.get('venue') || 'polymarket') as 'polymarket' | 'kalshi'
    const limit = searchParams.has('limit') ? Number(searchParams.get('limit')) : 20

    return NextResponse.json(
      buildPredictionDashboardOverview(auth.user.workspace_id ?? 1, venue, limit),
      { headers: { 'X-Prediction-Markets-API': 'v1' } },
    )
  } catch (error) {
    logger.error({ err: error }, 'GET /api/v1/prediction-markets/dashboard/overview error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to load dashboard overview')
    return NextResponse.json(response.body, { status: response.status })
  }
}

