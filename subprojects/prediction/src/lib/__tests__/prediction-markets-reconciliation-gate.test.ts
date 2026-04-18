import { describe, expect, it } from 'vitest'
import { evaluateReconciliationGate } from '@/lib/prediction-markets/reconciliation-gate'
import type {
  CapitalLedgerReconciliationReport,
  CapitalLedgerReconciliationSeverity,
} from '@/lib/prediction-markets/reconciliation'

function makeReconciliation(
  overrides: Partial<CapitalLedgerReconciliationReport> & {
    severity?: CapitalLedgerReconciliationSeverity
  } = {},
): CapitalLedgerReconciliationReport {
  return {
    theoretical: {
      snapshot: {
        venue: 'polymarket',
        collateral_currency: 'USDC',
        cash_available: 100,
        cash_locked: 10,
        withdrawable_amount: 90,
        open_exposure_usd: 15,
        transfer_latency_estimate_ms: 1000,
        positions: [],
      },
      totals: {
        cash_total: 110,
        locked_collateral: 10,
        open_positions: 0,
        utilization_ratio: 0.1364,
      },
      positions: [],
    },
    observed: {
      snapshot: {
        venue: 'polymarket',
        collateral_currency: 'USDC',
        cash_available: 88,
        cash_locked: 13,
        withdrawable_amount: 83,
        open_exposure_usd: 16,
        transfer_latency_estimate_ms: 1000,
        positions: [],
      },
      totals: {
        cash_total: 101,
        locked_collateral: 13,
        open_positions: 0,
        utilization_ratio: 0.1584,
      },
      positions: [],
    },
    severity: 'low',
    within_tolerance: false,
    summary: 'Observed ledger drift exceeds tolerance.',
    tolerance: {
      usd: 5,
      ratio: 0.01,
    },
    drift: {
      cash_available_usd: 12,
      cash_locked_usd: 3,
      withdrawable_amount_usd: 7,
      open_exposure_usd: 1,
      cash_total_usd: 9,
      locked_collateral_usd: 3,
      open_positions: 0,
    },
    reasons: [],
    ...overrides,
  }
}

describe('prediction markets reconciliation gate', () => {
  it('blocks live mode when drift is open', () => {
    const gate = evaluateReconciliationGate({
      mode: 'live',
      reconciliation: makeReconciliation({ severity: 'critical' }),
    })

    expect(gate).toMatchObject({
      mode: 'live',
      verdict: 'block',
    })
    expect(gate.blockers).toEqual(expect.arrayContaining([
      'reconciliation:open_drift:live_mode_blocked',
      'reconciliation:critical:live_mode_blocked',
    ]))
    expect(gate.warnings).toEqual(expect.arrayContaining([
      'reconciliation:Observed ledger drift exceeds tolerance.',
    ]))
  })

  it('blocks shadow mode when drift is critical', () => {
    const gate = evaluateReconciliationGate({
      mode: 'shadow',
      reconciliation: makeReconciliation({ severity: 'critical' }),
    })

    expect(gate.verdict).toBe('block')
    expect(gate.blockers).toContain('reconciliation:critical:shadow_mode_blocked')
  })

  it('warns for shadow mode when drift is non-critical', () => {
    const gate = evaluateReconciliationGate({
      mode: 'shadow',
      reconciliation: makeReconciliation({ severity: 'low' }),
    })

    expect(gate.verdict).toBe('warn')
    expect(gate.blockers).toEqual([])
    expect(gate.warnings).toEqual(expect.arrayContaining([
      'reconciliation:Observed ledger drift exceeds tolerance.',
      'reconciliation:low:shadow_mode_degraded',
    ]))
  })

  it('warns for paper mode when drift exists', () => {
    const gate = evaluateReconciliationGate({
      mode: 'paper',
      reconciliation: makeReconciliation({ severity: 'medium' }),
    })

    expect(gate.verdict).toBe('warn')
    expect(gate.blockers).toEqual([])
    expect(gate.warnings).toEqual(expect.arrayContaining([
      'reconciliation:medium:paper_mode_caution',
    ]))
  })

  it('passes when reconciliation is missing', () => {
    const gate = evaluateReconciliationGate({
      mode: 'paper',
      reconciliation: null,
    })

    expect(gate).toMatchObject({
      verdict: 'pass',
      blockers: [],
      warnings: [],
    })
  })

  it('blocks live mode when drift is open even if severity is none', () => {
    const gate = evaluateReconciliationGate({
      mode: 'live',
      reconciliation: makeReconciliation({
        severity: 'none',
        within_tolerance: false,
        summary: 'Ledger drift is present but severity remains uncategorized.',
      }),
    })

    expect(gate.verdict).toBe('block')
    expect(gate.blockers).toEqual(expect.arrayContaining([
      'reconciliation:open_drift:live_mode_blocked',
      'reconciliation:none:live_mode_blocked',
    ]))
    expect(gate.warnings).toEqual(expect.arrayContaining([
      'reconciliation:Ledger drift is present but severity remains uncategorized.',
    ]))
  })

  it('passes when reconciliation is within tolerance', () => {
    const gate = evaluateReconciliationGate({
      mode: 'live',
      reconciliation: makeReconciliation({
        within_tolerance: true,
        severity: 'none',
        summary: 'Ledger is within tolerance.',
      }),
    })

    expect(gate).toMatchObject({
      verdict: 'pass',
      blockers: [],
      warnings: [],
    })
  })
})
