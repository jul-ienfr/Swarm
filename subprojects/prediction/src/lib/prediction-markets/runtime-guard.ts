import {
  getVenueBudgetsContract,
  getVenueCapabilitiesContract,
  getVenueHealthSnapshotContract,
  type PredictionMarketVenueId,
} from '@/lib/prediction-markets/venue-ops'

export type PredictionMarketRuntimeGuardMode = 'discovery' | 'paper' | 'shadow' | 'live'
export type PredictionMarketRuntimeGuardVerdict = 'allowed' | 'degraded' | 'blocked'

type VenueCapabilitiesContract = ReturnType<typeof getVenueCapabilitiesContract>
type VenueHealthSnapshotContract = ReturnType<typeof getVenueHealthSnapshotContract>
type VenueBudgetsContract = ReturnType<typeof getVenueBudgetsContract>

export type PredictionMarketRuntimeGuardInput = {
  venue: PredictionMarketVenueId
  mode: PredictionMarketRuntimeGuardMode
  capabilities?: VenueCapabilitiesContract
  health?: VenueHealthSnapshotContract
  budgets?: VenueBudgetsContract
}

export type PredictionMarketRuntimeGuardResult = {
  venue: PredictionMarketVenueId
  mode: PredictionMarketRuntimeGuardMode
  verdict: PredictionMarketRuntimeGuardVerdict
  reasons: string[]
  constraints: string[]
  fallback_actions: string[]
  capabilities: VenueCapabilitiesContract
  health: VenueHealthSnapshotContract
  budgets: VenueBudgetsContract
}

type ModeBudgetThresholds = {
  snapshot_freshness_budget_ms: number
  decision_latency_budget_ms: number
}

const MODE_BUDGET_THRESHOLDS: Record<PredictionMarketRuntimeGuardMode, ModeBudgetThresholds> = {
  discovery: {
    snapshot_freshness_budget_ms: 30_000,
    decision_latency_budget_ms: 15_000,
  },
  paper: {
    snapshot_freshness_budget_ms: 15_000,
    decision_latency_budget_ms: 10_000,
  },
  shadow: {
    snapshot_freshness_budget_ms: 10_000,
    decision_latency_budget_ms: 5_000,
  },
  live: {
    snapshot_freshness_budget_ms: 5_000,
    decision_latency_budget_ms: 2_500,
  },
}

function pushUnique(target: string[], value: string) {
  if (!target.includes(value)) {
    target.push(value)
  }
}

function pushManyUnique(target: string[], values: string[]) {
  for (const value of values) {
    pushUnique(target, value)
  }
}

function baseFallbackActions(mode: PredictionMarketRuntimeGuardMode): string[] {
  switch (mode) {
    case 'discovery':
      return ['keep_read_only', 'reduce_polling_cadence']
    case 'paper':
      return ['downgrade_mode_to_shadow', 'keep_read_only']
    case 'shadow':
      return ['downgrade_mode_to_discovery', 'keep_read_only']
    case 'live':
      return ['downgrade_mode_to_shadow', 'disable_execution', 'keep_read_only']
  }
}

function addHealthSignals(
  input: PredictionMarketRuntimeGuardInput,
  health: VenueHealthSnapshotContract,
  verdict: { value: PredictionMarketRuntimeGuardVerdict },
  reasons: string[],
  constraints: string[],
  fallbackActions: string[],
) {
  pushUnique(constraints, `health.api_status=${health.api_status}`)
  pushUnique(constraints, `health.stream_status=${health.stream_status}`)
  pushUnique(constraints, `health.degraded_mode=${health.degraded_mode}`)

  if (health.incident_flags.length > 0) {
    pushUnique(reasons, `venue health has incident flags: ${health.incident_flags.join(', ')}`)
    pushUnique(fallbackActions, 'prefer_cached_snapshots')
    pushUnique(fallbackActions, 'reduce_polling_cadence')
    if (input.mode === 'live') {
      verdict.value = 'blocked'
      return
    }
    if (verdict.value === 'allowed') verdict.value = 'degraded'
  }

  if (health.api_status === 'blocked' || health.stream_status === 'blocked' || health.degraded_mode === 'blocked') {
    pushUnique(reasons, 'venue health is blocked')
    pushUnique(fallbackActions, 'quarantine_venue')
    pushUnique(fallbackActions, 'downgrade_mode_to_discovery')
    verdict.value = 'blocked'
    return
  }

  if (
    health.api_status === 'degraded' ||
    health.stream_status === 'degraded' ||
    health.degraded_mode === 'degraded' ||
    health.health_score < 0.75
  ) {
    pushUnique(reasons, 'venue health is degraded')
    pushUnique(fallbackActions, 'prefer_cached_snapshots')
    pushUnique(fallbackActions, 'reduce_polling_cadence')
    if (input.mode === 'live') {
      verdict.value = 'blocked'
      pushUnique(fallbackActions, 'downgrade_mode_to_shadow')
      return
    }
    if (verdict.value === 'allowed') verdict.value = 'degraded'
  }
}

function addCapabilitySignals(
  input: PredictionMarketRuntimeGuardInput,
  capabilities: VenueCapabilitiesContract,
  verdict: { value: PredictionMarketRuntimeGuardVerdict },
  reasons: string[],
  constraints: string[],
  fallbackActions: string[],
) {
  pushUnique(constraints, `supports_discovery=${capabilities.supports_discovery}`)
  pushUnique(constraints, `supports_paper_mode=${capabilities.supports_paper_mode}`)
  pushUnique(constraints, `supports_orderbook=${capabilities.supports_orderbook}`)
  pushUnique(constraints, `supports_trades=${capabilities.supports_trades}`)
  pushUnique(constraints, `supports_execution=${capabilities.supports_execution}`)
  pushUnique(constraints, `supports_websocket=${capabilities.supports_websocket}`)

  if (capabilities.automation_constraints.length > 0) {
    pushUnique(constraints, `automation_constraints=${capabilities.automation_constraints.join(' | ')}`)
  }

  if (!capabilities.supports_discovery) {
    pushUnique(reasons, 'venue does not support discovery')
    pushManyUnique(fallbackActions, ['downgrade_mode_to_discovery', 'keep_read_only'])
    verdict.value = 'blocked'
    return
  }

  if (input.mode === 'paper' && !capabilities.supports_paper_mode) {
    pushUnique(reasons, 'paper mode is not supported by the venue contract')
    pushManyUnique(fallbackActions, ['downgrade_mode_to_shadow', 'downgrade_mode_to_discovery', 'keep_read_only'])
    if (verdict.value === 'allowed') verdict.value = 'degraded'
  }

  if (input.mode === 'shadow' && !capabilities.supports_orderbook && !capabilities.supports_trades) {
    pushUnique(reasons, 'shadow mode has no orderbook or trade feeds to lean on')
    pushManyUnique(fallbackActions, ['downgrade_mode_to_discovery', 'keep_read_only'])
    if (verdict.value === 'allowed') verdict.value = 'degraded'
  }

  if (input.mode === 'live') {
    if (!capabilities.supports_execution) {
      pushUnique(reasons, 'live mode requires execution support')
      pushManyUnique(fallbackActions, ['downgrade_mode_to_shadow', 'disable_execution', 'keep_read_only'])
      verdict.value = 'blocked'
    }

    if (!capabilities.supports_positions) {
      pushUnique(reasons, 'live mode is missing position support')
      pushUnique(fallbackActions, 'prefer_paper_or_shadow')
      if (verdict.value === 'allowed') verdict.value = 'degraded'
    }
  }

  if (capabilities.automation_constraints.length > 0) {
    if (input.mode !== 'discovery') {
      pushUnique(reasons, `automation constraints apply: ${capabilities.automation_constraints.join(', ')}`)
    }
    if (input.mode === 'live') {
      pushManyUnique(fallbackActions, ['downgrade_mode_to_shadow', 'quarantine_venue', 'disable_execution'])
      verdict.value = 'blocked'
      return
    }

    if (input.mode !== 'discovery' && verdict.value === 'allowed') {
      verdict.value = 'degraded'
      pushUnique(fallbackActions, 'downgrade_mode_to_discovery')
    }
  }
}

function addBudgetSignals(
  input: PredictionMarketRuntimeGuardInput,
  budgets: VenueBudgetsContract,
  verdict: { value: PredictionMarketRuntimeGuardVerdict },
  reasons: string[],
  constraints: string[],
  fallbackActions: string[],
) {
  const thresholds = MODE_BUDGET_THRESHOLDS[input.mode]
  pushUnique(constraints, `snapshot_freshness_budget_ms<=${thresholds.snapshot_freshness_budget_ms}`)
  pushUnique(constraints, `decision_latency_budget_ms<=${thresholds.decision_latency_budget_ms}`)
  pushUnique(constraints, `stream_reconnect_budget_ms<=${budgets.stream_reconnect_budget_ms}`)
  pushUnique(constraints, `backpressure_policy=${budgets.backpressure_policy}`)

  const snapshotTooLoose = budgets.snapshot_freshness_budget_ms > thresholds.snapshot_freshness_budget_ms
  const decisionTooLoose = budgets.decision_latency_budget_ms > thresholds.decision_latency_budget_ms

  if (budgets.max_retries === 0) {
    pushUnique(constraints, 'max_retries=0')
    pushUnique(fallbackActions, 'avoid_retry_loops')
  }

  if (snapshotTooLoose || decisionTooLoose) {
    pushUnique(
      reasons,
      `budgets exceed the conservative envelope for ${input.mode} mode`,
    )
    pushManyUnique(fallbackActions, ['trim_history_window', 'lower_parallelism', 'prefer_cached_snapshots'])
    if (input.mode === 'live') {
      verdict.value = 'blocked'
      return
    }
    if (verdict.value === 'allowed') verdict.value = 'degraded'
  }
}

export function evaluatePredictionMarketRuntimeGuard(
  input: PredictionMarketRuntimeGuardInput,
): PredictionMarketRuntimeGuardResult {
  const capabilities = input.capabilities ?? getVenueCapabilitiesContract(input.venue)
  const health = input.health ?? getVenueHealthSnapshotContract(input.venue)
  const budgets = input.budgets ?? getVenueBudgetsContract(input.venue)

  const verdict = { value: 'allowed' as PredictionMarketRuntimeGuardVerdict }
  const reasons: string[] = []
  const constraints: string[] = [`mode=${input.mode}`, `venue=${input.venue}`]
  const fallbackActions: string[] = []

  pushManyUnique(fallbackActions, baseFallbackActions(input.mode))

  addCapabilitySignals(input, capabilities, verdict, reasons, constraints, fallbackActions)
  if (verdict.value === 'blocked') {
    return {
      venue: input.venue,
      mode: input.mode,
      verdict: verdict.value,
      reasons,
      constraints,
      fallback_actions: fallbackActions,
      capabilities,
      health,
      budgets,
    }
  }

  addHealthSignals(input, health, verdict, reasons, constraints, fallbackActions)
  addBudgetSignals(input, budgets, verdict, reasons, constraints, fallbackActions)

  return {
    venue: input.venue,
    mode: input.mode,
    verdict: verdict.value,
    reasons,
    constraints,
    fallback_actions: [...new Set(fallbackActions)],
    capabilities,
    health,
    budgets,
  }
}
