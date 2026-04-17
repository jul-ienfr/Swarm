import { mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { rankMemoryEntries } from '@/lib/prediction-markets/memory/scoring'
import {
  PredictionMarketFileProvider,
  PredictionMarketInMemoryProvider,
} from '@/lib/prediction-markets/memory/provider'

describe('prediction markets memory provider', () => {
  it('upserts, searches, and clears entries in memory', () => {
    const provider = new PredictionMarketInMemoryProvider()

    const first = provider.upsert({
      namespace: 'research',
      kind: 'trace',
      subject_id: 'polymarket:mkt-1:baseline-v0',
      content: {
        summary: 'Market-only baseline anchored at 0.51',
        notes: ['baseline', 'abstention'],
      },
      tags: ['research', 'baseline'],
      source_ref: 'trace-1',
      metadata: { venue: 'polymarket' },
      created_at: '2026-04-09T00:00:00.000Z',
    })

    const second = provider.upsert({
      namespace: 'research',
      kind: 'trace',
      subject_id: 'polymarket:mkt-1:baseline-v0',
      content: {
        summary: 'Market-only baseline updated at 0.52',
      },
      tags: ['research', 'baseline', 'updated'],
      source_ref: 'trace-1',
      metadata: { venue: 'polymarket', status: 'updated' },
    })

    expect(second.memory_id).toBe(first.memory_id)
    expect(second.updated_at >= first.updated_at).toBe(true)

    const recalled = provider.list({ namespace: 'research', text: 'baseline' })
    expect(recalled).toHaveLength(1)
    expect(recalled[0]).toMatchObject({
      memory_id: first.memory_id,
      kind: 'trace',
      subject_id: 'polymarket:mkt-1:baseline-v0',
    })
    expect(recalled[0].metadata).toMatchObject({ venue: 'polymarket', status: 'updated' })

    const snapshot = provider.snapshot()
    expect(snapshot.scope).toBe('prediction-markets')
    expect(snapshot.entries).toHaveLength(1)

    const cleared = provider.clear({ namespace: 'research', kind: 'trace' })
    expect(cleared).toBe(1)
    expect(provider.list()).toHaveLength(0)

    provider.restore(snapshot)
    expect(provider.list()).toHaveLength(1)
    expect(provider.get(first.memory_id)).toMatchObject({
      memory_id: first.memory_id,
      subject_id: 'polymarket:mkt-1:baseline-v0',
    })

    const filteredByMetadata = provider.list({
      namespace: 'research',
      metadata: { venue: 'polymarket', status: 'updated' },
    })
    expect(filteredByMetadata).toHaveLength(1)
  })

  it('persists and reloads entries from a file-backed provider', () => {
    const directory = mkdtempSync(join(tmpdir(), 'prediction-markets-memory-'))
    const filePath = join(directory, 'memory.json')

    const provider = new PredictionMarketFileProvider(filePath)
    const entry = provider.upsert({
      namespace: 'research',
      kind: 'benchmark',
      subject_id: 'polymarket:mkt-2:trace',
      content: { summary: 'Frozen market replay baseline' },
      tags: ['benchmark'],
      source_ref: 'benchmark-1',
      metadata: { venue: 'polymarket' },
    })

    expect(readFileSync(filePath, 'utf8')).toContain(entry.memory_id)

    const reloaded = new PredictionMarketFileProvider(filePath)
    expect(reloaded.get(entry.memory_id)).toMatchObject({
      memory_id: entry.memory_id,
      namespace: 'research',
      kind: 'benchmark',
      subject_id: 'polymarket:mkt-2:trace',
    })
    expect(reloaded.list({ text: 'replay baseline' })).toHaveLength(1)

    expect(reloaded.delete(entry.memory_id)).toBe(true)
    expect(reloaded.list()).toHaveLength(0)
  })

  it('ranks entries by importance and recency signals', () => {
    const scored = rankMemoryEntries([
      {
        memory_id: 'stale-low',
        namespace: 'research',
        kind: 'note',
        subject_id: 's-1',
        content: 'short note',
        tags: ['memory'],
        source_ref: null,
        created_at: '2026-03-01T00:00:00.000Z',
        updated_at: '2026-03-01T00:00:00.000Z',
        metadata: {},
      },
      {
        memory_id: 'fresh-high',
        namespace: 'research',
        kind: 'validation',
        subject_id: 's-2',
        content: {
          summary: 'validated forecast with evidence',
          evidence: ['source-a', 'source-b'],
        },
        tags: ['validation', 'foresight'],
        source_ref: 'src-1',
        created_at: '2026-04-09T00:00:00.000Z',
        updated_at: '2026-04-09T00:00:00.000Z',
        metadata: { importance: 0.95 },
      },
    ], {
      now: '2026-04-10T00:00:00.000Z',
      half_life_hours: 48,
    })

    expect(scored[0].memory_id).toBe('fresh-high')
    expect(scored[0].score).toBeGreaterThan(scored[1].score)
    expect(scored[0].score_breakdown.importance).toBeGreaterThan(scored[1].score_breakdown.importance)
  })
})
