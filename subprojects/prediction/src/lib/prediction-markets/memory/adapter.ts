import type { PredictionMarketVenue } from '@/lib/prediction-markets/schemas'
import type { PredictionMarketResearchPipelineTrace } from '@/lib/prediction-markets/research-pipeline-trace'
import {
  PredictionMarketCrossSimulationMemoryStore,
  type PredictionMarketCrossSimulationMemoryInput,
  type PredictionMarketCrossSimulationRegisterInput,
  type PredictionMarketCrossSimulationSummary,
} from '@/lib/prediction-markets/memory/cross-simulation'
import {
  validateForesightForecast,
  type PredictionMarketForesightForecast,
  type PredictionMarketForesightOutcome,
  type PredictionMarketForesightValidationOptions,
  type PredictionMarketForesightValidationResult,
} from '@/lib/prediction-markets/memory/foresight'
import {
  rankMemoryEntries,
  scoreMemoryEntry,
  type PredictionMarketScoredMemoryEntry,
  type PredictionMarketMemoryScoreOptions,
} from '@/lib/prediction-markets/memory/scoring'
import {
  type PredictionMarketMemoryEntry,
  type PredictionMarketMemoryFilter,
  type PredictionMarketMemoryProvider,
  type PredictionMarketMemorySnapshot,
} from '@/lib/prediction-markets/memory/provider'

export type PredictionMarketMemoryRememberInput = {
  namespace?: string | null
  kind: string
  subject_id: string
  content: unknown
  tags?: readonly string[] | null
  source_ref?: string | null
  metadata?: Record<string, unknown> | null
  created_at?: string | null
  memory_id?: string | null
}

export type PredictionMarketResearchMemoryTraceInput = {
  trace_id: string
  pipeline_id: string
  venue: PredictionMarketVenue
  market_id: string
  summary: string
  generated_at: string
  trace: PredictionMarketResearchPipelineTrace | Record<string, unknown>
  tags?: readonly string[] | null
  metadata?: Record<string, unknown> | null
}

export type PredictionMarketResearchMemoryForesightInput = PredictionMarketForesightForecast

export type PredictionMarketResearchMemoryOutcomeInput = PredictionMarketForesightOutcome

export type PredictionMarketResearchMemoryCrossSimulationInput = PredictionMarketCrossSimulationMemoryInput

export type PredictionMarketResearchMemoryCrossSimulationRegisterInput = PredictionMarketCrossSimulationRegisterInput

export type PredictionMarketResearchMemoryCrossSimulationSummary = PredictionMarketCrossSimulationSummary

export class PredictionMarketResearchMemoryAdapter {
  readonly adapter_kind = 'prediction-markets-research-memory' as const
  readonly cross_simulation: PredictionMarketCrossSimulationMemoryStore

  constructor(readonly provider: PredictionMarketMemoryProvider) {
    this.cross_simulation = new PredictionMarketCrossSimulationMemoryStore(provider)
  }

  remember(input: PredictionMarketMemoryRememberInput): PredictionMarketMemoryEntry {
    return this.provider.upsert({
      memory_id: input.memory_id ?? null,
      namespace: input.namespace?.trim() || 'research',
      kind: input.kind.trim(),
      subject_id: input.subject_id.trim(),
      content: input.content,
      tags: input.tags ?? [],
      source_ref: input.source_ref ?? null,
      metadata: input.metadata ?? {},
      created_at: input.created_at ?? null,
    })
  }

  rememberResearchTrace(input: PredictionMarketResearchMemoryTraceInput): PredictionMarketMemoryEntry {
    return this.remember({
      namespace: 'research',
      kind: 'research_trace',
      subject_id: `${input.venue}:${input.market_id}:${input.pipeline_id}`,
      content: {
        trace_id: input.trace_id,
        pipeline_id: input.pipeline_id,
        venue: input.venue,
        market_id: input.market_id,
        summary: input.summary,
        trace: input.trace,
      },
      tags: [
        'research',
        'trace',
        input.venue,
        input.market_id,
        input.pipeline_id,
        ...(input.tags ?? []),
      ],
      source_ref: input.trace_id,
      metadata: {
        venue: input.venue,
        market_id: input.market_id,
        pipeline_id: input.pipeline_id,
        generated_at: input.generated_at,
        ...input.metadata,
      },
      created_at: input.generated_at,
    })
  }

  recall(filter?: PredictionMarketMemoryFilter): PredictionMarketMemoryEntry[] {
    return this.provider.list(filter)
  }

  search(filter: PredictionMarketMemoryFilter & { text?: string | null }): PredictionMarketMemoryEntry[] {
    return this.provider.list(filter)
  }

  recallRanked(
    filter?: PredictionMarketMemoryFilter,
    options?: PredictionMarketMemoryScoreOptions,
  ): PredictionMarketScoredMemoryEntry[] {
    return rankMemoryEntries(this.provider.list(filter), options)
  }

  registerSimulation(input: PredictionMarketCrossSimulationRegisterInput): PredictionMarketScoredMemoryEntry {
    return this.cross_simulation.registerSimulation(input)
  }

  rememberCrossSimulationMemory(input: PredictionMarketCrossSimulationMemoryInput): PredictionMarketScoredMemoryEntry {
    return this.cross_simulation.remember(input)
  }

  rememberCrossSimulationObservation(
    input: Omit<PredictionMarketCrossSimulationMemoryInput, 'kind'> & {
      agent_id?: string | null
      topic?: string | null
    },
  ): PredictionMarketScoredMemoryEntry {
    return this.cross_simulation.rememberObservation(input)
  }

  rememberForesightForecast(input: PredictionMarketForesightForecast): PredictionMarketScoredMemoryEntry {
    return scoreMemoryEntry(this.remember({
      namespace: 'research',
      kind: 'foresight_forecast',
      subject_id: input.subject_id,
      content: input,
      tags: ['foresight', 'forecast', input.simulation_id, input.subject_id],
      source_ref: input.forecast_id,
      metadata: {
        simulation_id: input.simulation_id,
        forecast_id: input.forecast_id,
        confidence: input.confidence ?? null,
        generated_at: input.generated_at ?? null,
        ...input.metadata,
      },
      created_at: input.generated_at ?? null,
    }))
  }

  rememberForesightValidation(
    forecast: PredictionMarketForesightForecast,
    outcome: PredictionMarketForesightOutcome,
    options?: PredictionMarketForesightValidationOptions,
  ): PredictionMarketScoredMemoryEntry {
    const validation = validateForesightForecast(forecast, outcome, options)
    return this.cross_simulation.rememberValidation({
      simulation_id: validation.simulation_id,
      subject_id: validation.subject_id,
      content: validation,
      validation,
      tags: ['foresight', 'validation', validation.status],
      source_ref: validation.forecast_id,
      metadata: {
        forecast_id: validation.forecast_id,
        status: validation.status,
        exact_match: validation.exact_match,
        score: validation.score,
        confidence_error: validation.confidence_error,
      },
      created_at: validation.validated_at,
    })
  }

  summarizeSimulation(simulation_id: string): PredictionMarketCrossSimulationSummary {
    return this.cross_simulation.getSimulationSummary(simulation_id)
  }

  forget(memory_id: string): boolean {
    return this.provider.delete(memory_id)
  }

  clear(filter?: PredictionMarketMemoryFilter): number {
    return this.provider.clear(filter)
  }

  snapshot(): PredictionMarketMemorySnapshot {
    return this.provider.snapshot()
  }
}
