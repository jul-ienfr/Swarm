import { describe, expect, it } from 'vitest'
import {
  PREDICTION_MARKETS_ARTIFACT_BUCKETS,
  PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT,
  buildPredictionMarketArtifactLayout,
  buildPredictionMarketArtifactManifestKeys,
  getPredictionMarketArtifactDescriptor,
  getPredictionMarketBucketRoot,
  getPredictionMarketMarketRoot,
  getPredictionMarketRunRoot,
  getPredictionMarketVenueRoot,
} from '@/lib/prediction-markets/artifact-layout'

describe('prediction markets artifact layout', () => {
  it('builds stable roots for venue, market, and run', () => {
    expect(PREDICTION_MARKETS_ARTIFACT_BUCKETS).toEqual([
      'catalog',
      'orderbooks',
      'trades',
      'resolution',
      'evidence',
      'runs',
    ])
    expect(getPredictionMarketVenueRoot('polymarket')).toBe(
      `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket`,
    )
    expect(getPredictionMarketMarketRoot({
      venue: 'kalshi',
      market_id: 'BTC / Apr 2026',
    })).toBe(
      `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/kalshi/markets/BTC%20%2F%20Apr%202026`,
    )
    expect(getPredictionMarketRunRoot('run:abc/123')).toBe(
      `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/runs/run%3Aabc%2F123`,
    )
    expect(getPredictionMarketBucketRoot({
      venue: 'polymarket',
      market_id: 'mkt-123',
      bucket: 'resolution',
    })).toBe(
      `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket/markets/mkt-123/resolution`,
    )
  })

  it('maps current schema artifact types to canonical buckets and stable paths', () => {
    const layout = buildPredictionMarketArtifactLayout({
      run_id: 'pm-run-002',
      venue: 'polymarket',
      market_id: 'mkt-123',
      artifact_type: 'evidence_bundle',
    })

    expect(layout).toMatchObject({
      artifact_id: 'pm-run-002:evidence_bundle',
      bucket: 'evidence',
      extension: 'json',
      file_name: 'evidence_bundle.json',
      venue_root: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket`,
      market_root: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket/markets/mkt-123`,
      bucket_root: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket/markets/mkt-123/evidence`,
      run_root: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/runs/pm-run-002/evidence`,
      run_path: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/runs/pm-run-002/evidence/evidence_bundle.json`,
      market_path: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket/markets/mkt-123/evidence/pm-run-002--evidence_bundle.json`,
      latest_path: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket/markets/mkt-123/evidence/latest--evidence_bundle.json`,
      manifest_keys: {
        artifact_id: 'pm-run-002:evidence_bundle',
        artifact_type: 'evidence_bundle',
        bucket: 'evidence',
        file_name: 'evidence_bundle.json',
        run_key: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/runs/pm-run-002/evidence/evidence_bundle.json`,
        market_key: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket/markets/mkt-123/evidence/pm-run-002--evidence_bundle.json`,
        latest_key: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket/markets/mkt-123/evidence/latest--evidence_bundle.json`,
      },
    })
  })

  it('uses dedicated orderbooks and trades buckets for future raw market artifacts', () => {
    const orderbookLayout = buildPredictionMarketArtifactLayout({
      run_id: 'run-01',
      venue: 'kalshi',
      market_id: 'event-01',
      artifact_type: 'orderbook_snapshot',
    })
    const tradeLayout = buildPredictionMarketArtifactLayout({
      run_id: 'run-01',
      venue: 'kalshi',
      market_id: 'event-01',
      artifact_type: 'trade_tape',
    })

    expect(orderbookLayout.bucket).toBe('orderbooks')
    expect(orderbookLayout.file_name).toBe('orderbook_snapshot.json')
    expect(tradeLayout.bucket).toBe('trades')
    expect(tradeLayout.file_name).toBe('trade_tape.jsonl')
    expect(tradeLayout.market_path).toBe(
      `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/kalshi/markets/event-01/trades/run-01--trade_tape.jsonl`,
    )
  })

  it('keeps run-scoped artifacts under the runs bucket', () => {
    expect(getPredictionMarketArtifactDescriptor('market_snapshot')).toEqual({
      bucket: 'runs',
      basename: 'market_snapshot',
      extension: 'json',
    })
    expect(getPredictionMarketArtifactDescriptor('forecast_packet')).toEqual({
      bucket: 'runs',
      basename: 'forecast_packet',
      extension: 'json',
    })
    expect(getPredictionMarketArtifactDescriptor('microstructure_lab')).toEqual({
      bucket: 'runs',
      basename: 'microstructure_lab',
      extension: 'json',
    })
    expect(getPredictionMarketArtifactDescriptor('market_events')).toEqual({
      bucket: 'runs',
      basename: 'market_events',
      extension: 'json',
    })
    expect(getPredictionMarketArtifactDescriptor('market_positions')).toEqual({
      bucket: 'runs',
      basename: 'market_positions',
      extension: 'json',
    })
    expect(getPredictionMarketArtifactDescriptor('resolved_history')).toEqual({
      bucket: 'runs',
      basename: 'resolved_history',
      extension: 'json',
    })
    expect(getPredictionMarketArtifactDescriptor('cost_model_report')).toEqual({
      bucket: 'runs',
      basename: 'cost_model_report',
      extension: 'json',
    })
    expect(getPredictionMarketArtifactDescriptor('walk_forward_report')).toEqual({
      bucket: 'runs',
      basename: 'walk_forward_report',
      extension: 'json',
    })
    expect(getPredictionMarketArtifactDescriptor('run_manifest')).toEqual({
      bucket: 'runs',
      basename: 'run_manifest',
      extension: 'json',
    })
    expect(getPredictionMarketArtifactDescriptor('execution_readiness')).toEqual({
      bucket: 'runs',
      basename: 'execution_readiness',
      extension: 'json',
    })
    expect(getPredictionMarketArtifactDescriptor('execution_pathways')).toEqual({
      bucket: 'runs',
      basename: 'execution_pathways',
      extension: 'json',
    })
    expect(getPredictionMarketArtifactDescriptor('execution_projection')).toEqual({
      bucket: 'runs',
      basename: 'execution_projection',
      extension: 'json',
    })
    expect(getPredictionMarketArtifactDescriptor('shadow_arbitrage')).toEqual({
      bucket: 'runs',
      basename: 'shadow_arbitrage',
      extension: 'json',
    })
    expect(getPredictionMarketArtifactDescriptor('trade_intent_guard')).toEqual({
      bucket: 'runs',
      basename: 'trade_intent_guard',
      extension: 'json',
    })
    expect(getPredictionMarketArtifactDescriptor('multi_venue_execution')).toEqual({
      bucket: 'runs',
      basename: 'multi_venue_execution',
      extension: 'json',
    })
    expect(getPredictionMarketArtifactDescriptor('provenance_bundle')).toEqual({
      bucket: 'evidence',
      basename: 'provenance_bundle',
      extension: 'json',
    })
  })

  it('returns deterministic keys for the same input', () => {
    const first = buildPredictionMarketArtifactLayout({
      run_id: 'run-xyz',
      venue: 'polymarket',
      market_id: 'Will BTC > 100k?',
      artifact_type: 'resolution_policy',
    })
    const second = buildPredictionMarketArtifactLayout({
      run_id: 'run-xyz',
      venue: 'polymarket',
      market_id: 'Will BTC > 100k?',
      artifact_type: 'resolution_policy',
    })

    expect(first.run_key).toBe(second.run_key)
    expect(first.market_key).toBe(second.market_key)
    expect(first.latest_key).toBe(second.latest_key)
    expect(first.manifest_keys).toEqual(second.manifest_keys)
  })

  it('builds explicit manifest keys from stable storage paths', () => {
    expect(buildPredictionMarketArtifactManifestKeys({
      artifact_id: 'run-1:run_manifest',
      artifact_type: 'run_manifest',
      bucket: 'runs',
      file_name: 'run_manifest.json',
      run_key: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/runs/run-1/runs/run_manifest.json`,
      market_key: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket/markets/mkt-1/runs/run-1--run_manifest.json`,
      latest_key: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket/markets/mkt-1/runs/latest--run_manifest.json`,
    })).toEqual({
      artifact_id: 'run-1:run_manifest',
      artifact_type: 'run_manifest',
      bucket: 'runs',
      file_name: 'run_manifest.json',
      run_key: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/runs/run-1/runs/run_manifest.json`,
      market_key: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket/markets/mkt-1/runs/run-1--run_manifest.json`,
      latest_key: `${PREDICTION_MARKETS_ARTIFACT_LAYOUT_ROOT}/venues/polymarket/markets/mkt-1/runs/latest--run_manifest.json`,
    })
  })
})
