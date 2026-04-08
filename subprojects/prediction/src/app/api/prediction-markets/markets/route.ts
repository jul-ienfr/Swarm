import { NextRequest, NextResponse } from 'next/server'
import { requireRole } from '@/lib/auth'
import { readLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import { listPredictionMarketUniverse } from '@/lib/prediction-markets/service'
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
      limit: searchParams.has('limit') ? Number(searchParams.get('limit')) : undefined,
      search: searchParams.get('search') || undefined,
    })

    const result = await listPredictionMarketUniverse(query)
    return NextResponse.json({
      venue: result.venue,
      total: result.markets.length,
      markets: result.markets,
    })
  } catch (error) {
    logger.error({ err: error }, 'GET /api/prediction-markets/markets error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to fetch prediction markets')
    return NextResponse.json(response.body, { status: response.status })
  }
}

export const dynamic = 'force-dynamic'
