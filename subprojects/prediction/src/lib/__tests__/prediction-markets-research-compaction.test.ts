import { describe, expect, it } from 'vitest'

import { buildPredictionMarketResearchSupercompactContext } from '@/lib/prediction-markets/research-compaction'

describe('prediction markets research compaction', () => {
  it('builds a deterministic supercompact context block with bounded size', () => {
    const context = buildPredictionMarketResearchSupercompactContext({
      market: {
        market_id: 'market-compact-001',
        venue: 'polymarket',
        slug: 'market-compact-001',
        question: 'Will the compact context stay concise for research prompts?',
      },
      signals: [
        {
          signal_id: 'sig-1',
          kind: 'news',
          title: 'Officials restate the timeline in a very long headline that should still compact well',
          summary: 'Officials say the schedule remains on track despite chatter about delays and procedural friction.',
          source_name: 'Newswire',
          captured_at: '2026-04-08T08:00:00.000Z',
          stance: 'contradictory',
          tags: ['timeline', 'official'],
        },
        {
          signal_id: 'sig-2',
          kind: 'worldmonitor',
          title: 'Observers flag district delay risk',
          summary: 'Observer network reports possible tabulation delays in two districts.',
          source_name: 'WorldMonitor',
          captured_at: '2026-04-08T11:30:00.000Z',
          stance: 'supportive',
          tags: ['delay', 'district'],
        },
        {
          signal_id: 'sig-3',
          kind: 'manual_note',
          title: 'Desk note',
          summary: 'Desk still leans slightly Yes.',
          source_name: 'Desk',
          captured_at: '2026-04-08T12:00:00.000Z',
          stance: 'supportive',
          tags: ['desk'],
        },
      ],
      evidence_packets: [
        {
          evidence_id: 'ev-1',
          type: 'system_note',
          title: 'Observer note',
          summary: 'Observer network reports delay risk.',
        },
        {
          evidence_id: 'ev-2',
          type: 'manual_thesis',
          title: 'Desk thesis',
          summary: 'Desk leans Yes.',
        },
      ],
      retrieval_summary: {
        signal_count: 3,
        evidence_count: 2,
        latest_signal_at: '2026-04-08T12:00:00.000Z',
        counts_by_kind: {
          worldmonitor: 1,
          news: 1,
          alert: 0,
          manual_note: 1,
        },
        counts_by_stance: {
          supportive: 2,
          contradictory: 1,
          neutral: 0,
          unknown: 0,
        },
        health_status: 'healthy',
        health_issues: [],
      },
      weighted_aggregate_preview: {
        contributor_count: 2,
        usable_contributor_count: 2,
        coverage: 1,
        weighted_probability_yes: 0.5653,
        weighted_delta_bps: 653,
        abstention_recommended: false,
      },
      comparative_report: {
        summary: 'Market-only 50%, aggregate 56.5%, forecast unavailable, abstention not recommended. Preferred mode: aggregate.',
        market_only: { probability_yes: 0.5 },
        aggregate: { probability_yes: 0.5653 },
        forecast: { forecast_probability_yes: null },
        abstention: {
          recommended: false,
          blocks_forecast: false,
          reason_codes: [],
        },
      },
      abstention_policy: {
        policy_version: 'structured-abstention-v1',
        recommended: false,
        blocks_forecast: false,
        manual_review_required: false,
        trigger_codes: [],
        rationale: 'Sufficient signal coverage.',
      },
      external_references: [
        {
          reference_id: 'ref-1',
          reference_source: 'metaculus',
          source_name: 'Metaculus',
          reference_probability_yes: 0.57,
          market_delta_bps: 700,
          forecast_delta_bps: null,
        },
      ],
      key_factors: [
        'Base rate anchor at 50%.',
        'Observer network points to delay risk.',
        'Desk note leans Yes.',
      ],
      counterarguments: [
        'Officials say the schedule remains on track.',
      ],
      no_trade_hints: [
        'No trade unless the edge survives execution frictions.',
      ],
      max_chars: 700,
    })

    expect(context).toMatchObject({
      schema_version: 'supercompact_research_context.v1',
      format: 'supercompact',
      stats: {
        signal_count: 3,
        evidence_count: 2,
        reference_count: 1,
        health_status: 'healthy',
      },
      market: {
        market_id: 'market-compact-001',
        venue: 'polymarket',
      },
      stance_mix: {
        supportive: 2,
        contradictory: 1,
        neutral: 0,
        unknown: 0,
      },
    })
    expect(context.compact_summary).toContain('signals=3')
    expect(context.compact_prompt_block).toContain('Aggregate 56.5%')
    expect(context.compact_prompt_block).toContain('Abstention policy structured-abstention-v1')
    expect(context.compact_prompt_block.length).toBeLessThanOrEqual(700)
    expect(context.prompt_char_count).toBe(context.compact_prompt_block.length)
    expect(context.source_refs).toEqual(expect.arrayContaining(['market-compact-001', 'ev-1', 'ref-1']))
    expect(context.compact_bullets.length).toBeGreaterThan(4)
  })
})
