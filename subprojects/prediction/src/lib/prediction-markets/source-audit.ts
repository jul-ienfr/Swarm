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
import {
  buildPredictionMarketExternalIntegrationSummary,
  matchConversationScopedExternalSourceProfiles,
  type PredictionMarketExternalIntegrationSummary,
  type PredictionMarketExternalSourceProfileSummary,
} from './external-source-profiles'
import { buildPredictionMarketWatchlistAudit } from './watchlist-audit'

export type PredictionMarketSourceKind =
  | 'official_docs'
  | 'market_data'
  | 'news'
  | 'community_repo'
  | 'manual_note'
  | 'operator_brief'
  | 'decision_packet'
  | 'audit_log'
  | 'simulation'
  | 'other'

export type PredictionMarketSourceStatus = 'primary' | 'supporting' | 'weak'

export interface PredictionMarketSourceInput {
  source_id?: string | null
  kind: PredictionMarketSourceKind | string
  title: string
  url?: string | null
  captured_at?: string | null
  trust?: number | null
  freshness?: number | null
  evidence_strength?: number | null
  notes?: string[] | null
  source_refs?: string[] | null
  geo_refs?: string[] | null
}

export interface PredictionMarketSourceAuditEntry {
  source_id: string
  kind: string
  normalized_kind: PredictionMarketSourceKind | 'other'
  title: string
  url: string | null
  captured_at: string | null
  trust: number
  freshness: number
  evidence_strength: number
  score: number
  score_bps: number
  status: PredictionMarketSourceStatus
  notes: string[]
  source_refs: string[]
  geo_refs: string[]
  external_profiles: PredictionMarketExternalSourceProfileSummary[]
  fingerprint: string
}

export interface PredictionMarketSourceAudit {
  audit_id: string
  market_id: string
  as_of: string
  entries: PredictionMarketSourceAuditEntry[]
  primary_sources: PredictionMarketSourceAuditEntry[]
  supporting_sources: PredictionMarketSourceAuditEntry[]
  weak_sources: PredictionMarketSourceAuditEntry[]
  average_score: number
  coverage_score: number
  missing_url_sources: string[]
  source_kind_counts: Record<string, number>
  source_refs: string[]
  geo_refs: string[]
  external_profiles: PredictionMarketExternalSourceProfileSummary[]
  external_integration: PredictionMarketExternalIntegrationSummary
  watchlist_audit?: ReturnType<typeof buildPredictionMarketWatchlistAudit>
  summary: string
}

export interface PredictionMarketSourceAuditInput {
  market_id: string
  as_of?: string
  sources: PredictionMarketSourceInput[]
  primary_kinds?: Array<PredictionMarketSourceKind | string>
  minimum_primary_score?: number
}

const KNOWN_SOURCE_KINDS = new Set<PredictionMarketSourceKind>([
  'official_docs',
  'market_data',
  'news',
  'community_repo',
  'manual_note',
  'operator_brief',
  'decision_packet',
  'audit_log',
  'simulation',
  'other',
])

function normalizeGeoRef(value: string | null | undefined): string | null {
  const normalized = normalizeText(value)
  if (!normalized) return null
  if (/^\d{6}$/.test(normalized)) return normalized
  const prefixed = normalized.match(/(?:geo|adcode|cn)[:#/-]?(\d{6})/i)
  return prefixed?.[1] ?? null
}

function collectGeoRefs(input: PredictionMarketSourceInput, notes: string[], sourceRefs: string[]): string[] {
  return dedupeStrings([
    ...(input.geo_refs ?? []),
    ...notes,
    ...sourceRefs,
  ]
    .map((value) => normalizeGeoRef(value))
    .filter((value): value is string => value != null))
}

function normalizeSourceKind(kind: string): PredictionMarketSourceKind | 'other' {
  const normalized = normalizeText(kind)?.toLowerCase().replace(/[^a-z0-9]+/g, '_')
  if (!normalized) {
    return 'other'
  }
  if (KNOWN_SOURCE_KINDS.has(normalized as PredictionMarketSourceKind)) {
    return normalized as PredictionMarketSourceKind
  }
  return 'other'
}

function scoreSource(source: PredictionMarketSourceInput): PredictionMarketSourceAuditEntry {
  const normalizedKind = normalizeSourceKind(source.kind)
  const trust = clampNumber(toFiniteNumber(source.trust, 0.6), 0, 1)
  const freshness = clampNumber(toFiniteNumber(source.freshness, 0.6), 0, 1)
  const evidenceStrength = clampNumber(toFiniteNumber(source.evidence_strength, 0.6), 0, 1)
  const weightedScore = roundNumber(trust * 0.46 + freshness * 0.3 + evidenceStrength * 0.24, 4)
  const score = clampNumber(weightedScore, 0, 1)
  const status: PredictionMarketSourceStatus =
    score >= 0.75 || normalizedKind === 'official_docs' || normalizedKind === 'market_data'
      ? 'primary'
      : score >= 0.5
        ? 'supporting'
        : 'weak'

  const source_id = normalizeText(source.source_id) ?? fingerprint('source', source)
  const title = normalizeText(source.title) ?? 'Untitled source'
  const url = normalizeText(source.url)
  const captured_at = normalizeText(source.captured_at)
  const notes = dedupeStrings(source.notes ?? [])
  const source_refs = dedupeStrings(source.source_refs ?? [])
  const geo_refs = collectGeoRefs(source, notes, source_refs)
  const external_profiles = matchConversationScopedExternalSourceProfiles({
    sourceId: source.source_id,
    sourceName: title,
    title,
    sourceUrl: url,
    sourceRefs: source_refs,
    notes,
  })
  const entry: PredictionMarketSourceAuditEntry = {
    source_id,
    kind: normalizeText(source.kind) ?? 'other',
    normalized_kind: normalizedKind,
    title,
    url,
    captured_at,
    trust,
    freshness,
    evidence_strength: evidenceStrength,
    score,
    score_bps: Math.round(score * 10_000),
    status,
    notes,
    source_refs,
    geo_refs,
    external_profiles,
    fingerprint: fingerprint('source-entry', {
      source_id,
      normalizedKind,
      title,
      url,
      captured_at,
      trust,
      freshness,
      evidenceStrength,
      notes,
      source_refs,
      geo_refs,
      external_profile_ids: external_profiles.map((profile) => profile.profile_id),
    }),
  }
  return entry
}

export function buildPredictionMarketSourceAudit(input: PredictionMarketSourceAuditInput): PredictionMarketSourceAudit {
  const as_of = normalizeText(input.as_of) ?? new Date().toISOString()
  const primaryKinds = new Set(
    (input.primary_kinds ?? ['official_docs', 'market_data', 'decision_packet']).map((kind) =>
      normalizeSourceKind(kind),
    ),
  )

  const entries = input.sources.map((source) => scoreSource(source)).sort((left, right) => {
    if (right.score !== left.score) {
      return right.score - left.score
    }
    return left.title.localeCompare(right.title)
  })

  const primary_sources = entries.filter(
    (entry) => primaryKinds.has(entry.normalized_kind) || entry.score >= (input.minimum_primary_score ?? 0.75),
  )
  const supporting_sources = entries.filter(
    (entry) => entry.status === 'supporting' && !primary_sources.includes(entry),
  )
  const weak_sources = entries.filter(
    (entry) => entry.status === 'weak' && !primary_sources.includes(entry),
  )
  const source_kind_counts = entries.reduce<Record<string, number>>((accumulator, entry) => {
    accumulator[entry.normalized_kind] = (accumulator[entry.normalized_kind] ?? 0) + 1
    return accumulator
  }, {})
  const average_score = roundNumber(average(entries.map((entry) => entry.score)), 4)
  const coverage_score = roundNumber(
    clampNumber((primary_sources.length * 0.45 + supporting_sources.length * 0.3) / Math.max(entries.length, 1), 0, 1),
    4,
  )
  const missing_url_sources = entries.filter((entry) => !entry.url).map((entry) => entry.source_id)
  const source_refs = dedupeStrings(
    entries.flatMap((entry) => [entry.source_id, ...entry.source_refs, entry.url ?? null]),
  )
  const geo_refs = dedupeStrings(entries.flatMap((entry) => entry.geo_refs))
  const external_profiles = entries.reduce<PredictionMarketExternalSourceProfileSummary[]>((accumulator, entry) => {
    for (const profile of entry.external_profiles) {
      if (!accumulator.some((candidate) => candidate.profile_id === profile.profile_id)) {
        accumulator.push(profile)
      }
    }
    return accumulator
  }, [])
  const external_integration = buildPredictionMarketExternalIntegrationSummary(external_profiles)
  const audit_id = fingerprint('source-audit', {
    market_id: input.market_id,
    as_of,
    entries: entries.map((entry) => entry.fingerprint),
    primaryKinds: Array.from(primaryKinds),
  })
  const summary = compactParts([
    `${entries.length} sources audited`,
    `${primary_sources.length} primary`,
    `${supporting_sources.length} supporting`,
    `${weak_sources.length} weak`,
    `avg=${average_score.toFixed(2)}`,
    external_profiles.length > 0 ? `profiles=${external_profiles.length}` : null,
    geo_refs.length > 0 ? `geo=${geo_refs.length}` : null,
  ])
  const watchlistAudit = buildPredictionMarketWatchlistAudit()

  return {
    audit_id,
    market_id: input.market_id,
    as_of,
    entries,
    primary_sources,
    supporting_sources,
    weak_sources,
    average_score,
    coverage_score,
    missing_url_sources,
    source_kind_counts,
    source_refs,
    geo_refs,
    external_profiles,
    external_integration,
    watchlist_audit: watchlistAudit,
    summary,
  }
}
