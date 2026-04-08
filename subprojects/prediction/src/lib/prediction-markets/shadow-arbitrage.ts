import { type ExecutableEdge } from '@/lib/prediction-markets/schemas'
import { type MicrostructureLabSummary } from '@/lib/prediction-markets/microstructure-lab'

export type ShadowArbitrageFailureKind = 'one_leg_fill' | 'hedge_delay' | 'stale_edge'

export type ShadowArbitrageFailureCase = {
  kind: ShadowArbitrageFailureKind
  probability: number
  net_pnl_bps: number
  net_pnl_usd: number
  loss_vs_success_bps: number
  notes: string[]
}

export type ShadowArbitrageSimulationSummary = {
  base_executable_edge_bps: number
  microstructure_deterioration_bps: number
  shadow_drag_bps: number
  shadow_edge_bps: number
  base_size_usd: number
  recommended_size_usd: number
  hedge_success_probability: number
  hedge_success_expected: boolean
  estimated_net_pnl_bps: number
  estimated_net_pnl_usd: number
  worst_case_kind: ShadowArbitrageFailureKind
  failure_case_count: number
  scenario_overview: string[]
  notes: string[]
}

export type ShadowArbitrageSimulationReport = {
  read_only: true
  generated_at: string
  as_of_at: string
  executable_edge: ExecutableEdge
  microstructure_summary: MicrostructureLabSummary
  sizing: {
    requested_size_usd: number | null
    base_size_usd: number
    recommended_size_usd: number
    simulated_size_usd: number
    size_multiplier: number
  }
  failure_cases: ShadowArbitrageFailureCase[]
  summary: ShadowArbitrageSimulationSummary
}

export type ShadowArbitrageSimulationInput = {
  executable_edge: ExecutableEdge
  microstructure_summary: MicrostructureLabSummary
  size_usd?: number
  generated_at?: string
  as_of_at?: string
}

const FAILURE_CASE_ORDER: ShadowArbitrageFailureKind[] = ['one_leg_fill', 'hedge_delay', 'stale_edge']

const SEVERITY_DRAG_BPS: Record<MicrostructureLabSummary['worst_case_severity'], number> = {
  low: 2,
  medium: 6,
  high: 12,
  critical: 20,
}

const SEVERITY_PROBABILITY_PENALTY: Record<MicrostructureLabSummary['worst_case_severity'], number> = {
  low: 0.03,
  medium: 0.08,
  high: 0.16,
  critical: 0.28,
}

const MODE_PROBABILITY_PENALTY: Record<MicrostructureLabSummary['recommended_mode'], number> = {
  paper: 0.02,
  shadow: 0.07,
  wait: 0.18,
}

function nowIso(): string {
  return new Date().toISOString()
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function round(value: number): number {
  return Math.round(value)
}

function nonNegativeMs(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.round(value))
}

function parseIsoMs(iso: string | null | undefined): number | null {
  if (!iso) return null
  const parsed = Date.parse(iso)
  return Number.isFinite(parsed) ? parsed : null
}

function hasOverviewEntry(summary: MicrostructureLabSummary, kind: string): boolean {
  return summary.scenario_overview.some((entry) => entry.startsWith(`${kind}:`))
}

function extractScenarioMetric(
  summary: MicrostructureLabSummary,
  kind: string,
  key: 'hedge_delay' | 'book_age',
): number | null {
  const line = summary.scenario_overview.find((entry) => entry.startsWith(`${kind}:`))
  if (!line) return null

  const pattern = key === 'hedge_delay'
    ? /hedge_delay=(\d+)ms/
    : /book_age=(\d+)ms/
  const match = line.match(pattern)
  if (!match) return null

  const parsed = Number(match[1])
  return Number.isFinite(parsed) ? parsed : null
}

function severityModePenalty(summary: MicrostructureLabSummary): number {
  return SEVERITY_PROBABILITY_PENALTY[summary.worst_case_severity] + MODE_PROBABILITY_PENALTY[summary.recommended_mode]
}

function mapScenarioKindToFailureKind(
  kind: MicrostructureLabSummary['worst_case_kind'],
): ShadowArbitrageFailureKind {
  switch (kind) {
    case 'hedge_delay':
      return 'hedge_delay'
    case 'stale_book':
    case 'spread_collapse':
      return 'stale_edge'
    case 'partial_fill':
    case 'one_leg_fill':
    case 'cancel_replace':
    case 'queue_miss':
      return 'one_leg_fill'
  }
}

function sizeMultiplierFromSummary(summary: MicrostructureLabSummary): number {
  const qualityFactor = 0.4 + (0.6 * clamp(summary.execution_quality_score, 0, 1))
  const severityFactor = summary.worst_case_severity === 'low'
    ? 1
    : summary.worst_case_severity === 'medium'
      ? 0.85
      : summary.worst_case_severity === 'high'
        ? 0.65
        : 0.45
  return qualityFactor * severityFactor
}

function buildFailureWeights(input: {
  summary: MicrostructureLabSummary
  edgeAgeMs: number
  staleEdgeObserved: boolean
  hedgeDelayMs: number | null
  bookAgeMs: number | null
}): Record<ShadowArbitrageFailureKind, number> {
  const dominantFailureKind = mapScenarioKindToFailureKind(input.summary.worst_case_kind)
  const oneLegFillWeight = 1
    + (hasOverviewEntry(input.summary, 'one_leg_fill') ? 0.35 : 0)
    + (input.summary.worst_case_kind === 'partial_fill' ? 0.2 : 0)
    + (input.summary.worst_case_kind === 'cancel_replace' ? 0.15 : 0)
    + (input.summary.worst_case_kind === 'queue_miss' ? 0.2 : 0)
    + (dominantFailureKind === 'one_leg_fill' ? 0.45 : 0)
    + (input.summary.worst_case_severity === 'critical' ? 0.1 : 0)

  const hedgeDelayWeight = 1
    + (hasOverviewEntry(input.summary, 'hedge_delay') ? 0.35 : 0)
    + (dominantFailureKind === 'hedge_delay' ? 0.45 : 0)
    + (input.hedgeDelayMs != null ? clamp(input.hedgeDelayMs / 4_000, 0, 0.4) : 0)
    + (input.summary.recommended_mode === 'wait' ? 0.15 : 0)

  const staleEdgeWeight = 1
    + (hasOverviewEntry(input.summary, 'stale_book') ? 0.35 : 0)
    + (input.summary.worst_case_kind === 'spread_collapse' ? 0.35 : 0)
    + (dominantFailureKind === 'stale_edge' ? 0.6 : 0)
    + (input.staleEdgeObserved ? 0.55 : 0)
    + (input.bookAgeMs != null ? clamp(input.bookAgeMs / 30_000, 0, 0.35) : 0)
    + clamp(input.edgeAgeMs / 120_000, 0, 0.25)

  return {
    one_leg_fill: oneLegFillWeight,
    hedge_delay: hedgeDelayWeight,
    stale_edge: staleEdgeWeight,
  }
}

function buildFailureProbabilityMap(input: {
  summary: MicrostructureLabSummary
  edgeAgeMs: number
  staleEdgeObserved: boolean
  hedgeDelayMs: number | null
  bookAgeMs: number | null
  hedgeSuccessProbability: number
}): Record<ShadowArbitrageFailureKind, number> {
  const failMass = clamp(1 - input.hedgeSuccessProbability, 0, 1)
  if (failMass <= 0) {
    return {
      one_leg_fill: 0,
      hedge_delay: 0,
      stale_edge: 0,
    }
  }

  const weights = buildFailureWeights(input)
  const totalWeight = weights.one_leg_fill + weights.hedge_delay + weights.stale_edge
  if (totalWeight <= 0) {
    return {
      one_leg_fill: 0,
      hedge_delay: 0,
      stale_edge: failMass,
    }
  }

  return {
    one_leg_fill: failMass * (weights.one_leg_fill / totalWeight),
    hedge_delay: failMass * (weights.hedge_delay / totalWeight),
    stale_edge: failMass * (weights.stale_edge / totalWeight),
  }
}

function buildShadowEdgeBps(input: {
  baseExecutableEdgeBps: number
  summary: MicrostructureLabSummary
  edgeAgeMs: number
  staleEdgeObserved: boolean
}): number {
  const staleEdgePenaltyBps = input.staleEdgeObserved
    ? 12 + round(input.summary.executable_deterioration_bps * 0.25)
    : input.summary.worst_case_kind === 'stale_book'
      ? 8 + round(input.summary.executable_deterioration_bps * 0.15)
      : 0
  const ageDragBps = clamp(round(input.edgeAgeMs / 1_000), 0, 12)
  const shadowDragBps = round(
    (input.summary.executable_deterioration_bps * 0.5) +
      SEVERITY_DRAG_BPS[input.summary.worst_case_severity] +
      ageDragBps +
      staleEdgePenaltyBps,
  )

  return Math.max(0, input.baseExecutableEdgeBps - shadowDragBps)
}

function buildHedgeSuccessProbability(input: {
  summary: MicrostructureLabSummary
  edgeAgeMs: number
  staleEdgeObserved: boolean
}): number {
  const quality = clamp(input.summary.execution_quality_score, 0, 1)
  const agePenalty = clamp(input.edgeAgeMs / 60_000, 0, 0.15)
  const stalePenalty = input.staleEdgeObserved
    ? 0.12
    : input.summary.worst_case_kind === 'stale_book'
      ? 0.05
      : 0

  return clamp(
    0.3 + (quality * 0.65) - severityModePenalty(input.summary) - agePenalty - stalePenalty,
    0.05,
    0.98,
  )
}

function buildCasePnlBps(input: {
  kind: ShadowArbitrageFailureKind
  baseExecutableEdgeBps: number
  shadowEdgeBps: number
  summary: MicrostructureLabSummary
  edgeAgeMs: number
  staleEdgeObserved: boolean
  hedgeDelayMs: number | null
}): number {
  const quality = clamp(input.summary.execution_quality_score, 0, 1)

  if (input.kind === 'stale_edge') {
    return -round(
      (input.baseExecutableEdgeBps * 0.25) +
        (input.summary.executable_deterioration_bps * 0.5) +
        14 +
        (input.staleEdgeObserved ? 18 : 0) +
        clamp(input.edgeAgeMs / 2_000, 0, 20),
    )
  }

  if (input.kind === 'one_leg_fill') {
    return input.shadowEdgeBps - round(
      (input.baseExecutableEdgeBps * 0.35) +
        (input.summary.executable_deterioration_bps * 0.25) +
        8 +
        ((1 - quality) * 18),
    )
  }

  return input.shadowEdgeBps - round(
    (input.baseExecutableEdgeBps * 0.25) +
      (input.summary.executable_deterioration_bps * 0.35) +
      10 +
      clamp((input.hedgeDelayMs ?? 0) / 1_000, 0, 14),
  )
}

function buildScenarioOverview(summary: MicrostructureLabSummary): string[] {
  return summary.scenario_overview.map((entry) => entry.trim()).filter(Boolean)
}

function buildOperationalNotes(summary: MicrostructureLabSummary): string[] {
  const notes: string[] = []
  if (summary.recommended_mode === 'wait') {
    notes.push('Microstructure lab recommends wait, so shadow sizing stays informational and conservative.')
  }
  if (summary.worst_case_kind === 'spread_collapse') {
    notes.push('Spread collapse is folded into stale_edge risk because the quoted edge can vanish before the hedge locks.')
  }
  if (
    summary.worst_case_kind === 'partial_fill' ||
    summary.worst_case_kind === 'cancel_replace' ||
    summary.worst_case_kind === 'queue_miss'
  ) {
    notes.push(`Worst-case microstructure ${summary.worst_case_kind} is folded into one_leg_fill risk to keep the shadow loss surface additive.`)
  }
  if (summary.worst_case_executable_edge_bps <= 0) {
    notes.push('Worst-case microstructure can fully erase the executable edge before the hedge completes.')
  }
  return notes
}

function resolveSimulatedSize(input: {
  requestedSizeUsd: number | null
  recommendedSizeUsd: number
}): {
  simulatedSizeUsd: number
  notes: string[]
} {
  if (input.requestedSizeUsd == null) {
    return {
      simulatedSizeUsd: input.recommendedSizeUsd,
      notes: [],
    }
  }

  const simulatedSizeUsd = Math.min(input.requestedSizeUsd, input.recommendedSizeUsd)
  return {
    simulatedSizeUsd,
    notes: simulatedSizeUsd < input.requestedSizeUsd
      ? [
        `Requested size of ${input.requestedSizeUsd} USD exceeds the conservative shadow recommendation of ${input.recommendedSizeUsd} USD, so PnL is simulated on ${simulatedSizeUsd} USD.`,
      ]
      : [],
  }
}

export function buildShadowArbitrageSimulation(
  input: ShadowArbitrageSimulationInput,
): ShadowArbitrageSimulationReport {
  const generatedAt = input.generated_at ?? nowIso()
  const asOfAt = input.as_of_at ?? generatedAt
  const baseExecutableEdgeBps = Math.max(0, round(input.executable_edge.executable_edge_bps))
  const edgeAgeMs = nonNegativeMs((parseIsoMs(asOfAt) ?? parseIsoMs(generatedAt) ?? Date.now()) - (parseIsoMs(input.executable_edge.evaluated_at) ?? parseIsoMs(asOfAt) ?? Date.now()))
  const staleEdgeObserved = input.executable_edge.notes.some((note) => note.startsWith('stale_edge_expired:true'))
  const summary = input.microstructure_summary
  const shadowEdgeBps = buildShadowEdgeBps({
    baseExecutableEdgeBps,
    summary,
    edgeAgeMs,
    staleEdgeObserved,
  })
  const hedgeSuccessProbability = buildHedgeSuccessProbability({
    summary,
    edgeAgeMs,
    staleEdgeObserved,
  })
  const hedgeDelayMs = extractScenarioMetric(summary, 'hedge_delay', 'hedge_delay')
  const bookAgeMs = extractScenarioMetric(summary, 'stale_book', 'book_age')
  const failureProbabilities = buildFailureProbabilityMap({
    summary,
    edgeAgeMs,
    staleEdgeObserved,
    hedgeDelayMs,
    bookAgeMs,
    hedgeSuccessProbability,
  })

  const baseSizeUsd = Math.max(100, Math.min(1_000, baseExecutableEdgeBps * 10))
  const sizeMultiplier = sizeMultiplierFromSummary(summary)
  const recommendedSizeUsd = Math.max(25, round(baseSizeUsd * sizeMultiplier))
  const requestedSizeUsd = input.size_usd != null ? Math.max(1, round(input.size_usd)) : null
  const simulatedSizing = resolveSimulatedSize({
    requestedSizeUsd,
    recommendedSizeUsd,
  })
  const simulatedSizeUsd = simulatedSizing.simulatedSizeUsd
  const failureCases: ShadowArbitrageFailureCase[] = FAILURE_CASE_ORDER.map((kind) => {
    const probability = failureProbabilities[kind]
    const netPnlBps = buildCasePnlBps({
      kind,
      baseExecutableEdgeBps,
      shadowEdgeBps,
      summary,
      edgeAgeMs,
      staleEdgeObserved,
      hedgeDelayMs,
    })
    const lossVsSuccessBps = shadowEdgeBps - netPnlBps
    const notes = (() => {
      if (kind === 'one_leg_fill') {
        return [
          'One leg fills before the hedge can complete.',
          'This is the clearest legging-risk failure mode in the shadow model.',
        ]
      }
      if (kind === 'hedge_delay') {
        return [
          'The hedge leg is delayed long enough to erode the edge.',
          'A tighter unhedged window or slower routing increases this loss case.',
        ]
      }
      return [
        'The edge is stale before the hedge can lock it in.',
        'This is the dominant read-only failure mode when freshness slips.',
      ]
    })()

    return {
      kind,
      probability,
      net_pnl_bps: netPnlBps,
      net_pnl_usd: Number(((netPnlBps * simulatedSizeUsd) / 10_000).toFixed(2)),
      loss_vs_success_bps: lossVsSuccessBps,
      notes,
    }
  })

  const estimatedNetPnlBps = round(
    (hedgeSuccessProbability * shadowEdgeBps) +
      failureCases.reduce((sum, failureCase) => sum + (failureCase.probability * failureCase.net_pnl_bps), 0),
  )
  const estimatedNetPnlUsd = Number(((estimatedNetPnlBps * simulatedSizeUsd) / 10_000).toFixed(2))
  const failureCaseRanking = [...failureCases].sort((left, right) => left.net_pnl_bps - right.net_pnl_bps)
  const worstCaseKind = failureCaseRanking[0]?.kind ?? 'stale_edge'
  const operationalNotes = buildOperationalNotes(summary)

  return {
    read_only: true,
    generated_at: generatedAt,
    as_of_at: asOfAt,
    executable_edge: input.executable_edge,
    microstructure_summary: summary,
    sizing: {
      requested_size_usd: requestedSizeUsd,
      base_size_usd: baseSizeUsd,
      recommended_size_usd: recommendedSizeUsd,
      simulated_size_usd: simulatedSizeUsd,
      size_multiplier: Number(sizeMultiplier.toFixed(4)),
    },
    failure_cases: failureCases,
    summary: {
      base_executable_edge_bps: baseExecutableEdgeBps,
      microstructure_deterioration_bps: Math.max(0, round(summary.executable_deterioration_bps)),
      shadow_drag_bps: Math.max(0, baseExecutableEdgeBps - shadowEdgeBps),
      shadow_edge_bps: shadowEdgeBps,
      base_size_usd: baseSizeUsd,
      recommended_size_usd: recommendedSizeUsd,
      hedge_success_probability: Number(hedgeSuccessProbability.toFixed(4)),
      hedge_success_expected: hedgeSuccessProbability >= 0.6,
      estimated_net_pnl_bps: estimatedNetPnlBps,
      estimated_net_pnl_usd: estimatedNetPnlUsd,
      worst_case_kind: worstCaseKind,
      failure_case_count: failureCases.length,
      scenario_overview: buildScenarioOverview(summary),
      notes: [
        'Read-only shadow arbitrage simulation only estimates outcomes and never emits orders.',
        `Base executable edge is ${baseExecutableEdgeBps} bps.`,
        `Shadow drag is ${Math.max(0, baseExecutableEdgeBps - shadowEdgeBps)} bps after microstructure and freshness penalties.`,
        `Hedge success probability is ${(hedgeSuccessProbability * 100).toFixed(1)}%.`,
        `Estimated net PnL is ${estimatedNetPnlBps} bps / ${estimatedNetPnlUsd} USD on ${simulatedSizeUsd} USD.`,
        ...simulatedSizing.notes,
        ...operationalNotes,
        `Failure modes modelled: ${FAILURE_CASE_ORDER.join(', ')}.`,
        `Worst-case failure mode is ${worstCaseKind}.`,
      ],
    },
  }
}
