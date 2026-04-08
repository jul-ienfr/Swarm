import {
  type MarketRecommendationPacket,
  type MarketSnapshot,
  type TradeIntent,
} from '@/lib/prediction-markets/schemas'

export type MicrostructureScenarioKind =
  | 'partial_fill'
  | 'one_leg_fill'
  | 'cancel_replace'
  | 'queue_miss'
  | 'hedge_delay'
  | 'stale_book'
  | 'spread_collapse'

export type MicrostructureSeverity = 'low' | 'medium' | 'high' | 'critical'
export type MicrostructureScenarioStatus = 'stable' | 'degraded' | 'blocked'
export type MicrostructureRecommendedMode = 'paper' | 'shadow' | 'wait'

export type MicrostructureScenario = {
  kind: MicrostructureScenarioKind
  severity: MicrostructureSeverity
  status: MicrostructureScenarioStatus
  legs_required: number
  legs_filled: number
  fill_ratio: number
  impact_bps: number
  executable_edge_after_impact_bps: number
  hedge_delay_ms?: number
  book_age_ms?: number
  notes: string[]
}

export type MicrostructureLabSummary = {
  base_executable_edge_bps: number
  worst_case_kind: MicrostructureScenarioKind
  worst_case_severity: MicrostructureSeverity
  worst_case_executable_edge_bps: number
  executable_deterioration_bps: number
  execution_quality_score: number
  recommended_mode: MicrostructureRecommendedMode
  event_counts: Record<MicrostructureScenarioKind, number>
  scenario_overview: string[]
  notes: string[]
}

export type MicrostructureLabReport = {
  market_id: string
  venue: MarketSnapshot['venue']
  generated_at: string
  recommendation: Pick<
    MarketRecommendationPacket,
    'action' | 'side' | 'edge_bps' | 'spread_bps' | 'confidence' | 'market_price_yes' | 'market_bid_yes' | 'market_ask_yes'
  >
  baseline: {
    liquidity_usd: number
    depth_near_touch: number
    spread_bps: number
    confidence: number
    max_unhedged_leg_ms: number
  }
  scenarios: MicrostructureScenario[]
  summary: MicrostructureLabSummary
}

type MicrostructureLabInput = {
  snapshot: MarketSnapshot
  recommendation: MarketRecommendationPacket
  trade_intent?: Pick<TradeIntent, 'max_unhedged_leg_ms' | 'size_usd' | 'time_in_force'>
  generated_at?: string
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

function nonNegativeMs(value: number | null | undefined): number {
  if (!Number.isFinite(value ?? NaN)) return 0
  return Math.max(0, Math.round(value ?? 0))
}

function severityRank(severity: MicrostructureSeverity): number {
  switch (severity) {
    case 'low':
      return 0
    case 'medium':
      return 1
    case 'high':
      return 2
    case 'critical':
      return 3
  }
}

function severityFromImpact(impactBps: number): MicrostructureSeverity {
  if (impactBps >= 55) return 'critical'
  if (impactBps >= 25) return 'high'
  if (impactBps > 10) return 'medium'
  return 'low'
}

function statusFromScenario(impactBps: number, executableAfterImpactBps: number): MicrostructureScenarioStatus {
  if (executableAfterImpactBps <= 0 || impactBps >= 40) return 'blocked'
  if (impactBps >= 15) return 'degraded'
  return 'stable'
}

function recommendedModeFromSummary(input: {
  action: MarketRecommendationPacket['action']
  worstCaseSeverity: MicrostructureSeverity
  worstCaseExecutableEdgeBps: number
  executableDeteriorationBps: number
  baseExecutableEdgeBps: number
}): MicrostructureRecommendedMode {
  if (input.action !== 'bet') return 'wait'
  if (input.worstCaseExecutableEdgeBps <= 0) return 'wait'
  if (input.worstCaseSeverity === 'critical') return 'wait'
  if (
    input.worstCaseSeverity === 'high' ||
    input.executableDeteriorationBps >= Math.max(20, Math.round(input.baseExecutableEdgeBps * 0.2))
  ) {
    return 'shadow'
  }
  return 'paper'
}

function buildScenario(input: {
  kind: MicrostructureScenarioKind
  impactBps: number
  baseExecutableEdgeBps: number
  legsRequired: number
  legsFilled: number
  hedgeDelayMs?: number
  bookAgeMs?: number
  notes: string[]
}): MicrostructureScenario {
  const executableEdgeAfterImpactBps = Math.max(0, input.baseExecutableEdgeBps - input.impactBps)
  const severity = severityFromImpact(input.impactBps)

  return {
    kind: input.kind,
    severity,
    status: statusFromScenario(input.impactBps, executableEdgeAfterImpactBps),
    legs_required: input.legsRequired,
    legs_filled: input.legsFilled,
    fill_ratio: input.legsRequired === 0 ? 0 : Number((input.legsFilled / input.legsRequired).toFixed(2)),
    impact_bps: input.impactBps,
    executable_edge_after_impact_bps: executableEdgeAfterImpactBps,
    hedge_delay_ms: input.hedgeDelayMs,
    book_age_ms: input.bookAgeMs,
    notes: input.notes,
  }
}

function buildImpactFactors(input: MicrostructureLabInput) {
  const depth = input.snapshot.book?.depth_near_touch ?? 0
  const spreadBps = input.recommendation.spread_bps ?? input.snapshot.spread_bps ?? 0
  const liquidityUsd = input.snapshot.market.liquidity_usd ?? 0
  const confidence = input.recommendation.confidence ?? 0.5
  const maxUnhedgedLegMs = input.trade_intent?.max_unhedged_leg_ms ?? 2_000
  const bookFetchedAt = input.snapshot.book?.fetched_at ?? input.snapshot.captured_at
  const bookAgeMs = nonNegativeMs(Date.parse(input.generated_at ?? nowIso()) - Date.parse(bookFetchedAt ?? input.generated_at ?? nowIso()))

  const thinness = clamp(1 - (depth / 2_000), 0, 1)
  const spreadIntensity = clamp(spreadBps / 400, 0, 1)
  const liquidityPressure = clamp(1 - (liquidityUsd / 200_000), 0, 1)
  const urgencyPressure = clamp(1 - (maxUnhedgedLegMs / 2_000), 0, 1)
  const confidencePenalty = clamp(1 - confidence, 0, 1)
  const hedgeDelayPressure = clamp(1 - (maxUnhedgedLegMs / 4_000), 0, 1)
  const staleBookPressure = clamp(bookAgeMs / 15_000, 0, 1)

  return {
    depth,
    spreadBps,
    liquidityUsd,
    confidence,
    maxUnhedgedLegMs,
    bookAgeMs,
    thinness,
    spreadIntensity,
    liquidityPressure,
    urgencyPressure,
    confidencePenalty,
    hedgeDelayPressure,
    staleBookPressure,
  }
}

function buildExecutionQualityScore(input: {
  baseExecutableEdgeBps: number
  worstCaseExecutableEdgeBps: number
  confidence: number
  depth: number
  spreadBps: number
}): number {
  const retainedEdgeRatio = input.baseExecutableEdgeBps <= 0
    ? 0
    : clamp(input.worstCaseExecutableEdgeBps / input.baseExecutableEdgeBps, 0, 1)
  const depthScore = clamp(input.depth / 2_000, 0, 1)
  const spreadPenalty = clamp(input.spreadBps / 500, 0, 1)

  return Number(
    clamp(
      0.2 +
        (0.32 * retainedEdgeRatio) +
        (0.18 * input.confidence) +
        (0.15 * depthScore) -
        (0.1 * spreadPenalty),
      0,
      1,
    ).toFixed(4),
  )
}

export function buildMicrostructureLabReport(input: MicrostructureLabInput): MicrostructureLabReport {
  const factors = buildImpactFactors(input)
  const baseExecutableEdgeBps = Math.max(0, round(input.recommendation.edge_bps))
  const baseRecommendation = {
    action: input.recommendation.action,
    side: input.recommendation.side,
    edge_bps: input.recommendation.edge_bps,
    spread_bps: input.recommendation.spread_bps,
    confidence: input.recommendation.confidence,
    market_price_yes: input.recommendation.market_price_yes,
    market_bid_yes: input.recommendation.market_bid_yes,
    market_ask_yes: input.recommendation.market_ask_yes,
  } satisfies MicrostructureLabReport['recommendation']

  const scenarios = [
    buildScenario({
      kind: 'partial_fill',
      impactBps: round(5 + (10 * factors.thinness) + (8 * factors.spreadIntensity)),
      baseExecutableEdgeBps,
      legsRequired: 2,
      legsFilled: 1,
      notes: [
        'Partial fills become more likely as depth thins and spread widens.',
        'This scenario is a simple execution drag, not a full abort.',
      ],
    }),
    buildScenario({
      kind: 'one_leg_fill',
      impactBps: round(8.5 + (18 * factors.thinness) + (12 * factors.spreadIntensity) + (9 * factors.confidencePenalty) + (8 * factors.urgencyPressure)),
      baseExecutableEdgeBps,
      legsRequired: 2,
      legsFilled: 1,
      notes: [
        'One leg fills while the hedge is delayed or missed.',
        'This is the main legging-risk proxy in the lab.',
      ],
    }),
    buildScenario({
      kind: 'cancel_replace',
      impactBps: round(4 + (8 * factors.thinness) + (4 * factors.spreadIntensity) + (3 * factors.urgencyPressure)),
      baseExecutableEdgeBps,
      legsRequired: 2,
      legsFilled: 2,
      notes: [
        'Cancel/replace churn eats into the edge even when fills eventually happen.',
        'Thin books and urgent routing make this worse.',
      ],
    }),
    buildScenario({
      kind: 'queue_miss',
      impactBps: round(10 + (16 * factors.thinness) + (8 * factors.liquidityPressure) + (6 * factors.spreadIntensity)),
      baseExecutableEdgeBps,
      legsRequired: 2,
      legsFilled: 0,
      notes: [
        'Queue miss means the order sits behind the touch long enough to lose the opportunity.',
        'Low liquidity and thin depth both increase this risk.',
        'The severity should be read as a routing and priority signal, not just a pricing signal.',
      ],
    }),
    buildScenario({
      kind: 'hedge_delay',
      impactBps: round(9 + (14 * factors.urgencyPressure) + (10 * factors.hedgeDelayPressure) + (6 * factors.thinness)),
      baseExecutableEdgeBps,
      legsRequired: 2,
      legsFilled: 1,
      hedgeDelayMs: factors.maxUnhedgedLegMs,
      notes: [
        'Hedge delay captures the gap between the first leg and the protective hedge.',
        'Tighter max-unhedged windows should push the mode toward shadow or wait.',
      ],
    }),
    buildScenario({
      kind: 'stale_book',
      impactBps: round(12 + (18 * factors.staleBookPressure) + (8 * factors.spreadIntensity) + (6 * factors.confidencePenalty)),
      baseExecutableEdgeBps,
      legsRequired: 2,
      legsFilled: 0,
      bookAgeMs: factors.bookAgeMs,
      notes: [
        'A stale book should degrade the lab even if the nominal spread still looks attractive.',
        'This is the operational proxy for snapshot freshness loss.',
      ],
    }),
    buildScenario({
      kind: 'spread_collapse',
      impactBps: round(10 + (20 * factors.spreadIntensity) + (4 * factors.confidencePenalty)),
      baseExecutableEdgeBps,
      legsRequired: 2,
      legsFilled: 2,
      notes: [
        'A narrow or collapsing spread can erase the executable edge before completion.',
        'This scenario is the sharpest proxy for market moving against the plan.',
      ],
    }),
  ]

  const worstCase = [...scenarios].sort((left, right) => {
    const byImpact = right.impact_bps - left.impact_bps
    if (byImpact !== 0) return byImpact
    return severityRank(right.severity) - severityRank(left.severity)
  })[0]

  const worstCaseExecutableEdgeBps = worstCase?.executable_edge_after_impact_bps ?? 0
  const executableDeteriorationBps = Math.max(0, baseExecutableEdgeBps - worstCaseExecutableEdgeBps)
  const recommendedMode = recommendedModeFromSummary({
    action: input.recommendation.action,
    worstCaseSeverity: worstCase?.severity ?? 'low',
    worstCaseExecutableEdgeBps,
    executableDeteriorationBps,
    baseExecutableEdgeBps,
  })

  const eventCounts = scenarios.reduce<Record<MicrostructureScenarioKind, number>>(
    (counts, scenario) => {
      counts[scenario.kind] += 1
      return counts
    },
    {
      partial_fill: 0,
      one_leg_fill: 0,
      cancel_replace: 0,
      queue_miss: 0,
      hedge_delay: 0,
      stale_book: 0,
      spread_collapse: 0,
    },
  )

  const scenarioOverview = scenarios.map((scenario) => {
    const pieces = [
      `${scenario.kind}:${scenario.severity}/${scenario.status}`,
      `impact=${scenario.impact_bps}bps`,
      `edge_after=${scenario.executable_edge_after_impact_bps}bps`,
    ]
    if (scenario.hedge_delay_ms != null) pieces.push(`hedge_delay=${scenario.hedge_delay_ms}ms`)
    if (scenario.book_age_ms != null) pieces.push(`book_age=${scenario.book_age_ms}ms`)
    return pieces.join(' ')
  })

  return {
    market_id: input.snapshot.market.market_id,
    venue: input.snapshot.venue,
    generated_at: input.generated_at ?? nowIso(),
    recommendation: baseRecommendation,
    baseline: {
      liquidity_usd: factors.liquidityUsd,
      depth_near_touch: factors.depth,
      spread_bps: factors.spreadBps,
      confidence: factors.confidence,
      max_unhedged_leg_ms: factors.maxUnhedgedLegMs,
    },
    scenarios,
    summary: {
      base_executable_edge_bps: baseExecutableEdgeBps,
      worst_case_kind: worstCase?.kind ?? 'partial_fill',
      worst_case_severity: worstCase?.severity ?? 'low',
      worst_case_executable_edge_bps: worstCaseExecutableEdgeBps,
      executable_deterioration_bps: executableDeteriorationBps,
      execution_quality_score: buildExecutionQualityScore({
        baseExecutableEdgeBps,
        worstCaseExecutableEdgeBps,
        confidence: factors.confidence,
        depth: factors.depth,
        spreadBps: factors.spreadBps,
      }),
      recommended_mode: recommendedMode,
      event_counts: eventCounts,
      scenario_overview: scenarioOverview,
      notes: [
        `Base executable edge is ${baseExecutableEdgeBps} bps.`,
        `Worst-case deterioration is ${executableDeteriorationBps} bps.`,
        `Recommended mode is ${recommendedMode}.`,
        `Scenario overview: ${scenarioOverview.join(' | ')}.`,
      ],
    },
  }
}
