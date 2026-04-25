import { NextRequest, NextResponse } from 'next/server'

import { requireRole } from '@/lib/auth'
import { logger } from '@/lib/logger'
import { toPredictionMarketsErrorResponse } from '@/lib/prediction-markets/errors'
import {
  analyzeMeteoResolutionSource,
  buildMeteoBestBetsSummary,
  buildMeteoResolutionSourceRoute,
  buildMeteoExecutionCandidates,
  buildMeteoExecutionSummary,
  buildMeteoPricingReport,
  buildMeteoPricingReportFromProviders,
  buildMeteoStationMetadata,
  detectMeteoMarketAnomalies,
  extractMeteoResolutionSource,
  fetchMeteoResolutionSourceObservation,
  observationToForecastPoint,
} from '@/lib/prediction-markets/meteo'
import { toPolymarketQuoteMarketEvent } from '@/lib/prediction-markets/polymarket-market-event'
import { readLimiter } from '@/lib/rate-limit'

 type PolymarketQuoteEventInput = {
  event_id?: string
  ts?: string
  venue?: 'polymarket'
  market_id?: string
  event_type?: 'quote'
  best_bid?: number | null
  best_ask?: number | null
  last_trade_price?: number | null
  bid_size?: number | null
  ask_size?: number | null
  quote_age_ms?: number | null
}

 type PolymarketEventInput = {
  title?: string
  description?: string
  rules?: string
  resolution_source?: string
  market_id?: string
  quote_event?: PolymarketQuoteEventInput
}

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
    const includeExecution = optionalBoolean(searchParams.get('include_execution')) ?? false
    const includeResolutionObservation = optionalBoolean(searchParams.get('include_resolution_observation')) ?? false
    const meteostatStart = searchParams.get('meteostat_start') ?? undefined
    const meteostatEnd = searchParams.get('meteostat_end') ?? undefined
    const cacheTtlMs = optionalInteger(searchParams.get('cache_ttl_ms'), 'cache_ttl_ms')
    const retryCount = optionalInteger(searchParams.get('retry_count'), 'retry_count')
    const minEdgeBps = optionalInteger(searchParams.get('min_edge_bps'), 'min_edge_bps')
    const marketPrices = parseMarketPrices(searchParams.get('market_prices'))
    const resolutionSource = searchParams.get('resolution_source') ?? undefined
    const description = searchParams.get('description') ?? undefined
    const rules = searchParams.get('rules') ?? undefined
    const snapshotPayload = parsePolymarketSnapshot(searchParams.get('snapshot_json'))
    const polymarketEvent = snapshotPayload?.event ?? parsePolymarketEvent(searchParams.get('event_json'))
    const resolvedResolutionSource = resolutionSource ?? polymarketEvent?.resolution_source ?? undefined
    const resolvedDescription = description ?? polymarketEvent?.description ?? undefined
    const resolvedRules = rules ?? polymarketEvent?.rules ?? undefined

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

    const resolution = extractMeteoResolutionSource({
      question,
      spec: result.spec,
      resolutionSource: resolvedResolutionSource,
      description: resolvedDescription,
      rules: resolvedRules,
      polymarketEvent,
    })
    const station = buildMeteoStationMetadata({
      question,
      spec: result.spec,
      resolutionSource: resolvedResolutionSource,
      description: resolvedDescription,
      rules: resolvedRules,
      polymarketEvent,
    })
    const resolutionAnalysis = analyzeMeteoResolutionSource({
      question,
      spec: result.spec,
      resolutionSource: resolvedResolutionSource,
      description: resolvedDescription,
      rules: resolvedRules,
      polymarketEvent,
    })
    const resolutionSourceRoute = buildMeteoResolutionSourceRoute(resolution)
    let resolutionSourceObservation = undefined
    let resolutionSourceObservationError: { provider: string; message: string } | undefined
    if (includeResolutionObservation && resolutionSourceRoute.primary_poll_url) {
      try {
        resolutionSourceObservation = await fetchMeteoResolutionSourceObservation({
          route: resolutionSourceRoute,
          unit: result.spec.unit,
          cacheTtlMs,
          retryCount,
          now: new Date(),
          weatherApiKey: process.env.WEATHER_COM_API_KEY ?? process.env.WUNDERGROUND_API_KEY,
        })
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to fetch direct resolution-source observation'
        resolutionSourceObservationError = {
          provider: resolutionSourceRoute.provider,
          message,
        }
        logger.warn({ err: error, route: resolutionSourceRoute }, 'Direct météo resolution-source observation unavailable')
      }
    }
    const officialForecastPoints = resolutionSourceObservation
      ? [...result.forecastPoints, observationToForecastPoint(resolutionSourceObservation)]
      : result.forecastPoints
    const officialReport = resolutionSourceObservation
      ? buildMeteoPricingReport({
          spec: result.spec,
          forecastPoints: officialForecastPoints,
          marketPrices,
        })
      : result.report
    const executionCandidates = includeExecution
      ? buildMeteoExecutionCandidates({
          report: officialReport,
          forecastPoints: officialForecastPoints,
          minEdgeBps,
        })
      : undefined
    const anomalies = includeExecution ? detectMeteoMarketAnomalies(officialReport) : undefined
    const executionSummary = includeExecution && executionCandidates && anomalies
      ? buildMeteoExecutionSummary({
          candidates: executionCandidates,
          anomalies,
        })
      : undefined

    return NextResponse.json(
      {
        spec: result.spec,
        forecast_points: officialForecastPoints,
        report: officialReport,
        resolution_source: resolution,
        resolution_source_route: resolutionSourceRoute,
        ...(includeResolutionObservation ? { resolution_source_observation: resolutionSourceObservation ?? null } : {}),
        ...(resolutionSourceObservationError ? { resolution_source_observation_error: resolutionSourceObservationError } : {}),
        station_metadata: station,
        resolution_analysis: resolutionAnalysis,
        best_bets: buildMeteoBestBetsSummary(officialReport),
        ...(includeExecution
          ? {
              execution_candidates: executionCandidates,
              anomalies,
              execution_summary: executionSummary,
            }
          : {}),
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

function parsePolymarketEvent(value: string | null): PolymarketEventInput | undefined {
  if (value == null || value.trim() === '') {
    return undefined
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(value)
  } catch {
    throw new Error('Invalid query parameter: event_json must be valid JSON')
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Invalid query parameter: event_json must be a JSON object')
  }

  const event = parsed as Record<string, unknown>
  const quoteEvent = event.quote_event
  const normalizedQuoteEvent = quoteEvent && typeof quoteEvent === 'object' && !Array.isArray(quoteEvent)
    ? normalizeQuoteEvent(quoteEvent as Record<string, unknown>)
    : undefined

  return {
    title: typeof event.title === 'string' ? event.title : undefined,
    description: typeof event.description === 'string' ? event.description : undefined,
    rules: typeof event.rules === 'string' ? event.rules : undefined,
    resolution_source: typeof event.resolution_source === 'string' ? event.resolution_source : undefined,
    market_id: typeof event.market_id === 'string' ? event.market_id : undefined,
    quote_event: normalizedQuoteEvent,
  }
}

function parsePolymarketSnapshot(value: string | null): { event?: PolymarketEventInput } | undefined {
  if (value == null || value.trim() === '') {
    return undefined
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(value)
  } catch {
    throw new Error('Invalid query parameter: snapshot_json must be valid JSON')
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Invalid query parameter: snapshot_json must be a JSON object')
  }

  const snapshot = parsed as Record<string, unknown>
  const rawEvent = snapshot.event
  const normalizedEvent = rawEvent && typeof rawEvent === 'object' && !Array.isArray(rawEvent)
    ? rawEvent as Record<string, unknown>
    : undefined

  return {
    event: {
      title: typeof normalizedEvent?.title === 'string' ? normalizedEvent.title : undefined,
      description: typeof normalizedEvent?.description === 'string' ? normalizedEvent.description : undefined,
      rules: typeof normalizedEvent?.rules === 'string' ? normalizedEvent.rules : undefined,
      resolution_source: typeof normalizedEvent?.resolution_source === 'string' ? normalizedEvent.resolution_source : undefined,
      market_id: typeof snapshot.market === 'object' && snapshot.market && !Array.isArray(snapshot.market) && typeof (snapshot.market as Record<string, unknown>).market_id === 'string'
        ? (snapshot.market as Record<string, unknown>).market_id as string
        : undefined,
      quote_event: normalizeQuoteEvent(
        toPolymarketQuoteMarketEvent(parsed as never) as unknown as Record<string, unknown>,
      ),
    },
  }
}

function normalizeQuoteEvent(quoteEvent: Record<string, unknown>): PolymarketQuoteEventInput {
  return {
    event_id: typeof quoteEvent.event_id === 'string' ? quoteEvent.event_id : undefined,
    ts: typeof quoteEvent.ts === 'string' ? quoteEvent.ts : undefined,
    venue: quoteEvent.venue === 'polymarket' ? 'polymarket' : undefined,
    market_id: typeof quoteEvent.market_id === 'string' ? quoteEvent.market_id : undefined,
    event_type: quoteEvent.event_type === 'quote' ? 'quote' : undefined,
    best_bid: toNullableNumber(quoteEvent.best_bid),
    best_ask: toNullableNumber(quoteEvent.best_ask),
    last_trade_price: toNullableNumber(quoteEvent.last_trade_price),
    bid_size: toNullableNumber(quoteEvent.bid_size),
    ask_size: toNullableNumber(quoteEvent.ask_size),
    quote_age_ms: toNullableNumber(quoteEvent.quote_age_ms),
  }
}

function toNullableNumber(value: unknown): number | null | undefined {
  if (value == null) {
    return undefined
  }

  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  return null
}
