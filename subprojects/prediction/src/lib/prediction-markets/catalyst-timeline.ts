import {
  average,
  clampNumber,
  compactParts,
  dedupeStrings,
  fingerprint,
  normalizeText,
  roundNumber,
  toFiniteNumber,
} from './prediction-market-spine-utils'

export type PredictionMarketCatalystStatus = 'pending' | 'confirmed' | 'missed' | 'resolved' | 'invalidated'
export type PredictionMarketCatalystDirection = 'bullish' | 'bearish' | 'neutral'

export interface PredictionMarketCatalystInput {
  catalyst_id?: string | null
  label: string
  expected_at?: string | null
  occurred_at?: string | null
  status?: PredictionMarketCatalystStatus | null
  direction?: PredictionMarketCatalystDirection | null
  urgency?: number | null
  source_refs?: string[] | null
  impact_hint?: string | null
}

export interface PredictionMarketCatalystEvent {
  catalyst_id: string
  label: string
  expected_at: string | null
  occurred_at: string | null
  status: PredictionMarketCatalystStatus
  direction: PredictionMarketCatalystDirection
  urgency: number
  source_refs: string[]
  impact_hint: string | null
  sequence: number
  overdue: boolean
  lateness_minutes: number | null
  fingerprint: string
}

export interface PredictionMarketCatalystTimeline {
  timeline_id: string
  market_id: string
  as_of: string
  events: PredictionMarketCatalystEvent[]
  pending_count: number
  confirmed_count: number
  missed_count: number
  overdue_count: number
  urgency_score: number
  next_event_id: string | null
  source_refs: string[]
  summary: string
}

export interface PredictionMarketCatalystTimelineInput {
  market_id: string
  as_of?: string
  catalysts: PredictionMarketCatalystInput[]
}

function normalizeCatalystStatus(
  status: PredictionMarketCatalystStatus | null | undefined,
): PredictionMarketCatalystStatus {
  if (status === 'pending' || status === 'confirmed' || status === 'missed' || status === 'resolved' || status === 'invalidated') {
    return status
  }
  return 'pending'
}

function normalizeCatalystDirection(
  direction: PredictionMarketCatalystDirection | null | undefined,
): PredictionMarketCatalystDirection {
  if (direction === 'bullish' || direction === 'bearish' || direction === 'neutral') {
    return direction
  }
  return 'neutral'
}

function computeLatenessMinutes(asOf: string, expectedAt: string | null, status: PredictionMarketCatalystStatus): number | null {
  if (!expectedAt || status !== 'pending') {
    return null
  }
  const expected = Date.parse(expectedAt)
  const anchor = Date.parse(asOf)
  if (!Number.isFinite(expected) || !Number.isFinite(anchor) || anchor <= expected) {
    return null
  }
  return Math.round((anchor - expected) / 60_000)
}

export function buildPredictionMarketCatalystTimeline(
  input: PredictionMarketCatalystTimelineInput,
): PredictionMarketCatalystTimeline {
  const as_of = normalizeText(input.as_of) ?? new Date().toISOString()

  const events = input.catalysts
    .map<PredictionMarketCatalystEvent>((catalyst, index) => {
      const catalyst_id = normalizeText(catalyst.catalyst_id) ?? `${input.market_id}:catalyst:${index + 1}`
      const label = normalizeText(catalyst.label) ?? catalyst_id
      const expected_at = normalizeText(catalyst.expected_at)
      const occurred_at = normalizeText(catalyst.occurred_at)
      const status = normalizeCatalystStatus(catalyst.status)
      const direction = normalizeCatalystDirection(catalyst.direction)
      const urgency = clampNumber(toFiniteNumber(catalyst.urgency, 0.5), 0, 1)
      const source_refs = dedupeStrings(catalyst.source_refs ?? [])
      const impact_hint = normalizeText(catalyst.impact_hint)
      const lateness_minutes = computeLatenessMinutes(as_of, expected_at, status)
      const overdue = lateness_minutes !== null
      return {
        catalyst_id,
        label,
        expected_at,
        occurred_at,
        status,
        direction,
        urgency,
        source_refs,
        impact_hint,
        sequence: index + 1,
        overdue,
        lateness_minutes,
        fingerprint: fingerprint('catalyst-event', {
          catalyst_id,
          label,
          expected_at,
          occurred_at,
          status,
          direction,
          urgency,
          source_refs,
          impact_hint,
          overdue,
          lateness_minutes,
        }),
      }
    })
    .sort((left, right) => {
      const leftTime = Date.parse(left.expected_at ?? left.occurred_at ?? as_of)
      const rightTime = Date.parse(right.expected_at ?? right.occurred_at ?? as_of)
      if (Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime !== rightTime) {
        return leftTime - rightTime
      }
      if (right.urgency !== left.urgency) {
        return right.urgency - left.urgency
      }
      return left.label.localeCompare(right.label)
    })
    .map((event, index) => ({
      ...event,
      sequence: index + 1,
    }))

  const pending_count = events.filter((event) => event.status === 'pending').length
  const confirmed_count = events.filter((event) => event.status === 'confirmed' || event.status === 'resolved').length
  const missed_count = events.filter((event) => event.status === 'missed' || event.status === 'invalidated').length
  const overdue_count = events.filter((event) => event.overdue).length
  const urgency_score = roundNumber(
    clampNumber(
      average(events.map((event) => event.urgency)) * 0.6 +
        (confirmed_count + pending_count * 0.5 + overdue_count * 0.75) / Math.max(events.length, 1) * 0.4,
      0,
      1,
    ),
    4,
  )
  const next_event = events.find((event) => event.status === 'pending') ?? events[0] ?? null
  const timeline_id = fingerprint('catalyst-timeline', {
    market_id: input.market_id,
    as_of,
    events: events.map((event) => event.fingerprint),
  })
  const source_refs = dedupeStrings(events.flatMap((event) => event.source_refs))
  const summary = compactParts([
    `${events.length} catalysts`,
    `${pending_count} pending`,
    `${confirmed_count} confirmed`,
    `${overdue_count} overdue`,
    next_event ? `next=${next_event.label}` : null,
  ])

  return {
    timeline_id,
    market_id: input.market_id,
    as_of,
    events,
    pending_count,
    confirmed_count,
    missed_count,
    overdue_count,
    urgency_score,
    next_event_id: next_event?.catalyst_id ?? null,
    source_refs,
    summary,
  }
}
