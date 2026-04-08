import {
  normalizeResearchSignal,
  type MarketResearchSidecar,
  type PredictionMarketResearchSignal,
} from '@/lib/prediction-markets/research'
import {
  type CrossVenueOpsSummary,
  type CrossVenueArbitrageCandidate,
} from '@/lib/prediction-markets/cross-venue'
import {
  type MicrostructureLabReport,
  type MicrostructureSeverity,
} from '@/lib/prediction-markets/microstructure-lab'
import {
  type MarketSnapshot,
  type PredictionMarketMarketGraph,
  type ResolutionPolicy,
  type ResearchBridgeBundle,
  type PredictionMarketVenue,
} from '@/lib/prediction-markets/schemas'

export type PredictionMarketStrategyRegimeDisposition =
  | 'calm'
  | 'watch'
  | 'stress'
  | 'defense'

export type PredictionMarketStrategyPriceState =
  | 'tight'
  | 'balanced'
  | 'wide'
  | 'dislocated'

export type PredictionMarketStrategyFreshnessState =
  | 'fresh'
  | 'warm'
  | 'stale'

export type PredictionMarketStrategyResolutionState =
  | 'clear'
  | 'watch'
  | 'anomalous'

export type PredictionMarketStrategyResearchState =
  | 'supportive'
  | 'mixed'
  | 'abstain'

export type PredictionMarketStrategyLatencyState =
  | 'fresh'
  | 'lagging'
  | 'stale'

export type PredictionMarketStrategyResolutionAnomalyKind =
  | 'policy_ambiguity'
  | 'policy_blocked'
  | 'graph_misalignment'
  | 'signal_conflict'
  | 'horizon_drift'
  | 'attack_watch'
  | 'sniping_watch'
  | 'cross_venue_resolution_mismatch'

export type PredictionMarketStrategyResolutionAnomaly = {
  read_only: true
  anomaly_id: string
  market_id: string
  venue: PredictionMarketVenue
  anomaly_kind: PredictionMarketStrategyResolutionAnomalyKind
  severity: 'low' | 'medium' | 'high' | 'critical'
  watch_kind: 'analysis' | 'defense' | 'watch'
  score: number
  hours_to_resolution: number | null
  summary: string
  reasons: string[]
  signal_refs: string[]
}

export type PredictionMarketStrategyLatencyReferenceSource =
  | 'base_snapshot'
  | 'related_snapshot'
  | 'graph_node'
  | 'cross_venue_candidate'

export type PredictionMarketStrategyLatencyReference = {
  read_only: true
  reference_id: string
  market_id: string
  venue: PredictionMarketVenue
  source: PredictionMarketStrategyLatencyReferenceSource
  role: 'anchor' | 'reference' | 'comparison'
  price_yes: number | null
  spread_bps: number | null
  quote_age_ms: number | null
  freshness_gap_ms: number | null
  liquidity_usd: number | null
  reference_score: number
  summary: string
  reasons: string[]
}

export type PredictionMarketStrategyRegimeInput = {
  snapshot: MarketSnapshot
  related_snapshots?: MarketSnapshot[]
  market_graph?: PredictionMarketMarketGraph | null
  cross_venue_summary?: CrossVenueOpsSummary | null
  microstructure_lab?: MicrostructureLabReport | null
  research_sidecar?: MarketResearchSidecar | null
  research_bridge?: ResearchBridgeBundle | null
  resolution_policy?: ResolutionPolicy | null
  as_of_at?: string
}

export type PredictionMarketStrategyMarketRegime = {
  read_only: true
  regime_id: string
  market_id: string
  venue: PredictionMarketVenue
  generated_at: string
  disposition: PredictionMarketStrategyRegimeDisposition
  price_state: PredictionMarketStrategyPriceState
  freshness_state: PredictionMarketStrategyFreshnessState
  resolution_state: PredictionMarketStrategyResolutionState
  research_state: PredictionMarketStrategyResearchState
  latency_state: PredictionMarketStrategyLatencyState
  stress_level: 'low' | 'medium' | 'high' | 'critical'
  signal_strength: number
  confidence_score: number
  hours_to_resolution: number | null
  price_spread_bps: number | null
  quote_age_ms: number | null
  liquidity_usd: number | null
  anomaly_count: number
  anomaly_kinds: PredictionMarketStrategyResolutionAnomalyKind[]
  latency_reference_count: number
  key_signals: string[]
  reasons: string[]
  summary: string
}

const ATTACK_KEYWORDS = [
  'attack',
  'manipulate',
  'manipulation',
  'tamper',
  'tampering',
  'dispute',
  'oracle',
  'ambiguous',
  'exploit',
  'withhold',
  'game',
  'bribe',
  'rig',
]

const SNIPING_KEYWORDS = [
  'snip',
  'snipe',
  'deadline',
  'final hour',
  'final minute',
  'closing',
  'settle',
  'settlement',
  'resolution',
  'expiry',
  'expire',
]

function nowIso(): string {
  return new Date().toISOString()
}

function resolveAsOfMs(value?: string, fallback?: string): number {
  const target = value ?? fallback
  if (!target) return Date.now()
  const parsed = Date.parse(target)
  return Number.isFinite(parsed) ? parsed : Date.now()
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function round(value: number): number {
  return Number(value.toFixed(4))
}

function nonNegativeMs(value: number | null | undefined): number | null {
  if (!Number.isFinite(value ?? NaN)) return null
  return Math.max(0, Math.round(value ?? 0))
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

function normalizeText(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function tokenize(value: string): string[] {
  return normalizeText(value)
    .split(' ')
    .map((token) => token.trim())
    .filter((token) => token.length > 1)
}

function jaccard(left: readonly string[], right: readonly string[]): number {
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

function maybeNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function maybeString(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null
}

function getSnapshotPriceYes(snapshot: MarketSnapshot): number | null {
  const candidates = [
    snapshot.midpoint_yes,
    snapshot.yes_price,
    snapshot.best_bid_yes != null && snapshot.best_ask_yes != null
      ? (snapshot.best_bid_yes + snapshot.best_ask_yes) / 2
      : null,
    snapshot.best_bid_yes,
    snapshot.best_ask_yes,
    snapshot.market.last_trade_price,
  ]

  for (const value of candidates) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return clamp(value, 0, 1)
    }
  }

  return null
}

function getSnapshotSpreadBps(snapshot: MarketSnapshot): number | null {
  if (typeof snapshot.spread_bps === 'number' && Number.isFinite(snapshot.spread_bps)) {
    return Math.max(0, snapshot.spread_bps)
  }

  if (snapshot.best_bid_yes != null && snapshot.best_ask_yes != null) {
    return Math.max(0, (snapshot.best_ask_yes - snapshot.best_bid_yes) * 10_000)
  }

  return null
}

function getSnapshotQuoteAgeMs(snapshot: MarketSnapshot, asOfMs: number): number | null {
  const observedAt = snapshot.book?.fetched_at ?? snapshot.captured_at
  const parsed = Date.parse(observedAt)
  if (!Number.isFinite(parsed)) return null
  return Math.max(0, asOfMs - parsed)
}

function getHoursToResolution(snapshot: MarketSnapshot, asOfMs: number): number | null {
  const raw = snapshot.market.end_at ?? snapshot.market.start_at
  if (!raw) return null
  const parsed = Date.parse(raw)
  if (!Number.isFinite(parsed)) return null
  return (parsed - asOfMs) / 3_600_000
}

function getMarketQuestionKey(question: string): string {
  return tokenize(question).slice(0, 12).join(' ')
}

function researchSignalText(signal: PredictionMarketResearchSignal): string {
  return normalizeText([
    signal.title,
    signal.summary,
    signal.thesis_rationale ?? '',
    signal.source_name ?? '',
    signal.source_url ?? '',
  ].filter(Boolean).join(' '))
}

function collectResearchSignals(input: PredictionMarketStrategyRegimeInput): PredictionMarketResearchSignal[] {
  const signals: PredictionMarketResearchSignal[] = [...(input.research_sidecar?.signals ?? [])]

  for (const packet of input.research_bridge?.signal_packets ?? []) {
    signals.push(normalizeResearchSignal(packet as Parameters<typeof normalizeResearchSignal>[0]))
  }

  const seen = new Set<string>()
  const out: PredictionMarketResearchSignal[] = []
  for (const signal of signals) {
    if (seen.has(signal.signal_id)) continue
    seen.add(signal.signal_id)
    out.push(signal)
  }

  return out
}

function hasAnyKeyword(text: string, keywords: readonly string[]): boolean {
  return keywords.some((keyword) => text.includes(normalizeText(keyword)))
}

function researchSummaryState(input: PredictionMarketStrategyRegimeInput, signalCount: number): {
  state: PredictionMarketStrategyResearchState
  reasons: string[]
} {
  const sidecar = input.research_sidecar
  const bridge = input.research_bridge
  const reasons: string[] = []
  const signals = collectResearchSignals(input)
  const supportive = signals.filter((signal) => signal.stance === 'supportive').length
  const contradictory = signals.filter((signal) => signal.stance === 'contradictory').length
  const manualSignals = signals.filter((signal) => signal.kind === 'manual_note' && signal.thesis_probability != null)

  if (sidecar?.synthesis.abstention_recommended || bridge?.classification.toLowerCase().includes('abstain')) {
    reasons.push('research_abstention_recommended')
    return { state: 'abstain', reasons }
  }

  if (sidecar?.health.status === 'blocked') {
    reasons.push('research_health_blocked')
    return { state: 'abstain', reasons }
  }

  if (contradictory > supportive || manualSignals.length > 0) {
    reasons.push(contradictory > supportive ? 'contradictory_signals_dominate' : 'manual_thesis_present')
    return { state: 'mixed', reasons }
  }

  if (signalCount > 0) {
    reasons.push('supportive_or_neutral_research_available')
  }

  return { state: 'supportive', reasons }
}

function priceStateFromSpread(spreadBps: number | null): PredictionMarketStrategyPriceState {
  if (spreadBps == null) return 'balanced'
  if (spreadBps <= 25) return 'tight'
  if (spreadBps <= 75) return 'balanced'
  if (spreadBps <= 150) return 'wide'
  return 'dislocated'
}

function freshnessStateFromAge(ageMs: number | null): PredictionMarketStrategyFreshnessState {
  if (ageMs == null) return 'warm'
  if (ageMs <= 60_000) return 'fresh'
  if (ageMs <= 300_000) return 'warm'
  return 'stale'
}

function latencyStateFromGap(gapMs: number | null): PredictionMarketStrategyLatencyState {
  if (gapMs == null) return 'fresh'
  if (gapMs <= 10_000) return 'fresh'
  if (gapMs <= 60_000) return 'lagging'
  return 'stale'
}

function buildBaseResolutionAnomalies(input: PredictionMarketStrategyRegimeInput): PredictionMarketStrategyResolutionAnomaly[] {
  const asOfMs = resolveAsOfMs(input.as_of_at, input.snapshot.captured_at)
  const snapshot = input.snapshot
  const policy = input.resolution_policy
  const hoursToResolution = getHoursToResolution(snapshot, asOfMs)
  const basePrice = getSnapshotPriceYes(snapshot)
  const spreadBps = getSnapshotSpreadBps(snapshot)
  const quoteAgeMs = getSnapshotQuoteAgeMs(snapshot, asOfMs)
  const signals = collectResearchSignals(input)
  const signalRefs = uniqueStrings([
    ...(input.research_sidecar?.evidence_packets ?? []).map((packet) => packet.evidence_id),
    ...(signals.map((signal) => signal.signal_id)),
    ...(input.research_bridge?.evidence_refs ?? []),
  ])

  const anomalies: PredictionMarketStrategyResolutionAnomaly[] = []
  const baseSummaryParts = [
    `market=${snapshot.market.market_id}`,
    hoursToResolution != null ? `hours_to_resolution=${hoursToResolution.toFixed(2)}` : 'hours_to_resolution=unknown',
    spreadBps != null ? `spread_bps=${spreadBps.toFixed(2)}` : 'spread_bps=unknown',
    basePrice != null ? `price_yes=${basePrice.toFixed(4)}` : 'price_yes=unknown',
  ]

  if (policy?.status === 'blocked') {
    anomalies.push({
      read_only: true,
      anomaly_id: `resolution:${snapshot.market.market_id}:policy_blocked`,
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      anomaly_kind: 'policy_blocked',
      severity: 'critical',
      watch_kind: 'defense',
      score: 0.98,
      hours_to_resolution: hoursToResolution != null ? round(hoursToResolution) : null,
      summary: `${baseSummaryParts.join(' ')}; resolution policy is blocked.`,
      reasons: uniqueStrings([
        'resolution_policy_status_blocked',
        ...(policy.reasons ?? []),
      ]),
      signal_refs: signalRefs,
    })
  }

  if (policy?.status === 'ambiguous' || policy?.manual_review_required) {
    anomalies.push({
      read_only: true,
      anomaly_id: `resolution:${snapshot.market.market_id}:policy_ambiguity`,
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      anomaly_kind: 'policy_ambiguity',
      severity: policy?.manual_review_required ? 'high' : 'medium',
      watch_kind: 'watch',
      score: policy?.manual_review_required ? 0.86 : 0.72,
      hours_to_resolution: hoursToResolution != null ? round(hoursToResolution) : null,
      summary: `${baseSummaryParts.join(' ')}; resolution policy is ambiguous or requires review.`,
      reasons: uniqueStrings([
        'resolution_policy_requires_review',
        ...(policy?.reasons ?? []),
      ]),
      signal_refs: signalRefs,
    })
  }

  const attackSignals = signals.filter((signal) => hasAnyKeyword(researchSignalText(signal), ATTACK_KEYWORDS))
  if (attackSignals.length > 0) {
    anomalies.push({
      read_only: true,
      anomaly_id: `resolution:${snapshot.market.market_id}:attack_watch`,
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      anomaly_kind: 'attack_watch',
      severity: 'high',
      watch_kind: 'watch',
      score: 0.84,
      hours_to_resolution: hoursToResolution != null ? round(hoursToResolution) : null,
      summary: `${baseSummaryParts.join(' ')}; research signals mention resolution attack pressure.`,
      reasons: uniqueStrings([
        'attack_keyword_match',
        ...attackSignals.map((signal) => signal.signal_id),
      ]),
      signal_refs: attackSignals.map((signal) => signal.signal_id),
    })
  }

  const snipingSignals = signals.filter((signal) => hasAnyKeyword(researchSignalText(signal), SNIPING_KEYWORDS))
  if (snipingSignals.length > 0 || (hoursToResolution != null && hoursToResolution <= 72 && spreadBps != null && spreadBps >= 75)) {
    const score = snipingSignals.length > 0 ? 0.76 : 0.64
    anomalies.push({
      read_only: true,
      anomaly_id: `resolution:${snapshot.market.market_id}:sniping_watch`,
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      anomaly_kind: 'sniping_watch',
      severity: hoursToResolution != null && hoursToResolution <= 24 ? 'high' : 'medium',
      watch_kind: 'watch',
      score,
      hours_to_resolution: hoursToResolution != null ? round(hoursToResolution) : null,
      summary: `${baseSummaryParts.join(' ')}; resolution sniping window is open or approaching.`,
      reasons: uniqueStrings([
        hoursToResolution != null && hoursToResolution <= 72 ? 'near_resolution_window' : null,
        ...(snipingSignals.length > 0 ? snipingSignals.map((signal) => signal.signal_id) : []),
      ]),
      signal_refs: snipingSignals.map((signal) => signal.signal_id),
    })
  }

  if (input.market_graph) {
    const groups = input.market_graph.comparable_groups.filter((group) => group.market_ids.includes(snapshot.market.market_id))
    for (const group of groups) {
      const groupReasons = uniqueStrings([
        group.manual_review_required ? 'group_manual_review_required' : null,
        group.compatible_resolution ? null : 'group_resolution_incompatible',
        group.desalignment_dimensions.includes('resolution') ? 'group_resolution_desalignment' : null,
        group.narrative_risk_flags.includes('manual_review_required') ? 'group_narrative_manual_review' : null,
        group.narrative_risk_flags.includes('not_compatible') ? 'group_narrative_incompatibility' : null,
      ])
      if (groupReasons.length === 0) continue

      anomalies.push({
        read_only: true,
        anomaly_id: `resolution:${snapshot.market.market_id}:graph_${group.group_id}`,
        market_id: snapshot.market.market_id,
        venue: snapshot.venue,
        anomaly_kind: 'graph_misalignment',
        severity: group.manual_review_required ? 'high' : 'medium',
        watch_kind: group.manual_review_required ? 'defense' : 'watch',
        score: group.manual_review_required ? 0.8 : 0.62,
        hours_to_resolution: hoursToResolution != null ? round(hoursToResolution) : null,
        summary: `${baseSummaryParts.join(' ')}; comparable market graph shows resolution misalignment.`,
        reasons: groupReasons,
        signal_refs: signalRefs,
      })
    }
  }

  if (input.cross_venue_summary?.blocking_reasons?.length) {
    const crossVenueReasons = input.cross_venue_summary.blocking_reasons.filter((reason) =>
      reason.includes('resolution') || reason.includes('time_horizon') || reason.includes('manual_review'),
    )
    if (crossVenueReasons.length > 0) {
      anomalies.push({
        read_only: true,
        anomaly_id: `resolution:${snapshot.market.market_id}:cross_venue_mismatch`,
        market_id: snapshot.market.market_id,
        venue: snapshot.venue,
        anomaly_kind: 'cross_venue_resolution_mismatch',
        severity: 'medium',
        watch_kind: 'analysis',
        score: 0.58,
        hours_to_resolution: hoursToResolution != null ? round(hoursToResolution) : null,
        summary: `${baseSummaryParts.join(' ')}; cross-venue comparison shows resolution mismatch pressure.`,
        reasons: crossVenueReasons,
        signal_refs: signalRefs,
      })
    }
  }

  if (quoteAgeMs != null && quoteAgeMs >= 5 * 60_000 && hoursToResolution != null && hoursToResolution <= 48) {
    anomalies.push({
      read_only: true,
      anomaly_id: `resolution:${snapshot.market.market_id}:stale_quote_near_resolution`,
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      anomaly_kind: 'horizon_drift',
      severity: 'medium',
      watch_kind: 'watch',
      score: 0.55,
      hours_to_resolution: round(hoursToResolution),
      summary: `${baseSummaryParts.join(' ')}; stale quote data is arriving near the resolution window.`,
      reasons: uniqueStrings(['stale_quote_near_resolution', `quote_age_ms:${quoteAgeMs}`]),
      signal_refs: signalRefs,
    })
  }

  return anomalies
    .sort((left, right) => {
      const severityRank = (severity: PredictionMarketStrategyResolutionAnomaly['severity']): number => {
        switch (severity) {
          case 'critical':
            return 4
          case 'high':
            return 3
          case 'medium':
            return 2
          case 'low':
            return 1
        }
      }
      const bySeverity = severityRank(right.severity) - severityRank(left.severity)
      if (bySeverity !== 0) return bySeverity
      if (right.score !== left.score) return right.score - left.score
      return left.anomaly_id.localeCompare(right.anomaly_id)
    })
}

function graphNodeQuoteAgeMs(
  node: PredictionMarketMarketGraph['nodes'][number],
  asOfMs: number,
): number | null {
  const metadata = node.metadata as Record<string, unknown>
  const direct = maybeNumber(metadata.quote_age_ms ?? metadata.staleness_ms)
  if (direct != null) return Math.max(0, Math.round(direct))

  const timestamp = maybeString(metadata.fetched_at ?? metadata.captured_at ?? metadata.updated_at)
  if (timestamp) {
    const parsed = Date.parse(timestamp)
    if (Number.isFinite(parsed)) {
      return Math.max(0, asOfMs - parsed)
    }
  }

  return null
}

function graphNodeSpreadBps(node: PredictionMarketMarketGraph['nodes'][number]): number | null {
  const metadata = node.metadata as Record<string, unknown>
  const spread = maybeNumber(metadata.spread_bps)
  return spread != null ? Math.max(0, spread) : null
}

function graphNodeLiquidityUsd(node: PredictionMarketMarketGraph['nodes'][number]): number | null {
  const metadata = node.metadata as Record<string, unknown>
  const liquidity = maybeNumber(metadata.liquidity_usd)
  return liquidity != null ? Math.max(0, liquidity) : maybeNumber(node.liquidity) ?? null
}

function graphNodePriceYes(node: PredictionMarketMarketGraph['nodes'][number]): number | null {
  return maybeNumber(node.price_yes)
}

function deriveGraphReferences(
  input: PredictionMarketStrategyRegimeInput,
  asOfMs: number,
): PredictionMarketStrategyLatencyReference[] {
  if (!input.market_graph) return []

  const snapshot = input.snapshot
  const basePrice = getSnapshotPriceYes(snapshot)
  const baseAgeMs = getSnapshotQuoteAgeMs(snapshot, asOfMs)
  const references: PredictionMarketStrategyLatencyReference[] = []

  for (const node of input.market_graph.nodes) {
    if (node.market_id === snapshot.market.market_id) continue
    const priceYes = graphNodePriceYes(node)
    const quoteAgeMs = graphNodeQuoteAgeMs(node, asOfMs)
    const spreadBps = graphNodeSpreadBps(node)
    const liquidityUsd = graphNodeLiquidityUsd(node)
    const freshnessGapMs = baseAgeMs != null && quoteAgeMs != null
      ? Math.max(0, baseAgeMs - quoteAgeMs)
      : null
    const priceGapBps = basePrice != null && priceYes != null
      ? Math.abs(basePrice - priceYes) * 10_000
      : 0
    const liquidityScore = liquidityUsd != null ? clamp(liquidityUsd / 100_000, 0, 1) : 0.35
    const freshnessScore = quoteAgeMs != null ? clamp(1 - (quoteAgeMs / 300_000), 0, 1) : 0.45
    const spreadScore = spreadBps != null ? clamp(1 - (spreadBps / 200), 0, 1) : 0.5
    const referenceScore = round(
      clamp(
        (0.4 * freshnessScore) +
          (0.35 * liquidityScore) +
          (0.25 * spreadScore) +
          (priceGapBps > 0 ? clamp(priceGapBps / 300, 0, 1) * 0.1 : 0),
        0,
        1,
      ),
    )

    references.push({
      read_only: true,
      reference_id: `latref:${snapshot.market.market_id}:${node.market_id}:graph`,
      market_id: node.market_id,
      venue: node.venue,
      source: 'graph_node',
      role: node.role === 'reference' ? 'anchor' : 'comparison',
      price_yes: priceYes,
      spread_bps: spreadBps,
      quote_age_ms: quoteAgeMs,
      freshness_gap_ms: freshnessGapMs,
      liquidity_usd: liquidityUsd,
      reference_score: referenceScore,
      summary: `${node.market_id} from graph is a ${node.role} reference for ${snapshot.market.market_id}.`,
      reasons: uniqueStrings([
        node.canonical_event_id ? `canonical_event_id:${node.canonical_event_id}` : null,
        priceGapBps > 0 ? `price_gap_bps:${priceGapBps.toFixed(2)}` : null,
        freshnessGapMs != null ? `freshness_gap_ms:${freshnessGapMs}` : null,
      ]),
    })
  }

  return references
}

function deriveRelatedSnapshotReferences(
  input: PredictionMarketStrategyRegimeInput,
  asOfMs: number,
): PredictionMarketStrategyLatencyReference[] {
  const snapshot = input.snapshot
  const basePrice = getSnapshotPriceYes(snapshot)
  const baseAgeMs = getSnapshotQuoteAgeMs(snapshot, asOfMs)
  const references: PredictionMarketStrategyLatencyReference[] = []

  for (const related of input.related_snapshots ?? []) {
    if (related.market.market_id === snapshot.market.market_id) continue

    const priceYes = getSnapshotPriceYes(related)
    const quoteAgeMs = getSnapshotQuoteAgeMs(related, asOfMs)
    const spreadBps = getSnapshotSpreadBps(related)
    const liquidityUsd = related.market.liquidity_usd ?? related.book?.depth_near_touch ?? null
    const freshnessGapMs = baseAgeMs != null && quoteAgeMs != null
      ? Math.max(0, baseAgeMs - quoteAgeMs)
      : null
    const priceGapBps = basePrice != null && priceYes != null
      ? Math.abs(basePrice - priceYes) * 10_000
      : 0
    const referenceScore = round(
      clamp(
        (quoteAgeMs != null ? clamp(1 - (quoteAgeMs / 300_000), 0, 1) * 0.5 : 0.2) +
          (liquidityUsd != null ? clamp(liquidityUsd / 100_000, 0, 1) * 0.3 : 0.15) +
          (priceGapBps > 0 ? clamp(priceGapBps / 250, 0, 1) * 0.2 : 0.05),
        0,
        1,
      ),
    )

    references.push({
      read_only: true,
      reference_id: `latref:${snapshot.market.market_id}:${related.market.market_id}:snapshot`,
      market_id: related.market.market_id,
      venue: related.venue,
      source: 'related_snapshot',
      role: 'reference',
      price_yes: priceYes,
      spread_bps: spreadBps,
      quote_age_ms: quoteAgeMs,
      freshness_gap_ms: freshnessGapMs,
      liquidity_usd: liquidityUsd != null ? Math.max(0, liquidityUsd) : null,
      reference_score: referenceScore,
      summary: `${related.market.market_id} is a related snapshot reference for ${snapshot.market.market_id}.`,
      reasons: uniqueStrings([
        related.market.venue === snapshot.venue ? 'same_venue_reference' : 'cross_venue_reference',
        priceGapBps > 0 ? `price_gap_bps:${priceGapBps.toFixed(2)}` : null,
        freshnessGapMs != null ? `freshness_gap_ms:${freshnessGapMs}` : null,
      ]),
    })
  }

  return references
}

function deriveCrossVenueCandidateReference(
  input: PredictionMarketStrategyRegimeInput,
): PredictionMarketStrategyLatencyReference[] {
  const candidate = input.cross_venue_summary?.highest_confidence_candidate
  if (!candidate) return []

  const marketId = input.snapshot.market.market_id
  const references: PredictionMarketStrategyLatencyReference[] = []
  const entries: Array<{
    ref: CrossVenueArbitrageCandidate['buy_ref'] | CrossVenueArbitrageCandidate['sell_ref']
    price_yes: number
    role: 'anchor' | 'reference'
  }> = []

  if (candidate.buy_ref.market_id !== marketId) {
    entries.push({ ref: candidate.buy_ref, price_yes: candidate.buy_price_yes, role: 'reference' })
  }
  if (candidate.sell_ref.market_id !== marketId) {
    entries.push({ ref: candidate.sell_ref, price_yes: candidate.sell_price_yes, role: 'reference' })
  }

  for (const entry of entries) {
    references.push({
      read_only: true,
      reference_id: `latref:${marketId}:${entry.ref.market_id}:cross_venue`,
      market_id: entry.ref.market_id,
      venue: entry.ref.venue,
      source: 'cross_venue_candidate',
      role: entry.role,
      price_yes: entry.price_yes,
      spread_bps: Math.abs(candidate.gross_spread_bps),
      quote_age_ms: null,
      freshness_gap_ms: null,
      liquidity_usd: null,
      reference_score: round(clamp(candidate.confidence_score, 0, 1)),
      summary: `Cross-venue candidate ${candidate.canonical_event_key} provides a latency reference.`,
      reasons: uniqueStrings([
        `opportunity_type:${candidate.opportunity_type}`,
        `gross_spread_bps:${candidate.gross_spread_bps.toFixed(2)}`,
        `net_spread_bps:${candidate.net_spread_bps.toFixed(2)}`,
      ]),
    })
  }

  return references
}

export function deriveLatencyReferences(
  input: PredictionMarketStrategyRegimeInput,
): PredictionMarketStrategyLatencyReference[] {
  const asOfMs = resolveAsOfMs(input.as_of_at, input.snapshot.captured_at)
  const baseReference: PredictionMarketStrategyLatencyReference = {
    read_only: true,
    reference_id: `latref:${input.snapshot.market.market_id}:base`,
    market_id: input.snapshot.market.market_id,
    venue: input.snapshot.venue,
    source: 'base_snapshot',
    role: 'anchor',
    price_yes: getSnapshotPriceYes(input.snapshot),
    spread_bps: getSnapshotSpreadBps(input.snapshot),
    quote_age_ms: getSnapshotQuoteAgeMs(input.snapshot, asOfMs),
    freshness_gap_ms: 0,
    liquidity_usd: input.snapshot.market.liquidity_usd ?? input.snapshot.book?.depth_near_touch ?? null,
    reference_score: 1,
    summary: `Primary market snapshot for ${input.snapshot.market.market_id}.`,
    reasons: uniqueStrings([
      `question_key:${getMarketQuestionKey(input.snapshot.market.question)}`,
      input.snapshot.market.venue_type ? `venue_type:${input.snapshot.market.venue_type}` : null,
    ]),
  }

  const references = [
    baseReference,
    ...deriveRelatedSnapshotReferences(input, asOfMs),
    ...deriveGraphReferences(input, asOfMs),
    ...deriveCrossVenueCandidateReference(input),
  ]

  const seen = new Set<string>()
  const out: PredictionMarketStrategyLatencyReference[] = []
  for (const reference of references) {
    if (seen.has(reference.reference_id)) continue
    seen.add(reference.reference_id)
    out.push(reference)
  }

  return out.sort((left, right) => {
    if (right.reference_score !== left.reference_score) {
      return right.reference_score - left.reference_score
    }
    const rightFreshness = right.quote_age_ms ?? Number.MAX_SAFE_INTEGER
    const leftFreshness = left.quote_age_ms ?? Number.MAX_SAFE_INTEGER
    if (rightFreshness !== leftFreshness) return rightFreshness - leftFreshness
    return left.reference_id.localeCompare(right.reference_id)
  })
}

function resolutionStateFromAnomalies(
  anomalies: readonly PredictionMarketStrategyResolutionAnomaly[],
  hoursToResolution: number | null,
  policy?: ResolutionPolicy | null,
): PredictionMarketStrategyResolutionState {
  if (policy?.status === 'blocked') return 'anomalous'
  if (anomalies.some((anomaly) => anomaly.severity === 'critical' || anomaly.anomaly_kind === 'policy_blocked')) {
    return 'anomalous'
  }
  if (
    anomalies.some((anomaly) => anomaly.severity === 'high' || anomaly.watch_kind !== 'analysis') ||
    (hoursToResolution != null && hoursToResolution <= 72)
  ) {
    return 'watch'
  }
  return 'clear'
}

function latencyGapFromReferences(references: readonly PredictionMarketStrategyLatencyReference[]): number | null {
  const sorted = [...references]
    .filter((reference) => reference.source !== 'base_snapshot')
    .sort((left, right) => right.reference_score - left.reference_score)

  const best = sorted[0]
  if (!best) return null
  if (best.freshness_gap_ms == null) return null
  return best.freshness_gap_ms
}

function signalStrengthFromRegime(input: {
  spreadBps: number | null
  quoteAgeMs: number | null
  anomalyCount: number
  referenceCount: number
  signalCount: number
  researchState: PredictionMarketStrategyResearchState
}): number {
  const spreadComponent = input.spreadBps == null ? 0.5 : clamp(input.spreadBps / 200, 0, 1)
  const freshnessComponent = input.quoteAgeMs == null ? 0.45 : clamp(1 - (input.quoteAgeMs / 600_000), 0, 1)
  const anomalyPenalty = clamp(input.anomalyCount / 5, 0, 1)
  const referenceComponent = clamp(input.referenceCount / 6, 0, 1)
  const researchComponent = input.researchState === 'supportive'
    ? 1
    : input.researchState === 'mixed'
      ? 0.6
      : 0.35
  const signalComponent = clamp(input.signalCount / 8, 0, 1)

  return round(
    clamp(
      (0.26 * spreadComponent) +
        (0.22 * freshnessComponent) +
        (0.18 * referenceComponent) +
        (0.16 * researchComponent) +
        (0.1 * signalComponent) -
        (0.08 * anomalyPenalty),
      0,
      1,
    ),
  )
}

export function deriveResolutionAnomalies(
  input: PredictionMarketStrategyRegimeInput,
): PredictionMarketStrategyResolutionAnomaly[] {
  const asOfMs = resolveAsOfMs(input.as_of_at, input.snapshot.captured_at)
  const anomalies = buildBaseResolutionAnomalies(input)
  const market = input.snapshot.market
  const hoursToResolution = getHoursToResolution(input.snapshot, asOfMs)
  const quoteAgeMs = getSnapshotQuoteAgeMs(input.snapshot, asOfMs)
  const spreadBps = getSnapshotSpreadBps(input.snapshot)

  if (hoursToResolution != null && hoursToResolution <= 24) {
    anomalies.push({
      read_only: true,
      anomaly_id: `resolution:${market.market_id}:near_resolution_window`,
      market_id: market.market_id,
      venue: input.snapshot.venue,
      anomaly_kind: 'horizon_drift',
      severity: 'medium',
      watch_kind: 'watch',
      score: 0.62,
      hours_to_resolution: round(hoursToResolution),
      summary: `Market ${market.market_id} is inside the near-resolution window.`,
      reasons: uniqueStrings([
        'resolution_window_under_24h',
        spreadBps != null ? `spread_bps:${spreadBps.toFixed(2)}` : null,
      ]),
      signal_refs: uniqueStrings([
        ...(input.research_sidecar?.evidence_packets ?? []).map((packet) => packet.evidence_id),
      ]),
    })
  }

  if (quoteAgeMs != null && quoteAgeMs >= 5 * 60_000 && (hoursToResolution == null || hoursToResolution <= 72)) {
    anomalies.push({
      read_only: true,
      anomaly_id: `resolution:${market.market_id}:stale_quote_window`,
      market_id: market.market_id,
      venue: input.snapshot.venue,
      anomaly_kind: 'horizon_drift',
      severity: 'medium',
      watch_kind: 'watch',
      score: 0.58,
      hours_to_resolution: hoursToResolution != null ? round(hoursToResolution) : null,
      summary: `Stale quotes are persisting near the resolution window for ${market.market_id}.`,
      reasons: uniqueStrings([
        `quote_age_ms:${quoteAgeMs}`,
        hoursToResolution != null ? `hours_to_resolution:${hoursToResolution.toFixed(2)}` : null,
      ]),
      signal_refs: uniqueStrings([
        ...(input.research_bridge?.evidence_refs ?? []),
      ]),
    })
  }

  return anomalies
    .sort((left, right) => {
      const severityRank = (severity: PredictionMarketStrategyResolutionAnomaly['severity']): number => {
        switch (severity) {
          case 'critical':
            return 4
          case 'high':
            return 3
          case 'medium':
            return 2
          case 'low':
            return 1
        }
      }
      const bySeverity = severityRank(right.severity) - severityRank(left.severity)
      if (bySeverity !== 0) return bySeverity
      if (right.score !== left.score) return right.score - left.score
      return left.anomaly_id.localeCompare(right.anomaly_id)
    })
}

export function deriveMarketRegime(
  input: PredictionMarketStrategyRegimeInput & {
    resolution_anomalies?: readonly PredictionMarketStrategyResolutionAnomaly[]
    latency_references?: readonly PredictionMarketStrategyLatencyReference[]
  },
): PredictionMarketStrategyMarketRegime {
  const asOfMs = resolveAsOfMs(input.as_of_at, input.snapshot.captured_at)
  const spreadBps = getSnapshotSpreadBps(input.snapshot)
  const quoteAgeMs = getSnapshotQuoteAgeMs(input.snapshot, asOfMs)
  const hoursToResolution = getHoursToResolution(input.snapshot, asOfMs)
  const liquidityUsd = input.snapshot.market.liquidity_usd ?? input.snapshot.book?.depth_near_touch ?? null
  const priceState = priceStateFromSpread(spreadBps)
  const freshnessState = freshnessStateFromAge(quoteAgeMs)
  const anomalies = [...(input.resolution_anomalies ?? deriveResolutionAnomalies(input))]
  const latencyReferences = [...(input.latency_references ?? deriveLatencyReferences(input))]
  const bestReferenceGapMs = latencyGapFromReferences(latencyReferences)
  const latencyState = latencyStateFromGap(bestReferenceGapMs)
  const researchSummary = researchSummaryState(input, collectResearchSignals(input).length)
  const researchState = researchSummary.state
  const resolutionState = resolutionStateFromAnomalies(anomalies, hoursToResolution, input.resolution_policy)
  const crossVenueManualReviewCount = input.cross_venue_summary?.manual_review?.length ?? 0
  const crossVenueBlockingCount = input.cross_venue_summary?.blocking_reasons?.length ?? 0
  const microstructureSeverity: MicrostructureSeverity | null = input.microstructure_lab?.summary.worst_case_severity ?? null

  let disposition: PredictionMarketStrategyRegimeDisposition = 'calm'
  if (
    resolutionState === 'anomalous' ||
    (freshnessState === 'stale' && latencyState === 'stale') ||
    input.resolution_policy?.status === 'blocked'
  ) {
    disposition = 'defense'
  } else if (
    resolutionState === 'watch' ||
    researchState === 'abstain' ||
    priceState === 'dislocated' ||
    crossVenueManualReviewCount > 0 ||
    crossVenueBlockingCount > 0
  ) {
    disposition = 'watch'
  } else if (priceState === 'wide' || freshnessState === 'warm' || latencyState === 'lagging' || microstructureSeverity === 'high' || microstructureSeverity === 'critical') {
    disposition = 'stress'
  }

  const anomalyKinds = anomalies.map((anomaly) => anomaly.anomaly_kind)
  const keySignals = uniqueStrings([
    `spread_bps:${spreadBps != null ? spreadBps.toFixed(2) : 'unknown'}`,
    `freshness_state:${freshnessState}`,
    `price_state:${priceState}`,
    `resolution_state:${resolutionState}`,
    `research_state:${researchState}`,
    `latency_state:${latencyState}`,
    hoursToResolution != null ? `hours_to_resolution:${hoursToResolution.toFixed(2)}` : null,
    microstructureSeverity ? `microstructure_severity:${microstructureSeverity}` : null,
    crossVenueManualReviewCount > 0 ? `cross_venue_manual_review:${crossVenueManualReviewCount}` : null,
  ])

  const researchSignals = collectResearchSignals(input)
  const signalStrength = signalStrengthFromRegime({
    spreadBps,
    quoteAgeMs,
    anomalyCount: anomalies.length,
    referenceCount: latencyReferences.length,
    signalCount: researchSignals.length,
    researchState,
  })

  const confidenceScore = round(
    clamp(
      (0.35 * signalStrength) +
        (0.2 * clamp(latencyReferences.length / 6, 0, 1)) +
        (0.2 * clamp(researchSignals.length / 8, 0, 1)) +
        (0.25 * (resolutionState === 'clear' ? 1 : resolutionState === 'watch' ? 0.6 : 0.25)),
      0,
      1,
    ),
  )

  const stress_level: PredictionMarketStrategyMarketRegime['stress_level'] =
    disposition === 'defense'
      ? 'critical'
      : disposition === 'watch'
        ? anomalyKinds.length > 2 || freshnessState === 'stale' ? 'high' : 'medium'
        : disposition === 'stress'
          ? 'medium'
          : 'low'

  const summary = [
    `${input.snapshot.market.market_id} is in ${disposition} regime`,
    `price=${priceState}`,
    `freshness=${freshnessState}`,
    `resolution=${resolutionState}`,
    `research=${researchState}`,
    `latency=${latencyState}`,
  ].join('; ')

  const reasons = uniqueStrings([
    ...(anomalies.length > 0 ? [`resolution_anomalies:${anomalies.length}`] : []),
    ...(latencyReferences.length > 0 ? [`latency_references:${latencyReferences.length}`] : []),
    ...(researchState === 'abstain' ? ['research_abstention'] : []),
    ...researchSummary.reasons,
    ...(priceState === 'dislocated' ? ['price_dislocated'] : []),
    ...(freshnessState === 'stale' ? ['snapshot_stale'] : []),
    ...(crossVenueBlockingCount > 0 ? ['cross_venue_blocking_reasons'] : []),
  ])

  return {
    read_only: true,
    regime_id: `regime:${input.snapshot.market.market_id}:${input.snapshot.captured_at}`,
    market_id: input.snapshot.market.market_id,
    venue: input.snapshot.venue,
    generated_at: input.as_of_at ?? input.snapshot.captured_at ?? nowIso(),
    disposition,
    price_state: priceState,
    freshness_state: freshnessState,
    resolution_state: resolutionState,
    research_state: researchState,
    latency_state: latencyState,
    stress_level,
    signal_strength: signalStrength,
    confidence_score: confidenceScore,
    hours_to_resolution: hoursToResolution != null ? round(hoursToResolution) : null,
    price_spread_bps: spreadBps != null ? round(spreadBps) : null,
    quote_age_ms: nonNegativeMs(quoteAgeMs),
    liquidity_usd: liquidityUsd != null ? Math.max(0, liquidityUsd) : null,
    anomaly_count: anomalies.length,
    anomaly_kinds: anomalyKinds,
    latency_reference_count: latencyReferences.length,
    key_signals: keySignals,
    reasons,
    summary,
  }
}
