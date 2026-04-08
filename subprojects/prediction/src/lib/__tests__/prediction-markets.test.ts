import { describe, expect, it } from 'vitest'
import {
  buildEvidencePackets,
  buildForecastPacket,
  buildRecommendationPacket,
  buildResolutionPolicy,
} from '@/lib/prediction-markets/service'
import { type MarketResearchSidecar } from '@/lib/prediction-markets/research'
import {
  decisionPacketSchema,
  evidencePacketSchema,
  forecastPacketSchema,
  marketDescriptorSchema,
  marketRecommendationPacketSchema,
  marketSnapshotSchema,
  type MarketSnapshot,
  type ResearchBridgeBundle,
} from '@/lib/prediction-markets/schemas'

function makeMarketSnapshot(overrides: Partial<MarketSnapshot> = {}): MarketSnapshot {
  const market = marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: 'mkt-123',
    question: 'Will the test pass?',
    outcomes: ['Yes', 'No'],
    active: true,
    closed: false,
    accepting_orders: true,
    restricted: false,
    liquidity_usd: 10000,
    volume_usd: 50000,
    volume_24h_usd: 1000,
    best_bid: 0.49,
    best_ask: 0.51,
    last_trade_price: 0.5,
    tick_size: 0.01,
    min_order_size: 5,
    is_binary_yes_no: true,
    source_urls: ['https://example.com/market'],
  })

  return marketSnapshotSchema.parse({
    venue: 'polymarket',
    market,
    captured_at: '2026-04-08T00:00:00.000Z',
    yes_outcome_index: 0,
    yes_token_id: 'token-yes',
    yes_price: 0.5,
    no_price: 0.5,
    midpoint_yes: 0.5,
    best_bid_yes: 0.49,
    best_ask_yes: 0.51,
    spread_bps: 200,
    book: {
      token_id: 'token-yes',
      market_condition_id: 'cond-123',
      fetched_at: '2026-04-08T00:00:00.000Z',
      best_bid: 0.49,
      best_ask: 0.51,
      last_trade_price: 0.5,
      tick_size: 0.01,
      min_order_size: 5,
      bids: [
        { price: 0.49, size: 100 },
        { price: 0.48, size: 50 },
      ],
      asks: [
        { price: 0.51, size: 100 },
        { price: 0.52, size: 25 },
      ],
      depth_near_touch: 275,
    },
    history: [
      { timestamp: 1712534400, price: 0.48 },
      { timestamp: 1712538000, price: 0.5 },
    ],
    source_urls: ['https://example.com/market', 'https://example.com/book'],
    ...overrides,
  })
}

function makeEvidencePacket(snapshot: MarketSnapshot) {
  return evidencePacketSchema.parse({
    evidence_id: `${snapshot.market.market_id}:market-data`,
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    type: 'market_data',
    title: 'Live market snapshot',
    summary: 'Test evidence packet',
    source_url: snapshot.source_urls[0],
    captured_at: snapshot.captured_at,
    content_hash: 'sha256:test',
    metadata: {},
  })
}

function makeResearchSidecar(snapshot: MarketSnapshot): MarketResearchSidecar {
  const pipelineVersionMetadata = {
    pipeline_id: 'polymarket-research-pipeline',
    pipeline_version: 'poly-025-research-v1',
    forecaster_bundle_version: 'independent-forecasters-v1',
    calibration_version: 'calibration-shrinkage-v1',
    abstention_policy_version: 'structured-abstention-v1',
    stage_versions: {
      base_rate: 'base-rate-v1',
      retrieval: 'retrieval-v1',
      independent_forecasts: 'independent-forecasts-v1',
      calibration: 'calibration-shrinkage-v1',
      abstention: 'structured-abstention-v1',
    },
  } as const

  return {
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    generated_at: '2026-04-08T08:00:00.000Z',
    pipeline_version_metadata: pipelineVersionMetadata,
    signals: [],
    evidence_packets: [],
    health: {
      status: 'healthy',
      completeness_score: 1,
      duplicate_signal_count: 0,
      issues: [],
      source_kinds: ['news'],
    },
    synthesis: {
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      question: snapshot.market.question,
      generated_at: '2026-04-08T08:00:00.000Z',
      pipeline_version_metadata: pipelineVersionMetadata,
      signal_count: 1,
      evidence_count: 1,
      signal_kinds: ['news'],
      counts_by_kind: {
        worldmonitor: 0,
        news: 1,
        alert: 0,
        manual_note: 0,
      },
      counts_by_stance: {
        supportive: 0,
        contradictory: 1,
        neutral: 0,
        unknown: 0,
      },
      top_tags: ['timeline'],
      latest_signal_at: '2026-04-08T08:00:00.000Z',
      retrieval_summary: {
        signal_ids: ['signal-1'],
        evidence_ids: ['evidence-1'],
        signal_count: 1,
        evidence_count: 1,
        latest_signal_at: '2026-04-08T08:00:00.000Z',
        counts_by_kind: {
          worldmonitor: 0,
          news: 1,
          alert: 0,
          manual_note: 0,
        },
        counts_by_stance: {
          supportive: 0,
          contradictory: 1,
          neutral: 0,
          unknown: 0,
        },
        supportive_signal_ids: [],
        contradictory_signal_ids: ['signal-1'],
        neutral_signal_ids: [],
        unknown_signal_ids: [],
        missing_signal_kinds: [],
        health_status: 'healthy',
        health_issues: [],
      },
      manual_thesis_probability_hint: undefined,
      manual_thesis_rationale_hint: undefined,
      base_rate_probability_hint: 0.5,
      base_rate_rationale_hint: 'Base rate anchored to 50.0% with 0 supportive and 1 contradictory signals.',
      base_rate_source: 'market_midpoint',
      abstention_summary: {
        recommended: true,
        reason_codes: ['no_manual_thesis'],
        reasons: ['No manual thesis has been supplied, so there is no exogenous thesis edge yet.'],
        exogenous_thesis_present: false,
      },
      key_factors: ['Base rate anchor at 50.0% from market_midpoint.'],
      counterarguments: ['Officials say the schedule remains on track.'],
      no_trade_hints: ['No manual thesis has been supplied, so there is no exogenous thesis edge yet.'],
      abstention_recommended: true,
      summary: 'Research sidecar summary for the test fixture.',
      key_points: ['Official timeline still looks intact [contradictory]: Officials say the schedule remains on track.'],
      evidence_refs: ['evidence-1'],
      external_reference_count: 0,
      external_references: [],
      market_probability_yes_hint: 0.5,
      forecast_probability_yes_hint: null,
      market_delta_bps: null,
      forecast_delta_bps: null,
      forecaster_candidates: [
        {
          forecaster_id: 'market_base_rate',
          forecaster_kind: 'market_base_rate',
          role: 'baseline',
          status: 'ready',
          label: 'Market base rate (market_midpoint)',
          probability_yes: 0.5,
          rationale: 'Base rate anchored to 50.0% with 0 supportive and 1 contradictory signals.',
          input_signal_ids: ['signal-1'],
        },
      ],
      independent_forecaster_outputs: [
        {
          forecaster_id: 'market_base_rate',
          forecaster_kind: 'market_base_rate',
          role: 'baseline',
          status: 'ready',
          label: 'Market base rate (market_midpoint)',
          probability_yes: 0.5,
          rationale: 'Base rate anchored to 50.0% with 0 supportive and 1 contradictory signals.',
          input_signal_ids: ['signal-1'],
          pipeline_version: pipelineVersionMetadata.pipeline_version,
          calibration_version: pipelineVersionMetadata.calibration_version,
          abstention_policy_version: pipelineVersionMetadata.abstention_policy_version,
          raw_weight: 1,
          normalized_weight: 1,
          calibrated_probability_yes: 0.5,
          calibration_shift_bps: 0,
        },
      ],
      weighted_aggregate_preview: {
        pipeline_version: pipelineVersionMetadata.pipeline_version,
        calibration_version: pipelineVersionMetadata.calibration_version,
        abstention_policy_version: pipelineVersionMetadata.abstention_policy_version,
        contributor_count: 1,
        usable_contributor_count: 1,
        coverage: 1,
        raw_weight_total: 1,
        normalized_weight_total: 1,
        base_rate_probability_yes: 0.5,
        weighted_probability_yes: 0.5,
        weighted_probability_yes_raw: 0.5,
        weighted_delta_bps: 0,
        weighted_raw_delta_bps: 0,
        spread_bps: 0,
        contributors: [
          {
            forecaster_id: 'market_base_rate',
            forecaster_kind: 'market_base_rate',
            role: 'baseline',
            label: 'Market base rate (market_midpoint)',
            raw_weight: 1,
            normalized_weight: 1,
            probability_yes: 0.5,
            calibrated_probability_yes: 0.5,
            contribution_bps: 0,
          },
        ],
        rationale: 'Weighted aggregate uses the market base rate only for this fixture.',
        abstention_recommended: true,
      },
      comparative_report: {
        market_only: {
          probability_yes: 0.5,
          delta_bps_vs_market_only: 0,
          rationale: 'Base rate stays aligned with the market-only baseline.',
        },
        aggregate: {
          probability_yes: 0.5,
          delta_bps_vs_market_only: 0,
          rationale: 'Aggregate remains identical to the market-only baseline for this fixture.',
          coverage: 1,
          contributor_count: 1,
          usable_contributor_count: 1,
        },
        forecast: {
          forecast_probability_yes: null,
          delta_bps_vs_market_only: null,
          delta_bps_vs_aggregate: null,
          rationale: 'No exogenous forecast override is present for the fixture.',
        },
        abstention: {
          recommended: true,
          blocks_forecast: false,
          reason_codes: ['no_manual_thesis'],
          rationale: 'No manual thesis is present, so the fixture stays market-only.',
        },
        summary: 'Comparative report keeps the fixture in market_only mode because no exogenous forecast is present.',
      },
      calibration_snapshot: {
        snapshot_id: 'snapshot-1',
        snapshot_version: pipelineVersionMetadata.calibration_version,
        pipeline_version: pipelineVersionMetadata.pipeline_version,
        calibration_version: pipelineVersionMetadata.calibration_version,
        abstention_policy_version: pipelineVersionMetadata.abstention_policy_version,
        sample_size: 1,
        usable_contributor_count: 1,
        base_rate_probability_yes: 0.5,
        weighted_probability_yes: 0.5,
        weighted_probability_yes_raw: 0.5,
        calibration_gap_bps: 0,
        mean_abs_shift_bps: 0,
        sharpness: 1,
        coverage: 1,
        notes: ['Single baseline contributor for the fixture.'],
      },
      abstention_policy: {
        policy_id: 'structured-abstention',
        policy_version: pipelineVersionMetadata.abstention_policy_version,
        recommended: true,
        blocks_forecast: false,
        trigger_codes: ['no_manual_thesis'],
        rationale: 'No manual thesis is present, so the fixture stays market-only.',
        thresholds: {
          minimum_signal_count: 1,
          minimum_supportive_margin_bps: 250,
          minimum_manual_thesis_probability: 0.55,
          minimum_contributor_coverage: 0.5,
        },
      },
      health: {
        status: 'healthy',
        completeness_score: 1,
        duplicate_signal_count: 0,
        issues: [],
        source_kinds: ['news'],
      },
    } as MarketResearchSidecar['synthesis'],
  } as unknown as MarketResearchSidecar
}

describe('prediction markets service helpers', () => {
  it('buildResolutionPolicy blocks inactive markets and marks non-binary markets for manual review', () => {
    const inactiveSnapshot = makeMarketSnapshot({
      market: marketDescriptorSchema.parse({
        venue: 'polymarket',
        venue_type: 'execution-equivalent',
        market_id: 'inactive-market',
        question: 'Inactive?',
        outcomes: ['Yes', 'No'],
        active: false,
        closed: false,
        accepting_orders: false,
        restricted: false,
        liquidity_usd: 1000,
        volume_usd: 5000,
        volume_24h_usd: 100,
        best_bid: 0.4,
        best_ask: 0.6,
        last_trade_price: 0.5,
        tick_size: 0.01,
        min_order_size: 5,
        is_binary_yes_no: true,
        source_urls: ['https://example.com/inactive'],
      }),
      best_bid_yes: 0.4,
      best_ask_yes: 0.6,
      yes_price: 0.5,
      no_price: 0.5,
      midpoint_yes: 0.5,
      spread_bps: 2000,
    })

    const inactivePolicy = buildResolutionPolicy(inactiveSnapshot)
    expect(inactivePolicy.status).toBe('blocked')
    expect(inactivePolicy.reasons).toContain('market is not active')
    expect(inactivePolicy.reasons).toContain('market is not accepting orders')

    const nonBinarySnapshot = makeMarketSnapshot({
      market: marketDescriptorSchema.parse({
        venue: 'polymarket',
        venue_type: 'execution-equivalent',
        market_id: 'non-binary-market',
        question: 'Three outcomes?',
        outcomes: ['A', 'B', 'C'],
        active: true,
        closed: false,
        accepting_orders: true,
        restricted: false,
        liquidity_usd: 1000,
        volume_usd: 5000,
        volume_24h_usd: 100,
        best_bid: 0.3,
        best_ask: 0.4,
        last_trade_price: 0.35,
        tick_size: 0.01,
        min_order_size: 5,
        is_binary_yes_no: false,
        source_urls: ['https://example.com/non-binary'],
      }),
      best_bid_yes: 0.3,
      best_ask_yes: 0.4,
      yes_price: 0.35,
      no_price: 0.65,
      midpoint_yes: 0.35,
      spread_bps: 1000,
    })

    const nonBinaryPolicy = buildResolutionPolicy(nonBinarySnapshot)
    expect(nonBinaryPolicy.status).not.toBe('eligible')
    expect(nonBinaryPolicy.manual_review_required).toBe(true)
    expect(nonBinaryPolicy.reasons).toContain('market is not a binary yes/no contract')
  })

  it('buildForecastPacket uses the market midpoint without a manual thesis', () => {
    const snapshot = makeMarketSnapshot()
    const forecast = buildForecastPacket({
      snapshot,
      evidencePackets: [makeEvidencePacket(snapshot)],
    })

    expect(forecastPacketSchema.parse(forecast).basis).toBe('market_midpoint')
    expect(forecast.probability_yes).toBe(0.5)
    expect(forecast.evidence_refs).toHaveLength(1)
    expect(forecast).toMatchObject({
      comparator_id: 'candidate_market_midpoint',
      comparator_kind: 'candidate_model',
      pipeline_id: 'forecast-market',
      pipeline_version: 'baseline-v0',
      abstention_policy: 'baseline-confidence-policy',
    })
    expect(forecast.rationale).toContain(
      'Comparator: candidate_market_midpoint (candidate_model) on the market_midpoint basis.',
    )
    expect(forecast.rationale).toContain('Pipeline: forecast-market@baseline-v0.')
    expect(forecast.rationale).toContain('Abstention policy: baseline-confidence-policy.')
  })

  it('buildForecastPacket switches to manual_thesis when a thesis probability is provided', () => {
    const snapshot = makeMarketSnapshot()
    const forecast = buildForecastPacket({
      snapshot,
      evidencePackets: [makeEvidencePacket(snapshot)],
      thesisProbability: 0.74,
      thesisRationale: 'Manual conviction from external evidence',
    })

    expect(forecastPacketSchema.parse(forecast).basis).toBe('manual_thesis')
    expect(forecast.probability_yes).toBe(0.74)
    expect(forecast.rationale).toContain('Manual conviction')
    expect(forecast).toMatchObject({
      comparator_id: 'candidate_manual_thesis',
      comparator_kind: 'candidate_model',
      pipeline_id: 'forecast-market',
      pipeline_version: 'baseline-v0',
      abstention_policy: 'baseline-confidence-policy',
    })
  })

  it('buildForecastPacket incorporates research sidecar base-rate and no-trade hints', () => {
    const snapshot = makeMarketSnapshot()
    const researchSidecar = makeResearchSidecar(snapshot)

    const forecast = buildForecastPacket({
      snapshot,
      evidencePackets: [makeEvidencePacket(snapshot)],
      researchSidecar,
    })

    expect(forecastPacketSchema.parse(forecast).basis).toBe('market_midpoint')
    expect(forecast.probability_yes).toBe(0.5)
    expect(forecast.rationale).toContain('Base rate anchor:')
    expect(forecast.rationale).toContain('Forecaster candidates:')
    expect(forecast.rationale).toContain('Counterarguments:')
    expect(forecast.rationale).toContain('No-trade hints:')
    expect(forecast.rationale).toContain('Comparator: candidate_market_midpoint (candidate_model) on the market_midpoint basis.')
    expect(forecast.rationale).toContain('Pipeline: forecast-market@baseline-v0.')
    expect(forecast.rationale).toContain('Research retrieval:')
    expect(forecast.rationale).toContain('Research abstention cues:')
    expect(forecast.rationale).toContain(
      'Abstention policy: structured-abstention.',
    )
    expect(forecast.rationale).toContain(
      'Policy metadata: version=structured-abstention-v1; recommendation=abstain; blocks_forecast=false; triggers=no_manual_thesis; detail=No manual thesis is present, so the fixture stays market-only.',
    )
    expect(forecast.abstention_policy).toBe('structured-abstention')
    expect(forecast.abstention_reason).toBe('policy_threshold')
  })

  it('buildForecastPacket treats a research-driven thesis as manual_thesis rather than market_midpoint', () => {
    const snapshot = makeMarketSnapshot({
      best_bid_yes: 0.58,
      best_ask_yes: 0.6,
      yes_price: 0.59,
      no_price: 0.41,
      midpoint_yes: 0.59,
      spread_bps: 200,
      book: {
        token_id: 'token-yes',
        market_condition_id: 'cond-123',
        fetched_at: '2026-04-08T00:00:00.000Z',
        best_bid: 0.58,
        best_ask: 0.6,
        last_trade_price: 0.59,
        tick_size: 0.01,
        min_order_size: 5,
        bids: [{ price: 0.58, size: 100 }],
        asks: [{ price: 0.6, size: 100 }],
        depth_near_touch: 200,
      },
    })
    const researchSidecar = makeResearchSidecar(snapshot)
    const manualThesisProbability = 0.74
    const manualThesisRationale = 'External manual thesis now moves the fair value away from the midpoint.'

    const forecast = buildForecastPacket({
      snapshot,
      evidencePackets: [makeEvidencePacket(snapshot)],
      thesisProbability: manualThesisProbability,
      thesisRationale: manualThesisRationale,
      researchSidecar: {
        ...researchSidecar,
        synthesis: {
          ...researchSidecar.synthesis,
          manual_thesis_probability_hint: manualThesisProbability,
          manual_thesis_rationale_hint: manualThesisRationale,
          abstention_summary: {
            ...researchSidecar.synthesis.abstention_summary,
            exogenous_thesis_present: true,
            manual_thesis_probability_hint: manualThesisProbability,
            recommended: false,
            reason_codes: [],
            reasons: [],
          },
          weighted_aggregate_preview: {
            ...researchSidecar.synthesis.weighted_aggregate_preview,
            abstention_recommended: false,
          },
          abstention_policy: {
            ...researchSidecar.synthesis.abstention_policy,
            recommended: false,
            blocks_forecast: false,
            trigger_codes: [],
            rationale: 'Manual thesis clears abstention for this fixture.',
          },
        },
      },
    })

    const recommendation = buildRecommendationPacket({
      snapshot,
      resolutionPolicy: buildResolutionPolicy(snapshot),
      forecast,
      minEdgeBps: 150,
      maxSpreadBps: 300,
    })

    expect(forecastPacketSchema.parse(forecast).basis).toBe('manual_thesis')
    expect(forecast.comparator_id).toBe('candidate_manual_thesis')
    expect(forecast.probability_yes).toBe(0.74)
    expect(forecast.rationale).toContain('External manual thesis now moves the fair value away from the midpoint.')
    expect(recommendation.action).toBe('bet')
    expect(recommendation.side).toBe('yes')
    expect(recommendation.rationale).toContain('Bet yes now:')
    expect(recommendation.why_now.join(' ')).toContain('Manual thesis sets fair value to 74.0%')
    expect(recommendation.why_not_now).not.toContain(
      'Current fair value is still derived from the market itself, so no exogenous edge is proven yet.',
    )
  })

  it('buildForecastPacket prefers weighted aggregate, independent outputs, and policy metadata when available', () => {
    const snapshot = makeMarketSnapshot()
    const researchSidecar = makeResearchSidecar(snapshot)
    const weightedResearchSidecar: MarketResearchSidecar = {
      ...researchSidecar,
      synthesis: {
        ...researchSidecar.synthesis,
        abstention_summary: {
          ...researchSidecar.synthesis.abstention_summary,
          recommended: false,
          reason_codes: ['manual_review'],
          reasons: ['Structured policy keeps the blended forecast under review during rollout.'],
        },
        independent_forecaster_outputs: [
          researchSidecar.synthesis.independent_forecaster_outputs[0],
          {
            ...researchSidecar.synthesis.independent_forecaster_outputs[0],
            forecaster_id: 'external_consensus',
            forecaster_kind: 'external_reference',
            role: 'candidate',
            status: 'ready',
            label: 'External consensus',
            probability_yes: 0.76,
            rationale: 'External consensus supports a higher YES probability.',
            input_signal_ids: ['signal-2'],
            raw_weight: 1,
            normalized_weight: 1,
            calibrated_probability_yes: 0.76,
            calibration_shift_bps: 0,
          },
        ],
        weighted_aggregate_preview: {
          ...researchSidecar.synthesis.weighted_aggregate_preview,
          contributor_count: 2,
          usable_contributor_count: 2,
          coverage: 1,
          raw_weight_total: 2,
          normalized_weight_total: 2,
          weighted_probability_yes: 0.63,
          weighted_probability_yes_raw: 0.63,
          weighted_delta_bps: 1300,
          weighted_raw_delta_bps: 1300,
          rationale: 'Weighted aggregate blends the calibrated forecasters above base rate.',
          abstention_recommended: false,
          contributors: [
            researchSidecar.synthesis.weighted_aggregate_preview.contributors[0],
            {
              forecaster_id: 'external_consensus',
              forecaster_kind: 'external_reference',
              role: 'candidate',
              label: 'External consensus',
              raw_weight: 1,
              normalized_weight: 1,
              probability_yes: 0.76,
              calibrated_probability_yes: 0.76,
              contribution_bps: 2600,
            },
          ],
        },
        abstention_policy: {
          ...researchSidecar.synthesis.abstention_policy,
          recommended: true,
          blocks_forecast: true,
          trigger_codes: ['manual_review'],
          rationale: 'Policy keeps the packet in review during rollout.',
        },
      },
    }

    const forecast = buildForecastPacket({
      snapshot,
      evidencePackets: [makeEvidencePacket(snapshot)],
      researchSidecar: weightedResearchSidecar,
    })

    expect(forecastPacketSchema.parse(forecast).basis).toBe('market_midpoint')
    expect(forecast.probability_yes).toBe(0.63)
    expect(forecast.comparator_id).toBe('candidate_research_aggregate')
    expect(forecast.abstention_policy).toBe('structured-abstention')
    expect(forecast.abstention_reason).toBe('policy_threshold')
    expect(forecast.rationale).toContain(
      'Comparator: candidate_research_aggregate (candidate_model) on the market_midpoint basis.',
    )
    expect(forecast.rationale).toContain('Weighted aggregate preview: 63.0%')
    expect(forecast.rationale).toContain(
      'Independent forecaster outputs: 2/2 usable output(s); calibrated blend 63.0%; raw blend 63.0%.',
    )
    expect(forecast.rationale).toContain('Abstention policy: structured-abstention.')
    expect(forecast.rationale).toContain(
      'Policy metadata: version=structured-abstention-v1; recommendation=abstain; blocks_forecast=true; triggers=manual_review; detail=Policy keeps the packet in review during rollout.',
    )
    expect(forecast.rationale).toContain('Weighted contributors:')
  })

  it('buildRecommendationPacket lets a research-driven forecast claim edge when abstention is cleared', () => {
    const snapshot = makeMarketSnapshot()
    const researchSidecar = makeResearchSidecar(snapshot)
    const researchDrivenSidecar: MarketResearchSidecar = {
      ...researchSidecar,
      synthesis: {
        ...researchSidecar.synthesis,
        abstention_summary: {
          ...researchSidecar.synthesis.abstention_summary,
          recommended: false,
          reason_codes: [],
          reasons: [],
        },
        independent_forecaster_outputs: [
          researchSidecar.synthesis.independent_forecaster_outputs[0],
          {
            ...researchSidecar.synthesis.independent_forecaster_outputs[0],
            forecaster_id: 'external_consensus',
            forecaster_kind: 'external_reference',
            role: 'candidate',
            status: 'ready',
            label: 'External consensus',
            probability_yes: 0.76,
            rationale: 'External consensus supports a higher YES probability.',
            input_signal_ids: ['signal-2'],
            raw_weight: 1,
            normalized_weight: 1,
            calibrated_probability_yes: 0.76,
            calibration_shift_bps: 0,
          },
        ],
        weighted_aggregate_preview: {
          ...researchSidecar.synthesis.weighted_aggregate_preview,
          contributor_count: 2,
          usable_contributor_count: 2,
          coverage: 1,
          raw_weight_total: 2,
          normalized_weight_total: 2,
          weighted_probability_yes: 0.63,
          weighted_probability_yes_raw: 0.63,
          weighted_delta_bps: 1300,
          weighted_raw_delta_bps: 1300,
          rationale: 'Weighted aggregate blends the calibrated forecasters above base rate.',
          abstention_recommended: false,
          contributors: [
            researchSidecar.synthesis.weighted_aggregate_preview.contributors[0],
            {
              forecaster_id: 'external_consensus',
              forecaster_kind: 'external_reference',
              role: 'candidate',
              label: 'External consensus',
              raw_weight: 1,
              normalized_weight: 1,
              probability_yes: 0.76,
              calibrated_probability_yes: 0.76,
              contribution_bps: 2600,
            },
          ],
        },
        abstention_policy: {
          ...researchSidecar.synthesis.abstention_policy,
          recommended: false,
          blocks_forecast: false,
          trigger_codes: [],
          rationale: 'Policy clears the aggregate forecast for recommendation.',
        },
      },
    }

    const forecast = buildForecastPacket({
      snapshot,
      evidencePackets: [makeEvidencePacket(snapshot)],
      researchSidecar: researchDrivenSidecar,
    })

    const recommendation = buildRecommendationPacket({
      snapshot,
      resolutionPolicy: buildResolutionPolicy(snapshot),
      forecast,
      minEdgeBps: 150,
      maxSpreadBps: 300,
    })

    expect(forecast.comparator_id).toBe('candidate_research_aggregate')
    expect(recommendation.action).toBe('bet')
    expect(recommendation.side).toBe('yes')
    expect(recommendation.edge_bps).toBeGreaterThanOrEqual(150)
    expect(recommendation.rationale).toContain('Bet yes now:')
    expect(recommendation.why_now.join(' ')).toContain('Research-driven forecast sets fair value to 63.0%')
    expect(recommendation.why_not_now).not.toContain(
      'Current fair value is still derived from the market itself, so no exogenous edge is proven yet.',
    )
  })

  it('buildRecommendationPacket waits when a research-driven forecast is held by abstention', () => {
    const snapshot = makeMarketSnapshot()
    const researchSidecar = makeResearchSidecar(snapshot)
    const abstainedResearchSidecar: MarketResearchSidecar = {
      ...researchSidecar,
      synthesis: {
        ...researchSidecar.synthesis,
        abstention_summary: {
          ...researchSidecar.synthesis.abstention_summary,
          recommended: false,
          reason_codes: ['manual_review'],
          reasons: ['Research policy keeps this forecast under review.'],
        },
        independent_forecaster_outputs: [
          researchSidecar.synthesis.independent_forecaster_outputs[0],
          {
            ...researchSidecar.synthesis.independent_forecaster_outputs[0],
            forecaster_id: 'external_consensus',
            forecaster_kind: 'external_reference',
            role: 'candidate',
            status: 'ready',
            label: 'External consensus',
            probability_yes: 0.76,
            rationale: 'External consensus supports a higher YES probability.',
            input_signal_ids: ['signal-2'],
            raw_weight: 1,
            normalized_weight: 1,
            calibrated_probability_yes: 0.76,
            calibration_shift_bps: 0,
          },
        ],
        weighted_aggregate_preview: {
          ...researchSidecar.synthesis.weighted_aggregate_preview,
          contributor_count: 2,
          usable_contributor_count: 2,
          coverage: 1,
          raw_weight_total: 2,
          normalized_weight_total: 2,
          weighted_probability_yes: 0.63,
          weighted_probability_yes_raw: 0.63,
          weighted_delta_bps: 1300,
          weighted_raw_delta_bps: 1300,
          rationale: 'Weighted aggregate blends the calibrated forecasters above base rate.',
          abstention_recommended: false,
          contributors: [
            researchSidecar.synthesis.weighted_aggregate_preview.contributors[0],
            {
              forecaster_id: 'external_consensus',
              forecaster_kind: 'external_reference',
              role: 'candidate',
              label: 'External consensus',
              raw_weight: 1,
              normalized_weight: 1,
              probability_yes: 0.76,
              calibrated_probability_yes: 0.76,
              contribution_bps: 2600,
            },
          ],
        },
        abstention_policy: {
          ...researchSidecar.synthesis.abstention_policy,
          recommended: true,
          blocks_forecast: true,
          trigger_codes: ['manual_review'],
          rationale: 'Policy keeps the packet in review during rollout.',
        },
      },
    }

    const forecast = buildForecastPacket({
      snapshot,
      evidencePackets: [makeEvidencePacket(snapshot)],
      researchSidecar: abstainedResearchSidecar,
    })

    const recommendation = buildRecommendationPacket({
      snapshot,
      resolutionPolicy: buildResolutionPolicy(snapshot),
      forecast,
      minEdgeBps: 150,
      maxSpreadBps: 300,
    })

    expect(forecast.comparator_id).toBe('candidate_research_aggregate')
    expect(forecast.abstention_reason).toBe('policy_threshold')
    expect(recommendation.action).toBe('wait')
    expect(recommendation.risk_flags).toContain('forecast_abstention')
    expect(recommendation.reasons).toContain(
      'Forecast abstention policy is holding this packet at policy_threshold.',
    )
    expect(recommendation.why_not_now).toContain(
      'Forecast abstention policy currently holds the packet at policy_threshold.',
    )
  })

  it('buildForecastPacket uses research bridge pipeline metadata when available', () => {
    const snapshot = makeMarketSnapshot()
    const researchBridge = {
      classification: 'market_only',
      pipeline: {
        pipeline_id: 'bridge-forecast',
        pipeline_version: 'bridge-v1',
      },
      abstention_policy: {
        policy_id: 'bridge-abstention',
        rationale: 'Prefer abstention when evidence is thin.',
      },
    } as unknown as ResearchBridgeBundle

    const forecast = buildForecastPacket({
      snapshot,
      evidencePackets: [makeEvidencePacket(snapshot)],
      researchBridge,
    })

    expect(forecast.pipeline_id).toBe('bridge-forecast')
    expect(forecast.pipeline_version).toBe('bridge-v1')
    expect(forecast.abstention_policy).toBe('bridge-abstention')
    expect(forecast.rationale).toContain(
      'Comparator: candidate_market_midpoint (candidate_model) on the market_midpoint basis.',
    )
    expect(forecast.rationale).toContain('Pipeline: bridge-forecast@bridge-v1.')
    expect(forecast.rationale).toContain('Abstention policy: bridge-abstention.')
  })

  it('buildEvidencePackets bridges decision packets into system evidence', () => {
    const snapshot = makeMarketSnapshot()
    const decisionPacket = decisionPacketSchema.parse({
      correlation_id: 'decision-123',
      question: 'Will the market test stay aligned?',
      topic: 'prediction_markets',
      objective: 'Bridge deliberation into execution.',
      probability_estimate: 0.67,
      confidence_band: [0.61, 0.72],
      scenarios: ['base case'],
      risks: ['stale_data'],
      recommendation: 'bet yes only if execution stays conservative',
      rationale_summary: 'Committee view is modestly above market.',
      artifacts: ['decision-artifact-1'],
      mode_used: 'committee',
      engine_used: 'oaswarm',
      runtime_used: 'prediction_markets',
    })

    const evidencePackets = buildEvidencePackets({
      snapshot,
      thesisProbability: decisionPacket.probability_estimate,
      thesisRationale: 'Committee view is modestly above market.',
      decisionPacket,
    })

    expect(evidencePackets.map((packet) => packet.type)).toEqual([
      'market_data',
      'orderbook',
      'history',
      'system_note',
      'manual_thesis',
    ])
    expect(evidencePackets.find((packet) => packet.type === 'system_note')).toMatchObject({
      title: 'Decision packet bridge',
      metadata: expect.objectContaining({
        correlation_id: 'decision-123',
        probability_estimate: 0.67,
        recommendation: 'bet yes only if execution stays conservative',
      }),
    })
  })

  it('buildRecommendationPacket stays conservative for market-derived forecasts', () => {
    const snapshot = makeMarketSnapshot()
    const resolutionPolicy = buildResolutionPolicy(snapshot)
    const forecast = buildForecastPacket({
      snapshot,
      evidencePackets: [makeEvidencePacket(snapshot)],
    })

    const recommendation = buildRecommendationPacket({
      snapshot,
      resolutionPolicy,
      forecast,
    })

    expect(marketRecommendationPacketSchema.parse(recommendation).action).toBe('no_trade')
    expect(recommendation.side).toBeNull()
    expect(recommendation.edge_bps).toBe(0)
    expect(recommendation.rationale).toContain('No trade:')
    expect(recommendation.why_not_now).toContain(
      'Current fair value is still derived from the market itself, so no exogenous edge is proven yet.',
    )
    expect(recommendation.watch_conditions).toContain(
      'Re-run after a manual thesis or external evidence changes fair value away from the current market midpoint.',
    )
    expect(Date.parse(recommendation.next_review_at)).toBeGreaterThan(Date.parse(recommendation.produced_at))
  })

  it('buildRecommendationPacket returns wait when the spread is too wide', () => {
    const snapshot = makeMarketSnapshot({
      spread_bps: 900,
      best_bid_yes: 0.35,
      best_ask_yes: 0.44,
      yes_price: 0.395,
      no_price: 0.605,
      midpoint_yes: 0.395,
      book: {
        token_id: 'token-yes',
        market_condition_id: 'cond-123',
        fetched_at: '2026-04-08T00:00:00.000Z',
        best_bid: 0.35,
        best_ask: 0.44,
        last_trade_price: 0.395,
        tick_size: 0.01,
        min_order_size: 5,
        bids: [{ price: 0.35, size: 100 }],
        asks: [{ price: 0.44, size: 100 }],
        depth_near_touch: 200,
      },
    })
    const resolutionPolicy = buildResolutionPolicy(snapshot)
    const forecast = buildForecastPacket({
      snapshot,
      evidencePackets: [makeEvidencePacket(snapshot)],
    })

    const recommendation = buildRecommendationPacket({
      snapshot,
      resolutionPolicy,
      forecast,
      maxSpreadBps: 300,
    })

    expect(recommendation.action).toBe('wait')
    expect(recommendation.risk_flags).toContain('wide_spread')
    expect(recommendation.rationale).toContain('Wait:')
    expect(recommendation.why_not_now).toContain('Spread 900 bps is wider than the 300 bps budget.')
    expect(recommendation.watch_conditions).toContain(
      'Re-run when spread compresses to 300 bps or tighter.',
    )
    expect(Date.parse(recommendation.next_review_at)).toBeGreaterThan(Date.parse(recommendation.produced_at))
  })

  it('buildRecommendationPacket returns bet yes when manual thesis creates enough edge', () => {
    const snapshot = makeMarketSnapshot({
      best_bid_yes: 0.58,
      best_ask_yes: 0.60,
      yes_price: 0.59,
      no_price: 0.41,
      midpoint_yes: 0.59,
      spread_bps: 200,
      book: {
        token_id: 'token-yes',
        market_condition_id: 'cond-123',
        fetched_at: '2026-04-08T00:00:00.000Z',
        best_bid: 0.58,
        best_ask: 0.60,
        last_trade_price: 0.59,
        tick_size: 0.01,
        min_order_size: 5,
        bids: [{ price: 0.58, size: 100 }],
        asks: [{ price: 0.60, size: 100 }],
        depth_near_touch: 200,
      },
    })
    const resolutionPolicy = buildResolutionPolicy(snapshot)
    const forecast = buildForecastPacket({
      snapshot,
      evidencePackets: [makeEvidencePacket(snapshot)],
      thesisProbability: 0.8,
      thesisRationale: 'Manual thesis with a strong upside edge',
    })

    const recommendation = buildRecommendationPacket({
      snapshot,
      resolutionPolicy,
      forecast,
      minEdgeBps: 150,
      maxSpreadBps: 300,
    })

    expect(marketRecommendationPacketSchema.parse(recommendation).action).toBe('bet')
    expect(recommendation.side).toBe('yes')
    expect(recommendation.edge_bps).toBeGreaterThanOrEqual(150)
    expect(recommendation.rationale).toContain('Bet yes now:')
    expect(recommendation.why_now).toContain(
      `Manual thesis sets fair value to 80.0% with ${(recommendation.confidence * 100).toFixed(1)}% confidence.`,
    )
    expect(recommendation.why_now).toContain(
      'Executable YES edge is 2000 bps versus ask 60.0%.',
    )
    expect(recommendation.watch_conditions).toContain(
      'Reassess if the YES edge falls below 150 bps or if spread widens beyond 300 bps.',
    )
    expect(Date.parse(recommendation.next_review_at)).toBeGreaterThan(Date.parse(recommendation.produced_at))
  })
})
