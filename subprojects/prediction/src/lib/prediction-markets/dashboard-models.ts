import {
  getVenueCapabilitiesContract,
  getVenueFeedSurfaceContract,
  getVenueHealthSnapshotContract,
  getVenueStrategyContract,
  getVenueBudgetsContract,
  listPredictionMarketVenues,
  type PredictionMarketVenueId,
} from '@/lib/prediction-markets/venue-ops'
import {
  getPredictionMarketRunDetails,
  listPredictionMarketRuns,
} from '@/lib/prediction-markets/service'
import {
  listRecentPredictionDashboardEvents,
  type PredictionDashboardEvent,
} from '@/lib/prediction-markets/dashboard-events'
import {
  getDashboardLiveIntent,
  listDashboardLiveIntents,
  type PredictionDashboardLiveIntent,
} from '@/lib/prediction-markets/dashboard-live-intents'
import {
  getPredictionDashboardArbitrageSnapshot as getPredictionDashboardArbitrageScannerSnapshot,
  type PredictionDashboardArbitrageCandidate as ScannerPredictionDashboardArbitrageCandidate,
  type PredictionDashboardArbitrageSnapshot as ScannerPredictionDashboardArbitrageSnapshot,
  type PredictionDashboardArbitrageSnapshotInput as ScannerPredictionDashboardArbitrageSnapshotInput,
} from '@/lib/prediction-markets/arbitrage-scanner'

export type DashboardFreshness = 'fresh' | 'warm' | 'stale'

export type PredictionDashboardRunListItem = {
  run_id: string
  venue: string
  market_id: string
  market_slug: string | null
  recommendation: string | null
  status: string
  created_at: number
  updated_at: number
  confidence: number | null
  probability_yes: number | null
  edge_bps: number | null
  benchmark_state: string
  benchmark_ready: boolean
  benchmark_gate_kind: string | null
  benchmark_evidence_level: string | null
  benchmark_blockers: string[]
  selected_path: string | null
  selected_path_status: string | null
  selected_path_effective_mode: string | null
  live_promotable: boolean
  research_origin: string | null
  execution_summary: string | null
  strategy: PredictionDashboardStrategySummary | null
  freshness: DashboardFreshness
  transport: 'polling'
}

export type PredictionDashboardStrategySummary = {
  primary_strategy: string | null
  strategy_counts: {
    total: number
    actionable: number
    ready: number
    degraded: number
    blocked: number
    inactive: number
  }
  market_regime: string | null
  strategy_shadow_summary: string | null
  resolution_anomalies: string[]
  execution_intent_preview_kind: string | null
  operator_summary: string | null
}

export type PredictionDashboardRunDetail = {
  generated_at: string
  freshness: DashboardFreshness
  transport: 'polling'
  provenance: {
    workspace_id: number
    run_id: string
    venue: string
    source: 'prediction-markets'
  }
  run: Awaited<ReturnType<typeof getPredictionMarketRunDetails>>
  benchmark: {
    ready: boolean
    status: string
    gate_kind: string | null
    evidence_level: string | null
    summary: string | null
    blockers: string[]
    live_block_reason: string | null
  }
  research: {
    origin: string | null
    pipeline_id: string | null
    pipeline_version: string | null
    compare_preferred_mode: string | null
    weighted_probability_yes: number | null
    weighted_coverage: number | null
    abstention_blocks: boolean | null
  }
  execution: {
    selected_path: string | null
    selected_path_status: string | null
    selected_path_effective_mode: string | null
    selected_preview_source: string | null
    selected_preview: unknown
    requested_path: string | null
    ready: boolean
    blockers: string[]
    capital_status: string | null
    reconciliation_status: string | null
    live_promotable: boolean
  }
  strategy: PredictionDashboardStrategySummary | null
  surfaces: {
    dispatch?: unknown
    paper?: unknown
    shadow?: unknown
    live?: unknown
  }
  live_intents: PredictionDashboardLiveIntent[]
  alerts: Array<{
    code: string
    severity: 'low' | 'medium' | 'high' | 'critical'
    title: string
    summary: string
  }>
}

export type PredictionDashboardVenueSnapshot = {
  generated_at: string
  freshness: DashboardFreshness
  transport: 'polling'
  venue: PredictionMarketVenueId
  provenance: {
    source: 'prediction-markets'
    venue: PredictionMarketVenueId
  }
  capabilities: ReturnType<typeof getVenueCapabilitiesContract>
  health: ReturnType<typeof getVenueHealthSnapshotContract>
  feed: ReturnType<typeof getVenueFeedSurfaceContract>
  budgets: ReturnType<typeof getVenueBudgetsContract>
  strategy: ReturnType<typeof getVenueStrategyContract>
}

export type PredictionDashboardBenchmarkSnapshot = {
  generated_at: string
  freshness: DashboardFreshness
  transport: 'polling'
  provenance: {
    workspace_id: number
    venue: string
    run_id: string | null
    source: 'prediction-markets'
  }
  benchmark: PredictionDashboardRunDetail['benchmark']
  comparison: {
    selected_path: string | null
    selected_path_status: string | null
    selected_path_effective_mode: string | null
    benchmark_gate_blocks_live: boolean
    benchmark_gate_live_block_reason: string | null
    benchmark_gate_summary: string | null
  }
  run: PredictionDashboardRunListItem | null
}

export type PredictionDashboardArbitrageCandidate = ScannerPredictionDashboardArbitrageCandidate

export type PredictionDashboardArbitrageSnapshot = ScannerPredictionDashboardArbitrageSnapshot

export type PredictionDashboardArbitrageSnapshotInput = Omit<ScannerPredictionDashboardArbitrageSnapshotInput, 'workspaceId'>

export type PredictionDashboardOverview = {
  generated_at: string
  freshness: DashboardFreshness
  transport: 'polling'
  workspace_id: number
  venue: PredictionMarketVenueId
  filters: {
    recommendation: string | null
    selected_path: string | null
    benchmark_state: string | null
    surface_status: string | null
    date_window: string | null
  }
  metrics: {
    runs: number
    bet: number
    wait: number
    no_trade: number
    benchmark_ready: number
    live_promotable: number
    live_blocked: number
    degraded_venues: number
  }
  alerts: PredictionDashboardRunDetail['alerts']
  strategy: PredictionDashboardStrategySummary | null
  runs: PredictionDashboardRunListItem[]
  benchmark: PredictionDashboardBenchmarkSnapshot | null
  venue_snapshot: PredictionDashboardVenueSnapshot
  recent_events: PredictionDashboardEvent[]
  live_intents: PredictionDashboardLiveIntent[]
}

function freshnessFromAgeSeconds(ageSeconds: number): DashboardFreshness {
  if (ageSeconds <= 30) return 'fresh'
  if (ageSeconds <= 300) return 'warm'
  return 'stale'
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : []
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value == null || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function getArtifactPayload(
  input: Record<string, unknown> | null | undefined,
  artifactType: string,
): Record<string, unknown> | null {
  const artifacts = asArray(input?.artifacts)

  for (const artifact of artifacts) {
    const artifactRecord = asRecord(artifact)
    if (artifactRecord?.artifact_type !== artifactType) continue

    return asRecord(artifactRecord.payload)
  }

  return null
}

function uniqueStringArray(values: Array<string | null | undefined>): string[] {
  return [...new Set(asStringArray(values).map((value) => value.trim()).filter(Boolean))]
}

function formatPercentValue(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'n/a'
  return `${(value * 100).toFixed(1)}%`
}

function formatBpsValue(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'n/a'
  return `${Math.round(value)} bps`
}

function formatUsdValue(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'n/a'
  return `${Math.round(value)} USD`
}

function normalizeStrategyCounts(input: Record<string, unknown> | null, pathways: unknown[]): PredictionDashboardStrategySummary['strategy_counts'] {
  const derived = asArray(pathways)
  const derivedObjects = derived.map(asRecord).filter((pathway): pathway is Record<string, unknown> => pathway != null)
  const derivedStrings = derived.filter((pathway): pathway is string => typeof pathway === 'string' && pathway.trim().length > 0)
  const counts = derivedObjects.length > 0
    ? {
      total: derivedObjects.length,
      actionable: derivedObjects.filter((pathway) => pathway.actionable === true).length,
      ready: derivedObjects.filter((pathway) => asString(pathway.status) === 'ready').length,
      degraded: derivedObjects.filter((pathway) => asString(pathway.status) === 'degraded').length,
      blocked: derivedObjects.filter((pathway) => asString(pathway.status) === 'blocked').length,
      inactive: derivedObjects.filter((pathway) => asString(pathway.status) === 'inactive').length,
    }
    : {
      total: derivedStrings.length,
      actionable: derivedStrings.length,
      ready: 0,
      degraded: 0,
      blocked: 0,
      inactive: 0,
    }

  return {
    total: asNumber(input?.total) ?? counts.total,
    actionable: asNumber(input?.actionable) ?? counts.actionable,
    ready: asNumber(input?.ready) ?? counts.ready,
    degraded: asNumber(input?.degraded) ?? counts.degraded,
    blocked: asNumber(input?.blocked) ?? counts.blocked,
    inactive: asNumber(input?.inactive) ?? counts.inactive,
  }
}

function buildShadowSummary(
  shadowArbitrage: Record<string, unknown> | null,
): string | null {
  const summary = asRecord(shadowArbitrage?.summary)
  if (!summary) return null

  return uniqueStringArray([
    `Shadow strategy keeps ${formatBpsValue(asNumber(summary.shadow_edge_bps))} on ${formatUsdValue(asNumber(summary.recommended_size_usd))} size.`,
    `Hedge success is ${formatPercentValue(asNumber(summary.hedge_success_probability))}.`,
    summary.worst_case_kind ? `Worst case is ${summary.worst_case_kind}.` : null,
  ]).join(' ')
}

function buildStrategySummary(input: Record<string, unknown> | null | undefined): PredictionDashboardStrategySummary | null {
  if (!input) return null

  const strategy = asRecord(input.strategy)
  const executionPathways = strategy?.execution_pathways
    ? asRecord(strategy.execution_pathways)
    : asRecord(input.execution_pathways) ?? getArtifactPayload(input, 'execution_pathways')
  const executionProjection = strategy?.execution_projection
    ? asRecord(strategy.execution_projection)
    : asRecord(input.execution_projection) ?? getArtifactPayload(input, 'execution_projection')
  const shadowArbitrage = strategy?.shadow_arbitrage
    ? asRecord(strategy.shadow_arbitrage)
    : asRecord(input.shadow_arbitrage) ?? getArtifactPayload(input, 'shadow_arbitrage')
  const microstructureLab = strategy?.microstructure_lab
    ? asRecord(strategy.microstructure_lab)
    : asRecord(input.microstructure_lab) ?? getArtifactPayload(input, 'microstructure_lab')
  const multiVenueExecution = strategy?.multi_venue_execution
    ? asRecord(strategy.multi_venue_execution)
    : asRecord(input.multi_venue_execution) ?? getArtifactPayload(input, 'multi_venue_execution')
  const tradeIntentGuard = strategy?.trade_intent_guard
    ? asRecord(strategy.trade_intent_guard)
    : asRecord(input.trade_intent_guard) ?? getArtifactPayload(input, 'trade_intent_guard')
  const resolutionPolicy = strategy?.resolution_policy
    ? asRecord(strategy.resolution_policy)
    : asRecord(input.resolution_policy) ?? getArtifactPayload(input, 'resolution_policy')
  const hiddenPrimaryStrategy =
    asString(strategy?.primary_strategy) ??
    asString(strategy?.strategy_primary) ??
    asString(input.primary_strategy) ??
    asString(input.strategy_primary) ??
    asString(input.execution_pathways_highest_actionable_mode) ??
    asString(input.execution_projection_selected_path) ??
    asString(input.execution_projection_selected_path_effective_mode) ??
    asString(input.execution_readiness_highest_safe_mode) ??
    null
  const hiddenMarketRegime =
    asString(strategy?.market_regime) ??
    asString(strategy?.strategy_market_regime) ??
    asString(input.market_regime) ??
    asString(input.strategy_market_regime) ??
    asString(multiVenueExecution?.taxonomy) ??
    asString(microstructureLab && asRecord(microstructureLab.summary)?.recommended_mode) ??
    asString(input.execution_pathways_highest_actionable_mode) ??
    asString(input.execution_projection_selected_path_effective_mode) ??
    null
  const strategyCountsRecord = asRecord(strategy?.strategy_counts) ?? asRecord(strategy?.counts) ?? asRecord(input.strategy_counts) ?? asRecord(input.counts)
  const strategyCounts = normalizeStrategyCounts(
    strategyCountsRecord,
    asArray(executionPathways?.pathways ?? input.execution_pathways_actionable_modes ?? []),
  )
  const explicitResolutionAnomalies = uniqueStringArray([
    ...(asStringArray(strategy?.resolution_anomalies) ?? []),
    ...(asStringArray(input.resolution_anomalies) ?? []),
  ])
  const resolutionAnomalies = uniqueStringArray([
    ...explicitResolutionAnomalies,
    ...(asStringArray(resolutionPolicy?.reasons) ?? []),
    resolutionPolicy?.manual_review_required === true ? 'manual_review_required' : null,
    asString(resolutionPolicy?.status) && asString(resolutionPolicy?.status) !== 'eligible'
      ? `resolution_status:${asString(resolutionPolicy?.status)}`
      : null,
  ])
  const previewKind =
    asString(strategy?.execution_intent_preview_kind) ??
    asString(strategy?.preview_kind) ??
    asString(input.execution_intent_preview_kind) ??
    asString(input.preview_kind) ??
    asString(input.execution_projection_selected_preview_source) ??
    asString(input.selected_preview_source) ??
    null
  const strategyShadowSummary =
    asString(strategy?.strategy_shadow_summary) ??
    asString(strategy?.shadow_summary) ??
    asString(input.strategy_shadow_summary) ??
    asString(input.shadow_summary) ??
    buildShadowSummary(shadowArbitrage)

  const hasStrategyArtifacts =
    hiddenPrimaryStrategy != null ||
    hiddenMarketRegime != null ||
    previewKind != null ||
    strategyShadowSummary != null ||
    explicitResolutionAnomalies.length > 0 ||
    strategyCountsRecord != null ||
    executionPathways != null ||
    executionProjection != null ||
    shadowArbitrage != null ||
    microstructureLab != null ||
    multiVenueExecution != null ||
    tradeIntentGuard != null

  if (!hasStrategyArtifacts) return null

  const operatorSummary = uniqueStringArray([
    hiddenPrimaryStrategy ? `Primary strategy: ${hiddenPrimaryStrategy}.` : null,
    hiddenMarketRegime ? `Market regime: ${hiddenMarketRegime}.` : null,
    `Strategy counts: ready=${strategyCounts.ready}, degraded=${strategyCounts.degraded}, blocked=${strategyCounts.blocked}, inactive=${strategyCounts.inactive}.`,
    previewKind ? `Execution intent preview kind: ${previewKind}.` : null,
    strategyShadowSummary ? `Shadow summary: ${strategyShadowSummary}` : null,
    resolutionAnomalies.length > 0
      ? `Resolution anomalies: ${resolutionAnomalies.slice(0, 3).join('; ')}.`
      : null,
  ]).join(' ')

  return {
    primary_strategy: hiddenPrimaryStrategy,
    strategy_counts: strategyCounts,
    market_regime: hiddenMarketRegime,
    strategy_shadow_summary: strategyShadowSummary,
    resolution_anomalies: resolutionAnomalies,
    execution_intent_preview_kind: previewKind,
    operator_summary: operatorSummary || null,
  }
}

function summarizeBenchmark(detail: NonNullable<Awaited<ReturnType<typeof getPredictionMarketRunDetails>>>) {
  return {
    ready: detail.benchmark_promotion_ready === true,
    status: detail.benchmark_promotion_status ?? detail.research_benchmark_promotion_status ?? 'unknown',
    gate_kind: detail.benchmark_promotion_gate_kind ?? detail.research_promotion_gate_kind ?? null,
    evidence_level: detail.benchmark_evidence_level ?? detail.research_benchmark_evidence_level ?? null,
    summary:
      detail.benchmark_promotion_blocker_summary ??
      detail.benchmark_promotion_summary ??
      detail.research_benchmark_promotion_blocker_summary ??
      detail.research_benchmark_promotion_summary ??
      null,
    blockers: [
      ...(detail.benchmark_gate_blockers ?? []),
      ...(detail.benchmark_gate_reasons ?? []),
      ...(detail.research_benchmark_gate_blockers ?? []),
      ...(detail.research_benchmark_gate_reasons ?? []),
    ],
    live_block_reason: detail.benchmark_gate_live_block_reason ?? detail.research_benchmark_live_block_reason ?? null,
  }
}

function summarizeExecution(detail: NonNullable<Awaited<ReturnType<typeof getPredictionMarketRunDetails>>>) {
  const executionProjection = detail.execution_projection as Record<string, unknown> | null
  const selectedPath = detail.execution_projection_selected_path ?? asString(executionProjection?.selected_path) ?? null
  const selectedPathStatus = detail.execution_projection_selected_path_status ?? asString(executionProjection?.selected_path_status) ?? null
  const selectedPathEffectiveMode =
    detail.execution_projection_selected_path_effective_mode ??
    detail.execution_projection_recommended_effective_mode ??
    asString(executionProjection?.recommended_effective_mode) ??
    null
  const blockers = [
    ...asStringArray(executionProjection?.blocking_reasons),
    ...(detail.trade_intent_guard?.blocked_reasons ?? []),
  ]

  return {
    selected_path: selectedPath,
    selected_path_status: selectedPathStatus,
    selected_path_effective_mode: selectedPathEffectiveMode,
    selected_preview_source: detail.execution_projection_selected_preview_source ?? null,
    selected_preview: detail.execution_projection_selected_preview ?? null,
    requested_path: detail.execution_projection_requested_path ?? asString(executionProjection?.requested_path) ?? null,
    ready: selectedPath === 'live' && detail.benchmark_promotion_ready === true && detail.benchmark_gate_blocks_live !== true,
    blockers,
    capital_status: detail.execution_projection_capital_status ?? null,
    reconciliation_status: detail.execution_projection_reconciliation_status ?? null,
    live_promotable: selectedPath === 'live' && detail.benchmark_promotion_ready === true && detail.benchmark_gate_blocks_live !== true,
  }
}

function mapRunListItem(run: ReturnType<typeof listPredictionMarketRuns>[number]): PredictionDashboardRunListItem {
  const runRecord = run as Record<string, unknown>
  const executionProjection = (
    runRecord.execution_projection && typeof runRecord.execution_projection === 'object'
      ? runRecord.execution_projection
      : null
  ) as Record<string, unknown> | null
  const selectedPath = run.execution_projection_selected_path ?? asString(executionProjection?.selected_path)
  const selectedPathStatus = run.execution_projection_selected_path_status ?? asString(executionProjection?.selected_path_status) ?? null
  const selectedPathEffectiveMode =
    run.execution_projection_selected_path_effective_mode ??
    run.execution_projection_recommended_effective_mode ??
    asString(executionProjection?.recommended_effective_mode) ??
    null

  return {
    run_id: run.run_id,
    venue: run.venue,
    market_id: run.market_id,
    market_slug: run.market_slug ?? null,
    recommendation: run.recommendation ?? null,
    status: run.status,
    created_at: run.created_at,
    updated_at: run.updated_at,
    confidence: run.confidence ?? null,
    probability_yes: run.probability_yes ?? null,
    edge_bps: run.edge_bps ?? null,
    benchmark_state:
      (typeof runRecord.benchmark_state === 'string' ? runRecord.benchmark_state : null) ??
      run.benchmark_promotion_status ??
      run.research_benchmark_promotion_status ??
      'unknown',
    benchmark_ready: run.benchmark_promotion_ready === true,
    benchmark_gate_kind: run.benchmark_promotion_gate_kind ?? run.research_promotion_gate_kind ?? null,
    benchmark_evidence_level: run.benchmark_evidence_level ?? run.research_benchmark_evidence_level ?? null,
    benchmark_blockers: [
      ...(run.benchmark_gate_blockers ?? []),
      ...(run.benchmark_gate_reasons ?? []),
      ...(run.research_benchmark_gate_blockers ?? []),
      ...(run.research_benchmark_gate_reasons ?? []),
    ],
    selected_path: selectedPath,
    selected_path_status: selectedPathStatus,
    selected_path_effective_mode: selectedPathEffectiveMode,
    live_promotable:
      selectedPath === 'live' &&
      run.benchmark_promotion_ready === true &&
      run.benchmark_gate_blocks_live !== true,
    research_origin: run.research_runtime_mode ?? run.research_recommendation_origin ?? null,
    execution_summary:
      run.execution_projection_summary
      ?? asString((run.execution_projection_preflight_summary as Record<string, unknown> | undefined)?.summary)
      ?? null,
    strategy: buildStrategySummary(runRecord),
    freshness: freshnessFromAgeSeconds(Math.max(0, Math.floor(Date.now() / 1000) - run.updated_at)),
    transport: 'polling',
  }
}

function buildAlerts(detail: PredictionDashboardRunDetail | null, venue: PredictionDashboardVenueSnapshot): PredictionDashboardRunDetail['alerts'] {
  const alerts: PredictionDashboardRunDetail['alerts'] = []
  if (detail?.benchmark.ready === false || detail?.benchmark.live_block_reason) {
    alerts.push({
      code: 'live_blocked_by_benchmark',
      severity: 'high',
      title: 'Live blocked by benchmark',
      summary: detail?.benchmark.summary ?? 'Benchmark promotion remains unproven.',
    })
  }

  if (venue.health.api_status !== 'healthy') {
    alerts.push({
      code: 'venue_degraded',
      severity: 'medium',
      title: 'Venue degraded',
      summary: venue.health.notes ?? 'Venue health is not fully healthy.',
    })
  }

  if (venue.feed.market_feed_status !== 'healthy' && venue.feed.market_feed_status !== 'local_cache') {
    alerts.push({
      code: 'feed_stale',
      severity: 'medium',
      title: 'Feed stale',
      summary: venue.feed.summary ?? 'Market feed transport is not fully healthy.',
    })
  }

  if (detail && detail.execution.blockers.length > 0) {
    alerts.push({
      code: 'execution_blockers',
      severity: 'high',
      title: 'Execution blockers',
      summary: detail.execution.blockers.slice(0, 3).join('; '),
    })
  }

  return alerts
}

export function buildPredictionDashboardRunDetail(
  workspaceId: number,
  runId: string,
): PredictionDashboardRunDetail | null {
  const detail = getPredictionMarketRunDetails(runId, workspaceId)
  if (!detail) return null

  const benchmark = summarizeBenchmark(detail)
  const execution = summarizeExecution(detail)
  const strategy = buildStrategySummary(detail)
  const liveIntents = listDashboardLiveIntents(runId, workspaceId)
  const generatedAt = new Date().toISOString()

  const venueSnapshot = buildPredictionDashboardVenueSnapshot(detail.venue)
  const runDetail: PredictionDashboardRunDetail = {
    generated_at: generatedAt,
    freshness: freshnessFromAgeSeconds(0),
    transport: 'polling',
    provenance: {
      workspace_id: workspaceId,
      run_id: runId,
      venue: detail.venue,
      source: 'prediction-markets',
    },
    run: detail,
    benchmark,
    research: {
      origin: detail.research_recommendation_origin ?? detail.research_runtime_mode ?? null,
      pipeline_id: detail.research_pipeline_id ?? null,
      pipeline_version: detail.research_pipeline_version ?? null,
      compare_preferred_mode: detail.research_compare_preferred_mode ?? null,
      weighted_probability_yes: detail.research_weighted_probability_yes ?? null,
      weighted_coverage: detail.research_weighted_coverage ?? null,
      abstention_blocks: detail.research_abstention_policy_blocks_forecast ?? null,
    },
    execution,
    strategy,
    surfaces: {
      dispatch: detail.trade_intent_guard ?? null,
      paper: detail.paper_surface ?? null,
      shadow: detail.shadow_arbitrage ?? null,
      live: detail.execution_projection ?? null,
    },
    live_intents: liveIntents,
    alerts: buildAlerts(null as unknown as PredictionDashboardRunDetail, venueSnapshot),
  }

  runDetail.alerts = buildAlerts(runDetail, venueSnapshot)
  return runDetail
}

export function buildPredictionDashboardRunList(
  workspaceId: number,
  venue: PredictionMarketVenueId,
  limit = 20,
): {
  generated_at: string
  freshness: DashboardFreshness
  transport: 'polling'
  workspace_id: number
  venue: PredictionMarketVenueId
  total: number
  items: PredictionDashboardRunListItem[]
} {
  const runs = listPredictionMarketRuns({
    workspaceId,
    venue,
    limit,
  })

  return {
    generated_at: new Date().toISOString(),
    freshness: runs.length > 0 ? 'fresh' : 'warm',
    transport: 'polling',
    workspace_id: workspaceId,
    venue,
    total: runs.length,
    items: runs.map(mapRunListItem),
  }
}

export function buildPredictionDashboardVenueSnapshot(
  venue: PredictionMarketVenueId,
): PredictionDashboardVenueSnapshot {
  return {
    generated_at: new Date().toISOString(),
    freshness: 'fresh',
    transport: 'polling',
    venue,
    provenance: {
      source: 'prediction-markets',
      venue,
    },
    capabilities: getVenueCapabilitiesContract(venue),
    health: getVenueHealthSnapshotContract(venue),
    feed: getVenueFeedSurfaceContract(venue),
    budgets: getVenueBudgetsContract(venue),
    strategy: getVenueStrategyContract(venue),
  }
}

export function buildPredictionDashboardBenchmarkSnapshot(
  workspaceId: number,
  venue: PredictionMarketVenueId,
  runId?: string,
): PredictionDashboardBenchmarkSnapshot {
  const baseRuns = listPredictionMarketRuns({
    workspaceId,
    venue,
    limit: 25,
  })
  const selectedRunId = runId ?? baseRuns[0]?.run_id ?? null
  const runDetail = selectedRunId ? getPredictionMarketRunDetails(selectedRunId, workspaceId) : null
  const run = baseRuns.find((item) => item.run_id === selectedRunId) ?? null
  const benchmark = runDetail ? summarizeBenchmark(runDetail) : {
    ready: false,
    status: 'unknown',
    gate_kind: null,
    evidence_level: null,
    summary: null,
    blockers: [],
    live_block_reason: null,
  }

  return {
    generated_at: new Date().toISOString(),
    freshness: runDetail ? 'fresh' : 'warm',
    transport: 'polling',
    provenance: {
      workspace_id: workspaceId,
      venue,
      run_id: selectedRunId,
      source: 'prediction-markets',
    },
    benchmark,
    comparison: {
      selected_path: runDetail?.execution_projection_selected_path ?? null,
      selected_path_status: runDetail?.execution_projection_selected_path_status ?? null,
      selected_path_effective_mode:
        runDetail?.execution_projection_selected_path_effective_mode ??
        runDetail?.execution_projection_recommended_effective_mode ??
        null,
      benchmark_gate_blocks_live: runDetail?.benchmark_gate_blocks_live === true,
      benchmark_gate_live_block_reason: runDetail?.benchmark_gate_live_block_reason ?? null,
      benchmark_gate_summary: runDetail?.benchmark_gate_summary ?? null,
    },
    run: run ? mapRunListItem(run) : null,
  }
}

export function buildPredictionDashboardArbitrageSnapshot(
  workspaceId: number,
  venueOrPair:
    | PredictionMarketVenueId
    | [PredictionMarketVenueId, PredictionMarketVenueId]
    | PredictionDashboardArbitrageSnapshotInput = ['polymarket', 'kalshi'],
  runIdOrLimit?: string | number,
): Promise<PredictionDashboardArbitrageSnapshot> {
  if (typeof venueOrPair === 'object' && !Array.isArray(venueOrPair)) {
    return getPredictionDashboardArbitrageScannerSnapshot({
      workspaceId,
      ...venueOrPair,
    })
  }

  const limitPerVenue = typeof runIdOrLimit === 'number' ? runIdOrLimit : 16
  return getPredictionDashboardArbitrageScannerSnapshot({
    workspaceId,
    limitPerVenue,
    maxPairs: 40,
    minArbitrageSpreadBps: 25,
    shadowCandidateLimit: 8,
    forceRefresh: true,
  })
}

export async function getPredictionDashboardArbitrageCandidateSnapshot(
  workspaceId: number,
  candidateId: string,
  venueOrPair: PredictionMarketVenueId | [PredictionMarketVenueId, PredictionMarketVenueId] = ['polymarket', 'kalshi'],
  runIdOrLimit?: string | number,
): Promise<PredictionDashboardArbitrageCandidate | null> {
  const snapshot = await buildPredictionDashboardArbitrageSnapshot(workspaceId, venueOrPair, runIdOrLimit)
  return snapshot.candidates.find((candidate) => candidate.candidate_id === candidateId) ?? null
}

export function buildPredictionDashboardOverview(
  workspaceId: number,
  venue: PredictionMarketVenueId,
  limit = 20,
): PredictionDashboardOverview {
  const runs = buildPredictionDashboardRunList(workspaceId, venue, limit)
  const venueSnapshot = buildPredictionDashboardVenueSnapshot(venue)
  const benchmarkSnapshot = buildPredictionDashboardBenchmarkSnapshot(workspaceId, venue, runs.items[0]?.run_id)
  const detail = runs.items[0]?.run_id ? buildPredictionDashboardRunDetail(workspaceId, runs.items[0].run_id) : null
  const strategy = detail?.strategy ?? runs.items[0]?.strategy ?? null
  const liveIntents = listDashboardLiveIntents(undefined, workspaceId)
  const recentEvents = listRecentPredictionDashboardEvents(25)
  const metrics = {
    runs: runs.total,
    bet: runs.items.filter((item) => item.recommendation === 'bet').length,
    wait: runs.items.filter((item) => item.recommendation === 'wait').length,
    no_trade: runs.items.filter((item) => item.recommendation === 'no_trade').length,
    benchmark_ready: runs.items.filter((item) => item.benchmark_ready).length,
    live_promotable: runs.items.filter((item) => item.live_promotable).length,
    live_blocked: runs.items.filter((item) => item.selected_path === 'live' && !item.live_promotable).length,
    degraded_venues: venueSnapshot.health.api_status !== 'healthy' ? 1 : 0,
  }

  return {
    generated_at: new Date().toISOString(),
    freshness: detail ? 'fresh' : 'warm',
    transport: 'polling',
    workspace_id: workspaceId,
    venue,
    filters: {
      recommendation: null,
      selected_path: null,
      benchmark_state: null,
      surface_status: null,
      date_window: null,
    },
    metrics,
    alerts: detail?.alerts ?? buildAlerts(detail, venueSnapshot),
    strategy,
    runs: runs.items,
    benchmark: benchmarkSnapshot,
    venue_snapshot: venueSnapshot,
    recent_events: recentEvents,
    live_intents: liveIntents,
  }
}

export function buildDashboardSummaryForRuns(
  workspaceId: number,
  venue: PredictionMarketVenueId,
  limit = 20,
) {
  return buildPredictionDashboardRunList(workspaceId, venue, limit)
}

export function getDashboardLiveIntentSnapshot(intentId: string, workspaceId = 1) {
  return getDashboardLiveIntent(intentId, workspaceId)
}

export function listDashboardVenues() {
  return listPredictionMarketVenues()
}
