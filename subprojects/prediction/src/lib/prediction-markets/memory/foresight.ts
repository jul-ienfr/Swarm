export type PredictionMarketForesightForecast = {
  forecast_id: string
  simulation_id: string
  subject_id: string
  expected_outcome: string
  confidence?: number | null
  generated_at?: string | null
  tags?: readonly string[] | null
  metadata?: Record<string, unknown> | null
}

export type PredictionMarketForesightOutcome = {
  forecast_id?: string | null
  simulation_id?: string | null
  subject_id: string
  actual_outcome: string
  resolved_at?: string | null
  metadata?: Record<string, unknown> | null
}

export type PredictionMarketForesightValidationStatus = 'matched' | 'partial' | 'mismatched'

export type PredictionMarketForesightValidationResult = {
  forecast_id: string
  simulation_id: string
  subject_id: string
  expected_outcome: string
  actual_outcome: string
  confidence: number
  lexical_overlap: number
  exact_match: boolean
  confidence_error: number
  score: number
  status: PredictionMarketForesightValidationStatus
  validated_at: string
  resolved_at: string | null
  notes: string[]
  metadata: Record<string, unknown>
}

export type PredictionMarketForesightValidationSummary = {
  validations: number
  matched: number
  partial: number
  mismatched: number
  exact_match_rate: number
  average_score: number
  average_confidence_error: number
  average_lexical_overlap: number
  by_status: Record<PredictionMarketForesightValidationStatus, number>
}

export type PredictionMarketForesightValidationOptions = {
  now?: string | number | Date | null
  matched_threshold?: number | null
  partial_threshold?: number | null
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(1, value))
}

function toMillis(value: string | number | Date | null | undefined): number | null {
  if (value == null) return null
  if (value instanceof Date) return value.getTime()
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : null
}

function normalizeText(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function tokenize(value: string): Set<string> {
  const normalized = normalizeText(value)
  return new Set(normalized ? normalized.split(' ') : [])
}

function lexicalOverlap(expected: string, actual: string): number {
  const expectedTokens = tokenize(expected)
  const actualTokens = tokenize(actual)
  if (expectedTokens.size === 0 && actualTokens.size === 0) return 1
  if (expectedTokens.size === 0 || actualTokens.size === 0) return 0

  let intersection = 0
  for (const token of expectedTokens) {
    if (actualTokens.has(token)) intersection += 1
  }

  const union = new Set([...expectedTokens, ...actualTokens]).size
  return union === 0 ? 0 : clamp01(intersection / union)
}

export function validateForesightForecast(
  forecast: PredictionMarketForesightForecast,
  outcome: PredictionMarketForesightOutcome,
  options: PredictionMarketForesightValidationOptions = {},
): PredictionMarketForesightValidationResult {
  const validatedMillis = toMillis(options.now ?? new Date())
  const validated_at = validatedMillis == null ? new Date().toISOString() : new Date(validatedMillis).toISOString()
  const expected_outcome = forecast.expected_outcome.trim()
  const actual_outcome = outcome.actual_outcome.trim()
  const expectedNormalized = normalizeText(expected_outcome)
  const actualNormalized = normalizeText(actual_outcome)
  const exact_match = expectedNormalized.length > 0 && expectedNormalized === actualNormalized

  const overlap = lexicalOverlap(expected_outcome, actual_outcome)
  const confidence = clamp01(typeof forecast.confidence === 'number' ? forecast.confidence : overlap)

  const matchThreshold = options.matched_threshold ?? 0.75
  const partialThreshold = options.partial_threshold ?? 0.35

  const score = clamp01(
    exact_match
      ? 1
      : overlap * 0.7 + (1 - Math.abs(confidence - overlap)) * 0.3,
  )

  const status: PredictionMarketForesightValidationStatus = exact_match || score >= matchThreshold
    ? 'matched'
    : score >= partialThreshold
      ? 'partial'
      : 'mismatched'

  const notes: string[] = []
  if (!exact_match) notes.push('lexical mismatch')
  if (overlap < 0.25) notes.push('low token overlap')
  if (Math.abs(confidence - score) > 0.25) notes.push('confidence miscalibrated')
  if (forecast.subject_id !== outcome.subject_id) notes.push('subject mismatch')

  const resolvedAt = outcome.resolved_at ?? null
  const resolvedMs = toMillis(resolvedAt)
  const generatedMs = toMillis(forecast.generated_at ?? null)
  if (resolvedMs != null && generatedMs != null && resolvedMs >= generatedMs) {
    notes.push('resolution after forecast')
  }

  return {
    forecast_id: forecast.forecast_id,
    simulation_id: outcome.simulation_id ?? forecast.simulation_id,
    subject_id: outcome.subject_id,
    expected_outcome,
    actual_outcome,
    confidence,
    lexical_overlap: overlap,
    exact_match,
    confidence_error: Math.abs(confidence - score),
    score,
    status,
    validated_at,
    resolved_at: resolvedAt,
    notes,
    metadata: {
      forecast_metadata: forecast.metadata ?? {},
      outcome_metadata: outcome.metadata ?? {},
      tags: forecast.tags ?? [],
    },
  }
}

export function summarizeForesightValidation(
  validations: readonly PredictionMarketForesightValidationResult[],
): PredictionMarketForesightValidationSummary {
  const total = validations.length
  const by_status: Record<PredictionMarketForesightValidationStatus, number> = {
    matched: 0,
    partial: 0,
    mismatched: 0,
  }

  let average_score = 0
  let average_confidence_error = 0
  let average_lexical_overlap = 0

  for (const validation of validations) {
    by_status[validation.status] += 1
    average_score += validation.score
    average_confidence_error += validation.confidence_error
    average_lexical_overlap += validation.lexical_overlap
  }

  const divisor = total > 0 ? total : 1
  return {
    validations: total,
    matched: by_status.matched,
    partial: by_status.partial,
    mismatched: by_status.mismatched,
    exact_match_rate: total > 0 ? by_status.matched / total : 0,
    average_score: average_score / divisor,
    average_confidence_error: average_confidence_error / divisor,
    average_lexical_overlap: average_lexical_overlap / divisor,
    by_status,
  }
}
