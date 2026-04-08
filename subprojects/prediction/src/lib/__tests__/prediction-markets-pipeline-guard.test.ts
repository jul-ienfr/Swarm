import { describe, expect, it } from 'vitest'
import {
  applyPredictionMarketPipelineGuardrails,
  buildForecastPacket,
  buildPredictionMarketPipelineGuard,
  buildRecommendationPacket,
  buildResolutionPolicy,
  finalizePredictionMarketPipelineGuard,
} from '@/lib/prediction-markets/service'
import {
  evidencePacketSchema,
  marketDescriptorSchema,
  marketSnapshotSchema,
  type MarketSnapshot,
} from '@/lib/prediction-markets/schemas'

function makeMarketSnapshot(overrides: Partial<MarketSnapshot> = {}): MarketSnapshot {
  const market = marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: 'pipeline-guard-market',
    question: 'Will pipeline guards stay conservative?',
    outcomes: ['Yes', 'No'],
    active: true,
    closed: false,
    accepting_orders: true,
    restricted: false,
    liquidity_usd: 25000,
    volume_usd: 80000,
    volume_24h_usd: 3500,
    best_bid: 0.48,
    best_ask: 0.5,
    last_trade_price: 0.49,
    tick_size: 0.01,
    min_order_size: 5,
    is_binary_yes_no: true,
    source_urls: ['https://example.com/pipeline-guard-market'],
  })

  return marketSnapshotSchema.parse({
    venue: 'polymarket',
    market,
    captured_at: new Date(Date.now() - 1000).toISOString(),
    yes_outcome_index: 0,
    yes_token_id: 'token-yes',
    yes_price: 0.49,
    no_price: 0.51,
    midpoint_yes: 0.49,
    best_bid_yes: 0.48,
    best_ask_yes: 0.5,
    spread_bps: 200,
    book: {
      token_id: 'token-yes',
      market_condition_id: 'cond-pipeline',
      fetched_at: new Date(Date.now() - 1000).toISOString(),
      best_bid: 0.48,
      best_ask: 0.5,
      last_trade_price: 0.49,
      tick_size: 0.01,
      min_order_size: 5,
      bids: [{ price: 0.48, size: 250 }],
      asks: [{ price: 0.5, size: 250 }],
      depth_near_touch: 500,
    },
    history: [
      { timestamp: 1712534400, price: 0.46 },
      { timestamp: 1712538000, price: 0.49 },
    ],
    source_urls: [
      'https://example.com/pipeline-guard-market',
      'https://example.com/pipeline-guard-market/book',
    ],
    ...overrides,
  })
}

function makeEvidencePacket(snapshot: MarketSnapshot) {
  return evidencePacketSchema.parse({
    evidence_id: `${snapshot.market.market_id}:market-data`,
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    type: 'market_data',
    title: 'Live market snapshot',
    summary: 'Pipeline guard test evidence',
    source_url: snapshot.source_urls[0],
    captured_at: snapshot.captured_at,
    content_hash: 'sha256:pipeline-guard',
    metadata: {},
  })
}

describe('prediction markets pipeline guard', () => {
  it('flags stale snapshots and fetch budget breaches for advise mode', () => {
    const staleSnapshot = makeMarketSnapshot({
      captured_at: new Date(Date.now() - 20_000).toISOString(),
      book: {
        token_id: 'token-yes',
        market_condition_id: 'cond-pipeline',
        fetched_at: new Date(Date.now() - 20_000).toISOString(),
        best_bid: 0.48,
        best_ask: 0.5,
        last_trade_price: 0.49,
        tick_size: 0.01,
        min_order_size: 5,
        bids: [{ price: 0.48, size: 250 }],
        asks: [{ price: 0.5, size: 250 }],
        depth_near_touch: 500,
      },
    })

    const guard = buildPredictionMarketPipelineGuard({
      venue: 'polymarket',
      mode: 'advise',
      snapshot: staleSnapshot,
      fetchLatencyMs: 9001,
    })

    expect(guard.status).toBe('degraded')
    expect(guard.breached_budgets).toContain('fetch_latency_budget_ms')
    expect(guard.breached_budgets).toContain('snapshot_freshness_budget_ms')
    expect(guard.metrics.fetch_latency_ms).toBe(9001)
    expect(guard.metrics.snapshot_staleness_ms).toBeGreaterThan(8000)
  })

  it('marks decision latency breaches in the finalized guard', () => {
    const guard = buildPredictionMarketPipelineGuard({
      venue: 'polymarket',
      mode: 'replay',
      fetchLatencyMs: 0,
    })

    const finalized = finalizePredictionMarketPipelineGuard({
      guard,
      decisionLatencyMs: 9001,
    })

    expect(finalized.status).toBe('degraded')
    expect(finalized.breached_budgets).toContain('decision_latency_budget_ms')
    expect(finalized.metrics.decision_latency_ms).toBe(9001)
  })

  it('forces a bet recommendation back to wait when the pipeline is blocked', () => {
    const snapshot = makeMarketSnapshot()
    const resolutionPolicy = buildResolutionPolicy(snapshot)
    const forecast = buildForecastPacket({
      snapshot,
      evidencePackets: [makeEvidencePacket(snapshot)],
      thesisProbability: 0.74,
      thesisRationale: 'Manual thesis still likes YES here.',
    })
    const recommendation = buildRecommendationPacket({
      snapshot,
      resolutionPolicy,
      forecast,
    })

    expect(recommendation.action).toBe('bet')
    expect(recommendation.side).toBe('yes')

    const blockedGuard = {
      ...buildPredictionMarketPipelineGuard({
        venue: 'polymarket',
        mode: 'advise',
        snapshot,
        fetchLatencyMs: 100,
      }),
      status: 'blocked' as const,
      reasons: ['Venue health is blocked for this advisory pass.'],
    }

    const guarded = applyPredictionMarketPipelineGuardrails({
      snapshot,
      resolutionPolicy,
      forecast,
      recommendation,
      guard: blockedGuard,
    })

    expect(guarded.action).toBe('wait')
    expect(guarded.side).toBeNull()
    expect(guarded.risk_flags).toContain('venue_blocked')
    expect(guarded.why_not_now).toContain('Venue health is blocked for this advisory pass.')
  })
})
