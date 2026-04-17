import {
  getPredictionMarketP2BRuntimeSummary,
  getPredictionMarketP2CRuntimeSummary,
} from './external-runtime'

export type PredictionMarketWatchlistDiffAuditEntry = {
  profile_id: string
  upstream_profile_id: string
  mode: 'watchlist-diff-only'
  diff_ready: boolean
  bench_ready: boolean
  extraction_allowed: false
  summary: string
}

export type PredictionMarketSourceDiscoveryQualification = {
  profile_id: string
  runtime_dependency: false
  qualification_status: 'backlog_only' | 'qualified_read_only'
  summary: string
}

export type PredictionMarketWatchlistAudit = {
  diff_only_entries: PredictionMarketWatchlistDiffAuditEntry[]
  discovery_backlog: PredictionMarketSourceDiscoveryQualification[]
  summary: string
}

export function buildPredictionMarketWatchlistAudit(): PredictionMarketWatchlistAudit {
  const p2b = getPredictionMarketP2BRuntimeSummary()
  const p2c = getPredictionMarketP2CRuntimeSummary()

  return {
    diff_only_entries: p2b.watchlist_profile_ids.map((profileId) => ({
      profile_id: profileId,
      upstream_profile_id: 'koala73-worldmonitor',
      mode: 'watchlist-diff-only',
      diff_ready: false,
      bench_ready: false,
      extraction_allowed: false,
      summary: `${profileId} remains blocked on documented diff and local bench versus koala73/worldmonitor.`,
    })),
    discovery_backlog: p2c.configured_profile_ids.map((profileId) => ({
      profile_id: profileId,
      runtime_dependency: false,
      qualification_status: 'backlog_only',
      summary: `${profileId} remains a source-discovery backlog entry with no runtime dependency.`,
    })),
    summary: `${p2b.summary} ${p2c.summary}`,
  }
}
