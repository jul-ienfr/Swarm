import {
  average,
  clampNumber,
  compactParts,
  dedupeStrings,
  fingerprint,
  normalizeText,
  roundNumber,
  toFiniteNumber,
} from './prediction-market-spine-utils'
import {
  buildPredictionMarketExternalIntegrationSummary,
  getConversationScopedExternalSourceProfile,
  type PredictionMarketExternalIntegrationSummary,
} from './external-source-profiles'
import { getPredictionMarketP1CRuntimeSummary } from './external-runtime'
import { findGeoMapDataCnRecords, getGeoMapDataCnCoverageSummary } from './geomapdata-cn'
import type { PredictionMarketCatalystTimeline } from './catalyst-timeline'
import type { PredictionMarketRulesLineage } from './rules-lineage'
import type { PredictionMarketSourceAudit } from './source-audit'

export type PredictionMarketWorldStateRecommendation = 'bet' | 'wait' | 'no_trade'
export type PredictionMarketWorldStateBias = 'bullish' | 'bearish' | 'neutral'

export interface PredictionMarketPriceSignal {
  midpoint_yes?: number | null
  market_price_yes?: number | null
  fair_value_yes?: number | null
  spread_bps?: number | null
}

export interface PredictionMarketWorldStateInput {
  market_id: string
  market_question: string
  venue?: string | null
  as_of?: string
  source_audit: PredictionMarketSourceAudit
  rules_lineage: PredictionMarketRulesLineage
  catalyst_timeline: PredictionMarketCatalystTimeline
  price_signal?: PredictionMarketPriceSignal | null
  regime?: string | null
}

export interface PredictionMarketWorldStateSnapshot {
  world_state_id: string
  market_id: string
  market_question: string
  venue: string | null
  as_of: string
  regime: string | null
  source_audit: PredictionMarketSourceAudit
  rules_lineage: PredictionMarketRulesLineage
  catalyst_timeline: PredictionMarketCatalystTimeline
  bias: PredictionMarketWorldStateBias
  confidence_score: number
  tradability_score: number
  source_alignment_score: number
  rule_clarity_score: number
  catalyst_pressure_score: number
  external_integration: PredictionMarketExternalIntegrationSummary
  external_read_models_summary: string | null
  geo_context: PredictionMarketWorldStateGeoContext | null
  market_gap_yes: number | null
  market_gap_bps: number | null
  recommended_action: PredictionMarketWorldStateRecommendation
  recommended_side: 'yes' | 'no' | null
  recommendation_reason: string
  risk_flags: string[]
  source_refs: string[]
  summary: string
  fingerprint: string
}

export interface PredictionMarketWorldStateGeoContext {
  provider: 'lyhmyd1211/GeoMapData_CN'
  source_url: string
  adcodes: string[]
  region_names: string[]
  regions: Array<{
    adcode: string
    name: string
    level: string
    center: [number, number] | null
    centroid: [number, number] | null
  }>
  summary: string
}

function buildGeoContext(sourceAudit: PredictionMarketSourceAudit): PredictionMarketWorldStateGeoContext | null {
  const regions = findGeoMapDataCnRecords(sourceAudit.geo_refs)
  if (regions.length === 0) return null

  const coverage = getGeoMapDataCnCoverageSummary()
  return {
    provider: 'lyhmyd1211/GeoMapData_CN',
    source_url: coverage.source_url,
    adcodes: regions.map((region) => region.adcode),
    region_names: regions.map((region) => region.name),
    regions: regions.map((region) => ({
      adcode: region.adcode,
      name: region.name,
      level: region.level,
      center: region.center ?? null,
      centroid: region.centroid ?? null,
    })),
    summary: `Geo enrichment active for ${regions.length} China region(s) via GeoMapData_CN thin import.`,
  }
}

function buildExternalIntegration(sourceAudit: PredictionMarketSourceAudit, geoContext: PredictionMarketWorldStateGeoContext | null) {
  if (!geoContext) return sourceAudit.external_integration

  const geoProfile = getConversationScopedExternalSourceProfile('geomapdata-cn')
  if (!geoProfile) return sourceAudit.external_integration

  const profiles = [...sourceAudit.external_profiles]
  if (!profiles.some((profile) => profile.profile_id === geoProfile.profile_id)) {
    profiles.push(geoProfile)
  }

  return buildPredictionMarketExternalIntegrationSummary(profiles)
}

function resolveBias(marketGapYes: number | null): PredictionMarketWorldStateBias {
  if (marketGapYes === null) {
    return 'neutral'
  }
  if (marketGapYes > 0.02) {
    return 'bullish'
  }
  if (marketGapYes < -0.02) {
    return 'bearish'
  }
  return 'neutral'
}

function computeCatalystPressure(timeline: PredictionMarketCatalystTimeline): number {
  if (!timeline.events.length) {
    return 0.18
  }
  const weighted = timeline.events.reduce((sum, event) => {
    const statusWeight =
      event.status === 'confirmed' || event.status === 'resolved'
        ? 0.75
        : event.status === 'pending'
          ? 0.5
          : 0.25
    const urgencyWeight = 0.35 + event.urgency * 0.65
    const overdueWeight = event.overdue ? 1.15 : 1
    return sum + statusWeight * urgencyWeight * overdueWeight
  }, 0)
  return clampNumber(weighted / timeline.events.length, 0, 1)
}

function deriveRecommendation(input: {
  sourceAlignment: number
  ruleClarity: number
  catalystPressure: number
  marketGapYes: number | null
  spreadBps: number | null
}): {
  action: PredictionMarketWorldStateRecommendation
  side: 'yes' | 'no' | null
  confidence: number
  reason: string
  risk_flags: string[]
} {
  const risk_flags: string[] = []
  if (input.sourceAlignment < 0.45) {
    risk_flags.push('low_source_alignment')
  }
  if (input.ruleClarity < 0.5) {
    risk_flags.push('conflicted_rules')
  }
  if (input.catalystPressure < 0.3) {
    risk_flags.push('weak_catalyst_pressure')
  }
  if (input.spreadBps !== null && input.spreadBps > 400) {
    risk_flags.push('wide_spread')
  }

  const gap = input.marketGapYes ?? 0
  const gapStrength = clampNumber(Math.abs(gap) * 10, 0, 1)
  const confidence = roundNumber(
    clampNumber(input.sourceAlignment * 0.4 + input.ruleClarity * 0.2 + input.catalystPressure * 0.15 + gapStrength * 0.25, 0, 1),
    4,
  )

  if (input.sourceAlignment < 0.5 || input.ruleClarity < 0.45) {
    return {
      action: 'no_trade',
      side: null,
      confidence,
      reason: 'Source alignment or rule clarity is too weak for a live recommendation.',
      risk_flags,
    }
  }

  if (Math.abs(gap) < 0.02 && input.catalystPressure < 0.5) {
    return {
      action: 'wait',
      side: null,
      confidence,
      reason: 'The world-state is coherent, but the edge is too small to justify a trade.',
      risk_flags,
    }
  }

  if (gap > 0.025) {
    return {
      action: 'bet',
      side: 'yes',
      confidence,
      reason: 'The world-state implies Yes is underpriced relative to the current market signal.',
      risk_flags,
    }
  }

  if (gap < -0.025) {
    return {
      action: 'bet',
      side: 'no',
      confidence,
      reason: 'The world-state implies No is underpriced relative to the current market signal.',
      risk_flags,
    }
  }

  return {
    action: 'wait',
    side: null,
    confidence,
    reason: 'The world-state is valid but the edge remains within the wait band.',
    risk_flags,
  }
}

export function buildPredictionMarketWorldState(
  input: PredictionMarketWorldStateInput,
): PredictionMarketWorldStateSnapshot {
  const as_of = normalizeText(input.as_of) ?? new Date().toISOString()
  const venue = normalizeText(input.venue)
  const source_alignment_score = roundNumber(clampNumber(input.source_audit.average_score, 0, 1), 4)
  const rule_clarity_score = roundNumber(
    clampNumber(Math.max(0, 1 - input.rules_lineage.conflicted_clause_ids.length / Math.max(input.rules_lineage.clauses.length, 1)), 0, 1),
    4,
  )
  const catalyst_pressure_score = roundNumber(computeCatalystPressure(input.catalyst_timeline), 4)
  const midpoint_yes = input.price_signal?.midpoint_yes ?? null
  const fair_value_yes = input.price_signal?.fair_value_yes ?? null
  const market_price_yes = input.price_signal?.market_price_yes ?? null
  const spread_bps = input.price_signal?.spread_bps ?? null

  const marketGapYes =
    fair_value_yes !== null && market_price_yes !== null
      ? roundNumber(fair_value_yes - market_price_yes, 4)
      : midpoint_yes !== null && market_price_yes !== null
        ? roundNumber(midpoint_yes - market_price_yes, 4)
        : null
  const marketGapBps = marketGapYes === null ? null : Math.round(marketGapYes * 10_000)
  const bias = resolveBias(marketGapYes)
  const geo_context = buildGeoContext(input.source_audit)
  const external_integration = buildExternalIntegration(input.source_audit, geo_context)
  const p1cRuntime = getPredictionMarketP1CRuntimeSummary({
    geo_context_present: geo_context != null,
  })

  const recommendation = deriveRecommendation({
    sourceAlignment: source_alignment_score,
    ruleClarity: rule_clarity_score,
    catalystPressure: catalyst_pressure_score,
    marketGapYes,
    spreadBps: spread_bps,
  })

  const tradability_score = roundNumber(
    clampNumber(
      average([source_alignment_score, rule_clarity_score, catalyst_pressure_score, recommendation.confidence]),
      0,
      1,
    ),
    4,
  )

  const world_state_id = fingerprint('world-state', {
    market_id: input.market_id,
    as_of,
    source_audit_id: input.source_audit.audit_id,
    rules_lineage_id: input.rules_lineage.lineage_id,
    catalyst_timeline_id: input.catalyst_timeline.timeline_id,
    regime: normalizeText(input.regime),
    marketGapYes,
    marketGapBps,
    external_profiles: external_integration.profile_ids,
    geo_refs: geo_context?.adcodes ?? [],
  })

  const source_refs = dedupeStrings([
    ...input.source_audit.source_refs,
    ...input.rules_lineage.source_refs,
    ...input.catalyst_timeline.source_refs,
  ])
  const risk_flags = dedupeStrings([
    ...recommendation.risk_flags,
    bias === 'neutral' ? 'neutral_bias' : null,
    recommendation.action === 'no_trade' ? 'no_trade_default' : null,
  ])
  const summary = compactParts([
    `${input.market_question}`,
    `bias=${bias}`,
    `action=${recommendation.action}`,
    recommendation.side ? `side=${recommendation.side}` : null,
    `source=${source_alignment_score.toFixed(2)}`,
    `rules=${rule_clarity_score.toFixed(2)}`,
    `catalyst=${catalyst_pressure_score.toFixed(2)}`,
    marketGapBps !== null ? `gap=${marketGapBps}bps` : null,
    external_integration.total_profiles > 0 ? `profiles=${external_integration.total_profiles}` : null,
    geo_context ? `geo=${geo_context.adcodes.length}` : null,
  ])

  return {
    world_state_id,
    market_id: input.market_id,
    market_question: input.market_question,
    venue,
    as_of,
    regime: normalizeText(input.regime),
    source_audit: input.source_audit,
    rules_lineage: input.rules_lineage,
    catalyst_timeline: input.catalyst_timeline,
    bias,
    confidence_score: recommendation.confidence,
    tradability_score,
    source_alignment_score,
    rule_clarity_score,
    catalyst_pressure_score,
    external_integration,
    external_read_models_summary: p1cRuntime.summary,
    geo_context,
    market_gap_yes: marketGapYes,
    market_gap_bps: marketGapBps,
    recommended_action: recommendation.action,
    recommended_side: recommendation.side,
    recommendation_reason: recommendation.reason,
    risk_flags,
    source_refs,
    summary,
    fingerprint: fingerprint('world-state-snapshot', {
      world_state_id,
      bias,
      confidence_score: recommendation.confidence,
      tradability_score,
      recommendation: recommendation.action,
      side: recommendation.side,
      source_refs,
      risk_flags,
      external_profiles: external_integration.profile_ids,
      geo_refs: geo_context?.adcodes ?? [],
    }),
  }
}
