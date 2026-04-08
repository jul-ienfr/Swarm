import {
  normalizeCapitalLedgerSnapshot,
  type CapitalLedgerSourceInput,
  type NormalizedCapitalLedgerResult,
} from '@/lib/prediction-markets/capital-ledger'

export type CapitalLedgerReconciliationSeverity = 'none' | 'low' | 'medium' | 'high' | 'critical'
export type CapitalLedgerReconciliationReasonCode =
  | 'venue_mismatch'
  | 'collateral_currency_mismatch'
  | 'cash_available_drift'
  | 'cash_locked_drift'
  | 'withdrawable_amount_drift'
  | 'open_exposure_drift'
  | 'cash_total_drift'
  | 'locked_collateral_drift'
  | 'open_positions_drift'

export type CapitalLedgerReconciliationReason = {
  code: CapitalLedgerReconciliationReasonCode
  severity: Exclude<CapitalLedgerReconciliationSeverity, 'none'>
  message: string
}

export type CapitalLedgerReconciliationInput = {
  theoretical: CapitalLedgerSourceInput | NormalizedCapitalLedgerResult
  observed: CapitalLedgerSourceInput | NormalizedCapitalLedgerResult
  tolerance_usd?: number
  tolerance_ratio?: number
}

export type CapitalLedgerDriftMetrics = {
  cash_available_usd: number
  cash_locked_usd: number
  withdrawable_amount_usd: number
  open_exposure_usd: number
  cash_total_usd: number
  locked_collateral_usd: number
  open_positions: number
}

export type CapitalLedgerReconciliationReport = {
  theoretical: NormalizedCapitalLedgerResult
  observed: NormalizedCapitalLedgerResult
  severity: CapitalLedgerReconciliationSeverity
  within_tolerance: boolean
  summary: string
  tolerance: {
    usd: number
    ratio: number
  }
  drift: CapitalLedgerDriftMetrics
  reasons: CapitalLedgerReconciliationReason[]
}

const DEFAULT_TOLERANCE_USD = 5
const DEFAULT_TOLERANCE_RATIO = 0.01

function roundUsd(value: number): number {
  return Number(value.toFixed(2))
}

function rankSeverity(severity: CapitalLedgerReconciliationSeverity): number {
  switch (severity) {
    case 'none':
      return 0
    case 'low':
      return 1
    case 'medium':
      return 2
    case 'high':
      return 3
    case 'critical':
      return 4
  }
}

function maxSeverity(
  left: CapitalLedgerReconciliationSeverity,
  right: CapitalLedgerReconciliationSeverity,
): CapitalLedgerReconciliationSeverity {
  return rankSeverity(right) > rankSeverity(left) ? right : left
}

function ensureNormalized(
  input: CapitalLedgerSourceInput | NormalizedCapitalLedgerResult,
): NormalizedCapitalLedgerResult {
  return 'snapshot' in input && 'totals' in input
    ? input
    : normalizeCapitalLedgerSnapshot(input)
}

function classifyDriftSeverity(
  theoreticalValue: number,
  observedValue: number,
  toleranceUsd: number,
  toleranceRatio: number,
): Exclude<CapitalLedgerReconciliationSeverity, 'none'> | null {
  const absoluteDrift = Math.abs(observedValue - theoreticalValue)
  const denominator = Math.max(Math.abs(theoreticalValue), 1)
  const relativeDrift = absoluteDrift / denominator

  if (absoluteDrift <= toleranceUsd || relativeDrift <= toleranceRatio) {
    return null
  }

  if (absoluteDrift > toleranceUsd * 10 || relativeDrift > toleranceRatio * 10) {
    return 'critical'
  }
  if (absoluteDrift > toleranceUsd * 5 || relativeDrift > toleranceRatio * 5) {
    return 'high'
  }
  if (absoluteDrift > toleranceUsd * 2 || relativeDrift > toleranceRatio * 2) {
    return 'medium'
  }

  return 'low'
}

function pushReason(
  reasons: CapitalLedgerReconciliationReason[],
  code: CapitalLedgerReconciliationReasonCode,
  severity: Exclude<CapitalLedgerReconciliationSeverity, 'none'>,
  message: string,
) {
  reasons.push({ code, severity, message })
}

export function reconcileCapitalLedger(
  input: CapitalLedgerReconciliationInput,
): CapitalLedgerReconciliationReport {
  const theoretical = ensureNormalized(input.theoretical)
  const observed = ensureNormalized(input.observed)
  const toleranceUsd = input.tolerance_usd ?? DEFAULT_TOLERANCE_USD
  const toleranceRatio = input.tolerance_ratio ?? DEFAULT_TOLERANCE_RATIO
  const reasons: CapitalLedgerReconciliationReason[] = []
  let severity: CapitalLedgerReconciliationSeverity = 'none'

  const drift: CapitalLedgerDriftMetrics = {
    cash_available_usd: roundUsd(observed.snapshot.cash_available - theoretical.snapshot.cash_available),
    cash_locked_usd: roundUsd(observed.snapshot.cash_locked - theoretical.snapshot.cash_locked),
    withdrawable_amount_usd: roundUsd(observed.snapshot.withdrawable_amount - theoretical.snapshot.withdrawable_amount),
    open_exposure_usd: roundUsd(observed.snapshot.open_exposure_usd - theoretical.snapshot.open_exposure_usd),
    cash_total_usd: roundUsd(observed.totals.cash_total_usd - theoretical.totals.cash_total_usd),
    locked_collateral_usd: roundUsd(observed.totals.locked_collateral_usd - theoretical.totals.locked_collateral_usd),
    open_positions: observed.totals.open_positions - theoretical.totals.open_positions,
  }

  if (theoretical.snapshot.venue !== observed.snapshot.venue) {
    pushReason(
      reasons,
      'venue_mismatch',
      'critical',
      `Reconciliation compares different venues (${theoretical.snapshot.venue} vs ${observed.snapshot.venue}).`,
    )
    severity = 'critical'
  }

  if (theoretical.snapshot.collateral_currency !== observed.snapshot.collateral_currency) {
    pushReason(
      reasons,
      'collateral_currency_mismatch',
      'critical',
      `Collateral currency mismatch detected (${theoretical.snapshot.collateral_currency} vs ${observed.snapshot.collateral_currency}).`,
    )
    severity = 'critical'
  }

  const fieldChecks: Array<{
    code: CapitalLedgerReconciliationReasonCode
    theoreticalValue: number
    observedValue: number
    message: string
  }> = [
    {
      code: 'cash_available_drift',
      theoreticalValue: theoretical.snapshot.cash_available,
      observedValue: observed.snapshot.cash_available,
      message: `cash_available drifted by ${Math.abs(drift.cash_available_usd).toFixed(2)} USD.`,
    },
    {
      code: 'cash_locked_drift',
      theoreticalValue: theoretical.snapshot.cash_locked,
      observedValue: observed.snapshot.cash_locked,
      message: `cash_locked drifted by ${Math.abs(drift.cash_locked_usd).toFixed(2)} USD.`,
    },
    {
      code: 'withdrawable_amount_drift',
      theoreticalValue: theoretical.snapshot.withdrawable_amount,
      observedValue: observed.snapshot.withdrawable_amount,
      message: `withdrawable_amount drifted by ${Math.abs(drift.withdrawable_amount_usd).toFixed(2)} USD.`,
    },
    {
      code: 'open_exposure_drift',
      theoreticalValue: theoretical.snapshot.open_exposure_usd,
      observedValue: observed.snapshot.open_exposure_usd,
      message: `open_exposure_usd drifted by ${Math.abs(drift.open_exposure_usd).toFixed(2)} USD.`,
    },
    {
      code: 'cash_total_drift',
      theoreticalValue: theoretical.totals.cash_total_usd,
      observedValue: observed.totals.cash_total_usd,
      message: `cash_total_usd drifted by ${Math.abs(drift.cash_total_usd).toFixed(2)} USD.`,
    },
    {
      code: 'locked_collateral_drift',
      theoreticalValue: theoretical.totals.locked_collateral_usd,
      observedValue: observed.totals.locked_collateral_usd,
      message: `locked_collateral_usd drifted by ${Math.abs(drift.locked_collateral_usd).toFixed(2)} USD.`,
    },
  ]

  for (const fieldCheck of fieldChecks) {
    const fieldSeverity = classifyDriftSeverity(
      fieldCheck.theoreticalValue,
      fieldCheck.observedValue,
      toleranceUsd,
      toleranceRatio,
    )

    if (fieldSeverity) {
      pushReason(reasons, fieldCheck.code, fieldSeverity, fieldCheck.message)
      severity = maxSeverity(severity, fieldSeverity)
    }
  }

  if (drift.open_positions !== 0) {
    const positionSeverity: Exclude<CapitalLedgerReconciliationSeverity, 'none'> =
      Math.abs(drift.open_positions) >= 3 ? 'high' : 'medium'
    pushReason(
      reasons,
      'open_positions_drift',
      positionSeverity,
      `open position count drifted by ${Math.abs(drift.open_positions)}.`,
    )
    severity = maxSeverity(severity, positionSeverity)
  }

  const withinTolerance = severity === 'none'
  const headlineReason = reasons[0]
  const summary = withinTolerance
    ? 'Observed capital ledger matches the theoretical ledger within tolerance.'
    : `Observed capital ledger drifted from the theoretical ledger with ${severity} severity: ${headlineReason?.message ?? 'drift detected.'}`

  return {
    theoretical,
    observed,
    severity,
    within_tolerance: withinTolerance,
    summary,
    tolerance: {
      usd: toleranceUsd,
      ratio: toleranceRatio,
    },
    drift,
    reasons,
  }
}
