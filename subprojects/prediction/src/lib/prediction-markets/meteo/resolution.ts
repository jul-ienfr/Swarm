import { parseMeteoQuestion } from '@/lib/prediction-markets/meteo/market-spec'
import type {
  MeteoMarketSpec,
  MeteoPolymarketEventInput,
  MeteoResolutionAnalysis,
  MeteoResolutionPrecision,
  MeteoResolutionProvider,
  MeteoResolutionSource,
  MeteoResolutionSourceRoute,
  MeteoResolutionStationType,
  MeteoStationMetadata,
  MeteoTemperatureKind,
  MeteoTemperatureUnit,
} from '@/lib/prediction-markets/meteo/types'

type MeteoResolutionContext = {
  question: string
  spec?: MeteoMarketSpec
  resolutionSource?: string | null
  description?: string | null
  rules?: string | null
  polymarketEvent?: MeteoPolymarketEventInput | null
}

export function extractMeteoResolutionSource(input: MeteoResolutionContext): MeteoResolutionSource {
  const spec = input.spec ?? parseMeteoQuestion(input.question)
  const extractedFrom: MeteoResolutionSource['extractedFrom'] = []
  const resolvedSource = firstNonEmpty(input.resolutionSource, input.polymarketEvent?.resolution_source)
  const description = firstNonEmpty(input.description, input.polymarketEvent?.description)
  const rules = firstNonEmpty(input.rules, input.polymarketEvent?.rules)

  if (input.resolutionSource?.trim()) extractedFrom.push('resolutionSource')
  else if (input.polymarketEvent?.resolution_source?.trim()) extractedFrom.push('resolutionSource')
  if (description) extractedFrom.push('description')
  if (rules) extractedFrom.push('rules')
  if (input.question.trim()) extractedFrom.push('question')

  const provider = inferProvider(resolvedSource, description, rules)
  const stationCode = inferStationCode(resolvedSource, description, rules)
  const stationType = inferStationType(resolvedSource, description, rules)
  const stationName = inferStationName(description, spec.city, stationCode)
  const measurementKind = inferMeasurementKind(spec.kind, input.question, description, rules)
  const unit = inferUnit(spec.unit, resolvedSource, description, rules)
  const precision = inferPrecision(description, rules)
  const finalizationRule = inferFinalizationRule(rules, description)
  const revisionRule = inferRevisionRule(rules)

  return {
    provider,
    sourceUrl: resolvedSource,
    stationName,
    stationCode,
    stationType,
    measurementField: measurementKind === 'high'
      ? 'Daily Maximum Temperature'
      : measurementKind === 'low'
        ? 'Daily Minimum Temperature'
        : null,
    measurementKind,
    unit,
    precision,
    finalizationRule,
    revisionRule,
    extractedFrom: unique(extractedFrom),
    confidence: computeConfidence({ provider, stationCode, resolvedSource, description, rules, precision }),
  }
}

export function buildMeteoStationMetadata(input: MeteoResolutionContext): MeteoStationMetadata {
  const spec = input.spec ?? parseMeteoQuestion(input.question)
  const resolution = extractMeteoResolutionSource(input)
  const notes: string[] = []

  if (resolution.stationCode && resolution.sourceUrl?.includes(resolution.stationCode)) {
    notes.push('Station code inferred from resolution source URL.')
  }
  if (resolution.stationName && spec.city && resolution.stationName.toLowerCase().includes(spec.city.toLowerCase())) {
    notes.push('Station name aligns with parsed market city.')
  }
  if (resolution.provider === 'unknown') {
    notes.push('Resolution source provider could not be confidently identified.')
  }

  return {
    stationName: resolution.stationName,
    stationCode: resolution.stationCode,
    stationType: resolution.stationType,
    countryOrRegion: spec.countryOrRegion,
    city: spec.city,
    sourceProvider: resolution.provider,
    sourceUrl: resolution.sourceUrl,
    sourceNetwork: toSourceNetwork(resolution.provider),
    notes,
  }
}

export function analyzeMeteoResolutionSource(input: MeteoResolutionContext): MeteoResolutionAnalysis & { matchedSignals: string[] } {
  const resolution = extractMeteoResolutionSource(input)
  const matchedSignals = [
    resolution.provider !== 'unknown' ? 'provider' : null,
    resolution.stationCode ? 'station_code' : null,
    resolution.stationName ? 'station_name' : null,
    resolution.precision !== 'unknown' ? 'precision' : null,
    resolution.measurementKind !== 'unknown' ? 'measurement_kind' : null,
    resolution.finalizationRule ? 'finalization_rule' : null,
  ].filter((value): value is string => Boolean(value))

  const isOfficialSourceIdentified = resolution.provider !== 'unknown' && Boolean(resolution.sourceUrl || resolution.stationCode)
  return {
    isOfficialSourceIdentified,
    needsManualReview: !isOfficialSourceIdentified || resolution.confidence < 0.7,
    confidence: resolution.confidence,
    matchedSignals,
  }
}

export function buildMeteoResolutionSourceRoute(resolution: MeteoResolutionSource): MeteoResolutionSourceRoute {
  const stationCode = resolution.stationCode
  const fallbackPollUrls = resolution.sourceUrl ? [resolution.sourceUrl] : []

  if (resolution.provider === 'noaa' && stationCode) {
    return {
      provider: resolution.provider,
      station_code: stationCode,
      primary_poll_url: `https://api.weather.gov/stations/${stationCode}/observations/latest`,
      fallback_poll_urls: fallbackPollUrls,
      measurement_path: 'properties.temperature.value',
      expected_lag_seconds: 900,
      freshness_sla_seconds: 1200,
      official_lag_seconds: null,
    }
  }

  if (resolution.provider === 'wunderground' && stationCode) {
    const units = resolution.unit === 'c' ? 'm' : 'e'
    return {
      provider: resolution.provider,
      station_code: stationCode,
      primary_poll_url: `https://api.weather.com/v2/pws/observations/current?stationId=${stationCode}&format=json&units=${units}`,
      fallback_poll_urls: fallbackPollUrls,
      measurement_path: units === 'm' ? 'observations[0].metric.temp' : 'observations[0].imperial.temp',
      expected_lag_seconds: 1800,
      freshness_sla_seconds: 3600,
      official_lag_seconds: null,
    }
  }

  if (resolution.provider === 'hong-kong-observatory') {
    return {
      provider: resolution.provider,
      station_code: stationCode,
      primary_poll_url: 'https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en',
      fallback_poll_urls: [
        'https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?dataType=CLMTEMP&lang=en',
        ...fallbackPollUrls,
      ],
      measurement_path: 'temperature.data[].value filtered by place/station',
      expected_lag_seconds: 600,
      freshness_sla_seconds: 1200,
      official_lag_seconds: 86400,
    }
  }

  return {
    provider: resolution.provider,
    station_code: stationCode,
    primary_poll_url: resolution.sourceUrl,
    fallback_poll_urls: [],
    measurement_path: null,
    expected_lag_seconds: null,
    freshness_sla_seconds: null,
    official_lag_seconds: null,
  }
}

function firstNonEmpty(...values: Array<string | null | undefined>): string | null {
  for (const value of values) {
    const normalized = value?.trim()
    if (normalized) return normalized
  }
  return null
}

function inferProvider(...values: Array<string | null>): MeteoResolutionProvider {
  const joined = values.filter(Boolean).join(' ').toLowerCase()
  if (joined.includes('weather.gov') || joined.includes('noaa.gov')) return 'noaa'
  if (joined.includes('wunderground.com') || joined.includes('weather underground')) return 'wunderground'
  if (joined.includes('forecast.weather.gov') || joined.includes('national weather service')) return 'nws'
  if (joined.includes('hko.gov.hk') || joined.includes('hong kong observatory')) return 'hong-kong-observatory'
  return 'unknown'
}

function inferStationCode(...values: Array<string | null>): string | null {
  for (const value of values) {
    if (!value) continue
    const urlCode = value.match(/\/([A-Z0-9]{4,6})(?:\b|\/|\?|$)/)
    if (urlCode) return urlCode[1]
    const textCode = value.match(/\bstation\s*(?:code)?[:\s-]*([A-Z0-9]{3,6})\b/i)
    if (textCode) return textCode[1].toUpperCase()
  }
  return null
}

function inferStationType(...values: Array<string | null>): MeteoResolutionStationType {
  const joined = values.filter(Boolean).join(' ').toLowerCase()
  if (joined.includes('airport')) return 'airport'
  if (joined.includes('station')) return 'weather-station'
  return 'unknown'
}

function inferStationName(description: string | null, city: string | null, stationCode: string | null): string | null {
  if (description) {
    const airportMatch = description.match(/recorded at\s+([^.,]+?)(?:\s+station)?[.,]/i)
    if (airportMatch) return airportMatch[1].trim()
    const genericMatch = description.match(/(?:at|from)\s+([^.,]+?(?:station|airport))/i)
    if (genericMatch) return genericMatch[1].trim()
  }
  if (city && stationCode) return `${city} ${stationCode}`
  if (city) return `${city} weather station`
  return null
}

function inferMeasurementKind(
  specKind: MeteoTemperatureKind | null | undefined,
  question: string,
  description: string | null,
  rules: string | null,
): MeteoTemperatureKind | 'unknown' {
  if (specKind) return specKind
  const joined = `${question} ${description ?? ''} ${rules ?? ''}`.toLowerCase()
  if (joined.includes('highest temperature') || joined.includes('daily maximum')) return 'high'
  if (joined.includes('lowest temperature') || joined.includes('daily minimum')) return 'low'
  return 'unknown'
}

function inferUnit(
  specUnit: MeteoTemperatureUnit | null | undefined,
  ...values: Array<string | null>
): MeteoTemperatureUnit | null {
  if (specUnit) return specUnit
  const joined = values.filter(Boolean).join(' ').toLowerCase()
  if (joined.includes('fahrenheit') || /\b\d+\s*°?f\b/.test(joined)) return 'f'
  if (joined.includes('celsius') || /\b\d+\s*°?c\b/.test(joined)) return 'c'
  return null
}

function inferPrecision(...values: Array<string | null>): MeteoResolutionPrecision {
  const joined = values.filter(Boolean).join(' ').toLowerCase()
  if (joined.includes('whole degree')) return 'whole-degree'
  if (joined.includes('tenth') || joined.includes('0.1')) return 'tenth-degree'
  return 'unknown'
}

function inferFinalizationRule(rules: string | null, description: string | null): string | null {
  const text = firstNonEmpty(rules, description)
  if (!text) return null
  if (/finalized|finalisation|finalization/i.test(text)) return text
  if (/measured/i.test(text)) return text
  return null
}

function inferRevisionRule(rules: string | null): string | null {
  if (!rules) return null
  const match = rules.match(/([^.!?]*revision[^.!?]*[.!?]?)/i)
  return match?.[1]?.trim() ?? null
}

function computeConfidence(input: {
  provider: MeteoResolutionProvider
  stationCode: string | null
  resolvedSource: string | null
  description: string | null
  rules: string | null
  precision: MeteoResolutionPrecision
}): number {
  let score = 0.2
  if (input.provider !== 'unknown') score += 0.25
  if (input.resolvedSource) score += 0.2
  if (input.stationCode) score += 0.15
  if (input.description) score += 0.1
  if (input.rules) score += 0.1
  if (input.precision !== 'unknown') score += 0.1
  return Math.min(0.99, Math.round(score * 100) / 100)
}

function toSourceNetwork(provider: MeteoResolutionProvider): string | null {
  switch (provider) {
    case 'noaa':
      return 'NOAA'
    case 'nws':
      return 'NWS'
    case 'wunderground':
      return 'Weather Underground'
    case 'hong-kong-observatory':
      return 'Hong Kong Observatory'
    default:
      return null
  }
}

function unique<T>(values: T[]): T[] {
  return [...new Set(values)]
}