import {
  buildPredictionMarketExternalIntegrationSummary,
  getConversationScopedExternalSourceProfile,
  type PredictionMarketExternalIntegrationBatch,
  type PredictionMarketExternalIntegrationSummary,
  type PredictionMarketExternalSourceProfileSummary,
} from './external-source-profiles'

type ExternalRuntimeStatus = 'active' | 'configured' | 'catalog_only' | 'watchlist_only'

export type PredictionMarketExternalRuntimeActivation = {
  profile_id: string
  label: string
  batch: PredictionMarketExternalIntegrationBatch
  status: ExternalRuntimeStatus
  target_modules: string[]
  summary: string
}

export type PredictionMarketExternalBatchRuntimeSummary = {
  batch: PredictionMarketExternalIntegrationBatch
  active_profile_ids: string[]
  configured_profile_ids: string[]
  catalog_profile_ids: string[]
  watchlist_profile_ids: string[]
  active_profiles: PredictionMarketExternalSourceProfileSummary[]
  configured_profiles: PredictionMarketExternalSourceProfileSummary[]
  catalog_profiles: PredictionMarketExternalSourceProfileSummary[]
  watchlist_profiles: PredictionMarketExternalSourceProfileSummary[]
  integration: PredictionMarketExternalIntegrationSummary
  runtime_activations: PredictionMarketExternalRuntimeActivation[]
  summary: string
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const value of values) {
    const normalized = String(value ?? '').trim()
    if (!normalized || seen.has(normalized)) continue
    seen.add(normalized)
    out.push(normalized)
  }
  return out
}

function readEnvText(...names: string[]): string | null {
  for (const name of names) {
    const value = process.env[name]
    if (typeof value === 'string' && value.trim().length > 0) {
      return value.trim()
    }
  }
  return null
}

function readEnvTruthy(...names: string[]): boolean {
  for (const name of names) {
    const value = process.env[name]
    if (typeof value !== 'string') continue
    const normalized = value.trim().toLowerCase()
    if (['1', 'true', 'yes', 'on', 'enabled', 'active'].includes(normalized)) return true
  }
  return false
}

function asActivation(profileId: string, status: ExternalRuntimeStatus, summary: string): PredictionMarketExternalRuntimeActivation | null {
  const profile = getConversationScopedExternalSourceProfile(profileId)
  if (!profile) return null
  return {
    profile_id: profile.profile_id,
    label: profile.label,
    batch: profile.batch,
    status,
    target_modules: [...profile.target_modules],
    summary,
  }
}

export function buildPredictionMarketExternalBatchRuntimeSummary(input: {
  batch: PredictionMarketExternalIntegrationBatch
  active_profile_ids?: string[] | null
  configured_profile_ids?: string[] | null
  catalog_profile_ids?: string[] | null
  watchlist_profile_ids?: string[] | null
}): PredictionMarketExternalBatchRuntimeSummary {
  const activeProfiles = uniqueStrings(input.active_profile_ids ?? [])
    .map((profileId) => getConversationScopedExternalSourceProfile(profileId))
    .filter((profile): profile is PredictionMarketExternalSourceProfileSummary => profile != null)
  const configuredProfiles = uniqueStrings(input.configured_profile_ids ?? [])
    .map((profileId) => getConversationScopedExternalSourceProfile(profileId))
    .filter((profile): profile is PredictionMarketExternalSourceProfileSummary => profile != null)
    .filter((profile) => !activeProfiles.some((candidate) => candidate.profile_id === profile.profile_id))
  const catalogProfiles = uniqueStrings(input.catalog_profile_ids ?? [])
    .map((profileId) => getConversationScopedExternalSourceProfile(profileId))
    .filter((profile): profile is PredictionMarketExternalSourceProfileSummary => profile != null)
    .filter((profile) =>
      !activeProfiles.some((candidate) => candidate.profile_id === profile.profile_id)
      && !configuredProfiles.some((candidate) => candidate.profile_id === profile.profile_id),
    )
  const watchlistProfiles = uniqueStrings(input.watchlist_profile_ids ?? [])
    .map((profileId) => getConversationScopedExternalSourceProfile(profileId))
    .filter((profile): profile is PredictionMarketExternalSourceProfileSummary => profile != null)
    .filter((profile) =>
      !activeProfiles.some((candidate) => candidate.profile_id === profile.profile_id)
      && !configuredProfiles.some((candidate) => candidate.profile_id === profile.profile_id)
      && !catalogProfiles.some((candidate) => candidate.profile_id === profile.profile_id),
    )

  const integration = buildPredictionMarketExternalIntegrationSummary([
    ...activeProfiles,
    ...configuredProfiles,
    ...catalogProfiles,
    ...watchlistProfiles,
  ])
  const runtime_activations = [
    ...activeProfiles.map((profile) => asActivation(profile.profile_id, 'active', profile.summary)),
    ...configuredProfiles.map((profile) => asActivation(profile.profile_id, 'configured', profile.summary)),
    ...catalogProfiles.map((profile) => asActivation(profile.profile_id, 'catalog_only', profile.summary)),
    ...watchlistProfiles.map((profile) => asActivation(profile.profile_id, 'watchlist_only', profile.summary)),
  ].filter((activation): activation is PredictionMarketExternalRuntimeActivation => activation != null)

  return {
    batch: input.batch,
    active_profile_ids: activeProfiles.map((profile) => profile.profile_id),
    configured_profile_ids: configuredProfiles.map((profile) => profile.profile_id),
    catalog_profile_ids: catalogProfiles.map((profile) => profile.profile_id),
    watchlist_profile_ids: watchlistProfiles.map((profile) => profile.profile_id),
    active_profiles: activeProfiles,
    configured_profiles: configuredProfiles,
    catalog_profiles: catalogProfiles,
    watchlist_profiles: watchlistProfiles,
    integration,
    runtime_activations,
    summary: [
      `${input.batch} runtime summary`,
      `active=${activeProfiles.length}`,
      `configured=${configuredProfiles.length}`,
      `catalog=${catalogProfiles.length}`,
      `watchlist=${watchlistProfiles.length}`,
    ].join(' | '),
  }
}

export function getPredictionMarketP0ARuntimeSummary(): PredictionMarketExternalBatchRuntimeSummary {
  const tremorConfigured = readEnvTruthy('PREDICTION_MARKETS_POLYMARKET_TREMOR_ENABLED')
    || readEnvText('PREDICTION_MARKETS_POLYMARKET_TREMOR_URL', 'PREDICTION_MARKETS_TREMOR_URL') != null
  const mcpConfigured = readEnvTruthy('PREDICTION_MARKETS_POLYMARKET_MCP_ENABLED')
    || readEnvText('PREDICTION_MARKETS_POLYMARKET_MCP_URL') != null
  const analyticsConfigured = readEnvTruthy('PREDICTION_MARKETS_POLYMARKET_MCP_ANALYTICS_ENABLED')
    || readEnvText('PREDICTION_MARKETS_POLYMARKET_MCP_ANALYTICS_URL') != null

  return buildPredictionMarketExternalBatchRuntimeSummary({
    batch: 'P0-A',
    active_profile_ids: ['polymarket-clob-client', 'polymarket-py-clob-client'],
    configured_profile_ids: [
      tremorConfigured ? 'tremor' : null,
      mcpConfigured ? 'polymarket-mcp' : null,
      analyticsConfigured ? 'polymarket-mcp-analytics' : null,
    ],
    catalog_profile_ids: [
      tremorConfigured ? null : 'tremor',
      mcpConfigured ? null : 'polymarket-mcp',
      analyticsConfigured ? null : 'polymarket-mcp-analytics',
    ],
  })
}

export function getPredictionMarketP1ARuntimeSummary(input: {
  external_profile_ids?: string[] | null
} = {}): PredictionMarketExternalBatchRuntimeSummary {
  const externalProfileIds = uniqueStrings(input.external_profile_ids ?? [])
  const activeProfileIds = externalProfileIds.filter((profileId) => {
    const profile = getConversationScopedExternalSourceProfile(profileId)
    return profile?.batch === 'P1-A'
  })

  return buildPredictionMarketExternalBatchRuntimeSummary({
    batch: 'P1-A',
    active_profile_ids: activeProfileIds,
    catalog_profile_ids: ['worldosint', 'worldmonitor-app', 'hack23-cia', 'open-civic-datasets', 'koala73-worldmonitor', 'predihermes'],
  })
}

export function getPredictionMarketP1BRuntimeSummary(input: {
  operator_thesis_present?: boolean | null
  research_pipeline_trace_present?: boolean | null
} = {}): PredictionMarketExternalBatchRuntimeSummary {
  return buildPredictionMarketExternalBatchRuntimeSummary({
    batch: 'P1-B',
    active_profile_ids: [
      input.research_pipeline_trace_present ? 'mirofish' : null,
      input.research_pipeline_trace_present ? 'mscft' : null,
    ],
    configured_profile_ids: [
      input.operator_thesis_present ? 'socialpredict' : null,
      'views-platform',
      'views-pipeline',
    ],
    catalog_profile_ids: ['mirofish', 'views-platform', 'views-pipeline', 'socialpredict', 'mscft'],
  })
}

export function getPredictionMarketP1CRuntimeSummary(input: {
  geo_context_present?: boolean | null
} = {}): PredictionMarketExternalBatchRuntimeSummary {
  return buildPredictionMarketExternalBatchRuntimeSummary({
    batch: 'P1-C',
    active_profile_ids: input.geo_context_present ? ['citypulse', 'meteocool-core', 'city-monitor'] : [],
    catalog_profile_ids: ['misp-dashboard', 'cloudtak', 'freetak', 'esri-dsa', 'citypulse', 'meteocool-core', 'city-monitor'],
  })
}

export function getPredictionMarketP2BRuntimeSummary(): PredictionMarketExternalBatchRuntimeSummary {
  return buildPredictionMarketExternalBatchRuntimeSummary({
    batch: 'P2-B',
    watchlist_profile_ids: ['sjkncs-worldmonitor', 'sjkncs-worldmonitor-enhanced', 'worldmonitor-pro'],
  })
}

export function getPredictionMarketP2CRuntimeSummary(): PredictionMarketExternalBatchRuntimeSummary {
  return buildPredictionMarketExternalBatchRuntimeSummary({
    batch: 'P2-C',
    configured_profile_ids: ['doctorfree-osint', 'awesome-intelligence'],
  })
}
