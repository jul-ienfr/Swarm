import { NextRequest, NextResponse } from 'next/server'

import { requireRole } from '@/lib/auth'
import { readLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import { buildPredictionDashboardBenchmarkSnapshot } from '@/lib/prediction-markets/dashboard-models'

export async function GET(request: NextRequest) {
  const auth = requireRole(request, 'viewer')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = readLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { searchParams } = new URL(request.url)
    const venue = (searchParams.get('venue') || 'polymarket') as 'polymarket' | 'kalshi'
    const runId = searchParams.get('run_id') || undefined
    const snapshot = buildPredictionDashboardBenchmarkSnapshot(auth.user.workspace_id ?? 1, venue, runId)

    return NextResponse.json(snapshot, {
      headers: { 'X-Prediction-Markets-API': 'v1' },
    })
  } catch (error) {
    logger.error({ err: error }, 'GET /api/v1/prediction-markets/dashboard/benchmark error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to load dashboard benchmark snapshot')
    return NextResponse.json(response.body, { status: response.status })
  }
}

