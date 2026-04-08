import { createHash } from 'node:crypto'
import {
  evidencePacketSchema,
  predictionMarketResearchAbstentionPolicySchema,
  predictionMarketResearchComparativeReportSchema,
  type EvidencePacket,
  type MarketDescriptor,
  type MarketSnapshot,
  type PredictionMarketVenue,
} from '@/lib/prediction-markets/schemas'

type RawJson = Record<string, unknown>

export type PredictionMarketResearchPipelineVersionMetadata = {
  pipeline_id: string
  pipeline_version: string
  forecaster_bundle_version: string
  calibration_version: string
  abstention_policy_version: string
  stage_versions: {
    base_rate: string
    retrieval: string
    independent_forecasts: string
    calibration: string
    abstention: string
  }
}

export type PredictionMarketResearchTarget = Pick<
  MarketDescriptor,
  'market_id' | 'venue' | 'question' | 'slug'
>

export type PredictionMarketResearchSignalKind = 'worldmonitor' | 'news' | 'alert' | 'manual_note'
export type PredictionMarketResearchSignalStance = 'supportive' | 'contradictory' | 'neutral' | 'unknown'

export type PredictionMarketResearchSignal = {
  signal_id: string
  kind: PredictionMarketResearchSignalKind
  title: string
  summary: string
  source_name?: string
  source_url?: string
  captured_at: string
  tags: string[]
  stance: PredictionMarketResearchSignalStance
  confidence: number | null
  severity: 'low' | 'medium' | 'high' | 'critical' | null
  thesis_probability?: number
  thesis_rationale?: string
  payload?: RawJson
}

export type PredictionMarketExternalReferenceSource = 'metaculus' | 'manifold' | 'external'

export type PredictionMarketExternalReference = {
  reference_id: string
  reference_source: PredictionMarketExternalReferenceSource
  source_name?: string
  source_url?: string
  source_kind: PredictionMarketResearchSignalKind
  signal_id: string
  captured_at: string
  reference_probability_yes: number | null
  market_delta_bps: number | null
  forecast_delta_bps: number | null
  summary: string
}

export type PredictionMarketResearchSignalInput =
  | PredictionMarketResearchSignal
  | {
      signal_id?: string
      id?: string
      kind?: string
      source_kind?: string
      signal_type?: string
      title?: string
      headline?: string
      summary?: string
      message?: string
      note?: string
      body?: string
      source_name?: string
      source?: string
      source_url?: string
      url?: string
      link?: string
      captured_at?: string
      published_at?: string
      occurred_at?: string
      created_at?: string
      timestamp?: string
      tags?: string[]
      stance?: string
      confidence?: number
      severity?: string
      priority?: string
      thesis_probability?: number
      probability_yes?: number
      thesis_rationale?: string
      rationale?: string
      payload?: RawJson
      [key: string]: unknown
    }

export type PredictionMarketResearchRetrievalSummary = {
  signal_ids: string[]
  evidence_ids: string[]
  signal_count: number
  evidence_count: number
  latest_signal_at?: string
  counts_by_kind: Record<PredictionMarketResearchSignalKind, number>
  counts_by_stance: Record<PredictionMarketResearchSignalStance, number>
  supportive_signal_ids: string[]
  contradictory_signal_ids: string[]
  neutral_signal_ids: string[]
  unknown_signal_ids: string[]
  missing_signal_kinds: PredictionMarketResearchSignalKind[]
  health_status: MarketResearchSidecarHealthStatus
  health_issues: string[]
}

export type PredictionMarketResearchAbstentionSummary = {
  recommended: boolean
  reason_codes: string[]
  reasons: string[]
  exogenous_thesis_present: boolean
  manual_thesis_probability_hint?: number
}

export type PredictionMarketResearchAbstentionPolicy = {
  policy_id: string
  policy_version: string
  recommended: boolean
  blocks_forecast: boolean
  manual_review_required: boolean
  trigger_codes: string[]
  rationale: string
  thresholds: {
    minimum_signal_count: number
    minimum_supportive_margin_bps: number
    minimum_manual_thesis_probability: number
    minimum_contributor_coverage: number
  }
}

export type PredictionMarketResearchForecasterCandidateKind =
  | 'market_base_rate'
  | 'manual_thesis'
  | 'external_reference'

export type PredictionMarketResearchForecasterCandidateRole = 'baseline' | 'candidate' | 'comparator'

export type PredictionMarketResearchForecasterCandidateStatus = 'ready' | 'partial'

export type PredictionMarketResearchForecasterCandidate = {
  forecaster_id: string
  forecaster_kind: PredictionMarketResearchForecasterCandidateKind
  role: PredictionMarketResearchForecasterCandidateRole
  status: PredictionMarketResearchForecasterCandidateStatus
  label: string
  probability_yes: number | null
  rationale: string
  input_signal_ids: string[]
  source_name?: string
  source_url?: string
}

export type PredictionMarketResearchIndependentForecasterOutput = PredictionMarketResearchForecasterCandidate & {
  pipeline_version: string
  calibration_version: string
  abstention_policy_version: string
  raw_weight: number
  normalized_weight: number
  calibrated_probability_yes: number | null
  calibration_shift_bps: number | null
}

export type PredictionMarketResearchWeightedAggregateContributor = {
  forecaster_id: string
  forecaster_kind: PredictionMarketResearchForecasterCandidateKind
  role: PredictionMarketResearchForecasterCandidateRole
  label: string
  raw_weight: number
  normalized_weight: number
  probability_yes: number | null
  calibrated_probability_yes: number | null
  contribution_bps: number | null
}

export type PredictionMarketResearchWeightedAggregatePreview = {
  pipeline_version: string
  calibration_version: string
  abstention_policy_version: string
  contributor_count: number
  usable_contributor_count: number
  coverage: number
  raw_weight_total: number
  normalized_weight_total: number
  base_rate_probability_yes: number
  weighted_probability_yes: number | null
  weighted_probability_yes_raw: number | null
  weighted_delta_bps: number | null
  weighted_raw_delta_bps: number | null
  spread_bps: number | null
  contributors: PredictionMarketResearchWeightedAggregateContributor[]
  rationale: string
  abstention_recommended: boolean
}

export type PredictionMarketResearchComparativeSummary = {
  probability_yes: number | null
  delta_bps_vs_market_only: number | null
  rationale: string
}

export type PredictionMarketResearchForecastComparativeSummary = {
  forecast_probability_yes: number | null
  delta_bps_vs_market_only: number | null
  delta_bps_vs_aggregate: number | null
  rationale: string
}

export type PredictionMarketResearchAbstentionComparativeSummary = {
  recommended: boolean
  blocks_forecast: boolean
  reason_codes: string[]
  rationale: string
}

export type PredictionMarketResearchComparativeReport = {
  market_only: PredictionMarketResearchComparativeSummary
  aggregate: PredictionMarketResearchComparativeSummary & {
    coverage: number
    contributor_count: number
    usable_contributor_count: number
  }
  forecast: PredictionMarketResearchForecastComparativeSummary
  abstention: PredictionMarketResearchAbstentionComparativeSummary
  summary: string
}

export type PredictionMarketResearchCalibrationSnapshot = {
  snapshot_id: string
  snapshot_version: string
  pipeline_version: string
  calibration_version: string
  abstention_policy_version: string
  sample_size: number
  usable_contributor_count: number
  base_rate_probability_yes: number
  weighted_probability_yes: number | null
  weighted_probability_yes_raw: number | null
  calibration_gap_bps: number | null
  mean_abs_shift_bps: number | null
  sharpness: number
  coverage: number
  notes: string[]
}

export type MarketResearchSynthesis = {
  market_id: string
  venue: PredictionMarketVenue
  question: string
  generated_at: string
  pipeline_version_metadata: PredictionMarketResearchPipelineVersionMetadata
  signal_count: number
  evidence_count: number
  signal_kinds: PredictionMarketResearchSignalKind[]
  counts_by_kind: Record<PredictionMarketResearchSignalKind, number>
  counts_by_stance: Record<PredictionMarketResearchSignalStance, number>
  top_tags: string[]
  latest_signal_at?: string
  retrieval_summary: PredictionMarketResearchRetrievalSummary
  manual_thesis_probability_hint?: number
  manual_thesis_rationale_hint?: string
  base_rate_probability_hint: number
  base_rate_rationale_hint: string
  base_rate_source: PredictionMarketBaseRateResearch['base_rate_source']
  abstention_summary: PredictionMarketResearchAbstentionSummary
  key_factors: string[]
  counterarguments: string[]
  no_trade_hints: string[]
  abstention_recommended: boolean
  summary: string
  key_points: string[]
  evidence_refs: string[]
  external_reference_count: number
  external_references: PredictionMarketExternalReference[]
  market_probability_yes_hint: number
  forecast_probability_yes_hint: number | null
  market_delta_bps: number | null
  forecast_delta_bps: number | null
  forecaster_candidates: PredictionMarketResearchForecasterCandidate[]
  independent_forecaster_outputs: PredictionMarketResearchIndependentForecasterOutput[]
  weighted_aggregate_preview: PredictionMarketResearchWeightedAggregatePreview
  comparative_report: PredictionMarketResearchComparativeReport
  calibration_snapshot: PredictionMarketResearchCalibrationSnapshot
  abstention_policy: PredictionMarketResearchAbstentionPolicy
  health?: MarketResearchSidecarHealth
}

export type MarketResearchSidecarHealthStatus = 'healthy' | 'degraded' | 'blocked'

export type MarketResearchSidecarHealth = {
  status: MarketResearchSidecarHealthStatus
  completeness_score: number
  duplicate_signal_count: number
  issues: string[]
  source_kinds: PredictionMarketResearchSignalKind[]
}

export type MarketResearchSidecar = {
  market_id: string
  venue: PredictionMarketVenue
  generated_at: string
  pipeline_version_metadata: PredictionMarketResearchPipelineVersionMetadata
  signals: PredictionMarketResearchSignal[]
  evidence_packets: EvidencePacket[]
  health: MarketResearchSidecarHealth
  synthesis: MarketResearchSynthesis
}

export type PredictionMarketBaseRateResearch = {
  market_id: string
  venue: PredictionMarketVenue
  generated_at: string
  pipeline_version_metadata: PredictionMarketResearchPipelineVersionMetadata
  base_rate_probability_hint: number
  base_rate_source: 'market_midpoint' | 'yes_price' | 'fallback_50'
  base_rate_rationale_hint: string
  retrieval_summary: PredictionMarketResearchRetrievalSummary
  abstention_summary: PredictionMarketResearchAbstentionSummary
  abstention_policy: PredictionMarketResearchAbstentionPolicy
  key_factors: string[]
  counterarguments: string[]
  no_trade_hints: string[]
  abstention_recommended: boolean
  confidence: number
}

const RESEARCH_PIPELINE_VERSION_METADATA: PredictionMarketResearchPipelineVersionMetadata = {
  pipeline_id: 'polymarket-research-pipeline',
  pipeline_version: 'poly-025-research-v1',
  forecaster_bundle_version: 'independent-forecasters-v1',
  calibration_version: 'calibration-shrinkage-v1',
  abstention_policy_version: 'structured-abstention-v1',
  stage_versions: {
    base_rate: 'base-rate-v1',
    retrieval: 'retrieval-v1',
    independent_forecasts: 'independent-forecasts-v1',
    calibration: 'calibration-shrinkage-v1',
    abstention: 'structured-abstention-v1',
  },
}

const RESEARCH_ABSTENTION_POLICY_ID = 'structured-abstention'

function nowIso(): string {
  return new Date().toISOString()
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : undefined
}

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function readValue(input: PredictionMarketResearchSignalInput, key: string): unknown {
  return (input as Record<string, unknown>)[key]
}

function normalizeResearchKind(value: unknown): PredictionMarketResearchSignalKind {
  const normalized = asString(value)?.toLowerCase()
  switch (normalized) {
    case 'worldmonitor':
    case 'world_monitor':
      return 'worldmonitor'
    case 'twitter':
    case 'twitter_watcher':
    case 'tweet':
    case 'x':
    case 'alert':
    case 'alerts':
      return 'alert'
    case 'manual':
    case 'manual_note':
    case 'note':
      return 'manual_note'
    case 'news':
    default:
      return 'news'
  }
}

function inferResearchKind(input: PredictionMarketResearchSignalInput): PredictionMarketResearchSignalKind {
  const sourceHints = [
    asString(readValue(input, 'source_name')),
    asString(readValue(input, 'source')),
    asString(readValue(input, 'source_url')),
    asString(readValue(input, 'url')),
    asString(readValue(input, 'link')),
  ]
    .filter((value): value is string => Boolean(value))
    .join(' ')
    .toLowerCase()

  if (sourceHints.includes('worldmonitor') || sourceHints.includes('world_monitor')) {
    return 'worldmonitor'
  }

  if (
    sourceHints.includes('twitter') ||
    sourceHints.includes('x.com') ||
    sourceHints.includes('tweet') ||
    sourceHints.includes('/status/')
  ) {
    return 'alert'
  }

  return normalizeResearchKind(
    readValue(input, 'kind') ?? readValue(input, 'source_kind') ?? readValue(input, 'signal_type'),
  )
}

function normalizeStance(value: unknown): PredictionMarketResearchSignalStance {
  const normalized = asString(value)?.toLowerCase()
  switch (normalized) {
    case 'supportive':
    case 'supports':
    case 'bullish':
    case 'yes':
      return 'supportive'
    case 'contradictory':
    case 'contradicts':
    case 'bearish':
    case 'no':
      return 'contradictory'
    case 'neutral':
    case 'mixed':
      return 'neutral'
    default:
      return 'unknown'
  }
}

function normalizeSeverity(value: unknown): PredictionMarketResearchSignal['severity'] {
  const normalized = asString(value)?.toLowerCase()
  switch (normalized) {
    case 'low':
    case 'medium':
    case 'high':
    case 'critical':
      return normalized
    case 'urgent':
      return 'high'
    default:
      return null
  }
}

function normalizeTags(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return [...new Set(
    value
      .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      .map((item) => item.trim().toLowerCase()),
  )]
}

function isIsoTimestamp(value: string | undefined): value is string {
  if (!value) return false
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp)
}

function normalizeCapturedAt(input: PredictionMarketResearchSignalInput): string {
  const candidates = [
    asString(readValue(input, 'captured_at')),
    asString(readValue(input, 'published_at')),
    asString(readValue(input, 'occurred_at')),
    asString(readValue(input, 'created_at')),
    asString(readValue(input, 'timestamp')),
  ]

  const firstValid = candidates.find((value) => isIsoTimestamp(value))
  return firstValid || nowIso()
}

function maybeUrl(value: unknown): string | undefined {
  const raw = asString(value)
  if (!raw) return undefined

  try {
    return new URL(raw).toString()
  } catch {
    return undefined
  }
}

function stableSerialize(value: unknown): string {
  if (value == null || typeof value !== 'object') {
    return JSON.stringify(value)
  }

  if (Array.isArray(value)) {
    return `[${value.map((item) => stableSerialize(item)).join(',')}]`
  }

  const entries = Object.entries(value as RawJson)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, item]) => `${JSON.stringify(key)}:${stableSerialize(item)}`)

  return `{${entries.join(',')}}`
}

function hashText(value: string): string {
  return createHash('sha256').update(value).digest('hex')
}

function buildSignalId(input: PredictionMarketResearchSignalInput, kind: PredictionMarketResearchSignalKind): string {
  const explicitId = asString(readValue(input, 'signal_id'))
    || asString(readValue(input, 'id'))
  if (explicitId) return explicitId

  const fingerprint = stableSerialize({
    kind,
    title: asString(readValue(input, 'title'))
      || asString(readValue(input, 'headline')),
    summary: asString(readValue(input, 'summary'))
      || asString(readValue(input, 'message'))
      || asString(readValue(input, 'note'))
      || asString(readValue(input, 'body')),
    source_url: maybeUrl(readValue(input, 'source_url'))
      || maybeUrl(readValue(input, 'url'))
      || maybeUrl(readValue(input, 'link')),
    captured_at: normalizeCapturedAt(input),
  })

  return `${kind}:${hashText(fingerprint).slice(0, 16)}`
}

function normalizePayload(input: PredictionMarketResearchSignalInput): RawJson | undefined {
  const explicitPayload = readValue(input, 'payload')
  if (explicitPayload && typeof explicitPayload === 'object' && !Array.isArray(explicitPayload)) {
    return explicitPayload as RawJson
  }

  const raw = { ...(input as Record<string, unknown>) }
  delete raw.signal_id
  delete raw.id
  delete raw.kind
  delete raw.source_kind
  delete raw.signal_type
  delete raw.title
  delete raw.headline
  delete raw.summary
  delete raw.message
  delete raw.note
  delete raw.body
  delete raw.source_name
  delete raw.source
  delete raw.source_url
  delete raw.url
  delete raw.link
  delete raw.captured_at
  delete raw.published_at
  delete raw.occurred_at
  delete raw.created_at
  delete raw.timestamp
  delete raw.tags
  delete raw.stance
  delete raw.confidence
  delete raw.severity
  delete raw.priority
  delete raw.thesis_probability
  delete raw.probability_yes
  delete raw.thesis_rationale
  delete raw.rationale
  delete raw.payload

  const entries = Object.entries(raw).filter(([, value]) => value !== undefined)
  return entries.length > 0 ? Object.fromEntries(entries) : undefined
}

function summarizeText(input: PredictionMarketResearchSignalInput): string {
  return asString(readValue(input, 'summary'))
    || asString(readValue(input, 'message'))
    || asString(readValue(input, 'note'))
    || asString(readValue(input, 'body'))
    || 'External research signal captured for this market.'
}

function titleText(input: PredictionMarketResearchSignalInput): string {
  return asString(readValue(input, 'title'))
    || asString(readValue(input, 'headline'))
    || 'External research signal'
}

function normalizeConfidence(value: unknown): number | null {
  const parsed = asNumber(value)
  if (parsed == null) return null
  return Number(clamp(parsed, 0, 1).toFixed(4))
}

function normalizeReferenceSource(signal: PredictionMarketResearchSignal): PredictionMarketExternalReferenceSource | null {
  const sourceText = [
    signal.source_name,
    signal.source_url,
    signal.payload?.source_name as string | undefined,
    signal.payload?.source as string | undefined,
    signal.payload?.reference_source as string | undefined,
  ]
    .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    .join(' ')
    .toLowerCase()

  if (sourceText.includes('metaculus')) return 'metaculus'
  if (sourceText.includes('manifold')) return 'manifold'
  return null
}

function extractReferenceProbability(signal: PredictionMarketResearchSignal): number | null {
  const payload = signal.payload ?? {}
  const candidates = [
    signal.thesis_probability,
    payload.probability_yes,
    payload.forecast_probability_yes,
    payload.market_probability_yes,
    payload.probability,
    payload.chance,
    payload.estimate,
  ]

  for (const candidate of candidates) {
    const parsed = asNumber(candidate)
    if (parsed != null && parsed >= 0 && parsed <= 1) {
      return Number(parsed.toFixed(6))
    }
  }

  return null
}

function buildExternalReferences(input: {
  signals: PredictionMarketResearchSignal[]
  marketProbabilityYesHint: number
  forecastProbabilityYesHint: number | null
}): PredictionMarketExternalReference[] {
  const references: PredictionMarketExternalReference[] = []

  for (const signal of input.signals) {
    const referenceSource = normalizeReferenceSource(signal)
    if (referenceSource == null) continue

    const referenceProbabilityYes = extractReferenceProbability(signal)
    references.push({
      reference_id: signal.signal_id,
      reference_source: referenceSource,
      source_name: signal.source_name,
      source_url: signal.source_url,
      source_kind: signal.kind,
      signal_id: signal.signal_id,
      captured_at: signal.captured_at,
      reference_probability_yes: referenceProbabilityYes,
      market_delta_bps: referenceProbabilityYes == null
        ? null
        : Number(((referenceProbabilityYes - input.marketProbabilityYesHint) * 10_000).toFixed(2)),
      forecast_delta_bps: referenceProbabilityYes == null || input.forecastProbabilityYesHint == null
        ? null
        : Number(((referenceProbabilityYes - input.forecastProbabilityYesHint) * 10_000).toFixed(2)),
      summary: signal.summary,
    })
  }

  return references
}

function averageNullable(values: Array<number | null>): number | null {
  const filtered = values.filter((value): value is number => value != null)
  if (filtered.length === 0) return null
  return Number((filtered.reduce((sum, value) => sum + value, 0) / filtered.length).toFixed(2))
}

function formatProbabilityPercent(value: number | null): string {
  if (value == null) return 'n/a'
  return `${Math.round(value * 1000) / 10}%`
}

function formatBps(value: number | null): string {
  if (value == null) return 'n/a'
  const rounded = Math.round(value)
  return `${rounded >= 0 ? '+' : ''}${rounded} bps`
}

export function buildResearchPipelineVersionMetadata(): PredictionMarketResearchPipelineVersionMetadata {
  return {
    ...RESEARCH_PIPELINE_VERSION_METADATA,
    stage_versions: {
      ...RESEARCH_PIPELINE_VERSION_METADATA.stage_versions,
    },
  }
}

function probabilityToBps(value: number | null, baseline: number): number | null {
  if (value == null) return null
  return Number(((value - baseline) * 10_000).toFixed(2))
}

function calibrateProbability(input: {
  probability_yes: number
  forecaster_kind: PredictionMarketResearchForecasterCandidateKind
  status: PredictionMarketResearchForecasterCandidateStatus
  base_rate_probability_yes: number
}): number {
  const anchor = input.forecaster_kind === 'market_base_rate'
    ? input.base_rate_probability_yes
    : 0.5
  const shrink = input.status === 'partial' ? 0.85 : 1
  const calibrated = anchor + ((input.probability_yes - anchor) * shrink)
  return Number(clamp(calibrated, 0, 1).toFixed(4))
}

function weightForForecasterCandidate(input: {
  candidate: PredictionMarketResearchForecasterCandidate
  externalReferenceCount: number
  baseRateSource: PredictionMarketBaseRateResearch['base_rate_source']
}): number {
  switch (input.candidate.forecaster_kind) {
    case 'market_base_rate':
      return input.baseRateSource === 'fallback_50' ? 0.4 : 0.45
    case 'manual_thesis':
      return 0.35
    case 'external_reference':
      return input.externalReferenceCount > 0 ? 0.25 / input.externalReferenceCount : 0.25
  }
}

export function buildIndependentForecasterOutputs(input: {
  baseRateResearch: PredictionMarketBaseRateResearch
  forecasterCandidates: PredictionMarketResearchForecasterCandidate[]
  externalReferenceCount: number
}): PredictionMarketResearchIndependentForecasterOutput[] {
  const rawOutputs = input.forecasterCandidates.map((candidate) => {
    const probabilityYes = candidate.probability_yes
    const rawWeight = probabilityYes == null
      ? 0
      : weightForForecasterCandidate({
          candidate,
          externalReferenceCount: input.externalReferenceCount,
          baseRateSource: input.baseRateResearch.base_rate_source,
        })
    const calibratedProbabilityYes = probabilityYes == null
      ? null
      : calibrateProbability({
          probability_yes: probabilityYes,
          forecaster_kind: candidate.forecaster_kind,
          status: candidate.status,
          base_rate_probability_yes: input.baseRateResearch.base_rate_probability_hint,
        })

    return {
      ...candidate,
      pipeline_version: input.baseRateResearch.pipeline_version_metadata.pipeline_version,
      calibration_version: input.baseRateResearch.pipeline_version_metadata.calibration_version,
      abstention_policy_version: input.baseRateResearch.pipeline_version_metadata.abstention_policy_version,
      raw_weight: Number(rawWeight.toFixed(4)),
      normalized_weight: 0,
      calibrated_probability_yes: calibratedProbabilityYes,
      calibration_shift_bps: probabilityYes == null
        ? null
        : probabilityToBps(calibratedProbabilityYes, probabilityYes),
    }
  })

  const usableRawWeightTotal = rawOutputs.reduce((sum, output) => {
    return sum + (output.probability_yes == null ? 0 : output.raw_weight)
  }, 0)

  return rawOutputs.map((output) => ({
    ...output,
    normalized_weight: output.probability_yes == null || usableRawWeightTotal === 0
      ? 0
      : Number((output.raw_weight / usableRawWeightTotal).toFixed(4)),
  }))
}

export function buildWeightedAggregatePreview(input: {
  baseRateResearch: PredictionMarketBaseRateResearch
  independentForecasterOutputs: PredictionMarketResearchIndependentForecasterOutput[]
}): PredictionMarketResearchWeightedAggregatePreview {
  const usableOutputs = input.independentForecasterOutputs.filter(
    (output) => output.probability_yes != null && output.calibrated_probability_yes != null,
  )

  const rawWeightTotal = Number(
    input.independentForecasterOutputs
      .reduce((sum, output) => sum + output.raw_weight, 0)
      .toFixed(4),
  )
  const normalizedWeightTotal = Number(
    input.independentForecasterOutputs
      .reduce((sum, output) => sum + output.normalized_weight, 0)
      .toFixed(4),
  )
  const weightedProbabilityYes = usableOutputs.length === 0
    ? null
    : Number((
        usableOutputs.reduce((sum, output) => sum + (output.calibrated_probability_yes ?? 0) * output.normalized_weight, 0)
      ).toFixed(4))
  const weightedProbabilityYesRaw = usableOutputs.length === 0
    ? null
    : Number((
        usableOutputs.reduce((sum, output) => sum + (output.probability_yes ?? 0) * output.normalized_weight, 0)
      ).toFixed(4))
  const calibratedValues = usableOutputs
    .map((output) => output.calibrated_probability_yes)
    .filter((value): value is number => value != null)
  const rawValues = usableOutputs
    .map((output) => output.probability_yes)
    .filter((value): value is number => value != null)
  const coverage = input.independentForecasterOutputs.length === 0
    ? 0
    : Number((usableOutputs.length / input.independentForecasterOutputs.length).toFixed(4))

  const calibratedSpread = calibratedValues.length > 0
    ? Math.max(...calibratedValues) - Math.min(...calibratedValues)
    : null
  const rawSpread = rawValues.length > 0
    ? Math.max(...rawValues) - Math.min(...rawValues)
    : null

  const contributors = input.independentForecasterOutputs.map((output) => ({
    forecaster_id: output.forecaster_id,
    forecaster_kind: output.forecaster_kind,
    role: output.role,
    label: output.label,
    raw_weight: output.raw_weight,
    normalized_weight: output.normalized_weight,
    probability_yes: output.probability_yes,
    calibrated_probability_yes: output.calibrated_probability_yes,
    contribution_bps: probabilityToBps(output.calibrated_probability_yes, input.baseRateResearch.base_rate_probability_hint),
  }))

  return {
    pipeline_version: input.baseRateResearch.pipeline_version_metadata.pipeline_version,
    calibration_version: input.baseRateResearch.pipeline_version_metadata.calibration_version,
    abstention_policy_version: input.baseRateResearch.pipeline_version_metadata.abstention_policy_version,
    contributor_count: input.independentForecasterOutputs.length,
    usable_contributor_count: usableOutputs.length,
    coverage,
    raw_weight_total: rawWeightTotal,
    normalized_weight_total: normalizedWeightTotal,
    base_rate_probability_yes: input.baseRateResearch.base_rate_probability_hint,
    weighted_probability_yes: weightedProbabilityYes,
    weighted_probability_yes_raw: weightedProbabilityYesRaw,
    weighted_delta_bps: probabilityToBps(weightedProbabilityYes, input.baseRateResearch.base_rate_probability_hint),
    weighted_raw_delta_bps: probabilityToBps(weightedProbabilityYesRaw, input.baseRateResearch.base_rate_probability_hint),
    spread_bps: calibratedSpread == null
      ? rawSpread == null ? null : Number((rawSpread * 10_000).toFixed(2))
      : Number((calibratedSpread * 10_000).toFixed(2)),
    contributors,
    rationale: usableOutputs.length === 0
      ? 'No independent forecaster outputs were usable for aggregation.'
      : `Weighted aggregate blends ${usableOutputs.length} calibrated forecaster output${usableOutputs.length === 1 ? '' : 's'} against the ${input.baseRateResearch.base_rate_source} base rate.`,
    abstention_recommended: input.baseRateResearch.abstention_recommended,
  }
}

export function buildCalibrationSnapshot(input: {
  baseRateResearch: PredictionMarketBaseRateResearch
  weightedAggregatePreview: PredictionMarketResearchWeightedAggregatePreview
  independentForecasterOutputs: PredictionMarketResearchIndependentForecasterOutput[]
}): PredictionMarketResearchCalibrationSnapshot {
  const usableOutputs = input.independentForecasterOutputs.filter((output) => output.calibrated_probability_yes != null)
  const meanAbsShiftBps = averageNullable(
    usableOutputs.map((output) => Math.abs(output.calibration_shift_bps ?? 0)),
  )
  const calibrationGapBps = probabilityToBps(
    input.weightedAggregatePreview.weighted_probability_yes,
    input.weightedAggregatePreview.base_rate_probability_yes,
  )
  const coverage = input.independentForecasterOutputs.length === 0
    ? 0
    : Number((usableOutputs.length / input.independentForecasterOutputs.length).toFixed(4))
  const spreadBps = input.weightedAggregatePreview.spread_bps
  const sharpness = spreadBps == null
    ? 0
    : Number(clamp(1 - (spreadBps / 10_000), 0, 1).toFixed(4))

  return {
    snapshot_id: hashText(stableSerialize({
      pipeline_version: input.baseRateResearch.pipeline_version_metadata.pipeline_version,
      calibration_version: input.baseRateResearch.pipeline_version_metadata.calibration_version,
      base_rate_probability_yes: input.baseRateResearch.base_rate_probability_hint,
      weighted_probability_yes: input.weightedAggregatePreview.weighted_probability_yes,
      weighted_probability_yes_raw: input.weightedAggregatePreview.weighted_probability_yes_raw,
      contributor_count: input.independentForecasterOutputs.length,
      usable_contributor_count: usableOutputs.length,
    })).slice(0, 16),
    snapshot_version: input.baseRateResearch.pipeline_version_metadata.calibration_version,
    pipeline_version: input.baseRateResearch.pipeline_version_metadata.pipeline_version,
    calibration_version: input.baseRateResearch.pipeline_version_metadata.calibration_version,
    abstention_policy_version: input.baseRateResearch.pipeline_version_metadata.abstention_policy_version,
    sample_size: input.independentForecasterOutputs.length,
    usable_contributor_count: usableOutputs.length,
    base_rate_probability_yes: input.baseRateResearch.base_rate_probability_hint,
    weighted_probability_yes: input.weightedAggregatePreview.weighted_probability_yes,
    weighted_probability_yes_raw: input.weightedAggregatePreview.weighted_probability_yes_raw,
    calibration_gap_bps: calibrationGapBps,
    mean_abs_shift_bps: meanAbsShiftBps,
    sharpness,
    coverage,
    notes: [
      `Pipeline version ${input.baseRateResearch.pipeline_version_metadata.pipeline_version}.`,
      `Calibration version ${input.baseRateResearch.pipeline_version_metadata.calibration_version}.`,
      `Coverage ${Math.round(coverage * 1000) / 10}%.`,
    ],
  }
}

function buildComparativeReport(input: {
  marketOnlyProbabilityYes: number
  baseRateSource: PredictionMarketBaseRateResearch['base_rate_source']
  weightedAggregatePreview: PredictionMarketResearchWeightedAggregatePreview
  abstentionPolicy: PredictionMarketResearchAbstentionPolicy
  forecastProbabilityYes: number | null
}): PredictionMarketResearchComparativeReport {
  const marketOnlyProbabilityYes = input.marketOnlyProbabilityYes
  const aggregateProbabilityYes = input.weightedAggregatePreview.weighted_probability_yes
  const forecastProbabilityYes = input.forecastProbabilityYes
  const aggregateDeltaBps = probabilityToBps(aggregateProbabilityYes, marketOnlyProbabilityYes)
  const forecastDeltaBpsVsMarketOnly = probabilityToBps(forecastProbabilityYes, marketOnlyProbabilityYes)
  const forecastDeltaBpsVsAggregate = aggregateProbabilityYes == null
    ? null
    : probabilityToBps(forecastProbabilityYes, aggregateProbabilityYes)
  const aggregateContributionCount = input.weightedAggregatePreview.contributor_count
  const preferredMode: 'market_only' | 'aggregate' | 'abstention' = input.abstentionPolicy.blocks_forecast
    ? 'abstention'
    : aggregateProbabilityYes != null &&
        input.weightedAggregatePreview.coverage >= input.abstentionPolicy.thresholds.minimum_contributor_coverage &&
        aggregateDeltaBps != null &&
        Math.abs(aggregateDeltaBps) >= input.abstentionPolicy.thresholds.minimum_supportive_margin_bps
      ? 'aggregate'
      : 'market_only'

  return predictionMarketResearchComparativeReportSchema.parse({
    market_only: {
      probability_yes: marketOnlyProbabilityYes,
      delta_bps_vs_market_only: 0,
      rationale: `Market-only baseline anchored at ${formatProbabilityPercent(marketOnlyProbabilityYes)} from ${input.baseRateSource}.`,
    },
    aggregate: {
      probability_yes: aggregateProbabilityYes,
      delta_bps_vs_market_only: aggregateDeltaBps,
      coverage: input.weightedAggregatePreview.coverage,
      contributor_count: aggregateContributionCount,
      usable_contributor_count: input.weightedAggregatePreview.usable_contributor_count,
      rationale: input.weightedAggregatePreview.rationale,
    },
    forecast: {
      forecast_probability_yes: forecastProbabilityYes,
      delta_bps_vs_market_only: forecastDeltaBpsVsMarketOnly,
      delta_bps_vs_aggregate: forecastDeltaBpsVsAggregate,
      rationale: forecastProbabilityYes == null
        ? 'No forecast probability hint was supplied, so the forecast lane remains unscored.'
        : `Forecast hint sits at ${formatProbabilityPercent(forecastProbabilityYes)} and can be compared directly against market-only and aggregate baselines.`,
    },
    abstention: {
      recommended: input.abstentionPolicy.recommended,
      blocks_forecast: input.abstentionPolicy.blocks_forecast,
      reason_codes: input.abstentionPolicy.trigger_codes,
      rationale: input.abstentionPolicy.rationale,
    },
    summary: `Market-only ${formatProbabilityPercent(marketOnlyProbabilityYes)}, aggregate ${formatProbabilityPercent(aggregateProbabilityYes)} (${formatBps(aggregateDeltaBps)} vs market-only), forecast ${formatProbabilityPercent(forecastProbabilityYes)} (${formatBps(forecastDeltaBpsVsMarketOnly)} vs market-only, ${formatBps(forecastDeltaBpsVsAggregate)} vs aggregate), abstention ${input.abstentionPolicy.recommended ? 'recommended' : 'not recommended'}${input.abstentionPolicy.blocks_forecast ? ' and blocks forecast' : ''}. Preferred mode: ${preferredMode}.`,
  }) as PredictionMarketResearchComparativeReport
}

export function buildAbstentionPolicy(input: {
  abstentionSummary: PredictionMarketResearchAbstentionSummary
  health: MarketResearchSidecarHealth
  weightedAggregatePreview?: PredictionMarketResearchWeightedAggregatePreview
  pipelineVersionMetadata?: PredictionMarketResearchPipelineVersionMetadata
}): PredictionMarketResearchAbstentionPolicy {
  const triggerCodes = new Set(input.abstentionSummary.reason_codes)

  if (input.weightedAggregatePreview?.weighted_delta_bps != null && Math.abs(input.weightedAggregatePreview.weighted_delta_bps) < 150) {
    triggerCodes.add('low_weighted_edge')
  }

  if (input.weightedAggregatePreview?.coverage != null && input.weightedAggregatePreview.coverage < 0.5) {
    triggerCodes.add('low_forecaster_coverage')
  }

  if (input.health.status === 'blocked') {
    triggerCodes.add('research_health_blocked')
  }

  return predictionMarketResearchAbstentionPolicySchema.parse({
    policy_id: RESEARCH_ABSTENTION_POLICY_ID,
    policy_version: input.pipelineVersionMetadata?.abstention_policy_version
      ?? RESEARCH_PIPELINE_VERSION_METADATA.abstention_policy_version,
    recommended: input.abstentionSummary.recommended,
    blocks_forecast:
      input.abstentionSummary.recommended ||
      input.health.status === 'blocked' ||
      (input.weightedAggregatePreview?.weighted_probability_yes == null),
    manual_review_required:
      input.abstentionSummary.recommended ||
      input.health.status !== 'healthy',
    trigger_codes: [...triggerCodes],
    rationale: input.abstentionSummary.reasons.join(' ') || 'Structured abstention policy inherited from the base-rate summary.',
    thresholds: {
      minimum_signal_count: 1,
      minimum_supportive_margin_bps: 150,
      minimum_manual_thesis_probability: 0.55,
      minimum_contributor_coverage: 0.5,
    },
  }) as PredictionMarketResearchAbstentionPolicy
}

export function normalizeResearchSignal(input: PredictionMarketResearchSignalInput): PredictionMarketResearchSignal {
  const kind = inferResearchKind(input)
  const thesisProbability = normalizeConfidence(
    readValue(input, 'thesis_probability') ?? readValue(input, 'probability_yes'),
  )

  return {
    signal_id: buildSignalId(input, kind),
    kind,
    title: titleText(input),
    summary: summarizeText(input),
    source_name: asString(readValue(input, 'source_name') ?? readValue(input, 'source')),
    source_url: maybeUrl(readValue(input, 'source_url') ?? readValue(input, 'url') ?? readValue(input, 'link')),
    captured_at: normalizeCapturedAt(input),
    tags: normalizeTags(readValue(input, 'tags')),
    stance: normalizeStance(readValue(input, 'stance')),
    confidence: normalizeConfidence(readValue(input, 'confidence')),
    severity: normalizeSeverity(readValue(input, 'severity') ?? readValue(input, 'priority')),
    thesis_probability: kind === 'manual_note' ? thesisProbability ?? undefined : undefined,
    thesis_rationale: kind === 'manual_note'
      ? asString(readValue(input, 'thesis_rationale') ?? readValue(input, 'rationale'))
      : undefined,
    payload: normalizePayload(input),
  }
}

function buildEvidenceId(marketId: string, signalId: string): string {
  const normalized = signalId.toLowerCase().replace(/[^a-z0-9:_-]+/g, '-')
  return `${marketId}:research:${normalized}`
}

function buildEvidenceType(signal: PredictionMarketResearchSignal): EvidencePacket['type'] {
  return signal.kind === 'manual_note' && signal.thesis_probability != null ? 'manual_thesis' : 'system_note'
}

function buildEvidenceSummary(signal: PredictionMarketResearchSignal): string {
  if (signal.kind === 'manual_note' && signal.thesis_probability != null) {
    return signal.thesis_rationale
      || `${signal.title}. Manual thesis probability set to ${signal.thesis_probability}.`
  }

  const prefix = `[${signal.kind}]`
  return `${prefix} ${signal.summary}`
}

function buildEvidenceTitle(signal: PredictionMarketResearchSignal): string {
  switch (signal.kind) {
    case 'worldmonitor':
      return `World monitor: ${signal.title}`
    case 'alert':
      return `Alert: ${signal.title}`
    case 'manual_note':
      return `Manual note: ${signal.title}`
    case 'news':
    default:
      return `Research note: ${signal.title}`
  }
}

export function buildResearchEvidencePacket(input: {
  market: PredictionMarketResearchTarget
  signal: PredictionMarketResearchSignalInput
}): EvidencePacket {
  const signal = normalizeResearchSignal(input.signal)
  const metadata = {
    research_kind: signal.kind,
    source_name: signal.source_name,
    tags: signal.tags,
    stance: signal.stance,
    confidence: signal.confidence,
    severity: signal.severity,
    thesis_probability: signal.thesis_probability,
    thesis_rationale: signal.thesis_rationale,
    payload: signal.payload,
  }

  return evidencePacketSchema.parse({
    evidence_id: buildEvidenceId(input.market.market_id, signal.signal_id),
    market_id: input.market.market_id,
    venue: input.market.venue,
    type: buildEvidenceType(signal),
    title: buildEvidenceTitle(signal),
    summary: buildEvidenceSummary(signal),
    source_url: signal.source_url,
    captured_at: signal.captured_at,
    content_hash: hashText(stableSerialize({
      market_id: input.market.market_id,
      venue: input.market.venue,
      signal,
    })),
    metadata,
  })
}

export function buildResearchEvidencePackets(input: {
  market: PredictionMarketResearchTarget
  signals: PredictionMarketResearchSignalInput[]
}): EvidencePacket[] {
  return input.signals.map((signal) => buildResearchEvidencePacket({
    market: input.market,
    signal,
  }))
}

function sortSignals(signals: PredictionMarketResearchSignal[]): PredictionMarketResearchSignal[] {
  return [...signals].sort((left, right) => {
    const delta = Date.parse(right.captured_at) - Date.parse(left.captured_at)
    if (delta !== 0) return delta
    return left.signal_id.localeCompare(right.signal_id)
  })
}

function dedupeSignals(signals: PredictionMarketResearchSignal[]): {
  signals: PredictionMarketResearchSignal[]
  duplicateSignalCount: number
} {
  const byId = new Map<string, PredictionMarketResearchSignal>()
  let duplicateSignalCount = 0

  for (const signal of signals) {
    if (byId.has(signal.signal_id)) {
      duplicateSignalCount += 1
      continue
    }
    byId.set(signal.signal_id, signal)
  }

  return {
    signals: [...byId.values()],
    duplicateSignalCount,
  }
}

function buildSidecarHealth(input: {
  signals: PredictionMarketResearchSignal[]
  duplicateSignalCount: number
}): MarketResearchSidecarHealth {
  const issues: string[] = []
  let completenessScore = 1

  if (input.signals.length === 0) {
    return {
      status: 'blocked',
      completeness_score: 0,
      duplicate_signal_count: input.duplicateSignalCount,
      issues: ['no_signals'],
      source_kinds: [],
    }
  }

  if (input.duplicateSignalCount > 0) {
    issues.push('duplicate_signals_dropped')
    completenessScore -= Math.min(0.2, input.duplicateSignalCount * 0.05)
  }

  const hasExternalUrl = input.signals.some((signal) => signal.source_url)
  if (!hasExternalUrl) {
    issues.push('no_external_source_urls')
    completenessScore -= 0.15
  }

  const signalKinds = [...new Set(sortSignals(input.signals).map((signal) => signal.kind))]
  if (signalKinds.length === 1 && signalKinds[0] === 'manual_note') {
    issues.push('manual_only_sidecar')
    completenessScore -= 0.1
  }

  const unknownStanceCount = input.signals.filter((signal) => signal.stance === 'unknown').length
  if (unknownStanceCount === input.signals.length) {
    issues.push('all_stances_unknown')
    completenessScore -= 0.15
  }

  const status: MarketResearchSidecarHealthStatus = issues.length > 0
    ? 'degraded'
    : 'healthy'

  return {
    status,
    completeness_score: Number(clamp(completenessScore, 0, 1).toFixed(4)),
    duplicate_signal_count: input.duplicateSignalCount,
    issues,
    source_kinds: signalKinds,
  }
}

function countByKind(signals: PredictionMarketResearchSignal[]): Record<PredictionMarketResearchSignalKind, number> {
  return {
    worldmonitor: signals.filter((signal) => signal.kind === 'worldmonitor').length,
    news: signals.filter((signal) => signal.kind === 'news').length,
    alert: signals.filter((signal) => signal.kind === 'alert').length,
    manual_note: signals.filter((signal) => signal.kind === 'manual_note').length,
  }
}

function countByStance(signals: PredictionMarketResearchSignal[]): Record<PredictionMarketResearchSignalStance, number> {
  return {
    supportive: signals.filter((signal) => signal.stance === 'supportive').length,
    contradictory: signals.filter((signal) => signal.stance === 'contradictory').length,
    neutral: signals.filter((signal) => signal.stance === 'neutral').length,
    unknown: signals.filter((signal) => signal.stance === 'unknown').length,
  }
}

function topTags(signals: PredictionMarketResearchSignal[], limit = 5): string[] {
  const counts = new Map<string, number>()

  for (const signal of signals) {
    for (const tag of signal.tags) {
      counts.set(tag, (counts.get(tag) || 0) + 1)
    }
  }

  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, limit)
    .map(([tag]) => tag)
}

function manualThesisHint(signals: PredictionMarketResearchSignal[]): {
  probability?: number
  rationale?: string
} {
  const manualSignals = signals.filter((signal) => signal.kind === 'manual_note' && signal.thesis_probability != null)
  if (manualSignals.length === 0) return {}

  const avgProbability = manualSignals.reduce((sum, signal) => sum + (signal.thesis_probability || 0), 0) / manualSignals.length
  const rationale = manualSignals
    .map((signal) => signal.thesis_rationale || signal.summary)
    .filter((value, index, values) => value && values.indexOf(value) === index)
    .slice(0, 2)
    .join(' ')

  return {
    probability: Number(avgProbability.toFixed(4)),
    rationale: rationale || undefined,
  }
}

function buildRetrievalSummary(input: {
  signals: PredictionMarketResearchSignal[]
  evidencePackets: EvidencePacket[]
  health: MarketResearchSidecarHealth
}): PredictionMarketResearchRetrievalSummary {
  const signals = sortSignals(input.signals)
  const countsByKind = countByKind(signals)
  const countsByStance = countByStance(signals)
  const signalKinds: PredictionMarketResearchSignalKind[] = ['worldmonitor', 'news', 'alert', 'manual_note']

  return {
    signal_ids: signals.map((signal) => signal.signal_id),
    evidence_ids: input.evidencePackets.map((packet) => packet.evidence_id),
    signal_count: signals.length,
    evidence_count: input.evidencePackets.length,
    latest_signal_at: signals[0]?.captured_at,
    counts_by_kind: countsByKind,
    counts_by_stance: countsByStance,
    supportive_signal_ids: signals
      .filter((signal) => signal.stance === 'supportive')
      .map((signal) => signal.signal_id),
    contradictory_signal_ids: signals
      .filter((signal) => signal.stance === 'contradictory')
      .map((signal) => signal.signal_id),
    neutral_signal_ids: signals
      .filter((signal) => signal.stance === 'neutral')
      .map((signal) => signal.signal_id),
    unknown_signal_ids: signals
      .filter((signal) => signal.stance === 'unknown')
      .map((signal) => signal.signal_id),
    missing_signal_kinds: signalKinds.filter((kind) => countsByKind[kind] === 0),
    health_status: input.health.status,
    health_issues: input.health.issues,
  }
}

function buildAbstentionSummary(input: {
  signals: PredictionMarketResearchSignal[]
  health: MarketResearchSidecarHealth
  supportiveCount: number
  contradictoryCount: number
  manualThesisProbabilityHint?: number
}): PredictionMarketResearchAbstentionSummary {
  const exogenousThesisPresent = input.signals.some(
    (signal) => signal.kind === 'manual_note' && signal.thesis_probability != null,
  )
  const reasons: string[] = []
  const reasonCodes: string[] = []

  if (input.signals.length === 0) {
    reasonCodes.push('no_signals')
    reasons.push('No external research signals are present, so the output should remain market-only.')
  }

  if (input.health.status !== 'healthy') {
    reasonCodes.push(`research_health_${input.health.status}`)
    reasons.push(`Research sidecar health is ${input.health.status}, so the result should be treated as advisory only.`)
  }

  if (input.contradictoryCount >= input.supportiveCount && input.supportiveCount > 0) {
    reasonCodes.push('signal_mix_not_supportive')
    reasons.push('The signal mix is not strongly supportive, so abstention remains attractive.')
  }

  if (!exogenousThesisPresent) {
    reasonCodes.push('no_manual_thesis')
    reasons.push('No manual thesis has been supplied, so there is no exogenous thesis edge yet.')
  }

  const recommended =
    input.signals.length === 0 ||
    input.health.status === 'blocked' ||
    (input.contradictoryCount > input.supportiveCount && input.supportiveCount <= 1)

  return {
    recommended,
    reason_codes: reasonCodes,
    reasons,
    exogenous_thesis_present: exogenousThesisPresent,
    manual_thesis_probability_hint: input.manualThesisProbabilityHint,
  }
}

function buildForecasterCandidates(input: {
  signals: PredictionMarketResearchSignal[]
  baseRateResearch: PredictionMarketBaseRateResearch
  externalReferences: PredictionMarketExternalReference[]
}): PredictionMarketResearchForecasterCandidate[] {
  const candidates: PredictionMarketResearchForecasterCandidate[] = [
    {
      forecaster_id: 'market_base_rate',
      forecaster_kind: 'market_base_rate',
      role: 'baseline',
      status: input.baseRateResearch.base_rate_source === 'fallback_50' ? 'partial' : 'ready',
      label: `Market base rate (${input.baseRateResearch.base_rate_source})`,
      probability_yes: input.baseRateResearch.base_rate_probability_hint,
      rationale: input.baseRateResearch.base_rate_rationale_hint,
      input_signal_ids: input.baseRateResearch.retrieval_summary.signal_ids,
    },
  ]

  const manualSignals = input.signals.filter(
    (signal) => signal.kind === 'manual_note' && signal.thesis_probability != null,
  )
  if (manualSignals.length > 0) {
    candidates.push({
      forecaster_id: 'manual_thesis_consensus',
      forecaster_kind: 'manual_thesis',
      role: 'candidate',
      status: 'ready',
      label: 'Manual thesis consensus',
      probability_yes: input.baseRateResearch.abstention_summary.manual_thesis_probability_hint ?? null,
      rationale: manualSignals
        .map((signal) => signal.thesis_rationale || signal.summary)
        .filter((value, index, values) => value && values.indexOf(value) === index)
        .slice(0, 2)
        .join(' '),
      input_signal_ids: manualSignals.map((signal) => signal.signal_id),
    })
  }

  for (const reference of input.externalReferences) {
    candidates.push({
      forecaster_id: `external:${reference.reference_id}`,
      forecaster_kind: 'external_reference',
      role: 'comparator',
      status: reference.reference_probability_yes == null ? 'partial' : 'ready',
      label: reference.source_name
        ? `${reference.source_name} comparator`
        : `${reference.reference_source} comparator`,
      probability_yes: reference.reference_probability_yes,
      rationale: reference.summary,
      input_signal_ids: [reference.signal_id],
      source_name: reference.source_name,
      source_url: reference.source_url,
    })
  }

  return candidates
}

export function buildBaseRateResearch(input: {
  market: PredictionMarketResearchTarget
  snapshot?: Pick<MarketSnapshot, 'midpoint_yes' | 'yes_price'>
  signals: PredictionMarketResearchSignal[]
  evidencePackets: EvidencePacket[]
  health: MarketResearchSidecarHealth
}): PredictionMarketBaseRateResearch {
  const pipelineVersionMetadata = buildResearchPipelineVersionMetadata()
  const baseRateProbabilityHint = Number(
    clamp(
      input.snapshot?.midpoint_yes ?? input.snapshot?.yes_price ?? 0.5,
      0,
      1,
    ).toFixed(4),
  )
  const supportiveCount = input.signals.filter((signal) => signal.stance === 'supportive').length
  const contradictoryCount = input.signals.filter((signal) => signal.stance === 'contradictory').length
  const neutralCount = input.signals.filter((signal) => signal.stance === 'neutral').length
  const manualHint = manualThesisHint(input.signals)
  const baseRateSource: PredictionMarketBaseRateResearch['base_rate_source'] = input.snapshot?.midpoint_yes != null
    ? 'market_midpoint'
    : input.snapshot?.yes_price != null
      ? 'yes_price'
      : 'fallback_50'
  const retrievalSummary = buildRetrievalSummary({
    signals: input.signals,
    evidencePackets: input.evidencePackets,
    health: input.health,
  })
  const abstentionSummary = buildAbstentionSummary({
    signals: input.signals,
    health: input.health,
    supportiveCount,
    contradictoryCount,
    manualThesisProbabilityHint: manualHint.probability,
  })
  const abstentionPolicy = buildAbstentionPolicy({
    abstentionSummary,
    health: input.health,
    pipelineVersionMetadata,
  })

  const keyFactors = [
    `Base rate anchor at ${Math.round(baseRateProbabilityHint * 1000) / 10}% from ${baseRateSource}.`,
    `${supportiveCount} supportive, ${contradictoryCount} contradictory, ${neutralCount} neutral signal(s).`,
    `${input.evidencePackets.length} evidence packet(s) bridged into the research sidecar.`,
  ]

  const latestSignal = sortSignals(input.signals)[0]
  if (latestSignal) {
    keyFactors.push(`Latest signal: ${latestSignal.title}.`)
  }

  const counterarguments = [
    ...input.signals
      .filter((signal) => signal.stance === 'contradictory')
      .slice(0, 3)
      .map((signal) => signal.summary),
  ]

  if (input.health.issues.length > 0) {
    counterarguments.push(...input.health.issues.map((issue) => `Research health issue: ${issue}.`))
  }
  if (counterarguments.length === 0) {
    counterarguments.push('No contradictory research signals were supplied.')
  }

  const noTradeHints = abstentionSummary.reasons
  const abstentionRecommended = abstentionSummary.recommended

  const confidence = Number(
    clamp(
      0.25 +
        (Math.min(input.signals.length, 5) * 0.1) +
        (supportiveCount > contradictoryCount ? 0.1 : 0) +
        (input.health.status === 'healthy' ? 0.1 : 0) -
        (abstentionRecommended ? 0.15 : 0),
      0.05,
      0.95,
    ).toFixed(4),
  )

  return {
    market_id: input.market.market_id,
    venue: input.market.venue,
    generated_at: nowIso(),
    pipeline_version_metadata: pipelineVersionMetadata,
    base_rate_probability_hint: baseRateProbabilityHint,
    base_rate_source: baseRateSource,
    base_rate_rationale_hint: `Base rate anchored to ${Math.round(baseRateProbabilityHint * 1000) / 10}% with ${supportiveCount} supportive and ${contradictoryCount} contradictory signals.`,
    retrieval_summary: retrievalSummary,
    abstention_summary: abstentionSummary,
    abstention_policy: abstentionPolicy,
    key_factors: keyFactors,
    counterarguments,
    no_trade_hints: noTradeHints,
    abstention_recommended: abstentionRecommended,
    confidence,
  }
}

function buildKeyPoints(signals: PredictionMarketResearchSignal[]): string[] {
  return sortSignals(signals)
    .slice(0, 5)
    .map((signal) => {
      const source = signal.source_name ? ` (${signal.source_name})` : ''
      const stance = signal.stance !== 'unknown' ? ` [${signal.stance}]` : ''
      return `${signal.title}${source}${stance}: ${signal.summary}`
    })
}

function buildSynthesisSummary(input: {
  market: PredictionMarketResearchTarget
  signals: PredictionMarketResearchSignal[]
  countsByKind: Record<PredictionMarketResearchSignalKind, number>
  countsByStance: Record<PredictionMarketResearchSignalStance, number>
  baseRateResearch: PredictionMarketBaseRateResearch
}): string {
  const { countsByKind, countsByStance, signals, baseRateResearch } = input
  const fragments = [
    `${signals.length} external research signal${signals.length === 1 ? '' : 's'}`,
    `${countsByKind.worldmonitor} worldmonitor`,
    `${countsByKind.news} news`,
    `${countsByKind.alert} alerts`,
    `${countsByKind.manual_note} manual notes`,
  ]

  const stanceFragments = [
    `${countsByStance.supportive} supportive`,
    `${countsByStance.contradictory} contradictory`,
    `${countsByStance.neutral} neutral`,
  ]

  const abstentionFragment = baseRateResearch.abstention_recommended
    ? 'Abstention is recommended until stronger exogenous evidence appears.'
    : 'Abstention is not mandatory on the current signal mix.'

  return `Research sidecar for "${input.market.question}": ${fragments.join(', ')}. Signal stance mix: ${stanceFragments.join(', ')}. Base rate anchor: ${Math.round(baseRateResearch.base_rate_probability_hint * 1000) / 10}%. ${abstentionFragment}`
}

export function buildMarketResearchSynthesis(input: {
  market: PredictionMarketResearchTarget
  snapshot?: Pick<MarketSnapshot, 'midpoint_yes' | 'yes_price'>
  forecast_probability_yes?: number | null
  signals: PredictionMarketResearchSignalInput[]
  evidencePackets?: EvidencePacket[]
  health?: MarketResearchSidecarHealth
}): MarketResearchSynthesis {
  const normalizedSignals = input.signals.map((signal) => normalizeResearchSignal(signal))
  const dedupedSignals = dedupeSignals(normalizedSignals)
  const signals = sortSignals(dedupedSignals.signals)
  const evidencePackets = input.evidencePackets ?? buildResearchEvidencePackets({
    market: input.market,
    signals,
  })
  const countsByKind = countByKind(signals)
  const countsByStance = countByStance(signals)
  const manualHint = manualThesisHint(signals)
  const health = input.health ?? buildSidecarHealth({
    signals,
    duplicateSignalCount: dedupedSignals.duplicateSignalCount,
  })
  const pipelineVersionMetadata = buildResearchPipelineVersionMetadata()
  const marketProbabilityYesHint = Number(
    clamp(
      input.snapshot?.midpoint_yes ?? input.snapshot?.yes_price ?? 0.5,
      0,
      1,
    ).toFixed(4),
  )
  const externalReferences = buildExternalReferences({
    signals,
    marketProbabilityYesHint,
    forecastProbabilityYesHint: input.forecast_probability_yes ?? null,
  })
  const baseRateResearch = buildBaseRateResearch({
    market: input.market,
    snapshot: input.snapshot,
    signals,
    evidencePackets,
    health,
  })
  const forecasterCandidates = buildForecasterCandidates({
    signals,
    baseRateResearch,
    externalReferences,
  })
  const independentForecasterOutputs = buildIndependentForecasterOutputs({
    baseRateResearch,
    forecasterCandidates,
    externalReferenceCount: externalReferences.length,
  })
  const weightedAggregatePreview = buildWeightedAggregatePreview({
    baseRateResearch,
    independentForecasterOutputs,
  })
  const calibrationSnapshot = buildCalibrationSnapshot({
    baseRateResearch,
    weightedAggregatePreview,
    independentForecasterOutputs,
  })
  const abstentionPolicy = buildAbstentionPolicy({
    abstentionSummary: baseRateResearch.abstention_summary,
    health,
    weightedAggregatePreview,
    pipelineVersionMetadata,
  })
  const comparativeReport = buildComparativeReport({
    marketOnlyProbabilityYes: baseRateResearch.base_rate_probability_hint,
    baseRateSource: baseRateResearch.base_rate_source,
    weightedAggregatePreview,
    abstentionPolicy,
    forecastProbabilityYes: input.forecast_probability_yes ?? null,
  })

  return {
    market_id: input.market.market_id,
    venue: input.market.venue,
    question: input.market.question,
    generated_at: nowIso(),
    pipeline_version_metadata: pipelineVersionMetadata,
    signal_count: signals.length,
    evidence_count: evidencePackets.length,
    signal_kinds: [...new Set(signals.map((signal) => signal.kind))],
    counts_by_kind: countsByKind,
    counts_by_stance: countsByStance,
    top_tags: topTags(signals),
    latest_signal_at: signals[0]?.captured_at,
    retrieval_summary: baseRateResearch.retrieval_summary,
    manual_thesis_probability_hint: manualHint.probability,
    manual_thesis_rationale_hint: manualHint.rationale,
    base_rate_probability_hint: baseRateResearch.base_rate_probability_hint,
    base_rate_rationale_hint: baseRateResearch.base_rate_rationale_hint,
    base_rate_source: baseRateResearch.base_rate_source,
    abstention_summary: baseRateResearch.abstention_summary,
    key_factors: baseRateResearch.key_factors,
    counterarguments: baseRateResearch.counterarguments,
    no_trade_hints: baseRateResearch.no_trade_hints,
    abstention_recommended: baseRateResearch.abstention_recommended,
    summary: buildSynthesisSummary({
      market: input.market,
      signals,
      countsByKind,
      countsByStance,
      baseRateResearch,
    }),
    key_points: buildKeyPoints(signals),
    evidence_refs: evidencePackets.map((packet) => packet.evidence_id),
    external_reference_count: externalReferences.length,
    external_references: externalReferences,
    market_probability_yes_hint: marketProbabilityYesHint,
    forecast_probability_yes_hint: input.forecast_probability_yes ?? null,
    market_delta_bps: averageNullable(externalReferences.map((reference) => reference.market_delta_bps)),
    forecast_delta_bps: averageNullable(externalReferences.map((reference) => reference.forecast_delta_bps)),
    forecaster_candidates: forecasterCandidates,
    independent_forecaster_outputs: independentForecasterOutputs,
    weighted_aggregate_preview: weightedAggregatePreview,
    comparative_report: comparativeReport,
    calibration_snapshot: calibrationSnapshot,
    abstention_policy: abstentionPolicy,
    health,
  }
}

export function buildMarketResearchSidecar(input: {
  market: PredictionMarketResearchTarget
  snapshot?: Pick<MarketSnapshot, 'midpoint_yes' | 'yes_price'>
  forecast_probability_yes?: number | null
  signals: PredictionMarketResearchSignalInput[]
}): MarketResearchSidecar {
  const normalizedSignals = input.signals.map((signal) => normalizeResearchSignal(signal))
  const dedupedSignals = dedupeSignals(normalizedSignals)
  const pipelineVersionMetadata = buildResearchPipelineVersionMetadata()
  const health = buildSidecarHealth({
    signals: dedupedSignals.signals,
    duplicateSignalCount: dedupedSignals.duplicateSignalCount,
  })
  const evidencePackets = buildResearchEvidencePackets({
    market: input.market,
    signals: dedupedSignals.signals,
  })

  return {
    market_id: input.market.market_id,
    venue: input.market.venue,
    generated_at: nowIso(),
    pipeline_version_metadata: pipelineVersionMetadata,
    signals: dedupedSignals.signals,
    evidence_packets: evidencePackets,
    health,
    synthesis: buildMarketResearchSynthesis({
      market: input.market,
      snapshot: input.snapshot,
      forecast_probability_yes: input.forecast_probability_yes ?? null,
      signals: dedupedSignals.signals,
      evidencePackets,
      health,
    }),
  }
}

export function annotateMarketResearchSidecarComparisons(
  sidecar: MarketResearchSidecar,
  forecastProbabilityYes: number | null,
): MarketResearchSidecar {
  const externalReferences = buildExternalReferences({
    signals: sidecar.signals,
    marketProbabilityYesHint: sidecar.synthesis.market_probability_yes_hint,
    forecastProbabilityYesHint: forecastProbabilityYes,
  })
  const comparativeReportCandidate = sidecar.synthesis.weighted_aggregate_preview && sidecar.synthesis.abstention_policy
    ? buildComparativeReport({
      marketOnlyProbabilityYes: sidecar.synthesis.base_rate_probability_hint,
      baseRateSource: sidecar.synthesis.base_rate_source,
      weightedAggregatePreview: sidecar.synthesis.weighted_aggregate_preview,
      abstentionPolicy: sidecar.synthesis.abstention_policy,
      forecastProbabilityYes,
    })
    : sidecar.synthesis.comparative_report ?? {
      market_only: {
        probability_yes: sidecar.synthesis.base_rate_probability_hint,
        delta_bps_vs_market_only: 0,
        rationale: `Market-only baseline anchored at ${formatProbabilityPercent(sidecar.synthesis.base_rate_probability_hint)} from ${sidecar.synthesis.base_rate_source}.`,
      },
      aggregate: {
        probability_yes: null,
        delta_bps_vs_market_only: null,
        coverage: 0,
        contributor_count: 0,
        usable_contributor_count: 0,
        rationale: 'Aggregate preview is unavailable on this stored sidecar.',
      },
      forecast: {
        forecast_probability_yes: forecastProbabilityYes,
        delta_bps_vs_market_only: probabilityToBps(
          forecastProbabilityYes,
          sidecar.synthesis.base_rate_probability_hint,
        ),
        delta_bps_vs_aggregate: null,
        rationale: forecastProbabilityYes == null
          ? 'No forecast probability hint was supplied, so the forecast lane remains unscored.'
          : `Forecast hint sits at ${formatProbabilityPercent(forecastProbabilityYes)} and can be compared directly against the market-only baseline.`,
      },
      abstention: {
        recommended: sidecar.synthesis.abstention_recommended,
        blocks_forecast: sidecar.synthesis.abstention_recommended,
        reason_codes: sidecar.synthesis.abstention_summary?.reason_codes ?? [],
        rationale: sidecar.synthesis.abstention_summary?.reasons?.[0]
          ?? 'Abstention policy data is unavailable on this stored sidecar.',
      },
      summary: `Market-only ${formatProbabilityPercent(sidecar.synthesis.base_rate_probability_hint)}, aggregate unavailable, forecast ${formatProbabilityPercent(forecastProbabilityYes)}, abstention ${sidecar.synthesis.abstention_recommended ? 'recommended' : 'not recommended'}. Preferred mode: market_only.`,
    }
  const comparativeReportResult = predictionMarketResearchComparativeReportSchema.safeParse(comparativeReportCandidate)
  const comparativeReport: PredictionMarketResearchComparativeReport = comparativeReportResult.success
    ? comparativeReportResult.data as PredictionMarketResearchComparativeReport
    : {
      market_only: {
        probability_yes: sidecar.synthesis.base_rate_probability_hint,
        delta_bps_vs_market_only: 0,
        rationale: `Market-only baseline anchored at ${formatProbabilityPercent(sidecar.synthesis.base_rate_probability_hint)} from ${sidecar.synthesis.base_rate_source}.`,
      },
      aggregate: {
        probability_yes: null,
        delta_bps_vs_market_only: null,
        coverage: 0,
        contributor_count: 0,
        usable_contributor_count: 0,
        rationale: 'Aggregate preview is unavailable on this stored sidecar.',
      },
      forecast: {
        forecast_probability_yes: forecastProbabilityYes,
        delta_bps_vs_market_only: probabilityToBps(
          forecastProbabilityYes,
          sidecar.synthesis.base_rate_probability_hint,
        ),
        delta_bps_vs_aggregate: null,
        rationale: forecastProbabilityYes == null
          ? 'No forecast probability hint was supplied, so the forecast lane remains unscored.'
          : `Forecast hint sits at ${formatProbabilityPercent(forecastProbabilityYes)} and can be compared directly against the market-only baseline.`,
      },
      abstention: {
        recommended: sidecar.synthesis.abstention_recommended,
        blocks_forecast: sidecar.synthesis.abstention_recommended,
        reason_codes: sidecar.synthesis.abstention_summary?.reason_codes ?? [],
        rationale: sidecar.synthesis.abstention_summary?.reasons?.[0]
          ?? 'Abstention policy data is unavailable on this stored sidecar.',
      },
      summary: `Market-only ${formatProbabilityPercent(sidecar.synthesis.base_rate_probability_hint)}, aggregate unavailable, forecast ${formatProbabilityPercent(forecastProbabilityYes)}, abstention ${sidecar.synthesis.abstention_recommended ? 'recommended' : 'not recommended'}. Preferred mode: market_only.`,
    }

  return {
    ...sidecar,
    synthesis: {
      ...sidecar.synthesis,
      forecast_probability_yes_hint: forecastProbabilityYes,
      external_reference_count: externalReferences.length,
      external_references: externalReferences,
      market_delta_bps: averageNullable(externalReferences.map((reference) => reference.market_delta_bps)),
      forecast_delta_bps: averageNullable(externalReferences.map((reference) => reference.forecast_delta_bps)),
      comparative_report: comparativeReport,
    },
  }
}
