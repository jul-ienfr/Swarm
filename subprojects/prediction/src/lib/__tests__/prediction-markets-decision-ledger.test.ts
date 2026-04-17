import { describe, expect, it } from 'vitest'
import {
  appendDecisionLedgerEntry,
  createDecisionLedgerEntry,
  filterDecisionLedgerEntries,
  parseDecisionLedgerJsonl,
  serializeDecisionLedgerJsonl,
  summarizeDecisionLedgerEntries,
} from '@/lib/prediction-markets/decision-ledger'

describe('prediction markets decision ledger', () => {
  it('appends entries without mutating the original ledger', () => {
    const original = Object.freeze([
      createDecisionLedgerEntry({
        entry_type: 'BET_SKIPPED',
        cycle_id: 'cycle-1',
        market_id: 'm-1',
        question: 'Will it rain?',
        explanation: 'No edge found.',
        confidence: 0.2,
        tags: ['risk', 'low-edge'],
      }),
    ])

    const result = appendDecisionLedgerEntry(original, {
      entry_type: 'BET_PLACED',
      cycle_id: 'cycle-1',
      market_id: 'm-1',
      question: 'Will it rain?',
      explanation: 'Edge exceeded threshold.',
      data: { edge_bps: 41 },
      confidence: 0.76,
      tags: ['edge', 'execution'],
    })

    expect(result.entries).toHaveLength(2)
    expect(original).toHaveLength(1)
    expect(result.entry.entry_type).toBe('BET_PLACED')
    expect(result.entry.id).toMatch(/^ledger_/)
  })

  it('round-trips jsonl and preserves append-only ordering', () => {
    const first = createDecisionLedgerEntry({
      entry_type: 'PARAM_CHANGED',
      cycle_id: 'cycle-2',
      market_id: '',
      explanation: 'Raised the confidence threshold.',
      data: { before: 0.61, after: 0.68 },
    })
    const second = createDecisionLedgerEntry({
      entry_type: 'CALIBRATION_UPDATE',
      cycle_id: 'cycle-2',
      market_id: 'm-2',
      question: 'Will the market resolve yes?',
      explanation: 'Applied calibration curve update.',
      data: { calibration_error: 0.08 },
      confidence: 0.88,
      tags: ['calibration'],
    })

    const serialized = serializeDecisionLedgerJsonl([first, second])
    const parsed = parseDecisionLedgerJsonl(`${serialized}\n\nnot-json\n`)

    expect(parsed).toHaveLength(2)
    expect(parsed[0]).toMatchObject({ entry_type: 'PARAM_CHANGED', cycle_id: 'cycle-2' })
    expect(parsed[1]).toMatchObject({ entry_type: 'CALIBRATION_UPDATE', market_id: 'm-2' })
  })

  it('summarizes types, cycles, markets, and confidence', () => {
    const entries = [
      createDecisionLedgerEntry({
        entry_type: 'BET_PLACED',
        cycle_id: 'cycle-a',
        market_id: 'market-a',
        explanation: 'Placed first trade.',
        confidence: 0.7,
        timestamp: '2026-04-09T09:00:00.000Z',
      }),
      createDecisionLedgerEntry({
        entry_type: 'BET_SKIPPED',
        cycle_id: 'cycle-a',
        market_id: 'market-b',
        explanation: 'Skipped second trade.',
        confidence: 0.3,
        timestamp: '2026-04-09T09:01:00.000Z',
      }),
      createDecisionLedgerEntry({
        entry_type: 'BET_RESOLVED',
        cycle_id: 'cycle-b',
        market_id: 'market-a',
        explanation: 'Resolved the position.',
        confidence: 0.9,
        timestamp: '2026-04-09T09:02:00.000Z',
      }),
    ]

    const summary = summarizeDecisionLedgerEntries(entries)

    expect(summary.total_entries).toBe(3)
    expect(summary.entry_types.BET_PLACED).toBe(1)
    expect(summary.entry_types.BET_SKIPPED).toBe(1)
    expect(summary.entry_types.BET_RESOLVED).toBe(1)
    expect(summary.cycle_count).toBe(2)
    expect(summary.market_count).toBe(2)
    expect(summary.latest_entry?.entry_type).toBe('BET_RESOLVED')
    expect(summary.confidence_mean).toBeCloseTo(0.6333, 3)
    expect(summary.explanation_samples).toEqual([
      'Placed first trade.',
      'Skipped second trade.',
      'Resolved the position.',
    ])
  })

  it('filters by query, tag, market, and cycle', () => {
    const entries = [
      createDecisionLedgerEntry({
        entry_type: 'BET_PLACED',
        cycle_id: 'cycle-a',
        market_id: 'market-a',
        explanation: 'Entry alpha',
        tags: ['maker', 'alpha'],
      }),
      createDecisionLedgerEntry({
        entry_type: 'BET_SKIPPED',
        cycle_id: 'cycle-b',
        market_id: 'market-b',
        explanation: 'Entry beta',
        tags: ['risk'],
      }),
    ]

    expect(filterDecisionLedgerEntries(entries, { q: 'alpha' })).toHaveLength(1)
    expect(filterDecisionLedgerEntries(entries, { tag: 'risk' })).toHaveLength(1)
    expect(filterDecisionLedgerEntries(entries, { cycle_id: 'cycle-a' })).toHaveLength(1)
    expect(filterDecisionLedgerEntries(entries, { market_id: 'market-b' })).toHaveLength(1)
  })
})
