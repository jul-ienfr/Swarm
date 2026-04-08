import type { CrossVenueEvaluation } from '@/lib/prediction-markets/cross-venue'
import type { ExecutableEdge } from '@/lib/prediction-markets/schemas'
import type { MicrostructureLabSummary } from '@/lib/prediction-markets/microstructure-lab'
import type {
  PredictionMarketVenueSourceOfTruth,
  PredictionMarketVenueStrategy,
} from '@/lib/prediction-markets/venue-strategy'

export type PredictionMarketPreflightSummaryBase = {
  summary: string
}

export type PredictionMarketPreflightPenaltySummary = {
  capital_fragmentation_penalty_bps: number | null
  transfer_latency_penalty_bps: number | null
  low_confidence_penalty_bps: number | null
  stale_edge_penalty_bps: number | null
  microstructure_deterioration_bps: number | null
  microstructure_execution_quality_score: number | null
}

export type PredictionMarketStaleEdgeStatus = {
  state: 'fresh' | 'stale' | 'expired' | 'unknown'
  expired: boolean | null
  source: 'executable_edge' | 'cross_venue' | 'microstructure' | 'unknown'
  reasons: string[]
}

export type PredictionMarketPreflightSummaryEnrichment<TSummary extends PredictionMarketPreflightSummaryBase> =
  TSummary & {
    source_of_truth: PredictionMarketVenueSourceOfTruth
    execution_eligible: boolean
    stale_edge_status: PredictionMarketStaleEdgeStatus
    penalties: PredictionMarketPreflightPenaltySummary
  }

type EdgeLike = Pick<
  ExecutableEdge,
  'notes' | 'executable' | 'executable_edge_bps' | 'gross_spread_bps' | 'fee_bps' | 'slippage_bps' | 'hedge_risk_bps'
>

type CrossVenueLike = Pick<CrossVenueEvaluation, 'executable_edge' | 'arbitrage_candidate'>

type MicrostructureSummaryLike = Pick<
  MicrostructureLabSummary,
  'recommended_mode' | 'worst_case_severity' | 'executable_deterioration_bps' | 'execution_quality_score'
>

export type PredictionMarketPreflightSummaryEnrichmentInput = {
  venue_strategy: Pick<PredictionMarketVenueStrategy, 'source_of_truth' | 'execution_eligible'>
  executable_edge?: EdgeLike | null
  cross_venue?: CrossVenueLike | null
  microstructure_summary?: MicrostructureSummaryLike | null
}

function parseBooleanNote(notes: readonly string[], prefix: string): boolean | null {
  const value = notes.find((note) => note.startsWith(prefix))
  if (!value) return null

  const parsed = value.slice(prefix.length).trim().toLowerCase()
  if (parsed === 'true') return true
  if (parsed === 'false') return false
  return null
}

function parseNumericNote(notes: readonly string[], prefix: string): number | null {
  const value = notes.find((note) => note.startsWith(prefix))
  if (!value) return null

  const parsed = Number.parseFloat(value.slice(prefix.length))
  return Number.isFinite(parsed) ? parsed : null
}

function unique(values: readonly string[]): string[] {
  return [...new Set(values.filter((value) => value.trim().length > 0))]
}

function pickExecutableEdge(
  input: PredictionMarketPreflightSummaryEnrichmentInput,
): { edge: EdgeLike | null; source: PredictionMarketStaleEdgeStatus['source'] } {
  if (input.executable_edge) return { edge: input.executable_edge, source: 'executable_edge' }
  if (input.cross_venue?.executable_edge) return { edge: input.cross_venue.executable_edge, source: 'cross_venue' }
  if (input.cross_venue?.arbitrage_candidate?.executable_edge) {
    return { edge: input.cross_venue.arbitrage_candidate.executable_edge, source: 'cross_venue' }
  }

  return { edge: null, source: 'unknown' }
}

function buildPenaltySummary(
  edge: EdgeLike | null,
  microstructureSummary: MicrostructureSummaryLike | null | undefined,
): PredictionMarketPreflightPenaltySummary {
  const notes = edge?.notes ?? []
  return {
    capital_fragmentation_penalty_bps: parseNumericNote(notes, 'capital_fragmentation_penalty_bps:'),
    transfer_latency_penalty_bps: parseNumericNote(notes, 'transfer_latency_penalty_bps:'),
    low_confidence_penalty_bps: parseNumericNote(notes, 'low_confidence_penalty_bps:'),
    stale_edge_penalty_bps: parseNumericNote(notes, 'stale_edge_penalty_bps:'),
    microstructure_deterioration_bps: microstructureSummary?.executable_deterioration_bps ?? null,
    microstructure_execution_quality_score: microstructureSummary?.execution_quality_score ?? null,
  }
}

function buildStaleEdgeStatus(
  edge: EdgeLike | null,
  source: PredictionMarketStaleEdgeStatus['source'],
  microstructureSummary: MicrostructureSummaryLike | null | undefined,
): PredictionMarketStaleEdgeStatus {
  if (!edge) {
    return {
      state: 'unknown',
      expired: null,
      source,
      reasons: [],
    }
  }

  const expired = parseBooleanNote(edge.notes, 'stale_edge_expired:')
  const stalePenalty = parseNumericNote(edge.notes, 'stale_edge_penalty_bps:')
  const staleReasons = unique([
    expired != null ? `stale_edge_expired:${expired}` : null,
    stalePenalty != null ? `stale_edge_penalty_bps:${stalePenalty}` : null,
    microstructureSummary?.recommended_mode === 'wait'
      ? `microstructure:${microstructureSummary.recommended_mode}:${microstructureSummary.worst_case_severity}`
      : null,
  ].filter((value): value is string => typeof value === 'string'))

  if (expired === true) {
    return {
      state: 'expired',
      expired,
      source,
      reasons: staleReasons,
    }
  }

  if ((stalePenalty ?? 0) > 0 || microstructureSummary?.recommended_mode === 'wait') {
    return {
      state: 'stale',
      expired,
      source: microstructureSummary?.recommended_mode === 'wait' ? 'microstructure' : source,
      reasons: staleReasons,
    }
  }

  return {
    state: 'fresh',
    expired,
    source,
    reasons: staleReasons,
  }
}

export function enrichPredictionMarketPreflightSummary<TSummary extends PredictionMarketPreflightSummaryBase>(
  preflightSummary: TSummary,
  input: PredictionMarketPreflightSummaryEnrichmentInput,
): PredictionMarketPreflightSummaryEnrichment<TSummary> {
  const pickedEdge = pickExecutableEdge(input)
  const staleEdgeStatus = buildStaleEdgeStatus(pickedEdge.edge, pickedEdge.source, input.microstructure_summary)

  return {
    ...preflightSummary,
    source_of_truth: input.venue_strategy.source_of_truth,
    execution_eligible: input.venue_strategy.execution_eligible,
    stale_edge_status: staleEdgeStatus,
    penalties: buildPenaltySummary(pickedEdge.edge, input.microstructure_summary),
  }
}
