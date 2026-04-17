import { describe, expect, it } from 'vitest'
import { buildPredictionMarketSourceAudit } from '@/lib/prediction-markets/source-audit'

describe('prediction market source audit', () => {
  const sources = [
    {
      source_id: 'source-official-1',
      kind: 'official_docs',
      title: 'Official execution policy',
      url: 'https://example.com/docs/execution-policy',
      captured_at: '2026-04-09T09:00:00.000Z',
      trust: 0.96,
      freshness: 0.92,
      evidence_strength: 1,
      notes: ['Canonical policy reference'],
      source_refs: ['docs:execution-policy'],
    },
    {
      source_id: 'source-market-1',
      kind: 'news',
      title: 'WorldMonitor city update',
      url: 'https://www.worldmonitor.app',
      captured_at: '2026-04-09T09:10:00.000Z',
      trust: 0.66,
      freshness: 0.58,
      evidence_strength: 0.6,
      notes: ['Thin book but usable'],
      source_refs: ['geo:110000', 'book:snapshot'],
    },
    {
      source_id: 'source-community-1',
      kind: 'community_repo',
      title: 'Community backtest note',
      captured_at: '2026-04-09T09:20:00.000Z',
      trust: 0.28,
      freshness: 0.32,
      evidence_strength: 0.3,
      notes: ['No public URL attached'],
      source_refs: ['repo:backtest-note'],
    },
  ]

  it('sorts sources stably, fingerprints the audit, and classifies coverage', () => {
    const audit = buildPredictionMarketSourceAudit({
      market_id: 'market-audit-1',
      as_of: '2026-04-09T10:00:00.000Z',
      sources,
      primary_kinds: ['official_docs'],
      minimum_primary_score: 0.9,
    })

    const auditAgain = buildPredictionMarketSourceAudit({
      market_id: 'market-audit-1',
      as_of: '2026-04-09T10:00:00.000Z',
      sources: [...sources].reverse(),
      primary_kinds: ['official_docs'],
      minimum_primary_score: 0.9,
    })

    expect(audit.audit_id).toBe(auditAgain.audit_id)
    expect(audit.summary).toContain('3 sources audited')
    expect(audit.summary).toContain('1 primary')
    expect(audit.summary).toContain('1 supporting')
    expect(audit.summary).toContain('1 weak')
    expect(audit.entries[0].source_id).toBe('source-official-1')
    expect(audit.entries[0].status).toBe('primary')
    expect(audit.primary_sources.map((entry) => entry.source_id)).toEqual(['source-official-1'])
    expect(audit.supporting_sources.map((entry) => entry.source_id)).toEqual(['source-market-1'])
    expect(audit.weak_sources.map((entry) => entry.source_id)).toEqual(['source-community-1'])
    expect(audit.supporting_sources[0]?.external_profiles.map((profile) => profile.profile_id)).toContain('worldmonitor-app')
    expect(audit.missing_url_sources).toEqual(['source-community-1'])
    expect(audit.geo_refs).toEqual(['110000'])
    expect(audit.external_integration.profile_ids).toContain('worldmonitor-app')
    expect(audit.watchlist_audit?.diff_only_entries).toHaveLength(3)
    expect(audit.watchlist_audit?.discovery_backlog).toHaveLength(2)
    expect(audit.source_refs).toEqual(
      expect.arrayContaining(['source-official-1', 'source-market-1', 'source-community-1']),
    )
    expect(audit.average_score).toBeGreaterThan(0.6)
    expect(audit.coverage_score).toBeGreaterThan(0.2)
    expect(JSON.parse(JSON.stringify(audit))).toMatchObject({
      audit_id: audit.audit_id,
      market_id: 'market-audit-1',
    })
  })
})
