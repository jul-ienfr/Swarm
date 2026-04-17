import { afterEach, describe, expect, it } from 'vitest'
import {
  createPredictionMarketResearchMemoryRuntime,
  getPredictionMarketResearchMemoryRuntime,
  resetPredictionMarketResearchMemoryRuntimeForTests,
} from '@/lib/prediction-markets/memory/runtime'

describe('prediction markets research memory runtime', () => {
  const previousBackend = process.env.PREDICTION_MARKETS_RESEARCH_MEMORY_BACKEND
  const previousFile = process.env.PREDICTION_MARKETS_RESEARCH_MEMORY_FILE

  afterEach(() => {
    resetPredictionMarketResearchMemoryRuntimeForTests()
    if (previousBackend == null) {
      delete process.env.PREDICTION_MARKETS_RESEARCH_MEMORY_BACKEND
    } else {
      process.env.PREDICTION_MARKETS_RESEARCH_MEMORY_BACKEND = previousBackend
    }
    if (previousFile == null) {
      delete process.env.PREDICTION_MARKETS_RESEARCH_MEMORY_FILE
    } else {
      process.env.PREDICTION_MARKETS_RESEARCH_MEMORY_FILE = previousFile
    }
  })

  it('defaults to the in-memory provider', () => {
    delete process.env.PREDICTION_MARKETS_RESEARCH_MEMORY_BACKEND
    delete process.env.PREDICTION_MARKETS_RESEARCH_MEMORY_FILE

    const runtime = getPredictionMarketResearchMemoryRuntime()

    expect(runtime.provider_kind).toBe('memory')
    expect(runtime.adapter.adapter_kind).toBe('prediction-markets-research-memory')
  })

  it('supports an explicit file-backed provider', () => {
    process.env.PREDICTION_MARKETS_RESEARCH_MEMORY_BACKEND = 'file'
    process.env.PREDICTION_MARKETS_RESEARCH_MEMORY_FILE = '/tmp/prediction-markets-research-memory-runtime.test.json'

    const runtime = getPredictionMarketResearchMemoryRuntime()

    expect(runtime.provider_kind).toBe('file')
    expect(runtime.provider.scope).toBe('prediction-markets')
    expect(runtime.cross_simulation.namespace).toBe('cross-simulation')
  })

  it('can be created from an explicit seed snapshot without touching singleton state', () => {
    const runtime = createPredictionMarketResearchMemoryRuntime({
      provider_kind: 'memory',
      seed_snapshot: {
        schema_version: '1.0.0',
        provider_kind: 'memory',
        scope: 'prediction-markets',
        generated_at: '2026-04-10T00:00:00.000Z',
        entries: [
          {
            memory_id: 'seed-1',
            namespace: 'research',
            kind: 'seed',
            subject_id: 'sim-1',
            content: { summary: 'seeded memory' },
            tags: ['seed'],
            source_ref: 'seed-source',
            created_at: '2026-04-09T00:00:00.000Z',
            updated_at: '2026-04-10T00:00:00.000Z',
            metadata: { simulation_id: 'sim-1', importance: 0.9 },
          },
        ],
      },
    })

    expect(runtime.provider.list({ namespace: 'research' })).toHaveLength(1)
    expect(runtime.adapter.recallRanked({ namespace: 'research' })[0].memory_id).toBe('seed-1')
  })
})
