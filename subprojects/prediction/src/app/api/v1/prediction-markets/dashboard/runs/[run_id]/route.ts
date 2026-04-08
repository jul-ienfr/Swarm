import { NextRequest, NextResponse } from 'next/server'

import { requireRole } from '@/lib/auth'
import { readLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import { buildPredictionDashboardRunDetail } from '@/lib/prediction-markets/dashboard-models'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ run_id: string }> },
) {
  const auth = requireRole(request, 'viewer')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = readLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { run_id } = await params
    const detail = buildPredictionDashboardRunDetail(auth.user.workspace_id ?? 1, run_id)
    if (!detail) {
      return NextResponse.json({ error: 'Prediction market run not found' }, { status: 404 })
    }

    return NextResponse.json(detail, {
      headers: { 'X-Prediction-Markets-API': 'v1' },
    })
  } catch (error) {
    logger.error({ err: error }, 'GET /api/v1/prediction-markets/dashboard/runs/[run_id] error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to load dashboard run detail')
    return NextResponse.json(response.body, { status: response.status })
  }
}

