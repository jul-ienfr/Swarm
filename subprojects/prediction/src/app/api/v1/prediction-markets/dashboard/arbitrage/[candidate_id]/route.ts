import { NextRequest, NextResponse } from 'next/server'

import { requireRole } from '@/lib/auth'
import { readLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import { getPredictionDashboardArbitrageCandidateSnapshot } from '@/lib/prediction-markets/dashboard-read-models'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ candidate_id: string }> },
) {
  const auth = requireRole(request, 'viewer')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = readLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { candidate_id: candidateId } = await params
    const { searchParams } = new URL(request.url)
    const limitPerVenue = searchParams.has('limit_per_venue') ? Number(searchParams.get('limit_per_venue')) : 16
    const candidate = await getPredictionDashboardArbitrageCandidateSnapshot(
      auth.user.workspace_id ?? 1,
      candidateId,
      ['polymarket', 'kalshi'],
      limitPerVenue,
    )

    if (!candidate) {
      return NextResponse.json({ error: 'Arbitrage candidate not found' }, { status: 404 })
    }

    return NextResponse.json(candidate, {
      headers: { 'X-Prediction-Markets-API': 'v1' },
    })
  } catch (error) {
    logger.error({ err: error }, 'GET /api/v1/prediction-markets/dashboard/arbitrage/[candidate_id] error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to load dashboard arbitrage candidate')
    return NextResponse.json(response.body, { status: response.status })
  }
}
