import { describe, expect, it } from 'vitest'
import { PredictionMarketResearchMemoryAdapter } from '@/lib/prediction-markets/memory/adapter'
import { PredictionMarketInMemoryProvider } from '@/lib/prediction-markets/memory/provider'

describe('prediction markets research memory adapter', () => {
  it('stores research traces and exposes search/recall semantics', () => {
    const adapter = new PredictionMarketResearchMemoryAdapter(new PredictionMarketInMemoryProvider())

    const entry = adapter.rememberResearchTrace({
      trace_id: 'trace-100',
      pipeline_id: 'baseline-v0',
      venue: 'polymarket',
      market_id: 'mkt-research-001',
      generated_at: '2026-04-09T00:00:00.000Z',
      summary: 'Market-only baseline anchored at 0.51 and compared against aggregate.',
      trace: {
        summary: 'Market-only baseline anchored at 0.51 and compared against aggregate.',
        market_only_probability_yes: 0.51,
      },
      tags: ['baseline', 'abstention'],
    })

    expect(entry.namespace).toBe('research')
    expect(entry.kind).toBe('research_trace')
    expect(entry.subject_id).toBe('polymarket:mkt-research-001:baseline-v0')
    expect(entry.tags).toEqual(expect.arrayContaining(['research', 'trace', 'polymarket', 'baseline-v0']))

    const recalled = adapter.recall({ namespace: 'research', kind: 'research_trace' })
    expect(recalled).toHaveLength(1)
    expect(recalled[0]).toMatchObject({
      memory_id: entry.memory_id,
      source_ref: 'trace-100',
    })

    const searched = adapter.search({ text: 'aggregate' })
    expect(searched).toHaveLength(1)
    expect(searched[0].content).toMatchObject({
      summary: 'Market-only baseline anchored at 0.51 and compared against aggregate.',
    })

    expect(adapter.forget(entry.memory_id)).toBe(true)
    expect(adapter.recall()).toHaveLength(0)
  })
})
