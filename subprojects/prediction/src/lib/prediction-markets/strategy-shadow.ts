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
    disposition: 'watch',
    market_id: input.marketId,
    venue: input.venue,
    severity,
    signal_score: round(signalScore),
    summary: `Resolution sniping watch for ${input.marketId} near the endgame window.`,
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
    `shadow watchlist contains ${input.watchCount} watch signals`,
    `${input.defenseCount} defense signals`,
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
