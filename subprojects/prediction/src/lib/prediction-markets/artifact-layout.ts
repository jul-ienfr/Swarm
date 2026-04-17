import type {
  PredictionMarketArtifactType,
  PredictionMarketVenue,
} from '@/lib/prediction-markets/schemas'

export const PREDICTION_MARKETS_ARTIFACT_LAYOUT_VERSION = 'v1'
export const PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT =
  `prediction-markets/${PREDICTION_MARKETS_ARTIFACT_LAYOUT_VERSION}`
export const PREDICTION_MARKETS_ARTIFACT_BUCKETS = [
  'catalog',
  'orderbooks',
  'trades',
  'resolution',
  'evidence',
  'runs',
] as const

export type PredictionMarketArtifactBucket =
  (typeof PREDICTION_MARKETS_ARTIFACT_BUCKETS)[number]

export type PredictionMarketLayoutArtifactType =
  | PredictionMarketArtifactType
  | 'catalog_index'
  | 'orderbook_snapshot'
  | 'trade_tape'

export type PredictionMarketArtifactLayoutInput = {
  run_id: string
  venue: PredictionMarketVenue
  market_id: string
  artifact_type: PredictionMarketLayoutArtifactType
}

export type PredictionMarketArtifactLayout = {
  layout_version: typeof PREDICTION_MARKETS_ARTIFACT_LAYOUT_VERSION
  root_prefix: string
  artifact_id: string
  artifact_type: PredictionMarketLayoutArtifactType
  bucket: PredictionMarketArtifactBucket
  extension: 'json' | 'jsonl'
  file_name: string
  venue: PredictionMarketVenue
  market_id: string
  run_id: string
  venue_root: string
  market_root: string
  bucket_root: string
  run_root: string
  run_path: string
  market_path: string
  latest_path: string
  run_key: string
  market_key: string
  latest_key: string
  manifest_keys: PredictionMarketArtifactManifestKeys
}

export type PredictionMarketArtifactManifestKeys = {
  artifact_id: string
  artifact_type: PredictionMarketLayoutArtifactType
  bucket: PredictionMarketArtifactBucket
  file_name: string
  run_key: string
  market_key: string
  latest_key: string
}

type ArtifactLayoutDescriptor = {
  bucket: PredictionMarketArtifactBucket
  basename: string
  extension: 'json' | 'jsonl'
}

const ARTIFACT_LAYOUT_BY_TYPE: Record<PredictionMarketLayoutArtifactType, ArtifactLayoutDescriptor> = {
  catalog_index: {
    bucket: 'catalog',
    basename: 'catalog_index',
    extension: 'json',
  },
  market_descriptor: {
    bucket: 'catalog',
    basename: 'market_descriptor',
    extension: 'json',
  },
  orderbook_snapshot: {
    bucket: 'orderbooks',
    basename: 'orderbook_snapshot',
    extension: 'json',
  },
  trade_tape: {
    bucket: 'trades',
    basename: 'trade_tape',
    extension: 'jsonl',
  },
  resolution_policy: {
    bucket: 'resolution',
    basename: 'resolution_policy',
    extension: 'json',
  },
  evidence_bundle: {
    bucket: 'evidence',
    basename: 'evidence_bundle',
    extension: 'json',
  },
  research_sidecar: {
    bucket: 'evidence',
    basename: 'research_sidecar',
    extension: 'json',
  },
  timesfm_sidecar: {
    bucket: 'evidence',
    basename: 'timesfm_sidecar',
    extension: 'json',
  },
  source_audit: {
    bucket: 'evidence',
    basename: 'source_audit',
    extension: 'json',
  },
  rules_lineage: {
    bucket: 'evidence',
    basename: 'rules_lineage',
    extension: 'json',
  },
  catalyst_timeline: {
    bucket: 'evidence',
    basename: 'catalyst_timeline',
    extension: 'json',
  },
  world_state: {
    bucket: 'runs',
    basename: 'world_state',
    extension: 'json',
  },
  ticket_payload: {
    bucket: 'runs',
    basename: 'ticket_payload',
    extension: 'json',
  },
  quant_signal_bundle: {
    bucket: 'runs',
    basename: 'quant_signal_bundle',
    extension: 'json',
  },
  decision_ledger: {
    bucket: 'runs',
    basename: 'decision_ledger',
    extension: 'json',
  },
  calibration_report: {
    bucket: 'runs',
    basename: 'calibration_report',
    extension: 'json',
  },
  resolved_history: {
    bucket: 'runs',
    basename: 'resolved_history',
    extension: 'json',
  },
  cost_model_report: {
    bucket: 'runs',
    basename: 'cost_model_report',
    extension: 'json',
  },
  walk_forward_report: {
    bucket: 'runs',
    basename: 'walk_forward_report',
    extension: 'json',
  },
  autopilot_cycle_summary: {
    bucket: 'runs',
    basename: 'autopilot_cycle_summary',
    extension: 'json',
  },
  research_memory_summary: {
    bucket: 'runs',
    basename: 'research_memory_summary',
    extension: 'json',
  },
  research_bridge: {
    bucket: 'evidence',
    basename: 'research_bridge',
    extension: 'json',
  },
  microstructure_lab: {
    bucket: 'runs',
    basename: 'microstructure_lab',
    extension: 'json',
  },
  cross_venue_intelligence: {
    bucket: 'evidence',
    basename: 'cross_venue_intelligence',
    extension: 'json',
  },
  strategy_candidate_packet: {
    bucket: 'runs',
    basename: 'strategy_candidate_packet',
    extension: 'json',
  },
  strategy_decision_packet: {
    bucket: 'runs',
    basename: 'strategy_decision_packet',
    extension: 'json',
  },
  strategy_shadow_summary: {
    bucket: 'runs',
    basename: 'strategy_shadow_summary',
    extension: 'json',
  },
  strategy_shadow_report: {
    bucket: 'runs',
    basename: 'strategy_shadow_report',
    extension: 'json',
  },
  execution_intent_preview: {
    bucket: 'runs',
    basename: 'execution_intent_preview',
    extension: 'json',
  },
  quote_pair_intent_preview: {
    bucket: 'runs',
    basename: 'quote_pair_intent_preview',
    extension: 'json',
  },
  basket_intent_preview: {
    bucket: 'runs',
    basename: 'basket_intent_preview',
    extension: 'json',
  },
  latency_reference_bundle: {
    bucket: 'runs',
    basename: 'latency_reference_bundle',
    extension: 'json',
  },
  resolution_anomaly_report: {
    bucket: 'runs',
    basename: 'resolution_anomaly_report',
    extension: 'json',
  },
  autonomous_agent_report: {
    bucket: 'runs',
    basename: 'autonomous_agent_report',
    extension: 'json',
  },
  provenance_bundle: {
    bucket: 'evidence',
    basename: 'provenance_bundle',
    extension: 'json',
  },
  market_snapshot: {
    bucket: 'runs',
    basename: 'market_snapshot',
    extension: 'json',
  },
  forecast_packet: {
    bucket: 'runs',
    basename: 'forecast_packet',
    extension: 'json',
  },
  recommendation_packet: {
    bucket: 'runs',
    basename: 'recommendation_packet',
    extension: 'json',
  },
  paper_surface: {
    bucket: 'runs',
    basename: 'paper_surface',
    extension: 'json',
  },
  replay_surface: {
    bucket: 'runs',
    basename: 'replay_surface',
    extension: 'json',
  },
  market_events: {
    bucket: 'runs',
    basename: 'market_events',
    extension: 'json',
  },
  market_positions: {
    bucket: 'runs',
    basename: 'market_positions',
    extension: 'json',
  },
  pipeline_guard: {
    bucket: 'runs',
    basename: 'pipeline_guard',
    extension: 'json',
  },
  runtime_guard: {
    bucket: 'runs',
    basename: 'runtime_guard',
    extension: 'json',
  },
  compliance_report: {
    bucket: 'runs',
    basename: 'compliance_report',
    extension: 'json',
  },
  execution_readiness: {
    bucket: 'runs',
    basename: 'execution_readiness',
    extension: 'json',
  },
  execution_pathways: {
    bucket: 'runs',
    basename: 'execution_pathways',
    extension: 'json',
  },
  execution_projection: {
    bucket: 'runs',
    basename: 'execution_projection',
    extension: 'json',
  },
  shadow_arbitrage: {
    bucket: 'runs',
    basename: 'shadow_arbitrage',
    extension: 'json',
  },
  trade_intent_guard: {
    bucket: 'runs',
    basename: 'trade_intent_guard',
    extension: 'json',
  },
  multi_venue_execution: {
    bucket: 'runs',
    basename: 'multi_venue_execution',
    extension: 'json',
  },
  run_manifest: {
    bucket: 'runs',
    basename: 'run_manifest',
    extension: 'json',
  },
}

function encodeSegment(value: string): string {
  const trimmed = value.trim()
  return trimmed.length > 0
    ? encodeURIComponent(trimmed)
    : 'unknown'
}

function joinPath(...parts: string[]): string {
  return parts.map((part) => part.replace(/^\/+|\/+$/g, '')).filter(Boolean).join('/')
}

export function getPredictionMarketVenueRoot(venue: PredictionMarketVenue): string {
  return joinPath(
    PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT,
    'venues',
    encodeSegment(venue),
  )
}

export function getPredictionMarketMarketRoot(input: {
  venue: PredictionMarketVenue
  market_id: string
}): string {
  return joinPath(
    getPredictionMarketVenueRoot(input.venue),
    'markets',
    encodeSegment(input.market_id),
  )
}

export function getPredictionMarketBucketRoot(input: {
  venue: PredictionMarketVenue
  market_id: string
  bucket: PredictionMarketArtifactBucket
}): string {
  return joinPath(
    getPredictionMarketMarketRoot({
      venue: input.venue,
      market_id: input.market_id,
    }),
    input.bucket,
  )
}

export function getPredictionMarketRunRoot(runId: string): string {
  return joinPath(
    PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT,
    'runs',
    encodeSegment(runId),
  )
}

export function getPredictionMarketArtifactDescriptor(
  artifactType: PredictionMarketLayoutArtifactType,
): ArtifactLayoutDescriptor {
  return ARTIFACT_LAYOUT_BY_TYPE[artifactType]
}

export function buildPredictionMarketArtifactManifestKeys(input: {
  artifact_id: string
  artifact_type: PredictionMarketLayoutArtifactType
  bucket: PredictionMarketArtifactBucket
  file_name: string
  run_key: string
  market_key: string
  latest_key: string
}): PredictionMarketArtifactManifestKeys {
  return {
    artifact_id: input.artifact_id,
    artifact_type: input.artifact_type,
    bucket: input.bucket,
    file_name: input.file_name,
    run_key: input.run_key,
    market_key: input.market_key,
    latest_key: input.latest_key,
  }
}

export function buildPredictionMarketArtifactLayout(
  input: PredictionMarketArtifactLayoutInput,
): PredictionMarketArtifactLayout {
  const descriptor = getPredictionMarketArtifactDescriptor(input.artifact_type)
  const fileName = `${descriptor.basename}.${descriptor.extension}`
  const runSafe = encodeSegment(input.run_id)
  const artifactId = `${input.run_id}:${input.artifact_type}`
  const venueRoot = getPredictionMarketVenueRoot(input.venue)
  const marketRoot = getPredictionMarketMarketRoot({
    venue: input.venue,
    market_id: input.market_id,
  })
  const bucketRoot = getPredictionMarketBucketRoot({
    venue: input.venue,
    market_id: input.market_id,
    bucket: descriptor.bucket,
  })
  const runRoot = joinPath(getPredictionMarketRunRoot(input.run_id), descriptor.bucket)
  const runPath = joinPath(runRoot, fileName)
  const marketPath = joinPath(bucketRoot, `${runSafe}--${fileName}`)
  const latestPath = joinPath(bucketRoot, `latest--${fileName}`)
  const manifestKeys = buildPredictionMarketArtifactManifestKeys({
    artifact_id: artifactId,
    artifact_type: input.artifact_type,
    bucket: descriptor.bucket,
    file_name: fileName,
    run_key: runPath,
    market_key: marketPath,
    latest_key: latestPath,
  })

  return {
    layout_version: PREDICTION_MARKETS_ARTIFACT_LAYOUT_VERSION,
    root_prefix: PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT,
    artifact_id: artifactId,
    artifact_type: input.artifact_type,
    bucket: descriptor.bucket,
    extension: descriptor.extension,
    file_name: fileName,
    venue: input.venue,
    market_id: input.market_id,
    run_id: input.run_id,
    venue_root: venueRoot,
    market_root: marketRoot,
    bucket_root: bucketRoot,
    run_root: runRoot,
    run_path: runPath,
    market_path: marketPath,
    latest_path: latestPath,
    run_key: runPath,
    market_key: marketPath,
    latest_key: latestPath,
    manifest_keys: manifestKeys,
  }
}
