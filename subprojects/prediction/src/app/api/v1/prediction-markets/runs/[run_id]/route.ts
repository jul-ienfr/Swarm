import { NextRequest, NextResponse } from 'next/server'
import { requireRole } from '@/lib/auth'
import { readLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import { getPredictionMarketRunDetails } from '@/lib/prediction-markets/service'

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
    const details = getPredictionMarketRunDetails(run_id, auth.user.workspace_id ?? 1)
    if (!details) {
      return NextResponse.json({ error: 'Prediction market run not found' }, { status: 404 })
    }

    return NextResponse.json(details, {
      headers: { 'X-Prediction-Markets-API': 'v1' },
    })
  } catch (error) {
    logger.error({ err: error }, 'GET /api/v1/prediction-markets/runs/[run_id] error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to load prediction market run details')
    return NextResponse.json(response.body, { status: response.status })
  }
}
