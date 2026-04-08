import { randomUUID } from 'node:crypto'

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  comparePredictionDashboardArbitrageSnapshots,
  comparePredictionDashboardVenueSnapshots,
  formatPredictionDashboardEventAsSse,
  getPredictionDashboardEventHistory,
  listRecentPredictionDashboardEvents,
  publishPredictionDashboardEvent,
  publishPredictionDashboardArbitrageSnapshot,
  publishPredictionDashboardLiveIntentEvent,
  resetPredictionDashboardEventStateForTests,
  subscribePredictionDashboardEvents,
  type PredictionDashboardEvent,
  type PredictionDashboardArbitrageSnapshot,
  type PredictionDashboardVenueSnapshot,
} from '@/lib/prediction-markets/dashboard-events'

describe('prediction markets dashboard events', () => {
  const previousDbPath = process.env.PREDICTION_DB_PATH

  beforeEach(() => {
    process.env.PREDICTION_DB_PATH = `prediction-dashboard-events-${randomUUID()}`
    resetPredictionDashboardEventStateForTests()
  })

  afterEach(() => {
    resetPredictionDashboardEventStateForTests()
    if (previousDbPath == null) {
      delete process.env.PREDICTION_DB_PATH
    } else {
      process.env.PREDICTION_DB_PATH = previousDbPath
    }
  })

  function makeSnapshot(overrides: Partial<PredictionDashboardVenueSnapshot> = {}): PredictionDashboardVenueSnapshot {
    return {
      workspace_id: 7,
      venue: 'polymarket',
      captured_at: '2026-04-08T00:00:00.000Z',
      runs_total: 3,
      latest_run_id: 'run-1',
      latest_run_updated_at: 10,
      latest_recommendation: 'bet',
      latest_selected_path: 'shadow',
      latest_selected_path_status: 'ready',
      latest_live_route_allowed: false,
      benchmark_state: {
        ready: false,
        gate_kind: 'preview_only',
        status: 'preview_only',
        evidence_level: 'benchmark_preview',
        promotion_status: 'blocked',
        blocker_summary: 'blocked',
        live_block_reason: 'benchmark_promotion_not_ready_for_live',
        blockers: ['out_of_sample_unproven'],
        summary: 'benchmark gate blocked',
      },
      venue_health_status: 'ready',
      venue_feed_status: 'ready',
      venue_user_feed_status: 'ready',
      venue_rtds_status: 'unavailable',
      venue_capabilities: 'execution-equivalent',
      venue_supports_execution: false,
      venue_supports_paper_mode: false,
      venue_notes: ['read only'],
      arbitrage_state: {
        run_id: 'run-1',
        compared_pairs: 0,
        candidate_count: 0,
        manual_review_count: 0,
        best_shadow_edge_bps: null,
        best_shadow_size_usd: null,
        summary: 'No tradeable cross-venue execution plans were derived; the surface remains comparison-only.',
      },
      ...overrides,
    }
  }

  function makeArbitrageSnapshot(overrides: Partial<PredictionDashboardArbitrageSnapshot> = {}): PredictionDashboardArbitrageSnapshot {
    return {
      generated_at: '2026-04-08T00:00:00.000Z',
      freshness: 'fresh',
      transport: 'polling',
      workspace_id: 7,
      venue_pair: ['polymarket', 'kalshi'],
      compared_pairs: 2,
      candidate_count: 1,
      manual_review_count: 0,
      best_shadow_edge_bps: 210,
      candidates: [
        {
          candidate_id: 'arb-1',
          canonical_event_key: 'event-1',
          buy_venue: 'polymarket',
          sell_venue: 'kalshi',
          gross_spread_bps: 220,
          net_spread_bps: 180,
          shadow_edge_bps: 150,
          recommended_size_usd: 250,
          confidence_score: 0.88,
          freshness_ms: 4_000,
          blocking_reasons: [],
          manual_review_required: false,
          opportunity_type: 'true_arbitrage',
        },
      ],
      ...overrides,
    }
  }

  it('stores, lists, subscribes, and formats events', () => {
    const seen: PredictionDashboardEvent[] = []
    const unsubscribe = subscribePredictionDashboardEvents((event) => seen.push(event))

    const event = publishPredictionDashboardEvent({
      type: 'benchmark_gate_changed',
      severity: 'warn',
      workspace_id: 7,
      venue: 'polymarket',
      run_id: 'run-1',
      intent_id: null,
      source: 'poller',
      summary: 'Benchmark gate changed for polymarket.',
      payload: {
        previous: { ready: false },
        next: { ready: true },
      },
    })

    unsubscribe()

    expect(seen).toEqual([event])
    expect(listRecentPredictionDashboardEvents(1)).toEqual([event])
    expect(getPredictionDashboardEventHistory({ workspaceId: 7, kinds: ['benchmark_gate_changed'] })).toEqual([event])
    expect(formatPredictionDashboardEventAsSse(event)).toContain('event: benchmark_gate_changed')
    expect(formatPredictionDashboardEventAsSse(event)).toContain('"severity":"warn"')
  })

  it('supports live-intent events and filters history by venue', () => {
    const event = publishPredictionDashboardLiveIntentEvent({
      workspaceId: 7,
      venue: 'kalshi',
      liveIntentId: 'intent-1',
      runId: 'run-2',
      type: 'live_intent_created',
      summary: 'Live intent created for run-2',
      severity: 'error',
      payload: { gate: 'benchmark' },
    })

    expect(event.type).toBe('live_intent_created')
    expect(getPredictionDashboardEventHistory({ workspaceId: 7, venue: 'kalshi' })).toEqual([event])
    expect(getPredictionDashboardEventHistory({ workspaceId: 7, venue: 'polymarket' })).toEqual([])
  })

  it('computes benchmark and health changes from venue snapshots', () => {
    const previous = makeSnapshot()
    const next = makeSnapshot({
      runs_total: 4,
      latest_run_id: 'run-2',
      latest_run_updated_at: 20,
      latest_live_route_allowed: true,
      benchmark_state: {
        ready: true,
        gate_kind: 'promotion_ready',
        status: 'ready',
        evidence_level: 'promotion_evidence',
        promotion_status: 'ready',
        blocker_summary: null,
        live_block_reason: null,
        blockers: [],
        summary: 'benchmark gate ready',
      },
      venue_health_status: 'degraded',
      venue_feed_status: 'degraded',
      venue_user_feed_status: 'degraded',
      venue_rtds_status: 'unavailable',
    })

    const events = comparePredictionDashboardVenueSnapshots(previous, next)
    const kinds = events.map((event) => event.type)

    expect(kinds).toContain('latest_run_changed')
    expect(kinds).toContain('venue_degraded')
    expect(kinds).toContain('benchmark_gate_changed')
  })

  it('emits arbitrage candidate opened, updated, and closed events', () => {
    const previous = makeArbitrageSnapshot()
    const next = makeArbitrageSnapshot({
      generated_at: '2026-04-08T00:05:00.000Z',
      compared_pairs: 3,
      candidate_count: 2,
      manual_review_count: 1,
      best_shadow_edge_bps: 240,
      candidates: [
        {
          candidate_id: 'arb-1',
          canonical_event_key: 'event-1',
          buy_venue: 'polymarket',
          sell_venue: 'kalshi',
          gross_spread_bps: 250,
          net_spread_bps: 190,
          shadow_edge_bps: 165,
          recommended_size_usd: 300,
          confidence_score: 0.91,
          freshness_ms: 2_500,
          blocking_reasons: ['manual_review_required'],
          manual_review_required: true,
          opportunity_type: 'true_arbitrage',
        },
        {
          candidate_id: 'arb-2',
          canonical_event_key: 'event-2',
          buy_venue: 'polymarket',
          sell_venue: 'kalshi',
          gross_spread_bps: 140,
          net_spread_bps: 110,
          shadow_edge_bps: 90,
          recommended_size_usd: 120,
          confidence_score: 0.74,
          freshness_ms: 1_500,
          blocking_reasons: ['liquidity_low'],
          manual_review_required: true,
          opportunity_type: 'relative_value',
        },
      ],
    })

    const events = comparePredictionDashboardArbitrageSnapshots(previous, next)
    expect(events.map((event) => event.type)).toEqual([
      'arbitrage_candidate_updated',
      'arbitrage_candidate_opened',
    ])

    const closedEvents = comparePredictionDashboardArbitrageSnapshots(next, previous)
    expect(closedEvents.map((event) => event.type)).toContain('arbitrage_candidate_closed')

    const published = publishPredictionDashboardArbitrageSnapshot(next, previous)
    expect(published).toHaveLength(2)
    expect(listRecentPredictionDashboardEvents(2).map((event) => event.type)).toEqual([
      'arbitrage_candidate_updated',
      'arbitrage_candidate_opened',
    ])
  })
})
