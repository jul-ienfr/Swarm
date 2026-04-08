import { NextRequest, NextResponse } from 'next/server'
import { requireRole } from '@/lib/auth'
import { readLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { predictionMarketVenueSchema } from '@/lib/prediction-markets/schemas'
import {
  getVenueBudgets,
  getVenueBudgetsContract,
  getVenueCapabilities,
  getVenueCapabilitiesContract,
} from '@/lib/prediction-markets/venue-ops'

export async function GET(request: NextRequest) {
  const auth = requireRole(request, 'viewer')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = readLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { searchParams } = new URL(request.url)
    const venue = predictionMarketVenueSchema.parse(searchParams.get('venue') || 'polymarket')

    return NextResponse.json(
      {
        venue,
        capabilities: getVenueCapabilities(venue),
        capabilities_contract: getVenueCapabilitiesContract(venue),
        budgets: getVenueBudgets(venue),
        budgets_contract: getVenueBudgetsContract(venue),
      },
      { headers: { 'X-Prediction-Markets-API': 'v1' } },
    )
  } catch (error) {
    logger.error({ err: error }, 'GET /api/v1/prediction-markets/capabilities error')
    return NextResponse.json({ error: 'Failed to fetch prediction market capabilities' }, { status: 400 })
  }
}

export const dynamic = 'force-dynamic'
