import {
  type MarketSnapshot,
  type PredictionMarketMarketGraph,
  type PredictionMarketVenue,
  type PredictionMarketVenueType,
} from '@/lib/prediction-markets/schemas'
import {
  type PredictionMarketStrategyLatencyReference,
  type PredictionMarketStrategyMarketRegime,
  type PredictionMarketStrategyRegimeInput,
  type PredictionMarketStrategyResolutionAnomaly,
  deriveLatencyReferences,
  deriveMarketRegime,
  deriveResolutionAnomalies,
} from '@/lib/prediction-markets/strategy-regime'
import {
  buildShadowStrategyWatchlist,
  summarizeShadowStrategyWatchlist,
  type PredictionMarketShadowStrategyWatch,
  type PredictionMarketShadowStrategyWatchSummary,
} from '@/lib/prediction-markets/strategy-shadow'

export type PredictionMarketStrategyCandidateKind =
  | 'intramarket_parity'
  | 'maker_spread_capture'
  | 'latency_reference_spread'
  | 'logical_constraint_arb'
  | 'negative_risk_basket'
  | 'resolution_attack_watch'
  | 'resolution_sniping_watch'
  | 'autonomous_agent_advisory'

export type PredictionMarketStrategyDisposition =
  | 'advisory'
  | 'watch'
  | 'defense'

export type PredictionMarketStrategyCandidateSeverity =
  | 'low'
  | 'medium'
  | 'high'
  | 'critical'

export type PredictionMarketStrategyCandidateMetricValue = number | string | boolean | null

export type PredictionMarketStrategyCandidate = {
  read_only: true
  candidate_id: string
  kind: PredictionMarketStrategyCandidateKind
  disposition: PredictionMarketStrategyDisposition
  market_id: string | null
  venue: PredictionMarketVenue | null
  canonical_event_id: string | null
  group_id: string | null
  related_market_ids: string[]
  severity: PredictionMarketStrategyCandidateSeverity
  signal_score: number
  confidence_score: number
  summary: string
  reasons: string[]
  evidence_refs: string[]
  metrics: Record<string, PredictionMarketStrategyCandidateMetricValue>
  metadata: Record<string, unknown>
}

export type PredictionMarketStrategyCountSummary = {
  read_only: true
  total: number
  by_kind: Record<PredictionMarketStrategyCandidateKind, number>
  by_disposition: Record<PredictionMarketStrategyDisposition, number>
  by_severity: Record<PredictionMarketStrategyCandidateSeverity, number>
  advisory_count: number
  watch_count: number
  defense_count: number
  summary: string
}

export type PredictionMarketStrategyDecisionMode =
  | 'inactive'
  | 'advisory'
  | 'watch'
  | 'defense'

export type PredictionMarketStrategyDetectionInput = PredictionMarketStrategyRegimeInput & {
  regime?: PredictionMarketStrategyMarketRegime | null
  resolution_anomalies?: readonly PredictionMarketStrategyResolutionAnomaly[]
  latency_references?: readonly PredictionMarketStrategyLatencyReference[]
  max_candidates?: number
  min_intramarket_parity_bps?: number
  min_maker_spread_capture_bps?: number
  min_latency_reference_spread_bps?: number
  min_latency_reference_freshness_gap_ms?: number
  min_logical_constraint_gap_bps?: number
  min_negative_risk_gap_bps?: number
}

export type PredictionMarketStrategyDecision = {
  read_only: true
  decision_id: string
  generated_at: string
  market_id: string
  venue: PredictionMarketVenue
  mode: PredictionMarketStrategyDecisionMode
  regime: PredictionMarketStrategyMarketRegime
  candidate_count: number
  primary_candidate_id: string | null
  primary_candidate_kind: PredictionMarketStrategyCandidateKind | null
  primary_candidate_summary: string | null
  counts: PredictionMarketStrategyCountSummary
  candidates: PredictionMarketStrategyCandidate[]
  summary: string
  reasons: string[]
  shadow_watch_summary: PredictionMarketShadowStrategyWatchSummary
}

type ComparableGroup = PredictionMarketMarketGraph['comparable_groups'][number]
type GraphNode = PredictionMarketMarketGraph['nodes'][number]

type StrategyComparableFrame = {
  market_id: string
  venue: PredictionMarketVenue
  venue_type: PredictionMarketVenueType | null
  question: string
  question_key: string
  price_yes: number | null
  spread_bps: number | null
  quote_age_ms: number | null
  liquidity_usd: number | null
  active: boolean
  closed: boolean
  role: 'base' | 'related' | 'graph'
  group_ids: string[]
  canonical_event_ids: string[]
  evidence_refs: string[]
  source_kinds: Array<'snapshot' | 'graph_node'>
}

function nowIso(): string {
  return new Date().toISOString()
}

function resolveAsOfMs(value?: string): number {
  if (!value) return Date.now()
  const parsed = Date.parse(value)
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

function clampProbability(value: number): number {
  return clamp(value, 0, 1)
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

function questionKey(value: string): string {
  return tokenize(value).slice(0, 12).join(' ')
}

function maybeNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function maybeString(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null
}

function snapshotPriceYes(snapshot: MarketSnapshot): number | null {
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
      return clampProbability(value)
    }
  }

  return null
}

function snapshotSpreadBps(snapshot: MarketSnapshot): number | null {
  if (typeof snapshot.spread_bps === 'number' && Number.isFinite(snapshot.spread_bps)) {
    return Math.max(0, snapshot.spread_bps)
  }

  if (snapshot.best_bid_yes != null && snapshot.best_ask_yes != null) {
    return Math.max(0, (snapshot.best_ask_yes - snapshot.best_bid_yes) * 10_000)
  }

  return null
}

function snapshotQuoteAgeMs(snapshot: MarketSnapshot, asOfMs: number): number | null {
  const observedAt = snapshot.book?.fetched_at ?? snapshot.captured_at
  const parsed = Date.parse(observedAt)
  if (!Number.isFinite(parsed)) return null
  return Math.max(0, asOfMs - parsed)
}

function graphNodePriceYes(node: GraphNode): number | null {
  return maybeNumber(node.price_yes)
}

function graphNodeSpreadBps(node: GraphNode): number | null {
  const metadata = node.metadata as Record<string, unknown>
  return maybeNumber(metadata.spread_bps)
}

function graphNodeQuoteAgeMs(node: GraphNode, asOfMs: number): number | null {
  const metadata = node.metadata as Record<string, unknown>
  const direct = maybeNumber(metadata.quote_age_ms ?? metadata.staleness_ms)
  if (direct != null) return Math.max(0, Math.round(direct))

  const timestamp = maybeString(metadata.fetched_at ?? metadata.captured_at ?? metadata.updated_at)
  if (timestamp) {
    const parsed = Date.parse(timestamp)
    if (Number.isFinite(parsed)) return Math.max(0, asOfMs - parsed)
  }

  return null
}

function graphNodeLiquidityUsd(node: GraphNode): number | null {
  const metadata = node.metadata as Record<string, unknown>
  const direct = maybeNumber(metadata.liquidity_usd)
  if (direct != null) return Math.max(0, direct)
  const rawLiquidity = maybeNumber(node.liquidity)
  return rawLiquidity != null ? Math.max(0, rawLiquidity) : null
}

function graphNodeFrame(node: GraphNode, asOfMs: number): StrategyComparableFrame {
  return {
    market_id: node.market_id,
    venue: node.venue,
    venue_type: node.venue_type ?? null,
    question: node.question,
    question_key: questionKey(node.question),
    price_yes: graphNodePriceYes(node),
    spread_bps: graphNodeSpreadBps(node),
    quote_age_ms: graphNodeQuoteAgeMs(node, asOfMs),
    liquidity_usd: graphNodeLiquidityUsd(node),
    active: true,
    closed: node.status === 'closed',
    role: node.role === 'reference' ? 'related' : 'graph',
    group_ids: [],
    canonical_event_ids: node.canonical_event_id ? [node.canonical_event_id] : [],
    evidence_refs: node.snapshot_id ? [node.snapshot_id] : [],
    source_kinds: ['graph_node'],
  }
}

function snapshotFrame(
  snapshot: MarketSnapshot,
  role: StrategyComparableFrame['role'],
  asOfMs: number,
): StrategyComparableFrame {
  return {
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    venue_type: snapshot.market.venue_type ?? null,
    question: snapshot.market.question,
    question_key: questionKey(snapshot.market.question),
    price_yes: snapshotPriceYes(snapshot),
    spread_bps: snapshotSpreadBps(snapshot),
    quote_age_ms: snapshotQuoteAgeMs(snapshot, asOfMs),
    liquidity_usd: snapshot.market.liquidity_usd ?? snapshot.book?.depth_near_touch ?? null,
    active: snapshot.market.active,
    closed: snapshot.market.closed,
    role,
    group_ids: [],
    canonical_event_ids: [],
    evidence_refs: uniqueStrings([
      snapshot.book?.fetched_at ?? null,
      snapshot.captured_at,
    ]),
    source_kinds: ['snapshot'],
  }
}

function mergeFrame(target: StrategyComparableFrame, source: StrategyComparableFrame): StrategyComparableFrame {
  return {
    ...target,
    price_yes: target.price_yes ?? source.price_yes,
    spread_bps: target.spread_bps ?? source.spread_bps,
    quote_age_ms: target.quote_age_ms ?? source.quote_age_ms,
    liquidity_usd: target.liquidity_usd ?? source.liquidity_usd,
    active: target.active || source.active,
    closed: target.closed && source.closed,
    role: target.role === 'base' ? 'base' : source.role === 'base' ? 'base' : target.role,
    group_ids: uniqueStrings([...target.group_ids, ...source.group_ids]),
    canonical_event_ids: uniqueStrings([...target.canonical_event_ids, ...source.canonical_event_ids]),
    evidence_refs: uniqueStrings([...target.evidence_refs, ...source.evidence_refs]),
    source_kinds: uniqueStrings([...target.source_kinds, ...source.source_kinds]) as StrategyComparableFrame['source_kinds'],
  }
}

function collectComparableFrames(input: PredictionMarketStrategyDetectionInput): {
  base: StrategyComparableFrame
  frame_map: Map<string, StrategyComparableFrame>
  graph_groups: ComparableGroup[]
} {
  const asOfMs = resolveAsOfMs(input.as_of_at ?? input.snapshot.captured_at)
  const base = snapshotFrame(input.snapshot, 'base', asOfMs)
  const frameMap = new Map<string, StrategyComparableFrame>([[base.market_id, base]])

  for (const related of input.related_snapshots ?? []) {
    const next = snapshotFrame(related, 'related', asOfMs)
    const existing = frameMap.get(next.market_id)
    frameMap.set(next.market_id, existing ? mergeFrame(existing, next) : next)
  }

  for (const node of input.market_graph?.nodes ?? []) {
    const next = graphNodeFrame(node, asOfMs)
    const existing = frameMap.get(next.market_id)
    frameMap.set(next.market_id, existing ? mergeFrame(existing, next) : next)
  }

  const groups = input.market_graph?.comparable_groups ?? []
  for (const group of groups) {
    for (const marketId of group.market_ids) {
      const frame = frameMap.get(marketId)
      if (!frame) continue
      frame.group_ids = uniqueStrings([...frame.group_ids, group.group_id])
      frame.canonical_event_ids = uniqueStrings([...frame.canonical_event_ids, group.canonical_event_id])
      frameMap.set(marketId, frame)
    }
  }

  return {
    base: frameMap.get(input.snapshot.market.market_id) ?? base,
    frame_map: frameMap,
    graph_groups: groups.filter((group) => group.market_ids.includes(input.snapshot.market.market_id)),
  }
}

function severityFromScore(score: number): PredictionMarketStrategyCandidateSeverity {
  if (score >= 0.9) return 'critical'
  if (score >= 0.7) return 'high'
  if (score >= 0.45) return 'medium'
  return 'low'
}

function dispositionRank(disposition: PredictionMarketStrategyDisposition): number {
  switch (disposition) {
    case 'defense':
      return 3
    case 'watch':
      return 2
    case 'advisory':
      return 1
  }
}

function severityRank(severity: PredictionMarketStrategyCandidateSeverity): number {
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

function candidateSort(left: PredictionMarketStrategyCandidate, right: PredictionMarketStrategyCandidate): number {
  const dispositionDelta = dispositionRank(right.disposition) - dispositionRank(left.disposition)
  if (dispositionDelta !== 0) return dispositionDelta
  const severityDelta = severityRank(right.severity) - severityRank(left.severity)
  if (severityDelta !== 0) return severityDelta
  if (right.signal_score !== left.signal_score) return right.signal_score - left.signal_score
  if (right.confidence_score !== left.confidence_score) return right.confidence_score - left.confidence_score
  return left.candidate_id.localeCompare(right.candidate_id)
}

function normalizeCandidate(candidate: PredictionMarketStrategyCandidate): PredictionMarketStrategyCandidate {
  return {
    ...candidate,
    signal_score: round(clampProbability(candidate.signal_score)),
    confidence_score: round(clampProbability(candidate.confidence_score)),
    related_market_ids: uniqueStrings(candidate.related_market_ids),
    reasons: uniqueStrings(candidate.reasons),
    evidence_refs: uniqueStrings(candidate.evidence_refs),
  }
}

function normalizeMetricValue(value: unknown): PredictionMarketStrategyCandidateMetricValue {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') return value
  if (typeof value === 'boolean') return value
  if (value === null) return null
  return null
}

function normalizeMetrics(values: Record<string, unknown>): Record<string, PredictionMarketStrategyCandidateMetricValue> {
  const normalized: Record<string, PredictionMarketStrategyCandidateMetricValue> = {}
  for (const [key, value] of Object.entries(values)) {
    normalized[key] = normalizeMetricValue(value)
  }
  return normalized
}

function candidateId(kind: PredictionMarketStrategyCandidateKind, marketId: string | null, suffix: string): string {
  return `strategy:${kind}:${marketId ?? 'marketless'}:${suffix}`
}

function priceGapBps(left: number | null, right: number | null): number {
  if (left == null || right == null) return 0
  return Math.abs(left - right) * 10_000
}

function spreadThreshold(base: number, regime: PredictionMarketStrategyMarketRegime): number {
  let threshold = base
  if (regime.price_state === 'tight') threshold *= 1.12
  if (regime.price_state === 'wide') threshold *= 0.92
  if (regime.price_state === 'dislocated') threshold *= 0.85
  if (regime.freshness_state === 'stale') threshold *= 0.9
  return Math.max(1, Math.round(threshold))
}

function buildShadowCandidates(input: {
  regime: PredictionMarketStrategyMarketRegime
  watchlist: PredictionMarketShadowStrategyWatch[]
}): PredictionMarketStrategyCandidate[] {
  return input.watchlist.map((watch) =>
    normalizeCandidate({
      read_only: true,
      candidate_id: watch.watch_id,
      kind: watch.kind,
      disposition: watch.disposition,
      market_id: watch.market_id,
      venue: watch.venue,
      canonical_event_id: null,
      group_id: null,
      related_market_ids: [],
      severity: watch.severity,
      signal_score: watch.signal_score,
      confidence_score: watch.signal_score,
      summary: watch.summary,
      reasons: watch.reasons,
      evidence_refs: watch.evidence_refs,
      metrics: normalizeMetrics(watch.metadata),
      metadata: watch.metadata,
    }),
  )
}

function buildIntramarketParityCandidates(input: {
  regime: PredictionMarketStrategyMarketRegime
  base: StrategyComparableFrame
  frame_map: Map<string, StrategyComparableFrame>
  graph_groups: ComparableGroup[]
  threshold_bps: number
}): PredictionMarketStrategyCandidate[] {
  const candidates: PredictionMarketStrategyCandidate[] = []
  const basePrice = input.base.price_yes
  if (basePrice == null) return candidates

  const seen = new Set<string>()
  const groups = input.graph_groups.length > 0
    ? input.graph_groups
    : []

  const groupCandidates: Array<{
    group_id: string | null
    canonical_event_id: string | null
    related: StrategyComparableFrame
    gap_bps: number
    similarity: number
  }> = []

  for (const group of groups) {
    for (const marketId of group.market_ids) {
      if (marketId === input.base.market_id) continue
      const related = input.frame_map.get(marketId)
      if (!related || related.venue !== input.base.venue || related.price_yes == null) continue
      const similarity = jaccard(tokenize(input.base.question), tokenize(related.question))
      if (similarity < 0.35 && group.relation_kind === 'comparison') continue
      const gapBps = priceGapBps(basePrice, related.price_yes)
      if (gapBps < input.threshold_bps) continue
      groupCandidates.push({
        group_id: group.group_id,
        canonical_event_id: group.canonical_event_id,
        related,
        gap_bps: gapBps,
        similarity,
      })
    }
  }

  const fallbackRelated = [...input.frame_map.values()]
    .filter((frame) => frame.market_id !== input.base.market_id && frame.venue === input.base.venue && frame.price_yes != null)
    .map((frame) => ({
      group_id: frame.group_ids[0] ?? null,
      canonical_event_id: frame.canonical_event_ids[0] ?? null,
      related: frame,
      gap_bps: priceGapBps(basePrice, frame.price_yes),
      similarity: jaccard(tokenize(input.base.question), tokenize(frame.question)),
    }))
    .filter((candidate) => candidate.gap_bps >= input.threshold_bps && candidate.similarity >= 0.45)

  for (const item of [...groupCandidates, ...fallbackRelated].sort((left, right) => {
    if (right.gap_bps !== left.gap_bps) return right.gap_bps - left.gap_bps
    return right.similarity - left.similarity
  })) {
    const key = `${item.group_id ?? 'no-group'}:${item.related.market_id}`
    if (seen.has(key)) continue
    seen.add(key)

    const signalScore = clampProbability(
      (item.gap_bps / 400) +
        (item.similarity * 0.25) +
        (input.regime.signal_strength * 0.2),
    )

    candidates.push(normalizeCandidate({
      read_only: true,
      candidate_id: candidateId('intramarket_parity', input.base.market_id, key),
      kind: 'intramarket_parity',
      disposition: 'advisory',
      market_id: input.base.market_id,
      venue: input.base.venue,
      canonical_event_id: item.canonical_event_id,
      group_id: item.group_id,
      related_market_ids: [item.related.market_id],
      severity: severityFromScore(signalScore),
      signal_score: signalScore,
      confidence_score: clampProbability(0.45 + (item.similarity * 0.35) + (Math.min(item.gap_bps, 250) / 1000)),
      summary: `Same-venue parity gap of ${item.gap_bps.toFixed(2)} bps versus ${item.related.market_id}.`,
      reasons: uniqueStrings([
        `price_gap_bps:${item.gap_bps.toFixed(2)}`,
        `question_similarity:${item.similarity.toFixed(4)}`,
        item.group_id ? `group_id:${item.group_id}` : null,
      ]),
      evidence_refs: uniqueStrings([
        item.group_id,
        item.canonical_event_id,
        item.related.market_id,
      ]),
      metrics: {
        base_price_yes: basePrice,
        related_price_yes: item.related.price_yes,
        gap_bps: round(item.gap_bps),
        question_similarity: round(item.similarity),
        base_quote_age_ms: input.base.quote_age_ms,
        related_quote_age_ms: item.related.quote_age_ms,
        source: 'intramarket_parity',
      },
      metadata: {
        source: 'intramarket_parity',
        related_frame: item.related,
      },
    }))
  }

  return candidates.slice(0, 3)
}

function buildMakerSpreadCaptureCandidates(input: {
  regime: PredictionMarketStrategyMarketRegime
  base: StrategyComparableFrame
  min_spread_bps: number
}): PredictionMarketStrategyCandidate[] {
  const spreadBps = input.base.spread_bps
  const depthNearTouch = input.base.liquidity_usd ?? null
  const quoteAgeMs = input.base.quote_age_ms
  if (spreadBps == null || spreadBps < input.min_spread_bps) return []
  if (input.base.closed) return []
  if (input.base.active === false) return []

  const signalScore = clampProbability(
    (spreadBps / 250) +
      (depthNearTouch != null ? clamp(depthNearTouch / 100_000, 0, 1) * 0.2 : 0.05) +
      (input.regime.price_state === 'wide' ? 0.1 : 0) +
      (input.regime.price_state === 'dislocated' ? 0.15 : 0),
  )

  return [
    normalizeCandidate({
      read_only: true,
      candidate_id: candidateId('maker_spread_capture', input.base.market_id, 'single-market'),
      kind: 'maker_spread_capture',
      disposition: 'advisory',
      market_id: input.base.market_id,
      venue: input.base.venue,
      canonical_event_id: input.base.canonical_event_ids[0] ?? null,
      group_id: input.base.group_ids[0] ?? null,
      related_market_ids: [],
      severity: severityFromScore(signalScore),
      signal_score: signalScore,
      confidence_score: clampProbability(0.4 + (spreadBps / 400) + (depthNearTouch != null ? clamp(depthNearTouch / 150_000, 0, 1) * 0.2 : 0)),
      summary: `Maker spread capture candidate with ${spreadBps.toFixed(2)} bps spread on ${input.base.market_id}.`,
      reasons: uniqueStrings([
        `spread_bps:${spreadBps.toFixed(2)}`,
        input.base.quote_age_ms != null ? `quote_age_ms:${input.base.quote_age_ms}` : null,
      ]),
      evidence_refs: uniqueStrings(input.base.evidence_refs),
      metrics: {
        spread_bps: round(spreadBps),
        quote_age_ms: quoteAgeMs,
        liquidity_usd: input.base.liquidity_usd,
        source: 'maker_spread_capture',
      },
      metadata: {
        source: 'maker_spread_capture',
      },
    }),
  ]
}

function buildLatencyReferenceSpreadCandidates(input: {
  regime: PredictionMarketStrategyMarketRegime
  base: StrategyComparableFrame
  latency_references: readonly PredictionMarketStrategyLatencyReference[]
  min_spread_bps: number
  min_freshness_gap_ms: number
}): PredictionMarketStrategyCandidate[] {
  const basePrice = input.base.price_yes
  if (basePrice == null) return []

  const eligibleReferences = [...input.latency_references]
    .filter((reference) => reference.market_id !== input.base.market_id && reference.price_yes != null)
    .map((reference) => ({
      reference,
      price_gap_bps: priceGapBps(basePrice, reference.price_yes),
      freshness_gap_ms: reference.freshness_gap_ms ?? 0,
    }))
    .filter((item) =>
      item.price_gap_bps >= input.min_spread_bps &&
      (item.freshness_gap_ms === 0 ? item.reference.source === 'cross_venue_candidate' : item.freshness_gap_ms >= input.min_freshness_gap_ms),
    )

  if (eligibleReferences.length === 0) return []

  const best = eligibleReferences.sort((left, right) => {
    const leftScore = (left.price_gap_bps / 400) + (left.freshness_gap_ms / 120_000) + left.reference.reference_score
    const rightScore = (right.price_gap_bps / 400) + (right.freshness_gap_ms / 120_000) + right.reference.reference_score
    if (rightScore !== leftScore) return rightScore - leftScore
    return right.price_gap_bps - left.price_gap_bps
  })[0]

  const signalScore = clampProbability(
    (best.price_gap_bps / 350) +
      (best.freshness_gap_ms / 120_000) * 0.35 +
      (best.reference.reference_score * 0.25),
  )

  return [
    normalizeCandidate({
      read_only: true,
      candidate_id: candidateId('latency_reference_spread', input.base.market_id, best.reference.reference_id),
      kind: 'latency_reference_spread',
      disposition: 'advisory',
      market_id: input.base.market_id,
      venue: input.base.venue,
      canonical_event_id: input.base.canonical_event_ids[0] ?? null,
      group_id: input.base.group_ids[0] ?? null,
      related_market_ids: [best.reference.market_id],
      severity: severityFromScore(signalScore),
      signal_score: signalScore,
      confidence_score: clampProbability(0.45 + (best.reference.reference_score * 0.35) + (Math.min(best.price_gap_bps, 300) / 1000)),
      summary: `Latency reference spread of ${best.price_gap_bps.toFixed(2)} bps versus ${best.reference.market_id}.`,
      reasons: uniqueStrings([
        `price_gap_bps:${best.price_gap_bps.toFixed(2)}`,
        `freshness_gap_ms:${best.freshness_gap_ms}`,
        `reference_source:${best.reference.source}`,
      ]),
      evidence_refs: uniqueStrings([
        best.reference.reference_id,
        ...best.reference.reasons,
      ]),
      metrics: {
        price_gap_bps: round(best.price_gap_bps),
        freshness_gap_ms: round(best.freshness_gap_ms),
        reference_score: best.reference.reference_score,
        reference_quote_age_ms: best.reference.quote_age_ms,
        source: 'latency_reference_spread',
      },
      metadata: {
        source: 'latency_reference_spread',
        reference: best.reference,
      },
    }),
  ]
}

function extractPairMarketIds(pair: Record<string, unknown>): string[] {
  return uniqueStrings([
    maybeString(pair.parent_market_id),
    maybeString(pair.child_market_id),
    maybeString(pair.left_market_id),
    maybeString(pair.right_market_id),
  ])
}

function buildLogicalConstraintArbCandidates(input: {
  regime: PredictionMarketStrategyMarketRegime
  base: StrategyComparableFrame
  frame_map: Map<string, StrategyComparableFrame>
  graph_groups: ComparableGroup[]
  min_gap_bps: number
}): PredictionMarketStrategyCandidate[] {
  const candidates: PredictionMarketStrategyCandidate[] = []

  for (const group of input.graph_groups) {
    if (!group.market_ids.includes(input.base.market_id)) continue

    let strongest: {
      pair_type: 'natural_hedge' | 'parent_child'
      gap_bps: number
      related_ids: string[]
      summary: string
      reasons: string[]
      metrics: Record<string, PredictionMarketStrategyCandidateMetricValue>
      evidence_refs: string[]
    } | null = null

    for (const pair of group.natural_hedge_pairs) {
      const ids = extractPairMarketIds(pair)
      if (!ids.includes(input.base.market_id) || ids.length < 2) continue
      const relatedId = ids.find((id) => id !== input.base.market_id)
      if (!relatedId) continue
      const related = input.frame_map.get(relatedId)
      const basePrice = input.base.price_yes
      const relatedPrice = related?.price_yes ?? null
      const sum = basePrice != null && relatedPrice != null ? basePrice + relatedPrice : null
      if (sum == null) continue
      const gapBps = Math.abs(1 - sum) * 10_000
      if (gapBps < input.min_gap_bps) continue
      const summary = `Natural hedge basket sums to ${sum.toFixed(4)} vs parity 1.0000.`
      strongest = !strongest || gapBps > strongest.gap_bps
        ? {
            pair_type: 'natural_hedge',
            gap_bps: gapBps,
            related_ids: ids,
            summary,
            reasons: uniqueStrings([
              `pair_type:natural_hedge`,
              `basket_sum:${sum.toFixed(4)}`,
              `specificity_gap:${maybeNumber(pair.specificity_gap) ?? 0}`,
            ]),
            metrics: {
              basket_sum_yes: round(sum),
              gap_bps: round(gapBps),
              specificity_gap: maybeNumber(pair.specificity_gap),
            },
            evidence_refs: uniqueStrings([group.group_id, group.canonical_event_id, ...ids]),
          }
        : strongest
    }

    for (const pair of group.parent_child_pairs) {
      const parentId = maybeString(pair.parent_market_id)
      const childId = maybeString(pair.child_market_id)
      if (!parentId || !childId) continue
      if (input.base.market_id !== parentId && input.base.market_id !== childId) continue
      const parent = input.frame_map.get(parentId)
      const child = input.frame_map.get(childId)
      if (parent?.price_yes == null || child?.price_yes == null) continue
      const gapBps = Math.abs(parent.price_yes - child.price_yes) * 10_000
      if (gapBps < input.min_gap_bps) continue
      const summary = `Parent/child constraint gap of ${gapBps.toFixed(2)} bps between ${parentId} and ${childId}.`
      strongest = !strongest || gapBps > strongest.gap_bps
        ? {
            pair_type: 'parent_child',
            gap_bps: gapBps,
            related_ids: [parentId, childId],
            summary,
            reasons: uniqueStrings([
              'pair_type:parent_child',
              `specificity_gap:${maybeNumber(pair.specificity_gap) ?? 0}`,
              `shared_tokens:${Array.isArray(pair.shared_tokens) ? (pair.shared_tokens as unknown[]).length : 0}`,
            ]),
            metrics: {
              parent_price_yes: parent.price_yes,
              child_price_yes: child.price_yes,
              gap_bps: round(gapBps),
              specificity_gap: maybeNumber(pair.specificity_gap),
            },
            evidence_refs: uniqueStrings([group.group_id, group.canonical_event_id, parentId, childId]),
          }
        : strongest
    }

    if (!strongest) continue

    const signalScore = clampProbability(
      (strongest.gap_bps / 300) +
        (group.manual_review_required ? 0.12 : 0.02) +
        (input.regime.signal_strength * 0.15),
    )

    candidates.push(normalizeCandidate({
      read_only: true,
      candidate_id: candidateId('logical_constraint_arb', input.base.market_id, `${group.group_id}:${strongest.pair_type}`),
      kind: 'logical_constraint_arb',
      disposition: 'advisory',
      market_id: input.base.market_id,
      venue: input.base.venue,
      canonical_event_id: group.canonical_event_id,
      group_id: group.group_id,
      related_market_ids: strongest.related_ids,
      severity: severityFromScore(signalScore),
      signal_score: signalScore,
      confidence_score: clampProbability(0.45 + (Math.min(strongest.gap_bps, 250) / 1000)),
      summary: strongest.summary,
      reasons: uniqueStrings([
        ...strongest.reasons,
        group.manual_review_required ? 'group_manual_review_required' : null,
      ]),
      evidence_refs: strongest.evidence_refs,
      metrics: strongest.metrics,
      metadata: {
        source: 'logical_constraint_arb',
        pair_type: strongest.pair_type,
      },
    }))
  }

  return candidates.slice(0, 2)
}

function buildNegativeRiskBasketCandidates(input: {
  regime: PredictionMarketStrategyMarketRegime
  base: StrategyComparableFrame
  frame_map: Map<string, StrategyComparableFrame>
  graph_groups: ComparableGroup[]
  min_gap_bps: number
}): PredictionMarketStrategyCandidate[] {
  const candidates: PredictionMarketStrategyCandidate[] = []

  for (const group of input.graph_groups) {
    if (!group.market_ids.includes(input.base.market_id)) continue
    if (group.natural_hedge_market_ids.length < 2) continue
    const prices: Array<{ market_id: string; price_yes: number }> = []
    for (const marketId of group.natural_hedge_market_ids) {
      const frame = input.frame_map.get(marketId)
      if (frame?.price_yes == null) continue
      prices.push({ market_id: marketId, price_yes: frame.price_yes })
    }
    if (prices.length < 2) continue
    const basketSum = prices.reduce((sum, item) => sum + item.price_yes, 0)
    const gapBps = Math.max(0, (1 - basketSum) * 10_000)
    if (gapBps < input.min_gap_bps) continue

    const signalScore = clampProbability(
      (gapBps / 400) +
        (group.compatible_payout ? 0.1 : 0) +
        (group.compatible_resolution ? 0.08 : 0),
    )

    candidates.push(normalizeCandidate({
      read_only: true,
      candidate_id: candidateId('negative_risk_basket', input.base.market_id, group.group_id),
      kind: 'negative_risk_basket',
      disposition: 'advisory',
      market_id: input.base.market_id,
      venue: input.base.venue,
      canonical_event_id: group.canonical_event_id,
      group_id: group.group_id,
      related_market_ids: prices.map((item) => item.market_id),
      severity: severityFromScore(signalScore),
      signal_score: signalScore,
      confidence_score: clampProbability(0.4 + (Math.min(gapBps, 250) / 1000)),
      summary: `Negative risk basket gap of ${gapBps.toFixed(2)} bps across ${prices.length} linked markets.`,
      reasons: uniqueStrings([
        `basket_sum:${basketSum.toFixed(4)}`,
        `negative_risk_gap_bps:${gapBps.toFixed(2)}`,
        group.manual_review_required ? 'group_manual_review_required' : null,
      ]),
      evidence_refs: uniqueStrings([group.group_id, group.canonical_event_id, ...prices.map((item) => item.market_id)]),
      metrics: {
        basket_sum_yes: round(basketSum),
        gap_bps: round(gapBps),
        basket_size: prices.length,
        source: 'negative_risk_basket',
      },
      metadata: {
        source: 'negative_risk_basket',
        markets: prices,
      },
    }))
  }

  return candidates.slice(0, 2)
}

function collectResearchEvidenceRefs(input: PredictionMarketStrategyDetectionInput): string[] {
  return uniqueStrings([
    ...(input.research_sidecar?.evidence_packets ?? []).map((packet) => packet.evidence_id),
    ...(input.research_bridge?.evidence_refs ?? []),
    ...(input.research_bridge?.artifact_refs ?? []),
  ])
}

function buildAutonomousAgentAdvisoryCandidates(
  input: PredictionMarketStrategyDetectionInput & { regime: PredictionMarketStrategyMarketRegime },
): PredictionMarketStrategyCandidate[] {
  const sidecar = input.research_sidecar
  const bridge = input.research_bridge
  const signals = sidecar?.signals ?? []
  const signalCount = signals.length
  const evidenceRefs = collectResearchEvidenceRefs(input)
  const shouldEmit = Boolean(
    sidecar ||
    bridge ||
    input.regime.disposition !== 'calm' ||
    input.regime.research_state !== 'supportive' ||
    input.regime.anomaly_count > 0,
  )

  if (!shouldEmit) return []

  const supportive = signals.filter((signal) => signal.stance === 'supportive').length
  const contradictory = signals.filter((signal) => signal.stance === 'contradictory').length
  const manualProbability = sidecar?.synthesis.manual_thesis_probability_hint ?? null
  const abstentionRecommended = sidecar?.synthesis.abstention_recommended ?? false
  const bridgeClassification = bridge?.classification ?? null
  const bridgeReasons = bridge?.classification_reasons ?? []
  const healthStatus = sidecar?.health.status ?? 'unknown'

  const signalScore = clampProbability(
    0.35 +
      (signalCount / 10) +
      (abstentionRecommended ? 0.12 : 0) +
      (input.regime.research_state === 'abstain' ? 0.1 : 0) +
      (input.regime.disposition === 'defense' ? 0.1 : 0),
  )

  const severity: PredictionMarketStrategyCandidateSeverity =
    abstentionRecommended || input.regime.disposition === 'defense' || input.regime.research_state === 'abstain'
      ? 'high'
      : signalCount > 0
        ? 'medium'
        : 'low'

  return [
    normalizeCandidate({
      read_only: true,
      candidate_id: candidateId('autonomous_agent_advisory', input.snapshot.market.market_id, input.snapshot.captured_at),
      kind: 'autonomous_agent_advisory',
      disposition: 'advisory',
      market_id: input.snapshot.market.market_id,
      venue: input.snapshot.venue,
      canonical_event_id: input.snapshot.market.event_id ?? null,
      group_id: input.snapshot.market.condition_id ?? null,
      related_market_ids: [],
      severity,
      signal_score: signalScore,
      confidence_score: clampProbability(
        0.45 +
          (sidecar ? clamp((sidecar.health.completeness_score ?? 0) / 1, 0, 1) * 0.25 : 0) +
          (input.regime.confidence_score * 0.2) +
          (abstentionRecommended ? 0.05 : 0),
      ),
      summary: `Autonomous agent advisory inputs prepared for ${input.snapshot.market.market_id}.`,
      reasons: uniqueStrings([
        `signal_count:${signalCount}`,
        `supportive_signals:${supportive}`,
        `contradictory_signals:${contradictory}`,
        manualProbability != null ? `manual_thesis_probability_hint:${manualProbability.toFixed(4)}` : null,
        abstentionRecommended ? 'abstention_recommended' : null,
        bridgeClassification ? `bridge_classification:${bridgeClassification}` : null,
        healthStatus !== 'unknown' ? `research_health:${healthStatus}` : null,
        ...bridgeReasons,
      ]),
      evidence_refs: evidenceRefs,
      metrics: {
        signal_count: signalCount,
        evidence_count: evidenceRefs.length,
        manual_thesis_probability_hint: manualProbability,
        abstention_recommended: abstentionRecommended,
        research_health_score: sidecar?.health.completeness_score ?? null,
        research_health_status: healthStatus,
        bridge_freshness_score: bridge?.freshness_score ?? null,
        source: 'autonomous_agent_advisory',
      },
      metadata: {
        source: 'autonomous_agent_advisory',
        research_sidecar: sidecar ?? null,
        research_bridge: bridge ?? null,
      },
    }),
  ]
}

function summarizeCandidates(candidates: readonly PredictionMarketStrategyCandidate[]): PredictionMarketStrategyCountSummary {
  const byKind = {
    intramarket_parity: 0,
    maker_spread_capture: 0,
    latency_reference_spread: 0,
    logical_constraint_arb: 0,
    negative_risk_basket: 0,
    resolution_attack_watch: 0,
    resolution_sniping_watch: 0,
    autonomous_agent_advisory: 0,
  } satisfies Record<PredictionMarketStrategyCandidateKind, number>
  const byDisposition = {
    advisory: 0,
    watch: 0,
    defense: 0,
  } satisfies Record<PredictionMarketStrategyDisposition, number>
  const bySeverity = {
    low: 0,
    medium: 0,
    high: 0,
    critical: 0,
  } satisfies Record<PredictionMarketStrategyCandidateSeverity, number>

  for (const candidate of candidates) {
    byKind[candidate.kind] += 1
    byDisposition[candidate.disposition] += 1
    bySeverity[candidate.severity] += 1
  }

  return {
    read_only: true,
    total: candidates.length,
    by_kind: byKind,
    by_disposition: byDisposition,
    by_severity: bySeverity,
    advisory_count: byDisposition.advisory,
    watch_count: byDisposition.watch,
    defense_count: byDisposition.defense,
    summary: [
      `${candidates.length} normalized strategy candidates`,
      `${byDisposition.defense} defense`,
      `${byDisposition.watch} watch`,
      `${byDisposition.advisory} advisory`,
    ].join('; '),
  }
}

function buildSummaryReasons(input: {
  regime: PredictionMarketStrategyMarketRegime
  counts: PredictionMarketStrategyCountSummary
  primary: PredictionMarketStrategyCandidate | null
}): string[] {
  return uniqueStrings([
    ...input.regime.reasons,
    input.primary ? `primary_candidate:${input.primary.kind}` : null,
    input.counts.defense_count > 0 ? 'defense_candidates_present' : null,
    input.counts.watch_count > 0 ? 'watch_candidates_present' : null,
    input.counts.advisory_count > 0 ? 'advisory_candidates_present' : null,
  ])
}

export function detectStrategyCandidates(
  input: PredictionMarketStrategyDetectionInput,
): PredictionMarketStrategyCandidate[] {
  const regime = input.regime ?? deriveMarketRegime(input)
  const resolutionAnomalies = input.resolution_anomalies ?? deriveResolutionAnomalies(input)
  const latencyReferences = input.latency_references ?? deriveLatencyReferences(input)
  const watchlist = buildShadowStrategyWatchlist({
    ...input,
    regime,
    resolution_anomalies: resolutionAnomalies,
    latency_references: latencyReferences,
  })
  const shadowCandidates = buildShadowCandidates({ regime, watchlist })
  const counts = summarizeShadowStrategyWatchlist(watchlist)
  const { base, frame_map, graph_groups } = collectComparableFrames({
    ...input,
    regime,
    resolution_anomalies: resolutionAnomalies,
    latency_references: latencyReferences,
  })

  const candidates: PredictionMarketStrategyCandidate[] = [
    ...shadowCandidates,
    ...buildIntramarketParityCandidates({
      regime,
      base,
      frame_map,
      graph_groups,
      threshold_bps: spreadThreshold(input.min_intramarket_parity_bps ?? 35, regime),
    }),
    ...buildMakerSpreadCaptureCandidates({
      regime,
      base,
      min_spread_bps: spreadThreshold(input.min_maker_spread_capture_bps ?? 45, regime),
    }),
    ...buildLatencyReferenceSpreadCandidates({
      regime,
      base,
      latency_references: latencyReferences,
      min_spread_bps: spreadThreshold(input.min_latency_reference_spread_bps ?? 35, regime),
      min_freshness_gap_ms: input.min_latency_reference_freshness_gap_ms ?? 10_000,
    }),
    ...buildLogicalConstraintArbCandidates({
      regime,
      base,
      frame_map,
      graph_groups,
      min_gap_bps: spreadThreshold(input.min_logical_constraint_gap_bps ?? 75, regime),
    }),
    ...buildNegativeRiskBasketCandidates({
      regime,
      base,
      frame_map,
      graph_groups,
      min_gap_bps: spreadThreshold(input.min_negative_risk_gap_bps ?? 100, regime),
    }),
    ...buildAutonomousAgentAdvisoryCandidates({
      ...input,
      regime,
    }),
  ]

  const deduped = new Map<string, PredictionMarketStrategyCandidate>()
  for (const candidate of candidates) {
    const normalized = normalizeCandidate(candidate)
    if (deduped.has(normalized.candidate_id)) continue
    deduped.set(normalized.candidate_id, normalized)
  }

  return [...deduped.values()]
    .sort(candidateSort)
    .slice(0, input.max_candidates ?? 12)
}

export function summarizeStrategyCounts(
  candidates: readonly PredictionMarketStrategyCandidate[],
): PredictionMarketStrategyCountSummary {
  return summarizeCandidates(candidates)
}

export function buildStrategyDecision(
  input: PredictionMarketStrategyDetectionInput,
): PredictionMarketStrategyDecision {
  const regime = input.regime ?? deriveMarketRegime(input)
  const resolutionAnomalies = input.resolution_anomalies ?? deriveResolutionAnomalies(input)
  const latencyReferences = input.latency_references ?? deriveLatencyReferences(input)
  const candidates = detectStrategyCandidates({
    ...input,
    regime,
    resolution_anomalies: resolutionAnomalies,
    latency_references: latencyReferences,
  })
  const counts = summarizeCandidates(candidates)
  const shadowWatchlist = buildShadowStrategyWatchlist({
    ...input,
    regime,
    resolution_anomalies: resolutionAnomalies,
    latency_references: latencyReferences,
  })
  const shadowWatchSummary = summarizeShadowStrategyWatchlist(shadowWatchlist)
  const primary = candidates[0] ?? null
  const mode: PredictionMarketStrategyDecisionMode =
    counts.defense_count > 0 || regime.disposition === 'defense'
      ? 'defense'
      : counts.watch_count > 0 || regime.disposition === 'watch' || regime.disposition === 'stress'
        ? 'watch'
        : counts.advisory_count > 0
          ? 'advisory'
          : 'inactive'

  const summary = [
    `${mode} decision for ${input.snapshot.market.market_id}`,
    `candidates=${counts.total}`,
    `defense=${counts.defense_count}`,
    `watch=${counts.watch_count}`,
    `advisory=${counts.advisory_count}`,
    `regime=${regime.disposition}/${regime.resolution_state}/${regime.research_state}`,
  ].join('; ')

  return {
    read_only: true,
    decision_id: `strategy:${input.snapshot.market.market_id}:${input.as_of_at ?? input.snapshot.captured_at}`,
    generated_at: input.as_of_at ?? input.snapshot.captured_at,
    market_id: input.snapshot.market.market_id,
    venue: input.snapshot.venue,
    mode,
    regime,
    candidate_count: counts.total,
    primary_candidate_id: primary?.candidate_id ?? null,
    primary_candidate_kind: primary?.kind ?? null,
    primary_candidate_summary: primary?.summary ?? null,
    counts,
    candidates,
    summary,
    reasons: buildSummaryReasons({
      regime,
      counts,
      primary,
    }),
    shadow_watch_summary: shadowWatchSummary,
  }
}

export {
  buildShadowStrategyWatchlist,
  deriveLatencyReferences,
  deriveMarketRegime,
  deriveResolutionAnomalies,
  summarizeShadowStrategyWatchlist,
}

export type {
  PredictionMarketStrategyLatencyReference,
  PredictionMarketStrategyMarketRegime,
  PredictionMarketStrategyRegimeInput,
  PredictionMarketStrategyResolutionAnomaly,
  PredictionMarketShadowStrategyWatch,
  PredictionMarketShadowStrategyWatchSummary,
}
