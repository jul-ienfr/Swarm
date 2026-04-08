import { describe, expect, it } from 'vitest'
import {
  buildPredictionMarketArtifactReadback,
  indexPredictionMarketArtifactRefs,
} from '@/lib/prediction-markets/artifact-readback'
import {
  predictionMarketArtifactRefSchema,
  runManifestSchema,
} from '@/lib/prediction-markets/schemas'

describe('prediction markets artifact readback', () => {
  it('indexes refs deterministically and deduplicates by artifact id', () => {
    const refs = [
      predictionMarketArtifactRefSchema.parse({
        artifact_id: 'run-001:market_descriptor',
        artifact_type: 'market_descriptor',
        sha256: 'sha-market-descriptor',
      }),
      predictionMarketArtifactRefSchema.parse({
        artifact_id: 'run-001:market_descriptor',
        artifact_type: 'market_descriptor',
        sha256: 'sha-market-descriptor',
      }),
      predictionMarketArtifactRefSchema.parse({
        artifact_id: 'run-001:forecast_packet',
        artifact_type: 'forecast_packet',
        sha256: 'sha-forecast-packet',
      }),
      predictionMarketArtifactRefSchema.parse({
        artifact_id: 'run-001:run_manifest',
        artifact_type: 'run_manifest',
        sha256: 'sha-run-manifest',
      }),
    ]

    const index = indexPredictionMarketArtifactRefs(refs)

    expect(index.refs).toHaveLength(3)
    expect(index.duplicate_artifact_ids).toEqual(['run-001:market_descriptor'])
    expect(index.by_artifact_id['run-001:forecast_packet']).toEqual(refs[2])
    expect(index.by_artifact_type.market_descriptor).toEqual([refs[0]])
    expect(index.by_artifact_type.run_manifest).toEqual([refs[3]])
  })

  it('rebuilds a canonical readback index from manifest refs and observed refs', () => {
    const manifest = runManifestSchema.parse({
      run_id: 'run-002',
      source_run_id: 'run-001',
      mode: 'replay',
      venue: 'polymarket',
      market_id: 'mkt-123',
      market_slug: 'mkt-123',
      actor: 'operator',
      started_at: '2026-04-08T00:00:00.000Z',
      completed_at: '2026-04-08T00:01:00.000Z',
      status: 'completed',
      config_hash: 'cfg-hash-123',
      artifact_refs: [
        {
          artifact_id: 'run-002:market_descriptor',
          artifact_type: 'market_descriptor',
          sha256: 'sha-market-descriptor',
        },
        {
          artifact_id: 'run-002:run_manifest',
          artifact_type: 'run_manifest',
          sha256: 'sha-run-manifest',
        },
      ],
    })

    const readback = buildPredictionMarketArtifactReadback({
      manifest,
      artifact_refs: [
        {
          artifact_id: 'run-002:market_descriptor',
          artifact_type: 'market_descriptor',
          sha256: 'sha-market-descriptor',
        },
        {
          artifact_id: 'run-002:forecast_packet',
          artifact_type: 'forecast_packet',
          sha256: 'sha-forecast-packet',
        },
        {
          artifact_id: 'run-002:run_manifest',
          artifact_type: 'run_manifest',
          sha256: 'sha-run-manifest',
        },
      ],
    })

    expect(readback.manifest.run_id).toBe('run-002')
    expect(readback.manifest_artifact_refs).toHaveLength(2)
    expect(readback.observed_artifact_refs).toHaveLength(3)
    expect(readback.canonical_artifact_refs).toEqual([
      {
        artifact_id: 'run-002:market_descriptor',
        artifact_type: 'market_descriptor',
        sha256: 'sha-market-descriptor',
      },
      {
        artifact_id: 'run-002:run_manifest',
        artifact_type: 'run_manifest',
        sha256: 'sha-run-manifest',
      },
      {
        artifact_id: 'run-002:forecast_packet',
        artifact_type: 'forecast_packet',
        sha256: 'sha-forecast-packet',
      },
    ])
    expect(readback.manifest_only_artifact_ids).toEqual([])
    expect(readback.observed_only_artifact_ids).toEqual(['run-002:forecast_packet'])
    expect(readback.run_manifest_ref).toEqual({
      artifact_id: 'run-002:run_manifest',
      artifact_type: 'run_manifest',
      sha256: 'sha-run-manifest',
    })
  })
})
