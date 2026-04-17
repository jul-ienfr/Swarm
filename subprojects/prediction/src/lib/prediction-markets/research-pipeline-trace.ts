import type { EvidencePacket, PredictionMarketVenue } from '@/lib/prediction-markets/schemas'
import {
  buildPredictionMarketExternalIntegrationSummary,
  matchConversationScopedExternalSourceProfiles,
  type PredictionMarketExternalIntegrationSummary,
  type PredictionMarketExternalSourceProfileSummary,
} from './external-source-profiles'

type PredictionMarketResearchSignalKind = 'worldmonitor' | 'news' | 'alert' | 'manual_note'
type PredictionMarketResearchSignalStance = 'supportive' | 'contradictory' | 'neutral' | 'unknown'

type PredictionMarketResearchSignalLike = {
  signal_id: string
  kind: PredictionMarketResearchSignalKind
  title: string
  summary: string
  stance: PredictionMarketResearchSignalStance
  tags: string[]
  thesis_probability?: number
  source_name?: string
  source_url?: string
  external_profiles?: PredictionMarketExternalSourceProfileSummary[]
}

type PipelineVersionMetadataLike = {
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

type RetrievalSummaryLike = {
  signal_count: number
  evidence_count: number
  health_status: 'healthy' | 'degraded' | 'blocked'
  missing_signal_kinds: PredictionMarketResearchSignalKind[]
  counts_by_stance: Record<PredictionMarketResearchSignalStance, number>
  external_profiles?: PredictionMarketExternalSourceProfileSummary[]
  external_integration?: PredictionMarketExternalIntegrationSummary
}

type BaseRateResearchLike = {
  market_id: string
  venue: PredictionMarketVenue
  generated_at: string
  pipeline_version_metadata: PipelineVersionMetadataLike
  base_rate_probability_hint: number
  retrieval_summary: RetrievalSummaryLike
}

type WeightedAggregatePreviewLike = {
  base_rate_probability_yes: number
  weighted_probability_yes: number | null
  weighted_probability_yes_raw: number | null
  coverage: number
  contributor_count: number
  usable_contributor_count: number
}

type ComparativeReportLike = {
  summary: string
  abstention: {
    blocks_forecast: boolean
  }
  aggregate: {
    probability_yes: number | null
    coverage: number
    delta_bps_vs_market_only: number | null
  }
}

export type PredictionMarketResearchPipelineTrace = {
  trace_id: string
  pipeline_id: string
  pipeline_version: string
  market_id: string
  venue: PredictionMarketVenue
  generated_at: string
  pipeline_version_metadata: PipelineVersionMetadataLike
  stages: {
    query: {
      query_text: string
      market_id: string
      venue: PredictionMarketVenue
      signal_count: number
      evidence_count: number
      query_count: number
      queries: string[]
      query_terms: string[]
    }
    retrieval: {
      signal_count: number
      evidence_count: number
      health_status: 'healthy' | 'degraded' | 'blocked'
      missing_signal_kinds: PredictionMarketResearchSignalKind[]
      source_kinds: PredictionMarketResearchSignalKind[]
      external_profiles: PredictionMarketExternalSourceProfileSummary[]
      external_integration: PredictionMarketExternalIntegrationSummary
    }
    rank: {
      ranked_signal_ids: string[]
      ranked_signals: Array<{
        signal_id: string
        kind: PredictionMarketResearchSignalKind
        stance: PredictionMarketResearchSignalStance
        title: string
        summary: string
        reasons: string[]
      }>
      balance: {
        supportive_count: number
        contradictory_count: number
        neutral_count: number
        unknown_count: number
        direction: 'supportive' | 'contradictory' | 'balanced'
      }
    }
    summarize: {
      supporting_summary: string
      counter_summary: string
      key_tags: string[]
      source_family_summary: string
      both_sides_reasoning: string
    }
    aggregate: {
      baseline_probability_yes: number
      aggregate_probability_yes: number | null
      forecast_probability_yes: number | null
      preferred_mode: 'market_only' | 'aggregate' | 'abstention'
      comparative_summary: string
      contributor_count: number
      usable_contributor_count: number
      forecaster_count: number
      usable_forecaster_count: number
      coverage: number
    }
  }
  summary: string
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const value of values) {
    const normalized = String(value ?? '').trim()
    if (!normalized || seen.has(normalized)) continue
    seen.add(normalized)
    out.push(normalized)
  }
  return out
}

function summarizeSignals(
  signals: readonly PredictionMarketResearchSignalLike[],
  stance: PredictionMarketResearchSignalStance,
): string {
  const filtered = signals.filter((signal) => signal.stance === stance)
  if (filtered.length === 0) {
    return stance === 'supportive'
      ? 'No clearly supportive research signal was retrieved.'
      : 'No clearly contradictory research signal was retrieved.'
  }
  return filtered
    .slice(0, 2)
    .map((signal) => {
      const title = signal.title?.trim()
      const summary = signal.summary?.trim()
      if (title && summary) return `${title}. ${summary}`
      return title || summary || signal.signal_id
    })
    .join(' ')
}

function tokenize(value: string | null | undefined): string[] {
  return String(value ?? '')
    .toLowerCase()
    .split(/[^a-z0-9]+/g)
    .map((token) => token.trim())
    .filter((token) => token.length >= 3)
}

function buildQueryTerms(input: {
  question: string
  slug?: string | null
  signals: readonly PredictionMarketResearchSignalLike[]
  sourceKinds: readonly PredictionMarketResearchSignalKind[]
}): string[] {
  return uniqueStrings([
    ...tokenize(input.question),
    ...tokenize(input.slug),
    ...input.signals.flatMap((signal) => [
      ...tokenize(signal.title),
      ...tokenize(signal.summary),
      ...signal.tags,
    ]),
    ...input.sourceKinds,
  ]).slice(0, 20)
}

function buildRankedSignals(
  signals: readonly PredictionMarketResearchSignalLike[],
): Array<{
  signal_id: string
  kind: PredictionMarketResearchSignalKind
  stance: PredictionMarketResearchSignalStance
  title: string
  summary: string
  reasons: string[]
}> {
  const score = (signal: PredictionMarketResearchSignalLike): number => {
    let total = 0
    if (signal.kind === 'manual_note') total += 100
    if (signal.stance === 'supportive') total += 20
    if (signal.stance === 'contradictory') total += 10
    if (typeof signal['thesis_probability'] === 'number') {
      total += Math.round(Number(signal['thesis_probability']) * 100)
    }
    total += Math.min(signal.tags.length, 10)
    return total
  }

  return [...signals]
    .sort((left, right) => {
      const delta = score(right) - score(left)
      if (delta !== 0) return delta
      return left.signal_id.localeCompare(right.signal_id)
    })
    .map((signal) => {
      const reasons = [
        `kind=${signal.kind}`,
        `stance=${signal.stance}`,
        `tags=${signal.tags.length}`,
      ]
      const profileIds = signal.external_profiles?.map((profile) => profile.profile_id) ?? []
      if (profileIds.length > 0) {
        reasons.push(`profiles=${profileIds.join(',')}`)
      }
      const thesisProbability = signal['thesis_probability']
      if (typeof thesisProbability === 'number') {
        reasons.push(`thesis_probability=${thesisProbability.toFixed(4)}`)
      }
      return {
        signal_id: signal.signal_id,
        kind: signal.kind,
        stance: signal.stance,
        title: signal.title,
        summary: signal.summary,
        reasons,
      }
    })
}

function preferredMode(input: {
  comparativeReport: ComparativeReportLike
}): 'market_only' | 'aggregate' | 'abstention' {
  if (input.comparativeReport.abstention.blocks_forecast) return 'abstention'
  if (
    input.comparativeReport.aggregate.probability_yes != null &&
    input.comparativeReport.aggregate.coverage > 0 &&
    (input.comparativeReport.aggregate.delta_bps_vs_market_only == null
      ? false
      : Math.abs(input.comparativeReport.aggregate.delta_bps_vs_market_only) > 0)
  ) {
    return 'aggregate'
  }
  return 'market_only'
}

export function buildResearchPipelineTrace(input: {
  market: {
    market_id: string
    venue: PredictionMarketVenue
    question: string
    slug?: string | null
  }
  snapshot: {
    source_urls?: string[] | null
  } | null
  forecast_probability_yes: number | null
  signals: PredictionMarketResearchSignalLike[]
  evidencePackets: EvidencePacket[]
  health: {
    status: 'healthy' | 'degraded' | 'blocked'
    source_kinds: PredictionMarketResearchSignalKind[]
  }
  baseRateResearch: BaseRateResearchLike
  forecasterCandidates: Array<{ forecaster_id: string }>
  independentForecasterOutputs: Array<{ forecaster_id: string }>
  weightedAggregatePreview: WeightedAggregatePreviewLike
  comparativeReport: ComparativeReportLike
}): PredictionMarketResearchPipelineTrace {
  const externalProfiles = uniqueStrings(
    input.signals
      .flatMap((signal) => {
        const matched = signal.external_profiles
          ?? matchConversationScopedExternalSourceProfiles({
            sourceName: signal.source_name ?? null,
            title: signal.title,
            sourceUrl: signal.source_url ?? null,
            sourceRefs: signal.tags,
            notes: [signal.summary],
          })
        return matched.map((profile) => JSON.stringify(profile))
      }),
  ).map((value) => JSON.parse(value) as PredictionMarketExternalSourceProfileSummary)
  const externalIntegration = input.baseRateResearch.retrieval_summary.external_integration
    ?? buildPredictionMarketExternalIntegrationSummary(externalProfiles)
  const sourceKinds = uniqueStrings(input.signals.map((signal) => signal.kind)) as PredictionMarketResearchSignalKind[]
  const rankedSignalIds = input.signals.map((signal) => signal.signal_id)
  const countsByStance = input.baseRateResearch.retrieval_summary.counts_by_stance
  const supportiveCount = countsByStance.supportive ?? 0
  const contradictoryCount = countsByStance.contradictory ?? 0
  const neutralCount = countsByStance.neutral ?? 0
  const unknownCount = countsByStance.unknown ?? 0
  const direction = supportiveCount > contradictoryCount
    ? 'supportive'
    : contradictoryCount > supportiveCount
      ? 'contradictory'
      : 'balanced'
  const tracePreferredMode = preferredMode({ comparativeReport: input.comparativeReport })
  const keyTags = uniqueStrings(input.signals.flatMap((signal) => signal.tags)).slice(0, 6)
  const supportingSummary = summarizeSignals(input.signals, 'supportive')
  const counterSummary = summarizeSignals(input.signals, 'contradictory')
  const queryTerms = buildQueryTerms({
    question: input.market.question,
    slug: input.market.slug ?? null,
    signals: input.signals,
    sourceKinds,
  })
  const querySeeds = uniqueStrings([
    input.market.question,
    input.market.slug ?? null,
    ...sourceKinds,
    ...(input.snapshot?.source_urls ?? []).slice(0, 2),
  ]).slice(0, 5)
  const rankedSignals = buildRankedSignals(input.signals)
  const comparativeSummary = `Preferred mode: ${tracePreferredMode}. ${input.comparativeReport.summary}`.trim()
  const bothSidesReasoning =
    `Supportive: ${supportingSummary} `
    + `Counter: ${counterSummary} `
    + `Net direction: ${direction}.`
  const sourceFamilySummary = externalProfiles.length === 0
    ? 'No conversation-scoped external source family was detected in this trace.'
    : `External source families: ${externalProfiles.map((profile) => profile.label).join(', ')}.`

  return {
    trace_id: `${input.market.market_id}:research-pipeline-trace`,
    pipeline_id: input.baseRateResearch.pipeline_version_metadata.pipeline_id,
    pipeline_version: input.baseRateResearch.pipeline_version_metadata.pipeline_version,
    market_id: input.market.market_id,
    venue: input.market.venue,
    generated_at: input.baseRateResearch.generated_at,
    pipeline_version_metadata: input.baseRateResearch.pipeline_version_metadata,
    stages: {
      query: {
        query_text: input.market.question,
        market_id: input.market.market_id,
        venue: input.market.venue,
        signal_count: input.signals.length,
        evidence_count: input.evidencePackets.length,
        query_count: querySeeds.length,
        queries: querySeeds,
        query_terms: queryTerms,
      },
      retrieval: {
        signal_count: input.baseRateResearch.retrieval_summary.signal_count,
        evidence_count: input.baseRateResearch.retrieval_summary.evidence_count,
        health_status: input.health.status,
        missing_signal_kinds: input.baseRateResearch.retrieval_summary.missing_signal_kinds,
        source_kinds: sourceKinds,
        external_profiles: externalProfiles,
        external_integration: externalIntegration,
      },
      rank: {
        ranked_signal_ids: rankedSignalIds,
        ranked_signals: rankedSignals,
        balance: {
          supportive_count: supportiveCount,
          contradictory_count: contradictoryCount,
          neutral_count: neutralCount,
          unknown_count: unknownCount,
          direction,
        },
      },
      summarize: {
        supporting_summary: supportingSummary,
        counter_summary: counterSummary,
        key_tags: keyTags,
        source_family_summary: sourceFamilySummary,
        both_sides_reasoning: bothSidesReasoning,
      },
      aggregate: {
        baseline_probability_yes: input.weightedAggregatePreview.base_rate_probability_yes,
        aggregate_probability_yes:
          input.weightedAggregatePreview.weighted_probability_yes
          ?? input.weightedAggregatePreview.weighted_probability_yes_raw,
        forecast_probability_yes: input.forecast_probability_yes,
        preferred_mode: tracePreferredMode,
        comparative_summary: comparativeSummary,
        contributor_count: input.weightedAggregatePreview.contributor_count,
        usable_contributor_count: input.weightedAggregatePreview.usable_contributor_count,
        forecaster_count: input.forecasterCandidates.length,
        usable_forecaster_count: input.independentForecasterOutputs.length,
        coverage: input.weightedAggregatePreview.coverage,
      },
    },
    summary:
      `Research pipeline trace for ${input.market.market_id}: `
      + `query=${input.market.question}; `
      + `retrieval=${input.signals.length} signal(s)/${input.evidencePackets.length} evidence packet(s); `
      + `aggregate=${tracePreferredMode}: ${comparativeSummary}; `
      + `profiles=${externalIntegration.total_profiles}`,
  }
}
