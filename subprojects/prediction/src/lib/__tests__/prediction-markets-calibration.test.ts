import { describe, expect, it } from 'vitest'
import {
  applyCalibrationCurve,
  buildCalibrationBins,
  buildCalibrationReport,
} from '@/lib/prediction-markets/calibration'

describe('prediction markets calibration helpers', () => {
  it('builds weighted bins and calibration metrics', () => {
    const report = buildCalibrationReport([
      { predicted_probability: 0.1, actual_outcome: 0, weight: 1 },
      { predicted_probability: 0.2, actual_outcome: 0, weight: 2 },
      { predicted_probability: 0.7, actual_outcome: 1, weight: 1 },
      { predicted_probability: 0.8, actual_outcome: 1, weight: 3 },
    ], { bin_count: 4 })

    expect(report.bin_count).toBe(4)
    expect(report.total_points).toBe(4)
    expect(report.total_weight).toBe(7)
    expect(report.base_rate).toBeCloseTo(4 / 7, 6)
    expect(report.bins).toHaveLength(4)
    expect(report.bins[0].sample_count).toBe(2)
    expect(report.bins[2].sample_count).toBe(1)
    expect(report.bins[3].sample_count).toBe(1)
    expect(report.brier_score).not.toBeNull()
    expect(report.calibration_error).not.toBeNull()
  })

  it('returns stable output for empty curves', () => {
    const report = buildCalibrationReport([], { bin_count: 5 })

    expect(report.total_points).toBe(0)
    expect(report.bins).toHaveLength(5)
    expect(report.base_rate).toBeNull()
    expect(report.brier_score).toBeNull()
    expect(report.notes).toContain('empty_calibration_curve')
  })

  it('applies calibration by interpolating adjacent bins', () => {
    const report = buildCalibrationReport([
      { predicted_probability: 0.1, actual_outcome: 0 },
      { predicted_probability: 0.2, actual_outcome: 0 },
      { predicted_probability: 0.7, actual_outcome: 1 },
      { predicted_probability: 0.8, actual_outcome: 1 },
    ], { bin_count: 4 })

    const adjustedLow = applyCalibrationCurve(0.15, report)
    const adjustedHigh = applyCalibrationCurve(0.75, report)

    expect(adjustedLow.source).not.toBe('no_data')
    expect(adjustedLow.output_probability).toBeLessThanOrEqual(0.2)
    expect(adjustedHigh.output_probability).toBeGreaterThanOrEqual(0.8)
  })

  it('exposes raw bins for downstream dashboards', () => {
    const bins = buildCalibrationBins([
      { predicted_probability: 0.05, actual_outcome: 0 },
      { predicted_probability: 0.95, actual_outcome: 1 },
    ], { bin_count: 2 })

    expect(bins).toEqual([
      expect.objectContaining({ bin_index: 0, sample_count: 1, actual_rate: 0 }),
      expect.objectContaining({ bin_index: 1, sample_count: 1, actual_rate: 1 }),
    ])
  })
})
