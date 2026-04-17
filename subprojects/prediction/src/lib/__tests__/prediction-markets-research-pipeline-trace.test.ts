import { describe, expect, it, vi } from 'vitest'
import {
  buildBaseRateResearch,
  buildMarketResearchSidecar,
  buildResearchPipelineTrace,
} from '@/lib/prediction-markets/research'

describe('prediction markets research pipeline trace', () => {
  const market = {
    market_id: 'market-123',
    venue: 'polymarket' as const,
    question: 'Will the sample event resolve Yes?',
    slug: 'sample-event',
  }

  const signals = [
    {
      kind: 'news',
      title: 'Officials reiterate timeline',
      summary: 'The latest briefing suggests the schedule remains on track.',
      source_name: 'Newswire',
      source_url: 'https://example.com/news/timeline',
      captured_at: '2026-04-08T08:00:00.000Z',
      tags: ['timeline', 'official'],
      stance: 'contradictory',
    },
    {
      source_kind: 'worldmonitor',
      headline: 'Regional observers flag delayed tabulation',
      message: 'Observer network reports delays in two key districts.',
      source: 'WorldMonitor',
      url: 'https://example.com/worldmonitor/delay',
      published_at: '2026-04-08T11:30:00.000Z',
      tags: ['delay', 'districts'],
      stance: 'supportive',
    },
    {
      kind: 'manual_note',
      title: 'Analyst check-in',
      note: 'Current read slightly favors Yes.',
      captured_at: '2026-04-08T09:15:00.000Z',
      tags: ['desk', 'delay'],
      thesis_probability: 0.64,
      thesis_rationale: 'Observer reports add modest support to the delay thesis.',
      stance: 'supportive',
    },
  ]

  it('builds a deterministic query -> retrieval -> rank -> summarize -> aggregate trace', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-08T12:00:00.000Z'))

    const sidecar = buildMarketResearchSidecar({
      market,
      snapshot: { midpoint_yes: 0.52, yes_price: 0.52 },
      forecast_probability_yes: 0.61,
      signals,
    })
    const baseRateResearch = buildBaseRateResearch({
      market,
      snapshot: { midpoint_yes: 0.52, yes_price: 0.52 },
      signals: sidecar.signals,
      evidencePackets: sidecar.evidence_packets,
      health: sidecar.health,
    })

    const trace = buildResearchPipelineTrace({
      market,
      snapshot: { source_urls: ['https://example.com/news/timeline'] },
      signals: sidecar.signals,
      evidencePackets: sidecar.evidence_packets,
      health: sidecar.health,
      baseRateResearch,
      forecasterCandidates: sidecar.synthesis.forecaster_candidates,
      independentForecasterOutputs: sidecar.synthesis.independent_forecaster_outputs,
      weightedAggregatePreview: sidecar.synthesis.weighted_aggregate_preview,
      comparativeReport: sidecar.synthesis.comparative_report,
      forecast_probability_yes: 0.61,
    })

    const traceAgain = buildResearchPipelineTrace({
      market,
      snapshot: { source_urls: ['https://example.com/news/timeline'] },
      signals: sidecar.signals,
      evidencePackets: sidecar.evidence_packets,
      health: sidecar.health,
      baseRateResearch,
      forecasterCandidates: sidecar.synthesis.forecaster_candidates,
      independentForecasterOutputs: sidecar.synthesis.independent_forecaster_outputs,
      weightedAggregatePreview: sidecar.synthesis.weighted_aggregate_preview,
      comparativeReport: sidecar.synthesis.comparative_report,
      forecast_probability_yes: 0.61,
    })

    expect(trace.trace_id).toBe(traceAgain.trace_id)
    expect(trace.summary).toBe(traceAgain.summary)
    expect(trace.stages.query.query_terms).toEqual(expect.arrayContaining(['sample', 'event', 'resolve', 'timeline']))
    expect(trace.stages.retrieval).toMatchObject({
      signal_count: 3,
      evidence_count: 3,
      health_status: 'healthy',
      missing_signal_kinds: ['alert'],
      external_integration: {
        total_profiles: 1,
        profile_ids: ['worldmonitor-app'],
      },
    })
    expect(trace.stages.rank.ranked_signals[0]).toMatchObject({
      kind: 'manual_note',
      stance: 'supportive',
    })
    expect(trace.stages.rank.ranked_signals[0].reasons).toEqual(
      expect.arrayContaining([
        'kind=manual_note',
        'stance=supportive',
        'thesis_probability=0.6400',
        'tags=2',
      ]),
    )
    expect(trace.stages.summarize.both_sides_reasoning).toContain('Supportive:')
    expect(trace.stages.summarize.both_sides_reasoning).toContain('Counter:')
    expect(trace.stages.summarize.both_sides_reasoning).toContain('Net direction: supportive.')
    expect(trace.stages.summarize.source_family_summary).toContain('worldmonitor.app')
    expect(trace.stages.aggregate).toMatchObject({
      baseline_probability_yes: 0.52,
      forecaster_count: 2,
      usable_forecaster_count: 2,
      preferred_mode: 'aggregate',
      comparative_summary: expect.stringContaining('Preferred mode: aggregate.'),
    })
    expect(trace.summary).toContain('query=Will the sample event resolve Yes?')
    expect(trace.summary).toContain('aggregate=aggregate:')

    vi.useRealTimers()
  })
})
