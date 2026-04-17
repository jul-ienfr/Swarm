import { z } from 'zod'

export const PREDICTION_MARKETS_SCHEMA_VERSION = '1.0.0'
export const PREDICTION_MARKETS_BASELINE_MODEL = 'baseline-v0'

export const predictionMarketVenueSchema = z.enum(['polymarket', 'kalshi'])
export const predictionMarketModeSchema = z.enum(['advise', 'replay'])
export const predictionMarketAdviceRequestModeSchema = z.enum(['predict', 'predict_deep'])
export const predictionMarketAdviceResponseVariantSchema = z.enum(['standard', 'research_heavy', 'execution_heavy'])
export const predictionMarketTimesFMModeSchema = z.enum(['off', 'auto', 'required'])
export const predictionMarketTimesFMLaneSchema = z.enum(['microstructure', 'event_probability'])
export const predictionMarketRecommendationActionSchema = z.enum(['bet', 'no_trade', 'wait'])
export const predictionMarketSideSchema = z.enum(['yes', 'no'])
export const predictionMarketVenueTypeSchema = z.enum([
  'execution-equivalent',
  'execution-like',
  'reference-only',
  'experimental',
])
export const predictionMarketFeedTransportSchema = z.enum([
  'unknown',
  'http_json',
  'local_cache',
  'fixture_cache',
  'surrogate_snapshot',
  'unavailable',
])
export const crossVenueOpportunityTypeSchema = z.enum([
  'comparison_only',
  'relative_value',
  'cross_venue_signal',
  'true_arbitrage',
])
export const crossVenueTaxonomySchema = crossVenueOpportunityTypeSchema
export const predictionMarketHealthStatusSchema = z.enum(['healthy', 'degraded', 'blocked', 'unknown'])
export const venueHealthStatusSchema = predictionMarketHealthStatusSchema
export const predictionMarketDegradedModeSchema = z.enum(['normal', 'degraded', 'blocked'])
export const venueDegradedModeSchema = predictionMarketDegradedModeSchema
export const predictionMarketTimeInForceSchema = z.enum(['gtc', 'ioc', 'fok', 'day'])
export const tradeIntentTimeInForceSchema = predictionMarketTimeInForceSchema
export const executionProjectionVerdictSchema = z.enum(['allowed', 'downgraded', 'blocked'])
export const tradeIntentGuardVerdictSchema = z.enum(['allowed', 'annotated', 'blocked'])
export const predictionMarketArtifactTypeSchema = z.enum([
  'market_descriptor',
  'resolution_policy',
  'market_snapshot',
  'evidence_bundle',
  'forecast_packet',
  'recommendation_packet',
  'source_audit',
  'rules_lineage',
  'catalyst_timeline',
  'world_state',
  'ticket_payload',
  'quant_signal_bundle',
  'decision_ledger',
  'calibration_report',
  'resolved_history',
  'cost_model_report',
  'walk_forward_report',
  'autopilot_cycle_summary',
  'research_memory_summary',
  'paper_surface',
  'replay_surface',
  'market_events',
  'market_positions',
  'research_sidecar',
  'timesfm_sidecar',
  'microstructure_lab',
  'cross_venue_intelligence',
  'provenance_bundle',
  'pipeline_guard',
  'runtime_guard',
  'compliance_report',
  'execution_readiness',
  'execution_pathways',
  'execution_projection',
  'shadow_arbitrage',
  'trade_intent_guard',
  'multi_venue_execution',
  'strategy_candidate_packet',
  'strategy_decision_packet',
  'strategy_shadow_summary',
  'strategy_shadow_report',
  'execution_intent_preview',
  'quote_pair_intent_preview',
  'basket_intent_preview',
  'latency_reference_bundle',
  'resolution_anomaly_report',
  'autonomous_agent_report',
  'research_bridge',
  'run_manifest',
])

export const predictionMarketProbabilityBandSchema = z.object({
  low: z.number().min(0).max(1),
  high: z.number().min(0).max(1),
}).superRefine((value, ctx) => {
  if (value.high < value.low) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['high'],
      message: 'high must be greater than or equal to low',
    })
  }
})

export const decisionPacketScenarioSchema = z.preprocess((value) => {
  if (typeof value === 'string') {
    return {
      label: value,
      summary: value,
    }
  }

  return value
}, z.object({
  scenario_id: z.string().min(1).optional(),
  label: z.string().min(1),
  summary: z.string().min(1),
  probability: z.number().min(0).max(1).optional(),
}))

export const decisionPacketRiskSchema = z.preprocess((value) => {
  if (typeof value === 'string') {
    return {
      label: value,
      summary: value,
    }
  }

  return value
}, z.object({
  risk_id: z.string().min(1).optional(),
  label: z.string().min(1),
  severity: z.enum(['low', 'medium', 'high', 'critical']).default('medium'),
  summary: z.string().min(1),
}))

export const decisionPacketArtifactSchema = z.preprocess((value) => {
  if (typeof value === 'string') {
    return {
      artifact_id: value,
      artifact_type: 'external_reference',
    }
  }

  return value
}, z.object({
  artifact_id: z.string().min(1),
  artifact_type: z.string().min(1),
  uri: z.string().min(1).optional(),
  sha256: z.string().min(1).optional(),
}))

export const predictionMarketProvenanceLinkSchema = z.object({
  ref: z.string().min(1),
  kind: z.enum(['source', 'evidence', 'artifact', 'decision', 'signal', 'observation']).default('source'),
  label: z.string().min(1).optional(),
  uri: z.string().min(1).optional(),
  confidence: z.number().min(0).max(1).optional(),
})

export const predictionMarketProvenanceBundleSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  generated_at: z.string().min(1),
  provenance_refs: z.array(z.string().min(1)).default([]),
  evidence_refs: z.array(z.string().min(1)).default([]),
  artifact_refs: z.array(z.string().min(1)).default([]),
  links: z.array(predictionMarketProvenanceLinkSchema).default([]),
  summary: z.string().min(1),
})

export const predictionMarketResearchProvenanceBundleSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  bundle_id: z.string().min(1),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  generated_at: z.string().min(1),
  freshness_score: z.number().min(0).max(1),
  content_hash: z.string().min(1),
  provenance_refs: z.array(z.string().min(1)).default([]),
  evidence_refs: z.array(z.string().min(1)).default([]),
  artifact_refs: z.array(z.string().min(1)).default([]),
  links: z.array(predictionMarketProvenanceLinkSchema).default([]),
  summary: z.string().min(1),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const researchBridgeBundleSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  bundle_id: z.string().min(1),
  packet_version: z.string().min(1),
  compatibility_mode: z.enum(['market_only', 'social_bridge']),
  market_only_compatible: z.boolean().default(true),
  sidecar_name: z.string().min(1).nullable().optional(),
  sidecar_health: z.record(z.string(), z.unknown()).default({}),
  classification: z.string().min(1),
  classification_reasons: z.array(z.string().min(1)).default([]),
  market_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  run_id: z.string().min(1).nullable().optional(),
  findings: z.array(z.record(z.string(), z.unknown())).default([]),
  synthesis: z.record(z.string(), z.unknown()).nullable().optional(),
  pipeline: z.record(z.string(), z.unknown()).nullable().optional(),
  abstention_policy: z.record(z.string(), z.unknown()).nullable().optional(),
  signal_packets: z.array(z.record(z.string(), z.unknown())).default([]),
  artifact_refs: z.array(z.string().min(1)).default([]),
  evidence_refs: z.array(z.string().min(1)).default([]),
  provenance_refs: z.array(z.string().min(1)).default([]),
  social_context_refs: z.array(z.string().min(1)).default([]),
  provenance_bundle: predictionMarketResearchProvenanceBundleSchema.nullable().optional(),
  packet_refs: z.record(z.string(), z.string()).default({}),
  created_at: z.string().min(1),
  freshness_score: z.number().min(0).max(1),
  content_hash: z.string().min(1),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const predictionMarketPacketCompatibilityModeSchema = z.enum(['market_only', 'social_bridge'])

export const predictionMarketPacketContractSchema = z.object({
  contract_id: z.string().min(1),
  schema_version: z.string().min(1),
  packet_version: z.string().min(1),
  packet_kind: z.string().min(1),
  compatibility_mode: predictionMarketPacketCompatibilityModeSchema,
  market_only_compatible: z.boolean().default(true),
})

export const predictionMarketAdvisorStageStatusSchema = z.enum(['ready', 'degraded', 'blocked', 'skipped'])

export const predictionMarketAdvisorStageSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  stage_id: z.string().min(1),
  stage_kind: z.string().min(1),
  role: z.string().min(1),
  status: predictionMarketAdvisorStageStatusSchema.default('ready'),
  input_refs: z.array(z.string().min(1)).default([]),
  output_refs: z.array(z.string().min(1)).default([]),
  contract_ids: z.array(z.string().min(1)).default([]),
  summary: z.string().min(1),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const predictionMarketAdvisorArchitectureSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  architecture_id: z.string().min(1),
  mode: z.literal('advisor').default('advisor'),
  architecture_kind: z.literal('reference_agentic').default('reference_agentic'),
  runtime: z.string().min(1),
  backend_mode: z.string().min(1),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  social_bridge_state: z.enum(['available', 'unavailable']).default('unavailable'),
  research_bridge_state: z.enum(['available', 'ready', 'unavailable']).default('unavailable'),
  packet_contracts: z.record(z.string(), predictionMarketPacketContractSchema).default({}),
  packet_refs: z.record(z.string(), z.string().nullable()).default({}),
  stage_order: z.array(z.string().min(1)).default([]),
  stages: z.array(predictionMarketAdvisorStageSchema).default([]),
  summary: z.string().min(1),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const decisionPacketSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  packet_version: z.string().min(1).default('1.0.0'),
  packet_kind: z.literal('decision').default('decision'),
  compatibility_mode: predictionMarketPacketCompatibilityModeSchema.default('market_only'),
  market_only_compatible: z.boolean().default(true),
  contract_id: z.string().min(1).optional(),
  source_bundle_id: z.string().min(1).optional(),
  source_packet_refs: z.array(z.string().min(1)).default([]),
  social_context_refs: z.array(z.string().min(1)).default([]),
  market_context_refs: z.array(z.string().min(1)).default([]),
  correlation_id: z.string().min(1),
  question: z.string().min(1),
  topic: z.string().min(1),
  objective: z.string().min(1),
  probability_estimate: z.number().min(0).max(1),
  confidence_band: z.preprocess((value) => {
    if (Array.isArray(value) && value.length === 2) {
      return {
        low: value[0],
        high: value[1],
      }
    }

    return value
  }, predictionMarketProbabilityBandSchema),
  scenarios: z.array(decisionPacketScenarioSchema).default([]),
  risks: z.array(decisionPacketRiskSchema).default([]),
  recommendation: z.string().min(1),
  rationale_summary: z.string().min(1),
  artifacts: z.array(decisionPacketArtifactSchema).default([]),
  mode_used: z.string().min(1),
  engine_used: z.string().min(1),
  runtime_used: z.string().min(1),
  resolution_policy_ref: z.string().min(1).optional(),
  comparable_market_refs: z.array(z.string().min(1)).default([]),
  requires_manual_review: z.boolean().default(false),
})

export const strategyFamilySchema = z.string().trim().min(1)

export const DEFAULT_ENABLED_STRATEGY_FAMILIES = [
  'intramarket_parity',
  'maker_spread_capture',
  'latency_reference_spread',
  'logical_constraint_arb',
  'negative_risk_basket',
  'resolution_attack_watch',
  'resolution_sniping_watch',
  'autonomous_agent_advisory',
] as const

export const marketRegimeSchema = z.object({
  regime_id: z.string().min(1).optional(),
  label: z.string().min(1),
  summary: z.string().min(1),
  confidence: z.number().min(0).max(1),
  observed_at: z.string().min(1),
  signals: z.array(z.string().min(1)).default([]),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const executionQuoteLegSchema = z.object({
  side: predictionMarketSideSchema,
  price: z.number().min(0).max(1),
  size_usd: z.number().positive().optional(),
  notes: z.string().min(1).optional(),
})

export const basketIntentLegSchema = z.object({
  market_id: z.string().min(1),
  side: predictionMarketSideSchema,
  price: z.number().min(0).max(1),
  size_usd: z.number().positive(),
  notes: z.string().min(1).optional(),
})

export const quotePairIntentPreviewSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  preview_id: z.string().min(1),
  preview_kind: z.literal('quote_pair').default('quote_pair'),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  strategy_profile: z.string().trim().min(1).default('default'),
  strategy_family: strategyFamilySchema.optional(),
  quotes: z.array(executionQuoteLegSchema).length(2),
  max_slippage_bps: z.number().int().nonnegative().optional(),
  summary: z.string().min(1),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const basketIntentPreviewSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  preview_id: z.string().min(1),
  preview_kind: z.literal('basket').default('basket'),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  basket_id: z.string().min(1).optional(),
  strategy_profile: z.string().trim().min(1).default('default'),
  strategy_family: strategyFamilySchema.optional(),
  legs: z.array(basketIntentLegSchema).min(1),
  max_slippage_bps: z.number().int().nonnegative().optional(),
  summary: z.string().min(1),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const tradeExecutionIntentPreviewSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  preview_id: z.string().min(1),
  preview_kind: z.literal('trade').default('trade'),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  strategy_profile: z.string().trim().min(1).default('default'),
  strategy_family: strategyFamilySchema.optional(),
  trade_intent_preview: z.lazy(() => tradeIntentSchema),
  summary: z.string().min(1),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const shadowWatchIntentPreviewSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  preview_id: z.string().min(1),
  preview_kind: z.literal('shadow_watch').default('shadow_watch'),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  strategy_profile: z.string().trim().min(1).default('default'),
  strategy_family: strategyFamilySchema.optional(),
  watch_kinds: z.array(z.string().min(1)).default([]),
  notes: z.array(z.string().min(1)).default([]),
  summary: z.string().min(1),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const executionIntentPreviewSchema = z.discriminatedUnion('preview_kind', [
  tradeExecutionIntentPreviewSchema,
  quotePairIntentPreviewSchema,
  basketIntentPreviewSchema,
  shadowWatchIntentPreviewSchema,
])

export const latencyReferenceBundleSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  bundle_id: z.string().min(1),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  captured_at: z.string().min(1),
  decision_latency_budget_ms: z.number().int().positive().optional(),
  fetch_latency_budget_ms: z.number().int().positive().optional(),
  snapshot_freshness_budget_ms: z.number().int().positive().optional(),
  observed_latency_ms: z.number().int().nonnegative().optional(),
  p50_latency_ms: z.number().int().nonnegative().optional(),
  p95_latency_ms: z.number().int().nonnegative().optional(),
  p99_latency_ms: z.number().int().nonnegative().optional(),
  source_refs: z.array(z.string().min(1)).default([]),
  summary: z.string().min(1),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const resolutionAnomalyReportSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  report_id: z.string().min(1),
  run_id: z.string().min(1).optional(),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  anomaly_kind: z.enum([
    'late_resolution',
    'policy_mismatch',
    'oracle_conflict',
    'manual_override',
    'ambiguous_source',
    'other',
  ]),
  severity: z.enum(['low', 'medium', 'high', 'critical']).default('medium'),
  detected_at: z.string().min(1),
  source_refs: z.array(z.string().min(1)).default([]),
  impacted_artifact_refs: z.array(z.string().min(1)).default([]),
  summary: z.string().min(1),
  notes: z.array(z.string().min(1)).default([]),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const autonomousAgentReportSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  report_id: z.string().min(1),
  agent_id: z.string().min(1),
  agent_role: z.string().min(1),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  strategy_profile: z.string().trim().min(1).default('default'),
  strategy_family: strategyFamilySchema,
  market_regime: marketRegimeSchema.nullable().optional(),
  generated_at: z.string().min(1),
  observations: z.array(z.string().min(1)).default([]),
  actions: z.array(z.string().min(1)).default([]),
  confidence: z.number().min(0).max(1),
  summary: z.string().min(1),
  source_refs: z.array(z.string().min(1)).default([]),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const strategyShadowSummarySchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  shadow_id: z.string().min(1),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  strategy_profile: z.string().trim().min(1).default('default'),
  strategy_family: strategyFamilySchema,
  candidate_count: z.number().int().nonnegative(),
  decision_count: z.number().int().nonnegative(),
  disagreement_count: z.number().int().nonnegative(),
  alignment_rate: z.number().min(0).max(1),
  summary: z.string().min(1),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const strategyShadowReportSchema = strategyShadowSummarySchema.extend({
  report_id: z.string().min(1),
  generated_at: z.string().min(1),
  candidate_refs: z.array(z.string().min(1)).default([]),
  decision_refs: z.array(z.string().min(1)).default([]),
  outcome: z.enum(['aligned', 'diverged', 'blocked']).default('aligned'),
  notes: z.array(z.string().min(1)).default([]),
})

const strategyPacketCommonSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  packet_version: z.string().min(1).default('1.0.0'),
  compatibility_mode: predictionMarketPacketCompatibilityModeSchema.default('market_only'),
  market_only_compatible: z.boolean().default(true),
  contract_id: z.string().min(1).optional(),
  source_bundle_id: z.string().min(1).optional(),
  source_packet_refs: z.array(z.string().min(1)).default([]),
  social_context_refs: z.array(z.string().min(1)).default([]),
  market_context_refs: z.array(z.string().min(1)).default([]),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  strategy_profile: z.string().trim().min(1).default('default'),
  market_regime: marketRegimeSchema.nullable().optional(),
  correlation_id: z.string().min(1).optional(),
  summary: z.string().min(1),
  rationale: z.string().min(1).optional(),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const strategyCandidatePacketSchema = strategyPacketCommonSchema.extend({
  packet_kind: z.literal('strategy_candidate').default('strategy_candidate'),
  candidate_id: z.string().min(1),
  strategy_family: strategyFamilySchema,
  confidence: z.number().min(0).max(1),
  expected_edge_bps: z.number().nullable().optional(),
  execution_intent_preview: z.lazy(() => executionIntentPreviewSchema).nullable().optional(),
  latency_reference_bundle: z.lazy(() => latencyReferenceBundleSchema).nullable().optional(),
  resolution_anomaly_report: z.lazy(() => resolutionAnomalyReportSchema).nullable().optional(),
  autonomous_agent_report: z.lazy(() => autonomousAgentReportSchema).nullable().optional(),
  shadow_summary: z.lazy(() => strategyShadowSummarySchema).nullable().optional(),
  created_at: z.string().min(1),
})

export const strategyDecisionPacketSchema = strategyPacketCommonSchema.extend({
  packet_kind: z.literal('strategy_decision').default('strategy_decision'),
  decision_id: z.string().min(1),
  candidate_refs: z.array(z.string().min(1)).default([]),
  selected_candidate_ref: z.string().min(1).optional(),
  strategy_family: strategyFamilySchema.optional(),
  decision: z.enum(['adopt', 'reject', 'shadow', 'defer']),
  confidence: z.number().min(0).max(1),
  execution_intent_preview: z.lazy(() => executionIntentPreviewSchema).nullable().optional(),
  latency_reference_bundle: z.lazy(() => latencyReferenceBundleSchema).nullable().optional(),
  resolution_anomaly_report: z.lazy(() => resolutionAnomalyReportSchema).nullable().optional(),
  autonomous_agent_report: z.lazy(() => autonomousAgentReportSchema).nullable().optional(),
  shadow_report: z.lazy(() => strategyShadowReportSchema).nullable().optional(),
  created_at: z.string().min(1),
})

export const crossVenueMarketRefSchema = z.object({
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  venue_type: predictionMarketVenueTypeSchema.optional(),
  slug: z.string().min(1).optional(),
  question: z.string().min(1).optional(),
  side: predictionMarketSideSchema.optional(),
})
export const predictionMarketMarketRefSchema = crossVenueMarketRefSchema

export const predictionMarketBudgetsSchema = z.preprocess((value) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value

  const raw = value as Record<string, unknown>
  return {
    schema_version: raw.schema_version,
    fetch_latency_budget_ms: raw.fetch_latency_budget_ms,
    snapshot_freshness_budget_ms: raw.snapshot_freshness_budget_ms ?? raw.snapshot_freshness_ms,
    decision_latency_budget_ms: raw.decision_latency_budget_ms ?? raw.decision_latency_ms,
    stream_reconnect_budget_ms: raw.stream_reconnect_budget_ms ?? raw.stream_reconnect_ms,
    cache_ttl_ms: raw.cache_ttl_ms,
    max_retries: raw.max_retries,
    backpressure_policy: raw.backpressure_policy,
  }
}, z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  fetch_latency_budget_ms: z.number().int().positive().optional(),
  snapshot_freshness_budget_ms: z.number().int().positive(),
  decision_latency_budget_ms: z.number().int().positive(),
  stream_reconnect_budget_ms: z.number().int().positive().optional(),
  cache_ttl_ms: z.number().int().nonnegative().optional(),
  max_retries: z.number().int().nonnegative().default(0),
  backpressure_policy: z.string().min(1).default('degrade-to-wait'),
}))
export const predictionMarketPerformanceBudgetSchema = predictionMarketBudgetsSchema

export const marketDescriptorSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  venue: predictionMarketVenueSchema,
  venue_type: predictionMarketVenueTypeSchema.default('execution-equivalent'),
  market_id: z.string().min(1),
  event_id: z.string().optional(),
  condition_id: z.string().optional(),
  question_id: z.string().optional(),
  slug: z.string().optional(),
  question: z.string().min(1),
  description: z.string().optional(),
  outcomes: z.array(z.string().min(1)).min(2),
  outcome_token_ids: z.array(z.string().min(1)).optional(),
  start_at: z.string().optional(),
  end_at: z.string().optional(),
  active: z.boolean(),
  closed: z.boolean(),
  accepting_orders: z.boolean().optional(),
  restricted: z.boolean().optional(),
  liquidity_usd: z.number().nullable().optional(),
  volume_usd: z.number().nullable().optional(),
  volume_24h_usd: z.number().nullable().optional(),
  best_bid: z.number().nullable().optional(),
  best_ask: z.number().nullable().optional(),
  last_trade_price: z.number().nullable().optional(),
  tick_size: z.number().nullable().optional(),
  min_order_size: z.number().nullable().optional(),
  is_binary_yes_no: z.boolean().default(false),
  source_urls: z.array(z.string().url()).default([]),
})

export const resolutionPolicySchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  market_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  status: z.enum(['eligible', 'blocked', 'closed', 'ambiguous']),
  manual_review_required: z.boolean().default(false),
  reasons: z.array(z.string()).default([]),
  primary_sources: z.array(z.string()).default([]),
  resolution_text: z.string().optional(),
  evaluated_at: z.string().min(1),
})

export const marketOrderLevelSchema = z.object({
  price: z.number(),
  size: z.number(),
})

export const marketBookSchema = z.object({
  token_id: z.string().min(1),
  market_condition_id: z.string().optional(),
  fetched_at: z.string().min(1),
  best_bid: z.number().nullable(),
  best_ask: z.number().nullable(),
  last_trade_price: z.number().nullable(),
  tick_size: z.number().nullable(),
  min_order_size: z.number().nullable(),
  bids: z.array(marketOrderLevelSchema).default([]),
  asks: z.array(marketOrderLevelSchema).default([]),
  depth_near_touch: z.number().nullable().optional(),
})

export const marketHistoryPointSchema = z.object({
  timestamp: z.number(),
  price: z.number(),
})

export const marketSnapshotSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  venue: predictionMarketVenueSchema,
  market: marketDescriptorSchema,
  captured_at: z.string().min(1),
  yes_outcome_index: z.number().int().nonnegative().default(0),
  yes_token_id: z.string().optional(),
  yes_price: z.number().nullable(),
  no_price: z.number().nullable(),
  midpoint_yes: z.number().nullable(),
  best_bid_yes: z.number().nullable(),
  best_ask_yes: z.number().nullable(),
  spread_bps: z.number().nullable(),
  book: marketBookSchema.nullable().optional(),
  history: z.array(marketHistoryPointSchema).default([]),
  source_urls: z.array(z.string().url()).default([]),
})

export const evidencePacketSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  evidence_id: z.string().min(1),
  market_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  type: z.enum(['market_data', 'orderbook', 'history', 'manual_thesis', 'system_note']),
  title: z.string().min(1),
  summary: z.string().min(1),
  source_url: z.string().url().optional(),
  captured_at: z.string().min(1),
  content_hash: z.string().min(1),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const crossVenueMatchSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  canonical_event_id: z.string().min(1),
  left_market_ref: crossVenueMarketRefSchema,
  right_market_ref: crossVenueMarketRefSchema,
  semantic_similarity_score: z.number().min(0).max(1),
  resolution_compatibility_score: z.number().min(0).max(1),
  payout_compatibility_score: z.number().min(0).max(1),
  currency_compatibility_score: z.number().min(0).max(1),
  manual_review_required: z.boolean().default(false),
  notes: z.array(z.string().min(1)).default([]),
  }).superRefine((value, ctx) => {
  if (
    value.left_market_ref.venue === value.right_market_ref.venue &&
    value.left_market_ref.market_id === value.right_market_ref.market_id
  ) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['right_market_ref', 'market_id'],
      message: 'left and right market refs must point to distinct markets',
    })
  }
})

export const marketEquivalenceProofSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  proof_id: z.string().min(1),
  canonical_event_id: z.string().min(1),
  left_market_ref: crossVenueMarketRefSchema,
  right_market_ref: crossVenueMarketRefSchema,
  proof_status: z.enum(['blocked', 'partial', 'proven']),
  resolution_compatibility_score: z.number().min(0).max(1),
  payout_compatibility_score: z.number().min(0).max(1),
  currency_compatibility_score: z.number().min(0).max(1),
  timing_compatibility_score: z.number().min(0).max(1),
  manual_review_required: z.boolean().default(false),
  mismatch_reasons: z.array(z.string().min(1)).default([]),
  notes: z.array(z.string().min(1)).default([]),
})

export const predictionMarketOrderTraceAuditSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  trace_id: z.string().min(1).optional(),
  venue_order_status: z.string().min(1).optional(),
  venue_order_flow: z.string().min(1).optional(),
  transport_mode: z.string().min(1).optional(),
  venue_order_trace_kind: z.string().min(1).optional(),
  place_auditable: z.boolean().optional(),
  cancel_auditable: z.boolean().optional(),
  live_execution_status: z.string().min(1).optional(),
  market_execution_status: z.string().min(1).optional(),
  metadata: z.record(z.string(), z.unknown()).default({}),
}).passthrough()

export const predictionMarketPacketBundleSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  bundle_id: z.string().min(1),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  advisor_architecture: z.lazy(() => predictionMarketAdvisorArchitectureSchema).nullable().optional(),
  decision_packet: decisionPacketSchema.nullable().optional(),
  strategy_candidate_packet: z.lazy(() => strategyCandidatePacketSchema).nullable().optional(),
  strategy_decision_packet: z.lazy(() => strategyDecisionPacketSchema).nullable().optional(),
  strategy_shadow_report: z.lazy(() => strategyShadowReportSchema).nullable().optional(),
  evidence_packets: z.array(evidencePacketSchema).default([]),
  forecast_packet: z.lazy(() => forecastPacketSchema).nullable().optional(),
  recommendation_packet: z.lazy(() => marketRecommendationPacketSchema).nullable().optional(),
  research_bridge: z.lazy(() => researchBridgeBundleSchema).nullable().optional(),
  market_events: z.lazy(() => predictionMarketJsonArtifactSchema).nullable().optional(),
  market_positions: z.lazy(() => predictionMarketJsonArtifactSchema).nullable().optional(),
  paper_surface: z.lazy(() => predictionMarketJsonArtifactSchema).nullable().optional(),
  replay_surface: z.lazy(() => predictionMarketJsonArtifactSchema).nullable().optional(),
  order_trace_audit: z.lazy(() => predictionMarketOrderTraceAuditSchema).nullable().optional(),
  trade_intent_guard: z.lazy(() => tradeIntentGuardSchema).nullable().optional(),
  multi_venue_execution: z.lazy(() => multiVenueExecutionSchema).nullable().optional(),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const predictionMarketVenueCoverageSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  venue_count: z.number().int().nonnegative(),
  execution_capable_count: z.number().int().nonnegative(),
  paper_capable_count: z.number().int().nonnegative(),
  read_only_count: z.number().int().nonnegative(),
  degraded_venue_count: z.number().int().nonnegative(),
  degraded_venue_rate: z.number().min(0).max(1),
  execution_equivalent_count: z.number().int().nonnegative(),
  execution_like_count: z.number().int().nonnegative(),
  reference_only_count: z.number().int().nonnegative(),
  watchlist_only_count: z.number().int().nonnegative(),
  metadata_gap_count: z.number().int().nonnegative(),
  metadata_gap_rate: z.number().min(0).max(1),
  execution_surface_rate: z.number().min(0).max(1),
  availability_by_venue: z.record(z.string(), z.record(z.string(), z.unknown())).default({}),
})

export const executableEdgeSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  edge_id: z.string().min(1),
  canonical_event_id: z.string().min(1),
  opportunity_type: crossVenueOpportunityTypeSchema,
  buy_ref: crossVenueMarketRefSchema,
  sell_ref: crossVenueMarketRefSchema,
  buy_price_yes: z.number().min(0).max(1),
  sell_price_yes: z.number().min(0).max(1),
  gross_spread_bps: z.number(),
  fee_bps: z.number().nonnegative(),
  slippage_bps: z.number().nonnegative(),
  hedge_risk_bps: z.number().nonnegative(),
  executable_edge_bps: z.number(),
  confidence_score: z.number().min(0).max(1),
  executable: z.boolean(),
  evaluated_at: z.string().min(1),
  notes: z.array(z.string().min(1)).default([]),
})

export const arbPlanLegSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  leg_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  side: predictionMarketSideSchema,
  action: z.enum(['buy', 'sell']),
  price: z.number().min(0).max(1),
  size_usd: z.number().positive(),
  max_slippage_bps: z.number().int().nonnegative(),
  max_unhedged_leg_ms: z.number().int().nonnegative(),
})

export const arbPlanSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  arb_plan_id: z.string().min(1),
  canonical_event_id: z.string().min(1),
  opportunity_type: crossVenueOpportunityTypeSchema,
  executable_edge: executableEdgeSchema,
  legs: z.array(arbPlanLegSchema).min(1),
  required_capital_usd: z.number().nonnegative(),
  break_even_after_fees_bps: z.number(),
  max_unhedged_leg_ms: z.number().int().nonnegative(),
  exit_policy: z.string().min(1),
  manual_review_required: z.boolean().default(false),
  notes: z.array(z.string().min(1)).default([]),
})

export const predictionMarketMarketGraphRelationKindSchema = z.enum([
  'same_event',
  'same_question',
  'same_topic',
  'reference',
  'comparison',
])

export const predictionMarketMarketGraphNodeSchema = z.object({
  schema_version: z.string().default('v1'),
  node_id: z.string().min(1),
  market_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  venue_type: predictionMarketVenueTypeSchema,
  title: z.string().min(1),
  question: z.string().min(1),
  canonical_event_id: z.string().min(1).nullable().optional(),
  status: z.string().min(1).default('unknown'),
  role: z.string().min(1).default('comparison'),
  clarity_score: z.number().min(0).max(1),
  liquidity: z.number().nullable().optional(),
  price_yes: z.number().nullable().optional(),
  snapshot_id: z.string().min(1).nullable().optional(),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const predictionMarketMarketGraphEdgeSchema = z.object({
  schema_version: z.string().default('v1'),
  edge_id: z.string().min(1),
  source_node_id: z.string().min(1),
  target_node_id: z.string().min(1),
  relation: predictionMarketMarketGraphRelationKindSchema,
  similarity: z.number().min(0).max(1),
  compatible_resolution: z.boolean().default(false),
  rationale: z.string().min(1),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const predictionMarketCrossVenueMatchRejectionSchema = z.object({
  schema_version: z.string().default('v1'),
  rejection_id: z.string().min(1),
  left_market_id: z.string().min(1),
  right_market_id: z.string().min(1),
  left_venue: predictionMarketVenueSchema,
  right_venue: predictionMarketVenueSchema,
  canonical_event_id: z.string().min(1),
  question_left: z.string().default(''),
  question_right: z.string().default(''),
  question_key: z.string().default(''),
  similarity: z.number().min(0).max(1),
  reason_codes: z.array(z.string().min(1)).default([]),
  rationale: z.string().default(''),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const predictionMarketComparableMarketGroupSchema = z.object({
  schema_version: z.string().default('v1'),
  group_id: z.string().min(1),
  canonical_event_id: z.string().min(1),
  question_key: z.string().min(1),
  question: z.string().default(''),
  relation_kind: predictionMarketMarketGraphRelationKindSchema.default('comparison'),
  market_ids: z.array(z.string().min(1)).default([]),
  comparable_market_refs: z.array(z.string().min(1)).default([]),
  venues: z.array(z.string().min(1)).default([]),
  venue_types: z.array(z.string().min(1)).default([]),
  reference_market_ids: z.array(z.string().min(1)).default([]),
  comparison_market_ids: z.array(z.string().min(1)).default([]),
  parent_market_ids: z.array(z.string().min(1)).default([]),
  child_market_ids: z.array(z.string().min(1)).default([]),
  parent_child_pairs: z.array(z.record(z.string(), z.unknown())).default([]),
  natural_hedge_market_ids: z.array(z.string().min(1)).default([]),
  natural_hedge_pairs: z.array(z.record(z.string(), z.unknown())).default([]),
  resolution_sources: z.array(z.string().min(1)).default([]),
  currencies: z.array(z.string().min(1)).default([]),
  payout_currencies: z.array(z.string().min(1)).default([]),
  notes: z.array(z.string().min(1)).default([]),
  manual_review_required: z.boolean().default(false),
  compatible_resolution: z.boolean().default(false),
  compatible_currency: z.boolean().default(false),
  compatible_payout: z.boolean().default(false),
  match_count: z.number().int().nonnegative(),
  duplicate_market_count: z.number().int().nonnegative(),
  duplicate_market_rate: z.number().min(0).max(1),
  desalignment_count: z.number().int().nonnegative(),
  desalignment_rate: z.number().min(0).max(1),
  desalignment_dimensions: z.array(z.string().min(1)).default([]),
  narrative_risk_flags: z.array(z.string().min(1)).default([]),
  rationale: z.string().default(''),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const predictionMarketMarketGraphSchema = z.object({
  schema_version: z.string().default('v1'),
  graph_id: z.string().min(1),
  nodes: z.array(predictionMarketMarketGraphNodeSchema).default([]),
  edges: z.array(predictionMarketMarketGraphEdgeSchema).default([]),
  matches: z.array(crossVenueMatchSchema).default([]),
  rejected_matches: z.array(predictionMarketCrossVenueMatchRejectionSchema).default([]),
  comparable_groups: z.array(predictionMarketComparableMarketGroupSchema).default([]),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const venueCapabilitiesSchema = z.preprocess((value) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value

  const raw = value as Record<string, unknown>
  return {
    ...raw,
    automation_constraints: Array.isArray(raw.automation_constraints)
      ? raw.automation_constraints
      : typeof raw.automation_constraints === 'string' && raw.automation_constraints.trim().length > 0
        ? [raw.automation_constraints]
        : raw.automation_constraints,
    planned_order_types: Array.isArray(raw.planned_order_types)
      ? raw.planned_order_types
      : typeof raw.planned_order_types === 'string' && raw.planned_order_types.trim().length > 0
        ? [raw.planned_order_types]
        : raw.planned_order_types,
  }
}, z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  venue: predictionMarketVenueSchema,
  venue_type: predictionMarketVenueTypeSchema,
  supports_discovery: z.boolean(),
  supports_metadata: z.boolean().default(true),
  supports_orderbook: z.boolean(),
  supports_trades: z.boolean(),
  supports_positions: z.boolean(),
  supports_execution: z.boolean(),
  supports_websocket: z.boolean(),
  supports_paper_mode: z.boolean().default(false),
  tradeable: z.boolean().optional(),
  manual_review_required: z.boolean().optional(),
  supported_order_types: z.array(z.string().min(1)).default([]),
  planned_order_types: z.array(z.string().min(1)).default([]),
  rate_limit_notes: z.string().min(1).optional(),
  automation_constraints: z.array(z.string().min(1)).default([]),
  last_verified_at: z.string().optional(),
  metadata: z.record(z.string(), z.unknown()).default({}),
}))

export const marketFeedSurfaceSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  venue: predictionMarketVenueSchema,
  venue_type: predictionMarketVenueTypeSchema.nullable().optional(),
  backend_mode: z.string().min(1),
  ingestion_mode: z.string().min(1),
  market_feed_kind: z.string().min(1),
  user_feed_kind: z.string().min(1),
  supports_discovery: z.boolean(),
  supports_orderbook: z.boolean(),
  supports_trades: z.boolean(),
  supports_execution: z.boolean(),
  supports_paper_mode: z.boolean(),
  supports_market_feed: z.boolean(),
  supports_user_feed: z.boolean(),
  supports_events: z.boolean(),
  supports_positions: z.boolean(),
  supports_websocket: z.boolean(),
  supports_rtds: z.boolean(),
  live_streaming: z.boolean(),
  websocket_status: z.string().min(1).default('unavailable'),
  market_websocket_status: z.string().min(1).default('unavailable'),
  user_feed_websocket_status: z.string().min(1).default('unavailable'),
  tradeable: z.boolean().optional(),
  manual_review_required: z.boolean().optional(),
  api_access: z.array(z.string().min(1)).default([]),
  planned_order_types: z.array(z.string().min(1)).default([]),
  supported_order_types: z.array(z.string().min(1)).default([]),
  rate_limit_notes: z.array(z.string().min(1)).default([]),
  automation_constraints: z.array(z.string().min(1)).default([]),
  market_feed_transport: predictionMarketFeedTransportSchema,
  user_feed_transport: predictionMarketFeedTransportSchema,
  market_feed_status: z.string().min(1),
  user_feed_status: z.string().min(1),
  rtds_status: z.string().min(1),
  events_source: z.string().min(1).nullable().optional(),
  positions_source: z.string().min(1).nullable().optional(),
  market_feed_source: z.string().min(1).nullable().optional(),
  user_feed_source: z.string().min(1).nullable().optional(),
  configured_endpoints: z.record(z.string(), z.string()).default({}),
  summary: z.string().min(1),
  runbook: z.record(z.string(), z.unknown()).default({}),
  notes: z.array(z.string().min(1)).default([]),
  metadata_gap_count: z.number().int().nonnegative(),
  metadata_gap_rate: z.number().min(0).max(1),
  metadata_completeness: z.number().min(0).max(1),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const venueHealthSnapshotSchema = z.preprocess((value) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value

  const raw = value as Record<string, unknown>
  const normalizeStatus = (status: unknown) => {
    if (status === 'ok') return 'healthy'
    if (status === 'down') return 'blocked'
    return status
  }
  const rawHealthScore = typeof raw.health_score === 'number' ? raw.health_score : Number(raw.health_score)
  const normalizedHealthScore = Number.isFinite(rawHealthScore) && rawHealthScore > 1 && rawHealthScore <= 100
    ? rawHealthScore / 100
    : raw.health_score

  return {
    ...raw,
    health_score: normalizedHealthScore,
    api_status: normalizeStatus(raw.api_status),
    stream_status: normalizeStatus(raw.stream_status),
    degraded_mode: typeof raw.degraded_mode === 'boolean'
      ? (raw.degraded_mode ? 'degraded' : 'normal')
      : raw.degraded_mode,
  }
}, z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  venue: predictionMarketVenueSchema,
  captured_at: z.string().min(1),
  health_score: z.number().min(0).max(1),
  api_status: predictionMarketHealthStatusSchema,
  stream_status: predictionMarketHealthStatusSchema,
  staleness_ms: z.number().int().nonnegative(),
  degraded_mode: predictionMarketDegradedModeSchema.default('normal'),
  incident_flags: z.array(z.string().min(1)).default([]),
  notes: z.string().optional(),
  metadata: z.record(z.string(), z.unknown()).default({}),
}))

export const capitalLedgerSnapshotSchema = z.preprocess((value) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value

  const raw = value as Record<string, unknown>
  return {
    ...raw,
    cash_available: raw.cash_available ?? raw.cash_available_usd,
    cash_locked: raw.cash_locked ?? raw.cash_locked_usd,
    withdrawable_amount: raw.withdrawable_amount ?? raw.withdrawable_amount_usd,
  }
}, z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  captured_at: z.string().min(1),
  venue: predictionMarketVenueSchema,
  cash_available: z.number().nonnegative(),
  cash_locked: z.number().nonnegative(),
  collateral_currency: z.string().min(1),
  open_exposure_usd: z.number().nonnegative(),
  withdrawable_amount: z.number().nonnegative(),
  transfer_latency_estimate_ms: z.number().int().nonnegative(),
}))

export const forecastBasisSchema = z.enum([
  'market_midpoint',
  'manual_thesis',
  'timesfm_microstructure',
  'timesfm_event_probability',
])
export const forecastBenchmarkComparatorKindSchema = z.enum([
  'market_only',
  'baseline_model',
  'candidate_model',
  'single_llm',
  'ensemble',
  'decision_packet_assisted',
  'external_reference',
])
export const forecastBenchmarkComparatorRoleSchema = z.enum(['baseline', 'candidate', 'reference'])
export const forecastPipelineStageNameSchema = z.enum([
  'base_rates',
  'retrieval',
  'independent_forecasts',
  'calibration',
  'abstention',
])
export const forecastPipelineStageModeSchema = z.enum(['local', 'signal_reference', 'spec_only'])
export const forecastAbstentionReasonSchema = z.enum([
  'policy_threshold',
  'low_confidence',
  'calibration_guard',
  'evidence_gap',
  'market_too_close',
  'manual_review',
  'unknown',
])

export const forecastBenchmarkComparatorSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  comparator_id: z.string().min(1),
  label: z.string().min(1),
  kind: forecastBenchmarkComparatorKindSchema,
  role: forecastBenchmarkComparatorRoleSchema.default('candidate'),
  basis: forecastBasisSchema.optional(),
  model_family: z.string().min(1).optional(),
  pipeline_id: z.string().min(1).optional(),
  pipeline_version: z.string().min(1).optional(),
  source: z.enum(['local', 'external', 'hybrid']).default('local'),
  notes: z.array(z.string().min(1)).default([]),
  source_refs: z.array(z.string().min(1)).default([]),
})

export const forecastPipelineStageConfigSchema = z.object({
  stage: forecastPipelineStageNameSchema,
  mode: forecastPipelineStageModeSchema.default('local'),
  enabled: z.boolean().default(true),
  implementation: z.string().min(1).optional(),
  version: z.string().min(1).optional(),
  comparator_id: z.string().min(1).optional(),
  notes: z.array(z.string().min(1)).default([]),
})

export const forecastPipelineVersionSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  pipeline_id: z.string().min(1),
  pipeline_version: z.string().min(1),
  label: z.string().min(1),
  model_family: z.string().min(1),
  status: z.enum(['candidate', 'baseline', 'reference_only', 'deprecated']).default('candidate'),
  benchmark_scope: z.string().min(1).optional(),
  abstention_policy: z.string().min(1).optional(),
  comparator_ids: z.array(z.string().min(1)).default([]),
  stages: z.array(forecastPipelineStageConfigSchema).min(1),
  created_at: z.string().min(1),
  notes: z.array(z.string().min(1)).default([]),
})

export const forecastEvaluationRecordSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  evaluation_id: z.string().min(1),
  question_id: z.string().min(1),
  market_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  cutoff_at: z.string().min(1),
  forecast_probability: z.number().min(0).max(1),
  market_baseline_probability: z.number().min(0).max(1),
  resolved_outcome: z.boolean().nullable().optional(),
  brier_score: z.number().min(0).nullable().optional(),
  log_loss: z.number().min(0).nullable().optional(),
  ece_bucket: z.string().min(1),
  abstain_flag: z.boolean().default(false),
  basis: forecastBasisSchema.optional(),
  comparison_label: z.string().min(1).optional(),
  comparator_id: z.string().min(1).optional(),
  comparator_kind: forecastBenchmarkComparatorKindSchema.optional(),
  comparator_role: forecastBenchmarkComparatorRoleSchema.optional(),
  pipeline_id: z.string().min(1).optional(),
  pipeline_version: z.string().min(1).optional(),
  abstention_reason: forecastAbstentionReasonSchema.optional(),
})

export const predictionMarketResearchComparativeSummarySchema = z.object({
  probability_yes: z.number().min(0).max(1).nullable(),
  delta_bps_vs_market_only: z.number().nullable(),
  rationale: z.string().min(1),
})

export const predictionMarketResearchForecastComparativeSummarySchema = z.object({
  forecast_probability_yes: z.number().min(0).max(1).nullable(),
  delta_bps_vs_market_only: z.number().nullable(),
  delta_bps_vs_aggregate: z.number().nullable(),
  rationale: z.string().min(1),
})

export const predictionMarketResearchAggregateComparativeSummarySchema =
  predictionMarketResearchComparativeSummarySchema.extend({
    coverage: z.number().min(0).max(1),
    contributor_count: z.number().int().nonnegative(),
    usable_contributor_count: z.number().int().nonnegative(),
  })

export const predictionMarketResearchAbstentionComparativeSummarySchema = z.object({
  recommended: z.boolean(),
  blocks_forecast: z.boolean(),
  reason_codes: z.array(z.string().min(1)).default([]),
  rationale: z.string().min(1),
})

export const predictionMarketResearchComparativeReportSchema = z.object({
  market_only: predictionMarketResearchComparativeSummarySchema,
  aggregate: predictionMarketResearchAggregateComparativeSummarySchema,
  forecast: predictionMarketResearchForecastComparativeSummarySchema,
  abstention: predictionMarketResearchAbstentionComparativeSummarySchema,
  summary: z.string().min(1),
})

export const predictionMarketResearchAbstentionPolicySchema = z.object({
  policy_id: z.string().min(1),
  policy_version: z.string().min(1),
  recommended: z.boolean(),
  blocks_forecast: z.boolean(),
  trigger_codes: z.array(z.string().min(1)).default([]),
  rationale: z.string().min(1),
  thresholds: z.object({
    minimum_signal_count: z.number().int().nonnegative(),
    minimum_supportive_margin_bps: z.number().int().nonnegative(),
    minimum_manual_thesis_probability: z.number().min(0).max(1),
    minimum_contributor_coverage: z.number().min(0).max(1),
  }),
})

export const predictionMarketResearchPipelineStageStatusSchema = z.enum([
  'queued',
  'running',
  'complete',
  'partial',
  'blocked',
])

export const predictionMarketResearchPipelineStageSchema = z.object({
  stage_id: z.string().min(1),
  stage_kind: z.string().min(1),
  status: predictionMarketResearchPipelineStageStatusSchema,
  model_family: z.string().min(1).optional(),
  prompt_ref: z.string().min(1).optional(),
  input_refs: z.array(z.string().min(1)).default([]),
  output_refs: z.array(z.string().min(1)).default([]),
  signal_refs: z.array(z.string().min(1)).default([]),
  evidence_refs: z.array(z.string().min(1)).default([]),
  probability_yes: z.number().min(0).max(1).nullable().optional(),
  confidence: z.number().min(0).max(1).nullable().optional(),
  rationale: z.string().min(1).optional(),
  summary: z.string().min(1),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const predictionMarketResearchPipelineTraceSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  trace_id: z.string().min(1),
  pipeline_id: z.string().min(1),
  pipeline_version: z.string().min(1),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  model_family: z.string().min(1),
  started_at: z.string().min(1),
  completed_at: z.string().min(1).nullable().optional(),
  stage_count: z.number().int().nonnegative(),
  stages: z.array(predictionMarketResearchPipelineStageSchema).default([]),
  current_stage_id: z.string().min(1).optional(),
  terminal_stage_id: z.string().min(1).optional(),
  summary: z.string().min(1),
  key_factors: z.array(z.string().min(1)).default([]),
  source_refs: z.array(z.string().min(1)).default([]),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const predictionMarketResearchPipelineSummarySchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  summary_id: z.string().min(1),
  trace_id: z.string().min(1),
  pipeline_id: z.string().min(1),
  pipeline_version: z.string().min(1),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  model_family: z.string().min(1),
  generated_at: z.string().min(1),
  forecaster_count: z.number().int().nonnegative(),
  contributor_count: z.number().int().nonnegative(),
  signal_count: z.number().int().nonnegative(),
  evidence_count: z.number().int().nonnegative(),
  stage_count: z.number().int().nonnegative(),
  base_rate_probability_yes: z.number().min(0).max(1),
  aggregate_probability_yes: z.number().min(0).max(1).nullable().optional(),
  forecast_probability_yes: z.number().min(0).max(1).nullable().optional(),
  abstention_recommended: z.boolean(),
  key_factors: z.array(z.string().min(1)).default([]),
  caveats: z.array(z.string().min(1)).default([]),
  summary: z.string().min(1),
  source_refs: z.array(z.string().min(1)).default([]),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const calibrationSnapshotSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  snapshot_id: z.string().min(1),
  model_family: z.string().min(1),
  market_family: z.string().min(1),
  horizon_bucket: z.string().min(1),
  window_start: z.string().min(1),
  window_end: z.string().min(1),
  calibration_method: z.string().min(1),
  ece: z.number().min(0).max(1),
  sharpness: z.number().min(0).max(1),
  coverage: z.number().min(0).max(1),
  sample_size: z.number().int().nonnegative().optional(),
  comparator_id: z.string().min(1).optional(),
  pipeline_id: z.string().min(1).optional(),
  pipeline_version: z.string().min(1).optional(),
})

export const asOfEvidenceSetSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  evidence_set_id: z.string().min(1),
  market_id: z.string().min(1),
  cutoff_at: z.string().min(1),
  evidence_refs: z.array(z.string().min(1)).default([]),
  market_only_evidence_refs: z.array(z.string().min(1)).default([]),
  candidate_evidence_refs: z.array(z.string().min(1)).default([]),
  retrieval_policy: z.string().min(1),
  freshness_summary: z.string().min(1),
  provenance_summary: z.string().min(1),
  comparison_label: z.string().min(1).optional(),
  comparator_id: z.string().min(1).optional(),
  pipeline_id: z.string().min(1).optional(),
  pipeline_version: z.string().min(1).optional(),
})

export const tradeIntentSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  intent_id: z.string().min(1),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  side: predictionMarketSideSchema,
  size_usd: z.number().positive(),
  limit_price: z.number().min(0).max(1),
  max_slippage_bps: z.number().int().nonnegative(),
  max_unhedged_leg_ms: z.number().int().nonnegative(),
  time_in_force: predictionMarketTimeInForceSchema.default('gtc'),
  forecast_ref: z.string().min(1),
  risk_checks_passed: z.boolean(),
  created_at: z.string().min(1),
  notes: z.string().optional(),
})

export const predictionMarketApprovalTicketApprovalStatusSchema = z.enum([
  'pending',
  'pending_second_approval',
  'approved',
  'rejected',
  'blocked',
  'executed',
])

export const predictionMarketApprovalTicketApprovalStateSchema = z.object({
  status: predictionMarketApprovalTicketApprovalStatusSchema,
  requested_by: z.string().min(1),
  requested_at: z.string().min(1),
  required_approvals: z.number().int().positive().default(2),
  current: z.number().int().nonnegative().default(0),
  approvers: z.array(z.string().min(1)).default([]),
  rejections: z.array(z.string().min(1)).default([]),
  approved_at: z.string().min(1).nullable().optional(),
  rejected_at: z.string().min(1).nullable().optional(),
  summary: z.string().min(1),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const approvalTradeTicketSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  ticket_id: z.string().min(1),
  ticket_kind: z.literal('approval_trade_ticket').default('approval_trade_ticket'),
  workflow_stage: z.enum(['approval', 'trade', 'approved_trade', 'blocked']).default('approval'),
  run_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  market_slug: z.string().min(1).optional(),
  source_bundle_id: z.string().min(1).optional(),
  source_packet_refs: z.array(z.string().min(1)).default([]),
  social_context_refs: z.array(z.string().min(1)).default([]),
  market_context_refs: z.array(z.string().min(1)).default([]),
  recommendation: predictionMarketRecommendationActionSchema.optional(),
  side: predictionMarketSideSchema.nullable().optional(),
  size_usd: z.number().positive().optional(),
  limit_price: z.number().min(0).max(1).optional(),
  edge_bps: z.number().nullable().optional(),
  spread_bps: z.number().nullable().optional(),
  confidence: z.number().min(0).max(1).optional(),
  rationale: z.string().min(1),
  summary: z.string().min(1),
  approval_state: predictionMarketApprovalTicketApprovalStateSchema,
  trade_intent_preview: z.lazy(() => tradeIntentSchema).nullable().optional(),
  execution_intent_preview: z.lazy(() => executionIntentPreviewSchema).nullable().optional(),
  approved_trade_intent_ref: z.string().min(1).optional(),
  approved_by: z.array(z.string().min(1)).default([]),
  rejected_by: z.array(z.string().min(1)).default([]),
  notes: z.array(z.string().min(1)).default([]),
  created_at: z.string().min(1),
  updated_at: z.string().min(1).optional(),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const tradeIntentGuardSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  gate_name: z.literal('trade_intent_guard'),
  verdict: tradeIntentGuardVerdictSchema,
  manual_review_required: z.boolean(),
  blocked_reasons: z.array(z.string().min(1)).default([]),
  warning_reasons: z.array(z.string().min(1)).default([]),
  snapshot_staleness_ms: z.number().int().nonnegative().nullable(),
  edge_after_fees_bps: z.number().nullable(),
  venue_health_status: predictionMarketHealthStatusSchema,
  projection_verdict: executionProjectionVerdictSchema.nullable(),
  readiness_route: z.string().nullable(),
  selected_path: z.string().nullable().optional(),
  highest_safe_mode: z.string().nullable().optional(),
  trade_intent_preview: tradeIntentSchema.nullable().optional(),
  summary: z.string().min(1),
  source_refs: z.record(z.string(), z.string()).default({}),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const multiVenueExecutionSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  gate_name: z.literal('multi_venue_execution'),
  report_id: z.string().nullable().optional(),
  taxonomy: crossVenueTaxonomySchema.nullable().optional(),
  execution_filter_reason_codes: z.array(z.string().min(1)).default([]),
  execution_filter_reason_code_counts: z.record(z.string(), z.number().int().nonnegative()).default({}),
  market_count: z.number().int().nonnegative(),
  comparable_group_count: z.number().int().nonnegative(),
  execution_candidate_count: z.number().int().nonnegative(),
  execution_plan_count: z.number().int().nonnegative(),
  tradeable_plan_count: z.number().int().nonnegative(),
  execution_routes: z.record(z.string(), z.number().int().nonnegative()).default({}),
  tradeable_market_ids: z.array(z.string().min(1)).default([]),
  read_only_market_ids: z.array(z.string().min(1)).default([]),
  reference_market_ids: z.array(z.string().min(1)).default([]),
  signal_market_ids: z.array(z.string().min(1)).default([]),
  execution_market_ids: z.array(z.string().min(1)).default([]),
  summary: z.string().min(1),
  source_refs: z.record(z.string(), z.string()).default({}),
  metadata: z.record(z.string(), z.unknown()).default({}),
})

export const forecastPacketSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  packet_version: z.string().min(1).default('1.0.0'),
  packet_kind: z.literal('forecast').default('forecast'),
  compatibility_mode: predictionMarketPacketCompatibilityModeSchema.default('market_only'),
  market_only_compatible: z.boolean().default(true),
  contract_id: z.string().min(1).optional(),
  source_bundle_id: z.string().min(1).optional(),
  source_packet_refs: z.array(z.string().min(1)).default([]),
  social_context_refs: z.array(z.string().min(1)).default([]),
  market_context_refs: z.array(z.string().min(1)).default([]),
  market_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  basis: forecastBasisSchema,
  model: z.string().default(PREDICTION_MARKETS_BASELINE_MODEL),
  probability_yes: z.number().min(0).max(1),
  confidence: z.number().min(0).max(1),
  rationale: z.string().min(1),
  evidence_refs: z.array(z.string().min(1)).default([]),
  comparator_id: z.string().min(1).optional(),
  comparator_kind: forecastBenchmarkComparatorKindSchema.optional(),
  pipeline_id: z.string().min(1).optional(),
  pipeline_version: z.string().min(1).optional(),
  abstention_policy: z.string().min(1).optional(),
  abstention_reason: forecastAbstentionReasonSchema.optional(),
  resolution_policy_ref: z.string().min(1).optional(),
  comparable_market_refs: z.array(z.string().min(1)).default([]),
  requires_manual_review: z.boolean().default(false),
  produced_at: z.string().min(1),
})

export const marketRecommendationPacketSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  packet_version: z.string().min(1).default('1.0.0'),
  packet_kind: z.literal('recommendation').default('recommendation'),
  compatibility_mode: predictionMarketPacketCompatibilityModeSchema.default('market_only'),
  market_only_compatible: z.boolean().default(true),
  contract_id: z.string().min(1).optional(),
  source_bundle_id: z.string().min(1).optional(),
  source_packet_refs: z.array(z.string().min(1)).default([]),
  social_context_refs: z.array(z.string().min(1)).default([]),
  market_context_refs: z.array(z.string().min(1)).default([]),
  market_id: z.string().min(1),
  venue: predictionMarketVenueSchema,
  action: predictionMarketRecommendationActionSchema,
  side: predictionMarketSideSchema.nullable(),
  confidence: z.number().min(0).max(1),
  fair_value_yes: z.number().min(0).max(1),
  market_price_yes: z.number().min(0).max(1).nullable(),
  market_bid_yes: z.number().min(0).max(1).nullable(),
  market_ask_yes: z.number().min(0).max(1).nullable(),
  edge_bps: z.number(),
  spread_bps: z.number().nullable(),
  reasons: z.array(z.string()).default([]),
  risk_flags: z.array(z.string()).default([]),
  rationale: z.string().min(1).optional(),
  why_now: z.array(z.string().min(1)).default([]),
  why_not_now: z.array(z.string().min(1)).default([]),
  watch_conditions: z.array(z.string().min(1)).default([]),
  resolution_policy_ref: z.string().min(1).optional(),
  comparable_market_refs: z.array(z.string().min(1)).default([]),
  requires_manual_review: z.boolean().default(false),
  next_review_at: z.string().min(1).optional(),
  produced_at: z.string().min(1),
})

export type ForecastEvaluationRecord = z.infer<typeof forecastEvaluationRecordSchema>
export type PredictionMarketResearchComparativeSummary = z.infer<
  typeof predictionMarketResearchComparativeSummarySchema
>
export type PredictionMarketResearchForecastComparativeSummary = z.infer<
  typeof predictionMarketResearchForecastComparativeSummarySchema
>
export type PredictionMarketResearchAggregateComparativeSummary = z.infer<
  typeof predictionMarketResearchAggregateComparativeSummarySchema
>
export type PredictionMarketResearchAbstentionComparativeSummary = z.infer<
  typeof predictionMarketResearchAbstentionComparativeSummarySchema
>
export type PredictionMarketResearchComparativeReport = z.infer<
  typeof predictionMarketResearchComparativeReportSchema
>
export type PredictionMarketResearchAbstentionPolicy = z.infer<
  typeof predictionMarketResearchAbstentionPolicySchema
>
export type CalibrationSnapshot = z.infer<typeof calibrationSnapshotSchema>
export type AsOfEvidenceSet = z.infer<typeof asOfEvidenceSetSchema>
export type ForecastBenchmarkComparator = z.infer<typeof forecastBenchmarkComparatorSchema>
export type ForecastPipelineStageConfig = z.infer<typeof forecastPipelineStageConfigSchema>
export type ForecastPipelineVersion = z.infer<typeof forecastPipelineVersionSchema>

export const predictionMarketArtifactRefSchema = z.object({
  artifact_id: z.string().min(1),
  artifact_type: predictionMarketArtifactTypeSchema,
  sha256: z.string().min(1),
  layout_version: z.string().min(1).optional(),
  bucket: z.string().min(1).optional(),
  file_name: z.string().min(1).optional(),
  run_key: z.string().min(1).optional(),
  market_key: z.string().min(1).optional(),
  latest_key: z.string().min(1).optional(),
})

export const predictionMarketJsonArtifactSchema = z.record(z.string(), z.unknown())

export const runManifestSchema = z.object({
  schema_version: z.string().default(PREDICTION_MARKETS_SCHEMA_VERSION),
  run_id: z.string().min(1),
  source_run_id: z.string().optional(),
  mode: predictionMarketModeSchema,
  venue: predictionMarketVenueSchema,
  market_id: z.string().min(1),
  market_slug: z.string().optional(),
  actor: z.string().default('system'),
  started_at: z.string().min(1),
  completed_at: z.string().optional(),
  status: z.enum(['running', 'completed', 'failed']),
  config_hash: z.string().min(1),
  artifact_refs: z.array(predictionMarketArtifactRefSchema).default([]),
})

export const predictionMarketRunSummarySchema = z.object({
  run_id: z.string().min(1),
  source_run_id: z.string().nullable().optional(),
  workspace_id: z.number().int().positive(),
  venue: predictionMarketVenueSchema,
  mode: predictionMarketModeSchema,
  market_id: z.string().min(1),
  market_slug: z.string().nullable().optional(),
  status: z.enum(['running', 'completed', 'failed']),
  recommendation: predictionMarketRecommendationActionSchema.nullable(),
  side: predictionMarketSideSchema.nullable(),
  confidence: z.number().nullable(),
  probability_yes: z.number().nullable(),
  market_price_yes: z.number().nullable(),
  edge_bps: z.number().nullable(),
  created_at: z.number().int().nonnegative(),
  updated_at: z.number().int().nonnegative(),
  manifest: runManifestSchema,
  artifact_refs: z.array(predictionMarketArtifactRefSchema).default([]),
})

export const predictionMarketsQuerySchema = z.object({
  venue: predictionMarketVenueSchema.default('polymarket'),
  search: z.string().trim().min(1).optional(),
  recommendation: predictionMarketRecommendationActionSchema.optional(),
  limit: z.number().int().min(1).max(100).default(20),
})

export const predictionMarketsAdviceRequestSchema = z.object({
  venue: predictionMarketVenueSchema.default('polymarket'),
  market_id: z.string().trim().min(1).optional(),
  slug: z.string().trim().min(1).optional(),
  request_mode: z.preprocess((value) => {
    if (value == null || value === '') return undefined
    const normalized = String(value).trim().toLowerCase()
    if (normalized === 'predict-deep' || normalized === 'predict_deep' || normalized === 'deep') {
      return 'predict_deep'
    }
    return normalized
  }, predictionMarketAdviceRequestModeSchema.optional()),
  response_variant: z.preprocess((value) => {
    if (value == null || value === '') return undefined
    const normalized = String(value).trim().toLowerCase()
    if (normalized === 'research-heavy' || normalized === 'research_heavy' || normalized === 'deep') {
      return 'research_heavy'
    }
    if (normalized === 'execution-heavy' || normalized === 'execution_heavy') {
      return 'execution_heavy'
    }
    return normalized
  }, predictionMarketAdviceResponseVariantSchema.optional()),
  strategy_profile: z.preprocess((value) => {
    if (value == null || value === '' || value === 'default') return 'hybrid'
    return value
  }, z.enum(['forecast_only', 'execution_only', 'hybrid']).default('hybrid')),
  variant_tags: z.array(z.string().trim().min(1)).max(12).default([]),
  enabled_strategy_families: z.array(strategyFamilySchema).default([...DEFAULT_ENABLED_STRATEGY_FAMILIES]),
  thesis_probability: z.number().min(0).max(1).optional(),
  thesis_rationale: z.string().trim().min(1).max(4000).optional(),
  min_edge_bps: z.number().min(1).max(10_000).optional(),
  max_spread_bps: z.number().min(1).max(10_000).optional(),
  history_limit: z.number().int().min(0).max(500).optional(),
  timesfm_mode: predictionMarketTimesFMModeSchema.optional(),
  timesfm_lanes: z.array(predictionMarketTimesFMLaneSchema).min(1).max(2).optional(),
  evaluation_history: z.array(forecastEvaluationRecordSchema).max(1_000).optional(),
  research_signals: z.array(z.record(z.string(), z.unknown())).max(100).optional(),
  decision_packet: z.preprocess((value) => {
    if (value == null || value === '') return undefined
    return value
  }, decisionPacketSchema.optional()),
}).superRefine((value, ctx) => {
  if (!value.market_id && !value.slug) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['market_id'],
      message: 'market_id or slug is required',
    })
  }
})

export const predictionMarketsReplayRequestSchema = z.object({
  run_id: z.string().trim().min(1),
})

export type MarketDescriptor = z.infer<typeof marketDescriptorSchema>
export type PredictionMarketVenue = z.infer<typeof predictionMarketVenueSchema>
export type PredictionMarketSide = z.infer<typeof predictionMarketSideSchema>
export type PredictionMarketVenueType = z.infer<typeof predictionMarketVenueTypeSchema>
export type PredictionMarketAdviceRequestMode = z.infer<typeof predictionMarketAdviceRequestModeSchema>
export type PredictionMarketAdviceResponseVariant = z.infer<typeof predictionMarketAdviceResponseVariantSchema>
export type PredictionMarketTimesFMMode = z.infer<typeof predictionMarketTimesFMModeSchema>
export type PredictionMarketTimesFMLane = z.infer<typeof predictionMarketTimesFMLaneSchema>
export type PredictionMarketHealthStatus = z.infer<typeof predictionMarketHealthStatusSchema>
export type VenueHealthStatus = z.infer<typeof venueHealthStatusSchema>
export type PredictionMarketDegradedMode = z.infer<typeof predictionMarketDegradedModeSchema>
export type VenueDegradedMode = z.infer<typeof venueDegradedModeSchema>
export type PredictionMarketTimeInForce = z.infer<typeof predictionMarketTimeInForceSchema>
export type TradeIntentTimeInForce = z.infer<typeof tradeIntentTimeInForceSchema>
export type ExecutionProjectionVerdict = z.infer<typeof executionProjectionVerdictSchema>
export type TradeIntentGuardVerdict = z.infer<typeof tradeIntentGuardVerdictSchema>
export type PredictionMarketProbabilityBand = z.infer<typeof predictionMarketProbabilityBandSchema>
export type PredictionMarketPacketContract = z.infer<typeof predictionMarketPacketContractSchema>
export type PredictionMarketAdvisorStageStatus = z.infer<typeof predictionMarketAdvisorStageStatusSchema>
export type PredictionMarketAdvisorStage = z.infer<typeof predictionMarketAdvisorStageSchema>
export type PredictionMarketAdvisorArchitecture = z.infer<typeof predictionMarketAdvisorArchitectureSchema>
export type ResolutionPolicy = z.infer<typeof resolutionPolicySchema>
export type MarketSnapshot = z.infer<typeof marketSnapshotSchema>
export type EvidencePacket = z.infer<typeof evidencePacketSchema>
export type DecisionPacket = z.infer<typeof decisionPacketSchema>
export type DecisionPacketScenario = z.infer<typeof decisionPacketScenarioSchema>
export type DecisionPacketRisk = z.infer<typeof decisionPacketRiskSchema>
export type DecisionPacketArtifact = z.infer<typeof decisionPacketArtifactSchema>
export type StrategyFamily = z.infer<typeof strategyFamilySchema>
export type MarketRegime = z.infer<typeof marketRegimeSchema>
export type ExecutionQuoteLeg = z.infer<typeof executionQuoteLegSchema>
export type BasketIntentLeg = z.infer<typeof basketIntentLegSchema>
export type QuotePairIntentPreview = z.infer<typeof quotePairIntentPreviewSchema>
export type BasketIntentPreview = z.infer<typeof basketIntentPreviewSchema>
export type ExecutionIntentPreview = z.infer<typeof executionIntentPreviewSchema>
export type LatencyReferenceBundle = z.infer<typeof latencyReferenceBundleSchema>
export type ResolutionAnomalyReport = z.infer<typeof resolutionAnomalyReportSchema>
export type AutonomousAgentReport = z.infer<typeof autonomousAgentReportSchema>
export type StrategyShadowSummary = z.infer<typeof strategyShadowSummarySchema>
export type StrategyShadowReport = z.infer<typeof strategyShadowReportSchema>
export type StrategyCandidatePacket = z.infer<typeof strategyCandidatePacketSchema>
export type StrategyDecisionPacket = z.infer<typeof strategyDecisionPacketSchema>
export type PredictionMarketProvenanceLink = z.infer<typeof predictionMarketProvenanceLinkSchema>
export type PredictionMarketProvenanceBundle = z.infer<typeof predictionMarketProvenanceBundleSchema>
export type PredictionMarketResearchProvenanceBundle = z.infer<typeof predictionMarketResearchProvenanceBundleSchema>
export type ResearchBridgeBundle = z.infer<typeof researchBridgeBundleSchema>
export type CrossVenueMarketRef = z.infer<typeof crossVenueMarketRefSchema>
export type CrossVenueMatch = z.infer<typeof crossVenueMatchSchema>
export type CrossVenueOpportunityType = z.infer<typeof crossVenueOpportunityTypeSchema>
export type CrossVenueTaxonomy = z.infer<typeof crossVenueTaxonomySchema>
export type PredictionMarketMarketGraphRelationKind = z.infer<typeof predictionMarketMarketGraphRelationKindSchema>
export type PredictionMarketMarketGraphNode = z.infer<typeof predictionMarketMarketGraphNodeSchema>
export type PredictionMarketMarketGraphEdge = z.infer<typeof predictionMarketMarketGraphEdgeSchema>
export type PredictionMarketCrossVenueMatchRejection = z.infer<typeof predictionMarketCrossVenueMatchRejectionSchema>
export type PredictionMarketComparableMarketGroup = z.infer<typeof predictionMarketComparableMarketGroupSchema>
export type PredictionMarketMarketGraph = z.infer<typeof predictionMarketMarketGraphSchema>
export type MarketEquivalenceProof = z.infer<typeof marketEquivalenceProofSchema>
export type PredictionMarketOrderTraceAudit = z.infer<typeof predictionMarketOrderTraceAuditSchema>
export type PredictionMarketPacketBundle = z.infer<typeof predictionMarketPacketBundleSchema>
export type PredictionMarketVenueCoverage = z.infer<typeof predictionMarketVenueCoverageSchema>
export type ExecutableEdge = z.infer<typeof executableEdgeSchema>
export type ArbPlanLeg = z.infer<typeof arbPlanLegSchema>
export type ArbPlan = z.infer<typeof arbPlanSchema>
export type VenueCapabilities = z.infer<typeof venueCapabilitiesSchema>
export type VenueHealthSnapshot = z.infer<typeof venueHealthSnapshotSchema>
export type MarketFeedSurface = z.infer<typeof marketFeedSurfaceSchema>
export type CapitalLedgerSnapshot = z.infer<typeof capitalLedgerSnapshotSchema>
export type ForecastBasis = z.infer<typeof forecastBasisSchema>
export type ForecastBenchmarkComparatorKind = z.infer<typeof forecastBenchmarkComparatorKindSchema>
export type ForecastBenchmarkComparatorRole = z.infer<typeof forecastBenchmarkComparatorRoleSchema>
export type ForecastPipelineStageName = z.infer<typeof forecastPipelineStageNameSchema>
export type ForecastPipelineStageMode = z.infer<typeof forecastPipelineStageModeSchema>
export type ForecastAbstentionReason = z.infer<typeof forecastAbstentionReasonSchema>
export type TradeIntent = z.infer<typeof tradeIntentSchema>
export type PredictionMarketApprovalTicketApprovalStatus = z.infer<
  typeof predictionMarketApprovalTicketApprovalStatusSchema
>
export type PredictionMarketApprovalTicketApprovalState = z.infer<
  typeof predictionMarketApprovalTicketApprovalStateSchema
>
export type ApprovalTradeTicket = z.infer<typeof approvalTradeTicketSchema>
export type TradeIntentGuard = z.infer<typeof tradeIntentGuardSchema>
export type MultiVenueExecution = z.infer<typeof multiVenueExecutionSchema>
export type PredictionMarketBudgets = z.infer<typeof predictionMarketBudgetsSchema>
export type PredictionMarketPerformanceBudget = z.infer<typeof predictionMarketPerformanceBudgetSchema>
export type ForecastPacket = z.infer<typeof forecastPacketSchema>
export type MarketRecommendationPacket = z.infer<typeof marketRecommendationPacketSchema>
export type PredictionMarketArtifactRef = z.infer<typeof predictionMarketArtifactRefSchema>
export type PredictionMarketJsonArtifact = z.infer<typeof predictionMarketJsonArtifactSchema>
export type RunManifest = z.infer<typeof runManifestSchema>
export type PredictionMarketRunSummary = z.infer<typeof predictionMarketRunSummarySchema>
export type PredictionMarketsAdviceRequest = z.infer<typeof predictionMarketsAdviceRequestSchema>
export type PredictionMarketsReplayRequest = z.infer<typeof predictionMarketsReplayRequestSchema>
export type PredictionMarketArtifactType = z.infer<typeof predictionMarketArtifactTypeSchema>
export type PredictionMarketResearchPipelineStageStatus = z.infer<
  typeof predictionMarketResearchPipelineStageStatusSchema
>
export type PredictionMarketResearchPipelineStage = z.infer<
  typeof predictionMarketResearchPipelineStageSchema
>
export type PredictionMarketResearchPipelineTrace = z.infer<
  typeof predictionMarketResearchPipelineTraceSchema
>
export type PredictionMarketResearchPipelineSummary = z.infer<
  typeof predictionMarketResearchPipelineSummarySchema
>
