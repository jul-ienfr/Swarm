import type {
  MeteoMarketSpec,
  MeteoTemperatureBin,
  MeteoTemperatureKind,
  MeteoTemperatureUnit,
} from '@/lib/prediction-markets/meteo/types'

const DATE_PATTERN = /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4}\b/i
const KIND_PATTERNS: Array<{ pattern: RegExp; kind: MeteoTemperatureKind }> = [
  { pattern: /highest temperature/i, kind: 'high' },
  { pattern: /high(?:est)? temp/i, kind: 'high' },
  { pattern: /lowest temperature/i, kind: 'low' },
  { pattern: /low(?:est)? temp/i, kind: 'low' },
]

export function parseMeteoQuestion(question: string): MeteoMarketSpec {
  const cityRegion = extractCityAndRegion(question)
  const marketDateMatch = question.match(DATE_PATTERN)
  const kind = KIND_PATTERNS.find((candidate) => candidate.pattern.test(question))?.kind ?? null
  const bins = parseTemperatureBins(question)
  const unit = bins[0]?.unit ?? inferUnitFromQuestion(question)

  return {
    question,
    city: cityRegion.city,
    countryOrRegion: cityRegion.countryOrRegion,
    marketDate: marketDateMatch?.[0] ?? null,
    kind,
    unit,
    bins,
  }
}

function extractCityAndRegion(question: string): { city: string | null; countryOrRegion: string | null } {
  const normalized = question.replace(/\s+/g, ' ').trim()
  const match = normalized.match(/in\s+([^?]+?)(?:\s+on\s+|\?|$)/i)
  if (!match) {
    return { city: null, countryOrRegion: null }
  }

  const rawPlace = match[1]
    .replace(/^(the)\s+/i, '')
    .replace(/\bfor\b.*$/i, '')
    .trim()

  const [cityPart, regionPart] = rawPlace.split(',').map((part) => part.trim()).filter(Boolean)

  return {
    city: cityPart ?? null,
    countryOrRegion: regionPart ?? null,
  }
}

export function parseTemperatureBins(question: string): MeteoTemperatureBin[] {
  const seen = new Set<string>()
  const bins: MeteoTemperatureBin[] = []
  const rangePattern = /(\d+(?:\.\d+)?)\s*[°º]?\s*([CF])\s*[–-]\s*(\d+(?:\.\d+)?)\s*[°º]?\s*\2/gi
  const plusPattern = /(\d+(?:\.\d+)?)\s*[°º]?\s*([CF])\s*\+/gi
  const underPattern = /(?:under|below)\s*(\d+(?:\.\d+)?)\s*[°º]?\s*([CF])/gi

  for (const match of question.matchAll(rangePattern)) {
    const lowerValue = Number(match[1])
    const upperValue = Number(match[3])
    const unit = normalizeUnit(match[2])
    const label = `${lowerValue}-${upperValue}${unit.toUpperCase()}`
    if (seen.has(label)) continue
    seen.add(label)
    bins.push({
      label,
      unit,
      lower: { value: lowerValue, inclusive: true },
      upper: { value: upperValue, inclusive: true },
    })
  }

  for (const match of question.matchAll(plusPattern)) {
    const lowerValue = Number(match[1])
    const unit = normalizeUnit(match[2])
    const label = `${lowerValue}+${unit.toUpperCase()}`
    if (seen.has(label)) continue
    seen.add(label)
    bins.push({
      label,
      unit,
      lower: { value: lowerValue, inclusive: true },
      upper: null,
    })
  }

  for (const match of question.matchAll(underPattern)) {
    const upperValue = Number(match[1])
    const unit = normalizeUnit(match[2])
    const label = `under-${upperValue}${unit.toUpperCase()}`
    if (seen.has(label)) continue
    seen.add(label)
    bins.push({
      label,
      unit,
      lower: null,
      upper: { value: upperValue, inclusive: false },
    })
  }

  return bins.sort(compareBins)
}

function inferUnitFromQuestion(question: string): MeteoTemperatureUnit | null {
  if (/\bF\b|fahrenheit/i.test(question)) {
    return 'f'
  }
  if (/\bC\b|celsius/i.test(question)) {
    return 'c'
  }
  return null
}

function normalizeUnit(value: string): MeteoTemperatureUnit {
  return value.toLowerCase() === 'f' ? 'f' : 'c'
}

function compareBins(left: MeteoTemperatureBin, right: MeteoTemperatureBin): number {
  const leftFloor = left.lower?.value ?? Number.NEGATIVE_INFINITY
  const rightFloor = right.lower?.value ?? Number.NEGATIVE_INFINITY
  if (leftFloor !== rightFloor) {
    return leftFloor - rightFloor
  }

  const leftCeiling = left.upper?.value ?? Number.POSITIVE_INFINITY
  const rightCeiling = right.upper?.value ?? Number.POSITIVE_INFINITY
  return leftCeiling - rightCeiling
}
