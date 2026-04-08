import { describe, expect, it } from 'vitest'
import {
  marketDescriptorSchema,
  marketSnapshotSchema,
  type MarketDescriptor,
  type MarketSnapshot,
} from '@/lib/prediction-markets/schemas'
import { evaluateCrossVenuePair } from '@/lib/prediction-markets/cross-venue'
import { getPredictionMarketVenueStrategy } from '@/lib/prediction-markets/venue-strategy'
import { enrichPredictionMarketPreflightSummary } from '@/lib/prediction-markets/preflight-ops'

function makeDescriptor(overrides: Partial<MarketDescriptor> = {}): MarketDescriptor {
  return marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: 'market-1',
    slug: 'market-1',
    question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
    outcomes: ['Yes', 'No'],
    active: true,
    closed: false,
    accepting_orders: true,
    restricted: false,
    liquidity_usd: 100_000,
    volume_usd: 2_000_000,
    volume_24h_usd: 120_000,
    best_bid: 0.43,
    best_ask: 0.44,
    last_trade_price: 0.435,
    tick_size: 0.01,
    min_order_size: 5,
    is_binary_yes_no: true,
    start_at: '2026-12-01T00:00:00.000Z',
    end_at: '2026-12-31T23:59:59.000Z',
    source_urls: ['https://example.com/markets/market-1'],
    ...overrides,
  })
}

function makeSnapshot(
  market: MarketDescriptor,
  overrides: Partial<MarketSnapshot> = {},
): MarketSnapshot {
  return marketSnapshotSchema.parse({
    venue: market.venue,
    market,
    captured_at: '2026-04-08T00:00:00.000Z',
    yes_outcome_index: 0,
    yes_token_id: `${market.market_id}:yes`,
    yes_price: market.last_trade_price ?? null,
    no_price: market.last_trade_price != null ? Number((1 - market.last_trade_price).toFixed(6)) : null,
    midpoint_yes: market.last_trade_price ?? null,
    best_bid_yes: market.best_bid ?? null,
    best_ask_yes: market.best_ask ?? null,
    spread_bps: market.best_bid != null && market.best_ask != null
      ? Number(((market.best_ask - market.best_bid) * 10_000).toFixed(2))
      : null,
    book: null,
    history: [],
    source_urls: market.source_urls,
    ...overrides,
  })
}

function makePreflightSummary() {
  return {
    gate_name: 'execution_projection' as const,
    preflight_only: true as const,
    requested_path: 'live' as const,
    selected_path: 'paper' as const,
    verdict: 'downgraded' as const,
    highest_safe_requested_mode: 'paper' as const,
    recommended_effective_mode: 'paper' as const,
    manual_review_required: true,
    ttl_ms: 30_000,
    expires_at: '2026-04-08T00:30:00.000Z',
    counts: {
      total: 3,
      eligible: 1,
      ready: 0,
      degraded: 1,
      blocked: 2,
    },
    basis: {
      uses_execution_readiness: true,
      uses_compliance: true,
      uses_capital: false,
      uses_reconciliation: false,
      uses_microstructure: true,
      capital_status: 'unavailable' as const,
      reconciliation_status: 'unavailable' as const,
    },
    source_refs: ['run-1:pipeline_guard', 'run-1:execution_readiness'],
    blockers: [],
    downgrade_reasons: ['manual_review_required_for_execution'],
    microstructure: null,
    summary:
      'gate=execution_projection preflight=yes verdict=downgraded requested=live selected=paper highest_safe=paper recommended=paper manual_review=yes ttl_ms=30000 eligible=1/3 paths=ready:0|degraded:1|blocked:2 basis=readiness,compliance,microstructure refs=2 blockers=0 downgrades=1',
  }
}

describe('prediction market preflight ops', () => {
  it('enriches a preflight summary with strategy and edge penalty metadata', () => {
    const asOfAt = '2026-04-08T00:05:00.000Z'
    const polymarket = makeDescriptor({
      venue: 'polymarket',
      market_id: 'poly-btc-100k',
      slug: 'poly-btc-100k',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      best_bid: 0.43,
      best_ask: 0.44,
      last_trade_price: 0.435,
      source_urls: ['https://example.com/polymarket/btc-100k'],
    })
    const kalshi = makeDescriptor({
      venue: 'kalshi',
      market_id: 'kalshi-btc-100k',
      slug: 'kalshi-btc-100k',
      question: 'Will Bitcoin be above 100000 on 2026-12-31?',
      best_bid: 0.58,
      best_ask: 0.59,
      last_trade_price: 0.585,
      source_urls: ['https://example.com/kalshi/btc-100k'],
    })

    const evaluation = evaluateCrossVenuePair({
      left: polymarket,
      right: kalshi,
      leftSnapshot: makeSnapshot(polymarket),
      rightSnapshot: makeSnapshot(kalshi),
      asOfAt,
    })

    expect(evaluation.executable_edge).not.toBeNull()

    const baseSummary = makePreflightSummary()
    const enriched = enrichPredictionMarketPreflightSummary(baseSummary, {
      venue_strategy: getPredictionMarketVenueStrategy('polymarket'),
      executable_edge: evaluation.executable_edge,
    })

    expect(enriched).not.toBe(baseSummary)
    expect(baseSummary).not.toHaveProperty('source_of_truth')
    expect(enriched).toMatchObject({
      gate_name: 'execution_projection',
      source_of_truth: 'official_docs',
      execution_eligible: true,
      stale_edge_status: {
        state: 'fresh',
        expired: false,
        source: 'executable_edge',
        reasons: expect.arrayContaining(['stale_edge_expired:false']),
      },
      penalties: {
        capital_fragmentation_penalty_bps: 8,
        transfer_latency_penalty_bps: 2,
        low_confidence_penalty_bps: expect.any(Number),
        stale_edge_penalty_bps: expect.any(Number),
        microstructure_deterioration_bps: null,
        microstructure_execution_quality_score: null,
      },
    })
  })

  it('falls back to cross-venue executable edges and marks stale edges as expired with microstructure penalties', () => {
    const asOfAt = '2026-04-08T00:20:00.000Z'
    const polymarket = makeDescriptor({
      venue: 'polymarket',
      market_id: 'poly-btc-100k-stale',
      slug: 'poly-btc-100k-stale',
      question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
      best_bid: 0.43,
      best_ask: 0.44,
      last_trade_price: 0.435,
      source_urls: ['https://example.com/polymarket/btc-100k-stale'],
    })
    const kalshi = makeDescriptor({
      venue: 'kalshi',
      market_id: 'kalshi-btc-100k-stale',
      slug: 'kalshi-btc-100k-stale',
      question: 'Will Bitcoin be above 100000 on 2026-12-31?',
      best_bid: 0.58,
      best_ask: 0.59,
      last_trade_price: 0.585,
      source_urls: ['https://example.com/kalshi/btc-100k-stale'],
    })

    const evaluation = evaluateCrossVenuePair({
      left: polymarket,
      right: kalshi,
      leftSnapshot: makeSnapshot(polymarket, { captured_at: '2026-04-08T00:00:00.000Z' }),
      rightSnapshot: makeSnapshot(kalshi, { captured_at: '2026-04-08T00:00:00.000Z' }),
      asOfAt,
    })

    expect(evaluation.executable_edge).not.toBeNull()
    expect(evaluation.executable_edge?.notes).toContain('stale_edge_expired:true')

    const enriched = enrichPredictionMarketPreflightSummary(makePreflightSummary(), {
      venue_strategy: getPredictionMarketVenueStrategy('kalshi'),
      cross_venue: evaluation,
      microstructure_summary: {
        recommended_mode: 'wait',
        worst_case_severity: 'critical',
        executable_deterioration_bps: 47,
        execution_quality_score: 0.14,
      },
    })

    expect(enriched).toMatchObject({
      source_of_truth: 'official_docs',
      execution_eligible: true,
      stale_edge_status: {
        state: 'expired',
        expired: true,
        source: 'cross_venue',
        reasons: expect.arrayContaining(['stale_edge_expired:true']),
      },
      penalties: {
        capital_fragmentation_penalty_bps: 8,
        transfer_latency_penalty_bps: 2,
        low_confidence_penalty_bps: expect.any(Number),
        stale_edge_penalty_bps: expect.any(Number),
        microstructure_deterioration_bps: 47,
        microstructure_execution_quality_score: 0.14,
      },
    })
  })
})
