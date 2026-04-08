import { describe, expect, it } from 'vitest'
import {
  evaluatePredictionMarketCompliance,
  evaluatePredictionMarketComplianceMatrix,
} from '@/lib/prediction-markets/compliance'

describe('prediction markets compliance guard', () => {
  it('authorizes discovery on an execution-equivalent venue by default', () => {
    const decision = evaluatePredictionMarketCompliance({
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      mode: 'discovery',
    })

    expect(decision).toMatchObject({
      requested_mode: 'discovery',
      effective_mode: 'discovery',
      status: 'authorized',
      allowed: true,
    })
    expect(decision.reasons).toEqual([])
    expect(decision.summary).toContain('Discovery mode is authorized')
  })

  it('degrades paper mode when there is no native paper support', () => {
    const decision = evaluatePredictionMarketCompliance({
      venue: 'kalshi',
      venue_type: 'execution-equivalent',
      mode: 'paper',
      capabilities: {
        supports_discovery: true,
        supports_metadata: true,
        supports_paper_mode: false,
      },
    })

    expect(decision).toMatchObject({
      effective_mode: 'paper',
      status: 'degraded',
      allowed: true,
    })
    expect(decision.reasons.map((reason) => reason.code)).toContain('paper_mode_native_unavailable')
    expect(decision.summary).toContain('Paper mode is degraded')
  })

  it('downgrades live mode to shadow when execution is not supported', () => {
    const decision = evaluatePredictionMarketCompliance({
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      mode: 'live',
      capabilities: {
        supports_discovery: true,
        supports_metadata: true,
        supports_orderbook: true,
        supports_trades: true,
        supports_execution: false,
      },
    })

    expect(decision).toMatchObject({
      requested_mode: 'live',
      effective_mode: 'shadow',
      status: 'degraded',
      allowed: true,
    })
    expect(decision.reasons.map((reason) => reason.code)).toEqual([
      'execution_not_supported',
      'mode_downgraded',
    ])
    expect(decision.summary).toContain('degraded to shadow')
  })

  it('downgrades live mode to shadow when manual review is required before live', () => {
    const decision = evaluatePredictionMarketCompliance({
      venue: 'kalshi',
      venue_type: 'execution-equivalent',
      mode: 'live',
      capabilities: {
        supports_discovery: true,
        supports_metadata: true,
        supports_orderbook: true,
        supports_trades: true,
        supports_execution: true,
        automation_constraints: ['manual review before live'],
      },
    })

    expect(decision).toMatchObject({
      effective_mode: 'shadow',
      status: 'degraded',
      allowed: true,
    })
    expect(decision.reasons.map((reason) => reason.code)).toEqual([
      'manual_review_before_live',
      'mode_downgraded',
    ])
    expect(decision.summary).toContain('manual review before execution is allowed')
  })

  it('downgrades shadow mode to paper on a reference-only venue', () => {
    const decision = evaluatePredictionMarketCompliance({
      venue: 'polymarket',
      venue_type: 'reference-only',
      mode: 'shadow',
      capabilities: {
        supports_discovery: true,
        supports_metadata: true,
      },
    })

    expect(decision).toMatchObject({
      effective_mode: 'paper',
      status: 'degraded',
      allowed: true,
    })
    expect(decision.reasons.map((reason) => reason.code)).toEqual([
      'reference_only_venue_type',
      'mode_downgraded',
    ])
    expect(decision.summary).toContain('degraded to paper')
  })

  it('blocks live mode when discovery support is missing and no fallback exists', () => {
    const decision = evaluatePredictionMarketCompliance({
      venue: 'kalshi',
      venue_type: 'execution-equivalent',
      mode: 'live',
      capabilities: {
        supports_discovery: false,
      },
    })

    expect(decision).toMatchObject({
      effective_mode: 'live',
      status: 'blocked',
      allowed: false,
    })
    expect(decision.reasons.map((reason) => reason.code)).toEqual(['discovery_not_supported'])
    expect(decision.summary).toContain('blocked')
  })

  it('downgrades live mode to paper when jurisdiction is explicitly restricted', () => {
    const decision = evaluatePredictionMarketCompliance({
      venue: 'kalshi',
      venue_type: 'execution-equivalent',
      mode: 'live',
      capabilities: {
        supports_discovery: true,
        supports_metadata: true,
        supports_orderbook: true,
        supports_trades: true,
        supports_execution: true,
      },
      jurisdiction: 'restricted',
      account_type: 'trading',
      kyc_status: 'approved',
      api_key_present: true,
      trading_enabled: true,
    })

    expect(decision).toMatchObject({
      effective_mode: 'paper',
      status: 'degraded',
      allowed: true,
    })
    expect(decision.reasons.map((reason) => reason.code)).toEqual([
      'jurisdiction_restricted',
      'mode_downgraded',
    ])
    expect(decision.account_readiness).toMatchObject({
      jurisdiction_status: 'restricted',
      ready_for_shadow: false,
      ready_for_live: false,
    })
  })

  it('downgrades shadow mode to paper when account readiness is insufficient', () => {
    const decision = evaluatePredictionMarketCompliance({
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      mode: 'shadow',
      capabilities: {
        supports_discovery: true,
        supports_metadata: true,
        supports_orderbook: true,
        supports_trades: true,
      },
      jurisdiction: 'us',
      account_type: 'viewer',
      kyc_status: 'approved',
      api_key_present: false,
      trading_enabled: true,
    })

    expect(decision).toMatchObject({
      effective_mode: 'paper',
      status: 'degraded',
      allowed: true,
    })
    expect(decision.reasons.map((reason) => reason.code)).toEqual([
      'account_type_not_ready_for_shadow',
      'api_key_missing',
      'mode_downgraded',
    ])
    expect(decision.account_readiness).toMatchObject({
      jurisdiction_status: 'allowed',
      account_type: 'viewer',
      ready_for_shadow: false,
    })
  })

  it('downgrades live mode to shadow when an upstream manual review flag is present', () => {
    const decision = evaluatePredictionMarketCompliance({
      venue: 'kalshi',
      venue_type: 'execution-equivalent',
      mode: 'live',
      capabilities: {
        supports_discovery: true,
        supports_metadata: true,
        supports_orderbook: true,
        supports_trades: true,
        supports_execution: true,
      },
      jurisdiction: 'us',
      account_type: 'trading',
      kyc_status: 'approved',
      api_key_present: true,
      trading_enabled: true,
      manual_review_required: true,
    })

    expect(decision).toMatchObject({
      effective_mode: 'shadow',
      status: 'degraded',
      allowed: true,
    })
    expect(decision.reasons.map((reason) => reason.code)).toEqual([
      'manual_review_required',
      'mode_downgraded',
    ])
    expect(decision.account_readiness).toMatchObject({
      manual_review_required: true,
      ready_for_shadow: true,
      ready_for_live: false,
    })
  })

  it('authorizes shadow mode when only live manual review remains', () => {
    const decision = evaluatePredictionMarketCompliance({
      venue: 'kalshi',
      venue_type: 'execution-equivalent',
      mode: 'shadow',
      capabilities: {
        supports_discovery: true,
        supports_metadata: true,
        supports_orderbook: true,
        supports_trades: true,
      },
      jurisdiction: 'us',
      account_type: 'trading',
      kyc_status: 'approved',
      api_key_present: true,
      trading_enabled: true,
      manual_review_required: true,
    })

    expect(decision).toMatchObject({
      effective_mode: 'shadow',
      status: 'authorized',
      allowed: true,
    })
    expect(decision.reasons).toEqual([])
    expect(decision.account_readiness).toMatchObject({
      manual_review_required: true,
      ready_for_shadow: true,
      ready_for_live: false,
    })
  })

  it('builds a compliance matrix with highest authorized mode and readiness state', () => {
    const matrix = evaluatePredictionMarketComplianceMatrix({
      venue: 'polymarket',
      venue_type: 'execution-equivalent',
      capabilities: {
        supports_discovery: true,
        supports_metadata: true,
        supports_orderbook: true,
        supports_trades: true,
        supports_execution: true,
      },
      jurisdiction: 'us',
      account_type: 'trading',
      kyc_status: 'approved',
      api_key_present: true,
      trading_enabled: true,
    })

    expect(matrix.highest_authorized_mode).toBe('live')
    expect(matrix.decisions.live.status).toBe('authorized')
    expect(matrix.decisions.shadow.status).toBe('authorized')
    expect(matrix.account_readiness).toMatchObject({
      jurisdiction_status: 'allowed',
      ready_for_shadow: true,
      ready_for_live: true,
    })
  })
})
