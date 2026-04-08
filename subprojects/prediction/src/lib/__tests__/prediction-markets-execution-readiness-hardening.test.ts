import { describe, expect, it } from 'vitest'
import {
  buildPredictionMarketExecutionReadiness,
} from '@/lib/prediction-markets/execution-readiness'
import {
  evaluatePredictionMarketComplianceMatrix,
} from '@/lib/prediction-markets/compliance'
import {
  capitalLedgerSnapshotSchema,
  predictionMarketBudgetsSchema,
  venueCapabilitiesSchema,
  venueHealthSnapshotSchema,
  type PredictionMarketVenue,
  type PredictionMarketVenueType,
} from '@/lib/prediction-markets/schemas'

function makeCapabilities(input: {
  venue: PredictionMarketVenue
  venue_type?: PredictionMarketVenueType
  supports_discovery?: boolean
  supports_execution?: boolean
  supports_paper_mode?: boolean
  automation_constraints?: string[]
}) {
  return venueCapabilitiesSchema.parse({
    venue: input.venue,
    venue_type: input.venue_type ?? 'execution-equivalent',
    supports_discovery: input.supports_discovery ?? true,
    supports_metadata: true,
    supports_orderbook: true,
    supports_trades: true,
    supports_positions: true,
    supports_execution: input.supports_execution ?? true,
    supports_websocket: true,
    supports_paper_mode: input.supports_paper_mode ?? true,
    automation_constraints: input.automation_constraints ?? [],
    rate_limit_notes: 'Synthetic test contract.',
    last_verified_at: '2026-04-08T00:00:00.000Z',
  })
}

function makeHealthyHealth(venue: PredictionMarketVenue) {
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

function makeTightBudgets() {
  return predictionMarketBudgetsSchema.parse({
    fetch_latency_budget_ms: 4_000,
    snapshot_freshness_budget_ms: 4_000,
    decision_latency_budget_ms: 2_000,
    stream_reconnect_budget_ms: 4_000,
    cache_ttl_ms: 1_000,
    max_retries: 0,
    backpressure_policy: 'degrade-to-wait',
  })
}

describe('prediction markets execution readiness hardening', () => {
  it('blocks every mode when discovery support is missing from both compliance and runtime envelopes', () => {
    const capabilities = makeCapabilities({
      venue: 'polymarket',
      supports_discovery: false,
      supports_execution: true,
      supports_paper_mode: true,
    })
    const health = makeHealthyHealth('polymarket')
    const budgets = makeTightBudgets()
    const complianceMatrix = evaluatePredictionMarketComplianceMatrix({
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      capabilities: {
        supports_discovery: false,
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

    expect(readiness.highest_safe_mode).toBeNull()
    expect(readiness.overall_verdict).toBe('blocked')
    expect(readiness.compliance_matrix.highest_authorized_mode).toBeNull()
    expect(readiness.summary).toContain('All modes are blocked.')
    expect(readiness.mode_readiness).toHaveLength(4)
    expect(readiness.mode_readiness.every((entry) => entry.verdict === 'blocked')).toBe(true)
    expect(readiness.blockers).toEqual(expect.arrayContaining([
      'runtime:discovery mode blocked',
      'runtime:venue does not support discovery',
    ]))
    expect(readiness.blockers.some((value) => value.includes('compliance:Discovery mode is blocked'))).toBe(true)
  })

  it('keeps live as the highest safe mode while degrading on non-USD collateral warnings only', () => {
    const capabilities = makeCapabilities({
      venue: 'kalshi',
      supports_discovery: true,
      supports_execution: true,
      supports_paper_mode: true,
    })
    const health = makeHealthyHealth('kalshi')
    const budgets = makeTightBudgets()
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
    const capitalLedger = capitalLedgerSnapshotSchema.parse({
      venue: 'kalshi',
      captured_at: '2026-04-08T00:00:00.000Z',
      cash_available: 1_000,
      cash_locked: 100,
      collateral_currency: 'EUR',
      open_exposure_usd: 150,
      withdrawable_amount: 900,
      transfer_latency_estimate_ms: 30_000,
    })

    const readiness = buildPredictionMarketExecutionReadiness({
      capabilities,
      health,
      budgets,
      compliance_matrix: complianceMatrix,
      capital_ledger: capitalLedger,
    })

    expect(readiness.highest_safe_mode).toBe('live')
    expect(readiness.overall_verdict).toBe('degraded')
    expect(readiness.capital_ledger).toMatchObject({
      source: 'snapshot',
      collateral_currency: 'EUR',
      cash_available_usd: 1_000,
      open_exposure_usd: 150,
    })
    expect(readiness.warnings).toContain('capital:collateral_currency:EUR')
    expect(readiness.blockers).toEqual([])
    expect(readiness.mode_readiness.find((entry) => entry.mode === 'live')).toMatchObject({
      verdict: 'degraded',
      effective_mode: 'live',
    })
  })
})
