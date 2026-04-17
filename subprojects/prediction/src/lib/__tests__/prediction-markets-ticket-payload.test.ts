import { describe, expect, it } from 'vitest'
import { buildPredictionMarketTicketPayload } from '@/lib/prediction-markets/ticket-payload'
import { buildPredictionMarketWorldStateSpine } from '@/lib/prediction-markets/world-state-spine'

describe('prediction market ticket payload', () => {
  it('builds a compact approval payload from a world-state snapshot', () => {
    const spine = buildPredictionMarketWorldStateSpine({
      market_id: 'market-ticket-1',
      market_question: 'Will the ticket payload remain reviewable?',
      source_audit: {
        market_id: 'market-ticket-1',
        sources: [
          {
            source_id: 'ticket-source-1',
            kind: 'official_docs',
            title: 'Approval flow doc',
            trust: 0.95,
            freshness: 0.92,
            evidence_strength: 0.97,
          },
          {
            source_id: 'ticket-source-2',
            kind: 'market_data',
            title: 'Market sample',
            trust: 0.77,
            freshness: 0.71,
            evidence_strength: 0.76,
          },
        ],
      },
      rules_lineage: {
        market_id: 'market-ticket-1',
        clauses: [
          {
            clause_id: 'ticket-rule-1',
            rule_id: 'rule-ticket',
            title: 'Ticket rule',
            text: 'Create a compact payload before execution.',
            status: 'active',
          },
        ],
      },
      catalyst_timeline: {
        market_id: 'market-ticket-1',
        catalysts: [
          {
            catalyst_id: 'ticket-catalyst-1',
            label: 'Approval window',
            status: 'pending',
            urgency: 0.65,
          },
        ],
      },
      price_signal: {
        midpoint_yes: 0.48,
        market_price_yes: 0.45,
        fair_value_yes: 0.59,
        spread_bps: 150,
      },
    })

    const ticket = buildPredictionMarketTicketPayload({
      world_state: spine.world_state,
      ticket_id: 'ticket-manual-1',
      ticket_kind: 'approval',
      action: 'bet',
      size_usd: 88.5,
      limit_price_yes: 0.57,
      created_at: '2026-04-09T10:45:00.000Z',
      operator_notes: ['Manual review kept the trade in approval mode.'],
    })

    expect(ticket.ticket_id).toBe('ticket-manual-1')
    expect(ticket.ticket_kind).toBe('approval')
    expect(ticket.action).toBe('bet')
    expect(ticket.side).toBe('yes')
    expect(ticket.size_usd).toBe(88.5)
    expect(ticket.limit_price_yes).toBe(0.57)
    expect(ticket.summary).toContain('approval ticket')
    expect(ticket.summary).toContain('action=bet')
    expect(ticket.summary).toContain('side=yes')
    expect(ticket.summary).toContain('Will the ticket payload remain reviewable?')
    expect(ticket.rationale.join(' ')).toContain('Manual review kept the trade in approval mode.')
    expect(ticket.source_refs).toEqual(expect.arrayContaining(['ticket-source-1', 'ticket-source-2']))
    expect(ticket.rule_refs).toContain('rule-ticket')
    expect(ticket.catalyst_refs).toContain('ticket-catalyst-1')
    expect(ticket.fingerprint).toContain('prediction-ticket:')
    expect(JSON.parse(JSON.stringify(ticket))).toMatchObject({
      ticket_id: 'ticket-manual-1',
      action: 'bet',
      side: 'yes',
    })
  })
})
