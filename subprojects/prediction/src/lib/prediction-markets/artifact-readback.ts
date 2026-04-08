import {
  predictionMarketArtifactRefSchema,
  runManifestSchema,
  type PredictionMarketArtifactRef,
  type PredictionMarketArtifactType,
  type RunManifest,
} from '@/lib/prediction-markets/schemas'

export type PredictionMarketArtifactRefIndex = {
  refs: PredictionMarketArtifactRef[]
  by_artifact_id: Record<string, PredictionMarketArtifactRef>
  by_artifact_type: Partial<Record<PredictionMarketArtifactType, PredictionMarketArtifactRef[]>>
  duplicate_artifact_ids: string[]
}

export type PredictionMarketArtifactReadbackInput = {
  manifest: RunManifest
  artifact_refs?: Array<PredictionMarketArtifactRef>
}

export type PredictionMarketArtifactReadbackIndex = {
  manifest: RunManifest
  manifest_artifact_refs: PredictionMarketArtifactRef[]
  observed_artifact_refs: PredictionMarketArtifactRef[]
  canonical_artifact_refs: PredictionMarketArtifactRef[]
  manifest_index: PredictionMarketArtifactRefIndex
  observed_index: PredictionMarketArtifactRefIndex
  canonical_index: PredictionMarketArtifactRefIndex
  manifest_only_artifact_ids: string[]
  observed_only_artifact_ids: string[]
  run_manifest_ref: PredictionMarketArtifactRef | null
}

function normalizePredictionMarketArtifactRefs(
  artifactRefs: Array<PredictionMarketArtifactRef>,
): PredictionMarketArtifactRef[] {
  return artifactRefs.map((artifactRef) => predictionMarketArtifactRefSchema.parse(artifactRef))
}

export function indexPredictionMarketArtifactRefs(
  artifactRefs: Array<PredictionMarketArtifactRef>,
): PredictionMarketArtifactRefIndex {
  const refs = normalizePredictionMarketArtifactRefs(artifactRefs)
  const by_artifact_id: Record<string, PredictionMarketArtifactRef> = {}
  const by_artifact_type: Partial<Record<PredictionMarketArtifactType, PredictionMarketArtifactRef[]>> = {}
  const duplicateIds = new Set<string>()
  const canonicalRefs: PredictionMarketArtifactRef[] = []

  for (const artifactRef of refs) {
    if (by_artifact_id[artifactRef.artifact_id]) {
      duplicateIds.add(artifactRef.artifact_id)
      continue
    }

    by_artifact_id[artifactRef.artifact_id] = artifactRef
    canonicalRefs.push(artifactRef)
    by_artifact_type[artifactRef.artifact_type] ??= []
    by_artifact_type[artifactRef.artifact_type]!.push(artifactRef)
  }

  return {
    refs: canonicalRefs,
    by_artifact_id,
    by_artifact_type,
    duplicate_artifact_ids: [...duplicateIds],
  }
}

export function buildPredictionMarketArtifactReadback(
  input: PredictionMarketArtifactReadbackInput,
): PredictionMarketArtifactReadbackIndex {
  const manifest = runManifestSchema.parse(input.manifest)
  const manifestArtifactRefs = normalizePredictionMarketArtifactRefs(manifest.artifact_refs)
  const observedArtifactRefs = normalizePredictionMarketArtifactRefs(
    input.artifact_refs ?? manifestArtifactRefs,
  )
  const manifestIndex = indexPredictionMarketArtifactRefs(manifestArtifactRefs)
  const observedIndex = indexPredictionMarketArtifactRefs(observedArtifactRefs)
  const canonicalIndex = indexPredictionMarketArtifactRefs([
    ...manifestArtifactRefs,
    ...observedArtifactRefs,
  ])
  const manifestIds = new Set(manifestIndex.refs.map((artifactRef) => artifactRef.artifact_id))
  const observedIds = new Set(observedIndex.refs.map((artifactRef) => artifactRef.artifact_id))

  return {
    manifest,
    manifest_artifact_refs: manifestIndex.refs,
    observed_artifact_refs: observedIndex.refs,
    canonical_artifact_refs: canonicalIndex.refs,
    manifest_index: manifestIndex,
    observed_index: observedIndex,
    canonical_index: canonicalIndex,
    manifest_only_artifact_ids: [...manifestIds].filter((artifactId) => !observedIds.has(artifactId)),
    observed_only_artifact_ids: [...observedIds].filter((artifactId) => !manifestIds.has(artifactId)),
    run_manifest_ref:
      canonicalIndex.by_artifact_id[`${manifest.run_id}:run_manifest`] ??
      canonicalIndex.refs.find((artifactRef) => artifactRef.artifact_type === 'run_manifest') ??
      null,
  }
}
