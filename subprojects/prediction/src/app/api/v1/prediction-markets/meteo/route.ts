import { NextRequest, NextResponse } from 'next/server'

import { requireRole } from '@/lib/auth'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import { buildMeteoBestBetsSummary, buildMeteoPricingReportFromProviders } from '@/lib/prediction-markets/meteo'
import { readLimiter } from '@/lib/rate-limit'

export async function GET(request: NextRequest) {
  const auth = requireRole(request, 'viewer')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = readLimiter(request)
  if (rateCheck) return rateCheck

  try {
    const { searchParams } = new URL(request.url)

    const question = requiredString(searchParams.get('question'), 'question')
    const latitude = requiredNumber(searchParams.get('latitude'), 'latitude')
    const longitude = requiredNumber(searchParams.get('longitude'), 'longitude')

    const openMeteoModels = splitCsv(searchParams.get('open_meteo_models'))
    const includeNws = optionalBoolean(searchParams.get('include_nws'))
    const includeMeteostat = optionalBoolean(searchParams.get('include_meteostat'))
    const meteostatStart = searchParams.get('meteostat_start') ?? undefined
    const meteostatEnd = searchParams.get('meteostat_end') ?? undefined
    const cacheTtlMs = optionalInteger(searchParams.get('cache_ttl_ms'), 'cache_ttl_ms')
    const retryCount = optionalInteger(searchParams.get('retry_count'), 'retry_count')
    const marketPrices = parseMarketPrices(searchParams.get('market_prices'))

    const result = await buildMeteoPricingReportFromProviders({
      question,
      latitude,
      longitude,
      openMeteoModels,
      includeNws,
      includeMeteostat,
      meteostatStart,
      meteostatEnd,
      meteostatApiKey: process.env.METEOSTAT_API_KEY,
      cacheTtlMs,
      retryCount,
      marketPrices,
      userAgent: 'swarm-prediction/1.0 (+meteo-route)',
    })

    return NextResponse.json(
      {
        spec: result.spec,
        forecast_points: result.forecastPoints,
        report: result.report,
        best_bets: buildMeteoBestBetsSummary(result.report),
      },
      { headers: { 'X-Prediction-Markets-API': 'v1' } },
    )
  } catch (error) {
    logger.error({ err: error }, 'GET /api/v1/prediction-markets/meteo error')
    const response = toPredictionMarketsErrorResponse(error, 'Failed to load météo pricing report')
    return NextResponse.json(response.body, { status: response.status })
  }
}

export const dynamic = 'force-dynamic'

function requiredString(value: string | null, field: string): string {
  const normalized = value?.trim()
  if (!normalized) {
    throw new Error(`Missing required query parameter: ${field}`)
  }
  return normalized
}

function requiredNumber(value: string | null, field: string): number {
  if (value == null || value.trim() === '') {
    throw new Error(`Missing required query parameter: ${field}`)
  }

  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    throw new Error(`Invalid numeric query parameter: ${field}`)
  }

  return parsed
}

function optionalInteger(value: string | null, field: string): number | undefined {
  if (value == null || value.trim() === '') {
    return undefined
  }

  const parsed = Number(value)
  if (!Number.isInteger(parsed)) {
    throw new Error(`Invalid integer query parameter: ${field}`)
  }

  return parsed
}

function optionalBoolean(value: string | null): boolean | undefined {
  if (value == null || value.trim() === '') {
    return undefined
  }

  const normalized = value.trim().toLowerCase()
  if (normalized === 'true') return true
  if (normalized === 'false') return false
  throw new Error(`Invalid boolean query parameter value: ${value}`)
}

function splitCsv(value: string | null): string[] | undefined {
  if (value == null || value.trim() === '') {
    return undefined
  }

  const parts = value
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)

  return parts.length ? parts : undefined
}

function parseMarketPrices(value: string | null): Record<string, number> | undefined {
  if (value == null || value.trim() === '') {
    return undefined
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(value)
  } catch {
    throw new Error('Invalid query parameter: market_prices must be valid JSON')
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Invalid query parameter: market_prices must be a JSON object')
  }

  const entries = Object.entries(parsed)
  const normalized = Object.fromEntries(entries.map(([key, raw]) => {
    const numeric = typeof raw === 'number' ? raw : Number(raw)
    if (!Number.isFinite(numeric)) {
      throw new Error(`Invalid market price for bin: ${key}`)
    }
    return [key, numeric]
  }))

  return normalized
}
