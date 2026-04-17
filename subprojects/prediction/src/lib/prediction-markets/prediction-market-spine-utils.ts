import { createHash } from 'node:crypto'

export type PredictionMarketJsonPrimitive = string | number | boolean | null
export type PredictionMarketJson =
  | PredictionMarketJsonPrimitive
  | PredictionMarketJson[]
  | { [key: string]: PredictionMarketJson }

export function isPlainRecord(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  if (Array.isArray(value)) {
    return false
  }
  return Object.prototype.toString.call(value) === '[object Object]'
}

export function normalizeText(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const normalized = value.replace(/\s+/g, ' ').trim()
  return normalized.length ? normalized : null
}

export function toFiniteNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim().length) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }
  return fallback
}

export function clampNumber(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) {
    return min
  }
  return Math.min(max, Math.max(min, value))
}

export function roundNumber(value: number, digits = 4): number {
  const factor = 10 ** digits
  return Math.round((Number.isFinite(value) ? value : 0) * factor) / factor
}

export function dedupeStrings(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>()
  const deduped: string[] = []
  for (const value of values) {
    const normalized = normalizeText(value)
    if (!normalized || seen.has(normalized)) {
      continue
    }
    seen.add(normalized)
    deduped.push(normalized)
  }
  return deduped
}

export function compactParts(parts: Array<string | null | undefined>): string {
  return dedupeStrings(parts).join(' • ')
}

function sortDeep(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((entry) => sortDeep(entry))
  }
  if (isPlainRecord(value)) {
    return Object.keys(value)
      .sort((left, right) => left.localeCompare(right))
      .reduce<Record<string, unknown>>((accumulator, key) => {
        const nested = sortDeep(value[key])
        if (nested !== undefined) {
          accumulator[key] = nested as never
        }
        return accumulator
      }, {})
  }
  return value
}

export function stableJson(value: unknown): string {
  return JSON.stringify(sortDeep(value))
}

export function fingerprint(prefix: string, value: unknown): string {
  const payload = stableJson(value)
  const digest = createHash('sha256').update(payload).digest('hex').slice(0, 16)
  return `${prefix}:${digest}`
}

export function average(values: number[]): number {
  if (!values.length) {
    return 0
  }
  const total = values.reduce((sum, value) => sum + (Number.isFinite(value) ? value : 0), 0)
  return total / values.length
}

export function maxOrNull(values: number[]): number | null {
  if (!values.length) {
    return null
  }
  return Math.max(...values)
}

export function minOrNull(values: number[]): number | null {
  if (!values.length) {
    return null
  }
  return Math.min(...values)
}
