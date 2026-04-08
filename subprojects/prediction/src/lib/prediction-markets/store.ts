import { createHash } from 'node:crypto'
import { getDatabase } from '@/lib/db'
import {
  type AutonomousAgentReport,
  type BasketIntentPreview,
  type EvidencePacket,
  type ExecutionIntentPreview,
  type MarketDescriptor,
  type MarketRecommendationPacket,
  type PredictionMarketArtifactRef,
  type MarketSnapshot,
  type PredictionMarketArtifactType,
  type PredictionMarketJsonArtifact,
  type LatencyReferenceBundle,
  type TradeIntentGuard,
  type MultiVenueExecution,
  type PredictionMarketProvenanceBundle,
  type ResearchBridgeBundle,
  type ResolutionAnomalyReport,
  type PredictionMarketRunSummary,
  type PredictionMarketVenue,
  type ResolutionPolicy,
  type RunManifest,
  type ForecastPacket,
  type QuotePairIntentPreview,
  type StrategyCandidatePacket,
  type StrategyDecisionPacket,
  type StrategyShadowReport,
  type StrategyShadowSummary,
  autonomousAgentReportSchema,
  basketIntentPreviewSchema,
  evidencePacketSchema,
  executionIntentPreviewSchema,
  forecastPacketSchema,
  latencyReferenceBundleSchema,
  marketDescriptorSchema,
  marketRecommendationPacketSchema,
  marketSnapshotSchema,
  multiVenueExecutionSchema,
  predictionMarketJsonArtifactSchema,
  predictionMarketProvenanceBundleSchema,
  researchBridgeBundleSchema,
  predictionMarketRunSummarySchema,
  resolutionAnomalyReportSchema,
  resolutionPolicySchema,
  tradeIntentGuardSchema,
  quotePairIntentPreviewSchema,
  runManifestSchema,
  strategyCandidatePacketSchema,
  strategyDecisionPacketSchema,
  strategyShadowReportSchema,
  strategyShadowSummarySchema,
} from '@/lib/prediction-markets/schemas'
import { buildPredictionMarketArtifactLayout } from '@/lib/prediction-markets/artifact-layout'

type ArtifactPayload =
  | AutonomousAgentReport
  | BasketIntentPreview
  | MarketDescriptor
  | ExecutionIntentPreview
  | ResolutionPolicy
  | MarketSnapshot
  | ForecastPacket
  | LatencyReferenceBundle
  | MarketRecommendationPacket
  | PredictionMarketProvenanceBundle
  | QuotePairIntentPreview
  | ResearchBridgeBundle
  | ResolutionAnomalyReport
  | RunManifest
  | StrategyCandidatePacket
  | StrategyDecisionPacket
  | StrategyShadowReport
  | StrategyShadowSummary
  | PredictionMarketJsonArtifact
  | TradeIntentGuard
  | MultiVenueExecution
  | Array<ReturnType<typeof evidencePacketSchema.parse>>

type PersistArtifactInput = {
  workspaceId: number
  runId: string
  venue: PredictionMarketVenue
  marketId: string
  artifactType: PredictionMarketArtifactType
  payload: ArtifactPayload
}

type PersistExecutionInput = {
  workspaceId: number
  runId: string
  sourceRunId?: string
  venue: PredictionMarketVenue
  mode: 'advise' | 'replay'
  snapshot: MarketSnapshot
  resolutionPolicy: ResolutionPolicy
  evidencePackets: EvidencePacket[]
  forecast: ForecastPacket
  recommendation: MarketRecommendationPacket
  researchSidecar?: PredictionMarketJsonArtifact
  microstructureLab?: PredictionMarketJsonArtifact
  crossVenueIntelligence?: PredictionMarketJsonArtifact
  strategyCandidatePacket?: StrategyCandidatePacket
  strategyDecisionPacket?: StrategyDecisionPacket
  strategyShadowSummary?: StrategyShadowSummary
  strategyShadowReport?: StrategyShadowReport
  executionIntentPreview?: ExecutionIntentPreview
  quotePairIntentPreview?: QuotePairIntentPreview
  basketIntentPreview?: BasketIntentPreview
  latencyReferenceBundle?: LatencyReferenceBundle
  resolutionAnomalyReport?: ResolutionAnomalyReport
  autonomousAgentReport?: AutonomousAgentReport
  provenanceBundle?: PredictionMarketProvenanceBundle
  pipelineGuard?: PredictionMarketJsonArtifact
  runtimeGuard?: PredictionMarketJsonArtifact
  complianceReport?: PredictionMarketJsonArtifact
  executionReadiness?: PredictionMarketJsonArtifact
  executionPathways?: PredictionMarketJsonArtifact
  executionProjection?: PredictionMarketJsonArtifact
  shadowArbitrage?: PredictionMarketJsonArtifact
  paperSurface?: PredictionMarketJsonArtifact
  replaySurface?: PredictionMarketJsonArtifact
  tradeIntentGuard?: TradeIntentGuard
  multiVenueExecution?: MultiVenueExecution
  marketEvents?: PredictionMarketJsonArtifact
  marketPositions?: PredictionMarketJsonArtifact
  manifest: Omit<RunManifest, 'artifact_refs'>
}

type SummaryRow = {
  run_id: string
  source_run_id: string | null
  workspace_id: number
  venue: PredictionMarketVenue
  mode: 'advise' | 'replay'
  market_id: string
  market_slug: string | null
  status: 'running' | 'completed' | 'failed'
  recommendation: 'bet' | 'no_trade' | 'wait' | null
  side: 'yes' | 'no' | null
  confidence: number | null
  probability_yes: number | null
  market_price_yes: number | null
  edge_bps: number | null
  manifest_json: string
  artifact_index_json: string
  created_at: number
  updated_at: number
}

type ArtifactRow = {
  artifact_id: string
  artifact_type: PredictionMarketArtifactType
  sha256: string
  payload_json: string
}

function jsonHash(value: unknown): string {
  return createHash('sha256').update(JSON.stringify(value)).digest('hex')
}

function parseArtifactPayload(artifactType: PredictionMarketArtifactType, payloadJson: string): ArtifactPayload {
  const parsed = JSON.parse(payloadJson)

  switch (artifactType) {
    case 'market_descriptor':
      return marketDescriptorSchema.parse(parsed)
    case 'resolution_policy':
      return resolutionPolicySchema.parse(parsed)
    case 'market_snapshot':
      return marketSnapshotSchema.parse(parsed)
    case 'forecast_packet':
      return forecastPacketSchema.parse(parsed)
    case 'recommendation_packet':
      return marketRecommendationPacketSchema.parse(parsed)
    case 'strategy_candidate_packet':
      return strategyCandidatePacketSchema.parse(parsed)
    case 'strategy_decision_packet':
      return strategyDecisionPacketSchema.parse(parsed)
    case 'strategy_shadow_summary':
      return strategyShadowSummarySchema.parse(parsed)
    case 'strategy_shadow_report':
      return strategyShadowReportSchema.parse(parsed)
    case 'execution_intent_preview':
      return executionIntentPreviewSchema.parse(parsed)
    case 'quote_pair_intent_preview':
      return quotePairIntentPreviewSchema.parse(parsed)
    case 'basket_intent_preview':
      return basketIntentPreviewSchema.parse(parsed)
    case 'latency_reference_bundle':
      return latencyReferenceBundleSchema.parse(parsed)
    case 'resolution_anomaly_report':
      return resolutionAnomalyReportSchema.parse(parsed)
    case 'autonomous_agent_report':
      return autonomousAgentReportSchema.parse(parsed)
    case 'research_sidecar':
    case 'microstructure_lab':
    case 'cross_venue_intelligence':
    case 'market_events':
    case 'market_positions':
    case 'paper_surface':
    case 'replay_surface':
    case 'pipeline_guard':
    case 'runtime_guard':
    case 'compliance_report':
    case 'execution_readiness':
    case 'execution_pathways':
    case 'execution_projection':
    case 'shadow_arbitrage':
      return predictionMarketJsonArtifactSchema.parse(parsed)
    case 'trade_intent_guard':
      return tradeIntentGuardSchema.parse(parsed)
    case 'multi_venue_execution':
      return multiVenueExecutionSchema.parse(parsed)
    case 'provenance_bundle':
      return predictionMarketProvenanceBundleSchema.parse(parsed)
    case 'research_bridge':
      return researchBridgeBundleSchema.parse(parsed)
    case 'run_manifest':
      return runManifestSchema.parse(parsed)
    case 'evidence_bundle':
      return Array.isArray(parsed) ? parsed.map((item) => evidencePacketSchema.parse(item)) : []
  }

  throw new Error(`Unsupported prediction market artifact type: ${artifactType}`)
}

function hydrateSummary(row: SummaryRow): PredictionMarketRunSummary {
  return predictionMarketRunSummarySchema.parse({
    run_id: row.run_id,
    source_run_id: row.source_run_id,
    workspace_id: row.workspace_id,
    venue: row.venue,
    mode: row.mode,
    market_id: row.market_id,
    market_slug: row.market_slug,
    status: row.status,
    recommendation: row.recommendation,
    side: row.side,
    confidence: row.confidence,
    probability_yes: row.probability_yes,
    market_price_yes: row.market_price_yes,
    edge_bps: row.edge_bps,
    created_at: row.created_at,
    updated_at: row.updated_at,
    manifest: runManifestSchema.parse(JSON.parse(row.manifest_json)),
    artifact_refs: JSON.parse(row.artifact_index_json || '[]'),
  })
}

export function persistPredictionMarketArtifact(input: PersistArtifactInput) {
  const db = getDatabase()
  const payloadJson = JSON.stringify(input.payload)
  const layout = buildPredictionMarketArtifactLayout({
    run_id: input.runId,
    venue: input.venue,
    market_id: input.marketId,
    artifact_type: input.artifactType,
  })
  const artifactId = layout.artifact_id
  const sha256 = jsonHash(input.payload)

  db.prepare(`
    INSERT OR REPLACE INTO prediction_market_artifacts (
      artifact_id,
      workspace_id,
      run_id,
      artifact_type,
      sha256,
      payload_json,
      created_at
    ) VALUES (?, ?, ?, ?, ?, ?, (unixepoch()))
  `).run(
    artifactId,
    input.workspaceId,
    input.runId,
    input.artifactType,
    sha256,
    payloadJson,
  )

  return {
    artifact_id: artifactId,
    artifact_type: input.artifactType,
    sha256,
    layout_version: layout.layout_version,
    bucket: layout.bucket,
    file_name: layout.file_name,
    run_key: layout.run_key,
    market_key: layout.market_key,
    latest_key: layout.latest_key,
  }
}

type UpsertRunInput = {
  workspaceId: number
  runId: string
  sourceRunId?: string
  venue: PredictionMarketVenue
  mode: 'advise' | 'replay'
  marketId: string
  marketSlug?: string
  status: 'running' | 'completed' | 'failed'
  recommendation: 'bet' | 'no_trade' | 'wait' | null
  side: 'yes' | 'no' | null
  confidence: number | null
  probabilityYes: number | null
  marketPriceYes: number | null
  edgeBps: number | null
  manifest: RunManifest
  artifactRefs: PredictionMarketArtifactRef[]
}

export function upsertPredictionMarketRun(input: UpsertRunInput): PredictionMarketRunSummary {
  const db = getDatabase()
  const now = Math.floor(Date.now() / 1000)

  db.prepare(`
    INSERT INTO prediction_market_runs (
      run_id,
      source_run_id,
      workspace_id,
      venue,
      mode,
      market_id,
      market_slug,
      status,
      recommendation,
      side,
      confidence,
      probability_yes,
      market_price_yes,
      edge_bps,
      manifest_json,
      artifact_index_json,
      created_at,
      updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(run_id) DO UPDATE SET
      source_run_id = excluded.source_run_id,
      status = excluded.status,
      recommendation = excluded.recommendation,
      side = excluded.side,
      confidence = excluded.confidence,
      probability_yes = excluded.probability_yes,
      market_price_yes = excluded.market_price_yes,
      edge_bps = excluded.edge_bps,
      manifest_json = excluded.manifest_json,
      artifact_index_json = excluded.artifact_index_json,
      updated_at = excluded.updated_at
  `).run(
    input.runId,
    input.sourceRunId ?? null,
    input.workspaceId,
    input.venue,
    input.mode,
    input.marketId,
    input.marketSlug ?? null,
    input.status,
    input.recommendation,
    input.side,
    input.confidence,
    input.probabilityYes,
    input.marketPriceYes,
    input.edgeBps,
    JSON.stringify(input.manifest),
    JSON.stringify(input.artifactRefs),
    now,
    now,
  )

  return getPredictionMarketRunSummary(input.runId, input.workspaceId)!
}

export function persistPredictionMarketExecution(input: PersistExecutionInput) {
  const db = getDatabase()
  const transaction = db.transaction(() => {
    const provisionalManifest = runManifestSchema.parse({
      ...input.manifest,
      artifact_refs: [],
    })

    upsertPredictionMarketRun({
      workspaceId: input.workspaceId,
      runId: input.runId,
      sourceRunId: input.sourceRunId,
      venue: input.venue,
      mode: input.mode,
      marketId: input.snapshot.market.market_id,
      marketSlug: input.snapshot.market.slug,
      status: input.manifest.status,
      recommendation: input.recommendation.action,
      side: input.recommendation.side,
      confidence: input.recommendation.confidence,
      probabilityYes: input.forecast.probability_yes,
      marketPriceYes: input.recommendation.market_price_yes,
      edgeBps: input.recommendation.edge_bps,
      manifest: provisionalManifest,
      artifactRefs: [],
    })

    const dataArtifactRefs: PredictionMarketArtifactRef[] = [
      persistPredictionMarketArtifact({
        workspaceId: input.workspaceId,
        runId: input.runId,
        venue: input.venue,
        marketId: input.snapshot.market.market_id,
        artifactType: 'market_descriptor',
        payload: input.snapshot.market,
      }),
      persistPredictionMarketArtifact({
        workspaceId: input.workspaceId,
        runId: input.runId,
        venue: input.venue,
        marketId: input.snapshot.market.market_id,
        artifactType: 'resolution_policy',
        payload: input.resolutionPolicy,
      }),
      persistPredictionMarketArtifact({
        workspaceId: input.workspaceId,
        runId: input.runId,
        venue: input.venue,
        marketId: input.snapshot.market.market_id,
        artifactType: 'market_snapshot',
        payload: input.snapshot,
      }),
      persistPredictionMarketArtifact({
        workspaceId: input.workspaceId,
        runId: input.runId,
        venue: input.venue,
        marketId: input.snapshot.market.market_id,
        artifactType: 'evidence_bundle',
        payload: input.evidencePackets,
      }),
      persistPredictionMarketArtifact({
        workspaceId: input.workspaceId,
        runId: input.runId,
        venue: input.venue,
        marketId: input.snapshot.market.market_id,
        artifactType: 'forecast_packet',
        payload: input.forecast,
      }),
      persistPredictionMarketArtifact({
        workspaceId: input.workspaceId,
        runId: input.runId,
        venue: input.venue,
        marketId: input.snapshot.market.market_id,
        artifactType: 'recommendation_packet',
        payload: input.recommendation,
      }),
    ]
    const optionalArtifacts: Array<ReturnType<typeof persistPredictionMarketArtifact> | null> = [
      input.researchSidecar
      ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'research_sidecar',
          payload: input.researchSidecar,
        })
        : null,
      input.microstructureLab
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'microstructure_lab',
          payload: input.microstructureLab,
        })
        : null,
      input.crossVenueIntelligence
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'cross_venue_intelligence',
          payload: input.crossVenueIntelligence,
        })
        : null,
      input.strategyCandidatePacket
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'strategy_candidate_packet',
          payload: input.strategyCandidatePacket,
        })
        : null,
      input.strategyDecisionPacket
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'strategy_decision_packet',
          payload: input.strategyDecisionPacket,
        })
        : null,
      input.strategyShadowSummary
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'strategy_shadow_summary',
          payload: input.strategyShadowSummary,
        })
        : null,
      input.strategyShadowReport
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'strategy_shadow_report',
          payload: input.strategyShadowReport,
        })
        : null,
      input.executionIntentPreview
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'execution_intent_preview',
          payload: input.executionIntentPreview,
        })
        : null,
      input.quotePairIntentPreview
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'quote_pair_intent_preview',
          payload: input.quotePairIntentPreview,
        })
        : null,
      input.basketIntentPreview
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'basket_intent_preview',
          payload: input.basketIntentPreview,
        })
        : null,
      input.latencyReferenceBundle
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'latency_reference_bundle',
          payload: input.latencyReferenceBundle,
        })
        : null,
      input.resolutionAnomalyReport
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'resolution_anomaly_report',
          payload: input.resolutionAnomalyReport,
        })
        : null,
      input.autonomousAgentReport
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'autonomous_agent_report',
          payload: input.autonomousAgentReport,
        })
        : null,
      input.provenanceBundle
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'provenance_bundle',
          payload: input.provenanceBundle,
        })
        : null,
      input.marketEvents
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'market_events',
          payload: input.marketEvents,
        })
        : null,
      input.marketPositions
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'market_positions',
          payload: input.marketPositions,
        })
        : null,
      input.paperSurface
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'paper_surface',
          payload: input.paperSurface,
        })
        : null,
      input.replaySurface
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'replay_surface',
          payload: input.replaySurface,
        })
        : null,
      input.pipelineGuard
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'pipeline_guard',
          payload: input.pipelineGuard,
        })
        : null,
      input.runtimeGuard
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'runtime_guard',
          payload: input.runtimeGuard,
        })
        : null,
      input.complianceReport
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'compliance_report',
          payload: input.complianceReport,
        })
        : null,
      input.executionReadiness
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'execution_readiness',
          payload: input.executionReadiness,
        })
        : null,
      input.executionPathways
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'execution_pathways',
          payload: input.executionPathways,
        })
        : null,
      input.executionProjection
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'execution_projection',
          payload: input.executionProjection,
        })
        : null,
      input.shadowArbitrage
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'shadow_arbitrage',
          payload: input.shadowArbitrage,
        })
        : null,
      input.tradeIntentGuard
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'trade_intent_guard',
          payload: input.tradeIntentGuard,
        })
        : null,
      input.multiVenueExecution
        ? persistPredictionMarketArtifact({
          workspaceId: input.workspaceId,
          runId: input.runId,
          venue: input.venue,
          marketId: input.snapshot.market.market_id,
          artifactType: 'multi_venue_execution',
          payload: input.multiVenueExecution,
        })
        : null,
    ]
    const optionalArtifactRefs = optionalArtifacts.filter(
      (artifact): artifact is ReturnType<typeof persistPredictionMarketArtifact> => artifact != null,
    )

    const allArtifactRefs: PredictionMarketArtifactRef[] = [...dataArtifactRefs, ...optionalArtifactRefs]

    const finalManifest = runManifestSchema.parse({
      ...input.manifest,
      artifact_refs: allArtifactRefs,
    })

    const manifestArtifactRef = persistPredictionMarketArtifact({
      workspaceId: input.workspaceId,
      runId: input.runId,
      venue: input.venue,
      marketId: input.snapshot.market.market_id,
      artifactType: 'run_manifest',
      payload: finalManifest,
    })
    const artifactRefs = [...allArtifactRefs, manifestArtifactRef]

    const summary = upsertPredictionMarketRun({
      workspaceId: input.workspaceId,
      runId: input.runId,
      sourceRunId: input.sourceRunId,
      venue: input.venue,
      mode: input.mode,
      marketId: input.snapshot.market.market_id,
      marketSlug: input.snapshot.market.slug,
      status: input.manifest.status,
      recommendation: input.recommendation.action,
      side: input.recommendation.side,
      confidence: input.recommendation.confidence,
      probabilityYes: input.forecast.probability_yes,
      marketPriceYes: input.recommendation.market_price_yes,
      edgeBps: input.recommendation.edge_bps,
      manifest: finalManifest,
      artifactRefs,
    })

    return {
      summary,
      artifactRefs,
      manifest: finalManifest,
    }
  })

  return transaction()
}

export function getPredictionMarketRunSummary(runId: string, workspaceId: number): PredictionMarketRunSummary | null {
  const db = getDatabase()
  const row = db.prepare(`
    SELECT *
    FROM prediction_market_runs
    WHERE run_id = ? AND workspace_id = ?
  `).get(runId, workspaceId) as SummaryRow | undefined

  return row ? hydrateSummary(row) : null
}

export function listPredictionMarketRuns(input: {
  workspaceId: number
  venue?: PredictionMarketVenue
  recommendation?: 'bet' | 'no_trade' | 'wait'
  limit?: number
}): PredictionMarketRunSummary[] {
  const db = getDatabase()
  const params: Array<string | number> = [input.workspaceId]
  let sql = `
    SELECT *
    FROM prediction_market_runs
    WHERE workspace_id = ?
  `

  if (input.venue) {
    sql += ' AND venue = ?'
    params.push(input.venue)
  }

  if (input.recommendation) {
    sql += ' AND recommendation = ?'
    params.push(input.recommendation)
  }

  sql += ' ORDER BY created_at DESC LIMIT ?'
  params.push(Math.max(1, Math.min(input.limit ?? 20, 100)))

  const rows = db.prepare(sql).all(...params) as SummaryRow[]
  return rows.map(hydrateSummary)
}

export function findRecentPredictionMarketRunByConfig(input: {
  workspaceId: number
  venue: PredictionMarketVenue
  marketId: string
  mode: 'advise' | 'replay'
  configHash: string
  sourceRunId?: string
  windowSec: number
}): PredictionMarketRunSummary | null {
  if (!Number.isFinite(input.windowSec) || input.windowSec <= 0) return null

  const db = getDatabase()
  const rows = db.prepare(`
    SELECT *
    FROM prediction_market_runs
    WHERE workspace_id = ?
      AND venue = ?
      AND market_id = ?
      AND mode = ?
      AND status = 'completed'
    ORDER BY updated_at DESC
    LIMIT 25
  `).all(input.workspaceId, input.venue, input.marketId, input.mode) as SummaryRow[]

  const cutoff = Math.floor(Date.now() / 1000) - input.windowSec

  for (const row of rows) {
    const summary = hydrateSummary(row)
    if (summary.updated_at < cutoff) continue
    if (summary.manifest.config_hash !== input.configHash) continue
    if ((input.sourceRunId ?? null) !== (summary.source_run_id ?? null)) continue
    return summary
  }

  return null
}

export function getPredictionMarketRunDetails(runId: string, workspaceId: number) {
  const db = getDatabase()
  const summary = getPredictionMarketRunSummary(runId, workspaceId)
  if (!summary) return null

  const artifactRows = db.prepare(`
    SELECT artifact_id, artifact_type, sha256, payload_json
    FROM prediction_market_artifacts
    WHERE run_id = ? AND workspace_id = ?
    ORDER BY created_at ASC
  `).all(runId, workspaceId) as ArtifactRow[]

  const artifacts = artifactRows.map((row) => ({
    artifact_id: row.artifact_id,
    artifact_type: row.artifact_type,
    sha256: row.sha256,
    payload: parseArtifactPayload(row.artifact_type, row.payload_json),
  }))

  return {
    ...summary,
    artifacts,
  }
}
