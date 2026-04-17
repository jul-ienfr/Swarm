export type PredictionMarketExternalIntegrationBatch =
  | 'P0-A'
  | 'P1-A'
  | 'P1-B'
  | 'P1-C'
  | 'P2-A'
  | 'P2-B'
  | 'P2-C'

export type PredictionMarketExternalIntegrationMode =
  | 'import'
  | 'adapt'
  | 'wrap'
  | 'pattern-only'
  | 'watchlist-diff-only'
  | 'skip'

export type PredictionMarketExternalIntegrationRole =
  | 'execution'
  | 'reference'
  | 'signal'
  | 'comparison'
  | 'watchlist'

export type PredictionMarketExternalRuntimeStatus =
  | 'runtime_optional'
  | 'read_only_sidecar'
  | 'operator_wrapper'
  | 'pattern_only'
  | 'watchlist_only'
  | 'data_asset'

export type PredictionMarketCopyPastePriority = 'high' | 'medium' | 'low'

export interface PredictionMarketExternalSourceProfile {
  profile_id: string
  family: string
  label: string
  repo_slug: string
  homepage_url: string
  source_urls: string[]
  aliases: string[]
  batch: PredictionMarketExternalIntegrationBatch
  mode: PredictionMarketExternalIntegrationMode
  role: PredictionMarketExternalIntegrationRole
  runtime_status: PredictionMarketExternalRuntimeStatus
  target_modules: string[]
  copy_paste_priority: PredictionMarketCopyPastePriority
  canonical_gate: 'execution_projection' | 'read_only' | 'watchlist'
  summary: string
}

export interface PredictionMarketExternalSourceProfileSummary {
  profile_id: string
  family: string
  label: string
  repo_slug: string
  homepage_url: string
  batch: PredictionMarketExternalIntegrationBatch
  mode: PredictionMarketExternalIntegrationMode
  role: PredictionMarketExternalIntegrationRole
  runtime_status: PredictionMarketExternalRuntimeStatus
  copy_paste_priority: PredictionMarketCopyPastePriority
  canonical_gate: PredictionMarketExternalSourceProfile['canonical_gate']
  target_modules: string[]
  summary: string
}

export interface PredictionMarketExternalIntegrationSummary {
  total_profiles: number
  profile_ids: string[]
  families: string[]
  repo_slugs: string[]
  batches: PredictionMarketExternalIntegrationBatch[]
  modes: PredictionMarketExternalIntegrationMode[]
  roles: PredictionMarketExternalIntegrationRole[]
  runtime_statuses: PredictionMarketExternalRuntimeStatus[]
  read_only_profile_ids: string[]
  pattern_only_profile_ids: string[]
  watchlist_profile_ids: string[]
  data_asset_profile_ids: string[]
  copy_paste_ready_profile_ids: string[]
  summary: string
}

const CONVERSATION_SCOPED_EXTERNAL_SOURCE_PROFILES: readonly PredictionMarketExternalSourceProfile[] = [
  {
    profile_id: 'polymarket-clob-client',
    family: 'polymarket',
    label: 'Polymarket/clob-client',
    repo_slug: 'Polymarket/clob-client',
    homepage_url: 'https://github.com/Polymarket/clob-client',
    source_urls: ['https://github.com/Polymarket/clob-client'],
    aliases: ['polymarket clob client', 'clob-client', 'polymarket typescript client'],
    batch: 'P0-A',
    mode: 'adapt',
    role: 'execution',
    runtime_status: 'runtime_optional',
    target_modules: ['polymarket.ts', 'venue-ops.ts', 'cross-venue.ts', 'execution-preview.ts'],
    copy_paste_priority: 'high',
    canonical_gate: 'execution_projection',
    summary: 'Official TypeScript CLOB client reused as venue adapter lineage and orderbook/readback reference.',
  },
  {
    profile_id: 'polymarket-py-clob-client',
    family: 'polymarket',
    label: 'Polymarket/py-clob-client',
    repo_slug: 'Polymarket/py-clob-client',
    homepage_url: 'https://github.com/Polymarket/py-clob-client',
    source_urls: ['https://github.com/Polymarket/py-clob-client'],
    aliases: ['polymarket py clob client', 'py-clob-client', 'polymarket python client'],
    batch: 'P0-A',
    mode: 'adapt',
    role: 'execution',
    runtime_status: 'runtime_optional',
    target_modules: ['polymarket.ts', 'live-execution-bridge.ts', 'execution-pathways.ts'],
    copy_paste_priority: 'high',
    canonical_gate: 'execution_projection',
    summary: 'Official Python client kept as transport and paper/shadow/live parity reference.',
  },
  {
    profile_id: 'tremor',
    family: 'polymarket-monitoring',
    label: 'sculptdotfun/tremor',
    repo_slug: 'sculptdotfun/tremor',
    homepage_url: 'https://github.com/sculptdotfun/tremor',
    source_urls: ['https://github.com/sculptdotfun/tremor'],
    aliases: ['tremor polymarket', 'sculptdotfun tremor', 'tremor'],
    batch: 'P0-A',
    mode: 'wrap',
    role: 'signal',
    runtime_status: 'read_only_sidecar',
    target_modules: ['dashboard-events.ts', 'dashboard-read-models.ts', 'source-audit.ts'],
    copy_paste_priority: 'high',
    canonical_gate: 'read_only',
    summary: 'Real-time Polymarket movement monitor kept as a read-only alerting sidecar.',
  },
  {
    profile_id: 'polymarket-mcp',
    family: 'polymarket-operator',
    label: 'pab1it0/polymarket-mcp',
    repo_slug: 'pab1it0/polymarket-mcp',
    homepage_url: 'https://github.com/pab1it0/polymarket-mcp',
    source_urls: ['https://github.com/pab1it0/polymarket-mcp'],
    aliases: ['polymarket mcp', 'pab1it0 polymarket mcp'],
    batch: 'P0-A',
    mode: 'wrap',
    role: 'watchlist',
    runtime_status: 'operator_wrapper',
    target_modules: ['dashboard-control.ts', 'source-audit.ts'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Operator wrapper for market, event, orderbook, trades, and history inspection.',
  },
  {
    profile_id: 'polymarket-mcp-analytics',
    family: 'polymarket-operator',
    label: 'guangxiangdebizi/PolyMarket-MCP',
    repo_slug: 'guangxiangdebizi/PolyMarket-MCP',
    homepage_url: 'https://github.com/guangxiangdebizi/PolyMarket-MCP',
    source_urls: ['https://github.com/guangxiangdebizi/PolyMarket-MCP'],
    aliases: ['polymarket mcp analytics', 'polymarket mcp enhanced', 'guangxiangdebizi polymarket mcp'],
    batch: 'P0-A',
    mode: 'wrap',
    role: 'watchlist',
    runtime_status: 'operator_wrapper',
    target_modules: ['dashboard-control.ts', 'source-audit.ts'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Operator wrapper for positions, holders, and analytics, kept outside the core runtime.',
  },
  {
    profile_id: 'worldosint',
    family: 'osint',
    label: 'WorldOSINT',
    repo_slug: 'WorldOSINT',
    homepage_url: 'https://worldosint.com',
    source_urls: ['https://worldosint.com'],
    aliases: ['worldosint'],
    batch: 'P1-A',
    mode: 'wrap',
    role: 'signal',
    runtime_status: 'read_only_sidecar',
    target_modules: ['research.ts', 'research-pipeline-trace.ts', 'source-audit.ts', 'world-state-spine.ts'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'OSINT discovery feed used to improve recall, freshness, and date-confidence in research.',
  },
  {
    profile_id: 'worldmonitor-app',
    family: 'worldmonitor',
    label: 'worldmonitor.app',
    repo_slug: 'worldmonitor.app',
    homepage_url: 'https://www.worldmonitor.app',
    source_urls: ['https://www.worldmonitor.app', 'https://worldmonitor.app'],
    aliases: ['worldmonitor', 'world monitor', 'worldmonitor app'],
    batch: 'P1-A',
    mode: 'wrap',
    role: 'signal',
    runtime_status: 'read_only_sidecar',
    target_modules: ['research.ts', 'research-compaction.ts', 'source-audit.ts'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Discovery and convergence layer for multi-source situational awareness, never a final proof source.',
  },
  {
    profile_id: 'hack23-cia',
    family: 'osint',
    label: 'Hack23/cia',
    repo_slug: 'Hack23/cia',
    homepage_url: 'https://github.com/Hack23/cia',
    source_urls: ['https://github.com/Hack23/cia'],
    aliases: ['hack23 cia', 'cia dashboard', 'hack23/cia'],
    batch: 'P1-A',
    mode: 'wrap',
    role: 'reference',
    runtime_status: 'read_only_sidecar',
    target_modules: ['research.ts', 'research-pipeline-trace.ts', 'dashboard-read-models.ts'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Political intelligence dashboard used as contextual enrichment for civic and geopolitical markets.',
  },
  {
    profile_id: 'open-civic-datasets',
    family: 'civic-datasets',
    label: 'codeforamerica/open-civic-datasets',
    repo_slug: 'codeforamerica/open-civic-datasets',
    homepage_url: 'https://github.com/codeforamerica/open-civic-datasets',
    source_urls: ['https://github.com/codeforamerica/open-civic-datasets'],
    aliases: ['open civic datasets', 'codeforamerica open civic datasets'],
    batch: 'P1-A',
    mode: 'wrap',
    role: 'reference',
    runtime_status: 'read_only_sidecar',
    target_modules: ['research.ts', 'world-state-spine.ts', 'source-audit.ts'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Verified civic dataset directory used as a secondary evidence layer.',
  },
  {
    profile_id: 'koala73-worldmonitor',
    family: 'worldmonitor',
    label: 'koala73/worldmonitor',
    repo_slug: 'koala73/worldmonitor',
    homepage_url: 'https://github.com/koala73/worldmonitor',
    source_urls: ['https://github.com/koala73/worldmonitor'],
    aliases: ['koala73 worldmonitor', 'koala73/worldmonitor'],
    batch: 'P1-A',
    mode: 'pattern-only',
    role: 'reference',
    runtime_status: 'pattern_only',
    target_modules: ['research-compaction.ts', 'dashboard-read-models.ts', 'dashboard-events.ts'],
    copy_paste_priority: 'high',
    canonical_gate: 'read_only',
    summary: 'Baseline worldmonitor upstream used for clustering, freshness, alerting, and operator UX patterns.',
  },
  {
    profile_id: 'predihermes',
    family: 'research-orchestration',
    label: 'nativ3ai/hermes-geopolitical-market-sim',
    repo_slug: 'nativ3ai/hermes-geopolitical-market-sim',
    homepage_url: 'https://github.com/nativ3ai/hermes-geopolitical-market-sim',
    source_urls: ['https://github.com/nativ3ai/hermes-geopolitical-market-sim'],
    aliases: ['predihermes', 'hermes geopolitical market sim', 'hermes-geopolitical-market-sim'],
    batch: 'P1-A',
    mode: 'pattern-only',
    role: 'signal',
    runtime_status: 'pattern_only',
    target_modules: ['research.ts', 'research-pipeline-trace.ts', 'operator_thesis'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Topic tracking and seed-packet orchestration pattern, not a trading core.',
  },
  {
    profile_id: 'mirofish',
    family: 'miro',
    label: 'MiroFish',
    repo_slug: 'MiroFish',
    homepage_url: 'https://github.com/nativ3ai',
    source_urls: ['https://github.com/nativ3ai'],
    aliases: ['mirofish'],
    batch: 'P1-B',
    mode: 'wrap',
    role: 'comparison',
    runtime_status: 'read_only_sidecar',
    target_modules: ['research.ts', 'research-pipeline-trace.ts', 'execution-pathways.ts'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Dissent and counterfactual sidecar used to pressure-test theses.',
  },
  {
    profile_id: 'views-platform',
    family: 'forecast-governance',
    label: 'views-platform',
    repo_slug: 'views-platform',
    homepage_url: 'https://github.com/views-platform',
    source_urls: ['https://github.com/views-platform'],
    aliases: ['views platform', 'views-platform'],
    batch: 'P1-B',
    mode: 'adapt',
    role: 'comparison',
    runtime_status: 'runtime_optional',
    target_modules: ['calibration.ts', 'walk-forward.ts', 'benchmark.ts', 'autopilot-cycle.ts'],
    copy_paste_priority: 'high',
    canonical_gate: 'execution_projection',
    summary: 'Forecast governance and evaluation patterns reused for benchmark and walk-forward discipline.',
  },
  {
    profile_id: 'views-pipeline',
    family: 'forecast-governance',
    label: 'prio-data/views_pipeline',
    repo_slug: 'prio-data/views_pipeline',
    homepage_url: 'https://github.com/prio-data/views_pipeline',
    source_urls: ['https://github.com/prio-data/views_pipeline'],
    aliases: ['views pipeline', 'views_pipeline', 'prio-data views pipeline'],
    batch: 'P1-B',
    mode: 'adapt',
    role: 'comparison',
    runtime_status: 'runtime_optional',
    target_modules: ['calibration.ts', 'walk-forward.ts', 'benchmark.ts', 'autopilot-cycle.ts'],
    copy_paste_priority: 'high',
    canonical_gate: 'execution_projection',
    summary: 'Concrete VIEWS pipeline used as evaluation-harness lineage for forecasting discipline.',
  },
  {
    profile_id: 'socialpredict',
    family: 'market-design',
    label: 'openpredictionmarkets/socialpredict',
    repo_slug: 'openpredictionmarkets/socialpredict',
    homepage_url: 'https://github.com/openpredictionmarkets/socialpredict',
    source_urls: ['https://github.com/openpredictionmarkets/socialpredict'],
    aliases: ['socialpredict', 'openpredictionmarkets socialpredict'],
    batch: 'P1-B',
    mode: 'pattern-only',
    role: 'comparison',
    runtime_status: 'pattern_only',
    target_modules: ['contract-examples.ts', 'dashboard-models.ts', 'operator-analytics.ts'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Prediction-market product and economics pattern library for operator surfaces and contract structure.',
  },
  {
    profile_id: 'mscft',
    family: 'forecast-governance',
    label: 'captbullett65/MSCFT',
    repo_slug: 'captbullett65/MSCFT',
    homepage_url: 'https://github.com/captbullett65/MSCFT',
    source_urls: ['https://github.com/captbullett65/MSCFT'],
    aliases: ['mscft', 'captbullett65 mscft'],
    batch: 'P1-B',
    mode: 'pattern-only',
    role: 'comparison',
    runtime_status: 'pattern_only',
    target_modules: ['research-pipeline-trace.ts', 'ticket-payload.ts', 'operator_thesis'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Forecast-thesis hygiene and argument audit pattern library.',
  },
  {
    profile_id: 'misp-dashboard',
    family: 'cop-dashboard',
    label: 'MISP/misp-dashboard',
    repo_slug: 'MISP/misp-dashboard',
    homepage_url: 'https://github.com/MISP/misp-dashboard',
    source_urls: ['https://github.com/MISP/misp-dashboard'],
    aliases: ['misp dashboard', 'misp/misp-dashboard'],
    batch: 'P1-C',
    mode: 'pattern-only',
    role: 'signal',
    runtime_status: 'pattern_only',
    target_modules: ['dashboard-models.ts', 'dashboard-read-models.ts', 'dashboard-events.ts'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Dense live-event dashboard pattern for read-only operator monitoring.',
  },
  {
    profile_id: 'cloudtak',
    family: 'cop-dashboard',
    label: 'dfpc-coe/CloudTAK',
    repo_slug: 'dfpc-coe/CloudTAK',
    homepage_url: 'https://github.com/dfpc-coe/CloudTAK',
    source_urls: ['https://github.com/dfpc-coe/CloudTAK'],
    aliases: ['cloudtak', 'dfpc-coe cloudtak'],
    batch: 'P1-C',
    mode: 'pattern-only',
    role: 'signal',
    runtime_status: 'pattern_only',
    target_modules: ['dashboard-read-models.ts', 'world-state-spine.ts', 'dashboard-events.ts'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Map-first common operational picture patterns reused in read-only world-state surfaces.',
  },
  {
    profile_id: 'freetak',
    family: 'cop-dashboard',
    label: 'FreeTAKTeam/FreeTakServer',
    repo_slug: 'FreeTAKTeam/FreeTakServer',
    homepage_url: 'https://github.com/FreeTAKTeam/FreeTakServer',
    source_urls: ['https://github.com/FreeTAKTeam/FreeTakServer'],
    aliases: ['freetak', 'freetakserver', 'FreeTakServer'],
    batch: 'P1-C',
    mode: 'pattern-only',
    role: 'signal',
    runtime_status: 'pattern_only',
    target_modules: ['dashboard-read-models.ts', 'world-state-spine.ts', 'dashboard-events.ts'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Event diffusion and geo-overlay patterns reused only in read models.',
  },
  {
    profile_id: 'esri-dsa',
    family: 'cop-dashboard',
    label: 'Esri/dynamic-situational-awareness-qt',
    repo_slug: 'Esri/dynamic-situational-awareness-qt',
    homepage_url: 'https://github.com/Esri/dynamic-situational-awareness-qt',
    source_urls: ['https://github.com/Esri/dynamic-situational-awareness-qt'],
    aliases: ['esri dynamic situational awareness', 'dynamic-situational-awareness-qt'],
    batch: 'P1-C',
    mode: 'pattern-only',
    role: 'signal',
    runtime_status: 'pattern_only',
    target_modules: ['dashboard-models.ts', 'world-state-spine.ts', 'dashboard-read-models.ts'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Workflow patterns for map layers, overlays, and readable alert stacks.',
  },
  {
    profile_id: 'citypulse',
    family: 'city-dashboard',
    label: 'CityPulse/CityPulse-City-Dashboard',
    repo_slug: 'CityPulse/CityPulse-City-Dashboard',
    homepage_url: 'https://github.com/CityPulse/CityPulse-City-Dashboard',
    source_urls: ['https://github.com/CityPulse/CityPulse-City-Dashboard'],
    aliases: ['citypulse', 'citypulse city dashboard'],
    batch: 'P1-C',
    mode: 'pattern-only',
    role: 'signal',
    runtime_status: 'pattern_only',
    target_modules: ['dashboard-read-models.ts', 'dashboard-events.ts', 'world-state.ts'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Real-time plus historical city dashboard pattern reused for local triage views.',
  },
  {
    profile_id: 'meteocool-core',
    family: 'weather-cop',
    label: 'meteocool/core',
    repo_slug: 'meteocool/core',
    homepage_url: 'https://github.com/meteocool/core',
    source_urls: ['https://github.com/meteocool/core'],
    aliases: ['meteocool', 'meteocool core'],
    batch: 'P1-C',
    mode: 'pattern-only',
    role: 'signal',
    runtime_status: 'pattern_only',
    target_modules: ['dashboard-read-models.ts', 'world-state.ts', 'source-audit.ts'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Weather and radar overlay pattern reused for read-only alert presentation.',
  },
  {
    profile_id: 'city-monitor',
    family: 'city-dashboard',
    label: 'OdinMB/city-monitor',
    repo_slug: 'OdinMB/city-monitor',
    homepage_url: 'https://github.com/OdinMB/city-monitor',
    source_urls: ['https://github.com/OdinMB/city-monitor'],
    aliases: ['city-monitor', 'odinmb city-monitor', 'odin city monitor'],
    batch: 'P1-C',
    mode: 'pattern-only',
    role: 'signal',
    runtime_status: 'pattern_only',
    target_modules: ['dashboard-read-models.ts', 'world-state.ts', 'source-audit.ts'],
    copy_paste_priority: 'medium',
    canonical_gate: 'read_only',
    summary: 'Hyper-local city dashboard pattern used for compact, read-only situation views.',
  },
  {
    profile_id: 'geomapdata-cn',
    family: 'geo-datasets',
    label: 'lyhmyd1211/GeoMapData_CN',
    repo_slug: 'lyhmyd1211/GeoMapData_CN',
    homepage_url: 'https://github.com/lyhmyd1211/GeoMapData_CN',
    source_urls: ['https://github.com/lyhmyd1211/GeoMapData_CN'],
    aliases: ['geomapdata cn', 'GeoMapData_CN', 'lyhmyd1211 geomapdata cn'],
    batch: 'P2-A',
    mode: 'import',
    role: 'reference',
    runtime_status: 'data_asset',
    target_modules: ['world-state.ts', 'world-state-spine.ts', 'source-audit.ts'],
    copy_paste_priority: 'high',
    canonical_gate: 'read_only',
    summary: 'Copied geo dataset used for China region, centroid, and adcode enrichment only.',
  },
  {
    profile_id: 'sjkncs-worldmonitor',
    family: 'worldmonitor',
    label: 'sjkncs/worldmonitor',
    repo_slug: 'sjkncs/worldmonitor',
    homepage_url: 'https://github.com/sjkncs/worldmonitor',
    source_urls: ['https://github.com/sjkncs/worldmonitor'],
    aliases: ['sjkncs worldmonitor', 'sjkncs/worldmonitor'],
    batch: 'P2-B',
    mode: 'watchlist-diff-only',
    role: 'watchlist',
    runtime_status: 'watchlist_only',
    target_modules: ['research.ts'],
    copy_paste_priority: 'low',
    canonical_gate: 'watchlist',
    summary: 'Fork tracked only for proven diff versus koala73/worldmonitor.',
  },
  {
    profile_id: 'sjkncs-worldmonitor-enhanced',
    family: 'worldmonitor',
    label: 'sjkncs/worldmonitor-enhanced',
    repo_slug: 'sjkncs/worldmonitor-enhanced',
    homepage_url: 'https://github.com/sjkncs/worldmonitor-enhanced',
    source_urls: ['https://github.com/sjkncs/worldmonitor-enhanced'],
    aliases: ['sjkncs worldmonitor enhanced', 'worldmonitor-enhanced'],
    batch: 'P2-B',
    mode: 'watchlist-diff-only',
    role: 'watchlist',
    runtime_status: 'watchlist_only',
    target_modules: ['research.ts'],
    copy_paste_priority: 'low',
    canonical_gate: 'watchlist',
    summary: 'Fork tracked only after local diff audit and benchmark validation.',
  },
  {
    profile_id: 'worldmonitor-pro',
    family: 'worldmonitor',
    label: 'worldmonitor/worldmonitor',
    repo_slug: 'worldmonitor/worldmonitor',
    homepage_url: 'https://github.com/worldmonitor/worldmonitor',
    source_urls: ['https://github.com/worldmonitor/worldmonitor'],
    aliases: ['worldmonitor pro', 'worldmonitor/worldmonitor'],
    batch: 'P2-B',
    mode: 'watchlist-diff-only',
    role: 'watchlist',
    runtime_status: 'watchlist_only',
    target_modules: ['research.ts'],
    copy_paste_priority: 'low',
    canonical_gate: 'watchlist',
    summary: 'Low-density repackage tracked only for potential diff extraction versus upstream.',
  },
  {
    profile_id: 'doctorfree-osint',
    family: 'source-discovery',
    label: 'doctorfree/osint',
    repo_slug: 'doctorfree/osint',
    homepage_url: 'https://github.com/doctorfree/osint',
    source_urls: ['https://github.com/doctorfree/osint'],
    aliases: ['doctorfree osint', 'doctorfree/osint'],
    batch: 'P2-C',
    mode: 'wrap',
    role: 'watchlist',
    runtime_status: 'operator_wrapper',
    target_modules: ['source-audit.ts'],
    copy_paste_priority: 'low',
    canonical_gate: 'read_only',
    summary: 'Meta-source catalog used only for source discovery backlog expansion.',
  },
  {
    profile_id: 'awesome-intelligence',
    family: 'source-discovery',
    label: 'ARPSyndicate/awesome-intelligence',
    repo_slug: 'ARPSyndicate/awesome-intelligence',
    homepage_url: 'https://github.com/ARPSyndicate/awesome-intelligence',
    source_urls: ['https://github.com/ARPSyndicate/awesome-intelligence'],
    aliases: ['awesome intelligence', 'ARPSyndicate awesome intelligence'],
    batch: 'P2-C',
    mode: 'wrap',
    role: 'watchlist',
    runtime_status: 'operator_wrapper',
    target_modules: ['source-audit.ts'],
    copy_paste_priority: 'low',
    canonical_gate: 'read_only',
    summary: 'Meta-source catalog used only to qualify future candidates, never as runtime evidence.',
  },
] as const

function normalizeForMatch(value: string | null | undefined): string {
  return String(value ?? '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

function uniqueStrings<T extends string>(values: T[]): T[] {
  const seen = new Set<string>()
  const out: T[] = []
  for (const value of values) {
    if (!value || seen.has(value)) continue
    seen.add(value)
    out.push(value)
  }
  return out
}

function summarizeProfiles(profiles: readonly PredictionMarketExternalSourceProfileSummary[]): string {
  if (profiles.length === 0) {
    return 'No conversation-scoped external integration profile is currently active.'
  }
  const copyPasteReady = profiles.filter((profile) =>
    profile.mode === 'import' || profile.mode === 'adapt' || profile.mode === 'wrap'
  ).length
  const readOnly = profiles.filter((profile) =>
    profile.runtime_status === 'read_only_sidecar' || profile.runtime_status === 'operator_wrapper'
  ).length
  const patternOnly = profiles.filter((profile) => profile.runtime_status === 'pattern_only').length
  const watchlist = profiles.filter((profile) => profile.runtime_status === 'watchlist_only').length
  const dataAssets = profiles.filter((profile) => profile.runtime_status === 'data_asset').length

  return `${profiles.length} conversation-scoped profile(s); `
    + `${copyPasteReady} copy-paste-ready, `
    + `${readOnly} read-only wrappers, `
    + `${patternOnly} pattern-only, `
    + `${watchlist} watchlist-only, `
    + `${dataAssets} data assets.`
}

export function toPredictionMarketExternalSourceProfileSummary(
  profile: PredictionMarketExternalSourceProfile,
): PredictionMarketExternalSourceProfileSummary {
  return {
    profile_id: profile.profile_id,
    family: profile.family,
    label: profile.label,
    repo_slug: profile.repo_slug,
    homepage_url: profile.homepage_url,
    batch: profile.batch,
    mode: profile.mode,
    role: profile.role,
    runtime_status: profile.runtime_status,
    copy_paste_priority: profile.copy_paste_priority,
    canonical_gate: profile.canonical_gate,
    target_modules: [...profile.target_modules],
    summary: profile.summary,
  }
}

export function listConversationScopedExternalSourceProfiles(): PredictionMarketExternalSourceProfileSummary[] {
  return CONVERSATION_SCOPED_EXTERNAL_SOURCE_PROFILES.map((profile) =>
    toPredictionMarketExternalSourceProfileSummary(profile),
  )
}

export function getConversationScopedExternalSourceProfile(
  profileId: string | null | undefined,
): PredictionMarketExternalSourceProfileSummary | null {
  const normalized = normalizeForMatch(profileId)
  const profile = CONVERSATION_SCOPED_EXTERNAL_SOURCE_PROFILES.find((entry) =>
    normalizeForMatch(entry.profile_id) === normalized,
  )
  return profile ? toPredictionMarketExternalSourceProfileSummary(profile) : null
}

export function buildPredictionMarketExternalIntegrationSummary(
  profiles: readonly PredictionMarketExternalSourceProfileSummary[],
): PredictionMarketExternalIntegrationSummary {
  const uniqueProfiles = uniqueStrings(
    profiles
      .map((profile) => JSON.stringify(profile))
      .filter((value) => value.length > 0),
  ).map((value) => JSON.parse(value) as PredictionMarketExternalSourceProfileSummary)

  return {
    total_profiles: uniqueProfiles.length,
    profile_ids: uniqueStrings(uniqueProfiles.map((profile) => profile.profile_id)),
    families: uniqueStrings(uniqueProfiles.map((profile) => profile.family)),
    repo_slugs: uniqueStrings(uniqueProfiles.map((profile) => profile.repo_slug)),
    batches: uniqueStrings(uniqueProfiles.map((profile) => profile.batch)),
    modes: uniqueStrings(uniqueProfiles.map((profile) => profile.mode)),
    roles: uniqueStrings(uniqueProfiles.map((profile) => profile.role)),
    runtime_statuses: uniqueStrings(uniqueProfiles.map((profile) => profile.runtime_status)),
    read_only_profile_ids: uniqueStrings(
      uniqueProfiles
        .filter((profile) => profile.runtime_status === 'read_only_sidecar' || profile.runtime_status === 'operator_wrapper')
        .map((profile) => profile.profile_id),
    ),
    pattern_only_profile_ids: uniqueStrings(
      uniqueProfiles
        .filter((profile) => profile.runtime_status === 'pattern_only')
        .map((profile) => profile.profile_id),
    ),
    watchlist_profile_ids: uniqueStrings(
      uniqueProfiles
        .filter((profile) => profile.runtime_status === 'watchlist_only')
        .map((profile) => profile.profile_id),
    ),
    data_asset_profile_ids: uniqueStrings(
      uniqueProfiles
        .filter((profile) => profile.runtime_status === 'data_asset')
        .map((profile) => profile.profile_id),
    ),
    copy_paste_ready_profile_ids: uniqueStrings(
      uniqueProfiles
        .filter((profile) => profile.mode === 'import' || profile.mode === 'adapt' || profile.mode === 'wrap')
        .map((profile) => profile.profile_id),
    ),
    summary: summarizeProfiles(uniqueProfiles),
  }
}

export function getConversationScopedExternalCatalogSummary(): PredictionMarketExternalIntegrationSummary {
  return buildPredictionMarketExternalIntegrationSummary(listConversationScopedExternalSourceProfiles())
}

export function matchConversationScopedExternalSourceProfiles(input: {
  sourceId?: string | null
  sourceName?: string | null
  title?: string | null
  sourceUrl?: string | null
  sourceRefs?: string[] | null
  notes?: string[] | null
}): PredictionMarketExternalSourceProfileSummary[] {
  const normalizedUrl = String(input.sourceUrl ?? '').toLowerCase().trim()
  const normalizedText = normalizeForMatch([
    input.sourceId,
    input.sourceName,
    input.title,
    ...(input.sourceRefs ?? []),
    ...(input.notes ?? []),
  ].join(' '))

  const matches = CONVERSATION_SCOPED_EXTERNAL_SOURCE_PROFILES
    .map((profile) => {
      let score = 0

      if (normalizedUrl.length > 0) {
        for (const sourceUrl of profile.source_urls) {
          const candidate = sourceUrl.toLowerCase()
          if (normalizedUrl === candidate) score += 120
          else if (normalizedUrl.includes(candidate) || candidate.includes(normalizedUrl)) score += 100
        }
        const repoSlug = profile.repo_slug.toLowerCase()
        if (normalizedUrl.includes(repoSlug)) score += 110
      }

      if (normalizedText.length > 0) {
        const repoSlugMatch = normalizeForMatch(profile.repo_slug)
        if (repoSlugMatch.length > 0 && normalizedText.includes(repoSlugMatch)) score += 90
        const labelMatch = normalizeForMatch(profile.label)
        if (labelMatch.length > 0 && normalizedText.includes(labelMatch)) score += 70
        for (const alias of profile.aliases) {
          const normalizedAlias = normalizeForMatch(alias)
          if (normalizedAlias.length > 0 && normalizedText.includes(normalizedAlias)) {
            score += 60
          }
        }
      }

      return {
        profile,
        score,
      }
    })
    .filter((match) => match.score > 0)
    .sort((left, right) => {
      if (right.score !== left.score) return right.score - left.score
      if (left.profile.copy_paste_priority !== right.profile.copy_paste_priority) {
        const order = { high: 0, medium: 1, low: 2 }
        return order[left.profile.copy_paste_priority] - order[right.profile.copy_paste_priority]
      }
      return left.profile.label.localeCompare(right.profile.label)
    })

  return uniqueStrings(matches.map((match) => match.profile.profile_id))
    .map((profileId) => {
      const profile = CONVERSATION_SCOPED_EXTERNAL_SOURCE_PROFILES.find((entry) => entry.profile_id === profileId)
      return profile ? toPredictionMarketExternalSourceProfileSummary(profile) : null
    })
    .filter((profile): profile is PredictionMarketExternalSourceProfileSummary => profile != null)
}
