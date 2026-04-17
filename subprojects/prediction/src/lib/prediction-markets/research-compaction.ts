type CompactResearchSignal = {
  signal_id: string
  kind: string
  title: string
  summary: string
  source_name?: string
  captured_at?: string
  stance?: string
  tags?: string[]
}

type CompactEvidencePacket = {
  evidence_id?: string
  type?: string
  title?: string
  summary?: string
}

type CompactRetrievalSummary = {
  signal_count: number
  evidence_count: number
  latest_signal_at?: string
  counts_by_kind: Record<string, number>
  counts_by_stance: Record<string, number>
  missing_signal_kinds?: string[]
  health_status?: string
  health_issues?: string[]
}

type CompactWeightedAggregatePreview = {
  contributor_count?: number
  usable_contributor_count?: number
  coverage?: number
  weighted_probability_yes?: number | null
  weighted_delta_bps?: number | null
  abstention_recommended?: boolean
}

type CompactComparativeReport = {
  summary: string
  market_only?: {
    probability_yes?: number | null
  }
  aggregate?: {
    probability_yes?: number | null
  }
  forecast?: {
    forecast_probability_yes?: number | null
  }
  abstention?: {
    recommended?: boolean
    blocks_forecast?: boolean
    reason_codes?: string[]
  }
}

type CompactAbstentionPolicy = {
  policy_version: string
  recommended: boolean
  blocks_forecast: boolean
  manual_review_required: boolean
  trigger_codes: string[]
  rationale: string
}

type CompactExternalReference = {
  reference_id: string
  reference_source: string
  source_name?: string
  reference_probability_yes?: number | null
  market_delta_bps?: number | null
  forecast_delta_bps?: number | null
}

export type PredictionMarketResearchSupercompactContext = {
  schema_version: 'supercompact_research_context.v1'
  format: 'supercompact'
  compact_summary: string
  compact_bullets: string[]
  compact_prompt_block: string
  prompt_char_count: number
  source_refs: string[]
  stats: {
    signal_count: number
    evidence_count: number
    reference_count: number
    health_status: string
  }
  market: {
    market_id: string
    venue: string
    slug?: string
    question: string
  }
  stance_mix: {
    supportive: number
    contradictory: number
    neutral: number
    unknown: number
  }
}

export type BuildPredictionMarketResearchSupercompactContextInput = {
  market: {
    market_id?: string
    venue?: string
    question?: string
    slug?: string
  }
  signals: CompactResearchSignal[]
  evidence_packets: CompactEvidencePacket[]
  retrieval_summary: CompactRetrievalSummary
  weighted_aggregate_preview: CompactWeightedAggregatePreview
  comparative_report: CompactComparativeReport
  abstention_policy: CompactAbstentionPolicy
  external_references: CompactExternalReference[]
  key_factors: string[]
  counterarguments: string[]
  no_trade_hints: string[]
  max_chars?: number
}

function compactWhitespace(value: string): string {
  return value.replace(/\s+/g, ' ').trim()
}

function compactText(value: string | null | undefined, maxChars: number): string {
  const normalized = compactWhitespace(String(value ?? ''))
  if (normalized.length <= maxChars) return normalized
  if (maxChars <= 1) return normalized.slice(0, maxChars)
  return `${normalized.slice(0, Math.max(0, maxChars - 1)).trimEnd()}…`
}

function compactList(values: Array<string | null | undefined>, limit: number, itemMaxChars = 80): string[] {
  return values
    .map((value) => compactText(value, itemMaxChars))
    .filter((value) => value.length > 0)
    .slice(0, limit)
}

function formatProbability(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'n/a'
  return `${(value * 100).toFixed(1)}%`
}

function formatBps(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'n/a'
  return `${Math.round(value)}bps`
}

function topSignalsByStance(signals: CompactResearchSignal[], stance: string): string[] {
  return compactList(
    signals
      .filter((signal) => signal.stance === stance)
      .map((signal) => `${signal.title}${signal.source_name ? ` (${signal.source_name})` : ''}`),
    2,
    70,
  )
}

function topReferenceFragments(references: CompactExternalReference[]): string[] {
  return compactList(
    references.map((reference) => {
      const label = reference.source_name || reference.reference_source
      return `${label}:${formatProbability(reference.reference_probability_yes)}/mkt=${formatBps(reference.market_delta_bps)}/fcst=${formatBps(reference.forecast_delta_bps)}`
    }),
    3,
    72,
  )
}

export function buildPredictionMarketResearchSupercompactContext(
  input: BuildPredictionMarketResearchSupercompactContextInput,
): PredictionMarketResearchSupercompactContext {
  const maxChars = Math.max(400, input.max_chars ?? 1400)
  const retrievalSummary = input.retrieval_summary ?? {
    signal_count: 0,
    evidence_count: 0,
    health_status: 'unknown',
    latest_signal_at: null,
    counts_by_stance: {},
  }
  const countsByStance = (retrievalSummary.counts_by_stance ?? {}) as Partial<Record<'supportive' | 'contradictory' | 'neutral' | 'unknown', number>>
  const supportive = countsByStance.supportive ?? 0
  const contradictory = countsByStance.contradictory ?? 0
  const neutral = countsByStance.neutral ?? 0
  const unknown = countsByStance.unknown ?? 0
  const weightedAggregatePreview = input.weighted_aggregate_preview ?? {
    weighted_probability_yes: null,
    weighted_delta_bps: null,
    coverage: 0,
  }
  const comparativeReport = input.comparative_report ?? {
    market_only: { probability_yes: null },
    forecast: { forecast_probability_yes: null },
    summary: 'Comparative report unavailable.',
  }
  const abstentionPolicy = input.abstention_policy ?? {
    policy_version: 'unknown',
    recommended: false,
    blocks_forecast: false,
    trigger_codes: [],
  }

  const topSupportive = topSignalsByStance(input.signals, 'supportive')
  const topContradictory = topSignalsByStance(input.signals, 'contradictory')
  const latestTitles = compactList(input.signals.map((signal) => signal.title), 3, 72)
  const evidenceTypes = compactList(
    input.evidence_packets.map((packet) => `${packet.type}:${packet.evidence_id}`),
    4,
    72,
  )
  const referenceFragments = topReferenceFragments(input.external_references)
  const keyFactors = compactList(input.key_factors, 3, 92)
  const counterarguments = compactList(input.counterarguments, 2, 92)
  const noTradeHints = compactList(input.no_trade_hints, 2, 92)

  const bullets = compactList([
    `Market ${input.market.market_id ?? 'n/a'} on ${input.market.venue ?? 'n/a'}: ${input.market.question ?? 'n/a'}`,
    `Signals ${retrievalSummary.signal_count}, evidence ${retrievalSummary.evidence_count}, health ${retrievalSummary.health_status ?? 'unknown'}, latest ${compactText(retrievalSummary.latest_signal_at ?? 'n/a', 32)}`,
    `Stance mix supportive=${supportive} contradictory=${contradictory} neutral=${neutral} unknown=${unknown}`,
    `Aggregate ${formatProbability(weightedAggregatePreview.weighted_probability_yes)} vs market ${formatProbability(comparativeReport.market_only?.probability_yes)} vs forecast ${formatProbability(comparativeReport.forecast?.forecast_probability_yes)}; delta ${formatBps(weightedAggregatePreview.weighted_delta_bps)}; coverage ${typeof weightedAggregatePreview.coverage === 'number' ? weightedAggregatePreview.coverage.toFixed(2) : 'n/a'}`,
    `Abstention policy ${abstentionPolicy.policy_version}: recommended=${abstentionPolicy.recommended ? 'yes' : 'no'} blocks=${abstentionPolicy.blocks_forecast ? 'yes' : 'no'} triggers=${compactList(abstentionPolicy.trigger_codes, 4, 28).join(', ') || 'none'}`,
    `Comparative summary: ${compactText(comparativeReport.summary, 180)}`,
    topSupportive.length ? `Supportive: ${topSupportive.join(' | ')}` : null,
    topContradictory.length ? `Contradictory: ${topContradictory.join(' | ')}` : null,
    latestTitles.length ? `Latest titles: ${latestTitles.join(' | ')}` : null,
    evidenceTypes.length ? `Evidence: ${evidenceTypes.join(' | ')}` : null,
    referenceFragments.length ? `References: ${referenceFragments.join(' | ')}` : null,
    keyFactors.length ? `Factors: ${keyFactors.join(' | ')}` : null,
    counterarguments.length ? `Counters: ${counterarguments.join(' | ')}` : null,
    noTradeHints.length ? `No-trade: ${noTradeHints.join(' | ')}` : null,
  ], 14, 220)

  let promptBlock = bullets.join('\n')
  if (promptBlock.length > maxChars) {
    const trimmedBullets: string[] = []
    for (const bullet of bullets) {
      const candidate = [...trimmedBullets, bullet].join('\n')
      if (candidate.length > maxChars) break
      trimmedBullets.push(bullet)
    }
    promptBlock = trimmedBullets.join('\n')
  }

  const compactSummary = compactText(
    [
      `${input.market.question}`,
      `signals=${retrievalSummary.signal_count}`,
      `health=${retrievalSummary.health_status ?? 'unknown'}`,
      `aggregate=${formatProbability(weightedAggregatePreview.weighted_probability_yes)}`,
      `market=${formatProbability(comparativeReport.market_only?.probability_yes)}`,
      `forecast=${formatProbability(comparativeReport.forecast?.forecast_probability_yes)}`,
      `abstention=${abstentionPolicy.recommended ? 'yes' : 'no'}`,
    ].join(' | '),
    240,
  )

  const sourceRefs = compactList([
    input.market.market_id,
    input.market.slug,
    ...input.evidence_packets.map((packet) => packet.evidence_id),
    ...input.external_references.map((reference) => reference.reference_id),
  ], 12, 96)

  return {
    schema_version: 'supercompact_research_context.v1',
    format: 'supercompact',
    compact_summary: compactSummary,
    compact_bullets: bullets,
    compact_prompt_block: promptBlock,
    prompt_char_count: promptBlock.length,
    source_refs: sourceRefs,
    stats: {
      signal_count: retrievalSummary.signal_count,
      evidence_count: retrievalSummary.evidence_count,
      reference_count: input.external_references.length,
      health_status: retrievalSummary.health_status ?? 'unknown',
    },
    market: {
      market_id: input.market.market_id ?? 'n/a',
      venue: input.market.venue ?? 'unknown',
      slug: input.market.slug,
      question: input.market.question ?? 'n/a',
    },
    stance_mix: {
      supportive,
      contradictory,
      neutral,
      unknown,
    },
  }
}
