import type { PredictionMarketExecutionReadinessVerdict } from '@/lib/prediction-markets/execution-readiness'
import type { CapitalLedgerReconciliationSeverity } from '@/lib/prediction-markets/reconciliation'
import type { ExecutionIntentPreview } from '@/lib/prediction-markets/schemas'

export type ExecutionJournalEntry = {
  run_id: string
  entry_kind: 'execution_intent_preview'
  preview_id: string
  preview_kind: ExecutionIntentPreview['preview_kind']
  execution_readiness_verdict: PredictionMarketExecutionReadinessVerdict
  reconciliation_status: CapitalLedgerReconciliationSeverity | 'absent'
  venue: string
  market_id: string | null
  summary: string
}

export function appendExecutionJournalEntries(input: {
  existing: ExecutionJournalEntry[]
  runId: string
  preview: ExecutionIntentPreview | null
  executionReadinessVerdict: PredictionMarketExecutionReadinessVerdict
  reconciliationStatus: CapitalLedgerReconciliationSeverity | 'absent'
}): ExecutionJournalEntry[] {
  if (!input.preview) {
    return input.existing
  }

  if (input.existing.some((entry) => entry.entry_kind === 'execution_intent_preview' && entry.preview_id === input.preview?.preview_id)) {
    return input.existing
  }

  const marketId = 'market_id' in input.preview
    ? input.preview.market_id
    : null

  return [
    ...input.existing,
    {
      run_id: input.runId,
      entry_kind: 'execution_intent_preview',
      preview_id: input.preview.preview_id,
      preview_kind: input.preview.preview_kind,
      execution_readiness_verdict: input.executionReadinessVerdict,
      reconciliation_status: input.reconciliationStatus,
      venue: input.preview.venue,
      market_id: marketId,
      summary: input.preview.summary,
    },
  ]
}
