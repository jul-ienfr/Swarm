import {
  type ResearchBridgeBundle,
} from '@/lib/prediction-markets/schemas'
import {
  type MarketResearchSidecar,
} from '@/lib/prediction-markets/research'
import {
  type PredictionMarketStrategyLatencyReference,
  type PredictionMarketStrategyMarketRegime,
  type PredictionMarketStrategyRegimeInput,
  type PredictionMarketStrategyResolutionAnomaly,
  type PredictionMarketStrategyResolutionAnomalyKind,
  type PredictionMarketStrategyResolutionState,
  deriveLatencyReferences,
  deriveMarketRegime,
  deriveResolutionAnomalies,
} from '@/lib/prediction-markets/strategy-regime'

export type PredictionMarketShadowStrategyKind =
  | 'resolution_attack_watch'
  | 'resolution_sniping_watch'

export type PredictionMarketShadowStrategyDisposition = 'watch' | 'defense'

export type PredictionMarketShadowStrategyWatch = {
  read_only: true
  watch_id: string
  kind: PredictionMarketShadowStrategyKind
  disposition: PredictionMarketShadowStrategyDisposition
  market_id: string
  venue: PredictionMarketStrategyMarketRegime['venue']
  severity: 'low' | 'medium' | 'high' | 'critical'
  signal_score: number
  summary: string
  reasons: string[]
  watch_conditions: string[]
  defensive_controls: string[]
  evidence_refs: string[]
  metadata: Record<string, unknown>
}

export type PredictionMarketShadowStrategyWatchSummary = {
  read_only: true
  total: number
  watch_count: number
  defense_count: number
  attack_watch_count: number
  sniping_watch_count: number
  summary: string
  reasons: string[]
}

export type PredictionMarketShadowStrategyDefenseSummary = {
  read_only: true
  market_id: string
  venue: PredictionMarketStrategyMarketRegime['venue']
  generated_at: string
  regime_id: string
  disposition: PredictionMarketShadowStrategyDisposition
  freshness_state: PredictionMarketStrategyMarketRegime['freshness_state']
  resolution_state: PredictionMarketStrategyMarketRegime['resolution_state']
  latency_state: PredictionMarketStrategyMarketRegime['latency_state']
  watch_count: number
  defense_count: number
  attack_watch_count: number
  sniping_watch_count: number
  latency_reference_count: number
  best_latency_reference_id: string | null
  best_latency_reference_gap_ms: number | null
  severity: PredictionMarketShadowStrategyWatch['severity']
  summary: string
  reasons: string[]
  watch_conditions: string[]
  defensive_controls: string[]
  evidence_refs: string[]
}

export type PredictionMarketShadowStrategyInput = PredictionMarketStrategyRegimeInput & {
  regime?: PredictionMarketStrategyMarketRegime | null
  resolution_anomalies?: readonly PredictionMarketStrategyResolutionAnomaly[]
  latency_references?: readonly PredictionMarketStrategyLatencyReference[]
  research_sidecar?: MarketResearchSidecar | null
  research_bridge?: ResearchBridgeBundle | null
}

const ATTACK_KINDS: readonly PredictionMarketStrategyResolutionAnomalyKind[] = [
  'policy_ambiguity',
  'policy_blocked',
  'graph_misalignment',
  'signal_conflict',
  'attack_watch',
  'cross_venue_resolution_mismatch',
]

const SNIPING_KINDS: readonly PredictionMarketStrategyResolutionAnomalyKind[] = [
  'horizon_drift',
  'sniping_watch',
]

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function round(value: number): number {
  return Number(value.toFixed(4))
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

function severityRank(severity: PredictionMarketShadowStrategyWatch['severity']): number {
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

function watchSeverityFromResolutionState(state: PredictionMarketStrategyResolutionState): PredictionMarketShadowStrategyWatch['severity'] {
  switch (state) {
    case 'anomalous':
      return 'critical'
    case 'watch':
      return 'medium'
    case 'clear':
      return 'low'
  }
}

function bestLatencyReference(
  latencyReferences: readonly PredictionMarketStrategyLatencyReference[],
): PredictionMarketStrategyLatencyReference | null {
  return [...latencyReferences]
    .sort((left, right) => {
      if (right.reference_score !== left.reference_score) {
        return right.reference_score - left.reference_score
      }
      const leftFreshness = left.freshness_gap_ms ?? Number.MAX_SAFE_INTEGER
      const rightFreshness = right.freshness_gap_ms ?? Number.MAX_SAFE_INTEGER
      if (leftFreshness !== rightFreshness) return leftFreshness - rightFreshness
      const leftQuoteAge = left.quote_age_ms ?? Number.MAX_SAFE_INTEGER
      const rightQuoteAge = right.quote_age_ms ?? Number.MAX_SAFE_INTEGER
      if (leftQuoteAge !== rightQuoteAge) return leftQuoteAge - rightQuoteAge
      return left.reference_id.localeCompare(right.reference_id)
    })[0] ?? null
}

function mapResolutionAnomalyToWatchKind(
  anomaly: PredictionMarketStrategyResolutionAnomaly,
): PredictionMarketShadowStrategyKind | null {
  if (ATTACK_KINDS.includes(anomaly.anomaly_kind)) return 'resolution_attack_watch'
  if (SNIPING_KINDS.includes(anomaly.anomaly_kind)) return 'resolution_sniping_watch'
  if (anomaly.watch_kind === 'defense') return 'resolution_attack_watch'
  if (anomaly.watch_kind === 'watch') return anomaly.anomaly_kind === 'horizon_drift'
    ? 'resolution_sniping_watch'
    : 'resolution_attack_watch'
  return null
}

function buildShadowWatchId(
  kind: PredictionMarketShadowStrategyKind,
  marketId: string,
  suffix: string,
): string {
  return `shadow:${kind}:${marketId}:${suffix}`
}

function makeAttackWatch(input: {
  marketId: string
  venue: PredictionMarketShadowStrategyWatch['venue']
  source: string
  regime: PredictionMarketStrategyMarketRegime
  anomaly: PredictionMarketStrategyResolutionAnomaly | null
  reasons: string[]
  evidenceRefs: string[]
}): PredictionMarketShadowStrategyWatch {
  const severity = input.anomaly?.severity ?? watchSeverityFromResolutionState(input.regime.resolution_state)
  const signalScore = clamp(
    (input.anomaly?.score ?? 0.6) +
      (input.regime.resolution_state === 'anomalous' ? 0.18 : 0.05),
    0,
    1,
  )

  return {
    read_only: true,
    watch_id: buildShadowWatchId('resolution_attack_watch', input.marketId, input.source),
    kind: 'resolution_attack_watch',
    disposition: 'defense',
    market_id: input.marketId,
    venue: input.venue,
    severity,
    signal_score: round(signalScore),
    summary: `Defense watch for resolution attack pressure on ${input.marketId}.`,
    reasons: uniqueStrings([
      `source:${input.source}`,
      ...(input.anomaly?.reasons ?? []),
      ...input.reasons,
    ]),
    watch_conditions: uniqueStrings([
      'manual_review_required',
      'resolution_policy_ambiguity',
      'resolution_source_conflict',
      'freeze_autonomy',
    ]),
    defensive_controls: uniqueStrings([
      'route_to_manual_review',
      'prefer_primary_resolution_sources',
      'avoid_autonomous_execution',
      'preserve_read_only_monitoring',
      ...(input.regime.maker_quote_state !== 'viable' ? ['avoid_quote_fade_entry'] : []),
    ]),
    evidence_refs: uniqueStrings([
      ...(input.anomaly?.signal_refs ?? []),
      ...input.evidenceRefs,
    ]),
    metadata: {
      source: input.source,
      anomaly_id: input.anomaly?.anomaly_id ?? null,
      resolution_state: input.regime.resolution_state,
      disposition: input.regime.disposition,
      maker_quote_state: input.regime.maker_quote_state,
    },
  }
}

function makeSnipingWatch(input: {
  marketId: string
  venue: PredictionMarketShadowStrategyWatch['venue']
  regime: PredictionMarketStrategyMarketRegime
  anomaly: PredictionMarketStrategyResolutionAnomaly | null
  latencyReferences: readonly PredictionMarketStrategyLatencyReference[]
  reasons: string[]
  evidenceRefs: string[]
}): PredictionMarketShadowStrategyWatch {
  const bestReference = [...input.latencyReferences]
    .sort((left, right) => right.reference_score - left.reference_score)[0] ?? null
  const freshnessGapMs = bestReference?.freshness_gap_ms ?? null
  const severity = input.anomaly?.severity ?? (
    input.regime.hours_to_resolution != null && input.regime.hours_to_resolution <= 24
      ? 'high'
      : 'medium'
  )
  const signalScore = clamp(
    (input.anomaly?.score ?? 0.55) +
      (freshnessGapMs != null ? clamp(freshnessGapMs / 120_000, 0, 0.2) : 0) +
      (input.regime.hours_to_resolution != null && input.regime.hours_to_resolution <= 24 ? 0.12 : 0),
    0,
    1,
  )

  return {
    read_only: true,
    watch_id: buildShadowWatchId('resolution_sniping_watch', input.marketId, bestReference?.reference_id ?? 'none'),
    kind: 'resolution_sniping_watch',
    disposition: 'defense',
    market_id: input.marketId,
    venue: input.venue,
    severity,
    signal_score: round(signalScore),
    summary: [
      `Defense watch for resolution sniping pressure on ${input.marketId}.`,
      bestReference
        ? `best_reference=${bestReference.reference_id} freshness_gap_ms=${freshnessGapMs ?? 'n/a'}`
        : null,
    ].filter(Boolean).join(' '),
    reasons: uniqueStrings([
      ...(input.anomaly?.reasons ?? []),
      ...input.reasons,
      bestReference?.reference_id ? `best_reference:${bestReference.reference_id}` : null,
    ]),
    watch_conditions: uniqueStrings([
      'hours_to_resolution_under_72h',
      'fresh_reference_gap_positive',
      'spread_widening_near_resolution',
      'avoid_last_minute_entry',
    ]),
    defensive_controls: uniqueStrings([
      'prefer_fresh_quotes',
      'require_resolution_source_check',
      'monitor_quote_age',
      ...(input.regime.maker_quote_state !== 'viable' ? ['avoid_quote_fade_entry'] : []),
    ]),
    evidence_refs: uniqueStrings([
      ...(input.anomaly?.signal_refs ?? []),
      ...input.evidenceRefs,
      bestReference?.reference_id ?? null,
    ]),
    metadata: {
      anomaly_id: input.anomaly?.anomaly_id ?? null,
      best_reference_id: bestReference?.reference_id ?? null,
      freshness_gap_ms: freshnessGapMs,
      hours_to_resolution: input.regime.hours_to_resolution,
      disposition: input.regime.disposition,
      maker_quote_state: input.regime.maker_quote_state,
    },
  }
}

function watchSummaryFromCounts(input: {
  watchCount: number
  defenseCount: number
  attackCount: number
  snipingCount: number
}): string {
  return [
    `shadow defense watchlist contains ${input.defenseCount} defense signals`,
    `${input.watchCount} passive watch signals`,
    `${input.attackCount} attack-watch items`,
    `${input.snipingCount} sniping-watch items`,
  ].join('; ')
}

function normalizeAnomalies(
  anomalies: readonly PredictionMarketStrategyResolutionAnomaly[] | undefined,
): PredictionMarketStrategyResolutionAnomaly[] {
  return [...(anomalies ?? [])]
    .sort((left, right) => {
      const bySeverity = severityRank(right.severity) - severityRank(left.severity)
      if (bySeverity !== 0) return bySeverity
      if (right.score !== left.score) return right.score - left.score
      return left.anomaly_id.localeCompare(right.anomaly_id)
    })
}

function buildShadowWatchFromAnomaly(
  anomaly: PredictionMarketStrategyResolutionAnomaly,
  regime: PredictionMarketStrategyMarketRegime,
  latencyReferences: readonly PredictionMarketStrategyLatencyReference[],
): PredictionMarketShadowStrategyWatch | null {
  const kind = mapResolutionAnomalyToWatchKind(anomaly)
  if (!kind) return null

  if (kind === 'resolution_attack_watch') {
    return makeAttackWatch({
      marketId: anomaly.market_id,
      venue: anomaly.venue,
      source: anomaly.anomaly_kind,
      regime,
      anomaly,
      reasons: anomaly.reasons,
      evidenceRefs: anomaly.signal_refs,
    })
  }

  return makeSnipingWatch({
    marketId: anomaly.market_id,
    venue: anomaly.venue,
    regime,
    anomaly,
    latencyReferences,
    reasons: anomaly.reasons,
    evidenceRefs: anomaly.signal_refs,
  })
}

export function detectResolutionAttackWatch(
  input: PredictionMarketShadowStrategyInput,
): PredictionMarketShadowStrategyWatch[] {
  const regime = input.regime ?? deriveMarketRegime(input)
  const anomalies = normalizeAnomalies(input.resolution_anomalies ?? deriveResolutionAnomalies(input))
  const latencyReferences = input.latency_references ?? deriveLatencyReferences(input)

  return anomalies
    .filter((anomaly) => anomaly.watch_kind === 'defense' || anomaly.anomaly_kind === 'policy_blocked' || anomaly.anomaly_kind === 'policy_ambiguity' || anomaly.anomaly_kind === 'graph_misalignment' || anomaly.anomaly_kind === 'attack_watch')
    .map((anomaly) => buildShadowWatchFromAnomaly(anomaly, regime, latencyReferences))
    .filter((watch): watch is PredictionMarketShadowStrategyWatch => watch != null && watch.kind === 'resolution_attack_watch')
}

export function detectResolutionSnipingWatch(
  input: PredictionMarketShadowStrategyInput,
): PredictionMarketShadowStrategyWatch[] {
  const regime = input.regime ?? deriveMarketRegime(input)
  const anomalies = normalizeAnomalies(input.resolution_anomalies ?? deriveResolutionAnomalies(input))
  const latencyReferences = input.latency_references ?? deriveLatencyReferences(input)

  return anomalies
    .filter((anomaly) => anomaly.anomaly_kind === 'sniping_watch' || anomaly.anomaly_kind === 'horizon_drift')
    .map((anomaly) => buildShadowWatchFromAnomaly(anomaly, regime, latencyReferences))
    .filter((watch): watch is PredictionMarketShadowStrategyWatch => watch != null && watch.kind === 'resolution_sniping_watch')
}

export function buildShadowStrategyWatchlist(
  input: PredictionMarketShadowStrategyInput,
): PredictionMarketShadowStrategyWatch[] {
  const regime = input.regime ?? deriveMarketRegime(input)
  const anomalies = normalizeAnomalies(input.resolution_anomalies ?? deriveResolutionAnomalies(input))
  const latencyReferences = input.latency_references ?? deriveLatencyReferences(input)
  const watches: PredictionMarketShadowStrategyWatch[] = []

  for (const anomaly of anomalies) {
    const watch = buildShadowWatchFromAnomaly(anomaly, regime, latencyReferences)
    if (!watch) continue
    watches.push(watch)
  }

  return watches
    .sort((left, right) => {
      const bySeverity = severityRank(right.severity) - severityRank(left.severity)
      if (bySeverity !== 0) return bySeverity
      if (right.signal_score !== left.signal_score) return right.signal_score - left.signal_score
      return left.watch_id.localeCompare(right.watch_id)
    })
}

export function buildShadowStrategyDefenseSummary(
  input: PredictionMarketShadowStrategyInput,
): PredictionMarketShadowStrategyDefenseSummary {
  const regime = input.regime ?? deriveMarketRegime(input)
  const anomalies = normalizeAnomalies(input.resolution_anomalies ?? deriveResolutionAnomalies(input))
  const latencyReferences = input.latency_references ?? deriveLatencyReferences(input)
  const watches = buildShadowStrategyWatchlist({
    ...input,
    regime,
    resolution_anomalies: anomalies,
    latency_references: latencyReferences,
  })
  const counts = summarizeShadowStrategyWatchlist(watches)
  const topWatch = [...watches]
    .sort((left, right) => {
      const bySeverity = severityRank(right.severity) - severityRank(left.severity)
      if (bySeverity !== 0) return bySeverity
      if (right.signal_score !== left.signal_score) return right.signal_score - left.signal_score
      return left.watch_id.localeCompare(right.watch_id)
    })[0] ?? null
  const topLatencyReference = bestLatencyReference(latencyReferences)

  const summary = [
    `shadow defense summary for ${regime.market_id}`,
    `regime=${regime.disposition}/${regime.resolution_state}/${regime.latency_state}`,
    `maker_quote=${regime.maker_quote_state}`,
    `watches=${counts.total}`,
    `defense=${counts.defense_count}`,
    `attack=${counts.attack_watch_count}`,
    `sniping=${counts.sniping_watch_count}`,
    topLatencyReference
      ? `best_reference=${topLatencyReference.reference_id} gap_ms=${topLatencyReference.freshness_gap_ms ?? 'n/a'}`
      : null,
  ].filter(Boolean).join('; ')

  return {
    read_only: true,
    market_id: regime.market_id,
    venue: regime.venue,
    generated_at: regime.generated_at,
    regime_id: regime.regime_id,
    disposition: counts.defense_count > 0 || regime.disposition === 'defense' ? 'defense' : 'watch',
    freshness_state: regime.freshness_state,
    resolution_state: regime.resolution_state,
    latency_state: regime.latency_state,
    watch_count: counts.watch_count,
    defense_count: counts.defense_count,
    attack_watch_count: counts.attack_watch_count,
    sniping_watch_count: counts.sniping_watch_count,
    latency_reference_count: latencyReferences.length,
    best_latency_reference_id: topLatencyReference?.reference_id ?? null,
    best_latency_reference_gap_ms: topLatencyReference?.freshness_gap_ms ?? null,
    severity: topWatch?.severity ?? watchSeverityFromResolutionState(regime.resolution_state),
    summary,
    reasons: uniqueStrings([
      ...counts.reasons,
      'defense_only',
      latencyReferences.length > 0 ? `latency_references:${latencyReferences.length}` : null,
      regime.latency_state !== 'fresh' ? `latency_state:${regime.latency_state}` : null,
      regime.resolution_state !== 'clear' ? `resolution_state:${regime.resolution_state}` : null,
      `maker_quote_state:${regime.maker_quote_state}`,
      `maker_quote_freshness_budget_ms:${regime.maker_quote_freshness_budget_ms}`,
      topWatch?.kind ? `top_watch_kind:${topWatch.kind}` : null,
    ]),
    watch_conditions: uniqueStrings([
      'manual_review_required',
      'resolution_policy_check',
      'freshness_gate_enforced',
      regime.latency_state === 'stale' ? 'prefer_wait_over_action' : null,
      regime.maker_quote_state !== 'viable' ? 'maker_quote_guard_active' : null,
    ]),
    defensive_controls: uniqueStrings([
      ...watches.flatMap((watch) => watch.defensive_controls),
      'route_to_manual_review',
      'preserve_read_only_monitoring',
      ...(regime.maker_quote_state !== 'viable' ? ['avoid_quote_fade_entry'] : []),
    ]),
    evidence_refs: uniqueStrings([
      ...watches.flatMap((watch) => watch.evidence_refs),
      topLatencyReference?.reference_id ?? null,
    ]),
  }
}

export function summarizeShadowStrategyWatchlist(
  watches: readonly PredictionMarketShadowStrategyWatch[],
): PredictionMarketShadowStrategyWatchSummary {
  const defenseCount = watches.filter((watch) => watch.disposition === 'defense').length
  const watchCount = watches.filter((watch) => watch.disposition === 'watch').length
  const attackWatchCount = watches.filter((watch) => watch.kind === 'resolution_attack_watch').length
  const snipingWatchCount = watches.filter((watch) => watch.kind === 'resolution_sniping_watch').length

  return {
    read_only: true,
    total: watches.length,
    watch_count: watchCount,
    defense_count: defenseCount,
    attack_watch_count: attackWatchCount,
    sniping_watch_count: snipingWatchCount,
    summary: watchSummaryFromCounts({
      watchCount,
      defenseCount,
      attackCount: attackWatchCount,
      snipingCount: snipingWatchCount,
    }),
    reasons: uniqueStrings([
      defenseCount > 0 ? 'defense_signals_present' : null,
      watchCount > 0 ? 'watch_signals_present' : null,
      attackWatchCount > 0 ? 'attack_watch_present' : null,
      snipingWatchCount > 0 ? 'sniping_watch_present' : null,
    ]),
  }
}
