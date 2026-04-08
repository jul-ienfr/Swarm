import { describe, expect, it } from 'vitest'
import {
  multiVenueExecutionSchema,
  marketDescriptorSchema,
  predictionMarketMarketGraphSchema,
  marketSnapshotSchema,
  predictionMarketRunSummarySchema,
  runManifestSchema,
} from '@/lib/prediction-markets/schemas'

function makeDescriptor(overrides: Record<string, unknown> = {}) {
  return marketDescriptorSchema.parse({
    venue: 'polymarket',
    market_id: 'venue-test-market',
    question: 'Will venue contracts stay stable?',
    outcomes: ['Yes', 'No'],
    active: true,
    closed: false,
    accepting_orders: true,
    restricted: false,
    is_binary_yes_no: true,
    source_urls: ['https://example.com/markets/venue-test-market'],
    ...overrides,
  })
}

describe('prediction markets multi-venue contracts', () => {
  it('defaults descriptors to execution-equivalent venues', () => {
    const descriptor = makeDescriptor()

    expect(descriptor.venue_type).toBe('execution-equivalent')
  })

  it('accepts reference-only and experimental venue classifications', () => {
    const referenceOnly = makeDescriptor({
      market_id: 'reference-market',
      venue_type: 'reference-only',
    })
    const experimental = makeDescriptor({
      market_id: 'experimental-market',
      venue_type: 'experimental',
    })

    expect(referenceOnly.venue_type).toBe('reference-only')
    expect(experimental.venue_type).toBe('experimental')
  })

  it('rejects unsupported venue classifications', () => {
    const result = marketDescriptorSchema.safeParse({
      venue: 'polymarket',
      market_id: 'bad-venue-type',
      question: 'Invalid venue type?',
      outcomes: ['Yes', 'No'],
      active: true,
      closed: false,
      source_urls: ['https://example.com/markets/bad-venue-type'],
      venue_type: 'arbitrage-only',
    })

    expect(result.success).toBe(false)
    if (result.success) return

    expect(result.error.issues[0]?.path).toEqual(['venue_type'])
  })

  it('supports reference-style snapshots without an order book', () => {
    const snapshot = marketSnapshotSchema.parse({
      venue: 'polymarket',
      market: makeDescriptor({
        market_id: 'reference-snapshot',
        venue_type: 'reference-only',
        accepting_orders: false,
      }),
      captured_at: '2026-04-08T00:00:00.000Z',
      yes_outcome_index: 0,
      yes_price: 0.61,
      no_price: 0.39,
      midpoint_yes: 0.61,
      best_bid_yes: null,
      best_ask_yes: null,
      spread_bps: null,
      book: null,
      history: [],
      source_urls: ['https://example.com/reference-snapshot'],
    })

    expect(snapshot.market.venue_type).toBe('reference-only')
    expect(snapshot.book).toBeNull()
    expect(snapshot.history).toEqual([])
  })

  it('preserves replay lineage and audit artifacts in run contracts', () => {
    const manifest = runManifestSchema.parse({
      run_id: 'pm-run-002',
      source_run_id: 'pm-run-001',
      mode: 'replay',
      venue: 'polymarket',
      market_id: 'venue-test-market',
      market_slug: 'venue-test-market',
      actor: 'operator',
      started_at: '2026-04-08T00:00:00.000Z',
      completed_at: '2026-04-08T00:01:00.000Z',
      status: 'completed',
      config_hash: 'cfg-hash-123',
      artifact_refs: [
        {
          artifact_id: 'pm-run-002:market_snapshot',
          artifact_type: 'market_snapshot',
          sha256: 'sha-market-snapshot',
        },
        {
          artifact_id: 'pm-run-002:run_manifest',
          artifact_type: 'run_manifest',
          sha256: 'sha-run-manifest',
        },
      ],
    })

    const summary = predictionMarketRunSummarySchema.parse({
      run_id: manifest.run_id,
      source_run_id: manifest.source_run_id,
      workspace_id: 1,
      venue: manifest.venue,
      mode: manifest.mode,
      market_id: manifest.market_id,
      market_slug: manifest.market_slug,
      status: 'completed',
      recommendation: 'wait',
      side: null,
      confidence: 0.42,
      probability_yes: 0.61,
      market_price_yes: 0.61,
      edge_bps: 0,
      created_at: 1712534400,
      updated_at: 1712534460,
      manifest,
      artifact_refs: manifest.artifact_refs,
    })

    expect(summary.source_run_id).toBe('pm-run-001')
    expect(summary.artifact_refs).toHaveLength(2)
    expect(summary.manifest.mode).toBe('replay')
  })

  it('accepts taxonomy and filter reason codes on multi-venue execution surfaces', () => {
    const execution = multiVenueExecutionSchema.parse({
      gate_name: 'multi_venue_execution',
      taxonomy: 'cross_venue_signal',
      execution_filter_reason_codes: ['manual_review_required', 'execution_like_venue'],
      execution_filter_reason_code_counts: {
        manual_review_required: 1,
        execution_like_venue: 1,
      },
      market_count: 2,
      comparable_group_count: 1,
      execution_candidate_count: 1,
      execution_plan_count: 1,
      tradeable_plan_count: 0,
      execution_routes: {
        comparison_only: 0,
        relative_value: 0,
        cross_venue_signal: 1,
        true_arbitrage: 0,
      },
      tradeable_market_ids: [],
      read_only_market_ids: ['market-1', 'market-2'],
      reference_market_ids: ['market-1', 'market-2'],
      signal_market_ids: [],
      execution_market_ids: [],
      summary: 'No tradeable cross-venue execution plans were derived; the surface remains comparison-only.',
      source_refs: {
        cross_venue_intelligence: 'run-1:cross_venue_intelligence',
        execution_pathways: 'run-1:execution_pathways',
        execution_projection: 'run-1:execution_projection',
      },
      metadata: {
        run_id: 'run-1',
        market_id: 'market-1',
        venue: 'polymarket',
        cross_venue_report_present: true,
        execution_pathways_highest_actionable_mode: 'shadow',
        execution_projection_selected_path: 'shadow',
        execution_projection_selected_path_status: 'ready',
        execution_projection_selected_path_shadow_signal_present: true,
        execution_projection_selected_path_canonical_size_usd: 60,
        execution_projection_selected_preview_available: true,
        execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
        execution_projection_selected_preview_size_usd: 60,
        execution_surface_preview_via: 'execution_projection_selected_preview',
        execution_surface_preview_source: 'canonical_trade_intent_preview',
        execution_surface_preview_size_usd: 60,
        execution_surface_preview_uses_projection_selected_preview: true,
        execution_candidate_count: 1,
        tradeable_plan_count: 0,
        taxonomy: 'cross_venue_signal',
        execution_filter_reason_codes: ['manual_review_required', 'execution_like_venue'],
        execution_filter_reason_code_counts: {
          manual_review_required: 1,
          execution_like_venue: 1,
        },
      },
    })

    expect(execution.taxonomy).toBe('cross_venue_signal')
    expect(execution.execution_filter_reason_codes).toEqual([
      'manual_review_required',
      'execution_like_venue',
    ])
    expect(execution.execution_filter_reason_code_counts).toEqual({
      manual_review_required: 1,
      execution_like_venue: 1,
    })
  })

  it('parses market graph relations and comparable groups', () => {
    const graph = predictionMarketMarketGraphSchema.parse({
      schema_version: 'v1',
      graph_id: 'mgraph_test',
      nodes: [
        {
          schema_version: 'v1',
          node_id: 'polymarket:market-1',
          market_id: 'market-1',
          venue: 'polymarket',
          venue_type: 'execution-equivalent',
          title: 'Will Bitcoin exceed 100000 by 2026-12-31?',
          question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
          canonical_event_id: 'cve:2026-12-31:bitcoin',
          status: 'active',
          role: 'reference',
          clarity_score: 0.92,
          liquidity: 100000,
          price_yes: 0.54,
          snapshot_id: 'snapshot-1',
          metadata: {
            categories: ['crypto'],
            tags: ['btc'],
            role_hint: 'reference',
          },
        },
        {
          schema_version: 'v1',
          node_id: 'kalshi:market-2',
          market_id: 'market-2',
          venue: 'kalshi',
          venue_type: 'execution-equivalent',
          title: 'Will Bitcoin be above 100000 on 2026-12-31?',
          question: 'Will Bitcoin be above 100000 on 2026-12-31?',
          canonical_event_id: 'cve:2026-12-31:bitcoin',
          status: 'active',
          role: 'comparison',
          clarity_score: 0.88,
          liquidity: 85000,
          price_yes: 0.58,
          snapshot_id: 'snapshot-2',
          metadata: {
            categories: ['crypto'],
            tags: ['btc'],
            role_hint: 'comparison',
          },
        },
      ],
      edges: [
        {
          schema_version: 'v1',
          edge_id: 'edge-1',
          source_node_id: 'polymarket:market-1',
          target_node_id: 'kalshi:market-2',
          relation: 'same_event',
          similarity: 0.91,
          compatible_resolution: true,
          rationale: 'Shared canonical event and aligned resolution',
          metadata: {
            canonical_event_id: 'cve:2026-12-31:bitcoin',
            opportunity_type: 'relative_value',
          },
        },
      ],
      matches: [
        {
          canonical_event_id: 'cve:2026-12-31:bitcoin',
          left_market_ref: {
            venue: 'polymarket',
            market_id: 'market-1',
            venue_type: 'execution-equivalent',
            question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
            side: 'yes',
          },
          right_market_ref: {
            venue: 'kalshi',
            market_id: 'market-2',
            venue_type: 'execution-equivalent',
            question: 'Will Bitcoin be above 100000 on 2026-12-31?',
            side: 'yes',
          },
          semantic_similarity_score: 0.91,
          resolution_compatibility_score: 1,
          payout_compatibility_score: 1,
          currency_compatibility_score: 1,
          manual_review_required: false,
          notes: ['canonical_event_key:2026-12-31:bitcoin', 'confidence_score:0.9100'],
        },
      ],
      rejected_matches: [],
      comparable_groups: [
        {
          schema_version: 'v1',
          group_id: 'cmpgrp_test',
          canonical_event_id: 'cve:2026-12-31:bitcoin',
          question_key: 'will bitcoin exceed 100000 by 2026 12 31',
          question: 'Will Bitcoin exceed 100000 by 2026-12-31?',
          relation_kind: 'same_event',
          market_ids: ['market-1', 'market-2'],
          comparable_market_refs: ['market-1', 'market-2'],
          venues: ['kalshi', 'polymarket'],
          venue_types: ['execution-equivalent'],
          reference_market_ids: ['market-1'],
          comparison_market_ids: ['market-2'],
          parent_market_ids: ['market-1'],
          child_market_ids: ['market-2'],
          parent_child_pairs: [
            {
              parent_market_id: 'market-1',
              child_market_id: 'market-2',
              shared_tokens: ['bitcoin', '100000'],
              specificity_gap: 1,
            },
          ],
          natural_hedge_market_ids: [],
          natural_hedge_pairs: [],
          resolution_sources: [],
          currencies: [],
          payout_currencies: [],
          notes: ['manual_review_required'],
          manual_review_required: false,
          compatible_resolution: true,
          compatible_currency: true,
          compatible_payout: true,
          match_count: 1,
          duplicate_market_count: 1,
          duplicate_market_rate: 0.5,
          desalignment_count: 0,
          desalignment_rate: 0,
          desalignment_dimensions: [],
          narrative_risk_flags: [],
          rationale: 'relation=same_event; venues=[kalshi, polymarket]',
          metadata: {
            node_count: 2,
            reference_count: 1,
            comparison_count: 1,
            parent_market_count: 1,
            child_market_count: 1,
            parent_child_pair_count: 1,
            natural_hedge_market_count: 0,
            natural_hedge_pair_count: 0,
            question_key: 'will bitcoin exceed 100000 by 2026 12 31',
            duplicate_market_count: 1,
            duplicate_market_rate: 0.5,
            desalignment_count: 0,
            desalignment_rate: 0,
            desalignment_dimensions: [],
            notes: ['manual_review_required'],
          },
        },
      ],
      metadata: {
        market_count: 2,
        match_count: 1,
        rejected_match_count: 0,
        grouped_market_count: 2,
        grouped_market_coverage_rate: 1,
        ungrouped_market_count: 0,
        duplicate_market_count: 1,
        duplicate_market_rate: 0.5,
        comparable_group_count: 1,
        relation_threshold: 0.45,
        similarity_threshold: 0.58,
      },
    })

    expect(graph.nodes).toHaveLength(2)
    expect(graph.edges).toHaveLength(1)
    expect(graph.comparable_groups).toHaveLength(1)
    expect(graph.metadata).toMatchObject({
      market_count: 2,
      match_count: 1,
      comparable_group_count: 1,
    })
  })
})
