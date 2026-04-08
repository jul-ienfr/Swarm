import { NextRequest, NextResponse } from 'next/server'

import { requireRole } from '@/lib/auth'
import { readLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import { buildPredictionDashboardArbitrageSnapshot } from '@/lib/prediction-markets/dashboard-read-models'

function parseNumber(searchParams: URLSearchParams, key: string, fallback: number) {
  const value = searchParams.get(key)
  if (value == null) return fallback
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function parseNumberAlias(
  searchParams: URLSearchParams,
  keys: readonly string[],
  fallback: number,
) {
  for (const key of keys) {
    const value = searchParams.get(key)
    if (value == null) continue
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
}

export async function GET(request: NextRequest) {
  const auth = requireRole(request, 'viewer')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = readLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { searchParams } = new URL(request.url)
    const limitPerVenue = parseNumberAlias(searchParams, ['limit_per_venue', 'limit'], 16)
    const maxPairs = parseNumber(searchParams, 'max_pairs', 40)
    const minArbitrageSpreadBps = parseNumber(searchParams, 'min_arbitrage_spread_bps', 25)
    const shadowCandidates = parseNumber(searchParams, 'shadow_candidates', 8)

    const snapshot = await buildPredictionDashboardArbitrageSnapshot(auth.user.workspace_id ?? 1, {
      limitPerVenue,
      maxPairs,
      minArbitrageSpreadBps,
      shadowCandidateLimit: shadowCandidates,
      forceRefresh: true,
    })

    return NextResponse.json({ arbitrage: snapshot }, {
      headers: { 'X-Prediction-Markets-API': 'v1' },
    })
  } catch (error) {
    logger.error({ err: error }, 'GET /api/v1/prediction-markets/dashboard/arbitrage error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to load dashboard arbitrage snapshot')
    return NextResponse.json(response.body, { status: response.status })
  }
}
