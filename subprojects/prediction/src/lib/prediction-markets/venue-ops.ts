import {
  getKalshiDefaultBudgets,
  getKalshiVenueCapabilities,
  getKalshiVenueHealthSnapshot,
} from '@/lib/prediction-markets/kalshi'
import {
  getPolymarketDefaultBudgets,
  getPolymarketVenueCapabilities,
  getPolymarketVenueHealthSnapshot,
} from '@/lib/prediction-markets/polymarket'
import {
  marketFeedSurfaceSchema,
  predictionMarketBudgetsSchema,
  predictionMarketVenueCoverageSchema,
  venueCapabilitiesSchema,
  venueHealthSnapshotSchema,
  type MarketFeedSurface as MarketFeedSurfaceContract,
  type PredictionMarketVenueCoverage,
} from '@/lib/prediction-markets/schemas'
import {
  getPredictionMarketVenueStrategy,
  type PredictionMarketVenueSourceHierarchyEntry,
  type PredictionMarketVenueStrategy,
} from '@/lib/prediction-markets/venue-strategy'

export type PredictionMarketVenueId = 'polymarket' | 'kalshi'

const POLYMARKET_MARKET_WEBSOCKET_URL = 'wss://ws-subscriptions-clob.polymarket.com/ws/market'
const POLYMARKET_USER_WEBSOCKET_URL = 'wss://ws-subscriptions-clob.polymarket.com/ws/user'
const POLYMARKET_RTDS_URL = 'wss://ws-live-data.polymarket.com'

export type VenueCapabilities = {
  venue: PredictionMarketVenueId
  label: string
  venue_type: 'execution-equivalent' | 'execution-like' | 'reference-only'
  market_shape: 'binary_only' | 'binary_or_multi_outcome'
  supports: {
    list_markets: boolean
    get_market: boolean
    build_snapshot: boolean
    orderbook: boolean
    history: boolean
    search: boolean
    replay: boolean
  }
  limits: {
    binary_only: boolean
    max_list_limit: number
    max_history_limit: number
  }
  notes: string[]
}

export type VenueHealthSnapshot = {
  venue: PredictionMarketVenueId
  status: 'ready' | 'degraded'
  checked_at: string
  network_checked: false
  read_only: true
  configured_endpoints: string[]
  reasons: string[]
}

export type VenueBudgets = {
  venue: PredictionMarketVenueId
  default_list_limit: number
  max_list_limit: number
  default_history_limit: number
  max_history_limit: number
  timeout_ms: number
  max_http_requests_per_snapshot: number
  max_search_pages: number
  max_parallel_requests: number
  conservative: true
}

export type VenueStrategy = PredictionMarketVenueStrategy
export type VenueSourceHierarchyEntry = PredictionMarketVenueSourceHierarchyEntry

export function getVenueCapabilities(venue: PredictionMarketVenueId): VenueCapabilities {
  switch (venue) {
    case 'kalshi':
      return getKalshiVenueCapabilities()
    case 'polymarket':
      return getPolymarketVenueCapabilities()
    default:
      throw new Error(`Unsupported prediction market venue: ${venue}`)
  }
}

export function getVenueHealthSnapshot(venue: PredictionMarketVenueId): VenueHealthSnapshot {
  switch (venue) {
    case 'kalshi':
      return getKalshiVenueHealthSnapshot()
    case 'polymarket':
      return getPolymarketVenueHealthSnapshot()
    default:
      throw new Error(`Unsupported prediction market venue: ${venue}`)
  }
}

export function getVenueBudgets(venue: PredictionMarketVenueId): VenueBudgets {
  switch (venue) {
    case 'kalshi':
      return getKalshiDefaultBudgets()
    case 'polymarket':
      return getPolymarketDefaultBudgets()
    default:
      throw new Error(`Unsupported prediction market venue: ${venue}`)
  }
}

export function listPredictionMarketVenues(): PredictionMarketVenueId[] {
  return ['polymarket', 'kalshi']
}

export function getVenueStrategy(venue: PredictionMarketVenueId): VenueStrategy {
  return getPredictionMarketVenueStrategy(venue)
}

export function getVenueStrategyContract(venue: PredictionMarketVenueId): VenueStrategy {
  return getVenueStrategy(venue)
}

export function getVenueSourceHierarchy(venue: PredictionMarketVenueId): VenueSourceHierarchyEntry[] {
  return getVenueStrategy(venue).source_hierarchy
}

export function getVenueCapabilitiesContract(venue: PredictionMarketVenueId) {
  const capabilities = getVenueCapabilities(venue)
  const strategy = getVenueStrategy(venue)
  const sourceHierarchy = strategy.source_hierarchy
  const communityReference = strategy.community_reference
  const supportsPositions = true
  const supportsExecution = false
  const supportsWebsocket = true
  const supportsPaperMode = venue === 'kalshi'
  const tradeable = capabilities.venue_type === 'execution-equivalent'
  const manualReviewRequired = true

  return venueCapabilitiesSchema.parse({
    venue: capabilities.venue,
    venue_type: capabilities.venue_type,
    supports_discovery: capabilities.supports.list_markets,
    supports_metadata: capabilities.supports.get_market,
    supports_orderbook: capabilities.supports.orderbook,
    supports_trades: capabilities.supports.history,
    supports_positions: supportsPositions,
    supports_execution: supportsExecution,
    supports_websocket: supportsWebsocket,
    supports_paper_mode: supportsPaperMode,
    tradeable,
    manual_review_required: manualReviewRequired,
    supported_order_types: ['limit'],
    planned_order_types: ['limit'],
    rate_limit_notes: [
      `source_of_truth:${strategy.source_of_truth}#priority:${sourceHierarchy[0]?.priority ?? 1}`,
      `community_reference:${communityReference.source}#priority:${communityReference.priority}`,
      `execution_eligible:${strategy.execution_eligible}`,
      ...capabilities.notes,
    ].join(' | '),
    automation_constraints: supportsExecution
      ? []
      : ['read-only advisory mode only'],
  })
}

export function getVenueHealthSnapshotContract(venue: PredictionMarketVenueId) {
  const health = getVenueHealthSnapshot(venue)
  const degraded = health.status !== 'ready' || health.reasons.length > 0

  return venueHealthSnapshotSchema.parse({
    venue: health.venue,
    captured_at: health.checked_at,
    health_score: degraded ? 65 : 100,
    api_status: degraded ? 'degraded' : 'ok',
    stream_status: 'unknown',
    staleness_ms: 0,
    degraded_mode: degraded,
    incident_flags: health.reasons,
    notes: health.configured_endpoints.join(', '),
  })
}

export function getVenueBudgetsContract(venue: PredictionMarketVenueId) {
  const budgets = getVenueBudgets(venue)

  return predictionMarketBudgetsSchema.parse({
    fetch_latency_budget_ms: budgets.timeout_ms,
    snapshot_freshness_ms: budgets.timeout_ms,
    decision_latency_ms: budgets.timeout_ms,
    stream_reconnect_ms: budgets.timeout_ms * 2,
    cache_ttl_ms: budgets.timeout_ms,
    max_retries: 0,
    backpressure_policy: budgets.conservative ? 'degrade-to-wait' : 'best-effort',
  })
}

export function getVenueFeedSurfaceContract(venue: PredictionMarketVenueId): MarketFeedSurfaceContract {
  const capabilities = getVenueCapabilities(venue)
  const strategy = getVenueStrategy(venue)
  const sourceHierarchy = strategy.source_hierarchy
  const communityReference = strategy.community_reference
  const websocketSummary = 'WebSocket market/user feeds and RTDS are operator-bound surfaces, not auto-connected live transports.'
  const apiAccess = [
    `source_of_truth:${strategy.source_of_truth}`,
    `community_reference:${communityReference.source}`,
    `execution_eligible:${strategy.execution_eligible}`,
  ]
  const tradeable = capabilities.venue_type === 'execution-equivalent'
  const manualReviewRequired = true

  return marketFeedSurfaceSchema.parse({
    venue: capabilities.venue,
    venue_type: capabilities.venue_type,
    backend_mode: 'read_only',
    ingestion_mode: 'read_only',
    market_feed_kind: 'market_snapshot',
    user_feed_kind: 'position_snapshot',
    supports_discovery: capabilities.supports.list_markets,
    supports_orderbook: capabilities.supports.orderbook,
    supports_trades: capabilities.supports.history,
    supports_execution: false,
    supports_paper_mode: venue === 'kalshi',
    supports_market_feed: true,
    supports_user_feed: true,
    supports_events: true,
    supports_positions: true,
    supports_websocket: true,
    supports_rtds: true,
    live_streaming: false,
    websocket_status: 'operator_bound',
    market_websocket_status: 'operator_bound',
    user_feed_websocket_status: 'operator_bound',
    tradeable,
    manual_review_required: manualReviewRequired,
    api_access: apiAccess,
    supported_order_types: ['limit'],
    planned_order_types: ['limit'],
    rate_limit_notes: [
      `source_of_truth:${strategy.source_of_truth}#priority:${sourceHierarchy[0]?.priority ?? 1}`,
      `community_reference:${communityReference.source}#priority:${communityReference.priority}`,
      `execution_eligible:${strategy.execution_eligible}`,
      ...capabilities.notes,
    ],
    automation_constraints: [
      'read-only advisory mode only',
      'websocket and RTDS surfaces are operator-bound only',
    ],
    market_feed_transport: 'local_cache',
    user_feed_transport: 'local_cache',
    market_feed_status: 'local_cache',
    user_feed_status: 'local_cache',
    rtds_status: 'operator_bound',
    events_source: 'snapshot_polling',
    positions_source: 'local_position_cache',
    market_feed_source: 'snapshot_polling',
    user_feed_source: 'local_position_cache',
    configured_endpoints: {
      market_feed_source: 'snapshot_polling',
      user_feed_source: 'local_position_cache',
      market_websocket: POLYMARKET_MARKET_WEBSOCKET_URL,
      user_websocket: POLYMARKET_USER_WEBSOCKET_URL,
      rtds: POLYMARKET_RTDS_URL,
    },
    summary: `Read-only market and user snapshot feeds remain available for ${capabilities.label} in swarm; ${websocketSummary} The surface stays manual-review-only until an operator binds the live transport.`,
    runbook: {
      runbook_id: `${venue}_read_only_feed_surface`,
      recovery_steps: [
        'Use snapshot polling for market feed refreshes.',
        'Use local cache for user feed snapshots.',
        'Bind the operator session before attempting websocket or RTDS use.',
      ],
      source_hierarchy: sourceHierarchy.map((entry) => ({
        source: entry.source,
        priority: entry.priority,
      })),
    },
    notes: [
      'read_only_support_only',
      'websocket_operator_bound_only',
      'rtds_operator_bound_only',
    ],
    metadata_gap_count: 0,
    metadata_gap_rate: 0,
    metadata_completeness: 1,
    metadata: {
      read_only: true,
      backend_mode: 'read_only',
      venue_type: capabilities.venue_type,
      source_of_truth: strategy.source_of_truth,
      community_reference: communityReference.source,
      execution_eligible: strategy.execution_eligible,
      supports_discovery: capabilities.supports.list_markets,
      supports_orderbook: capabilities.supports.orderbook,
      supports_trades: capabilities.supports.history,
      supports_execution: false,
      supports_websocket: true,
      supports_paper_mode: venue === 'kalshi',
      websocket_status: 'operator_bound',
      market_websocket_status: 'operator_bound',
      user_feed_websocket_status: 'operator_bound',
      rtds_status: 'operator_bound',
    },
  })
}

export function getVenueCoverageContract(): PredictionMarketVenueCoverage {
  const venues = listPredictionMarketVenues()
  const capabilities = venues.map((venue) => getVenueCapabilitiesContract(venue))
  const healthSnapshots = venues.map((venue) => getVenueHealthSnapshotContract(venue))
  const venueCount = venues.length
  const degradedVenueCount = healthSnapshots.filter((health) =>
    health.api_status !== 'healthy' ||
    health.stream_status !== 'healthy' ||
    health.degraded_mode !== 'normal' ||
    health.staleness_ms > 0,
  ).length
  const executionCapableCount = capabilities.filter((capability) => capability.supports_execution).length
  const paperCapableCount = capabilities.filter((capability) => capability.supports_paper_mode).length
  const readOnlyCount = capabilities.filter((capability) => capability.manual_review_required || !capability.supports_execution).length
  const executionEquivalentCount = capabilities.filter((capability) => capability.venue_type === 'execution-equivalent').length
  const executionLikeCount = capabilities.filter((capability) => capability.venue_type === 'execution-like').length
  const referenceOnlyCount = capabilities.filter((capability) => capability.venue_type === 'reference-only').length
  const watchlistOnlyCount = capabilities.filter((capability) => capability.venue_type === 'experimental').length
  const metadataGapCount = capabilities.filter((capability) => (capability.supports_metadata ?? true) === false).length
  return predictionMarketVenueCoverageSchema.parse({
    venue_count: venueCount,
    execution_capable_count: executionCapableCount,
    paper_capable_count: paperCapableCount,
    read_only_count: readOnlyCount,
    degraded_venue_count: degradedVenueCount,
    degraded_venue_rate: venueCount > 0 ? degradedVenueCount / venueCount : 0,
    execution_equivalent_count: executionEquivalentCount,
    execution_like_count: executionLikeCount,
    reference_only_count: referenceOnlyCount,
    watchlist_only_count: watchlistOnlyCount,
    metadata_gap_count: metadataGapCount,
    metadata_gap_rate: venueCount > 0 ? metadataGapCount / venueCount : 0,
    execution_surface_rate: venueCount > 0 ? executionCapableCount / venueCount : 0,
    availability_by_venue: Object.fromEntries(
      venues.map((venue, index) => [
        venue,
        {
          venue,
          health_status: healthSnapshots[index]?.api_status ?? 'unknown',
          degraded:
            healthSnapshots[index]?.api_status !== 'healthy' ||
            healthSnapshots[index]?.stream_status !== 'healthy' ||
            (healthSnapshots[index]?.incident_flags?.length ?? 0) > 0,
          supports_execution: capabilities[index]?.supports_execution ?? false,
          supports_paper_mode: capabilities[index]?.supports_paper_mode ?? false,
          planned_order_types: capabilities[index]?.planned_order_types ?? [],
          supported_order_types: capabilities[index]?.supported_order_types ?? [],
        },
      ]),
    ),
  })
}
