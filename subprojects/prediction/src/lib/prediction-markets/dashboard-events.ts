import { clearInterval, setInterval } from 'node:timers'

import { getPredictionMarketRunDetails, listPredictionMarketRuns } from '@/lib/prediction-markets/service'
import { getVenueCapabilities, getVenueHealthSnapshot, listPredictionMarketVenues, type PredictionMarketVenueId } from '@/lib/prediction-markets/venue-ops'

export type PredictionDashboardEventSeverity = 'info' | 'warn' | 'error'

export type PredictionDashboardEventType =
  | 'heartbeat'
  | 'dashboard_snapshot'
  | 'runs_refresh_hint'
  | 'latest_run_changed'
  | 'benchmark_gate_changed'
  | 'arbitrage_candidate_opened'
  | 'arbitrage_candidate_updated'
  | 'arbitrage_candidate_closed'
  | 'venue_degraded'
  | 'venue_recovered'
  | 'live_intent_created'
  | 'live_intent_approved'
  | 'live_intent_rejected'
  | 'live_intent_executed'
  | 'live_intent_failed'
  | 'capital_blocker'
  | 'reconciliation_drift'

export type PredictionDashboardEventSource = 'poller' | 'manual' | 'workflow' | 'system'

export type DashboardFreshness = 'fresh' | 'warm' | 'stale'

export type PredictionDashboardEvent = {
  event_id: string
  type: PredictionDashboardEventType
  severity: PredictionDashboardEventSeverity
  emitted_at: string
  summary: string
  workspace_id: number | null
  venue: PredictionMarketVenueId | 'all' | null
  run_id: string | null
  intent_id: string | null
  source: PredictionDashboardEventSource
  payload: Record<string, unknown>
}

export type PredictionDashboardArbitrageCandidate = {
  candidate_id: string
  canonical_event_key: string
  buy_venue: PredictionMarketVenueId
  sell_venue: PredictionMarketVenueId
  gross_spread_bps: number
  net_spread_bps: number
  shadow_edge_bps: number
  recommended_size_usd: number
  confidence_score: number
  freshness_ms: number
  blocking_reasons: string[]
  manual_review_required: boolean
  opportunity_type?: string | null
}

export type PredictionDashboardArbitrageSnapshot = {
  generated_at: string
  freshness: DashboardFreshness
  transport: 'polling'
  workspace_id: number
  venue_pair: [PredictionMarketVenueId, PredictionMarketVenueId]
  compared_pairs: number
  candidate_count: number
  manual_review_count: number
  best_shadow_edge_bps: number | null
  candidates: PredictionDashboardArbitrageCandidate[]
}

export type PredictionDashboardArbitrageState = {
  run_id: string | null
  compared_pairs: number
  candidate_count: number
  manual_review_count: number
  best_shadow_edge_bps: number | null
  best_shadow_size_usd: number | null
  summary: string | null
}

export type PredictionDashboardBenchmarkState = {
  ready: boolean
  gate_kind: string | null
  status: string | null
  evidence_level: string | null
  promotion_status: string | null
  blocker_summary: string | null
  live_block_reason: string | null
  blockers: string[]
  summary: string | null
}

export type PredictionDashboardVenueSnapshot = {
  workspace_id: number
  venue: PredictionMarketVenueId
  captured_at: string
  runs_total: number
  latest_run_id: string | null
  latest_run_updated_at: number | null
  latest_recommendation: string | null
  latest_selected_path: string | null
  latest_selected_path_status: string | null
  latest_live_route_allowed: boolean | null
  benchmark_state: PredictionDashboardBenchmarkState
  venue_health_status: string | null
  venue_feed_status: string | null
  venue_user_feed_status: string | null
  venue_rtds_status: string | null
  venue_capabilities: string | null
  venue_supports_execution: boolean | null
  venue_supports_paper_mode: boolean | null
  venue_notes: string[]
  arbitrage_state: PredictionDashboardArbitrageState
}

export type PredictionDashboardVenueObservation = {
  workspaceId: number
  venue: PredictionMarketVenueId
  limit?: number
  pollIntervalMs?: number
  initialSnapshot?: PredictionDashboardVenueSnapshot | null
}

export type PredictionDashboardEventHistoryFilter = {
  workspaceId?: number
  venue?: PredictionMarketVenueId | 'all'
  kinds?: PredictionDashboardEventType[]
  limit?: number
}

export type PredictionDashboardBootstrap = {
  snapshots: PredictionDashboardVenueSnapshot[]
  events: PredictionDashboardEvent[]
}

type DashboardEventSubscriber = (event: PredictionDashboardEvent) => void

type DashboardObserverState = {
  snapshot: PredictionDashboardVenueSnapshot | null
  subscribers: number
  timer: ReturnType<typeof setInterval> | null
  pollIntervalMs: number
  limit: number
}

const MAX_HISTORY = 250
const DEFAULT_POLL_INTERVAL_MS = 5000
const DEFAULT_LIMIT = 25

let sequence = 0
const recentEvents: PredictionDashboardEvent[] = []
const listeners = new Set<DashboardEventSubscriber>()
const observers = new Map<string, DashboardObserverState>()

function nowIso() {
  return new Date().toISOString()
}

function nextEventId(type: PredictionDashboardEventType) {
  sequence += 1
  return `dashboard-${type}-${String(sequence).padStart(6, '0')}`
}

function normalizeString(value: unknown): string | null {
  if (typeof value === 'string' && value.trim().length > 0) return value.trim()
  return null
}

function normalizeStrings(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value == null || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function isTruthy(value: unknown): boolean {
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value !== 0
  if (typeof value === 'string') {
    return ['true', '1', 'yes', 'ready', 'allowed', 'authorized'].includes(value.toLowerCase())
  }
  return Boolean(value)
}

function sameValue(left: unknown, right: unknown) {
  if (Array.isArray(left) || Array.isArray(right)) {
    return JSON.stringify(left ?? []) === JSON.stringify(right ?? [])
  }

  if (left && typeof left === 'object' && right && typeof right === 'object') {
    return JSON.stringify(left) === JSON.stringify(right)
  }

  return left === right
}

function emptyArbitrageState(): PredictionDashboardArbitrageState {
  return {
    run_id: null,
    compared_pairs: 0,
    candidate_count: 0,
    manual_review_count: 0,
    best_shadow_edge_bps: null,
    best_shadow_size_usd: null,
    summary: null,
  }
}

function normalizeCandidateKey(candidate: PredictionDashboardArbitrageCandidate) {
  return candidate.candidate_id || candidate.canonical_event_key
}

function candidateFingerprint(candidate: PredictionDashboardArbitrageCandidate) {
  return JSON.stringify({
    canonical_event_key: candidate.canonical_event_key,
    buy_venue: candidate.buy_venue,
    sell_venue: candidate.sell_venue,
    gross_spread_bps: candidate.gross_spread_bps,
    net_spread_bps: candidate.net_spread_bps,
    shadow_edge_bps: candidate.shadow_edge_bps,
    recommended_size_usd: candidate.recommended_size_usd,
    confidence_score: candidate.confidence_score,
    freshness_ms: candidate.freshness_ms,
    blocking_reasons: candidate.blocking_reasons,
    manual_review_required: candidate.manual_review_required,
    opportunity_type: candidate.opportunity_type ?? null,
  })
}

function pushEvent(event: PredictionDashboardEvent) {
  recentEvents.push(event)
  while (recentEvents.length > MAX_HISTORY) {
    recentEvents.shift()
  }

  for (const listener of listeners) {
    try {
      listener(event)
    } catch {
      // Best-effort fan-out only.
    }
  }
}

function buildBenchmarkState(detail: Record<string, unknown> | null | undefined): PredictionDashboardBenchmarkState {
  const canonical = detail ?? {}
  const fallback = canonical.research_benchmark_gate_summary ? canonical : {}
  const read = (key: string) => canonical[key] ?? fallback[key]

  return {
    ready: isTruthy(read('benchmark_promotion_ready')),
    gate_kind: normalizeString(read('benchmark_promotion_gate_kind')),
    status: normalizeString(read('benchmark_gate_status')),
    evidence_level: normalizeString(read('benchmark_evidence_level')),
    promotion_status: normalizeString(read('benchmark_promotion_status')),
    blocker_summary: normalizeString(read('benchmark_promotion_blocker_summary')),
    live_block_reason: normalizeString(read('benchmark_gate_live_block_reason')),
    blockers: normalizeStrings(read('benchmark_gate_blockers')),
    summary: normalizeString(read('benchmark_gate_summary')),
  }
}

function buildArbitrageState(detail: Record<string, unknown> | null | undefined): PredictionDashboardArbitrageState {
  const canonical = detail ?? {}
  const fallback = canonical.cross_venue_summary ? canonical : {}
  const read = (key: string) => canonical[key] ?? fallback[key]
  const crossVenueIntelligence = asRecord(read('cross_venue_intelligence')) ?? asRecord(asRecord(canonical.run)?.cross_venue_intelligence)
  const shadowArbitrage = asRecord(read('shadow_arbitrage')) ?? asRecord(asRecord(canonical.run)?.shadow_arbitrage)
  const crossVenueSummary = asRecord(read('cross_venue_summary'))
  const shadowSummary = asRecord(shadowArbitrage?.summary)

  const candidateCount = Array.isArray(crossVenueIntelligence?.arbitrage_candidates)
    ? crossVenueIntelligence.arbitrage_candidates.length
    : 0
  const manualReviewCount = Array.isArray(crossVenueSummary?.manual_review)
    ? crossVenueSummary.manual_review.length
    : 0
  const comparedPairs = typeof crossVenueSummary?.total_pairs === 'number'
    ? Number(crossVenueSummary.total_pairs)
    : Array.isArray(crossVenueIntelligence?.evaluations)
      ? crossVenueIntelligence.evaluations.length
      : candidateCount

  return {
    run_id: normalizeString(read('run_id')) ?? null,
    compared_pairs: comparedPairs,
    candidate_count: candidateCount,
    manual_review_count: manualReviewCount,
    best_shadow_edge_bps: typeof shadowSummary?.shadow_edge_bps === 'number' ? shadowSummary.shadow_edge_bps : null,
    best_shadow_size_usd: typeof shadowSummary?.recommended_size_usd === 'number' ? shadowSummary.recommended_size_usd : null,
    summary: normalizeString(
      candidateCount > 0
        ? `Cross-venue arbitrage scan found ${candidateCount} candidate${candidateCount === 1 ? '' : 's'}.`
        : 'No tradeable cross-venue execution plans were derived; the surface remains comparison-only.',
    ),
  }
}

function buildLatestRunProjection(detail: Record<string, unknown> | null | undefined) {
  const projection = detail?.execution_projection && typeof detail.execution_projection === 'object'
    ? detail.execution_projection as Record<string, unknown>
    : null

  const selectedPath = normalizeString(detail?.execution_projection_selected_path ?? projection?.selected_path)
  const selectedPathStatus = normalizeString(detail?.execution_projection_selected_path_status ?? projection?.selected_path_status)
  const liveRouteAllowed = selectedPath === 'live'
    ? isTruthy(detail?.execution_projection_selected_path_effective_mode === 'live' || detail?.execution_projection_recommended_effective_mode === 'live')
    : isTruthy(detail?.benchmark_gate_blocks_live === false)

  return {
    selected_path: selectedPath,
    selected_path_status: selectedPathStatus,
    live_route_allowed: liveRouteAllowed,
  }
}

function buildSnapshotPayload(snapshot: PredictionDashboardVenueSnapshot) {
  return {
    snapshot,
    benchmark_state: snapshot.benchmark_state,
    arbitrage_state: snapshot.arbitrage_state,
    latest_run_id: snapshot.latest_run_id,
    latest_run_updated_at: snapshot.latest_run_updated_at,
    latest_selected_path: snapshot.latest_selected_path,
    latest_selected_path_status: snapshot.latest_selected_path_status,
    latest_live_route_allowed: snapshot.latest_live_route_allowed,
    venue_health_status: snapshot.venue_health_status,
    venue_feed_status: snapshot.venue_feed_status,
    venue_user_feed_status: snapshot.venue_user_feed_status,
    venue_rtds_status: snapshot.venue_rtds_status,
    runs_total: snapshot.runs_total,
  }
}

export function publishPredictionDashboardEvent(input: Omit<PredictionDashboardEvent, 'event_id' | 'emitted_at'> & {
  emitted_at?: string
  event_id?: string
}): PredictionDashboardEvent {
  const event: PredictionDashboardEvent = {
    event_id: input.event_id ?? nextEventId(input.type),
    type: input.type,
    severity: input.severity,
    emitted_at: input.emitted_at ?? nowIso(),
    summary: input.summary,
    workspace_id: input.workspace_id ?? null,
    venue: input.venue ?? null,
    run_id: input.run_id ?? null,
    intent_id: input.intent_id ?? null,
    source: input.source,
    payload: input.payload ?? {},
  }

  pushEvent(event)
  return event
}

export function publishPredictionDashboardLiveIntentEvent(input: {
  workspaceId: number
  venue: PredictionMarketVenueId
  liveIntentId: string
  runId: string
  type: Extract<PredictionDashboardEventType, `live_intent_${string}`>
  summary: string
  severity?: PredictionDashboardEventSeverity
  payload?: Record<string, unknown>
}): PredictionDashboardEvent {
  return publishPredictionDashboardEvent({
    type: input.type,
    severity: input.severity ?? 'info',
    summary: input.summary,
    workspace_id: input.workspaceId,
    venue: input.venue,
    run_id: input.runId,
    intent_id: input.liveIntentId,
    source: 'workflow',
    payload: input.payload ?? {},
  })
}

export function comparePredictionDashboardArbitrageSnapshots(
  previous: PredictionDashboardArbitrageSnapshot | null,
  next: PredictionDashboardArbitrageSnapshot,
): Array<Omit<PredictionDashboardEvent, 'event_id' | 'emitted_at'>> {
  const events: Array<Omit<PredictionDashboardEvent, 'event_id' | 'emitted_at'>> = []
  const previousCandidates = new Map<string, PredictionDashboardArbitrageCandidate>()
  const nextCandidates = new Map<string, PredictionDashboardArbitrageCandidate>()

  for (const candidate of previous?.candidates ?? []) {
    previousCandidates.set(normalizeCandidateKey(candidate), candidate)
  }

  for (const candidate of next.candidates) {
    nextCandidates.set(normalizeCandidateKey(candidate), candidate)
  }

  for (const [candidateKey, candidate] of nextCandidates.entries()) {
    const previousCandidate = previousCandidates.get(candidateKey)
    const payload = {
      next: candidate,
      previous: previousCandidate ?? null,
      generated_at: next.generated_at,
      workspace_id: next.workspace_id,
      venue_pair: next.venue_pair,
      compared_pairs: next.compared_pairs,
      candidate_count: next.candidate_count,
      manual_review_count: next.manual_review_count,
      best_shadow_edge_bps: next.best_shadow_edge_bps,
    }

    if (!previousCandidate) {
      events.push({
        type: 'arbitrage_candidate_opened',
        severity: candidate.shadow_edge_bps > 0 ? 'info' : 'warn',
        workspace_id: next.workspace_id,
        venue: 'all',
        run_id: null,
        intent_id: null,
        source: 'poller',
        summary: `Arbitrage candidate opened for ${candidate.canonical_event_key}.`,
        payload,
      })
      continue
    }

    if (candidateFingerprint(previousCandidate) !== candidateFingerprint(candidate)) {
      events.push({
        type: 'arbitrage_candidate_updated',
        severity: candidate.shadow_edge_bps > 0 ? 'info' : 'warn',
        workspace_id: next.workspace_id,
        venue: 'all',
        run_id: null,
        intent_id: null,
        source: 'poller',
        summary: `Arbitrage candidate updated for ${candidate.canonical_event_key}.`,
        payload,
      })
    }
  }

  if (previous) {
    for (const [candidateKey, candidate] of previousCandidates.entries()) {
      if (nextCandidates.has(candidateKey)) continue
      events.push({
        type: 'arbitrage_candidate_closed',
        severity: 'info',
        workspace_id: previous.workspace_id,
        venue: 'all',
        run_id: null,
        intent_id: null,
        source: 'poller',
        summary: `Arbitrage candidate closed for ${candidate.canonical_event_key}.`,
        payload: {
          previous: candidate,
          next: null,
          generated_at: next.generated_at,
          workspace_id: next.workspace_id,
          venue_pair: next.venue_pair,
          compared_pairs: next.compared_pairs,
          candidate_count: next.candidate_count,
          manual_review_count: next.manual_review_count,
          best_shadow_edge_bps: next.best_shadow_edge_bps,
        },
      })
    }
  }

  return events
}

export function publishPredictionDashboardArbitrageSnapshot(
  next: PredictionDashboardArbitrageSnapshot,
  previous: PredictionDashboardArbitrageSnapshot | null = null,
): PredictionDashboardEvent[] {
  return comparePredictionDashboardArbitrageSnapshots(previous, next).map((event) =>
    publishPredictionDashboardEvent(event))
}

export function subscribePredictionDashboardEvents(listener: DashboardEventSubscriber): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function listRecentPredictionDashboardEvents(limit = 50): PredictionDashboardEvent[] {
  const boundedLimit = Math.max(1, Math.min(MAX_HISTORY, Math.round(limit)))
  return recentEvents.slice(-boundedLimit)
}

export function getPredictionDashboardEventHistory(filter: PredictionDashboardEventHistoryFilter = {}): PredictionDashboardEvent[] {
  const kinds = filter.kinds ? new Set(filter.kinds) : null
  return recentEvents
    .filter((event) =>
      (filter.workspaceId == null || event.workspace_id === filter.workspaceId)
      && (filter.venue == null || filter.venue === 'all' || event.venue === filter.venue || event.venue === 'all')
      && (kinds == null || kinds.has(event.type)))
    .slice(-(filter.limit ?? MAX_HISTORY))
}

export function resetPredictionDashboardEventStateForTests() {
  recentEvents.splice(0, recentEvents.length)
  listeners.clear()
  sequence = 0
  for (const observer of observers.values()) {
    if (observer.timer) clearInterval(observer.timer)
  }
  observers.clear()
}

export async function buildPredictionDashboardVenueSnapshot(input: PredictionDashboardVenueObservation): Promise<PredictionDashboardVenueSnapshot> {
  const runs = listPredictionMarketRuns({
    workspaceId: input.workspaceId,
    venue: input.venue,
    limit: input.limit ?? DEFAULT_LIMIT,
  })
  const latestRun = runs[0] ?? null
  const latestDetail = latestRun ? getPredictionMarketRunDetails(latestRun.run_id, input.workspaceId) : null
  const health = getVenueHealthSnapshot(input.venue)
  const capabilities = getVenueCapabilities(input.venue)
  const latestProjection = buildLatestRunProjection(latestDetail ?? latestRun)

  return {
    workspace_id: input.workspaceId,
    venue: input.venue,
    captured_at: nowIso(),
    runs_total: runs.length,
    latest_run_id: latestRun?.run_id ?? null,
    latest_run_updated_at: latestRun?.updated_at ?? null,
    latest_recommendation: latestRun?.recommendation ?? null,
    latest_selected_path: latestProjection.selected_path,
    latest_selected_path_status: latestProjection.selected_path_status,
    latest_live_route_allowed: latestProjection.live_route_allowed,
    benchmark_state: buildBenchmarkState(latestDetail ?? latestRun),
    venue_health_status: normalizeString(health.status),
    venue_feed_status: normalizeString((health as Record<string, unknown>).market_feed_status),
    venue_user_feed_status: normalizeString((health as Record<string, unknown>).user_feed_status),
    venue_rtds_status: normalizeString((health as Record<string, unknown>).rtds_status),
    venue_capabilities: normalizeString(capabilities.venue_type),
    venue_supports_execution: typeof (capabilities as Record<string, unknown>).supports_execution === 'boolean'
      ? Boolean((capabilities as Record<string, unknown>).supports_execution)
      : null,
    venue_supports_paper_mode: typeof (capabilities as Record<string, unknown>).supports_paper_mode === 'boolean'
      ? Boolean((capabilities as Record<string, unknown>).supports_paper_mode)
      : null,
    venue_notes: normalizeStrings((capabilities as Record<string, unknown>).notes),
    arbitrage_state: buildArbitrageState(latestDetail ?? latestRun),
  }
}

export function comparePredictionDashboardVenueSnapshots(
  previous: PredictionDashboardVenueSnapshot | null,
  next: PredictionDashboardVenueSnapshot,
): Array<Omit<PredictionDashboardEvent, 'event_id' | 'emitted_at'>> {
  const events: Array<Omit<PredictionDashboardEvent, 'event_id' | 'emitted_at'>> = []
  const previousArbitrageState = previous?.arbitrage_state ?? emptyArbitrageState()
  const nextArbitrageState = next.arbitrage_state ?? emptyArbitrageState()

  if (!previous) {
    events.push({
      type: 'dashboard_snapshot',
      severity: 'info',
      workspace_id: next.workspace_id,
      venue: next.venue,
      run_id: next.latest_run_id,
      intent_id: null,
      source: 'poller',
      summary: `Dashboard snapshot captured for ${next.venue}.`,
      payload: buildSnapshotPayload(next),
    })

    if (next.runs_total > 0) {
      events.push({
        type: 'runs_refresh_hint',
        severity: 'info',
        workspace_id: next.workspace_id,
        venue: next.venue,
        run_id: next.latest_run_id,
        intent_id: null,
        source: 'poller',
        summary: `Runs list loaded for ${next.venue}: ${next.runs_total} runs.`,
        payload: {
          runs_total: next.runs_total,
          latest_run_id: next.latest_run_id,
          latest_selected_path: next.latest_selected_path,
        },
      })
    }

    return events
  }

  if (
    previous.runs_total !== next.runs_total
    || previous.latest_run_id !== next.latest_run_id
    || previous.latest_run_updated_at !== next.latest_run_updated_at
  ) {
    events.push({
      type: previous.latest_run_id !== next.latest_run_id ? 'latest_run_changed' : 'runs_refresh_hint',
      severity: 'info',
      workspace_id: next.workspace_id,
      venue: next.venue,
      run_id: next.latest_run_id,
      intent_id: null,
      source: 'poller',
      summary: previous.latest_run_id !== next.latest_run_id
        ? `Latest run changed for ${next.venue}.`
        : `Runs list refreshed for ${next.venue}: ${next.runs_total} runs.`,
      payload: {
        previous_runs_total: previous.runs_total,
        runs_total: next.runs_total,
        previous_latest_run_id: previous.latest_run_id,
        latest_run_id: next.latest_run_id,
      },
    })
  }

  if (!sameValue(previous.venue_health_status, next.venue_health_status)) {
    const degraded = next.venue_health_status !== 'ready'
    events.push({
      type: degraded ? 'venue_degraded' : 'venue_recovered',
      severity: degraded ? 'warn' : 'info',
      workspace_id: next.workspace_id,
      venue: next.venue,
      run_id: next.latest_run_id,
      intent_id: null,
      source: 'poller',
      summary: degraded
        ? `${next.venue} health degraded.`
        : `${next.venue} health recovered.`,
      payload: {
        previous_health_status: previous.venue_health_status,
        health_status: next.venue_health_status,
        venue_feed_status: next.venue_feed_status,
        venue_user_feed_status: next.venue_user_feed_status,
        venue_rtds_status: next.venue_rtds_status,
      },
    })
  }

  if (
    !sameValue(previous.benchmark_state.ready, next.benchmark_state.ready)
    || !sameValue(previous.benchmark_state.status, next.benchmark_state.status)
    || !sameValue(previous.benchmark_state.gate_kind, next.benchmark_state.gate_kind)
    || !sameValue(previous.benchmark_state.evidence_level, next.benchmark_state.evidence_level)
    || !sameValue(previous.benchmark_state.live_block_reason, next.benchmark_state.live_block_reason)
    || !sameValue(previous.benchmark_state.blocker_summary, next.benchmark_state.blocker_summary)
    || !sameValue(previous.benchmark_state.summary, next.benchmark_state.summary)
  ) {
    events.push({
      type: 'benchmark_gate_changed',
      severity: next.benchmark_state.ready ? 'info' : 'warn',
      workspace_id: next.workspace_id,
      venue: next.venue,
      run_id: next.latest_run_id,
      intent_id: null,
      source: 'poller',
      summary: `Benchmark gate changed for ${next.venue}.`,
      payload: {
        previous: previous.benchmark_state,
        next: next.benchmark_state,
      },
    })
  }

  if (
    !sameValue(previousArbitrageState.candidate_count, nextArbitrageState.candidate_count)
    || !sameValue(previousArbitrageState.manual_review_count, nextArbitrageState.manual_review_count)
    || !sameValue(previousArbitrageState.best_shadow_edge_bps, nextArbitrageState.best_shadow_edge_bps)
    || !sameValue(previousArbitrageState.best_shadow_size_usd, nextArbitrageState.best_shadow_size_usd)
    || !sameValue(previousArbitrageState.summary, nextArbitrageState.summary)
  ) {
    const previousCount = previousArbitrageState.candidate_count
    const nextCount = nextArbitrageState.candidate_count
    const eventType =
      previousCount === 0 && nextCount > 0
        ? 'arbitrage_candidate_opened'
        : previousCount > 0 && nextCount === 0
          ? 'arbitrage_candidate_closed'
          : 'arbitrage_candidate_updated'

    events.push({
      type: eventType,
      severity: nextCount > 0 ? 'info' : 'warn',
      workspace_id: next.workspace_id,
      venue: next.venue,
      run_id: next.latest_run_id,
      intent_id: null,
      source: 'poller',
      summary: `Cross-venue arbitrage changed for ${next.venue}.`,
      payload: {
        previous: previousArbitrageState,
        next: nextArbitrageState,
      },
    })
  }

  return events
}

function observerKey(input: PredictionDashboardVenueObservation) {
  return `${input.workspaceId}:${input.venue}`
}

export function ensurePredictionDashboardVenuePolling(input: PredictionDashboardVenueObservation): () => void {
  const key = observerKey(input)
  const existing = observers.get(key)
  if (existing) {
    existing.subscribers += 1
    if (!existing.snapshot && input.initialSnapshot) {
      existing.snapshot = input.initialSnapshot
    }
    return () => stopPredictionDashboardVenuePolling(input)
  }

  const state: DashboardObserverState = {
    snapshot: input.initialSnapshot ?? null,
    subscribers: 1,
    timer: null,
    pollIntervalMs: input.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS,
    limit: input.limit ?? DEFAULT_LIMIT,
  }

  const poll = async () => {
    try {
      const next = await buildPredictionDashboardVenueSnapshot({
        workspaceId: input.workspaceId,
        venue: input.venue,
        limit: state.limit,
      })
      const events = comparePredictionDashboardVenueSnapshots(state.snapshot, next)
      state.snapshot = next
      for (const event of events) {
        publishPredictionDashboardEvent(event)
      }
    } catch (error) {
      publishPredictionDashboardEvent({
        type: 'runs_refresh_hint',
        severity: 'warn',
        workspace_id: input.workspaceId,
        venue: input.venue,
        run_id: null,
        intent_id: null,
        source: 'poller',
        summary: `Dashboard poll failed for ${input.venue}.`,
        payload: {
          error: error instanceof Error ? error.message : String(error),
        },
      })
    }
  }

  state.timer = setInterval(() => {
    void poll()
  }, state.pollIntervalMs)
  observers.set(key, state)
  void poll()

  return () => stopPredictionDashboardVenuePolling(input)
}

export function stopPredictionDashboardVenuePolling(input: PredictionDashboardVenueObservation) {
  const key = observerKey(input)
  const existing = observers.get(key)
  if (!existing) return

  existing.subscribers -= 1
  if (existing.subscribers > 0) return

  if (existing.timer) clearInterval(existing.timer)
  observers.delete(key)
}

export function formatPredictionDashboardEventAsSse(event: PredictionDashboardEvent): string {
  const lines = [
    `id: ${event.event_id}`,
    `event: ${event.type}`,
    `data: ${JSON.stringify(event)}`,
  ]

  return `${lines.join('\n')}\n\n`
}

export function formatPredictionDashboardSseComment(comment: string): string {
  const safe = comment.replaceAll('\n', ' ').trim()
  return `: ${safe}\n\n`
}
