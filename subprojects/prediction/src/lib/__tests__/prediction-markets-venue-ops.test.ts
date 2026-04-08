import { describe, expect, it } from 'vitest'
import {
  getVenueBudgets,
  getVenueBudgetsContract,
  getVenueCapabilities,
  getVenueCapabilitiesContract,
  getVenueCoverageContract,
  getVenueFeedSurfaceContract,
  getVenueHealthSnapshot,
  getVenueHealthSnapshotContract,
  getVenueSourceHierarchy,
  getVenueStrategyContract,
  listPredictionMarketVenues,
} from '@/lib/prediction-markets/venue-ops'
import {
  predictionMarketVenueTypeSchema,
  venueCapabilitiesSchema,
} from '@/lib/prediction-markets/schemas'

describe('prediction market venue ops', () => {
  it('exposes both supported venues in a stable order', () => {
    expect(listPredictionMarketVenues()).toEqual(['polymarket', 'kalshi'])
  })

  it('exposes conservative capabilities, health, and budgets for Polymarket', () => {
    const capabilities = getVenueCapabilities('polymarket')
    const health = getVenueHealthSnapshot('polymarket')
    const budgets = getVenueBudgets('polymarket')
    const strategy = getVenueStrategyContract('polymarket')

    expect(capabilities).toMatchObject({
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      market_shape: 'binary_or_multi_outcome',
      supports: {
        list_markets: true,
        get_market: true,
        build_snapshot: true,
        orderbook: true,
        history: true,
        search: true,
        replay: true,
      },
      limits: {
        binary_only: false,
        max_list_limit: 100,
        max_history_limit: 500,
      },
    })

    expect(health).toMatchObject({
      venue: 'polymarket',
      network_checked: false,
      read_only: true,
      status: 'ready',
      reasons: [],
    })
    expect(health.configured_endpoints).toHaveLength(2)

    expect(budgets).toMatchObject({
      venue: 'polymarket',
      default_list_limit: 20,
      max_list_limit: 100,
      default_history_limit: 120,
      max_history_limit: 500,
      timeout_ms: 8000,
      max_http_requests_per_snapshot: 3,
      max_search_pages: 1,
      max_parallel_requests: 2,
      conservative: true,
    })

    expect(getVenueCapabilitiesContract('polymarket')).toMatchObject({
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      supports_discovery: true,
      supports_metadata: true,
      supports_orderbook: true,
      supports_positions: true,
      supports_execution: false,
      supports_websocket: true,
      tradeable: true,
      manual_review_required: true,
      supported_order_types: ['limit'],
      planned_order_types: ['limit'],
    })
    expect(getVenueHealthSnapshotContract('polymarket')).toMatchObject({
      venue: 'polymarket',
      api_status: 'healthy',
      degraded_mode: 'normal',
    })
    expect(getVenueFeedSurfaceContract('polymarket')).toMatchObject({
      venue: 'polymarket',
      backend_mode: 'read_only',
      ingestion_mode: 'read_only',
      supports_market_feed: true,
      supports_user_feed: true,
      supports_websocket: true,
      supports_rtds: true,
      live_streaming: false,
      tradeable: true,
      manual_review_required: true,
      supported_order_types: ['limit'],
      planned_order_types: ['limit'],
      market_feed_transport: 'local_cache',
      websocket_status: 'operator_bound',
      market_websocket_status: 'operator_bound',
      user_feed_websocket_status: 'operator_bound',
      rtds_status: 'operator_bound',
    })
    expect(getVenueBudgetsContract('polymarket')).toMatchObject({
      fetch_latency_budget_ms: 8000,
      snapshot_freshness_budget_ms: 8000,
      decision_latency_budget_ms: 8000,
      max_retries: 0,
      backpressure_policy: 'degrade-to-wait',
    })

    expect(strategy).toMatchObject({
      venue: 'polymarket',
      source_of_truth: 'official_docs',
      role: 'execution-equivalent',
      execution_eligible: true,
      source_of_truth_priority: ['official_docs', 'community_repos'],
    })
    expect(strategy.source_hierarchy).toEqual([
      {
        source: 'official_docs',
        role: 'source_of_truth',
        priority: 1,
        execution_eligible: true,
        notes: expect.arrayContaining([
          'Primary implementation authority for contracts, APIs, and product behavior.',
          'Use this layer to define runtime behavior and operational policy.',
        ]),
      },
      {
        source: 'community_repos',
        role: 'community_reference',
        priority: 2,
        execution_eligible: false,
        notes: expect.arrayContaining([
          'Useful for patterns, examples, and edge-case discovery.',
          'Do not use as implementation authority when it conflicts with official docs.',
        ]),
      },
    ])
    expect(strategy.community_reference).toMatchObject({
      source: 'community_repos',
      role: 'community_reference',
      priority: 2,
      execution_eligible: false,
    })
    expect(strategy.notes).toEqual(expect.arrayContaining([
      'Official venue docs are the implementation source of truth.',
      'Community repos are a secondary reference layer, not implementation policy.',
      'Venue remains execution-equivalent at the strategy layer, even when runtime is preflight-only.',
    ]))
    expect(getVenueSourceHierarchy('polymarket')).toEqual(strategy.source_hierarchy)
    expect(getVenueCapabilitiesContract('polymarket').rate_limit_notes).toContain('source_of_truth:official_docs#priority:1')
    expect(getVenueCapabilitiesContract('polymarket').rate_limit_notes).toContain('community_reference:community_repos#priority:2')
    expect(getVenueCapabilitiesContract('polymarket').rate_limit_notes).toContain('execution_eligible:true')
  })

  it('exposes conservative capabilities, health, and budgets for Kalshi', () => {
    const capabilities = getVenueCapabilities('kalshi')
    const health = getVenueHealthSnapshot('kalshi')
    const budgets = getVenueBudgets('kalshi')
    const strategy = getVenueStrategyContract('kalshi')

    expect(capabilities).toMatchObject({
      venue: 'kalshi',
      venue_type: 'execution-equivalent',
      market_shape: 'binary_only',
      supports: {
        list_markets: true,
        get_market: true,
        build_snapshot: true,
        orderbook: true,
        history: true,
        search: true,
        replay: true,
      },
      limits: {
        binary_only: true,
        max_list_limit: 1000,
        max_history_limit: 500,
      },
    })

    expect(health).toMatchObject({
      venue: 'kalshi',
      network_checked: false,
      read_only: true,
      status: 'ready',
      reasons: [],
    })
    expect(health.configured_endpoints).toEqual([
      'https://api.elections.kalshi.com/trade-api/v2',
    ])

    expect(budgets).toMatchObject({
      venue: 'kalshi',
      default_list_limit: 20,
      max_list_limit: 1000,
      default_history_limit: 120,
      max_history_limit: 500,
      timeout_ms: 8000,
      max_http_requests_per_snapshot: 3,
      max_search_pages: 5,
      max_parallel_requests: 2,
      conservative: true,
    })

    expect(getVenueCapabilitiesContract('kalshi')).toMatchObject({
      venue: 'kalshi',
      venue_type: 'execution-equivalent',
      supports_discovery: true,
      supports_metadata: true,
      supports_orderbook: true,
      supports_positions: true,
      supports_execution: false,
      supports_websocket: true,
      tradeable: true,
      manual_review_required: true,
      supported_order_types: ['limit'],
      planned_order_types: ['limit'],
    })
    expect(getVenueHealthSnapshotContract('kalshi')).toMatchObject({
      venue: 'kalshi',
      api_status: 'healthy',
      degraded_mode: 'normal',
    })
    expect(getVenueFeedSurfaceContract('kalshi')).toMatchObject({
      venue: 'kalshi',
      backend_mode: 'read_only',
      ingestion_mode: 'read_only',
      supports_market_feed: true,
      supports_user_feed: true,
      supports_websocket: true,
      supports_rtds: true,
      live_streaming: false,
      tradeable: true,
      manual_review_required: true,
      supported_order_types: ['limit'],
      planned_order_types: ['limit'],
      market_feed_transport: 'local_cache',
      websocket_status: 'operator_bound',
      market_websocket_status: 'operator_bound',
      user_feed_websocket_status: 'operator_bound',
      rtds_status: 'operator_bound',
    })
    expect(getVenueBudgetsContract('kalshi')).toMatchObject({
      fetch_latency_budget_ms: 8000,
      snapshot_freshness_budget_ms: 8000,
      decision_latency_budget_ms: 8000,
      max_retries: 0,
      backpressure_policy: 'degrade-to-wait',
    })

    expect(strategy).toMatchObject({
      venue: 'kalshi',
      source_of_truth: 'official_docs',
      role: 'execution-equivalent',
      execution_eligible: true,
      source_of_truth_priority: ['official_docs', 'community_repos'],
    })
    expect(strategy.source_hierarchy).toEqual([
      {
        source: 'official_docs',
        role: 'source_of_truth',
        priority: 1,
        execution_eligible: true,
        notes: expect.arrayContaining([
          'Primary implementation authority for contracts, APIs, and product behavior.',
          'Use this layer to define runtime behavior and operational policy.',
        ]),
      },
      {
        source: 'community_repos',
        role: 'community_reference',
        priority: 2,
        execution_eligible: false,
        notes: expect.arrayContaining([
          'Useful for patterns, examples, and edge-case discovery.',
          'Do not use as implementation authority when it conflicts with official docs.',
        ]),
      },
    ])
    expect(strategy.community_reference).toMatchObject({
      source: 'community_repos',
      role: 'community_reference',
      priority: 2,
      execution_eligible: false,
    })
    expect(strategy.notes).toEqual(expect.arrayContaining([
      'Official venue docs are the implementation source of truth.',
      'Community repos are a secondary reference layer, not implementation policy.',
      'Venue remains execution-equivalent at the strategy layer, even when runtime is preflight-only.',
    ]))
    expect(getVenueSourceHierarchy('kalshi')).toEqual(strategy.source_hierarchy)
    expect(getVenueCapabilitiesContract('kalshi').rate_limit_notes).toContain('source_of_truth:official_docs#priority:1')
    expect(getVenueCapabilitiesContract('kalshi').rate_limit_notes).toContain('community_reference:community_repos#priority:2')
    expect(getVenueCapabilitiesContract('kalshi').rate_limit_notes).toContain('execution_eligible:true')
  })

  it('summarizes venue coverage with degraded rates and order type surfaces', () => {
    expect(getVenueCoverageContract()).toMatchObject({
      schema_version: expect.any(String),
      venue_count: 2,
      execution_capable_count: 0,
      paper_capable_count: 1,
      read_only_count: 2,
      degraded_venue_count: 2,
      degraded_venue_rate: 1,
      execution_equivalent_count: 2,
      execution_like_count: 0,
      reference_only_count: 0,
      watchlist_only_count: 0,
      metadata_gap_count: 0,
      metadata_gap_rate: 0,
      execution_surface_rate: 0,
    })
    expect(getVenueCoverageContract().availability_by_venue).toMatchObject({
      polymarket: {
        venue: 'polymarket',
        health_status: 'healthy',
        degraded: true,
        supports_execution: false,
        supports_paper_mode: false,
        planned_order_types: ['limit'],
        supported_order_types: ['limit'],
      },
      kalshi: {
        venue: 'kalshi',
        health_status: 'healthy',
        degraded: true,
        supports_execution: false,
        supports_paper_mode: true,
        planned_order_types: ['limit'],
        supported_order_types: ['limit'],
      },
    })
  })

  it('accepts execution-like venue types and makes tradeability explicit in the report surface', () => {
    expect(predictionMarketVenueTypeSchema.parse('execution-like')).toBe('execution-like')

    expect(venueCapabilitiesSchema.parse({
      venue: 'polymarket',
      venue_type: 'execution-like',
      supports_discovery: true,
      supports_orderbook: true,
      supports_trades: true,
      supports_positions: true,
      supports_execution: false,
      supports_websocket: false,
      tradeable: false,
      manual_review_required: true,
      automation_constraints: ['manual review before action'],
    })).toMatchObject({
      venue_type: 'execution-like',
      tradeable: false,
      manual_review_required: true,
    })
  })

  it('keeps the feed surface explicitly read-only and swarm-scoped', () => {
    const surface = getVenueFeedSurfaceContract('polymarket')

    expect(surface.summary).toContain('swarm')
    expect(surface.summary).toContain('manual-review-only')
    expect(surface.automation_constraints).toEqual([
      'read-only advisory mode only',
      'websocket and RTDS surfaces are operator-bound only',
    ])
    expect(surface.supports_websocket).toBe(true)
    expect(surface.supports_rtds).toBe(true)
    expect(surface.websocket_status).toBe('operator_bound')
    expect(surface.market_websocket_status).toBe('operator_bound')
    expect(surface.user_feed_websocket_status).toBe('operator_bound')
    expect(surface.rtds_status).toBe('operator_bound')
    expect(surface.metadata.backend_mode).toBe('read_only')
    expect(surface.metadata.supports_execution).toBe(false)
  })
})
