import { NextRequest, NextResponse } from 'next/server'
import { requireRole } from '@/lib/auth'
import { readLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import { listPredictionMarketRuns } from '@/lib/prediction-markets/service'
import { predictionMarketsQuerySchema } from '@/lib/prediction-markets/schemas'

export async function GET(request: NextRequest) {
  const auth = requireRole(request, 'viewer')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = readLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { searchParams } = new URL(request.url)
    const query = predictionMarketsQuerySchema.parse({
      venue: searchParams.get('venue') || 'polymarket',
      recommendation: searchParams.get('recommendation') || undefined,
      limit: searchParams.has('limit') ? Number(searchParams.get('limit')) : undefined,
    })

    const runs = listPredictionMarketRuns({
      workspaceId: auth.user.workspace_id ?? 1,
      venue: query.venue,
      recommendation: query.recommendation,
      limit: query.limit,
    })

    return NextResponse.json({ runs, total: runs.length })
  } catch (error) {
    logger.error({ err: error }, 'GET /api/prediction-markets/runs error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to fetch prediction market runs')
    return NextResponse.json(response.body, { status: response.status })
  }
}
