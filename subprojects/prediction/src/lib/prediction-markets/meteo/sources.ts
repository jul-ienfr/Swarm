import { fetchJsonWithMeteoProviderCache } from '@/lib/prediction-markets/meteo/provider-cache'
import type {
  MeteoForecastConsensus,
  MeteoForecastContribution,
  MeteoForecastPoint,
  MeteoForecastProviderKind,
  MeteoMeteostatDailyPayload,
  MeteoMeteostatFetchParams,
  MeteoNwsFetchParams,
  MeteoNwsPointMetadata,
  MeteoNwsTemperaturePayload,
  MeteoResolutionSourceObservation,
  MeteoResolutionSourceRoute,
  MeteoOpenMeteoFetchParams,
  MeteoOpenMeteoTemperaturePayload,
  MeteoTemperatureKind,
  MeteoTemperatureUnit,
} from '@/lib/prediction-markets/meteo/types'

export function normalizeOpenMeteoTemperaturePayload(input: {
  payload: MeteoOpenMeteoTemperaturePayload
  kind: MeteoTemperatureKind
  weight?: number
}): MeteoForecastPoint {
  const series = input.kind === 'high'
    ? input.payload.daily.temperature_2m_max
    : input.payload.daily.temperature_2m_min

  if (!series?.length) {
    throw new Error('Open-Meteo payload does not contain usable temperature data')
  }

  return {
    provider: input.payload.model ? `open-meteo:${input.payload.model}` : input.payload.provider ?? 'open-meteo',
    mean: series[0],
    stddev: deriveStddev(series),
    weight: input.weight ?? 1,
  }
}

export function normalizeNwsTemperaturePayload(input: {
  payload: MeteoNwsTemperaturePayload
  kind: MeteoTemperatureKind
  weight?: number
}): MeteoForecastPoint {
  if (!input.payload.periods.length) {
    throw new Error('NWS payload does not contain forecast periods')
  }

  const preferredPeriod = input.kind === 'high'
    ? input.payload.periods.find((period) => period.isDaytime)
    : input.payload.periods.find((period) => period.isDaytime === false)

  const selectedPeriod = preferredPeriod ?? input.payload.periods[0]

  return {
    provider: input.payload.provider ?? 'nws',
    mean: selectedPeriod.temperature,
    stddev: 1.8,
    weight: input.weight ?? 1,
  }
}

export function normalizeMeteostatDailyPayload(input: {
  payload: MeteoMeteostatDailyPayload
  kind: MeteoTemperatureKind
  weight?: number
  sourceLabel?: string
}): MeteoForecastPoint {
  const row = input.payload.data[0]
  if (!row) {
    throw new Error('Meteostat payload does not contain usable daily data')
  }

  const rawValue = input.kind === 'high' ? row.tmax : row.tmin
  if (rawValue === null || rawValue === undefined) {
    throw new Error(`Meteostat payload does not contain usable ${input.kind} temperature data`)
  }

  const unit = normalizeTemperatureUnit(input.payload.meta?.units) ?? 'c'
  const mean = unit === 'c' ? celsiusToFahrenheit(rawValue) : rawValue
  const fallbackStddev = row.tavg === null || row.tavg === undefined ? 2.2 : Math.max(Math.abs(mean - celsiusToFahrenheitIfNeeded(row.tavg, unit)), 1.4)

  return {
    provider: input.sourceLabel ?? input.payload.provider ?? 'meteostat',
    mean: round4(mean),
    stddev: round4(fallbackStddev),
    weight: input.weight ?? 1,
  }
}

export async function fetchOpenMeteoForecastPoint(params: MeteoOpenMeteoFetchParams): Promise<MeteoForecastPoint> {
  const kindKey = params.kind === 'high' ? 'temperature_2m_max' : 'temperature_2m_min'
  const url = new URL('https://api.open-meteo.com/v1/forecast')
  url.searchParams.set('latitude', String(params.latitude))
  url.searchParams.set('longitude', String(params.longitude))
  url.searchParams.set('daily', kindKey)
  url.searchParams.set('timezone', 'UTC')
  url.searchParams.set('forecast_days', '3')
  url.searchParams.set('temperature_unit', 'fahrenheit')
  if (params.model) {
    url.searchParams.set('models', params.model)
  }

  const payload = await fetchJsonWithMeteoProviderCache<MeteoOpenMeteoTemperaturePayload>({
    url: url.toString(),
    fetchImpl: params.fetchImpl,
    cacheTtlMs: params.cacheTtlMs ?? 10 * 60_000,
    retryCount: params.retryCount ?? 1,
  })

  return normalizeOpenMeteoTemperaturePayload({
    payload: {
      ...payload,
      provider: payload.provider ?? 'open-meteo',
      model: payload.model ?? params.model,
    },
    kind: params.kind,
    weight: params.weight,
  })
}

export async function fetchNwsForecastPoint(params: MeteoNwsFetchParams): Promise<MeteoForecastPoint> {
  const pointMetadata = await fetchNwsPointMetadata({
    latitude: params.latitude,
    longitude: params.longitude,
    fetchImpl: params.fetchImpl,
    userAgent: params.userAgent,
    cacheTtlMs: params.cacheTtlMs,
    retryCount: params.retryCount,
  })

  const forecastUrl = pointMetadata.forecast ?? pointMetadata.forecastHourly
  if (!forecastUrl) {
    throw new Error('NWS points lookup did not return a forecast URL')
  }

  const forecastJson = await fetchJsonWithMeteoProviderCache<{ properties?: { periods?: MeteoNwsTemperaturePayload['periods'] } }>({
    url: forecastUrl,
    fetchImpl: params.fetchImpl,
    init: { headers: buildNwsHeaders(params.userAgent) },
    cacheTtlMs: params.cacheTtlMs ?? 10 * 60_000,
    retryCount: params.retryCount ?? 1,
  })
  const periods = forecastJson.properties?.periods
  if (!periods?.length) {
    throw new Error('NWS forecast response does not contain usable periods')
  }

  return normalizeNwsTemperaturePayload({
    payload: {
      provider: 'nws',
      periods,
    },
    kind: params.kind,
    weight: params.weight,
  })
}

export async function fetchMeteostatHistoricalPoint(params: MeteoMeteostatFetchParams): Promise<MeteoForecastPoint> {
  const url = new URL('https://meteostat.p.rapidapi.com/point/daily')
  url.searchParams.set('lat', String(params.latitude))
  url.searchParams.set('lon', String(params.longitude))
  url.searchParams.set('start', params.start)
  url.searchParams.set('end', params.end)
  url.searchParams.set('units', params.units ?? 'imperial')
  if (typeof params.altitude === 'number') {
    url.searchParams.set('alt', String(params.altitude))
  }

  const headers: HeadersInit = {
    'Accept': 'application/json',
  }
  if (params.apiKey) {
    headers['X-RapidAPI-Key'] = params.apiKey
    headers['X-RapidAPI-Host'] = 'meteostat.p.rapidapi.com'
  }

  const payload = await fetchJsonWithMeteoProviderCache<MeteoMeteostatDailyPayload>({
    url: url.toString(),
    fetchImpl: params.fetchImpl,
    init: { headers },
    cacheTtlMs: params.cacheTtlMs ?? 6 * 60 * 60_000,
    retryCount: params.retryCount ?? 1,
  })

  return normalizeMeteostatDailyPayload({
    payload: {
      ...payload,
      provider: payload.provider ?? 'meteostat',
    },
    kind: params.kind,
    weight: params.weight,
    sourceLabel: params.sourceLabel ?? 'meteostat:historical',
  })
}

export async function fetchMeteoResolutionSourceObservation(input: {
  route: MeteoResolutionSourceRoute
  unit: MeteoTemperatureUnit
  fetchImpl?: typeof fetch
  cacheTtlMs?: number
  retryCount?: number
  now?: Date
  weatherApiKey?: string
}): Promise<MeteoResolutionSourceObservation> {
  if (!input.route.primary_poll_url) {
    throw new Error('Resolution source route does not define a primary polling URL')
  }

  const fetchUrl = buildResolutionObservationFetchUrl(input.route, input.weatherApiKey)
  const payload = await fetchJsonWithMeteoProviderCache<{
    properties?: {
      timestamp?: string
      temperature?: { value?: number | null; unitCode?: string | null }
    }
    observations?: Array<{
      stationID?: string
      obsTimeUtc?: string
      obsTimeLocal?: string
      imperial?: { temp?: number | null }
      metric?: { temp?: number | null }
    }>
    temperature?: {
      recordTime?: string
      data?: Array<{ place?: string; value?: number | null; unit?: string | null }>
    }
  }>({
    url: fetchUrl,
    fetchImpl: input.fetchImpl,
    cacheTtlMs: input.cacheTtlMs ?? Math.max(30_000, (input.route.freshness_sla_seconds ?? 300) * 500),
    retryCount: input.retryCount ?? 1,
  })

  if (input.route.provider === 'noaa') {
    return buildNoaaResolutionObservation({
      route: input.route,
      payload,
      unit: input.unit,
      now: input.now,
    })
  }

  if (input.route.provider === 'wunderground') {
    return buildWundergroundResolutionObservation({
      route: input.route,
      payload,
      unit: input.unit,
      now: input.now,
    })
  }

  if (input.route.provider === 'hong-kong-observatory') {
    return buildHkoResolutionObservation({
      route: input.route,
      payload,
      unit: input.unit,
      now: input.now,
    })
  }

  throw new Error(`Direct observation fetch is not implemented for provider: ${input.route.provider}`)
}

type NoaaResolutionObservationPayload = {
  properties?: {
    timestamp?: string
    temperature?: { value?: number | null; unitCode?: string | null }
  }
}

type WundergroundResolutionObservationPayload = {
  observations?: Array<{
    stationID?: string
    obsTimeUtc?: string
    obsTimeLocal?: string
    imperial?: { temp?: number | null }
    metric?: { temp?: number | null }
  }>
}

type HkoResolutionObservationPayload = {
  temperature?: {
    recordTime?: string
    data?: Array<{ place?: string; value?: number | null; unit?: string | null }>
  }
}

function buildNoaaResolutionObservation(input: {
  route: MeteoResolutionSourceRoute
  payload: NoaaResolutionObservationPayload
  unit: MeteoTemperatureUnit
  now?: Date
}): MeteoResolutionSourceObservation {
  const rawTemperature = input.payload.properties?.temperature?.value
  if (rawTemperature === null || rawTemperature === undefined || !Number.isFinite(rawTemperature)) {
    throw new Error('NOAA station observation does not contain usable temperature data')
  }

  const sourceUnit = input.payload.properties?.temperature?.unitCode?.toLowerCase().includes('degf') ? 'f' : 'c'
  const observedAt = input.payload.properties?.timestamp ?? null

  return buildResolutionObservation({
    route: input.route,
    rawTemperature,
    sourceUnit,
    targetUnit: input.unit,
    observedAt,
    now: input.now,
  })
}

function buildWundergroundResolutionObservation(input: {
  route: MeteoResolutionSourceRoute
  payload: WundergroundResolutionObservationPayload
  unit: MeteoTemperatureUnit
  now?: Date
}): MeteoResolutionSourceObservation {
  const normalizedStationCode = input.route.station_code?.trim().toLowerCase()
  const observation = input.payload.observations?.find((row) => {
    const stationId = row.stationID?.trim().toLowerCase()
    return stationId ? stationId === normalizedStationCode : false
  }) ?? input.payload.observations?.[0]
  const rawMetricTemperature = observation?.metric?.temp
  const rawImperialTemperature = observation?.imperial?.temp
  const rawTemperature = rawMetricTemperature ?? rawImperialTemperature
  if (rawTemperature === null || rawTemperature === undefined || !Number.isFinite(rawTemperature)) {
    throw new Error('Wunderground station observation does not contain usable temperature data')
  }

  return buildResolutionObservation({
    route: input.route,
    rawTemperature,
    sourceUnit: rawMetricTemperature !== null && rawMetricTemperature !== undefined ? 'c' : 'f',
    targetUnit: input.unit,
    observedAt: observation?.obsTimeUtc ?? observation?.obsTimeLocal ?? null,
    now: input.now,
  })
}

function buildHkoResolutionObservation(input: {
  route: MeteoResolutionSourceRoute
  payload: HkoResolutionObservationPayload
  unit: MeteoTemperatureUnit
  now?: Date
}): MeteoResolutionSourceObservation {
  const rows = input.payload.temperature?.data ?? []
  const normalizedStationCode = input.route.station_code?.trim().toLowerCase()
  const preferredRow = rows.find((row) => {
    const place = row.place?.trim().toLowerCase()
    if (!place) return false
    if (place === normalizedStationCode) return true
    return place.includes('hong kong observatory') || place === 'hko'
  }) ?? rows[0]
  const rawTemperature = preferredRow?.value
  if (rawTemperature === null || rawTemperature === undefined || !Number.isFinite(rawTemperature)) {
    throw new Error('HKO current weather payload does not contain usable temperature data')
  }

  const sourceUnit = normalizeTemperatureUnit(preferredRow?.unit) ?? 'c'
  const observedAt = input.payload.temperature?.recordTime ?? null

  return buildResolutionObservation({
    route: input.route,
    rawTemperature,
    sourceUnit,
    targetUnit: input.unit,
    observedAt,
    now: input.now,
  })
}

function buildResolutionObservationFetchUrl(route: MeteoResolutionSourceRoute, weatherApiKey?: string): string {
  const primaryPollUrl = route.primary_poll_url
  if (!primaryPollUrl) {
    throw new Error('Resolution source route does not define a primary polling URL')
  }

  const normalizedApiKey = weatherApiKey?.trim()
  if (route.provider !== 'wunderground' || !normalizedApiKey) return primaryPollUrl

  const url = new URL(primaryPollUrl)
  if (!url.searchParams.has('apiKey')) {
    url.searchParams.set('apiKey', normalizedApiKey)
  }
  return url.toString()
}

function buildResolutionObservation(input: {
  route: MeteoResolutionSourceRoute
  rawTemperature: number
  sourceUnit: MeteoTemperatureUnit
  targetUnit: MeteoTemperatureUnit
  observedAt: string | null
  now?: Date
}): MeteoResolutionSourceObservation {
  const temperature = input.targetUnit === input.sourceUnit
    ? input.rawTemperature
    : input.targetUnit === 'f'
      ? celsiusToFahrenheit(input.rawTemperature)
      : fahrenheitToCelsius(input.rawTemperature)
  const ageSeconds = input.observedAt && input.now
    ? Math.max(0, Math.floor((input.now.getTime() - new Date(input.observedAt).getTime()) / 1000))
    : null

  return {
    provider: input.route.provider,
    station_code: input.route.station_code,
    observed_at: input.observedAt,
    temperature: round4(temperature),
    unit: input.targetUnit,
    source_url: input.route.primary_poll_url ?? '',
    age_seconds: ageSeconds,
    is_fresh: ageSeconds === null || input.route.freshness_sla_seconds === null
      ? null
      : ageSeconds <= input.route.freshness_sla_seconds,
  }
}

export function observationToForecastPoint(observation: MeteoResolutionSourceObservation): MeteoForecastPoint {
  return {
    provider: `official-observation:${observation.provider}:${observation.station_code ?? 'unknown'}`,
    mean: observation.temperature,
    stddev: observation.is_fresh === false ? 0.8 : 0.35,
    weight: observation.is_fresh === false ? 3 : 8,
  }
}

export async function fetchNwsPointMetadata(input: {
  latitude: number
  longitude: number
  fetchImpl?: typeof fetch
  userAgent?: string
  cacheTtlMs?: number
  retryCount?: number
}): Promise<MeteoNwsPointMetadata> {
  const json = await fetchJsonWithMeteoProviderCache<{
    properties?: {
      forecast?: string
      forecastHourly?: string
      gridId?: string
      gridX?: number
      gridY?: number
    }
  }>({
    url: `https://api.weather.gov/points/${input.latitude},${input.longitude}`,
    fetchImpl: input.fetchImpl,
    init: { headers: buildNwsHeaders(input.userAgent) },
    cacheTtlMs: input.cacheTtlMs ?? 10 * 60_000,
    retryCount: input.retryCount ?? 1,
  })

  return {
    forecast: json.properties?.forecast,
    forecastHourly: json.properties?.forecastHourly,
    gridId: json.properties?.gridId,
    gridX: json.properties?.gridX,
    gridY: json.properties?.gridY,
  }
}

export function buildMeteoForecastConsensus(points: MeteoForecastPoint[]): MeteoForecastConsensus {
  if (!points.length) {
    throw new Error('At least one forecast point is required')
  }

  const normalized = points.map((point) => ({ ...point, weight: point.weight ?? 1 }))
  const totalWeight = normalized.reduce((sum, point) => sum + (point.weight ?? 0), 0)
  const mean = normalized.reduce((sum, point) => sum + point.mean * (point.weight ?? 0), 0) / totalWeight
  const secondMoment = normalized.reduce((sum, point) => {
    const weight = point.weight ?? 0
    return sum + weight * (point.stddev ** 2 + point.mean ** 2)
  }, 0) / totalWeight
  const variance = Math.max(secondMoment - mean ** 2, 0.01)

  const contributions: MeteoForecastContribution[] = normalized.map((point) => ({
    provider: point.provider,
    providerKind: inferProviderKind(point.provider),
    sourceLabel: point.provider,
    weight: point.weight ?? 1,
    mean: round4(point.mean),
    stddev: round4(point.stddev),
  }))

  return {
    mean: round4(mean),
    stddev: round4(Math.sqrt(variance)),
    totalWeight: round4(totalWeight),
    providers: [...new Set(contributions.map((entry) => entry.provider))],
    contributions,
  }
}

export function inferProviderKind(provider: string): MeteoForecastProviderKind {
  const normalized = provider.toLowerCase()
  if (normalized.includes('open-meteo')) return 'open-meteo'
  if (normalized.includes('nws') || normalized.includes('weather.gov') || normalized.includes('noaa')) return 'nws'
  if (normalized.includes('meteostat')) return 'meteostat'
  if (normalized.includes('observation') || normalized.includes('metar')) return 'official-observation'
  return 'custom'
}

export function normalizeTemperatureUnit(rawUnit: string | undefined | null): MeteoTemperatureUnit | null {
  if (!rawUnit) return null
  const normalized = rawUnit.trim().toLowerCase()
  if (normalized === '°c' || normalized === 'c' || normalized === 'celsius' || normalized === 'metric') return 'c'
  if (normalized === '°f' || normalized === 'f' || normalized === 'fahrenheit' || normalized === 'imperial') return 'f'
  return null
}

function deriveStddev(series: number[]): number {
  if (series.length === 1) {
    return 1.5
  }
  const mean = series.reduce((sum, value) => sum + value, 0) / series.length
  const variance = series.reduce((sum, value) => sum + (value - mean) ** 2, 0) / series.length
  return round4(Math.max(Math.sqrt(variance), 0.8))
}

function buildNwsHeaders(userAgent?: string): HeadersInit {
  return {
    'Accept': 'application/geo+json',
    'User-Agent': userAgent ?? 'Hermes prediction meteo module',
  }
}

function celsiusToFahrenheit(value: number): number {
  return value * 9 / 5 + 32
}

function fahrenheitToCelsius(value: number): number {
  return (value - 32) * 5 / 9
}

function celsiusToFahrenheitIfNeeded(value: number, unit: MeteoTemperatureUnit): number {
  return unit === 'c' ? celsiusToFahrenheit(value) : value
}

function round4(value: number): number {
  return Math.round(value * 10_000) / 10_000
}
