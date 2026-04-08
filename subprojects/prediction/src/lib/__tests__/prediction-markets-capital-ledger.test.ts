import { describe, expect, it } from 'vitest'
import {
  computeCapitalLedgerTotals,
  normalizeCapitalLedgerSnapshot,
} from '@/lib/prediction-markets/capital-ledger'
import { reconcileCapitalLedger } from '@/lib/prediction-markets/reconciliation'

describe('prediction markets capital ledger', () => {
  it('normalizes a polymarket ledger snapshot and computes totals from positions', () => {
    const result = normalizeCapitalLedgerSnapshot({
      venue: 'polymarket',
      captured_at: '2026-04-08T00:00:00.000Z',
      cash_available_usd: 1000,
      cash_locked_usd: 125,
      withdrawable_amount_usd: 920,
      positions: [
        {
          position_id: 'p-1',
          market_id: 'mkt-1',
          exposure_usd: 150,
          collateral_locked_usd: 60,
          unrealized_pnl_usd: 12,
          status: 'open',
        },
        {
          position_id: 'p-2',
          market_id: 'mkt-2',
          exposure_usd: 75,
          collateral_locked_usd: 25,
          unrealized_pnl_usd: -3,
          status: 'open',
        },
      ],
    })

    expect(result.snapshot).toMatchObject({
      venue: 'polymarket',
      cash_available: 1000,
      cash_locked: 125,
      withdrawable_amount: 920,
      open_exposure_usd: 225,
      transfer_latency_estimate_ms: 15000,
    })
    expect(result.totals).toEqual({
      cash_total_usd: 1125,
      exposure_total_usd: 225,
      locked_collateral_usd: 85,
      unrealized_pnl_usd: 9,
      open_positions: 2,
      utilization_ratio: 0.2,
    })
    expect(result.notes.map((note) => note.code)).toContain('default_applied')
  })

  it('normalizes a kalshi ledger snapshot from alias fields', () => {
    const result = normalizeCapitalLedgerSnapshot({
      venue: 'kalshi',
      captured_at: '2026-04-08T00:00:00.000Z',
      available_balance: 750,
      reserved_balance: 180,
      withdrawable_balance: 700,
      open_exposure_usd: 260,
      collateral_currency: 'USD',
    })

    expect(result.snapshot).toMatchObject({
      venue: 'kalshi',
      cash_available: 750,
      cash_locked: 180,
      withdrawable_amount: 700,
      open_exposure_usd: 260,
      transfer_latency_estimate_ms: 60000,
    })
    expect(result.notes.map((note) => note.message)).toEqual(expect.arrayContaining([
      'cash_available normalized from available_balance.',
      'cash_locked normalized from reserved_balance.',
      'withdrawable_amount normalized from withdrawable_balance.',
      'transfer_latency_estimate_ms defaulted for kalshi.',
    ]))
  })

  it('computes totals directly from a normalized snapshot', () => {
    const normalized = normalizeCapitalLedgerSnapshot({
      venue: 'polymarket',
      captured_at: '2026-04-08T00:00:00.000Z',
      cash_available: 400,
      cash_locked: 100,
      withdrawable_amount: 380,
      open_exposure_usd: 90,
      transfer_latency_estimate_ms: 12000,
    })

    expect(computeCapitalLedgerTotals({ snapshot: normalized.snapshot })).toEqual({
      cash_total_usd: 500,
      exposure_total_usd: 90,
      locked_collateral_usd: 100,
      unrealized_pnl_usd: 0,
      open_positions: 0,
      utilization_ratio: 0.18,
    })
  })

  it('reports no drift when observed capital stays within tolerance', () => {
    const report = reconcileCapitalLedger({
      theoretical: {
        venue: 'polymarket',
        captured_at: '2026-04-08T00:00:00.000Z',
        cash_available: 1000,
        cash_locked: 100,
        withdrawable_amount: 950,
        open_exposure_usd: 250,
        transfer_latency_estimate_ms: 15000,
      },
      observed: {
        venue: 'polymarket',
        captured_at: '2026-04-08T00:01:00.000Z',
        cash_available: 1002,
        cash_locked: 102,
        withdrawable_amount: 948,
        open_exposure_usd: 252,
        transfer_latency_estimate_ms: 15000,
      },
      tolerance_usd: 5,
      tolerance_ratio: 0.02,
    })

    expect(report).toMatchObject({
      severity: 'none',
      within_tolerance: true,
      reasons: [],
    })
    expect(report.summary).toContain('matches the theoretical ledger within tolerance')
  })

  it('reports structured drift reasons with severity when observed values diverge materially', () => {
    const report = reconcileCapitalLedger({
      theoretical: {
        venue: 'kalshi',
        captured_at: '2026-04-08T00:00:00.000Z',
        available_balance: 800,
        reserved_balance: 120,
        withdrawable_balance: 760,
        open_exposure_usd: 200,
      },
      observed: {
        venue: 'kalshi',
        captured_at: '2026-04-08T00:01:00.000Z',
        available_balance: 620,
        reserved_balance: 240,
        withdrawable_balance: 580,
        open_exposure_usd: 360,
        positions: [
          { position_id: 'k-1', market_id: 'evt-1', exposure_usd: 180, collateral_locked_usd: 90, status: 'open' },
          { position_id: 'k-2', market_id: 'evt-2', exposure_usd: 180, collateral_locked_usd: 80, status: 'open' },
          { position_id: 'k-3', market_id: 'evt-3', exposure_usd: 40, collateral_locked_usd: 20, status: 'open' },
        ],
      },
      tolerance_usd: 10,
      tolerance_ratio: 0.02,
    })

    expect(report.severity).toBe('critical')
    expect(report.within_tolerance).toBe(false)
    expect(report.reasons.map((reason) => reason.code)).toEqual(expect.arrayContaining([
      'cash_available_drift',
      'cash_locked_drift',
      'withdrawable_amount_drift',
      'open_exposure_drift',
      'locked_collateral_drift',
      'open_positions_drift',
    ]))
    expect(report.summary).toContain('drifted from the theoretical ledger')
  })

  it('flags venue or currency mismatches as critical', () => {
    const report = reconcileCapitalLedger({
      theoretical: {
        venue: 'polymarket',
        captured_at: '2026-04-08T00:00:00.000Z',
        collateral_currency: 'USD',
        cash_available: 500,
        cash_locked: 50,
        withdrawable_amount: 480,
        open_exposure_usd: 100,
        transfer_latency_estimate_ms: 15000,
      },
      observed: {
        venue: 'kalshi',
        captured_at: '2026-04-08T00:01:00.000Z',
        collateral_currency: 'USDC',
        cash_available: 500,
        cash_locked: 50,
        withdrawable_amount: 480,
        open_exposure_usd: 100,
        transfer_latency_estimate_ms: 15000,
      },
    })

    expect(report.severity).toBe('critical')
    expect(report.within_tolerance).toBe(false)
    expect(report.reasons.map((reason) => reason.code)).toEqual(expect.arrayContaining([
      'venue_mismatch',
      'collateral_currency_mismatch',
    ]))
  })
})
