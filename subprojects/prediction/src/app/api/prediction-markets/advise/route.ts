import { NextRequest, NextResponse } from 'next/server'
import { requireRole } from '@/lib/auth'
import { heavyLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import { validateBody } from '@/lib/validation'
import { advisePredictionMarket } from '@/lib/prediction-markets/service'
import { predictionMarketsAdviceRequestSchema } from '@/lib/prediction-markets/schemas'

export async function POST(request: NextRequest) {
  const auth = requireRole(request, 'operator')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = heavyLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const result = await validateBody(request, predictionMarketsAdviceRequestSchema)
    if ('error' in result) return result.error

    const payload = await advisePredictionMarket({
      ...result.data,
      workspaceId: auth.user.workspace_id ?? 1,
      actor: auth.user.username || 'system',
    })

    return NextResponse.json(payload, { status: 201 })
  } catch (error) {
    logger.error({ err: error }, 'POST /api/prediction-markets/advise error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to advise prediction market')
    return NextResponse.json(response.body, { status: response.status })
  }
}
