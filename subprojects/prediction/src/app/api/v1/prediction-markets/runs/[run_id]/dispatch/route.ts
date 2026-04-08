import { NextRequest, NextResponse } from 'next/server'
import { requireRole } from '@/lib/auth'
import { heavyLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import { preparePredictionMarketRunDispatch } from '@/lib/prediction-markets/service'

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ run_id: string }> },
) {
  const auth = requireRole(request, 'operator')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = heavyLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { run_id } = await params
    const payload = preparePredictionMarketRunDispatch({
      runId: run_id,
      workspaceId: auth.user.workspace_id ?? 1,
    })

    return NextResponse.json(payload, {
      status: 200,
      headers: { 'X-Prediction-Markets-API': 'v1' },
    })
  } catch (error) {
    logger.error({ err: error }, 'POST /api/v1/prediction-markets/runs/[run_id]/dispatch error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to prepare prediction market dispatch')
    return NextResponse.json(response.body, { status: response.status })
  }
}
