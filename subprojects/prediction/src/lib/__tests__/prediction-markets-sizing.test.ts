import { describe, expect, it } from 'vitest'
import { buildConservativePredictionMarketSizing } from '@/lib/prediction-markets/sizing'

describe('prediction market sizing helper', () => {
  it('applies conservative haircuts when confidence, calibration, liquidity, depth, and correlation are weak', () => {
    const sizing = buildConservativePredictionMarketSizing({
      baseSizeUsd: 100,
      signals: {
        confidence: 0.42,
        calibration_ece: 0.38,
        liquidity_usd: 8_000,
        depth_near_touch: 300,
        portfolio_correlation: 0.9,
      },
    })

    expect(sizing.size_usd).toBeLessThan(20)
    expect(sizing.multiplier).toBeLessThan(0.2)
    expect(sizing.factors.confidence_factor).toBeLessThan(0.8)
    expect(sizing.factors.calibration_factor).toBeLessThan(0.9)
    expect(sizing.factors.liquidity_factor).toBeLessThan(0.8)
    expect(sizing.factors.depth_factor).toBeLessThan(0.8)
    expect(sizing.factors.portfolio_correlation_factor).toBeLessThan(0.8)
    expect(sizing.notes.join(' ')).toContain('thin')
    expect(sizing.notes.join(' ')).toContain('shallow')
    expect(sizing.notes.join(' ')).toContain('elevated')
  })

  it('remains conservative even when the signals are strong', () => {
    const sizing = buildConservativePredictionMarketSizing({
      baseSizeUsd: 100,
      signals: {
        confidence: 0.94,
        calibration_ece: 0.03,
        liquidity_usd: 250_000,
        depth_near_touch: 6_000,
        portfolio_correlation: 0.08,
      },
    })

    expect(sizing.size_usd).toBeLessThanOrEqual(85)
    expect(sizing.multiplier).toBeLessThanOrEqual(0.85)
    expect(sizing.size_usd).toBeGreaterThan(50)
    expect(sizing.factors.confidence_factor).toBeGreaterThan(0.9)
    expect(sizing.factors.calibration_factor).toBeGreaterThan(0.9)
    expect(sizing.factors.liquidity_factor).toBeCloseTo(1, 4)
    expect(sizing.factors.depth_factor).toBeCloseTo(1, 4)
  })

  it('uses conservative defaults when calibration and correlation are missing', () => {
    const sizing = buildConservativePredictionMarketSizing({
      baseSizeUsd: 80,
      signals: {
        confidence: 0.8,
        liquidity_usd: 120_000,
        depth_near_touch: 4_000,
      },
    })

    expect(sizing.size_usd).toBeLessThan(80)
    expect(sizing.notes.join(' ')).toContain('Calibration unavailable')
    expect(sizing.notes.join(' ')).toContain('Portfolio correlation unavailable')
    expect(sizing.factors.calibration_factor).toBeLessThan(0.9)
    expect(sizing.factors.portfolio_correlation_factor).toBeLessThan(0.95)
  })

  it('respects explicit min and max bounds', () => {
    const capped = buildConservativePredictionMarketSizing({
      baseSizeUsd: 200,
      minSizeUsd: 25,
      maxSizeUsd: 40,
      signals: {
        confidence: 0.99,
        calibration_ece: 0.01,
        liquidity_usd: 500_000,
        depth_near_touch: 25_000,
        portfolio_correlation: 0.01,
      },
    })

    expect(capped.size_usd).toBe(40)
    expect(capped.base_size_usd).toBe(200)
    expect(capped.multiplier).toBeLessThanOrEqual(0.85)
  })
})
