import { describe, expect, it } from 'vitest'
import { buildPredictionMarketWorldStateSpine } from '@/lib/prediction-markets/world-state-spine'

describe('prediction market world-state spine', () => {
  it('builds a bullish world-state and a bet-ready ticket payload', () => {
    const spine = buildPredictionMarketWorldStateSpine({
      market_id: 'market-world-state-1',
      market_question: 'Will the live execution path remain governed and profitable?',
      venue: 'polymarket',
      as_of: '2026-04-09T10:30:00.000Z',
      regime: 'live-governed',
      source_audit: {
        market_id: 'market-world-state-1',
        as_of: '2026-04-09T10:15:00.000Z',
        sources: [
          {
            source_id: 'world-state-official',
            kind: 'official_docs',
            title: 'Official operator guide',
            url: 'https://example.com/docs/operator-guide',
            trust: 0.97,
            freshness: 0.96,
            evidence_strength: 1,
            notes: ['Primary operator guidance'],
          },
          {
            source_id: 'world-state-market',
            kind: 'market_data',
            title: 'Market midpoint snapshot',
            url: 'https://example.com/markets/midpoint',
            trust: 0.82,
            freshness: 0.78,
            evidence_strength: 0.84,
            notes: ['Market conditions remain stable'],
            geo_refs: ['110000'],
          },
        ],
      },
      rules_lineage: {
        market_id: 'market-world-state-1',
        as_of: '2026-04-09T10:20:00.000Z',
        rule_set_name: 'governed-live-stack',
        clauses: [
          {
            clause_id: 'world-state-bet-band',
            rule_id: 'rule-bet-band',
            title: 'Bet band',
            text: 'Only bet when the gap is decisive and the venue is ready.',
            source_refs: ['world-state-official'],
            status: 'active',
          },
          {
            clause_id: 'world-state-draft-watch',
            rule_id: 'rule-watch-band',
            title: 'Watch band',
            text: 'Wait when the edge is under the threshold.',
            source_refs: ['world-state-market'],
            status: 'draft',
          },
        ],
      },
      catalyst_timeline: {
        market_id: 'market-world-state-1',
        as_of: '2026-04-09T10:30:00.000Z',
        catalysts: [
          {
            catalyst_id: 'world-state-confirmed',
            label: 'Approval memo published',
            expected_at: '2026-04-09T09:45:00.000Z',
            occurred_at: '2026-04-09T09:40:00.000Z',
            status: 'confirmed',
            direction: 'bullish',
            urgency: 0.82,
            source_refs: ['world-state-official'],
          },
          {
            catalyst_id: 'world-state-pending',
            label: 'Venue window opens',
            expected_at: '2026-04-09T11:00:00.000Z',
            status: 'pending',
            direction: 'bullish',
            urgency: 0.58,
            source_refs: ['world-state-market'],
          },
        ],
      },
      price_signal: {
        midpoint_yes: 0.5,
        market_price_yes: 0.52,
        fair_value_yes: 0.64,
        spread_bps: 180,
      },
      ticket_kind: 'approval',
      action: 'bet',
      size_usd: 77.25,
      limit_price_yes: 0.58,
      created_at: '2026-04-09T10:31:00.000Z',
      operator_notes: ['Proceed if venue remains ready.'],
    })

    expect(spine.world_state.recommended_action).toBe('bet')
    expect(spine.world_state.recommended_side).toBe('yes')
    expect(spine.world_state.bias).toBe('bullish')
    expect(spine.world_state.source_alignment_score).toBeGreaterThan(0.75)
    expect(spine.world_state.summary).toContain('bias=bullish')
    expect(spine.world_state.summary).toContain('action=bet')
    expect(spine.world_state.geo_context?.adcodes).toEqual(['110000'])
    expect(spine.world_state.external_integration.data_asset_profile_ids).toContain('geomapdata-cn')
    expect(spine.world_state.external_read_models_summary).toContain('P1-C runtime summary')
    expect(spine.ticket_payload.ticket_kind).toBe('approval')
    expect(spine.ticket_payload.action).toBe('bet')
    expect(spine.ticket_payload.side).toBe('yes')
    expect(spine.ticket_payload.size_usd).toBe(77.25)
    expect(spine.ticket_payload.limit_price_yes).toBe(0.58)
    expect(spine.ticket_payload.rationale.join(' ')).toContain('World-state bias: bullish.')
    expect(spine.ticket_payload.summary).toContain('approval ticket')
    expect(spine.ticket_payload.summary).toContain('action=bet')
    expect(spine.ticket_payload.summary).toContain('side=yes')
    expect(spine.ticket_payload.summary).toContain('edge=1200bps')
    expect(JSON.parse(JSON.stringify(spine))).toMatchObject({
      world_state: {
        market_id: 'market-world-state-1',
      },
      ticket_payload: {
        ticket_id: spine.ticket_payload.ticket_id,
      },
    })
  })

  it('falls back to a no-trade world-state when source alignment and rules are weak', () => {
    const spine = buildPredictionMarketWorldStateSpine({
      market_id: 'market-world-state-2',
      market_question: 'Will the weak setup still deserve a live trade?',
      source_audit: {
        market_id: 'market-world-state-2',
        sources: [
          {
            source_id: 'weak-source-1',
            kind: 'community_repo',
            title: 'Loose note',
            trust: 0.35,
            freshness: 0.34,
            evidence_strength: 0.4,
            notes: ['Unverified note'],
          },
        ],
      },
      rules_lineage: {
        market_id: 'market-world-state-2',
        clauses: [
          {
            clause_id: 'weak-rule-1',
            rule_id: 'rule-conflicted',
            title: 'Conflicted clause',
            text: 'This clause is still under dispute.',
            status: 'conflicted',
          },
        ],
      },
      catalyst_timeline: {
        market_id: 'market-world-state-2',
        catalysts: [
          {
            catalyst_id: 'weak-catalyst-1',
            label: 'Unclear catalyst',
            status: 'pending',
            urgency: 0.18,
          },
        ],
      },
      price_signal: {
        midpoint_yes: 0.51,
        market_price_yes: 0.5,
        fair_value_yes: 0.51,
        spread_bps: 210,
      },
    })

    expect(spine.world_state.recommended_action).toBe('no_trade')
    expect(spine.world_state.recommended_side).toBeNull()
    expect(spine.world_state.risk_flags).toEqual(expect.arrayContaining(['low_source_alignment', 'conflicted_rules']))
    expect(spine.ticket_payload.action).toBe('no_trade')
    expect(spine.ticket_payload.side).toBeNull()
    expect(spine.ticket_payload.summary).toContain('no_trade')
  })
})
