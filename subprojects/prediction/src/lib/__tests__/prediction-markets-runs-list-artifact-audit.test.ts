import { describe, expect, it, vi } from 'vitest'

const storeMocks = vi.hoisted(() => ({
  listPredictionMarketRuns: vi.fn(),
}))

vi.mock('@/lib/prediction-markets/store', () => ({
  listPredictionMarketRuns: storeMocks.listPredictionMarketRuns,
}))

import { listPredictionMarketRuns } from '@/lib/prediction-markets/service'
import {
  predictionMarketArtifactRefSchema,
  runManifestSchema,
} from '@/lib/prediction-markets/schemas'

function makeArtifactRef(input: {
  runId: string
  artifactType: 'market_descriptor' | 'forecast_packet' | 'recommendation_packet' | 'run_manifest'
  sha256: string
}) {
  return predictionMarketArtifactRefSchema.parse({
    artifact_id: `${input.runId}:${input.artifactType}`,
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
    mode: 'advise',
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

describe('prediction markets runs list artifact audit', () => {
  it('keeps the runs list readable for ops when manifest and observed artifacts diverge', () => {
    const runId = 'run-ops-001'
    const marketDescriptor = makeArtifactRef({
      runId,
      artifactType: 'market_descriptor',
      sha256: 'sha-market-descriptor',
    })
    const forecastPacket = makeArtifactRef({
      runId,
      artifactType: 'forecast_packet',
      sha256: 'sha-forecast-packet',
    })
    const recommendationPacket = makeArtifactRef({
      runId,
      artifactType: 'recommendation_packet',
      sha256: 'sha-recommendation-packet',
    })
    const runManifestRef = makeArtifactRef({
      runId,
      artifactType: 'run_manifest',
      sha256: 'sha-run-manifest',
    })

    storeMocks.listPredictionMarketRuns.mockReturnValueOnce([
      {
        run_id: runId,
        source_run_id: null,
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: 'mkt-audit-001',
        market_slug: 'mkt-audit-001',
        status: 'completed',
        recommendation: 'wait',
        side: null,
        confidence: 0.62,
        probability_yes: 0.53,
        market_price_yes: 0.49,
        edge_bps: 400,
        created_at: 1712534400,
        updated_at: 1712534460,
        manifest: makeRunManifest({
          runId,
          artifactRefs: [
            marketDescriptor,
            forecastPacket,
            forecastPacket,
            runManifestRef,
          ],
        }),
        artifact_refs: [
          marketDescriptor,
          forecastPacket,
          runManifestRef,
          recommendationPacket,
        ],
      },
    ])

    const runs = listPredictionMarketRuns({
      workspaceId: 1,
      venue: 'polymarket',
      limit: 20,
    })

    expect(runs).toHaveLength(1)
    expect(runs[0]).toMatchObject({
      run_id: runId,
      workspace_id: 1,
      venue: 'polymarket',
      status: 'completed',
    })
    expect(runs[0]?.artifact_audit).toEqual({
      manifest_ref_count: 3,
      observed_ref_count: 4,
      canonical_ref_count: 4,
      run_manifest_present: true,
      duplicate_artifact_ids: [`${runId}:forecast_packet`],
      manifest_only_artifact_ids: [],
      observed_only_artifact_ids: [`${runId}:recommendation_packet`],
    })
  })
})
