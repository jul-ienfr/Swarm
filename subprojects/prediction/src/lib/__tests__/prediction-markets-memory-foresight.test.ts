import { describe, expect, it } from 'vitest'
import { PredictionMarketInMemoryProvider } from '@/lib/prediction-markets/memory/provider'
import { PredictionMarketCrossSimulationMemoryStore } from '@/lib/prediction-markets/memory/cross-simulation'
import {
  summarizeForesightValidation,
  validateForesightForecast,
} from '@/lib/prediction-markets/memory/foresight'

describe('prediction markets memory foresight primitives', () => {
  it('scores exact and partial forecast matches', () => {
    const exact = validateForesightForecast(
      {
        forecast_id: 'forecast-1',
        simulation_id: 'sim-1',
        subject_id: 'market-1',
        expected_outcome: 'Polymarket settles YES',
        confidence: 0.9,
        generated_at: '2026-04-09T10:00:00.000Z',
      },
      {
        forecast_id: 'forecast-1',
        simulation_id: 'sim-1',
        subject_id: 'market-1',
        actual_outcome: 'Polymarket settles YES',
        resolved_at: '2026-04-09T12:00:00.000Z',
      },
      { now: '2026-04-10T00:00:00.000Z' },
    )

    const partial = validateForesightForecast(
      {
        forecast_id: 'forecast-2',
        simulation_id: 'sim-1',
        subject_id: 'market-2',
        expected_outcome: 'Market resolves at a premium',
        confidence: 0.4,
      },
      {
        simulation_id: 'sim-1',
        subject_id: 'market-2',
        actual_outcome: 'Market resolves with a premium',
      },
    )

    expect(exact.status).toBe('matched')
    expect(exact.exact_match).toBe(true)
    expect(exact.score).toBe(1)

    expect(partial.status === 'partial' || partial.status === 'matched').toBe(true)
    expect(partial.lexical_overlap).toBeGreaterThan(0)
    expect(partial.confidence_error).toBeGreaterThanOrEqual(0)

    const summary = summarizeForesightValidation([exact, partial])
    expect(summary.validations).toBe(2)
    expect(summary.matched).toBeGreaterThanOrEqual(1)
    expect(summary.average_score).toBeGreaterThan(0)
  })

  it('stores cross-simulation memories and validations with simulation summaries', () => {
    const provider = new PredictionMarketInMemoryProvider()
    const store = new PredictionMarketCrossSimulationMemoryStore(provider)

    store.registerSimulation({
      simulation_id: 'sim-42',
      metadata: { run_label: 'shadow-1', agent_count: 6 },
    })

    store.rememberObservation({
      simulation_id: 'sim-42',
      subject_id: 'market-42',
      content: { summary: 'spread widens before trigger' },
      topic: 'spread',
      agent_id: 'agent-a',
      metadata: { importance: 0.72 },
      created_at: '2026-04-09T09:00:00.000Z',
    })

    const validation = validateForesightForecast(
      {
        forecast_id: 'forecast-42',
        simulation_id: 'sim-42',
        subject_id: 'market-42',
        expected_outcome: 'spread widens before trigger',
        confidence: 0.8,
      },
      {
        simulation_id: 'sim-42',
        subject_id: 'market-42',
        actual_outcome: 'spread widens before trigger',
      },
    )

    store.rememberValidation({
      simulation_id: 'sim-42',
      content: validation,
      validation,
    })

    const summary = store.getSimulationSummary('sim-42')
    expect(summary.simulation_id).toBe('sim-42')
    expect(summary.memory_count).toBeGreaterThanOrEqual(2)
    expect(summary.top_memories[0].score).toBeGreaterThanOrEqual(summary.top_memories[summary.top_memories.length - 1]?.score ?? 0)
    expect(summary.topic_distribution.spread).toBeGreaterThan(0)
    expect(summary.validation_summary.validations).toBe(1)
    expect(summary.validation_summary.matched).toBe(1)

    const recall = store.recall('sim-42', { kind: 'cross_sim_memory' })
    expect(recall).toHaveLength(1)
    expect(recall[0].metadata).toMatchObject({ simulation_id: 'sim-42' })
  })
})
