import { describe, expect, it } from 'vitest'
import {
  approvalTradeTicketSchema,
  capitalLedgerSnapshotSchema,
  crossVenueMatchSchema,
  decisionPacketSchema,
  predictionMarketBudgetsSchema,
  predictionMarketPerformanceBudgetSchema,
  predictionMarketResearchPipelineSummarySchema,
  predictionMarketResearchPipelineStageSchema,
  predictionMarketResearchPipelineTraceSchema,
  predictionMarketProvenanceBundleSchema,
  predictionMarketsAdviceRequestSchema,
  predictionMarketsQuerySchema,
  predictionMarketsReplayRequestSchema,
  tradeIntentSchema,
  venueCapabilitiesSchema,
  venueHealthSnapshotSchema,
} from '@/lib/prediction-markets/schemas'

describe('prediction markets request schemas', () => {
  it('applies defaults for query requests', () => {
    const parsed = predictionMarketsQuerySchema.parse({})

    expect(parsed).toEqual({
      venue: 'polymarket',
      limit: 20,
    })
  })

  it('rejects query limits above the supported maximum', () => {
    const result = predictionMarketsQuerySchema.safeParse({
      limit: 101,
    })

    expect(result.success).toBe(false)
    if (result.success) return

    expect(result.error.issues[0]?.path).toEqual(['limit'])
  })

  it('accepts advice requests addressed by slug only', () => {
    const parsed = predictionMarketsAdviceRequestSchema.parse({
      slug: 'will-btc-hit-100k',
      thesis_probability: 0.62,
      thesis_rationale: 'External evidence supports a modest edge.',
      min_edge_bps: 75,
      max_spread_bps: 250,
      history_limit: 48,
    })

    expect(parsed).toMatchObject({
      venue: 'polymarket',
      slug: 'will-btc-hit-100k',
      thesis_probability: 0.62,
      min_edge_bps: 75,
      max_spread_bps: 250,
      history_limit: 48,
    })
  })

  it('normalizes predict-deep request aliases and variant tags', () => {
    const parsed = predictionMarketsAdviceRequestSchema.parse({
      market_id: '12345',
      request_mode: 'predict-deep',
      response_variant: 'research-heavy',
      variant_tags: ['polfish', 'supercompact'],
    })

    expect(parsed).toMatchObject({
      market_id: '12345',
      request_mode: 'predict_deep',
      response_variant: 'research_heavy',
      variant_tags: ['polfish', 'supercompact'],
    })
  })

  it('accepts optional research signals for sidecar-backed market research', () => {
    const parsed = predictionMarketsAdviceRequestSchema.parse({
      market_id: '12345',
      research_signals: [
        {
          signal_type: 'world_monitor',
          headline: 'Breaking update from field observers',
          message: 'New evidence may change the event timing.',
          published_at: '2026-04-08T10:30:00.000Z',
        },
      ],
    })

    expect(parsed.research_signals).toEqual([
      {
        signal_type: 'world_monitor',
        headline: 'Breaking update from field observers',
        message: 'New evidence may change the event timing.',
        published_at: '2026-04-08T10:30:00.000Z',
      },
    ])
  })

  it('accepts TimesFM mode and lane options on advice requests', () => {
    const parsed = predictionMarketsAdviceRequestSchema.parse({
      market_id: '12345',
      request_mode: 'predict-deep',
      timesfm_mode: 'required',
      timesfm_lanes: ['microstructure', 'event_probability'],
    })

    expect(parsed).toMatchObject({
      market_id: '12345',
      request_mode: 'predict_deep',
      timesfm_mode: 'required',
      timesfm_lanes: ['microstructure', 'event_probability'],
    })
  })

  it('accepts optional evaluation history for local calibration replay', () => {
    const parsed = predictionMarketsAdviceRequestSchema.parse({
      market_id: '12345',
      evaluation_history: [
        {
          evaluation_id: 'eval-001',
          question_id: 'question-001',
          market_id: 'BTC / Jun 2026',
          venue: 'polymarket',
          cutoff_at: '2026-04-01T00:00:00.000Z',
          forecast_probability: 0.7,
          market_baseline_probability: 0.6,
          resolved_outcome: true,
          brier_score: 0.09,
          log_loss: 0.356675,
          ece_bucket: '60_80',
          abstain_flag: false,
          basis: 'manual_thesis',
          comparator_id: 'candidate_manual_thesis',
          comparator_kind: 'candidate_model',
          comparator_role: 'candidate',
          pipeline_id: 'forecast-market',
          pipeline_version: 'baseline-v0',
        },
      ],
    })

    expect(parsed.evaluation_history).toEqual([
      expect.objectContaining({
        evaluation_id: 'eval-001',
        market_id: 'BTC / Jun 2026',
        resolved_outcome: true,
      }),
    ])
  })

  it('accepts and normalizes an embedded decision packet on advice requests', () => {
    const parsed = predictionMarketsAdviceRequestSchema.parse({
      market_id: '12345',
      decision_packet: {
        correlation_id: 'corr-123',
        question: 'Will the embedded contract stay green?',
        topic: 'quality',
        objective: 'validate the advisory bridge',
        probability_estimate: 0.74,
        confidence_band: [0.68, 0.8],
        scenarios: ['green', { label: 'amber', summary: 'monitor for drift' }],
        risks: ['stale_data'],
        recommendation: 'continue',
        rationale_summary: 'The embedded packet should reuse the canonical contract.',
        artifacts: ['artifact-1'],
        mode_used: 'committee',
        engine_used: 'baseline-v0',
        runtime_used: 'prediction_markets',
      },
    })

    expect(parsed.decision_packet).toMatchObject({
      correlation_id: 'corr-123',
      probability_estimate: 0.74,
      confidence_band: { low: 0.68, high: 0.8 },
      scenarios: [
        { label: 'green', summary: 'green' },
        { label: 'amber', summary: 'monitor for drift' },
      ],
      risks: [
        {
          label: 'stale_data',
          severity: 'medium',
          summary: 'stale_data',
        },
      ],
      artifacts: [
        {
          artifact_id: 'artifact-1',
          artifact_type: 'external_reference',
        },
      ],
    })
  })

  it('rejects advice requests when neither market_id nor slug is provided', () => {
    const result = predictionMarketsAdviceRequestSchema.safeParse({
      thesis_probability: 0.55,
    })

    expect(result.success).toBe(false)
    if (result.success) return

    expect(result.error.issues.some((issue) => issue.path.join('.') === 'market_id')).toBe(true)
  })

  it('rejects advice requests with thesis probabilities outside [0, 1]', () => {
    const result = predictionMarketsAdviceRequestSchema.safeParse({
      market_id: '12345',
      thesis_probability: 1.1,
    })

    expect(result.success).toBe(false)
    if (result.success) return

    expect(result.error.issues[0]?.path).toEqual(['thesis_probability'])
  })

  it('trims replay run ids and rejects blank ones', () => {
    expect(predictionMarketsReplayRequestSchema.parse({ run_id: ' run-123 ' })).toEqual({
      run_id: 'run-123',
    })

    const result = predictionMarketsReplayRequestSchema.safeParse({ run_id: '   ' })
    expect(result.success).toBe(false)
    if (result.success) return

    expect(result.error.issues[0]?.path).toEqual(['run_id'])
  })

  it('parses the new planning and contract schemas', () => {
    const decision = decisionPacketSchema.parse({
      correlation_id: 'corr-123',
      question: 'Will the test remain green?',
      topic: 'quality',
      objective: 'validate the contract layer',
      probability_estimate: 0.73,
      confidence_band: [0.68, 0.78],
      scenarios: ['green', 'yellow'],
      risks: ['stale_data'],
      recommendation: 'continue',
      rationale_summary: 'Minimal contract is sufficient for this phase.',
      artifacts: ['artifact-1'],
      mode_used: 'committee',
      engine_used: 'baseline-v0',
      runtime_used: 'prediction_markets',
    })

    const budgets = predictionMarketBudgetsSchema.parse({
      snapshot_freshness_ms: 30_000,
      decision_latency_ms: 750,
    })
    const sameBudgetsViaAlias = predictionMarketPerformanceBudgetSchema.parse({
      snapshot_freshness_budget_ms: 30_000,
      decision_latency_budget_ms: 750,
      fetch_latency_budget_ms: 400,
      max_retries: 2,
    })

    const capabilities = venueCapabilitiesSchema.parse({
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      supports_discovery: true,
      supports_orderbook: true,
      supports_trades: true,
      supports_positions: false,
      supports_execution: false,
      supports_websocket: true,
      automation_constraints: 'manual review before live',
    })

    expect(decision.confidence_band).toEqual({ low: 0.68, high: 0.78 })
    expect(decision.scenarios).toEqual([
      { label: 'green', summary: 'green' },
      { label: 'yellow', summary: 'yellow' },
    ])
    expect(decision.risks[0]).toMatchObject({
      label: 'stale_data',
      severity: 'medium',
      summary: 'stale_data',
    })
    expect(decision.artifacts[0]).toEqual({
      artifact_id: 'artifact-1',
      artifact_type: 'external_reference',
    })
    const provenance = predictionMarketProvenanceBundleSchema.parse({
      run_id: 'run-123',
      venue: 'polymarket',
      market_id: '12345',
      generated_at: '2026-04-08T00:00:00.000Z',
      provenance_refs: ['tweet:t-1', 'run:run-123'],
      evidence_refs: ['evidence:1'],
      artifact_refs: ['artifact:1'],
      links: [
        {
          ref: 'tweet:t-1',
          kind: 'signal',
          label: 'watch signal',
          uri: 'https://example.com/signal',
        },
      ],
      summary: 'Signal provenance bundle for the embedded contract.',
    })
    expect(budgets).toMatchObject({
      snapshot_freshness_budget_ms: 30_000,
      decision_latency_budget_ms: 750,
      backpressure_policy: 'degrade-to-wait',
    })
    expect(sameBudgetsViaAlias.fetch_latency_budget_ms).toBe(400)
    expect(sameBudgetsViaAlias.max_retries).toBe(2)
    expect(budgets.backpressure_policy).toBe('degrade-to-wait')
    expect(capabilities.supports_metadata).toBe(true)
    expect(capabilities.supports_paper_mode).toBe(false)
    expect(capabilities.automation_constraints).toEqual(['manual review before live'])
    expect(provenance.provenance_refs).toEqual(['tweet:t-1', 'run:run-123'])
    expect(provenance.links[0]).toMatchObject({
      ref: 'tweet:t-1',
      kind: 'signal',
      label: 'watch signal',
    })
  })

  it('parses approval trade tickets and research pipeline traces', () => {
    const approvalTicket = approvalTradeTicketSchema.parse({
      ticket_id: 'ticket-123',
      run_id: 'run-123',
      venue: 'kalshi',
      market_id: 'market-123',
      workflow_stage: 'approval',
      rationale: 'Ticket stays in approval until the second reviewer signs off.',
      summary: 'Approval ticket for governed trade review.',
      approval_state: {
        status: 'pending',
        requested_by: 'operator-a',
        requested_at: '2026-04-08T00:00:00.000Z',
        summary: 'Awaiting second approval.',
      },
      trade_intent_preview: {
        intent_id: 'intent-123',
        run_id: 'run-123',
        venue: 'kalshi',
        market_id: 'market-123',
        side: 'yes',
        size_usd: 50,
        limit_price: 0.51,
        max_slippage_bps: 25,
        max_unhedged_leg_ms: 500,
        forecast_ref: 'forecast-123',
        risk_checks_passed: true,
        created_at: '2026-04-08T00:00:00.000Z',
      },
      created_at: '2026-04-08T00:00:00.000Z',
    })

    const trace = predictionMarketResearchPipelineTraceSchema.parse({
      trace_id: 'trace-123',
      pipeline_id: 'research-pipeline-123',
      pipeline_version: '2026.04.08',
      run_id: 'run-123',
      venue: 'polymarket',
      market_id: 'market-123',
      model_family: 'llm-superforecaster/oracle',
      started_at: '2026-04-08T00:00:00.000Z',
      stage_count: 2,
      stages: [
        predictionMarketResearchPipelineStageSchema.parse({
          stage_id: 'ingestion',
          stage_kind: 'ingestion',
          status: 'complete',
          summary: 'Collected signals.',
        }),
        predictionMarketResearchPipelineStageSchema.parse({
          stage_id: 'forecast',
          stage_kind: 'forecast',
          status: 'complete',
          probability_yes: 0.62,
          confidence: 0.7,
          summary: 'Produced a calibrated estimate.',
        }),
      ],
      summary: 'Trace stays compact while retaining stage-by-stage auditability.',
    })

    const summary = predictionMarketResearchPipelineSummarySchema.parse({
      summary_id: 'summary-123',
      trace_id: trace.trace_id,
      pipeline_id: trace.pipeline_id,
      pipeline_version: trace.pipeline_version,
      run_id: trace.run_id,
      venue: trace.venue,
      market_id: trace.market_id,
      model_family: trace.model_family,
      generated_at: '2026-04-08T00:00:05.000Z',
      forecaster_count: 2,
      contributor_count: 2,
      signal_count: 2,
      evidence_count: 2,
      stage_count: trace.stage_count,
      base_rate_probability_yes: 0.5,
      forecast_probability_yes: 0.62,
      abstention_recommended: false,
      summary: 'Research summary remains parseable and operationally useful.',
    })

    expect(approvalTicket.approval_state.status).toBe('pending')
    expect(approvalTicket.trade_intent_preview?.forecast_ref).toBe('forecast-123')
    expect(trace.stages).toHaveLength(2)
    expect(trace.stages[1]?.probability_yes).toBe(0.62)
    expect(summary.trace_id).toBe(trace.trace_id)
    expect(summary.forecast_probability_yes).toBe(0.62)
  })

  it('parses cross-venue, health, capital and trade-intent contracts', () => {
    const match = crossVenueMatchSchema.parse({
      canonical_event_id: 'event-123',
      left_market_ref: { venue: 'polymarket', market_id: 'poly-1', venue_type: 'execution-equivalent' },
      right_market_ref: { venue: 'kalshi', market_id: 'kal-1', venue_type: 'execution-equivalent' },
      semantic_similarity_score: 0.91,
      resolution_compatibility_score: 0.93,
      payout_compatibility_score: 0.89,
      currency_compatibility_score: 1,
      manual_review_required: false,
      notes: ['high_confidence_match'],
    })

    const health = venueHealthSnapshotSchema.parse({
      venue: 'kalshi',
      captured_at: '2026-04-08T00:00:00.000Z',
      health_score: 97,
      api_status: 'ok',
      stream_status: 'unknown',
      staleness_ms: 1200,
      degraded_mode: true,
    })

    const capital = capitalLedgerSnapshotSchema.parse({
      captured_at: '2026-04-08T00:00:00.000Z',
      venue: 'polymarket',
      cash_available_usd: 1000,
      cash_locked_usd: 50,
      collateral_currency: 'USD',
      open_exposure_usd: 250,
      withdrawable_amount_usd: 950,
      transfer_latency_estimate_ms: 15_000,
    })

    const tradeIntent = tradeIntentSchema.parse({
      intent_id: 'intent-123',
      run_id: 'run-123',
      venue: 'polymarket',
      market_id: 'mkt-123',
      side: 'yes',
      size_usd: 25,
      limit_price: 0.54,
      max_slippage_bps: 75,
      max_unhedged_leg_ms: 5_000,
      forecast_ref: 'forecast-123',
      risk_checks_passed: true,
      created_at: '2026-04-08T00:00:00.000Z',
    })

    expect(match.manual_review_required).toBe(false)
    expect(health.health_score).toBe(0.97)
    expect(health.api_status).toBe('healthy')
    expect(health.degraded_mode).toBe('degraded')
    expect(capital.withdrawable_amount).toBe(950)
    expect(capital.cash_available).toBe(1000)
    expect(tradeIntent.time_in_force).toBe('gtc')
  })

  it('rejects invalid confidence bands and duplicate cross-venue refs', () => {
    const invalidDecision = decisionPacketSchema.safeParse({
      correlation_id: 'corr-124',
      question: 'Invalid confidence band?',
      topic: 'quality',
      objective: 'exercise guardrails',
      probability_estimate: 0.4,
      confidence_band: { low: 0.7, high: 0.6 },
      recommendation: 'wait',
      rationale_summary: 'This should fail.',
      mode_used: 'committee',
      engine_used: 'baseline-v0',
      runtime_used: 'prediction_markets',
    })

    expect(invalidDecision.success).toBe(false)
    if (invalidDecision.success) return

    expect(invalidDecision.error.issues[0]?.path).toEqual(['confidence_band', 'high'])

    const duplicateMatch = crossVenueMatchSchema.safeParse({
      canonical_event_id: 'event-dup',
      left_market_ref: { venue: 'polymarket', market_id: 'same-market' },
      right_market_ref: { venue: 'polymarket', market_id: 'same-market' },
      semantic_similarity_score: 1,
      resolution_compatibility_score: 1,
      payout_compatibility_score: 1,
      currency_compatibility_score: 1,
    })

    expect(duplicateMatch.success).toBe(false)
    if (duplicateMatch.success) return

    expect(duplicateMatch.error.issues[0]?.path).toEqual(['right_market_ref', 'market_id'])
  })
})
