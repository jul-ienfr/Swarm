import {
  evaluatePredictionMarketComplianceMatrix,
  type PredictionMarketComplianceDecision,
  type PredictionMarketComplianceMatrix,
} from '@/lib/prediction-markets/compliance'
import {
  normalizeCapitalLedgerSnapshot,
  type CapitalLedgerSourceInput,
  type NormalizedCapitalLedgerResult,
} from '@/lib/prediction-markets/capital-ledger'
import {
  reconcileCapitalLedger,
  type CapitalLedgerReconciliationReport,
} from '@/lib/prediction-markets/reconciliation'
import {
  evaluatePredictionMarketRuntimeGuard,
  type PredictionMarketRuntimeGuardResult,
} from '@/lib/prediction-markets/runtime-guard'
import {
  capitalLedgerSnapshotSchema,
  predictionMarketBudgetsSchema,
  type CapitalLedgerSnapshot,
  type PredictionMarketBudgets,
  type PredictionMarketVenue,
  type PredictionMarketVenueType,
  type VenueCapabilities,
  type VenueHealthSnapshot,
} from '@/lib/prediction-markets/schemas'

export type PredictionMarketExecutionReadinessMode = 'discovery' | 'paper' | 'shadow' | 'live'
export type PredictionMarketExecutionReadinessVerdict = 'ready' | 'degraded' | 'blocked'

export type PredictionMarketExecutionReadinessCapitalLedger =
  | CapitalLedgerSnapshot
  | NormalizedCapitalLedgerResult

export type PredictionMarketExecutionReadinessModeReport = {
  mode: PredictionMarketExecutionReadinessMode
  compliance_status: PredictionMarketComplianceDecision['status']
  runtime_verdict: PredictionMarketRuntimeGuardResult['verdict']
  verdict: PredictionMarketExecutionReadinessVerdict
  effective_mode: PredictionMarketExecutionReadinessMode
  blockers: string[]
  warnings: string[]
  summary: string
}

export type PredictionMarketExecutionReadinessReport = {
  venue: PredictionMarketVenue
  venue_type: PredictionMarketVenueType
  capabilities: VenueCapabilities
  health: VenueHealthSnapshot
  budgets: PredictionMarketBudgets
  compliance_matrix: PredictionMarketComplianceMatrix
  capital_ledger: ExecutionReadinessCapitalSummary | null
  reconciliation: ExecutionReadinessReconciliationSummary | null
  mode_readiness: PredictionMarketExecutionReadinessModeReport[]
  highest_safe_mode: PredictionMarketExecutionReadinessMode | null
  overall_verdict: PredictionMarketExecutionReadinessVerdict
  blockers: string[]
  warnings: string[]
  summary: string
}

export type ExecutionReadinessCapitalSummary = {
  source: 'normalized' | 'snapshot'
  collateral_currency: string
  cash_available_usd: number
  cash_locked_usd: number
  open_exposure_usd: number
  utilization_ratio: number
  open_positions: number
  transfer_latency_estimate_ms: number
}

export type ExecutionReadinessReconciliationSummary = Pick<
  CapitalLedgerReconciliationReport,
  'severity' | 'within_tolerance' | 'summary' | 'tolerance' | 'drift'
>

export type PredictionMarketExecutionReadinessInput = {
  capabilities: VenueCapabilities
  health: VenueHealthSnapshot
  budgets: PredictionMarketBudgets
  compliance_matrix: PredictionMarketComplianceMatrix
  capital_ledger?: PredictionMarketExecutionReadinessCapitalLedger
  reconciliation?: CapitalLedgerReconciliationReport
}

const MODE_ORDER: PredictionMarketExecutionReadinessMode[] = [
  'discovery',
  'paper',
  'shadow',
  'live',
]

function unique(values: readonly string[]): string[] {
  return [...new Set(values.filter((value) => value.trim().length > 0))]
}

function joinOrNone(values: readonly string[]): string {
  return values.length > 0 ? values.join('; ') : 'none'
}

function formatModeLabel(mode: PredictionMarketExecutionReadinessMode): string {
  return `${mode[0].toUpperCase()}${mode.slice(1)}`
}

function isNormalizedCapitalLedgerResult(
  value: PredictionMarketExecutionReadinessCapitalLedger,
): value is NormalizedCapitalLedgerResult {
  return 'snapshot' in value && 'totals' in value && 'positions' in value
}

function summarizeCapitalLedger(
  input: PredictionMarketExecutionReadinessCapitalLedger,
): ExecutionReadinessCapitalSummary {
  if (isNormalizedCapitalLedgerResult(input)) {
    return {
      source: 'normalized',
      collateral_currency: input.snapshot.collateral_currency,
      cash_available_usd: input.snapshot.cash_available,
      cash_locked_usd: input.snapshot.cash_locked,
      open_exposure_usd: input.snapshot.open_exposure_usd,
      utilization_ratio: input.totals.utilization_ratio,
      open_positions: input.totals.open_positions,
      transfer_latency_estimate_ms: input.snapshot.transfer_latency_estimate_ms,
    }
  }

  const snapshot = capitalLedgerSnapshotSchema.parse(input)
  const normalized = normalizeCapitalLedgerSnapshot(snapshot as CapitalLedgerSourceInput)

  return {
    source: 'snapshot',
    collateral_currency: snapshot.collateral_currency,
    cash_available_usd: snapshot.cash_available,
    cash_locked_usd: snapshot.cash_locked,
    open_exposure_usd: snapshot.open_exposure_usd,
    utilization_ratio: normalized.totals.utilization_ratio,
    open_positions: normalized.totals.open_positions,
    transfer_latency_estimate_ms: snapshot.transfer_latency_estimate_ms,
  }
}

function pushUnique(target: string[], value: string) {
  if (!target.includes(value)) {
    target.push(value)
  }
}

function collectComplianceSignals(
  decision: PredictionMarketComplianceDecision,
  blockers: string[],
  warnings: string[],
) {
  if (decision.status === 'blocked') {
    pushUnique(blockers, `compliance:${decision.summary}`)
    for (const reason of decision.reasons) {
      pushUnique(blockers, `compliance:${reason.code} -> ${reason.message}`)
    }
    return
  }

  if (decision.status === 'degraded') {
    pushUnique(warnings, `compliance:${decision.summary}`)
    for (const reason of decision.reasons) {
      pushUnique(warnings, `compliance:${reason.code} -> ${reason.message}`)
    }
  }
}

function collectRuntimeSignals(
  runtime: PredictionMarketRuntimeGuardResult,
  blockers: string[],
  warnings: string[],
) {
  if (runtime.verdict === 'blocked') {
    pushUnique(blockers, `runtime:${runtime.mode} mode blocked`)
    for (const reason of runtime.reasons) {
      pushUnique(blockers, `runtime:${reason}`)
    }
    return
  }

  if (runtime.verdict === 'degraded') {
    pushUnique(warnings, `runtime:${runtime.mode} mode degraded`)
    for (const reason of runtime.reasons) {
      pushUnique(warnings, `runtime:${reason}`)
    }
  }
}

function collectCapitalSignals(
  mode: PredictionMarketExecutionReadinessMode,
  capital: ExecutionReadinessCapitalSummary | null,
  blockers: string[],
  warnings: string[],
) {
  if (!capital) return

  if (capital.collateral_currency.toUpperCase() !== 'USD' && capital.collateral_currency.toUpperCase() !== 'USDC') {
    pushUnique(warnings, `capital:collateral_currency:${capital.collateral_currency}`)
  }

  if (mode === 'live') {
    if (capital.utilization_ratio >= 0.95 || capital.open_exposure_usd > capital.cash_available_usd + capital.cash_locked_usd) {
      pushUnique(blockers, 'capital:live_mode_capacity_exhausted')
    } else if (capital.utilization_ratio >= 0.8) {
      pushUnique(warnings, 'capital:live_mode_high_utilization')
    }
    return
  }

  if (mode === 'shadow') {
    if (capital.utilization_ratio >= 1) {
      pushUnique(blockers, 'capital:shadow_mode_capacity_exhausted')
    } else if (capital.utilization_ratio >= 0.85) {
      pushUnique(warnings, 'capital:shadow_mode_high_utilization')
    }
    return
  }

  if (mode === 'paper' && capital.utilization_ratio >= 0.98) {
    pushUnique(warnings, 'capital:paper_mode_tight_capacity')
  }
}

function collectReconciliationSignals(
  mode: PredictionMarketExecutionReadinessMode,
  reconciliation: CapitalLedgerReconciliationReport | null,
  blockers: string[],
  warnings: string[],
) {
  if (!reconciliation) return

  if (reconciliation.within_tolerance) {
    return
  }

  pushUnique(warnings, `reconciliation:${reconciliation.summary}`)

  const prefix = `reconciliation:${reconciliation.severity}`
  if (mode === 'live') {
    pushUnique(blockers, 'reconciliation:open_drift:live_mode_blocked')
    pushUnique(blockers, `${prefix}:live_mode_blocked`)
    return
  }

  if (mode === 'shadow') {
    if (reconciliation.severity === 'critical') {
      pushUnique(blockers, `${prefix}:shadow_mode_blocked`)
    } else {
      pushUnique(warnings, `${prefix}:shadow_mode_degraded`)
    }
    return
  }

  if (mode === 'paper' && reconciliation.severity !== 'none') {
    pushUnique(warnings, `${prefix}:paper_mode_caution`)
  }
}

function buildModeSummary(input: {
  mode: PredictionMarketExecutionReadinessMode
  compliance: PredictionMarketComplianceDecision
  runtime: PredictionMarketRuntimeGuardResult
  capital: ExecutionReadinessCapitalSummary | null
  reconciliation: CapitalLedgerReconciliationReport | null
}): PredictionMarketExecutionReadinessModeReport {
  const blockers: string[] = []
  const warnings: string[] = []

  collectComplianceSignals(input.compliance, blockers, warnings)
  collectRuntimeSignals(input.runtime, blockers, warnings)
  collectCapitalSignals(input.mode, input.capital, blockers, warnings)
  collectReconciliationSignals(input.mode, input.reconciliation, blockers, warnings)

  const verdict: PredictionMarketExecutionReadinessVerdict = blockers.length > 0
    ? 'blocked'
    : warnings.length > 0
      ? 'degraded'
      : 'ready'

  const effectiveMode = input.compliance.effective_mode
  const effectiveLabel = effectiveMode === input.mode ? '' : ` -> ${effectiveMode}`
  const detail = blockers[0] ?? warnings[0] ?? input.compliance.summary
  const summary = `${formatModeLabel(input.mode)} mode ${verdict}${effectiveLabel}: ${detail}`

  return {
    mode: input.mode,
    compliance_status: input.compliance.status,
    runtime_verdict: input.runtime.verdict,
    verdict,
    effective_mode: effectiveMode,
    blockers: unique(blockers),
    warnings: unique(warnings),
    summary,
  }
}

export function buildPredictionMarketExecutionReadiness(
  input: PredictionMarketExecutionReadinessInput,
): PredictionMarketExecutionReadinessReport {
  const capitalLedger = input.capital_ledger ? summarizeCapitalLedger(input.capital_ledger) : null
  const reconciliation = input.reconciliation
    ? {
      severity: input.reconciliation.severity,
      within_tolerance: input.reconciliation.within_tolerance,
      summary: input.reconciliation.summary,
      tolerance: input.reconciliation.tolerance,
      drift: input.reconciliation.drift,
    }
    : null

  const modeReadiness = MODE_ORDER.map((mode) => {
    const compliance = input.compliance_matrix.decisions[mode]
    const runtime = evaluatePredictionMarketRuntimeGuard({
      venue: input.compliance_matrix.venue,
      mode,
      capabilities: input.capabilities,
      health: input.health,
      budgets: input.budgets,
    })

    return buildModeSummary({
      mode,
      compliance,
      runtime,
      capital: capitalLedger,
      reconciliation: input.reconciliation ?? null,
    })
  })

  const highestSafeReport = [...modeReadiness].reverse().find((report) => report.verdict !== 'blocked') ?? null
  const highestSafeMode = highestSafeReport?.effective_mode ?? null
  const overallVerdict: PredictionMarketExecutionReadinessVerdict = highestSafeReport
    ? highestSafeReport.verdict
    : 'blocked'

  const blockers = unique(modeReadiness.flatMap((report) => report.blockers))
  const warnings = unique(modeReadiness.flatMap((report) => report.warnings))
  const complianceTopMode = input.compliance_matrix.highest_authorized_mode
    ? `highest compliance mode: ${input.compliance_matrix.highest_authorized_mode}`
    : 'no compliance mode is authorized'

  const summary = highestSafeMode
    ? `Highest safe mode is ${highestSafeMode}. ${complianceTopMode}. ${highestSafeReport?.summary ?? 'No additional mode summary.'}`
    : `All modes are blocked. ${complianceTopMode}. ${blockers[0] ?? 'No safe operating mode.'}`

  return {
    venue: input.compliance_matrix.venue,
    venue_type: input.compliance_matrix.venue_type,
    capabilities: input.capabilities,
    health: input.health,
    budgets: input.budgets,
    compliance_matrix: input.compliance_matrix,
    capital_ledger: capitalLedger,
    reconciliation,
    mode_readiness: modeReadiness,
    highest_safe_mode: highestSafeMode,
    overall_verdict: overallVerdict,
    blockers,
    warnings,
    summary,
  }
}

export function buildPredictionMarketExecutionReadinessFromMatrix(input: {
  capabilities: VenueCapabilities
  health: VenueHealthSnapshot
  budgets: PredictionMarketBudgets
  compliance_input: Omit<Parameters<typeof evaluatePredictionMarketComplianceMatrix>[0], 'mode'>
  capital_ledger?: PredictionMarketExecutionReadinessCapitalLedger
  reconciliation?: CapitalLedgerReconciliationReport
}): PredictionMarketExecutionReadinessReport {
  const complianceMatrix = evaluatePredictionMarketComplianceMatrix(input.compliance_input)
  return buildPredictionMarketExecutionReadiness({
    capabilities: input.capabilities,
    health: input.health,
    budgets: predictionMarketBudgetsSchema.parse(input.budgets),
    compliance_matrix: complianceMatrix,
    capital_ledger: input.capital_ledger,
    reconciliation: input.reconciliation,
  })
}
