import { NextRequest, NextResponse } from 'next/server'

import { requireRole } from '@/lib/auth'
import { readLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import { buildPredictionDashboardVenueSnapshot } from '@/lib/prediction-markets/dashboard-models'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ venue: string }> },
) {
  const auth = requireRole(request, 'viewer')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = readLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { venue } = await params
    if (venue !== 'polymarket' && venue !== 'kalshi') {
      return NextResponse.json({ error: 'Unsupported venue' }, { status: 400 })
    }

    return NextResponse.json(buildPredictionDashboardVenueSnapshot(venue), {
      headers: { 'X-Prediction-Markets-API': 'v1' },
    })
  } catch (error) {
    logger.error({ err: error }, 'GET /api/v1/prediction-markets/dashboard/venues/[venue] error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to load dashboard venue snapshot')
    return NextResponse.json(response.body, { status: response.status })
  }
}

