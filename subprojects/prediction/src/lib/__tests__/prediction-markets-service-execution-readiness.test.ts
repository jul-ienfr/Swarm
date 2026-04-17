import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { buildPredictionMarketExecutionReadiness } from '@/lib/prediction-markets/execution-readiness'
import { reconcileCapitalLedger } from '@/lib/prediction-markets/reconciliation'

const mocks = vi.hoisted(() => ({
  buildPolymarketSnapshot: vi.fn(),
  listPolymarketMarkets: vi.fn(),
  buildKalshiSnapshot: vi.fn(),
  listKalshiMarkets: vi.fn(),
  findRecentPredictionMarketRunByConfig: vi.fn(),
  getStoredPredictionMarketRunDetails: vi.fn(),
  listPredictionMarketRuns: vi.fn(),
  persistPredictionMarketExecution: vi.fn(),
  createRun: vi.fn(),
  updateRun: vi.fn(),
  computeConfigHash: vi.fn(() => 'cfg-hash'),
  getRun: vi.fn(),
  getVenueCapabilitiesContract: vi.fn(),
  getVenueCoverageContract: vi.fn(),
  getVenueHealthSnapshotContract: vi.fn(),
  getVenueFeedSurfaceContract: vi.fn(),
  getVenueBudgetsContract: vi.fn(),
  listPredictionMarketVenues: vi.fn(),
  evaluatePredictionMarketCompliance: vi.fn(),
  evaluatePredictionMarketRuntimeGuard: vi.fn(),
}))

vi.mock('@/lib/prediction-markets/polymarket', () => ({
  buildPolymarketSnapshot: mocks.buildPolymarketSnapshot,
  listPolymarketMarkets: mocks.listPolymarketMarkets,
}))

vi.mock('@/lib/prediction-markets/kalshi', () => ({
  buildKalshiSnapshot: mocks.buildKalshiSnapshot,
  listKalshiMarkets: mocks.listKalshiMarkets,
}))

vi.mock('@/lib/prediction-markets/store', () => ({
  findRecentPredictionMarketRunByConfig: mocks.findRecentPredictionMarketRunByConfig,
  getPredictionMarketRunDetails: mocks.getStoredPredictionMarketRunDetails,
  listPredictionMarketRuns: mocks.listPredictionMarketRuns,
  persistPredictionMarketExecution: mocks.persistPredictionMarketExecution,
}))

vi.mock('@/lib/runs', () => ({
  createRun: mocks.createRun,
  updateRun: mocks.updateRun,
  computeConfigHash: mocks.computeConfigHash,
  getRun: mocks.getRun,
}))

vi.mock('@/lib/prediction-markets/venue-ops', () => ({
  getVenueCapabilitiesContract: mocks.getVenueCapabilitiesContract,
  getVenueCoverageContract: mocks.getVenueCoverageContract,
  getVenueHealthSnapshotContract: mocks.getVenueHealthSnapshotContract,
  getVenueFeedSurfaceContract: mocks.getVenueFeedSurfaceContract,
  getVenueBudgetsContract: mocks.getVenueBudgetsContract,
  listPredictionMarketVenues: mocks.listPredictionMarketVenues,
}))

vi.mock('@/lib/prediction-markets/compliance', () => ({
  evaluatePredictionMarketCompliance: mocks.evaluatePredictionMarketCompliance,
}))

vi.mock('@/lib/prediction-markets/runtime-guard', () => ({
  evaluatePredictionMarketRuntimeGuard: mocks.evaluatePredictionMarketRuntimeGuard,
}))

import {
  advisePredictionMarket,
  getPredictionMarketRunDetails,
  preparePredictionMarketRunDispatch,
  preparePredictionMarketRunLive,
  preparePredictionMarketRunPaper,
  preparePredictionMarketRunShadow,
  replayPredictionMarketRun,
} from '@/lib/prediction-markets/service'
import {
  evidencePacketSchema,
  forecastPacketSchema,
  marketDescriptorSchema,
  marketRecommendationPacketSchema,
  marketSnapshotSchema,
  resolutionPolicySchema,
  runManifestSchema,
  type MarketDescriptor,
  type MarketSnapshot,
} from '@/lib/prediction-markets/schemas'
import { type PredictionMarketComplianceDecision, type PredictionMarketComplianceMatrix } from '@/lib/prediction-markets/compliance'
import { type PredictionMarketRuntimeGuardResult } from '@/lib/prediction-markets/runtime-guard'

type FutureTopLevelTradeIntentPreviewSurface = {
  selected_trade_intent_preview?: unknown | null
  canonical_trade_intent_preview?: unknown | null
  execution_projection_selected_preview?: unknown | null
  execution_projection_selected_preview_source?: unknown | null
  trade_intent_guard?: {
    trade_intent_preview?: unknown | null
  } | null
  execution_projection?: {
    selected_path?: string | null
    projected_paths?: Record<string, {
      canonical_trade_intent_preview?: unknown | null
      trade_intent_preview?: unknown | null
    }>
  } | null
}

type FutureTradeIntentPreview = {
  size_usd: number
  notes?: string
}

const originalLiveTransportEnv = {
  backend: process.env.POLYMARKET_EXECUTION_BACKEND,
  token: process.env.POLYMARKET_EXECUTION_AUTH_TOKEN,
  liveOrderPath: process.env.POLYMARKET_EXECUTION_LIVE_ORDER_PATH,
  cancelPath: process.env.POLYMARKET_EXECUTION_CANCEL_PATH,
}

function asFutureTradeIntentPreview(value: unknown): FutureTradeIntentPreview | null {
  const record = value as Record<string, unknown> | null
  return record && typeof record.size_usd === 'number'
    ? value as FutureTradeIntentPreview
    : null
}

function expectFutureTopLevelTradeIntentPreviewAlignment(
  surface: FutureTopLevelTradeIntentPreviewSurface,
) {
  const projectedPaths = surface.execution_projection?.projected_paths ?? {}
  const selectedPath = surface.execution_projection?.selected_path ?? null
  const selectedProjectionPath = selectedPath ? projectedPaths[selectedPath] ?? null : null
  const candidateProjectionSelectedPreview =
    selectedProjectionPath?.canonical_trade_intent_preview ??
    selectedProjectionPath?.trade_intent_preview ??
    null
  const rawProjectionSelectedPreview = asFutureTradeIntentPreview(candidateProjectionSelectedPreview)
  const projectionCanonicalSizeUsd = selectedProjectionPath &&
    typeof selectedProjectionPath === 'object' &&
    'sizing_signal' in selectedProjectionPath &&
    selectedProjectionPath.sizing_signal &&
    typeof selectedProjectionPath.sizing_signal === 'object' &&
    'canonical_size_usd' in (selectedProjectionPath.sizing_signal as Record<string, unknown>)
      ? ((selectedProjectionPath.sizing_signal as Record<string, unknown>).canonical_size_usd as number | null | undefined) ?? null
      : null
  const expectedProjectionSelectedPreview = rawProjectionSelectedPreview != null &&
    projectionCanonicalSizeUsd != null &&
    projectionCanonicalSizeUsd < rawProjectionSelectedPreview.size_usd
    ? {
      ...rawProjectionSelectedPreview,
      size_usd: projectionCanonicalSizeUsd,
      notes: [
        rawProjectionSelectedPreview.notes,
        `Canonical execution sizing caps preview size to ${projectionCanonicalSizeUsd} USD.`,
      ].filter(Boolean).join(' '),
    }
    : rawProjectionSelectedPreview
  const expectedTradeIntentPreview = surface.trade_intent_guard?.trade_intent_preview
    ?? expectedProjectionSelectedPreview
    ?? null
  const expectedTradeIntentPreviewSource = selectedProjectionPath?.canonical_trade_intent_preview != null
    ? 'canonical_trade_intent_preview'
    : selectedProjectionPath?.trade_intent_preview != null
      ? 'trade_intent_preview'
      : null

  for (const fieldName of ['selected_trade_intent_preview', 'canonical_trade_intent_preview'] as const) {
    const topLevelTradeIntentPreview = surface[fieldName]
    if (topLevelTradeIntentPreview != null) {
      expect(topLevelTradeIntentPreview).toEqual(expectedTradeIntentPreview)
    }
  }

  if (surface.execution_projection_selected_preview != null) {
    expect(surface.execution_projection_selected_preview).toEqual(expectedProjectionSelectedPreview)
  }

  if (surface.execution_projection_selected_preview_source != null) {
    expect(surface.execution_projection_selected_preview_source).toBe(expectedTradeIntentPreviewSource)
  }
}

function makeDescriptor(overrides: Partial<MarketDescriptor> = {}): MarketDescriptor {
  return marketDescriptorSchema.parse({
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    market_id: 'execution-readiness-market',
    slug: 'execution-readiness-market',
    question: 'Will the execution readiness test stay stable?',
    outcomes: ['Yes', 'No'],
    active: true,
    closed: false,
    accepting_orders: true,
    restricted: false,
    liquidity_usd: 120_000,
    volume_usd: 900_000,
    volume_24h_usd: 55_000,
    best_bid: 0.49,
    best_ask: 0.51,
    last_trade_price: 0.5,
    tick_size: 0.01,
    min_order_size: 5,
    is_binary_yes_no: true,
    end_at: '2026-12-31T23:59:59.000Z',
    source_urls: ['https://example.com/execution-readiness-market'],
    ...overrides,
  })
}

function makeSnapshot(market: MarketDescriptor): MarketSnapshot {
  return marketSnapshotSchema.parse({
    venue: market.venue,
    market,
    captured_at: '2026-04-08T00:00:00.000Z',
    yes_outcome_index: 0,
    yes_token_id: `${market.market_id}:yes`,
    yes_price: 0.5,
    no_price: 0.5,
    midpoint_yes: 0.5,
    best_bid_yes: 0.49,
    best_ask_yes: 0.51,
    spread_bps: 200,
    book: {
      token_id: `${market.market_id}:yes`,
      market_condition_id: `${market.market_id}:cond`,
      fetched_at: '2026-04-08T00:00:00.000Z',
      best_bid: 0.49,
      best_ask: 0.51,
      last_trade_price: 0.5,
      tick_size: 0.01,
      min_order_size: 5,
      bids: [{ price: 0.49, size: 400 }],
      asks: [{ price: 0.51, size: 400 }],
      depth_near_touch: 800,
    },
    history: [
      { timestamp: 1712534400, price: 0.48 },
      { timestamp: 1712538000, price: 0.5 },
    ],
    source_urls: [
      'https://example.com/execution-readiness-market',
      'https://example.com/execution-readiness-market/book',
    ],
  })
}

function makeStoredRunDetails(runId: string, snapshot: MarketSnapshot) {
  const resolutionPolicy = resolutionPolicySchema.parse({
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    status: 'eligible',
    manual_review_required: false,
    reasons: [],
    primary_sources: snapshot.source_urls,
    evaluated_at: '2026-04-08T00:00:00.000Z',
  })

  const evidencePackets = [
    evidencePacketSchema.parse({
      evidence_id: `${snapshot.market.market_id}:manual-thesis`,
      market_id: snapshot.market.market_id,
      venue: snapshot.venue,
      type: 'manual_thesis',
      title: 'Manual thesis override',
      summary: 'Stored manual thesis for replay.',
      captured_at: '2026-04-08T00:00:00.000Z',
      content_hash: 'sha256:manual-thesis',
      metadata: {
        thesis_probability: 0.7,
        thesis_rationale: 'Stored manual thesis for replay.',
      },
    }),
  ]

  const forecast = forecastPacketSchema.parse({
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    basis: 'manual_thesis',
    probability_yes: 0.7,
    confidence: 0.55,
    rationale: 'Stored forecast',
    evidence_refs: evidencePackets.map((packet) => packet.evidence_id),
    produced_at: '2026-04-08T00:00:00.000Z',
  })

  const recommendation = marketRecommendationPacketSchema.parse({
    market_id: snapshot.market.market_id,
    venue: snapshot.venue,
    action: 'bet',
    side: 'yes',
    confidence: 0.55,
    fair_value_yes: 0.7,
    market_price_yes: 0.5,
    market_bid_yes: 0.49,
    market_ask_yes: 0.51,
    edge_bps: 1900,
    spread_bps: 200,
    reasons: ['Stored recommendation'],
    risk_flags: [],
    produced_at: '2026-04-08T00:00:00.000Z',
  })

  const manifest = runManifestSchema.parse({
    run_id: runId,
    mode: 'advise',
    venue: snapshot.venue,
    market_id: snapshot.market.market_id,
    market_slug: snapshot.market.slug,
    actor: 'operator',
    started_at: '2026-04-08T00:00:00.000Z',
    completed_at: '2026-04-08T00:00:02.000Z',
    status: 'completed',
    config_hash: 'stored-config-hash',
  })

  return {
    run: { id: runId, status: 'completed' },
    summary: {
      run_id: runId,
      workspace_id: 1,
      venue: snapshot.venue,
      mode: 'advise',
      market_id: snapshot.market.market_id,
      market_slug: snapshot.market.slug ?? null,
      status: 'completed',
      recommendation: 'bet',
      side: 'yes',
      confidence: 0.55,
      probability_yes: 0.7,
      market_price_yes: 0.5,
      edge_bps: 1900,
    },
    artifacts: [
      { artifact_type: 'market_snapshot', payload: snapshot },
      { artifact_type: 'resolution_policy', payload: resolutionPolicy },
      { artifact_type: 'evidence_bundle', payload: evidencePackets },
      { artifact_type: 'forecast_packet', payload: forecast },
      { artifact_type: 'recommendation_packet', payload: recommendation },
      {
        artifact_type: 'shadow_arbitrage',
        payload: {
          read_only: true,
          generated_at: '2026-04-08T00:00:01.000Z',
          as_of_at: '2026-04-08T00:00:01.000Z',
          executable_edge: {
            edge_id: `${runId}:shadow-edge`,
          },
          microstructure_summary: {
            recommended_mode: 'shadow',
          },
          sizing: {
            requested_size_usd: null,
            base_size_usd: 100,
            recommended_size_usd: 75,
            simulated_size_usd: 75,
            size_multiplier: 0.75,
          },
          failure_cases: [],
          summary: {
            shadow_edge_bps: 112,
            recommended_size_usd: 75,
          },
        },
      },
      { artifact_type: 'run_manifest', payload: manifest },
    ],
  }
}

function makeBenchmarkExecutionProjection() {
  return {
    gate_name: 'execution_projection',
    preflight_only: true,
    requested_path: 'live',
    selected_path: 'shadow',
    eligible_paths: ['paper', 'shadow'],
    verdict: 'downgraded',
    blocking_reasons: [],
    downgrade_reasons: ['capital_ledger_unavailable'],
    manual_review_required: true,
    generated_at: '2026-04-08T00:00:00.000Z',
    ttl_ms: 30_000,
    expires_at: '2026-04-08T00:00:30.000Z',
    projected_paths: {
      paper: {
        path: 'paper',
        requested_mode: 'paper',
        effective_mode: 'paper',
        status: 'ready',
        allowed: true,
        blockers: [],
        warnings: [],
        reason_summary: 'Paper projection is ready.',
        simulation: {
          expected_fill_confidence: 0.97,
          expected_slippage_bps: 0,
          stale_quote_risk: 'low',
          quote_age_ms: 0,
          notes: [],
          shadow_arbitrage: null,
        },
        trade_intent_preview: {
          size_usd: 25,
          limit_price: 0.47,
          time_in_force: 'day',
          max_slippage_bps: 20,
        },
        canonical_trade_intent_preview: {
          size_usd: 25,
          limit_price: 0.47,
          time_in_force: 'day',
          max_slippage_bps: 20,
        },
        sizing_signal: {
          preview_size_usd: 25,
          base_size_usd: 25,
          recommended_size_usd: 25,
          max_size_usd: 25,
          canonical_size_usd: 25,
          shadow_recommended_size_usd: null,
          limit_price: 0.47,
          max_slippage_bps: 20,
          max_unhedged_leg_ms: null,
          time_in_force: 'day',
          multiplier: 1,
          sizing_source: 'default',
          source: 'trade_intent_preview',
          notes: [],
        },
        shadow_arbitrage_signal: null,
      },
      shadow: {
        path: 'shadow',
        requested_mode: 'shadow',
        effective_mode: 'shadow',
        status: 'ready',
        allowed: true,
        blockers: [],
        warnings: [],
        reason_summary: 'Shadow projection is ready.',
        simulation: {
          expected_fill_confidence: 0.91,
          expected_slippage_bps: 22,
          stale_quote_risk: 'medium',
          quote_age_ms: 850,
          notes: [],
          shadow_arbitrage: {
            read_only: true,
            generated_at: '2026-04-08T00:00:01.000Z',
            as_of_at: '2026-04-08T00:00:01.000Z',
            executable_edge: { edge_id: 'shadow-edge' },
            microstructure_summary: { recommended_mode: 'shadow' },
            sizing: {
              requested_size_usd: null,
              base_size_usd: 100,
              recommended_size_usd: 60,
              simulated_size_usd: 60,
              size_multiplier: 0.6,
            },
            failure_cases: [],
            summary: {
              shadow_edge_bps: 82,
              recommended_size_usd: 60,
            },
          },
        },
        trade_intent_preview: {
          size_usd: 60,
          limit_price: 0.49,
          time_in_force: 'ioc',
          max_slippage_bps: 35,
        },
        canonical_trade_intent_preview: {
          size_usd: 60,
          limit_price: 0.49,
          time_in_force: 'ioc',
          max_slippage_bps: 35,
        },
        sizing_signal: {
          preview_size_usd: 60,
          base_size_usd: 60,
          recommended_size_usd: 60,
          max_size_usd: 60,
          canonical_size_usd: 60,
          shadow_recommended_size_usd: 60,
          limit_price: 0.49,
          max_slippage_bps: 35,
          max_unhedged_leg_ms: 5000,
          time_in_force: 'ioc',
          multiplier: 0.6,
          sizing_source: 'default',
          source: 'trade_intent_preview+shadow_arbitrage',
          notes: [],
        },
        shadow_arbitrage_signal: {
          read_only: true,
          market_id: 'execution-readiness-market',
          venue: 'polymarket',
          base_executable_edge_bps: 110,
          shadow_edge_bps: 82,
          recommended_size_usd: 60,
          hedge_success_probability: 0.91,
          estimated_net_pnl_bps: 24,
          estimated_net_pnl_usd: 15,
          worst_case_kind: 'hedge_delay',
          failure_case_count: 2,
        },
      },
    },
    basis: {
      uses_execution_readiness: true,
      uses_compliance: true,
      uses_capital: false,
      uses_reconciliation: false,
      uses_microstructure: false,
      capital_status: 'unavailable',
      reconciliation_status: 'unavailable',
      source_refs: {
        pipeline_guard: 'run-benchmark-surface-001:pipeline_guard',
        compliance_report: 'run-benchmark-surface-001:compliance_report',
        execution_readiness: 'run-benchmark-surface-001:execution_readiness',
        venue_health: 'run-benchmark-surface-001:pipeline_guard#venue_health',
        capital_ledger: null,
        reconciliation: null,
        microstructure_lab: null,
      },
      canonical_gate: {
        gate_name: 'execution_projection',
        single_runtime_gate: true,
        enforced_for_modes: ['paper', 'shadow', 'live'],
      },
    },
    microstructure_summary: null,
    modes: {
      paper: {
        requested_mode: 'paper',
        verdict: 'ready',
        effective_mode: 'paper',
        blockers: [],
        warnings: [],
        summary: 'Paper projection is ready.',
      },
      shadow: {
        requested_mode: 'shadow',
        verdict: 'ready',
        effective_mode: 'shadow',
        blockers: [],
        warnings: [],
        summary: 'Shadow projection is ready.',
      },
      live: {
        requested_mode: 'live',
        verdict: 'blocked',
        effective_mode: 'shadow',
        blockers: ['capital_ledger_unavailable'],
        warnings: [],
        summary: 'Live projection is blocked.',
      },
    },
    highest_safe_requested_mode: 'shadow',
    recommended_effective_mode: 'shadow',
    preflight_summary: {
      gate_name: 'execution_projection',
      preflight_only: true,
      requested_path: 'live',
      selected_path: 'shadow',
      verdict: 'downgraded',
      highest_safe_requested_mode: 'shadow',
      recommended_effective_mode: 'shadow',
      manual_review_required: true,
      ttl_ms: 30_000,
      expires_at: '2026-04-08T00:00:30.000Z',
      counts: { total: 3, eligible: 2, ready: 2, degraded: 0, blocked: 1 },
      basis: {
        uses_execution_readiness: true,
        uses_compliance: true,
        uses_capital: false,
        uses_reconciliation: false,
        uses_microstructure: false,
        capital_status: 'unavailable',
        reconciliation_status: 'unavailable',
      },
      source_refs: [
        'run-benchmark-surface-001:pipeline_guard',
        'run-benchmark-surface-001:compliance_report',
        'run-benchmark-surface-001:execution_readiness',
      ],
      blockers: [],
      downgrade_reasons: ['capital_ledger_unavailable'],
      microstructure: null,
      summary: 'gate=execution_projection preflight=yes verdict=downgraded requested=live selected=shadow highest_safe=shadow recommended=shadow manual_review=yes ttl_ms=30000 blocks=0',
    },
  } as const
}

function makeLiveBenchmarkExecutionProjection() {
  const projection = structuredClone(makeBenchmarkExecutionProjection()) as Record<string, any>

  projection.selected_path = 'live'
  projection.eligible_paths = ['paper', 'shadow', 'live']
  projection.verdict = 'allowed'
  projection.downgrade_reasons = []
  projection.manual_review_required = false
  projection.highest_safe_requested_mode = 'live'
  projection.recommended_effective_mode = 'live'
  projection.projected_paths.live = {
    path: 'live',
    requested_mode: 'live',
    effective_mode: 'live',
    status: 'ready',
    allowed: true,
    blockers: [],
    warnings: [],
    reason_summary: 'Live projection is ready.',
    simulation: {
      expected_fill_confidence: 0.74,
      expected_slippage_bps: 38,
      stale_quote_risk: 'medium',
      quote_age_ms: 850,
      notes: [],
      shadow_arbitrage: null,
    },
    trade_intent_preview: {
      size_usd: 40,
      limit_price: 0.5,
      time_in_force: 'ioc',
      max_slippage_bps: 35,
    },
    canonical_trade_intent_preview: {
      size_usd: 40,
      limit_price: 0.5,
      time_in_force: 'ioc',
      max_slippage_bps: 35,
    },
    sizing_signal: {
      preview_size_usd: 40,
      base_size_usd: 40,
      recommended_size_usd: 40,
      max_size_usd: 40,
      canonical_size_usd: 40,
      shadow_recommended_size_usd: null,
      limit_price: 0.5,
      max_slippage_bps: 35,
      max_unhedged_leg_ms: null,
      time_in_force: 'ioc',
      multiplier: 1,
      sizing_source: 'default',
      source: 'trade_intent_preview',
      notes: [],
    },
    shadow_arbitrage_signal: null,
  }
  projection.basis = {
    ...projection.basis,
    uses_capital: true,
    uses_reconciliation: true,
    capital_status: 'attached',
    reconciliation_status: 'attached',
  }
  projection.modes.live = {
    requested_mode: 'live',
    verdict: 'ready',
    effective_mode: 'live',
    blockers: [],
    warnings: [],
    summary: 'Live projection is ready.',
  }
  projection.preflight_summary = {
    ...projection.preflight_summary,
    selected_path: 'live',
    verdict: 'allowed',
    highest_safe_requested_mode: 'live',
    recommended_effective_mode: 'live',
    manual_review_required: false,
    counts: { total: 3, eligible: 3, ready: 3, degraded: 0, blocked: 0 },
    blockers: [],
    downgrade_reasons: [],
    summary: 'gate=execution_projection preflight=yes verdict=allowed requested=live selected=live highest_safe=live recommended=live manual_review=no ttl_ms=30000 blocks=0',
  }
  projection.summary = 'Requested live; selected live. live is benchmark-gated and execution_projection-first.'

  return projection
}

function makeBenchmarkResearchSignals() {
  return [
    {
      kind: 'news',
      title: 'Metaculus consensus tightens',
      summary: 'The community forecast nudges upward.',
      source_name: 'Metaculus',
      source_url: 'https://www.metaculus.com/questions/forecast-123/',
      captured_at: '2026-04-08T00:00:00.000Z',
      tags: ['forecast'],
      stance: 'supportive',
      payload: { probability_yes: 0.57 },
    },
    {
      kind: 'news',
      title: 'Manifold traders stay bullish',
      summary: 'The market price remains above the baseline.',
      source_name: 'Manifold',
      source_url: 'https://manifold.markets/m/sample-market',
      captured_at: '2026-04-08T00:00:00.000Z',
      tags: ['forecast', 'market'],
      stance: 'supportive',
      payload: { forecast_probability_yes: 0.63 },
    },
  ]
}


function makeRuntimeGuard(overrides: Partial<PredictionMarketRuntimeGuardResult> = {}): PredictionMarketRuntimeGuardResult {
  return {
    venue: 'polymarket',
    mode: 'discovery',
    verdict: 'degraded',
    reasons: ['venue health is degraded'],
    constraints: ['mode=discovery', 'venue=polymarket'],
    fallback_actions: ['keep_read_only', 'reduce_polling_cadence', 'downgrade_mode_to_shadow'],
    capabilities: {
      schema_version: '1.0.0',
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      supports_discovery: true,
      supports_metadata: true,
      supports_orderbook: true,
      supports_trades: true,
      supports_positions: true,
      supports_execution: true,
      supports_websocket: false,
      supports_paper_mode: false,
      planned_order_types: ['limit'],
      supported_order_types: ['limit'],
      automation_constraints: ['read-only advisory mode only'],
      last_verified_at: '2026-04-08T00:00:00.000Z',
    },
    health: {
      schema_version: '1.0.0',
      venue: 'polymarket',
      captured_at: '2026-04-08T00:00:00.000Z',
      health_score: 0.74,
      api_status: 'degraded',
      stream_status: 'degraded',
      staleness_ms: 12000,
      degraded_mode: 'degraded',
      incident_flags: ['stale_snapshot'],
      notes: 'Synthetic readiness test fixture.',
    },
    budgets: {
      schema_version: '1.0.0',
      fetch_latency_budget_ms: 15000,
      snapshot_freshness_budget_ms: 10000,
      decision_latency_budget_ms: 5000,
      stream_reconnect_budget_ms: 30000,
      cache_ttl_ms: 60000,
      max_retries: 0,
      backpressure_policy: 'degrade-to-wait',
    },
    ...overrides,
  }
}

function makeRuntimeGuardForMode(
  mode: PredictionMarketRuntimeGuardResult['mode'],
): PredictionMarketRuntimeGuardResult {
  if (mode === 'live') {
    return makeRuntimeGuard({
      mode,
      verdict: 'blocked',
      reasons: ['venue health is degraded', 'live automation remains disabled'],
      fallback_actions: ['downgrade_mode_to_shadow', 'disable_execution', 'keep_read_only'],
    })
  }

  return makeRuntimeGuard({
    mode,
    verdict: 'degraded',
    reasons: ['venue health is degraded'],
  })
}

function makeComplianceDecision(overrides: Partial<PredictionMarketComplianceDecision> = {}): PredictionMarketComplianceDecision {
  return {
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    requested_mode: 'discovery',
    effective_mode: 'paper',
    status: 'degraded',
    allowed: true,
    summary: 'Discovery mode is degraded to paper: manual review remains required.',
    reasons: [
      {
        code: 'manual_review_required',
        severity: 'warning',
        message: 'Upstream manual review remains required.',
      },
      {
        code: 'mode_downgraded',
        severity: 'warning',
        message: 'discovery mode was downgraded to paper.',
      },
    ],
    account_readiness: {
      jurisdiction_status: 'allowed',
      account_type: 'viewer',
      kyc_status: 'approved',
      api_key_present: true,
      trading_enabled: true,
      manual_review_required: true,
      ready_for_paper: true,
      ready_for_shadow: false,
      ready_for_live: false,
    },
    ...overrides,
  }
}

function makeComplianceDecisionForMode(
  mode: PredictionMarketComplianceDecision['requested_mode'],
): PredictionMarketComplianceDecision {
  if (mode === 'discovery') {
    return makeComplianceDecision({
      requested_mode: mode,
      effective_mode: 'discovery',
      status: 'authorized',
      summary: 'Discovery mode is authorized.',
      reasons: [],
      account_readiness: {
        jurisdiction_status: 'allowed',
        account_type: 'viewer',
        kyc_status: 'approved',
        api_key_present: true,
        trading_enabled: true,
        manual_review_required: true,
        ready_for_paper: true,
        ready_for_shadow: false,
        ready_for_live: false,
      },
    })
  }

  if (mode === 'paper') {
    return makeComplianceDecision({
      requested_mode: mode,
      effective_mode: 'paper',
      status: 'degraded',
      summary: 'Paper mode is degraded because polymarket has no native paper support.',
      reasons: [
        {
          code: 'paper_mode_native_unavailable',
          severity: 'warning',
          message: 'Paper mode is degraded because polymarket has no native paper support.',
        },
      ],
    })
  }

  if (mode === 'shadow') {
    return makeComplianceDecision({
      requested_mode: mode,
      effective_mode: 'paper',
      status: 'degraded',
      summary: 'Shadow mode is degraded to paper: polymarket is constrained to read-only advisory use.',
      reasons: [
        {
          code: 'read_only_automation_constraint',
          severity: 'warning',
          message: 'polymarket is constrained to read-only advisory use.',
        },
        {
          code: 'mode_downgraded',
          severity: 'warning',
          message: 'shadow mode was downgraded to paper.',
        },
      ],
    })
  }

  return makeComplianceDecision({
    requested_mode: mode,
    effective_mode: 'paper',
    status: 'degraded',
    summary: 'Live mode is degraded to paper: polymarket is constrained to read-only advisory use.',
    reasons: [
      {
        code: 'read_only_automation_constraint',
        severity: 'warning',
        message: 'polymarket is constrained to read-only advisory use.',
      },
      {
        code: 'mode_downgraded',
        severity: 'warning',
        message: 'live mode was downgraded to paper.',
      },
    ],
  })
}

function makeComplianceMatrixForReadiness(): PredictionMarketComplianceMatrix {
  const discovery = makeComplianceDecisionForMode('discovery')
  const paper = makeComplianceDecisionForMode('paper')
  const shadow = makeComplianceDecisionForMode('shadow')
  const live = makeComplianceDecision({
    requested_mode: 'live',
    effective_mode: 'live',
    status: 'authorized',
    allowed: true,
    summary: 'Live mode is authorized.',
    reasons: [],
    account_readiness: {
      jurisdiction_status: 'allowed',
      account_type: 'trading',
      kyc_status: 'approved',
      api_key_present: true,
      trading_enabled: true,
      manual_review_required: false,
      ready_for_paper: true,
      ready_for_shadow: true,
      ready_for_live: true,
    },
  })

  return {
    venue: 'polymarket',
    venue_type: 'execution-equivalent',
    highest_authorized_mode: 'live',
    account_readiness: live.account_readiness,
    decisions: {
      discovery,
      paper,
      shadow,
      live,
    },
  }
}

describe('prediction markets service execution readiness', () => {
  const market = makeDescriptor()
  const snapshot = makeSnapshot(market)
  const crossVenuePeer = makeDescriptor({
    venue: 'kalshi',
    market_id: 'execution-readiness-peer',
    slug: 'execution-readiness-peer',
    question: market.question,
    end_at: '2027-03-31T23:59:59.000Z',
  })
  const storedRunDetails = makeStoredRunDetails('run-execution-readiness-001', snapshot)

  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-08T00:00:00.000Z'))
    process.env.POLYMARKET_EXECUTION_BACKEND = 'live'
    process.env.POLYMARKET_EXECUTION_AUTH_TOKEN = 'test-live-token'
    process.env.POLYMARKET_EXECUTION_LIVE_ORDER_PATH = 'https://executor.example.test/polymarket/orders'
    process.env.POLYMARKET_EXECUTION_CANCEL_PATH = 'https://executor.example.test/polymarket/orders/cancel'

    mocks.buildPolymarketSnapshot.mockReset()
    mocks.listPolymarketMarkets.mockReset()
    mocks.buildKalshiSnapshot.mockReset()
    mocks.listKalshiMarkets.mockReset()
    mocks.findRecentPredictionMarketRunByConfig.mockReset()
    mocks.getStoredPredictionMarketRunDetails.mockReset()
    mocks.listPredictionMarketRuns.mockReset()
    mocks.persistPredictionMarketExecution.mockReset()
    mocks.createRun.mockReset()
    mocks.updateRun.mockReset()
    mocks.computeConfigHash.mockReset()
    mocks.getRun.mockReset()
    mocks.getVenueCapabilitiesContract.mockReset()
    mocks.getVenueCoverageContract.mockReset()
    mocks.getVenueHealthSnapshotContract.mockReset()
    mocks.getVenueFeedSurfaceContract.mockReset()
    mocks.getVenueBudgetsContract.mockReset()
    mocks.listPredictionMarketVenues.mockReset()
    mocks.evaluatePredictionMarketCompliance.mockReset()
    mocks.evaluatePredictionMarketRuntimeGuard.mockReset()

    mocks.computeConfigHash.mockImplementation(() => 'cfg-hash')
    mocks.buildPolymarketSnapshot.mockResolvedValue(snapshot)
    mocks.buildKalshiSnapshot.mockResolvedValue(snapshot)
    mocks.listPolymarketMarkets.mockResolvedValue([market])
    mocks.listKalshiMarkets.mockResolvedValue([crossVenuePeer])
    mocks.findRecentPredictionMarketRunByConfig.mockReturnValue(null)
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(storedRunDetails)
    mocks.listPredictionMarketRuns.mockReturnValue([])
    mocks.persistPredictionMarketExecution.mockReturnValue({
      summary: storedRunDetails.summary,
      artifactRefs: snapshot.market.market_id ? [] : [],
      manifest: storedRunDetails.artifacts.at(-1)?.payload,
    })
    mocks.createRun.mockReturnValue({ id: 'run-execution-readiness-001', started_at: '2026-04-08T00:00:00.000Z' })
    mocks.updateRun.mockReturnValue(undefined)
    mocks.getRun.mockReturnValue({ id: 'run-execution-readiness-001', status: 'completed' })
    mocks.listPredictionMarketVenues.mockReturnValue(['polymarket', 'kalshi'])
    mocks.getVenueCapabilitiesContract.mockImplementation(() => makeRuntimeGuard().capabilities)
    mocks.getVenueCoverageContract.mockReturnValue({
      schema_version: '1.0.0',
      venue_count: 2,
      execution_capable_count: 0,
      paper_capable_count: 1,
      read_only_count: 2,
      degraded_venue_count: 0,
      degraded_venue_rate: 0,
      execution_equivalent_count: 2,
      execution_like_count: 0,
      reference_only_count: 0,
      watchlist_only_count: 0,
      metadata_gap_count: 0,
      metadata_gap_rate: 0,
      execution_surface_rate: 0,
      availability_by_venue: {
        polymarket: {
          venue: 'polymarket',
          health_status: 'ready',
          degraded: false,
          supports_execution: false,
          supports_paper_mode: false,
          planned_order_types: ['limit'],
          supported_order_types: ['limit'],
        },
        kalshi: {
          venue: 'kalshi',
          health_status: 'ready',
          degraded: false,
          supports_execution: false,
          supports_paper_mode: true,
          planned_order_types: ['limit'],
          supported_order_types: ['limit'],
        },
      },
    })
    mocks.getVenueHealthSnapshotContract.mockImplementation(() => makeRuntimeGuard().health)
    mocks.getVenueFeedSurfaceContract.mockImplementation(() => ({
      schema_version: '1.0.0',
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      backend_mode: 'read_only',
      ingestion_mode: 'read_only',
      market_feed_kind: 'market_snapshot',
      user_feed_kind: 'position_snapshot',
      supports_discovery: true,
      supports_orderbook: true,
      supports_trades: true,
      supports_execution: false,
      supports_paper_mode: true,
      supports_market_feed: true,
      supports_user_feed: true,
      supports_events: true,
      supports_positions: true,
      supports_websocket: false,
      supports_rtds: false,
      live_streaming: false,
      api_access: ['source_of_truth:official_docs'],
      planned_order_types: ['limit'],
      supported_order_types: ['limit'],
      rate_limit_notes: ['read-only advisory mode only'],
      automation_constraints: ['read-only advisory mode only'],
      market_feed_transport: 'local_cache',
      user_feed_transport: 'local_cache',
      market_feed_status: 'local_cache',
      user_feed_status: 'local_cache',
      rtds_status: 'unavailable',
      events_source: 'snapshot_polling',
      positions_source: 'local_position_cache',
      market_feed_source: 'snapshot_polling',
      user_feed_source: 'local_position_cache',
      configured_endpoints: {
        market_feed_source: 'snapshot_polling',
        user_feed_source: 'local_position_cache',
      },
      summary: 'read-only feed surface',
      runbook: {},
      notes: [],
      metadata_gap_count: 0,
      metadata_gap_rate: 0,
      metadata_completeness: 1,
      metadata: {},
    }))
    mocks.getVenueBudgetsContract.mockImplementation(() => makeRuntimeGuard().budgets)
    mocks.evaluatePredictionMarketRuntimeGuard.mockImplementation((input: { mode: PredictionMarketRuntimeGuardResult['mode'] }) =>
      makeRuntimeGuardForMode(input.mode))
    mocks.evaluatePredictionMarketCompliance.mockImplementation((input: {
      mode: PredictionMarketComplianceDecision['requested_mode']
    }) => makeComplianceDecisionForMode(input.mode))
  })

  afterEach(() => {
    vi.useRealTimers()
    if (originalLiveTransportEnv.backend === undefined) delete process.env.POLYMARKET_EXECUTION_BACKEND
    else process.env.POLYMARKET_EXECUTION_BACKEND = originalLiveTransportEnv.backend
    if (originalLiveTransportEnv.token === undefined) delete process.env.POLYMARKET_EXECUTION_AUTH_TOKEN
    else process.env.POLYMARKET_EXECUTION_AUTH_TOKEN = originalLiveTransportEnv.token
    if (originalLiveTransportEnv.liveOrderPath === undefined) delete process.env.POLYMARKET_EXECUTION_LIVE_ORDER_PATH
    else process.env.POLYMARKET_EXECUTION_LIVE_ORDER_PATH = originalLiveTransportEnv.liveOrderPath
    if (originalLiveTransportEnv.cancelPath === undefined) delete process.env.POLYMARKET_EXECUTION_CANCEL_PATH
    else process.env.POLYMARKET_EXECUTION_CANCEL_PATH = originalLiveTransportEnv.cancelPath
  })

  it('attaches execution_readiness additively on advise and replay payloads', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: makeBenchmarkResearchSignals(),
    })

    const replayResult = await replayPredictionMarketRun({
      workspaceId: 1,
      actor: 'tester',
      runId: 'run-execution-readiness-001',
    })

    expect(adviseResult).toMatchObject({
      snapshot: expect.objectContaining({
        market: expect.objectContaining({
          market_id: market.market_id,
        }),
      }),
      runtime_guard: expect.objectContaining({
        verdict: 'degraded',
      }),
      compliance: expect.objectContaining({
        status: 'authorized',
      }),
      execution_readiness: expect.objectContaining({
        overall_verdict: 'blocked',
        highest_safe_mode: 'discovery',
        pipeline_status: 'degraded',
        cross_venue_summary: expect.objectContaining({
          manual_review: expect.any(Array),
        }),
      }),
      pipeline_guard: expect.objectContaining({
        venue_feed_surface: expect.objectContaining({
          backend_mode: 'read_only',
        }),
      }),
      prediction_run: expect.objectContaining({
        primary_strategy: expect.any(String),
        market_regime: expect.any(String),
        execution_intent_preview_kind: expect.any(String),
        resolution_anomalies: expect.any(Array),
      }),
    })

    expect(replayResult).toMatchObject({
      runtime_guard: expect.objectContaining({
        verdict: 'degraded',
      }),
      compliance: expect.objectContaining({
        status: 'authorized',
      }),
      execution_readiness: expect.objectContaining({
        overall_verdict: 'blocked',
        highest_safe_mode: 'discovery',
        pipeline_status: 'normal',
        cross_venue_summary: expect.objectContaining({
          manual_review: expect.any(Array),
        }),
      }),
      pipeline_guard: expect.objectContaining({
        status: 'normal',
        venue_feed_surface: expect.objectContaining({
          backend_mode: 'read_only',
        }),
      }),
      prediction_run: expect.objectContaining({
        primary_strategy: expect.any(String),
        market_regime: expect.any(String),
        execution_intent_preview_kind: expect.any(String),
        resolution_anomalies: expect.any(Array),
      }),
    })

    expect(adviseResult.execution_readiness.warnings).toEqual(expect.arrayContaining([
      'runtime:discovery mode degraded',
      'compliance:Paper mode is degraded because polymarket has no native paper support.',
      'compliance:Shadow mode is degraded to paper: polymarket is constrained to read-only advisory use.',
    ]))
    expect(replayResult.execution_readiness.warnings).toEqual(expect.arrayContaining([
      'runtime:discovery mode degraded',
      'compliance:Paper mode is degraded because polymarket has no native paper support.',
      'compliance:Shadow mode is degraded to paper: polymarket is constrained to read-only advisory use.',
    ]))
    expect(adviseResult.execution_readiness.blockers).toEqual(expect.arrayContaining([
      'runtime:live mode blocked',
      'runtime:venue health is degraded',
      'runtime:live automation remains disabled',
    ]))
    expect(replayResult.execution_readiness.blockers).toEqual(expect.arrayContaining([
      'runtime:live mode blocked',
      'runtime:venue health is degraded',
      'runtime:live automation remains disabled',
    ]))
    expect(adviseResult.execution_readiness.cross_venue_summary.manual_review.length).toBeGreaterThan(0)
    expect(replayResult.execution_readiness.cross_venue_summary.manual_review.length).toBeGreaterThan(0)
  })

  it('attaches research forecast hints additively on advise payloads when research signals are present', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: [
        {
          kind: 'news',
          title: 'Metaculus consensus tightens',
          summary: 'The community forecast nudges upward.',
          source_name: 'Metaculus',
          source_url: 'https://www.metaculus.com/questions/forecast-123/',
          captured_at: '2026-04-08T00:00:00.000Z',
          tags: ['forecast'],
          stance: 'supportive',
          payload: { probability_yes: 0.57 },
        },
        {
          kind: 'news',
          title: 'Manifold traders stay bullish',
          summary: 'The market price remains above the baseline.',
          source_name: 'Manifold',
          source_url: 'https://manifold.markets/m/sample-market',
          captured_at: '2026-04-08T00:00:00.000Z',
          tags: ['forecast', 'market'],
          stance: 'supportive',
          payload: { forecast_probability_yes: 0.63 },
        },
      ],
    })

    expect(adviseResult.research_sidecar).toBeDefined()
    expect(adviseResult.research_sidecar?.synthesis.pipeline_version_metadata).toMatchObject({
      pipeline_id: 'polymarket-research-pipeline',
      pipeline_version: 'poly-025-research-v1',
    })
    expect(adviseResult.research_sidecar?.synthesis.comparative_report.summary).toContain('Preferred mode: aggregate.')
    expect(adviseResult.forecast).toMatchObject({
      basis: 'market_midpoint',
      comparator_id: 'candidate_research_aggregate',
    })
    expect(adviseResult.recommendation.why_now.join(' ')).toContain(
      'Research-driven forecast sets fair value to',
    )
    expect(adviseResult.recommendation.why_not_now).not.toContain(
      'Current fair value is still derived from the market itself, so no exogenous edge is proven yet.',
    )
    expect(adviseResult.prediction_run).toMatchObject({
      research_pipeline_id: 'polymarket-research-pipeline',
      research_pipeline_version: 'poly-025-research-v1',
      research_compare_preferred_mode: 'aggregate',
      research_compare_summary: expect.stringContaining('Preferred mode: aggregate.'),
      research_recommendation_origin: 'research_driven',
      research_recommendation_origin_summary: expect.stringContaining('research-driven forecast'),
      research_abstention_flipped_recommendation: false,
      research_abstention_policy_version: 'structured-abstention-v1',
      research_abstention_policy_blocks_forecast: false,
      research_forecast_probability_yes_hint: adviseResult.forecast.probability_yes,
      research_benchmark_gate_summary: expect.stringContaining('benchmark gate:'),
      research_benchmark_uplift_bps: expect.any(Number),
      research_benchmark_verdict: 'preview_only',
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'unproven',
      research_benchmark_promotion_ready: false,
      research_benchmark_preview_available: true,
      research_benchmark_promotion_evidence: 'unproven',
      research_benchmark_evidence_level: 'benchmark_preview',
      research_promotion_gate_kind: 'preview_only',
      research_benchmark_promotion_blocker_summary: 'out_of_sample_unproven',
      research_benchmark_promotion_summary: 'out_of_sample_unproven',
      research_benchmark_gate_blockers: ['out_of_sample_unproven'],
      research_benchmark_gate_reasons: ['out_of_sample_unproven'],
      benchmark_gate_summary: expect.stringContaining('benchmark gate:'),
      benchmark_uplift_bps: expect.any(Number),
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'unproven',
      benchmark_promotion_ready: false,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'unproven',
      benchmark_evidence_level: 'benchmark_preview',
      benchmark_promotion_gate_kind: 'preview_only',
      benchmark_gate_blockers: ['out_of_sample_unproven'],
      benchmark_gate_reasons: ['out_of_sample_unproven'],
      benchmark_promotion_summary: 'out_of_sample_unproven',
      research_runtime_summary: expect.stringContaining(
        'research: mode=research_driven pipeline=polymarket-research-pipeline version=poly-025-research-v1',
      ),
    })
    expect(adviseResult.prediction_run.research_forecaster_count).toBeGreaterThan(0)
    expect(adviseResult.prediction_run.research_weighted_probability_yes).toBeGreaterThan(0.5)
    expect(adviseResult.prediction_run.research_weighted_coverage).toBeGreaterThan(0)
  })

  it('promotes a research-driven manual thesis away from market_midpoint in runtime advise output', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: [
        ...makeBenchmarkResearchSignals(),
        {
          kind: 'manual_note',
          title: 'Analyst conviction shifts higher',
          summary: 'A manual thesis overrides the midpoint anchor.',
          source_name: 'Analyst note',
          source_url: 'https://example.com/manual-thesis',
          captured_at: '2026-04-08T00:00:00.000Z',
          tags: ['thesis'],
          stance: 'supportive',
          thesis_probability: 0.74,
          thesis_rationale: 'Manual thesis now moves the fair value away from the midpoint.',
          payload: { thesis_probability: 0.74 },
        },
      ],
    })

    expect(adviseResult.forecast).toMatchObject({
      basis: 'manual_thesis',
      comparator_id: 'candidate_manual_thesis',
      probability_yes: 0.74,
    })
    expect(adviseResult.recommendation.why_now.join(' ')).toContain('Manual thesis sets fair value to 74.0%')
    expect(adviseResult.recommendation.why_not_now).not.toContain(
      'Current fair value is still derived from the market itself, so no exogenous edge is proven yet.',
    )
    expect(adviseResult.prediction_run).toMatchObject({
      research_recommendation_origin: 'manual_thesis',
      research_recommendation_origin_summary: expect.stringContaining('manual thesis override'),
      research_abstention_flipped_recommendation: false,
      approval_ticket: expect.objectContaining({
        summary: expect.any(String),
      }),
      operator_thesis: expect.objectContaining({
        source: 'manual_thesis',
        probability_yes: 0.74,
      }),
      research_pipeline_trace: expect.objectContaining({
        preferred_mode: 'aggregate',
        oracle_family: 'llm_superforecaster',
      }),
      approval_ticket_summary: expect.any(String),
      operator_thesis_summary: expect.stringContaining('74% yes via manual_thesis'),
      research_pipeline_trace_summary: expect.any(String),
    })
    expect(adviseResult.execution_pathways).toMatchObject({
      approval_ticket: expect.objectContaining({
        summary: expect.any(String),
      }),
      operator_thesis: expect.objectContaining({
        source: 'manual_thesis',
        probability_yes: 0.74,
      }),
      research_pipeline_trace: expect.objectContaining({
        preferred_mode: 'aggregate',
        oracle_family: 'llm_superforecaster',
      }),
    })
    const readbackDetails = {
      ...storedRunDetails,
      artifacts: [
        ...storedRunDetails.artifacts,
        {
          artifact_type: 'execution_pathways',
          payload: adviseResult.execution_pathways,
        },
      ],
    }
    mocks.getStoredPredictionMarketRunDetails.mockReturnValueOnce(readbackDetails)
    expect(getPredictionMarketRunDetails(adviseResult.run.id, 1)).toMatchObject({
      approval_ticket: expect.objectContaining({
        summary: expect.any(String),
      }),
      operator_thesis: expect.objectContaining({
        source: 'manual_thesis',
        probability_yes: 0.74,
      }),
      research_pipeline_trace: expect.objectContaining({
        preferred_mode: 'aggregate',
        oracle_family: 'llm_superforecaster',
      }),
      execution_pathways: expect.objectContaining({
        approval_ticket: expect.objectContaining({
          summary: expect.any(String),
        }),
        operator_thesis: expect.objectContaining({
          source: 'manual_thesis',
          probability_yes: 0.74,
        }),
        research_pipeline_trace: expect.objectContaining({
          preferred_mode: 'aggregate',
          oracle_family: 'llm_superforecaster',
        }),
      }),
    })
  })

  it('keeps paper and shadow surfaces ready while exposing the benchmark gate hints additively', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: [
        {
          kind: 'news',
          title: 'Metaculus consensus tightens',
          summary: 'The community forecast nudges upward.',
          source_name: 'Metaculus',
          source_url: 'https://www.metaculus.com/questions/forecast-123/',
          captured_at: '2026-04-08T00:00:00.000Z',
          tags: ['forecast'],
          stance: 'supportive',
          payload: { probability_yes: 0.57 },
        },
      ],
    })

    const benchmarkedExecutionProjection = {
      gate_name: 'execution_projection',
      preflight_only: true,
      requested_path: 'live',
      selected_path: 'shadow',
      eligible_paths: ['paper', 'shadow'],
      verdict: 'downgraded',
      blocking_reasons: [],
      downgrade_reasons: ['capital_ledger_unavailable'],
      manual_review_required: true,
      generated_at: '2026-04-08T00:00:00.000Z',
      ttl_ms: 30_000,
      expires_at: '2026-04-08T00:00:30.000Z',
      projected_paths: {
        paper: {
          path: 'paper',
          requested_mode: 'paper',
          effective_mode: 'paper',
          status: 'ready',
          allowed: true,
          blockers: [],
          warnings: [],
          reason_summary: 'Paper projection is ready.',
          simulation: {
            expected_fill_confidence: 0.97,
            expected_slippage_bps: 0,
            stale_quote_risk: 'low',
            quote_age_ms: 0,
            notes: [],
            shadow_arbitrage: null,
          },
          trade_intent_preview: {
            size_usd: 25,
            limit_price: 0.47,
            time_in_force: 'day',
            max_slippage_bps: 20,
          },
          canonical_trade_intent_preview: {
            size_usd: 25,
            limit_price: 0.47,
            time_in_force: 'day',
            max_slippage_bps: 20,
          },
          sizing_signal: {
            preview_size_usd: 25,
            base_size_usd: 25,
            recommended_size_usd: 25,
            max_size_usd: 25,
            canonical_size_usd: 25,
            shadow_recommended_size_usd: null,
            limit_price: 0.47,
            max_slippage_bps: 20,
            max_unhedged_leg_ms: null,
            time_in_force: 'day',
            multiplier: 1,
            sizing_source: 'default',
            source: 'trade_intent_preview',
            notes: [],
          },
          shadow_arbitrage_signal: null,
        },
        shadow: {
          path: 'shadow',
          requested_mode: 'shadow',
          effective_mode: 'shadow',
          status: 'ready',
          allowed: true,
          blockers: [],
          warnings: [],
          reason_summary: 'Shadow projection is ready.',
          simulation: {
            expected_fill_confidence: 0.91,
            expected_slippage_bps: 22,
            stale_quote_risk: 'medium',
            quote_age_ms: 850,
            notes: [],
            shadow_arbitrage: {
              read_only: true,
              generated_at: '2026-04-08T00:00:01.000Z',
              as_of_at: '2026-04-08T00:00:01.000Z',
              executable_edge: { edge_id: 'shadow-edge' },
              microstructure_summary: { recommended_mode: 'shadow' },
              sizing: {
                requested_size_usd: null,
                base_size_usd: 100,
                recommended_size_usd: 60,
                simulated_size_usd: 60,
                size_multiplier: 0.6,
              },
              failure_cases: [],
              summary: {
                shadow_edge_bps: 82,
                recommended_size_usd: 60,
              },
            },
          },
          trade_intent_preview: {
            size_usd: 60,
            limit_price: 0.49,
            time_in_force: 'ioc',
            max_slippage_bps: 35,
          },
          canonical_trade_intent_preview: {
            size_usd: 60,
            limit_price: 0.49,
            time_in_force: 'ioc',
            max_slippage_bps: 35,
          },
          sizing_signal: {
            preview_size_usd: 60,
            base_size_usd: 60,
            recommended_size_usd: 60,
            max_size_usd: 60,
            canonical_size_usd: 60,
            shadow_recommended_size_usd: 60,
            limit_price: 0.49,
            max_slippage_bps: 35,
            max_unhedged_leg_ms: 5000,
            time_in_force: 'ioc',
            multiplier: 0.6,
            sizing_source: 'default',
            source: 'trade_intent_preview+shadow_arbitrage',
            notes: [],
          },
          shadow_arbitrage_signal: {
            read_only: true,
            market_id: market.market_id,
            venue: 'polymarket',
            base_executable_edge_bps: 110,
            shadow_edge_bps: 82,
            recommended_size_usd: 60,
            hedge_success_probability: 0.91,
            estimated_net_pnl_bps: 24,
            estimated_net_pnl_usd: 15,
            worst_case_kind: 'hedge_delay',
            failure_case_count: 2,
          },
        },
      },
      basis: {
        uses_execution_readiness: true,
        uses_compliance: true,
        uses_capital: false,
        uses_reconciliation: false,
        uses_microstructure: false,
        capital_status: 'unavailable',
        reconciliation_status: 'unavailable',
        source_refs: {
          pipeline_guard: 'run-benchmark-surface-001:pipeline_guard',
          compliance_report: 'run-benchmark-surface-001:compliance_report',
          execution_readiness: 'run-benchmark-surface-001:execution_readiness',
          venue_health: 'run-benchmark-surface-001:pipeline_guard#venue_health',
          capital_ledger: null,
          reconciliation: null,
          microstructure_lab: null,
        },
        canonical_gate: {
          gate_name: 'execution_projection',
          single_runtime_gate: true,
          enforced_for_modes: ['paper', 'shadow', 'live'],
        },
      },
      microstructure_summary: null,
      modes: {
        paper: {
          requested_mode: 'paper',
          verdict: 'ready',
          effective_mode: 'paper',
          blockers: [],
          warnings: [],
          summary: 'Paper projection is ready.',
        },
        shadow: {
          requested_mode: 'shadow',
          verdict: 'ready',
          effective_mode: 'shadow',
          blockers: [],
          warnings: [],
          summary: 'Shadow projection is ready.',
        },
        live: {
          requested_mode: 'live',
          verdict: 'blocked',
          effective_mode: 'shadow',
          blockers: ['capital_ledger_unavailable'],
          warnings: [],
          summary: 'Live projection is blocked.',
        },
      },
      highest_safe_requested_mode: 'shadow',
      recommended_effective_mode: 'shadow',
      preflight_summary: {
        gate_name: 'execution_projection',
        preflight_only: true,
        requested_path: 'live',
        selected_path: 'shadow',
        verdict: 'downgraded',
        highest_safe_requested_mode: 'shadow',
        recommended_effective_mode: 'shadow',
        manual_review_required: true,
        ttl_ms: 30_000,
        expires_at: '2026-04-08T00:00:30.000Z',
        counts: { total: 3, eligible: 2, ready: 2, degraded: 0, blocked: 1 },
        basis: {
          uses_execution_readiness: true,
          uses_compliance: true,
          uses_capital: false,
          uses_reconciliation: false,
          uses_microstructure: false,
          capital_status: 'unavailable',
          reconciliation_status: 'unavailable',
        },
        source_refs: [
          'run-benchmark-surface-001:pipeline_guard',
          'run-benchmark-surface-001:compliance_report',
          'run-benchmark-surface-001:execution_readiness',
        ],
        blockers: [],
        downgrade_reasons: ['capital_ledger_unavailable'],
        microstructure: null,
        summary: 'gate=execution_projection preflight=yes verdict=downgraded requested=live selected=shadow highest_safe=shadow recommended=shadow manual_review=yes ttl_ms=30000 blocks=0',
      },
    } as const

    const benchmarkedRunDetails = {
      run: { id: 'run-benchmark-surface-001', status: 'completed' },
      summary: {
        run_id: 'run-benchmark-surface-001',
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: market.market_id,
        market_slug: market.slug ?? null,
        status: 'completed',
        recommendation: 'bet',
        side: 'yes',
        confidence: 0.55,
        probability_yes: 0.7,
        market_price_yes: 0.5,
        edge_bps: 1900,
      },
      artifacts: [],
      run_id: 'run-benchmark-surface-001',
      workspace_id: 1,
      execution_projection: benchmarkedExecutionProjection,
      execution_readiness: adviseResult.execution_readiness,
      execution_pathways: adviseResult.execution_pathways,
      research_sidecar: adviseResult.research_sidecar,
      paper_surface: null,
      replay_surface: null,
      shadow_arbitrage: adviseResult.shadow_arbitrage ?? null,
      trade_intent_guard: adviseResult.trade_intent_guard ?? null,
      execution_projection_selected_preview_source: 'trade_intent_preview',
      multi_venue_execution: adviseResult.multi_venue_execution ?? null,
    } as never
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(benchmarkedRunDetails)

    const paperPlan = preparePredictionMarketRunPaper({
      workspaceId: 1,
      runId: 'run-benchmark-surface-001',
    })
    const shadowPlan = preparePredictionMarketRunShadow({
      workspaceId: 1,
      runId: 'run-benchmark-surface-001',
    })

    expect(paperPlan).toMatchObject({
      paper_status: 'ready',
      paper_blocking_reasons: [],
      benchmark_surface_blocking_reasons: [],
      benchmark_promotion_blockers: ['research_benchmark:out_of_sample_unproven'],
      benchmark_promotion_ready: false,
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'unproven',
      research_benchmark_promotion_ready: false,
      research_benchmark_gate_blockers: ['out_of_sample_unproven'],
      research_benchmark_gate_reasons: ['out_of_sample_unproven'],
    })
    expect(paperPlan.research_benchmark_gate_summary).toContain('benchmark gate:')
    expect(paperPlan.paper_trade_intent_preview_source).toBe('canonical_trade_intent_preview')
    expect(paperPlan.summary).toContain('Paper surface is ready')

    expect(shadowPlan).toMatchObject({
      shadow_status: 'ready',
      shadow_blocking_reasons: [],
      benchmark_surface_blocking_reasons: [],
      benchmark_promotion_blockers: ['research_benchmark:out_of_sample_unproven'],
      benchmark_promotion_ready: false,
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'unproven',
      research_benchmark_promotion_ready: false,
      research_benchmark_gate_blockers: ['out_of_sample_unproven'],
      research_benchmark_gate_reasons: ['out_of_sample_unproven'],
    })
    expect(shadowPlan.research_benchmark_gate_summary).toContain('benchmark gate:')
    expect(shadowPlan.shadow_trade_intent_preview_source).toBe('canonical_trade_intent_preview')
    expect(shadowPlan.summary).toContain('Shadow surface is ready')
  })

  it('blocks live when execution_projection does not canonically select live and benchmark promotion is still unproven', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: makeBenchmarkResearchSignals(),
    })

    const benchmarkedRunDetails = {
      run: { id: 'run-benchmark-live-blocked-001', status: 'completed' },
      summary: {
        run_id: 'run-benchmark-live-blocked-001',
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: market.market_id,
        market_slug: market.slug ?? null,
        status: 'completed',
        recommendation: 'bet',
        side: 'yes',
        confidence: 0.55,
        probability_yes: 0.7,
        market_price_yes: 0.5,
        edge_bps: 1900,
      },
      artifacts: [],
      run_id: 'run-benchmark-live-blocked-001',
      workspace_id: 1,
      execution_projection: makeBenchmarkExecutionProjection(),
      execution_readiness: adviseResult.execution_readiness,
      execution_pathways: adviseResult.execution_pathways,
      research_sidecar: adviseResult.research_sidecar,
      paper_surface: null,
      replay_surface: null,
      shadow_arbitrage: adviseResult.shadow_arbitrage ?? null,
      trade_intent_guard: adviseResult.trade_intent_guard ?? null,
      multi_venue_execution: adviseResult.multi_venue_execution ?? null,
      venue_feed_surface: {
        venue: 'polymarket',
        backend_mode: 'read_only',
        market_feed_status: 'local_cache',
        user_feed_status: 'local_cache',
        rtds_status: 'unavailable',
        summary: 'Read-only market and user feed surface; live websocket unavailable.',
      },
    } as never
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(benchmarkedRunDetails)

    const livePlan = preparePredictionMarketRunLive({
      workspaceId: 1,
      runId: 'run-benchmark-live-blocked-001',
    })

    expect(livePlan).toMatchObject({
      live_route_allowed: false,
      live_status: 'blocked',
      benchmark_surface_blocking_reasons: [],
      benchmark_promotion_blockers: ['benchmark:out_of_sample_unproven'],
      benchmark_promotion_ready: false,
      benchmark_gate_blocks_live: false,
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'unproven',
      research_benchmark_promotion_ready: false,
      live_path: null,
    })
    expect(livePlan.venue_feed_surface).toMatchObject({
      backend_mode: 'read_only',
      market_feed_status: 'local_cache',
      user_feed_status: 'local_cache',
    })
    expect(livePlan.venue_feed_surface_summary).toContain('Read-only market and user feed surface')
    expect(livePlan.venue_pathway_summary).toContain('execution pathways remain inactive')
    expect(livePlan.research_benchmark_gate_blockers).toEqual(
      expect.arrayContaining(['out_of_sample_unproven']),
    )
    expect(livePlan.research_benchmark_gate_reasons).toEqual(
      expect.arrayContaining(['out_of_sample_unproven']),
    )
    expect(livePlan.live_blocking_reasons).toEqual(
      expect.arrayContaining(['selected_path_not_live']),
    )
    expect(livePlan.summary).toContain('Live surface is blocked')
    expect(livePlan.summary).toContain('rollback=paper')
  })

  it('keeps live blocked until the benchmark promotion gate is satisfied even when the live projection path is ready', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
    })

    const benchmarkedRunDetails = {
      run: { id: 'run-benchmark-live-ready-path-001', status: 'completed' },
      summary: {
        run_id: 'run-benchmark-live-ready-path-001',
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: market.market_id,
        market_slug: market.slug ?? null,
        status: 'completed',
        recommendation: 'bet',
        side: 'yes',
        confidence: 0.55,
        probability_yes: 0.7,
        market_price_yes: 0.5,
        edge_bps: 1900,
      },
      artifacts: [],
      run_id: 'run-benchmark-live-ready-path-001',
      workspace_id: 1,
      execution_projection: makeLiveBenchmarkExecutionProjection(),
      execution_readiness: adviseResult.execution_readiness,
      execution_pathways: adviseResult.execution_pathways,
      research_sidecar: adviseResult.research_sidecar,
      research_benchmark_promotion_ready: false,
      paper_surface: null,
      replay_surface: null,
      shadow_arbitrage: adviseResult.shadow_arbitrage ?? null,
      trade_intent_guard: adviseResult.trade_intent_guard ?? null,
      multi_venue_execution: adviseResult.multi_venue_execution ?? null,
      venue_feed_surface: {
        venue: 'polymarket',
        backend_mode: 'read_only',
        market_feed_status: 'local_cache',
        user_feed_status: 'local_cache',
        rtds_status: 'unavailable',
        summary: 'Read-only market and user feed surface; live websocket unavailable.',
      },
    } as never
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(benchmarkedRunDetails)

    const livePlan = preparePredictionMarketRunLive({
      workspaceId: 1,
      runId: 'run-benchmark-live-ready-path-001',
    })
    const liveRunDetails = getPredictionMarketRunDetails('run-benchmark-live-ready-path-001', 1)
    expect(livePlan).toMatchObject({
      live_route_allowed: false,
      live_status: 'blocked',
      benchmark_surface_blocking_reasons: [],
      benchmark_promotion_blockers: ['benchmark:out_of_sample_unproven'],
      benchmark_promotion_ready: false,
      benchmark_gate_blocks_live: true,
      benchmark_gate_live_block_reason: expect.stringContaining('out_of_sample_unproven'),
      research_benchmark_gate_blocks_live: true,
      research_benchmark_live_block_reason: expect.stringContaining('out_of_sample_unproven'),
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'unproven',
      research_benchmark_promotion_ready: false,
      live_path: {
        path: 'live',
        status: 'ready',
        effective_mode: 'live',
      },
      live_trade_intent_preview_source: 'canonical_trade_intent_preview',
    })
    expect(livePlan.venue_feed_surface).toMatchObject({
      backend_mode: 'read_only',
      market_feed_status: 'local_cache',
      user_feed_status: 'local_cache',
    })
    expect(livePlan.venue_feed_surface_summary).toContain('Read-only market and user feed surface')
    expect(livePlan.venue_pathway_summary).toContain('execution pathways remain inactive')
    expect(livePlan.research_benchmark_gate_blockers).toEqual(
      expect.arrayContaining(['out_of_sample_unproven']),
    )
    expect(livePlan.trade_intent_guard?.blocked_reasons).toEqual(
      expect.arrayContaining(['benchmark_promotion_not_ready_for_live']),
    )
    expect(livePlan.trade_intent_guard?.metadata).toMatchObject({
      benchmark_promotion_ready: false,
      benchmark_promotion_gate_kind: null,
      benchmark_promotion_blocker_summary: expect.stringContaining('out_of_sample_unproven'),
      benchmark_gate_blocks_live: true,
      benchmark_gate_live_block_reason: expect.stringContaining('out_of_sample_unproven'),
    })
    expect(liveRunDetails?.benchmark_gate_blocks_live).toBe(true)
    expect(liveRunDetails?.benchmark_gate_live_block_reason).toContain('out_of_sample_unproven')
    expect(livePlan.live_trade_intent_preview).toMatchObject({ size_usd: 40 })
    expect(livePlan.live_trade_intent_preview_source).toBe('canonical_trade_intent_preview')
    expect(livePlan.live_blocking_reasons).toEqual(
      expect.arrayContaining(['benchmark:out_of_sample_unproven']),
    )
    expect(livePlan.summary).toContain('Live surface is blocked')
    expect(livePlan.summary).toContain('rollback=shadow')
  })

  it('adds an explicit kill-switch hint when the canonical benchmark live gate carries a kill-switch reason', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: makeBenchmarkResearchSignals(),
    })

    const killSwitchTradeIntentGuard = structuredClone(adviseResult.trade_intent_guard) as NonNullable<
      typeof adviseResult.trade_intent_guard
    >
    killSwitchTradeIntentGuard.metadata = {
      ...(killSwitchTradeIntentGuard.metadata ?? {}),
      benchmark_gate_live_block_reason: 'runtime_guard_kill_switch',
      benchmark_promotion_blocker_summary: 'runtime_guard_kill_switch',
      benchmark_promotion_summary: 'runtime_guard_kill_switch',
    }

    const killSwitchRunDetails = {
      run: { id: 'run-benchmark-live-kill-switch-001', status: 'completed' },
      summary: {
        run_id: 'run-benchmark-live-kill-switch-001',
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: market.market_id,
        market_slug: market.slug ?? null,
        status: 'completed',
        recommendation: 'bet',
        side: 'yes',
        confidence: 0.55,
        probability_yes: 0.7,
        market_price_yes: 0.5,
        edge_bps: 1900,
      },
      artifacts: [],
      run_id: 'run-benchmark-live-kill-switch-001',
      workspace_id: 1,
      execution_projection: makeLiveBenchmarkExecutionProjection(),
      execution_readiness: adviseResult.execution_readiness,
      execution_pathways: adviseResult.execution_pathways,
      research_sidecar: adviseResult.research_sidecar,
      paper_surface: null,
      replay_surface: null,
      shadow_arbitrage: adviseResult.shadow_arbitrage ?? null,
      trade_intent_guard: killSwitchTradeIntentGuard,
      multi_venue_execution: adviseResult.multi_venue_execution ?? null,
      venue_feed_surface: {
        venue: 'polymarket',
        backend_mode: 'read_only',
        market_feed_status: 'local_cache',
        user_feed_status: 'local_cache',
        rtds_status: 'unavailable',
        summary: 'Read-only market and user feed surface; live websocket unavailable.',
      },
    } as never
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(killSwitchRunDetails)

    const livePlan = preparePredictionMarketRunLive({
      workspaceId: 1,
      runId: 'run-benchmark-live-kill-switch-001',
    })

    expect(livePlan.live_status).toBe('blocked')
    expect(livePlan.summary).toContain('rollback=shadow')
    expect(livePlan.summary).toContain('kill_switch=inspect')
  })

  it('propagates the benchmark live gate into the canonical advisor architecture metadata', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
    })

    const benchmarkedRunDetails = {
      run: { id: 'run-benchmark-architecture-001', status: 'completed' },
      summary: {
        run_id: 'run-benchmark-architecture-001',
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: market.market_id,
        market_slug: market.slug ?? null,
        status: 'completed',
        recommendation: 'bet',
        side: 'yes',
        confidence: 0.55,
        probability_yes: 0.7,
        market_price_yes: 0.5,
        edge_bps: 1900,
      },
      artifacts: [],
      run_id: 'run-benchmark-architecture-001',
      workspace_id: 1,
      execution_projection: makeLiveBenchmarkExecutionProjection(),
      execution_readiness: adviseResult.execution_readiness,
      execution_pathways: adviseResult.execution_pathways,
      research_sidecar: adviseResult.research_sidecar,
      research_benchmark_promotion_ready: false,
      paper_surface: null,
      replay_surface: null,
      shadow_arbitrage: adviseResult.shadow_arbitrage ?? null,
      trade_intent_guard: adviseResult.trade_intent_guard ?? null,
      multi_venue_execution: adviseResult.multi_venue_execution ?? null,
    } as never
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(benchmarkedRunDetails)

    const details = getPredictionMarketRunDetails('run-benchmark-architecture-001', 1)

    expect(details?.trade_intent_guard?.blocked_reasons).toEqual(
      expect.arrayContaining(['benchmark_promotion_not_ready_for_live']),
    )
    expect(details?.trade_intent_guard?.metadata).toMatchObject({
      benchmark_promotion_ready: false,
      benchmark_promotion_gate_kind: null,
      benchmark_promotion_blocker_summary: expect.stringContaining('out_of_sample_unproven'),
      benchmark_gate_blocks_live: true,
      benchmark_gate_live_block_reason: expect.stringContaining('out_of_sample_unproven'),
    })
  })

  it('rehydrates dispatch trade_intent_guard metadata for live promotion gating', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: makeBenchmarkResearchSignals(),
    })

    const readyTradeIntentGuard = structuredClone(adviseResult.trade_intent_guard) as NonNullable<
      typeof adviseResult.trade_intent_guard
    >
    readyTradeIntentGuard.verdict = 'allowed'
    readyTradeIntentGuard.manual_review_required = false
    readyTradeIntentGuard.selected_path = 'live'
    readyTradeIntentGuard.highest_safe_mode = 'live'
    readyTradeIntentGuard.blocked_reasons = []
    readyTradeIntentGuard.metadata = {
      ...(readyTradeIntentGuard.metadata ?? {}),
      trade_intent_preview_available: true,
      trade_intent_preview_source: 'canonical_trade_intent_preview',
      trade_intent_preview_via: 'execution_projection_selected_preview',
      trade_intent_preview_uses_projection_selected_preview: true,
      execution_projection_selected_preview_available: true,
      execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
      trade_intent_preview_capped_to_canonical_size: false,
      selected_projection_path_status: 'ready',
      selected_projection_path_effective_mode: 'live',
      selected_projection_sizing_signal_present: true,
      selected_projection_shadow_arbitrage_signal_present: false,
      selected_projection_canonical_size_usd: 40,
    }

    const benchmarkedRunDetails = {
      run: { id: 'run-benchmark-dispatch-live-001', status: 'completed' },
      summary: {
        run_id: 'run-benchmark-dispatch-live-001',
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: market.market_id,
        market_slug: market.slug ?? null,
        status: 'completed',
        recommendation: 'bet',
        side: 'yes',
        confidence: 0.55,
        probability_yes: 0.7,
        market_price_yes: 0.5,
        edge_bps: 1900,
      },
      artifacts: [],
      run_id: 'run-benchmark-dispatch-live-001',
      workspace_id: 1,
      execution_projection: makeLiveBenchmarkExecutionProjection(),
      execution_readiness: adviseResult.execution_readiness,
      execution_pathways: adviseResult.execution_pathways,
      research_sidecar: adviseResult.research_sidecar,
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'unproven',
      research_benchmark_promotion_ready: false,
      research_benchmark_preview_available: true,
      research_benchmark_promotion_evidence: 'unproven',
      research_benchmark_verdict: 'preview_only',
      research_benchmark_evidence_level: 'benchmark_preview',
      research_promotion_gate_kind: 'preview_only',
      research_benchmark_promotion_blocker_summary: 'out_of_sample_unproven',
      research_benchmark_gate_blockers: ['out_of_sample_unproven'],
      research_benchmark_gate_reasons: ['out_of_sample_unproven'],
      benchmark_gate_summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
      benchmark_uplift_bps: 1100,
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'unproven',
      benchmark_promotion_ready: false,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'unproven',
      benchmark_evidence_level: 'benchmark_preview',
      benchmark_promotion_gate_kind: 'preview_only',
      benchmark_promotion_blocker_summary: 'out_of_sample_unproven',
      benchmark_gate_blockers: ['out_of_sample_unproven'],
      benchmark_gate_reasons: ['out_of_sample_unproven'],
      paper_surface: null,
      replay_surface: null,
      shadow_arbitrage: adviseResult.shadow_arbitrage ?? null,
      trade_intent_guard: readyTradeIntentGuard,
      multi_venue_execution: adviseResult.multi_venue_execution ?? null,
    } as never
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(benchmarkedRunDetails)

    const dispatchPlan = preparePredictionMarketRunDispatch({
      workspaceId: 1,
      runId: 'run-benchmark-dispatch-live-001',
    })

    expect(dispatchPlan).toMatchObject({
      dispatch_status: 'blocked',
      benchmark_promotion_blockers: ['benchmark:out_of_sample_unproven'],
      benchmark_promotion_ready: false,
      trade_intent_guard: {
        verdict: 'blocked',
        blocked_reasons: expect.arrayContaining(['benchmark_promotion_not_ready_for_live']),
      },
    })
    expect(dispatchPlan.dispatch_blocking_reasons).toEqual(
      expect.arrayContaining([
        'trade_intent_guard:benchmark_promotion_not_ready_for_live',
        'benchmark:out_of_sample_unproven',
      ]),
    )
    expect(dispatchPlan.trade_intent_guard?.metadata).toMatchObject({
      benchmark_promotion_ready: false,
      benchmark_gate_blocks_live: true,
      benchmark_gate_live_block_reason: expect.stringContaining('out_of_sample_unproven'),
    })
  })

  it('promotes paper, shadow, and live surfaces when the benchmark gate is satisfied and live is canonically selected', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: makeBenchmarkResearchSignals(),
    })

    const readyTradeIntentGuard = structuredClone(adviseResult.trade_intent_guard) as NonNullable<
      typeof adviseResult.trade_intent_guard
    >
    readyTradeIntentGuard.verdict = 'allowed'
    readyTradeIntentGuard.manual_review_required = false
    readyTradeIntentGuard.selected_path = 'live'
    readyTradeIntentGuard.highest_safe_mode = 'live'
    readyTradeIntentGuard.blocked_reasons = []
    readyTradeIntentGuard.metadata = {
      ...(readyTradeIntentGuard.metadata ?? {}),
      trade_intent_preview_available: true,
      trade_intent_preview_source: 'canonical_trade_intent_preview',
      trade_intent_preview_via: 'execution_projection_selected_preview',
      trade_intent_preview_uses_projection_selected_preview: true,
      execution_projection_selected_preview_available: true,
      execution_projection_selected_preview_source: 'canonical_trade_intent_preview',
      trade_intent_preview_capped_to_canonical_size: false,
      selected_projection_path_status: 'ready',
      selected_projection_path_effective_mode: 'live',
      selected_projection_sizing_signal_present: true,
      selected_projection_shadow_arbitrage_signal_present: false,
      selected_projection_canonical_size_usd: 40,
    }

    const benchmarkReadyRunDetails = {
      run: { id: 'run-benchmark-live-ready-002', status: 'completed' },
      summary: {
        run_id: 'run-benchmark-live-ready-002',
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: market.market_id,
        market_slug: market.slug ?? null,
        status: 'completed',
        recommendation: 'bet',
        side: 'yes',
        confidence: 0.55,
        probability_yes: 0.7,
        market_price_yes: 0.5,
        edge_bps: 1900,
      },
      artifacts: [],
      run_id: 'run-benchmark-live-ready-002',
      workspace_id: 1,
      execution_projection: makeLiveBenchmarkExecutionProjection(),
      execution_readiness: adviseResult.execution_readiness,
      execution_pathways: adviseResult.execution_pathways,
      research_sidecar: adviseResult.research_sidecar,
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'eligible',
      research_benchmark_promotion_ready: true,
      research_benchmark_preview_available: true,
      research_benchmark_promotion_evidence: 'local_benchmark',
      research_benchmark_verdict: 'local_benchmark_ready',
      research_benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      research_promotion_gate_kind: 'local_benchmark',
      research_benchmark_promotion_blocker_summary: 'promotion gate satisfied',
      research_benchmark_gate_blockers: [],
      research_benchmark_gate_reasons: ['local benchmark promotion gate is satisfied'],
      research_benchmark_gate_summary: 'benchmark gate: promotion=eligible ready=yes preview=yes evidence=local_benchmark out_of_sample=local_benchmark',
      benchmark_gate_summary: 'benchmark gate: promotion=eligible ready=yes preview=yes evidence=local_benchmark out_of_sample=local_benchmark',
      benchmark_uplift_bps: expect.any(Number),
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'eligible',
      benchmark_promotion_ready: true,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'local_benchmark',
      benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_promotion_summary: 'promotion gate satisfied',
      benchmark_gate_blockers: [],
      benchmark_gate_reasons: ['local benchmark promotion gate is satisfied'],
      paper_surface: null,
      replay_surface: null,
      shadow_arbitrage: adviseResult.shadow_arbitrage ?? null,
      trade_intent_guard: readyTradeIntentGuard,
      multi_venue_execution: adviseResult.multi_venue_execution ?? null,
    } as never
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(benchmarkReadyRunDetails)

    const paperPlan = preparePredictionMarketRunPaper({
      workspaceId: 1,
      runId: 'run-benchmark-live-ready-002',
    })
    const shadowPlan = preparePredictionMarketRunShadow({
      workspaceId: 1,
      runId: 'run-benchmark-live-ready-002',
    })
    const livePlan = preparePredictionMarketRunLive({
      workspaceId: 1,
      runId: 'run-benchmark-live-ready-002',
    })

    expect(paperPlan).toMatchObject({
      paper_status: 'ready',
      benchmark_promotion_blockers: [],
      benchmark_promotion_ready: true,
      research_benchmark_verdict: 'local_benchmark_ready',
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_preview_available: true,
      research_benchmark_promotion_evidence: 'local_benchmark',
      research_benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      research_promotion_gate_kind: 'local_benchmark',
      research_benchmark_promotion_blocker_summary: 'promotion gate satisfied',
    })
    expect(shadowPlan).toMatchObject({
      shadow_status: 'ready',
      benchmark_promotion_blockers: [],
      benchmark_promotion_ready: true,
      research_benchmark_verdict: 'local_benchmark_ready',
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_preview_available: true,
      research_benchmark_promotion_evidence: 'local_benchmark',
      research_benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      research_promotion_gate_kind: 'local_benchmark',
      research_benchmark_promotion_blocker_summary: 'promotion gate satisfied',
    })
    expect(livePlan).toMatchObject({
      live_route_allowed: true,
      live_status: 'ready',
      benchmark_surface_blocking_reasons: [],
      benchmark_promotion_blockers: [],
      benchmark_promotion_ready: true,
      benchmark_gate_blocks_live: false,
      benchmark_gate_live_block_reason: null,
      research_benchmark_gate_blocks_live: false,
      research_benchmark_live_block_reason: null,
      research_benchmark_verdict: 'local_benchmark_ready',
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_preview_available: true,
      research_benchmark_promotion_evidence: 'local_benchmark',
      research_benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      research_promotion_gate_kind: 'local_benchmark',
      research_benchmark_promotion_blocker_summary: 'promotion gate satisfied',
      live_path: {
        path: 'live',
        status: 'ready',
        effective_mode: 'live',
      },
      live_trade_intent_preview_source: 'canonical_trade_intent_preview',
    })
    expect(livePlan.venue_pathway_summary).toContain('Requested live; selected live')
    expect(livePlan.trade_intent_guard?.metadata).toMatchObject({
      benchmark_promotion_ready: true,
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_promotion_blocker_summary: 'promotion gate satisfied',
      benchmark_gate_blocks_live: false,
      benchmark_gate_live_block_reason: null,
    })
    expect(livePlan.live_blocking_reasons).toEqual([])
    expect(livePlan.live_trade_intent_preview).toMatchObject({ size_usd: 40 })
    expect(livePlan.summary).toContain('Live surface is ready')
  })

  it('exposes benchmark abstention blockers without blocking paper and shadow surfaces', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: makeBenchmarkResearchSignals(),
    })

    const blockedResearchSidecar = structuredClone(adviseResult.research_sidecar)
    if (blockedResearchSidecar?.synthesis?.abstention_policy) {
      blockedResearchSidecar.synthesis.abstention_policy.blocks_forecast = true
    }
    if (blockedResearchSidecar?.synthesis?.comparative_report?.abstention) {
      blockedResearchSidecar.synthesis.comparative_report.abstention.blocks_forecast = true
    }
    const blockedForecast = structuredClone(adviseResult.forecast)
    blockedForecast.abstention_reason = blockedForecast.abstention_reason ?? 'policy_threshold'
    blockedForecast.requires_manual_review = true
    const blockedRecommendation = structuredClone(adviseResult.recommendation)
    blockedRecommendation.action = 'wait'

    const benchmarkedExecutionProjection = makeBenchmarkExecutionProjection()
    const benchmarkedRunDetails = {
      run: { id: 'run-benchmark-surface-blocked-001', status: 'completed' },
      summary: {
        run_id: 'run-benchmark-surface-blocked-001',
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: market.market_id,
        market_slug: market.slug ?? null,
        status: 'completed',
        recommendation: 'bet',
        side: 'yes',
        confidence: 0.55,
        probability_yes: 0.7,
        market_price_yes: 0.5,
        edge_bps: 1900,
      },
      artifacts: [],
      run_id: 'run-benchmark-surface-blocked-001',
      workspace_id: 1,
      execution_projection: benchmarkedExecutionProjection,
      execution_readiness: adviseResult.execution_readiness,
      execution_pathways: adviseResult.execution_pathways,
      research_sidecar: blockedResearchSidecar,
      forecast: blockedForecast,
      recommendation: blockedRecommendation,
      paper_surface: null,
      replay_surface: null,
      shadow_arbitrage: adviseResult.shadow_arbitrage ?? null,
      trade_intent_guard: adviseResult.trade_intent_guard ?? null,
      multi_venue_execution: adviseResult.multi_venue_execution ?? null,
    } as never
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(benchmarkedRunDetails)

    const paperPlan = preparePredictionMarketRunPaper({
      workspaceId: 1,
      runId: 'run-benchmark-surface-blocked-001',
    })
    const shadowPlan = preparePredictionMarketRunShadow({
      workspaceId: 1,
      runId: 'run-benchmark-surface-blocked-001',
    })

    expect(paperPlan).toMatchObject({
      paper_status: 'ready',
      benchmark_surface_blocking_reasons: [],
      benchmark_promotion_blockers: ['research_benchmark:out_of_sample_unproven'],
      benchmark_promotion_ready: false,
      research_benchmark_gate_status: 'blocked_by_abstention',
      research_benchmark_promotion_status: 'blocked',
      research_benchmark_promotion_ready: false,
    })
    expect(paperPlan.research_runtime_mode).toBe('research_driven')
    expect(paperPlan.research_abstention_policy_blocks_forecast).toBe(true)
    expect(paperPlan.research_recommendation_origin).toBe('abstention')
    expect(paperPlan.research_abstention_flipped_recommendation).toBe(true)
    expect(paperPlan.research_recommendation_origin_summary).toContain('Abstention policy flipped')
    expect(paperPlan.research_benchmark_gate_blockers).toEqual(
      expect.arrayContaining(['abstention_blocks_forecast']),
    )
    expect(paperPlan.paper_blocking_reasons).toEqual([])
    expect(paperPlan.summary).toContain('Paper surface is ready')

    expect(shadowPlan).toMatchObject({
      shadow_status: 'ready',
      benchmark_surface_blocking_reasons: [],
      benchmark_promotion_blockers: ['research_benchmark:out_of_sample_unproven'],
      benchmark_promotion_ready: false,
      research_benchmark_gate_status: 'blocked_by_abstention',
      research_benchmark_promotion_status: 'blocked',
      research_benchmark_promotion_ready: false,
    })
    expect(shadowPlan.research_runtime_mode).toBe('research_driven')
    expect(shadowPlan.research_abstention_policy_blocks_forecast).toBe(true)
    expect(shadowPlan.research_recommendation_origin).toBe('abstention')
    expect(shadowPlan.research_abstention_flipped_recommendation).toBe(true)
    expect(shadowPlan.research_benchmark_gate_blockers).toEqual(
      expect.arrayContaining(['abstention_blocks_forecast']),
    )
    expect(shadowPlan.shadow_blocking_reasons).toEqual([])
    expect(shadowPlan.summary).toContain('Shadow surface is ready')
  })

  it('attaches execution_pathways additively on advise and replay payloads', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
    })

    const replayResult = await replayPredictionMarketRun({
      workspaceId: 1,
      actor: 'tester',
      runId: 'run-execution-readiness-001',
    })

    expect(adviseResult.execution_pathways).toMatchObject({
      recommendation_action: 'wait',
      recommendation_side: null,
      highest_actionable_mode: null,
      pathways: expect.arrayContaining([
        expect.objectContaining({
          mode: 'paper',
          actionable: false,
          status: 'inactive',
          trade_intent_preview: null,
        }),
        expect.objectContaining({
          mode: 'shadow',
          actionable: false,
          status: 'inactive',
        }),
        expect.objectContaining({
          mode: 'live',
          actionable: false,
          status: 'inactive',
        }),
      ]),
    })
    expect(replayResult.execution_pathways).toMatchObject({
      recommendation_action: 'bet',
      recommendation_side: 'yes',
      highest_actionable_mode: 'paper',
    })
    expect(adviseResult.execution_pathways.summary).toContain('inactive')
    expect(replayResult.execution_pathways.summary).toContain('paper')

    expect(adviseResult.execution_projection).toMatchObject({
      requested_path: 'paper',
      selected_path: 'paper',
      selected_edge_bucket: 'no_trade',
      selected_pre_trade_gate: expect.objectContaining({
        gate_name: 'hard_no_trade',
        verdict: 'not_applicable',
        edge_bucket: 'no_trade',
      }),
      verdict: 'allowed',
      ttl_ms: 30_000,
      highest_safe_requested_mode: 'paper',
      recommended_effective_mode: 'paper',
      basis: expect.objectContaining({
        uses_execution_readiness: true,
        uses_compliance: true,
        uses_capital: false,
        uses_reconciliation: false,
        uses_microstructure: false,
        capital_status: 'unavailable',
        reconciliation_status: 'unavailable',
        source_refs: {
          pipeline_guard: 'run-execution-readiness-001:pipeline_guard',
          compliance_report: 'run-execution-readiness-001:compliance_report',
          execution_readiness: 'run-execution-readiness-001:execution_readiness',
          venue_health: 'run-execution-readiness-001:pipeline_guard#venue_health',
          capital_ledger: null,
          reconciliation: null,
          microstructure_lab: null,
        },
        canonical_gate: {
          gate_name: 'execution_projection',
          single_runtime_gate: true,
          enforced_for_modes: ['paper', 'shadow', 'live'],
        },
      }),
      modes: expect.objectContaining({
        paper: expect.objectContaining({
          requested_mode: 'paper',
          effective_mode: 'paper',
        }),
        shadow: expect.objectContaining({
          requested_mode: 'shadow',
        }),
        live: expect.objectContaining({
          requested_mode: 'live',
        }),
      }),
    })
    expect(adviseResult.execution_projection?.preflight_summary).toMatchObject({
      selected_edge_bucket: 'no_trade',
      selected_pre_trade_gate: expect.objectContaining({
        gate_name: 'hard_no_trade',
        verdict: 'not_applicable',
        edge_bucket: 'no_trade',
      }),
    })
    expect(replayResult.execution_projection).toMatchObject({
      requested_path: 'live',
      selected_path: 'paper',
      selected_edge_bucket: 'execution_alpha',
      selected_pre_trade_gate: expect.objectContaining({
        gate_name: 'hard_no_trade',
        verdict: 'pass',
        edge_bucket: 'execution_alpha',
      }),
      verdict: 'downgraded',
      highest_safe_requested_mode: 'paper',
      recommended_effective_mode: 'paper',
    })
    expect(replayResult.execution_projection?.preflight_summary).toMatchObject({
      gate_name: 'execution_projection',
      preflight_only: true,
      requested_path: 'live',
      selected_path: 'paper',
      verdict: 'downgraded',
      highest_safe_requested_mode: 'paper',
      recommended_effective_mode: 'paper',
      manual_review_required: true,
      counts: {
        total: 3,
        eligible: 1,
        ready: 0,
        degraded: 1,
        blocked: 2,
      },
      basis: {
        uses_execution_readiness: true,
        uses_compliance: true,
        uses_capital: false,
        uses_reconciliation: false,
        uses_microstructure: true,
        capital_status: 'unavailable',
        reconciliation_status: 'unavailable',
      },
      microstructure: expect.objectContaining({
        recommended_mode: expect.any(String),
        worst_case_severity: expect.any(String),
        executable_deterioration_bps: expect.any(Number),
        execution_quality_score: expect.any(Number),
      }),
      source_of_truth: 'official_docs',
      execution_eligible: true,
      stale_edge_status: {
        state: 'fresh',
        expired: false,
        source: 'cross_venue',
      },
      penalties: {
        capital_fragmentation_penalty_bps: 8,
        transfer_latency_penalty_bps: 2,
        low_confidence_penalty_bps: expect.any(Number),
        stale_edge_penalty_bps: 0,
        microstructure_deterioration_bps: 30,
        microstructure_execution_quality_score: expect.any(Number),
      },
    })
    expect(replayResult.execution_projection?.preflight_summary.source_refs).toEqual([
      'run-execution-readiness-001:pipeline_guard',
      'run-execution-readiness-001:compliance_report',
      'run-execution-readiness-001:execution_readiness',
      'run-execution-readiness-001:pipeline_guard#venue_health',
      'run-execution-readiness-001:microstructure_lab',
    ])
    expect(replayResult.execution_projection?.preflight_summary.blockers).toEqual([])
    expect(replayResult.execution_projection?.preflight_summary.downgrade_reasons).toEqual([
      'runtime:live mode blocked',
      'runtime:venue health is degraded',
      'runtime:live automation remains disabled',
      'manual_review_required_for_execution',
      'capital_ledger_unavailable',
      'reconciliation_unavailable',
      'effective_mode:live->paper',
    ])
    expect(replayResult.execution_projection?.preflight_summary.selected_edge_bucket).toBe('execution_alpha')
    expect(replayResult.execution_projection?.preflight_summary.selected_pre_trade_gate).toMatchObject({
      gate_name: 'hard_no_trade',
      verdict: 'pass',
      edge_bucket: 'execution_alpha',
    })
    expect(replayResult.execution_projection?.preflight_summary.summary).toContain(
      'gate=execution_projection preflight=yes verdict=downgraded requested=live selected=paper',
    )
    expect(replayResult.execution_projection?.preflight_summary.summary).toContain(
      'edge_bucket=execution_alpha',
    )
    expect(replayResult.execution_projection?.preflight_summary.summary).toContain(
      'pre_trade=pass:',
    )
    expect(replayResult.execution_projection?.preflight_summary.summary).not.toContain('\n')
    expect(replayResult.execution_projection?.basis.source_refs).toEqual({
      pipeline_guard: 'run-execution-readiness-001:pipeline_guard',
      compliance_report: 'run-execution-readiness-001:compliance_report',
      execution_readiness: 'run-execution-readiness-001:execution_readiness',
      venue_health: 'run-execution-readiness-001:pipeline_guard#venue_health',
      capital_ledger: null,
      reconciliation: null,
      microstructure_lab: 'run-execution-readiness-001:microstructure_lab',
    })
    expect(replayResult.execution_projection?.projected_paths.paper.simulation).toMatchObject({
      quote_age_ms: expect.any(Number),
      expected_fill_confidence: expect.any(Number),
      expected_slippage_bps: expect.any(Number),
    })
    expect(replayResult.execution_projection?.projected_paths.shadow.blockers).toEqual(expect.arrayContaining([
      'manual_review_required_for_execution',
      'capital_ledger_unavailable',
    ]))
    expect(replayResult.execution_projection?.projected_paths.live.blockers).toEqual(expect.arrayContaining([
      'manual_review_required_for_execution',
      'capital_ledger_unavailable',
      'reconciliation_unavailable',
    ]))
    expect(adviseResult.prediction_run).toMatchObject({
      execution_pathways_highest_actionable_mode: 'paper',
      execution_projection_selected_edge_bucket: 'no_trade',
      execution_projection_selected_pre_trade_gate_verdict: 'not_applicable',
      shadow_arbitrage_present: false,
      shadow_arbitrage_recommended_size_usd: null,
    })
    expect(replayResult.prediction_run).toMatchObject({
      execution_pathways_highest_actionable_mode: 'paper',
      execution_projection_selected_edge_bucket: 'execution_alpha',
      execution_projection_selected_pre_trade_gate_verdict: 'pass',
      shadow_arbitrage_present: false,
      shadow_arbitrage_recommended_size_usd: null,
    })
    expect(adviseResult.prediction_run?.execution_projection_selected_pre_trade_gate_summary).toContain(
      'No-trade gate stays inactive',
    )
    expect(replayResult.prediction_run?.execution_projection_selected_pre_trade_gate_summary).toContain(
      'Hard no-trade gate pass',
    )

    expect(adviseResult.trade_intent_guard).toMatchObject({
      gate_name: 'trade_intent_guard',
      verdict: 'blocked',
      manual_review_required: true,
      selected_path: 'paper',
      highest_safe_mode: 'paper',
      source_refs: expect.objectContaining({
        pipeline_guard: 'run-execution-readiness-001:pipeline_guard',
        execution_projection: 'run-execution-readiness-001:execution_projection',
      }),
      metadata: expect.objectContaining({
        selected_projection_path_status: 'degraded',
        selected_projection_shadow_arbitrage_signal_present: false,
      }),
    })
    expect(adviseResult.trade_intent_guard?.metadata).toHaveProperty('trade_intent_preview_source')
    expect(adviseResult.trade_intent_guard?.metadata).toHaveProperty('selected_projection_sizing_signal_present')
    expect(adviseResult.trade_intent_guard?.metadata).toHaveProperty('selected_projection_canonical_size_usd')
    expect(replayResult.trade_intent_guard).toMatchObject({
      gate_name: 'trade_intent_guard',
      verdict: 'blocked',
      manual_review_required: true,
      metadata: expect.objectContaining({
        selected_projection_path_status: 'degraded',
        selected_projection_shadow_arbitrage_signal_present: false,
      }),
    })
    expect(replayResult.trade_intent_guard?.metadata).toHaveProperty('trade_intent_preview_source')
    expect(replayResult.trade_intent_guard?.metadata).toHaveProperty('selected_projection_sizing_signal_present')
    expect(replayResult.trade_intent_guard?.metadata).toHaveProperty('selected_projection_canonical_size_usd')
    expect(adviseResult.multi_venue_execution).toMatchObject({
      gate_name: 'multi_venue_execution',
      market_count: expect.any(Number),
      comparable_group_count: expect.any(Number),
      execution_candidate_count: expect.any(Number),
      execution_plan_count: expect.any(Number),
      tradeable_plan_count: expect.any(Number),
      summary: expect.any(String),
      metadata: expect.objectContaining({
        execution_projection_selected_path: 'paper',
        execution_projection_selected_path_status: 'degraded',
        execution_projection_selected_path_shadow_signal_present: false,
      }),
    })
    expect(adviseResult.multi_venue_execution?.metadata).toHaveProperty('execution_projection_selected_path_canonical_size_usd')
    expect(adviseResult.multi_venue_execution?.metadata).toHaveProperty('execution_projection_selected_preview_available')
    expect(adviseResult.multi_venue_execution?.metadata).toHaveProperty('execution_projection_selected_preview_source')
    expect(adviseResult.multi_venue_execution?.metadata).toHaveProperty('execution_projection_selected_preview_size_usd')
    expect(replayResult.multi_venue_execution).toMatchObject({
      gate_name: 'multi_venue_execution',
      market_count: expect.any(Number),
      summary: expect.any(String),
      metadata: expect.objectContaining({
        execution_projection_selected_path: 'paper',
        execution_projection_selected_path_status: 'degraded',
        execution_projection_selected_path_shadow_signal_present: false,
      }),
    })
    expect(replayResult.multi_venue_execution?.metadata).toHaveProperty('execution_projection_selected_path_canonical_size_usd')
    expect(replayResult.multi_venue_execution?.metadata).toHaveProperty('execution_projection_selected_preview_available')
    expect(replayResult.multi_venue_execution?.metadata).toHaveProperty('execution_projection_selected_preview_source')
    expect(replayResult.multi_venue_execution?.metadata).toHaveProperty('execution_projection_selected_preview_size_usd')
  })

  it('preserves stored benchmark promotion hints when advise reuses an existing run', async () => {
    const storedBenchmarkedRunDetails = {
      ...structuredClone(storedRunDetails),
      research_benchmark_verdict: 'local_benchmark_ready',
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'eligible',
      research_benchmark_promotion_ready: true,
      research_benchmark_preview_available: true,
      research_benchmark_promotion_evidence: 'local_benchmark',
      research_benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      research_promotion_gate_kind: 'local_benchmark',
      research_benchmark_promotion_blocker_summary: 'promotion gate satisfied',
      research_benchmark_promotion_summary: 'promotion gate satisfied',
      research_benchmark_gate_blockers: [],
      research_benchmark_gate_reasons: ['local benchmark promotion gate is satisfied'],
      research_benchmark_gate_summary:
        'benchmark gate: promotion=eligible ready=yes preview=yes evidence=local_benchmark out_of_sample=local_benchmark',
      benchmark_gate_summary:
        'benchmark gate: promotion=eligible ready=yes preview=yes evidence=local_benchmark out_of_sample=local_benchmark',
      benchmark_uplift_bps: 250,
      benchmark_verdict: 'local_benchmark_ready',
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'eligible',
      benchmark_promotion_ready: true,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'local_benchmark',
      benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_promotion_blocker_summary: 'promotion gate satisfied',
      benchmark_promotion_summary: 'promotion gate satisfied',
      benchmark_gate_blockers: [],
      benchmark_gate_reasons: ['local benchmark promotion gate is satisfied'],
    } as typeof storedRunDetails & Record<string, unknown>

    mocks.findRecentPredictionMarketRunByConfig.mockReturnValue(storedBenchmarkedRunDetails.summary)
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(storedBenchmarkedRunDetails)

    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
    })

    expect(adviseResult.reused_existing_run).toBe(true)
    expect(adviseResult.prediction_run).toMatchObject({
      research_benchmark_verdict: 'local_benchmark_ready',
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'eligible',
      research_benchmark_promotion_ready: true,
      research_benchmark_preview_available: true,
      research_benchmark_promotion_evidence: 'local_benchmark',
      research_benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      research_promotion_gate_kind: 'local_benchmark',
      research_benchmark_promotion_blocker_summary: 'promotion gate satisfied',
      research_benchmark_promotion_summary: 'promotion gate satisfied',
      benchmark_verdict: 'local_benchmark_ready',
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'eligible',
      benchmark_promotion_ready: true,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'local_benchmark',
      benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_promotion_blocker_summary: 'promotion gate satisfied',
      benchmark_promotion_summary: 'promotion gate satisfied',
    })
  })

  it('keeps reused_existing_run benchmark hints anchored to stored canonical summary fields when details only expose research aliases', async () => {
    const canonicalBenchmarkSummary = {
      ...structuredClone(storedRunDetails.summary),
      benchmark_gate_summary: 'benchmark summary canonical should win',
      benchmark_uplift_bps: 777,
      benchmark_verdict: 'local_benchmark_blocked',
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'unproven',
      benchmark_promotion_ready: false,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'unproven',
      benchmark_evidence_level: 'benchmark_preview',
      benchmark_promotion_gate_kind: 'preview_only',
      benchmark_promotion_blocker_summary: 'benchmark summary canonical blocker',
      benchmark_promotion_summary: 'benchmark summary canonical blocker',
      benchmark_gate_blocks_live: true,
      benchmark_gate_live_block_reason: 'benchmark summary canonical blocker',
      benchmark_gate_blockers: ['out_of_sample_unproven'],
      benchmark_gate_reasons: ['out_of_sample_unproven'],
    }
    const storedResearchAliasOnlyRunDetails = {
      ...structuredClone(storedRunDetails),
      summary: canonicalBenchmarkSummary,
      research_benchmark_gate_summary: 'research alias should not win',
      research_benchmark_uplift_bps: 111,
      research_benchmark_verdict: 'local_benchmark_ready',
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'eligible',
      research_benchmark_promotion_ready: true,
      research_benchmark_preview_available: true,
      research_benchmark_promotion_evidence: 'local_benchmark',
      research_benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      research_promotion_gate_kind: 'local_benchmark',
      research_benchmark_promotion_blocker_summary: 'research alias should not win',
      research_benchmark_promotion_summary: 'research alias should not win',
      research_benchmark_gate_blockers: [],
      research_benchmark_gate_reasons: ['research alias should not win'],
      benchmark_gate_summary: undefined,
      benchmark_uplift_bps: undefined,
      benchmark_verdict: undefined,
      benchmark_gate_status: undefined,
      benchmark_promotion_status: undefined,
      benchmark_promotion_ready: undefined,
      benchmark_preview_available: undefined,
      benchmark_promotion_evidence: undefined,
      benchmark_evidence_level: undefined,
      benchmark_promotion_gate_kind: undefined,
      benchmark_promotion_blocker_summary: undefined,
      benchmark_promotion_summary: undefined,
      benchmark_gate_blocks_live: undefined,
      benchmark_gate_live_block_reason: undefined,
      benchmark_gate_blockers: undefined,
      benchmark_gate_reasons: undefined,
    } as typeof storedRunDetails & Record<string, unknown>

    mocks.findRecentPredictionMarketRunByConfig.mockReturnValue(canonicalBenchmarkSummary)
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(storedResearchAliasOnlyRunDetails)

    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
    })

    expect(adviseResult.reused_existing_run).toBe(true)
    expect(adviseResult.prediction_run).toMatchObject({
      benchmark_gate_summary: 'benchmark summary canonical should win',
      benchmark_uplift_bps: 777,
      benchmark_verdict: 'local_benchmark_blocked',
      benchmark_promotion_status: 'unproven',
      benchmark_promotion_ready: false,
      benchmark_promotion_blocker_summary: 'benchmark summary canonical blocker',
      benchmark_promotion_summary: 'benchmark summary canonical blocker',
      benchmark_gate_blocks_live: true,
      benchmark_gate_live_block_reason: 'benchmark summary canonical blocker',
      benchmark_gate_blockers: ['out_of_sample_unproven'],
      benchmark_gate_reasons: ['out_of_sample_unproven'],
      research_benchmark_promotion_ready: false,
      research_benchmark_promotion_blocker_summary: 'benchmark summary canonical blocker',
      research_benchmark_promotion_summary: 'benchmark summary canonical blocker',
    })
  })

  it('keeps stored benchmark fields authoritative during run-detail reconstruction', () => {
    const storedBenchmarkedRunDetails = {
      ...structuredClone(storedRunDetails),
      research_benchmark_verdict: 'preview_only',
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'unproven',
      research_benchmark_promotion_ready: false,
      research_benchmark_preview_available: true,
      research_benchmark_promotion_evidence: 'unproven',
      research_benchmark_evidence_level: 'benchmark_preview',
      research_promotion_gate_kind: 'preview_only',
      research_benchmark_promotion_blocker_summary: 'out_of_sample_unproven',
      research_benchmark_promotion_summary: 'out_of_sample_unproven',
      research_benchmark_gate_blockers: ['out_of_sample_unproven'],
      research_benchmark_gate_reasons: ['out_of_sample_unproven'],
      research_benchmark_gate_summary:
        'benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 uplift_vs_market_only=1100bps uplift_vs_aggregate=850bps status=preview_only promotion=unproven ready=no preview=yes evidence=unproven blockers=out_of_sample_unproven out_of_sample=unproven',
      benchmark_gate_summary:
        'benchmark gate: promotion=eligible ready=yes preview=yes evidence=local_benchmark out_of_sample=local_benchmark',
      benchmark_uplift_bps: 250,
      benchmark_verdict: 'local_benchmark_ready',
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'eligible',
      benchmark_promotion_ready: true,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'local_benchmark',
      benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_promotion_blocker_summary: 'promotion gate satisfied',
      benchmark_promotion_summary: 'promotion gate satisfied',
      benchmark_gate_blocks_live: false,
      benchmark_gate_live_block_reason: null,
      benchmark_gate_blockers: [],
      benchmark_gate_reasons: ['local benchmark promotion gate is satisfied'],
    } as typeof storedRunDetails & Record<string, unknown>

    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(storedBenchmarkedRunDetails)

    const details = getPredictionMarketRunDetails('run-execution-readiness-001', 1)

    expect(details?.benchmark_verdict).toBe('local_benchmark_ready')
    expect(details?.benchmark_promotion_ready).toBe(true)
    expect(details?.benchmark_gate_blocks_live).toBe(false)
    expect(details?.benchmark_gate_live_block_reason).toBeNull()
    expect(details?.benchmark_gate_summary).toContain('promotion=eligible ready=yes')
  })

  it('rehydrates benchmark-only aliases into the run detail benchmark hints', async () => {
    const benchmarkOnlyRunDetails = {
      ...structuredClone(storedRunDetails),
      research_benchmark_gate_summary: undefined,
      research_benchmark_uplift_bps: undefined,
      research_benchmark_verdict: undefined,
      research_benchmark_gate_status: undefined,
      research_benchmark_promotion_status: undefined,
      research_benchmark_promotion_ready: undefined,
      research_benchmark_preview_available: undefined,
      research_benchmark_promotion_evidence: undefined,
      research_benchmark_evidence_level: undefined,
      research_promotion_gate_kind: undefined,
      research_benchmark_promotion_blocker_summary: undefined,
      research_benchmark_promotion_summary: undefined,
      research_benchmark_gate_blockers: undefined,
      research_benchmark_gate_reasons: undefined,
      benchmark_gate_summary: 'benchmark gate: benchmark-only alias propagation',
      benchmark_uplift_bps: 333,
      benchmark_verdict: 'local_benchmark_ready',
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'eligible',
      benchmark_promotion_ready: true,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'local_benchmark',
      benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_promotion_blocker_summary: 'benchmark-only promotion satisfied',
      benchmark_promotion_summary: 'benchmark-only promotion satisfied',
      benchmark_gate_blockers: [],
      benchmark_gate_reasons: ['benchmark-only alias propagation'],
    } as typeof storedRunDetails & Record<string, unknown>

    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(benchmarkOnlyRunDetails)

    const runDetails = getPredictionMarketRunDetails('run-execution-readiness-001', 1)

    expect(runDetails).toMatchObject({
      benchmark_gate_summary: 'benchmark gate: benchmark-only alias propagation',
      benchmark_uplift_bps: 333,
      benchmark_verdict: 'local_benchmark_ready',
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'eligible',
      benchmark_promotion_ready: true,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'local_benchmark',
      benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_promotion_blocker_summary: 'benchmark-only promotion satisfied',
      benchmark_promotion_summary: 'benchmark-only promotion satisfied',
      benchmark_gate_blockers: [],
      benchmark_gate_reasons: ['benchmark-only alias propagation'],
      research_benchmark_promotion_blocker_summary: 'benchmark-only promotion satisfied',
    })
    expect(runDetails?.benchmark_gate_blocks_live).toBe(false)
    expect(runDetails?.benchmark_gate_live_block_reason).toBeNull()
    expect(runDetails?.packet_bundle?.advisor_architecture.stages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          stage_kind: 'execution_preflight',
          metadata: expect.objectContaining({
            benchmark_promotion_ready: true,
            benchmark_promotion_gate_kind: 'local_benchmark',
            benchmark_gate_blocks_live: false,
            benchmark_gate_live_block_reason: null,
          }),
        }),
      ]),
    )
  })

  it('preserves stored benchmark aliases on replay prediction_run hydration', async () => {
    const benchmarkOnlyRunDetails = {
      ...structuredClone(storedRunDetails),
      research_benchmark_gate_summary: undefined,
      research_benchmark_uplift_bps: undefined,
      research_benchmark_verdict: undefined,
      research_benchmark_gate_status: undefined,
      research_benchmark_promotion_status: undefined,
      research_benchmark_promotion_ready: undefined,
      research_benchmark_preview_available: undefined,
      research_benchmark_promotion_evidence: undefined,
      research_benchmark_evidence_level: undefined,
      research_promotion_gate_kind: undefined,
      research_benchmark_promotion_blocker_summary: undefined,
      research_benchmark_promotion_summary: undefined,
      research_benchmark_gate_blockers: undefined,
      research_benchmark_gate_reasons: undefined,
      benchmark_gate_summary: 'benchmark gate: benchmark-only alias propagation',
      benchmark_uplift_bps: 333,
      benchmark_verdict: 'local_benchmark_ready',
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'eligible',
      benchmark_promotion_ready: true,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'local_benchmark',
      benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_promotion_blocker_summary: 'benchmark-only promotion satisfied',
      benchmark_promotion_summary: 'benchmark-only promotion satisfied',
      benchmark_gate_blocks_live: false,
      benchmark_gate_live_block_reason: null,
      benchmark_gate_blockers: [],
      benchmark_gate_reasons: ['benchmark-only alias propagation'],
    } as typeof storedRunDetails & Record<string, unknown>

    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(benchmarkOnlyRunDetails)

    const replayResult = await replayPredictionMarketRun({
      workspaceId: 1,
      actor: 'tester',
      runId: 'run-execution-readiness-001',
    })

    expect(replayResult.prediction_run).toMatchObject({
      benchmark_gate_summary: 'benchmark gate: benchmark-only alias propagation',
      benchmark_uplift_bps: 333,
      benchmark_verdict: 'local_benchmark_ready',
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'eligible',
      benchmark_promotion_ready: true,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'local_benchmark',
      benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_promotion_blocker_summary: 'benchmark-only promotion satisfied',
      benchmark_promotion_summary: 'benchmark-only promotion satisfied',
      benchmark_gate_blocks_live: false,
      benchmark_gate_blockers: [],
      benchmark_gate_reasons: ['benchmark-only alias propagation'],
      research_benchmark_promotion_blocker_summary: 'benchmark-only promotion satisfied',
    })
    expect(replayResult.prediction_run?.benchmark_gate_live_block_reason ?? null).toBeNull()
  })

  it('uses benchmark-only aliases as the canonical promotion state for dispatch, paper, and shadow surfaces', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: makeBenchmarkResearchSignals(),
    })

    const benchmarkOnlyRunDetails = {
      run: { id: 'run-benchmark-surface-canonical-001', status: 'completed' },
      summary: {
        run_id: 'run-benchmark-surface-canonical-001',
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: market.market_id,
        market_slug: market.slug ?? null,
        status: 'completed',
        recommendation: 'bet',
        side: 'yes',
        confidence: 0.55,
        probability_yes: 0.7,
        market_price_yes: 0.5,
        edge_bps: 1900,
      },
      artifacts: [],
      run_id: 'run-benchmark-surface-canonical-001',
      workspace_id: 1,
      execution_projection: adviseResult.execution_projection,
      execution_readiness: adviseResult.execution_readiness,
      execution_pathways: adviseResult.execution_pathways,
      research_sidecar: adviseResult.research_sidecar,
      trade_intent_guard: adviseResult.trade_intent_guard ?? null,
      multi_venue_execution: adviseResult.multi_venue_execution ?? null,
      paper_surface: null,
      replay_surface: null,
      shadow_arbitrage: adviseResult.shadow_arbitrage ?? null,
      research_benchmark_gate_summary: undefined,
      research_benchmark_uplift_bps: undefined,
      research_benchmark_verdict: undefined,
      research_benchmark_gate_status: undefined,
      research_benchmark_promotion_status: undefined,
      research_benchmark_promotion_ready: undefined,
      research_benchmark_preview_available: undefined,
      research_benchmark_promotion_evidence: undefined,
      research_benchmark_evidence_level: undefined,
      research_promotion_gate_kind: undefined,
      research_benchmark_promotion_blocker_summary: undefined,
      research_benchmark_promotion_summary: undefined,
      research_benchmark_gate_blockers: undefined,
      research_benchmark_gate_reasons: undefined,
      benchmark_gate_summary: 'benchmark gate: benchmark-only surface propagation',
      benchmark_uplift_bps: 444,
      benchmark_verdict: 'local_benchmark_ready',
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'eligible',
      benchmark_promotion_ready: true,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'local_benchmark',
      benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      benchmark_promotion_gate_kind: 'local_benchmark',
      benchmark_promotion_blocker_summary: 'benchmark-only promotion satisfied',
      benchmark_promotion_summary: 'benchmark-only promotion satisfied',
      benchmark_gate_blockers: [],
      benchmark_gate_reasons: ['benchmark-only surface propagation'],
      benchmark_gate_blocks_live: false,
      benchmark_gate_live_block_reason: null,
    } as typeof storedRunDetails & Record<string, unknown>

    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(benchmarkOnlyRunDetails)

    const dispatchPlan = preparePredictionMarketRunDispatch({
      workspaceId: 1,
      runId: 'run-benchmark-surface-canonical-001',
    })
    const paperPlan = preparePredictionMarketRunPaper({
      workspaceId: 1,
      runId: 'run-benchmark-surface-canonical-001',
    })
    const shadowPlan = preparePredictionMarketRunShadow({
      workspaceId: 1,
      runId: 'run-benchmark-surface-canonical-001',
    })

    expect(dispatchPlan).toMatchObject({
      benchmark_promotion_ready: true,
      benchmark_promotion_blockers: [],
    })
    expect(paperPlan).toMatchObject({
      benchmark_promotion_ready: true,
      benchmark_promotion_blockers: [],
    })
    expect(shadowPlan).toMatchObject({
      benchmark_promotion_ready: true,
      benchmark_promotion_blockers: [],
    })
  })

  it('uses canonical benchmark abstention blockers on operator surfaces when only benchmark_* fields are stored', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: makeBenchmarkResearchSignals(),
    })

    const benchmarkOnlyBlockedRunDetails = {
      run: { id: 'run-benchmark-surface-canonical-002', status: 'completed' },
      summary: {
        run_id: 'run-benchmark-surface-canonical-002',
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: market.market_id,
        market_slug: market.slug ?? null,
        status: 'completed',
        recommendation: 'wait',
        side: null,
        confidence: 0.55,
        probability_yes: 0.7,
        market_price_yes: 0.5,
        edge_bps: 1900,
      },
      artifacts: [],
      run_id: 'run-benchmark-surface-canonical-002',
      workspace_id: 1,
      execution_projection: makeLiveBenchmarkExecutionProjection(),
      execution_readiness: adviseResult.execution_readiness,
      execution_pathways: adviseResult.execution_pathways,
      research_sidecar: adviseResult.research_sidecar,
      trade_intent_guard: adviseResult.trade_intent_guard ?? null,
      multi_venue_execution: adviseResult.multi_venue_execution ?? null,
      paper_surface: null,
      replay_surface: null,
      shadow_arbitrage: adviseResult.shadow_arbitrage ?? null,
      research_abstention_policy_blocks_forecast: false,
      research_benchmark_gate_summary: undefined,
      research_benchmark_uplift_bps: undefined,
      research_benchmark_verdict: undefined,
      research_benchmark_gate_status: undefined,
      research_benchmark_promotion_status: undefined,
      research_benchmark_promotion_ready: undefined,
      research_benchmark_preview_available: undefined,
      research_benchmark_promotion_evidence: undefined,
      research_benchmark_evidence_level: undefined,
      research_promotion_gate_kind: undefined,
      research_benchmark_promotion_blocker_summary: undefined,
      research_benchmark_promotion_summary: undefined,
      research_benchmark_gate_blockers: undefined,
      research_benchmark_gate_reasons: undefined,
      research_benchmark_live_block_reason: undefined,
      benchmark_gate_summary: 'benchmark gate: canonical abstention surface propagation',
      benchmark_uplift_bps: 444,
      benchmark_verdict: 'blocked_by_abstention',
      benchmark_gate_status: 'blocked_by_abstention',
      benchmark_promotion_status: 'blocked',
      benchmark_promotion_ready: false,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'unproven',
      benchmark_evidence_level: 'benchmark_preview',
      benchmark_promotion_gate_kind: 'preview_only',
      benchmark_promotion_blocker_summary: 'abstention_blocks_forecast',
      benchmark_promotion_summary: 'abstention_blocks_forecast',
      benchmark_gate_blockers: ['abstention_blocks_forecast'],
      benchmark_gate_reasons: ['abstention_blocks_forecast'],
      benchmark_gate_blocks_live: undefined,
      benchmark_gate_live_block_reason: undefined,
    } as typeof storedRunDetails & Record<string, unknown>

    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(benchmarkOnlyBlockedRunDetails)

    const dispatchPlan = preparePredictionMarketRunDispatch({
      workspaceId: 1,
      runId: 'run-benchmark-surface-canonical-002',
    })
    const paperPlan = preparePredictionMarketRunPaper({
      workspaceId: 1,
      runId: 'run-benchmark-surface-canonical-002',
    })
    const shadowPlan = preparePredictionMarketRunShadow({
      workspaceId: 1,
      runId: 'run-benchmark-surface-canonical-002',
    })
    const livePlan = preparePredictionMarketRunLive({
      workspaceId: 1,
      runId: 'run-benchmark-surface-canonical-002',
    })

    expect(dispatchPlan.benchmark_surface_blocking_reasons).toEqual(['benchmark:abstention_blocks_forecast'])
    expect(paperPlan).toMatchObject({
      benchmark_surface_blocking_reasons: ['benchmark:abstention_blocks_forecast'],
      benchmark_promotion_ready: false,
      benchmark_promotion_blockers: ['benchmark:abstention_blocks_forecast'],
    })
    expect(shadowPlan).toMatchObject({
      benchmark_surface_blocking_reasons: ['benchmark:abstention_blocks_forecast'],
      benchmark_promotion_ready: false,
      benchmark_promotion_blockers: ['benchmark:abstention_blocks_forecast'],
    })
    expect(livePlan).toMatchObject({
      benchmark_surface_blocking_reasons: ['benchmark:abstention_blocks_forecast'],
      benchmark_promotion_ready: false,
      benchmark_promotion_blockers: ['benchmark:abstention_blocks_forecast'],
    })
    expect(livePlan.live_blocking_reasons).toEqual(
      expect.arrayContaining(['benchmark:abstention_blocks_forecast']),
    )
  })

  it('uses canonical benchmark promotion blockers on operator surfaces when only benchmark_* fields are stored', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: makeBenchmarkResearchSignals(),
    })

    const readyTradeIntentGuard = structuredClone(adviseResult.trade_intent_guard) as NonNullable<
      typeof adviseResult.trade_intent_guard
    >
    readyTradeIntentGuard.verdict = 'allowed'
    readyTradeIntentGuard.manual_review_required = false
    readyTradeIntentGuard.selected_path = 'live'
    readyTradeIntentGuard.highest_safe_mode = 'live'
    readyTradeIntentGuard.blocked_reasons = []

    const benchmarkOnlyBlockedRunDetails = {
      run: { id: 'run-benchmark-surface-canonical-003', status: 'completed' },
      summary: {
        run_id: 'run-benchmark-surface-canonical-003',
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: market.market_id,
        market_slug: market.slug ?? null,
        status: 'completed',
        recommendation: 'bet',
        side: 'yes',
        confidence: 0.55,
        probability_yes: 0.7,
        market_price_yes: 0.5,
        edge_bps: 1900,
      },
      artifacts: [],
      run_id: 'run-benchmark-surface-canonical-003',
      workspace_id: 1,
      execution_projection: makeLiveBenchmarkExecutionProjection(),
      execution_readiness: adviseResult.execution_readiness,
      execution_pathways: adviseResult.execution_pathways,
      research_sidecar: adviseResult.research_sidecar,
      trade_intent_guard: readyTradeIntentGuard,
      multi_venue_execution: adviseResult.multi_venue_execution ?? null,
      paper_surface: null,
      replay_surface: null,
      shadow_arbitrage: adviseResult.shadow_arbitrage ?? null,
      research_abstention_policy_blocks_forecast: false,
      research_benchmark_gate_summary: undefined,
      research_benchmark_uplift_bps: undefined,
      research_benchmark_verdict: undefined,
      research_benchmark_gate_status: undefined,
      research_benchmark_promotion_status: undefined,
      research_benchmark_promotion_ready: undefined,
      research_benchmark_preview_available: undefined,
      research_benchmark_promotion_evidence: undefined,
      research_benchmark_evidence_level: undefined,
      research_promotion_gate_kind: undefined,
      research_benchmark_promotion_blocker_summary: undefined,
      research_benchmark_promotion_summary: undefined,
      research_benchmark_gate_blockers: undefined,
      research_benchmark_gate_reasons: undefined,
      research_benchmark_live_block_reason: undefined,
      benchmark_gate_summary: 'benchmark gate: canonical promotion blocker propagation',
      benchmark_uplift_bps: 444,
      benchmark_verdict: 'local_benchmark_blocked',
      benchmark_gate_status: 'preview_only',
      benchmark_promotion_status: 'unproven',
      benchmark_promotion_ready: false,
      benchmark_preview_available: true,
      benchmark_promotion_evidence: 'unproven',
      benchmark_evidence_level: 'benchmark_preview',
      benchmark_promotion_gate_kind: 'preview_only',
      benchmark_promotion_blocker_summary: 'out_of_sample_unproven',
      benchmark_promotion_summary: 'out_of_sample_unproven',
      benchmark_gate_blockers: ['out_of_sample_unproven'],
      benchmark_gate_reasons: ['out_of_sample_unproven'],
      benchmark_gate_blocks_live: true,
      benchmark_gate_live_block_reason: 'out_of_sample_unproven',
    } as typeof storedRunDetails & Record<string, unknown>

    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(benchmarkOnlyBlockedRunDetails)

    const dispatchPlan = preparePredictionMarketRunDispatch({
      workspaceId: 1,
      runId: 'run-benchmark-surface-canonical-003',
    })
    const paperPlan = preparePredictionMarketRunPaper({
      workspaceId: 1,
      runId: 'run-benchmark-surface-canonical-003',
    })
    const shadowPlan = preparePredictionMarketRunShadow({
      workspaceId: 1,
      runId: 'run-benchmark-surface-canonical-003',
    })
    const livePlan = preparePredictionMarketRunLive({
      workspaceId: 1,
      runId: 'run-benchmark-surface-canonical-003',
    })

    expect(dispatchPlan).toMatchObject({
      benchmark_promotion_ready: false,
      benchmark_promotion_blockers: ['benchmark:out_of_sample_unproven'],
    })
    expect(dispatchPlan.dispatch_blocking_reasons).toEqual(
      expect.arrayContaining(['benchmark:out_of_sample_unproven']),
    )
    expect(paperPlan).toMatchObject({
      benchmark_promotion_ready: false,
      benchmark_promotion_blockers: ['benchmark:out_of_sample_unproven'],
    })
    expect(shadowPlan).toMatchObject({
      benchmark_promotion_ready: false,
      benchmark_promotion_blockers: ['benchmark:out_of_sample_unproven'],
    })
    expect(livePlan).toMatchObject({
      benchmark_promotion_ready: false,
      benchmark_promotion_blockers: ['benchmark:out_of_sample_unproven'],
      benchmark_gate_blocks_live: true,
      benchmark_gate_live_block_reason: 'out_of_sample_unproven',
    })
    expect(livePlan.live_blocking_reasons).toEqual(
      expect.arrayContaining(['benchmark:out_of_sample_unproven']),
    )
  })

  it('uses benchmark_promotion_summary as the live benchmark blocker fallback when the blocker summary is absent', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: makeBenchmarkResearchSignals(),
    })

    const liveFallbackRunDetails = {
      run: { id: 'run-benchmark-live-fallback-001', status: 'completed' },
      summary: {
        run_id: 'run-benchmark-live-fallback-001',
        workspace_id: 1,
        venue: 'polymarket',
        mode: 'advise',
        market_id: market.market_id,
        market_slug: market.slug ?? null,
        status: 'completed',
        recommendation: 'bet',
        side: 'yes',
        confidence: 0.55,
        probability_yes: 0.7,
        market_price_yes: 0.5,
        edge_bps: 1900,
      },
      artifacts: [],
      run_id: 'run-benchmark-live-fallback-001',
      workspace_id: 1,
      execution_projection: makeLiveBenchmarkExecutionProjection(),
      execution_readiness: adviseResult.execution_readiness,
      execution_pathways: adviseResult.execution_pathways,
      research_sidecar: adviseResult.research_sidecar,
      research_benchmark_gate_summary: undefined,
      research_benchmark_uplift_bps: undefined,
      research_benchmark_verdict: undefined,
      research_benchmark_gate_status: undefined,
      research_benchmark_promotion_status: undefined,
      research_benchmark_promotion_ready: undefined,
      research_benchmark_preview_available: undefined,
      research_benchmark_promotion_evidence: undefined,
      research_benchmark_evidence_level: undefined,
      research_promotion_gate_kind: undefined,
      research_benchmark_promotion_blocker_summary: undefined,
      research_benchmark_promotion_summary: undefined,
      research_benchmark_gate_blockers: undefined,
      research_benchmark_gate_reasons: undefined,
      benchmark_gate_summary: undefined,
      benchmark_promotion_ready: false,
      benchmark_promotion_summary: 'benchmark-only promotion summary fallback',
      benchmark_promotion_blocker_summary: undefined,
      benchmark_gate_blocks_live: undefined,
      benchmark_gate_live_block_reason: undefined,
      paper_surface: null,
      replay_surface: null,
      shadow_arbitrage: adviseResult.shadow_arbitrage ?? null,
      trade_intent_guard: adviseResult.trade_intent_guard ?? null,
      multi_venue_execution: adviseResult.multi_venue_execution ?? null,
    } as never
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(liveFallbackRunDetails)

    const livePlan = preparePredictionMarketRunLive({
      workspaceId: 1,
      runId: 'run-benchmark-live-fallback-001',
    })
    const liveRunDetails = getPredictionMarketRunDetails('run-benchmark-live-fallback-001', 1)

    expect(livePlan).toMatchObject({
      live_status: 'blocked',
      benchmark_promotion_ready: false,
      benchmark_gate_blocks_live: true,
      benchmark_gate_live_block_reason: 'benchmark-only promotion summary fallback',
      research_benchmark_live_block_reason: 'benchmark-only promotion summary fallback',
    })
    expect(liveRunDetails?.benchmark_gate_blocks_live).toBe(true)
    expect(liveRunDetails?.benchmark_gate_live_block_reason).toBe('benchmark-only promotion summary fallback')
    expect(livePlan.live_blocking_reasons).toEqual(
      expect.arrayContaining(['benchmark:out_of_sample_unproven']),
    )
  })

  it('keeps packet_bundle advisor_architecture benchmark-canonical when rehydrated research aliases disagree', async () => {
    const benchmarkCanonicalRunDetails = {
      ...structuredClone(storedRunDetails),
      research_benchmark_gate_summary:
        'research benchmark gate: market_only=0.5100 aggregate=0.5950 forecast=0.6200 promotion=ready ready=yes',
      research_benchmark_uplift_bps: 444,
      research_benchmark_verdict: 'local_benchmark_ready',
      research_benchmark_gate_status: 'preview_only',
      research_benchmark_promotion_status: 'eligible',
      research_benchmark_promotion_ready: true,
      research_benchmark_preview_available: true,
      research_benchmark_promotion_evidence: 'local_benchmark',
      research_benchmark_evidence_level: 'out_of_sample_promotion_evidence',
      research_promotion_gate_kind: 'local_benchmark',
      research_benchmark_promotion_blocker_summary: 'research canonical promotion satisfied',
      research_benchmark_promotion_summary: 'research canonical promotion satisfied',
      research_benchmark_gate_blockers: [],
      research_benchmark_gate_reasons: ['research canonical promotion'],
      research_benchmark_live_block_reason: null,
    } as never
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(benchmarkCanonicalRunDetails)

    const replayResult = await replayPredictionMarketRun({
      workspaceId: 1,
      actor: 'tester',
      runId: 'run-execution-readiness-001',
    })

    expect(replayResult.prediction_run).toMatchObject({
      benchmark_gate_blocks_live: false,
      research_benchmark_promotion_ready: true,
    })
    expect(replayResult.prediction_run?.benchmark_gate_live_block_reason ?? null).toBeNull()
    expect(replayResult.prediction_run?.research_benchmark_live_block_reason ?? null).toBeNull()
    expect(replayResult.packet_bundle?.advisor_architecture.stages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          stage_kind: 'execution_preflight',
          metadata: expect.objectContaining({
            benchmark_promotion_ready: false,
            benchmark_gate_blocks_live: false,
            benchmark_gate_live_block_reason: null,
            benchmark_promotion_gate_kind: 'preview_only',
          }),
        }),
      ]),
    )
  })

  it('prefers benchmark promotion summary over conflicting research blocker summary when canonical blocker summary is absent', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: makeBenchmarkResearchSignals(),
    })

    const conflictingRunDetails = {
      ...structuredClone(storedRunDetails),
      summary: structuredClone(storedRunDetails.summary),
      artifacts: [],
      run_id: 'run-benchmark-summary-priority-001',
      workspace_id: 1,
      execution_projection: makeLiveBenchmarkExecutionProjection(),
      execution_readiness: adviseResult.execution_readiness,
      execution_pathways: adviseResult.execution_pathways,
      research_sidecar: adviseResult.research_sidecar,
      research_benchmark_promotion_ready: false,
      research_benchmark_promotion_blocker_summary: 'research alias blocker should not win',
      research_benchmark_promotion_summary: 'research alias blocker should not win',
      research_benchmark_gate_blockers: ['out_of_sample_unproven'],
      benchmark_promotion_ready: false,
      benchmark_promotion_blocker_summary: undefined,
      benchmark_promotion_summary: 'benchmark-only canonical summary should win',
      benchmark_gate_blocks_live: undefined,
      benchmark_gate_live_block_reason: undefined,
      trade_intent_guard: adviseResult.trade_intent_guard ?? null,
      multi_venue_execution: adviseResult.multi_venue_execution ?? null,
      shadow_arbitrage: adviseResult.shadow_arbitrage ?? null,
      paper_surface: null,
      replay_surface: null,
    } as never
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(conflictingRunDetails)

    const livePlan = preparePredictionMarketRunLive({
      workspaceId: 1,
      runId: 'run-benchmark-summary-priority-001',
    })
    const liveRunDetails = getPredictionMarketRunDetails('run-benchmark-summary-priority-001', 1)

    expect(livePlan).toMatchObject({
      live_status: 'blocked',
      benchmark_promotion_ready: false,
      benchmark_gate_live_block_reason: 'benchmark-only canonical summary should win',
      benchmark_promotion_blocker_summary: 'benchmark-only canonical summary should win',
    })
    expect(liveRunDetails?.benchmark_gate_live_block_reason).toBe('benchmark-only canonical summary should win')
    expect(liveRunDetails?.trade_intent_guard?.metadata).toMatchObject({
      benchmark_promotion_blocker_summary: 'benchmark-only canonical summary should win',
      benchmark_gate_live_block_reason: 'benchmark-only canonical summary should win',
    })
  })

  it('prefers canonical benchmark promotion summary over conflicting research live block reason when no benchmark live block reason is stored', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: makeBenchmarkResearchSignals(),
    })

    const conflictingRunDetails = {
      ...structuredClone(storedRunDetails),
      summary: structuredClone(storedRunDetails.summary),
      artifacts: [],
      run_id: 'run-benchmark-live-reason-priority-001',
      workspace_id: 1,
      execution_projection: makeLiveBenchmarkExecutionProjection(),
      execution_readiness: adviseResult.execution_readiness,
      execution_pathways: adviseResult.execution_pathways,
      research_sidecar: adviseResult.research_sidecar,
      research_benchmark_promotion_ready: false,
      research_benchmark_live_block_reason: 'research live block reason should not win',
      research_benchmark_promotion_blocker_summary: 'research live block reason should not win',
      research_benchmark_promotion_summary: 'research live block reason should not win',
      research_benchmark_gate_blockers: ['out_of_sample_unproven'],
      benchmark_promotion_ready: false,
      benchmark_promotion_blocker_summary: undefined,
      benchmark_promotion_summary: 'benchmark-only live blocker summary should win',
      benchmark_gate_blocks_live: undefined,
      benchmark_gate_live_block_reason: undefined,
      trade_intent_guard: adviseResult.trade_intent_guard ?? null,
      multi_venue_execution: adviseResult.multi_venue_execution ?? null,
      shadow_arbitrage: adviseResult.shadow_arbitrage ?? null,
      paper_surface: null,
      replay_surface: null,
    } as never
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(conflictingRunDetails)

    const livePlan = preparePredictionMarketRunLive({
      workspaceId: 1,
      runId: 'run-benchmark-live-reason-priority-001',
    })
    const liveRunDetails = getPredictionMarketRunDetails('run-benchmark-live-reason-priority-001', 1)

    expect(livePlan).toMatchObject({
      live_status: 'blocked',
      benchmark_promotion_ready: false,
      benchmark_gate_live_block_reason: 'benchmark-only live blocker summary should win',
      benchmark_promotion_blocker_summary: 'benchmark-only live blocker summary should win',
    })
    expect(liveRunDetails?.benchmark_gate_live_block_reason).toBe('benchmark-only live blocker summary should win')
    expect(liveRunDetails?.trade_intent_guard?.metadata).toMatchObject({
      benchmark_promotion_blocker_summary: 'benchmark-only live blocker summary should win',
      benchmark_gate_live_block_reason: 'benchmark-only live blocker summary should win',
    })
  })

  it('uses benchmark promotion summary as stored live gate fallback when benchmark_gate_blocks_live is true but the live block reason is absent', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
      research_signals: makeBenchmarkResearchSignals(),
    })

    const storedLiveGateRunDetails = {
      ...structuredClone(storedRunDetails),
      summary: structuredClone(storedRunDetails.summary),
      artifacts: [],
      run_id: 'run-benchmark-live-stored-gate-fallback-001',
      workspace_id: 1,
      execution_projection: makeLiveBenchmarkExecutionProjection(),
      execution_readiness: adviseResult.execution_readiness,
      execution_pathways: adviseResult.execution_pathways,
      research_sidecar: adviseResult.research_sidecar,
      research_benchmark_promotion_ready: false,
      research_benchmark_promotion_blocker_summary: 'research stored live gate blocker should not win',
      research_benchmark_promotion_summary: 'research stored live gate blocker should not win',
      research_benchmark_gate_blockers: ['out_of_sample_unproven'],
      benchmark_promotion_ready: false,
      benchmark_promotion_blocker_summary: undefined,
      benchmark_promotion_summary: 'benchmark stored live gate summary should win',
      benchmark_gate_blocks_live: true,
      benchmark_gate_live_block_reason: undefined,
      trade_intent_guard: adviseResult.trade_intent_guard ?? null,
      multi_venue_execution: adviseResult.multi_venue_execution ?? null,
      shadow_arbitrage: adviseResult.shadow_arbitrage ?? null,
      paper_surface: null,
      replay_surface: null,
    } as never
    mocks.getStoredPredictionMarketRunDetails.mockReturnValue(storedLiveGateRunDetails)

    const livePlan = preparePredictionMarketRunLive({
      workspaceId: 1,
      runId: 'run-benchmark-live-stored-gate-fallback-001',
    })
    const liveRunDetails = getPredictionMarketRunDetails('run-benchmark-live-stored-gate-fallback-001', 1)

    expect(livePlan).toMatchObject({
      live_status: 'blocked',
      benchmark_promotion_ready: false,
      benchmark_gate_blocks_live: true,
      benchmark_gate_live_block_reason: 'benchmark stored live gate summary should win',
      benchmark_promotion_blocker_summary: 'benchmark stored live gate summary should win',
    })
    expect(liveRunDetails?.benchmark_gate_blocks_live).toBe(true)
    expect(liveRunDetails?.benchmark_gate_live_block_reason).toBe('benchmark stored live gate summary should win')
    expect(liveRunDetails?.trade_intent_guard?.metadata).toMatchObject({
      benchmark_promotion_blocker_summary: 'benchmark stored live gate summary should win',
      benchmark_gate_live_block_reason: 'benchmark stored live gate summary should win',
    })
  })

  it('blocks live readiness as soon as reconciliation drift is open', () => {
    const reconciliation = reconcileCapitalLedger({
      theoretical: {
        venue: 'polymarket',
        cash_available: 100,
        cash_locked: 0,
        withdrawable_amount: 100,
        open_exposure_usd: 0,
        positions: [],
      },
      observed: {
        venue: 'polymarket',
        cash_available: 99.75,
        cash_locked: 0,
        withdrawable_amount: 99.75,
        open_exposure_usd: 0,
        positions: [],
      },
      tolerance_usd: 0.01,
      tolerance_ratio: 0.001,
    })

    const readiness = buildPredictionMarketExecutionReadiness({
      capabilities: makeRuntimeGuard().capabilities,
      health: makeRuntimeGuard().health,
      budgets: makeRuntimeGuard().budgets,
      compliance_matrix: makeComplianceMatrixForReadiness(),
      capital_ledger: {
        snapshot: {
          venue: 'polymarket',
          collateral_currency: 'USD',
          cash_available: 100,
          cash_locked: 0,
          withdrawable_amount: 100,
          open_exposure_usd: 0,
          transfer_latency_estimate_ms: 15_000,
        },
        totals: {
          cash_total_usd: 100,
          exposure_total_usd: 0,
          locked_collateral_usd: 0,
          unrealized_pnl_usd: 0,
          open_positions: 0,
          utilization_ratio: 0,
        },
        positions: [],
        notes: [],
      } as any,
      reconciliation,
    })

    const liveMode = readiness.mode_readiness.find((report) => report.mode === 'live')
    expect(liveMode).not.toBeUndefined()
    expect(liveMode?.verdict).toBe('blocked')
    expect(liveMode?.blockers).toEqual(expect.arrayContaining([
      'reconciliation:open_drift:live_mode_blocked',
    ]))
    expect(readiness.warnings).toEqual(expect.arrayContaining([
      expect.stringContaining('reconciliation:'),
    ]))
  })

  it('keeps derived guard and multi-venue metadata aligned with the canonical selected path', async () => {
    const adviseResult = await advisePredictionMarket({
      workspaceId: 1,
      actor: 'tester',
      venue: 'polymarket',
      market_id: market.market_id,
    })

    const replayResult = await replayPredictionMarketRun({
      workspaceId: 1,
      actor: 'tester',
      runId: 'run-execution-readiness-001',
    })

    const assertCanonicalSelectionAlignment = (
      result: typeof adviseResult | typeof replayResult,
    ) => {
      const selectedPath = result.execution_projection?.selected_path ?? null
      const selectedProjectionPath = selectedPath
        ? result.execution_projection?.projected_paths[selectedPath] ?? null
        : null
      const selectedCanonicalSizeUsd = selectedProjectionPath?.sizing_signal?.canonical_size_usd ?? null
      const rawExpectedProjectionSelectedPreview =
        selectedProjectionPath?.canonical_trade_intent_preview ??
        selectedProjectionPath?.trade_intent_preview ??
        null
      const expectedProjectionSelectedPreview = rawExpectedProjectionSelectedPreview != null &&
        selectedCanonicalSizeUsd != null &&
        selectedCanonicalSizeUsd < rawExpectedProjectionSelectedPreview.size_usd
        ? {
          ...rawExpectedProjectionSelectedPreview,
          size_usd: selectedCanonicalSizeUsd,
          notes: [
            rawExpectedProjectionSelectedPreview.notes,
            `Canonical execution sizing caps preview size to ${selectedCanonicalSizeUsd} USD.`,
          ].filter(Boolean).join(' '),
        }
        : rawExpectedProjectionSelectedPreview
      const expectedTradeIntentPreview = expectedProjectionSelectedPreview
      const expectedProjectionSelectedPreviewSource = selectedProjectionPath?.canonical_trade_intent_preview != null
        ? 'canonical_trade_intent_preview'
        : selectedProjectionPath?.trade_intent_preview != null
          ? 'trade_intent_preview'
          : null
      const expectedTradeIntentPreviewSource = expectedProjectionSelectedPreviewSource ?? 'none'
      const expectedTradeIntentPreviewVia = selectedProjectionPath?.canonical_trade_intent_preview != null ||
          selectedProjectionPath?.trade_intent_preview != null
        ? 'execution_projection_selected_preview'
        : 'none'

      expect(result.trade_intent_guard?.selected_path).toBe(selectedPath)
      expect(result.trade_intent_guard?.highest_safe_mode).toBe(
        result.execution_projection?.highest_safe_requested_mode ?? null,
      )
      expect(result.trade_intent_guard?.trade_intent_preview ?? null).toEqual(expectedTradeIntentPreview)
      expect(result.trade_intent_guard?.metadata).toMatchObject({
        execution_pathways_highest_actionable_mode: result.execution_pathways?.highest_actionable_mode ?? null,
        trade_intent_preview_available: expectedTradeIntentPreview != null,
        trade_intent_preview_source: expectedTradeIntentPreviewSource,
        trade_intent_preview_via: expectedTradeIntentPreviewVia,
        trade_intent_preview_uses_projection_selected_preview:
          expectedTradeIntentPreviewVia === 'execution_projection_selected_preview',
        execution_projection_selected_preview_available:
          expectedTradeIntentPreviewVia === 'execution_projection_selected_preview',
        execution_projection_selected_preview_source:
          expectedProjectionSelectedPreviewSource,
        trade_intent_preview_capped_to_canonical_size:
          rawExpectedProjectionSelectedPreview != null &&
          expectedTradeIntentPreview != null &&
          rawExpectedProjectionSelectedPreview.size_usd !== expectedTradeIntentPreview.size_usd,
        selected_projection_path_status: selectedProjectionPath?.status ?? null,
        selected_projection_path_effective_mode: selectedProjectionPath?.effective_mode ?? null,
        selected_projection_sizing_signal_present: selectedProjectionPath?.sizing_signal != null,
        selected_projection_shadow_arbitrage_signal_present: selectedProjectionPath?.shadow_arbitrage_signal != null,
        selected_projection_canonical_size_usd: selectedProjectionPath?.sizing_signal?.canonical_size_usd ?? null,
      })

      expect(result.multi_venue_execution?.metadata).toMatchObject({
        execution_pathways_highest_actionable_mode: result.execution_pathways?.highest_actionable_mode ?? null,
        execution_projection_selected_path: selectedPath,
        execution_projection_selected_path_status: selectedProjectionPath?.status ?? null,
        execution_projection_selected_path_shadow_signal_present: selectedProjectionPath?.shadow_arbitrage_signal != null,
        execution_projection_selected_path_canonical_size_usd: selectedProjectionPath?.sizing_signal?.canonical_size_usd ?? null,
        execution_projection_selected_preview_available: expectedProjectionSelectedPreview != null,
        execution_projection_selected_preview_source: expectedProjectionSelectedPreviewSource,
        execution_projection_selected_preview_size_usd:
          expectedProjectionSelectedPreview?.size_usd ?? null,
        execution_surface_preview_via: expectedTradeIntentPreviewVia,
        execution_surface_preview_source: expectedTradeIntentPreviewSource,
        execution_surface_preview_size_usd: expectedTradeIntentPreview?.size_usd ?? null,
        execution_surface_preview_uses_projection_selected_preview:
          expectedTradeIntentPreviewVia === 'execution_projection_selected_preview',
      })

      expect(result.prediction_run).toMatchObject({
        execution_projection_gate_name: 'execution_projection',
        execution_projection_preflight_only: true,
        execution_projection_requested_path: result.execution_projection?.requested_path ?? null,
        execution_pathways_highest_actionable_mode:
          result.execution_pathways?.highest_actionable_mode ??
          result.execution_projection?.selected_path ??
          result.execution_projection?.highest_safe_requested_mode ??
          null,
        execution_projection_selected_path: selectedPath,
        execution_projection_selected_path_status: selectedProjectionPath?.status ?? null,
        execution_projection_selected_path_effective_mode: selectedProjectionPath?.effective_mode ?? null,
        execution_projection_selected_path_reason_summary: selectedProjectionPath?.reason_summary ?? null,
        execution_projection_verdict: result.execution_projection?.verdict ?? null,
        execution_projection_highest_safe_requested_mode:
          result.execution_projection?.highest_safe_requested_mode ?? null,
        execution_projection_recommended_effective_mode:
          result.execution_projection?.recommended_effective_mode ?? null,
        execution_projection_manual_review_required:
          result.execution_projection?.manual_review_required ?? false,
        execution_projection_ttl_ms: result.execution_projection?.ttl_ms ?? null,
        execution_projection_expires_at: result.execution_projection?.expires_at ?? null,
        execution_projection_blocking_reasons:
          result.execution_projection?.blocking_reasons ?? [],
        execution_projection_downgrade_reasons:
          result.execution_projection?.downgrade_reasons ?? [],
        execution_projection_summary: result.execution_projection?.summary ?? null,
        execution_projection_preflight_summary:
          result.execution_projection?.preflight_summary ?? null,
        execution_projection_capital_status: result.execution_projection?.basis.capital_status ?? null,
        execution_projection_reconciliation_status: result.execution_projection?.basis.reconciliation_status ?? null,
        execution_projection_selected_edge_bucket:
          result.execution_projection?.selected_edge_bucket ?? null,
        execution_projection_selected_pre_trade_gate:
          result.execution_projection?.selected_pre_trade_gate ?? null,
        execution_projection_selected_pre_trade_gate_verdict:
          result.execution_projection?.selected_pre_trade_gate?.verdict ?? null,
        execution_projection_selected_pre_trade_gate_summary:
          result.execution_projection?.selected_pre_trade_gate?.summary ?? null,
        execution_projection_selected_path_net_edge_bps:
          result.execution_projection?.selected_pre_trade_gate?.net_edge_bps ?? null,
        execution_projection_selected_path_minimum_net_edge_bps:
          result.execution_projection?.selected_pre_trade_gate?.minimum_net_edge_bps ?? null,
        execution_projection_selected_preview: expectedProjectionSelectedPreview,
        execution_projection_selected_preview_source: expectedProjectionSelectedPreviewSource,
        execution_projection_selected_path_canonical_size_usd: selectedProjectionPath?.sizing_signal?.canonical_size_usd ?? null,
        execution_projection_selected_path_shadow_signal_present: selectedProjectionPath?.shadow_arbitrage_signal != null,
      })

      expectFutureTopLevelTradeIntentPreviewAlignment(
        result as FutureTopLevelTradeIntentPreviewSurface,
      )
    }

    assertCanonicalSelectionAlignment(adviseResult)
    assertCanonicalSelectionAlignment(replayResult)
  })

})
