import { describe, expect, it } from 'vitest'

import {
  buildShadowStrategyDefenseSummary,
  buildShadowStrategyWatchlist,
  summarizeShadowStrategyWatchlist,
  type PredictionMarketShadowStrategyInput,
} from '@/lib/prediction-markets/strategy-shadow'
import { type PredictionMarketStrategyMarketRegime } from '@/lib/prediction-markets/strategy-regime'

function makeRegime(): PredictionMarketStrategyMarketRegime {
  return {
    read_only: true,
    regime_id: 'regime:shadow-defense:market-1',
    market_id: 'market-1',
    venue: 'polymarket',
    generated_at: '2026-04-09T00:00:00.000Z',
    disposition: 'defense',
    price_state: 'dislocated',
    freshness_state: 'stale',
    resolution_state: 'anomalous',
    research_state: 'abstain',
    latency_state: 'lagging',
    maker_quote_state: 'blocked',
    maker_quote_freshness_budget_ms: 0,
    stress_level: 'critical',
    signal_strength: 0.92,
    confidence_score: 0.88,
    hours_to_resolution: 8,
    price_spread_bps: 180,
    quote_age_ms: 420_000,
    liquidity_usd: 120_000,
    anomaly_count: 2,
    anomaly_kinds: ['policy_blocked', 'horizon_drift'],
    latency_reference_count: 2,
    key_signals: ['strategy:shadow'],
    reasons: ['resolution_state:anomalous'],
    summary: 'Defense regime for shadow strategy testing.',
  }
}

function makeInput(): PredictionMarketShadowStrategyInput {
  return {
    snapshot: {} as never,
    regime: makeRegime(),
    resolution_anomalies: [
      {
        read_only: true,
        anomaly_id: 'anomaly:attack',
        market_id: 'market-1',
        venue: 'polymarket',
        anomaly_kind: 'policy_blocked',
        severity: 'high',
        watch_kind: 'defense',
        score: 0.95,
        hours_to_resolution: 8,
        summary: 'Policy blocked anomaly.',
        reasons: ['policy_blocked', 'resolution_guard'],
        signal_refs: ['policy-ref'],
      },
      {
        read_only: true,
        anomaly_id: 'anomaly:sniping',
        market_id: 'market-1',
        venue: 'polymarket',
        anomaly_kind: 'horizon_drift',
        severity: 'medium',
        watch_kind: 'watch',
        score: 0.74,
        hours_to_resolution: 8,
        summary: 'Near-resolution sniping anomaly.',
        reasons: ['horizon_drift'],
        signal_refs: ['sniping-ref'],
      },
    ],
    latency_references: [
      {
        read_only: true,
        reference_id: 'ref-worse',
        market_id: 'market-1',
        venue: 'polymarket',
        source: 'base_snapshot',
        role: 'reference',
        price_yes: 0.48,
        spread_bps: 200,
        quote_age_ms: 180_000,
        freshness_gap_ms: 18_000,
        liquidity_usd: 40_000,
        reference_score: 0.76,
        summary: 'Older baseline reference.',
        reasons: ['stale'],
      },
      {
        read_only: true,
        reference_id: 'ref-better',
        market_id: 'market-1',
        venue: 'polymarket',
        source: 'cross_venue_candidate',
        role: 'anchor',
        price_yes: 0.49,
        spread_bps: 90,
        quote_age_ms: 15_000,
        freshness_gap_ms: 9_000,
        liquidity_usd: 55_000,
        reference_score: 0.98,
        summary: 'Best fresh anchor reference.',
        reasons: ['fresh_anchor'],
      },
    ],
  }
}

describe('strategy shadow', () => {
  it('treats attack and sniping watches as defense-only and emits a latency-aware summary', () => {
    const input = makeInput()
    const watchlist = buildShadowStrategyWatchlist(input)
    const summary = summarizeShadowStrategyWatchlist(watchlist)
    const defenseSummary = buildShadowStrategyDefenseSummary(input)

    expect(watchlist).toHaveLength(2)
    expect(watchlist.every((watch) => watch.disposition === 'defense')).toBe(true)
    expect(watchlist.map((watch) => watch.kind)).toEqual([
      'resolution_attack_watch',
      'resolution_sniping_watch',
    ])

    expect(summary).toMatchObject({
      total: 2,
      watch_count: 0,
      defense_count: 2,
      attack_watch_count: 1,
      sniping_watch_count: 1,
    })
    expect(summary.summary).toContain('shadow defense watchlist contains 2 defense signals')
    expect(summary.reasons).toEqual(expect.arrayContaining([
      'defense_signals_present',
      'attack_watch_present',
      'sniping_watch_present',
    ]))

    expect(defenseSummary).toMatchObject({
      market_id: 'market-1',
      venue: 'polymarket',
      disposition: 'defense',
      latency_reference_count: 2,
      best_latency_reference_id: 'ref-better',
      best_latency_reference_gap_ms: 9_000,
      severity: 'high',
      watch_count: 0,
      defense_count: 2,
      attack_watch_count: 1,
      sniping_watch_count: 1,
    })
    expect(defenseSummary.summary).toContain('shadow defense summary for market-1')
    expect(defenseSummary.summary).toContain('regime=defense/anomalous/lagging')
    expect(defenseSummary.summary).toContain('maker_quote=blocked')
    expect(defenseSummary.summary).toContain('best_reference=ref-better gap_ms=9000')
    expect(defenseSummary.reasons).toEqual(expect.arrayContaining([
      'defense_only',
      'latency_references:2',
      'latency_state:lagging',
      'resolution_state:anomalous',
      'maker_quote_state:blocked',
      'maker_quote_freshness_budget_ms:0',
      'top_watch_kind:resolution_attack_watch',
    ]))
    expect(defenseSummary.defensive_controls).toEqual(expect.arrayContaining([
      'route_to_manual_review',
      'preserve_read_only_monitoring',
      'prefer_fresh_quotes',
      'monitor_quote_age',
      'avoid_quote_fade_entry',
    ]))
  })
})
