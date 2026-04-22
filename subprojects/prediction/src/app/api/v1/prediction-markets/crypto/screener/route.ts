import { NextRequest, NextResponse } from 'next/server'

import { requireRole } from '@/lib/auth'
import { readLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import {
  buildPredictionCryptoScreenerLive,
  predictionCryptoScreenerQuerySchema,
} from '@/lib/prediction-markets/crypto'

export async function GET(request: NextRequest) {
  const auth = requireRole(request, 'viewer')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = readLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { searchParams } = new URL(request.url)
    const query = predictionCryptoScreenerQuerySchema.parse({
      venue: searchParams.get('venue') ?? undefined,
      asset: searchParams.get('asset') ?? undefined,
      archetype: searchParams.get('archetype') ?? undefined,
      execution_profile: searchParams.get('execution_profile') ?? undefined,
      source_mode: searchParams.get('source_mode') ?? undefined,
      limit: searchParams.has('limit') ? Number(searchParams.get('limit')) : undefined,
    })

    const result = await buildPredictionCryptoScreenerLive(query)
    return NextResponse.json(
      {
        screener: result,
      },
      { headers: { 'X-Prediction-Markets-API': 'v1' } },
    )
  } catch (error) {
    logger.error({ err: error }, 'GET /api/v1/prediction-markets/crypto/screener error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to load CRYPTO screener')
    return NextResponse.json(response.body, { status: response.status })
  }
}

export const dynamic = 'force-dynamic'
