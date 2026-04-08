import { NextRequest, NextResponse } from 'next/server'
import { requireRole } from '@/lib/auth'
import { readLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { predictionMarketVenueSchema } from '@/lib/prediction-markets/schemas'
import {
  getVenueBudgets,
  getVenueBudgetsContract,
  getVenueHealthSnapshot,
  getVenueHealthSnapshotContract,
} from '@/lib/prediction-markets/venue-ops'

export async function GET(request: NextRequest) {
  const auth = requireRole(request, 'viewer')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = readLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { searchParams } = new URL(request.url)
    const venue = predictionMarketVenueSchema.parse(searchParams.get('venue') || 'polymarket')

    return NextResponse.json({
      venue,
      health: getVenueHealthSnapshot(venue),
      health_contract: getVenueHealthSnapshotContract(venue),
      budgets: getVenueBudgets(venue),
      budgets_contract: getVenueBudgetsContract(venue),
    })
  } catch (error) {
    logger.error({ err: error }, 'GET /api/prediction-markets/health error')
    return NextResponse.json({ error: 'Failed to fetch prediction market health' }, { status: 400 })
  }
}

export const dynamic = 'force-dynamic'
