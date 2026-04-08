import { randomUUID } from 'node:crypto'
import { clearInterval, setInterval } from 'node:timers'

import { buildKalshiSnapshot, listKalshiMarkets } from '@/lib/prediction-markets/kalshi'
import { buildMicrostructureLabReport } from '@/lib/prediction-markets/microstructure-lab'
import { buildPolymarketSnapshot, listPolymarketMarkets } from '@/lib/prediction-markets/polymarket'
import {
  evaluateCrossVenuePair,
  findCrossVenueMatches,
  summarizeCrossVenueIntelligence,
  type CrossVenueArbitrageCandidate,
  type CrossVenueEvaluation,
} from '@/lib/prediction-markets/cross-venue'
import {
  buildShadowArbitrageSimulation,
} from '@/lib/prediction-markets/shadow-arbitrage'
import {
  marketRecommendationPacketSchema,
  type MarketDescriptor,
  type MarketRecommendationPacket,
  type PredictionMarketVenue,
} from '@/lib/prediction-markets/schemas'
import {
  publishPredictionDashboardEvent,
  type PredictionDashboardEvent,
} from '@/lib/prediction-markets/dashboard-events'

export type DashboardFreshness = 'fresh' | 'warm' | 'stale'

export type PredictionDashboardArbitrageCandidate = {
  candidate_id: string
  canonical_event_id: string
  canonical_event_key: string
  opportunity_type: CrossVenueArbitrageCandidate['opportunity_type']
  buy_venue: PredictionMarketVenue
  sell_venue: PredictionMarketVenue
  buy_market_id: string
  sell_market_id: string
  buy_question: string
  sell_question: string
  buy_price_yes: number
  sell_price_yes: number
  gross_spread_bps: number
  net_spread_bps: number
  executable_edge_bps: number | null
  confidence_score: number
  manual_review_required: boolean
  shadow_ready: boolean
  shadow_edge_bps: number | null
  recommended_size_usd: number | null
  hedge_success_probability: number | null
  estimated_net_pnl_bps: number | null
  estimated_net_pnl_usd: number | null
  freshness_ms: number | null
  blocking_reasons: string[]
  notes: string[]
}

export type PredictionDashboardArbitrageOverview = {
  compared_pairs: number
  compatible_pairs: number
  candidate_count: number
  manual_review_count: number
  comparison_only_count: number
  shadow_ready_count: number
  best_shadow_edge_bps: number | null
  best_net_spread_bps: number | null
  best_executable_edge_bps: number | null
  best_candidate_id: string | null
  summary: string
  errors: string[]
}

export type PredictionDashboardArbitrageSnapshot = {
  generated_at: string
  freshness: DashboardFreshness
  transport: 'polling'
  workspace_id: number
  venue_pair: readonly [PredictionMarketVenue, PredictionMarketVenue]
  route: '/dashboard/arbitrage'
  filters: {
    limit_per_venue: number
    max_pairs: number
    min_arbitrage_spread_bps: number
    shadow_candidates: number
  }
  compared_pairs: number
  candidate_count: number
  manual_review_count: number
  shadow_ready_count: number
  best_shadow_edge_bps: number | null
  best_net_spread_bps: number | null
  summary: string
  overview: PredictionDashboardArbitrageOverview
  candidates: PredictionDashboardArbitrageCandidate[]
}

export type PredictionDashboardArbitrageSnapshotInput = {
  workspaceId: number
  limitPerVenue?: number
  maxPairs?: number
  minArbitrageSpreadBps?: number
  shadowCandidateLimit?: number
  pollIntervalMs?: number
  forceRefresh?: boolean
}

type ArbitrageScannerState = {
  snapshot: PredictionDashboardArbitrageSnapshot | null
  refreshPromise: Promise<PredictionDashboardArbitrageSnapshot> | null
  timer: ReturnType<typeof setInterval> | null
  pollIntervalMs: number
  options: Required<Omit<PredictionDashboardArbitrageSnapshotInput, 'workspaceId' | 'forceRefresh'>>
}

const GLOBAL_KEY = Symbol.for('prediction-markets.dashboard-arbitrage-scanner')

const DEFAULT_OPTIONS: ArbitrageScannerState['options'] = {
  limitPerVenue: 16,
  maxPairs: 40,
  minArbitrageSpreadBps: 25,
  shadowCandidateLimit: 8,
  pollIntervalMs: 60_000,
}

function getGlobalState() {
  const globalScope = globalThis as typeof globalThis & {
    [GLOBAL_KEY]?: Map<number, ArbitrageScannerState>
  }

  if (!globalScope[GLOBAL_KEY]) {
    globalScope[GLOBAL_KEY] = new Map<number, ArbitrageScannerState>()
  }

  return globalScope[GLOBAL_KEY]
}

function nowIso(): string {
  return new Date().toISOString()
}

function freshnessFromAgeMs(ageMs: number): DashboardFreshness {
  if (ageMs <= 30_000) return 'fresh'
  if (ageMs <= 300_000) return 'warm'
  return 'stale'
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function round(value: number): number {
  return Math.round(value)
}

function toDescriptorKey(venue: PredictionMarketVenue, marketId: string) {
  return `${venue}:${marketId}`
}

function getMarketPriceYes(market: MarketDescriptor) {
  const midpoint = market.best_bid != null && market.best_ask != null
    ? Number(((market.best_bid + market.best_ask) / 2).toFixed(6))
    : null

  return market.last_trade_price ?? midpoint ?? market.best_bid ?? market.best_ask ?? 0.5
}

function buildRecommendationPacket(input: {
  market: MarketDescriptor
  candidate: CrossVenueArbitrageCandidate
}): MarketRecommendationPacket {
  const marketPriceYes = getMarketPriceYes(input.market)
  const fairValueYes = clamp(
    (input.candidate.buy_price_yes + input.candidate.sell_price_yes) / 2,
    0,
    1,
  )

  return marketRecommendationPacketSchema.parse({
    schema_version: input.market.schema_version,
    market_id: input.market.market_id,
    venue: input.market.venue,
    action: input.candidate.executable ? 'bet' : 'wait',
    side: input.candidate.executable ? 'yes' : null,
    confidence: clamp(input.candidate.confidence_score, 0, 1),
    fair_value_yes: fairValueYes,
    market_price_yes: marketPriceYes,
    market_bid_yes: input.market.best_bid ?? null,
    market_ask_yes: input.market.best_ask ?? null,
    edge_bps: input.candidate.executable_edge.executable_edge_bps,
    spread_bps: input.candidate.gross_spread_bps,
    reasons: [
      `cross_venue_candidate:${input.candidate.candidate_type}`,
      `opportunity_type:${input.candidate.opportunity_type}`,
      ...input.candidate.reasons,
    ],
    risk_flags: input.candidate.executable ? [] : ['shadow_only', 'manual_review_required'],
    rationale: `Cross-venue arbitrage candidate for ${input.candidate.canonical_event_key}.`,
    why_now: [
      `gross_spread_bps:${input.candidate.gross_spread_bps}`,
      `net_spread_bps:${input.candidate.net_spread_bps}`,
    ],
    why_not_now: input.candidate.executable ? [] : ['Cross-venue execution is not yet executable from the cached snapshot.'],
    watch_conditions: [
      'shadow_edge_remaining_positive',
      'freshness_within_budget',
      'venue_health_ready',
    ],
    comparable_market_refs: [
      input.candidate.buy_ref.market_id,
      input.candidate.sell_ref.market_id,
    ],
    requires_manual_review: !input.candidate.executable || input.candidate.market_equivalence_proof.manual_review_required,
    produced_at: nowIso(),
  })
}

function candidateSignature(candidate: PredictionDashboardArbitrageCandidate): string {
  return JSON.stringify({
    candidate_id: candidate.candidate_id,
    opportunity_type: candidate.opportunity_type,
    buy_venue: candidate.buy_venue,
    sell_venue: candidate.sell_venue,
    gross_spread_bps: candidate.gross_spread_bps,
    net_spread_bps: candidate.net_spread_bps,
    executable_edge_bps: candidate.executable_edge_bps,
    shadow_edge_bps: candidate.shadow_edge_bps,
    shadow_ready: candidate.shadow_ready,
    manual_review_required: candidate.manual_review_required,
    blocking_reasons: candidate.blocking_reasons,
  })
}

function publishArbitrageDiff(
  workspaceId: number,
  previous: PredictionDashboardArbitrageSnapshot | null,
  next: PredictionDashboardArbitrageSnapshot,
) {
  const previousCandidates = new Map(previous?.candidates.map((candidate) => [candidate.candidate_id, candidate]) ?? [])
  const nextCandidates = new Map(next.candidates.map((candidate) => [candidate.candidate_id, candidate]))

  for (const [candidateId, candidate] of nextCandidates) {
    const before = previousCandidates.get(candidateId)
    if (!before) {
      publishPredictionDashboardEvent({
        type: 'arbitrage_candidate_opened',
        severity: candidate.shadow_ready ? 'info' : 'warn',
        workspace_id: workspaceId,
        venue: 'all',
        run_id: null,
        intent_id: null,
        source: 'workflow',
        summary: `Arbitrage candidate opened: ${candidate.canonical_event_key}.`,
        payload: {
          candidate,
          snapshot_generated_at: next.generated_at,
        },
      })
      continue
    }

    if (candidateSignature(before) !== candidateSignature(candidate)) {
      publishPredictionDashboardEvent({
        type: 'arbitrage_candidate_updated',
        severity: candidate.shadow_ready ? 'info' : 'warn',
        workspace_id: workspaceId,
        venue: 'all',
        run_id: null,
        intent_id: null,
        source: 'workflow',
        summary: `Arbitrage candidate updated: ${candidate.canonical_event_key}.`,
        payload: {
          previous: before,
          next: candidate,
          snapshot_generated_at: next.generated_at,
        },
      })
    }
  }

  if (previous) {
    for (const [candidateId, candidate] of previousCandidates) {
      if (nextCandidates.has(candidateId)) continue
      publishPredictionDashboardEvent({
        type: 'arbitrage_candidate_closed',
        severity: 'info',
        workspace_id: workspaceId,
        venue: 'all',
        run_id: null,
        intent_id: null,
        source: 'workflow',
        summary: `Arbitrage candidate closed: ${candidate.canonical_event_key}.`,
        payload: {
          candidate,
          snapshot_generated_at: next.generated_at,
        },
      })
    }
  }
}

function getState(workspaceId: number, options?: Partial<ArbitrageScannerState['options']>) {
  const stateMap = getGlobalState()
  let state = stateMap.get(workspaceId)

  if (!state) {
    state = {
      snapshot: null,
      refreshPromise: null,
      timer: null,
      pollIntervalMs: DEFAULT_OPTIONS.pollIntervalMs,
      options: { ...DEFAULT_OPTIONS },
    }
    stateMap.set(workspaceId, state)
  }

  if (options) {
    state.options = {
      limitPerVenue: options.limitPerVenue ?? state.options.limitPerVenue,
      maxPairs: options.maxPairs ?? state.options.maxPairs,
      minArbitrageSpreadBps: options.minArbitrageSpreadBps ?? state.options.minArbitrageSpreadBps,
      shadowCandidateLimit: options.shadowCandidateLimit ?? state.options.shadowCandidateLimit,
      pollIntervalMs: options.pollIntervalMs ?? state.options.pollIntervalMs,
    }
    state.pollIntervalMs = state.options.pollIntervalMs
  }

  return state
}

function uniqueMarketMap(markets: MarketDescriptor[]) {
  const map = new Map<string, MarketDescriptor>()
  for (const market of markets) {
    if (!market.is_binary_yes_no) continue
    if (!market.active || market.closed) continue
    map.set(toDescriptorKey(market.venue, market.market_id), market)
  }
  return map
}

async function loadVenueMarkets(limitPerVenue: number) {
  const [polymarketMarkets, kalshiMarkets] = await Promise.all([
    listPolymarketMarkets({ limit: limitPerVenue, active: true, closed: false }),
    listKalshiMarkets({ limit: limitPerVenue, active: true, closed: false }),
  ])

  return {
    markets: [...polymarketMarkets, ...kalshiMarkets],
    marketMap: uniqueMarketMap([...polymarketMarkets, ...kalshiMarkets]),
  }
}

async function buildShadowCandidate(
  evaluation: CrossVenueEvaluation,
  marketMap: Map<string, MarketDescriptor>,
): Promise<PredictionDashboardArbitrageCandidate> {
  const candidate = evaluation.arbitrage_candidate
  const buyMarket = marketMap.get(toDescriptorKey(candidate?.buy_ref.venue ?? 'polymarket', candidate?.buy_ref.market_id ?? ''))
  const sellMarket = marketMap.get(toDescriptorKey(candidate?.sell_ref.venue ?? 'kalshi', candidate?.sell_ref.market_id ?? ''))
  const generatedAt = nowIso()

  if (!candidate || !buyMarket || !sellMarket) {
    return {
      candidate_id: candidate?.arb_plan.arb_plan_id ?? `arb:${evaluation.canonical_event_id}:${randomUUID()}`,
      canonical_event_id: evaluation.canonical_event_id,
      canonical_event_key: evaluation.canonical_event_key,
      opportunity_type: evaluation.opportunity_type,
      buy_venue: candidate?.buy_ref.venue ?? buyMarket?.venue ?? 'polymarket',
      sell_venue: candidate?.sell_ref.venue ?? sellMarket?.venue ?? 'kalshi',
      buy_market_id: candidate?.buy_ref.market_id ?? buyMarket?.market_id ?? 'unknown',
      sell_market_id: candidate?.sell_ref.market_id ?? sellMarket?.market_id ?? 'unknown',
      buy_question: buyMarket?.question ?? 'n/a',
      sell_question: sellMarket?.question ?? 'n/a',
      buy_price_yes: candidate?.buy_price_yes ?? buyMarket?.last_trade_price ?? 0.5,
      sell_price_yes: candidate?.sell_price_yes ?? sellMarket?.last_trade_price ?? 0.5,
      gross_spread_bps: candidate?.gross_spread_bps ?? 0,
      net_spread_bps: candidate?.net_spread_bps ?? 0,
      executable_edge_bps: candidate?.executable_edge.executable_edge_bps ?? null,
      confidence_score: evaluation.confidence_score,
      manual_review_required: true,
      shadow_ready: false,
      shadow_edge_bps: null,
      recommended_size_usd: null,
      hedge_success_probability: null,
      estimated_net_pnl_bps: null,
      estimated_net_pnl_usd: null,
      freshness_ms: null,
      blocking_reasons: ['cross_venue_snapshot_unavailable'],
      notes: ['Unable to materialize a shadow candidate because one or both venue snapshots are missing.'],
    }
  }

  const [buySnapshot, sellSnapshot] = await Promise.all([
    buyMarket.venue === 'polymarket'
      ? buildPolymarketSnapshot({ marketId: buyMarket.market_id, historyLimit: 40 })
      : buildKalshiSnapshot({ marketId: buyMarket.market_id, historyLimit: 40 }),
    sellMarket.venue === 'polymarket'
      ? buildPolymarketSnapshot({ marketId: sellMarket.market_id, historyLimit: 40 })
      : buildKalshiSnapshot({ marketId: sellMarket.market_id, historyLimit: 40 }),
  ])

  const refinedEvaluation = evaluateCrossVenuePair({
    left: buyMarket,
    right: sellMarket,
    leftSnapshot: buySnapshot,
    rightSnapshot: sellSnapshot,
    asOfAt: generatedAt,
  })

  const refinedCandidate = refinedEvaluation.arbitrage_candidate ?? candidate
  const recommendation = buildRecommendationPacket({
    market: buyMarket,
    candidate: refinedCandidate,
  })
  const microstructure = buildMicrostructureLabReport({
    snapshot: buySnapshot,
    recommendation,
    trade_intent: {
      size_usd: refinedCandidate.arb_plan.required_capital_usd,
      max_unhedged_leg_ms: refinedCandidate.arb_plan.max_unhedged_leg_ms,
      time_in_force: 'gtc',
    },
    generated_at: generatedAt,
  })
  const shadow = buildShadowArbitrageSimulation({
    executable_edge: refinedCandidate.executable_edge,
    microstructure_summary: microstructure.summary,
    size_usd: refinedCandidate.arb_plan.required_capital_usd,
    generated_at: generatedAt,
    as_of_at: generatedAt,
  })
  const freshnessMs = Math.max(
    0,
    Date.now() - Date.parse(buySnapshot.captured_at),
    Date.now() - Date.parse(sellSnapshot.captured_at),
  )
  const blockingReasons = [
    ...refinedCandidate.reasons,
    ...(refinedCandidate.executable ? [] : ['non_executable_candidate']),
    ...(shadow.summary.shadow_edge_bps > 0 ? [] : ['shadow_edge_non_positive']),
    ...(shadow.summary.hedge_success_expected ? [] : ['shadow_not_robust']),
  ]

  return {
    candidate_id: refinedCandidate.arb_plan.arb_plan_id,
    canonical_event_id: refinedCandidate.canonical_event_id,
    canonical_event_key: refinedCandidate.canonical_event_key,
    opportunity_type: refinedCandidate.opportunity_type,
    buy_venue: refinedCandidate.buy_ref.venue,
    sell_venue: refinedCandidate.sell_ref.venue,
    buy_market_id: refinedCandidate.buy_ref.market_id,
    sell_market_id: refinedCandidate.sell_ref.market_id,
    buy_question: buyMarket.question,
    sell_question: sellMarket.question,
    buy_price_yes: refinedCandidate.buy_price_yes,
    sell_price_yes: refinedCandidate.sell_price_yes,
    gross_spread_bps: refinedCandidate.gross_spread_bps,
    net_spread_bps: refinedCandidate.net_spread_bps,
    executable_edge_bps: refinedCandidate.executable_edge.executable_edge_bps,
    confidence_score: refinedCandidate.confidence_score,
    manual_review_required:
      refinedCandidate.market_equivalence_proof.manual_review_required ||
      !refinedCandidate.executable ||
      shadow.summary.hedge_success_expected === false,
    shadow_ready:
      refinedCandidate.executable &&
      shadow.summary.shadow_edge_bps > 0 &&
      shadow.summary.hedge_success_expected,
    shadow_edge_bps: shadow.summary.shadow_edge_bps,
    recommended_size_usd: shadow.summary.recommended_size_usd,
    hedge_success_probability: shadow.summary.hedge_success_probability,
    estimated_net_pnl_bps: shadow.summary.estimated_net_pnl_bps,
    estimated_net_pnl_usd: shadow.summary.estimated_net_pnl_usd,
    freshness_ms: freshnessMs,
    blocking_reasons: Array.from(new Set(blockingReasons)),
    notes: [
      ...refinedCandidate.reasons,
      ...refinedCandidate.executable_edge.notes,
      ...shadow.summary.notes,
    ],
  }
}

async function refreshArbitrageSnapshot(
  workspaceId: number,
  options: ArbitrageScannerState['options'],
): Promise<PredictionDashboardArbitrageSnapshot> {
  const generatedAt = nowIso()
  const errors: string[] = []
  const { markets, marketMap } = await loadVenueMarkets(options.limitPerVenue)
  const evaluations = findCrossVenueMatches({
    markets,
    snapshots: [],
    includeManualReview: true,
    maxPairs: options.maxPairs,
    minArbitrageSpreadBps: options.minArbitrageSpreadBps,
  })
  const summary = summarizeCrossVenueIntelligence(evaluations)
  const candidates = summary.compatible
    .filter((evaluation) => evaluation.arbitrage_candidate != null)
    .slice(0, options.shadowCandidateLimit)

  const builtCandidates = await Promise.all(candidates.map(async (evaluation) => {
    try {
      return await buildShadowCandidate(evaluation, marketMap)
    } catch (error) {
      errors.push(`shadow refresh failed for ${evaluation.canonical_event_key}: ${error instanceof Error ? error.message : String(error)}`)
      const candidate = evaluation.arbitrage_candidate
      return {
        candidate_id: candidate?.arb_plan.arb_plan_id ?? `arb:${evaluation.canonical_event_id}:${randomUUID()}`,
        canonical_event_id: evaluation.canonical_event_id,
        canonical_event_key: evaluation.canonical_event_key,
        opportunity_type: evaluation.opportunity_type,
        buy_venue: candidate?.buy_ref.venue ?? 'polymarket',
        sell_venue: candidate?.sell_ref.venue ?? 'kalshi',
        buy_market_id: candidate?.buy_ref.market_id ?? 'unknown',
        sell_market_id: candidate?.sell_ref.market_id ?? 'unknown',
        buy_question: marketMap.get(toDescriptorKey(candidate?.buy_ref.venue ?? 'polymarket', candidate?.buy_ref.market_id ?? ''))?.question ?? 'n/a',
        sell_question: marketMap.get(toDescriptorKey(candidate?.sell_ref.venue ?? 'kalshi', candidate?.sell_ref.market_id ?? ''))?.question ?? 'n/a',
        buy_price_yes: candidate?.buy_price_yes ?? 0.5,
        sell_price_yes: candidate?.sell_price_yes ?? 0.5,
        gross_spread_bps: candidate?.gross_spread_bps ?? 0,
        net_spread_bps: candidate?.net_spread_bps ?? 0,
        executable_edge_bps: candidate?.executable_edge.executable_edge_bps ?? null,
        confidence_score: evaluation.confidence_score,
        manual_review_required: true,
        shadow_ready: false,
        shadow_edge_bps: null,
        recommended_size_usd: null,
        hedge_success_probability: null,
        estimated_net_pnl_bps: null,
        estimated_net_pnl_usd: null,
        freshness_ms: null,
        blocking_reasons: ['shadow_refresh_error'],
        notes: [error instanceof Error ? error.message : String(error)],
      }
    }
  }))

  const bestCandidate = builtCandidates[0] ?? null
  const shadowReadyCount = builtCandidates.filter((candidate) => candidate.shadow_ready).length
  const bestShadowEdgeBps = builtCandidates.reduce<number | null>((best, candidate) => {
    if (candidate.shadow_edge_bps == null) return best
    if (best == null) return candidate.shadow_edge_bps
    return Math.max(best, candidate.shadow_edge_bps)
  }, null)
  const bestNetSpreadBps = builtCandidates.reduce<number | null>((best, candidate) => {
    if (best == null) return candidate.net_spread_bps
    return Math.max(best, candidate.net_spread_bps)
  }, null)
  const bestExecutableEdgeBps = builtCandidates.reduce<number | null>((best, candidate) => {
    if (candidate.executable_edge_bps == null) return best
    if (best == null) return candidate.executable_edge_bps
    return Math.max(best, candidate.executable_edge_bps)
  }, null)

  const snapshot: PredictionDashboardArbitrageSnapshot = {
    generated_at: generatedAt,
    freshness: freshnessFromAgeMs(0),
    transport: 'polling',
    workspace_id: workspaceId,
    venue_pair: ['polymarket', 'kalshi'],
    route: '/dashboard/arbitrage',
    filters: {
      limit_per_venue: options.limitPerVenue,
      max_pairs: options.maxPairs,
      min_arbitrage_spread_bps: options.minArbitrageSpreadBps,
      shadow_candidates: options.shadowCandidateLimit,
    },
    compared_pairs: summary.total_pairs,
    candidate_count: builtCandidates.length,
    manual_review_count: summary.manual_review.length,
    shadow_ready_count: shadowReadyCount,
    best_shadow_edge_bps: bestShadowEdgeBps,
    best_net_spread_bps: bestNetSpreadBps,
    summary: builtCandidates.length > 0
      ? `Found ${builtCandidates.length} cross-venue candidates across ${summary.total_pairs} compared pairs.`
      : `No cross-venue candidates found across ${summary.total_pairs} compared pairs.`,
    overview: {
      compared_pairs: summary.total_pairs,
      compatible_pairs: summary.compatible.length,
      candidate_count: builtCandidates.length,
      manual_review_count: summary.manual_review.length,
      comparison_only_count: summary.comparison_only.length,
      shadow_ready_count: shadowReadyCount,
      best_shadow_edge_bps: bestShadowEdgeBps,
      best_net_spread_bps: bestNetSpreadBps,
      best_executable_edge_bps: bestExecutableEdgeBps,
      best_candidate_id: bestCandidate?.candidate_id ?? null,
      summary: builtCandidates.length > 0
        ? `Found ${builtCandidates.length} cross-venue candidates across ${summary.total_pairs} compared pairs.`
        : `No cross-venue candidates found across ${summary.total_pairs} compared pairs.`,
      errors,
    },
    candidates: builtCandidates.sort((left, right) => {
      if ((right.shadow_edge_bps ?? -1) !== (left.shadow_edge_bps ?? -1)) {
        return (right.shadow_edge_bps ?? -1) - (left.shadow_edge_bps ?? -1)
      }
      if (right.net_spread_bps !== left.net_spread_bps) {
        return right.net_spread_bps - left.net_spread_bps
      }
      return right.confidence_score - left.confidence_score
    }),
  }

  return snapshot
}

function getStateWithOptions(workspaceId: number, options?: Partial<PredictionDashboardArbitrageSnapshotInput>) {
  return getState(workspaceId, {
    limitPerVenue: options?.limitPerVenue,
    maxPairs: options?.maxPairs,
    minArbitrageSpreadBps: options?.minArbitrageSpreadBps,
    shadowCandidateLimit: options?.shadowCandidateLimit,
    pollIntervalMs: options?.pollIntervalMs,
  })
}

function ensurePolling(workspaceId: number, state: ArbitrageScannerState) {
  if (state.timer) return
  state.timer = setInterval(() => {
    void refreshPredictionDashboardArbitrageSnapshot(workspaceId, state.options)
  }, state.pollIntervalMs)
}

async function refreshPredictionDashboardArbitrageSnapshot(
  workspaceId: number,
  input: Partial<Omit<PredictionDashboardArbitrageSnapshotInput, 'workspaceId'>> = {},
): Promise<PredictionDashboardArbitrageSnapshot> {
  return getPredictionDashboardArbitrageSnapshot({
    workspaceId,
    ...input,
    forceRefresh: true,
  })
}

export function ensurePredictionDashboardArbitragePolling(
  input: PredictionDashboardArbitrageSnapshotInput,
): void {
  const state = getStateWithOptions(input.workspaceId, input)
  ensurePolling(input.workspaceId, state)
}

export async function getPredictionDashboardArbitrageSnapshot(
  input: PredictionDashboardArbitrageSnapshotInput,
): Promise<PredictionDashboardArbitrageSnapshot> {
  const state = getStateWithOptions(input.workspaceId, input)
  ensurePolling(input.workspaceId, state)

  const snapshotAgeMs = state.snapshot?.generated_at
    ? Date.now() - Date.parse(state.snapshot.generated_at)
    : Number.POSITIVE_INFINITY
  const shouldRefresh = input.forceRefresh === true || state.snapshot == null || snapshotAgeMs > state.pollIntervalMs

  if (!shouldRefresh) {
    return state.snapshot
  }

  if (state.refreshPromise) {
    return state.refreshPromise
  }

  state.refreshPromise = refreshArbitrageSnapshot(input.workspaceId, state.options)
    .then((snapshot) => {
      const previous = state.snapshot
      state.snapshot = snapshot
      publishArbitrageDiff(input.workspaceId, previous, snapshot)
      return snapshot
    })
    .finally(() => {
      state.refreshPromise = null
    })

  return state.refreshPromise
}

export function getCachedPredictionDashboardArbitrageSnapshot(
  workspaceId: number,
): PredictionDashboardArbitrageSnapshot | null {
  return getGlobalState().get(workspaceId)?.snapshot ?? null
}

export function resetPredictionDashboardArbitrageStateForTests() {
  const stateMap = getGlobalState()
  for (const state of stateMap.values()) {
    if (state.timer) clearInterval(state.timer)
  }
  stateMap.clear()
}
