import { describe, expect, it } from 'vitest'
import {
  buildPredictionMarketArtifactReadback,
  indexPredictionMarketArtifactRefs,
} from '@/lib/prediction-markets/artifact-readback'
import {
  predictionMarketArtifactRefSchema,
  runManifestSchema,
  type PredictionMarketArtifactType,
} from '@/lib/prediction-markets/schemas'

function makeArtifactRef(input: {
  runId: string
  artifactType: PredictionMarketArtifactType
  sha256: string
  artifactId?: string
}) {
  return predictionMarketArtifactRefSchema.parse({
    artifact_id: input.artifactId ?? `${input.runId}:${input.artifactType}`,
    artifact_type: input.artifactType,
    sha256: input.sha256,
  })
}

function makeRunManifest(input: {
  runId: string
  artifactRefs: Array<ReturnType<typeof makeArtifactRef>>
}) {
  return runManifestSchema.parse({
    run_id: input.runId,
    source_run_id: 'run-source-001',
    mode: 'replay',
    venue: 'polymarket',
    market_id: 'mkt-audit-001',
    market_slug: 'mkt-audit-001',
    actor: 'operator',
    started_at: '2026-04-08T00:00:00.000Z',
    completed_at: '2026-04-08T00:01:00.000Z',
    status: 'completed',
    config_hash: `cfg-${input.runId}`,
    artifact_refs: input.artifactRefs,
  })
}

describe('prediction markets artifact readback surfaces', () => {
  it('keeps the run-surface manifest index readable for ops audit review', () => {
    const manifestRefs = [
      makeArtifactRef({
        runId: 'run-ops-001',
        artifactType: 'market_descriptor',
        sha256: 'sha-market-descriptor',
      }),
      makeArtifactRef({
        runId: 'run-ops-001',
        artifactType: 'forecast_packet',
        sha256: 'sha-forecast-packet',
      }),
      makeArtifactRef({
        runId: 'run-ops-001',
        artifactType: 'run_manifest',
        sha256: 'sha-run-manifest',
      }),
    ]

    const readback = buildPredictionMarketArtifactReadback({
      manifest: makeRunManifest({
        runId: 'run-ops-001',
        artifactRefs: manifestRefs,
      }),
      artifact_refs: manifestRefs,
    })

    expect(readback.manifest_index.refs.map((ref) => ref.artifact_id)).toEqual([
      'run-ops-001:market_descriptor',
      'run-ops-001:forecast_packet',
      'run-ops-001:run_manifest',
    ])
    expect(readback.manifest_index.by_artifact_type.market_descriptor).toEqual([manifestRefs[0]])
    expect(readback.manifest_index.by_artifact_type.forecast_packet).toEqual([manifestRefs[1]])
    expect(readback.manifest_index.by_artifact_type.run_manifest).toEqual([manifestRefs[2]])
    expect(readback.manifest_only_artifact_ids).toEqual([])
    expect(readback.observed_only_artifact_ids).toEqual([])
    expect(readback.run_manifest_ref).toEqual(manifestRefs[2])
  })

  it('builds a runs-surface canonical index with stable first-seen ordering', () => {
    const manifestRefs = [
      makeArtifactRef({
        runId: 'run-ops-002',
        artifactType: 'market_descriptor',
        sha256: 'sha-market-descriptor',
      }),
      makeArtifactRef({
        runId: 'run-ops-002',
        artifactType: 'run_manifest',
        sha256: 'sha-run-manifest',
      }),
    ]
    const observedRefs = [
      makeArtifactRef({
        runId: 'run-ops-002',
        artifactType: 'market_descriptor',
        sha256: 'sha-market-descriptor',
      }),
      makeArtifactRef({
        runId: 'run-ops-002',
        artifactType: 'forecast_packet',
        sha256: 'sha-forecast-packet',
      }),
      makeArtifactRef({
        runId: 'run-ops-002',
        artifactType: 'forecast_packet',
        sha256: 'sha-forecast-packet',
      }),
      makeArtifactRef({
        runId: 'run-ops-002',
        artifactType: 'run_manifest',
        sha256: 'sha-run-manifest',
      }),
      makeArtifactRef({
        runId: 'run-ops-002',
        artifactType: 'recommendation_packet',
        sha256: 'sha-recommendation-packet',
      }),
    ]

    const readback = buildPredictionMarketArtifactReadback({
      manifest: makeRunManifest({
        runId: 'run-ops-002',
        artifactRefs: manifestRefs,
      }),
      artifact_refs: observedRefs,
    })

    expect(readback.canonical_index.refs.map((ref) => ref.artifact_id)).toEqual([
      'run-ops-002:market_descriptor',
      'run-ops-002:run_manifest',
      'run-ops-002:forecast_packet',
      'run-ops-002:recommendation_packet',
    ])
    expect(readback.canonical_index.duplicate_artifact_ids).toEqual([
      'run-ops-002:market_descriptor',
      'run-ops-002:forecast_packet',
      'run-ops-002:run_manifest',
    ])
    expect(readback.canonical_index.by_artifact_type.forecast_packet).toEqual([
      observedRefs[1],
    ])
    expect(readback.observed_index.refs.map((ref) => ref.artifact_id)).toEqual([
      'run-ops-002:market_descriptor',
      'run-ops-002:forecast_packet',
      'run-ops-002:run_manifest',
      'run-ops-002:recommendation_packet',
    ])
    expect(readback.observed_only_artifact_ids).toEqual([
      'run-ops-002:forecast_packet',
      'run-ops-002:recommendation_packet',
    ])
  })

  it('falls back to the first run_manifest ref when the run-scoped id is missing', () => {
    const legacyRunManifest = makeArtifactRef({
      runId: 'legacy-run',
      artifactId: 'legacy:run_manifest',
      artifactType: 'run_manifest',
      sha256: 'sha-legacy-run-manifest',
    })
    const manifestRefs = [
      makeArtifactRef({
        runId: 'run-ops-003',
        artifactType: 'market_descriptor',
        sha256: 'sha-market-descriptor',
      }),
      legacyRunManifest,
    ]

    const readback = buildPredictionMarketArtifactReadback({
      manifest: makeRunManifest({
        runId: 'run-ops-003',
        artifactRefs: manifestRefs,
      }),
      artifact_refs: [
        makeArtifactRef({
          runId: 'run-ops-003',
          artifactType: 'market_descriptor',
          sha256: 'sha-market-descriptor',
        }),
        makeArtifactRef({
          runId: 'run-ops-003',
          artifactType: 'forecast_packet',
          sha256: 'sha-forecast-packet',
        }),
        legacyRunManifest,
      ],
    })

    expect(readback.run_manifest_ref).toEqual(legacyRunManifest)
    expect(readback.canonical_index.by_artifact_type.run_manifest).toEqual([
      legacyRunManifest,
    ])
    expect(readback.manifest_only_artifact_ids).toEqual([])
    expect(readback.observed_only_artifact_ids).toEqual([
      'run-ops-003:forecast_packet',
    ])
  })
})

describe('indexPredictionMarketArtifactRefs', () => {
  it('keeps a compact, readable index for repeated artifact ids', () => {
    const first = makeArtifactRef({
      runId: 'run-ops-004',
      artifactType: 'market_descriptor',
      sha256: 'sha-market-descriptor',
    })
    const duplicate = makeArtifactRef({
      runId: 'run-ops-004',
      artifactType: 'market_descriptor',
      sha256: 'sha-market-descriptor',
    })
    const manifest = makeArtifactRef({
      runId: 'run-ops-004',
      artifactType: 'run_manifest',
      sha256: 'sha-run-manifest',
    })

    const index = indexPredictionMarketArtifactRefs([
      first,
      duplicate,
      manifest,
    ])

    expect(index.refs).toEqual([first, manifest])
    expect(index.by_artifact_id['run-ops-004:market_descriptor']).toEqual(first)
    expect(index.by_artifact_type.market_descriptor).toEqual([first])
    expect(index.by_artifact_type.run_manifest).toEqual([manifest])
    expect(index.duplicate_artifact_ids).toEqual([
      'run-ops-004:market_descriptor',
    ])
  })
})
