import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  listPolymarketMarkets: vi.fn(),
  listKalshiMarkets: vi.fn(),
  buildPolymarketSnapshot: vi.fn(),
  buildKalshiSnapshot: vi.fn(),
  findCrossVenueMatches: vi.fn(),
  summarizeCrossVenueIntelligence: vi.fn(),
  evaluateCrossVenuePair: vi.fn(),
  buildMicrostructureLabReport: vi.fn(),
  buildShadowArbitrageSimulation: vi.fn(),
  publishPredictionDashboardEvent: vi.fn(),
}))

vi.mock('@/lib/prediction-markets/polymarket', () => ({
  listPolymarketMarkets: mocks.listPolymarketMarkets,
  buildPolymarketSnapshot: mocks.buildPolymarketSnapshot,
}))

vi.mock('@/lib/prediction-markets/kalshi', () => ({
  listKalshiMarkets: mocks.listKalshiMarkets,
  buildKalshiSnapshot: mocks.buildKalshiSnapshot,
}))

vi.mock('@/lib/prediction-markets/cross-venue', () => ({
  findCrossVenueMatches: mocks.findCrossVenueMatches,
  summarizeCrossVenueIntelligence: mocks.summarizeCrossVenueIntelligence,
  evaluateCrossVenuePair: mocks.evaluateCrossVenuePair,
}))

vi.mock('@/lib/prediction-markets/microstructure-lab', () => ({
  buildMicrostructureLabReport: mocks.buildMicrostructureLabReport,
}))

vi.mock('@/lib/prediction-markets/shadow-arbitrage', () => ({
  buildShadowArbitrageSimulation: mocks.buildShadowArbitrageSimulation,
}))

vi.mock('@/lib/prediction-markets/dashboard-events', () => ({
  publishPredictionDashboardEvent: mocks.publishPredictionDashboardEvent,
}))

function makeMarket(venue: 'polymarket' | 'kalshi', marketId: string, question: string) {
  return {
    schema_version: '1.0.0',
    venue,
    market_id: marketId,
    question,
    title: question,
    active: true,
    closed: false,
    is_binary_yes_no: true,
    best_bid: 0.41,
    best_ask: 0.43,
    last_trade_price: 0.42,
    liquidity_usd: 25_000,
    source_urls: [],
  }
}

function makeEvaluation(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    canonical_event_id: 'btc-2026',
    canonical_event_key: 'btc-2026',
    confidence_score: 0.91,
    opportunity_type: 'true_arbitrage',
    market_equivalence_proof: {
      proof_status: 'proven',
      manual_review_required: false,
    },
    executable_edge: {
      executable_edge_bps: 88,
      notes: ['edge is executable'],
    },
    match: {},
    mismatch_reasons: [],
    compatible: true,
    arbitrage_candidate: {
      candidate_type: 'yes_yes_spread',
      opportunity_type: 'true_arbitrage',
      canonical_event_id: 'btc-2026',
      canonical_event_key: 'btc-2026',
      buy_ref: { venue: 'polymarket', market_id: 'poly-btc' },
      sell_ref: { venue: 'kalshi', market_id: 'kal-btc' },
      buy_price_yes: 0.42,
      sell_price_yes: 0.53,
      gross_spread_bps: 1100,
      net_spread_bps: 92,
      confidence_score: 0.91,
      executable: true,
      executable_edge: {
        executable_edge_bps: 88,
        notes: ['executable'],
      },
      market_equivalence_proof: {
        proof_status: 'proven',
        manual_review_required: false,
      },
      arb_plan: {
        arb_plan_id: 'arb:btc-2026',
        canonical_event_id: 'btc-2026',
        opportunity_type: 'true_arbitrage',
        executable_edge: {
          executable_edge_bps: 88,
        },
        legs: [],
        required_capital_usd: 250,
        break_even_after_fees_bps: 24,
        max_unhedged_leg_ms: 2_000,
        exit_policy: 'shadow-only',
        manual_review_required: false,
        notes: [],
      },
      reasons: ['spread_positive'],
    },
    ...overrides,
  }
}

describe('prediction markets arbitrage scanner', () => {
  const previousDbPath = process.env.PREDICTION_DB_PATH
  let scanStep = 0

  beforeEach(() => {
    process.env.PREDICTION_DB_PATH = `prediction-arbitrage-scanner-${scanStep}`
    scanStep = 0
    mocks.listPolymarketMarkets.mockReset()
    mocks.listKalshiMarkets.mockReset()
    mocks.buildPolymarketSnapshot.mockReset()
    mocks.buildKalshiSnapshot.mockReset()
    mocks.findCrossVenueMatches.mockReset()
    mocks.summarizeCrossVenueIntelligence.mockReset()
    mocks.evaluateCrossVenuePair.mockReset()
    mocks.buildMicrostructureLabReport.mockReset()
    mocks.buildShadowArbitrageSimulation.mockReset()
    mocks.publishPredictionDashboardEvent.mockReset()

    mocks.listPolymarketMarkets.mockResolvedValue([
      makeMarket('polymarket', 'poly-btc', 'Will Bitcoin exceed 100000 by 2026-12-31?'),
    ])
    mocks.listKalshiMarkets.mockResolvedValue([
      makeMarket('kalshi', 'kal-btc', 'Will Bitcoin be above 100000 on 2026-12-31?'),
    ])
    mocks.buildPolymarketSnapshot.mockResolvedValue({ captured_at: '2026-04-08T00:00:00.000Z' })
    mocks.buildKalshiSnapshot.mockResolvedValue({ captured_at: '2026-04-08T00:00:00.000Z' })
    mocks.buildMicrostructureLabReport.mockReturnValue({
      summary: {
        worst_case_kind: 'partial_fill',
        worst_case_severity: 'medium',
        recommended_mode: 'paper',
        execution_quality_score: 0.81,
        scenario_overview: ['one_leg_fill: hedge_delay=500ms book_age=100ms'],
        notes: ['microstructure ok'],
      },
    })
    mocks.buildShadowArbitrageSimulation.mockReturnValue({
      summary: {
        shadow_edge_bps: 72,
        recommended_size_usd: 250,
        hedge_success_probability: 0.93,
        hedge_success_expected: true,
        estimated_net_pnl_bps: 60,
        estimated_net_pnl_usd: 15,
        notes: ['shadow ok'],
      },
    })
    mocks.findCrossVenueMatches.mockImplementation(() => {
      scanStep += 1
      if (scanStep <= 2) {
        return [makeEvaluation()]
      }
      return []
    })
    mocks.summarizeCrossVenueIntelligence.mockImplementation((evaluations: Array<ReturnType<typeof makeEvaluation>>) => ({
      total_pairs: scanStep <= 2 ? 1 : 0,
      opportunity_type_counts: {
        comparison_only: 0,
        relative_value: 0,
        cross_venue_signal: 0,
        true_arbitrage: scanStep <= 2 ? 1 : 0,
      },
      compatible: scanStep <= 2 ? evaluations : [],
      manual_review: [],
      comparison_only: [],
      blocking_reasons: [],
      highest_confidence_candidate: scanStep <= 2 ? evaluations[0]?.arbitrage_candidate ?? null : null,
    }))
    mocks.evaluateCrossVenuePair.mockImplementation(() => makeEvaluation())
  })

  afterEach(() => {
    if (previousDbPath == null) {
      delete process.env.PREDICTION_DB_PATH
    } else {
      process.env.PREDICTION_DB_PATH = previousDbPath
    }
  })

  it('builds a shadow-only snapshot and emits candidate lifecycle events', async () => {
    const { getPredictionDashboardArbitrageSnapshot, resetPredictionDashboardArbitrageStateForTests } = await import('@/lib/prediction-markets/arbitrage-scanner')

    try {
      const first = await getPredictionDashboardArbitrageSnapshot({
        workspaceId: 7,
        limitPerVenue: 2,
        maxPairs: 10,
        minArbitrageSpreadBps: 25,
        shadowCandidateLimit: 4,
        forceRefresh: true,
      })

      expect(first.overview.candidate_count).toBe(1)
      expect(first.candidates[0]?.shadow_ready).toBe(true)
      expect(mocks.publishPredictionDashboardEvent).toHaveBeenCalledWith(expect.objectContaining({
        type: 'arbitrage_candidate_opened',
      }))

      mocks.buildShadowArbitrageSimulation.mockReturnValueOnce({
        summary: {
          shadow_edge_bps: 12,
          recommended_size_usd: 120,
          hedge_success_probability: 0.72,
          hedge_success_expected: true,
          estimated_net_pnl_bps: 8,
          estimated_net_pnl_usd: 3,
          notes: ['shadow updated'],
        },
      })
      mocks.evaluateCrossVenuePair.mockImplementationOnce(() => makeEvaluation({
        arbitrage_candidate: {
          candidate_type: 'yes_yes_spread',
          opportunity_type: 'true_arbitrage',
          canonical_event_id: 'btc-2026',
          canonical_event_key: 'btc-2026',
          buy_ref: { venue: 'polymarket', market_id: 'poly-btc' },
          sell_ref: { venue: 'kalshi', market_id: 'kal-btc' },
          buy_price_yes: 0.42,
          sell_price_yes: 0.53,
          gross_spread_bps: 1100,
          net_spread_bps: 92,
          confidence_score: 0.91,
          executable: true,
          executable_edge: { executable_edge_bps: 88, notes: ['executable'] },
          market_equivalence_proof: {
            proof_status: 'proven',
            manual_review_required: false,
          },
          arb_plan: {
            arb_plan_id: 'arb:btc-2026',
            canonical_event_id: 'btc-2026',
            opportunity_type: 'true_arbitrage',
            executable_edge: { executable_edge_bps: 88 },
            legs: [],
            required_capital_usd: 250,
            break_even_after_fees_bps: 24,
            max_unhedged_leg_ms: 2_000,
            exit_policy: 'shadow-only',
            manual_review_required: false,
            notes: [],
          },
          reasons: ['spread_positive'],
        },
      }))

      const second = await getPredictionDashboardArbitrageSnapshot({
        workspaceId: 7,
        limitPerVenue: 2,
        maxPairs: 10,
        minArbitrageSpreadBps: 25,
        shadowCandidateLimit: 4,
        forceRefresh: true,
      })

      expect(second.overview.candidate_count).toBe(1)
      expect(second.candidates[0]?.shadow_edge_bps).toBe(12)
      expect(mocks.publishPredictionDashboardEvent).toHaveBeenCalledWith(expect.objectContaining({
        type: 'arbitrage_candidate_updated',
      }))

      const third = await getPredictionDashboardArbitrageSnapshot({
        workspaceId: 7,
        limitPerVenue: 2,
        maxPairs: 10,
        minArbitrageSpreadBps: 25,
        shadowCandidateLimit: 4,
        forceRefresh: true,
      })

      expect(third.overview.candidate_count).toBe(0)
      expect(mocks.publishPredictionDashboardEvent).toHaveBeenCalledWith(expect.objectContaining({
        type: 'arbitrage_candidate_closed',
      }))
    } finally {
      resetPredictionDashboardArbitrageStateForTests()
    }
  })

  it('ranks candidates by quality and actionability signals', async () => {
    const { getPredictionDashboardArbitrageSnapshot, resetPredictionDashboardArbitrageStateForTests } = await import('@/lib/prediction-markets/arbitrage-scanner')

    const weakEvaluation = makeEvaluation({
      canonical_event_id: 'eth-2026',
      canonical_event_key: 'eth-2026',
      confidence_score: 0.54,
      arbitrage_candidate: {
        candidate_type: 'yes_yes_spread',
        opportunity_type: 'true_arbitrage',
        canonical_event_id: 'eth-2026',
        canonical_event_key: 'eth-2026',
        buy_ref: { venue: 'polymarket', market_id: 'poly-eth' },
        sell_ref: { venue: 'kalshi', market_id: 'kal-eth' },
        buy_price_yes: 0.44,
        sell_price_yes: 0.47,
        gross_spread_bps: 300,
        net_spread_bps: 18,
        confidence_score: 0.54,
        executable: false,
        executable_edge: {
          executable_edge_bps: 12,
          notes: ['thin edge'],
        },
        market_equivalence_proof: {
          proof_status: 'proven',
          manual_review_required: true,
        },
        arb_plan: {
          arb_plan_id: 'arb:eth-2026',
          canonical_event_id: 'eth-2026',
          opportunity_type: 'true_arbitrage',
          executable_edge: {
            executable_edge_bps: 12,
          },
          legs: [],
          required_capital_usd: 100,
          break_even_after_fees_bps: 14,
          max_unhedged_leg_ms: 4_000,
          exit_policy: 'shadow-only',
          manual_review_required: true,
          notes: [],
        },
        reasons: ['thin_edge', 'manual_review_required'],
      },
    })

    mocks.findCrossVenueMatches.mockImplementation(() => [makeEvaluation(), weakEvaluation])
    mocks.summarizeCrossVenueIntelligence.mockImplementation((evaluations: Array<ReturnType<typeof makeEvaluation>>) => ({
      total_pairs: 2,
      opportunity_type_counts: {
        comparison_only: 0,
        relative_value: 0,
        cross_venue_signal: 0,
        true_arbitrage: 2,
      },
      compatible: evaluations,
      manual_review: [evaluations[1]],
      comparison_only: [],
      blocking_reasons: [],
      highest_confidence_candidate: evaluations[0]?.arbitrage_candidate ?? null,
    }))
    let shadowCall = 0
    mocks.buildShadowArbitrageSimulation.mockImplementation(() => {
      shadowCall += 1
      return shadowCall % 2 === 1
        ? {
            summary: {
              shadow_edge_bps: 80,
              recommended_size_usd: 240,
              hedge_success_probability: 0.95,
              hedge_success_expected: true,
              estimated_net_pnl_bps: 58,
              estimated_net_pnl_usd: 14,
              notes: ['good shadow'],
            },
          }
        : {
            summary: {
              shadow_edge_bps: 8,
              recommended_size_usd: 60,
              hedge_success_probability: 0.68,
              hedge_success_expected: false,
              estimated_net_pnl_bps: 3,
              estimated_net_pnl_usd: 1,
              notes: ['weak shadow'],
            },
          }
    })

    try {
      const full = await getPredictionDashboardArbitrageSnapshot({
        workspaceId: 7,
        limitPerVenue: 2,
        maxPairs: 10,
        minArbitrageSpreadBps: 25,
        shadowCandidateLimit: 4,
        forceRefresh: true,
      })

      expect(full.candidates[0]?.candidate_id).toBe('arb:btc-2026')
      expect(full.candidates[0]?.ranking_score).toBeGreaterThan(full.candidates[1]?.ranking_score ?? 0)
      expect(full.overview.best_quality_score).toBe(full.candidates[0]?.quality_score ?? null)
      expect(full.overview.best_actionability_score).toBe(full.candidates[0]?.actionability_score ?? null)
      expect(full.candidates[0]?.quality_signals).toEqual(expect.arrayContaining([
        'executable_edge_bps:88',
        'shadow_edge_bps:80',
      ]))
      expect(full.candidates[0]?.actionability_signals).toEqual(expect.arrayContaining([
        'shadow_ready',
        'manual_review_clear',
      ]))
      expect(full.overview.actionable_candidate_count).toBe(1)
      expect(full.candidates[0]?.actionability_score).toBeGreaterThan(full.candidates[1]?.actionability_score ?? 0)
    } finally {
      resetPredictionDashboardArbitrageStateForTests()
    }
  })
})
