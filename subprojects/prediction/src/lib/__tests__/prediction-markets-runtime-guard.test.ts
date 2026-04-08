import { describe, expect, it } from 'vitest'
import {
  getVenueBudgetsContract,
  getVenueCapabilitiesContract,
  getVenueHealthSnapshotContract,
} from '@/lib/prediction-markets/venue-ops'
import { evaluatePredictionMarketRuntimeGuard } from '@/lib/prediction-markets/runtime-guard'

describe('prediction market runtime guard', () => {
  it('allows discovery on a healthy venue', () => {
    const result = evaluatePredictionMarketRuntimeGuard({
      venue: 'polymarket',
      mode: 'discovery',
      capabilities: getVenueCapabilitiesContract('polymarket'),
      health: getVenueHealthSnapshotContract('polymarket'),
      budgets: getVenueBudgetsContract('polymarket'),
    })

    expect(result.verdict).toBe('allowed')
    expect(result.reasons).toEqual([])
    expect(result.constraints).toEqual(
      expect.arrayContaining(['mode=discovery', 'venue=polymarket', 'supports_discovery=true']),
    )
    expect(result.fallback_actions).toEqual(
      expect.arrayContaining(['keep_read_only', 'reduce_polling_cadence']),
    )
  })

  it('degrades paper runs when the venue is advisory-only', () => {
    const result = evaluatePredictionMarketRuntimeGuard({
      venue: 'polymarket',
      mode: 'paper',
      capabilities: getVenueCapabilitiesContract('polymarket'),
      health: getVenueHealthSnapshotContract('polymarket'),
      budgets: getVenueBudgetsContract('polymarket'),
    })

    expect(result.verdict).toBe('degraded')
    expect(result.reasons).toEqual(
      expect.arrayContaining([
        'paper mode is not supported by the venue contract',
        'automation constraints apply: read-only advisory mode only',
      ]),
    )
    expect(result.fallback_actions).toEqual(
      expect.arrayContaining(['downgrade_mode_to_shadow', 'downgrade_mode_to_discovery']),
    )
  })

  it('blocks live runs when execution is not supported', () => {
    const result = evaluatePredictionMarketRuntimeGuard({
      venue: 'kalshi',
      mode: 'live',
      capabilities: getVenueCapabilitiesContract('kalshi'),
      health: getVenueHealthSnapshotContract('kalshi'),
      budgets: getVenueBudgetsContract('kalshi'),
    })

    expect(result.verdict).toBe('blocked')
    expect(result.reasons).toEqual(
      expect.arrayContaining([
        'live mode requires execution support',
        'automation constraints apply: read-only advisory mode only',
      ]),
    )
    expect(result.fallback_actions).toEqual(
      expect.arrayContaining(['downgrade_mode_to_shadow', 'disable_execution', 'quarantine_venue']),
    )
  })

  it('degrades shadow runs on degraded health', () => {
    const result = evaluatePredictionMarketRuntimeGuard({
      venue: 'kalshi',
      mode: 'shadow',
      capabilities: getVenueCapabilitiesContract('kalshi'),
      health: {
        ...getVenueHealthSnapshotContract('kalshi'),
        api_status: 'degraded',
        stream_status: 'degraded',
        degraded_mode: 'degraded',
        health_score: 0.61,
        incident_flags: ['stale_snapshot'],
      },
      budgets: getVenueBudgetsContract('kalshi'),
    })

    expect(result.verdict).toBe('degraded')
    expect(result.reasons).toEqual(
      expect.arrayContaining(['venue health is degraded', 'venue health has incident flags: stale_snapshot']),
    )
    expect(result.fallback_actions).toEqual(
      expect.arrayContaining(['prefer_cached_snapshots', 'reduce_polling_cadence']),
    )
  })

  it('degrades on budget pressure even when the venue is otherwise capable', () => {
    const result = evaluatePredictionMarketRuntimeGuard({
      venue: 'kalshi',
      mode: 'shadow',
      capabilities: {
        ...getVenueCapabilitiesContract('kalshi'),
        supports_paper_mode: true,
        supports_execution: true,
        supports_positions: true,
        automation_constraints: [],
      },
      health: {
        ...getVenueHealthSnapshotContract('kalshi'),
        api_status: 'healthy',
        stream_status: 'healthy',
        degraded_mode: 'normal',
        health_score: 1,
        incident_flags: [],
      },
      budgets: {
        ...getVenueBudgetsContract('kalshi'),
        snapshot_freshness_budget_ms: 60_000,
        decision_latency_budget_ms: 30_000,
        stream_reconnect_budget_ms: 90_000,
        cache_ttl_ms: 60_000,
        max_retries: 2,
        backpressure_policy: 'degrade-to-wait',
      },
    })

    expect(result.verdict).toBe('degraded')
    expect(result.reasons[0]).toContain('budgets exceed the conservative envelope')
    expect(result.constraints).toEqual(
      expect.arrayContaining([
        'snapshot_freshness_budget_ms<=10000',
        'decision_latency_budget_ms<=5000',
        'backpressure_policy=degrade-to-wait',
      ]),
    )
    expect(result.fallback_actions).toEqual(
      expect.arrayContaining(['trim_history_window', 'lower_parallelism', 'prefer_cached_snapshots']),
    )
  })
})
