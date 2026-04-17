import { describe, expect, it, vi } from 'vitest'
import {
  buildBaseRateResearch,
  buildResearchPipelineVersionMetadata,
  buildMarketResearchSidecar,
  buildResearchEvidencePacket,
  annotateMarketResearchSidecarComparisons,
  normalizeResearchSignal,
} from '@/lib/prediction-markets/research'

describe('prediction markets research bridge', () => {
  const market = {
    market_id: 'market-123',
    venue: 'polymarket' as const,
    question: 'Will the sample event resolve Yes?',
    slug: 'sample-event',
  }

  it('normalizes worldmonitor-like payloads into a stable bridge signal', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-08T12:00:00.000Z'))

    const signal = normalizeResearchSignal({
      signal_type: 'world_monitor',
      headline: 'Election board delays official count',
      message: 'Local reporting suggests the timetable may slip by a day.',
      source: 'WorldMonitor',
      link: 'https://example.com/worldmonitor/story',
      published_at: '2026-04-08T10:30:00.000Z',
      tags: ['US', 'Election', 'US'],
      stance: 'mixed',
      confidence: 0.82,
      priority: 'urgent',
      region: 'us',
      country: 'usa',
    })

    expect(signal).toMatchObject({
      kind: 'worldmonitor',
      title: 'Election board delays official count',
      summary: 'Local reporting suggests the timetable may slip by a day.',
      source_name: 'WorldMonitor',
      source_url: 'https://example.com/worldmonitor/story',
      captured_at: '2026-04-08T10:30:00.000Z',
      tags: ['us', 'election'],
      stance: 'neutral',
      confidence: 0.82,
      severity: 'high',
    })
    expect(signal.signal_id.startsWith('worldmonitor:')).toBe(true)
    expect(signal.external_profiles.map((profile) => profile.profile_id)).toContain('worldmonitor-app')
    expect(signal.payload).toEqual({
      region: 'us',
      country: 'usa',
    })

    vi.useRealTimers()
  })

  it('maps manual notes with thesis probability into manual_thesis evidence', () => {
    const packet = buildResearchEvidencePacket({
      market,
      signal: {
        kind: 'manual_note',
        title: 'Desk update after overnight monitoring',
        note: 'Desk thinks the Yes side is now stronger.',
        captured_at: '2026-04-08T11:00:00.000Z',
        thesis_probability: 0.67,
        thesis_rationale: 'Field reports and official statements improve the Yes case.',
        tags: ['desk', 'overnight'],
      },
    })

    expect(packet.type).toBe('manual_thesis')
    expect(packet.market_id).toBe('market-123')
    expect(packet.venue).toBe('polymarket')
    expect(packet.title).toContain('Manual note')
    expect(packet.summary).toBe('Field reports and official statements improve the Yes case.')
    expect(packet.evidence_id).toContain('market-123:research:')
    expect(packet.metadata).toMatchObject({
      research_kind: 'manual_note',
      tags: ['desk', 'overnight'],
      thesis_probability: 0.67,
      thesis_rationale: 'Field reports and official statements improve the Yes case.',
      external_profile_ids: [],
    })
  })

  it('buildBaseRateResearch returns conservative abstention hints when signals are weak or absent', () => {
    const baseRate = buildBaseRateResearch({
      market,
      signals: [],
      evidencePackets: [],
      health: {
        status: 'blocked',
        completeness_score: 0,
        duplicate_signal_count: 0,
        issues: ['no_signals'],
        source_kinds: [],
      },
    })

    expect(baseRate).toMatchObject({
      market_id: 'market-123',
      venue: 'polymarket',
      base_rate_probability_hint: 0.5,
      base_rate_source: 'fallback_50',
      abstention_recommended: true,
    })
    expect(baseRate.retrieval_summary).toMatchObject({
      signal_count: 0,
      evidence_count: 0,
      counts_by_kind: {
        worldmonitor: 0,
        news: 0,
        alert: 0,
        manual_note: 0,
      },
      missing_signal_kinds: ['worldmonitor', 'news', 'alert', 'manual_note'],
      health_status: 'blocked',
      health_issues: ['no_signals'],
      external_integration: {
        total_profiles: 0,
      },
      external_runtime: {
        p1_a: expect.stringContaining('P1-A runtime summary'),
        p2_b: expect.stringContaining('P2-B runtime summary'),
        p2_c: expect.stringContaining('P2-C runtime summary'),
      },
    })
    expect(baseRate.abstention_summary).toMatchObject({
      recommended: true,
      reason_codes: ['no_signals', 'research_health_blocked', 'no_manual_thesis'],
      exogenous_thesis_present: false,
    })
    expect(baseRate.key_factors).toContain('0 supportive, 0 contradictory, 0 neutral signal(s).')
    expect(baseRate.no_trade_hints).toContain(
      'No external research signals are present, so the output should remain market-only.',
    )
    expect(baseRate.no_trade_hints).toContain(
      'Research sidecar health is blocked, so the result should be treated as advisory only.',
    )
    expect(baseRate.no_trade_hints).toContain(
      'No manual thesis has been supplied, so there is no exogenous thesis edge yet.',
    )
  })

  it('builds a decoupled research sidecar with evidence packets and synthesis', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-08T12:00:00.000Z'))

    const sidecar = buildMarketResearchSidecar({
      market,
      signals: [
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
      ],
    })

    expect(sidecar.market_id).toBe('market-123')
    expect(sidecar.venue).toBe('polymarket')
    expect(sidecar.generated_at).toBe('2026-04-08T12:00:00.000Z')
    expect(sidecar.evidence_packets).toHaveLength(3)
    expect(sidecar.evidence_packets.map((packet) => packet.type)).toEqual([
      'system_note',
      'system_note',
      'manual_thesis',
    ])

    expect(sidecar.synthesis).toMatchObject({
      market_id: 'market-123',
      venue: 'polymarket',
      question: 'Will the sample event resolve Yes?',
      generated_at: '2026-04-08T12:00:00.000Z',
      signal_count: 3,
      evidence_count: 3,
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
      latest_signal_at: '2026-04-08T11:30:00.000Z',
      retrieval_summary: {
        signal_count: 3,
        evidence_count: 3,
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
        external_integration: {
          total_profiles: 1,
          profile_ids: ['worldmonitor-app'],
        },
      },
      external_integration: {
        total_profiles: 1,
        profile_ids: ['worldmonitor-app'],
      },
      manual_thesis_probability_hint: 0.64,
      manual_thesis_rationale_hint: 'Observer reports add modest support to the delay thesis.',
      base_rate_probability_hint: 0.5,
      base_rate_rationale_hint: 'Base rate anchored to 50% with 2 supportive and 1 contradictory signals.',
      base_rate_source: 'fallback_50',
      abstention_recommended: false,
      abstention_summary: {
        recommended: false,
        reason_codes: [],
        exogenous_thesis_present: true,
        manual_thesis_probability_hint: 0.64,
      },
    })

    expect(sidecar.synthesis.key_factors).toContain('Base rate anchor at 50% from fallback_50.')
    expect(sidecar.synthesis.key_factors).toContain('3 evidence packet(s) bridged into the research sidecar.')
    expect(sidecar.synthesis.key_factors).toContain('P1-A active discovery profiles: worldmonitor-app.')
    expect(sidecar.synthesis.counterarguments).toContain('The latest briefing suggests the schedule remains on track.')
    expect(sidecar.synthesis.no_trade_hints).toEqual(expect.arrayContaining([
      expect.stringContaining('Watchlist diff-only remains non-canonical'),
      expect.stringContaining('Source discovery backlog stays read-only and non-runtime-critical'),
    ]))
    expect(sidecar.synthesis.signal_kinds).toEqual(['worldmonitor', 'manual_note', 'news'])
    expect(sidecar.synthesis.top_tags).toEqual(['delay', 'desk', 'districts', 'official', 'timeline'])
    expect(sidecar.synthesis.summary).toContain('Research sidecar for "Will the sample event resolve Yes?"')
    expect(sidecar.synthesis.key_points[0]).toContain('Regional observers flag delayed tabulation')
    expect(sidecar.synthesis.evidence_refs).toEqual(
      sidecar.evidence_packets.map((packet) => packet.evidence_id),
    )
    expect(sidecar.synthesis.retrieval_summary.supportive_signal_ids).toHaveLength(2)
    expect(sidecar.synthesis.retrieval_summary.contradictory_signal_ids).toHaveLength(1)
    expect(sidecar.synthesis.external_profiles.map((profile) => profile.profile_id)).toEqual(['worldmonitor-app'])
    expect(sidecar.evidence_packets[1]?.metadata).toMatchObject({
      external_profile_ids: ['worldmonitor-app'],
    })
    expect(sidecar.synthesis.forecaster_candidates).toEqual([
      expect.objectContaining({
        forecaster_id: 'market_base_rate',
        forecaster_kind: 'market_base_rate',
        role: 'baseline',
        probability_yes: 0.5,
      }),
      expect.objectContaining({
        forecaster_id: 'manual_thesis_consensus',
        forecaster_kind: 'manual_thesis',
        role: 'candidate',
        probability_yes: 0.64,
        input_signal_ids: expect.any(Array),
      }),
    ])
    expect(sidecar.pipeline_version_metadata).toEqual(buildResearchPipelineVersionMetadata())
    expect(sidecar.synthesis.pipeline_version_metadata).toEqual(sidecar.pipeline_version_metadata)
    expect(sidecar.synthesis.pipeline_trace).toMatchObject({
      pipeline_version_metadata: sidecar.pipeline_version_metadata,
      stages: {
        query: {
          market_id: 'market-123',
          venue: 'polymarket',
          signal_count: 3,
          evidence_count: 3,
        },
        retrieval: {
          signal_count: 3,
          evidence_count: 3,
          health_status: 'healthy',
          missing_signal_kinds: ['alert'],
        },
        rank: {
          balance: {
            supportive_count: 2,
            contradictory_count: 1,
            neutral_count: 0,
            unknown_count: 0,
            direction: 'supportive',
          },
        },
        summarize: {
          supporting_summary: expect.stringContaining('Regional observers flag delayed tabulation'),
          counter_summary: expect.stringContaining('Officials reiterate timeline'),
          source_family_summary: expect.stringContaining('worldmonitor.app'),
        },
        aggregate: {
          baseline_probability_yes: 0.5,
          preferred_mode: 'aggregate',
          comparative_summary: expect.stringContaining('Preferred mode: aggregate.'),
        },
      },
    })
    expect(sidecar.synthesis.independent_forecaster_outputs).toEqual([
      expect.objectContaining({
        forecaster_id: 'market_base_rate',
        raw_weight: 0.4,
        normalized_weight: 0.5333,
        calibrated_probability_yes: 0.5,
        calibration_shift_bps: 0,
      }),
      expect.objectContaining({
        forecaster_id: 'manual_thesis_consensus',
        raw_weight: 0.35,
        normalized_weight: 0.4667,
        calibrated_probability_yes: 0.64,
        calibration_shift_bps: 0,
      }),
    ])
    expect(sidecar.synthesis.weighted_aggregate_preview).toMatchObject({
      pipeline_version: 'poly-025-research-v1',
      calibration_version: 'calibration-shrinkage-v1',
      abstention_policy_version: 'structured-abstention-v1',
      contributor_count: 2,
      usable_contributor_count: 2,
      coverage: 1,
      raw_weight_total: 0.75,
      normalized_weight_total: 1,
      base_rate_probability_yes: 0.5,
      weighted_probability_yes: 0.5653,
      weighted_probability_yes_raw: 0.5653,
      weighted_delta_bps: 653,
      weighted_raw_delta_bps: 653,
      abstention_recommended: false,
    })
    expect(sidecar.synthesis.comparative_report).toMatchObject({
      market_only: {
        probability_yes: 0.5,
        delta_bps_vs_market_only: 0,
      },
      aggregate: {
        probability_yes: 0.5653,
        delta_bps_vs_market_only: 653,
        coverage: 1,
        contributor_count: 2,
        usable_contributor_count: 2,
      },
      forecast: {
        forecast_probability_yes: null,
        delta_bps_vs_market_only: null,
        delta_bps_vs_aggregate: null,
      },
      abstention: {
        recommended: false,
        blocks_forecast: false,
        reason_codes: [],
      },
    })
    expect(sidecar.synthesis.comparative_report.preferred_mode).toBe('aggregate')
    expect(sidecar.synthesis.comparative_report.summary).toContain('Preferred mode: aggregate.')
    expect(sidecar.synthesis.supercompact_context).toMatchObject({
      schema_version: 'supercompact_research_context.v1',
      format: 'supercompact',
      stats: {
        signal_count: 3,
        evidence_count: 3,
        health_status: 'healthy',
      },
      stance_mix: {
        supportive: 2,
        contradictory: 1,
        neutral: 0,
        unknown: 0,
      },
    })
    expect(sidecar.synthesis.supercompact_context.compact_summary).toContain('signals=3')
    expect(sidecar.synthesis.supercompact_context.compact_prompt_block).toContain('Aggregate 56.5%')
    expect(sidecar.synthesis.supercompact_context.compact_prompt_block).toContain('Abstention policy structured-abstention-v1')
    expect(sidecar.synthesis.supercompact_context.source_refs).toEqual(
      expect.arrayContaining(sidecar.evidence_packets.map((packet) => packet.evidence_id)),
    )
    expect(sidecar.synthesis.calibration_snapshot).toMatchObject({
      pipeline_version: 'poly-025-research-v1',
      calibration_version: 'calibration-shrinkage-v1',
      abstention_policy_version: 'structured-abstention-v1',
      sample_size: 2,
      usable_contributor_count: 2,
      base_rate_probability_yes: 0.5,
      weighted_probability_yes: 0.5653,
      weighted_probability_yes_raw: 0.5653,
      calibration_gap_bps: 653,
      mean_abs_shift_bps: 0,
      coverage: 1,
      benchmark_preferred_mode: 'aggregate',
      benchmark_summary: expect.stringContaining('Preferred mode: aggregate.'),
      benchmark_blockers: [],
      benchmark_out_of_sample_ready: true,
      validation_state: 'ready',
      validation_blockers: [],
      calibration_quality: 'tight',
      calibration_bias: 'yes_upward',
    })
    expect(sidecar.synthesis.calibration_snapshot.validation_summary).toContain('Validation state: ready')
    expect(sidecar.synthesis.calibration_snapshot.calibration_summary).toContain('Calibration tight')
    expect(sidecar.synthesis.abstention_policy).toMatchObject({
      policy_id: 'structured-abstention',
      policy_version: 'structured-abstention-v1',
      recommended: false,
      blocks_forecast: false,
    })
    expect(sidecar.health).toMatchObject({
      status: 'healthy',
      duplicate_signal_count: 0,
      issues: [],
      source_kinds: ['worldmonitor', 'manual_note', 'news'],
    })

    vi.useRealTimers()
  })

  it('tracks Metaculus and Manifold references with market and forecast deltas when available', () => {
    const sidecar = buildMarketResearchSidecar({
      market,
      snapshot: { midpoint_yes: 0.52, yes_price: 0.52 },
      forecast_probability_yes: 0.61,
      signals: [
        {
          kind: 'news',
          title: 'Metaculus consensus tightens',
          summary: 'The community forecast nudges upward.',
          source_name: 'Metaculus',
          source_url: 'https://www.metaculus.com/questions/forecast-123/',
          captured_at: '2026-04-08T09:00:00.000Z',
          tags: ['forecast'],
          stance: 'supportive',
          payload: {
            probability_yes: 0.57,
          },
        },
        {
          kind: 'news',
          title: 'Manifold traders stay bullish',
          summary: 'The market price remains above the baseline.',
          source_name: 'Manifold',
          source_url: 'https://manifold.markets/m/sample-market',
          captured_at: '2026-04-08T10:30:00.000Z',
          tags: ['forecast', 'market'],
          stance: 'supportive',
          payload: {
            forecast_probability_yes: 0.63,
          },
        },
      ],
    })

    expect(sidecar.synthesis.external_reference_count).toBe(2)
    expect(sidecar.synthesis.external_references.map((reference) => reference.reference_source)).toEqual(
      expect.arrayContaining(['metaculus', 'manifold']),
    )
    expect(sidecar.synthesis.market_probability_yes_hint).toBe(0.52)
    expect(sidecar.synthesis.forecast_probability_yes_hint).toBe(0.61)
    expect(sidecar.synthesis.market_delta_bps).toBe(800)
    expect(sidecar.synthesis.forecast_delta_bps).toBe(-100)
    expect(sidecar.synthesis.comparative_report).toMatchObject({
      market_only: {
        probability_yes: 0.52,
        delta_bps_vs_market_only: 0,
      },
      forecast: {
        forecast_probability_yes: 0.61,
        delta_bps_vs_market_only: 900,
      },
      abstention: {
        recommended: false,
      },
    })
    expect(sidecar.synthesis.comparative_report.preferred_mode).toBe('aggregate')
    expect(sidecar.synthesis.comparative_report.summary).toContain('forecast 61%')
    expect(sidecar.synthesis.forecaster_candidates).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          forecaster_id: 'market_base_rate',
          role: 'baseline',
          probability_yes: 0.52,
        }),
        expect.objectContaining({
          forecaster_kind: 'external_reference',
          role: 'comparator',
          source_name: 'Metaculus',
          probability_yes: 0.57,
        }),
        expect.objectContaining({
          forecaster_kind: 'external_reference',
          role: 'comparator',
          source_name: 'Manifold',
          probability_yes: 0.63,
        }),
      ]),
    )
    const metaculusReference = sidecar.synthesis.external_references.find((reference) => reference.reference_source === 'metaculus')
    const manifoldReference = sidecar.synthesis.external_references.find((reference) => reference.reference_source === 'manifold')
    expect(metaculusReference).toMatchObject({
      source_name: 'Metaculus',
      source_url: 'https://www.metaculus.com/questions/forecast-123/',
      reference_probability_yes: 0.57,
      market_delta_bps: 500,
      forecast_delta_bps: -400,
    })
    expect(manifoldReference).toMatchObject({
      source_name: 'Manifold',
      source_url: 'https://manifold.markets/m/sample-market',
      reference_probability_yes: 0.63,
      market_delta_bps: 1100,
      forecast_delta_bps: 200,
    })
  })

  it('recomputes the supercompact context after comparative annotation updates', () => {
    const sidecar = buildMarketResearchSidecar({
      market,
      snapshot: { midpoint_yes: 0.52, yes_price: 0.52 },
      signals: [
        {
          kind: 'manual_note',
          title: 'Desk update',
          note: 'Desk leans yes.',
          captured_at: '2026-04-08T09:00:00.000Z',
          thesis_probability: 0.61,
          thesis_rationale: 'Desk thesis stays mildly constructive.',
          tags: ['desk'],
          stance: 'supportive',
        },
      ],
    })

    const annotated = annotateMarketResearchSidecarComparisons(sidecar, 0.64)

    expect(annotated.synthesis.forecast_probability_yes_hint).toBe(0.64)
    expect(annotated.synthesis.supercompact_context.compact_prompt_block).toContain('forecast 64.0%')
    expect(annotated.synthesis.supercompact_context.compact_prompt_block).toContain('Comparative summary:')
    expect(annotated.synthesis.supercompact_context.stats.reference_count).toBe(
      annotated.synthesis.external_reference_count,
    )
  })

  it('deduplicates repeated narrative signals and classifies social feeds as alerts', () => {
    const sidecar = buildMarketResearchSidecar({
      market,
      signals: [
        {
          kind: 'news',
          title: 'Officials reiterate timeline',
          summary: 'The latest briefing suggests the schedule remains on track.',
          source_name: 'Newswire',
          source_url: 'https://example.com/news/timeline',
          captured_at: '2026-04-08T08:00:00.000Z',
          tags: ['timeline'],
        },
        {
          source_kind: 'twitter',
          headline: 'Officials reiterate timeline',
          message: 'The latest briefing suggests the schedule remains on track.',
          source: 'Twitter Watcher',
          url: 'https://x.com/example/status/123',
          published_at: '2026-04-08T08:00:00.000Z',
          tags: ['timeline'],
          stance: 'neutral',
        },
        {
          source_kind: 'twitter',
          headline: 'Officials reiterate timeline',
          message: 'The latest briefing suggests the schedule remains on track.',
          source: 'Twitter Watcher',
          url: 'https://x.com/example/status/123',
          published_at: '2026-04-08T08:00:00.000Z',
          tags: ['timeline'],
          stance: 'neutral',
        },
      ],
    })

    expect(sidecar.signals).toHaveLength(2)
    expect(sidecar.signals.map((signal) => signal.kind)).toEqual(expect.arrayContaining(['news', 'alert']))
    expect(sidecar.health).toMatchObject({
      status: 'degraded',
      duplicate_signal_count: 1,
      issues: ['duplicate_signals_dropped'],
    })
    expect(sidecar.health.source_kinds).toEqual(expect.arrayContaining(['news', 'alert']))
  })

  it('integrates TimesFM lanes while keeping event probability bench-only', () => {
    const sidecar = buildMarketResearchSidecar({
      market,
      snapshot: { midpoint_yes: 0.52, yes_price: 0.52 },
      signals: [],
      timesfmSidecar: {
        schema_version: 'v1',
        sidecar_name: 'timesfm_sidecar',
        run_id: 'run-timesfm',
        market_id: market.market_id,
        venue: market.venue,
        question: market.question,
        requested_mode: 'auto',
        effective_mode: 'auto',
        requested_lanes: ['microstructure', 'event_probability'],
        selected_lane: 'microstructure',
        generated_at: '2026-04-08T12:00:00.000Z',
        health: {
          healthy: true,
          status: 'healthy',
          backend: 'fixture',
          dependency_status: 'fixture_backend',
          issues: [],
          summary: 'fixture backend ready',
        },
        vendor: {
          source: 'master_snapshot',
        },
        lanes: {
          microstructure: {
            lane: 'microstructure',
            status: 'ready',
            eligible: true,
            influences_research_aggregate: true,
            comparator_id: 'candidate_timesfm_microstructure',
            comparator_kind: 'candidate_model',
            basis: 'timesfm_microstructure',
            model_family: 'timesfm-2.5',
            pipeline_id: 'timesfm-master-snapshot',
            pipeline_version: 'd720daa67865',
            probability_yes: 0.58,
            confidence: 0.63,
            probability_band: { low: 0.52, center: 0.58, high: 0.64 },
            quantiles: { p10: 0.52, p50: 0.58, p90: 0.64 },
            horizon: 24,
            summary: 'microstructure lane ready',
            rationale: 'Fixture backend forecast',
            reasons: [],
            source_refs: ['commit:d720daa6786539c2566a44464fbda1019c0a82c0'],
            metadata: {},
          },
          event_probability: {
            lane: 'event_probability',
            status: 'ready',
            eligible: true,
            influences_research_aggregate: false,
            comparator_id: 'candidate_timesfm_event_probability',
            comparator_kind: 'candidate_model',
            basis: 'timesfm_event_probability',
            model_family: 'timesfm-2.5',
            pipeline_id: 'timesfm-master-snapshot',
            pipeline_version: 'd720daa67865',
            probability_yes: 0.55,
            confidence: 0.57,
            probability_band: { low: 0.49, center: 0.55, high: 0.61 },
            quantiles: { p10: 0.49, p50: 0.55, p90: 0.61 },
            horizon: 48,
            summary: 'event lane ready',
            rationale: 'Bench-only fixture forecast',
            reasons: [],
            source_refs: ['commit:d720daa6786539c2566a44464fbda1019c0a82c0'],
            metadata: {},
          },
        },
        summary: 'TimesFM ready',
        metadata: {},
      },
    })

    expect(sidecar.health.status).toBe('degraded')
    expect(sidecar.health.issues).toContain('timesfm_sidecar_only')
    expect(sidecar.synthesis.forecaster_candidates.map((candidate) => candidate.forecaster_kind)).toEqual(
      expect.arrayContaining(['timesfm_microstructure', 'timesfm_event_probability']),
    )

    const microstructureOutput = sidecar.synthesis.independent_forecaster_outputs.find(
      (candidate) => candidate.forecaster_kind === 'timesfm_microstructure',
    )
    const eventOutput = sidecar.synthesis.independent_forecaster_outputs.find(
      (candidate) => candidate.forecaster_kind === 'timesfm_event_probability',
    )

    expect(microstructureOutput?.raw_weight).toBeGreaterThan(0)
    expect(eventOutput?.raw_weight).toBe(0)
    expect(sidecar.synthesis.weighted_aggregate_preview?.contributors).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ forecaster_kind: 'timesfm_microstructure' }),
        expect.objectContaining({ forecaster_kind: 'timesfm_event_probability' }),
      ]),
    )
  })
})
