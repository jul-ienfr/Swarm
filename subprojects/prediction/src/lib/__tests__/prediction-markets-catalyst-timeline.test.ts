import { describe, expect, it } from 'vitest'
import { buildPredictionMarketCatalystTimeline } from '@/lib/prediction-markets/catalyst-timeline'

describe('prediction market catalyst timeline', () => {
  const catalysts = [
    {
      catalyst_id: 'catalyst-early-overdue',
      label: 'Early filing deadline',
      expected_at: '2026-04-09T08:00:00.000Z',
      status: 'pending' as const,
      direction: 'bullish' as const,
      urgency: 0.88,
      source_refs: ['news:deadline'],
      impact_hint: 'Could unlock a rapid repricing.',
    },
    {
      catalyst_id: 'catalyst-confirmed',
      label: 'Official guidance published',
      expected_at: '2026-04-09T09:30:00.000Z',
      occurred_at: '2026-04-09T09:20:00.000Z',
      status: 'confirmed' as const,
      direction: 'bullish' as const,
      urgency: 0.64,
      source_refs: ['docs:guidance'],
      impact_hint: 'Confirms the original thesis.',
    },
    {
      catalyst_id: 'catalyst-future-watch',
      label: 'Decision window opens',
      expected_at: '2026-04-09T14:00:00.000Z',
      status: 'pending' as const,
      direction: 'neutral' as const,
      urgency: 0.46,
      source_refs: ['calendar:window'],
      impact_hint: 'Still several hours away.',
    },
  ]

  it('orders catalysts, marks overdue events, and summarizes pressure', () => {
    const timeline = buildPredictionMarketCatalystTimeline({
      market_id: 'market-catalyst-1',
      as_of: '2026-04-09T10:00:00.000Z',
      catalysts,
    })

    const timelineAgain = buildPredictionMarketCatalystTimeline({
      market_id: 'market-catalyst-1',
      as_of: '2026-04-09T10:00:00.000Z',
      catalysts: [...catalysts].reverse(),
    })

    expect(timeline.timeline_id).toBe(timelineAgain.timeline_id)
    expect(timeline.events).toHaveLength(3)
    expect(timeline.events[0].catalyst_id).toBe('catalyst-early-overdue')
    expect(timeline.events[0].overdue).toBe(true)
    expect(timeline.events[1].catalyst_id).toBe('catalyst-confirmed')
    expect(timeline.events[2].catalyst_id).toBe('catalyst-future-watch')
    expect(timeline.pending_count).toBe(2)
    expect(timeline.confirmed_count).toBe(1)
    expect(timeline.overdue_count).toBe(1)
    expect(timeline.next_event_id).toBe('catalyst-early-overdue')
    expect(timeline.summary).toContain('3 catalysts')
    expect(timeline.summary).toContain('2 pending')
    expect(timeline.summary).toContain('1 confirmed')
    expect(timeline.summary).toContain('1 overdue')
    expect(timeline.summary).toContain('next=Early filing deadline')
    expect(timeline.urgency_score).toBeGreaterThan(0.5)
    expect(JSON.parse(JSON.stringify(timeline))).toMatchObject({
      timeline_id: timeline.timeline_id,
      market_id: 'market-catalyst-1',
    })
  })
})
