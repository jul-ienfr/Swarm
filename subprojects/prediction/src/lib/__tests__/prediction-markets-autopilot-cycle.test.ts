import { describe, expect, it } from 'vitest'
import {
  buildAutopilotCycleRecord,
  buildAutopilotCycleSummary,
  ledgerEntriesToAutopilotRecords,
  summarizeAutopilotCycles,
} from '@/lib/prediction-markets/autopilot-cycle'
import { createDecisionLedgerEntry } from '@/lib/prediction-markets/decision-ledger'
import { buildCalibrationReport } from '@/lib/prediction-markets/calibration'

describe('prediction markets autopilot cycle primitives', () => {
  it('summarizes a single cycle with outcomes, costs, and blocking signals', () => {
    const records = [
      buildAutopilotCycleRecord({
        cycle_id: 'cycle-1',
        stage: 'scan',
        status: 'running',
        market_id: 'm-1',
        action_type: 'scan',
        confidence: 0.4,
        note: 'Initial scan in progress.',
        created_at: '2026-04-09T10:00:00.000Z',
      }),
      buildAutopilotCycleRecord({
        cycle_id: 'cycle-1',
        stage: 'ticket',
        status: 'approved',
        market_id: 'm-1',
        action_type: 'ticket',
        edge_bps: 42,
        confidence: 0.7,
        note: 'Ticket approved.',
      }),
      buildAutopilotCycleRecord({
        cycle_id: 'cycle-1',
        stage: 'execution',
        status: 'executed',
        market_id: 'm-1',
        action_type: 'execute',
        pnl_usd: 13.5,
        cost_usd: 2.25,
        confidence: 0.8,
        completed_at: '2026-04-09T10:05:00.000Z',
      }),
    ]

    const summary = buildAutopilotCycleSummary(records)

    expect(summary.cycle_id).toBe('cycle-1')
    expect(summary.stage_counts.ticket).toBe(1)
    expect(summary.status_counts.executed).toBe(1)
    expect(summary.record_count).toBe(3)
    expect(summary.market_count).toBe(1)
    expect(summary.edge_bps_mean).toBe(42)
    expect(summary.pnl_usd_total).toBe(13.5)
    expect(summary.cost_usd_total).toBe(2.25)
    expect(summary.roi_pct).toBeCloseTo(600, 3)
    expect(summary.health).toBe('healthy')
  })

  it('summarizes from decision ledger entries and calibration metadata', () => {
    const ledgerEntries = [
      createDecisionLedgerEntry({
        entry_type: 'BET_PLACED',
        cycle_id: 'cycle-2',
        market_id: 'm-2',
        explanation: 'Trade entered.',
        confidence: 0.62,
        data: { stage: 'execution', status: 'executed', edge_bps: 35, pnl_usd: 9.75, cost_usd: 1.5 },
      }),
      createDecisionLedgerEntry({
        entry_type: 'BET_SKIPPED',
        cycle_id: 'cycle-2',
        market_id: 'm-3',
        explanation: 'Trade skipped.',
        confidence: 0.4,
        data: { stage: 'scan', status: 'blocked', blocked_reason: 'freshness_limit' },
      }),
    ]
    const records = ledgerEntriesToAutopilotRecords(ledgerEntries)
    const calibration = buildCalibrationReport([
      { predicted_probability: 0.2, actual_outcome: 0 },
      { predicted_probability: 0.8, actual_outcome: 1 },
    ])

    const report = summarizeAutopilotCycles(records, {
      calibration_report: calibration,
      ledger_entries: ledgerEntries,
    })

    expect(report.total_cycles).toBe(1)
    expect(report.total_records).toBe(2)
    expect(report.cycles[0].ledger_entries?.total_entries).toBe(2)
    expect(report.cycles[0].calibration_error).toBe(calibration.calibration_error)
    expect(report.overview.health).toBe('healthy')
    expect(report.overview.mean_calibration_error).toBe(calibration.calibration_error)
  })

  it('groups multiple cycles and preserves blocked health', () => {
    const records = [
      buildAutopilotCycleRecord({
        cycle_id: 'cycle-a',
        stage: 'approval',
        status: 'blocked',
        blocked_reason: 'no_approval',
      }),
      buildAutopilotCycleRecord({
        cycle_id: 'cycle-b',
        stage: 'execution',
        status: 'executed',
        pnl_usd: 5,
        cost_usd: 1,
      }),
    ]

    const report = summarizeAutopilotCycles(records)

    expect(report.total_cycles).toBe(2)
    expect(report.overview.blocked_cycles).toBe(1)
    expect(report.cycles.find((cycle) => cycle.cycle_id === 'cycle-a')?.health).toBe('blocked')
    expect(report.cycles.find((cycle) => cycle.cycle_id === 'cycle-b')?.health).toBe('healthy')
  })
})

