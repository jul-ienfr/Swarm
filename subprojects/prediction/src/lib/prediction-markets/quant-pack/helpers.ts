export type QuantSide = 'yes' | 'no'

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function round(value: number, digits = 4): number {
  if (!Number.isFinite(value)) return 0
  return Number(value.toFixed(digits))
}

export function sum(values: readonly number[]): number {
  return values.reduce((acc, value) => acc + (Number.isFinite(value) ? value : 0), 0)
}

export function mean(values: readonly number[]): number {
  const usable = values.filter((value) => Number.isFinite(value))
  if (usable.length === 0) return 0
  return sum(usable) / usable.length
}

export function uniqueStrings(values: readonly (string | null | undefined)[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const value of values) {
    const text = String(value ?? '').trim()
    if (!text || seen.has(text)) continue
    seen.add(text)
    out.push(text)
  }
  return out
}

export function normalizeText(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function tokenize(value: string): string[] {
  return normalizeText(value)
    .split(' ')
    .map((token) => token.trim())
    .filter((token) => token.length > 1)
}

export function jaccard(left: readonly string[], right: readonly string[]): number {
  const leftSet = new Set(left)
  const rightSet = new Set(right)
  const universe = new Set([...leftSet, ...rightSet])
  if (universe.size === 0) return 0

  let intersection = 0
  for (const token of leftSet) {
    if (rightSet.has(token)) intersection += 1
  }

  return intersection / universe.size
}

export function asPositiveFiniteNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

