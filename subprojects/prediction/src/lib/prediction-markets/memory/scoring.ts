import type { PredictionMarketMemoryEntry } from '@/lib/prediction-markets/memory/provider'

export type PredictionMarketMemoryScoreBreakdown = {
  importance: number
  recency: number
  structure: number
  total: number
  signals: string[]
}

export type PredictionMarketMemoryScoreOptions = {
  now?: string | number | Date | null
  half_life_hours?: number | null
  importance_weight?: number | null
  recency_weight?: number | null
  structure_weight?: number | null
}

export type PredictionMarketScoredMemoryEntry = PredictionMarketMemoryEntry & {
  score: number
  score_breakdown: PredictionMarketMemoryScoreBreakdown
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(1, value))
}

function toMillis(value: string | number | Date | null | undefined): number | null {
  if (value == null) return null
  if (value instanceof Date) {
    const millis = value.getTime()
    return Number.isFinite(millis) ? millis : null
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }
  const millis = Date.parse(value)
  return Number.isFinite(millis) ? millis : null
}

function stringify(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function normalizeImportanceCandidate(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  if (value <= 0) return 0
  if (value <= 1) return value
  if (value <= 100) return value / 100
  return 1
}

function collectMetadataSignals(metadata: Record<string, unknown>): { score: number; signals: string[] } {
  const signals: string[] = []
  let score = 0

  for (const key of ['importance', 'priority', 'weight', 'signal_strength', 'salience', 'confidence']) {
    const candidate = normalizeImportanceCandidate(metadata[key])
    if (candidate == null) continue
    score = Math.max(score, candidate)
    signals.push(`metadata:${key}`)
  }

  const status = String(metadata.validation_status ?? metadata.status ?? '').toLowerCase()
  if (status.includes('confirm') || status.includes('valid') || status.includes('hit')) {
    score = Math.max(score, 0.82)
    signals.push('metadata:validated')
  } else if (status.includes('reject') || status.includes('miss')) {
    score = Math.max(score, 0.18)
    signals.push('metadata:negative')
  }

  if (metadata.freshness != null) {
    const freshness = normalizeImportanceCandidate(metadata.freshness)
    if (freshness != null) {
      score = Math.max(score, freshness)
      signals.push('metadata:freshness')
    }
  }

  return { score: clamp01(score), signals }
}

function collectContentSignals(content: unknown): { score: number; signals: string[] } {
  const signals: string[] = []
  const text = stringify(content).trim()
  if (!text) return { score: 0, signals }

  const lower = text.toLowerCase()
  let score = 0.18
  if (lower.includes('forecast')) {
    score += 0.08
    signals.push('content:forecast')
  }
  if (lower.includes('validation')) {
    score += 0.06
    signals.push('content:validation')
  }
  if (lower.includes('decision')) {
    score += 0.05
    signals.push('content:decision')
  }
  if (lower.includes('simulation')) {
    score += 0.06
    signals.push('content:simulation')
  }
  if (lower.includes('evidence') || lower.includes('source')) {
    score += 0.04
    signals.push('content:evidence')
  }

  if (text.length > 240) {
    score += 0.08
    signals.push('content:longform')
  } else if (text.length > 120) {
    score += 0.04
    signals.push('content:structured')
  }

  if (text.includes('{') || text.includes('[')) {
    score += 0.04
    signals.push('content:structured_payload')
  }

  return { score: clamp01(score), signals }
}

function collectTagSignals(tags: readonly string[] | undefined): { score: number; signals: string[] } {
  const normalized = [...new Set((tags ?? []).map((tag) => String(tag ?? '').trim().toLowerCase()).filter(Boolean))]
  const signals: string[] = []
  let score = 0

  for (const tag of normalized) {
    if (['foresight', 'validation', 'decision', 'simulation', 'cross-simulation', 'cross_simulation'].includes(tag)) {
      score += 0.05
      signals.push(`tag:${tag}`)
    } else if (['research', 'signal', 'benchmark', 'forecast', 'memory'].includes(tag)) {
      score += 0.03
      signals.push(`tag:${tag}`)
    }
  }

  return { score: clamp01(score), signals }
}

export function scoreMemoryImportance(
  target: Pick<
    PredictionMarketMemoryEntry,
    'content' | 'tags' | 'metadata' | 'created_at' | 'updated_at' | 'source_ref' | 'namespace' | 'kind' | 'subject_id'
  >,
): number {
  const metadataSignals = collectMetadataSignals(target.metadata ?? {})
  const contentSignals = collectContentSignals(target.content)
  const tagSignals = collectTagSignals(target.tags)

  const identitySignals = [
    target.namespace,
    target.kind,
    target.subject_id,
    target.source_ref,
  ].filter(Boolean).length

  const identityBonus = identitySignals > 0 ? Math.min(0.06, identitySignals * 0.015) : 0
  const createdBonus = target.created_at ? 0.01 : 0
  const updatedBonus = target.updated_at ? 0.01 : 0

  return clamp01(
    metadataSignals.score * 0.55 +
    contentSignals.score * 0.3 +
    tagSignals.score * 0.1 +
    identityBonus +
    createdBonus +
    updatedBonus,
  )
}

export function scoreMemoryTimeDecay(
  target: Pick<PredictionMarketMemoryEntry, 'created_at' | 'updated_at'>,
  options: PredictionMarketMemoryScoreOptions = {},
): number {
  const reference = toMillis(options.now ?? new Date())
  const baseline = toMillis(target.updated_at ?? target.created_at ?? options.now ?? new Date())
  if (reference == null || baseline == null) return 1

  const ageHours = Math.max(0, (reference - baseline) / 3_600_000)
  const halfLifeHours = Math.max(0.25, options.half_life_hours ?? 72)
  return clamp01(Math.exp((-Math.LN2 * ageHours) / halfLifeHours))
}

function scoreStructure(target: Pick<PredictionMarketMemoryEntry, 'content' | 'metadata'>): number {
  const content = target.content
  if (content == null) return 0.05

  let score = 0.12
  if (Array.isArray(content)) {
    score += Math.min(0.2, content.length * 0.02)
  } else if (typeof content === 'object') {
    const keys = Object.keys(content as Record<string, unknown>)
    score += Math.min(0.22, keys.length * 0.03)
    if (keys.some((key) => ['forecast', 'validation', 'summary', 'evidence', 'outcome', 'decision'].includes(key))) {
      score += 0.06
    }
  } else if (typeof content === 'string') {
    score += Math.min(0.2, Math.max(0, content.length - 40) / 600)
  }

  if (target.metadata && Object.keys(target.metadata).length > 0) {
    score += 0.08
  }

  return clamp01(score)
}

export function scoreMemoryPriority(
  target: Pick<
    PredictionMarketMemoryEntry,
    'content' | 'tags' | 'metadata' | 'created_at' | 'updated_at' | 'source_ref' | 'namespace' | 'kind' | 'subject_id'
  >,
  options: PredictionMarketMemoryScoreOptions = {},
): PredictionMarketMemoryScoreBreakdown {
  const importance = scoreMemoryImportance(target)
  const recency = scoreMemoryTimeDecay(target, options)
  const structure = scoreStructure(target)

  const importanceWeight = options.importance_weight ?? 0.55
  const recencyWeight = options.recency_weight ?? 0.35
  const structureWeight = options.structure_weight ?? 0.1
  const weightTotal = importanceWeight + recencyWeight + structureWeight
  const normalizedWeightTotal = weightTotal > 0 ? weightTotal : 1

  const total = clamp01(
    (
      importance * importanceWeight +
      recency * recencyWeight +
      structure * structureWeight
    ) / normalizedWeightTotal,
  )

  return {
    importance,
    recency,
    structure,
    total,
    signals: [
      `importance=${importance.toFixed(3)}`,
      `recency=${recency.toFixed(3)}`,
      `structure=${structure.toFixed(3)}`,
    ],
  }
}

export function scoreMemoryEntry(
  entry: PredictionMarketMemoryEntry,
  options: PredictionMarketMemoryScoreOptions = {},
): PredictionMarketScoredMemoryEntry {
  const score_breakdown = scoreMemoryPriority(entry, options)
  return {
    ...entry,
    score: score_breakdown.total,
    score_breakdown,
  }
}

export function rankMemoryEntries(
  entries: readonly PredictionMarketMemoryEntry[],
  options: PredictionMarketMemoryScoreOptions = {},
): PredictionMarketScoredMemoryEntry[] {
  return [...entries]
    .map((entry) => scoreMemoryEntry(entry, options))
    .sort((left, right) => {
      const delta = right.score - left.score
      if (delta !== 0) return delta
      const updatedDelta = Date.parse(right.updated_at) - Date.parse(left.updated_at)
      if (updatedDelta !== 0) return updatedDelta
      const createdDelta = Date.parse(right.created_at) - Date.parse(left.created_at)
      if (createdDelta !== 0) return createdDelta
      return left.memory_id.localeCompare(right.memory_id)
    })
}
