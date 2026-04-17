import type { PredictionMarketMemoryFilter, PredictionMarketMemoryProvider, PredictionMarketMemorySnapshot } from '@/lib/prediction-markets/memory/provider'
import { rankMemoryEntries, type PredictionMarketScoredMemoryEntry } from '@/lib/prediction-markets/memory/scoring'
import {
  summarizeForesightValidation,
  type PredictionMarketForesightValidationResult,
} from '@/lib/prediction-markets/memory/foresight'

export type PredictionMarketCrossSimulationMemoryKind =
  | 'simulation_run'
  | 'cross_sim_memory'
  | 'foresight_forecast'
  | 'foresight_validation'

export type PredictionMarketCrossSimulationMemoryInput = {
  simulation_id: string
  kind?: PredictionMarketCrossSimulationMemoryKind | string | null
  subject_id?: string | null
  content: unknown
  tags?: readonly string[] | null
  source_ref?: string | null
  metadata?: Record<string, unknown> | null
  created_at?: string | null
  memory_id?: string | null
}

export type PredictionMarketCrossSimulationRegisterInput = {
  simulation_id: string
  metadata?: Record<string, unknown> | null
  tags?: readonly string[] | null
  created_at?: string | null
  source_ref?: string | null
}

export type PredictionMarketCrossSimulationSummary = {
  simulation_id: string
  simulation: PredictionMarketScoredMemoryEntry | null
  memory_count: number
  top_memories: PredictionMarketScoredMemoryEntry[]
  topic_distribution: Record<string, number>
  validation_summary: ReturnType<typeof summarizeForesightValidation>
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const value of values) {
    const normalized = String(value ?? '').trim()
    if (!normalized || seen.has(normalized)) continue
    seen.add(normalized)
    out.push(normalized)
  }
  return out
}

function mergeMetadata(...values: Array<Record<string, unknown> | null | undefined>): Record<string, unknown> {
  return values.reduce<Record<string, unknown>>((acc, value) => {
    if (!value) return acc
    return { ...acc, ...value }
  }, {})
}

function topicDistribution(entries: readonly PredictionMarketScoredMemoryEntry[]): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const entry of entries) {
    for (const tag of entry.tags ?? []) {
      const normalized = String(tag ?? '').trim().toLowerCase()
      if (!normalized) continue
      counts[normalized] = (counts[normalized] ?? 0) + 1
    }
  }
  return counts
}

function findValidationResults(entries: readonly PredictionMarketScoredMemoryEntry[]): PredictionMarketForesightValidationResult[] {
  const results: PredictionMarketForesightValidationResult[] = []
  for (const entry of entries) {
    if (entry.kind !== 'foresight_validation') continue
    if (entry.content == null || typeof entry.content !== 'object' || Array.isArray(entry.content)) continue
    const content = entry.content as Partial<PredictionMarketForesightValidationResult>
    if (typeof content.forecast_id !== 'string' || typeof content.simulation_id !== 'string') continue
    if (typeof content.subject_id !== 'string' || typeof content.expected_outcome !== 'string') continue
    if (typeof content.actual_outcome !== 'string') continue
    results.push({
      forecast_id: content.forecast_id,
      simulation_id: content.simulation_id,
      subject_id: content.subject_id,
      expected_outcome: content.expected_outcome,
      actual_outcome: content.actual_outcome,
      confidence: typeof content.confidence === 'number' ? content.confidence : 0,
      lexical_overlap: typeof content.lexical_overlap === 'number' ? content.lexical_overlap : 0,
      exact_match: Boolean(content.exact_match),
      confidence_error: typeof content.confidence_error === 'number' ? content.confidence_error : 0,
      score: typeof content.score === 'number' ? content.score : 0,
      status: content.status === 'partial' || content.status === 'mismatched' ? content.status : 'matched',
      validated_at: typeof content.validated_at === 'string' ? content.validated_at : new Date().toISOString(),
      resolved_at: typeof content.resolved_at === 'string' ? content.resolved_at : null,
      notes: Array.isArray(content.notes) ? content.notes.map((note) => String(note)) : [],
      metadata: content.metadata && typeof content.metadata === 'object' && !Array.isArray(content.metadata)
        ? content.metadata as Record<string, unknown>
        : {},
    })
  }
  return results
}

export class PredictionMarketCrossSimulationMemoryStore {
  constructor(
    readonly provider: PredictionMarketMemoryProvider,
    readonly namespace = 'cross-simulation',
  ) {}

  registerSimulation(input: PredictionMarketCrossSimulationRegisterInput): PredictionMarketScoredMemoryEntry {
    const simulation_id = input.simulation_id.trim()
    return this.remember({
      simulation_id,
      kind: 'simulation_run',
      subject_id: simulation_id,
      content: {
        simulation_id,
        kind: 'simulation_run',
        metadata: input.metadata ?? {},
      },
      tags: uniqueStrings(['simulation', 'cross-simulation', ...(input.tags ?? [])]),
      source_ref: input.source_ref ?? simulation_id,
      metadata: mergeMetadata(
        { simulation_id, simulation_kind: 'simulation_run' },
        input.metadata,
      ),
      created_at: input.created_at ?? null,
    })
  }

  remember(input: PredictionMarketCrossSimulationMemoryInput): PredictionMarketScoredMemoryEntry {
    const simulation_id = input.simulation_id.trim()
    const kind = String(input.kind ?? 'cross_sim_memory').trim() || 'cross_sim_memory'
    const subject_id = String(input.subject_id ?? simulation_id).trim() || simulation_id

    return rankMemoryEntries([
      this.provider.upsert({
        memory_id: input.memory_id ?? null,
        namespace: this.namespace,
        kind,
        subject_id,
        content: input.content,
        tags: uniqueStrings([
          'cross-simulation',
          simulation_id,
          kind,
          ...(input.tags ?? []),
        ]),
        source_ref: input.source_ref ?? null,
        metadata: mergeMetadata(
          {
            simulation_id,
            simulation_kind: kind,
            subject_id,
          },
          input.metadata,
        ),
        created_at: input.created_at ?? null,
      }),
    ])[0]
  }

  rememberObservation(input: Omit<PredictionMarketCrossSimulationMemoryInput, 'kind'> & {
    agent_id?: string | null
    topic?: string | null
  }): PredictionMarketScoredMemoryEntry {
    const tags = uniqueStrings([
      'observation',
      input.topic ?? null,
      input.agent_id ?? null,
      ...(input.tags ?? []),
    ])
    return this.remember({
      ...input,
      kind: 'cross_sim_memory',
      tags,
      metadata: mergeMetadata(
        input.metadata,
        {
          agent_id: input.agent_id ?? null,
          topic: input.topic ?? null,
        },
      ),
      subject_id: input.subject_id ?? input.agent_id ?? input.simulation_id,
    })
  }

  rememberForecast(input: Omit<PredictionMarketCrossSimulationMemoryInput, 'kind'> & {
    forecast_id: string
  }): PredictionMarketScoredMemoryEntry {
    return this.remember({
      ...input,
      kind: 'foresight_forecast',
      subject_id: input.subject_id ?? input.forecast_id,
      tags: uniqueStrings(['foresight', 'forecast', ...(input.tags ?? [])]),
      metadata: mergeMetadata(input.metadata, {
        forecast_id: input.forecast_id,
      }),
    })
  }

  rememberValidation(input: Omit<PredictionMarketCrossSimulationMemoryInput, 'kind'> & {
    validation: PredictionMarketForesightValidationResult
  }): PredictionMarketScoredMemoryEntry {
    return this.remember({
      simulation_id: input.simulation_id,
      kind: 'foresight_validation',
      subject_id: input.subject_id ?? input.validation.subject_id,
      content: input.validation,
      tags: uniqueStrings(['foresight', 'validation', ...(input.tags ?? [])]),
      source_ref: input.source_ref ?? input.validation.forecast_id,
      metadata: mergeMetadata(input.metadata, {
        forecast_id: input.validation.forecast_id,
        validation_status: input.validation.status,
      }),
      created_at: input.created_at ?? input.validation.validated_at,
    })
  }

  recall(simulation_id: string, filter?: PredictionMarketMemoryFilter): PredictionMarketScoredMemoryEntry[] {
    return rankMemoryEntries(
      this.provider.list({
        ...filter,
        namespace: this.namespace,
        metadata: {
          simulation_id,
          ...(filter?.metadata ?? {}),
        },
      }),
    )
  }

  listSimulations(limit = 50): PredictionMarketScoredMemoryEntry[] {
    return rankMemoryEntries(
      this.provider.list({
        namespace: this.namespace,
        kind: 'simulation_run',
        limit,
      }),
    )
  }

  getSimulationSummary(simulation_id: string): PredictionMarketCrossSimulationSummary {
    const memories = this.recall(simulation_id)
    const simulation = memories.find((entry) => entry.kind === 'simulation_run') ?? null
    const validations = findValidationResults(memories)

    return {
      simulation_id,
      simulation,
      memory_count: memories.length,
      top_memories: memories.slice(0, 10),
      topic_distribution: topicDistribution(memories),
      validation_summary: summarizeForesightValidation(validations),
    }
  }

  snapshot(): PredictionMarketMemorySnapshot {
    return this.provider.snapshot()
  }
}
