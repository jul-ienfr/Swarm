import { parseMeteoQuestion } from '@/lib/prediction-markets/meteo/market-spec'
import { buildMeteoPricingReport } from '@/lib/prediction-markets/meteo/pricing'
import {
  fetchMeteostatHistoricalPoint,
  fetchNwsForecastPoint,
  fetchOpenMeteoForecastPoint,
} from '@/lib/prediction-markets/meteo/sources'
import type {
  MeteoFetchLike,
  MeteoForecastPoint,
  MeteoMarketSpec,
  MeteoPricingReport,
  MeteoTemperatureKind,
} from '@/lib/prediction-markets/meteo/types'

export async function buildMeteoForecastPointsFromProviders(input: {
  latitude: number
  longitude: number
  kind: MeteoTemperatureKind
  openMeteoModels?: string[]
  includeNws?: boolean
  includeMeteostat?: boolean
  meteostatStart?: string
  meteostatEnd?: string
  meteostatApiKey?: string
  openMeteoWeight?: number
  nwsWeight?: number
  meteostatWeight?: number
  cacheTtlMs?: number
  retryCount?: number
  fetchImpl?: MeteoFetchLike
  userAgent?: string
}): Promise<MeteoForecastPoint[]> {
  const points: MeteoForecastPoint[] = []
  const openMeteoModels = normalizeOpenMeteoModels(input.openMeteoModels)

  for (const model of openMeteoModels) {
    points.push(await fetchOpenMeteoForecastPoint({
      latitude: input.latitude,
      longitude: input.longitude,
      kind: input.kind,
      model,
      weight: input.openMeteoWeight,
      fetchImpl: input.fetchImpl,
      cacheTtlMs: input.cacheTtlMs,
      retryCount: input.retryCount,
    }))
  }

  if (input.includeNws !== false) {
    points.push(await fetchNwsForecastPoint({
      latitude: input.latitude,
      longitude: input.longitude,
      kind: input.kind,
      weight: input.nwsWeight,
      fetchImpl: input.fetchImpl,
      userAgent: input.userAgent,
      cacheTtlMs: input.cacheTtlMs,
      retryCount: input.retryCount,
    }))
  }

  if (input.includeMeteostat) {
    if (!input.meteostatStart || !input.meteostatEnd) {
      throw new Error('Meteostat requires meteostatStart and meteostatEnd')
    }

    points.push(await fetchMeteostatHistoricalPoint({
      latitude: input.latitude,
      longitude: input.longitude,
      kind: input.kind,
      start: input.meteostatStart,
      end: input.meteostatEnd,
      apiKey: input.meteostatApiKey,
      weight: input.meteostatWeight,
      fetchImpl: input.fetchImpl,
      cacheTtlMs: input.cacheTtlMs,
      retryCount: input.retryCount,
      sourceLabel: 'meteostat:historical',
    }))
  }

  if (!points.length) {
    throw new Error('At least one meteo provider must be enabled')
  }

  return points
}

export async function buildMeteoPricingReportFromProviders(input: {
  question: string
  latitude: number
  longitude: number
  kind?: MeteoTemperatureKind
  openMeteoModels?: string[]
  includeNws?: boolean
  includeMeteostat?: boolean
  meteostatStart?: string
  meteostatEnd?: string
  meteostatApiKey?: string
  openMeteoWeight?: number
  nwsWeight?: number
  meteostatWeight?: number
  marketPrices?: Record<string, number>
  cacheTtlMs?: number
  retryCount?: number
  fetchImpl?: MeteoFetchLike
  userAgent?: string
}): Promise<{ spec: MeteoMarketSpec; forecastPoints: MeteoForecastPoint[]; report: MeteoPricingReport }> {
  const spec = parseMeteoQuestion(input.question)
  const kind = input.kind ?? spec.kind

  if (!kind) {
    throw new Error('Unable to determine meteo market kind from the question')
  }

  const forecastPoints = await buildMeteoForecastPointsFromProviders({
    latitude: input.latitude,
    longitude: input.longitude,
    kind,
    openMeteoModels: input.openMeteoModels,
    includeNws: input.includeNws,
    includeMeteostat: input.includeMeteostat,
    meteostatStart: input.meteostatStart,
    meteostatEnd: input.meteostatEnd,
    meteostatApiKey: input.meteostatApiKey,
    openMeteoWeight: input.openMeteoWeight,
    nwsWeight: input.nwsWeight,
    meteostatWeight: input.meteostatWeight,
    cacheTtlMs: input.cacheTtlMs,
    retryCount: input.retryCount,
    fetchImpl: input.fetchImpl,
    userAgent: input.userAgent,
  })

  return {
    spec,
    forecastPoints,
    report: buildMeteoPricingReport({
      spec,
      forecastPoints,
      marketPrices: input.marketPrices,
    }),
  }
}

function normalizeOpenMeteoModels(models: string[] | undefined): string[] {
  const normalized = (models ?? ['ecmwf', 'gfs'])
    .map((model) => model.trim())
    .filter(Boolean)
  return normalized.length ? normalized : ['ecmwf', 'gfs']
}
