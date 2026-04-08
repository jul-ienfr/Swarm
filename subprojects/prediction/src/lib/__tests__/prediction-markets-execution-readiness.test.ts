import { describe, expect, it } from 'vitest'
import {
  buildPredictionMarketExecutionReadiness,
} from '@/lib/prediction-markets/execution-readiness'
import {
  evaluatePredictionMarketComplianceMatrix,
} from '@/lib/prediction-markets/compliance'
import {
  reconcileCapitalLedger,
} from '@/lib/prediction-markets/reconciliation'
import { type CapitalLedgerSourceInput } from '@/lib/prediction-markets/capital-ledger'
import {
  predictionMarketBudgetsSchema,
  venueCapabilitiesSchema,
  venueHealthSnapshotSchema,
} from '@/lib/prediction-markets/schemas'

function makeReadyCapabilities(venueType: 'execution-equivalent' | 'reference-only') {
  return venueCapabilitiesSchema.parse({
    venue: 'polymarket',
    venue_type: venueType,
    supports_discovery: true,
    supports_metadata: true,
    supports_orderbook: true,
    supports_trades: true,
    supports_positions: true,
    supports_execution: venueType === 'execution-equivalent',
    supports_websocket: true,
    supports_paper_mode: true,
    automation_constraints: [],
    rate_limit_notes: 'read-only and execution-safe',
    last_verified_at: '2026-04-08T00:00:00.000Z',
  })
}

function makeHealthyHealth(venue: 'polymarket' | 'kalshi') {
  return venueHealthSnapshotSchema.parse({
    venue,
    captured_at: '2026-04-08T00:00:00.000Z',
    health_score: 1,
    api_status: 'healthy',
    stream_status: 'healthy',
    staleness_ms: 0,
    degraded_mode: 'normal',
    incident_flags: [],
  })
}

function makeTightBudgets(venue: 'polymarket' | 'kalshi') {
  return predictionMarketBudgetsSchema.parse({
    venue,
    fetch_latency_budget_ms: 4_000,
    snapshot_freshness_budget_ms: 4_000,
    decision_latency_budget_ms: 2_000,
    stream_reconnect_budget_ms: 4_000,
    cache_ttl_ms: 1_000,
    max_retries: 0,
    backpressure_policy: 'degrade-to-wait',
  })
}

describe('prediction markets execution readiness', () => {
  it('keeps live as the highest safe mode when every subsystem is healthy', () => {
    const capabilities = makeReadyCapabilities('execution-equivalent')
    const health = makeHealthyHealth('polymarket')
    const budgets = makeTightBudgets('polymarket')
    const complianceMatrix = evaluatePredictionMarketComplianceMatrix({
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      capabilities: {
        supports_discovery: true,
        supports_metadata: true,
        supports_orderbook: true,
        supports_trades: true,
        supports_execution: true,
        supports_paper_mode: true,
        automation_constraints: [],
      },
      jurisdiction: 'us',
      account_type: 'trading',
      kyc_status: 'approved',
      api_key_present: true,
      trading_enabled: true,
    })

    const readiness = buildPredictionMarketExecutionReadiness({
      capabilities,
      health,
      budgets,
      compliance_matrix: complianceMatrix,
    })

    expect(readiness.highest_safe_mode).toBe('live')
    expect(readiness.overall_verdict).toBe('ready')
    expect(readiness.blockers).toEqual([])
    expect(readiness.warnings).toEqual([])
    expect(readiness.mode_readiness.find((entry) => entry.mode === 'live')).toMatchObject({
      verdict: 'ready',
      effective_mode: 'live',
    })
  })

  it('drops back to paper when capital pressure and reconciliation drift make higher modes unsafe', () => {
    const capabilities = makeReadyCapabilities('execution-equivalent')
    const health = makeHealthyHealth('kalshi')
    const budgets = makeTightBudgets('kalshi')
    const complianceMatrix = evaluatePredictionMarketComplianceMatrix({
      venue: 'kalshi',
      venue_type: 'execution-equivalent',
      capabilities: {
        supports_discovery: true,
        supports_metadata: true,
        supports_orderbook: true,
        supports_trades: true,
        supports_execution: true,
        supports_paper_mode: true,
        automation_constraints: [],
      },
      jurisdiction: 'us',
      account_type: 'trading',
      kyc_status: 'approved',
      api_key_present: true,
      trading_enabled: true,
    })
    const capitalLedger: CapitalLedgerSourceInput = {
      venue: 'kalshi',
      captured_at: '2026-04-08T00:00:00.000Z',
      cash_available: 100,
      cash_locked: 50,
      collateral_currency: 'USD',
      open_exposure_usd: 180,
      withdrawable_amount: 90,
      transfer_latency_estimate_ms: 60_000,
    }
    const reconciliation = reconcileCapitalLedger({
      theoretical: capitalLedger,
      observed: {
        venue: 'kalshi',
        captured_at: '2026-04-08T00:01:00.000Z',
        cash_available: 70,
        cash_locked: 80,
        collateral_currency: 'USD',
        open_exposure_usd: 220,
        withdrawable_amount: 55,
        transfer_latency_estimate_ms: 60_000,
      },
      tolerance_usd: 5,
      tolerance_ratio: 0.01,
    })

    const readiness = buildPredictionMarketExecutionReadiness({
      capabilities,
      health,
      budgets,
      compliance_matrix: complianceMatrix,
      capital_ledger: capitalLedger,
      reconciliation,
    })

    expect(readiness.highest_safe_mode).toBe('paper')
    expect(readiness.overall_verdict).toBe('degraded')
    expect(readiness.blockers).toEqual(expect.arrayContaining([
      'capital:live_mode_capacity_exhausted',
      'capital:shadow_mode_capacity_exhausted',
      'reconciliation:critical:live_mode_blocked',
      'reconciliation:critical:shadow_mode_blocked',
    ]))
    expect(readiness.mode_readiness.find((entry) => entry.mode === 'live')).toMatchObject({
      verdict: 'blocked',
      effective_mode: 'live',
    })
    expect(readiness.mode_readiness.find((entry) => entry.mode === 'paper')).toMatchObject({
      verdict: 'degraded',
    })
  })

  it('keeps paper as the highest safe mode on a reference-only venue', () => {
    const capabilities = makeReadyCapabilities('reference-only')
    const health = makeHealthyHealth('polymarket')
    const budgets = makeTightBudgets('polymarket')
    const complianceMatrix = evaluatePredictionMarketComplianceMatrix({
      venue: 'polymarket',
      venue_type: 'reference-only',
      capabilities: {
        supports_discovery: true,
        supports_metadata: true,
        supports_orderbook: true,
        supports_trades: true,
        supports_execution: false,
        supports_paper_mode: false,
        automation_constraints: ['read-only advisory mode only'],
      },
      jurisdiction: 'us',
      account_type: 'viewer',
      kyc_status: 'approved',
      api_key_present: false,
      trading_enabled: false,
    })

    const readiness = buildPredictionMarketExecutionReadiness({
      capabilities,
      health,
      budgets,
      compliance_matrix: complianceMatrix,
    })

    expect(readiness.highest_safe_mode).toBe('paper')
    expect(readiness.overall_verdict).toBe('degraded')
    expect(readiness.mode_readiness.find((entry) => entry.mode === 'live')).toMatchObject({
      verdict: 'blocked',
    })
    expect(readiness.mode_readiness.find((entry) => entry.mode === 'shadow')).toMatchObject({
      verdict: 'degraded',
    })
    expect(readiness.mode_readiness.find((entry) => entry.mode === 'paper')).toMatchObject({
      verdict: 'degraded',
      effective_mode: 'paper',
    })
    expect(readiness.summary).toContain('Highest safe mode is paper')
  })
})
