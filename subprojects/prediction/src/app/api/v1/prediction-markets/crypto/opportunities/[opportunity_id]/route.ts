import { NextRequest, NextResponse } from 'next/server'

import { requireRole } from '@/lib/auth'
import { readLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { PredictionMarketsError, toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import {
  getPredictionCryptoScreenerOpportunity,
  predictionCryptoOpportunityIdSchema,
} from '@/lib/prediction-markets/crypto'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ opportunity_id: string }> },
) {
  const auth = requireRole(request, 'viewer')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = readLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { searchParams } = new URL(request.url)
    const { opportunity_id } = await params
    const opportunityId = predictionCryptoOpportunityIdSchema.parse(opportunity_id)
    const opportunity = await getPredictionCryptoScreenerOpportunity(opportunityId, {
      source_mode: searchParams.get('source_mode') === 'seeded' ? 'seeded' : 'auto',
    })

    if (!opportunity) {
      throw new PredictionMarketsError('CRYPTO screener opportunity not found', {
        status: 404,
        code: 'crypto_opportunity_not_found',
      })
    }

    return NextResponse.json(
      {
        opportunity,
      },
      { headers: { 'X-Prediction-Markets-API': 'v1' } },
    )
  } catch (error) {
    logger.error({ err: error }, 'GET /api/v1/prediction-markets/crypto/opportunities/[opportunity_id] error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to load CRYPTO screener opportunity')
    return NextResponse.json(response.body, { status: response.status })
  }
}

export const dynamic = 'force-dynamic'
