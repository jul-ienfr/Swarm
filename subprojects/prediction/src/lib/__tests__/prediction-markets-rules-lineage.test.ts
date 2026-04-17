import { describe, expect, it } from 'vitest'
import { buildPredictionMarketRulesLineage } from '@/lib/prediction-markets/rules-lineage'

describe('prediction market rules lineage', () => {
  const clauses = [
    {
      clause_id: 'clause-yes-floor',
      rule_id: 'rule-price-floor',
      title: 'Price floor',
      text: 'Do not bet when spread exceeds the protected band.',
      source_refs: ['docs:execution-policy', 'log:approval'],
      status: 'active' as const,
      introduced_at: '2026-04-09T06:00:00.000Z',
    },
    {
      clause_id: 'clause-escalation',
      rule_id: 'rule-operator-approval',
      title: 'Operator escalation',
      text: 'Escalate if the approval path is not cleanly available.',
      source_refs: ['docs:approval-flow'],
      status: 'conflicted' as const,
      introduced_at: '2026-04-09T06:10:00.000Z',
    },
    {
      clause_id: 'clause-old-support',
      rule_id: 'rule-price-floor',
      title: 'Legacy support',
      text: 'Older version of the floor logic.',
      source_refs: ['docs:legacy'],
      status: 'superseded' as const,
      superseded_by: ['clause-yes-floor'],
    },
    {
      clause_id: 'clause-draft-signal',
      rule_id: 'rule-catalyst-filter',
      title: 'Draft catalyst filter',
      text: 'Use catalyst pressure to filter weak live signals.',
      source_refs: ['notes:catalyst-filter'],
      status: 'draft' as const,
    },
  ]

  it('builds a canonical lineage with stable fingerprints and rule summaries', () => {
    const lineage = buildPredictionMarketRulesLineage({
      market_id: 'market-lineage-1',
      as_of: '2026-04-09T10:30:00.000Z',
      rule_set_name: 'live-approval-stack',
      clauses,
    })

    const lineageAgain = buildPredictionMarketRulesLineage({
      market_id: 'market-lineage-1',
      as_of: '2026-04-09T10:30:00.000Z',
      rule_set_name: 'live-approval-stack',
      clauses: [...clauses].reverse(),
    })

    expect(lineage.lineage_id).toBe(lineageAgain.lineage_id)
    expect(lineage.summary).toContain('4 clauses across 3 rules')
    expect(lineage.summary).toContain('1 active')
    expect(lineage.summary).toContain('1 conflicted')
    expect(lineage.summary).toContain('1 superseded')
    expect(lineage.active_clause_ids).toEqual(['clause-yes-floor'])
    expect(lineage.conflicted_clause_ids).toEqual(['clause-escalation'])
    expect(lineage.superseded_clause_ids).toEqual(['clause-old-support'])
    expect(lineage.canonical_rule_ids).toEqual([
      'rule-catalyst-filter',
      'rule-operator-approval',
      'rule-price-floor',
    ])
    expect(lineage.source_refs).toEqual(
      expect.arrayContaining(['docs:execution-policy', 'docs:approval-flow', 'docs:legacy', 'notes:catalyst-filter']),
    )
    expect(lineage.clauses[0].rule_id).toBe('rule-catalyst-filter')
    expect(lineage.clauses[1].rule_id).toBe('rule-operator-approval')
    expect(lineage.clause_fingerprints).toHaveLength(4)
    expect(lineage.coherence_score).toBeGreaterThan(0.5)
    expect(JSON.parse(JSON.stringify(lineage))).toMatchObject({
      lineage_id: lineage.lineage_id,
      rule_set_name: 'live-approval-stack',
    })
  })
})
