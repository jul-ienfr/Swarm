import { describe, expect, it } from 'vitest'
import { appendExecutionJournalEntries } from '@/lib/prediction-markets/execution-journal'
import type { ExecutionIntentPreview } from '@/lib/prediction-markets/schemas'

function makePreview(overrides: Partial<ExecutionIntentPreview> = {}): ExecutionIntentPreview {
  return {
    schema_version: 'prediction-markets/v1',
    preview_id: 'run-001:trade-preview',
    preview_kind: 'trade',
    run_id: 'run-001',
    venue: 'polymarket',
    market_id: 'market-001',
    strategy_profile: 'shadow',
    strategy_family: 'latency_reference_spread',
    trade_intent_preview: {
      schema_version: 'prediction-markets/v1',
      intent_id: 'intent-001',
      run_id: 'run-001',
      venue: 'polymarket',
      market_id: 'market-001',
      side: 'yes',
      size_usd: 25,
      limit_price: 0.58,
      max_slippage_bps: 15,
      max_unhedged_leg_ms: 200,
      time_in_force: 'gtc',
      forecast_ref: 'forecast-001',
      risk_checks_passed: true,
      created_at: '2026-04-08T00:00:00.000Z',
      notes: 'Shadow trade preview generated for auditability.',
    },
    summary: 'Trade preview for shadow execution journal coverage.',
    metadata: {
      strategy_summary: 'Shadow trade preview generated for auditability.',
    },
    ...overrides,
  }
}

describe('prediction markets execution journal', () => {
  it('writes a journal entry when an execution intent preview is present', () => {
    const preview = makePreview()
    const entries = appendExecutionJournalEntries({
      existing: [],
      runId: 'run-001',
      preview,
      executionReadinessVerdict: 'blocked',
      reconciliationStatus: 'low',
    })

    expect(entries).toHaveLength(1)
    expect(entries[0]).toMatchObject({
      run_id: 'run-001',
      entry_kind: 'execution_intent_preview',
      preview_id: preview.preview_id,
      preview_kind: 'trade',
      execution_readiness_verdict: 'blocked',
      reconciliation_status: 'low',
      market_id: 'market-001',
      venue: 'polymarket',
    })
    expect(entries[0].summary).toContain('Trade preview for shadow execution journal coverage.')
  })

  it('deduplicates the same preview id on repeated append', () => {
    const preview = makePreview()
    const existing = appendExecutionJournalEntries({
      existing: [],
      runId: 'run-001',
      preview,
      executionReadinessVerdict: 'blocked',
      reconciliationStatus: 'low',
    })

    const entries = appendExecutionJournalEntries({
      existing,
      runId: 'run-001',
      preview,
      executionReadinessVerdict: 'blocked',
      reconciliationStatus: 'low',
    })

    expect(entries).toHaveLength(1)
  })

  it('appends a new entry when existing execution previews belong to another run', () => {
    const preview = makePreview({
      preview_id: 'run-002:trade-preview',
      run_id: 'run-002',
      trade_intent_preview: {
        ...makePreview().trade_intent_preview,
        run_id: 'run-002',
        intent_id: 'intent-002',
      },
    })

    const existing = [
      {
        run_id: 'run-001',
        entry_kind: 'execution_intent_preview' as const,
        preview_id: 'run-001:trade-preview',
        preview_kind: 'trade' as const,
        execution_readiness_verdict: 'blocked' as const,
        reconciliation_status: 'low' as const,
        venue: 'polymarket',
        market_id: 'market-001',
        summary: 'Existing entry from an earlier run',
      },
    ]

    const entries = appendExecutionJournalEntries({
      existing,
      runId: 'run-002',
      preview,
      executionReadinessVerdict: 'ready',
      reconciliationStatus: 'none',
    })

    expect(entries).toHaveLength(2)
    expect(entries[1]).toMatchObject({
      run_id: 'run-002',
      preview_id: 'run-002:trade-preview',
      execution_readiness_verdict: 'ready',
      reconciliation_status: 'none',
    })
  })

  it('returns existing entries unchanged when preview is absent', () => {
    const existing = [
      {
        run_id: 'run-001',
        entry_kind: 'execution_intent_preview',
        preview_id: 'existing-preview',
        preview_kind: 'trade',
        execution_readiness_verdict: 'ready',
        reconciliation_status: 'none',
        venue: 'polymarket',
        market_id: 'market-001',
        summary: 'Existing entry',
      },
    ]

    const entries = appendExecutionJournalEntries({
      existing,
      runId: 'run-001',
      preview: null,
      executionReadinessVerdict: 'blocked',
      reconciliationStatus: 'low',
    })

    expect(entries).toEqual(existing)
  })
})
