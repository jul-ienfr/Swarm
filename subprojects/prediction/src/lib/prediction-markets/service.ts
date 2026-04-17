import { randomUUID } from 'node:crypto'
import { createRun, type AgentRun, updateRun, computeConfigHash } from '@/lib/runs'
import { getRun } from '@/lib/runs'
import { PredictionMarketsError } from '@/lib/prediction-markets/errors'
import {
  buildKalshiSnapshot,
  listKalshiMarkets,
} from '@/lib/prediction-markets/kalshi'
import {
  buildPolymarketSnapshot,
  listPolymarketMarkets,
} from '@/lib/prediction-markets/polymarket'
import {
  type AutonomousAgentReport,
  type BasketIntentPreview,
  type ExecutionIntentPreview,
  type DecisionPacket,
  type EvidencePacket,
  type ForecastPacket,
  type ForecastEvaluationRecord,
  type LatencyReferenceBundle,
  type MarketDescriptor,
  type MarketRegime,
  type ResolutionPolicy,
  type MarketSnapshot,
  type MarketRecommendationPacket,
  type PredictionMarketArtifactRef,
  type PredictionMarketBudgets,
  type PredictionMarketDegradedMode,
  type MarketFeedSurface,
  type MultiVenueExecution,
  type PredictionMarketJsonArtifact,
  type PredictionMarketPacketBundle,
  type PredictionMarketAdvisorArchitecture,
  type PredictionMarketPacketContract,
  type PredictionMarketProvenanceBundle,
  type PredictionMarketOrderTraceAudit,
  type PredictionMarketVenueCoverage,
  type QuotePairIntentPreview,
  type ResearchBridgeBundle,
  type PredictionMarketsAdviceRequest,
  type PredictionMarketAdviceRequestMode,
  type PredictionMarketAdviceResponseVariant,
  type PredictionMarketHealthStatus,
  type PredictionMarketTimesFMLane,
  type PredictionMarketTimesFMMode,
  type ResolutionAnomalyReport,
  type PredictionMarketVenue,
  type RunManifest,
  type StrategyCandidatePacket,
  type StrategyDecisionPacket,
  type StrategyFamily,
  type StrategyShadowReport,
  type StrategyShadowSummary,
  type TradeIntent,
  type TradeIntentGuard,
  type VenueCapabilities,
  type VenueHealthSnapshot,
  type CrossVenueTaxonomy,
  type PredictionMarketMarketGraph,
  DEFAULT_ENABLED_STRATEGY_FAMILIES,
  decisionPacketSchema,
  evidencePacketSchema,
  forecastPacketSchema,
  marketRecommendationPacketSchema,
  predictionMarketsAdviceRequestSchema,
  predictionMarketsReplayRequestSchema,
  resolutionPolicySchema,
  runManifestSchema,
  predictionMarketPacketBundleSchema,
  predictionMarketAdvisorArchitectureSchema,
  multiVenueExecutionSchema,
  predictionMarketOrderTraceAuditSchema,
  tradeIntentGuardSchema,
  predictionMarketMarketGraphSchema,
  predictionMarketMarketGraphNodeSchema,
  predictionMarketMarketGraphEdgeSchema,
  predictionMarketComparableMarketGroupSchema,
  predictionMarketCrossVenueMatchRejectionSchema,
  PREDICTION_MARKETS_SCHEMA_VERSION,
  PREDICTION_MARKETS_BASELINE_MODEL,
} from '@/lib/prediction-markets/schemas'
import {
  findRecentPredictionMarketRunByConfig,
  getPredictionMarketRunDetails as getStoredPredictionMarketRunDetails,
  listPredictionMarketRuns as listStoredPredictionMarketRuns,
  persistPredictionMarketExecution,
} from '@/lib/prediction-markets/store'
import {
  getVenueBudgetsContract,
  getVenueCapabilitiesContract,
  getVenueCoverageContract,
  getVenueFeedSurfaceContract,
  getVenueHealthSnapshotContract,
  listPredictionMarketVenues,
} from '@/lib/prediction-markets/venue-ops'
import { getPredictionMarketVenueStrategy } from '@/lib/prediction-markets/venue-strategy'
import {
  evaluatePredictionMarketCompliance,
  type PredictionMarketComplianceDecision,
  type PredictionMarketComplianceMatrix,
} from '@/lib/prediction-markets/compliance'
import {
  detectCrossVenueArbitrageCandidates,
  findCrossVenueMatches,
  summarizeCrossVenueIntelligence,
  type CrossVenueArbitrageCandidate,
  type CrossVenueEvaluation,
  type CrossVenueOpsSummary,
} from '@/lib/prediction-markets/cross-venue'
import {
  evaluatePredictionMarketRuntimeGuard,
  type PredictionMarketRuntimeGuardResult,
} from '@/lib/prediction-markets/runtime-guard'
import {
  buildPredictionMarketExecutionReadiness,
  type PredictionMarketExecutionReadinessMode,
  type PredictionMarketExecutionReadinessReport,
} from '@/lib/prediction-markets/execution-readiness'
import {
  buildPredictionMarketExecutionPathways,
  type PredictionMarketExecutionPathwaysApprovalTicket,
  type PredictionMarketExecutionPathways,
  type PredictionMarketExecutionPathwaysOperatorThesis,
  type PredictionMarketExecutionPathwaysResearchPipelineTrace,
} from '@/lib/prediction-markets/execution-pathways'
import {
  projectPredictionMarketExecutionPath,
  type PredictionMarketExecutionProjection,
} from '@/lib/prediction-markets/execution-path'
import {
  buildMarketResearchSidecar,
  annotateMarketResearchSidecarComparisons,
  type MarketResearchSidecar,
} from '@/lib/prediction-markets/research'
import {
  resolvePredictionMarketTimesFMOptions,
  runPredictionMarketTimesFMSidecar,
  shouldRunPredictionMarketTimesFM,
  summarizePredictionMarketTimesFMSidecar,
  type PredictionMarketTimesFMSidecar,
} from '@/lib/prediction-markets/timesfm'
import {
  buildMicrostructureLabReport,
  type MicrostructureLabReport,
} from '@/lib/prediction-markets/microstructure-lab'
import { buildResolvedHistoryDataset, toCalibrationPointsFromResolvedHistory } from '@/lib/prediction-markets/resolved-history'
import { buildPredictionMarketCostModelReport } from '@/lib/prediction-markets/cost-model'
import { buildPredictionMarketWalkForwardReport } from '@/lib/prediction-markets/walk-forward'
import {
  extractForecastEvaluationHistoryFromArtifacts,
  resolvePredictionMarketEvaluationHistory,
} from '@/lib/prediction-markets/evaluation-history-source'
import {
  buildStrategyDecision,
  deriveLatencyReferences,
  deriveMarketRegime,
  deriveResolutionAnomalies,
  type PredictionMarketStrategyCandidate,
  type PredictionMarketStrategyCandidateKind,
  type PredictionMarketStrategyDecision,
  type PredictionMarketStrategyLatencyReference,
  type PredictionMarketStrategyMarketRegime,
  type PredictionMarketStrategyResolutionAnomaly,
  summarizeStrategyCounts,
} from '@/lib/prediction-markets/strategy-engine'
import {
  summarizePredictionMarketsBenchmarkGate,
  type PredictionMarketsBenchmarkGateSummary,
} from '@/lib/prediction-markets/benchmark-gate'
import { type ShadowArbitrageSimulationReport } from '@/lib/prediction-markets/shadow-arbitrage'
import {
  buildPredictionMarketArtifactReadback,
  type PredictionMarketArtifactReadbackIndex,
} from '@/lib/prediction-markets/artifact-readback'
import {
  enrichPredictionMarketPreflightSummary,
  type PredictionMarketPreflightPenaltySummary,
  type PredictionMarketStaleEdgeStatus,
} from '@/lib/prediction-markets/preflight-ops'
import {
  executePredictionMarketLiveExecutionBridge,
  resolvePredictionMarketLiveExecutionBridgeStatus,
} from '@/lib/prediction-markets/live-execution-bridge'
import { getPredictionMarketResearchMemoryRuntime } from '@/lib/prediction-markets/memory/runtime'
import {
  buildPredictionMarketWorldStateSpine,
  type PredictionMarketWorldStateSpine,
} from '@/lib/prediction-markets/world-state-spine'
import { type PredictionMarketSourceAudit } from '@/lib/prediction-markets/source-audit'
import { type PredictionMarketRulesLineage } from '@/lib/prediction-markets/rules-lineage'
import { type PredictionMarketCatalystTimeline } from '@/lib/prediction-markets/catalyst-timeline'
import { type PredictionMarketWorldStateSnapshot } from '@/lib/prediction-markets/world-state'
import { type PredictionMarketTicketPayload } from '@/lib/prediction-markets/ticket-payload'
import {
  appendDecisionLedgerEntry,
  summarizeDecisionLedgerEntries,
  type DecisionLedgerEntry,
  type DecisionLedgerSummary,
} from '@/lib/prediction-markets/decision-ledger'
import { buildCalibrationReport, type CalibrationReport } from '@/lib/prediction-markets/calibration'
import {
  buildAutopilotCycleRecord,
  summarizeAutopilotCycles,
  type AutopilotCycleSummaryReport,
} from '@/lib/prediction-markets/autopilot-cycle'
import {
  assessBinaryParity,
  assessMultiOutcomeParity,
  assessOddsDivergence,
  assessOrderbookImbalance,
  assessSpreadCapture,
  calculateKellySizing,
} from '@/lib/prediction-markets/quant-pack'

type AdviceExecutionInput = PredictionMarketsAdviceRequest & {
  workspaceId: number
  actor?: string
}

type PredictionMarketAdviceRequestContract = {
  request_mode: PredictionMarketAdviceRequestMode
  response_variant: PredictionMarketAdviceResponseVariant
  strategy_profile: PredictionMarketsAdviceRequest['strategy_profile']
  history_limit: number
  variant_tags: string[]
  timesfm_mode: PredictionMarketTimesFMMode
  timesfm_lanes: PredictionMarketTimesFMLane[]
}

type ReplayExecutionInput = {
  workspaceId: number
  actor?: string
  runId: string
}

type PredictionMarketRunDispatchStatus = 'ready' | 'blocked'

type PredictionMarketRunDispatchPlan = PredictionMarketRunRuntimeHints & {
  gate_name: 'execution_projection_dispatch'
  preflight_only: true
  run_id: string
  workspace_id: number
  dispatch_status: PredictionMarketRunDispatchStatus
  dispatch_blocking_reasons: string[]
  benchmark_surface_blocking_reasons: string[]
  benchmark_promotion_blockers: string[]
  benchmark_promotion_ready: boolean
  summary: string
  source_refs: {
    run_detail: string
    execution_projection: string | null
    trade_intent_guard: string | null
    multi_venue_execution: string | null
  }
  execution_readiness: PredictionMarketExecutionReadiness | null
  execution_pathways: PredictionMarketExecutionPathwaysReport | null
  execution_projection: PredictionMarketExecutionProjectionReport | null
  shadow_arbitrage: ShadowArbitrageSimulationReport | null
  trade_intent_guard: TradeIntentGuard | null
  multi_venue_execution: MultiVenueExecution | null
}

type PredictionMarketRunPaperStatus = 'ready' | 'blocked'

type PredictionMarketRunPaperPlan = PredictionMarketRunRuntimeHints & {
  gate_name: 'execution_projection_paper'
  preflight_only: true
  run_id: string
  workspace_id: number
  surface_mode: 'paper'
  paper_status: PredictionMarketRunPaperStatus
  paper_blocking_reasons: string[]
  benchmark_surface_blocking_reasons: string[]
  benchmark_promotion_blockers: string[]
  benchmark_promotion_ready: boolean
  summary: string
  source_refs: {
    run_detail: string
    execution_projection: string | null
    paper_projected_path: string | null
    trade_intent_guard: string | null
    multi_venue_execution: string | null
  }
  execution_readiness: PredictionMarketExecutionReadiness | null
  execution_pathways: PredictionMarketExecutionPathwaysReport | null
  execution_projection: PredictionMarketExecutionProjectionReport | null
  shadow_arbitrage: ShadowArbitrageSimulationReport | null
  trade_intent_guard: TradeIntentGuard | null
  multi_venue_execution: MultiVenueExecution | null
  venue_feed_surface: MarketFeedSurface | null
  paper_path: PredictionMarketExecutionProjectionReport['projected_paths']['paper'] | null
  paper_trade_intent_preview: TradeIntent | null
  paper_trade_intent_preview_source: 'canonical_trade_intent_preview' | 'trade_intent_preview' | null
  paper_surface?: PredictionMarketReplaySurface | null
  replay_surface?: PredictionMarketReplaySurface | null
  paper_no_trade_zone_count?: number | null
  paper_no_trade_zone_rate?: number | null
  replay_no_trade_leg_count?: number | null
  replay_no_trade_leg_rate?: number | null
}

type PredictionMarketRunShadowStatus = 'ready' | 'blocked'

type PredictionMarketRunShadowPlan = PredictionMarketRunRuntimeHints & {
  gate_name: 'execution_projection_shadow'
  preflight_only: true
  run_id: string
  workspace_id: number
  surface_mode: 'shadow'
  shadow_status: PredictionMarketRunShadowStatus
  shadow_blocking_reasons: string[]
  benchmark_surface_blocking_reasons: string[]
  benchmark_promotion_blockers: string[]
  benchmark_promotion_ready: boolean
  summary: string
  source_refs: {
    run_detail: string
    execution_projection: string | null
    shadow_projected_path: string | null
    shadow_arbitrage: string | null
    trade_intent_guard: string | null
    multi_venue_execution: string | null
  }
  execution_readiness: PredictionMarketExecutionReadiness | null
  execution_pathways: PredictionMarketExecutionPathwaysReport | null
  execution_projection: PredictionMarketExecutionProjectionReport | null
  shadow_arbitrage: ShadowArbitrageSimulationReport | null
  trade_intent_guard: TradeIntentGuard | null
  multi_venue_execution: MultiVenueExecution | null
  venue_feed_surface: MarketFeedSurface | null
  shadow_path: PredictionMarketExecutionProjectionReport['projected_paths']['shadow'] | null
  shadow_trade_intent_preview: TradeIntent | null
  shadow_trade_intent_preview_source: 'canonical_trade_intent_preview' | 'trade_intent_preview' | null
  paper_surface?: PredictionMarketReplaySurface | null
  replay_surface?: PredictionMarketReplaySurface | null
  paper_no_trade_zone_count?: number | null
  paper_no_trade_zone_rate?: number | null
  replay_no_trade_leg_count?: number | null
  replay_no_trade_leg_rate?: number | null
}

type PredictionMarketRunLiveStatus = 'ready' | 'blocked'

type PredictionMarketRunLivePlan = PredictionMarketRunRuntimeHints & {
  gate_name: 'execution_projection_live'
  preflight_only: true
  run_id: string
  workspace_id: number
  surface_mode: 'live'
  live_route_allowed: boolean
  live_status: PredictionMarketRunLiveStatus
  live_blocking_reasons: string[]
  benchmark_surface_blocking_reasons: string[]
  benchmark_promotion_blockers: string[]
  benchmark_promotion_ready: boolean
  live_transport_ready: boolean
  live_transport_blockers: string[]
  live_transport_summary: string
  summary: string
  source_refs: {
    run_detail: string
    execution_projection: string | null
    live_projected_path: string | null
    trade_intent_guard: string | null
    multi_venue_execution: string | null
  }
  execution_readiness: PredictionMarketExecutionReadiness | null
  execution_pathways: PredictionMarketExecutionPathwaysReport | null
  execution_projection: PredictionMarketExecutionProjectionReport | null
  shadow_arbitrage: ShadowArbitrageSimulationReport | null
  trade_intent_guard: TradeIntentGuard | null
  multi_venue_execution: MultiVenueExecution | null
  venue_feed_surface: MarketFeedSurface | null
  live_path: PredictionMarketExecutionProjectionReport['projected_paths']['live'] | null
  live_trade_intent_preview: TradeIntent | null
  live_trade_intent_preview_source: 'canonical_trade_intent_preview' | 'trade_intent_preview' | null
  paper_surface?: PredictionMarketReplaySurface | null
  replay_surface?: PredictionMarketReplaySurface | null
  paper_no_trade_zone_count?: number | null
  paper_no_trade_zone_rate?: number | null
  replay_no_trade_leg_count?: number | null
  replay_no_trade_leg_rate?: number | null
}

type PredictionMarketRunLiveExecutionReceipt = {
  gate_name: 'execution_projection_live_materialization'
  execution_mode: 'live'
  source_run_id: string
  materialized_run_id: string
  approved_intent_id: string | null
  approved_by: string[]
  transport_mode: string
  performed_live: boolean
  live_execution_status: string
  receipt_summary: string
  preflight_surface: PredictionMarketRunLivePlan
  order_trace_audit: Record<string, unknown> | null
  live_execution: Record<string, unknown> | null
  market_execution: Record<string, unknown> | null
  manifest: Record<string, unknown> | null
}

type RecommendationHumanReport = {
  rationale: string
  why_now: string[]
  why_not_now: string[]
  watch_conditions: string[]
  next_review_at: string
}

type EnrichedMarketRecommendationPacket = MarketRecommendationPacket & RecommendationHumanReport
type StoredPredictionMarketRunDetails = NonNullable<ReturnType<typeof getStoredPredictionMarketRunDetails>>
type StoredPredictionMarketRunSummary = ReturnType<typeof listStoredPredictionMarketRuns>[number]
type PredictionMarketCrossVenueIntelligence = {
  evaluations: CrossVenueEvaluation[]
  arbitrage_candidates: CrossVenueArbitrageCandidate[]
  errors: string[]
  summary?: CrossVenueOpsSummary
}

function isPresent<T>(value: T | null | undefined): value is T {
  return value != null
}
type PredictionMarketExecutionReadiness = PredictionMarketExecutionReadinessReport & {
  pipeline_status: PredictionMarketPipelineStatus
  pipeline_reasons: string[]
  cross_venue_summary: CrossVenueOpsSummary
  microstructure_lab: MicrostructureLabReport | null
}
type PredictionMarketExecutionPathwaysReport = PredictionMarketExecutionPathways
type PredictionMarketExecutionProjectionMode = 'paper' | 'shadow' | 'live'
type PredictionMarketReplaySurface = PredictionMarketJsonArtifact & {
  no_trade_zone_count?: number
  no_trade_zone_rate?: number
  no_trade_leg_count?: number
  no_trade_leg_rate?: number
  order_trace_audit?: PredictionMarketOrderTraceAudit | null
}
type PredictionMarketExecutionProjectionReportBasis = {
  basis: {
    uses_execution_readiness: true
    uses_compliance: true
    uses_capital: boolean
    uses_reconciliation: boolean
    uses_microstructure: boolean
    capital_status: 'attached' | 'unavailable'
    reconciliation_status: 'attached' | 'degraded' | 'unavailable'
    source_refs: {
      pipeline_guard: string
      compliance_report: string
      execution_readiness: string
      venue_health: string
      capital_ledger: string | null
      reconciliation: string | null
      microstructure_lab: string | null
    }
    canonical_gate: {
      gate_name: 'execution_projection'
      single_runtime_gate: true
      enforced_for_modes: PredictionMarketExecutionProjectionMode[]
    }
  }
  microstructure_summary: null | {
    recommended_mode: MicrostructureLabReport['summary']['recommended_mode']
    worst_case_severity: MicrostructureLabReport['summary']['worst_case_severity']
    executable_deterioration_bps: number
    execution_quality_score: number
  }
}
type PredictionMarketExecutionPreflightSummary = {
  gate_name: 'execution_projection'
  preflight_only: true
  requested_path: PredictionMarketExecutionProjectionMode
  selected_path: PredictionMarketExecutionProjectionMode | null
  verdict: 'allowed' | 'downgraded' | 'blocked'
  highest_safe_requested_mode: PredictionMarketExecutionProjectionMode | null
  recommended_effective_mode: PredictionMarketExecutionReadinessMode | null
  manual_review_required: boolean
  ttl_ms: number
  expires_at: string
  counts: {
    total: number
    eligible: number
    ready: number
    degraded: number
    blocked: number
  }
  basis: {
    uses_execution_readiness: boolean
    uses_compliance: boolean
    uses_capital: boolean
    uses_reconciliation: boolean
    uses_microstructure: boolean
    capital_status: 'attached' | 'unavailable'
    reconciliation_status: 'attached' | 'degraded' | 'unavailable'
  }
  source_refs: string[]
  blockers: string[]
  downgrade_reasons: string[]
  selected_edge_bucket?: PredictionMarketExecutionProjection['selected_edge_bucket'] | null
  selected_pre_trade_gate?: PredictionMarketExecutionProjection['selected_pre_trade_gate'] | null
  source_of_truth?: 'official_docs' | 'community_repos'
  execution_eligible?: boolean
  stale_edge_status?: PredictionMarketStaleEdgeStatus
  penalties?: PredictionMarketPreflightPenaltySummary
  microstructure: null | {
    recommended_mode: MicrostructureLabReport['summary']['recommended_mode']
    worst_case_severity: MicrostructureLabReport['summary']['worst_case_severity']
    executable_deterioration_bps: number
    execution_quality_score: number
  }
  summary: string
}
type PredictionMarketExecutionProjectionReport = PredictionMarketExecutionProjection & PredictionMarketExecutionProjectionReportBasis & {
  highest_safe_requested_mode: PredictionMarketExecutionProjectionMode | null
  recommended_effective_mode: PredictionMarketExecutionReadinessMode | null
  modes: Record<PredictionMarketExecutionProjectionMode, {
    requested_mode: PredictionMarketExecutionProjectionMode
    verdict: 'inactive' | 'ready' | 'degraded' | 'blocked'
    effective_mode: PredictionMarketExecutionReadinessMode
    blockers: string[]
    warnings: string[]
    summary: string
  }>
  preflight_summary: PredictionMarketExecutionPreflightSummary
}
type PredictionMarketStrategyCounts = {
  total: number
  actionable: number
  ready: number
  degraded: number
  blocked: number
  inactive: number
}
type PredictionMarketStrategyRuntimeArtifacts = {
  strategy_profile: PredictionMarketsAdviceRequest['strategy_profile']
  enabled_strategy_families: StrategyFamily[]
  strategy_candidate_packet: StrategyCandidatePacket | null
  strategy_decision_packet: StrategyDecisionPacket | null
  strategy_shadow_summary: StrategyShadowSummary | null
  strategy_shadow_report: StrategyShadowReport | null
  execution_intent_preview: ExecutionIntentPreview | null
  quote_pair_intent_preview: QuotePairIntentPreview | null
  basket_intent_preview: BasketIntentPreview | null
  maker_spread_capture_inventory_summary: string | null
  maker_spread_capture_adverse_selection_summary: string | null
  maker_spread_capture_quote_transport_summary: string | null
  maker_spread_capture_blockers: string[]
  maker_spread_capture_risk_caps: string[]
  latency_reference_bundle: LatencyReferenceBundle | null
  resolution_anomaly_report: ResolutionAnomalyReport | null
  autonomous_agent_report: AutonomousAgentReport | null
  strategy_name: string | null
  market_regime_summary: string | null
  primary_strategy_summary: string | null
  strategy_summary: string | null
  strategy_counts: PredictionMarketStrategyCounts | null
  resolution_anomalies: string[]
  strategy_trade_intent_preview: TradeIntent | null
  strategy_canonical_trade_intent_preview: TradeIntent | null
}
type PredictionMarketCopiedPatternArtifacts = {
  source_audit: PredictionMarketSourceAudit
  rules_lineage: PredictionMarketRulesLineage
  catalyst_timeline: PredictionMarketCatalystTimeline
  world_state: PredictionMarketWorldStateSnapshot
  ticket_payload: PredictionMarketTicketPayload
  quant_signal_bundle: PredictionMarketJsonArtifact
  decision_ledger: PredictionMarketJsonArtifact & {
    entries: DecisionLedgerEntry[]
    summary: DecisionLedgerSummary
  }
  calibration_report: CalibrationReport
  resolved_history: PredictionMarketJsonArtifact
  cost_model_report: PredictionMarketJsonArtifact
  walk_forward_report: PredictionMarketJsonArtifact
  autopilot_cycle_summary: AutopilotCycleSummaryReport
  research_memory_summary: PredictionMarketJsonArtifact | null
}
type MakerSpreadCaptureDiagnostics = {
  inventory_summary: string | null
  adverse_selection_summary: string | null
  quote_transport_summary: string | null
  blockers: string[]
  risk_caps: string[]
}
type StoredExecutionArtifacts = {
  snapshot: MarketSnapshot
  resolution_policy: ResolutionPolicy
  evidence_packets: EvidencePacket[]
  forecast: ForecastPacket
  recommendation: EnrichedMarketRecommendationPacket
  market_events: PredictionMarketJsonArtifact | null
  market_positions: PredictionMarketJsonArtifact | null
  source_audit: PredictionMarketJsonArtifact | null
  rules_lineage: PredictionMarketJsonArtifact | null
  catalyst_timeline: PredictionMarketJsonArtifact | null
  world_state: PredictionMarketJsonArtifact | null
  ticket_payload: PredictionMarketJsonArtifact | null
  quant_signal_bundle: PredictionMarketJsonArtifact | null
  decision_ledger: PredictionMarketJsonArtifact | null
  calibration_report: PredictionMarketJsonArtifact | null
  resolved_history: PredictionMarketJsonArtifact | null
  cost_model_report: PredictionMarketJsonArtifact | null
  walk_forward_report: PredictionMarketJsonArtifact | null
  autopilot_cycle_summary: PredictionMarketJsonArtifact | null
  research_memory_summary: PredictionMarketJsonArtifact | null
  paper_surface: PredictionMarketReplaySurface | null
  replay_surface: PredictionMarketReplaySurface | null
  research_bridge: ResearchBridgeBundle | null
  research_sidecar: MarketResearchSidecar | null
  timesfm_sidecar: PredictionMarketTimesFMSidecar | null
  order_trace_audit: PredictionMarketOrderTraceAudit | null
  venue_coverage: PredictionMarketVenueCoverage
  cross_venue_intelligence: PredictionMarketCrossVenueIntelligence | null
  provenance_bundle: PredictionMarketProvenanceBundle | null
  pipeline_guard: PredictionMarketPipelineGuard | null
  runtime_guard: PredictionMarketRuntimeGuardResult | null
  compliance: PredictionMarketComplianceDecision | null
  execution_readiness: PredictionMarketExecutionReadiness | null
  execution_pathways: PredictionMarketExecutionPathwaysReport | null
  execution_projection: PredictionMarketExecutionProjectionReport | null
  strategy_candidate_packet: StrategyCandidatePacket | null
  strategy_decision_packet: StrategyDecisionPacket | null
  strategy_shadow_summary: StrategyShadowSummary | null
  strategy_shadow_report: StrategyShadowReport | null
  execution_intent_preview: ExecutionIntentPreview | null
  quote_pair_intent_preview: QuotePairIntentPreview | null
  basket_intent_preview: BasketIntentPreview | null
  maker_spread_capture_inventory_summary?: string | null
  maker_spread_capture_adverse_selection_summary?: string | null
  maker_spread_capture_quote_transport_summary?: string | null
  maker_spread_capture_blockers?: string[]
  maker_spread_capture_risk_caps?: string[]
  latency_reference_bundle: LatencyReferenceBundle | null
  resolution_anomaly_report: ResolutionAnomalyReport | null
  autonomous_agent_report: AutonomousAgentReport | null
  shadow_arbitrage: ShadowArbitrageSimulationReport | null
  trade_intent_guard: TradeIntentGuard | null
  multi_venue_execution: MultiVenueExecution | null
  microstructure_lab: MicrostructureLabReport | null
}
type PredictionMarketArtifactAuditSummary = {
  manifest_ref_count: number
  observed_ref_count: number
  canonical_ref_count: number
  run_manifest_present: boolean
  duplicate_artifact_ids: string[]
  manifest_only_artifact_ids: string[]
  observed_only_artifact_ids: string[]
}
type PredictionMarketWalkForwardSurfaceSummary = {
  summary: string | null
  sample_count: number | null
  window_count: number | null
  win_rate: number | null
  brier_score: number | null
  log_loss: number | null
  uplift_bps: number | null
  promotion_ready: boolean
  notes: string[]
}
type PredictionMarketRunSummaryWithArtifactAudit = StoredPredictionMarketRunSummary & {
  artifact_audit: PredictionMarketArtifactAuditSummary
  request_mode?: PredictionMarketAdviceRequestMode | null
  response_variant?: PredictionMarketAdviceResponseVariant | null
  request_variant_tags?: string[]
  research_runtime_mode?: 'market_only' | 'research_driven' | null
  research_recommendation_origin?: 'market_only' | 'research_driven' | 'manual_thesis' | 'abstention' | null
  research_recommendation_origin_summary?: string | null
  research_abstention_flipped_recommendation?: boolean | null
  research_pipeline_id?: string | null
  research_pipeline_version?: string | null
  research_forecaster_count?: number | null
  research_weighted_probability_yes?: number | null
  research_weighted_coverage?: number | null
  research_compare_preferred_mode?: 'market_only' | 'aggregate' | 'abstention' | null
  research_compare_summary?: string | null
  research_abstention_policy_version?: string | null
  research_abstention_policy_blocks_forecast?: boolean | null
  research_forecast_probability_yes_hint?: number | null
  research_runtime_summary?: string | null
  timesfm_requested_mode?: PredictionMarketTimesFMMode | null
  timesfm_effective_mode?: PredictionMarketTimesFMMode | null
  timesfm_requested_lanes?: PredictionMarketTimesFMLane[]
  timesfm_selected_lane?: PredictionMarketTimesFMLane | null
  timesfm_health?: PredictionMarketTimesFMSidecar['health']['status'] | null
  timesfm_summary?: string | null
  research_benchmark_gate_summary?: string | null
  research_benchmark_uplift_bps?: number | null
  research_benchmark_verdict?: PredictionMarketsBenchmarkGateSummary['verdict'] | null
  research_benchmark_gate_status?: PredictionMarketsBenchmarkGateSummary['status'] | null
  research_benchmark_promotion_status?: PredictionMarketsBenchmarkGateSummary['promotion_status'] | null
  research_benchmark_promotion_ready?: boolean
  research_benchmark_preview_available?: boolean
  research_benchmark_promotion_evidence?: PredictionMarketsBenchmarkGateSummary['promotion_evidence'] | null
  research_benchmark_evidence_level?: PredictionMarketsBenchmarkGateSummary['evidence_level'] | null
  research_promotion_gate_kind?: PredictionMarketsBenchmarkGateSummary['promotion_gate_kind'] | null
  research_benchmark_promotion_blocker_summary?: string | null
  research_benchmark_promotion_summary?: string | null
  research_benchmark_gate_blocks_live?: boolean
  research_benchmark_live_block_reason?: string | null
  research_benchmark_gate_blockers?: string[]
  research_benchmark_gate_reasons?: string[]
  benchmark_gate_summary?: string | null
  benchmark_uplift_bps?: number | null
  benchmark_verdict?: PredictionMarketsBenchmarkGateSummary['verdict'] | null
  benchmark_gate_status?: PredictionMarketsBenchmarkGateSummary['status'] | null
  benchmark_promotion_status?: PredictionMarketsBenchmarkGateSummary['promotion_status'] | null
  benchmark_promotion_ready?: boolean
  benchmark_gate_blocks_live?: boolean
  benchmark_preview_available?: boolean
  benchmark_promotion_evidence?: PredictionMarketsBenchmarkGateSummary['promotion_evidence'] | null
  benchmark_evidence_level?: PredictionMarketsBenchmarkGateSummary['evidence_level'] | null
  benchmark_promotion_gate_kind?: PredictionMarketsBenchmarkGateSummary['promotion_gate_kind'] | null
  benchmark_promotion_blocker_summary?: string | null
  benchmark_promotion_summary?: string | null
  benchmark_gate_live_block_reason?: string | null
  benchmark_gate_blockers?: string[]
  benchmark_gate_reasons?: string[]
  primary_strategy?: string | null
  strategy_primary?: string | null
  primary_strategy_summary?: string | null
  market_regime?: string | null
  strategy_market_regime?: string | null
  strategy_counts?: PredictionMarketStrategyCounts | null
  strategy_candidate_count?: number | null
  execution_intent_preview_kind?: string | null
  execution_intent_preview_source?: string | null
  maker_spread_capture_inventory_summary?: string | null
  maker_spread_capture_adverse_selection_summary?: string | null
  maker_spread_capture_quote_transport_summary?: string | null
  maker_spread_capture_blockers?: string[]
  maker_spread_capture_risk_caps?: string[]
  approval_ticket_id?: string | null
  approval_ticket_required?: boolean
  approval_ticket_status?: NonNullable<PredictionMarketExecutionPathwaysReport['approval_ticket']>['status'] | null
  approval_ticket_summary?: string | null
  operator_thesis_present?: boolean
  operator_thesis_source?: NonNullable<PredictionMarketExecutionPathwaysReport['operator_thesis']>['source'] | null
  operator_thesis_probability_yes?: number | null
  operator_thesis_summary?: string | null
  source_audit_average_score?: number | null
  source_audit_coverage_score?: number | null
  source_audit_summary?: string | null
  world_state_recommended_action?: 'bet' | 'wait' | 'no_trade' | null
  world_state_recommended_side?: 'yes' | 'no' | null
  world_state_confidence_score?: number | null
  world_state_summary?: string | null
  world_state_risk_flags?: string[]
  ticket_payload_action?: string | null
  ticket_payload_size_usd?: number | null
  ticket_payload_summary?: string | null
  quant_signal_summary?: string | null
  quant_signal_viable_count?: number | null
  decision_ledger_total_entries?: number | null
  decision_ledger_latest_entry_type?: string | null
  calibration_error?: number | null
  calibration_brier_score?: number | null
  resolved_history_summary?: string | null
  resolved_history_points?: number | null
  resolved_history_source_summary?: string | null
  resolved_history_first_cutoff_at?: string | null
  resolved_history_last_cutoff_at?: string | null
  cost_model_summary?: string | null
  cost_model_total_points?: number | null
  cost_model_viable_point_count?: number | null
  cost_model_viable_point_rate?: number | null
  cost_model_average_cost_bps?: number | null
  cost_model_average_net_edge_bps?: number | null
  walk_forward_summary?: PredictionMarketWalkForwardSurfaceSummary | null
  walk_forward_total_points?: number | null
  walk_forward_windows?: number | null
  walk_forward_stable_window_rate?: number | null
  walk_forward_mean_brier_improvement?: number | null
  walk_forward_mean_log_loss_improvement?: number | null
  walk_forward_mean_net_edge_bps?: number | null
  walk_forward_promotion_ready?: boolean
  autopilot_cycle_health?: 'healthy' | 'degraded' | 'blocked' | null
  autopilot_cycle_summary?: string | null
  research_memory_summary?: string | null
  research_memory_memory_count?: number | null
  research_memory_validation_score?: number | null
  research_pipeline_trace_summary?: string | null
  research_pipeline_trace_preferred_mode?: NonNullable<PredictionMarketExecutionPathwaysReport['research_pipeline_trace']>['preferred_mode'] | null
  research_pipeline_trace_oracle_family?: NonNullable<PredictionMarketExecutionPathwaysReport['research_pipeline_trace']>['oracle_family'] | null
  research_pipeline_trace_forecaster_count?: number | null
  research_pipeline_trace_evidence_count?: number | null
  strategy_shadow_summary?: string | null
  resolution_anomalies?: string[]
  execution_pathways_highest_actionable_mode?: PredictionMarketExecutionReadinessMode | null
  execution_projection_gate_name?: PredictionMarketExecutionProjection['gate_name']
  execution_projection_preflight_only?: boolean
  execution_projection_requested_path?: PredictionMarketExecutionProjectionMode | null
  execution_projection_selected_path?: PredictionMarketExecutionProjectionMode | null
  execution_projection_selected_path_status?: PredictionMarketExecutionProjection['projected_paths']['paper']['status'] | null
  execution_projection_selected_path_effective_mode?: PredictionMarketExecutionReadinessMode | null
  execution_projection_selected_path_reason_summary?: string | null
  execution_projection_verdict?: PredictionMarketExecutionProjection['verdict'] | null
  execution_projection_highest_safe_requested_mode?: PredictionMarketExecutionProjectionMode | null
  execution_projection_recommended_effective_mode?: PredictionMarketExecutionReadinessMode | null
  execution_projection_manual_review_required?: boolean
  execution_projection_ttl_ms?: number | null
  execution_projection_expires_at?: string | null
  execution_projection_blocking_reasons?: string[]
  execution_projection_downgrade_reasons?: string[]
  execution_projection_summary?: string | null
  execution_projection_preflight_summary?: PredictionMarketExecutionPreflightSummary | null
  execution_projection_capital_status?: PredictionMarketExecutionProjectionReportBasis['basis']['capital_status'] | null
  execution_projection_reconciliation_status?: PredictionMarketExecutionProjectionReportBasis['basis']['reconciliation_status'] | null
  execution_projection_selected_preview?: TradeIntent | null
  execution_projection_selected_preview_source?: 'canonical_trade_intent_preview' | 'trade_intent_preview' | null
  execution_projection_selected_edge_bucket?: PredictionMarketExecutionProjection['selected_edge_bucket'] | null
  execution_projection_selected_pre_trade_gate?: PredictionMarketExecutionProjection['selected_pre_trade_gate'] | null
  execution_projection_selected_pre_trade_gate_verdict?: NonNullable<PredictionMarketExecutionProjection['selected_pre_trade_gate']>['verdict'] | null
  execution_projection_selected_pre_trade_gate_summary?: string | null
  execution_projection_selected_path_net_edge_bps?: number | null
  execution_projection_selected_path_minimum_net_edge_bps?: number | null
  execution_projection_selected_path_canonical_size_usd?: number | null
  execution_projection_selected_path_shadow_signal_present?: boolean
  venue_feed_surface_summary?: string | null
  venue_pathway_summary?: string | null
  venue_pathway_highest_actionable_mode?: PredictionMarketExecutionReadinessMode | null
  multi_venue_taxonomy?: CrossVenueTaxonomy | null
  multi_venue_execution_filter_reason_codes?: string[]
  multi_venue_execution_filter_reason_code_counts?: Record<string, number>
  shadow_arbitrage_present?: boolean
  shadow_arbitrage_shadow_edge_bps?: number | null
  shadow_arbitrage_recommended_size_usd?: number | null
  shadow_arbitrage?: ShadowArbitrageSimulationReport | null
}
type PredictionMarketRunRuntimeHints = Pick<
  PredictionMarketRunSummaryWithArtifactAudit,
  | 'request_mode'
  | 'response_variant'
  | 'request_variant_tags'
  | 'research_runtime_mode'
  | 'research_recommendation_origin'
  | 'research_recommendation_origin_summary'
  | 'research_abstention_flipped_recommendation'
  | 'research_pipeline_id'
  | 'research_pipeline_version'
  | 'research_forecaster_count'
  | 'research_weighted_probability_yes'
  | 'research_weighted_coverage'
  | 'research_compare_preferred_mode'
  | 'research_compare_summary'
  | 'research_abstention_policy_version'
  | 'research_abstention_policy_blocks_forecast'
  | 'research_forecast_probability_yes_hint'
  | 'research_runtime_summary'
  | 'timesfm_requested_mode'
  | 'timesfm_effective_mode'
  | 'timesfm_requested_lanes'
  | 'timesfm_selected_lane'
  | 'timesfm_health'
  | 'timesfm_summary'
  | 'research_benchmark_gate_summary'
  | 'research_benchmark_uplift_bps'
  | 'research_benchmark_verdict'
  | 'research_benchmark_gate_status'
  | 'research_benchmark_promotion_status'
  | 'research_benchmark_promotion_ready'
  | 'research_benchmark_preview_available'
  | 'research_benchmark_promotion_evidence'
  | 'research_benchmark_evidence_level'
  | 'research_promotion_gate_kind'
  | 'research_benchmark_promotion_blocker_summary'
  | 'research_benchmark_promotion_summary'
  | 'research_benchmark_gate_blocks_live'
  | 'research_benchmark_live_block_reason'
  | 'research_benchmark_gate_blockers'
  | 'research_benchmark_gate_reasons'
  | 'benchmark_gate_summary'
  | 'benchmark_uplift_bps'
  | 'benchmark_verdict'
  | 'benchmark_gate_status'
  | 'benchmark_promotion_status'
  | 'benchmark_promotion_ready'
  | 'benchmark_gate_blocks_live'
  | 'benchmark_preview_available'
  | 'benchmark_promotion_evidence'
  | 'benchmark_evidence_level'
  | 'benchmark_promotion_gate_kind'
  | 'benchmark_promotion_blocker_summary'
  | 'benchmark_promotion_summary'
  | 'benchmark_gate_live_block_reason'
  | 'benchmark_gate_blockers'
  | 'benchmark_gate_reasons'
  | 'primary_strategy'
  | 'strategy_primary'
  | 'primary_strategy_summary'
  | 'market_regime'
  | 'strategy_market_regime'
  | 'strategy_counts'
  | 'strategy_candidate_count'
  | 'execution_intent_preview_kind'
  | 'execution_intent_preview_source'
  | 'maker_spread_capture_inventory_summary'
  | 'maker_spread_capture_adverse_selection_summary'
  | 'maker_spread_capture_quote_transport_summary'
  | 'maker_spread_capture_blockers'
  | 'maker_spread_capture_risk_caps'
  | 'approval_ticket_id'
  | 'approval_ticket_required'
  | 'approval_ticket_status'
  | 'approval_ticket_summary'
  | 'operator_thesis_present'
  | 'operator_thesis_source'
  | 'operator_thesis_probability_yes'
  | 'operator_thesis_summary'
  | 'source_audit_average_score'
  | 'source_audit_coverage_score'
  | 'source_audit_summary'
  | 'world_state_recommended_action'
  | 'world_state_recommended_side'
  | 'world_state_confidence_score'
  | 'world_state_summary'
  | 'world_state_risk_flags'
  | 'ticket_payload_action'
  | 'ticket_payload_size_usd'
  | 'ticket_payload_summary'
  | 'quant_signal_summary'
  | 'quant_signal_viable_count'
  | 'decision_ledger_total_entries'
  | 'decision_ledger_latest_entry_type'
  | 'calibration_error'
  | 'calibration_brier_score'
  | 'resolved_history_summary'
  | 'resolved_history_points'
  | 'resolved_history_source_summary'
  | 'resolved_history_first_cutoff_at'
  | 'resolved_history_last_cutoff_at'
  | 'cost_model_summary'
  | 'cost_model_total_points'
  | 'cost_model_viable_point_count'
  | 'cost_model_viable_point_rate'
  | 'cost_model_average_cost_bps'
  | 'cost_model_average_net_edge_bps'
  | 'walk_forward_summary'
  | 'walk_forward_total_points'
  | 'walk_forward_windows'
  | 'walk_forward_stable_window_rate'
  | 'walk_forward_mean_brier_improvement'
  | 'walk_forward_mean_log_loss_improvement'
  | 'walk_forward_mean_net_edge_bps'
  | 'walk_forward_promotion_ready'
  | 'autopilot_cycle_health'
  | 'autopilot_cycle_summary'
  | 'research_memory_summary'
  | 'research_memory_memory_count'
  | 'research_memory_validation_score'
  | 'research_pipeline_trace_summary'
  | 'research_pipeline_trace_preferred_mode'
  | 'research_pipeline_trace_oracle_family'
  | 'research_pipeline_trace_forecaster_count'
  | 'research_pipeline_trace_evidence_count'
  | 'strategy_shadow_summary'
  | 'resolution_anomalies'
  | 'execution_projection_gate_name'
  | 'execution_projection_preflight_only'
  | 'execution_projection_requested_path'
  | 'execution_pathways_highest_actionable_mode'
  | 'execution_projection_selected_path'
  | 'execution_projection_selected_path_status'
  | 'execution_projection_selected_path_effective_mode'
  | 'execution_projection_selected_path_reason_summary'
  | 'execution_projection_verdict'
  | 'execution_projection_highest_safe_requested_mode'
  | 'execution_projection_recommended_effective_mode'
  | 'execution_projection_manual_review_required'
  | 'execution_projection_ttl_ms'
  | 'execution_projection_expires_at'
  | 'execution_projection_blocking_reasons'
  | 'execution_projection_downgrade_reasons'
  | 'execution_projection_summary'
  | 'execution_projection_preflight_summary'
  | 'execution_projection_capital_status'
  | 'execution_projection_reconciliation_status'
  | 'execution_projection_selected_preview'
  | 'execution_projection_selected_preview_source'
  | 'execution_projection_selected_edge_bucket'
  | 'execution_projection_selected_pre_trade_gate'
  | 'execution_projection_selected_pre_trade_gate_verdict'
  | 'execution_projection_selected_pre_trade_gate_summary'
  | 'execution_projection_selected_path_net_edge_bps'
  | 'execution_projection_selected_path_minimum_net_edge_bps'
  | 'execution_projection_selected_path_canonical_size_usd'
  | 'execution_projection_selected_path_shadow_signal_present'
  | 'venue_feed_surface_summary'
  | 'venue_pathway_summary'
  | 'venue_pathway_highest_actionable_mode'
  | 'multi_venue_taxonomy'
  | 'multi_venue_execution_filter_reason_codes'
  | 'multi_venue_execution_filter_reason_code_counts'
  | 'shadow_arbitrage_present'
  | 'shadow_arbitrage_shadow_edge_bps'
  | 'shadow_arbitrage_recommended_size_usd'
  | 'shadow_arbitrage'
> & {
  approval_ticket?: PredictionMarketExecutionPathwaysApprovalTicket | null
  operator_thesis?: PredictionMarketExecutionPathwaysOperatorThesis | null
  research_pipeline_trace?: PredictionMarketExecutionPathwaysResearchPipelineTrace | null
}
type PredictionMarketRunDetailsWithArtifactAudit = StoredPredictionMarketRunDetails & PredictionMarketRunRuntimeHints & {
  manifest?: RunManifest
  artifact_refs?: PredictionMarketArtifactRef[]
  artifact_readback?: PredictionMarketArtifactReadbackIndex
  artifact_audit?: PredictionMarketArtifactAuditSummary
  forecast?: ForecastPacket | null
  recommendation?: MarketRecommendationPacket | null
  packet_bundle?: PredictionMarketPacketBundle
  paper_surface?: PredictionMarketReplaySurface | null
  replay_surface?: PredictionMarketReplaySurface | null
  paper_no_trade_zone_count?: number | null
  paper_no_trade_zone_rate?: number | null
  replay_no_trade_leg_count?: number | null
  replay_no_trade_leg_rate?: number | null
  provenance_bundle?: PredictionMarketProvenanceBundle
  research_bridge?: ResearchBridgeBundle | null
  research_sidecar?: MarketResearchSidecar | null
  timesfm_sidecar?: PredictionMarketTimesFMSidecar | null
  order_trace_audit?: PredictionMarketOrderTraceAudit | null
  venue_coverage?: PredictionMarketVenueCoverage
  execution_readiness?: PredictionMarketExecutionReadiness
  execution_pathways?: PredictionMarketExecutionPathwaysReport
  execution_projection?: PredictionMarketExecutionProjectionReport
  shadow_arbitrage?: ShadowArbitrageSimulationReport | null
  trade_intent_guard?: TradeIntentGuard
  multi_venue_execution?: MultiVenueExecution
  market_events?: PredictionMarketJsonArtifact
  market_positions?: PredictionMarketJsonArtifact
  source_audit_artifact?: PredictionMarketJsonArtifact | null
  rules_lineage_artifact?: PredictionMarketJsonArtifact | null
  catalyst_timeline_artifact?: PredictionMarketJsonArtifact | null
  world_state_artifact?: PredictionMarketJsonArtifact | null
  ticket_payload_artifact?: PredictionMarketJsonArtifact | null
  quant_signal_bundle?: PredictionMarketJsonArtifact | null
  decision_ledger_artifact?: PredictionMarketJsonArtifact | null
  calibration_report_artifact?: PredictionMarketJsonArtifact | null
  resolved_history_artifact?: PredictionMarketJsonArtifact | null
  cost_model_report_artifact?: PredictionMarketJsonArtifact | null
  walk_forward_report_artifact?: PredictionMarketJsonArtifact | null
  autopilot_cycle_summary_artifact?: PredictionMarketJsonArtifact | null
  research_memory_summary_artifact?: PredictionMarketJsonArtifact | null
  venue_feed_surface?: MarketFeedSurface
  microstructure_lab?: MicrostructureLabReport
  market_graph?: PredictionMarketMarketGraph | null
  strategy_candidate_packet?: StrategyCandidatePacket | null
  strategy_decision_packet?: StrategyDecisionPacket | null
  strategy_shadow_summary_packet?: StrategyShadowSummary | null
  strategy_shadow_report?: StrategyShadowReport | null
  execution_intent_preview?: ExecutionIntentPreview | null
  quote_pair_intent_preview?: QuotePairIntentPreview | null
  basket_intent_preview?: BasketIntentPreview | null
  latency_reference_bundle?: LatencyReferenceBundle | null
  resolution_anomaly_report?: ResolutionAnomalyReport | null
  autonomous_agent_report?: AutonomousAgentReport | null
}

const DEFAULT_MIN_EDGE_BPS = 150
const DEFAULT_MAX_SPREAD_BPS = 300
const DEFAULT_MIN_DEPTH_NEAR_TOUCH = 200
const DEFAULT_FORECAST_PIPELINE_ID = 'forecast-market'
const DEFAULT_FORECAST_PIPELINE_VERSION = 'baseline-v0'
const DEFAULT_FORECAST_ABSTENTION_POLICY = 'baseline-confidence-policy'
const DEFAULT_IDEMPOTENCY_WINDOW_SEC = 60
const DEFAULT_MIN_VENUE_HEALTH_SCORE = 0.7
const DEFAULT_BLOCKED_VENUE_HEALTH_SCORE = 0.4
const DEFAULT_PREDICT_HISTORY_LIMIT = 120
const DEFAULT_PREDICT_DEEP_HISTORY_LIMIT = 240

function resolvePredictionMarketAdviceRequestContract(
  input: AdviceExecutionInput,
  parsed: PredictionMarketsAdviceRequest,
): PredictionMarketAdviceRequestContract {
  const request_mode = parsed.request_mode ?? 'predict'
  const timesfmOptions = resolvePredictionMarketTimesFMOptions({
    requestMode: request_mode,
    requestedMode: parsed.timesfm_mode ?? null,
    requestedLanes: parsed.timesfm_lanes ?? null,
  })
  const response_variant = parsed.response_variant
    ?? (request_mode === 'predict_deep' ? 'research_heavy' : 'standard')
  const strategy_profile = input.strategy_profile != null
    ? parsed.strategy_profile
    : response_variant === 'execution_heavy'
      ? 'execution_only'
      : response_variant === 'research_heavy'
        ? 'forecast_only'
        : parsed.strategy_profile
  const history_limit = input.history_limit != null
    ? parsed.history_limit ?? DEFAULT_PREDICT_HISTORY_LIMIT
    : request_mode === 'predict_deep'
      ? DEFAULT_PREDICT_DEEP_HISTORY_LIMIT
      : DEFAULT_PREDICT_HISTORY_LIMIT

  return {
    request_mode,
    response_variant,
    strategy_profile,
    history_limit,
    variant_tags: parsed.variant_tags ?? [],
    timesfm_mode: timesfmOptions.mode,
    timesfm_lanes: timesfmOptions.lanes,
  }
}

function getSnapshotHistoryPoints(snapshot: { history?: unknown }): Array<unknown> {
  return Array.isArray(snapshot.history) ? snapshot.history : []
}

type SnapshotBuildInput = {
  marketId?: string
  slug?: string
  historyLimit?: number
}

type VenueAdapter = {
  listMarkets: (input: { limit?: number; search?: string }) => Promise<MarketDescriptor[]>
  buildSnapshot: (input: SnapshotBuildInput) => Promise<MarketSnapshot>
  toolsAvailable: string[]
  snapshotToolName: string
}

type PredictionMarketPipelineStatus = PredictionMarketDegradedMode

type PredictionMarketPipelineGuard = {
  mode: 'advise' | 'replay'
  venue: PredictionMarketVenue
  status: PredictionMarketPipelineStatus
  reasons: string[]
  breached_budgets: string[]
  metrics: {
    fetch_latency_ms: number
    decision_latency_ms: number
    snapshot_staleness_ms: number
  }
  venue_capabilities: VenueCapabilities
  venue_health: VenueHealthSnapshot
  venue_feed_surface: MarketFeedSurface
  budgets: PredictionMarketBudgets
}

function nowIso(): string {
  return new Date().toISOString()
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function nonNegativeInt(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.round(value))
}

function hashText(text: string): string {
  return computeConfigHash(text)
}

function hashDecisionPacket(decisionPacket: DecisionPacket | null | undefined): string | null {
  if (!decisionPacket) return null
  return hashText(JSON.stringify(decisionPacket))
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

const DEFENSE_ONLY_STRATEGY_FAMILIES = new Set<PredictionMarketStrategyCandidateKind>([
  'resolution_attack_watch',
  'resolution_sniping_watch',
])

function roundStrategyNumber(value: number, digits = 4): number {
  return Number(value.toFixed(digits))
}

function resolvePredictionMarketStrategyProfile(
  value: PredictionMarketsAdviceRequest['strategy_profile'] | null | undefined,
): PredictionMarketsAdviceRequest['strategy_profile'] {
  if (value === 'forecast_only' || value === 'execution_only') return value
  return 'hybrid'
}

function resolvePredictionMarketEnabledStrategyFamilies(
  values: readonly StrategyFamily[] | null | undefined,
): StrategyFamily[] {
  const normalized = uniqueStrings([...(values ?? [])]) as StrategyFamily[]
  return normalized.length > 0
    ? normalized
    : [...DEFAULT_ENABLED_STRATEGY_FAMILIES]
}

function strategySizeUsd(snapshot: MarketSnapshot): number {
  return Math.max(10, Math.round(snapshot.market.min_order_size ?? 10))
}

function priceForStrategySide(snapshot: MarketSnapshot, side: TradeIntent['side']): number {
  if (side === 'yes') {
    return clamp(snapshot.best_ask_yes ?? snapshot.yes_price ?? snapshot.midpoint_yes ?? 0.5, 0.01, 0.99)
  }

  return clamp(snapshot.no_price ?? (snapshot.yes_price != null ? 1 - snapshot.yes_price : 0.5), 0.01, 0.99)
}

function buildStrategyMarketRegimePayload(
  regime: PredictionMarketStrategyMarketRegime,
): MarketRegime {
  return {
    regime_id: regime.regime_id,
    label: regime.disposition,
    summary: regime.summary,
    confidence: regime.confidence_score,
    observed_at: regime.generated_at,
    signals: regime.key_signals,
    metadata: {
      disposition: regime.disposition,
      price_state: regime.price_state,
      freshness_state: regime.freshness_state,
      resolution_state: regime.resolution_state,
      research_state: regime.research_state,
      latency_state: regime.latency_state,
      stress_level: regime.stress_level,
      reasons: regime.reasons,
      anomaly_count: regime.anomaly_count,
      latency_reference_count: regime.latency_reference_count,
      signal_strength: regime.signal_strength,
      hours_to_resolution: regime.hours_to_resolution,
    },
  }
}

function buildStrategyCountsPayload(
  decision: PredictionMarketStrategyDecision,
): PredictionMarketStrategyCounts {
  return {
    total: decision.counts.total,
    actionable: decision.counts.advisory_count,
    ready: decision.counts.advisory_count,
    degraded: decision.counts.watch_count,
    blocked: decision.counts.defense_count,
    inactive: decision.mode === 'inactive' ? 1 : 0,
  }
}

function strategySeverityRank(
  severity: PredictionMarketStrategyResolutionAnomaly['severity'],
): number {
  switch (severity) {
    case 'critical':
      return 4
    case 'high':
      return 3
    case 'medium':
      return 2
    case 'low':
      return 1
  }
}

function mapStrategyResolutionAnomalyKind(
  kind: PredictionMarketStrategyResolutionAnomaly['anomaly_kind'],
): ResolutionAnomalyReport['anomaly_kind'] {
  switch (kind) {
    case 'policy_ambiguity':
    case 'policy_blocked':
    case 'graph_misalignment':
      return 'policy_mismatch'
    case 'signal_conflict':
    case 'cross_venue_resolution_mismatch':
      return 'oracle_conflict'
    case 'horizon_drift':
    case 'sniping_watch':
      return 'late_resolution'
    case 'attack_watch':
      return 'manual_override'
  }
}

function buildStrategyTradeIntentPreview(input: {
  runId: string
  snapshot: MarketSnapshot
  forecast: ForecastPacket
  recommendation: MarketRecommendationPacket
  candidate: PredictionMarketStrategyCandidate
}): TradeIntent {
  const inferredSide: TradeIntent['side'] =
    input.recommendation.side
    ?? ((input.recommendation.fair_value_yes ?? input.forecast.probability_yes) >= (input.recommendation.market_price_yes ?? input.snapshot.midpoint_yes ?? 0.5)
      ? 'yes'
      : 'no')
  const price = priceForStrategySide(input.snapshot, inferredSide)
  const sizeUsd = strategySizeUsd(input.snapshot)

  return {
    schema_version: input.snapshot.schema_version,
    intent_id: `${input.runId}:strategy:${input.candidate.kind}`,
    run_id: input.runId,
    venue: input.snapshot.venue,
    market_id: input.snapshot.market.market_id,
    side: inferredSide,
    size_usd: sizeUsd,
    limit_price: roundStrategyNumber(price),
    max_slippage_bps: Math.max(10, Math.round(input.snapshot.spread_bps ?? input.recommendation.spread_bps ?? 25)),
    max_unhedged_leg_ms: input.candidate.kind === 'latency_reference_spread' ? 250 : 1_000,
    time_in_force: input.candidate.kind === 'latency_reference_spread' ? 'ioc' : 'day',
    forecast_ref: `forecast:${input.forecast.market_id}:${input.forecast.produced_at}`,
    risk_checks_passed: true,
    created_at: input.recommendation.produced_at,
    notes: `${input.candidate.kind} strategy preview derived from the normalized strategy engine.`,
  }
}

function snapshotObservedAgeMs(snapshot: MarketSnapshot): number | null {
  const observedAt = snapshot.book?.fetched_at ?? snapshot.captured_at
  const parsed = Date.parse(observedAt)
  return Number.isFinite(parsed) ? Math.max(0, Date.now() - parsed) : null
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return uniqueStrings(value.map((entry) => asString(entry)))
}

function asJsonArtifact<T>(value: T): PredictionMarketJsonArtifact {
  return value as unknown as PredictionMarketJsonArtifact
}

function countReadyTimesFMLanes(sidecar: PredictionMarketTimesFMSidecar | null | undefined): number {
  if (!sidecar?.lanes) return 0
  return Object.values(sidecar.lanes).filter((lane) => lane?.status === 'ready').length
}

function hasReadyTimesFMLanes(sidecar: PredictionMarketTimesFMSidecar | null | undefined): boolean {
  return countReadyTimesFMLanes(sidecar) > 0
}

function buildPredictionMarketTimesFMFailureBundle(input: {
  runId: string
  snapshot: MarketSnapshot
  requestContract: PredictionMarketAdviceRequestContract
  reason: string
}): PredictionMarketTimesFMSidecar {
  const issue = input.reason.trim() || 'sidecar_failed'
  return {
    schema_version: 'v1',
    sidecar_name: 'timesfm_sidecar',
    run_id: input.runId,
    market_id: input.snapshot.market.market_id,
    venue: input.snapshot.venue,
    question: input.snapshot.market.question,
    requested_mode: input.requestContract.timesfm_mode,
    effective_mode: input.requestContract.timesfm_mode,
    requested_lanes: input.requestContract.timesfm_lanes,
    selected_lane: null,
    generated_at: nowIso(),
    health: {
      healthy: false,
      status: input.requestContract.timesfm_mode === 'required' ? 'blocked' : 'degraded',
      backend: 'unavailable',
      dependency_status: 'sidecar_failed',
      issues: [issue],
      summary: `TimesFM sidecar failed before producing a bundle: ${issue}`,
    },
    vendor: {
      source: 'master_snapshot',
      failure_mode: 'service_sidecar_wrapper',
    },
    lanes: {},
    summary: `TimesFM unavailable: ${issue}`,
    metadata: {
      request_mode: input.requestContract.request_mode,
      response_variant: input.requestContract.response_variant,
    },
  }
}

function formatUsdAmount(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'n/a'
  return `${roundStrategyNumber(value, 2).toFixed(2)} USD`
}

function buildMakerSpreadCaptureDiagnostics(input: {
  snapshot: MarketSnapshot
  makerSpreadCaptureEnabled: boolean
  regime: PredictionMarketStrategyMarketRegime
  strategyCandidate: PredictionMarketStrategyCandidate | null
  strategySummary: string | null
  shadowSummary: StrategyShadowSummary | null
  sizeUsd: number
  maxSlippageBps: number
}): MakerSpreadCaptureDiagnostics | null {
  if (!input.makerSpreadCaptureEnabled && input.strategyCandidate?.kind !== 'maker_spread_capture') return null

  const metrics = input.strategyCandidate?.metrics ?? {}
  const metadata = asRecord(input.strategyCandidate?.metadata)
  const spreadBps = asNumber(metrics.spread_bps) ?? asNumber(metadata?.spread_bps) ?? input.snapshot.spread_bps ?? null
  const quoteAgeMs = asNumber(metrics.quote_age_ms) ?? asNumber(metadata?.quote_age_ms) ?? snapshotObservedAgeMs(input.snapshot)
  const regimeFreshnessBudgetMs = asNumber(input.regime.maker_quote_freshness_budget_ms)
  const freshnessBudgetMs =
    asNumber(metrics.maker_quote_freshness_budget_ms)
    ?? asNumber(metadata?.maker_quote_freshness_budget_ms)
    ?? (
      input.strategyCandidate
        ? regimeFreshnessBudgetMs
        : regimeFreshnessBudgetMs != null
          ? Math.min(regimeFreshnessBudgetMs, 30_000)
          : 30_000
    )
    ?? null
  const makerQuoteState =
    asString(metrics.maker_quote_state) ??
    asString(metadata?.maker_quote_state) ??
    input.regime.maker_quote_state ??
    null
  const quoteFreshnessScore =
    asNumber(metrics.quote_freshness_score) ??
    asNumber(metadata?.quote_freshness_score) ??
    null
  const freshnessState =
    asString(metrics.freshness_state) ??
    asString(metadata?.freshness_state) ??
    input.regime.freshness_state ??
    null
  const latencyState =
    asString(metrics.latency_state) ??
    asString(metadata?.latency_state) ??
    input.regime.latency_state ??
    null
  const liquidityUsd = asNumber(metrics.liquidity_usd) ?? input.snapshot.market.liquidity_usd ?? input.snapshot.book?.depth_near_touch ?? null
  const depthNearTouch = input.snapshot.book?.depth_near_touch ?? null
  const transportMode = input.snapshot.book != null ? 'orderbook_snapshot' : 'snapshot_only'
  const inventorySummary = uniqueStrings([
    `inventory: preview size ${formatUsdAmount(input.sizeUsd)}`,
    liquidityUsd != null ? `liquidity ${formatUsdAmount(liquidityUsd)}` : null,
    depthNearTouch != null ? `depth near touch ${formatUsdAmount(depthNearTouch)}` : null,
    makerQuoteState != null ? `quote state ${makerQuoteState}` : null,
    input.strategySummary != null ? `strategy ${input.strategySummary}` : null,
  ]).join('; ')
  const adverseSelectionSummary = uniqueStrings([
    `adverse selection: spread ${spreadBps != null ? `${Math.round(spreadBps)} bps` : 'n/a'}`,
    `freshness score ${quoteFreshnessScore != null ? quoteFreshnessScore.toFixed(2) : 'n/a'}`,
    `quote age ${quoteAgeMs != null ? `${Math.round(quoteAgeMs)} ms` : 'n/a'}`,
    `freshness budget ${freshnessBudgetMs != null ? `${Math.round(freshnessBudgetMs)} ms` : 'n/a'}`,
    freshnessState != null ? `freshness state ${freshnessState}` : null,
    latencyState != null ? `latency state ${latencyState}` : null,
    input.shadowSummary?.summary != null ? `shadow ${input.shadowSummary.summary}` : null,
  ]).join('; ')
  const quoteTransportSummary = uniqueStrings([
    `quote transport: ${transportMode}`,
    input.snapshot.book?.fetched_at != null
      ? `fetched_at ${input.snapshot.book.fetched_at}`
      : `captured_at ${input.snapshot.captured_at}`,
    `source refs ${input.snapshot.source_urls.length}`,
    quoteAgeMs != null ? `observed age ${Math.round(quoteAgeMs)} ms` : null,
  ]).join('; ')
  const blockers = uniqueStrings([
    input.snapshot.market.active === false ? 'market_inactive' : null,
    input.snapshot.market.accepting_orders === false ? 'market_not_accepting_orders' : null,
    input.snapshot.market.restricted ? 'market_restricted' : null,
    spreadBps == null ? 'maker_spread_unavailable' : null,
    quoteAgeMs == null ? 'quote_transport_unavailable' : null,
    freshnessBudgetMs != null && quoteAgeMs != null && quoteAgeMs > freshnessBudgetMs
      ? 'quote_freshness_budget_exceeded'
      : null,
    freshnessBudgetMs != null && quoteAgeMs != null && quoteAgeMs > Math.round(freshnessBudgetMs * 0.8)
      ? 'quote_transport_near_freshness_limit'
      : null,
    makerQuoteState === 'guarded' ? 'maker_quote_guard_active' : null,
    makerQuoteState === 'blocked' ? 'maker_quote_blocked' : null,
    quoteFreshnessScore != null && quoteFreshnessScore < 0.5 ? 'quote_freshness_score_low' : null,
    depthNearTouch != null && input.sizeUsd > depthNearTouch * 0.06 ? 'inventory_size_exceeds_depth_guard' : null,
    liquidityUsd != null && input.sizeUsd > liquidityUsd * 0.01 ? 'inventory_size_exceeds_liquidity_guard' : null,
  ])
  const riskCaps = uniqueStrings([
    `recommended_size_usd:${input.sizeUsd.toFixed(2)}`,
    `max_slippage_bps:${input.maxSlippageBps}`,
    freshnessBudgetMs != null ? `quote_freshness_budget_ms:${Math.round(freshnessBudgetMs)}` : null,
    quoteAgeMs != null ? `quote_age_ms:${Math.round(quoteAgeMs)}` : null,
    liquidityUsd != null ? `inventory_cap_usd:${roundStrategyNumber(Math.min(input.sizeUsd, Math.max(10, liquidityUsd * 0.002)), 2).toFixed(2)}` : null,
    depthNearTouch != null ? `depth_cap_usd:${roundStrategyNumber(Math.min(input.sizeUsd, Math.max(10, depthNearTouch * 0.05)), 2).toFixed(2)}` : null,
  ])

  return {
    inventory_summary: inventorySummary || null,
    adverse_selection_summary: adverseSelectionSummary || null,
    quote_transport_summary: quoteTransportSummary || null,
    blockers,
    risk_caps: riskCaps,
  }
}

export function buildStrategyExecutionIntentArtifacts(input: {
  runId: string
  snapshot: MarketSnapshot
  forecast: ForecastPacket
  recommendation: MarketRecommendationPacket
  strategyProfile: PredictionMarketsAdviceRequest['strategy_profile']
  primaryCandidate: PredictionMarketStrategyCandidate | null
  strategySummary: string | null
  shadowSummary: StrategyShadowSummary | null
  makerSpreadCaptureDiagnostics: MakerSpreadCaptureDiagnostics | null
}): Pick<
  PredictionMarketStrategyRuntimeArtifacts,
  | 'execution_intent_preview'
  | 'quote_pair_intent_preview'
  | 'basket_intent_preview'
  | 'strategy_trade_intent_preview'
  | 'strategy_canonical_trade_intent_preview'
  | 'maker_spread_capture_inventory_summary'
  | 'maker_spread_capture_adverse_selection_summary'
  | 'maker_spread_capture_quote_transport_summary'
  | 'maker_spread_capture_blockers'
  | 'maker_spread_capture_risk_caps'
> {
  if (input.strategyProfile === 'forecast_only') {
    return {
      execution_intent_preview: null,
      quote_pair_intent_preview: null,
      basket_intent_preview: null,
      strategy_trade_intent_preview: null,
      strategy_canonical_trade_intent_preview: null,
      maker_spread_capture_inventory_summary: null,
      maker_spread_capture_adverse_selection_summary: null,
      maker_spread_capture_quote_transport_summary: null,
      maker_spread_capture_blockers: [],
      maker_spread_capture_risk_caps: [],
    }
  }

  const sizeUsd = strategySizeUsd(input.snapshot)
  const strategyFamily = input.primaryCandidate?.kind ?? (input.makerSpreadCaptureDiagnostics ? 'maker_spread_capture' : null)
  const summary = input.primaryCandidate?.summary ?? input.strategySummary

  if (!strategyFamily) {
    return {
      execution_intent_preview: null,
      quote_pair_intent_preview: null,
      basket_intent_preview: null,
      strategy_trade_intent_preview: null,
      strategy_canonical_trade_intent_preview: null,
      maker_spread_capture_inventory_summary: null,
      maker_spread_capture_adverse_selection_summary: null,
      maker_spread_capture_quote_transport_summary: null,
      maker_spread_capture_blockers: [],
      maker_spread_capture_risk_caps: [],
    }
  }

  if (strategyFamily === 'maker_spread_capture') {
    const makerDiagnostics = input.makerSpreadCaptureDiagnostics
    const makerSummary = uniqueStrings([
      summary,
      makerDiagnostics?.inventory_summary ?? null,
      makerDiagnostics?.adverse_selection_summary ?? null,
      makerDiagnostics?.quote_transport_summary ?? null,
    ]).join(' | ')
    const quotePairIntentPreview: QuotePairIntentPreview = {
      schema_version: input.snapshot.schema_version,
      preview_id: `${input.runId}:quote-pair-preview`,
      preview_kind: 'quote_pair',
      run_id: input.runId,
      venue: input.snapshot.venue,
      market_id: input.snapshot.market.market_id,
      strategy_profile: input.strategyProfile,
      strategy_family: strategyFamily,
      quotes: [
        {
          side: 'yes',
          price: roundStrategyNumber(clamp(input.snapshot.best_bid_yes ?? input.snapshot.yes_price ?? 0.49, 0.01, 0.99)),
          size_usd: sizeUsd,
        },
        {
          side: 'no',
          price: roundStrategyNumber(clamp(input.snapshot.no_price ?? (input.snapshot.best_ask_yes != null ? 1 - input.snapshot.best_ask_yes : 0.51), 0.01, 0.99)),
          size_usd: sizeUsd,
        },
      ],
      max_slippage_bps: Math.max(10, Math.round(input.snapshot.spread_bps ?? input.recommendation.spread_bps ?? 25)),
      summary: makerSummary,
      metadata: {
        strategy_summary: input.strategySummary,
        maker_spread_capture_inventory_summary: makerDiagnostics?.inventory_summary ?? null,
        maker_spread_capture_adverse_selection_summary: makerDiagnostics?.adverse_selection_summary ?? null,
        maker_spread_capture_quote_transport_summary: makerDiagnostics?.quote_transport_summary ?? null,
        maker_spread_capture_blockers: makerDiagnostics?.blockers ?? [],
        maker_spread_capture_risk_caps: makerDiagnostics?.risk_caps ?? [],
      },
    }

    return {
      execution_intent_preview: quotePairIntentPreview,
      quote_pair_intent_preview: quotePairIntentPreview,
      basket_intent_preview: null,
      strategy_trade_intent_preview: null,
      strategy_canonical_trade_intent_preview: null,
      maker_spread_capture_inventory_summary: makerDiagnostics?.inventory_summary ?? null,
      maker_spread_capture_adverse_selection_summary: makerDiagnostics?.adverse_selection_summary ?? null,
      maker_spread_capture_quote_transport_summary: makerDiagnostics?.quote_transport_summary ?? null,
      maker_spread_capture_blockers: makerDiagnostics?.blockers ?? [],
      maker_spread_capture_risk_caps: makerDiagnostics?.risk_caps ?? [],
    }
  }

  if (strategyFamily === 'intramarket_parity' || strategyFamily === 'logical_constraint_arb' || strategyFamily === 'negative_risk_basket') {
    const relatedMarketIds = input.primaryCandidate.related_market_ids.length > 0
      ? input.primaryCandidate.related_market_ids
      : [input.snapshot.market.market_id]
    const basketIntentPreview: BasketIntentPreview = {
      schema_version: input.snapshot.schema_version,
      preview_id: `${input.runId}:basket-preview`,
      preview_kind: 'basket',
      run_id: input.runId,
      venue: input.snapshot.venue,
      basket_id: `${input.runId}:${strategyFamily}`,
      strategy_profile: input.strategyProfile,
      strategy_family: strategyFamily,
      legs: [
        {
          market_id: input.snapshot.market.market_id,
          side: input.recommendation.side ?? 'yes',
          price: roundStrategyNumber(priceForStrategySide(input.snapshot, input.recommendation.side ?? 'yes')),
          size_usd: sizeUsd,
          notes: 'Base market leg for the strategy basket preview.',
        },
        ...relatedMarketIds.slice(0, 3).map((marketId, index) => ({
          market_id: marketId,
          side: strategyFamily === 'intramarket_parity'
            ? (index % 2 === 0 ? 'no' : 'yes')
            : (input.recommendation.side ?? 'yes'),
          price: roundStrategyNumber(strategyFamily === 'intramarket_parity'
            ? clamp(input.snapshot.no_price ?? 0.5, 0.01, 0.99)
            : clamp(input.snapshot.midpoint_yes ?? input.snapshot.yes_price ?? 0.5, 0.01, 0.99)),
          size_usd: sizeUsd,
          notes: strategyFamily === 'intramarket_parity'
            ? 'Parity hedge leg for the same-venue basket preview.'
            : 'Linked market leg derived from the normalized strategy graph.',
        })),
      ],
      max_slippage_bps: Math.max(10, Math.round(input.snapshot.spread_bps ?? input.recommendation.spread_bps ?? 40)),
      summary,
      metadata: {
        related_market_ids: input.primaryCandidate.related_market_ids,
      },
    }

    return {
      execution_intent_preview: basketIntentPreview,
      quote_pair_intent_preview: null,
      basket_intent_preview: basketIntentPreview,
      strategy_trade_intent_preview: null,
      strategy_canonical_trade_intent_preview: null,
      maker_spread_capture_inventory_summary: null,
      maker_spread_capture_adverse_selection_summary: null,
      maker_spread_capture_quote_transport_summary: null,
      maker_spread_capture_blockers: [],
      maker_spread_capture_risk_caps: [],
    }
  }

  if (strategyFamily === 'latency_reference_spread') {
    const tradeIntentPreview = buildStrategyTradeIntentPreview({
      runId: input.runId,
      snapshot: input.snapshot,
      forecast: input.forecast,
      recommendation: input.recommendation,
      candidate: input.primaryCandidate,
    })

    return {
      execution_intent_preview: {
        schema_version: input.snapshot.schema_version,
        preview_id: `${input.runId}:trade-preview`,
        preview_kind: 'trade',
        run_id: input.runId,
        venue: input.snapshot.venue,
        market_id: input.snapshot.market.market_id,
        strategy_profile: input.strategyProfile,
        strategy_family: strategyFamily,
        trade_intent_preview: tradeIntentPreview,
        summary,
        metadata: {
          strategy_summary: input.strategySummary,
        },
      },
      quote_pair_intent_preview: null,
      basket_intent_preview: null,
      strategy_trade_intent_preview: tradeIntentPreview,
      strategy_canonical_trade_intent_preview: tradeIntentPreview,
      maker_spread_capture_inventory_summary: null,
      maker_spread_capture_adverse_selection_summary: null,
      maker_spread_capture_quote_transport_summary: null,
      maker_spread_capture_blockers: [],
      maker_spread_capture_risk_caps: [],
    }
  }

  return {
    execution_intent_preview: {
      schema_version: input.snapshot.schema_version,
      preview_id: `${input.runId}:shadow-watch-preview`,
      preview_kind: 'shadow_watch',
      run_id: input.runId,
      venue: input.snapshot.venue,
      market_id: input.snapshot.market.market_id,
      strategy_profile: input.strategyProfile,
      strategy_family: strategyFamily,
      watch_kinds: [strategyFamily],
      notes: uniqueStrings([
        input.primaryCandidate.summary,
        input.shadowSummary?.summary ?? null,
      ]),
      summary,
      metadata: {
        disposition: input.primaryCandidate.disposition,
        severity: input.primaryCandidate.severity,
      },
    },
    quote_pair_intent_preview: null,
    basket_intent_preview: null,
    strategy_trade_intent_preview: null,
    strategy_canonical_trade_intent_preview: null,
    maker_spread_capture_inventory_summary: null,
    maker_spread_capture_adverse_selection_summary: null,
    maker_spread_capture_quote_transport_summary: null,
    maker_spread_capture_blockers: [],
    maker_spread_capture_risk_caps: [],
  }
}

function buildPredictionMarketStrategyRuntimeArtifacts(input: {
  runId: string
  snapshot: MarketSnapshot
  forecast: ForecastPacket
  recommendation: MarketRecommendationPacket
  resolutionPolicy: ResolutionPolicy
  evidencePackets: EvidencePacket[]
  researchSidecar?: MarketResearchSidecar | null
  researchBridge?: ResearchBridgeBundle | null
  crossVenueIntelligence?: PredictionMarketCrossVenueIntelligence | null
  microstructureLab?: MicrostructureLabReport | null
  marketGraph?: PredictionMarketMarketGraph | null
  pipelineGuard?: PredictionMarketPipelineGuard | null
  strategyProfile?: PredictionMarketsAdviceRequest['strategy_profile'] | null
  enabledStrategyFamilies?: readonly StrategyFamily[] | null
}): PredictionMarketStrategyRuntimeArtifacts {
  const strategyProfile = resolvePredictionMarketStrategyProfile(input.strategyProfile)
  const enabledStrategyFamilies = resolvePredictionMarketEnabledStrategyFamilies(input.enabledStrategyFamilies)
  const enabledSet = new Set(enabledStrategyFamilies)
  const regime = deriveMarketRegime({
    snapshot: input.snapshot,
    market_graph: input.marketGraph,
    cross_venue_summary: input.crossVenueIntelligence?.summary ?? null,
    microstructure_lab: input.microstructureLab ?? null,
    research_sidecar: input.researchSidecar ?? null,
    research_bridge: input.researchBridge ?? null,
    resolution_policy: input.resolutionPolicy,
    as_of_at: input.recommendation.produced_at,
  })
  const latencyReferences = deriveLatencyReferences({
    snapshot: input.snapshot,
    market_graph: input.marketGraph,
    cross_venue_summary: input.crossVenueIntelligence?.summary ?? null,
    microstructure_lab: input.microstructureLab ?? null,
    research_sidecar: input.researchSidecar ?? null,
    research_bridge: input.researchBridge ?? null,
    resolution_policy: input.resolutionPolicy,
    as_of_at: input.recommendation.produced_at,
  })
  const resolutionAnomalies = deriveResolutionAnomalies({
    snapshot: input.snapshot,
    market_graph: input.marketGraph,
    cross_venue_summary: input.crossVenueIntelligence?.summary ?? null,
    microstructure_lab: input.microstructureLab ?? null,
    research_sidecar: input.researchSidecar ?? null,
    research_bridge: input.researchBridge ?? null,
    resolution_policy: input.resolutionPolicy,
    as_of_at: input.recommendation.produced_at,
  })
  const rawDecision = buildStrategyDecision({
    snapshot: input.snapshot,
    market_graph: input.marketGraph,
    cross_venue_summary: input.crossVenueIntelligence?.summary ?? null,
    microstructure_lab: input.microstructureLab ?? null,
    research_sidecar: input.researchSidecar ?? null,
    research_bridge: input.researchBridge ?? null,
    resolution_policy: input.resolutionPolicy,
    as_of_at: input.recommendation.produced_at,
    regime,
    resolution_anomalies: resolutionAnomalies,
    latency_references: latencyReferences,
  })
  const filteredCandidates = rawDecision.candidates.filter((candidate) => enabledSet.has(candidate.kind))
  const counts = summarizeStrategyCounts(filteredCandidates)
  const primaryCandidate = filteredCandidates[0] ?? null
  const mode: PredictionMarketStrategyDecision['mode'] =
    counts.defense_count > 0 || regime.disposition === 'defense'
      ? 'defense'
      : counts.watch_count > 0 || regime.disposition === 'watch' || regime.disposition === 'stress'
        ? 'watch'
        : counts.advisory_count > 0
          ? 'advisory'
          : 'inactive'
  const decision: PredictionMarketStrategyDecision = {
    ...rawDecision,
    mode,
    candidate_count: counts.total,
    primary_candidate_id: primaryCandidate?.candidate_id ?? null,
    primary_candidate_kind: primaryCandidate?.kind ?? null,
    primary_candidate_summary: primaryCandidate?.summary ?? null,
    counts,
    candidates: filteredCandidates,
    summary: [
      `${mode} decision for ${input.snapshot.market.market_id}`,
      `candidates=${counts.total}`,
      `enabled_families=${enabledStrategyFamilies.join(',')}`,
      `regime=${regime.disposition}/${regime.resolution_state}/${regime.research_state}`,
    ].join('; '),
    reasons: uniqueStrings([
      ...rawDecision.reasons,
      `strategy_profile:${strategyProfile}`,
      `enabled_strategy_families:${enabledStrategyFamilies.join(',')}`,
    ]),
  }
  const strategyFamily = primaryCandidate?.kind ?? 'directional_forecast'
  const marketRegime = buildStrategyMarketRegimePayload(regime)
  const strategyCounts = buildStrategyCountsPayload(decision)
  const strategyShadowSummary: StrategyShadowSummary = {
    schema_version: input.snapshot.schema_version,
    shadow_id: `${input.runId}:strategy-shadow`,
    run_id: input.runId,
    venue: input.snapshot.venue,
    market_id: input.snapshot.market.market_id,
    strategy_profile: strategyProfile,
    strategy_family: strategyFamily,
    candidate_count: decision.candidate_count,
    decision_count: 1,
    disagreement_count: decision.counts.watch_count > 0 && decision.counts.defense_count > 0 ? 1 : 0,
    alignment_rate: decision.candidate_count > 0
      ? roundStrategyNumber(
        (decision.candidate_count - (decision.counts.watch_count > 0 && decision.counts.defense_count > 0 ? 1 : 0))
        / decision.candidate_count,
      )
      : 1,
    summary: decision.shadow_watch_summary.summary,
    metadata: {
      shadow_watch_summary: decision.shadow_watch_summary,
      strategy_counts: strategyCounts,
    },
  }
  const strategyShadowReport: StrategyShadowReport = {
    ...strategyShadowSummary,
    report_id: `${input.runId}:strategy-shadow-report`,
    generated_at: input.recommendation.produced_at,
    candidate_refs: filteredCandidates.map((candidate) => candidate.candidate_id),
    decision_refs: [`${input.runId}:strategy-decision`],
    outcome: mode === 'defense' ? 'blocked' : mode === 'watch' ? 'diverged' : 'aligned',
    notes: uniqueStrings([
      decision.summary,
      decision.shadow_watch_summary.summary,
    ]),
  }
  const makerSpreadCaptureDiagnostics = buildMakerSpreadCaptureDiagnostics({
    snapshot: input.snapshot,
    makerSpreadCaptureEnabled: enabledStrategyFamilies.includes('maker_spread_capture'),
    regime,
    strategyCandidate: primaryCandidate?.kind === 'maker_spread_capture' ? primaryCandidate : null,
    strategySummary: decision.summary,
    shadowSummary: strategyShadowSummary,
    sizeUsd: strategySizeUsd(input.snapshot),
    maxSlippageBps: Math.max(10, Math.round(input.snapshot.spread_bps ?? input.recommendation.spread_bps ?? 25)),
  })
  const executionIntentArtifacts = buildStrategyExecutionIntentArtifacts({
    runId: input.runId,
    snapshot: input.snapshot,
    forecast: input.forecast,
    recommendation: input.recommendation,
    strategyProfile,
    primaryCandidate,
    strategySummary: decision.summary,
    shadowSummary: strategyShadowSummary,
    makerSpreadCaptureDiagnostics,
  })
  const strongestAnomaly = [...resolutionAnomalies].sort((left, right) =>
    strategySeverityRank(right.severity) - strategySeverityRank(left.severity),
  )[0] ?? null
  const resolutionAnomalyReport = strongestAnomaly
    ? {
      schema_version: input.snapshot.schema_version,
      report_id: `${input.runId}:resolution-anomaly`,
      run_id: input.runId,
      venue: input.snapshot.venue,
      market_id: input.snapshot.market.market_id,
      anomaly_kind: mapStrategyResolutionAnomalyKind(strongestAnomaly.anomaly_kind),
      severity: strongestAnomaly.severity,
      detected_at: input.recommendation.produced_at,
      source_refs: uniqueStrings(strongestAnomaly.signal_refs),
      impacted_artifact_refs: uniqueStrings([
        `resolution_policy:${input.snapshot.market.market_id}`,
        strongestAnomaly.anomaly_id,
      ]),
      summary: strongestAnomaly.summary,
      notes: uniqueStrings([
        ...strongestAnomaly.reasons,
        ...resolutionAnomalies.slice(0, 3).map((anomaly) => anomaly.summary),
      ]),
      metadata: {
        anomalies: resolutionAnomalies.slice(0, 5),
      },
    } satisfies ResolutionAnomalyReport
    : null
  const bestLatencyReference = [...latencyReferences]
    .sort((left, right) => right.reference_score - left.reference_score)[0] ?? null
  const latencyReferenceBundle = latencyReferences.length > 0
    ? {
      schema_version: input.snapshot.schema_version,
      bundle_id: `${input.runId}:latency-reference-bundle`,
      run_id: input.runId,
      venue: input.snapshot.venue,
      market_id: input.snapshot.market.market_id,
      captured_at: input.recommendation.produced_at,
      decision_latency_budget_ms: input.pipelineGuard?.budgets.decision_latency_budget_ms,
      fetch_latency_budget_ms: input.pipelineGuard?.budgets.fetch_latency_budget_ms,
      snapshot_freshness_budget_ms: input.pipelineGuard?.budgets.snapshot_freshness_budget_ms,
      observed_latency_ms: bestLatencyReference?.quote_age_ms ?? bestLatencyReference?.freshness_gap_ms ?? undefined,
      p50_latency_ms: undefined,
      p95_latency_ms: undefined,
      p99_latency_ms: undefined,
      source_refs: uniqueStrings(latencyReferences.map((reference) => reference.reference_id)),
      summary: `${latencyReferences.length} latency references captured for ${input.snapshot.market.market_id}.`,
      metadata: {
        references: latencyReferences.slice(0, 5),
        best_reference_id: bestLatencyReference?.reference_id ?? null,
      },
    } satisfies LatencyReferenceBundle
    : null
  const autonomousAgentCandidate = filteredCandidates.find((candidate) => candidate.kind === 'autonomous_agent_advisory') ?? null
  const autonomousAgentReport = autonomousAgentCandidate
    ? {
      schema_version: input.snapshot.schema_version,
      report_id: `${input.runId}:autonomous-agent-report`,
      agent_id: 'agent:prediction-markets:strategy-layer',
      agent_role: 'strategy-orchestrator',
      run_id: input.runId,
      venue: input.snapshot.venue,
      market_id: input.snapshot.market.market_id,
      strategy_profile: strategyProfile,
      strategy_family: autonomousAgentCandidate.kind,
      market_regime: marketRegime,
      generated_at: input.recommendation.produced_at,
      observations: autonomousAgentCandidate.reasons.slice(0, 5),
      actions: uniqueStrings([
        mode === 'defense' ? 'hold_defense_watch' : null,
        mode === 'watch' ? 'continue_shadow_monitoring' : null,
        mode === 'advisory' ? 'keep_advisory_only_until_guards_clear' : null,
      ]),
      confidence: autonomousAgentCandidate.confidence_score,
      summary: autonomousAgentCandidate.summary,
      source_refs: autonomousAgentCandidate.evidence_refs,
      metadata: {
        candidate_id: autonomousAgentCandidate.candidate_id,
      },
    } satisfies AutonomousAgentReport
    : null
  const decisionChoice: StrategyDecisionPacket['decision'] =
    primaryCandidate == null
      ? 'defer'
      : strategyProfile === 'forecast_only'
        ? 'defer'
        : DEFENSE_ONLY_STRATEGY_FAMILIES.has(primaryCandidate.kind) || primaryCandidate.disposition !== 'advisory' || mode !== 'advisory'
          ? 'shadow'
          : 'adopt'
  const strategyCandidatePacket = primaryCandidate
    ? {
      schema_version: input.snapshot.schema_version,
      packet_version: '1.0.0',
      packet_kind: 'strategy_candidate',
      compatibility_mode: 'market_only',
      market_only_compatible: true,
      contract_id: `${PREDICTION_MARKETS_SCHEMA_VERSION}:strategy_candidate:1.0.0:market_only`,
      source_bundle_id: `${input.runId}:strategy_packet_bundle`,
      source_packet_refs: input.evidencePackets.map((packet) => packet.evidence_id),
      social_context_refs: [],
      market_context_refs: uniqueStrings([input.snapshot.market.market_id, ...primaryCandidate.related_market_ids]),
      run_id: input.runId,
      venue: input.snapshot.venue,
      market_id: input.snapshot.market.market_id,
      strategy_profile: strategyProfile,
      market_regime: marketRegime,
      correlation_id: primaryCandidate.candidate_id,
      summary: primaryCandidate.summary,
      rationale: decision.summary,
      metadata: {
        candidate_metrics: primaryCandidate.metrics,
        candidate_metadata: primaryCandidate.metadata,
        strategy_counts: strategyCounts,
        enabled_strategy_families: enabledStrategyFamilies,
      },
      candidate_id: primaryCandidate.candidate_id,
      strategy_family: primaryCandidate.kind,
      confidence: primaryCandidate.confidence_score,
      expected_edge_bps: typeof primaryCandidate.metrics.gap_bps === 'number'
        ? primaryCandidate.metrics.gap_bps
        : typeof primaryCandidate.metrics.price_gap_bps === 'number'
          ? primaryCandidate.metrics.price_gap_bps
          : null,
      execution_intent_preview: executionIntentArtifacts.execution_intent_preview,
      latency_reference_bundle: latencyReferenceBundle,
      resolution_anomaly_report: resolutionAnomalyReport,
      autonomous_agent_report: autonomousAgentReport,
      shadow_summary: strategyShadowSummary,
      created_at: input.recommendation.produced_at,
    } satisfies StrategyCandidatePacket
    : null
  const strategyDecisionPacket: StrategyDecisionPacket = {
    schema_version: input.snapshot.schema_version,
    packet_version: '1.0.0',
    packet_kind: 'strategy_decision',
    compatibility_mode: 'market_only',
    market_only_compatible: true,
    contract_id: `${PREDICTION_MARKETS_SCHEMA_VERSION}:strategy_decision:1.0.0:market_only`,
    source_bundle_id: `${input.runId}:strategy_packet_bundle`,
    source_packet_refs: uniqueStrings([
      ...(strategyCandidatePacket ? [strategyCandidatePacket.candidate_id] : []),
      ...input.evidencePackets.map((packet) => packet.evidence_id),
    ]),
    social_context_refs: [],
    market_context_refs: uniqueStrings([
      input.snapshot.market.market_id,
      ...filteredCandidates.flatMap((candidate) => candidate.related_market_ids),
    ]),
    run_id: input.runId,
    venue: input.snapshot.venue,
    market_id: input.snapshot.market.market_id,
    strategy_profile: strategyProfile,
    market_regime: marketRegime,
    correlation_id: `${input.runId}:strategy-decision`,
    summary: decision.summary,
    rationale: decision.primary_candidate_summary ?? decision.summary,
    metadata: {
      strategy_counts: strategyCounts,
      strategy_mode: decision.mode,
      enabled_strategy_families: enabledStrategyFamilies,
      resolution_anomalies: resolutionAnomalies.map((anomaly) => anomaly.summary),
      candidate_summaries: filteredCandidates.map((candidate) => candidate.summary),
      ...(makerSpreadCaptureDiagnostics != null ? {
        maker_spread_capture_inventory_summary: makerSpreadCaptureDiagnostics.inventory_summary,
        maker_spread_capture_adverse_selection_summary: makerSpreadCaptureDiagnostics.adverse_selection_summary,
        maker_spread_capture_quote_transport_summary: makerSpreadCaptureDiagnostics.quote_transport_summary,
        maker_spread_capture_blockers: makerSpreadCaptureDiagnostics.blockers,
        maker_spread_capture_risk_caps: makerSpreadCaptureDiagnostics.risk_caps,
      } : {}),
    },
    decision_id: `${input.runId}:strategy-decision`,
    candidate_refs: filteredCandidates.map((candidate) => candidate.candidate_id),
    selected_candidate_ref: primaryCandidate?.candidate_id ?? undefined,
    strategy_family: primaryCandidate?.kind,
    decision: decisionChoice,
    confidence: primaryCandidate?.confidence_score ?? regime.confidence_score,
    execution_intent_preview: executionIntentArtifacts.execution_intent_preview,
    latency_reference_bundle: latencyReferenceBundle,
    resolution_anomaly_report: resolutionAnomalyReport,
    autonomous_agent_report: autonomousAgentReport,
    shadow_report: strategyShadowReport,
    created_at: input.recommendation.produced_at,
  }

  return {
    strategy_profile: strategyProfile,
    enabled_strategy_families: enabledStrategyFamilies,
    strategy_candidate_packet: strategyCandidatePacket,
    strategy_decision_packet: strategyDecisionPacket,
    strategy_shadow_summary: strategyShadowSummary,
    strategy_shadow_report: strategyShadowReport,
    execution_intent_preview: executionIntentArtifacts.execution_intent_preview,
    quote_pair_intent_preview: executionIntentArtifacts.quote_pair_intent_preview,
    basket_intent_preview: executionIntentArtifacts.basket_intent_preview,
    latency_reference_bundle: latencyReferenceBundle,
    resolution_anomaly_report: resolutionAnomalyReport,
    autonomous_agent_report: autonomousAgentReport,
    strategy_name: primaryCandidate?.kind ?? null,
    market_regime_summary: regime.summary,
    primary_strategy_summary: decision.primary_candidate_summary ?? decision.summary,
    strategy_summary: decision.summary,
    strategy_counts: strategyCounts,
    resolution_anomalies: resolutionAnomalies.map((anomaly) => anomaly.summary),
    strategy_trade_intent_preview: executionIntentArtifacts.strategy_trade_intent_preview,
    strategy_canonical_trade_intent_preview: executionIntentArtifacts.strategy_canonical_trade_intent_preview,
    maker_spread_capture_inventory_summary: executionIntentArtifacts.maker_spread_capture_inventory_summary,
    maker_spread_capture_adverse_selection_summary: executionIntentArtifacts.maker_spread_capture_adverse_selection_summary,
    maker_spread_capture_quote_transport_summary: executionIntentArtifacts.maker_spread_capture_quote_transport_summary,
    maker_spread_capture_blockers: executionIntentArtifacts.maker_spread_capture_blockers,
    maker_spread_capture_risk_caps: executionIntentArtifacts.maker_spread_capture_risk_caps,
  }
}

function normalizePredictionMarketStrategyCounts(value: unknown): PredictionMarketStrategyCounts | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const counts = value as Record<string, unknown>
  const readNumber = (key: keyof PredictionMarketStrategyCounts) => {
    const next = counts[key]
    return typeof next === 'number' && Number.isFinite(next) ? next : 0
  }

  return {
    total: readNumber('total'),
    actionable: readNumber('actionable'),
    ready: readNumber('ready'),
    degraded: readNumber('degraded'),
    blocked: readNumber('blocked'),
    inactive: readNumber('inactive'),
  }
}

function resolveRollbackMode(input: {
  currentMode: string | null
  paperPath?: { status?: string | null } | null
  shadowPath?: { status?: string | null } | null
}): string | null {
  const paperReady = input.paperPath != null && input.paperPath.status !== 'blocked'
  const shadowReady = input.shadowPath != null && input.shadowPath.status !== 'blocked'

  if (input.currentMode === 'live') {
    if (shadowReady) return 'shadow'
    if (paperReady) return 'paper'
    return 'advisor'
  }

  if (input.currentMode === 'shadow') {
    if (paperReady) return 'paper'
    return 'advisor'
  }

  if (input.currentMode === 'paper') {
    return 'advisor'
  }

  if (shadowReady) return 'shadow'
  if (paperReady) return 'paper'
  return 'advisor'
}

function buildBlockedSurfaceSummary(input: {
  surfaceLabel: string
  blockedReasons: Array<string | null | undefined>
  rollbackMode?: string | null
  killSwitchSignals?: Array<string | null | undefined>
}): string {
  const reasons = uniqueStrings(input.blockedReasons).slice(0, 3)
  const parts = [
    `${input.surfaceLabel} surface is blocked: ${reasons.length > 0 ? reasons.join(';') : 'unavailable'}`,
  ]
  if (input.rollbackMode) {
    parts.push(`rollback=${input.rollbackMode}`)
  }
  const killSwitchSignals = uniqueStrings([...(input.killSwitchSignals ?? []), ...reasons])
  if (killSwitchSignals.some((reason) => reason.toLowerCase().includes('kill_switch'))) {
    parts.push('kill_switch=inspect')
  }
  return parts.join(' | ')
}

function firstDefined<T>(...values: Array<T | null | undefined>): T | undefined {
  for (const value of values) {
    if (value != null) return value
  }

  return undefined
}

function formatPercent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'n/a'
  return `${(value * 100).toFixed(1)}%`
}

function formatBps(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'n/a'
  return `${Math.round(value)} bps`
}

function firstPositiveNumber(...values: Array<number | null | undefined>): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
      return value
    }
  }

  return null
}

function derivePredictionMarketLiveStake(input: {
  liveSurface: PredictionMarketRunLivePlan
  details: PredictionMarketRunDetailsWithArtifactAudit
}): number {
  const livePath = asRecord(input.liveSurface.live_path)
  const canonicalPreview = asRecord(livePath?.canonical_trade_intent_preview)
  const selectedPreview = asRecord(input.liveSurface.execution_projection_selected_preview)
  const livePreview = asRecord(input.liveSurface.live_trade_intent_preview)
  const stake = firstPositiveNumber(
    typeof livePreview?.size_usd === 'number' ? livePreview.size_usd : null,
    typeof selectedPreview?.size_usd === 'number' ? selectedPreview.size_usd : null,
    typeof canonicalPreview?.size_usd === 'number' ? canonicalPreview.size_usd : null,
    input.details.execution_projection_selected_path_canonical_size_usd ?? null,
  )

  return stake ?? 10
}

function buildDecisionPacketThesisRationale(decisionPacket: DecisionPacket): string {
  return [
    decisionPacket.rationale_summary,
    `Decision packet recommendation: ${decisionPacket.recommendation}.`,
    `Probability estimate: ${formatPercent(decisionPacket.probability_estimate)}.`,
  ].join(' ')
}

function extractDecisionPacketFromEvidencePackets(evidencePackets: EvidencePacket[]): DecisionPacket | undefined {
  for (const packet of evidencePackets) {
    if (packet.type !== 'system_note') continue
    const parsed = decisionPacketSchema.safeParse(packet.metadata.decision_packet)
    if (parsed.success) return parsed.data
  }

  return undefined
}

type PredictionMarketResearchMemoryCapture = {
  entry: {
    memory_id: string
    provider_kind: string
    subject_id: string
    summary: string
  } | null
  artifact: PredictionMarketJsonArtifact | null
}

function capturePredictionMarketResearchMemory(input: {
  runId: string
  workspaceId: number
  venue: PredictionMarketVenue
  marketId: string
  marketSlug?: string | null
  recommendation: MarketRecommendationPacket
  forecast: ForecastPacket
  researchSidecar?: MarketResearchSidecar | null
  strategyName?: string | null
  marketRegime?: string | null
  requestMode?: PredictionMarketAdviceRequestMode | null
  responseVariant?: PredictionMarketAdviceResponseVariant | null
}): PredictionMarketResearchMemoryCapture {
  const pipelineTrace = input.researchSidecar?.synthesis.pipeline_trace
  const pipelineId = input.researchSidecar?.pipeline_version_metadata.pipeline_id
  if (!pipelineTrace || !pipelineId) {
    return {
      entry: null,
      artifact: null,
    }
  }

  try {
    const runtime = getPredictionMarketResearchMemoryRuntime()
    runtime.adapter.registerSimulation({
      simulation_id: input.runId,
      created_at: input.researchSidecar?.generated_at ?? null,
      source_ref: pipelineTrace.trace_id,
      tags: uniqueStrings([
        'prediction-markets',
        input.venue,
        input.recommendation.action,
        input.strategyName ?? null,
      ]),
      metadata: {
        workspace_id: input.workspaceId,
        market_id: input.marketId,
        market_slug: input.marketSlug ?? null,
        provider_kind: runtime.provider_kind,
      },
    })
    const entry = runtime.adapter.rememberResearchTrace({
      trace_id: pipelineTrace.trace_id,
      pipeline_id: pipelineId,
      venue: input.venue,
      market_id: input.marketId,
      generated_at: input.researchSidecar?.generated_at ?? new Date().toISOString(),
      summary:
        input.researchSidecar?.synthesis.supercompact_context.compact_summary
        || pipelineTrace.summary,
      trace: pipelineTrace,
      tags: uniqueStrings([
        input.requestMode ?? null,
        input.responseVariant ?? null,
        input.recommendation.action,
        input.strategyName ?? null,
      ]),
      metadata: {
        run_id: input.runId,
        workspace_id: input.workspaceId,
        market_slug: input.marketSlug ?? null,
        recommendation: input.recommendation.action,
        primary_strategy: input.strategyName ?? null,
        market_regime: input.marketRegime ?? null,
        provider_kind: runtime.provider_kind,
      },
    })
    runtime.adapter.rememberCrossSimulationObservation({
      simulation_id: input.runId,
      agent_id: 'research-pipeline',
      topic: input.marketId,
      content:
        input.researchSidecar?.synthesis.supercompact_context.compact_summary
        || pipelineTrace.summary,
      tags: uniqueStrings([
        'research',
        input.venue,
        input.recommendation.action,
        input.strategyName ?? null,
      ]),
      source_ref: pipelineTrace.trace_id,
      metadata: {
        pipeline_id: pipelineId,
        recommendation: input.recommendation.action,
        probability_yes: input.forecast.probability_yes,
      },
      created_at: input.researchSidecar?.generated_at ?? null,
    })
    runtime.adapter.rememberForesightForecast({
      forecast_id: `${input.runId}:research_forecast`,
      simulation_id: input.runId,
      subject_id: input.marketId,
      expected_outcome: `${input.recommendation.action}:${input.recommendation.side ?? 'none'}`,
      confidence: input.forecast.confidence ?? input.recommendation.confidence ?? null,
      generated_at: input.researchSidecar?.generated_at ?? null,
      tags: uniqueStrings([
        input.venue,
        input.recommendation.action,
        input.recommendation.side ?? null,
      ]),
      metadata: {
        probability_yes: input.forecast.probability_yes,
        fair_value_yes: input.recommendation.fair_value_yes,
      },
    })
    const simulationSummary = runtime.adapter.summarizeSimulation(input.runId)
    return {
      entry: {
        memory_id: entry.memory_id,
        provider_kind: runtime.provider_kind,
        subject_id: entry.subject_id,
        summary:
          typeof entry.content === 'object' && entry.content && 'summary' in entry.content
            ? String((entry.content as Record<string, unknown>).summary ?? '')
            : pipelineTrace.summary,
      },
      artifact: {
        simulation_id: simulationSummary.simulation_id,
        provider_kind: runtime.provider_kind,
        memory_count: simulationSummary.memory_count,
        top_memories: simulationSummary.top_memories.slice(0, 5).map((memory) => ({
          memory_id: memory.memory_id,
          kind: memory.kind,
          score: memory.score,
          subject_id: memory.subject_id,
          tags: memory.tags,
        })),
        topic_distribution: simulationSummary.topic_distribution,
        validation_summary: simulationSummary.validation_summary,
        summary: `memory=${simulationSummary.memory_count} provider=${runtime.provider_kind} validations=${simulationSummary.validation_summary.validations}`,
      },
    }
  } catch {
    return {
      entry: null,
      artifact: null,
    }
  }
}

function buildPredictionMarketCopiedPatternArtifacts(input: {
  runId: string
  venue: PredictionMarketVenue
  snapshot: MarketSnapshot
  resolutionPolicy: ResolutionPolicy
  evidencePackets: EvidencePacket[]
  forecast: ForecastPacket
  recommendation: MarketRecommendationPacket
  evaluationHistory?: ForecastEvaluationRecord[]
  evaluationHistorySourceSummary?: string | null
  researchSidecar?: MarketResearchSidecar | null
  strategyDecision?: StrategyDecisionPacket | null
  marketGraph?: PredictionMarketMarketGraph | null
  researchMemorySummary?: PredictionMarketJsonArtifact | null
}): PredictionMarketCopiedPatternArtifacts {
  const marketId = input.snapshot.market.market_id
  const marketQuestion = input.snapshot.market.question
  const asOf =
    input.recommendation.produced_at
    || input.forecast.produced_at
    || input.snapshot.captured_at
    || new Date().toISOString()
  const decisionPacket = extractDecisionPacketFromEvidencePackets(input.evidencePackets) ?? null
  const strategyExecutionIntentPreview = asRecord(input.strategyDecision?.execution_intent_preview)
  const strategyTradeIntentPreview = asRecord(strategyExecutionIntentPreview?.trade_intent_preview)
  const normalizedBookLevels = (
    levels: Array<{ price?: number | null; size?: number | null }> | null | undefined,
  ) =>
    (levels ?? [])
      .map((level) => ({
        price: asNumber(level?.price),
        size: asNumber(level?.size),
      }))
      .filter((level): level is { price: number; size: number } => level.price != null && level.size != null)
  const researchSidecarSummary =
    input.researchSidecar?.synthesis.supercompact_context.compact_summary
    ?? input.researchSidecar?.synthesis.pipeline_trace.summary
    ?? 'research sidecar'
  const worldStateSpine = buildPredictionMarketWorldStateSpine({
    market_id: marketId,
    market_question: marketQuestion,
    venue: input.venue,
    as_of: asOf,
    regime: input.strategyDecision?.market_regime?.label ?? null,
    source_audit: {
      market_id: marketId,
      as_of: asOf,
      sources: [
        {
          kind: 'market_data',
          title: 'Market snapshot',
          url: input.snapshot.market.source_urls?.[0] ?? null,
          captured_at: input.snapshot.captured_at,
          trust: 0.88,
          freshness: 0.9,
          evidence_strength: 0.82,
          source_refs: uniqueStrings([input.snapshot.market.market_id, input.snapshot.market.slug ?? null]),
        },
        {
          kind: 'official_docs',
          title: 'Resolution policy',
          url: input.resolutionPolicy.primary_sources?.[0] ?? null,
          captured_at: input.resolutionPolicy.evaluated_at,
          trust: input.resolutionPolicy.manual_review_required ? 0.62 : 0.84,
          freshness: 0.7,
          evidence_strength: input.resolutionPolicy.status === 'eligible' ? 0.82 : 0.58,
          notes: input.resolutionPolicy.reasons,
          source_refs: input.resolutionPolicy.primary_sources ?? [],
        },
        ...input.evidencePackets.map((packet) => ({
          kind:
            packet.type === 'market_data'
              || packet.type === 'orderbook'
              || packet.type === 'history'
              ? 'market_data'
              : packet.type === 'system_note' || packet.type === 'manual_thesis'
                  ? 'operator_brief'
                  : 'other',
          title: packet.title,
          url: packet.source_url ?? null,
          captured_at: packet.captured_at,
          trust: packet.type === 'market_data' || packet.type === 'orderbook' ? 0.82 : 0.56,
          freshness: packet.type === 'market_data' || packet.type === 'orderbook' ? 0.88 : 0.62,
          evidence_strength: packet.type === 'market_data' || packet.type === 'orderbook' ? 0.8 : 0.58,
          notes: [packet.summary],
          source_refs: uniqueStrings([packet.evidence_id, packet.source_url ?? null]),
        })),
        ...(decisionPacket ? [{
          kind: 'decision_packet' as const,
          title: 'Decision packet',
          captured_at: asOf,
          trust: 0.74,
          freshness: 0.7,
          evidence_strength: 0.76,
          notes: [decisionPacket.rationale_summary],
          source_refs: uniqueStrings([
            decisionPacket.correlation_id,
            ...(decisionPacket.source_packet_refs ?? []),
          ]),
        }] : []),
        ...(input.researchSidecar ? [{
          kind: 'operator_brief' as const,
          title: 'Research sidecar synthesis',
          captured_at: input.researchSidecar.generated_at,
          trust: 0.66,
          freshness: 0.72,
          evidence_strength: 0.64,
          notes: [researchSidecarSummary],
          source_refs: uniqueStrings([
            input.researchSidecar.generated_at ?? null,
          ]),
        }] : []),
      ],
    },
    rules_lineage: {
      market_id: marketId,
      as_of: asOf,
      rule_set_name: `${input.venue}-resolution-rules`,
      clauses: [
        {
          rule_id: 'resolution_text',
          title: 'Resolution text',
          text: input.resolutionPolicy.resolution_text || input.snapshot.market.description || marketQuestion,
          source_refs: input.resolutionPolicy.primary_sources ?? [],
          status: input.resolutionPolicy.manual_review_required ? 'conflicted' : 'active',
          introduced_at: input.resolutionPolicy.evaluated_at,
        },
        ...input.resolutionPolicy.reasons.map((reason, index) => ({
          rule_id: `resolution_reason_${index + 1}`,
          title: `Resolution reason ${index + 1}`,
          text: reason,
          source_refs: input.resolutionPolicy.primary_sources ?? [],
          status: reason.toLowerCase().includes('manual') ? 'conflicted' as const : 'active' as const,
          introduced_at: input.resolutionPolicy.evaluated_at,
        })),
      ],
    },
    catalyst_timeline: {
      market_id: marketId,
      as_of: asOf,
      catalysts: [
        input.snapshot.market.end_at ? {
          label: 'Market end',
          expected_at: input.snapshot.market.end_at,
          status: 'pending' as const,
          direction: 'neutral' as const,
          urgency: 0.9,
          source_refs: uniqueStrings([input.snapshot.market.market_id, input.snapshot.market.slug ?? null]),
          impact_hint: 'Trading window closes at market end.',
        } : null,
        input.recommendation.next_review_at ? {
          label: 'Next review',
          expected_at: input.recommendation.next_review_at,
          status: 'pending' as const,
          direction: 'neutral' as const,
          urgency: 0.55,
          source_refs: uniqueStrings([marketId, input.recommendation.resolution_policy_ref ?? null]),
          impact_hint: 'Operator review checkpoint.',
        } : null,
        input.resolutionPolicy.evaluated_at ? {
          label: 'Resolution evaluation',
          occurred_at: input.resolutionPolicy.evaluated_at,
          status: 'confirmed' as const,
          direction: 'neutral' as const,
          urgency: 0.4,
          source_refs: input.resolutionPolicy.primary_sources ?? [],
          impact_hint: 'Rules were last evaluated here.',
        } : null,
      ].filter(isPresent),
    },
    price_signal: {
      midpoint_yes: input.snapshot.midpoint_yes ?? input.snapshot.yes_price ?? null,
      market_price_yes: input.recommendation.market_price_yes ?? input.snapshot.yes_price ?? null,
      fair_value_yes: input.recommendation.fair_value_yes ?? input.forecast.probability_yes ?? null,
      spread_bps: input.snapshot.spread_bps ?? null,
    },
    ticket_kind: input.recommendation.action === 'bet' ? 'approval' : 'analysis',
    action: input.recommendation.action,
    size_usd: firstPositiveNumber(
      asNumber(strategyTradeIntentPreview?.size_usd),
      input.recommendation.requires_manual_review ? 25 : 10,
    ),
    limit_price_yes: input.recommendation.market_ask_yes ?? input.snapshot.best_ask_yes ?? null,
    operator_notes: uniqueStrings([
      input.recommendation.rationale,
      ...(input.recommendation.reasons ?? []),
    ]),
  })
  const binaryParity = assessBinaryParity({
    market_id: marketId,
    yes_price: input.snapshot.yes_price,
    no_price: input.snapshot.no_price,
    fee_rate: 0.02,
    min_edge_bps: 1,
  })
  const orderbookImbalance = assessOrderbookImbalance({
    market_id: marketId,
    question: marketQuestion,
    token_id: input.snapshot.yes_token_id ?? null,
    best_bid: input.snapshot.best_bid_yes,
    best_ask: input.snapshot.best_ask_yes,
    spread: input.snapshot.best_ask_yes != null && input.snapshot.best_bid_yes != null
      ? Math.max(0, input.snapshot.best_ask_yes - input.snapshot.best_bid_yes)
      : null,
    liquidity_usd: input.snapshot.market.liquidity_usd,
    volume_24h_usd: input.snapshot.market.volume_24h_usd,
    fetched_at: input.snapshot.captured_at,
    bids: normalizedBookLevels(input.snapshot.book?.bids),
    asks: normalizedBookLevels(input.snapshot.book?.asks),
    market_yes_price: input.snapshot.yes_price,
    fee_rate: 0.02,
  })
  const oddsDivergence = assessOddsDivergence({
    market_id: marketId,
    question: marketQuestion,
    market_yes_price: input.snapshot.yes_price,
    fee_rate: 0.02,
    bookmaker_quotes: [],
  })
  const spreadCapture = assessSpreadCapture({
    market_id: marketId,
    question: marketQuestion,
    best_bid: input.snapshot.best_bid_yes ?? input.snapshot.yes_price,
    best_ask: input.snapshot.best_ask_yes ?? input.snapshot.yes_price,
    fee_rate: 0.02,
    freshness_gap_ms: null,
    freshness_budget_ms: null,
    inventory_bias: input.strategyDecision?.strategy_family === 'maker_spread_capture' ? 0.1 : 0,
  })
  const kellySizing = calculateKellySizing({
    market_id: marketId,
    question: marketQuestion,
    probability_yes: input.forecast.probability_yes,
    market_yes_price: input.snapshot.yes_price,
    bankroll_usd: 1_000,
    max_position_usd: firstPositiveNumber(
      asNumber(strategyTradeIntentPreview?.size_usd),
      100,
    ) ?? 100,
    fee_rate: 0.02,
    preferred_side: input.recommendation.side ?? null,
  })
  const comparableGroup = input.marketGraph?.comparable_groups?.[0] ?? null
  const multiOutcomeParity = comparableGroup && comparableGroup.market_ids.length > 1
    ? assessMultiOutcomeParity({
      market_group_id: comparableGroup.group_id,
      min_edge_bps: 1,
      legs: comparableGroup.market_ids.map((market_id) => ({
        market_id,
        yes_price: input.snapshot.yes_price / comparableGroup.market_ids.length,
        fee_rate: 0.02,
      })),
    })
    : null
  const quantAssessments = [
    orderbookImbalance,
    oddsDivergence,
    binaryParity,
    spreadCapture,
    kellySizing,
    multiOutcomeParity,
  ].filter(isPresent)
  const viableQuantSignals = quantAssessments.filter((assessment) => assessment.viable)
  const quant_signal_bundle: PredictionMarketJsonArtifact = {
    run_id: input.runId,
    market_id: marketId,
    generated_at: asOf,
    assessments: {
      orderbook_imbalance: orderbookImbalance,
      odds_divergence: oddsDivergence,
      binary_parity: binaryParity,
      multi_outcome_parity: multiOutcomeParity,
      spread_capture: spreadCapture,
      kelly_sizing: kellySizing,
    },
    viable_count: viableQuantSignals.length,
    viable_kinds: viableQuantSignals.map((assessment) => String(assessment.kind)),
    summary:
      viableQuantSignals.length > 0
        ? `${viableQuantSignals.length} quant signals are viable; strongest=${String(viableQuantSignals[0]?.kind ?? 'none')}`
        : 'Quant signal pack collected but no signal clears fees, spread and viability gates.',
  }
  const resolved_history = buildResolvedHistoryDataset({
    runId: input.runId,
    venue: input.venue,
    marketId,
    generatedAt: asOf,
    evaluationHistory: input.evaluationHistory,
    defaults: {
      liquidity_usd: input.snapshot.market.liquidity_usd ?? null,
      volume_24h_usd: input.snapshot.market.volume_24h_usd ?? null,
      spread_bps: input.snapshot.spread_bps ?? null,
      size_usd: firstPositiveNumber(
        asNumber(strategyTradeIntentPreview?.size_usd),
        input.recommendation.requires_manual_review ? 25 : 10,
      ) ?? null,
      category: input.strategyDecision?.strategy_family ?? null,
    },
  })
  resolved_history.source_summary = input.evaluationHistorySourceSummary ?? null
  if (input.evaluationHistorySourceSummary) {
    resolved_history.notes = uniqueStrings([
      ...resolved_history.notes,
      input.evaluationHistorySourceSummary,
    ])
  }
  const cost_model_report = buildPredictionMarketCostModelReport({
    runId: input.runId,
    venue: input.venue,
    marketId,
    generatedAt: asOf,
    points: resolved_history.points,
  })
  const walk_forward_report = buildPredictionMarketWalkForwardReport({
    runId: input.runId,
    venue: input.venue,
    marketId,
    generatedAt: asOf,
    points: resolved_history.points,
    options: {
      weight_by_liquidity: true,
    },
  })
  const calibration_report_base = buildCalibrationReport(
    toCalibrationPointsFromResolvedHistory(resolved_history.points, {
      weight_by_liquidity: true,
    }),
    {
      bin_count: 10,
      minimum_points_for_summary: 3,
    },
  )
  const calibration_report: CalibrationReport = {
    ...calibration_report_base,
    notes: uniqueStrings([
      ...calibration_report_base.notes,
      `resolved_history_points:${resolved_history.resolved_records}`,
      `walk_forward_windows:${walk_forward_report.total_windows}`,
      cost_model_report.average_net_edge_bps == null
        ? null
        : `mean_net_edge_bps:${cost_model_report.average_net_edge_bps}`,
    ]),
  }
  let ledgerEntries: DecisionLedgerEntry[] = []
  ledgerEntries = appendDecisionLedgerEntry(ledgerEntries, {
    entry_type: 'PARAM_CHANGED',
    market_id: marketId,
    question: marketQuestion,
    cycle_id: input.runId,
    explanation: `World-state snapshot recorded for ${marketId}.`,
    tags: ['world_state', input.venue],
    source: 'clonehorse',
    confidence: worldStateSpine.world_state.confidence_score,
    data: {
      stage: 'scan',
      status: 'resolved',
      market_id: marketId,
      world_state_id: worldStateSpine.world_state.world_state_id,
      regime: input.strategyDecision?.market_regime?.label ?? null,
    },
  }).entries
  ledgerEntries = appendDecisionLedgerEntry(ledgerEntries, {
    entry_type: input.recommendation.action === 'bet' ? 'BET_PLACED' : 'BET_SKIPPED',
    market_id: marketId,
    question: marketQuestion,
    cycle_id: input.runId,
    explanation: worldStateSpine.ticket_payload.summary,
    tags: ['ticket', input.recommendation.action, input.recommendation.side ?? 'flat'],
    actor: 'swarm',
    source: 'service',
    confidence: input.recommendation.confidence ?? worldStateSpine.world_state.confidence_score,
    data: {
      stage: 'ticket',
      status: input.recommendation.action === 'bet' ? 'approved' : 'skipped',
      action_type: input.recommendation.action,
      side: input.recommendation.side,
      edge_bps: input.recommendation.edge_bps,
      size_usd: worldStateSpine.ticket_payload.size_usd,
      blocked_reason: input.recommendation.action === 'bet' ? null : 'no_trade_default',
    },
  }).entries
  ledgerEntries = appendDecisionLedgerEntry(ledgerEntries, {
    entry_type: 'CALIBRATION_UPDATE',
    market_id: marketId,
    question: marketQuestion,
    cycle_id: input.runId,
    explanation: calibration_report.notes.join('; ') || 'Calibration module attached without resolved outcomes yet.',
    tags: ['calibration'],
    actor: 'swarm',
    source: 'polfish',
    confidence: null,
    data: {
      stage: 'forecast',
      status: calibration_report.total_points > 0 ? 'resolved' : 'running',
      calibration_error: calibration_report.calibration_error,
      brier_score: calibration_report.brier_score,
      note_count: calibration_report.notes.length,
    },
  }).entries
  const autopilotRecords = [
    buildAutopilotCycleRecord({
      cycle_id: input.runId,
      stage: 'scan',
      status: 'resolved',
      market_id: marketId,
      action_type: 'scan',
      confidence: worldStateSpine.world_state.confidence_score,
      created_at: asOf,
      completed_at: asOf,
      note: worldStateSpine.source_audit.summary,
    }),
    buildAutopilotCycleRecord({
      cycle_id: input.runId,
      stage: 'research',
      status: input.researchSidecar ? 'resolved' : 'skipped',
      market_id: marketId,
      action_type: 'research',
      confidence: input.forecast.confidence ?? null,
      created_at: asOf,
      completed_at: asOf,
      note:
        input.researchSidecar?.synthesis.supercompact_context.compact_summary
        ?? input.researchSidecar?.synthesis.pipeline_trace.summary
        ?? 'No research sidecar attached.',
    }),
    buildAutopilotCycleRecord({
      cycle_id: input.runId,
      stage: 'forecast',
      status: 'approved',
      market_id: marketId,
      action_type: 'forecast',
      edge_bps: input.recommendation.edge_bps,
      confidence: input.forecast.confidence ?? input.recommendation.confidence ?? null,
      created_at: asOf,
      completed_at: asOf,
      note: `forecast_yes=${formatPercent(input.forecast.probability_yes)}`,
    }),
    buildAutopilotCycleRecord({
      cycle_id: input.runId,
      stage: 'ticket',
      status: input.recommendation.action === 'bet' ? 'approved' : 'skipped',
      market_id: marketId,
      action_type: input.recommendation.action,
      edge_bps: input.recommendation.edge_bps,
      confidence: input.recommendation.confidence ?? null,
      created_at: asOf,
      completed_at: asOf,
      blocked_reason: input.recommendation.action === 'bet' ? null : 'no_trade_default',
      note: worldStateSpine.ticket_payload.summary,
    }),
  ]
  const autopilot_cycle_summary = summarizeAutopilotCycles(autopilotRecords, {
    calibration_report,
    ledger_entries: ledgerEntries,
  })
  ledgerEntries = appendDecisionLedgerEntry(ledgerEntries, {
    entry_type: 'CYCLE_SUMMARY',
    market_id: marketId,
    question: marketQuestion,
    cycle_id: input.runId,
    explanation: `Autopilot cycle health is ${autopilot_cycle_summary.overview.health}.`,
    tags: ['autopilot', autopilot_cycle_summary.overview.health],
    actor: 'swarm',
    source: 'polfish',
    confidence: input.recommendation.confidence ?? null,
    data: {
      stage: 'monitor',
      status: autopilot_cycle_summary.overview.health === 'blocked' ? 'blocked' : 'resolved',
      edge_bps: input.recommendation.edge_bps,
      health: autopilot_cycle_summary.overview.health,
      total_cycles: autopilot_cycle_summary.total_cycles,
    },
  }).entries
  const decision_ledger: PredictionMarketCopiedPatternArtifacts['decision_ledger'] = {
    ledger_id: `${input.runId}:decision-ledger`,
    entries: ledgerEntries,
    summary: summarizeDecisionLedgerEntries(ledgerEntries),
  }

  return {
    ...worldStateSpine,
    quant_signal_bundle,
    decision_ledger,
    calibration_report,
    resolved_history: asJsonArtifact(resolved_history),
    cost_model_report: asJsonArtifact(cost_model_report),
    walk_forward_report: asJsonArtifact(walk_forward_report),
    autopilot_cycle_summary,
    research_memory_summary: input.researchMemorySummary ?? null,
  }
}

function buildPredictionMarketPacketBundle(input: {
  bundleId: string
  runId: string
  venue: PredictionMarketVenue
  marketId: string
  decisionPacket?: DecisionPacket | null
  strategyCandidatePacket?: StrategyCandidatePacket | null
  strategyDecisionPacket?: StrategyDecisionPacket | null
  strategyShadowReport?: StrategyShadowReport | null
  evidencePackets: EvidencePacket[]
  forecastPacket?: ForecastPacket | null
  recommendationPacket?: MarketRecommendationPacket | null
  researchBridge?: ResearchBridgeBundle | null
  marketEvents?: PredictionMarketJsonArtifact | null
  marketPositions?: PredictionMarketJsonArtifact | null
  paperSurface?: PredictionMarketJsonArtifact | null
  replaySurface?: PredictionMarketJsonArtifact | null
  orderTraceAudit?: PredictionMarketOrderTraceAudit | null
  tradeIntentGuard?: TradeIntentGuard | null
  multiVenueExecution?: MultiVenueExecution | null
  benchmarkPromotionReady?: boolean | null
  benchmarkPromotionGateKind?: PredictionMarketsBenchmarkGateSummary['promotion_gate_kind'] | null
  benchmarkPromotionBlockerSummary?: string | null
  benchmarkGateBlocksLive?: boolean | null
  benchmarkGateLiveBlockReason?: string | null
}): PredictionMarketPacketBundle {
  const advisorArchitecture = buildPredictionMarketAdvisorArchitecture({
    bundleId: input.bundleId,
    runId: input.runId,
    venue: input.venue,
    marketId: input.marketId,
    decisionPacket: input.decisionPacket ?? null,
    evidencePackets: input.evidencePackets,
    forecastPacket: input.forecastPacket ?? null,
    recommendationPacket: input.recommendationPacket ?? null,
    researchBridge: input.researchBridge ?? null,
    tradeIntentGuard: input.tradeIntentGuard ?? null,
    multiVenueExecution: input.multiVenueExecution ?? null,
    benchmarkPromotionReady: input.benchmarkPromotionReady ?? null,
    benchmarkPromotionGateKind: input.benchmarkPromotionGateKind ?? null,
    benchmarkPromotionBlockerSummary: input.benchmarkPromotionBlockerSummary ?? null,
    benchmarkGateBlocksLive: input.benchmarkGateBlocksLive ?? null,
    benchmarkGateLiveBlockReason: input.benchmarkGateLiveBlockReason ?? null,
  })

  return predictionMarketPacketBundleSchema.parse({
    schema_version: '1.0.0',
    bundle_id: input.bundleId,
    run_id: input.runId,
    venue: input.venue,
    market_id: input.marketId,
    advisor_architecture: advisorArchitecture,
    decision_packet: input.decisionPacket ?? undefined,
    strategy_candidate_packet: input.strategyCandidatePacket ?? undefined,
    strategy_decision_packet: input.strategyDecisionPacket ?? undefined,
    strategy_shadow_report: input.strategyShadowReport ?? undefined,
    evidence_packets: input.evidencePackets,
    forecast_packet: input.forecastPacket ?? undefined,
    recommendation_packet: input.recommendationPacket ?? undefined,
    research_bridge: input.researchBridge ?? undefined,
    market_events: input.marketEvents ?? undefined,
    market_positions: input.marketPositions ?? undefined,
    paper_surface: input.paperSurface ?? undefined,
    replay_surface: input.replaySurface ?? undefined,
    order_trace_audit: input.orderTraceAudit ?? undefined,
    trade_intent_guard: input.tradeIntentGuard ?? undefined,
    multi_venue_execution: input.multiVenueExecution ?? undefined,
  })
}

function buildPredictionMarketPacketContract(input: {
  packet:
    | DecisionPacket
    | ForecastPacket
    | MarketRecommendationPacket
    | null
    | undefined
  packetKind: 'decision' | 'forecast' | 'recommendation'
}): PredictionMarketPacketContract {
  const packet = input.packet as Record<string, unknown> | null | undefined
  const schemaVersion = typeof packet?.schema_version === 'string' && packet.schema_version.trim().length > 0
    ? packet.schema_version
    : PREDICTION_MARKETS_SCHEMA_VERSION
  const packetVersion = typeof packet?.packet_version === 'string' && packet.packet_version.trim().length > 0
    ? packet.packet_version
    : '1.0.0'
  const compatibilityMode = packet?.compatibility_mode === 'social_bridge' ? 'social_bridge' : 'market_only'
  const marketOnlyCompatible = typeof packet?.market_only_compatible === 'boolean'
    ? packet.market_only_compatible
    : true
  const contractId = typeof packet?.contract_id === 'string' && packet.contract_id.trim().length > 0
    ? packet.contract_id
    : `${schemaVersion}:${input.packetKind}:${packetVersion}:${compatibilityMode}`

  return {
    contract_id: contractId,
    schema_version: schemaVersion,
    packet_version: packetVersion,
    packet_kind: input.packetKind,
    compatibility_mode: compatibilityMode,
    market_only_compatible: marketOnlyCompatible,
  }
}

function buildPredictionMarketAdvisorArchitecture(input: {
  bundleId: string
  runId: string
  venue: PredictionMarketVenue
  marketId: string
  decisionPacket?: DecisionPacket | null
  evidencePackets: EvidencePacket[]
  forecastPacket?: ForecastPacket | null
  recommendationPacket?: MarketRecommendationPacket | null
  researchBridge?: ResearchBridgeBundle | null
  tradeIntentGuard?: TradeIntentGuard | null
  multiVenueExecution?: MultiVenueExecution | null
  benchmarkPromotionReady?: boolean | null
  benchmarkPromotionGateKind?: PredictionMarketsBenchmarkGateSummary['promotion_gate_kind'] | null
  benchmarkPromotionBlockerSummary?: string | null
  benchmarkGateBlocksLive?: boolean | null
  benchmarkGateLiveBlockReason?: string | null
}): PredictionMarketAdvisorArchitecture {
  const socialBridgeState = input.decisionPacket ? 'available' : 'unavailable'
  const researchBridgeState = input.researchBridge
    ? 'available'
    : input.evidencePackets.length > 0
      ? 'ready'
      : 'unavailable'
  const forecastContract = buildPredictionMarketPacketContract({
    packet: input.forecastPacket,
    packetKind: 'forecast',
  })
  const recommendationContract = buildPredictionMarketPacketContract({
    packet: input.recommendationPacket,
    packetKind: 'recommendation',
  })
  const decisionContract = buildPredictionMarketPacketContract({
    packet: input.decisionPacket,
    packetKind: 'decision',
  })
  const recommendationAction = input.recommendationPacket?.action ?? 'wait'
  const recommendationStatus = recommendationAction === 'bet' ? 'ready' : 'degraded'
  const executionStatus = input.tradeIntentGuard == null && input.multiVenueExecution == null
    ? 'skipped'
    : input.tradeIntentGuard?.verdict === 'blocked'
      ? 'blocked'
      : input.tradeIntentGuard?.verdict === 'allowed'
        ? 'ready'
        : 'degraded'
  const tradeIntentGuardMetadata = asRecord(input.tradeIntentGuard?.metadata)
  const benchmarkPromotionReady =
    input.benchmarkPromotionReady != null
      ? input.benchmarkPromotionReady
      : typeof tradeIntentGuardMetadata?.benchmark_promotion_ready === 'boolean'
        ? tradeIntentGuardMetadata.benchmark_promotion_ready
        : null
  const benchmarkLiveGate = resolvePredictionMarketBenchmarkLiveGateState({
    benchmark_promotion_ready: benchmarkPromotionReady,
    benchmark_gate_live_block_reason: input.benchmarkGateLiveBlockReason
      ?? (typeof tradeIntentGuardMetadata?.benchmark_gate_live_block_reason === 'string'
        ? tradeIntentGuardMetadata.benchmark_gate_live_block_reason
        : null),
    benchmark_promotion_blocker_summary: input.benchmarkPromotionBlockerSummary
      ?? (typeof tradeIntentGuardMetadata?.benchmark_promotion_blocker_summary === 'string'
        ? tradeIntentGuardMetadata.benchmark_promotion_blocker_summary
        : null),
    benchmark_promotion_gate_kind: input.benchmarkPromotionGateKind
      ?? (tradeIntentGuardMetadata?.benchmark_promotion_gate_kind === 'preview_only'
      || tradeIntentGuardMetadata?.benchmark_promotion_gate_kind === 'local_benchmark'
        ? tradeIntentGuardMetadata.benchmark_promotion_gate_kind
        : null),
    benchmark_gate_blocks_live: input.benchmarkGateBlocksLive ?? null,
    trade_intent_guard: input.tradeIntentGuard ?? null,
  })
  const benchmarkGateBlocksLive = benchmarkLiveGate.blocks_live
  const benchmarkGateLiveBlockReason = benchmarkLiveGate.live_block_reason
  const benchmarkPromotionGateKind = benchmarkLiveGate.promotion_gate_kind

  return predictionMarketAdvisorArchitectureSchema.parse({
    schema_version: PREDICTION_MARKETS_SCHEMA_VERSION,
    architecture_id: `${input.runId}:advisor_architecture`,
    mode: 'advisor',
    architecture_kind: 'reference_agentic',
    runtime: 'swarm',
    backend_mode: 'prediction-subproject',
    run_id: input.runId,
    venue: input.venue,
    market_id: input.marketId,
    social_bridge_state: socialBridgeState,
    research_bridge_state: researchBridgeState,
    packet_contracts: {
      decision: decisionContract,
      forecast: forecastContract,
      recommendation: recommendationContract,
    },
    packet_refs: {
      decision: input.decisionPacket?.correlation_id ?? null,
      forecast: input.forecastPacket ? `${input.runId}:forecast_packet` : null,
      recommendation: input.recommendationPacket ? `${input.runId}:recommendation_packet` : null,
      research_bridge: input.researchBridge?.bundle_id ?? null,
      trade_intent_guard: input.tradeIntentGuard?.gate_name ?? null,
      multi_venue_execution: input.multiVenueExecution?.gate_name ?? null,
    },
    stage_order: [
      'decision_packet_bridge',
      'research_bridge',
      'forecast_packet',
      'recommendation_packet',
      'execution_preflight',
    ],
    stages: [
      {
        stage_id: `${input.runId}:decision_packet_bridge`,
        stage_kind: 'decision_packet_bridge',
        role: 'social_bridge',
        status: input.decisionPacket ? 'ready' : 'skipped',
        input_refs: input.decisionPacket ? [input.decisionPacket.correlation_id] : [],
        output_refs: input.decisionPacket ? [input.decisionPacket.correlation_id] : [],
        contract_ids: input.decisionPacket ? [decisionContract.contract_id] : [],
        summary: input.decisionPacket
          ? 'Upstream decision packet is available as an advisor bridge input.'
          : 'Advisor run remains market-only because no decision packet bridge was provided.',
        metadata: {
          social_bridge_state: socialBridgeState,
        },
      },
      {
        stage_id: `${input.runId}:research_bridge`,
        stage_kind: 'research_bridge',
        role: 'evidence',
        status: input.researchBridge || input.evidencePackets.length > 0 ? 'ready' : 'skipped',
        input_refs: input.evidencePackets.map((packet) => packet.evidence_id),
        output_refs: input.researchBridge ? [input.researchBridge.bundle_id] : [],
        contract_ids: [],
        summary: input.researchBridge
          ? 'Research bridge bundle is available for replayable advisor context.'
          : 'Evidence packets remain the local advisory evidence surface.',
        metadata: {
          evidence_count: input.evidencePackets.length,
          research_bridge_state: researchBridgeState,
        },
      },
      {
        stage_id: `${input.runId}:forecast_packet`,
        stage_kind: 'forecast_packet',
        role: 'forecast',
        status: input.forecastPacket ? 'ready' : 'skipped',
        input_refs: input.evidencePackets.map((packet) => packet.evidence_id),
        output_refs: input.forecastPacket ? [`${input.runId}:forecast_packet`] : [],
        contract_ids: input.forecastPacket ? [forecastContract.contract_id] : [],
        summary: 'Canonical forecast packet for the advisor path.',
        metadata: {
          basis: input.forecastPacket?.basis ?? null,
          probability_yes: input.forecastPacket?.probability_yes ?? null,
        },
      },
      {
        stage_id: `${input.runId}:recommendation_packet`,
        stage_kind: 'recommendation_packet',
        role: 'recommendation',
        status: input.recommendationPacket ? recommendationStatus : 'skipped',
        input_refs: input.forecastPacket ? [`${input.runId}:forecast_packet`] : [],
        output_refs: input.recommendationPacket ? [`${input.runId}:recommendation_packet`] : [],
        contract_ids: input.recommendationPacket ? [recommendationContract.contract_id] : [],
        summary: 'Operator-facing recommendation packet derived from forecast and market state.',
        metadata: {
          action: input.recommendationPacket?.action ?? null,
          side: input.recommendationPacket?.side ?? null,
        },
      },
      {
        stage_id: `${input.runId}:execution_preflight`,
        stage_kind: 'execution_preflight',
        role: 'execution_gate',
        status: executionStatus,
        input_refs: [
          input.tradeIntentGuard?.gate_name ?? null,
          input.multiVenueExecution?.gate_name ?? null,
        ].filter(isPresent),
        output_refs: [
          input.tradeIntentGuard?.gate_name ?? null,
          input.multiVenueExecution?.gate_name ?? null,
        ].filter(isPresent),
        contract_ids: [],
        summary: benchmarkGateBlocksLive
          ? 'Execution stays preflight-first in the autonomous prediction subproject; governed live materialization is still blocked by the benchmark gate.'
          : 'Execution stays preflight-first in the autonomous prediction subproject; governed live materialization still requires an approved live intent and a configured transport.',
        metadata: {
          trade_intent_guard_verdict: input.tradeIntentGuard?.verdict ?? null,
          trade_intent_guard_blocked_reasons: input.tradeIntentGuard?.blocked_reasons ?? [],
          selected_path: input.tradeIntentGuard?.selected_path ?? null,
          highest_safe_mode: input.tradeIntentGuard?.highest_safe_mode ?? null,
          benchmark_promotion_ready: benchmarkPromotionReady,
          benchmark_gate_blocks_live: benchmarkGateBlocksLive,
          benchmark_gate_live_block_reason: benchmarkGateLiveBlockReason,
          benchmark_promotion_gate_kind: benchmarkPromotionGateKind,
          execution_candidate_count: input.multiVenueExecution?.execution_candidate_count ?? null,
        },
      },
    ],
    summary:
      'Reference advisor architecture for the prediction subproject: decision packet bridge -> research bridge -> forecast packet -> recommendation packet -> execution preflight.',
    metadata: {
      bundle_id: input.bundleId,
      evidence_count: input.evidencePackets.length,
    },
  })
}

function extractManualThesisFromEvidencePackets(evidencePackets: EvidencePacket[]): {
  thesisProbability?: number
  thesisRationale?: string
} {
  const manualThesis = evidencePackets.find((packet) => packet.type === 'manual_thesis')

  return {
    thesisProbability: typeof manualThesis?.metadata.thesis_probability === 'number'
      ? manualThesis.metadata.thesis_probability
      : undefined,
    thesisRationale: typeof manualThesis?.metadata.thesis_rationale === 'string'
      ? manualThesis.metadata.thesis_rationale
      : undefined,
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null
}

function asFiniteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function deriveTimesFMCrossVenueGapBps(
  crossVenueIntelligence: PredictionMarketCrossVenueIntelligence | null | undefined,
): number | null {
  const highestConfidenceCandidate = crossVenueIntelligence?.summary?.highest_confidence_candidate ?? null
  const candidateGap =
    asFiniteNumber(highestConfidenceCandidate?.net_spread_bps)
    ?? asFiniteNumber(highestConfidenceCandidate?.gross_spread_bps)
    ?? null
  if (candidateGap != null) return candidateGap

  for (const evaluation of crossVenueIntelligence?.evaluations ?? []) {
    const executableEdge = asRecord(evaluation.executable_edge)
    const evaluationGap =
      asFiniteNumber(executableEdge?.gap_bps)
      ?? asFiniteNumber(executableEdge?.price_gap_bps)
      ?? asFiniteNumber(evaluation.arbitrage_candidate?.net_spread_bps)
      ?? asFiniteNumber(evaluation.arbitrage_candidate?.gross_spread_bps)
      ?? null
    if (evaluationGap != null) return evaluationGap
  }

  return null
}

function asSurfaceRecord(value: unknown): PredictionMarketReplaySurface | null {
  const record = asRecord(value)
  return record ? record as PredictionMarketReplaySurface : null
}

function extractReplaySurfaceCounters(surface: PredictionMarketReplaySurface | null | undefined) {
  const record = asRecord(surface)
  return {
    no_trade_zone_count: typeof record?.no_trade_zone_count === 'number' ? record.no_trade_zone_count : null,
    no_trade_zone_rate: typeof record?.no_trade_zone_rate === 'number' ? record.no_trade_zone_rate : null,
    no_trade_leg_count: typeof record?.no_trade_leg_count === 'number' ? record.no_trade_leg_count : null,
    no_trade_leg_rate: typeof record?.no_trade_leg_rate === 'number' ? record.no_trade_leg_rate : null,
  }
}

function extractOrderTraceAudit(details: StoredPredictionMarketRunDetails): PredictionMarketOrderTraceAudit | null {
  const candidateArtifacts = details.artifacts.filter((artifact) =>
    ['paper_surface', 'replay_surface', 'pipeline_guard', 'runtime_guard', 'trade_intent_guard', 'multi_venue_execution'].includes(artifact.artifact_type),
  )

  for (const artifact of candidateArtifacts) {
    const record = asRecord(artifact.payload)
    const audit = asRecord(record?.order_trace_audit)
    if (audit) {
      return predictionMarketOrderTraceAuditSchema.parse(audit)
    }
  }

  return null
}

function readFirstString(record: Record<string, unknown> | null, keys: string[]): string | null {
  if (!record) return null
  for (const key of keys) {
    const value = asString(record[key])
    if (value) return value
  }
  return null
}

function averageProbabilityFromForecasterOutputs(outputs: Array<{
  probability_yes: number | null
  calibrated_probability_yes: number | null
  raw_weight: number
  normalized_weight: number
}>): {
  calibrated_probability_yes: number | null
  raw_probability_yes: number | null
  usable_count: number
} {
  const usableOutputs = outputs.filter((output) =>
    output.probability_yes != null || output.calibrated_probability_yes != null,
  )

  const totalWeight = usableOutputs.reduce((sum, output) => {
    const weight = Number.isFinite(output.normalized_weight) && output.normalized_weight > 0
      ? output.normalized_weight
      : output.raw_weight
    return sum + weight
  }, 0)

  if (usableOutputs.length === 0 || totalWeight <= 0) {
    return {
      calibrated_probability_yes: null,
      raw_probability_yes: null,
      usable_count: 0,
    }
  }

  const calibratedProbabilityYes = usableOutputs.reduce((sum, output) => {
    const weight = Number.isFinite(output.normalized_weight) && output.normalized_weight > 0
      ? output.normalized_weight
      : output.raw_weight
    return sum + ((output.calibrated_probability_yes ?? 0) * weight)
  }, 0) / totalWeight

  const rawProbabilityYes = usableOutputs.reduce((sum, output) => {
    const weight = Number.isFinite(output.normalized_weight) && output.normalized_weight > 0
      ? output.normalized_weight
      : output.raw_weight
    return sum + ((output.probability_yes ?? 0) * weight)
  }, 0) / totalWeight

  return {
    calibrated_probability_yes: Number(calibratedProbabilityYes.toFixed(4)),
    raw_probability_yes: Number(rawProbabilityYes.toFixed(4)),
    usable_count: usableOutputs.length,
  }
}

function computeSnapshotStalenessMs(capturedAt: string): number {
  const parsed = Date.parse(capturedAt)
  if (!Number.isFinite(parsed)) return 0
  return Math.max(0, Date.now() - parsed)
}

function forecastUsesMarketOnlyFairValue(forecast: ForecastPacket): boolean {
  return forecast.basis === 'market_midpoint'
    && (forecast.comparator_id == null || forecast.comparator_id === 'candidate_market_midpoint')
}

function forecastUsesResearchDrivenFairValue(forecast: ForecastPacket): boolean {
  return forecast.basis === 'market_midpoint' && !forecastUsesMarketOnlyFairValue(forecast)
}

function escalatePipelineStatus(
  current: PredictionMarketPipelineStatus,
  next: PredictionMarketPipelineStatus,
): PredictionMarketPipelineStatus {
  const rank: Record<PredictionMarketPipelineStatus, number> = {
    normal: 0,
    degraded: 1,
    blocked: 2,
  }

  return rank[next] > rank[current] ? next : current
}

function pickNextReviewDelayMs(input: {
  snapshot: MarketSnapshot
  resolutionPolicy: ResolutionPolicy
  recommendation: MarketRecommendationPacket
  forecast: ForecastPacket
}): number {
  const { recommendation, resolutionPolicy, forecast, snapshot } = input

  let delayMs = 60 * 60 * 1000

  if (recommendation.action === 'bet') {
    delayMs = 30 * 60 * 1000
  } else if (recommendation.action === 'wait') {
    delayMs = 20 * 60 * 1000
  } else {
    delayMs = forecast.basis === 'market_midpoint'
      ? 2 * 60 * 60 * 1000
      : 60 * 60 * 1000
  }

  if (resolutionPolicy.status === 'ambiguous') {
    delayMs = Math.max(delayMs, 4 * 60 * 60 * 1000)
  } else if (resolutionPolicy.status === 'closed') {
    delayMs = Math.max(delayMs, 12 * 60 * 60 * 1000)
  }

  if (recommendation.risk_flags.includes('incomplete_market_data')) {
    delayMs = Math.min(delayMs, 15 * 60 * 1000)
  }
  if (recommendation.risk_flags.includes('wide_spread')) {
    delayMs = Math.min(delayMs, 20 * 60 * 1000)
  }
  if (recommendation.risk_flags.includes('thin_orderbook')) {
    delayMs = Math.min(delayMs, 20 * 60 * 1000)
  }

  const anchor = Date.parse(recommendation.produced_at)
  const baseMs = Number.isFinite(anchor) ? anchor : Date.now()
  let nextMs = baseMs + delayMs

  const marketEnd = snapshot.market.end_at ? Date.parse(snapshot.market.end_at) : NaN
  if (Number.isFinite(marketEnd) && marketEnd > baseMs) {
    nextMs = Math.min(nextMs, marketEnd)
  }

  if (nextMs <= baseMs) {
    nextMs = baseMs + 60 * 1000
  }

  return nextMs
}

function enrichRecommendationPacket(input: {
  snapshot: MarketSnapshot
  resolutionPolicy: ResolutionPolicy
  forecast: ForecastPacket
  recommendation: MarketRecommendationPacket
  minEdgeBps?: number
  maxSpreadBps?: number
}): EnrichedMarketRecommendationPacket {
  const minEdgeBps = input.minEdgeBps ?? DEFAULT_MIN_EDGE_BPS
  const maxSpreadBps = input.maxSpreadBps ?? DEFAULT_MAX_SPREAD_BPS
  const depthNearTouch = input.snapshot.book?.depth_near_touch ?? null
  const spreadBps = input.recommendation.spread_bps ?? input.snapshot.spread_bps ?? null
  const impliedNoAsk = input.recommendation.market_bid_yes == null
    ? null
    : Number((1 - input.recommendation.market_bid_yes).toFixed(4))
  const fairValueNo = Number((1 - input.recommendation.fair_value_yes).toFixed(4))
  const usesMarketOnlyFairValue = forecastUsesMarketOnlyFairValue(input.forecast)
  const usesResearchDrivenFairValue = forecastUsesResearchDrivenFairValue(input.forecast)
  const whyNow: string[] = []
  const whyNotNow: string[] = []
  const watchConditions: string[] = []

  if (input.resolutionPolicy.status === 'eligible') {
    whyNow.push('Resolution policy is currently eligible for automation.')
  } else {
    whyNotNow.push(
      `Resolution policy is ${input.resolutionPolicy.status}, so execution stays blocked until the contract is clearer.`,
      ...input.resolutionPolicy.reasons,
    )
    watchConditions.push('Re-run when the resolution policy returns to eligible and any manual review is cleared.')
  }

  if (input.snapshot.book && input.recommendation.market_bid_yes != null && input.recommendation.market_ask_yes != null) {
    whyNow.push(
      `Executable YES prices are visible now at bid ${formatPercent(input.recommendation.market_bid_yes)} / ask ${formatPercent(input.recommendation.market_ask_yes)}.`,
    )
  } else {
    whyNotNow.push('Executable bid/ask data is incomplete, so the recommendation cannot be promoted to a firm execution decision.')
    watchConditions.push('Re-run once bid, ask, and near-touch book data are available together.')
  }

  if (spreadBps != null && spreadBps <= maxSpreadBps) {
    whyNow.push(`Spread ${formatBps(spreadBps)} is inside the ${formatBps(maxSpreadBps)} execution budget.`)
  } else if (spreadBps != null) {
    whyNotNow.push(`Spread ${formatBps(spreadBps)} is wider than the ${formatBps(maxSpreadBps)} budget.`)
    watchConditions.push(`Re-run when spread compresses to ${formatBps(maxSpreadBps)} or tighter.`)
  }

  if (depthNearTouch != null && depthNearTouch >= DEFAULT_MIN_DEPTH_NEAR_TOUCH) {
    whyNow.push(`Near-touch depth ${depthNearTouch} supports a first-pass executable check.`)
  } else if (depthNearTouch != null) {
    whyNotNow.push(
      `Near-touch depth ${depthNearTouch} is below the ${DEFAULT_MIN_DEPTH_NEAR_TOUCH} minimum, so fills could be fragile.`,
    )
    watchConditions.push(`Re-run when near-touch depth reaches at least ${DEFAULT_MIN_DEPTH_NEAR_TOUCH}.`)
  }

  if (input.forecast.basis === 'manual_thesis') {
    whyNow.push(
      `Manual thesis sets fair value to ${formatPercent(input.forecast.probability_yes)} with ${formatPercent(input.forecast.confidence)} confidence.`,
    )
  } else if (usesResearchDrivenFairValue) {
    whyNow.push(
      `Research-driven forecast sets fair value to ${formatPercent(input.forecast.probability_yes)} with ${formatPercent(input.forecast.confidence)} confidence.`,
    )
    watchConditions.push(
      'Re-run after the research pipeline, calibration, or benchmark gate materially changes the research-derived fair value.',
    )
  } else {
    whyNotNow.push('Current fair value is still derived from the market itself, so no exogenous edge is proven yet.')
    watchConditions.push('Re-run after a manual thesis or external evidence changes fair value away from the current market midpoint.')
  }

  if (input.forecast.abstention_reason) {
    whyNotNow.push(`Forecast abstention policy currently holds the packet at ${input.forecast.abstention_reason}.`)
    watchConditions.push('Re-run after the abstention policy clears or new evidence shifts the research-derived forecast.')
  }

  if (input.forecast.requires_manual_review) {
    whyNotNow.push('Forecast still requires manual review before execution promotion.')
    watchConditions.push('Re-run after manual review clears the forecast for execution promotion.')
  }

  if (input.recommendation.action === 'bet' && input.recommendation.side === 'yes') {
    whyNow.push(
      `Executable YES edge is ${formatBps(input.recommendation.edge_bps)} versus ask ${formatPercent(input.recommendation.market_ask_yes)}.`,
    )
    watchConditions.push(
      `Reassess if the YES edge falls below ${formatBps(minEdgeBps)} or if spread widens beyond ${formatBps(maxSpreadBps)}.`,
    )
  } else if (input.recommendation.action === 'bet' && input.recommendation.side === 'no') {
    whyNow.push(
      `Executable NO edge is ${formatBps(input.recommendation.edge_bps)} versus implied NO ask ${formatPercent(impliedNoAsk)}.`,
    )
    watchConditions.push(
      `Reassess if the NO edge falls below ${formatBps(minEdgeBps)} or if spread widens beyond ${formatBps(maxSpreadBps)}.`,
    )
  } else {
    if (input.recommendation.edge_bps < minEdgeBps) {
      whyNotNow.push(
        `Best executable edge is ${formatBps(input.recommendation.edge_bps)}, below the ${formatBps(minEdgeBps)} threshold.`,
      )
    }

    const yesTrigger = clamp(input.recommendation.fair_value_yes - (minEdgeBps / 10_000), 0, 1)
    watchConditions.push(`Re-run if the executable YES ask falls to ${formatPercent(yesTrigger)} or lower.`)

    const noTrigger = clamp(fairValueNo - (minEdgeBps / 10_000), 0, 1)
    watchConditions.push(`Re-run if the executable NO ask falls to ${formatPercent(noTrigger)} or lower.`)
  }

  if (input.forecast.basis === 'manual_thesis' && getSnapshotHistoryPoints(input.snapshot).length === 0) {
    whyNotNow.push('Frozen price history is missing, so replay quality is weaker than desired for a manual-thesis trade.')
    watchConditions.push('Re-run after freezing enough recent history to support replay and calibration.')
  }

  if (input.resolutionPolicy.manual_review_required && input.resolutionPolicy.status === 'eligible') {
    watchConditions.push('Keep an eye on resolution wording because manual review is still recommended.')
  }

  const rationale = (() => {
    if (input.recommendation.action === 'bet' && input.recommendation.side === 'yes') {
      return `Bet yes now: fair value ${formatPercent(input.recommendation.fair_value_yes)} is above executable YES ask ${formatPercent(input.recommendation.market_ask_yes)} by ${formatBps(input.recommendation.edge_bps)}, with spread ${formatBps(spreadBps)} and confidence ${formatPercent(input.recommendation.confidence)}.`
    }
    if (input.recommendation.action === 'bet' && input.recommendation.side === 'no') {
      return `Bet no now: implied NO fair value ${formatPercent(fairValueNo)} beats executable NO ask ${formatPercent(impliedNoAsk)} by ${formatBps(input.recommendation.edge_bps)}, with spread ${formatBps(spreadBps)} and confidence ${formatPercent(input.recommendation.confidence)}.`
    }
    if (input.recommendation.action === 'wait') {
      return `Wait: ${uniqueStrings(whyNotNow)[0] || 'market quality is not yet good enough for an execution decision.'}`
    }
    return `No trade: ${uniqueStrings(whyNotNow)[0] || `no executable edge clears the ${formatBps(minEdgeBps)} threshold right now.`}`
  })()

  return {
    ...input.recommendation,
    packet_version: input.recommendation.packet_version ?? '1.0.0',
    packet_kind: 'recommendation',
    compatibility_mode: input.recommendation.compatibility_mode ?? 'market_only',
    market_only_compatible: input.recommendation.market_only_compatible ?? true,
    contract_id:
      input.recommendation.contract_id
      ?? `${PREDICTION_MARKETS_SCHEMA_VERSION}:recommendation:1.0.0:${input.recommendation.compatibility_mode ?? 'market_only'}`,
    source_bundle_id:
      input.recommendation.source_bundle_id
      ?? `${input.snapshot.market.market_id}:advisor_packet_bundle`,
    source_packet_refs:
      input.recommendation.source_packet_refs?.length
        ? input.recommendation.source_packet_refs
        : [`${input.snapshot.market.market_id}:forecast_packet`],
    social_context_refs: input.recommendation.social_context_refs ?? [],
    market_context_refs:
      input.recommendation.market_context_refs?.length
        ? input.recommendation.market_context_refs
        : [input.snapshot.market.market_id, input.snapshot.market.slug ?? input.snapshot.market.market_id],
    resolution_policy_ref:
      input.recommendation.resolution_policy_ref
      ?? `${input.snapshot.market.market_id}:resolution_policy`,
    comparable_market_refs: input.recommendation.comparable_market_refs ?? [],
    requires_manual_review:
      input.recommendation.requires_manual_review
      ?? input.resolutionPolicy.manual_review_required
      ?? false,
    rationale,
    why_now: uniqueStrings(whyNow),
    why_not_now: uniqueStrings([...whyNotNow, ...input.recommendation.reasons]),
    watch_conditions: uniqueStrings(watchConditions),
    next_review_at: new Date(pickNextReviewDelayMs(input)).toISOString(),
  }
}

function getVenueAdapter(venue: PredictionMarketVenue): VenueAdapter {
  switch (venue) {
    case 'kalshi':
      return {
        listMarkets: listKalshiMarkets,
        buildSnapshot: buildKalshiSnapshot,
        toolsAvailable: ['kalshi:markets', 'kalshi:orderbook', 'kalshi:candlesticks'],
        snapshotToolName: 'kalshi.market_snapshot',
      }
    case 'polymarket':
      return {
        listMarkets: listPolymarketMarkets,
        buildSnapshot: buildPolymarketSnapshot,
        toolsAvailable: ['polymarket:gamma', 'polymarket:clob'],
        snapshotToolName: 'polymarket.market_snapshot',
      }
    default:
      throw new PredictionMarketsError(`Unsupported prediction market venue: ${venue}`, {
        status: 400,
        code: 'unsupported_venue',
      })
  }
}

export function buildPredictionMarketPipelineGuard(input: {
  venue: PredictionMarketVenue
  mode: 'advise' | 'replay'
  snapshot?: MarketSnapshot
  fetchLatencyMs?: number
}): PredictionMarketPipelineGuard {
  const venueCapabilities = getVenueCapabilitiesContract(input.venue)
  const venueHealth = getVenueHealthSnapshotContract(input.venue)
  const venueFeedSurface = getVenueFeedSurfaceContract(input.venue)
  const budgets = getVenueBudgetsContract(input.venue)
  const reasons: string[] = []
  const breachedBudgets: string[] = []
  const fetchLatencyMs = nonNegativeInt(input.fetchLatencyMs ?? 0)
  const snapshotStalenessMs = input.mode === 'advise' && input.snapshot
    ? computeSnapshotStalenessMs(input.snapshot.captured_at)
    : 0
  let status: PredictionMarketPipelineStatus = 'normal'

  if (input.mode === 'advise') {
    if (!venueCapabilities.supports_discovery || !venueCapabilities.supports_metadata) {
      status = escalatePipelineStatus(status, 'blocked')
      reasons.push('Venue capabilities do not meet the minimum read-only discovery requirements.')
    }

    if (!venueCapabilities.supports_orderbook) {
      status = escalatePipelineStatus(status, 'degraded')
      reasons.push('Venue does not expose an order book, so executable checks stay degraded.')
    }

    if (venueHealth.degraded_mode === 'blocked'
      || venueHealth.api_status === 'blocked'
      || venueHealth.health_score < DEFAULT_BLOCKED_VENUE_HEALTH_SCORE) {
      status = escalatePipelineStatus(status, 'blocked')
      reasons.push('Venue health is blocked, so advisory output is forced into a safe non-executable mode.')
    } else if (venueHealth.degraded_mode === 'degraded'
      || venueHealth.api_status === 'degraded'
      || venueHealth.health_score < DEFAULT_MIN_VENUE_HEALTH_SCORE) {
      status = escalatePipelineStatus(status, 'degraded')
      reasons.push('Venue health is degraded, so advisory output must stay conservative.')
    }

    if (budgets.fetch_latency_budget_ms && fetchLatencyMs > budgets.fetch_latency_budget_ms) {
      status = escalatePipelineStatus(status, 'degraded')
      breachedBudgets.push('fetch_latency_budget_ms')
      reasons.push(
        `Snapshot fetch latency ${fetchLatencyMs} ms breached budget ${budgets.fetch_latency_budget_ms} ms.`,
      )
    }

    if (snapshotStalenessMs > budgets.snapshot_freshness_budget_ms) {
      status = escalatePipelineStatus(status, 'degraded')
      breachedBudgets.push('snapshot_freshness_budget_ms')
      reasons.push(
        `Snapshot staleness ${snapshotStalenessMs} ms breached budget ${budgets.snapshot_freshness_budget_ms} ms.`,
      )
    }

    if (input.snapshot && !input.snapshot.book && venueCapabilities.supports_orderbook) {
      status = escalatePipelineStatus(status, 'degraded')
      reasons.push('Order book data is missing even though the venue should provide it.')
    }
  }

  return {
    mode: input.mode,
    venue: input.venue,
    status,
    reasons: uniqueStrings(reasons),
    breached_budgets: uniqueStrings(breachedBudgets),
    metrics: {
      fetch_latency_ms: fetchLatencyMs,
      decision_latency_ms: 0,
      snapshot_staleness_ms: snapshotStalenessMs,
    },
    venue_capabilities: venueCapabilities,
    venue_health: venueHealth,
    venue_feed_surface: venueFeedSurface,
    budgets,
  }
}

export function finalizePredictionMarketPipelineGuard(input: {
  guard: PredictionMarketPipelineGuard
  decisionLatencyMs: number
}): PredictionMarketPipelineGuard {
  const decisionLatencyMs = nonNegativeInt(input.decisionLatencyMs)
  const reasons = [...input.guard.reasons]
  const breachedBudgets = [...input.guard.breached_budgets]
  let status = input.guard.status

  if (decisionLatencyMs > input.guard.budgets.decision_latency_budget_ms) {
    status = escalatePipelineStatus(status, 'degraded')
    breachedBudgets.push('decision_latency_budget_ms')
    reasons.push(
      `Decision latency ${decisionLatencyMs} ms breached budget ${input.guard.budgets.decision_latency_budget_ms} ms.`,
    )
  }

  return {
    ...input.guard,
    status,
    reasons: uniqueStrings(reasons),
    breached_budgets: uniqueStrings(breachedBudgets),
    metrics: {
      ...input.guard.metrics,
      decision_latency_ms: decisionLatencyMs,
    },
  }
}

export function applyPredictionMarketPipelineGuardrails(input: {
  snapshot: MarketSnapshot
  resolutionPolicy: ResolutionPolicy
  forecast: ForecastPacket
  recommendation: EnrichedMarketRecommendationPacket
  guard: PredictionMarketPipelineGuard
  minEdgeBps?: number
  maxSpreadBps?: number
}): EnrichedMarketRecommendationPacket {
  if (input.guard.status === 'normal' && input.guard.breached_budgets.length === 0) {
    return input.recommendation
  }

  const reasons = [...input.recommendation.reasons, ...input.guard.reasons]
  const riskFlags = [...input.recommendation.risk_flags]

  if (input.guard.status === 'degraded') {
    riskFlags.push('venue_degraded')
  }
  if (input.guard.status === 'blocked') {
    riskFlags.push('venue_blocked')
  }
  if (input.guard.breached_budgets.length > 0) {
    riskFlags.push('budget_breach')
  }

  const guardedRecommendation = marketRecommendationPacketSchema.parse({
    ...input.recommendation,
    action: 'wait',
    side: null,
    reasons: uniqueStrings(reasons),
    risk_flags: uniqueStrings(riskFlags),
    produced_at: input.recommendation.produced_at,
  })

  return enrichRecommendationPacket({
    snapshot: input.snapshot,
    resolutionPolicy: input.resolutionPolicy,
    forecast: input.forecast,
    recommendation: guardedRecommendation,
    minEdgeBps: input.minEdgeBps,
    maxSpreadBps: input.maxSpreadBps,
  })
}

async function buildCrossVenueIntelligence(input: {
  snapshot: MarketSnapshot
  limitPerVenue?: number
}) {
  const venues = listPredictionMarketVenues().filter((venue) => venue !== input.snapshot.venue)
  const markets: MarketDescriptor[] = [input.snapshot.market]
  const snapshots: MarketSnapshot[] = [input.snapshot]
  const errors: string[] = []

  for (const venue of venues) {
    const adapter = getVenueAdapter(venue)
    try {
      const peers = await adapter.listMarkets({
        limit: input.limitPerVenue ?? 12,
        search: input.snapshot.market.question,
      })
      markets.push(...peers)
    } catch (error) {
      errors.push(
        `cross-venue discovery failed for ${venue}: ${error instanceof Error ? error.message : 'unknown error'}`,
      )
    }
  }

  const evaluations = findCrossVenueMatches({
    markets,
    snapshots,
    includeManualReview: true,
    maxPairs: 20,
  }).filter((evaluation) => (
    evaluation.match.left_market_ref.market_id === input.snapshot.market.market_id ||
    evaluation.match.right_market_ref.market_id === input.snapshot.market.market_id
  ))

  return normalizeCrossVenueIntelligence({
    evaluations,
    arbitrage_candidates: detectCrossVenueArbitrageCandidates(evaluations),
    errors,
  })
}

export function buildResolutionPolicy(snapshot: MarketSnapshot) {
  const reasons: string[] = []
  let status: 'eligible' | 'blocked' | 'closed' | 'ambiguous' = 'eligible'
  let manualReviewRequired = false

  if (snapshot.market.closed) {
    status = 'closed'
    reasons.push('market is closed')
  }

  if (!snapshot.market.active) {
    status = 'blocked'
    reasons.push('market is not active')
  }

  if (!snapshot.market.accepting_orders) {
    status = status === 'closed' ? status : 'blocked'
    reasons.push('market is not accepting orders')
  }

  if (!snapshot.market.is_binary_yes_no) {
    status = 'ambiguous'
    manualReviewRequired = true
    reasons.push('market is not a binary yes/no contract')
  }

  if (!snapshot.market.end_at) {
    manualReviewRequired = true
    reasons.push('market has no explicit end date')
  }

  if (snapshot.market.restricted) {
    reasons.push('market is marked restricted')
  }

  return resolutionPolicySchema.parse({
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    status,
    manual_review_required: manualReviewRequired,
    reasons,
    primary_sources: snapshot.source_urls,
    resolution_text: snapshot.market.description,
    evaluated_at: nowIso(),
  })
}

export function buildEvidencePackets(input: {
  snapshot: MarketSnapshot
  thesisProbability?: number
  thesisRationale?: string
  decisionPacket?: DecisionPacket
}): EvidencePacket[] {
  const packets: EvidencePacket[] = []
  const capturedAt = nowIso()
  const snapshot = input.snapshot

  packets.push(evidencePacketSchema.parse({
    evidence_id: `${snapshot.market.market_id}:market-data`,
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    type: 'market_data',
    title: 'Live market snapshot',
    summary: `Midpoint ${snapshot.midpoint_yes ?? snapshot.yes_price ?? 'n/a'}, liquidity ${snapshot.market.liquidity_usd ?? 'n/a'} USD.`,
    source_url: snapshot.source_urls[0],
    captured_at: capturedAt,
    content_hash: hashText(JSON.stringify(snapshot.market)),
    metadata: {
      yes_price: snapshot.yes_price,
      spread_bps: snapshot.spread_bps,
      liquidity_usd: snapshot.market.liquidity_usd,
    },
  }))

  if (snapshot.book) {
    packets.push(evidencePacketSchema.parse({
      evidence_id: `${snapshot.market.market_id}:orderbook`,
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      type: 'orderbook',
      title: 'Order book near-touch state',
      summary: `Best bid ${snapshot.book.best_bid ?? 'n/a'}, best ask ${snapshot.book.best_ask ?? 'n/a'}, depth ${snapshot.book.depth_near_touch ?? 'n/a'}.`,
      source_url: snapshot.source_urls.find((url) => url.includes('/book')),
      captured_at: capturedAt,
      content_hash: hashText(JSON.stringify(snapshot.book)),
      metadata: {
        best_bid: snapshot.book.best_bid,
        best_ask: snapshot.book.best_ask,
        depth_near_touch: snapshot.book.depth_near_touch,
      },
    }))
  }

  const historyPoints = getSnapshotHistoryPoints(snapshot)

  if (historyPoints.length > 0) {
    packets.push(evidencePacketSchema.parse({
      evidence_id: `${snapshot.market.market_id}:history`,
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      type: 'history',
      title: 'Recent price history',
      summary: `${historyPoints.length} historical points were frozen for replay.`,
      source_url: snapshot.source_urls.find((url) => url.includes('/prices-history')),
      captured_at: capturedAt,
      content_hash: hashText(JSON.stringify(historyPoints)),
      metadata: {
        history_points: historyPoints.length,
      },
    }))
  }

  if (input.decisionPacket) {
    const decisionPacketHash = hashDecisionPacket(input.decisionPacket)
    packets.push(evidencePacketSchema.parse({
      evidence_id: `${snapshot.market.market_id}:decision-packet:${(decisionPacketHash ?? 'unknown').slice(0, 12)}`,
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      type: 'system_note',
      title: 'Decision packet bridge',
      summary: [
        `Decision packet ${input.decisionPacket.correlation_id} estimates YES at ${formatPercent(input.decisionPacket.probability_estimate)}.`,
        `Band ${formatPercent(input.decisionPacket.confidence_band.low)} to ${formatPercent(input.decisionPacket.confidence_band.high)}.`,
        input.decisionPacket.rationale_summary,
      ].join(' '),
      captured_at: capturedAt,
      content_hash: decisionPacketHash ?? hashText(input.decisionPacket.correlation_id),
      metadata: {
        decision_packet: input.decisionPacket,
        decision_packet_hash: decisionPacketHash,
        correlation_id: input.decisionPacket.correlation_id,
        probability_estimate: input.decisionPacket.probability_estimate,
        confidence_band: input.decisionPacket.confidence_band,
        recommendation: input.decisionPacket.recommendation,
        rationale_summary: input.decisionPacket.rationale_summary,
        mode_used: input.decisionPacket.mode_used,
        engine_used: input.decisionPacket.engine_used,
        runtime_used: input.decisionPacket.runtime_used,
        risk_labels: input.decisionPacket.risks.map((risk) => risk.label),
        artifact_ids: input.decisionPacket.artifacts.map((artifact) => artifact.artifact_id),
      },
    }))
  }

  if (input.thesisProbability != null) {
    packets.push(evidencePacketSchema.parse({
      evidence_id: `${snapshot.market.market_id}:manual-thesis`,
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      type: 'manual_thesis',
      title: 'Manual thesis override',
      summary: input.thesisRationale || `Manual thesis probability set to ${input.thesisProbability}.`,
      captured_at: capturedAt,
      content_hash: hashText(`${input.thesisProbability}:${input.thesisRationale || ''}`),
      metadata: {
        thesis_probability: input.thesisProbability,
        thesis_rationale: input.thesisRationale,
      },
    }))
  }

  return packets
}

export function buildForecastPacket(input: {
  snapshot: MarketSnapshot
  evidencePackets: EvidencePacket[]
  thesisProbability?: number
  thesisRationale?: string
  researchSidecar?: MarketResearchSidecar | null
  researchBridge?: ResearchBridgeBundle | null
}): ForecastPacket {
  const basis = input.thesisProbability != null ? 'manual_thesis' : 'market_midpoint'
  const marketPrior = input.snapshot.midpoint_yes ?? input.snapshot.yes_price ?? 0.5
  const researchSynthesis = input.researchSidecar?.synthesis
  const abstentionSummary = researchSynthesis?.abstention_summary
  const weightedAggregatePreview = researchSynthesis?.weighted_aggregate_preview ?? null
  const independentForecasterOutputs = researchSynthesis?.independent_forecaster_outputs ?? []
  const researchAbstentionPolicy = researchSynthesis?.abstention_policy ?? null
  const independentForecastBlend = averageProbabilityFromForecasterOutputs(independentForecasterOutputs)
  const baseRateProbability = researchSynthesis?.base_rate_probability_hint ?? marketPrior
  const weightedAggregateProbability =
    weightedAggregatePreview?.weighted_probability_yes
    ?? weightedAggregatePreview?.weighted_probability_yes_raw
  const comparativeReport = researchSynthesis?.comparative_report ?? null
  const blendedResearchProbability =
    weightedAggregateProbability
    ?? independentForecastBlend.calibrated_probability_yes
    ?? independentForecastBlend.raw_probability_yes
    ?? baseRateProbability
  const probabilityYes = clamp(input.thesisProbability ?? blendedResearchProbability, 0, 1)
  const liquidityScore = clamp((input.snapshot.market.liquidity_usd ?? 0) / 50_000, 0, 1)
  const depthScore = clamp((input.snapshot.book?.depth_near_touch ?? 0) / 5_000, 0, 1)
  const spreadPenalty = clamp((input.snapshot.spread_bps ?? 999) / 500, 0, 1)
  const basisBoost = basis === 'manual_thesis' ? 0.1 : 0
  const researchHealthStatus = researchSynthesis?.health?.status ?? researchSynthesis?.retrieval_summary.health_status ?? null
  const researchHealthPenalty = researchHealthStatus === 'blocked'
    ? 0.06
    : researchHealthStatus === 'degraded'
      ? 0.03
      : 0
  const weightedPreviewPenalty = weightedAggregatePreview?.abstention_recommended ? 0.03 : 0
  const abstentionPolicyPenalty = researchAbstentionPolicy?.blocks_forecast ? 0.04 : 0
  const abstentionPenalty = (abstentionSummary?.recommended ? 0.08 : 0) + researchHealthPenalty + weightedPreviewPenalty + abstentionPolicyPenalty
  const weightedPreviewConfidenceBoost = weightedAggregatePreview
    ? clamp(
        (weightedAggregatePreview.coverage * 0.08) +
          (weightedAggregatePreview.weighted_delta_bps == null
            ? 0
            : clamp(Math.abs(weightedAggregatePreview.weighted_delta_bps) / 10_000, 0, 0.1)),
        0,
        0.15,
      )
    : 0
  const independentBlendConfidenceBoost = independentForecasterOutputs.length > 0
    ? clamp(independentForecastBlend.usable_count / independentForecasterOutputs.length * 0.05, 0, 0.05)
    : 0
  const confidence = clamp(
    0.2 +
      (0.25 * liquidityScore) +
      (0.2 * depthScore) +
      basisBoost +
      weightedPreviewConfidenceBoost +
      independentBlendConfidenceBoost -
      (0.2 * spreadPenalty) -
      abstentionPenalty,
    0.05,
    0.95,
  )

  const researchBridgePipeline = asRecord(input.researchBridge?.pipeline)
  const researchBridgeAbstentionPolicy = asRecord(input.researchBridge?.abstention_policy)
  const researchAggregateShiftedFromMarket =
    researchSynthesis != null && (
      (weightedAggregateProbability != null && Math.abs(weightedAggregateProbability - marketPrior) >= 0.0001)
      || (independentForecastBlend.calibrated_probability_yes != null
        && Math.abs(independentForecastBlend.calibrated_probability_yes - marketPrior) >= 0.0001)
      || (researchSynthesis.forecast_probability_yes_hint != null
        && Math.abs(researchSynthesis.forecast_probability_yes_hint - marketPrior) >= 0.0001)
      || independentForecasterOutputs.some((output) => output.role !== 'baseline' || output.forecaster_kind !== 'market_base_rate')
      || Math.abs(comparativeReport?.aggregate.delta_bps_vs_market_only ?? 0) > 0
      || Math.abs(comparativeReport?.forecast.delta_bps_vs_market_only ?? 0) > 0
    )
  const comparatorId = basis === 'manual_thesis'
    ? 'candidate_manual_thesis'
    : researchAggregateShiftedFromMarket
      ? 'candidate_research_aggregate'
      : 'candidate_market_midpoint'
  const comparatorKind = 'candidate_model'
  const pipelineId = readFirstString(researchBridgePipeline, ['pipeline_id', 'id', 'name']) ?? DEFAULT_FORECAST_PIPELINE_ID
  const pipelineVersion = readFirstString(researchBridgePipeline, ['pipeline_version', 'version']) ?? DEFAULT_FORECAST_PIPELINE_VERSION
  const abstentionPolicy = readFirstString(
    asRecord(researchAbstentionPolicy),
    ['policy_id', 'policy_name', 'name', 'id'],
  ) ?? readFirstString(
    researchBridgeAbstentionPolicy,
    ['policy_id', 'policy_name', 'name', 'id'],
  ) ?? DEFAULT_FORECAST_ABSTENTION_POLICY
  const researchKeyFactors = researchSynthesis?.key_factors ?? []
  const researchCounterarguments = researchSynthesis?.counterarguments ?? []
  const researchNoTradeHints = researchSynthesis?.no_trade_hints ?? []
  const forecasterCandidates = researchSynthesis?.forecaster_candidates ?? []
  const forecastPolicyVersion = readFirstString(asRecord(researchAbstentionPolicy), ['policy_version'])
  const researchAbstentionReasonCodes = abstentionSummary?.reason_codes ?? []
  const researchHealth = researchSynthesis?.health ?? null
  const researchHealthIssues = researchHealth?.issues ?? []
  const forecastAbstentionReason = weightedAggregatePreview?.abstention_recommended
    ? 'policy_threshold'
    : researchAbstentionPolicy?.blocks_forecast
      ? 'policy_threshold'
      : abstentionSummary?.recommended
        ? 'evidence_gap'
        : null
  const weightedContributorFragments = weightedAggregatePreview?.contributors.slice(0, 3).map((contributor) => (
    `${contributor.label}${contributor.calibrated_probability_yes != null ? `=${formatPercent(contributor.calibrated_probability_yes)}` : contributor.probability_yes != null ? `=${formatPercent(contributor.probability_yes)}` : ''}`
  )) ?? []
  const researchFragments = [
    `Comparator: ${comparatorId} (${comparatorKind}) on the ${basis} basis.`,
    `Pipeline: ${pipelineId}@${pipelineVersion}.`,
    weightedAggregatePreview
      ? `Weighted aggregate preview: ${formatPercent(weightedAggregatePreview.weighted_probability_yes ?? weightedAggregatePreview.weighted_probability_yes_raw)}${weightedAggregatePreview.weighted_delta_bps != null ? ` (${formatBps(weightedAggregatePreview.weighted_delta_bps)} vs base rate)` : ''}; coverage=${formatPercent(weightedAggregatePreview.coverage)}; usable=${weightedAggregatePreview.usable_contributor_count}/${weightedAggregatePreview.contributor_count}.`
      : null,
    independentForecasterOutputs.length > 0
      ? `Independent forecaster outputs: ${independentForecastBlend.usable_count}/${independentForecasterOutputs.length} usable output(s); calibrated blend ${formatPercent(independentForecastBlend.calibrated_probability_yes)}${independentForecastBlend.raw_probability_yes != null ? `; raw blend ${formatPercent(independentForecastBlend.raw_probability_yes)}` : ''}.`
      : null,
    independentForecasterOutputs.length > 0
      ? `Independent contributors: ${independentForecasterOutputs.slice(0, 3).map((output) => (
        `${output.label}${output.calibrated_probability_yes != null ? `=${formatPercent(output.calibrated_probability_yes)}` : output.probability_yes != null ? `=${formatPercent(output.probability_yes)}` : ''}`
      )).join(', ')}.`
      : null,
    `Abstention policy: ${abstentionPolicy}.`,
    researchAbstentionPolicy
      ? `Policy metadata: ${forecastPolicyVersion ? `version=${forecastPolicyVersion}; ` : ''}recommendation=${researchAbstentionPolicy.recommended ? 'abstain' : 'continue'}; blocks_forecast=${researchAbstentionPolicy.blocks_forecast ? 'true' : 'false'}${researchAbstentionPolicy.trigger_codes.length > 0 ? `; triggers=${researchAbstentionPolicy.trigger_codes.join(', ')}` : ''}${researchAbstentionPolicy.rationale ? `; detail=${researchAbstentionPolicy.rationale}` : ''}.`
      : abstentionSummary
        ? `Policy metadata: recommendation=${abstentionSummary.recommended ? 'abstain' : 'continue'}${forecastAbstentionReason ? `; reason=${forecastAbstentionReason}` : ''}${abstentionSummary.reasons[0] ? `; detail=${abstentionSummary.reasons[0]}` : ''}.`
        : null,
    researchSynthesis
      ? `Research retrieval: ${researchSynthesis.retrieval_summary.signal_count} signal(s), ${researchSynthesis.retrieval_summary.evidence_count} evidence packet(s), health=${researchSynthesis.retrieval_summary.health_status}.`
      : null,
    researchHealth
      ? `Research sidecar health: ${researchHealth.status} (${Math.round(researchHealth.completeness_score * 100)}% completeness, ${researchHealth.duplicate_signal_count} duplicate signal(s)).`
      : null,
    researchAbstentionReasonCodes.length > 0
      ? `Research abstention cues: ${researchAbstentionReasonCodes.join(', ')}.`
      : null,
    researchHealthIssues.length > 0
      ? `Research health issues: ${researchHealthIssues.slice(0, 3).join(' ')}`
      : null,
    researchSynthesis
      ? `Base rate anchor: ${formatPercent(researchSynthesis.base_rate_probability_hint)} (${researchSynthesis.base_rate_rationale_hint}).`
      : null,
    weightedAggregatePreview?.rationale
      ? `Weighted aggregate rationale: ${weightedAggregatePreview.rationale}`
      : null,
    forecasterCandidates.length > 0
      ? `Forecaster candidates: ${forecasterCandidates.slice(0, 3).map((candidate) => (
        `${candidate.label}[${candidate.role}/${candidate.status}]${candidate.probability_yes != null ? `=${formatPercent(candidate.probability_yes)}` : ''}`
      )).join(', ')}.`
      : null,
    weightedContributorFragments.length > 0
      ? `Weighted contributors: ${weightedContributorFragments.join(', ')}.`
      : null,
    researchKeyFactors.length > 0 ? `Key factors: ${researchKeyFactors.slice(0, 3).join(' ')}` : null,
    researchCounterarguments.length > 0 ? `Counterarguments: ${researchCounterarguments.slice(0, 3).join(' ')}` : null,
    researchNoTradeHints.length > 0 ? `No-trade hints: ${researchNoTradeHints.slice(0, 2).join(' ')}` : null,
  ].filter((fragment): fragment is string => Boolean(fragment))

  const rationale = [
    basis === 'manual_thesis'
      ? (input.thesisRationale || 'Manual thesis applied on top of live market data.')
      : comparatorId === 'candidate_research_aggregate'
        ? 'Research-driven forecast blends exogenous signals against the live market baseline.'
        : 'Baseline forecast anchored on live market midpoint and current order book quality.',
    ...researchFragments,
  ].join(' ')

  return forecastPacketSchema.parse({
    packet_version: '1.0.0',
    packet_kind: 'forecast',
    compatibility_mode: 'market_only',
    market_only_compatible: true,
    contract_id: `${PREDICTION_MARKETS_SCHEMA_VERSION}:forecast:1.0.0:market_only`,
    source_bundle_id: `${input.snapshot.market.market_id}:advisor_packet_bundle`,
    source_packet_refs: input.evidencePackets.map((packet) => packet.evidence_id),
    social_context_refs: input.researchBridge?.social_context_refs ?? [],
    market_context_refs: [
      input.snapshot.market.market_id,
      input.snapshot.market.slug ?? input.snapshot.market.market_id,
    ],
    market_id: input.snapshot.market.market_id,
    venue: input.snapshot.venue,
    basis,
    model: PREDICTION_MARKETS_BASELINE_MODEL,
    probability_yes: Number(probabilityYes.toFixed(6)),
    confidence: Number(confidence.toFixed(4)),
    rationale,
    evidence_refs: input.evidencePackets.map((packet) => packet.evidence_id),
    comparator_id: comparatorId,
    comparator_kind: comparatorKind,
    pipeline_id: pipelineId,
    pipeline_version: pipelineVersion,
    abstention_policy: abstentionPolicy,
    abstention_reason: forecastAbstentionReason ?? undefined,
    requires_manual_review: Boolean(
      researchAbstentionPolicy?.manual_review_required
      || abstentionSummary?.recommended
      || weightedAggregatePreview?.abstention_recommended,
    ),
    produced_at: nowIso(),
  })
}

export function buildRecommendationPacket(input: {
  snapshot: MarketSnapshot
  resolutionPolicy: ReturnType<typeof buildResolutionPolicy>
  forecast: ForecastPacket
  minEdgeBps?: number
  maxSpreadBps?: number
}): EnrichedMarketRecommendationPacket {
  const minEdgeBps = input.minEdgeBps ?? DEFAULT_MIN_EDGE_BPS
  const maxSpreadBps = input.maxSpreadBps ?? DEFAULT_MAX_SPREAD_BPS
  const marketBid = input.snapshot.best_bid_yes ?? input.snapshot.yes_price ?? null
  const marketAsk = input.snapshot.best_ask_yes ?? input.snapshot.yes_price ?? null
  const marketPrice = input.snapshot.midpoint_yes ?? input.snapshot.yes_price ?? null
  const spreadBps = input.snapshot.spread_bps ?? null
  const usesMarketOnlyFairValue = forecastUsesMarketOnlyFairValue(input.forecast)
  const usesResearchDrivenFairValue = forecastUsesResearchDrivenFairValue(input.forecast)
  const reasons: string[] = []
  const riskFlags: string[] = []
  const finalize = (recommendation: MarketRecommendationPacket) => enrichRecommendationPacket({
    snapshot: input.snapshot,
    resolutionPolicy: input.resolutionPolicy,
    forecast: input.forecast,
    recommendation,
    minEdgeBps,
    maxSpreadBps,
  })

  if (input.resolutionPolicy.status !== 'eligible') {
    reasons.push(...input.resolutionPolicy.reasons)
    return finalize(marketRecommendationPacketSchema.parse({
      market_id: input.snapshot.market.market_id,
      venue: input.snapshot.venue,
      action: 'wait',
      side: null,
      confidence: input.forecast.confidence,
      fair_value_yes: input.forecast.probability_yes,
      market_price_yes: marketPrice,
      market_bid_yes: marketBid,
      market_ask_yes: marketAsk,
      edge_bps: 0,
      spread_bps: spreadBps,
      reasons,
      risk_flags: ['resolution_guard'],
      produced_at: nowIso(),
    }))
  }

  if (!input.snapshot.book || marketBid == null || marketAsk == null || marketPrice == null) {
    reasons.push('Executable market data is incomplete; order book verification is required before trading.')
    return finalize(marketRecommendationPacketSchema.parse({
      market_id: input.snapshot.market.market_id,
      venue: input.snapshot.venue,
      action: 'wait',
      side: null,
      confidence: input.forecast.confidence,
      fair_value_yes: input.forecast.probability_yes,
      market_price_yes: marketPrice,
      market_bid_yes: marketBid,
      market_ask_yes: marketAsk,
      edge_bps: 0,
      spread_bps: spreadBps,
      reasons,
      risk_flags: ['incomplete_market_data'],
      produced_at: nowIso(),
    }))
  }

  if ((input.snapshot.book.depth_near_touch ?? 0) < DEFAULT_MIN_DEPTH_NEAR_TOUCH) {
    riskFlags.push('thin_orderbook')
    reasons.push(
      `Near-touch depth ${(input.snapshot.book.depth_near_touch ?? 0)} is below minimum ${DEFAULT_MIN_DEPTH_NEAR_TOUCH}.`,
    )
  }

  if (input.forecast.basis === 'manual_thesis' && getSnapshotHistoryPoints(input.snapshot).length === 0) {
    riskFlags.push('missing_history')
    reasons.push('Manual thesis runs require a frozen price history to support replay and audit.')
  }

  if (spreadBps != null && spreadBps > maxSpreadBps) {
    riskFlags.push('wide_spread')
    reasons.push(`Spread ${spreadBps} bps exceeds max ${maxSpreadBps} bps.`)
  }

  if (input.forecast.abstention_reason) {
    riskFlags.push('forecast_abstention')
    reasons.push(`Forecast abstention policy is holding this packet at ${input.forecast.abstention_reason}.`)
  }

  if (input.forecast.requires_manual_review) {
    riskFlags.push('forecast_manual_review')
    reasons.push('Forecast still requires manual review before it can claim an executable edge.')
  }

  if (input.forecast.abstention_reason || input.forecast.requires_manual_review) {
    return finalize(marketRecommendationPacketSchema.parse({
      market_id: input.snapshot.market.market_id,
      venue: input.snapshot.venue,
      action: 'wait',
      side: null,
      confidence: input.forecast.confidence,
      fair_value_yes: input.forecast.probability_yes,
      market_price_yes: marketPrice,
      market_bid_yes: marketBid,
      market_ask_yes: marketAsk,
      edge_bps: 0,
      spread_bps: spreadBps,
      reasons,
      risk_flags: uniqueStrings(riskFlags),
      produced_at: nowIso(),
    }))
  }

  if (usesMarketOnlyFairValue) {
    reasons.push('Baseline forecast is market-derived, so no exogenous edge is claimed yet.')
    return finalize(marketRecommendationPacketSchema.parse({
      market_id: input.snapshot.market.market_id,
      venue: input.snapshot.venue,
      action: spreadBps != null && spreadBps > maxSpreadBps ? 'wait' : 'no_trade',
      side: null,
      confidence: input.forecast.confidence,
      fair_value_yes: input.forecast.probability_yes,
      market_price_yes: marketPrice,
      market_bid_yes: marketBid,
      market_ask_yes: marketAsk,
      edge_bps: 0,
      spread_bps: spreadBps,
      reasons,
      risk_flags: riskFlags,
      produced_at: nowIso(),
    }))
  }

  const edgeYesBps = marketAsk == null ? 0 : Number(((input.forecast.probability_yes - marketAsk) * 10_000).toFixed(2))
  const marketNoAsk = marketBid == null ? null : Number((1 - marketBid).toFixed(6))
  const fairValueNo = Number((1 - input.forecast.probability_yes).toFixed(6))
  const edgeNoBps = marketNoAsk == null ? 0 : Number(((fairValueNo - marketNoAsk) * 10_000).toFixed(2))

  if (riskFlags.length === 0 && edgeYesBps >= minEdgeBps) {
    reasons.push(
      usesResearchDrivenFairValue
        ? `Research-driven forecast shows +${edgeYesBps} bps edge on Yes after executable ask comparison.`
        : `Manual thesis shows +${edgeYesBps} bps edge on Yes after executable ask comparison.`,
    )
    return finalize(marketRecommendationPacketSchema.parse({
      market_id: input.snapshot.market.market_id,
      venue: input.snapshot.venue,
      action: 'bet',
      side: 'yes',
      confidence: input.forecast.confidence,
      fair_value_yes: input.forecast.probability_yes,
      market_price_yes: marketPrice,
      market_bid_yes: marketBid,
      market_ask_yes: marketAsk,
      edge_bps: edgeYesBps,
      spread_bps: spreadBps,
      reasons,
      risk_flags: [],
      produced_at: nowIso(),
    }))
  }

  if (riskFlags.length === 0 && edgeNoBps >= minEdgeBps) {
    reasons.push(
      usesResearchDrivenFairValue
        ? `Research-driven forecast shows +${edgeNoBps} bps edge on No versus implied executable price.`
        : `Manual thesis shows +${edgeNoBps} bps edge on No versus implied executable price.`,
    )
    return finalize(marketRecommendationPacketSchema.parse({
      market_id: input.snapshot.market.market_id,
      venue: input.snapshot.venue,
      action: 'bet',
      side: 'no',
      confidence: input.forecast.confidence,
      fair_value_yes: input.forecast.probability_yes,
      market_price_yes: marketPrice,
      market_bid_yes: marketBid,
      market_ask_yes: marketAsk,
      edge_bps: edgeNoBps,
      spread_bps: spreadBps,
      reasons,
      risk_flags: [],
      produced_at: nowIso(),
    }))
  }

  reasons.push(`No executable edge beyond ${minEdgeBps} bps was found.`)
  return finalize(marketRecommendationPacketSchema.parse({
    market_id: input.snapshot.market.market_id,
    venue: input.snapshot.venue,
    action: riskFlags.length > 0 ? 'wait' : 'no_trade',
    side: null,
    confidence: input.forecast.confidence,
    fair_value_yes: input.forecast.probability_yes,
    market_price_yes: marketPrice,
    market_bid_yes: marketBid,
    market_ask_yes: marketAsk,
    edge_bps: Math.max(edgeYesBps, edgeNoBps),
    spread_bps: spreadBps,
    reasons,
    risk_flags: riskFlags,
    produced_at: nowIso(),
  }))
}

function buildInitialRun(input: {
  actor: string
  marketId?: string
  slug?: string
  configHash: string
  venue: PredictionMarketVenue
  mode: 'advise' | 'replay'
  toolsAvailable: string[]
}): AgentRun {
  const startedAt = nowIso()
  return {
    id: randomUUID(),
    agent_id: 'prediction_markets',
    agent_name: 'Prediction Markets',
    runtime: 'prediction_markets',
    model: PREDICTION_MARKETS_BASELINE_MODEL,
    status: 'running',
    outcome: null,
    trigger: 'manual',
    started_at: startedAt,
    steps: [
      {
        id: randomUUID(),
        type: 'message',
        input_preview: `${input.mode} ${input.marketId || input.slug || 'market'}`,
        started_at: startedAt,
        ended_at: startedAt,
      },
    ],
    tools_available: input.toolsAvailable,
    cost: { input_tokens: 0, output_tokens: 0, total_tokens: 0, cost_usd: 0, model: PREDICTION_MARKETS_BASELINE_MODEL },
    provenance: {
      run_hash: '',
      config_hash: input.configHash,
      runtime: 'prediction_markets',
      model_version: PREDICTION_MARKETS_BASELINE_MODEL,
      created_at: startedAt,
      signed_by: input.actor,
    },
    tags: ['prediction_markets', `mode:${input.mode}`, `venue:${input.venue}`],
    metadata: {
      market_id: input.marketId,
      slug: input.slug,
      venue: input.venue,
    },
  }
}

function buildCompletedSteps(input: {
  startedAt: string
  snapshot: MarketSnapshot
  recommendation: MarketRecommendationPacket & { rationale?: string }
  snapshotToolName: string
}): AgentRun['steps'] {
  const finishedAt = nowIso()
  const recommendationSummary = input.recommendation.rationale
    ? `${input.recommendation.action}${input.recommendation.side ? `:${input.recommendation.side}` : ''} — ${input.recommendation.rationale}`
    : `${input.recommendation.action}${input.recommendation.side ? `:${input.recommendation.side}` : ''}`

  return [
    {
      id: randomUUID(),
      type: 'tool_call',
      tool_name: input.snapshotToolName,
      input_preview: input.snapshot.market.market_id,
      output_preview: `spread=${input.snapshot.spread_bps ?? 'n/a'}bps`,
      success: true,
      started_at: input.startedAt,
      ended_at: finishedAt,
    },
    {
      id: randomUUID(),
      type: 'message',
      input_preview: 'baseline forecast',
      output_preview: recommendationSummary.slice(0, 220),
      success: true,
      started_at: input.startedAt,
      ended_at: finishedAt,
    },
  ]
}

function getIdempotencyWindowSec(): number {
  const parsed = Number(process.env.PREDICTION_MARKETS_IDEMPOTENCY_WINDOW_SEC)
  return Number.isFinite(parsed) && parsed >= 0
    ? parsed
    : DEFAULT_IDEMPOTENCY_WINDOW_SEC
}

function summarizePredictionMarketArtifactReadback(
  readback: PredictionMarketArtifactReadbackIndex,
): PredictionMarketArtifactAuditSummary {
  const runManifestArtifactId = readback.run_manifest_ref?.artifact_id

  return {
    manifest_ref_count: readback.manifest_artifact_refs.length,
    observed_ref_count: readback.observed_artifact_refs.length,
    canonical_ref_count: readback.canonical_artifact_refs.length,
    run_manifest_present: readback.run_manifest_ref != null,
    duplicate_artifact_ids: uniqueStrings([
      ...readback.manifest_index.duplicate_artifact_ids,
      ...readback.observed_index.duplicate_artifact_ids,
    ]),
    manifest_only_artifact_ids: readback.manifest_only_artifact_ids,
    observed_only_artifact_ids: readback.observed_only_artifact_ids.filter((artifactId) => artifactId !== runManifestArtifactId),
  }
}

function toArtifactRefsFromArtifacts(details: StoredPredictionMarketRunDetails) {
  return details.artifacts.flatMap((artifact) => {
    if (typeof artifact.artifact_id !== 'string' || typeof artifact.sha256 !== 'string') {
      return []
    }

    return [{
      artifact_id: artifact.artifact_id,
      artifact_type: artifact.artifact_type,
      sha256: artifact.sha256,
    }]
  })
}

function resolvePredictionMarketRunManifest(
  details: StoredPredictionMarketRunDetails,
): RunManifest | undefined {
  const maybeDetails = details as StoredPredictionMarketRunDetails & {
    summary?: { manifest?: RunManifest }
  }
  const manifestArtifact = details.artifacts.find((artifact) => artifact.artifact_type === 'run_manifest')
  const manifestFromArtifact = manifestArtifact
    ? (() => {
      const parsed = runManifestSchema.safeParse(manifestArtifact.payload)
      return parsed.success ? parsed.data : undefined
    })()
    : undefined

  return maybeDetails.manifest ?? maybeDetails.summary?.manifest ?? manifestFromArtifact
}

function resolvePredictionMarketRunArtifactRefs(
  details: StoredPredictionMarketRunDetails,
): PredictionMarketArtifactRef[] {
  const maybeDetails = details as StoredPredictionMarketRunDetails & {
    summary?: { artifact_refs?: PredictionMarketArtifactRef[] }
  }
  const manifestArtifact = details.artifacts.find((artifact) => artifact.artifact_type === 'run_manifest')
  const manifestArtifactRefs = manifestArtifact
    ? (() => {
      const parsed = runManifestSchema.safeParse(manifestArtifact.payload)
      return parsed.success ? parsed.data.artifact_refs : undefined
    })()
    : undefined

  return maybeDetails.artifact_refs
    ?? maybeDetails.summary?.artifact_refs
    ?? manifestArtifactRefs
    ?? toArtifactRefsFromArtifacts(details)
}

function enrichPredictionMarketRunSummaryWithArtifactAudit(
  summary: StoredPredictionMarketRunSummary,
): PredictionMarketRunSummaryWithArtifactAudit {
  const artifactReadback = buildPredictionMarketArtifactReadback({
    manifest: summary.manifest,
    artifact_refs: summary.artifact_refs,
  })
  const hasRuntimeHints = summary.artifact_refs.some((artifactRef) =>
    artifactRef.artifact_type === 'research_sidecar' ||
    artifactRef.artifact_type === 'timesfm_sidecar' ||
    artifactRef.artifact_type === 'source_audit' ||
    artifactRef.artifact_type === 'world_state' ||
    artifactRef.artifact_type === 'ticket_payload' ||
    artifactRef.artifact_type === 'quant_signal_bundle' ||
    artifactRef.artifact_type === 'decision_ledger' ||
    artifactRef.artifact_type === 'calibration_report' ||
    artifactRef.artifact_type === 'resolved_history' ||
    artifactRef.artifact_type === 'cost_model_report' ||
    artifactRef.artifact_type === 'walk_forward_report' ||
    artifactRef.artifact_type === 'autopilot_cycle_summary' ||
    artifactRef.artifact_type === 'research_memory_summary' ||
    artifactRef.artifact_type === 'strategy_candidate_packet' ||
    artifactRef.artifact_type === 'strategy_decision_packet' ||
    artifactRef.artifact_type === 'strategy_shadow_summary' ||
    artifactRef.artifact_type === 'execution_intent_preview' ||
    artifactRef.artifact_type === 'resolution_anomaly_report' ||
    artifactRef.artifact_type === 'execution_pathways' ||
    artifactRef.artifact_type === 'execution_projection' ||
    artifactRef.artifact_type === 'shadow_arbitrage' ||
    artifactRef.artifact_type === 'multi_venue_execution',
  )

  let runtimeHints: PredictionMarketRunRuntimeHints = {}
  let benchmarkGateOverride: Partial<PredictionMarketRunRuntimeHints> = buildPredictionMarketBenchmarkGateOverride(
    summary as Partial<PredictionMarketRunSummaryWithArtifactAudit>,
  )

  if (hasRuntimeHints) {
    const details = getStoredPredictionMarketRunDetails(summary.run_id, summary.workspace_id)
    if (details) {
      const enrichedDetails = enrichStoredPredictionMarketRunDetails(
        details as StoredPredictionMarketRunDetails & Partial<PredictionMarketRunRuntimeHints>,
      )
      const findArtifact = (artifactType: string) =>
        enrichedDetails.artifacts.find((artifact) => artifact.artifact_type === artifactType)?.payload

      const topLevelExecutionProjection = (
        enrichedDetails as Partial<PredictionMarketRunRuntimeHints> & {
          execution_projection?: PredictionMarketExecutionProjectionReport | null
        }
      ).execution_projection ?? null
      const executionPathways = (findArtifact('execution_pathways') ?? null) as PredictionMarketExecutionPathwaysReport | null
      const executionProjection = normalizeExecutionProjectionReport(
        topLevelExecutionProjection
        ?? ((findArtifact('execution_projection') ?? null) as PredictionMarketExecutionProjectionReport | null),
      )
      const shadowArbitrage = (
        (findArtifact('shadow_arbitrage') ?? null) as ShadowArbitrageSimulationReport | null
      )
      const multiVenueExecution = (findArtifact('multi_venue_execution') ?? null) as MultiVenueExecution | null
      const researchSidecar = (findArtifact('research_sidecar') ?? null) as MarketResearchSidecar | null
      const timesfmSidecar = (findArtifact('timesfm_sidecar') ?? null) as PredictionMarketTimesFMSidecar | null
      const sourceAudit = (findArtifact('source_audit') ?? null) as PredictionMarketJsonArtifact | null
      const worldState = (findArtifact('world_state') ?? null) as PredictionMarketJsonArtifact | null
      const ticketPayload = (findArtifact('ticket_payload') ?? null) as PredictionMarketJsonArtifact | null
      const quantSignalBundle = (findArtifact('quant_signal_bundle') ?? null) as PredictionMarketJsonArtifact | null
      const decisionLedger = (findArtifact('decision_ledger') ?? null) as PredictionMarketJsonArtifact | null
      const calibrationReport = (findArtifact('calibration_report') ?? null) as PredictionMarketJsonArtifact | null
      const resolvedHistory = (findArtifact('resolved_history') ?? null) as PredictionMarketJsonArtifact | null
      const costModelReport = (findArtifact('cost_model_report') ?? null) as PredictionMarketJsonArtifact | null
      const walkForwardReport = (findArtifact('walk_forward_report') ?? null) as PredictionMarketJsonArtifact | null
      const autopilotCycleSummary = (findArtifact('autopilot_cycle_summary') ?? null) as PredictionMarketJsonArtifact | null
      const researchMemorySummary = (findArtifact('research_memory_summary') ?? null) as PredictionMarketJsonArtifact | null
      const strategyCandidate = (findArtifact('strategy_candidate_packet') ?? null) as StrategyCandidatePacket | null
      const strategyDecision = (findArtifact('strategy_decision_packet') ?? null) as StrategyDecisionPacket | null
      const strategyShadowSummary = (findArtifact('strategy_shadow_summary') ?? null) as StrategyShadowSummary | null
      const executionIntentPreview = (findArtifact('execution_intent_preview') ?? null) as ExecutionIntentPreview | null
      const resolutionAnomalyReport = (findArtifact('resolution_anomaly_report') ?? null) as ResolutionAnomalyReport | null
      const forecast = (findArtifact('forecast_packet') ?? null) as ForecastPacket | null
      const recommendation = (findArtifact('recommendation_packet') ?? null) as MarketRecommendationPacket | null
      const rawTradeIntentGuard = (
        (
          enrichedDetails as Partial<PredictionMarketRunRuntimeHints> & {
            trade_intent_guard?: TradeIntentGuard | null
          }
        ).trade_intent_guard
        ?? ((findArtifact('trade_intent_guard') ?? null) as TradeIntentGuard | null)
      )
      const benchmarkAwareDetailsInput = {
        ...enrichedDetails,
        execution_projection: executionProjection,
        trade_intent_guard: rawTradeIntentGuard,
      } as Partial<PredictionMarketRunRuntimeHints> & {
        execution_projection?: PredictionMarketExecutionProjectionReport | null
        trade_intent_guard?: TradeIntentGuard | null
      }
      const benchmarkAwareTradeIntentGuard = rehydratePredictionMarketTradeIntentGuardForBenchmarkPromotion(
        rawTradeIntentGuard,
        benchmarkAwareDetailsInput,
      )
      const benchmarkLiveGate = resolvePredictionMarketBenchmarkLiveGateState({
        ...benchmarkAwareDetailsInput,
        trade_intent_guard: benchmarkAwareTradeIntentGuard,
      })
      const benchmarkAwareDetails = {
        ...benchmarkAwareDetailsInput,
        trade_intent_guard: benchmarkAwareTradeIntentGuard,
        research_benchmark_gate_blocks_live: benchmarkLiveGate.blocks_live,
        research_benchmark_live_block_reason: benchmarkLiveGate.live_block_reason,
        benchmark_gate_blocks_live: benchmarkLiveGate.blocks_live,
        benchmark_gate_live_block_reason: benchmarkLiveGate.live_block_reason,
      }
      const venueFeedSurface = (
        benchmarkAwareDetails as Partial<PredictionMarketRunRuntimeHints> & {
          venue_feed_surface?: MarketFeedSurface | null
        }
      ).venue_feed_surface ?? null
      benchmarkGateOverride = resolvePredictionMarketSummaryBenchmarkGateOverride(
        summary as Partial<PredictionMarketRunRuntimeHints>,
        benchmarkAwareDetails as Partial<PredictionMarketRunRuntimeHints>,
        enrichedDetails as Partial<PredictionMarketRunRuntimeHints>,
      )

      runtimeHints = buildPredictionMarketRunRuntimeHints({
        researchSidecar,
        timesfmSidecar,
        forecast,
        recommendation,
        venueFeedSurface,
        executionPathways,
        executionProjection,
        shadowArbitrage,
        multiVenueExecution,
        strategyCandidate,
        strategyDecision,
        executionIntentPreview,
        resolutionAnomalyReport,
        strategyShadowSummary,
        sourceAudit,
        worldState,
        ticketPayload,
        quantSignalBundle,
        decisionLedger,
        calibrationReport,
        resolvedHistory,
        costModelReport,
        walkForwardReport,
        autopilotCycleSummary,
        researchMemorySummary,
        benchmarkGateOverride,
      })
    }
  }

  return {
    ...summary,
    ...runtimeHints,
    ...benchmarkGateOverride,
    artifact_audit: summarizePredictionMarketArtifactReadback(artifactReadback),
  }
}

function emptyCrossVenueIntelligence(): PredictionMarketCrossVenueIntelligence {
  return {
    evaluations: [],
    arbitrage_candidates: [],
    errors: [],
    summary: summarizeCrossVenueIntelligence([]),
  }
}

function normalizeCrossVenueIntelligence(
  intelligence: PredictionMarketCrossVenueIntelligence | null | undefined,
): PredictionMarketCrossVenueIntelligence {
  const base = intelligence ?? emptyCrossVenueIntelligence()
  return {
    ...base,
    summary: base.summary ?? summarizeCrossVenueIntelligence(base.evaluations),
  }
}

function normalizeGraphText(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function graphQuestionTokens(question: string): string[] {
  const stopwords = new Set([
    'a', 'an', 'and', 'are', 'at', 'be', 'by', 'for', 'from', 'if', 'in', 'is', 'it', 'of', 'on', 'or', 'the', 'to', 'vs', 'what', 'when', 'will', 'with',
  ])
  return normalizeGraphText(question)
    .split(' ')
    .map((token) => token.trim())
    .filter((token) => token.length > 1 && !stopwords.has(token))
}

function graphQuestionSpecificityScore(question: string, marketId: string): number {
  const tokens = graphQuestionTokens(question)
  const temporalMarkers = new Set([
    'q1', 'q2', 'q3', 'q4', 'week', 'month', 'quarter', 'year', 'annual', 'annually',
    '2024', '2025', '2026', '2027', '2028', '2029', '2030',
  ])
  const temporalScore = normalizeGraphText(question)
    .split(' ')
    .filter((token) => token.length > 0 && (temporalMarkers.has(token) || /\d/.test(token)))
    .length
  return Number((tokens.length + temporalScore * 0.2 + (marketId ? 0.1 : 0)).toFixed(6))
}

function graphHedgeProfile(question: string): { kind: 'neutral' | 'upside' | 'downside' | 'negated' | 'mixed'; tokens: string[] } {
  const tokens = normalizeGraphText(question).split(' ').filter(Boolean)
  const negationMarkers = new Set(['not', 'no', 'never', 'without', 'fail', 'fails', 'failed', 'failing', 'miss', 'misses', 'missed'])
  const downsideMarkers = new Set(['drop', 'drops', 'dropped', 'decline', 'declines', 'declined', 'fall', 'falls', 'fell', 'down', 'decrease', 'decreases', 'decreased', 'lower', 'lowers', 'lowered', 'under', 'below', 'lose', 'loses', 'lost', 'reject', 'rejects', 'reduce', 'reduces', 'reduced', 'less'])
  const positiveMarkers = new Set(['above', 'over', 'greater', 'more', 'increase', 'increases', 'increased', 'rise', 'rises', 'risen', 'up', 'higher', 'gain', 'gains', 'gained', 'win', 'wins', 'won', 'approve', 'approves', 'approved', 'pass', 'passes', 'passed', 'launch', 'launches', 'launched', 'adopt', 'adopts', 'adopted', 'exceed', 'exceeds', 'exceeded'])
  const hasNegation = tokens.some((token) => negationMarkers.has(token))
  const hasDownside = tokens.some((token) => downsideMarkers.has(token))
  const hasPositive = tokens.some((token) => positiveMarkers.has(token))
  let kind: 'neutral' | 'upside' | 'downside' | 'negated' | 'mixed' = 'neutral'
  if (hasNegation && (hasPositive || hasDownside)) {
    kind = 'mixed'
  } else if (hasNegation) {
    kind = 'negated'
  } else if (hasPositive && hasDownside) {
    kind = 'mixed'
  } else if (hasPositive) {
    kind = 'upside'
  } else if (hasDownside) {
    kind = 'downside'
  }
  return { kind, tokens }
}

function countStrings(values: string[]): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const value of values) {
    counts[value] = (counts[value] ?? 0) + 1
  }
  return counts
}

function uniqueByKey<T>(values: T[], keyFn: (value: T) => string): T[] {
  const seen = new Set<string>()
  const output: T[] = []
  for (const value of values) {
    const key = keyFn(value)
    if (seen.has(key)) continue
    seen.add(key)
    output.push(value)
  }
  return output
}

function derivePredictionMarketMarketGraph(input: {
  snapshot: MarketSnapshot
  crossVenueIntelligence?: PredictionMarketCrossVenueIntelligence | null
}): PredictionMarketMarketGraph | null {
  const intelligence = normalizeCrossVenueIntelligence(input.crossVenueIntelligence)
  const evaluations = intelligence.evaluations
  if (evaluations.length === 0) return null

  type GraphNodeSeed = {
    venue: PredictionMarketVenue
    market_id: string
    venue_type: 'execution-equivalent' | 'execution-like' | 'reference-only' | 'experimental'
    question: string
    title: string
    canonical_event_id: string | null
    status: string
    role: string
    clarity_score: number
    liquidity: number | null
    price_yes: number | null
    snapshot_id: string | null
    metadata: Record<string, unknown>
  }

  const nodeSeeds = new Map<string, GraphNodeSeed>()
  const nodeOrder: string[] = []
  const getMatchLeftQuestion = (evaluation: typeof evaluations[number]) =>
    evaluation.match.left_market_ref.question?.trim()
    || evaluation.match.left_market_ref.slug?.trim()
    || evaluation.match.left_market_ref.market_id
  const getMatchRightQuestion = (evaluation: typeof evaluations[number]) =>
    evaluation.match.right_market_ref.question?.trim()
    || evaluation.match.right_market_ref.slug?.trim()
    || evaluation.match.right_market_ref.market_id
  const getMatchQuestionKey = (evaluation: typeof evaluations[number]) =>
    normalizeGraphText(
      getMatchLeftQuestion(evaluation) === getMatchRightQuestion(evaluation)
        ? getMatchLeftQuestion(evaluation)
        : `${getMatchLeftQuestion(evaluation)} ${getMatchRightQuestion(evaluation)}`,
    ) || evaluation.canonical_event_key || evaluation.canonical_event_id
  const hasCompatibleResolution = (evaluation: typeof evaluations[number]) =>
    evaluation.market_equivalence_proof.resolution_compatibility_score >= 1
  const recordNode = (
    ref: { venue?: PredictionMarketVenue; market_id?: string; venue_type?: 'execution-equivalent' | 'execution-like' | 'reference-only' | 'experimental'; question?: string; slug?: string },
    options: {
      canonical_event_id?: string | null
      role?: string
      clarity_score?: number
      liquidity?: number | null
      price_yes?: number | null
      snapshot_id?: string | null
      status?: string
      metadata?: Record<string, unknown>
    } = {},
  ) => {
    if (!ref.venue || !ref.market_id) {
      return
    }
    const key = `${ref.venue}:${ref.market_id}`
    const existing = nodeSeeds.get(key)
    const question = (ref.question ?? ref.slug ?? ref.market_id).trim()
    const title = question
    const venueType = ref.venue_type ?? 'execution-equivalent'
    const seed: GraphNodeSeed = existing ?? {
      venue: ref.venue,
      market_id: ref.market_id,
      venue_type: venueType,
      question,
      title,
      canonical_event_id: options.canonical_event_id ?? null,
      status: options.status ?? 'unknown',
      role: options.role ?? 'comparison',
      clarity_score: options.clarity_score ?? Math.min(1, 0.45 + graphQuestionTokens(question).length * 0.05),
      liquidity: options.liquidity ?? null,
      price_yes: options.price_yes ?? null,
      snapshot_id: options.snapshot_id ?? null,
      metadata: {
        categories: [],
        tags: [],
        source_url: null,
        resolution_source: null,
        role_hint: options.role ?? 'comparison',
      },
    }
    if (!existing) {
      nodeSeeds.set(key, seed)
      nodeOrder.push(key)
    }
    if (options.canonical_event_id != null) {
      seed.canonical_event_id = options.canonical_event_id
    }
    if (options.role != null) {
      seed.role = options.role
      seed.metadata.role_hint = options.role
    }
    if (options.clarity_score != null) {
      seed.clarity_score = options.clarity_score
    }
    if (options.liquidity != null) {
      seed.liquidity = options.liquidity
    }
    if (options.price_yes != null) {
      seed.price_yes = options.price_yes
    }
    if (options.snapshot_id != null) {
      seed.snapshot_id = options.snapshot_id
    }
    if (options.status != null) {
      seed.status = options.status
    }
    if (options.metadata != null) {
      seed.metadata = {
        ...seed.metadata,
        ...options.metadata,
      }
    }
  }

  const snapshotMarket = input.snapshot.market
  recordNode(
    {
      venue: input.snapshot.venue,
      market_id: snapshotMarket.market_id,
      venue_type: snapshotMarket.venue_type,
      question: snapshotMarket.question,
      slug: snapshotMarket.slug,
    },
    {
      canonical_event_id: null,
      role: 'reference',
      clarity_score: Math.min(1, 0.65 + graphQuestionTokens(snapshotMarket.question).length * 0.04),
      liquidity: snapshotMarket.liquidity_usd ?? null,
      price_yes: input.snapshot.yes_price ?? input.snapshot.midpoint_yes ?? null,
      snapshot_id: input.snapshot.captured_at,
      status: snapshotMarket.closed ? 'closed' : snapshotMarket.active ? 'active' : 'unknown',
      metadata: {
        categories: [],
        tags: [],
        source_url: input.snapshot.source_urls[0] ?? null,
        resolution_source: null,
        role_hint: 'reference',
      },
    },
  )

  for (const evaluation of evaluations) {
    const canonicalEventId = evaluation.canonical_event_id
    const pairQuestion = getMatchLeftQuestion(evaluation) || getMatchRightQuestion(evaluation)
    const leftRef = evaluation.match.left_market_ref
    const rightRef = evaluation.match.right_market_ref
    recordNode(leftRef, {
      canonical_event_id: canonicalEventId,
      role: leftRef.venue === input.snapshot.venue && leftRef.market_id === input.snapshot.market.market_id
        ? 'reference'
        : leftRef.venue_type === 'reference-only'
          ? 'reference'
          : 'comparison',
      clarity_score: Math.max(0.2, Math.min(1, 0.4 + graphQuestionTokens(leftRef.question ?? pairQuestion).length * 0.05)),
      status: leftRef.venue === input.snapshot.venue && leftRef.market_id === input.snapshot.market.market_id ? (snapshotMarket.closed ? 'closed' : snapshotMarket.active ? 'active' : 'unknown') : 'unknown',
      metadata: {
        categories: [],
        tags: [],
        source_url: null,
        resolution_source: null,
        role_hint: leftRef.venue_type ?? 'comparison',
      },
    })
    recordNode(rightRef, {
      canonical_event_id: canonicalEventId,
      role: rightRef.venue === input.snapshot.venue && rightRef.market_id === input.snapshot.market.market_id
        ? 'reference'
        : rightRef.venue_type === 'reference-only'
          ? 'reference'
          : 'comparison',
      clarity_score: Math.max(0.2, Math.min(1, 0.4 + graphQuestionTokens(rightRef.question ?? pairQuestion).length * 0.05)),
      status: rightRef.venue === input.snapshot.venue && rightRef.market_id === input.snapshot.market.market_id ? (snapshotMarket.closed ? 'closed' : snapshotMarket.active ? 'active' : 'unknown') : 'unknown',
      metadata: {
        categories: [],
        tags: [],
        source_url: null,
        resolution_source: null,
        role_hint: rightRef.venue_type ?? 'comparison',
      },
    })
  }

  const nodes = nodeOrder.map((key) => {
    const seed = nodeSeeds.get(key)
    if (!seed) return null
    const nodeId = `${seed.venue}:${seed.market_id}`
    return predictionMarketMarketGraphNodeSchema.parse({
      schema_version: 'v1',
      node_id: nodeId,
      market_id: seed.market_id,
      venue: seed.venue,
      venue_type: seed.venue_type,
      title: seed.title,
      question: seed.question,
      canonical_event_id: seed.canonical_event_id,
      status: seed.status,
      role: seed.role,
      clarity_score: seed.clarity_score,
      liquidity: seed.liquidity,
      price_yes: seed.price_yes,
      snapshot_id: seed.snapshot_id,
      metadata: seed.metadata,
    })
  }).filter((node): node is PredictionMarketMarketGraph['nodes'][number] => node != null)

  const nodeByMarketId = new Map(nodes.map((node) => [node.market_id, node]))
  const edges = evaluations.map((evaluation) => {
    const left = nodeByMarketId.get(evaluation.match.left_market_ref.market_id)
    const right = nodeByMarketId.get(evaluation.match.right_market_ref.market_id)
    if (!left || !right) return null
    const relation = normalizeGraphText(getMatchLeftQuestion(evaluation)) === normalizeGraphText(getMatchRightQuestion(evaluation))
      ? 'same_question'
      : evaluation.match.canonical_event_id === evaluation.canonical_event_id
        ? 'same_event'
        : 'same_topic'
    return predictionMarketMarketGraphEdgeSchema.parse({
      schema_version: 'v1',
      edge_id: `edge_${evaluation.canonical_event_id}_${left.market_id}_${right.market_id}`,
      source_node_id: left.node_id,
      target_node_id: right.node_id,
      relation,
      similarity: evaluation.match.semantic_similarity_score,
      compatible_resolution: hasCompatibleResolution(evaluation),
      rationale: evaluation.match.notes.join('; '),
      metadata: {
        canonical_event_id: evaluation.canonical_event_id,
        opportunity_type: evaluation.opportunity_type,
        confidence_score: evaluation.confidence_score,
        manual_review_required: evaluation.match.manual_review_required,
        executable_edge_present: evaluation.executable_edge != null,
        arbitrage_candidate_present: evaluation.arbitrage_candidate != null,
      },
    })
  }).filter((edge): edge is PredictionMarketMarketGraph['edges'][number] => edge != null)

  const matches = uniqueByKey(evaluations.map((evaluation) => evaluation.match), (match) => [
    match.canonical_event_id,
    match.left_market_ref.venue,
    match.left_market_ref.market_id,
    match.right_market_ref.venue,
    match.right_market_ref.market_id,
  ].join('|'))

  const rejectedMatches = evaluations
    .filter((evaluation) => !evaluation.compatible || evaluation.match.manual_review_required)
    .map((evaluation, index) => ({
      schema_version: 'v1',
      rejection_id: `rejection_${evaluation.canonical_event_id}_${index}`,
      left_market_id: evaluation.match.left_market_ref.market_id,
      right_market_id: evaluation.match.right_market_ref.market_id,
      left_venue: evaluation.match.left_market_ref.venue,
      right_venue: evaluation.match.right_market_ref.venue,
      canonical_event_id: evaluation.canonical_event_id,
      question_left: getMatchLeftQuestion(evaluation),
      question_right: getMatchRightQuestion(evaluation),
      question_key: getMatchQuestionKey(evaluation),
      similarity: evaluation.match.semantic_similarity_score,
      reason_codes: [...new Set(evaluation.mismatch_reasons)],
      rationale: evaluation.match.notes.join('; '),
      metadata: {
        opportunity_type: evaluation.opportunity_type,
        manual_review_required: evaluation.match.manual_review_required,
      },
    }))
    .map((rejection) => predictionMarketCrossVenueMatchRejectionSchema.parse(rejection))

  const comparableGroupMap = new Map<string, {
    canonical_event_id: string
    question_key: string
    question: string
    market_ids: Set<string>
    venues: Set<string>
    venue_types: Set<string>
    relation_kind: 'same_event' | 'same_question' | 'same_topic' | 'reference' | 'comparison'
    reference_market_ids: Set<string>
    comparison_market_ids: Set<string>
    parent_market_ids: Set<string>
    child_market_ids: Set<string>
    parent_child_pairs: Array<Record<string, unknown>>
    natural_hedge_market_ids: Set<string>
    natural_hedge_pairs: Array<Record<string, unknown>>
    notes: Set<string>
    manual_review_required: boolean
    compatible_resolution: boolean
    compatible_currency: boolean
    compatible_payout: boolean
    match_count: number
    duplicate_market_count: number
    desalignment_dimensions: Set<string>
    narrative_risk_flags: Set<string>
    metadata: Record<string, unknown>
  }>()

  const byCanonicalEvent = new Map<string, Array<{ evaluation: typeof evaluations[number]; left: PredictionMarketMarketGraph['nodes'][number]; right: PredictionMarketMarketGraph['nodes'][number] }>>()
  for (const evaluation of evaluations) {
    const left = nodeByMarketId.get(evaluation.match.left_market_ref.market_id)
    const right = nodeByMarketId.get(evaluation.match.right_market_ref.market_id)
    if (!left || !right) continue
    const list = byCanonicalEvent.get(evaluation.canonical_event_id) ?? []
    list.push({ evaluation, left, right })
    byCanonicalEvent.set(evaluation.canonical_event_id, list)
  }

  for (const [canonicalEventId, items] of byCanonicalEvent.entries()) {
    const nodesForGroup = uniqueByKey(items.flatMap((item) => [item.left, item.right]), (node) => node.market_id)
    if (nodesForGroup.length < 2) continue
    const questions = nodesForGroup.map((node) => normalizeGraphText(node.question))
    const allSameQuestion = questions.every((question) => question === questions[0])
    const relationKind = allSameQuestion ? 'same_question' : 'same_topic'
    const questionKey = normalizeGraphText(
      items[0] ? getMatchQuestionKey(items[0].evaluation) : canonicalEventId,
    ) || normalizeGraphText(items[0]?.left.question ?? items[0]?.right.question ?? canonicalEventId)
    const group = comparableGroupMap.get(canonicalEventId) ?? {
      canonical_event_id: canonicalEventId,
      question_key: questionKey,
      question: items[0] ? (getMatchLeftQuestion(items[0].evaluation) || getMatchRightQuestion(items[0].evaluation)) : nodesForGroup[0].question,
      market_ids: new Set<string>(),
      venues: new Set<string>(),
      venue_types: new Set<string>(),
      relation_kind: relationKind,
      reference_market_ids: new Set<string>(),
      comparison_market_ids: new Set<string>(),
      parent_market_ids: new Set<string>(),
      child_market_ids: new Set<string>(),
      parent_child_pairs: [] as Array<Record<string, unknown>>,
      natural_hedge_market_ids: new Set<string>(),
      natural_hedge_pairs: [] as Array<Record<string, unknown>>,
      notes: new Set<string>(),
      manual_review_required: false,
      compatible_resolution: true,
      compatible_currency: true,
      compatible_payout: true,
      match_count: 0,
      duplicate_market_count: 0,
      desalignment_dimensions: new Set<string>(),
      narrative_risk_flags: new Set<string>(),
      metadata: {},
    }
    for (const node of nodesForGroup) {
      group.market_ids.add(node.market_id)
      group.venues.add(node.venue)
      group.venue_types.add(node.venue_type)
      if (node.role === 'reference') {
        group.reference_market_ids.add(node.market_id)
      } else {
        group.comparison_market_ids.add(node.market_id)
      }
    }

    const questionTokenMap = new Map(nodesForGroup.map((node) => [node.market_id, graphQuestionTokens(node.question)]))
    for (const left of nodesForGroup) {
      for (const right of nodesForGroup) {
        if (left.market_id >= right.market_id) continue
        const leftTokens = questionTokenMap.get(left.market_id) ?? []
        const rightTokens = questionTokenMap.get(right.market_id) ?? []
        const leftSet = new Set(leftTokens)
        const rightSet = new Set(rightTokens)
        const sharedTokens = [...leftSet].filter((token) => rightSet.has(token)).sort()
        if (leftTokens.length > rightTokens.length && rightTokens.every((token) => leftSet.has(token))) {
          group.parent_market_ids.add(right.market_id)
          group.child_market_ids.add(left.market_id)
          group.parent_child_pairs.push({
            parent_market_id: right.market_id,
            child_market_id: left.market_id,
            shared_tokens: sharedTokens,
            specificity_gap: Number((graphQuestionSpecificityScore(left.question, left.market_id) - graphQuestionSpecificityScore(right.question, right.market_id)).toFixed(6)),
          })
        } else if (rightTokens.length > leftTokens.length && leftTokens.every((token) => rightSet.has(token))) {
          group.parent_market_ids.add(left.market_id)
          group.child_market_ids.add(right.market_id)
          group.parent_child_pairs.push({
            parent_market_id: left.market_id,
            child_market_id: right.market_id,
            shared_tokens: sharedTokens,
            specificity_gap: Number((graphQuestionSpecificityScore(right.question, right.market_id) - graphQuestionSpecificityScore(left.question, left.market_id)).toFixed(6)),
          })
        }

        const leftProfile = graphHedgeProfile(left.question)
        const rightProfile = graphHedgeProfile(right.question)
        const hedgeKinds = new Set([leftProfile.kind, rightProfile.kind])
        if (sharedTokens.length >= 2 && ((hedgeKinds.has('upside') && hedgeKinds.has('downside')) || (hedgeKinds.has('neutral') && hedgeKinds.has('negated')) || hedgeKinds.has('mixed'))) {
          group.natural_hedge_market_ids.add(left.market_id)
          group.natural_hedge_market_ids.add(right.market_id)
          group.natural_hedge_pairs.push({
            left_market_id: left.market_id,
            right_market_id: right.market_id,
            hedge_kind: hedgeKinds.has('upside') && hedgeKinds.has('downside')
              ? 'complementary'
              : 'inverse',
            shared_tokens: sharedTokens,
            left_signal: leftProfile.kind,
            right_signal: rightProfile.kind,
          })
        }
      }
    }

    for (const evaluation of items.map((item) => item.evaluation)) {
      group.match_count += 1
      if (evaluation.match.manual_review_required) group.manual_review_required = true
      if (!hasCompatibleResolution(evaluation)) group.compatible_resolution = false
      if (!evaluation.match.currency_compatibility_score || evaluation.match.currency_compatibility_score < 1) group.compatible_currency = false
      if (!evaluation.match.payout_compatibility_score || evaluation.match.payout_compatibility_score < 1) group.compatible_payout = false
      if (evaluation.match.notes.includes('question_normalized')) group.notes.add('question_normalized')
      if (evaluation.match.notes.includes('resolution_mismatch')) group.notes.add('resolution_mismatch')
      if (evaluation.match.notes.includes('currency_mismatch')) group.notes.add('currency_mismatch')
      if (evaluation.match.notes.includes('payout_currency_mismatch')) group.notes.add('payout_currency_mismatch')
      if (evaluation.match.notes.some((note) => note.startsWith('timebox_') || note.startsWith('cutoff_') || note.startsWith('timezone_'))) {
        group.notes.add('timing_mismatch')
        group.desalignment_dimensions.add('timing')
      }
      if (!evaluation.compatible) {
        group.narrative_risk_flags.add('not_compatible')
      }
      if (evaluation.match.manual_review_required) {
        group.narrative_risk_flags.add('manual_review_required')
      }
      group.duplicate_market_count = Math.max(group.duplicate_market_count, Math.max(0, nodesForGroup.length - 1))
      if (evaluation.mismatch_reasons.length > 0) {
        for (const reason of evaluation.mismatch_reasons) {
          if (reason.includes('resolution')) group.desalignment_dimensions.add('resolution')
          if (reason.includes('currency')) group.desalignment_dimensions.add('currency')
          if (reason.includes('payout')) group.desalignment_dimensions.add('payout')
          if (reason.includes('time') || reason.includes('timezone') || reason.includes('cutoff')) group.desalignment_dimensions.add('timing')
        }
      }
    }

    group.metadata = {
      node_count: nodesForGroup.length,
      reference_count: group.reference_market_ids.size,
      comparison_count: group.comparison_market_ids.size,
      parent_market_count: group.parent_market_ids.size,
      child_market_count: group.child_market_ids.size,
      parent_child_pair_count: group.parent_child_pairs.length,
      natural_hedge_market_count: group.natural_hedge_market_ids.size,
      natural_hedge_pair_count: group.natural_hedge_pairs.length,
      question_key: questionKey,
      duplicate_market_count: group.duplicate_market_count,
      duplicate_market_rate: Number((group.duplicate_market_count / Math.max(1, nodesForGroup.length)).toFixed(6)),
      desalignment_count: group.desalignment_dimensions.size,
      desalignment_rate: Number((group.desalignment_dimensions.size / 4).toFixed(6)),
      desalignment_dimensions: [...group.desalignment_dimensions].sort(),
      notes: [...group.notes].sort(),
    }
    comparableGroupMap.set(canonicalEventId, group)
  }

  const comparableGroups = [...comparableGroupMap.values()].map((group) =>
    predictionMarketComparableMarketGroupSchema.parse({
      schema_version: 'v1',
      group_id: `cmpgrp_${group.canonical_event_id.replace(/[^a-z0-9]+/gi, '_').slice(0, 24)}`,
      canonical_event_id: group.canonical_event_id,
      question_key: group.question_key,
      question: group.question,
      relation_kind: group.relation_kind,
      market_ids: [...group.market_ids].sort(),
      comparable_market_refs: [...group.market_ids].sort(),
      venues: [...group.venues].sort(),
      venue_types: [...group.venue_types].sort(),
      reference_market_ids: [...group.reference_market_ids].sort(),
      comparison_market_ids: [...group.comparison_market_ids].sort(),
      parent_market_ids: [...group.parent_market_ids].sort(),
      child_market_ids: [...group.child_market_ids].sort(),
      parent_child_pairs: group.parent_child_pairs,
      natural_hedge_market_ids: [...group.natural_hedge_market_ids].sort(),
      natural_hedge_pairs: group.natural_hedge_pairs,
      resolution_sources: [],
      currencies: [],
      payout_currencies: [],
      notes: [...group.notes].sort(),
      manual_review_required: group.manual_review_required,
      compatible_resolution: group.compatible_resolution,
      compatible_currency: group.compatible_currency,
      compatible_payout: group.compatible_payout,
      match_count: group.match_count,
      duplicate_market_count: group.duplicate_market_count,
      duplicate_market_rate: Number((group.duplicate_market_count / Math.max(1, group.market_ids.size)).toFixed(6)),
      desalignment_count: group.desalignment_dimensions.size,
      desalignment_rate: Number((group.desalignment_dimensions.size / 4).toFixed(6)),
      desalignment_dimensions: [...group.desalignment_dimensions].sort(),
      narrative_risk_flags: [...group.narrative_risk_flags].sort(),
      rationale: [
        `relation=${group.relation_kind}`,
        `venues=[${[...group.venues].sort().join(', ')}]`,
        group.manual_review_required ? 'manual_review_required=yes' : 'manual_review_required=no',
        group.parent_child_pairs.length > 0 ? `parent_child_pairs=${group.parent_child_pairs.length}` : null,
        group.natural_hedge_pairs.length > 0 ? `natural_hedge_pairs=${group.natural_hedge_pairs.length}` : null,
      ].filter((part): part is string => Boolean(part)).join('; '),
      metadata: {
        node_count: group.market_ids.size,
        reference_count: group.reference_market_ids.size,
        comparison_count: group.comparison_market_ids.size,
        parent_market_count: group.parent_market_ids.size,
        child_market_count: group.child_market_ids.size,
        parent_child_pair_count: group.parent_child_pairs.length,
        natural_hedge_market_count: group.natural_hedge_market_ids.size,
        natural_hedge_pair_count: group.natural_hedge_pairs.length,
        question_key: group.question_key,
        duplicate_market_count: group.duplicate_market_count,
        duplicate_market_rate: Number((group.duplicate_market_count / Math.max(1, group.market_ids.size)).toFixed(6)),
        desalignment_count: group.desalignment_dimensions.size,
        desalignment_rate: Number((group.desalignment_dimensions.size / 4).toFixed(6)),
        desalignment_dimensions: [...group.desalignment_dimensions].sort(),
        notes: [...group.notes].sort(),
      },
    }),
  )

  const derivedRoutes = intelligence.summary?.opportunity_type_counts ?? {
    comparison_only: evaluations.filter((evaluation) => evaluation.opportunity_type === 'comparison_only').length,
    relative_value: evaluations.filter((evaluation) => evaluation.opportunity_type === 'relative_value').length,
    cross_venue_signal: evaluations.filter((evaluation) => evaluation.opportunity_type === 'cross_venue_signal').length,
    true_arbitrage: evaluations.filter((evaluation) => evaluation.opportunity_type === 'true_arbitrage').length,
  }
  const executionFilterReasonCodes = uniqueStrings([
    ...evaluations.flatMap((evaluation) => evaluation.mismatch_reasons),
    ...evaluations.flatMap((evaluation) => evaluation.match.manual_review_required ? ['manual_review_required'] : []),
    ...evaluations.flatMap((evaluation) => evaluation.opportunity_type === 'comparison_only' ? ['comparison_only'] : []),
    ...evaluations.flatMap((evaluation) => evaluation.executable_edge == null ? ['no_executable_edge'] : []),
    ...evaluations.flatMap((evaluation) => evaluation.arbitrage_candidate && !evaluation.arbitrage_candidate.executable ? ['non_executable_arbitrage_candidate'] : []),
    ...evaluations.flatMap((evaluation) => {
      const codes: string[] = []
      if (evaluation.match.left_market_ref.venue_type === 'execution-like' || evaluation.match.right_market_ref.venue_type === 'execution-like') {
        codes.push('execution_like_venue')
      }
      if (evaluation.match.left_market_ref.venue_type === 'reference-only' || evaluation.match.right_market_ref.venue_type === 'reference-only') {
        codes.push('reference_only_venue')
      }
      return codes
    }),
  ])
  const executionFilterReasonCodeCounts = countStrings(executionFilterReasonCodes)
  const taxonomy: CrossVenueTaxonomy = derivedRoutes.true_arbitrage > 0
    ? 'true_arbitrage'
    : derivedRoutes.cross_venue_signal > 0
      ? 'cross_venue_signal'
      : derivedRoutes.relative_value > 0
        ? 'relative_value'
        : 'comparison_only'

  return predictionMarketMarketGraphSchema.parse({
    schema_version: 'v1',
    graph_id: `mgraph_${input.snapshot.market.market_id}_${hashText(JSON.stringify({
      marketCount: evaluations.length,
      canonicalEventIds: [...new Set(evaluations.map((evaluation) => evaluation.canonical_event_id))].sort(),
    })).slice(0, 12)}`,
    nodes,
    edges,
    matches,
    rejected_matches: rejectedMatches,
    comparable_groups: comparableGroups,
    metadata: {
      market_count: nodes.length,
      match_count: matches.length,
      rejected_match_count: rejectedMatches.length,
      grouped_market_count: comparableGroups.reduce((sum, group) => sum + group.market_ids.length, 0),
      grouped_market_coverage_rate: Number((comparableGroups.reduce((sum, group) => sum + group.market_ids.length, 0) / Math.max(1, nodes.length)).toFixed(6)),
      ungrouped_market_count: Math.max(0, nodes.length - comparableGroups.reduce((sum, group) => sum + group.market_ids.length, 0)),
      duplicate_market_count: comparableGroups.reduce((sum, group) => sum + group.duplicate_market_count, 0),
      duplicate_market_rate: Number((comparableGroups.reduce((sum, group) => sum + group.duplicate_market_count, 0) / Math.max(1, nodes.length)).toFixed(6)),
      comparable_group_count: comparableGroups.length,
      relation_threshold: 0.45,
      similarity_threshold: 0.58,
      taxonomy,
      execution_filter_reason_codes: executionFilterReasonCodes,
      execution_filter_reason_code_counts: executionFilterReasonCodeCounts,
    },
  })
}

function deriveVenueHealthStatus(
  pipelineGuard: PredictionMarketPipelineGuard | null | undefined,
  runtimeGuard: PredictionMarketRuntimeGuardResult | null | undefined,
): PredictionMarketHealthStatus {
  const health = pipelineGuard?.venue_health
  if (health) {
    if (health.degraded_mode === 'blocked' || health.api_status === 'blocked' || health.stream_status === 'blocked') {
      return 'blocked'
    }
    if (health.degraded_mode === 'degraded' || health.api_status === 'degraded' || health.stream_status === 'degraded') {
      return 'degraded'
    }
    if (health.health_score >= DEFAULT_MIN_VENUE_HEALTH_SCORE) {
      return 'healthy'
    }
  }

  if (runtimeGuard?.verdict === 'blocked') return 'blocked'
  if (runtimeGuard?.verdict === 'degraded') return 'degraded'
  return 'unknown'
}

function capTradeIntentPreviewToCanonicalSize(
  tradeIntentPreview: TradeIntent | null | undefined,
  canonicalSizeUsd: number | null | undefined,
): TradeIntent | null {
  if (!tradeIntentPreview) return null

  if (
    canonicalSizeUsd == null ||
    !Number.isFinite(canonicalSizeUsd) ||
    canonicalSizeUsd <= 0 ||
    canonicalSizeUsd >= tradeIntentPreview.size_usd
  ) {
    return tradeIntentPreview
  }

  return {
    ...tradeIntentPreview,
    size_usd: canonicalSizeUsd,
    notes: uniqueStrings([
      tradeIntentPreview.notes,
      `Canonical execution sizing caps preview size to ${canonicalSizeUsd} USD.`,
    ]).join(' '),
  }
}

function derivePredictionMarketTradeIntentGuard(input: {
  runId: string
  snapshot: MarketSnapshot
  recommendation: EnrichedMarketRecommendationPacket
  pipelineGuard?: PredictionMarketPipelineGuard | null
  runtimeGuard?: PredictionMarketRuntimeGuardResult | null
  compliance?: PredictionMarketComplianceDecision | null
  executionReadiness?: PredictionMarketExecutionReadiness | null
  executionPathways?: PredictionMarketExecutionPathwaysReport | null
  executionProjection?: PredictionMarketExecutionProjectionReport | null
  crossVenueIntelligence?: PredictionMarketCrossVenueIntelligence | null
  benchmarkPromotionReady?: boolean | null
  benchmarkPromotionGateKind?: PredictionMarketsBenchmarkGateSummary['promotion_gate_kind'] | null
  benchmarkPromotionBlockerSummary?: string | null
}): TradeIntentGuard {
  const blockedReasons = uniqueStrings([
    ...(input.recommendation.action === 'bet' ? [] : [`recommendation:${input.recommendation.action}`]),
    ...(input.recommendation.side ? [] : ['missing_trade_side']),
    ...(input.pipelineGuard?.status === 'blocked' ? [
      ...input.pipelineGuard.reasons.map((reason) => `pipeline:${reason}`),
      ...input.pipelineGuard.breached_budgets.map((budget) => `pipeline_budget:${budget}`),
    ] : []),
    ...(input.runtimeGuard?.verdict === 'blocked' ? [
      ...input.runtimeGuard.reasons.map((reason) => `runtime:${reason}`),
    ] : []),
    ...(input.compliance?.status === 'blocked' ? [
      `compliance:${input.compliance.summary}`,
    ] : []),
    ...(input.executionReadiness?.overall_verdict === 'blocked' ? [
      ...input.executionReadiness.blockers.map((reason) => `readiness:${reason}`),
    ] : []),
    ...(input.executionProjection?.verdict === 'blocked' ? [
      ...input.executionProjection.preflight_summary.blockers.map((reason) => `projection:${reason}`),
    ] : []),
    ...(input.executionProjection?.manual_review_required ? ['manual_review_required_for_execution'] : []),
    ...(input.executionReadiness?.compliance_matrix.account_readiness.manual_review_required
      ? ['readiness_manual_review_required']
      : []),
    ...(input.executionProjection?.selected_path === 'live' && input.benchmarkPromotionReady === false
      ? ['benchmark_promotion_not_ready_for_live']
      : []),
    ...(input.executionProjection?.selected_path ? [] : ['no_actionable_execution_projection_path']),
  ])
  const executionSurfacePreview = resolvePredictionMarketExecutionSurfacePreview({
    executionProjection: input.executionProjection,
    executionPathways: input.executionPathways,
  })
  const warningReasons = uniqueStrings([
    ...(input.pipelineGuard?.status === 'degraded' ? input.pipelineGuard.reasons.map((reason) => `pipeline:${reason}`) : []),
    ...(input.runtimeGuard?.verdict === 'degraded' ? input.runtimeGuard.reasons.map((reason) => `runtime:${reason}`) : []),
    ...(input.compliance?.status === 'degraded'
      ? (input.compliance.reasons ?? []).map((reason) => `compliance:${reason.code}`)
      : []),
    ...(input.executionReadiness?.overall_verdict === 'degraded' ? input.executionReadiness.warnings.map((reason) => `readiness:${reason}`) : []),
    ...(input.executionProjection?.verdict === 'downgraded' ? [
      ...input.executionProjection.preflight_summary.downgrade_reasons.map((reason) => `projection:${reason}`),
    ] : []),
    ...(executionSurfacePreview.preview != null ? ['trade_intent_preview_available'] : []),
  ])
  const manualReviewRequired = Boolean(
    input.recommendation.action !== 'bet'
    || input.recommendation.side == null
    || input.pipelineGuard?.status === 'blocked'
    || input.runtimeGuard?.verdict === 'blocked'
    || input.compliance?.status === 'blocked'
    || input.executionReadiness?.compliance_matrix.account_readiness.manual_review_required
    || input.executionProjection?.manual_review_required
  )
  const verdict = blockedReasons.length > 0 || manualReviewRequired
    ? 'blocked'
    : warningReasons.length > 0
      ? 'annotated'
      : 'allowed'
  const selectedPath = input.executionProjection?.selected_path ?? null
  const highestSafeMode = input.executionProjection?.highest_safe_requested_mode ?? null
  const selectedProjectionPath = executionSurfacePreview.selected_projection_path
  const rawTradeIntentPreview = executionSurfacePreview.raw_preview
  const tradeIntentPreview = executionSurfacePreview.preview
  const tradeIntentPreviewSource = executionSurfacePreview.preview_source ?? 'none'
  const tradeIntentPreviewVia = executionSurfacePreview.source
  const benchmarkGateLiveBlockReason =
    input.executionProjection?.selected_path === 'live' && input.benchmarkPromotionReady === false
      ? (input.benchmarkPromotionBlockerSummary ?? 'out_of_sample_unproven')
      : null
  const summary = blockedReasons.length > 0
    ? `blocked=${blockedReasons.slice(0, 3).join(';')}`
    : warningReasons.length > 0
      ? `warnings=${warningReasons.slice(0, 3).join(';')}`
      : 'trade_intent_guard_ok'

  return tradeIntentGuardSchema.parse({
    schema_version: '1.0.0',
    gate_name: 'trade_intent_guard',
    verdict,
    manual_review_required: manualReviewRequired,
    blocked_reasons: blockedReasons,
    warning_reasons: warningReasons,
    snapshot_staleness_ms: input.pipelineGuard?.metrics.snapshot_staleness_ms ?? null,
    edge_after_fees_bps: input.recommendation.edge_bps ?? null,
    venue_health_status: deriveVenueHealthStatus(input.pipelineGuard, input.runtimeGuard),
    projection_verdict: input.executionProjection?.verdict ?? null,
    readiness_route: input.executionReadiness?.highest_safe_mode ?? null,
    selected_path: selectedPath,
    highest_safe_mode: highestSafeMode,
    trade_intent_preview: tradeIntentPreview,
    summary,
    source_refs: {
      pipeline_guard: `${input.runId}:pipeline_guard`,
      runtime_guard: `${input.runId}:runtime_guard`,
      compliance_report: `${input.runId}:compliance_report`,
      execution_readiness: `${input.runId}:execution_readiness`,
      execution_pathways: `${input.runId}:execution_pathways`,
      execution_projection: `${input.runId}:execution_projection`,
      cross_venue_intelligence: `${input.runId}:cross_venue_intelligence`,
      recommendation_packet: `${input.runId}:recommendation_packet`,
    },
    metadata: {
      run_id: input.runId,
      market_id: input.snapshot.market.market_id,
      venue: input.snapshot.venue,
      cross_venue_manual_review_count: input.executionReadiness?.cross_venue_summary.manual_review.length ?? 0,
      cross_venue_comparison_only_count: input.executionReadiness?.cross_venue_summary.comparison_only.length ?? 0,
      execution_pathways_highest_actionable_mode: input.executionPathways?.highest_actionable_mode ?? null,
      trade_intent_preview_available: tradeIntentPreview != null,
      trade_intent_preview_source: tradeIntentPreviewSource,
      trade_intent_preview_via: tradeIntentPreviewVia,
      trade_intent_preview_uses_projection_selected_preview:
        executionSurfacePreview.uses_projection_selected_preview,
      execution_projection_selected_preview_available:
        executionSurfacePreview.uses_projection_selected_preview,
      execution_projection_selected_preview_source:
        executionSurfacePreview.projection_selected_preview_source,
      trade_intent_preview_capped_to_canonical_size:
        rawTradeIntentPreview != null &&
        tradeIntentPreview != null &&
        rawTradeIntentPreview.size_usd !== tradeIntentPreview.size_usd,
      selected_projection_path_status: selectedProjectionPath?.status ?? null,
      selected_projection_path_effective_mode: selectedProjectionPath?.effective_mode ?? null,
      selected_projection_sizing_signal_present: selectedProjectionPath?.sizing_signal != null,
      selected_projection_shadow_arbitrage_signal_present: selectedProjectionPath?.shadow_arbitrage_signal != null,
      selected_projection_canonical_size_usd: selectedProjectionPath?.sizing_signal?.canonical_size_usd ?? null,
      benchmark_promotion_ready: input.benchmarkPromotionReady ?? null,
      benchmark_promotion_gate_kind: input.benchmarkPromotionGateKind ?? null,
      benchmark_promotion_blocker_summary: input.benchmarkPromotionBlockerSummary ?? null,
      benchmark_gate_blocks_live: benchmarkGateLiveBlockReason != null,
      benchmark_gate_live_block_reason: benchmarkGateLiveBlockReason,
    },
  })
}

function derivePredictionMarketMultiVenueExecution(input: {
  runId: string
  snapshot: MarketSnapshot
  crossVenueIntelligence?: PredictionMarketCrossVenueIntelligence | null
  executionPathways?: PredictionMarketExecutionPathwaysReport | null
  executionProjection?: PredictionMarketExecutionProjectionReport | null
  tradeIntentGuard?: TradeIntentGuard | null
}): MultiVenueExecution {
  const evaluations = input.crossVenueIntelligence?.evaluations ?? []
  const candidates = input.crossVenueIntelligence?.arbitrage_candidates ?? []
  const reportSummary = input.crossVenueIntelligence?.summary
  const marketIds = new Set<string>([input.snapshot.market.market_id])
  const referenceMarketIds = new Set<string>()
  const signalMarketIds = new Set<string>()
  const executionMarketIds = new Set<string>()
  const readOnlyMarketIds = new Set<string>()
  const comparableGroupIds = new Set<string>()

  for (const evaluation of evaluations) {
    comparableGroupIds.add(evaluation.canonical_event_id)
    marketIds.add(evaluation.match.left_market_ref.market_id)
    marketIds.add(evaluation.match.right_market_ref.market_id)
    referenceMarketIds.add(evaluation.match.left_market_ref.market_id)
    referenceMarketIds.add(evaluation.match.right_market_ref.market_id)

    if (evaluation.arbitrage_candidate?.executable) {
      signalMarketIds.add(evaluation.match.left_market_ref.market_id)
      signalMarketIds.add(evaluation.match.right_market_ref.market_id)
      executionMarketIds.add(evaluation.arbitrage_candidate.buy_ref.market_id)
      executionMarketIds.add(evaluation.arbitrage_candidate.sell_ref.market_id)
    } else {
      readOnlyMarketIds.add(evaluation.match.left_market_ref.market_id)
      readOnlyMarketIds.add(evaluation.match.right_market_ref.market_id)
    }
  }

  const executionRoutes = reportSummary?.opportunity_type_counts ?? {
    comparison_only: evaluations.filter((evaluation) => evaluation.opportunity_type === 'comparison_only').length,
    relative_value: evaluations.filter((evaluation) => evaluation.opportunity_type === 'relative_value').length,
    cross_venue_signal: evaluations.filter((evaluation) => evaluation.opportunity_type === 'cross_venue_signal').length,
    true_arbitrage: evaluations.filter((evaluation) => evaluation.opportunity_type === 'true_arbitrage').length,
  }
  const tradeablePlanCount = candidates.filter((candidate) => candidate.executable).length
  const executionPlanCount = evaluations.length
  const selectedProjectionPath = resolveCanonicalPredictionMarketProjectionPath(input.executionProjection)
  const selectedPreview = resolveCanonicalPredictionMarketSelectedPreview(input.executionProjection)
  const executionSurfacePreview = resolvePredictionMarketExecutionSurfacePreview({
    executionProjection: input.executionProjection,
    executionPathways: input.executionPathways,
  })
  const executionFilterReasonCodes = uniqueStrings([
    ...evaluations.flatMap((evaluation) => evaluation.mismatch_reasons),
    ...evaluations.flatMap((evaluation) => evaluation.match.manual_review_required ? ['manual_review_required'] : []),
    ...evaluations.flatMap((evaluation) => evaluation.opportunity_type === 'comparison_only' ? ['comparison_only'] : []),
    ...evaluations.flatMap((evaluation) => evaluation.executable_edge == null ? ['no_executable_edge'] : []),
    ...evaluations.flatMap((evaluation) => evaluation.arbitrage_candidate && !evaluation.arbitrage_candidate.executable ? ['non_executable_arbitrage_candidate'] : []),
    ...(executionMarketIds.size === 0 ? ['no_execution_market'] : []),
    ...(input.tradeIntentGuard?.manual_review_required ? ['manual_review_required'] : []),
    ...(input.tradeIntentGuard?.blocked_reasons ?? []),
    ...(input.tradeIntentGuard?.verdict === 'blocked' ? ['trade_intent_guard_blocked'] : []),
    ...(input.executionProjection?.verdict === 'blocked' ? ['execution_projection_blocked'] : []),
    ...(input.executionProjection?.verdict === 'downgraded' ? ['execution_projection_downgraded'] : []),
    ...evaluations.flatMap((evaluation) => {
      const codes: string[] = []
      if (evaluation.match.left_market_ref.venue_type === 'execution-like' || evaluation.match.right_market_ref.venue_type === 'execution-like') {
        codes.push('execution_like_venue')
      }
      if (evaluation.match.left_market_ref.venue_type === 'reference-only' || evaluation.match.right_market_ref.venue_type === 'reference-only') {
        codes.push('reference_only_venue')
      }
      return codes
    }),
  ])
  const executionFilterReasonCodeCounts = countStrings(executionFilterReasonCodes)
  const taxonomy: CrossVenueTaxonomy = executionRoutes.true_arbitrage > 0
    ? 'true_arbitrage'
    : executionRoutes.cross_venue_signal > 0
      ? 'cross_venue_signal'
      : executionRoutes.relative_value > 0
        ? 'relative_value'
        : 'comparison_only'

  const summary = tradeablePlanCount > 0
    ? `${tradeablePlanCount} tradeable cross-venue plans derived across ${comparableGroupIds.size} comparable groups.`
    : `No tradeable cross-venue execution plans were derived; the surface remains comparison-only.`

  return multiVenueExecutionSchema.parse({
    schema_version: '1.0.0',
    gate_name: 'multi_venue_execution',
    report_id: null,
    taxonomy,
    execution_filter_reason_codes: executionFilterReasonCodes,
    execution_filter_reason_code_counts: executionFilterReasonCodeCounts,
    market_count: marketIds.size,
    comparable_group_count: comparableGroupIds.size,
    execution_candidate_count: candidates.length,
    execution_plan_count: executionPlanCount,
    tradeable_plan_count: tradeablePlanCount,
    execution_routes: executionRoutes,
    tradeable_market_ids: Array.from(executionMarketIds),
    read_only_market_ids: Array.from(readOnlyMarketIds),
    reference_market_ids: Array.from(referenceMarketIds),
    signal_market_ids: Array.from(signalMarketIds),
    execution_market_ids: Array.from(executionMarketIds),
    summary,
    source_refs: {
      cross_venue_intelligence: `${input.runId}:cross_venue_intelligence`,
      execution_pathways: `${input.runId}:execution_pathways`,
      execution_projection: `${input.runId}:execution_projection`,
    },
    metadata: {
      run_id: input.runId,
      market_id: input.snapshot.market.market_id,
      venue: input.snapshot.venue,
      cross_venue_report_present: reportSummary != null,
      execution_pathways_highest_actionable_mode: input.executionPathways?.highest_actionable_mode ?? null,
      execution_projection_selected_path: input.executionProjection?.selected_path ?? null,
      execution_projection_selected_path_status: selectedProjectionPath?.status ?? null,
      execution_projection_selected_path_shadow_signal_present: selectedProjectionPath?.shadow_arbitrage_signal != null,
      execution_projection_selected_path_canonical_size_usd: selectedProjectionPath?.sizing_signal?.canonical_size_usd ?? null,
      execution_projection_selected_preview_available: selectedPreview.preview != null,
      execution_projection_selected_preview_source: selectedPreview.source,
      execution_projection_selected_preview_size_usd: selectedPreview.preview?.size_usd ?? null,
      execution_surface_preview_via: executionSurfacePreview.source,
      execution_surface_preview_source: executionSurfacePreview.preview_source,
      execution_surface_preview_size_usd: executionSurfacePreview.preview?.size_usd ?? null,
      execution_surface_preview_uses_projection_selected_preview:
        executionSurfacePreview.uses_projection_selected_preview,
      execution_candidate_count: candidates.length,
      tradeable_plan_count: tradeablePlanCount,
      taxonomy,
      execution_filter_reason_codes: executionFilterReasonCodes,
      execution_filter_reason_code_counts: executionFilterReasonCodeCounts,
    },
  })
}

function capExecutionReadinessMode(
  highestSafeMode: PredictionMarketExecutionReadinessReport['highest_safe_mode'],
  capMode: PredictionMarketExecutionReadinessReport['highest_safe_mode'],
): PredictionMarketExecutionReadinessReport['highest_safe_mode'] {
  if (!highestSafeMode || !capMode) return highestSafeMode

  const rank: Record<NonNullable<PredictionMarketExecutionReadinessReport['highest_safe_mode']>, number> = {
    discovery: 0,
    paper: 1,
    shadow: 2,
    live: 3,
  }

  return rank[highestSafeMode] > rank[capMode] ? capMode : highestSafeMode
}

function buildPredictionMarketComplianceMatrix(input: {
  snapshot: MarketSnapshot
  pipelineGuard: PredictionMarketPipelineGuard
  compliance: PredictionMarketComplianceDecision
}): PredictionMarketComplianceMatrix {
  const accountReadiness = input.compliance.account_readiness ?? {
    jurisdiction_status: 'unknown',
    account_type: 'viewer',
    kyc_status: 'unknown',
    api_key_present: false,
    trading_enabled: false,
    manual_review_required: true,
    ready_for_paper: true,
    ready_for_shadow: false,
    ready_for_live: false,
  }
  const normalizeDecision = (
    mode: PredictionMarketComplianceDecision['requested_mode'],
    decision: Partial<PredictionMarketComplianceDecision>,
  ): PredictionMarketComplianceDecision => {
    const normalizedStatus = decision.status ?? 'degraded'
    return {
      venue: decision.venue ?? input.snapshot.venue,
      venue_type: decision.venue_type ?? input.snapshot.market.venue_type,
      requested_mode: decision.requested_mode ?? mode,
      effective_mode: decision.effective_mode ?? mode,
      status: normalizedStatus,
      allowed: decision.allowed ?? normalizedStatus !== 'blocked',
      summary: decision.summary ?? `${mode} mode compliance was normalized conservatively.`,
      reasons: Array.isArray(decision.reasons) ? decision.reasons : [],
      account_readiness: decision.account_readiness ?? accountReadiness,
    }
  }
  const complianceInput = {
    venue: input.snapshot.venue,
    venue_type: input.snapshot.market.venue_type,
    capabilities: input.pipelineGuard.venue_capabilities,
    jurisdiction: accountReadiness.jurisdiction_status,
    account_type: accountReadiness.account_type,
    kyc_status: accountReadiness.kyc_status,
    api_key_present: accountReadiness.api_key_present,
    trading_enabled: accountReadiness.trading_enabled,
    manual_review_required: accountReadiness.manual_review_required,
  } as const

  const decisions = {
    discovery: normalizeDecision('discovery', evaluatePredictionMarketCompliance({ ...complianceInput, mode: 'discovery' })),
    paper: normalizeDecision('paper', evaluatePredictionMarketCompliance({ ...complianceInput, mode: 'paper' })),
    shadow: normalizeDecision('shadow', evaluatePredictionMarketCompliance({ ...complianceInput, mode: 'shadow' })),
    live: normalizeDecision('live', evaluatePredictionMarketCompliance({ ...complianceInput, mode: 'live' })),
  }
  const highestAuthorizedMode = (['live', 'shadow', 'paper', 'discovery'] as const).find((mode) =>
    decisions[mode].allowed && decisions[mode].status !== 'blocked',
  ) ?? null

  return {
    venue: input.snapshot.venue,
    venue_type: input.snapshot.market.venue_type,
    highest_authorized_mode: highestAuthorizedMode,
    account_readiness: decisions.live.account_readiness,
    decisions,
  }
}

function derivePredictionMarketExecutionReadiness(input: {
  snapshot: MarketSnapshot
  pipelineGuard: PredictionMarketPipelineGuard
  compliance: PredictionMarketComplianceDecision
  crossVenueIntelligence: PredictionMarketCrossVenueIntelligence
  microstructureLab?: MicrostructureLabReport | null
  strategyDecision?: StrategyDecisionPacket | null
  resolutionAnomalyReport?: ResolutionAnomalyReport | null
}): PredictionMarketExecutionReadiness {
  const complianceMatrix = buildPredictionMarketComplianceMatrix({
    snapshot: input.snapshot,
    pipelineGuard: input.pipelineGuard,
    compliance: input.compliance,
  })
  const baseReadiness = buildPredictionMarketExecutionReadiness({
    capabilities: input.pipelineGuard.venue_capabilities,
    health: input.pipelineGuard.venue_health,
    budgets: input.pipelineGuard.budgets,
    compliance_matrix: complianceMatrix,
  })
  const crossVenueSummary = input.crossVenueIntelligence.summary ?? summarizeCrossVenueIntelligence(
    input.crossVenueIntelligence.evaluations,
  )
  const pipelineReasonLines = input.pipelineGuard.reasons.map((reason) => `pipeline:${reason}`)
  const pipelineBudgetLines = input.pipelineGuard.breached_budgets.map((reason) => `pipeline_budget:${reason}`)

  let highestSafeMode = baseReadiness.highest_safe_mode
  let overallVerdict = baseReadiness.overall_verdict

  if (input.pipelineGuard.status === 'blocked') {
    highestSafeMode = capExecutionReadinessMode(highestSafeMode, 'discovery')
    overallVerdict = 'blocked'
  } else if (input.pipelineGuard.status === 'degraded') {
    highestSafeMode = capExecutionReadinessMode(highestSafeMode, 'paper')
    if (overallVerdict === 'ready') {
      overallVerdict = 'degraded'
    }
  }

  const microstructureWarnings: string[] = []
  if (input.microstructureLab) {
    microstructureWarnings.push(
      `microstructure:${input.microstructureLab.summary.recommended_mode}:${input.microstructureLab.summary.worst_case_severity}`,
    )

    if (input.microstructureLab.summary.recommended_mode === 'wait') {
      highestSafeMode = capExecutionReadinessMode(highestSafeMode, 'paper')
      if (overallVerdict === 'ready') {
        overallVerdict = 'degraded'
      }
      microstructureWarnings.push('microstructure:shadow_and_live_require_dry_run_only')
    }
  }

  const strategyWarnings: string[] = []
  if (input.strategyDecision) {
    strategyWarnings.push(`strategy:${input.strategyDecision.decision}`)
    if (input.strategyDecision.strategy_family) {
      strategyWarnings.push(`strategy_family:${input.strategyDecision.strategy_family}`)
    }

    if (input.strategyDecision.decision === 'shadow') {
      highestSafeMode = capExecutionReadinessMode(highestSafeMode, 'paper')
      if (overallVerdict === 'ready') {
        overallVerdict = 'degraded'
      }
      strategyWarnings.push('strategy:shadow_only_until_manual_review_clears')
    } else if (input.strategyDecision.decision === 'defer') {
      highestSafeMode = capExecutionReadinessMode(highestSafeMode, 'discovery')
      overallVerdict = 'blocked'
      strategyWarnings.push('strategy:deferred_execution_disabled')
    }
  }

  if (input.resolutionAnomalyReport?.severity === 'high' || input.resolutionAnomalyReport?.severity === 'critical') {
    highestSafeMode = capExecutionReadinessMode(highestSafeMode, 'discovery')
    overallVerdict = 'blocked'
    strategyWarnings.push(`resolution_anomaly:${input.resolutionAnomalyReport.anomaly_kind}`)
  }

  const blockers = uniqueStrings([
    ...baseReadiness.blockers,
    ...(input.pipelineGuard.status === 'blocked' ? pipelineReasonLines : []),
    ...(input.strategyDecision?.decision === 'defer' ? ['strategy_execution_deferred'] : []),
    ...((input.resolutionAnomalyReport?.severity === 'high' || input.resolutionAnomalyReport?.severity === 'critical')
      ? [`resolution_anomaly:${input.resolutionAnomalyReport.anomaly_kind}`]
      : []),
  ])
  const warnings = uniqueStrings([
    ...baseReadiness.warnings,
    ...(input.pipelineGuard.status !== 'blocked' ? pipelineReasonLines : []),
    ...pipelineBudgetLines,
    ...microstructureWarnings,
    ...strategyWarnings,
  ])
  const summary = highestSafeMode
    ? `Highest safe mode is ${highestSafeMode}. Pipeline is ${input.pipelineGuard.status}. ${baseReadiness.summary}${input.microstructureLab ? ` Microstructure recommends ${input.microstructureLab.summary.recommended_mode}.` : ''}`
    : `No safe execution mode. Pipeline is ${input.pipelineGuard.status}. ${baseReadiness.summary}${input.microstructureLab ? ` Microstructure recommends ${input.microstructureLab.summary.recommended_mode}.` : ''}`

  return {
    ...baseReadiness,
    compliance_matrix: complianceMatrix,
    highest_safe_mode: highestSafeMode,
    overall_verdict: overallVerdict,
    blockers,
    warnings,
    summary,
    pipeline_status: input.pipelineGuard.status,
    pipeline_reasons: uniqueStrings(input.pipelineGuard.reasons),
    cross_venue_summary: crossVenueSummary,
    microstructure_lab: input.microstructureLab ?? null,
  }
}

function derivePredictionMarketExecutionPathways(input: {
  runId: string
  snapshot: MarketSnapshot
  resolutionPolicy: ResolutionPolicy
  forecast: ForecastPacket
  recommendation: EnrichedMarketRecommendationPacket
  executionReadiness: PredictionMarketExecutionReadiness
  strategy_name?: string | null
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
  strategy_trade_intent_preview?: TradeIntent | null
  strategy_canonical_trade_intent_preview?: TradeIntent | null
  strategy_shadow_summary?: string | null
  operator_thesis?: PredictionMarketExecutionPathwaysOperatorThesis | null
  research_pipeline_trace?: PredictionMarketExecutionPathwaysResearchPipelineTrace | null
}): PredictionMarketExecutionPathwaysReport {
  return buildPredictionMarketExecutionPathways({
    runId: input.runId,
    snapshot: input.snapshot,
    resolutionPolicy: input.resolutionPolicy,
    forecast: input.forecast,
    recommendation: input.recommendation,
    executionReadiness: input.executionReadiness,
    strategy_name: input.strategy_name ?? null,
    market_regime_summary: input.market_regime_summary ?? null,
    primary_strategy_summary: input.primary_strategy_summary ?? null,
    strategy_summary: input.strategy_summary ?? null,
    strategy_trade_intent_preview: input.strategy_trade_intent_preview ?? null,
    strategy_canonical_trade_intent_preview: input.strategy_canonical_trade_intent_preview ?? null,
    strategy_shadow_summary: input.strategy_shadow_summary ?? null,
    operator_thesis: input.operator_thesis ?? null,
    research_pipeline_trace: input.research_pipeline_trace ?? null,
  })
}

function buildPredictionMarketExecutionPathwaySupplementalArtifacts(input: {
  evidencePackets?: EvidencePacket[] | null
  decisionPacket?: DecisionPacket | null
  researchSidecar?: MarketResearchSidecar | null
  thesisProbability?: number | null
  thesisRationale?: string | null
}): {
  operator_thesis: PredictionMarketExecutionPathwaysOperatorThesis | null
  research_pipeline_trace: PredictionMarketExecutionPathwaysResearchPipelineTrace | null
} {
  const researchSynthesis = input.researchSidecar?.synthesis ?? null
  const manualThesisEvidenceRefs = uniqueStrings(
    (input.evidencePackets ?? [])
      .filter((packet) => packet.type === 'manual_thesis')
      .map((packet) => packet.evidence_id),
  )
  const hasManualThesisHints =
    manualThesisEvidenceRefs.length > 0 ||
    input.thesisProbability != null ||
    input.thesisRationale != null ||
    researchSynthesis?.manual_thesis_probability_hint != null ||
    researchSynthesis?.manual_thesis_rationale_hint != null
  const operatorSource: PredictionMarketExecutionPathwaysOperatorThesis['source'] =
    hasManualThesisHints
      ? 'manual_thesis'
      : input.decisionPacket
        ? 'decision_packet'
        : input.researchSidecar
          ? 'research_bridge'
          : 'none'
  const probabilityYes =
    input.thesisProbability
    ?? input.decisionPacket?.probability_estimate
    ?? researchSynthesis?.manual_thesis_probability_hint
    ?? null
  const rationale =
    input.thesisRationale
    ?? (input.decisionPacket ? buildDecisionPacketThesisRationale(input.decisionPacket) : undefined)
    ?? researchSynthesis?.manual_thesis_rationale_hint
    ?? null
  const evidenceRefs = uniqueStrings([
    ...manualThesisEvidenceRefs,
    ...(input.decisionPacket?.source_packet_refs ?? []),
    ...(researchSynthesis?.evidence_refs ?? []),
  ])

  const operatorThesis =
    operatorSource === 'none' &&
    probabilityYes == null &&
    rationale == null &&
    evidenceRefs.length === 0
      ? null
      : {
          present: probabilityYes != null || rationale != null || evidenceRefs.length > 0,
          source: operatorSource,
          probability_yes: probabilityYes,
          rationale,
          evidence_refs: evidenceRefs,
          summary: probabilityYes != null
            ? `Operator thesis: ${Math.round(probabilityYes * 100)}% yes via ${operatorSource}.`
            : `Operator thesis: ${operatorSource}.`,
        }

  const pipelineTrace = researchSynthesis?.pipeline_trace ?? null
  const researchPipelineTrace: PredictionMarketExecutionPathwaysResearchPipelineTrace | null = pipelineTrace && researchSynthesis
    ? {
        pipeline_id: researchSynthesis.pipeline_version_metadata.pipeline_id,
        pipeline_version: researchSynthesis.pipeline_version_metadata.pipeline_version,
        preferred_mode: pipelineTrace.stages.aggregate.preferred_mode,
        oracle_family: researchSynthesis.forecaster_candidates.length > 0 ||
          researchSynthesis.independent_forecaster_outputs.length > 0
          ? 'llm_superforecaster'
          : researchSynthesis.manual_thesis_probability_hint != null ||
              researchSynthesis.manual_thesis_rationale_hint != null
            ? 'manual_only'
            : 'llm_oracle',
        forecaster_count:
          researchSynthesis.forecaster_candidates.length > 0
            ? researchSynthesis.forecaster_candidates.length
            : researchSynthesis.independent_forecaster_outputs.length > 0
              ? researchSynthesis.independent_forecaster_outputs.length
              : null,
        evidence_count: researchSynthesis.evidence_count,
        source_refs: uniqueStrings([
          ...researchSynthesis.evidence_refs,
          ...pipelineTrace.stages.query.queries,
        ]),
        summary: pipelineTrace.summary,
      }
    : null

  return {
    operator_thesis: operatorThesis,
    research_pipeline_trace: researchPipelineTrace,
  }
}

function derivePredictionMarketExecutionProjection(input: {
  runId: string
  snapshot: MarketSnapshot
  forecast: ForecastPacket
  resolutionPolicy: ResolutionPolicy
  recommendation: EnrichedMarketRecommendationPacket
  executionReadiness: PredictionMarketExecutionReadiness
  crossVenueIntelligence?: PredictionMarketCrossVenueIntelligence | null
  strategy_name?: string | null
  market_regime_summary?: string | null
  primary_strategy_summary?: string | null
  strategy_summary?: string | null
  strategy_trade_intent_preview?: TradeIntent | null
  strategy_canonical_trade_intent_preview?: TradeIntent | null
  strategy_shadow_summary?: string | null
}): PredictionMarketExecutionProjectionReport {
  const projection = projectPredictionMarketExecutionPath({
    run_id: input.runId,
    snapshot: input.snapshot,
    forecast: input.forecast,
    recommendation: input.recommendation,
    execution_readiness: input.executionReadiness,
    resolution_policy: input.resolutionPolicy,
    strategy_name: input.strategy_name ?? null,
    market_regime_summary: input.market_regime_summary ?? null,
    primary_strategy_summary: input.primary_strategy_summary ?? null,
    strategy_summary: input.strategy_summary ?? null,
    strategy_trade_intent_preview: input.strategy_trade_intent_preview ?? null,
    strategy_canonical_trade_intent_preview: input.strategy_canonical_trade_intent_preview ?? null,
    strategy_shadow_summary: input.strategy_shadow_summary ?? null,
  })

  const modes = Object.fromEntries(
    (['paper', 'shadow', 'live'] as const).map((mode) => {
      const report = projection.projected_paths[mode]
      return [mode, {
        requested_mode: mode,
        verdict: report.status,
        effective_mode: report.effective_mode,
        blockers: report.blockers,
        warnings: report.warnings,
        summary: report.reason_summary,
      }]
    }),
  ) as PredictionMarketExecutionProjectionReport['modes']

  const selectedPath = projection.selected_path
  const selectedReport = selectedPath ? projection.projected_paths[selectedPath] : null

  const report = {
    ...projection,
    basis: {
      uses_execution_readiness: true as const,
      uses_compliance: true as const,
      uses_capital: input.executionReadiness.capital_ledger != null,
      uses_reconciliation: input.executionReadiness.reconciliation != null,
      uses_microstructure: input.executionReadiness.microstructure_lab != null,
      capital_status: input.executionReadiness.capital_ledger ? 'attached' as const : 'unavailable' as const,
      reconciliation_status: input.executionReadiness.reconciliation
        ? (input.executionReadiness.reconciliation.within_tolerance ? 'attached' as const : 'degraded' as const)
        : 'unavailable' as const,
      source_refs: {
        pipeline_guard: `${input.runId}:pipeline_guard`,
        compliance_report: `${input.runId}:compliance_report`,
        execution_readiness: `${input.runId}:execution_readiness`,
        venue_health: `${input.runId}:pipeline_guard#venue_health`,
        capital_ledger: input.executionReadiness.capital_ledger
          ? `${input.runId}:execution_readiness#capital_ledger`
          : null,
        reconciliation: input.executionReadiness.reconciliation
          ? `${input.runId}:execution_readiness#reconciliation`
          : null,
        microstructure_lab: input.executionReadiness.microstructure_lab
          ? `${input.runId}:microstructure_lab`
          : null,
      },
      canonical_gate: {
        gate_name: 'execution_projection' as const,
        single_runtime_gate: true as const,
        enforced_for_modes: ['paper', 'shadow', 'live'] as PredictionMarketExecutionProjectionMode[],
      },
    },
    microstructure_summary: input.executionReadiness.microstructure_lab
      ? {
        recommended_mode: input.executionReadiness.microstructure_lab.summary.recommended_mode,
        worst_case_severity: input.executionReadiness.microstructure_lab.summary.worst_case_severity,
        executable_deterioration_bps: input.executionReadiness.microstructure_lab.summary.executable_deterioration_bps,
        execution_quality_score: input.executionReadiness.microstructure_lab.summary.execution_quality_score,
      }
      : null,
    highest_safe_requested_mode: selectedPath,
    recommended_effective_mode: selectedReport?.effective_mode ?? null,
    modes,
  }

  return {
    ...report,
    preflight_summary: buildPredictionMarketExecutionPreflightSummary(report, {
      venue: input.resolutionPolicy.venue,
      crossVenueIntelligence: input.crossVenueIntelligence ?? null,
    }),
  }
}

function derivePredictionMarketExecutionSurfaces(input: {
  runId: string
  snapshot: MarketSnapshot
  recommendation: EnrichedMarketRecommendationPacket
  pipelineGuard?: PredictionMarketPipelineGuard | null
  runtimeGuard?: PredictionMarketRuntimeGuardResult | null
  compliance?: PredictionMarketComplianceDecision | null
  crossVenueIntelligence?: PredictionMarketCrossVenueIntelligence | null
  executionReadiness?: PredictionMarketExecutionReadiness | null
  executionPathways?: PredictionMarketExecutionPathwaysReport | null
  executionProjection?: PredictionMarketExecutionProjectionReport | null
  benchmarkPromotionReady?: boolean | null
  benchmarkPromotionGateKind?: PredictionMarketsBenchmarkGateSummary['promotion_gate_kind'] | null
  benchmarkPromotionBlockerSummary?: string | null
}): {
  trade_intent_guard: TradeIntentGuard
  multi_venue_execution: MultiVenueExecution
} {
  const tradeIntentGuard = derivePredictionMarketTradeIntentGuard({
    runId: input.runId,
    snapshot: input.snapshot,
    recommendation: input.recommendation,
    pipelineGuard: input.pipelineGuard,
    runtimeGuard: input.runtimeGuard,
    compliance: input.compliance,
    executionReadiness: input.executionReadiness,
    executionPathways: input.executionPathways,
    executionProjection: input.executionProjection,
    crossVenueIntelligence: input.crossVenueIntelligence,
    benchmarkPromotionReady: input.benchmarkPromotionReady,
    benchmarkPromotionGateKind: input.benchmarkPromotionGateKind,
    benchmarkPromotionBlockerSummary: input.benchmarkPromotionBlockerSummary,
  })
  return {
    trade_intent_guard: tradeIntentGuard,
    multi_venue_execution: derivePredictionMarketMultiVenueExecution({
      runId: input.runId,
      snapshot: input.snapshot,
      crossVenueIntelligence: input.crossVenueIntelligence,
      executionPathways: input.executionPathways,
      executionProjection: input.executionProjection,
      tradeIntentGuard,
    }),
  }
}

function normalizeExecutionProjectionReport(
  projection: PredictionMarketExecutionProjectionReport | null | undefined,
): PredictionMarketExecutionProjectionReport | null {
  if (!projection) return null
  if (projection.preflight_summary) {
    return {
      ...projection,
      microstructure_summary: projection.microstructure_summary ?? null,
    }
  }
  return {
    ...projection,
    microstructure_summary: projection.microstructure_summary ?? null,
    preflight_summary: buildPredictionMarketExecutionPreflightSummary(projection),
  }
}

function rehydratePredictionMarketTradeIntentGuardForBenchmarkPromotion(
  tradeIntentGuard: TradeIntentGuard | null,
  details: Partial<PredictionMarketRunRuntimeHints> & {
    execution_projection?: PredictionMarketExecutionProjectionReport | null
  },
): TradeIntentGuard | null {
  if (!tradeIntentGuard) return null

  const benchmarkPromotionState = resolvePredictionMarketBenchmarkPromotionState(details)
  const benchmarkLiveGate = resolvePredictionMarketBenchmarkLiveGateState({
    ...details,
    trade_intent_guard: tradeIntentGuard,
  })
  const benchmarkPromotionBlockerSummary = benchmarkPromotionState.promotion_blocker_summary
    ?? benchmarkLiveGate.live_block_reason
    ?? null
  const baseMetadata = {
    ...(tradeIntentGuard.metadata ?? {}),
    benchmark_promotion_ready: benchmarkLiveGate.promotion_ready,
    benchmark_promotion_gate_kind: benchmarkLiveGate.promotion_gate_kind,
    benchmark_promotion_blocker_summary: benchmarkPromotionBlockerSummary,
    benchmark_gate_blocks_live: benchmarkLiveGate.blocks_live,
    benchmark_gate_live_block_reason: benchmarkLiveGate.live_block_reason,
  }
  if (!benchmarkLiveGate.blocks_live) {
    return tradeIntentGuardSchema.parse({
      ...tradeIntentGuard,
      metadata: baseMetadata,
    })
  }

  const blockedReasons = uniqueStrings([
    ...(tradeIntentGuard.blocked_reasons ?? []),
    'benchmark_promotion_not_ready_for_live',
  ])

  return tradeIntentGuardSchema.parse({
    ...tradeIntentGuard,
    verdict: 'blocked',
    manual_review_required: true,
    blocked_reasons: blockedReasons,
    summary: `blocked=${blockedReasons.slice(0, 3).join(';')}`,
    metadata: baseMetadata,
  })
}

function buildPredictionMarketExecutionPreflightSummary(
  projection: Omit<PredictionMarketExecutionProjectionReport, 'preflight_summary'>,
  options?: {
    venue?: PredictionMarketVenue
    crossVenueIntelligence?: PredictionMarketCrossVenueIntelligence | null
  },
): PredictionMarketExecutionPreflightSummary {
  const projectedPathReports = Object.values(projection.projected_paths)
  const canonicalProjectionPath = resolveCanonicalPredictionMarketProjectionPath(projection)
  const selectedEdgeBucket =
    projection.selected_edge_bucket
    ?? canonicalProjectionPath?.edge_bucket
    ?? null
  const selectedPreTradeGate =
    projection.selected_pre_trade_gate
    ?? canonicalProjectionPath?.pre_trade_gate
    ?? null
  const counts = {
    total: projectedPathReports.length,
    eligible: projection.eligible_paths.length,
    ready: projectedPathReports.filter((report) => report.status === 'ready').length,
    degraded: projectedPathReports.filter((report) => report.status === 'degraded').length,
    blocked: projectedPathReports.filter((report) => report.status === 'blocked').length,
  }
  const basisParts = [
    projection.basis.uses_execution_readiness ? 'readiness' : null,
    projection.basis.uses_compliance ? 'compliance' : null,
    projection.basis.uses_capital ? 'capital' : null,
    projection.basis.uses_reconciliation ? 'reconciliation' : null,
    projection.basis.uses_microstructure ? 'microstructure' : null,
  ].filter(Boolean)
  const sourceRefs = Object.values(projection.basis.source_refs).filter(
    (value): value is string => typeof value === 'string' && value.length > 0,
  )
  const summary: PredictionMarketExecutionPreflightSummary = {
    gate_name: projection.gate_name,
    preflight_only: projection.preflight_only,
    requested_path: projection.requested_path,
    selected_path: projection.selected_path,
    verdict: projection.verdict,
    highest_safe_requested_mode: projection.highest_safe_requested_mode,
    recommended_effective_mode: projection.recommended_effective_mode,
    manual_review_required: projection.manual_review_required,
    ttl_ms: projection.ttl_ms,
    expires_at: projection.expires_at,
    counts,
    basis: {
      uses_execution_readiness: projection.basis.uses_execution_readiness,
      uses_compliance: projection.basis.uses_compliance,
      uses_capital: projection.basis.uses_capital,
      uses_reconciliation: projection.basis.uses_reconciliation,
      uses_microstructure: projection.basis.uses_microstructure,
      capital_status: projection.basis.capital_status,
      reconciliation_status: projection.basis.reconciliation_status,
    },
    source_refs: sourceRefs,
    blockers: [...projection.blocking_reasons],
    downgrade_reasons: [...projection.downgrade_reasons],
    selected_edge_bucket: selectedEdgeBucket,
    selected_pre_trade_gate: selectedPreTradeGate,
    microstructure: projection.microstructure_summary,
    summary: [
      `gate=${projection.gate_name}`,
      `preflight=yes`,
      `verdict=${projection.verdict}`,
      `requested=${projection.requested_path}`,
      `selected=${projection.selected_path ?? 'none'}`,
      `highest_safe=${projection.highest_safe_requested_mode ?? 'none'}`,
      `recommended=${projection.recommended_effective_mode ?? 'none'}`,
      `manual_review=${projection.manual_review_required ? 'yes' : 'no'}`,
      `ttl_ms=${projection.ttl_ms}`,
      `eligible=${counts.eligible}/${counts.total}`,
      `paths=ready:${counts.ready}|degraded:${counts.degraded}|blocked:${counts.blocked}`,
      `basis=${basisParts.length > 0 ? basisParts.join(',') : 'none'}`,
      selectedEdgeBucket ? `edge_bucket=${selectedEdgeBucket}` : null,
      selectedPreTradeGate ? `pre_trade=${selectedPreTradeGate.verdict}:${selectedPreTradeGate.net_edge_bps}/${selectedPreTradeGate.minimum_net_edge_bps}bps` : null,
      projection.microstructure_summary
        ? `microstructure=${projection.microstructure_summary.recommended_mode}:${projection.microstructure_summary.worst_case_severity}:${projection.microstructure_summary.executable_deterioration_bps}bps`
        : null,
      `refs=${sourceRefs.length}`,
      `blockers=${projection.blocking_reasons.length}`,
      `downgrades=${projection.downgrade_reasons.length}`,
    ].filter((part): part is string => typeof part === 'string' && part.length > 0).join(' '),
  }

  if (!options?.venue) {
    return summary
  }

  const highestConfidenceCandidate = options.crossVenueIntelligence?.summary?.highest_confidence_candidate ??
    options.crossVenueIntelligence?.arbitrage_candidates[0] ??
    null
  const evaluationWithEdge = options.crossVenueIntelligence?.evaluations.find(
    (evaluation) => evaluation.executable_edge != null || evaluation.arbitrage_candidate != null,
  ) ?? null
  const crossVenueSurface = highestConfidenceCandidate
    ? {
      executable_edge: null,
      arbitrage_candidate: highestConfidenceCandidate,
    }
    : evaluationWithEdge
      ? {
        executable_edge: evaluationWithEdge.executable_edge,
        arbitrage_candidate: evaluationWithEdge.arbitrage_candidate,
      }
      : null

  return enrichPredictionMarketPreflightSummary(summary, {
    venue_strategy: getPredictionMarketVenueStrategy(options.venue),
    cross_venue: crossVenueSurface,
    microstructure_summary: projection.microstructure_summary,
  })
}

function derivePredictionMarketShadowArbitrage(
  executionProjection: PredictionMarketExecutionProjectionReport | null | undefined,
): ShadowArbitrageSimulationReport | null {
  return executionProjection?.projected_paths.shadow?.simulation.shadow_arbitrage ?? null
}

function resolveCanonicalPredictionMarketProjectionPath(
  executionProjection: Pick<
    PredictionMarketExecutionProjectionReport,
    'selected_path' | 'requested_path' | 'projected_paths'
  > | null | undefined,
) {
  if (!executionProjection) return null

  if (executionProjection.selected_path) {
    return executionProjection.projected_paths[executionProjection.selected_path] ?? null
  }

  return executionProjection.projected_paths[executionProjection.requested_path] ?? null
}

function resolvePredictionMarketProjectionPathByMode(
  executionProjection: Pick<
    PredictionMarketExecutionProjectionReport,
    'projected_paths'
  > | null | undefined,
  mode: PredictionMarketExecutionProjectionMode,
) {
  if (!executionProjection) return null
  return executionProjection.projected_paths[mode] ?? null
}

function resolveCanonicalPredictionMarketShadowArbitrage(input: {
  executionProjection?: PredictionMarketExecutionProjectionReport | null
  shadowArbitrage?: ShadowArbitrageSimulationReport | null
}): ShadowArbitrageSimulationReport | null {
  return derivePredictionMarketShadowArbitrage(input.executionProjection) ?? input.shadowArbitrage ?? null
}

function resolveCanonicalPredictionMarketSelectedPreview(
  executionProjection: PredictionMarketExecutionProjectionReport | null | undefined,
): {
  preview: TradeIntent | null
  source: 'canonical_trade_intent_preview' | 'trade_intent_preview' | null
} {
  const selectedProjectionPath = resolveCanonicalPredictionMarketProjectionPath(executionProjection)
  if (!selectedProjectionPath) {
    return {
      preview: null,
      source: null,
    }
  }

  if (selectedProjectionPath.canonical_trade_intent_preview) {
    return {
      preview: selectedProjectionPath.canonical_trade_intent_preview,
      source: 'canonical_trade_intent_preview',
    }
  }

  if (selectedProjectionPath.trade_intent_preview) {
    return {
      preview: capTradeIntentPreviewToCanonicalSize(
        selectedProjectionPath.trade_intent_preview,
        selectedProjectionPath.sizing_signal?.canonical_size_usd ?? null,
      ),
      source: 'trade_intent_preview',
    }
  }

  return {
    preview: null,
    source: null,
  }
}

function resolvePredictionMarketProjectionPreviewByMode(
  executionProjection: PredictionMarketExecutionProjectionReport | null | undefined,
  mode: PredictionMarketExecutionProjectionMode,
): {
  preview: TradeIntent | null
  source: 'canonical_trade_intent_preview' | 'trade_intent_preview' | null
} {
  const projectionPath = resolvePredictionMarketProjectionPathByMode(executionProjection, mode)
  if (!projectionPath) {
    return {
      preview: null,
      source: null,
    }
  }

  if (projectionPath.canonical_trade_intent_preview) {
    return {
      preview: projectionPath.canonical_trade_intent_preview,
      source: 'canonical_trade_intent_preview',
    }
  }

  if (projectionPath.trade_intent_preview) {
    return {
      preview: capTradeIntentPreviewToCanonicalSize(
        projectionPath.trade_intent_preview,
        projectionPath.sizing_signal?.canonical_size_usd ?? null,
      ),
      source: 'trade_intent_preview',
    }
  }

  return {
    preview: null,
    source: null,
  }
}

function resolvePredictionMarketExecutionSurfacePreview(input: {
  executionProjection?: PredictionMarketExecutionProjectionReport | null
  executionPathways?: PredictionMarketExecutionPathwaysReport | null
}): {
  preview: TradeIntent | null
  raw_preview: TradeIntent | null
  source: 'execution_projection_selected_preview' | 'execution_pathways:selected_path' | 'execution_pathways:first_available' | 'none'
  preview_source: 'canonical_trade_intent_preview' | 'trade_intent_preview' | 'none'
  projection_selected_preview_source: 'canonical_trade_intent_preview' | 'trade_intent_preview' | null
  uses_projection_selected_preview: boolean
  selected_projection_path: ReturnType<typeof resolveCanonicalPredictionMarketProjectionPath>
} {
  const selectedProjectionPath = resolveCanonicalPredictionMarketProjectionPath(input.executionProjection)
  const selectedProjectionPreview = resolveCanonicalPredictionMarketSelectedPreview(input.executionProjection)

  if (selectedProjectionPreview.preview) {
    return {
      preview: selectedProjectionPreview.preview,
      raw_preview:
        selectedProjectionPath?.canonical_trade_intent_preview
        ?? selectedProjectionPath?.trade_intent_preview
        ?? selectedProjectionPreview.preview,
      source: 'execution_projection_selected_preview',
      preview_source: selectedProjectionPreview.source ?? 'none',
      projection_selected_preview_source: selectedProjectionPreview.source,
      uses_projection_selected_preview: true,
      selected_projection_path: selectedProjectionPath,
    }
  }

  return {
    preview: null,
    raw_preview: null,
    source: 'none',
    preview_source: 'none',
    projection_selected_preview_source: null,
    uses_projection_selected_preview: false,
    selected_projection_path: selectedProjectionPath,
  }
}

function buildPredictionMarketRunRuntimeHints(input: {
  requestContract?: PredictionMarketAdviceRequestContract | null
  researchSidecar?: MarketResearchSidecar | null
  timesfmSidecar?: PredictionMarketTimesFMSidecar | null
  forecast?: ForecastPacket | null
  recommendation?: MarketRecommendationPacket | null
  venueFeedSurface?: MarketFeedSurface | null
  executionPathways?: PredictionMarketExecutionPathwaysReport | null
  executionProjection?: PredictionMarketExecutionProjectionReport | null
  shadowArbitrage?: ShadowArbitrageSimulationReport | null
  multiVenueExecution?: MultiVenueExecution | null
  strategyCandidate?: StrategyCandidatePacket | null
  strategyDecision?: StrategyDecisionPacket | null
  executionIntentPreview?: ExecutionIntentPreview | null
  resolutionAnomalyReport?: ResolutionAnomalyReport | null
  strategyShadowSummary?: StrategyShadowSummary | null
  sourceAudit?: PredictionMarketJsonArtifact | null
  worldState?: PredictionMarketJsonArtifact | null
  ticketPayload?: PredictionMarketJsonArtifact | null
  quantSignalBundle?: PredictionMarketJsonArtifact | null
  decisionLedger?: PredictionMarketJsonArtifact | null
  calibrationReport?: PredictionMarketJsonArtifact | null
  resolvedHistory?: PredictionMarketJsonArtifact | null
  costModelReport?: PredictionMarketJsonArtifact | null
  walkForwardReport?: PredictionMarketJsonArtifact | null
  autopilotCycleSummary?: PredictionMarketJsonArtifact | null
  researchMemorySummary?: PredictionMarketJsonArtifact | null
  benchmarkGateOverride?: Partial<Pick<
    PredictionMarketRunRuntimeHints,
    | 'research_benchmark_gate_summary'
    | 'research_benchmark_uplift_bps'
    | 'research_benchmark_verdict'
    | 'research_benchmark_gate_status'
    | 'research_benchmark_promotion_status'
    | 'research_benchmark_promotion_ready'
    | 'research_benchmark_preview_available'
    | 'research_benchmark_promotion_evidence'
    | 'research_benchmark_evidence_level'
    | 'research_promotion_gate_kind'
    | 'research_benchmark_promotion_blocker_summary'
    | 'research_benchmark_promotion_summary'
    | 'research_benchmark_gate_blockers'
    | 'research_benchmark_gate_reasons'
    | 'benchmark_gate_summary'
    | 'benchmark_uplift_bps'
    | 'benchmark_verdict'
  | 'benchmark_gate_status'
  | 'benchmark_promotion_status'
  | 'benchmark_promotion_ready'
  | 'benchmark_gate_blocks_live'
  | 'benchmark_preview_available'
  | 'benchmark_promotion_evidence'
  | 'benchmark_evidence_level'
  | 'benchmark_promotion_gate_kind'
  | 'benchmark_promotion_blocker_summary'
  | 'benchmark_promotion_summary'
  | 'benchmark_gate_live_block_reason'
  | 'benchmark_gate_blockers'
  | 'benchmark_gate_reasons'
  | 'benchmark_gate_summary'
  | 'benchmark_uplift_bps'
  | 'benchmark_verdict'
  | 'benchmark_gate_status'
  | 'benchmark_promotion_status'
  | 'benchmark_promotion_ready'
  | 'benchmark_preview_available'
  | 'benchmark_promotion_evidence'
  | 'benchmark_evidence_level'
  >> | null
}): PredictionMarketRunRuntimeHints {
  const selectedProjectionPath = resolveCanonicalPredictionMarketProjectionPath(input.executionProjection)
  const selectedPreTradeGate =
    selectedProjectionPath?.pre_trade_gate
    ?? input.executionProjection?.selected_pre_trade_gate
    ?? null
  const selectedEdgeBucket =
    selectedProjectionPath?.edge_bucket
    ?? input.executionProjection?.selected_edge_bucket
    ?? null
  const selectedPreview = resolvePredictionMarketExecutionSurfacePreview({
    executionProjection: input.executionProjection,
    executionPathways: input.executionPathways,
  })
  const canonicalShadowArbitrage = resolveCanonicalPredictionMarketShadowArbitrage({
    executionProjection: input.executionProjection,
    shadowArbitrage: input.shadowArbitrage,
  })
  const researchSynthesis = input.researchSidecar?.synthesis ?? null
  const researchPipeline = input.researchSidecar?.pipeline_version_metadata ?? null
  const researchComparative = researchSynthesis?.comparative_report ?? null
  const researchWeightedAggregate = researchSynthesis?.weighted_aggregate_preview ?? null
  const researchAbstentionPolicy = researchSynthesis?.abstention_policy ?? null
  const baseResearchBenchmarkGate = summarizePredictionMarketsBenchmarkGate({
    comparativeReport: researchComparative,
    forecastProbabilityYesHint: researchSynthesis?.forecast_probability_yes_hint ?? null,
  })
  const resolvedResearchBenchmarkStatus =
    input.benchmarkGateOverride?.research_benchmark_gate_status
    ?? baseResearchBenchmarkGate.status
  const resolvedResearchBenchmarkPromotionStatus =
    input.benchmarkGateOverride?.research_benchmark_promotion_status
    ?? baseResearchBenchmarkGate.promotion_status
  const resolvedResearchBenchmarkPromotionReady =
    input.benchmarkGateOverride?.research_benchmark_promotion_ready
    ?? baseResearchBenchmarkGate.promotion_ready
  const resolvedResearchBenchmarkPreviewAvailable =
    input.benchmarkGateOverride?.research_benchmark_preview_available
    ?? baseResearchBenchmarkGate.preview_available
  const resolvedResearchBenchmarkPromotionEvidence =
    input.benchmarkGateOverride?.research_benchmark_promotion_evidence
    ?? baseResearchBenchmarkGate.promotion_evidence
  const resolvedResearchBenchmarkEvidenceLevel =
    input.benchmarkGateOverride?.research_benchmark_evidence_level
    ?? baseResearchBenchmarkGate.evidence_level
  const resolvedResearchPromotionGateKind =
    input.benchmarkGateOverride?.research_promotion_gate_kind
    ?? baseResearchBenchmarkGate.promotion_gate_kind
  const resolvedResearchBenchmarkBlockers =
    input.benchmarkGateOverride?.research_benchmark_gate_blockers
    ?? baseResearchBenchmarkGate.blockers
  const resolvedResearchBenchmarkReasons =
    input.benchmarkGateOverride?.research_benchmark_gate_reasons
    ?? baseResearchBenchmarkGate.reasons
  const resolvedResearchBenchmarkVerdict =
    input.benchmarkGateOverride?.research_benchmark_verdict
    ?? (
      resolvedResearchBenchmarkStatus === 'blocked_by_abstention'
        ? 'blocked_by_abstention'
        : resolvedResearchBenchmarkPromotionReady
          ? 'local_benchmark_ready'
          : resolvedResearchBenchmarkPromotionStatus === 'blocked'
            ? 'local_benchmark_blocked'
            : 'preview_only'
    )
  const resolvedResearchBenchmarkPromotionBlockerSummary =
    input.benchmarkGateOverride?.research_benchmark_promotion_blocker_summary
    ?? (
      resolvedResearchBenchmarkBlockers.length > 0
        ? resolvedResearchBenchmarkBlockers.join('; ')
        : resolvedResearchBenchmarkPromotionReady
          ? 'promotion gate satisfied'
          : 'out_of_sample_unproven'
    )
  const resolvedResearchBenchmarkPromotionSummary =
    input.benchmarkGateOverride?.research_benchmark_promotion_summary
    ?? resolvedResearchBenchmarkPromotionBlockerSummary
  const researchBenchmarkGate: PredictionMarketsBenchmarkGateSummary = {
    verdict: resolvedResearchBenchmarkVerdict,
    status: resolvedResearchBenchmarkStatus,
    promotion_status: resolvedResearchBenchmarkPromotionStatus,
    promotion_ready: resolvedResearchBenchmarkPromotionReady,
    preview_available: resolvedResearchBenchmarkPreviewAvailable,
    promotion_evidence: resolvedResearchBenchmarkPromotionEvidence,
    evidence_level: resolvedResearchBenchmarkEvidenceLevel,
    promotion_gate_kind: resolvedResearchPromotionGateKind,
    market_only_probability: baseResearchBenchmarkGate.market_only_probability,
    aggregate_probability: baseResearchBenchmarkGate.aggregate_probability,
    forecast_probability: baseResearchBenchmarkGate.forecast_probability,
    promotion_blocker_summary: resolvedResearchBenchmarkPromotionBlockerSummary,
    upliftBps: input.benchmarkGateOverride?.research_benchmark_uplift_bps ?? baseResearchBenchmarkGate.upliftBps,
    forecast_uplift_bps: input.benchmarkGateOverride?.research_benchmark_uplift_bps ?? baseResearchBenchmarkGate.forecast_uplift_bps,
    aggregate_uplift_bps: baseResearchBenchmarkGate.aggregate_uplift_bps,
    blockers: resolvedResearchBenchmarkBlockers,
    reasons: resolvedResearchBenchmarkReasons,
    summary: input.benchmarkGateOverride?.research_benchmark_gate_summary ?? baseResearchBenchmarkGate.summary,
  }
  const resolvedBenchmarkGateSummary =
    input.benchmarkGateOverride?.benchmark_gate_summary
    ?? researchBenchmarkGate.summary
  const resolvedBenchmarkUpliftBps =
    input.benchmarkGateOverride?.benchmark_uplift_bps
    ?? researchBenchmarkGate.upliftBps
  const resolvedBenchmarkVerdict =
    input.benchmarkGateOverride?.benchmark_verdict
    ?? researchBenchmarkGate.verdict
  const resolvedBenchmarkGateStatus =
    input.benchmarkGateOverride?.benchmark_gate_status
    ?? researchBenchmarkGate.status
  const resolvedBenchmarkPromotionStatus =
    input.benchmarkGateOverride?.benchmark_promotion_status
    ?? researchBenchmarkGate.promotion_status
  const resolvedBenchmarkPromotionReady =
    input.benchmarkGateOverride?.benchmark_promotion_ready
    ?? researchBenchmarkGate.promotion_ready
  const resolvedBenchmarkPreviewAvailable =
    input.benchmarkGateOverride?.benchmark_preview_available
    ?? researchBenchmarkGate.preview_available
  const resolvedBenchmarkPromotionEvidence =
    input.benchmarkGateOverride?.benchmark_promotion_evidence
    ?? researchBenchmarkGate.promotion_evidence
  const resolvedBenchmarkEvidenceLevel =
    input.benchmarkGateOverride?.benchmark_evidence_level
    ?? researchBenchmarkGate.evidence_level
  const resolvedBenchmarkPromotionGateKind =
    input.benchmarkGateOverride?.benchmark_promotion_gate_kind
    ?? researchBenchmarkGate.promotion_gate_kind
  const resolvedBenchmarkPromotionBlockerSummary =
    input.benchmarkGateOverride?.benchmark_promotion_blocker_summary
    ?? researchBenchmarkGate.promotion_blocker_summary
  const resolvedBenchmarkPromotionSummary =
    input.benchmarkGateOverride?.benchmark_promotion_summary
    ?? resolvedBenchmarkPromotionBlockerSummary
  const resolvedBenchmarkGateBlockers =
    input.benchmarkGateOverride?.benchmark_gate_blockers
    ?? researchBenchmarkGate.blockers
  const resolvedBenchmarkGateReasons =
    input.benchmarkGateOverride?.benchmark_gate_reasons
    ?? researchBenchmarkGate.reasons
  const researchRuntimeSummary = summarizePredictionMarketResearchRuntimeHints({
    pipelineId: researchPipeline?.pipeline_id ?? null,
    pipelineVersion: researchPipeline?.pipeline_version ?? null,
    forecasterCount:
      researchSynthesis?.independent_forecaster_outputs?.length
      ?? researchSynthesis?.forecaster_candidates?.length
      ?? null,
    weightedProbabilityYes:
      researchWeightedAggregate?.weighted_probability_yes
      ?? researchWeightedAggregate?.weighted_probability_yes_raw
      ?? null,
    weightedCoverage: researchWeightedAggregate?.coverage ?? null,
    preferredMode: researchComparative?.abstention.blocks_forecast
      ? 'abstention'
      : researchComparative?.aggregate.probability_yes != null &&
          researchComparative.aggregate.coverage > 0 &&
          (researchComparative.aggregate.delta_bps_vs_market_only == null
            ? false
            : Math.abs(researchComparative.aggregate.delta_bps_vs_market_only) > 0)
        ? 'aggregate'
        : researchComparative != null
          ? 'market_only'
          : null,
    abstentionVersion: researchAbstentionPolicy?.policy_version ?? null,
    abstentionBlocksForecast: researchAbstentionPolicy?.blocks_forecast ?? null,
    forecastProbabilityYesHint: researchSynthesis?.forecast_probability_yes_hint ?? null,
  })
  const benchmarkLiveGate = resolvePredictionMarketBenchmarkLiveGateState({
    execution_projection: input.executionProjection,
    benchmark_promotion_ready: resolvedBenchmarkPromotionReady,
    benchmark_promotion_blocker_summary: resolvedBenchmarkPromotionBlockerSummary,
    benchmark_promotion_gate_kind: resolvedBenchmarkPromotionGateKind,
    benchmark_gate_blocks_live: input.benchmarkGateOverride?.benchmark_gate_blocks_live,
    benchmark_gate_live_block_reason: input.benchmarkGateOverride?.benchmark_gate_live_block_reason,
  })
  const benchmarkGateBlocksLive = benchmarkLiveGate.blocks_live
  const benchmarkGateLiveBlockReason = benchmarkLiveGate.live_block_reason
  const timesfmSidecar = input.timesfmSidecar ?? null
  const timesfmSummary = summarizePredictionMarketTimesFMSidecar(timesfmSidecar) ?? timesfmSidecar?.summary ?? null

  const runtimeHints: PredictionMarketRunRuntimeHints = {}
  if (input.requestContract?.request_mode != null) {
    runtimeHints.request_mode = input.requestContract.request_mode
  }
  if (input.requestContract?.response_variant != null) {
    runtimeHints.response_variant = input.requestContract.response_variant
  }
  if (input.requestContract?.variant_tags != null) {
    runtimeHints.request_variant_tags = input.requestContract.variant_tags
  }
  const timesfmRequestedMode =
    timesfmSidecar?.requested_mode
    ?? input.requestContract?.timesfm_mode
    ?? null
  if (timesfmRequestedMode != null) {
    runtimeHints.timesfm_requested_mode = timesfmRequestedMode
  }
  const timesfmEffectiveMode =
    timesfmSidecar?.effective_mode
    ?? (timesfmRequestedMode === 'off' ? 'off' : null)
  if (timesfmEffectiveMode != null) {
    runtimeHints.timesfm_effective_mode = timesfmEffectiveMode
  }
  const timesfmRequestedLanes =
    timesfmSidecar?.requested_lanes
    ?? input.requestContract?.timesfm_lanes
    ?? []
  if (timesfmRequestedLanes.length > 0) {
    runtimeHints.timesfm_requested_lanes = timesfmRequestedLanes
  }
  if (timesfmSidecar?.selected_lane != null) {
    runtimeHints.timesfm_selected_lane = timesfmSidecar.selected_lane
  }
  if (timesfmSidecar?.health?.status != null) {
    runtimeHints.timesfm_health = timesfmSidecar.health.status
  }
  if (timesfmSummary != null) {
    runtimeHints.timesfm_summary = timesfmSummary
  }

  if (researchPipeline?.pipeline_id != null) {
    runtimeHints.research_pipeline_id = researchPipeline.pipeline_id
  }
  if (researchPipeline?.pipeline_version != null) {
    runtimeHints.research_pipeline_version = researchPipeline.pipeline_version
  }
  const forecasterCount =
    researchSynthesis?.independent_forecaster_outputs?.length
    ?? researchSynthesis?.forecaster_candidates?.length
    ?? null
  if (forecasterCount != null) {
    runtimeHints.research_forecaster_count = forecasterCount
  }
  const weightedProbabilityYes =
    researchWeightedAggregate?.weighted_probability_yes
    ?? researchWeightedAggregate?.weighted_probability_yes_raw
    ?? null
  if (weightedProbabilityYes != null) {
    runtimeHints.research_weighted_probability_yes = weightedProbabilityYes
  }
  if (researchWeightedAggregate?.coverage != null) {
    runtimeHints.research_weighted_coverage = researchWeightedAggregate.coverage
  }
  const comparePreferredMode = researchComparative?.abstention.blocks_forecast
    ? 'abstention'
    : researchComparative?.aggregate.probability_yes != null &&
        researchComparative.aggregate.coverage > 0 &&
        (researchComparative.aggregate.delta_bps_vs_market_only == null
          ? false
          : Math.abs(researchComparative.aggregate.delta_bps_vs_market_only) > 0)
      ? 'aggregate'
      : researchComparative != null
        ? 'market_only'
        : null
  const researchRuntimeMode: 'market_only' | 'research_driven' | null = comparePreferredMode == null
    ? null
    : comparePreferredMode === 'market_only'
      ? 'market_only'
      : 'research_driven'
  if (comparePreferredMode != null) {
    runtimeHints.research_compare_preferred_mode = comparePreferredMode
  }
  if (researchComparative?.summary != null) {
    runtimeHints.research_compare_summary = researchComparative.summary
  }
  if (researchAbstentionPolicy?.policy_version != null) {
    runtimeHints.research_abstention_policy_version = researchAbstentionPolicy.policy_version
  }
  if (researchAbstentionPolicy?.blocks_forecast != null) {
    runtimeHints.research_abstention_policy_blocks_forecast = researchAbstentionPolicy.blocks_forecast
  }
  if (researchSynthesis?.forecast_probability_yes_hint != null) {
    runtimeHints.research_forecast_probability_yes_hint = researchSynthesis.forecast_probability_yes_hint
  }
  if (researchRuntimeSummary != null) {
    runtimeHints.research_runtime_summary = researchRuntimeSummary
  }
  if (researchRuntimeMode != null) {
    runtimeHints.research_runtime_mode = researchRuntimeMode
  }
  if (input.venueFeedSurface?.summary != null) {
    runtimeHints.venue_feed_surface_summary = input.venueFeedSurface.summary
  }
  const venuePathwaySummary =
    input.executionProjection?.selected_path === 'live' && resolvedBenchmarkPromotionReady === true
      ? input.executionProjection.summary ?? input.executionPathways?.summary ?? null
      : input.executionPathways?.summary ?? null
  if (venuePathwaySummary != null) {
    runtimeHints.venue_pathway_summary = venuePathwaySummary
  }
  if (input.executionPathways?.highest_actionable_mode != null) {
    runtimeHints.venue_pathway_highest_actionable_mode = input.executionPathways.highest_actionable_mode
  }
  const strategyDecision = input.strategyDecision ?? null
  const strategyCandidate = input.strategyCandidate ?? null
  const strategyMetadata = asRecord(strategyDecision?.metadata) ?? asRecord(strategyCandidate?.metadata)
  const strategyCounts = normalizePredictionMarketStrategyCounts(strategyMetadata?.strategy_counts)
  const strategyPrimary =
    strategyDecision?.strategy_family
    ?? strategyCandidate?.strategy_family
    ?? null
  const strategyMarketRegime =
    strategyDecision?.market_regime
    ?? strategyCandidate?.market_regime
    ?? null
  const executionIntentPreview =
    input.executionIntentPreview
    ?? strategyDecision?.execution_intent_preview
    ?? strategyCandidate?.execution_intent_preview
    ?? null
  const resolutionAnomalyReport =
    input.resolutionAnomalyReport
    ?? strategyDecision?.resolution_anomaly_report
    ?? strategyCandidate?.resolution_anomaly_report
    ?? null
  const strategyShadowSummary =
    input.strategyShadowSummary?.summary
    ?? strategyDecision?.shadow_report?.summary
    ?? strategyCandidate?.shadow_summary?.summary
    ?? null
  const approvalTicket = input.executionPathways?.approval_ticket ?? null
  const operatorThesis = input.executionPathways?.operator_thesis ?? null
  const researchPipelineTrace = input.executionPathways?.research_pipeline_trace ?? null
  if (strategyPrimary != null) {
    runtimeHints.primary_strategy = strategyPrimary
    runtimeHints.strategy_primary = strategyPrimary
  }
  const primaryStrategySummary =
    strategyDecision?.summary
    ?? strategyCandidate?.summary
    ?? null
  if (primaryStrategySummary != null) {
    runtimeHints.primary_strategy_summary = primaryStrategySummary
  }
  if (strategyMarketRegime?.label != null) {
    runtimeHints.market_regime = strategyMarketRegime.label
    runtimeHints.strategy_market_regime = strategyMarketRegime.label
  }
  if (strategyCounts != null) {
    runtimeHints.strategy_counts = strategyCounts
    runtimeHints.strategy_candidate_count = strategyCounts.total
  }
  if (executionIntentPreview?.preview_kind != null) {
    runtimeHints.execution_intent_preview_kind = executionIntentPreview.preview_kind
    runtimeHints.execution_intent_preview_source = strategyDecision
      ? 'strategy_decision_packet'
      : 'strategy_candidate_packet'
  }
  if (approvalTicket?.ticket_id != null) {
    runtimeHints.approval_ticket_id = approvalTicket.ticket_id
  }
  if (approvalTicket?.required != null) {
    runtimeHints.approval_ticket_required = approvalTicket.required
  }
  if (approvalTicket?.status != null) {
    runtimeHints.approval_ticket_status = approvalTicket.status
  }
  if (approvalTicket?.summary != null) {
    runtimeHints.approval_ticket_summary = approvalTicket.summary
  }
  if (approvalTicket != null) {
    runtimeHints.approval_ticket = approvalTicket
  }
  if (operatorThesis?.present != null) {
    runtimeHints.operator_thesis_present = operatorThesis.present
  }
  if (operatorThesis?.source != null) {
    runtimeHints.operator_thesis_source = operatorThesis.source
  }
  if (operatorThesis?.probability_yes != null) {
    runtimeHints.operator_thesis_probability_yes = operatorThesis.probability_yes
  }
  if (operatorThesis?.summary != null) {
    runtimeHints.operator_thesis_summary = operatorThesis.summary
  }
  if (operatorThesis != null) {
    runtimeHints.operator_thesis = operatorThesis
  }
  if (researchPipelineTrace?.summary != null) {
    runtimeHints.research_pipeline_trace_summary = researchPipelineTrace.summary
  }
  if (researchPipelineTrace?.preferred_mode != null) {
    runtimeHints.research_pipeline_trace_preferred_mode = researchPipelineTrace.preferred_mode
  }
  if (researchPipelineTrace?.oracle_family != null) {
    runtimeHints.research_pipeline_trace_oracle_family = researchPipelineTrace.oracle_family
  }
  if (researchPipelineTrace?.forecaster_count != null) {
    runtimeHints.research_pipeline_trace_forecaster_count = researchPipelineTrace.forecaster_count
  }
  if (researchPipelineTrace?.evidence_count != null) {
    runtimeHints.research_pipeline_trace_evidence_count = researchPipelineTrace.evidence_count
  }
  if (researchPipelineTrace != null) {
    runtimeHints.research_pipeline_trace = researchPipelineTrace
  }
  if (strategyShadowSummary != null) {
    runtimeHints.strategy_shadow_summary = strategyShadowSummary
  }
  const resolutionAnomalies = uniqueStrings([
    resolutionAnomalyReport?.summary ?? null,
    ...(resolutionAnomalyReport?.notes ?? []),
  ])
  if (resolutionAnomalies.length > 0) {
    runtimeHints.resolution_anomalies = resolutionAnomalies
  }
  const makerSpreadCaptureMetadata =
    asRecord(executionIntentPreview?.metadata) ??
    strategyMetadata
  const makerSpreadCaptureInventorySummary = asString(makerSpreadCaptureMetadata?.maker_spread_capture_inventory_summary)
  const makerSpreadCaptureAdverseSelectionSummary = asString(makerSpreadCaptureMetadata?.maker_spread_capture_adverse_selection_summary)
  const makerSpreadCaptureQuoteTransportSummary = asString(makerSpreadCaptureMetadata?.maker_spread_capture_quote_transport_summary)
  const makerSpreadCaptureBlockers = asStringArray(makerSpreadCaptureMetadata?.maker_spread_capture_blockers)
  const makerSpreadCaptureRiskCaps = asStringArray(makerSpreadCaptureMetadata?.maker_spread_capture_risk_caps)
  if (makerSpreadCaptureInventorySummary != null) {
    runtimeHints.maker_spread_capture_inventory_summary = makerSpreadCaptureInventorySummary
  }
  if (makerSpreadCaptureAdverseSelectionSummary != null) {
    runtimeHints.maker_spread_capture_adverse_selection_summary = makerSpreadCaptureAdverseSelectionSummary
  }
  if (makerSpreadCaptureQuoteTransportSummary != null) {
    runtimeHints.maker_spread_capture_quote_transport_summary = makerSpreadCaptureQuoteTransportSummary
  }
  runtimeHints.maker_spread_capture_blockers = makerSpreadCaptureBlockers
  runtimeHints.maker_spread_capture_risk_caps = makerSpreadCaptureRiskCaps
  if (researchBenchmarkGate.summary != null) runtimeHints.research_benchmark_gate_summary = researchBenchmarkGate.summary
  if (researchBenchmarkGate.upliftBps != null) runtimeHints.research_benchmark_uplift_bps = researchBenchmarkGate.upliftBps
  if (researchBenchmarkGate.verdict != null) runtimeHints.research_benchmark_verdict = researchBenchmarkGate.verdict
  runtimeHints.research_benchmark_gate_status = researchBenchmarkGate.status
  runtimeHints.research_benchmark_promotion_status = researchBenchmarkGate.promotion_status
  runtimeHints.research_benchmark_promotion_ready = researchBenchmarkGate.promotion_ready
  runtimeHints.research_benchmark_preview_available = researchBenchmarkGate.preview_available
  runtimeHints.research_benchmark_promotion_evidence = researchBenchmarkGate.promotion_evidence
  runtimeHints.research_benchmark_evidence_level = researchBenchmarkGate.evidence_level
  runtimeHints.research_promotion_gate_kind = researchBenchmarkGate.promotion_gate_kind
  if (researchBenchmarkGate.promotion_blocker_summary != null) {
    runtimeHints.research_benchmark_promotion_blocker_summary = researchBenchmarkGate.promotion_blocker_summary
  }
  runtimeHints.research_benchmark_promotion_summary = resolvedResearchBenchmarkPromotionSummary
  runtimeHints.research_benchmark_gate_blocks_live = benchmarkGateBlocksLive
  runtimeHints.research_benchmark_live_block_reason = benchmarkGateLiveBlockReason ?? null
  runtimeHints.research_benchmark_gate_blockers = researchBenchmarkGate.blockers
  runtimeHints.research_benchmark_gate_reasons = researchBenchmarkGate.reasons
  runtimeHints.benchmark_verdict = resolvedBenchmarkVerdict
  runtimeHints.benchmark_gate_summary = resolvedBenchmarkGateSummary
  runtimeHints.benchmark_uplift_bps = resolvedBenchmarkUpliftBps
  runtimeHints.benchmark_gate_status = resolvedBenchmarkGateStatus
  runtimeHints.benchmark_promotion_status = resolvedBenchmarkPromotionStatus
  runtimeHints.benchmark_promotion_ready = resolvedBenchmarkPromotionReady
  runtimeHints.benchmark_preview_available = resolvedBenchmarkPreviewAvailable
  runtimeHints.benchmark_promotion_evidence = resolvedBenchmarkPromotionEvidence
  runtimeHints.benchmark_evidence_level = resolvedBenchmarkEvidenceLevel
  runtimeHints.benchmark_promotion_gate_kind = resolvedBenchmarkPromotionGateKind
  if (resolvedBenchmarkPromotionBlockerSummary != null) {
    runtimeHints.benchmark_promotion_blocker_summary = resolvedBenchmarkPromotionBlockerSummary
  }
  runtimeHints.benchmark_promotion_summary = resolvedBenchmarkPromotionSummary
  runtimeHints.benchmark_gate_blocks_live = benchmarkGateBlocksLive
  runtimeHints.benchmark_gate_live_block_reason = benchmarkGateLiveBlockReason ?? null
  runtimeHints.benchmark_gate_blockers = resolvedBenchmarkGateBlockers
  runtimeHints.benchmark_gate_reasons = resolvedBenchmarkGateReasons

  const recommendationOrigin = resolvePredictionMarketRecommendationOrigin({
    forecast: input.forecast,
    recommendation: input.recommendation,
    preferredMode: comparePreferredMode,
    blocksForecast:
      researchAbstentionPolicy?.blocks_forecast
      ?? researchComparative?.abstention.blocks_forecast
      ?? false,
  })
  if (recommendationOrigin != null) {
    runtimeHints.research_recommendation_origin = recommendationOrigin.origin
    runtimeHints.research_recommendation_origin_summary = recommendationOrigin.summary
    runtimeHints.research_abstention_flipped_recommendation = recommendationOrigin.abstention_flipped_recommendation
  }

  const sourceAudit = asRecord(input.sourceAudit)
  if (typeof sourceAudit?.average_score === 'number') {
    runtimeHints.source_audit_average_score = sourceAudit.average_score
  }
  if (typeof sourceAudit?.coverage_score === 'number') {
    runtimeHints.source_audit_coverage_score = sourceAudit.coverage_score
  }
  if (typeof sourceAudit?.summary === 'string') {
    runtimeHints.source_audit_summary = sourceAudit.summary
  }
  const worldState = asRecord(input.worldState)
  if (
    worldState?.recommended_action === 'bet'
    || worldState?.recommended_action === 'wait'
    || worldState?.recommended_action === 'no_trade'
  ) {
    runtimeHints.world_state_recommended_action = worldState.recommended_action
  }
  if (worldState?.recommended_side === 'yes' || worldState?.recommended_side === 'no') {
    runtimeHints.world_state_recommended_side = worldState.recommended_side
  }
  if (typeof worldState?.confidence_score === 'number') {
    runtimeHints.world_state_confidence_score = worldState.confidence_score
  }
  if (typeof worldState?.summary === 'string') {
    runtimeHints.world_state_summary = worldState.summary
  }
  const worldStateRiskFlags = asStringArray(worldState?.risk_flags)
  if (worldStateRiskFlags.length > 0) {
    runtimeHints.world_state_risk_flags = worldStateRiskFlags
  }
  const ticketPayload = asRecord(input.ticketPayload)
  if (typeof ticketPayload?.action === 'string') {
    runtimeHints.ticket_payload_action = ticketPayload.action
  }
  if (typeof ticketPayload?.size_usd === 'number') {
    runtimeHints.ticket_payload_size_usd = ticketPayload.size_usd
  }
  if (typeof ticketPayload?.summary === 'string') {
    runtimeHints.ticket_payload_summary = ticketPayload.summary
  }
  const quantSignalBundle = asRecord(input.quantSignalBundle)
  if (typeof quantSignalBundle?.summary === 'string') {
    runtimeHints.quant_signal_summary = quantSignalBundle.summary
  }
  if (typeof quantSignalBundle?.viable_count === 'number') {
    runtimeHints.quant_signal_viable_count = quantSignalBundle.viable_count
  }
  const decisionLedger = asRecord(input.decisionLedger)
  const ledgerSummary = asRecord(decisionLedger?.summary)
  if (typeof ledgerSummary?.total_entries === 'number') {
    runtimeHints.decision_ledger_total_entries = ledgerSummary.total_entries
  }
  const latestLedgerEntry = asRecord(ledgerSummary?.latest_entry)
  if (typeof latestLedgerEntry?.entry_type === 'string') {
    runtimeHints.decision_ledger_latest_entry_type = latestLedgerEntry.entry_type
  }
  const calibrationReport = asRecord(input.calibrationReport)
  if (typeof calibrationReport?.calibration_error === 'number') {
    runtimeHints.calibration_error = calibrationReport.calibration_error
  }
  if (typeof calibrationReport?.brier_score === 'number') {
    runtimeHints.calibration_brier_score = calibrationReport.brier_score
  }
  const resolvedHistory = asRecord(input.resolvedHistory)
  if (typeof resolvedHistory?.summary === 'string') {
    runtimeHints.resolved_history_summary = resolvedHistory.summary
  }
  if (typeof resolvedHistory?.resolved_records === 'number') {
    runtimeHints.resolved_history_points = resolvedHistory.resolved_records
  }
  if (typeof resolvedHistory?.source_summary === 'string') {
    runtimeHints.resolved_history_source_summary = resolvedHistory.source_summary
  }
  if (typeof resolvedHistory?.first_cutoff_at === 'string') {
    runtimeHints.resolved_history_first_cutoff_at = resolvedHistory.first_cutoff_at
  }
  if (typeof resolvedHistory?.last_cutoff_at === 'string') {
    runtimeHints.resolved_history_last_cutoff_at = resolvedHistory.last_cutoff_at
  }
  const costModelReport = asRecord(input.costModelReport)
  if (typeof costModelReport?.summary === 'string') {
    runtimeHints.cost_model_summary = costModelReport.summary
  }
  if (typeof costModelReport?.total_points === 'number') {
    runtimeHints.cost_model_total_points = costModelReport.total_points
  }
  if (typeof costModelReport?.viable_point_count === 'number') {
    runtimeHints.cost_model_viable_point_count = costModelReport.viable_point_count
  }
  if (typeof costModelReport?.viable_point_rate === 'number') {
    runtimeHints.cost_model_viable_point_rate = costModelReport.viable_point_rate
  }
  if (typeof costModelReport?.average_cost_bps === 'number') {
    runtimeHints.cost_model_average_cost_bps = costModelReport.average_cost_bps
  }
  if (typeof costModelReport?.average_net_edge_bps === 'number') {
    runtimeHints.cost_model_average_net_edge_bps = costModelReport.average_net_edge_bps
  }
  const walkForwardReport = asRecord(input.walkForwardReport)
  const walkForwardSummary: PredictionMarketWalkForwardSurfaceSummary | null = walkForwardReport
    ? {
      summary: asString(walkForwardReport.summary),
      sample_count: asNumber(walkForwardReport.total_points),
      window_count: asNumber(walkForwardReport.total_windows),
      win_rate: asNumber(walkForwardReport.stable_window_rate),
      brier_score: asNumber(walkForwardReport.mean_calibrated_brier_score),
      log_loss: asNumber(walkForwardReport.mean_calibrated_log_loss),
      uplift_bps: asNumber(walkForwardReport.mean_net_edge_bps),
      promotion_ready: walkForwardReport.promotion_ready === true,
      notes: asStringArray(walkForwardReport.notes),
    }
    : null
  if (walkForwardSummary && (
    walkForwardSummary.summary != null ||
    walkForwardSummary.sample_count != null ||
    walkForwardSummary.window_count != null ||
    walkForwardSummary.win_rate != null ||
    walkForwardSummary.brier_score != null ||
    walkForwardSummary.log_loss != null ||
    walkForwardSummary.uplift_bps != null ||
    walkForwardSummary.notes.length > 0
  )) {
    runtimeHints.walk_forward_summary = walkForwardSummary
  }
  if (typeof walkForwardReport?.total_points === 'number') {
    runtimeHints.walk_forward_total_points = walkForwardReport.total_points
  }
  if (typeof walkForwardReport?.total_windows === 'number') {
    runtimeHints.walk_forward_windows = walkForwardReport.total_windows
  }
  if (typeof walkForwardReport?.stable_window_rate === 'number') {
    runtimeHints.walk_forward_stable_window_rate = walkForwardReport.stable_window_rate
  }
  if (typeof walkForwardReport?.mean_brier_improvement === 'number') {
    runtimeHints.walk_forward_mean_brier_improvement = walkForwardReport.mean_brier_improvement
  }
  if (typeof walkForwardReport?.mean_log_loss_improvement === 'number') {
    runtimeHints.walk_forward_mean_log_loss_improvement = walkForwardReport.mean_log_loss_improvement
  }
  if (typeof walkForwardReport?.mean_net_edge_bps === 'number') {
    runtimeHints.walk_forward_mean_net_edge_bps = walkForwardReport.mean_net_edge_bps
  }
  if (typeof walkForwardReport?.promotion_ready === 'boolean') {
    runtimeHints.walk_forward_promotion_ready = walkForwardReport.promotion_ready
  }
  const autopilotCycleSummary = asRecord(input.autopilotCycleSummary)
  const autopilotOverview = asRecord(autopilotCycleSummary?.overview)
  if (
    autopilotOverview?.health === 'healthy'
    || autopilotOverview?.health === 'degraded'
    || autopilotOverview?.health === 'blocked'
  ) {
    runtimeHints.autopilot_cycle_health = autopilotOverview.health
  }
  if (typeof autopilotOverview?.health === 'string') {
    runtimeHints.autopilot_cycle_summary = `autopilot=${autopilotOverview.health} cycles=${String(autopilotCycleSummary?.total_cycles ?? 0)}`
  }
  const researchMemorySummary = asRecord(input.researchMemorySummary)
  if (typeof researchMemorySummary?.summary === 'string') {
    runtimeHints.research_memory_summary = researchMemorySummary.summary
  }
  if (typeof researchMemorySummary?.memory_count === 'number') {
    runtimeHints.research_memory_memory_count = researchMemorySummary.memory_count
  }
  const validationSummary = asRecord(researchMemorySummary?.validation_summary)
  if (typeof validationSummary?.average_score === 'number') {
    runtimeHints.research_memory_validation_score = validationSummary.average_score
  }

  return {
    ...runtimeHints,
    multi_venue_taxonomy: input.multiVenueExecution?.taxonomy ?? null,
    multi_venue_execution_filter_reason_codes: input.multiVenueExecution?.execution_filter_reason_codes ?? [],
    multi_venue_execution_filter_reason_code_counts: input.multiVenueExecution?.execution_filter_reason_code_counts ?? {},
    execution_projection_gate_name: input.executionProjection?.gate_name ?? undefined,
    execution_projection_preflight_only: input.executionProjection?.preflight_only ?? undefined,
    execution_projection_requested_path: input.executionProjection?.requested_path ?? null,
    execution_pathways_highest_actionable_mode:
      input.executionPathways?.highest_actionable_mode ??
      input.executionProjection?.selected_path ??
      input.executionProjection?.highest_safe_requested_mode ??
      null,
    execution_projection_selected_path: input.executionProjection?.selected_path ?? null,
    execution_projection_selected_path_status: selectedProjectionPath?.status ?? null,
    execution_projection_selected_path_effective_mode: selectedProjectionPath?.effective_mode ?? null,
    execution_projection_selected_path_reason_summary: selectedProjectionPath?.reason_summary ?? null,
    execution_projection_verdict: input.executionProjection?.verdict ?? null,
    execution_projection_highest_safe_requested_mode: input.executionProjection?.highest_safe_requested_mode ?? null,
    execution_projection_recommended_effective_mode: input.executionProjection?.recommended_effective_mode ?? null,
    execution_projection_manual_review_required: input.executionProjection?.manual_review_required ?? undefined,
    execution_projection_ttl_ms: input.executionProjection?.ttl_ms ?? null,
    execution_projection_expires_at: input.executionProjection?.expires_at ?? null,
    execution_projection_blocking_reasons: input.executionProjection?.blocking_reasons ?? [],
    execution_projection_downgrade_reasons: input.executionProjection?.downgrade_reasons ?? [],
    execution_projection_summary: input.executionProjection?.summary ?? null,
    execution_projection_preflight_summary: input.executionProjection?.preflight_summary ?? null,
    execution_projection_capital_status: input.executionProjection?.basis.capital_status ?? null,
    execution_projection_reconciliation_status: input.executionProjection?.basis.reconciliation_status ?? null,
    execution_projection_selected_preview: selectedPreview.preview,
    execution_projection_selected_preview_source:
      selectedPreview.preview_source === 'none' ? null : selectedPreview.preview_source,
    execution_projection_selected_edge_bucket: selectedEdgeBucket,
    execution_projection_selected_pre_trade_gate: selectedPreTradeGate,
    execution_projection_selected_pre_trade_gate_verdict: selectedPreTradeGate?.verdict ?? null,
    execution_projection_selected_pre_trade_gate_summary: selectedPreTradeGate?.summary ?? null,
    execution_projection_selected_path_net_edge_bps: selectedPreTradeGate?.net_edge_bps ?? null,
    execution_projection_selected_path_minimum_net_edge_bps: selectedPreTradeGate?.minimum_net_edge_bps ?? null,
    execution_projection_selected_path_canonical_size_usd: selectedProjectionPath?.sizing_signal?.canonical_size_usd ?? null,
    execution_projection_selected_path_shadow_signal_present: selectedProjectionPath?.shadow_arbitrage_signal != null,
    shadow_arbitrage_present: canonicalShadowArbitrage != null,
    shadow_arbitrage_shadow_edge_bps: canonicalShadowArbitrage?.summary.shadow_edge_bps ?? null,
    shadow_arbitrage_recommended_size_usd: canonicalShadowArbitrage?.summary.recommended_size_usd ?? null,
    shadow_arbitrage: canonicalShadowArbitrage ?? undefined,
  }
}

function summarizePredictionMarketResearchRuntimeHints(input: {
  pipelineId: string | null
  pipelineVersion: string | null
  forecasterCount: number | null
  weightedProbabilityYes: number | null
  weightedCoverage: number | null
  preferredMode: 'market_only' | 'aggregate' | 'abstention' | null
  abstentionVersion: string | null
  abstentionBlocksForecast: boolean | null
  forecastProbabilityYesHint: number | null
}): string | null {
  if (
    input.pipelineId == null &&
    input.pipelineVersion == null &&
    input.forecasterCount == null &&
    input.weightedProbabilityYes == null &&
    input.weightedCoverage == null &&
    input.preferredMode == null &&
    input.abstentionVersion == null &&
    input.abstentionBlocksForecast == null &&
    input.forecastProbabilityYesHint == null
  ) {
    return null
  }

  const parts = ['research:']
  const mode = input.preferredMode === 'market_only' ? 'market_only' : 'research_driven'
  parts.push(`mode=${mode}`)
  if (input.pipelineId) parts.push(`pipeline=${input.pipelineId}`)
  if (input.pipelineVersion) parts.push(`version=${input.pipelineVersion}`)
  if (input.forecasterCount != null) parts.push(`forecasters=${input.forecasterCount}`)
  if (input.weightedProbabilityYes != null) parts.push(`weighted_yes=${input.weightedProbabilityYes}`)
  if (input.weightedCoverage != null) parts.push(`coverage=${input.weightedCoverage}`)
  if (input.preferredMode) parts.push(`preferred=${input.preferredMode}`)
  if (input.abstentionVersion) parts.push(`abstention=${input.abstentionVersion}`)
  if (input.abstentionBlocksForecast != null) {
    parts.push(`blocks_forecast=${input.abstentionBlocksForecast ? 'yes' : 'no'}`)
  }
  if (input.forecastProbabilityYesHint != null) parts.push(`forecast_hint=${input.forecastProbabilityYesHint}`)
  return parts.join(' ')
}

type PredictionMarketRecommendationOrigin =
  | 'market_only'
  | 'research_driven'
  | 'manual_thesis'
  | 'abstention'

function resolvePredictionMarketRecommendationOrigin(input: {
  forecast: ForecastPacket | null | undefined
  recommendation: MarketRecommendationPacket | null | undefined
  preferredMode?: 'market_only' | 'aggregate' | 'abstention' | null
  blocksForecast?: boolean
}): {
  origin: PredictionMarketRecommendationOrigin
  summary: string
  abstention_flipped_recommendation: boolean
} | null {
  const recommendationAction = input.recommendation?.action ?? 'unknown'
  if (!input.forecast) {
    if (input.blocksForecast) {
      return {
        origin: 'abstention',
        summary: `Abstention policy flipped the recommendation to ${recommendationAction} before a canonical forecast packet was rehydrated.`,
        abstention_flipped_recommendation: true,
      }
    }

    if (input.preferredMode === 'market_only') {
      return {
        origin: 'market_only',
        summary: `Recommendation runtime still originates from the market midpoint baseline and resolves to ${recommendationAction}.`,
        abstention_flipped_recommendation: false,
      }
    }

    if (input.preferredMode != null) {
      return {
        origin: 'research_driven',
        summary: `Recommendation runtime originates from a research-driven forecast and resolves to ${recommendationAction}.`,
        abstention_flipped_recommendation: false,
      }
    }

    return null
  }

  const abstentionFlippedRecommendation = Boolean(
    input.forecast.abstention_reason || input.forecast.requires_manual_review,
  )

  if (input.forecast.basis === 'manual_thesis') {
    return {
      origin: 'manual_thesis',
      summary: `Recommendation runtime originates from a manual thesis override and resolves to ${recommendationAction}.`,
      abstention_flipped_recommendation: abstentionFlippedRecommendation,
    }
  }

  if (input.preferredMode === 'abstention' || input.blocksForecast) {
    return {
      origin: 'abstention',
      summary: `Abstention policy flipped the recommendation to ${recommendationAction} before promotion evidence cleared the benchmark gate.`,
      abstention_flipped_recommendation: true,
    }
  }

  if (abstentionFlippedRecommendation) {
    return {
      origin: 'abstention',
      summary: `Abstention policy flipped the recommendation to ${recommendationAction} at ${input.forecast.abstention_reason ?? 'manual review'}.`,
      abstention_flipped_recommendation: true,
    }
  }

  if (forecastUsesResearchDrivenFairValue(input.forecast)) {
    return {
      origin: 'research_driven',
      summary: `Recommendation runtime originates from a research-driven forecast and resolves to ${recommendationAction}.`,
      abstention_flipped_recommendation: false,
    }
  }

  return {
    origin: 'market_only',
    summary: `Recommendation runtime still originates from the market midpoint baseline and resolves to ${recommendationAction}.`,
    abstention_flipped_recommendation: false,
  }
}

function isForecastPacketLike(value: unknown): value is ForecastPacket {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const packet = value as Record<string, unknown>
  return (
    typeof packet.basis === 'string'
    || typeof packet.basis === 'object'
    || typeof packet.probability_yes === 'number'
    || typeof packet.abstention_reason === 'string'
  )
}

function isRecommendationPacketLike(value: unknown): value is MarketRecommendationPacket {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const packet = value as Record<string, unknown>
  return typeof packet.action === 'string'
}

function extractStoredExecutionArtifacts(details: StoredPredictionMarketRunDetails): StoredExecutionArtifacts {
  const findArtifact = (artifactType: string) =>
    details.artifacts.find((artifact) => artifact.artifact_type === artifactType)?.payload

  const snapshot = findArtifact('market_snapshot') as MarketSnapshot | undefined
  const resolutionPolicy = findArtifact('resolution_policy') as ReturnType<typeof buildResolutionPolicy> | undefined
  const evidencePackets = findArtifact('evidence_bundle') as EvidencePacket[] | undefined
  const forecast = findArtifact('forecast_packet') as ForecastPacket | undefined
  const recommendation = findArtifact('recommendation_packet') as MarketRecommendationPacket | undefined
  const marketEvents = (findArtifact('market_events') ?? null) as PredictionMarketJsonArtifact | null
  const marketPositions = (findArtifact('market_positions') ?? null) as PredictionMarketJsonArtifact | null
  const sourceAudit = (findArtifact('source_audit') ?? null) as PredictionMarketJsonArtifact | null
  const rulesLineage = (findArtifact('rules_lineage') ?? null) as PredictionMarketJsonArtifact | null
  const catalystTimeline = (findArtifact('catalyst_timeline') ?? null) as PredictionMarketJsonArtifact | null
  const worldState = (findArtifact('world_state') ?? null) as PredictionMarketJsonArtifact | null
  const ticketPayload = (findArtifact('ticket_payload') ?? null) as PredictionMarketJsonArtifact | null
  const quantSignalBundle = (findArtifact('quant_signal_bundle') ?? null) as PredictionMarketJsonArtifact | null
  const decisionLedger = (findArtifact('decision_ledger') ?? null) as PredictionMarketJsonArtifact | null
  const calibrationReport = (findArtifact('calibration_report') ?? null) as PredictionMarketJsonArtifact | null
  const resolvedHistory = (findArtifact('resolved_history') ?? null) as PredictionMarketJsonArtifact | null
  const costModelReport = (findArtifact('cost_model_report') ?? null) as PredictionMarketJsonArtifact | null
  const walkForwardReport = (findArtifact('walk_forward_report') ?? null) as PredictionMarketJsonArtifact | null
  const autopilotCycleSummary = (findArtifact('autopilot_cycle_summary') ?? null) as PredictionMarketJsonArtifact | null
  const researchMemorySummary = (findArtifact('research_memory_summary') ?? null) as PredictionMarketJsonArtifact | null
  const paperSurface = asSurfaceRecord(findArtifact('paper_surface'))
  const replaySurface = asSurfaceRecord(findArtifact('replay_surface'))
  const researchBridge = (findArtifact('research_bridge') ?? null) as ResearchBridgeBundle | null
  const researchSidecar = (findArtifact('research_sidecar') ?? null) as MarketResearchSidecar | null
  const timesfmSidecar = (findArtifact('timesfm_sidecar') ?? null) as PredictionMarketTimesFMSidecar | null
  const microstructureLab = (findArtifact('microstructure_lab') ?? null) as MicrostructureLabReport | null
  const crossVenueIntelligence = normalizeCrossVenueIntelligence(
    (findArtifact('cross_venue_intelligence') ?? null) as PredictionMarketCrossVenueIntelligence | null,
  )
  const provenanceBundle = (findArtifact('provenance_bundle') ?? null) as PredictionMarketProvenanceBundle | null
  const pipelineGuard = (findArtifact('pipeline_guard') ?? null) as PredictionMarketPipelineGuard | null
  const runtimeGuard = (findArtifact('runtime_guard') ?? null) as PredictionMarketRuntimeGuardResult | null
  const compliance = (findArtifact('compliance_report') ?? null) as PredictionMarketComplianceDecision | null
  const strategyCandidatePacket = (findArtifact('strategy_candidate_packet') ?? null) as StrategyCandidatePacket | null
  const strategyDecisionPacket = (findArtifact('strategy_decision_packet') ?? null) as StrategyDecisionPacket | null
  const strategyShadowSummary = (findArtifact('strategy_shadow_summary') ?? null) as StrategyShadowSummary | null
  const strategyShadowReport = (findArtifact('strategy_shadow_report') ?? null) as StrategyShadowReport | null
  const executionIntentPreview = (findArtifact('execution_intent_preview') ?? null) as ExecutionIntentPreview | null
  const quotePairIntentPreview = (findArtifact('quote_pair_intent_preview') ?? null) as QuotePairIntentPreview | null
  const basketIntentPreview = (findArtifact('basket_intent_preview') ?? null) as BasketIntentPreview | null
  const latencyReferenceBundle = (findArtifact('latency_reference_bundle') ?? null) as LatencyReferenceBundle | null
  const resolutionAnomalyReport = (findArtifact('resolution_anomaly_report') ?? null) as ResolutionAnomalyReport | null
  const autonomousAgentReport = (findArtifact('autonomous_agent_report') ?? null) as AutonomousAgentReport | null
  const executionReadiness = (findArtifact('execution_readiness') ?? null) as PredictionMarketExecutionReadiness | null
  const executionPathways = (findArtifact('execution_pathways') ?? null) as PredictionMarketExecutionPathwaysReport | null
  const executionProjection = normalizeExecutionProjectionReport(
    (findArtifact('execution_projection') ?? null) as PredictionMarketExecutionProjectionReport | null,
  )
  const shadowArbitrage = (findArtifact('shadow_arbitrage') ?? null) as ShadowArbitrageSimulationReport | null
  const rawTradeIntentGuard = (findArtifact('trade_intent_guard') ?? null) as TradeIntentGuard | null
  const tradeIntentGuard = rehydratePredictionMarketTradeIntentGuardForBenchmarkPromotion(
    rawTradeIntentGuard,
    details as Partial<PredictionMarketRunRuntimeHints> & {
      execution_projection?: PredictionMarketExecutionProjectionReport | null
    },
  )
  const multiVenueExecution = (findArtifact('multi_venue_execution') ?? null) as MultiVenueExecution | null

  if (!snapshot || !resolutionPolicy || !evidencePackets || !forecast || !recommendation) {
    throw new PredictionMarketsError('Stored artifacts are incomplete for replay', {
      status: 409,
      code: 'stored_artifacts_incomplete',
    })
  }

  return {
    snapshot,
    resolution_policy: resolutionPolicy,
    evidence_packets: evidencePackets,
    forecast,
    recommendation: enrichRecommendationPacket({
      snapshot,
      resolutionPolicy,
      forecast,
      recommendation,
    }),
    market_events: marketEvents,
    market_positions: marketPositions,
    source_audit: sourceAudit,
    rules_lineage: rulesLineage,
    catalyst_timeline: catalystTimeline,
    world_state: worldState,
    ticket_payload: ticketPayload,
    quant_signal_bundle: quantSignalBundle,
    decision_ledger: decisionLedger,
    calibration_report: calibrationReport,
    resolved_history: resolvedHistory,
    cost_model_report: costModelReport,
    walk_forward_report: walkForwardReport,
    autopilot_cycle_summary: autopilotCycleSummary,
    research_memory_summary: researchMemorySummary,
    paper_surface: paperSurface,
    replay_surface: replaySurface,
    research_bridge: researchBridge,
    research_sidecar: researchSidecar,
    timesfm_sidecar: timesfmSidecar,
    microstructure_lab: microstructureLab,
    cross_venue_intelligence: crossVenueIntelligence,
    provenance_bundle: provenanceBundle,
    pipeline_guard: pipelineGuard,
    runtime_guard: runtimeGuard,
    compliance,
    execution_readiness: executionReadiness,
    execution_pathways: executionPathways,
    execution_projection: executionProjection,
    strategy_candidate_packet: strategyCandidatePacket,
    strategy_decision_packet: strategyDecisionPacket,
    strategy_shadow_summary: strategyShadowSummary,
    strategy_shadow_report: strategyShadowReport,
    execution_intent_preview: executionIntentPreview,
    quote_pair_intent_preview: quotePairIntentPreview,
    basket_intent_preview: basketIntentPreview,
    latency_reference_bundle: latencyReferenceBundle,
    resolution_anomaly_report: resolutionAnomalyReport,
    autonomous_agent_report: autonomousAgentReport,
    shadow_arbitrage: resolveCanonicalPredictionMarketShadowArbitrage({
      executionProjection,
      shadowArbitrage,
    }),
    trade_intent_guard: tradeIntentGuard,
    multi_venue_execution: multiVenueExecution,
    order_trace_audit: extractOrderTraceAudit(details),
    venue_coverage: getVenueCoverageContract(),
  }
}

function enrichStoredPredictionMarketRunDetails(
  details: StoredPredictionMarketRunDetails & Partial<PredictionMarketRunRuntimeHints>,
): StoredPredictionMarketRunDetails & Partial<PredictionMarketRunRuntimeHints> {
  const snapshotArtifact = details.artifacts.find((artifact) => artifact.artifact_type === 'market_snapshot')
  const resolutionArtifact = details.artifacts.find((artifact) => artifact.artifact_type === 'resolution_policy')
  const forecastArtifact = details.artifacts.find((artifact) => artifact.artifact_type === 'forecast_packet')
  const recommendationArtifactIndex = details.artifacts.findIndex((artifact) => artifact.artifact_type === 'recommendation_packet')

  if (
    !snapshotArtifact ||
    !resolutionArtifact ||
    !forecastArtifact ||
    recommendationArtifactIndex < 0
  ) {
    return details
  }

  const enrichedRecommendation = enrichRecommendationPacket({
    snapshot: snapshotArtifact.payload as MarketSnapshot,
    resolutionPolicy: resolutionArtifact.payload as ResolutionPolicy,
    forecast: forecastArtifact.payload as ForecastPacket,
    recommendation: details.artifacts[recommendationArtifactIndex].payload as MarketRecommendationPacket,
  })

  const artifacts = [...details.artifacts]
  artifacts[recommendationArtifactIndex] = {
    ...artifacts[recommendationArtifactIndex],
    payload: enrichedRecommendation,
  }

  return {
    ...details,
    artifacts,
  }
}

function extractRunDetailForecastPacket(
  details: Pick<StoredPredictionMarketRunDetails, 'artifacts'> & {
    forecast?: unknown
  },
): ForecastPacket | null {
  if (isForecastPacketLike(details.forecast)) {
    return details.forecast
  }
  const artifact = details.artifacts.find((entry) => entry.artifact_type === 'forecast_packet')
  return (artifact?.payload as ForecastPacket | undefined) ?? null
}

function extractRunDetailRecommendationPacket(
  details: Pick<StoredPredictionMarketRunDetails, 'artifacts'> & {
    recommendation?: unknown
  },
): MarketRecommendationPacket | null {
  if (isRecommendationPacketLike(details.recommendation)) {
    return details.recommendation
  }
  const artifact = details.artifacts.find((entry) => entry.artifact_type === 'recommendation_packet')
  return (artifact?.payload as MarketRecommendationPacket | undefined) ?? null
}

function buildPredictionMarketBenchmarkGateOverride(
  details: Partial<
    Pick<
      PredictionMarketRunSummaryWithArtifactAudit,
    | 'research_benchmark_gate_summary'
    | 'research_benchmark_uplift_bps'
    | 'research_benchmark_verdict'
    | 'research_benchmark_gate_status'
    | 'research_benchmark_promotion_status'
    | 'research_benchmark_promotion_ready'
    | 'research_benchmark_preview_available'
    | 'research_benchmark_promotion_evidence'
    | 'research_benchmark_evidence_level'
    | 'research_promotion_gate_kind'
    | 'research_benchmark_promotion_blocker_summary'
    | 'research_benchmark_gate_blockers'
    | 'research_benchmark_gate_reasons'
    | 'research_benchmark_promotion_summary'
    | 'benchmark_gate_summary'
    | 'benchmark_uplift_bps'
    | 'benchmark_verdict'
    | 'benchmark_gate_status'
    | 'benchmark_promotion_status'
    | 'benchmark_promotion_ready'
    | 'benchmark_preview_available'
    | 'benchmark_promotion_evidence'
    | 'benchmark_evidence_level'
    | 'benchmark_promotion_gate_kind'
    | 'benchmark_promotion_blocker_summary'
    | 'benchmark_promotion_summary'
    | 'research_benchmark_gate_blocks_live'
    | 'research_benchmark_live_block_reason'
    | 'benchmark_gate_blocks_live'
    | 'benchmark_gate_live_block_reason'
    | 'benchmark_gate_blockers'
    | 'benchmark_gate_reasons'
    >
  >,
): Partial<Pick<
  PredictionMarketRunRuntimeHints,
  | 'research_benchmark_gate_summary'
  | 'research_benchmark_uplift_bps'
  | 'research_benchmark_verdict'
  | 'research_benchmark_gate_status'
  | 'research_benchmark_promotion_status'
  | 'research_benchmark_promotion_ready'
  | 'research_benchmark_preview_available'
  | 'research_benchmark_promotion_evidence'
  | 'research_benchmark_evidence_level'
  | 'research_promotion_gate_kind'
  | 'research_benchmark_promotion_blocker_summary'
  | 'research_benchmark_gate_blockers'
  | 'research_benchmark_gate_reasons'
  | 'research_benchmark_promotion_summary'
  | 'benchmark_gate_summary'
  | 'benchmark_uplift_bps'
  | 'benchmark_verdict'
  | 'benchmark_gate_status'
  | 'benchmark_promotion_status'
  | 'benchmark_promotion_ready'
  | 'benchmark_preview_available'
  | 'benchmark_promotion_evidence'
  | 'benchmark_evidence_level'
  | 'benchmark_promotion_gate_kind'
  | 'benchmark_promotion_blocker_summary'
  | 'benchmark_promotion_summary'
  | 'benchmark_gate_summary'
  | 'benchmark_gate_blocks_live'
  | 'benchmark_gate_live_block_reason'
  | 'research_benchmark_gate_blocks_live'
  | 'research_benchmark_live_block_reason'
  | 'benchmark_gate_blockers'
  | 'benchmark_gate_reasons'
>> {
  const benchmarkPromotionReady =
    firstDefined(details.benchmark_promotion_ready, details.research_benchmark_promotion_ready)
  const benchmarkPromotionBlockerSummary =
    firstDefined(
      details.benchmark_promotion_blocker_summary,
      details.benchmark_promotion_summary,
      details.research_benchmark_promotion_blocker_summary,
      details.research_benchmark_promotion_summary,
    ) ?? null
  const benchmarkGateBlocksLive =
    firstDefined(
      details.benchmark_gate_blocks_live,
      details.research_benchmark_gate_blocks_live,
      benchmarkPromotionReady === false ? true : undefined,
    )
  const benchmarkGateLiveBlockReason =
    details.benchmark_gate_live_block_reason
    ?? details.research_benchmark_live_block_reason
    ?? (benchmarkGateBlocksLive === true ? benchmarkPromotionBlockerSummary : null)

  return {
    research_benchmark_gate_summary: firstDefined(details.research_benchmark_gate_summary, details.benchmark_gate_summary),
    research_benchmark_uplift_bps: firstDefined(details.research_benchmark_uplift_bps, details.benchmark_uplift_bps),
    research_benchmark_verdict: firstDefined(details.research_benchmark_verdict, details.benchmark_verdict),
    research_benchmark_gate_status: firstDefined(details.research_benchmark_gate_status, details.benchmark_gate_status),
    research_benchmark_promotion_status: firstDefined(
      details.research_benchmark_promotion_status,
      details.benchmark_promotion_status,
    ),
    research_benchmark_promotion_ready: firstDefined(
      details.research_benchmark_promotion_ready,
      details.benchmark_promotion_ready,
    ),
    research_benchmark_preview_available: firstDefined(
      details.research_benchmark_preview_available,
      details.benchmark_preview_available,
    ),
    research_benchmark_promotion_evidence: firstDefined(
      details.research_benchmark_promotion_evidence,
      details.benchmark_promotion_evidence,
    ),
    research_benchmark_evidence_level: firstDefined(
      details.research_benchmark_evidence_level,
      details.benchmark_evidence_level,
    ),
    research_promotion_gate_kind: firstDefined(
      details.research_promotion_gate_kind,
      details.benchmark_promotion_gate_kind,
    ),
    research_benchmark_promotion_blocker_summary: firstDefined(
      details.research_benchmark_promotion_blocker_summary,
      details.benchmark_promotion_blocker_summary,
      details.benchmark_promotion_summary,
    ),
    research_benchmark_promotion_summary: firstDefined(
      details.research_benchmark_promotion_summary,
      details.benchmark_promotion_summary,
    ),
    research_benchmark_gate_blockers: firstDefined(
      details.research_benchmark_gate_blockers,
      details.benchmark_gate_blockers,
    ),
    research_benchmark_gate_reasons: firstDefined(
      details.research_benchmark_gate_reasons,
      details.benchmark_gate_reasons,
    ),
    benchmark_gate_summary: firstDefined(details.benchmark_gate_summary, details.research_benchmark_gate_summary),
    benchmark_uplift_bps: firstDefined(details.benchmark_uplift_bps, details.research_benchmark_uplift_bps),
    benchmark_verdict: firstDefined(details.benchmark_verdict, details.research_benchmark_verdict),
    benchmark_gate_status: firstDefined(details.benchmark_gate_status, details.research_benchmark_gate_status),
    benchmark_promotion_status: firstDefined(
      details.benchmark_promotion_status,
      details.research_benchmark_promotion_status,
    ),
    benchmark_promotion_ready: firstDefined(
      details.benchmark_promotion_ready,
      details.research_benchmark_promotion_ready,
    ),
    benchmark_preview_available: firstDefined(
      details.benchmark_preview_available,
      details.research_benchmark_preview_available,
    ),
    benchmark_promotion_evidence: firstDefined(
      details.benchmark_promotion_evidence,
      details.research_benchmark_promotion_evidence,
    ),
    benchmark_evidence_level: firstDefined(
      details.benchmark_evidence_level,
      details.research_benchmark_evidence_level,
    ),
    benchmark_promotion_gate_kind: firstDefined(
      details.benchmark_promotion_gate_kind,
      details.research_promotion_gate_kind,
    ),
    benchmark_promotion_blocker_summary: firstDefined(
      details.benchmark_promotion_blocker_summary,
      details.benchmark_promotion_summary,
      details.research_benchmark_promotion_blocker_summary,
      details.research_benchmark_promotion_summary,
    ),
    benchmark_promotion_summary: firstDefined(
      details.benchmark_promotion_summary,
      details.research_benchmark_promotion_summary,
    ),
    benchmark_gate_blocks_live: benchmarkGateBlocksLive,
    benchmark_gate_live_block_reason: benchmarkGateLiveBlockReason,
    research_benchmark_gate_blocks_live: benchmarkGateBlocksLive,
    research_benchmark_live_block_reason: benchmarkGateLiveBlockReason,
    benchmark_gate_blockers: firstDefined(details.benchmark_gate_blockers, details.research_benchmark_gate_blockers),
    benchmark_gate_reasons: firstDefined(details.benchmark_gate_reasons, details.research_benchmark_gate_reasons),
  }
}

function hasExplicitPredictionMarketCanonicalBenchmarkHints(
  details: Partial<PredictionMarketRunRuntimeHints>,
): boolean {
  return [
    details.benchmark_gate_summary,
    details.benchmark_uplift_bps,
    details.benchmark_verdict,
    details.benchmark_gate_status,
    details.benchmark_promotion_status,
    details.benchmark_promotion_ready,
    details.benchmark_preview_available,
    details.benchmark_promotion_evidence,
    details.benchmark_evidence_level,
    details.benchmark_promotion_gate_kind,
    details.benchmark_promotion_blocker_summary,
    details.benchmark_promotion_summary,
    details.benchmark_gate_blocks_live,
    details.benchmark_gate_live_block_reason,
    details.benchmark_gate_blockers,
    details.benchmark_gate_reasons,
  ].some((value) => value !== undefined)
}

function resolvePredictionMarketSummaryBenchmarkGateOverride(
  summary: Partial<PredictionMarketRunRuntimeHints>,
  details: Partial<PredictionMarketRunRuntimeHints>,
  canonicalHintSource: Partial<PredictionMarketRunRuntimeHints> = details,
): Partial<PredictionMarketRunRuntimeHints> {
  const summaryBenchmarkGateOverride = buildPredictionMarketBenchmarkGateOverride(summary)
  const detailBenchmarkGateOverride = buildPredictionMarketBenchmarkGateOverride(details)
  const mergedBenchmarkGateOverride = hasExplicitPredictionMarketCanonicalBenchmarkHints(canonicalHintSource)
    ? {
      ...summaryBenchmarkGateOverride,
      ...detailBenchmarkGateOverride,
    }
    : summaryBenchmarkGateOverride
  const fallbackBenchmarkGateBlocksLive =
    mergedBenchmarkGateOverride.benchmark_gate_blocks_live
    ?? mergedBenchmarkGateOverride.research_benchmark_gate_blocks_live
    ?? (mergedBenchmarkGateOverride.research_benchmark_promotion_ready === false ? true : undefined)
  const fallbackBenchmarkGateLiveBlockReason =
    mergedBenchmarkGateOverride.benchmark_gate_live_block_reason
    ?? mergedBenchmarkGateOverride.research_benchmark_live_block_reason
    ?? (
      mergedBenchmarkGateOverride.research_benchmark_promotion_ready === false
        ? mergedBenchmarkGateOverride.research_benchmark_promotion_blocker_summary
        ?? mergedBenchmarkGateOverride.research_benchmark_promotion_summary
        ?? mergedBenchmarkGateOverride.research_benchmark_gate_summary
        : null
    )

  return {
    ...mergedBenchmarkGateOverride,
    benchmark_gate_blocks_live: fallbackBenchmarkGateBlocksLive,
    benchmark_gate_live_block_reason: fallbackBenchmarkGateLiveBlockReason ?? null,
  }
}

function resolvePredictionMarketStoredRunBenchmarkHintSource(
  runId: string,
  workspaceId: number,
): Partial<PredictionMarketRunRuntimeHints> | null {
  const storedDetails = getStoredPredictionMarketRunDetails(runId, workspaceId)
  if (!storedDetails) return null

  return enrichStoredPredictionMarketRunDetails(
    storedDetails as StoredPredictionMarketRunDetails & Partial<PredictionMarketRunRuntimeHints>,
  ) as Partial<PredictionMarketRunRuntimeHints>
}

function buildPredictionMarketBenchmarkGateOverrideFromSummary(
  summary: PredictionMarketsBenchmarkGateSummary,
): Partial<Pick<
  PredictionMarketRunRuntimeHints,
  | 'research_benchmark_gate_summary'
  | 'research_benchmark_uplift_bps'
  | 'research_benchmark_verdict'
  | 'research_benchmark_gate_status'
  | 'research_benchmark_promotion_status'
  | 'research_benchmark_promotion_ready'
  | 'research_benchmark_preview_available'
  | 'research_benchmark_promotion_evidence'
  | 'research_benchmark_evidence_level'
  | 'research_promotion_gate_kind'
  | 'research_benchmark_promotion_blocker_summary'
  | 'research_benchmark_gate_blockers'
  | 'research_benchmark_gate_reasons'
  | 'research_benchmark_promotion_summary'
  | 'research_benchmark_gate_blocks_live'
  | 'research_benchmark_live_block_reason'
  | 'benchmark_gate_blocks_live'
  | 'benchmark_gate_live_block_reason'
>> {
  const benchmarkGateBlocksLive = summary.promotion_ready === false
  const benchmarkGateLiveBlockReason = benchmarkGateBlocksLive
    ? summary.promotion_blocker_summary ?? summary.summary ?? 'out_of_sample_unproven'
    : null

  return {
    research_benchmark_gate_summary: summary.summary,
    research_benchmark_uplift_bps: summary.upliftBps,
    research_benchmark_verdict: summary.verdict,
    research_benchmark_gate_status: summary.status,
    research_benchmark_promotion_status: summary.promotion_status,
    research_benchmark_promotion_ready: summary.promotion_ready,
    research_benchmark_preview_available: summary.preview_available,
    research_benchmark_promotion_evidence: summary.promotion_evidence,
    research_benchmark_evidence_level: summary.evidence_level,
    research_promotion_gate_kind: summary.promotion_gate_kind,
    research_benchmark_promotion_blocker_summary: summary.promotion_blocker_summary,
    research_benchmark_gate_blockers: summary.blockers,
    research_benchmark_gate_reasons: summary.reasons,
    research_benchmark_promotion_summary: summary.promotion_blocker_summary,
    research_benchmark_gate_blocks_live: benchmarkGateBlocksLive,
    research_benchmark_live_block_reason: benchmarkGateLiveBlockReason,
    benchmark_gate_blocks_live: benchmarkGateBlocksLive,
    benchmark_gate_live_block_reason: benchmarkGateLiveBlockReason,
  }
}

type PredictionMarketBenchmarkPromotionState = {
  promotion_ready: boolean | null
  promotion_blocker_summary: string | null
  promotion_gate_kind: PredictionMarketsBenchmarkGateSummary['promotion_gate_kind'] | null
  gate_blockers: string[]
}

function resolvePredictionMarketBenchmarkPromotionState(details: {
  benchmark_promotion_ready?: boolean | null
  research_benchmark_promotion_ready?: boolean | null
  benchmark_promotion_blocker_summary?: string | null
  research_benchmark_promotion_blocker_summary?: string | null
  benchmark_promotion_summary?: string | null
  research_benchmark_promotion_summary?: string | null
  benchmark_promotion_gate_kind?: PredictionMarketsBenchmarkGateSummary['promotion_gate_kind'] | null
  research_promotion_gate_kind?: PredictionMarketsBenchmarkGateSummary['promotion_gate_kind'] | null
  benchmark_gate_blockers?: string[]
  research_benchmark_gate_blockers?: string[]
}): PredictionMarketBenchmarkPromotionState {
  return {
    promotion_ready:
      details.benchmark_promotion_ready
      ?? details.research_benchmark_promotion_ready
      ?? null,
    promotion_blocker_summary:
      details.benchmark_promotion_blocker_summary
      ?? details.benchmark_promotion_summary
      ?? details.research_benchmark_promotion_blocker_summary
      ?? details.research_benchmark_promotion_summary
      ?? null,
    promotion_gate_kind:
      details.benchmark_promotion_gate_kind
      ?? details.research_promotion_gate_kind
      ?? null,
    gate_blockers:
      details.benchmark_gate_blockers
      ?? details.research_benchmark_gate_blockers
      ?? [],
  }
}

function resolvePredictionMarketBenchmarkSurfaceBlockingReasons(details: {
  research_abstention_policy_blocks_forecast?: boolean | null
  benchmark_gate_status?: PredictionMarketsBenchmarkGateSummary['status'] | null
  research_benchmark_gate_status?: PredictionMarketsBenchmarkGateSummary['status'] | null
  benchmark_gate_blockers?: string[]
  research_benchmark_gate_blockers?: string[]
}): string[] {
  const usesCanonicalBenchmarkHints =
    details.benchmark_gate_status === 'blocked_by_abstention'
    || details.benchmark_gate_blockers !== undefined

  return details.research_abstention_policy_blocks_forecast === true
    || details.benchmark_gate_status === 'blocked_by_abstention'
    || details.research_benchmark_gate_status === 'blocked_by_abstention'
    ? (
      details.benchmark_gate_blockers && details.benchmark_gate_blockers.length > 0
        ? details.benchmark_gate_blockers.map((reason) => `benchmark:${reason}`)
        : details.research_benchmark_gate_blockers && details.research_benchmark_gate_blockers.length > 0
          ? details.research_benchmark_gate_blockers.map((reason) => `research_benchmark:${reason}`)
          : [usesCanonicalBenchmarkHints ? 'benchmark:abstention_blocks_forecast' : 'research_benchmark:abstention_blocks_forecast']
    )
    : []
}

function resolvePredictionMarketBenchmarkPromotionBlockers(
  details: {
    benchmark_gate_blockers?: string[]
    benchmark_promotion_ready?: boolean | null
    benchmark_promotion_blocker_summary?: string | null
    benchmark_promotion_summary?: string | null
    benchmark_promotion_gate_kind?: PredictionMarketsBenchmarkGateSummary['promotion_gate_kind'] | null
    research_benchmark_gate_blockers?: string[]
    research_benchmark_promotion_ready?: boolean | null
  },
  requiresBenchmarkPromotionGate: boolean,
): string[] {
  const benchmarkPromotionState = resolvePredictionMarketBenchmarkPromotionState(details)
  if (!requiresBenchmarkPromotionGate || benchmarkPromotionState.promotion_ready === true) {
    return []
  }

  const usesCanonicalBenchmarkHints =
    details.benchmark_gate_blockers !== undefined
    || details.benchmark_promotion_ready !== undefined
    || details.benchmark_promotion_blocker_summary !== undefined
    || details.benchmark_promotion_summary !== undefined
    || details.benchmark_promotion_gate_kind !== undefined

  return benchmarkPromotionState.gate_blockers.length > 0
    ? benchmarkPromotionState.gate_blockers.map((reason) =>
      `${usesCanonicalBenchmarkHints ? 'benchmark' : 'research_benchmark'}:${reason}`)
    : [`${usesCanonicalBenchmarkHints ? 'benchmark' : 'research_benchmark'}:out_of_sample_unproven`]
}

function resolvePredictionMarketBenchmarkLiveGateState(details: {
  benchmark_promotion_ready?: boolean | null
  research_benchmark_promotion_ready?: boolean | null
  benchmark_gate_blockers?: string[]
  research_benchmark_gate_blockers?: string[]
  benchmark_gate_live_block_reason?: string | null
  research_benchmark_live_block_reason?: string | null
  benchmark_promotion_blocker_summary?: string | null
  research_benchmark_promotion_blocker_summary?: string | null
  benchmark_promotion_summary?: string | null
  research_benchmark_promotion_summary?: string | null
  benchmark_promotion_gate_kind?: PredictionMarketsBenchmarkGateSummary['promotion_gate_kind'] | null
  research_promotion_gate_kind?: PredictionMarketsBenchmarkGateSummary['promotion_gate_kind'] | null
  benchmark_gate_blocks_live?: boolean | null
  execution_projection_selected_path?: string | null
  execution_projection?: PredictionMarketExecutionProjectionReport | null
  trade_intent_guard?: TradeIntentGuard | null
}): {
  blocks_live: boolean
  live_block_reason: string | null
  promotion_gate_kind: PredictionMarketsBenchmarkGateSummary['promotion_gate_kind'] | null
  promotion_ready: boolean
  promotion_blockers: string[]
} {
  const usesCanonicalBenchmarkPromotionHints =
    details.benchmark_promotion_ready !== undefined
    || details.benchmark_gate_blockers !== undefined
    || details.benchmark_promotion_blocker_summary !== undefined
    || details.benchmark_promotion_summary !== undefined
    || details.benchmark_promotion_gate_kind !== undefined
    || details.benchmark_gate_blocks_live !== undefined
    || details.benchmark_gate_live_block_reason !== undefined
  const hasStoredBenchmarkLiveGate =
    details.benchmark_gate_blocks_live !== undefined
    || details.benchmark_gate_live_block_reason !== undefined
  if (hasStoredBenchmarkLiveGate) {
    const benchmarkPromotionState = resolvePredictionMarketBenchmarkPromotionState(details)
    const storedLiveBlockReason = details.benchmark_gate_live_block_reason
      ?? (details.benchmark_gate_blocks_live === true
        ? benchmarkPromotionState.promotion_blocker_summary
        : null)
    return {
      blocks_live: details.benchmark_gate_blocks_live === true,
      live_block_reason: storedLiveBlockReason,
      promotion_gate_kind: benchmarkPromotionState.promotion_gate_kind,
      promotion_ready: benchmarkPromotionState.promotion_ready === true,
      promotion_blockers: resolvePredictionMarketBenchmarkPromotionBlockers(
        usesCanonicalBenchmarkPromotionHints
          ? {
            benchmark_gate_blockers: benchmarkPromotionState.gate_blockers,
            benchmark_promotion_ready: benchmarkPromotionState.promotion_ready,
            benchmark_promotion_blocker_summary: benchmarkPromotionState.promotion_blocker_summary,
            benchmark_promotion_gate_kind: benchmarkPromotionState.promotion_gate_kind,
          }
          : {
            research_benchmark_gate_blockers: benchmarkPromotionState.gate_blockers,
            research_benchmark_promotion_ready: benchmarkPromotionState.promotion_ready,
          },
        true,
      ),
    }
  }

  const benchmarkPromotionState = resolvePredictionMarketBenchmarkPromotionState(details)
  const selectedPath = details.execution_projection_selected_path
    ?? details.execution_projection?.selected_path
    ?? details.trade_intent_guard?.selected_path
    ?? null
  const promotionReady = benchmarkPromotionState.promotion_ready
  const blocksLive = selectedPath === 'live' && promotionReady !== true
  const liveBlockReason = blocksLive
    ? (
      details.benchmark_gate_live_block_reason
      ?? benchmarkPromotionState.promotion_blocker_summary
      ?? details.research_benchmark_live_block_reason
      ?? details.benchmark_promotion_summary
      ?? details.research_benchmark_promotion_summary
      ?? 'out_of_sample_unproven'
    )
    : null
  const promotionGateKind = benchmarkPromotionState.promotion_gate_kind
  const promotionBlockers = resolvePredictionMarketBenchmarkPromotionBlockers(
    usesCanonicalBenchmarkPromotionHints
      ? {
        benchmark_gate_blockers: benchmarkPromotionState.gate_blockers,
        benchmark_promotion_ready: promotionReady,
        benchmark_promotion_blocker_summary: benchmarkPromotionState.promotion_blocker_summary,
        benchmark_promotion_gate_kind: benchmarkPromotionState.promotion_gate_kind,
      }
      : {
        research_benchmark_gate_blockers: benchmarkPromotionState.gate_blockers,
        research_benchmark_promotion_ready: promotionReady,
      },
    true,
  )

  return {
    blocks_live: blocksLive,
    live_block_reason: liveBlockReason,
    promotion_gate_kind: promotionGateKind,
    promotion_ready: promotionReady === true,
    promotion_blockers: promotionBlockers,
  }
}

export async function listPredictionMarketUniverse(input: {
  venue?: PredictionMarketVenue
  limit?: number
  search?: string
}) {
  const venue = input.venue ?? 'polymarket'
  const adapter = getVenueAdapter(venue)

  return {
    venue,
    markets: await adapter.listMarkets({
      limit: input.limit,
      search: input.search,
    }),
  }
}

export async function advisePredictionMarket(input: AdviceExecutionInput) {
  const requestStartedAt = Date.now()
  const parsed = predictionMarketsAdviceRequestSchema.parse(input)
  const requestContract = resolvePredictionMarketAdviceRequestContract(input, parsed)
  const decisionPacket = parsed.decision_packet
  const decisionPacketHash = hashDecisionPacket(decisionPacket)
  const adapter = getVenueAdapter(parsed.venue)
  const actor = input.actor || 'system'
  let run: AgentRun | null = null
  let startedAt = ''

  try {
    const snapshotFetchStartedAt = Date.now()
    const snapshot = await adapter.buildSnapshot({
      marketId: parsed.market_id,
      slug: parsed.slug,
      historyLimit: requestContract.history_limit,
    })
    const evaluationHistoryResolution = resolvePredictionMarketEvaluationHistory({
      workspaceId: input.workspaceId,
      venue: parsed.venue,
      marketId: snapshot.market.market_id,
      providedHistory: parsed.evaluation_history,
      targetRecords: requestContract.history_limit,
    })
    const effectiveEvaluationHistory = evaluationHistoryResolution.evaluation_history
    const configHash = computeConfigHash({
      venue: parsed.venue,
      market_id: parsed.market_id,
      slug: parsed.slug,
      resolved_market_id: snapshot.market.market_id,
      request_mode: requestContract.request_mode,
      response_variant: requestContract.response_variant,
      strategy_profile: requestContract.strategy_profile,
      variant_tags: requestContract.variant_tags,
      thesis_probability: parsed.thesis_probability,
      thesis_rationale: parsed.thesis_rationale,
      min_edge_bps: parsed.min_edge_bps ?? DEFAULT_MIN_EDGE_BPS,
      max_spread_bps: parsed.max_spread_bps ?? DEFAULT_MAX_SPREAD_BPS,
      history_limit: requestContract.history_limit,
      timesfm_mode: requestContract.timesfm_mode,
      timesfm_lanes: requestContract.timesfm_lanes,
      evaluation_history_hash: effectiveEvaluationHistory.length > 0 ? hashText(JSON.stringify(effectiveEvaluationHistory)) : null,
      evaluation_history_source: evaluationHistoryResolution.source,
      research_signal_hash: parsed.research_signals ? hashText(JSON.stringify(parsed.research_signals)) : null,
      decision_packet_hash: decisionPacketHash,
      decision_packet_correlation_id: decisionPacket?.correlation_id ?? null,
    })
    const pipelineGuard = buildPredictionMarketPipelineGuard({
      venue: parsed.venue,
      mode: 'advise',
      snapshot,
      fetchLatencyMs: Date.now() - snapshotFetchStartedAt,
    })
    const deduplicatedSummary = findRecentPredictionMarketRunByConfig({
      workspaceId: input.workspaceId,
      venue: parsed.venue,
      marketId: snapshot.market.market_id,
      mode: 'advise',
      configHash,
      windowSec: getIdempotencyWindowSec(),
    })
    if (deduplicatedSummary) {
      const details = getPredictionMarketRunDetails(deduplicatedSummary.run_id, input.workspaceId)
      if (details) {
        const benchmarkGateOverride = resolvePredictionMarketSummaryBenchmarkGateOverride(
          deduplicatedSummary as Partial<PredictionMarketRunRuntimeHints>,
          details,
          resolvePredictionMarketStoredRunBenchmarkHintSource(
            deduplicatedSummary.run_id,
            deduplicatedSummary.workspace_id,
          ) ?? details,
        )
        const finalizedPipelineGuard = finalizePredictionMarketPipelineGuard({
          guard: pipelineGuard,
          decisionLatencyMs: Date.now() - requestStartedAt,
        })
        const runtimeGuard = evaluatePredictionMarketRuntimeGuard({
          venue: parsed.venue,
          mode: 'discovery',
          capabilities: finalizedPipelineGuard.venue_capabilities,
          health: finalizedPipelineGuard.venue_health,
          budgets: finalizedPipelineGuard.budgets,
        })
        const compliance = evaluatePredictionMarketCompliance({
          venue: parsed.venue,
          venue_type: snapshot.market.venue_type,
          mode: 'discovery',
          capabilities: finalizedPipelineGuard.venue_capabilities,
        })
        const storedArtifacts = extractStoredExecutionArtifacts(details)
        const normalizedCrossVenueIntelligence = normalizeCrossVenueIntelligence(
          storedArtifacts.cross_venue_intelligence,
        )
        const executionReadiness = storedArtifacts.execution_readiness ?? derivePredictionMarketExecutionReadiness({
          snapshot: storedArtifacts.snapshot,
          pipelineGuard: storedArtifacts.pipeline_guard ?? finalizedPipelineGuard,
          compliance: storedArtifacts.compliance ?? compliance,
          crossVenueIntelligence: normalizedCrossVenueIntelligence,
          microstructureLab: storedArtifacts.microstructure_lab,
          strategyDecision: storedArtifacts.strategy_decision_packet,
          resolutionAnomalyReport: storedArtifacts.resolution_anomaly_report,
        })
        const pathwaySupplementalArtifacts = buildPredictionMarketExecutionPathwaySupplementalArtifacts({
          evidencePackets: storedArtifacts.evidence_packets,
          decisionPacket: extractDecisionPacketFromEvidencePackets(storedArtifacts.evidence_packets),
          researchSidecar: storedArtifacts.research_sidecar,
          thesisProbability: extractManualThesisFromEvidencePackets(storedArtifacts.evidence_packets).thesisProbability,
          thesisRationale: extractManualThesisFromEvidencePackets(storedArtifacts.evidence_packets).thesisRationale,
        })
        let executionPathways = storedArtifacts.execution_pathways ?? derivePredictionMarketExecutionPathways({
          runId: deduplicatedSummary.run_id,
          snapshot: storedArtifacts.snapshot,
          resolutionPolicy: storedArtifacts.resolution_policy,
          forecast: storedArtifacts.forecast,
          recommendation: storedArtifacts.recommendation,
          executionReadiness,
          strategy_name: storedArtifacts.strategy_decision_packet?.strategy_family ?? storedArtifacts.strategy_candidate_packet?.strategy_family ?? null,
          market_regime_summary: storedArtifacts.strategy_decision_packet?.market_regime?.summary ?? storedArtifacts.strategy_candidate_packet?.market_regime?.summary ?? null,
          primary_strategy_summary: storedArtifacts.strategy_decision_packet?.summary ?? storedArtifacts.strategy_candidate_packet?.summary ?? null,
          strategy_summary: storedArtifacts.strategy_decision_packet?.summary ?? null,
          operator_thesis: pathwaySupplementalArtifacts.operator_thesis,
          research_pipeline_trace: pathwaySupplementalArtifacts.research_pipeline_trace,
        })
        if (executionPathways && (
          executionPathways.operator_thesis == null ||
          executionPathways.research_pipeline_trace == null
        )) {
          executionPathways = {
            ...executionPathways,
            operator_thesis: executionPathways.operator_thesis ?? pathwaySupplementalArtifacts.operator_thesis,
            research_pipeline_trace: executionPathways.research_pipeline_trace ?? pathwaySupplementalArtifacts.research_pipeline_trace,
          }
        }
        const executionProjection = storedArtifacts.execution_projection ?? derivePredictionMarketExecutionProjection({
          runId: deduplicatedSummary.run_id,
          snapshot: storedArtifacts.snapshot,
          forecast: storedArtifacts.forecast,
          resolutionPolicy: storedArtifacts.resolution_policy,
          recommendation: storedArtifacts.recommendation,
          executionReadiness,
          crossVenueIntelligence: normalizedCrossVenueIntelligence,
          strategy_name: storedArtifacts.strategy_decision_packet?.strategy_family ?? storedArtifacts.strategy_candidate_packet?.strategy_family ?? null,
          market_regime_summary: storedArtifacts.strategy_decision_packet?.market_regime?.summary ?? storedArtifacts.strategy_candidate_packet?.market_regime?.summary ?? null,
          primary_strategy_summary: storedArtifacts.strategy_decision_packet?.summary ?? storedArtifacts.strategy_candidate_packet?.summary ?? null,
          strategy_summary: storedArtifacts.strategy_decision_packet?.summary ?? null,
        })
        const shadowArbitrage = storedArtifacts.shadow_arbitrage ?? derivePredictionMarketShadowArbitrage(executionProjection)
        const benchmarkPromotionState = resolvePredictionMarketBenchmarkPromotionState(details)
        const executionSurfaces = derivePredictionMarketExecutionSurfaces({
          runId: deduplicatedSummary.run_id,
          snapshot: storedArtifacts.snapshot,
          recommendation: storedArtifacts.recommendation,
          pipelineGuard: storedArtifacts.pipeline_guard ?? finalizedPipelineGuard,
          runtimeGuard: storedArtifacts.runtime_guard ?? runtimeGuard,
          compliance: storedArtifacts.compliance ?? compliance,
          crossVenueIntelligence: normalizedCrossVenueIntelligence,
        executionReadiness,
        executionPathways,
        executionProjection,
        benchmarkPromotionReady: benchmarkPromotionState.promotion_ready,
        benchmarkPromotionGateKind: benchmarkPromotionState.promotion_gate_kind,
        benchmarkPromotionBlockerSummary: benchmarkPromotionState.promotion_blocker_summary,
      })
        const annotatedResearchSidecar = storedArtifacts.research_sidecar
          ? annotateMarketResearchSidecarComparisons(
            storedArtifacts.research_sidecar,
            storedArtifacts.forecast.probability_yes,
          )
          : null
        return {
          run: getRun(deduplicatedSummary.run_id, input.workspaceId),
          request_contract: requestContract,
          prediction_run: {
            ...deduplicatedSummary,
            ...buildPredictionMarketRunRuntimeHints({
              requestContract,
              researchSidecar: annotatedResearchSidecar,
              timesfmSidecar: storedArtifacts.timesfm_sidecar,
              forecast: storedArtifacts.forecast,
              recommendation: storedArtifacts.recommendation,
              venueFeedSurface: details.venue_feed_surface ?? null,
              executionPathways,
              executionProjection,
              shadowArbitrage,
              multiVenueExecution: executionSurfaces.multi_venue_execution,
              strategyCandidate: storedArtifacts.strategy_candidate_packet,
              strategyDecision: storedArtifacts.strategy_decision_packet,
              executionIntentPreview: storedArtifacts.execution_intent_preview,
              resolutionAnomalyReport: storedArtifacts.resolution_anomaly_report,
              strategyShadowSummary: storedArtifacts.strategy_shadow_summary,
              sourceAudit: storedArtifacts.source_audit,
              worldState: storedArtifacts.world_state,
              ticketPayload: storedArtifacts.ticket_payload,
              quantSignalBundle: storedArtifacts.quant_signal_bundle,
              decisionLedger: storedArtifacts.decision_ledger,
              calibrationReport: asJsonArtifact(storedArtifacts.calibration_report),
              resolvedHistory: storedArtifacts.resolved_history,
              costModelReport: storedArtifacts.cost_model_report,
              walkForwardReport: storedArtifacts.walk_forward_report,
              autopilotCycleSummary: asJsonArtifact(storedArtifacts.autopilot_cycle_summary),
              researchMemorySummary: storedArtifacts.research_memory_summary,
              benchmarkGateOverride,
            }),
          },
          reused_existing_run: true,
          snapshot: storedArtifacts.snapshot,
          resolution_policy: storedArtifacts.resolution_policy,
          evidence_packets: storedArtifacts.evidence_packets,
          forecast: storedArtifacts.forecast,
          recommendation: storedArtifacts.recommendation,
          market_events: storedArtifacts.market_events,
          market_positions: storedArtifacts.market_positions,
          strategy_candidate_packet: storedArtifacts.strategy_candidate_packet ?? undefined,
          strategy_decision_packet: storedArtifacts.strategy_decision_packet ?? undefined,
          strategy_shadow_summary_packet: storedArtifacts.strategy_shadow_summary ?? undefined,
          strategy_shadow_report: storedArtifacts.strategy_shadow_report ?? undefined,
          execution_intent_preview: storedArtifacts.execution_intent_preview ?? undefined,
          quote_pair_intent_preview: storedArtifacts.quote_pair_intent_preview ?? undefined,
          basket_intent_preview: storedArtifacts.basket_intent_preview ?? undefined,
          latency_reference_bundle: storedArtifacts.latency_reference_bundle ?? undefined,
          resolution_anomaly_report: storedArtifacts.resolution_anomaly_report ?? undefined,
          autonomous_agent_report: storedArtifacts.autonomous_agent_report ?? undefined,
          research_sidecar: annotatedResearchSidecar,
          timesfm_sidecar: storedArtifacts.timesfm_sidecar,
          microstructure_lab: storedArtifacts.microstructure_lab,
          cross_venue_intelligence: normalizedCrossVenueIntelligence,
          pipeline_guard: storedArtifacts.pipeline_guard ?? finalizedPipelineGuard,
          runtime_guard: storedArtifacts.runtime_guard ?? runtimeGuard,
          compliance: storedArtifacts.compliance ?? compliance,
          execution_readiness: executionReadiness,
          execution_pathways: executionPathways,
          execution_projection: executionProjection,
          shadow_arbitrage: shadowArbitrage,
          trade_intent_guard: executionSurfaces.trade_intent_guard,
          multi_venue_execution: executionSurfaces.multi_venue_execution,
        }
      }
    }

    startedAt = nowIso()
    run = createRun(buildInitialRun({
      actor,
      marketId: snapshot.market.market_id,
      slug: snapshot.market.slug,
      configHash,
      venue: parsed.venue,
      mode: 'advise',
      toolsAvailable: adapter.toolsAvailable,
    }), input.workspaceId)

    const resolutionPolicy = buildResolutionPolicy(snapshot)
    const preTimesFMCrossVenueIntelligence = await buildCrossVenueIntelligence({
      snapshot,
    })
    const preTimesFMMarketGraph = derivePredictionMarketMarketGraph({
      snapshot,
      crossVenueIntelligence: preTimesFMCrossVenueIntelligence,
    })
    const preTimesFMRegime = deriveMarketRegime({
      snapshot,
      market_graph: preTimesFMMarketGraph,
      cross_venue_summary: preTimesFMCrossVenueIntelligence.summary ?? null,
      microstructure_lab: null,
      research_sidecar: null,
      research_bridge: null,
      resolution_policy: resolutionPolicy,
      as_of_at: snapshot.captured_at,
    })
    let timesfmSidecar: PredictionMarketTimesFMSidecar | null = null
    if (shouldRunPredictionMarketTimesFM({
      mode: requestContract.timesfm_mode,
      lanes: requestContract.timesfm_lanes,
    })) {
      try {
        timesfmSidecar = runPredictionMarketTimesFMSidecar({
          runId: run.id,
          requestMode: requestContract.request_mode,
          mode: requestContract.timesfm_mode,
          lanes: requestContract.timesfm_lanes,
          snapshot,
          regime: preTimesFMRegime.disposition,
          crossVenueGapBps: deriveTimesFMCrossVenueGapBps(preTimesFMCrossVenueIntelligence),
        })
      } catch (error) {
        if (requestContract.timesfm_mode === 'required') {
          throw new PredictionMarketsError(
            `TimesFM required mode failed: ${error instanceof Error ? error.message : String(error)}`,
            {
              status: 503,
              code: 'timesfm_required_unavailable',
            },
          )
        }
        timesfmSidecar = buildPredictionMarketTimesFMFailureBundle({
          runId: run.id,
          snapshot,
          requestContract,
          reason: error instanceof Error ? error.message : String(error),
        })
      }
      if (requestContract.timesfm_mode === 'required' && !hasReadyTimesFMLanes(timesfmSidecar)) {
        throw new PredictionMarketsError(
          `TimesFM required mode did not produce a ready lane: ${timesfmSidecar?.health.summary ?? 'unavailable'}`,
          {
            status: 503,
            code: 'timesfm_required_unavailable',
          },
        )
      }
    }
    const researchSignals = parsed.research_signals ?? []
    const researchSidecar = researchSignals.length > 0 || timesfmSidecar
      ? buildMarketResearchSidecar({
        market: {
          market_id: snapshot.market.market_id,
          venue: snapshot.venue,
          question: snapshot.market.question,
          slug: snapshot.market.slug,
        },
        snapshot,
        signals: researchSignals,
        timesfmSidecar,
      })
      : null
    const thesisProbability = parsed.thesis_probability ??
      decisionPacket?.probability_estimate ??
      researchSidecar?.synthesis.manual_thesis_probability_hint
    const thesisRationale = parsed.thesis_rationale ??
      (decisionPacket ? buildDecisionPacketThesisRationale(decisionPacket) : undefined) ??
      researchSidecar?.synthesis.manual_thesis_rationale_hint
    const baseEvidencePackets = buildEvidencePackets({
      snapshot,
      thesisProbability,
      thesisRationale,
      decisionPacket,
    })
    const evidencePackets = researchSidecar
      ? [...baseEvidencePackets, ...researchSidecar.evidence_packets]
      : baseEvidencePackets
    const forecast = buildForecastPacket({
      snapshot,
      evidencePackets,
      thesisProbability,
      thesisRationale,
      researchSidecar,
    })
    const annotatedResearchSidecar = researchSidecar
      ? annotateMarketResearchSidecarComparisons(researchSidecar, forecast.probability_yes)
      : null
    const recommendation = buildRecommendationPacket({
      snapshot,
      resolutionPolicy,
      forecast,
      minEdgeBps: parsed.min_edge_bps,
      maxSpreadBps: parsed.max_spread_bps,
    })
    const finalizedPipelineGuard = finalizePredictionMarketPipelineGuard({
      guard: pipelineGuard,
      decisionLatencyMs: Date.now() - requestStartedAt,
    })
    const guardedRecommendation = applyPredictionMarketPipelineGuardrails({
      snapshot,
      resolutionPolicy,
      forecast,
      recommendation,
      guard: finalizedPipelineGuard,
      minEdgeBps: parsed.min_edge_bps,
      maxSpreadBps: parsed.max_spread_bps,
    })
    const runtimeGuard = evaluatePredictionMarketRuntimeGuard({
      venue: parsed.venue,
      mode: 'discovery',
      capabilities: finalizedPipelineGuard.venue_capabilities,
      health: finalizedPipelineGuard.venue_health,
      budgets: finalizedPipelineGuard.budgets,
    })
    const compliance = evaluatePredictionMarketCompliance({
      venue: parsed.venue,
      venue_type: snapshot.market.venue_type,
      mode: 'discovery',
      capabilities: finalizedPipelineGuard.venue_capabilities,
    })
    const crossVenueIntelligence = preTimesFMCrossVenueIntelligence
    const marketGraph = preTimesFMMarketGraph
    const microstructureLab = guardedRecommendation.action === 'bet'
      ? buildMicrostructureLabReport({
        snapshot,
        recommendation: guardedRecommendation,
        generated_at: nowIso(),
      })
      : null
    const strategyArtifacts = buildPredictionMarketStrategyRuntimeArtifacts({
      runId: run.id,
      snapshot,
      forecast,
      recommendation: guardedRecommendation,
      resolutionPolicy,
      evidencePackets,
      researchSidecar: annotatedResearchSidecar,
      researchBridge: null,
      crossVenueIntelligence,
      microstructureLab,
      marketGraph,
      pipelineGuard: finalizedPipelineGuard,
      strategyProfile: requestContract.strategy_profile,
      enabledStrategyFamilies: parsed.enabled_strategy_families,
    })
    const executionReadiness = derivePredictionMarketExecutionReadiness({
      snapshot,
      pipelineGuard: finalizedPipelineGuard,
      compliance,
      crossVenueIntelligence,
      microstructureLab,
      strategyDecision: strategyArtifacts.strategy_decision_packet,
      resolutionAnomalyReport: strategyArtifacts.resolution_anomaly_report,
    })
    const pathwaySupplementalArtifacts = buildPredictionMarketExecutionPathwaySupplementalArtifacts({
      evidencePackets,
      decisionPacket,
      researchSidecar: annotatedResearchSidecar,
      thesisProbability,
      thesisRationale,
    })
    const executionPathways = derivePredictionMarketExecutionPathways({
      runId: run.id,
      snapshot,
      resolutionPolicy,
      forecast,
      recommendation: guardedRecommendation,
      executionReadiness,
      strategy_name: strategyArtifacts.strategy_name,
      market_regime_summary: strategyArtifacts.market_regime_summary,
      primary_strategy_summary: strategyArtifacts.primary_strategy_summary,
      strategy_summary: strategyArtifacts.strategy_summary,
      strategy_trade_intent_preview: strategyArtifacts.strategy_trade_intent_preview,
      strategy_canonical_trade_intent_preview: strategyArtifacts.strategy_canonical_trade_intent_preview,
      strategy_shadow_summary: strategyArtifacts.strategy_shadow_summary?.summary ?? null,
      operator_thesis: pathwaySupplementalArtifacts.operator_thesis,
      research_pipeline_trace: pathwaySupplementalArtifacts.research_pipeline_trace,
    })
    const executionProjection = derivePredictionMarketExecutionProjection({
      runId: run.id,
      snapshot,
      forecast,
      resolutionPolicy,
      recommendation: guardedRecommendation,
      executionReadiness,
      crossVenueIntelligence,
      strategy_name: strategyArtifacts.strategy_name,
      market_regime_summary: strategyArtifacts.market_regime_summary,
      primary_strategy_summary: strategyArtifacts.primary_strategy_summary,
      strategy_summary: strategyArtifacts.strategy_summary,
      strategy_trade_intent_preview: strategyArtifacts.strategy_trade_intent_preview,
      strategy_canonical_trade_intent_preview: strategyArtifacts.strategy_canonical_trade_intent_preview,
      strategy_shadow_summary: strategyArtifacts.strategy_shadow_summary?.summary ?? null,
    })
    const shadowArbitrage = derivePredictionMarketShadowArbitrage(executionProjection)
    const benchmarkGateSummary = summarizePredictionMarketsBenchmarkGate({
      comparativeReport: annotatedResearchSidecar?.synthesis?.comparative_report ?? null,
      forecastProbabilityYesHint: forecast.probability_yes,
    })
    const executionSurfaces = derivePredictionMarketExecutionSurfaces({
      runId: run.id,
      snapshot,
      recommendation: guardedRecommendation,
      pipelineGuard: finalizedPipelineGuard,
      runtimeGuard,
      compliance,
      crossVenueIntelligence,
      executionReadiness,
      executionPathways,
      executionProjection,
      benchmarkPromotionReady: benchmarkGateSummary.promotion_ready,
      benchmarkPromotionGateKind: benchmarkGateSummary.promotion_gate_kind,
      benchmarkPromotionBlockerSummary: benchmarkGateSummary.promotion_blocker_summary,
    })
    const packetBundle = buildPredictionMarketPacketBundle({
      bundleId: `${run.id}:packet_bundle`,
      runId: run.id,
      venue: parsed.venue,
      marketId: snapshot.market.market_id,
      decisionPacket,
      strategyCandidatePacket: strategyArtifacts.strategy_candidate_packet,
      strategyDecisionPacket: strategyArtifacts.strategy_decision_packet,
      strategyShadowReport: strategyArtifacts.strategy_shadow_report,
      evidencePackets,
      forecastPacket: forecast,
      recommendationPacket: guardedRecommendation,
      researchBridge: null,
      marketEvents: undefined,
      marketPositions: undefined,
      paperSurface: undefined,
      replaySurface: undefined,
      orderTraceAudit: null,
      tradeIntentGuard: executionSurfaces.trade_intent_guard,
      multiVenueExecution: executionSurfaces.multi_venue_execution,
      benchmarkPromotionReady: benchmarkGateSummary.promotion_ready,
      benchmarkPromotionGateKind: benchmarkGateSummary.promotion_gate_kind,
      benchmarkPromotionBlockerSummary: benchmarkGateSummary.promotion_blocker_summary,
    })
    const researchMemoryCapture = capturePredictionMarketResearchMemory({
      runId: run.id,
      workspaceId: input.workspaceId,
      venue: parsed.venue,
      marketId: snapshot.market.market_id,
      marketSlug: snapshot.market.slug ?? null,
      recommendation: guardedRecommendation,
      forecast,
      researchSidecar: annotatedResearchSidecar,
      strategyName: strategyArtifacts.strategy_name ?? null,
      marketRegime: strategyArtifacts.strategy_decision_packet?.market_regime?.label ?? null,
      requestMode: requestContract.request_mode,
      responseVariant: requestContract.response_variant,
    })
    const researchMemoryEntry = researchMemoryCapture.entry
    const copiedPatternArtifacts = buildPredictionMarketCopiedPatternArtifacts({
      runId: run.id,
      venue: parsed.venue,
      snapshot,
      resolutionPolicy,
      evidencePackets,
      forecast,
      recommendation: guardedRecommendation,
      evaluationHistory: effectiveEvaluationHistory,
      evaluationHistorySourceSummary: evaluationHistoryResolution.source_summary,
      researchSidecar: annotatedResearchSidecar,
      strategyDecision: strategyArtifacts.strategy_decision_packet,
      marketGraph,
      researchMemorySummary: researchMemoryCapture.artifact,
    })

    const manifest = runManifestSchema.parse({
      run_id: run.id,
      mode: 'advise',
      venue: parsed.venue,
      market_id: snapshot.market.market_id,
      market_slug: snapshot.market.slug,
      actor,
      started_at: startedAt,
      completed_at: nowIso(),
      status: 'completed',
      config_hash: configHash,
    })
    const persisted = persistPredictionMarketExecution({
      workspaceId: input.workspaceId,
      runId: run.id,
      venue: parsed.venue,
      mode: 'advise',
      snapshot,
      resolutionPolicy,
      evidencePackets,
      forecast,
      recommendation: guardedRecommendation,
      sourceAudit: asJsonArtifact(copiedPatternArtifacts.source_audit),
      rulesLineage: asJsonArtifact(copiedPatternArtifacts.rules_lineage),
      catalystTimeline: asJsonArtifact(copiedPatternArtifacts.catalyst_timeline),
      worldState: asJsonArtifact(copiedPatternArtifacts.world_state),
      ticketPayload: asJsonArtifact(copiedPatternArtifacts.ticket_payload),
      quantSignalBundle: copiedPatternArtifacts.quant_signal_bundle,
      decisionLedger: copiedPatternArtifacts.decision_ledger,
      calibrationReport: asJsonArtifact(copiedPatternArtifacts.calibration_report),
      resolvedHistory: copiedPatternArtifacts.resolved_history,
      costModelReport: copiedPatternArtifacts.cost_model_report,
      walkForwardReport: copiedPatternArtifacts.walk_forward_report,
      autopilotCycleSummary: asJsonArtifact(copiedPatternArtifacts.autopilot_cycle_summary),
      researchMemorySummary: copiedPatternArtifacts.research_memory_summary ?? undefined,
      researchSidecar: annotatedResearchSidecar ?? undefined,
      timesfmSidecar: timesfmSidecar ? asJsonArtifact(timesfmSidecar) : undefined,
      microstructureLab: microstructureLab ?? undefined,
      crossVenueIntelligence,
      strategyCandidatePacket: strategyArtifacts.strategy_candidate_packet ?? undefined,
      strategyDecisionPacket: strategyArtifacts.strategy_decision_packet ?? undefined,
      strategyShadowSummary: strategyArtifacts.strategy_shadow_summary ?? undefined,
      strategyShadowReport: strategyArtifacts.strategy_shadow_report ?? undefined,
      executionIntentPreview: strategyArtifacts.execution_intent_preview ?? undefined,
      quotePairIntentPreview: strategyArtifacts.quote_pair_intent_preview ?? undefined,
      basketIntentPreview: strategyArtifacts.basket_intent_preview ?? undefined,
      latencyReferenceBundle: strategyArtifacts.latency_reference_bundle ?? undefined,
      resolutionAnomalyReport: strategyArtifacts.resolution_anomaly_report ?? undefined,
      autonomousAgentReport: strategyArtifacts.autonomous_agent_report ?? undefined,
      pipelineGuard: finalizedPipelineGuard,
      runtimeGuard,
      complianceReport: compliance,
      executionReadiness,
      executionPathways,
      executionProjection,
      shadowArbitrage: shadowArbitrage ?? undefined,
      tradeIntentGuard: executionSurfaces.trade_intent_guard,
      multiVenueExecution: executionSurfaces.multi_venue_execution,
      manifest,
    })
    const artifactRefs = persisted.artifactRefs
    const summary = persisted.summary

    updateRun(run.id, {
      status: 'completed',
      outcome: 'success',
      ended_at: nowIso(),
      duration_ms: Date.now() - Date.parse(startedAt),
      steps: buildCompletedSteps({
        startedAt,
        snapshot,
        recommendation: guardedRecommendation,
        snapshotToolName: adapter.snapshotToolName,
      }),
      tags: [
        'prediction_markets',
        'mode:advise',
        `request_mode:${requestContract.request_mode}`,
        `response_variant:${requestContract.response_variant}`,
        `venue:${parsed.venue}`,
        `recommendation:${guardedRecommendation.action}`,
        `pipeline:${finalizedPipelineGuard.status}`,
      ],
      metadata: {
        market_id: snapshot.market.market_id,
        market_slug: snapshot.market.slug,
        request_mode: requestContract.request_mode,
        response_variant: requestContract.response_variant,
        request_variant_tags: requestContract.variant_tags,
        strategy_profile_resolved: requestContract.strategy_profile,
        history_limit_resolved: requestContract.history_limit,
        research_memory_id: researchMemoryEntry?.memory_id ?? null,
        research_memory_provider_kind: researchMemoryEntry?.provider_kind ?? null,
        research_memory_summary: researchMemoryCapture.artifact?.summary ?? null,
        recommendation: guardedRecommendation.action,
        side: guardedRecommendation.side,
        confidence: guardedRecommendation.confidence,
        artifact_refs: artifactRefs,
        decision_packet_present: decisionPacket != null,
        decision_packet_correlation_id: decisionPacket?.correlation_id ?? null,
        decision_packet_probability_estimate: decisionPacket?.probability_estimate ?? null,
        pipeline_guard_status: finalizedPipelineGuard.status,
        pipeline_budget_breaches: finalizedPipelineGuard.breached_budgets,
        runtime_guard_verdict: runtimeGuard.verdict,
        compliance_status: compliance.status,
        snapshot_fetch_latency_ms: finalizedPipelineGuard.metrics.fetch_latency_ms,
        snapshot_staleness_ms: finalizedPipelineGuard.metrics.snapshot_staleness_ms,
        decision_latency_ms: finalizedPipelineGuard.metrics.decision_latency_ms,
        cross_venue_match_count: crossVenueIntelligence.evaluations.length,
        cross_venue_arbitrage_candidate_count: crossVenueIntelligence.arbitrage_candidates.length,
        cross_venue_manual_review_count: executionReadiness.cross_venue_summary.manual_review.length,
        cross_venue_comparison_only_count: executionReadiness.cross_venue_summary.comparison_only.length,
        cross_venue_blocking_reasons: executionReadiness.cross_venue_summary.blocking_reasons,
        microstructure_recommended_mode: microstructureLab?.summary.recommended_mode ?? null,
        microstructure_worst_case_severity: microstructureLab?.summary.worst_case_severity ?? null,
        microstructure_execution_quality_score: microstructureLab?.summary.execution_quality_score ?? null,
        execution_readiness_highest_safe_mode: executionReadiness.highest_safe_mode,
        execution_readiness_overall_verdict: executionReadiness.overall_verdict,
        execution_pathways_highest_actionable_mode: executionPathways.highest_actionable_mode,
        execution_pathways_actionable_modes: executionPathways.pathways
          .filter((pathway) => pathway.actionable)
          .map((pathway) => pathway.mode),
        execution_projection_requested_path: executionProjection.requested_path,
        execution_projection_selected_path: executionProjection.selected_path,
        execution_projection_gate_name: executionProjection.gate_name,
        execution_projection_preflight_only: executionProjection.preflight_only,
        execution_projection_verdict: executionProjection.verdict,
        execution_projection_manual_review_required: executionProjection.manual_review_required,
        execution_projection_ttl_ms: executionProjection.ttl_ms,
        execution_projection_highest_safe_requested_mode: executionProjection.highest_safe_requested_mode,
        execution_projection_recommended_effective_mode: executionProjection.recommended_effective_mode,
        execution_projection_preflight_summary: executionProjection.preflight_summary,
        primary_strategy: strategyArtifacts.strategy_name,
        market_regime: strategyArtifacts.strategy_decision_packet.market_regime?.label ?? null,
        strategy_counts: strategyArtifacts.strategy_counts,
        execution_intent_preview_kind: strategyArtifacts.execution_intent_preview?.preview_kind ?? null,
        strategy_shadow_summary: strategyArtifacts.strategy_shadow_summary?.summary ?? null,
        resolution_anomalies: strategyArtifacts.resolution_anomalies,
        source_audit_average_score: copiedPatternArtifacts.source_audit.average_score,
        world_state_action: copiedPatternArtifacts.world_state.recommended_action,
        quant_signal_viable_count: asNumber(copiedPatternArtifacts.quant_signal_bundle.viable_count),
        autopilot_cycle_health: copiedPatternArtifacts.autopilot_cycle_summary.overview.health,
        shadow_arbitrage_present: shadowArbitrage != null,
        shadow_arbitrage_shadow_edge_bps: shadowArbitrage?.summary.shadow_edge_bps ?? null,
        shadow_arbitrage_recommended_size_usd: shadowArbitrage?.summary.recommended_size_usd ?? null,
      },
    }, input.workspaceId)

    return {
      run: getRun(run.id, input.workspaceId),
      request_contract: requestContract,
      research_memory: researchMemoryEntry,
      prediction_run: {
        ...summary,
        ...buildPredictionMarketRunRuntimeHints({
          requestContract,
          researchSidecar: annotatedResearchSidecar,
          timesfmSidecar,
          forecast,
          recommendation: guardedRecommendation,
          venueFeedSurface: pipelineGuard.venue_feed_surface,
          executionPathways,
          executionProjection,
          shadowArbitrage,
          multiVenueExecution: executionSurfaces.multi_venue_execution,
          strategyCandidate: strategyArtifacts.strategy_candidate_packet,
          strategyDecision: strategyArtifacts.strategy_decision_packet,
          executionIntentPreview: strategyArtifacts.execution_intent_preview,
          resolutionAnomalyReport: strategyArtifacts.resolution_anomaly_report,
          strategyShadowSummary: strategyArtifacts.strategy_shadow_summary,
          sourceAudit: asJsonArtifact(copiedPatternArtifacts.source_audit),
          worldState: asJsonArtifact(copiedPatternArtifacts.world_state),
          ticketPayload: asJsonArtifact(copiedPatternArtifacts.ticket_payload),
          quantSignalBundle: copiedPatternArtifacts.quant_signal_bundle,
          decisionLedger: copiedPatternArtifacts.decision_ledger,
          calibrationReport: asJsonArtifact(copiedPatternArtifacts.calibration_report),
          resolvedHistory: copiedPatternArtifacts.resolved_history,
          costModelReport: copiedPatternArtifacts.cost_model_report,
          walkForwardReport: copiedPatternArtifacts.walk_forward_report,
          autopilotCycleSummary: asJsonArtifact(copiedPatternArtifacts.autopilot_cycle_summary),
          researchMemorySummary: copiedPatternArtifacts.research_memory_summary,
          benchmarkGateOverride: buildPredictionMarketBenchmarkGateOverrideFromSummary(benchmarkGateSummary),
        }),
    },
      snapshot,
      resolution_policy: resolutionPolicy,
      evidence_packets: evidencePackets,
      forecast,
      recommendation: guardedRecommendation,
      market_events: undefined,
      market_positions: undefined,
      source_audit_artifact: asJsonArtifact(copiedPatternArtifacts.source_audit),
      rules_lineage_artifact: asJsonArtifact(copiedPatternArtifacts.rules_lineage),
      catalyst_timeline_artifact: asJsonArtifact(copiedPatternArtifacts.catalyst_timeline),
      world_state_artifact: asJsonArtifact(copiedPatternArtifacts.world_state),
      ticket_payload_artifact: asJsonArtifact(copiedPatternArtifacts.ticket_payload),
      quant_signal_bundle: copiedPatternArtifacts.quant_signal_bundle,
      decision_ledger_artifact: copiedPatternArtifacts.decision_ledger,
      calibration_report_artifact: asJsonArtifact(copiedPatternArtifacts.calibration_report),
      resolved_history_artifact: copiedPatternArtifacts.resolved_history,
      cost_model_report_artifact: copiedPatternArtifacts.cost_model_report,
      walk_forward_report_artifact: copiedPatternArtifacts.walk_forward_report,
      autopilot_cycle_summary_artifact: asJsonArtifact(copiedPatternArtifacts.autopilot_cycle_summary),
      research_memory_summary_artifact: copiedPatternArtifacts.research_memory_summary,
      strategy_candidate_packet: strategyArtifacts.strategy_candidate_packet ?? undefined,
      strategy_decision_packet: strategyArtifacts.strategy_decision_packet ?? undefined,
      strategy_shadow_summary_packet: strategyArtifacts.strategy_shadow_summary ?? undefined,
      strategy_shadow_report: strategyArtifacts.strategy_shadow_report ?? undefined,
      execution_intent_preview: strategyArtifacts.execution_intent_preview ?? undefined,
      quote_pair_intent_preview: strategyArtifacts.quote_pair_intent_preview ?? undefined,
      basket_intent_preview: strategyArtifacts.basket_intent_preview ?? undefined,
      latency_reference_bundle: strategyArtifacts.latency_reference_bundle ?? undefined,
      resolution_anomaly_report: strategyArtifacts.resolution_anomaly_report ?? undefined,
      autonomous_agent_report: strategyArtifacts.autonomous_agent_report ?? undefined,
      microstructure_lab: microstructureLab ?? undefined,
      pipeline_guard: finalizedPipelineGuard,
      runtime_guard: runtimeGuard,
      compliance,
      cross_venue_intelligence: crossVenueIntelligence,
      execution_readiness: executionReadiness,
      execution_pathways: executionPathways,
      execution_projection: executionProjection,
      shadow_arbitrage: shadowArbitrage ?? undefined,
      trade_intent_guard: executionSurfaces.trade_intent_guard,
      multi_venue_execution: executionSurfaces.multi_venue_execution,
      research_sidecar: annotatedResearchSidecar,
      timesfm_sidecar: timesfmSidecar,
      packet_bundle: packetBundle,
      market_graph: marketGraph ?? undefined,
    }
  } catch (error) {
    if (run) {
      updateRun(run.id, {
        status: 'failed',
        outcome: 'failed',
        ended_at: nowIso(),
        duration_ms: startedAt ? Date.now() - Date.parse(startedAt) : undefined,
        error: error instanceof Error ? error.message : 'Unknown prediction markets error',
      }, input.workspaceId)
    }
    throw error
  }
}

export async function replayPredictionMarketRun(input: ReplayExecutionInput) {
  const requestStartedAt = Date.now()
  predictionMarketsReplayRequestSchema.parse({ run_id: input.runId })
  const existing = getPredictionMarketRunDetails(input.runId, input.workspaceId)

  if (!existing) {
    throw new PredictionMarketsError('Prediction market run not found', {
      status: 404,
      code: 'run_not_found',
    })
  }

  const stored = extractStoredExecutionArtifacts(existing)
  const snapshot = stored.snapshot
  const paperSurface = stored.paper_surface
  const replaySurface = stored.replay_surface
  const paperSurfaceCounters = extractReplaySurfaceCounters(paperSurface)
  const replaySurfaceCounters = extractReplaySurfaceCounters(replaySurface)
  const storedEvidence = stored.evidence_packets
  const previousRecommendation = stored.recommendation
  const pipelineGuard = buildPredictionMarketPipelineGuard({
    venue: snapshot.venue,
    mode: 'replay',
    snapshot,
    fetchLatencyMs: 0,
  })

  const decisionPacket = extractDecisionPacketFromEvidencePackets(storedEvidence)
  const manualThesis = extractManualThesisFromEvidencePackets(storedEvidence)
  const thesisProbability = manualThesis.thesisProbability ?? decisionPacket?.probability_estimate
  const thesisRationale = manualThesis.thesisRationale ??
    (decisionPacket ? buildDecisionPacketThesisRationale(decisionPacket) : undefined)
  const researchSidecar = stored.research_sidecar
  const timesfmSidecar = stored.timesfm_sidecar

  const actor = input.actor || 'system'
  const adapter = getVenueAdapter(snapshot.venue)
  const replayEvaluationHistoryResolution = resolvePredictionMarketEvaluationHistory({
    workspaceId: input.workspaceId,
    venue: snapshot.venue,
    marketId: snapshot.market.market_id,
    providedHistory: extractForecastEvaluationHistoryFromArtifacts(existing.artifacts),
    providedSource: 'stored_artifact',
    excludeRunIds: [input.runId],
  })
  const replayEvaluationHistory = replayEvaluationHistoryResolution.evaluation_history
  const configHash = computeConfigHash({
    replay_of: input.runId,
    thesis_probability: thesisProbability,
    decision_packet_hash: hashDecisionPacket(decisionPacket),
    evaluation_history_hash: replayEvaluationHistory.length > 0 ? hashText(JSON.stringify(replayEvaluationHistory)) : null,
    evaluation_history_source: replayEvaluationHistoryResolution.source,
  })
  const deduplicatedSummary = findRecentPredictionMarketRunByConfig({
    workspaceId: input.workspaceId,
    venue: snapshot.venue,
    marketId: snapshot.market.market_id,
    mode: 'replay',
    configHash,
    sourceRunId: input.runId,
    windowSec: getIdempotencyWindowSec(),
  })
  if (deduplicatedSummary) {
    const details = getPredictionMarketRunDetails(deduplicatedSummary.run_id, input.workspaceId)
    if (details) {
      const benchmarkGateOverride = resolvePredictionMarketSummaryBenchmarkGateOverride(
        deduplicatedSummary as Partial<PredictionMarketRunRuntimeHints>,
        details,
        resolvePredictionMarketStoredRunBenchmarkHintSource(
          deduplicatedSummary.run_id,
          deduplicatedSummary.workspace_id,
        ) ?? details,
      )
      const finalizedPipelineGuard = finalizePredictionMarketPipelineGuard({
        guard: pipelineGuard,
        decisionLatencyMs: Date.now() - requestStartedAt,
      })
      const runtimeGuard = evaluatePredictionMarketRuntimeGuard({
        venue: snapshot.venue,
        mode: 'discovery',
        capabilities: finalizedPipelineGuard.venue_capabilities,
        health: finalizedPipelineGuard.venue_health,
        budgets: finalizedPipelineGuard.budgets,
      })
      const compliance = evaluatePredictionMarketCompliance({
        venue: snapshot.venue,
        venue_type: snapshot.market.venue_type,
        mode: 'discovery',
        capabilities: finalizedPipelineGuard.venue_capabilities,
      })
      const storedArtifacts = extractStoredExecutionArtifacts(details)
      const normalizedCrossVenueIntelligence = normalizeCrossVenueIntelligence(
        storedArtifacts.cross_venue_intelligence,
      )
      const executionReadiness = storedArtifacts.execution_readiness ?? derivePredictionMarketExecutionReadiness({
        snapshot: storedArtifacts.snapshot,
        pipelineGuard: storedArtifacts.pipeline_guard ?? finalizedPipelineGuard,
        compliance: storedArtifacts.compliance ?? compliance,
        crossVenueIntelligence: normalizedCrossVenueIntelligence,
        microstructureLab: storedArtifacts.microstructure_lab,
        strategyDecision: storedArtifacts.strategy_decision_packet,
        resolutionAnomalyReport: storedArtifacts.resolution_anomaly_report,
      })
      const pathwaySupplementalArtifacts = buildPredictionMarketExecutionPathwaySupplementalArtifacts({
        evidencePackets: storedArtifacts.evidence_packets,
        decisionPacket,
        researchSidecar: storedArtifacts.research_sidecar,
        thesisProbability,
        thesisRationale,
      })
      let executionPathways = storedArtifacts.execution_pathways ?? derivePredictionMarketExecutionPathways({
        runId: deduplicatedSummary.run_id,
        snapshot: storedArtifacts.snapshot,
        resolutionPolicy: storedArtifacts.resolution_policy,
        forecast: storedArtifacts.forecast,
        recommendation: storedArtifacts.recommendation,
        executionReadiness,
        strategy_name: storedArtifacts.strategy_decision_packet?.strategy_family ?? storedArtifacts.strategy_candidate_packet?.strategy_family ?? null,
        market_regime_summary: storedArtifacts.strategy_decision_packet?.market_regime?.summary ?? storedArtifacts.strategy_candidate_packet?.market_regime?.summary ?? null,
        primary_strategy_summary: storedArtifacts.strategy_decision_packet?.summary ?? storedArtifacts.strategy_candidate_packet?.summary ?? null,
        strategy_summary: storedArtifacts.strategy_decision_packet?.summary ?? null,
        operator_thesis: pathwaySupplementalArtifacts.operator_thesis,
        research_pipeline_trace: pathwaySupplementalArtifacts.research_pipeline_trace,
      })
      if (executionPathways && (
        executionPathways.operator_thesis == null ||
        executionPathways.research_pipeline_trace == null
      )) {
        executionPathways = {
          ...executionPathways,
          operator_thesis: executionPathways.operator_thesis ?? pathwaySupplementalArtifacts.operator_thesis,
          research_pipeline_trace: executionPathways.research_pipeline_trace ?? pathwaySupplementalArtifacts.research_pipeline_trace,
        }
      }
      const executionProjection = storedArtifacts.execution_projection ?? derivePredictionMarketExecutionProjection({
        runId: deduplicatedSummary.run_id,
        snapshot: storedArtifacts.snapshot,
        forecast: storedArtifacts.forecast,
        resolutionPolicy: storedArtifacts.resolution_policy,
        recommendation: storedArtifacts.recommendation,
        executionReadiness,
        crossVenueIntelligence: normalizedCrossVenueIntelligence,
        strategy_name: storedArtifacts.strategy_decision_packet?.strategy_family ?? storedArtifacts.strategy_candidate_packet?.strategy_family ?? null,
        market_regime_summary: storedArtifacts.strategy_decision_packet?.market_regime?.summary ?? storedArtifacts.strategy_candidate_packet?.market_regime?.summary ?? null,
        primary_strategy_summary: storedArtifacts.strategy_decision_packet?.summary ?? storedArtifacts.strategy_candidate_packet?.summary ?? null,
        strategy_summary: storedArtifacts.strategy_decision_packet?.summary ?? null,
      })
      const shadowArbitrage = storedArtifacts.shadow_arbitrage ?? derivePredictionMarketShadowArbitrage(executionProjection)
      const benchmarkPromotionState = resolvePredictionMarketBenchmarkPromotionState(details)
      const executionSurfaces = derivePredictionMarketExecutionSurfaces({
        runId: deduplicatedSummary.run_id,
        snapshot: storedArtifacts.snapshot,
        recommendation: storedArtifacts.recommendation,
        pipelineGuard: storedArtifacts.pipeline_guard ?? finalizedPipelineGuard,
        runtimeGuard: storedArtifacts.runtime_guard ?? runtimeGuard,
        compliance: storedArtifacts.compliance ?? compliance,
        crossVenueIntelligence: normalizedCrossVenueIntelligence,
        executionReadiness,
        executionPathways,
        executionProjection,
        benchmarkPromotionReady: benchmarkPromotionState.promotion_ready,
        benchmarkPromotionGateKind: benchmarkPromotionState.promotion_gate_kind,
        benchmarkPromotionBlockerSummary: benchmarkPromotionState.promotion_blocker_summary,
      })
      const annotatedResearchSidecar = storedArtifacts.research_sidecar
        ? annotateMarketResearchSidecarComparisons(
          storedArtifacts.research_sidecar,
          storedArtifacts.forecast.probability_yes,
        )
        : null
      return {
        run: getRun(deduplicatedSummary.run_id, input.workspaceId),
        prediction_run: {
          ...deduplicatedSummary,
        ...buildPredictionMarketRunRuntimeHints({
          timesfmSidecar: storedArtifacts.timesfm_sidecar,
          researchSidecar: annotatedResearchSidecar,
          forecast: storedArtifacts.forecast,
          recommendation: storedArtifacts.recommendation,
          venueFeedSurface: details.venue_feed_surface ?? null,
          executionPathways,
          executionProjection,
          shadowArbitrage,
          multiVenueExecution: executionSurfaces.multi_venue_execution,
          strategyCandidate: storedArtifacts.strategy_candidate_packet,
          strategyDecision: storedArtifacts.strategy_decision_packet,
          executionIntentPreview: storedArtifacts.execution_intent_preview,
          resolutionAnomalyReport: storedArtifacts.resolution_anomaly_report,
          strategyShadowSummary: storedArtifacts.strategy_shadow_summary,
          benchmarkGateOverride,
        }),
        },
        reused_existing_run: true,
        snapshot: storedArtifacts.snapshot,
        resolution_policy: storedArtifacts.resolution_policy,
        evidence_packets: storedArtifacts.evidence_packets,
        forecast: storedArtifacts.forecast,
        recommendation: storedArtifacts.recommendation,
        market_events: storedArtifacts.market_events,
        market_positions: storedArtifacts.market_positions,
        strategy_candidate_packet: storedArtifacts.strategy_candidate_packet ?? undefined,
        strategy_decision_packet: storedArtifacts.strategy_decision_packet ?? undefined,
        strategy_shadow_summary_packet: storedArtifacts.strategy_shadow_summary ?? undefined,
        strategy_shadow_report: storedArtifacts.strategy_shadow_report ?? undefined,
        execution_intent_preview: storedArtifacts.execution_intent_preview ?? undefined,
        quote_pair_intent_preview: storedArtifacts.quote_pair_intent_preview ?? undefined,
        basket_intent_preview: storedArtifacts.basket_intent_preview ?? undefined,
        latency_reference_bundle: storedArtifacts.latency_reference_bundle ?? undefined,
        resolution_anomaly_report: storedArtifacts.resolution_anomaly_report ?? undefined,
        autonomous_agent_report: storedArtifacts.autonomous_agent_report ?? undefined,
        paper_surface: storedArtifacts.paper_surface ?? null,
        replay_surface: storedArtifacts.replay_surface ?? null,
        paper_no_trade_zone_count: extractReplaySurfaceCounters(storedArtifacts.paper_surface).no_trade_zone_count,
        paper_no_trade_zone_rate: extractReplaySurfaceCounters(storedArtifacts.paper_surface).no_trade_zone_rate,
        replay_no_trade_leg_count: extractReplaySurfaceCounters(storedArtifacts.replay_surface).no_trade_leg_count,
        replay_no_trade_leg_rate: extractReplaySurfaceCounters(storedArtifacts.replay_surface).no_trade_leg_rate,
        research_sidecar: storedArtifacts.research_sidecar,
        timesfm_sidecar: storedArtifacts.timesfm_sidecar,
        microstructure_lab: storedArtifacts.microstructure_lab,
        cross_venue_intelligence: normalizedCrossVenueIntelligence,
        pipeline_guard: storedArtifacts.pipeline_guard ?? finalizedPipelineGuard,
        runtime_guard: storedArtifacts.runtime_guard ?? runtimeGuard,
        compliance: storedArtifacts.compliance ?? compliance,
        execution_readiness: executionReadiness,
        execution_pathways: executionPathways,
        execution_projection: executionProjection,
        shadow_arbitrage: shadowArbitrage,
        trade_intent_guard: executionSurfaces.trade_intent_guard,
        multi_venue_execution: executionSurfaces.multi_venue_execution,
      }
    }
  }

  const replayRun = createRun({
    ...buildInitialRun({
      actor,
      marketId: snapshot.market.market_id,
      slug: snapshot.market.slug,
      configHash,
      venue: snapshot.venue,
      mode: 'replay',
      toolsAvailable: adapter.toolsAvailable,
    }),
    parent_run_id: input.runId,
    tags: ['prediction_markets', 'mode:replay', `venue:${snapshot.venue}`],
  }, input.workspaceId)

  const resolutionPolicy = buildResolutionPolicy(snapshot)
  const baseEvidencePackets = buildEvidencePackets({
    snapshot,
    thesisProbability,
    thesisRationale,
    decisionPacket,
  })
  const evidencePackets = researchSidecar
    ? [...baseEvidencePackets, ...researchSidecar.evidence_packets]
    : baseEvidencePackets
  const forecast = buildForecastPacket({
    snapshot,
    evidencePackets,
    thesisProbability,
    thesisRationale,
    researchSidecar,
    researchBridge: stored.research_bridge,
  })
  const annotatedResearchSidecar = researchSidecar
    ? annotateMarketResearchSidecarComparisons(researchSidecar, forecast.probability_yes)
    : null
  const recommendation = buildRecommendationPacket({
    snapshot,
    resolutionPolicy,
    forecast,
  })
  const finalizedPipelineGuard = finalizePredictionMarketPipelineGuard({
    guard: pipelineGuard,
    decisionLatencyMs: Date.now() - requestStartedAt,
  })
  const guardedRecommendation = applyPredictionMarketPipelineGuardrails({
    snapshot,
    resolutionPolicy,
    forecast,
    recommendation,
    guard: finalizedPipelineGuard,
  })
  const runtimeGuard = evaluatePredictionMarketRuntimeGuard({
    venue: snapshot.venue,
    mode: 'discovery',
    capabilities: finalizedPipelineGuard.venue_capabilities,
    health: finalizedPipelineGuard.venue_health,
    budgets: finalizedPipelineGuard.budgets,
  })
  const compliance = evaluatePredictionMarketCompliance({
    venue: snapshot.venue,
    venue_type: snapshot.market.venue_type,
    mode: 'discovery',
    capabilities: finalizedPipelineGuard.venue_capabilities,
  })
  const crossVenueIntelligence = await buildCrossVenueIntelligence({
    snapshot,
  })
  const marketGraph = derivePredictionMarketMarketGraph({
    snapshot,
    crossVenueIntelligence,
  })
  const microstructureLab = guardedRecommendation.action === 'bet'
    ? buildMicrostructureLabReport({
      snapshot,
      recommendation: guardedRecommendation,
      generated_at: nowIso(),
    })
    : null
  const strategyArtifacts = buildPredictionMarketStrategyRuntimeArtifacts({
    runId: replayRun.id,
    snapshot,
    forecast,
    recommendation: guardedRecommendation,
    resolutionPolicy,
    evidencePackets,
    researchSidecar: annotatedResearchSidecar,
    researchBridge: stored.research_bridge,
    crossVenueIntelligence,
    microstructureLab,
    marketGraph,
    pipelineGuard: finalizedPipelineGuard,
    strategyProfile: 'hybrid',
    enabledStrategyFamilies: DEFAULT_ENABLED_STRATEGY_FAMILIES,
  })
  const executionReadiness = derivePredictionMarketExecutionReadiness({
    snapshot,
    pipelineGuard: finalizedPipelineGuard,
    compliance,
    crossVenueIntelligence,
    microstructureLab,
    strategyDecision: strategyArtifacts.strategy_decision_packet,
    resolutionAnomalyReport: strategyArtifacts.resolution_anomaly_report,
  })
  const pathwaySupplementalArtifacts = buildPredictionMarketExecutionPathwaySupplementalArtifacts({
    evidencePackets: storedEvidence,
    decisionPacket,
    researchSidecar,
    thesisProbability,
    thesisRationale,
  })
  const executionPathways = derivePredictionMarketExecutionPathways({
    runId: replayRun.id,
    snapshot,
    resolutionPolicy,
    forecast,
    recommendation: guardedRecommendation,
    executionReadiness,
    strategy_name: strategyArtifacts.strategy_name,
    market_regime_summary: strategyArtifacts.market_regime_summary,
    primary_strategy_summary: strategyArtifacts.primary_strategy_summary,
    strategy_summary: strategyArtifacts.strategy_summary,
    strategy_trade_intent_preview: strategyArtifacts.strategy_trade_intent_preview,
    strategy_canonical_trade_intent_preview: strategyArtifacts.strategy_canonical_trade_intent_preview,
    strategy_shadow_summary: strategyArtifacts.strategy_shadow_summary?.summary ?? null,
    operator_thesis: pathwaySupplementalArtifacts.operator_thesis,
    research_pipeline_trace: pathwaySupplementalArtifacts.research_pipeline_trace,
  })
  const executionProjection = derivePredictionMarketExecutionProjection({
    runId: replayRun.id,
    snapshot,
    forecast,
    resolutionPolicy,
    recommendation: guardedRecommendation,
    executionReadiness,
    crossVenueIntelligence,
    strategy_name: strategyArtifacts.strategy_name,
    market_regime_summary: strategyArtifacts.market_regime_summary,
    primary_strategy_summary: strategyArtifacts.primary_strategy_summary,
    strategy_summary: strategyArtifacts.strategy_summary,
    strategy_trade_intent_preview: strategyArtifacts.strategy_trade_intent_preview,
    strategy_canonical_trade_intent_preview: strategyArtifacts.strategy_canonical_trade_intent_preview,
    strategy_shadow_summary: strategyArtifacts.strategy_shadow_summary?.summary ?? null,
  })
  const shadowArbitrage = derivePredictionMarketShadowArbitrage(executionProjection)
  const benchmarkGateSummary = summarizePredictionMarketsBenchmarkGate({
    comparativeReport: annotatedResearchSidecar?.synthesis?.comparative_report ?? null,
    forecastProbabilityYesHint: forecast.probability_yes,
  })
  const executionSurfaces = derivePredictionMarketExecutionSurfaces({
    runId: replayRun.id,
    snapshot,
    recommendation: guardedRecommendation,
    pipelineGuard: finalizedPipelineGuard,
    runtimeGuard,
    compliance,
    crossVenueIntelligence,
    executionReadiness,
    executionPathways,
    executionProjection,
    benchmarkPromotionReady: benchmarkGateSummary.promotion_ready,
    benchmarkPromotionGateKind: benchmarkGateSummary.promotion_gate_kind,
    benchmarkPromotionBlockerSummary: benchmarkGateSummary.promotion_blocker_summary,
  })
  const packetBundle = buildPredictionMarketPacketBundle({
    bundleId: `${replayRun.id}:packet_bundle`,
    runId: replayRun.id,
    venue: snapshot.venue,
    marketId: snapshot.market.market_id,
    decisionPacket,
    strategyCandidatePacket: strategyArtifacts.strategy_candidate_packet,
    strategyDecisionPacket: strategyArtifacts.strategy_decision_packet,
    strategyShadowReport: strategyArtifacts.strategy_shadow_report,
    evidencePackets,
    forecastPacket: forecast,
    recommendationPacket: guardedRecommendation,
    researchBridge: stored.research_bridge,
    marketEvents: stored.market_events,
    marketPositions: stored.market_positions,
    paperSurface: paperSurface,
    replaySurface: replaySurface,
    orderTraceAudit: stored.order_trace_audit,
    tradeIntentGuard: executionSurfaces.trade_intent_guard,
    multiVenueExecution: executionSurfaces.multi_venue_execution,
    benchmarkPromotionReady: benchmarkGateSummary.promotion_ready,
    benchmarkPromotionGateKind: benchmarkGateSummary.promotion_gate_kind,
    benchmarkPromotionBlockerSummary: benchmarkGateSummary.promotion_blocker_summary,
  })
  const researchMemoryCapture = capturePredictionMarketResearchMemory({
    runId: replayRun.id,
    workspaceId: input.workspaceId,
    venue: snapshot.venue,
    marketId: snapshot.market.market_id,
    marketSlug: snapshot.market.slug ?? null,
    recommendation: guardedRecommendation,
    forecast,
    researchSidecar: annotatedResearchSidecar,
    strategyName: strategyArtifacts.strategy_name ?? null,
    marketRegime: strategyArtifacts.strategy_decision_packet?.market_regime?.label ?? null,
  })
  const copiedPatternArtifacts = buildPredictionMarketCopiedPatternArtifacts({
    runId: replayRun.id,
    venue: snapshot.venue,
    snapshot,
    resolutionPolicy,
    evidencePackets,
    forecast,
    recommendation: guardedRecommendation,
    evaluationHistory: replayEvaluationHistory,
    evaluationHistorySourceSummary: replayEvaluationHistoryResolution.source_summary,
    researchSidecar: annotatedResearchSidecar,
    strategyDecision: strategyArtifacts.strategy_decision_packet,
    marketGraph,
    researchMemorySummary: researchMemoryCapture.artifact,
  })

  const manifest = runManifestSchema.parse({
    run_id: replayRun.id,
    source_run_id: input.runId,
    mode: 'replay',
    venue: snapshot.venue,
    market_id: snapshot.market.market_id,
    market_slug: snapshot.market.slug,
    actor,
    started_at: replayRun.started_at,
    completed_at: nowIso(),
    status: 'completed',
    config_hash: configHash,
  })
  const persisted = persistPredictionMarketExecution({
    workspaceId: input.workspaceId,
    runId: replayRun.id,
    sourceRunId: input.runId,
    venue: snapshot.venue,
    mode: 'replay',
    snapshot,
    resolutionPolicy,
    evidencePackets,
    forecast,
    recommendation: guardedRecommendation,
    sourceAudit: asJsonArtifact(copiedPatternArtifacts.source_audit),
    rulesLineage: asJsonArtifact(copiedPatternArtifacts.rules_lineage),
    catalystTimeline: asJsonArtifact(copiedPatternArtifacts.catalyst_timeline),
    worldState: asJsonArtifact(copiedPatternArtifacts.world_state),
    ticketPayload: asJsonArtifact(copiedPatternArtifacts.ticket_payload),
    quantSignalBundle: copiedPatternArtifacts.quant_signal_bundle,
    decisionLedger: copiedPatternArtifacts.decision_ledger,
    calibrationReport: asJsonArtifact(copiedPatternArtifacts.calibration_report),
    resolvedHistory: copiedPatternArtifacts.resolved_history,
    costModelReport: copiedPatternArtifacts.cost_model_report,
    walkForwardReport: copiedPatternArtifacts.walk_forward_report,
    autopilotCycleSummary: asJsonArtifact(copiedPatternArtifacts.autopilot_cycle_summary),
    researchMemorySummary: copiedPatternArtifacts.research_memory_summary ?? undefined,
    researchSidecar: annotatedResearchSidecar ?? undefined,
    timesfmSidecar: timesfmSidecar ? asJsonArtifact(timesfmSidecar) : undefined,
    microstructureLab: microstructureLab ?? undefined,
    crossVenueIntelligence,
    strategyCandidatePacket: strategyArtifacts.strategy_candidate_packet ?? undefined,
    strategyDecisionPacket: strategyArtifacts.strategy_decision_packet ?? undefined,
    strategyShadowSummary: strategyArtifacts.strategy_shadow_summary ?? undefined,
    strategyShadowReport: strategyArtifacts.strategy_shadow_report ?? undefined,
    executionIntentPreview: strategyArtifacts.execution_intent_preview ?? undefined,
    quotePairIntentPreview: strategyArtifacts.quote_pair_intent_preview ?? undefined,
    basketIntentPreview: strategyArtifacts.basket_intent_preview ?? undefined,
    latencyReferenceBundle: strategyArtifacts.latency_reference_bundle ?? undefined,
    resolutionAnomalyReport: strategyArtifacts.resolution_anomaly_report ?? undefined,
    autonomousAgentReport: strategyArtifacts.autonomous_agent_report ?? undefined,
    pipelineGuard: finalizedPipelineGuard,
    runtimeGuard,
    complianceReport: compliance,
    executionReadiness,
    executionPathways,
    executionProjection,
    shadowArbitrage: shadowArbitrage ?? undefined,
    tradeIntentGuard: executionSurfaces.trade_intent_guard,
    multiVenueExecution: executionSurfaces.multi_venue_execution,
    manifest,
  })
  const artifactRefs = persisted.artifactRefs
  const summary = persisted.summary

  updateRun(replayRun.id, {
    status: 'completed',
    outcome: 'success',
    ended_at: nowIso(),
    duration_ms: Date.now() - Date.parse(replayRun.started_at),
    steps: buildCompletedSteps({
      startedAt: replayRun.started_at,
      snapshot,
      recommendation: guardedRecommendation,
      snapshotToolName: adapter.snapshotToolName,
    }),
    tags: [
      'prediction_markets',
      'mode:replay',
      `venue:${snapshot.venue}`,
      `recommendation:${guardedRecommendation.action}`,
      `pipeline:${finalizedPipelineGuard.status}`,
    ],
    metadata: {
      source_run_id: input.runId,
      research_memory_summary: researchMemoryCapture.artifact?.summary ?? null,
      replay_consistent: guardedRecommendation.action === previousRecommendation.action &&
        guardedRecommendation.side === previousRecommendation.side,
      artifact_refs: artifactRefs,
      decision_packet_present: decisionPacket != null,
      decision_packet_correlation_id: decisionPacket?.correlation_id ?? null,
      decision_packet_probability_estimate: decisionPacket?.probability_estimate ?? null,
      pipeline_guard_status: finalizedPipelineGuard.status,
      pipeline_budget_breaches: finalizedPipelineGuard.breached_budgets,
      runtime_guard_verdict: runtimeGuard.verdict,
      compliance_status: compliance.status,
      snapshot_fetch_latency_ms: finalizedPipelineGuard.metrics.fetch_latency_ms,
      snapshot_staleness_ms: finalizedPipelineGuard.metrics.snapshot_staleness_ms,
      decision_latency_ms: finalizedPipelineGuard.metrics.decision_latency_ms,
      cross_venue_match_count: crossVenueIntelligence.evaluations.length,
      cross_venue_arbitrage_candidate_count: crossVenueIntelligence.arbitrage_candidates.length,
      cross_venue_manual_review_count: executionReadiness.cross_venue_summary.manual_review.length,
      cross_venue_comparison_only_count: executionReadiness.cross_venue_summary.comparison_only.length,
      cross_venue_blocking_reasons: executionReadiness.cross_venue_summary.blocking_reasons,
      microstructure_recommended_mode: microstructureLab?.summary.recommended_mode ?? null,
      microstructure_worst_case_severity: microstructureLab?.summary.worst_case_severity ?? null,
      microstructure_execution_quality_score: microstructureLab?.summary.execution_quality_score ?? null,
      execution_readiness_highest_safe_mode: executionReadiness.highest_safe_mode,
      execution_readiness_overall_verdict: executionReadiness.overall_verdict,
      execution_pathways_highest_actionable_mode: executionPathways.highest_actionable_mode,
      execution_pathways_actionable_modes: executionPathways.pathways
        .filter((pathway) => pathway.actionable)
        .map((pathway) => pathway.mode),
      execution_projection_requested_path: executionProjection.requested_path,
      execution_projection_selected_path: executionProjection.selected_path,
      execution_projection_gate_name: executionProjection.gate_name,
      execution_projection_preflight_only: executionProjection.preflight_only,
      execution_projection_verdict: executionProjection.verdict,
      execution_projection_manual_review_required: executionProjection.manual_review_required,
      execution_projection_ttl_ms: executionProjection.ttl_ms,
      execution_projection_highest_safe_requested_mode: executionProjection.highest_safe_requested_mode,
      execution_projection_recommended_effective_mode: executionProjection.recommended_effective_mode,
      execution_projection_preflight_summary: executionProjection.preflight_summary,
      primary_strategy: strategyArtifacts.strategy_name,
      market_regime: strategyArtifacts.strategy_decision_packet.market_regime?.label ?? null,
      strategy_counts: strategyArtifacts.strategy_counts,
      execution_intent_preview_kind: strategyArtifacts.execution_intent_preview?.preview_kind ?? null,
      strategy_shadow_summary: strategyArtifacts.strategy_shadow_summary?.summary ?? null,
      resolution_anomalies: strategyArtifacts.resolution_anomalies,
      source_audit_average_score: copiedPatternArtifacts.source_audit.average_score,
      world_state_action: copiedPatternArtifacts.world_state.recommended_action,
      quant_signal_viable_count: asNumber(copiedPatternArtifacts.quant_signal_bundle.viable_count),
      autopilot_cycle_health: copiedPatternArtifacts.autopilot_cycle_summary.overview.health,
      shadow_arbitrage_present: shadowArbitrage != null,
      shadow_arbitrage_shadow_edge_bps: shadowArbitrage?.summary.shadow_edge_bps ?? null,
      shadow_arbitrage_recommended_size_usd: shadowArbitrage?.summary.recommended_size_usd ?? null,
    },
  }, input.workspaceId)

  return {
    run: getRun(replayRun.id, input.workspaceId),
      prediction_run: {
        ...summary,
        ...buildPredictionMarketRunRuntimeHints({
          timesfmSidecar,
          researchSidecar: annotatedResearchSidecar,
          forecast,
        recommendation: guardedRecommendation,
        venueFeedSurface: pipelineGuard.venue_feed_surface,
        executionPathways,
        executionProjection,
        shadowArbitrage,
        multiVenueExecution: executionSurfaces.multi_venue_execution,
        strategyCandidate: strategyArtifacts.strategy_candidate_packet,
        strategyDecision: strategyArtifacts.strategy_decision_packet,
        executionIntentPreview: strategyArtifacts.execution_intent_preview,
        resolutionAnomalyReport: strategyArtifacts.resolution_anomaly_report,
        strategyShadowSummary: strategyArtifacts.strategy_shadow_summary,
        sourceAudit: asJsonArtifact(copiedPatternArtifacts.source_audit),
        worldState: asJsonArtifact(copiedPatternArtifacts.world_state),
        ticketPayload: asJsonArtifact(copiedPatternArtifacts.ticket_payload),
        quantSignalBundle: copiedPatternArtifacts.quant_signal_bundle,
        decisionLedger: copiedPatternArtifacts.decision_ledger,
        calibrationReport: asJsonArtifact(copiedPatternArtifacts.calibration_report),
        resolvedHistory: copiedPatternArtifacts.resolved_history,
        costModelReport: copiedPatternArtifacts.cost_model_report,
        walkForwardReport: copiedPatternArtifacts.walk_forward_report,
        autopilotCycleSummary: asJsonArtifact(copiedPatternArtifacts.autopilot_cycle_summary),
        researchMemorySummary: copiedPatternArtifacts.research_memory_summary,
          benchmarkGateOverride: buildPredictionMarketBenchmarkGateOverrideFromSummary(benchmarkGateSummary),
        }),
        ...buildPredictionMarketBenchmarkGateOverride(existing),
    },
    snapshot,
    resolution_policy: resolutionPolicy,
    evidence_packets: evidencePackets,
    forecast,
    recommendation: guardedRecommendation,
    market_events: undefined,
    market_positions: undefined,
    source_audit_artifact: asJsonArtifact(copiedPatternArtifacts.source_audit),
    rules_lineage_artifact: asJsonArtifact(copiedPatternArtifacts.rules_lineage),
    catalyst_timeline_artifact: asJsonArtifact(copiedPatternArtifacts.catalyst_timeline),
    world_state_artifact: asJsonArtifact(copiedPatternArtifacts.world_state),
    ticket_payload_artifact: asJsonArtifact(copiedPatternArtifacts.ticket_payload),
    quant_signal_bundle: copiedPatternArtifacts.quant_signal_bundle,
    decision_ledger_artifact: copiedPatternArtifacts.decision_ledger,
    calibration_report_artifact: asJsonArtifact(copiedPatternArtifacts.calibration_report),
    resolved_history_artifact: copiedPatternArtifacts.resolved_history,
    cost_model_report_artifact: copiedPatternArtifacts.cost_model_report,
    walk_forward_report_artifact: copiedPatternArtifacts.walk_forward_report,
    autopilot_cycle_summary_artifact: asJsonArtifact(copiedPatternArtifacts.autopilot_cycle_summary),
    research_memory_summary_artifact: copiedPatternArtifacts.research_memory_summary,
    timesfm_sidecar: timesfmSidecar,
    strategy_candidate_packet: strategyArtifacts.strategy_candidate_packet ?? undefined,
    strategy_decision_packet: strategyArtifacts.strategy_decision_packet ?? undefined,
    strategy_shadow_summary_packet: strategyArtifacts.strategy_shadow_summary ?? undefined,
    strategy_shadow_report: strategyArtifacts.strategy_shadow_report ?? undefined,
    execution_intent_preview: strategyArtifacts.execution_intent_preview ?? undefined,
    quote_pair_intent_preview: strategyArtifacts.quote_pair_intent_preview ?? undefined,
    basket_intent_preview: strategyArtifacts.basket_intent_preview ?? undefined,
    latency_reference_bundle: strategyArtifacts.latency_reference_bundle ?? undefined,
    resolution_anomaly_report: strategyArtifacts.resolution_anomaly_report ?? undefined,
    autonomous_agent_report: strategyArtifacts.autonomous_agent_report ?? undefined,
    paper_surface: paperSurface ?? null,
    replay_surface: replaySurface ?? null,
    paper_no_trade_zone_count: paperSurfaceCounters.no_trade_zone_count,
    paper_no_trade_zone_rate: paperSurfaceCounters.no_trade_zone_rate,
    replay_no_trade_leg_count: replaySurfaceCounters.no_trade_leg_count,
    replay_no_trade_leg_rate: replaySurfaceCounters.no_trade_leg_rate,
    microstructure_lab: microstructureLab ?? undefined,
    pipeline_guard: finalizedPipelineGuard,
    runtime_guard: runtimeGuard,
    compliance,
    cross_venue_intelligence: crossVenueIntelligence,
    execution_readiness: executionReadiness,
    execution_pathways: executionPathways,
    execution_projection: executionProjection,
    shadow_arbitrage: shadowArbitrage ?? undefined,
    trade_intent_guard: executionSurfaces.trade_intent_guard,
    multi_venue_execution: executionSurfaces.multi_venue_execution,
    research_sidecar: annotatedResearchSidecar,
    packet_bundle: packetBundle,
    market_graph: marketGraph ?? undefined,
  }
}

export function getPredictionMarketRunDetails(
  runId: string,
  workspaceId: number,
): PredictionMarketRunDetailsWithArtifactAudit | null {
  const details = getStoredPredictionMarketRunDetails(runId, workspaceId)
  if (!details) return null

  const enrichedDetails = enrichStoredPredictionMarketRunDetails(details)
  const benchmarkAwareDetailsInput: Partial<PredictionMarketRunRuntimeHints> & {
    trade_intent_guard?: TradeIntentGuard | null
    execution_projection?: PredictionMarketExecutionProjectionReport | null
  } = enrichedDetails as Partial<PredictionMarketRunRuntimeHints> & {
    trade_intent_guard?: TradeIntentGuard | null
    execution_projection?: PredictionMarketExecutionProjectionReport | null
  }
  const benchmarkAwareTradeIntentGuard = rehydratePredictionMarketTradeIntentGuardForBenchmarkPromotion(
    benchmarkAwareDetailsInput.trade_intent_guard ?? null,
    benchmarkAwareDetailsInput,
  )
  const benchmarkLiveGate = resolvePredictionMarketBenchmarkLiveGateState({
    ...benchmarkAwareDetailsInput,
    trade_intent_guard: benchmarkAwareTradeIntentGuard,
  })
  const benchmarkAwareDetails = benchmarkAwareTradeIntentGuard
    ? {
      ...enrichedDetails,
      research_benchmark_gate_blocks_live: benchmarkLiveGate.blocks_live,
      research_benchmark_live_block_reason: benchmarkLiveGate.live_block_reason,
      benchmark_gate_blocks_live: benchmarkLiveGate.blocks_live,
      benchmark_gate_live_block_reason: benchmarkLiveGate.live_block_reason,
      trade_intent_guard: benchmarkAwareTradeIntentGuard,
    }
    : {
      ...enrichedDetails,
      research_benchmark_gate_blocks_live: benchmarkLiveGate.blocks_live,
      research_benchmark_live_block_reason: benchmarkLiveGate.live_block_reason,
      benchmark_gate_blocks_live: benchmarkLiveGate.blocks_live,
      benchmark_gate_live_block_reason: benchmarkLiveGate.live_block_reason,
    }
  const resolvedRunId = enrichedDetails.run_id ?? runId
  const manifest = resolvePredictionMarketRunManifest(benchmarkAwareDetails)
  const artifactRefs = resolvePredictionMarketRunArtifactRefs(benchmarkAwareDetails)
  if (!manifest) {
    return {
      ...benchmarkAwareDetails,
      run_id: resolvedRunId,
      ...buildPredictionMarketBenchmarkGateOverride(
        benchmarkAwareDetails as Partial<PredictionMarketRunSummaryWithArtifactAudit>,
      ),
    }
  }
  const artifactReadback = buildPredictionMarketArtifactReadback({
    manifest,
    artifact_refs: toArtifactRefsFromArtifacts(benchmarkAwareDetails),
  })
  const forecastPacket = extractRunDetailForecastPacket(benchmarkAwareDetails)
  const recommendationPacket = extractRunDetailRecommendationPacket(benchmarkAwareDetails)
  let executionReadiness: PredictionMarketExecutionReadiness | undefined
  let executionPathways: PredictionMarketExecutionPathwaysReport | undefined
  let executionProjection: PredictionMarketExecutionProjectionReport | undefined
  let shadowArbitrage: ShadowArbitrageSimulationReport | null | undefined
  let tradeIntentGuard: TradeIntentGuard | undefined
  let multiVenueExecution: MultiVenueExecution | undefined
  let marketEvents: PredictionMarketJsonArtifact | undefined
  let marketPositions: PredictionMarketJsonArtifact | undefined
  let sourceAuditArtifact: PredictionMarketJsonArtifact | null | undefined
  let rulesLineageArtifact: PredictionMarketJsonArtifact | null | undefined
  let catalystTimelineArtifact: PredictionMarketJsonArtifact | null | undefined
  let worldStateArtifact: PredictionMarketJsonArtifact | null | undefined
  let ticketPayloadArtifact: PredictionMarketJsonArtifact | null | undefined
  let quantSignalBundle: PredictionMarketJsonArtifact | null | undefined
  let decisionLedgerArtifact: PredictionMarketJsonArtifact | null | undefined
  let calibrationReportArtifact: PredictionMarketJsonArtifact | null | undefined
  let resolvedHistoryArtifact: PredictionMarketJsonArtifact | null | undefined
  let costModelReportArtifact: PredictionMarketJsonArtifact | null | undefined
  let walkForwardReportArtifact: PredictionMarketJsonArtifact | null | undefined
  let autopilotCycleSummaryArtifact: PredictionMarketJsonArtifact | null | undefined
  let researchMemorySummaryArtifact: PredictionMarketJsonArtifact | null | undefined
  let paperSurface: PredictionMarketReplaySurface | null | undefined
  let replaySurface: PredictionMarketReplaySurface | null | undefined
  let microstructureLab: MicrostructureLabReport | undefined
  let researchSidecar: MarketResearchSidecar | undefined
  let timesfmSidecar: PredictionMarketTimesFMSidecar | undefined
  let researchBridge: ResearchBridgeBundle | null | undefined
  let venueFeedSurface: MarketFeedSurface | undefined
  let marketGraph: PredictionMarketMarketGraph | null | undefined
  let packetBundle: PredictionMarketPacketBundle | undefined
  let strategyCandidatePacket: StrategyCandidatePacket | null | undefined
  let strategyDecisionPacket: StrategyDecisionPacket | null | undefined
  let strategyShadowSummary: StrategyShadowSummary | null | undefined
  let strategyShadowReport: StrategyShadowReport | null | undefined
  let executionIntentPreview: ExecutionIntentPreview | null | undefined
  let quotePairIntentPreview: QuotePairIntentPreview | null | undefined
  let basketIntentPreview: BasketIntentPreview | null | undefined
  let latencyReferenceBundle: LatencyReferenceBundle | null | undefined
  let resolutionAnomalyReport: ResolutionAnomalyReport | null | undefined
  let autonomousAgentReport: AutonomousAgentReport | null | undefined
  const venueCoverage = getVenueCoverageContract()
  const orderTraceAudit = extractOrderTraceAudit(benchmarkAwareDetails)

  try {
    const storedArtifacts = extractStoredExecutionArtifacts(benchmarkAwareDetails)
    marketEvents = storedArtifacts.market_events ?? undefined
    marketPositions = storedArtifacts.market_positions ?? undefined
    sourceAuditArtifact = storedArtifacts.source_audit ?? undefined
    rulesLineageArtifact = storedArtifacts.rules_lineage ?? undefined
    catalystTimelineArtifact = storedArtifacts.catalyst_timeline ?? undefined
    worldStateArtifact = storedArtifacts.world_state ?? undefined
    ticketPayloadArtifact = storedArtifacts.ticket_payload ?? undefined
    quantSignalBundle = storedArtifacts.quant_signal_bundle ?? undefined
    decisionLedgerArtifact = storedArtifacts.decision_ledger ?? undefined
    calibrationReportArtifact = storedArtifacts.calibration_report ?? undefined
    resolvedHistoryArtifact = storedArtifacts.resolved_history ?? undefined
    costModelReportArtifact = storedArtifacts.cost_model_report ?? undefined
    walkForwardReportArtifact = storedArtifacts.walk_forward_report ?? undefined
    autopilotCycleSummaryArtifact = storedArtifacts.autopilot_cycle_summary ?? undefined
    researchMemorySummaryArtifact = storedArtifacts.research_memory_summary ?? undefined
    paperSurface = storedArtifacts.paper_surface ?? undefined
    replaySurface = storedArtifacts.replay_surface ?? undefined
    microstructureLab = storedArtifacts.microstructure_lab ?? undefined
    researchBridge = storedArtifacts.research_bridge ?? undefined
    timesfmSidecar = storedArtifacts.timesfm_sidecar ?? undefined
    strategyCandidatePacket = storedArtifacts.strategy_candidate_packet
    strategyDecisionPacket = storedArtifacts.strategy_decision_packet
    strategyShadowSummary = storedArtifacts.strategy_shadow_summary
    strategyShadowReport = storedArtifacts.strategy_shadow_report
    executionIntentPreview = storedArtifacts.execution_intent_preview
    quotePairIntentPreview = storedArtifacts.quote_pair_intent_preview
    basketIntentPreview = storedArtifacts.basket_intent_preview
    latencyReferenceBundle = storedArtifacts.latency_reference_bundle
    resolutionAnomalyReport = storedArtifacts.resolution_anomaly_report
    autonomousAgentReport = storedArtifacts.autonomous_agent_report
    researchSidecar = storedArtifacts.research_sidecar
      ? annotateMarketResearchSidecarComparisons(
        storedArtifacts.research_sidecar,
        storedArtifacts.forecast.probability_yes,
      )
      : undefined
    const pipelineGuard = storedArtifacts.pipeline_guard
    venueFeedSurface = pipelineGuard?.venue_feed_surface ?? getVenueFeedSurfaceContract(storedArtifacts.snapshot.venue)
    const compliance = storedArtifacts.compliance ?? (pipelineGuard
      ? evaluatePredictionMarketCompliance({
        venue: storedArtifacts.snapshot.venue,
        venue_type: storedArtifacts.snapshot.market.venue_type,
        mode: 'discovery',
        capabilities: pipelineGuard.venue_capabilities,
      })
      : null)
    executionReadiness = storedArtifacts.execution_readiness ?? (pipelineGuard && compliance
      ? derivePredictionMarketExecutionReadiness({
        snapshot: storedArtifacts.snapshot,
        pipelineGuard,
        compliance,
        crossVenueIntelligence: normalizeCrossVenueIntelligence(storedArtifacts.cross_venue_intelligence),
        microstructureLab: storedArtifacts.microstructure_lab,
        strategyDecision: storedArtifacts.strategy_decision_packet,
        resolutionAnomalyReport: storedArtifacts.resolution_anomaly_report,
      })
      : undefined)
    const pathwaySupplementalArtifacts = buildPredictionMarketExecutionPathwaySupplementalArtifacts({
      evidencePackets: storedArtifacts.evidence_packets,
      decisionPacket: extractDecisionPacketFromEvidencePackets(storedArtifacts.evidence_packets),
      researchSidecar: researchSidecar ?? storedArtifacts.research_sidecar,
      thesisProbability: extractManualThesisFromEvidencePackets(storedArtifacts.evidence_packets).thesisProbability,
      thesisRationale: extractManualThesisFromEvidencePackets(storedArtifacts.evidence_packets).thesisRationale,
    })
    executionPathways = storedArtifacts.execution_pathways ?? (executionReadiness
      ? derivePredictionMarketExecutionPathways({
        runId,
        snapshot: storedArtifacts.snapshot,
        resolutionPolicy: storedArtifacts.resolution_policy,
        forecast: storedArtifacts.forecast,
        recommendation: storedArtifacts.recommendation,
        executionReadiness,
        strategy_name: storedArtifacts.strategy_decision_packet?.strategy_family ?? storedArtifacts.strategy_candidate_packet?.strategy_family ?? null,
        market_regime_summary: storedArtifacts.strategy_decision_packet?.market_regime?.summary ?? storedArtifacts.strategy_candidate_packet?.market_regime?.summary ?? null,
        primary_strategy_summary: storedArtifacts.strategy_decision_packet?.summary ?? storedArtifacts.strategy_candidate_packet?.summary ?? null,
        strategy_summary: storedArtifacts.strategy_decision_packet?.summary ?? null,
        operator_thesis: pathwaySupplementalArtifacts.operator_thesis,
        research_pipeline_trace: pathwaySupplementalArtifacts.research_pipeline_trace,
      })
      : undefined)
    if (executionPathways && (
      executionPathways.operator_thesis == null ||
      executionPathways.research_pipeline_trace == null
    )) {
      executionPathways = {
        ...executionPathways,
        operator_thesis: executionPathways.operator_thesis ?? pathwaySupplementalArtifacts.operator_thesis,
        research_pipeline_trace: executionPathways.research_pipeline_trace ?? pathwaySupplementalArtifacts.research_pipeline_trace,
      }
    }
    executionProjection = storedArtifacts.execution_projection ?? (executionReadiness
      ? derivePredictionMarketExecutionProjection({
        runId,
        snapshot: storedArtifacts.snapshot,
        forecast: storedArtifacts.forecast,
        resolutionPolicy: storedArtifacts.resolution_policy,
        recommendation: storedArtifacts.recommendation,
        executionReadiness,
        crossVenueIntelligence: normalizeCrossVenueIntelligence(storedArtifacts.cross_venue_intelligence),
        strategy_name: storedArtifacts.strategy_decision_packet?.strategy_family ?? storedArtifacts.strategy_candidate_packet?.strategy_family ?? null,
        market_regime_summary: storedArtifacts.strategy_decision_packet?.market_regime?.summary ?? storedArtifacts.strategy_candidate_packet?.market_regime?.summary ?? null,
        primary_strategy_summary: storedArtifacts.strategy_decision_packet?.summary ?? storedArtifacts.strategy_candidate_packet?.summary ?? null,
        strategy_summary: storedArtifacts.strategy_decision_packet?.summary ?? null,
      })
      : undefined)
    shadowArbitrage = storedArtifacts.shadow_arbitrage ?? derivePredictionMarketShadowArbitrage(executionProjection)
    const benchmarkPromotionState = resolvePredictionMarketBenchmarkPromotionState(
      benchmarkAwareDetails as Partial<PredictionMarketRunRuntimeHints>,
    )
    const executionSurfaces = executionReadiness
      ? derivePredictionMarketExecutionSurfaces({
        runId,
        snapshot: storedArtifacts.snapshot,
        recommendation: storedArtifacts.recommendation,
        pipelineGuard: storedArtifacts.pipeline_guard,
        runtimeGuard: storedArtifacts.runtime_guard,
        compliance,
        crossVenueIntelligence: normalizeCrossVenueIntelligence(storedArtifacts.cross_venue_intelligence),
        executionReadiness,
        executionPathways,
        executionProjection,
        benchmarkPromotionReady: benchmarkPromotionState.promotion_ready,
        benchmarkPromotionGateKind: benchmarkPromotionState.promotion_gate_kind,
        benchmarkPromotionBlockerSummary: benchmarkPromotionState.promotion_blocker_summary,
      })
      : null
    tradeIntentGuard = storedArtifacts.trade_intent_guard ?? executionSurfaces?.trade_intent_guard
    multiVenueExecution = storedArtifacts.multi_venue_execution ?? executionSurfaces?.multi_venue_execution
    packetBundle = buildPredictionMarketPacketBundle({
      bundleId: `${resolvedRunId}:packet_bundle`,
      runId: resolvedRunId,
      venue: storedArtifacts.snapshot.venue,
      marketId: storedArtifacts.snapshot.market.market_id,
      decisionPacket: extractDecisionPacketFromEvidencePackets(storedArtifacts.evidence_packets),
      strategyCandidatePacket: storedArtifacts.strategy_candidate_packet,
      strategyDecisionPacket: storedArtifacts.strategy_decision_packet,
      strategyShadowReport: storedArtifacts.strategy_shadow_report,
      evidencePackets: storedArtifacts.evidence_packets,
      forecastPacket: storedArtifacts.forecast,
      recommendationPacket: storedArtifacts.recommendation,
      researchBridge: storedArtifacts.research_bridge,
      marketEvents: storedArtifacts.market_events,
      marketPositions: storedArtifacts.market_positions,
      paperSurface: storedArtifacts.paper_surface,
      replaySurface: storedArtifacts.replay_surface,
      orderTraceAudit: orderTraceAudit,
      tradeIntentGuard: tradeIntentGuard ?? null,
      multiVenueExecution: multiVenueExecution ?? null,
      benchmarkPromotionReady: benchmarkLiveGate.promotion_ready,
      benchmarkPromotionGateKind: benchmarkLiveGate.promotion_gate_kind,
      benchmarkPromotionBlockerSummary:
        benchmarkLiveGate.live_block_reason
        ?? benchmarkPromotionState.promotion_blocker_summary,
      benchmarkGateBlocksLive: benchmarkLiveGate.blocks_live,
      benchmarkGateLiveBlockReason: benchmarkLiveGate.live_block_reason,
    })
    marketGraph = derivePredictionMarketMarketGraph({
      snapshot: storedArtifacts.snapshot,
      crossVenueIntelligence: normalizeCrossVenueIntelligence(storedArtifacts.cross_venue_intelligence),
    }) ?? undefined
  } catch (error) {
    if (!(error instanceof PredictionMarketsError) || error.code !== 'stored_artifacts_incomplete') {
      throw error
    }
  }

  return {
    ...benchmarkAwareDetails,
    run_id: resolvedRunId,
    manifest,
    artifact_refs: artifactRefs,
    artifact_readback: artifactReadback,
    artifact_audit: summarizePredictionMarketArtifactReadback(artifactReadback),
    paper_surface: paperSurface ?? null,
    replay_surface: replaySurface ?? null,
    paper_no_trade_zone_count: extractReplaySurfaceCounters(paperSurface).no_trade_zone_count,
    paper_no_trade_zone_rate: extractReplaySurfaceCounters(paperSurface).no_trade_zone_rate,
    replay_no_trade_leg_count: extractReplaySurfaceCounters(replaySurface).no_trade_leg_count,
    replay_no_trade_leg_rate: extractReplaySurfaceCounters(replaySurface).no_trade_leg_rate,
    ...buildPredictionMarketRunRuntimeHints({
      timesfmSidecar: timesfmSidecar ?? null,
      researchSidecar: researchSidecar,
      forecast: forecastPacket,
      recommendation: recommendationPacket,
      venueFeedSurface: venueFeedSurface ?? null,
      executionPathways,
      executionProjection,
      shadowArbitrage,
      multiVenueExecution: multiVenueExecution ?? null,
      strategyCandidate: strategyCandidatePacket ?? null,
      strategyDecision: strategyDecisionPacket ?? null,
      executionIntentPreview: executionIntentPreview ?? null,
      resolutionAnomalyReport: resolutionAnomalyReport ?? null,
      strategyShadowSummary: strategyShadowSummary ?? null,
      sourceAudit: sourceAuditArtifact ?? null,
      worldState: worldStateArtifact ?? null,
      ticketPayload: ticketPayloadArtifact ?? null,
      quantSignalBundle: quantSignalBundle ?? null,
      decisionLedger: decisionLedgerArtifact ?? null,
      calibrationReport: calibrationReportArtifact ?? null,
      resolvedHistory: resolvedHistoryArtifact ?? null,
      costModelReport: costModelReportArtifact ?? null,
      walkForwardReport: walkForwardReportArtifact ?? null,
      autopilotCycleSummary: autopilotCycleSummaryArtifact ?? null,
      researchMemorySummary: researchMemorySummaryArtifact ?? null,
      benchmarkGateOverride: buildPredictionMarketBenchmarkGateOverride(benchmarkAwareDetails),
    }),
    ...buildPredictionMarketBenchmarkGateOverride(benchmarkAwareDetails),
    benchmark_gate_blocks_live: benchmarkLiveGate.blocks_live,
    benchmark_gate_live_block_reason: benchmarkLiveGate.live_block_reason,
    research_benchmark_gate_blocks_live: benchmarkLiveGate.blocks_live,
    research_benchmark_live_block_reason: benchmarkLiveGate.live_block_reason,
    execution_readiness: executionReadiness,
    execution_pathways: executionPathways,
    execution_projection: executionProjection,
    shadow_arbitrage: shadowArbitrage,
    trade_intent_guard: tradeIntentGuard,
    multi_venue_execution: multiVenueExecution,
    research_bridge: researchBridge,
    research_sidecar: researchSidecar,
    timesfm_sidecar: timesfmSidecar ?? null,
    packet_bundle: packetBundle,
    market_events: marketEvents,
    market_positions: marketPositions,
    source_audit_artifact: sourceAuditArtifact ?? null,
    rules_lineage_artifact: rulesLineageArtifact ?? null,
    catalyst_timeline_artifact: catalystTimelineArtifact ?? null,
    world_state_artifact: worldStateArtifact ?? null,
    ticket_payload_artifact: ticketPayloadArtifact ?? null,
    quant_signal_bundle: quantSignalBundle ?? null,
    decision_ledger_artifact: decisionLedgerArtifact ?? null,
    calibration_report_artifact: calibrationReportArtifact ?? null,
    resolved_history_artifact: resolvedHistoryArtifact ?? null,
    cost_model_report_artifact: costModelReportArtifact ?? null,
    walk_forward_report_artifact: walkForwardReportArtifact ?? null,
    autopilot_cycle_summary_artifact: autopilotCycleSummaryArtifact ?? null,
    research_memory_summary_artifact: researchMemorySummaryArtifact ?? null,
    venue_feed_surface: venueFeedSurface,
    venue_coverage: venueCoverage,
    microstructure_lab: microstructureLab,
    order_trace_audit: orderTraceAudit,
    market_graph: marketGraph ?? null,
    strategy_candidate_packet: strategyCandidatePacket ?? null,
    strategy_decision_packet: strategyDecisionPacket ?? null,
    strategy_shadow_summary_packet: strategyShadowSummary ?? null,
    strategy_shadow_report: strategyShadowReport ?? null,
    execution_intent_preview: executionIntentPreview ?? null,
    quote_pair_intent_preview: quotePairIntentPreview ?? null,
    basket_intent_preview: basketIntentPreview ?? null,
    latency_reference_bundle: latencyReferenceBundle ?? null,
    resolution_anomaly_report: resolutionAnomalyReport ?? null,
    autonomous_agent_report: autonomousAgentReport ?? null,
  }
}

export function preparePredictionMarketRunDispatch(input: {
  runId: string
  workspaceId: number
}): PredictionMarketRunDispatchPlan {
  const details = getPredictionMarketRunDetails(input.runId, input.workspaceId)
  if (!details) {
    throw new PredictionMarketsError('Prediction market run not found', {
      status: 404,
      code: 'run_not_found',
    })
  }

  const executionProjection = details.execution_projection ?? null
  const forecastPacket = extractRunDetailForecastPacket(details)
  const recommendationPacket = extractRunDetailRecommendationPacket(details)
  const benchmarkPromotionState = resolvePredictionMarketBenchmarkPromotionState(details)
  if (!executionProjection) {
    throw new PredictionMarketsError('Prediction market run has no execution projection', {
      status: 409,
      code: 'execution_projection_unavailable',
    })
  }

  const selectedProjectionPath = resolveCanonicalPredictionMarketProjectionPath(executionProjection)
  const selectedProjectionPreview = resolveCanonicalPredictionMarketSelectedPreview(executionProjection)
  const selectedPreview = details.execution_projection_selected_preview ?? selectedProjectionPreview.preview
  const selectedPreviewSource = details.execution_projection_selected_preview_source ?? selectedProjectionPreview.source
  const selectedPath = details.execution_projection_selected_path ?? executionProjection.selected_path ?? null
  const paperPath = resolvePredictionMarketProjectionPathByMode(executionProjection, 'paper')
  const shadowPath = resolvePredictionMarketProjectionPathByMode(executionProjection, 'shadow')
  const selectedPathLabel = executionProjection.selected_path ? 'selected_path' : 'requested_path'
  const projectionBlockers = executionProjection.verdict === 'blocked'
    ? executionProjection.blocking_reasons.map((reason) => `projection:${reason}`)
    : []
  const selectedPathBlockers = selectedProjectionPath?.status === 'blocked'
    ? selectedProjectionPath.blockers.map((reason) => `${selectedPathLabel}:${reason}`)
    : []
  const dispatchTradeIntentGuard = rehydratePredictionMarketTradeIntentGuardForBenchmarkPromotion(
    details.trade_intent_guard ?? null,
    details,
  )
  const guardBlockers = dispatchTradeIntentGuard?.verdict === 'blocked'
    ? (dispatchTradeIntentGuard.blocked_reasons ?? []).map((reason) => `trade_intent_guard:${reason}`)
    : []
  const benchmarkSurfaceBlockingReasons = resolvePredictionMarketBenchmarkSurfaceBlockingReasons(details)
  const requiresBenchmarkPromotionGate = selectedPath === 'live'
    || selectedProjectionPath?.effective_mode === 'live'
    || executionProjection.recommended_effective_mode === 'live'
  const benchmarkPromotionBlockers = resolvePredictionMarketBenchmarkPromotionBlockers(
    details,
    requiresBenchmarkPromotionGate,
  )
  const dispatchBlockingReasons = uniqueStrings([
    ...(selectedPath ? [] : ['no_actionable_execution_projection_path']),
    ...projectionBlockers,
    ...selectedPathBlockers,
    ...(selectedPreview ? [] : ['selected_path_missing_trade_intent_preview']),
    ...(details.trade_intent_guard ? [] : ['trade_intent_guard_unavailable']),
    ...guardBlockers,
    ...benchmarkSurfaceBlockingReasons,
    ...benchmarkPromotionBlockers,
  ])
  const dispatchStatus: PredictionMarketRunDispatchStatus = dispatchBlockingReasons.length > 0
    ? 'blocked'
    : 'ready'

  const summary = dispatchStatus === 'ready'
    ? `Dispatch preflight is ready for ${selectedPath ?? 'none'} using the canonical execution_projection preview.`
    : buildBlockedSurfaceSummary({
      surfaceLabel: 'Dispatch',
      blockedReasons: dispatchBlockingReasons,
      rollbackMode: resolveRollbackMode({
        currentMode: selectedPath,
        paperPath,
        shadowPath,
      }),
    })

  return {
    gate_name: 'execution_projection_dispatch',
    preflight_only: true,
    run_id: details.run_id,
    workspace_id: details.workspace_id,
    dispatch_status: dispatchStatus,
    dispatch_blocking_reasons: dispatchBlockingReasons,
    benchmark_surface_blocking_reasons: benchmarkSurfaceBlockingReasons,
    benchmark_promotion_blockers: benchmarkPromotionBlockers,
    benchmark_promotion_ready: benchmarkPromotionState.promotion_ready === true,
    summary,
    source_refs: {
      run_detail: details.run_id,
      execution_projection: `${details.run_id}:execution_projection`,
      trade_intent_guard: details.trade_intent_guard ? `${details.run_id}:trade_intent_guard` : null,
      multi_venue_execution: details.multi_venue_execution ? `${details.run_id}:multi_venue_execution` : null,
    },
    execution_readiness: details.execution_readiness ?? null,
    execution_pathways: details.execution_pathways ?? null,
    execution_projection: executionProjection,
    shadow_arbitrage: details.shadow_arbitrage ?? null,
    trade_intent_guard: dispatchTradeIntentGuard,
    multi_venue_execution: details.multi_venue_execution ?? null,
    ...buildPredictionMarketRunRuntimeHints({
      timesfmSidecar: details.timesfm_sidecar ?? null,
      researchSidecar: details.research_sidecar ?? null,
      forecast: forecastPacket,
      recommendation: recommendationPacket,
      venueFeedSurface: details.venue_feed_surface ?? null,
      executionPathways: details.execution_pathways,
      executionProjection: executionProjection,
      shadowArbitrage: details.shadow_arbitrage,
      multiVenueExecution: details.multi_venue_execution ?? null,
      sourceAudit: details.source_audit_artifact ?? null,
      worldState: details.world_state_artifact ?? null,
      ticketPayload: details.ticket_payload_artifact ?? null,
      quantSignalBundle: details.quant_signal_bundle ?? null,
      decisionLedger: details.decision_ledger_artifact ?? null,
      calibrationReport: details.calibration_report_artifact ?? null,
      resolvedHistory: details.resolved_history_artifact ?? null,
      costModelReport: details.cost_model_report_artifact ?? null,
      walkForwardReport: details.walk_forward_report_artifact ?? null,
      autopilotCycleSummary: details.autopilot_cycle_summary_artifact ?? null,
      researchMemorySummary: details.research_memory_summary_artifact ?? null,
      benchmarkGateOverride: buildPredictionMarketBenchmarkGateOverride(details),
    }),
    execution_projection_selected_preview: selectedPreview,
    execution_projection_selected_preview_source: selectedPreviewSource ?? null,
  }
}

export function preparePredictionMarketRunPaper(input: {
  runId: string
  workspaceId: number
}): PredictionMarketRunPaperPlan {
  const details = getPredictionMarketRunDetails(input.runId, input.workspaceId)
  if (!details) {
    throw new PredictionMarketsError('Prediction market run not found', {
      status: 404,
      code: 'run_not_found',
    })
  }

  const executionProjection = details.execution_projection ?? null
  const forecastPacket = extractRunDetailForecastPacket(details)
  const recommendationPacket = extractRunDetailRecommendationPacket(details)
  const benchmarkPromotionState = resolvePredictionMarketBenchmarkPromotionState(details)
  if (!executionProjection) {
    throw new PredictionMarketsError('Prediction market run has no execution projection', {
      status: 409,
      code: 'execution_projection_unavailable',
    })
  }

  const paperPath = resolvePredictionMarketProjectionPathByMode(executionProjection, 'paper')
  const paperPreview = resolvePredictionMarketProjectionPreviewByMode(executionProjection, 'paper')
  const benchmarkSurfaceBlockingReasons = resolvePredictionMarketBenchmarkSurfaceBlockingReasons(details)
  const benchmarkPromotionBlockers = resolvePredictionMarketBenchmarkPromotionBlockers(details, true)
  const paperBlockingReasons = uniqueStrings([
    ...(paperPath ? [] : ['paper_path_unavailable']),
    ...(paperPath?.status === 'blocked'
      ? paperPath.blockers.map((reason) => `paper_path:${reason}`)
      : []),
    ...(paperPreview.preview ? [] : ['paper_path_missing_trade_intent_preview']),
    ...benchmarkSurfaceBlockingReasons,
  ])
  const paperStatus: PredictionMarketRunPaperStatus = paperBlockingReasons.length > 0
    ? 'blocked'
    : 'ready'
  const paperRollbackMode = resolveRollbackMode({
    currentMode: paperPath?.effective_mode ?? 'paper',
    paperPath,
    shadowPath: resolvePredictionMarketProjectionPathByMode(executionProjection, 'shadow'),
  })

  const summary = paperStatus === 'ready'
    ? [
      'Paper surface is ready using execution_projection.projected_paths.paper and the canonical paper preview.',
      benchmarkPromotionBlockers.length > 0
        ? 'Live promotion remains blocked by the benchmark gate.'
        : null,
    ].filter(Boolean).join(' ')
    : buildBlockedSurfaceSummary({
      surfaceLabel: 'Paper',
      blockedReasons: paperBlockingReasons,
      rollbackMode: paperRollbackMode,
    })

  return {
    gate_name: 'execution_projection_paper',
    preflight_only: true,
    run_id: details.run_id,
    workspace_id: details.workspace_id,
    surface_mode: 'paper',
    paper_status: paperStatus,
    paper_blocking_reasons: paperBlockingReasons,
    benchmark_surface_blocking_reasons: benchmarkSurfaceBlockingReasons,
    benchmark_promotion_blockers: benchmarkPromotionBlockers,
    benchmark_promotion_ready: benchmarkPromotionState.promotion_ready === true,
    summary,
    source_refs: {
      run_detail: details.run_id,
      execution_projection: `${details.run_id}:execution_projection`,
      paper_projected_path: `${details.run_id}:execution_projection#paper`,
      trade_intent_guard: details.trade_intent_guard ? `${details.run_id}:trade_intent_guard` : null,
      multi_venue_execution: details.multi_venue_execution ? `${details.run_id}:multi_venue_execution` : null,
    },
    execution_readiness: details.execution_readiness ?? null,
    execution_pathways: details.execution_pathways ?? null,
    execution_projection: executionProjection,
    shadow_arbitrage: details.shadow_arbitrage ?? null,
    trade_intent_guard: details.trade_intent_guard ?? null,
    multi_venue_execution: details.multi_venue_execution ?? null,
    venue_feed_surface: details.venue_feed_surface ?? null,
    paper_surface: details.paper_surface ?? null,
    replay_surface: details.replay_surface ?? null,
    paper_no_trade_zone_count: extractReplaySurfaceCounters(details.paper_surface).no_trade_zone_count,
    paper_no_trade_zone_rate: extractReplaySurfaceCounters(details.paper_surface).no_trade_zone_rate,
    replay_no_trade_leg_count: extractReplaySurfaceCounters(details.replay_surface).no_trade_leg_count,
    replay_no_trade_leg_rate: extractReplaySurfaceCounters(details.replay_surface).no_trade_leg_rate,
    paper_path: paperPath,
    paper_trade_intent_preview: paperPreview.preview,
    paper_trade_intent_preview_source: paperPreview.source,
    ...buildPredictionMarketRunRuntimeHints({
      timesfmSidecar: details.timesfm_sidecar ?? null,
      researchSidecar: details.research_sidecar ?? null,
      forecast: forecastPacket,
      recommendation: recommendationPacket,
      venueFeedSurface: details.venue_feed_surface ?? null,
      executionPathways: details.execution_pathways,
      executionProjection: executionProjection,
      shadowArbitrage: details.shadow_arbitrage,
      multiVenueExecution: details.multi_venue_execution ?? null,
      sourceAudit: details.source_audit_artifact ?? null,
      worldState: details.world_state_artifact ?? null,
      ticketPayload: details.ticket_payload_artifact ?? null,
      quantSignalBundle: details.quant_signal_bundle ?? null,
      decisionLedger: details.decision_ledger_artifact ?? null,
      calibrationReport: details.calibration_report_artifact ?? null,
      resolvedHistory: details.resolved_history_artifact ?? null,
      costModelReport: details.cost_model_report_artifact ?? null,
      walkForwardReport: details.walk_forward_report_artifact ?? null,
      autopilotCycleSummary: details.autopilot_cycle_summary_artifact ?? null,
      researchMemorySummary: details.research_memory_summary_artifact ?? null,
      benchmarkGateOverride: buildPredictionMarketBenchmarkGateOverride(details),
    }),
  }
}

export function preparePredictionMarketRunShadow(input: {
  runId: string
  workspaceId: number
}): PredictionMarketRunShadowPlan {
  const details = getPredictionMarketRunDetails(input.runId, input.workspaceId)
  if (!details) {
    throw new PredictionMarketsError('Prediction market run not found', {
      status: 404,
      code: 'run_not_found',
    })
  }

  const executionProjection = details.execution_projection ?? null
  const forecastPacket = extractRunDetailForecastPacket(details)
  const recommendationPacket = extractRunDetailRecommendationPacket(details)
  const benchmarkPromotionState = resolvePredictionMarketBenchmarkPromotionState(details)
  if (!executionProjection) {
    throw new PredictionMarketsError('Prediction market run has no execution projection', {
      status: 409,
      code: 'execution_projection_unavailable',
    })
  }

  const shadowPath = resolvePredictionMarketProjectionPathByMode(executionProjection, 'shadow')
  const shadowPreview = resolvePredictionMarketProjectionPreviewByMode(executionProjection, 'shadow')
  const benchmarkSurfaceBlockingReasons = resolvePredictionMarketBenchmarkSurfaceBlockingReasons(details)
  const benchmarkPromotionBlockers = resolvePredictionMarketBenchmarkPromotionBlockers(details, true)
  const shadowBlockingReasons = uniqueStrings([
    ...(shadowPath ? [] : ['shadow_path_unavailable']),
    ...(shadowPath?.status === 'blocked'
      ? shadowPath.blockers.map((reason) => `shadow_path:${reason}`)
      : []),
    ...(shadowPreview.preview ? [] : ['shadow_path_missing_trade_intent_preview']),
    ...benchmarkSurfaceBlockingReasons,
  ])
  const shadowStatus: PredictionMarketRunShadowStatus = shadowBlockingReasons.length > 0
    ? 'blocked'
    : 'ready'
  const shadowRollbackMode = resolveRollbackMode({
    currentMode: shadowPath?.effective_mode ?? 'shadow',
    paperPath: resolvePredictionMarketProjectionPathByMode(executionProjection, 'paper'),
    shadowPath,
  })

  const summary = shadowStatus === 'ready'
    ? [
      'Shadow surface is ready using execution_projection.projected_paths.shadow and the canonical shadow preview.',
      benchmarkPromotionBlockers.length > 0
        ? 'Live promotion remains blocked by the benchmark gate.'
        : null,
    ].filter(Boolean).join(' ')
    : buildBlockedSurfaceSummary({
      surfaceLabel: 'Shadow',
      blockedReasons: shadowBlockingReasons,
      rollbackMode: shadowRollbackMode,
    })

  return {
    gate_name: 'execution_projection_shadow',
    preflight_only: true,
    run_id: details.run_id,
    workspace_id: details.workspace_id,
    surface_mode: 'shadow',
    shadow_status: shadowStatus,
    shadow_blocking_reasons: shadowBlockingReasons,
    benchmark_surface_blocking_reasons: benchmarkSurfaceBlockingReasons,
    benchmark_promotion_blockers: benchmarkPromotionBlockers,
    benchmark_promotion_ready: benchmarkPromotionState.promotion_ready === true,
    summary,
    source_refs: {
      run_detail: details.run_id,
      execution_projection: `${details.run_id}:execution_projection`,
      shadow_projected_path: `${details.run_id}:execution_projection#shadow`,
      shadow_arbitrage: details.shadow_arbitrage ? `${details.run_id}:shadow_arbitrage` : null,
      trade_intent_guard: details.trade_intent_guard ? `${details.run_id}:trade_intent_guard` : null,
      multi_venue_execution: details.multi_venue_execution ? `${details.run_id}:multi_venue_execution` : null,
    },
    execution_readiness: details.execution_readiness ?? null,
    execution_pathways: details.execution_pathways ?? null,
    execution_projection: executionProjection,
    shadow_arbitrage: details.shadow_arbitrage ?? null,
    trade_intent_guard: details.trade_intent_guard ?? null,
    multi_venue_execution: details.multi_venue_execution ?? null,
    venue_feed_surface: details.venue_feed_surface ?? null,
    paper_surface: details.paper_surface ?? null,
    replay_surface: details.replay_surface ?? null,
    paper_no_trade_zone_count: extractReplaySurfaceCounters(details.paper_surface).no_trade_zone_count,
    paper_no_trade_zone_rate: extractReplaySurfaceCounters(details.paper_surface).no_trade_zone_rate,
    replay_no_trade_leg_count: extractReplaySurfaceCounters(details.replay_surface).no_trade_leg_count,
    replay_no_trade_leg_rate: extractReplaySurfaceCounters(details.replay_surface).no_trade_leg_rate,
    shadow_path: shadowPath,
    shadow_trade_intent_preview: shadowPreview.preview,
    shadow_trade_intent_preview_source: shadowPreview.source,
    ...buildPredictionMarketRunRuntimeHints({
      timesfmSidecar: details.timesfm_sidecar ?? null,
      researchSidecar: details.research_sidecar ?? null,
      forecast: forecastPacket,
      recommendation: recommendationPacket,
      venueFeedSurface: details.venue_feed_surface ?? null,
      executionPathways: details.execution_pathways,
      executionProjection: executionProjection,
      shadowArbitrage: details.shadow_arbitrage,
      multiVenueExecution: details.multi_venue_execution ?? null,
      sourceAudit: details.source_audit_artifact ?? null,
      worldState: details.world_state_artifact ?? null,
      ticketPayload: details.ticket_payload_artifact ?? null,
      quantSignalBundle: details.quant_signal_bundle ?? null,
      decisionLedger: details.decision_ledger_artifact ?? null,
      calibrationReport: details.calibration_report_artifact ?? null,
      resolvedHistory: details.resolved_history_artifact ?? null,
      costModelReport: details.cost_model_report_artifact ?? null,
      walkForwardReport: details.walk_forward_report_artifact ?? null,
      autopilotCycleSummary: details.autopilot_cycle_summary_artifact ?? null,
      researchMemorySummary: details.research_memory_summary_artifact ?? null,
      benchmarkGateOverride: buildPredictionMarketBenchmarkGateOverride(details),
    }),
  }
}

export function preparePredictionMarketRunLive(input: {
  runId: string
  workspaceId: number
}): PredictionMarketRunLivePlan {
  const details = getPredictionMarketRunDetails(input.runId, input.workspaceId)
  if (!details) {
    throw new PredictionMarketsError('Prediction market run not found', {
      status: 404,
      code: 'run_not_found',
    })
  }

  const executionProjection = details.execution_projection ?? null
  const forecastPacket = extractRunDetailForecastPacket(details)
  const recommendationPacket = extractRunDetailRecommendationPacket(details)
  if (!executionProjection) {
    throw new PredictionMarketsError('Prediction market run has no execution projection', {
      status: 409,
      code: 'execution_projection_unavailable',
    })
  }

  const selectedProjectionPath = resolveCanonicalPredictionMarketProjectionPath(executionProjection)
  const selectedProjectionPreview = resolveCanonicalPredictionMarketSelectedPreview(executionProjection)
  const selectedPreview = details.execution_projection_selected_preview ?? selectedProjectionPreview.preview
  const selectedPreviewSource = details.execution_projection_selected_preview_source ?? selectedProjectionPreview.source
  const selectedPath = details.execution_projection_selected_path ?? executionProjection.selected_path ?? null
  const livePath = resolvePredictionMarketProjectionPathByMode(executionProjection, 'live')
  const paperPath = resolvePredictionMarketProjectionPathByMode(executionProjection, 'paper')
  const shadowPath = resolvePredictionMarketProjectionPathByMode(executionProjection, 'shadow')
  const livePreview = resolvePredictionMarketProjectionPreviewByMode(executionProjection, 'live')
  const benchmarkSurfaceBlockingReasons = resolvePredictionMarketBenchmarkSurfaceBlockingReasons(details)
  const liveVenueFeedSurface = details.venue_feed_surface ?? getVenueFeedSurfaceContract(details.venue)
  const liveTransport = resolvePredictionMarketLiveExecutionBridgeStatus(
    details.venue ?? liveVenueFeedSurface?.venue ?? null,
  )
  const liveTradeIntentGuard = rehydratePredictionMarketTradeIntentGuardForBenchmarkPromotion(
    details.trade_intent_guard ?? null,
    details,
  )
  const benchmarkLiveGate = resolvePredictionMarketBenchmarkLiveGateState({
    ...details,
    trade_intent_guard: liveTradeIntentGuard,
  })
  const benchmarkPromotionBlockers = benchmarkLiveGate.promotion_blockers
  const guardBlockers = liveTradeIntentGuard?.verdict === 'blocked'
    ? (liveTradeIntentGuard.blocked_reasons ?? []).map((reason) => `trade_intent_guard:${reason}`)
    : []
  const liveProjectionIsPromotable =
    selectedPath === 'live'
    && benchmarkLiveGate.promotion_ready
    && liveTransport.live_transport_ready
  const liveBlockingReasons = uniqueStrings([
    ...(selectedPath ? [] : ['no_actionable_execution_projection_path']),
    ...(selectedPath === 'live' ? [] : ['selected_path_not_live']),
    ...(selectedProjectionPath?.status === 'blocked'
      ? selectedProjectionPath.blockers.map((reason) => `selected_path:${reason}`)
      : []),
    ...(livePath ? [] : ['live_path_unavailable']),
    ...(livePath?.status === 'blocked'
      ? livePath.blockers.map((reason) => `live_path:${reason}`)
      : []),
    ...(selectedPreview ? [] : ['selected_path_missing_trade_intent_preview']),
    ...(liveTradeIntentGuard ? [] : ['trade_intent_guard_unavailable']),
    ...guardBlockers,
    ...liveTransport.blockers,
    ...(details.benchmark_gate_live_block_reason ? [`benchmark:${details.benchmark_gate_live_block_reason}`] : []),
    ...(benchmarkLiveGate.live_block_reason ? [`benchmark:${benchmarkLiveGate.live_block_reason}`] : []),
    ...benchmarkSurfaceBlockingReasons,
    ...benchmarkPromotionBlockers,
  ])
  const liveStatus: PredictionMarketRunLiveStatus = liveBlockingReasons.length > 0
    ? 'blocked'
    : 'ready'
  const liveRouteAllowed = liveStatus === 'ready'
  const liveRollbackMode = resolveRollbackMode({
    currentMode: livePath?.effective_mode ?? selectedPath ?? 'live',
    paperPath,
    shadowPath,
  })

  const summary = liveStatus === 'ready'
    ? 'Live surface is ready using execution_projection.selected_path=live; it remains the canonical preflight surface for governed live routing, and real venue execution is available via execution_mode=live after an approved live intent.'
    : buildBlockedSurfaceSummary({
      surfaceLabel: 'Live',
      blockedReasons: liveBlockingReasons,
      rollbackMode: liveRollbackMode,
      killSwitchSignals: [
        benchmarkLiveGate.live_block_reason,
        liveTradeIntentGuard?.metadata?.benchmark_gate_live_block_reason as string | null | undefined,
        liveTradeIntentGuard?.metadata?.benchmark_promotion_blocker_summary as string | null | undefined,
        liveTradeIntentGuard?.metadata?.benchmark_promotion_summary as string | null | undefined,
      ],
    })

  return {
    gate_name: 'execution_projection_live',
    preflight_only: true,
    run_id: details.run_id,
    workspace_id: details.workspace_id,
    surface_mode: 'live',
    live_route_allowed: liveRouteAllowed,
    live_status: liveStatus,
    live_blocking_reasons: liveBlockingReasons,
    benchmark_surface_blocking_reasons: benchmarkSurfaceBlockingReasons,
    benchmark_promotion_blockers: benchmarkPromotionBlockers,
    benchmark_promotion_ready: benchmarkLiveGate.promotion_ready,
    live_transport_ready: liveTransport.live_transport_ready,
    live_transport_blockers: liveTransport.blockers,
    live_transport_summary: liveTransport.summary,
    summary,
    source_refs: {
      run_detail: details.run_id,
      execution_projection: `${details.run_id}:execution_projection`,
      live_projected_path: `${details.run_id}:execution_projection#live`,
      trade_intent_guard: details.trade_intent_guard ? `${details.run_id}:trade_intent_guard` : null,
      multi_venue_execution: details.multi_venue_execution ? `${details.run_id}:multi_venue_execution` : null,
    },
    execution_readiness: details.execution_readiness ?? null,
    execution_pathways: details.execution_pathways ?? null,
    execution_projection: executionProjection,
    shadow_arbitrage: details.shadow_arbitrage ?? null,
    trade_intent_guard: liveTradeIntentGuard,
    multi_venue_execution: details.multi_venue_execution ?? null,
    venue_feed_surface: liveVenueFeedSurface,
    paper_surface: details.paper_surface ?? null,
    replay_surface: details.replay_surface ?? null,
    paper_no_trade_zone_count: extractReplaySurfaceCounters(details.paper_surface).no_trade_zone_count,
    paper_no_trade_zone_rate: extractReplaySurfaceCounters(details.paper_surface).no_trade_zone_rate,
    replay_no_trade_leg_count: extractReplaySurfaceCounters(details.replay_surface).no_trade_leg_count,
    replay_no_trade_leg_rate: extractReplaySurfaceCounters(details.replay_surface).no_trade_leg_rate,
    live_path: livePath,
    live_trade_intent_preview: liveProjectionIsPromotable
      ? selectedPreview
      : livePreview.preview,
    live_trade_intent_preview_source: liveProjectionIsPromotable
      ? (selectedPreviewSource ?? null)
      : livePreview.source,
    ...buildPredictionMarketRunRuntimeHints({
      timesfmSidecar: details.timesfm_sidecar ?? null,
      researchSidecar: details.research_sidecar ?? null,
      forecast: forecastPacket,
      recommendation: recommendationPacket,
      venueFeedSurface: liveVenueFeedSurface,
      executionPathways: details.execution_pathways,
      executionProjection: executionProjection,
      shadowArbitrage: details.shadow_arbitrage,
      multiVenueExecution: details.multi_venue_execution ?? null,
      sourceAudit: details.source_audit_artifact ?? null,
      worldState: details.world_state_artifact ?? null,
      ticketPayload: details.ticket_payload_artifact ?? null,
      quantSignalBundle: details.quant_signal_bundle ?? null,
      decisionLedger: details.decision_ledger_artifact ?? null,
      calibrationReport: details.calibration_report_artifact ?? null,
      resolvedHistory: details.resolved_history_artifact ?? null,
      costModelReport: details.cost_model_report_artifact ?? null,
      walkForwardReport: details.walk_forward_report_artifact ?? null,
      autopilotCycleSummary: details.autopilot_cycle_summary_artifact ?? null,
      researchMemorySummary: details.research_memory_summary_artifact ?? null,
      benchmarkGateOverride: buildPredictionMarketBenchmarkGateOverride(details),
    }),
  }
}

export function executePredictionMarketRunLive(input: {
  runId: string
  workspaceId: number
  actor: string
  approvedIntentId?: string | null
  approvedBy?: string[]
}): PredictionMarketRunLiveExecutionReceipt {
  const details = getPredictionMarketRunDetails(input.runId, input.workspaceId)
  if (!details) {
    throw new PredictionMarketsError('Prediction market run not found', {
      status: 404,
      code: 'run_not_found',
    })
  }

  const liveSurface = preparePredictionMarketRunLive({
    runId: input.runId,
    workspaceId: input.workspaceId,
  })

  if (liveSurface.live_status !== 'ready' || liveSurface.live_route_allowed !== true) {
    throw new PredictionMarketsError(
      liveSurface.summary || 'Prediction market live surface is blocked',
      {
        status: 409,
        code: 'live_surface_blocked',
      },
    )
  }

  const executionRunId = `${input.runId}__live_${randomUUID().replace(/-/g, '').slice(0, 12)}`
  const bridgePayload = executePredictionMarketLiveExecutionBridge({
    sourceRunId: input.runId,
    executionRunId,
    marketId: details.market_id,
    marketSlug: details.market_slug ?? null,
    decisionPacket: (details.packet_bundle?.decision_packet ?? null) as Record<string, unknown> | null,
    stake: derivePredictionMarketLiveStake({
      liveSurface,
      details,
    }),
    actor: input.actor,
    approvedIntentId: input.approvedIntentId ?? null,
    approvedBy: uniqueStrings(input.approvedBy ?? []),
    persist: true,
    dryRun: false,
    allowLiveExecution: true,
    authorized: true,
    complianceApproved: true,
    scopes: ['prediction_markets:execute'],
  })

  const liveExecution = asRecord(bridgePayload.live_execution)
  const marketExecution = asRecord(bridgePayload.market_execution)
  const orderTraceAudit = asRecord(bridgePayload.order_trace_audit)
  const manifest = asRecord(bridgePayload.manifest)
  const materializedRunId = asString(bridgePayload.run_id) ?? executionRunId
  const transportMode =
    asString(orderTraceAudit?.transport_mode)
    ?? (liveExecution?.dry_run === false ? 'live' : 'dry_run')
  const performedLive = orderTraceAudit?.live_submission_performed === true
  const liveExecutionStatus =
    asString(orderTraceAudit?.live_execution_status)
    ?? asString(liveExecution?.status)
    ?? (performedLive ? 'live_submission_performed' : 'live_submission_not_performed')
  const receiptSummary = performedLive
    ? `Live execution materialized from ${input.runId} as ${materializedRunId}.`
    : `Live execution request was processed from ${input.runId} as ${materializedRunId}, but venue submission was not performed.`

  return {
    gate_name: 'execution_projection_live_materialization',
    execution_mode: 'live',
    source_run_id: input.runId,
    materialized_run_id: materializedRunId,
    approved_intent_id: input.approvedIntentId ?? null,
    approved_by: uniqueStrings(input.approvedBy ?? []),
    transport_mode: transportMode,
    performed_live: performedLive,
    live_execution_status: liveExecutionStatus,
    receipt_summary: receiptSummary,
    preflight_surface: liveSurface,
    order_trace_audit: orderTraceAudit,
    live_execution: liveExecution,
    market_execution: marketExecution,
    manifest,
  }
}

export function listPredictionMarketRuns(
  input: Parameters<typeof listStoredPredictionMarketRuns>[0],
): PredictionMarketRunSummaryWithArtifactAudit[] {
  return listStoredPredictionMarketRuns(input).map(enrichPredictionMarketRunSummaryWithArtifactAudit)
}
