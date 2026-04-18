import type {
  CapitalLedgerReconciliationReport,
  CapitalLedgerReconciliationSeverity,
} from '@/lib/prediction-markets/reconciliation'
import type { PredictionMarketExecutionReadinessMode } from '@/lib/prediction-markets/execution-readiness'

export type ReconciliationGateVerdict = 'pass' | 'warn' | 'block'

export type ReconciliationGateResult = {
  mode: PredictionMarketExecutionReadinessMode
  verdict: ReconciliationGateVerdict
  blockers: string[]
  warnings: string[]
}

function pushUnique(target: string[], value: string) {
  if (!target.includes(value)) {
    target.push(value)
  }
}

function severityPrefix(severity: CapitalLedgerReconciliationSeverity): string {
  return `reconciliation:${severity}`
}

export function evaluateReconciliationGate(input: {
  mode: PredictionMarketExecutionReadinessMode
  reconciliation: CapitalLedgerReconciliationReport | null
}): ReconciliationGateResult {
  const blockers: string[] = []
  const warnings: string[] = []

  if (!input.reconciliation || input.reconciliation.within_tolerance) {
    return {
      mode: input.mode,
      verdict: 'pass',
      blockers,
      warnings,
    }
  }

  pushUnique(warnings, `reconciliation:${input.reconciliation.summary}`)
  const prefix = severityPrefix(input.reconciliation.severity)

  if (input.mode === 'live') {
    pushUnique(blockers, 'reconciliation:open_drift:live_mode_blocked')
    pushUnique(blockers, `${prefix}:live_mode_blocked`)
  } else if (input.mode === 'shadow') {
    if (input.reconciliation.severity === 'critical') {
      pushUnique(blockers, `${prefix}:shadow_mode_blocked`)
    } else {
      pushUnique(warnings, `${prefix}:shadow_mode_degraded`)
    }
  } else if (input.mode === 'paper' && input.reconciliation.severity !== 'none') {
    pushUnique(warnings, `${prefix}:paper_mode_caution`)
  }

  return {
    mode: input.mode,
    verdict: blockers.length > 0 ? 'block' : warnings.length > 0 ? 'warn' : 'pass',
    blockers,
    warnings,
  }
}
