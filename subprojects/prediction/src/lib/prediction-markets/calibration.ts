export type CalibrationPoint = {
  predicted_probability: number
  actual_outcome: number | boolean
  weight?: number | null
  label?: string | null
}

export type CalibrationBin = {
  bin_index: number
  lower_bound: number
  upper_bound: number
  sample_count: number
  sample_weight: number
  predicted_mean: number | null
  actual_rate: number | null
  calibration_gap: number | null
  brier_score: number | null
}

export type CalibrationCurveAdjustment = {
  input_probability: number
  output_probability: number
  source: 'no_data' | 'nearest_bin' | 'interpolated'
  matching_bins: number[]
}

export type CalibrationReport = {
  bin_count: number
  total_points: number
  total_weight: number
  base_rate: number | null
  brier_score: number | null
  calibration_error: number | null
  sharpness: number | null
  reliability: number | null
  max_calibration_gap: number | null
  bins: CalibrationBin[]
  notes: string[]
}

export type CalibrationOptions = {
  bin_count?: number
  minimum_points_for_summary?: number
}

function clampProbability(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.min(1, Math.max(0, value))
}

function normalizeActual(actual: number | boolean): number {
  if (typeof actual === 'boolean') return actual ? 1 : 0
  return actual >= 0.5 ? 1 : 0
}

function normalizeWeight(weight: number | null | undefined): number {
  if (weight == null || !Number.isFinite(weight) || weight <= 0) return 1
  return weight
}

function buildEmptyBins(binCount: number): CalibrationBin[] {
  return Array.from({ length: binCount }, (_, index) => ({
    bin_index: index,
    lower_bound: Number((index / binCount).toFixed(4)),
    upper_bound: Number(((index + 1) / binCount).toFixed(4)),
    sample_count: 0,
    sample_weight: 0,
    predicted_mean: null,
    actual_rate: null,
    calibration_gap: null,
    brier_score: null,
  }))
}

export function buildCalibrationBins(
  points: readonly CalibrationPoint[],
  options: CalibrationOptions = {},
): CalibrationBin[] {
  const binCount = Math.max(1, Math.floor(options.bin_count ?? 10))
  const bins = buildEmptyBins(binCount)

  for (const point of points) {
    const predicted = clampProbability(Number(point.predicted_probability))
    const actual = normalizeActual(point.actual_outcome)
    const weight = normalizeWeight(point.weight)
    const index = Math.min(binCount - 1, Math.floor(predicted * binCount))
    const bin = bins[index]
    bin.sample_count += 1
    bin.sample_weight += weight
    bin.predicted_mean = (bin.predicted_mean ?? 0) + predicted * weight
    bin.actual_rate = (bin.actual_rate ?? 0) + actual * weight
    bin.brier_score = (bin.brier_score ?? 0) + Math.pow(predicted - actual, 2) * weight
  }

  for (const bin of bins) {
    if (bin.sample_weight <= 0) continue
    bin.predicted_mean = Number((bin.predicted_mean! / bin.sample_weight).toFixed(6))
    bin.actual_rate = Number((bin.actual_rate! / bin.sample_weight).toFixed(6))
    bin.calibration_gap = Number((bin.actual_rate - bin.predicted_mean).toFixed(6))
    bin.brier_score = Number((bin.brier_score! / bin.sample_weight).toFixed(6))
  }

  return bins
}

export function buildCalibrationReport(
  points: readonly CalibrationPoint[],
  options: CalibrationOptions = {},
): CalibrationReport {
  const binCount = Math.max(1, Math.floor(options.bin_count ?? 10))
  const minimumPointsForSummary = Math.max(1, Math.floor(options.minimum_points_for_summary ?? 1))
  const bins = buildCalibrationBins(points, { bin_count: binCount })
  const totalPoints = points.length
  const totalWeight = points.reduce((sum, point) => sum + normalizeWeight(point.weight), 0)
  const weightedActual = points.reduce((sum, point) => sum + normalizeActual(point.actual_outcome) * normalizeWeight(point.weight), 0)
  const baseRate = totalWeight > 0 ? weightedActual / totalWeight : null
  const binWeightSum = bins.reduce((sum, bin) => sum + bin.sample_weight, 0)
  const weightedGap = bins.reduce((sum, bin) => sum + Math.abs(bin.calibration_gap ?? 0) * bin.sample_weight, 0)
  const weightedBrier = bins.reduce((sum, bin) => sum + (bin.brier_score ?? 0) * bin.sample_weight, 0)
  const sharpness = points.length > 0 && baseRate !== null
    ? points.reduce((sum, point) => sum + Math.abs(clampProbability(point.predicted_probability) - baseRate) * normalizeWeight(point.weight), 0) / totalWeight
    : null
  const maxCalibrationGap = bins.reduce((max, bin) => Math.max(max, Math.abs(bin.calibration_gap ?? 0)), 0)

  const notes: string[] = []
  if (totalPoints < minimumPointsForSummary) {
    notes.push(`insufficient_points:${totalPoints}/${minimumPointsForSummary}`)
  }
  if (binWeightSum === 0) {
    notes.push('empty_calibration_curve')
  }
  if (maxCalibrationGap >= 0.15) {
    notes.push('material_calibration_gap')
  }

  return {
    bin_count: binCount,
    total_points: totalPoints,
    total_weight: Number(totalWeight.toFixed(6)),
    base_rate: baseRate === null ? null : Number(baseRate.toFixed(6)),
    brier_score: totalWeight > 0 ? Number((weightedBrier / totalWeight).toFixed(6)) : null,
    calibration_error: totalWeight > 0 ? Number((weightedGap / totalWeight).toFixed(6)) : null,
    sharpness: sharpness === null ? null : Number(sharpness.toFixed(6)),
    reliability: totalWeight > 0 ? Number((weightedGap / totalWeight).toFixed(6)) : null,
    max_calibration_gap: Number(maxCalibrationGap.toFixed(6)),
    bins,
    notes,
  }
}

export function calibrateProbability(
  probability: number,
  report: CalibrationReport,
): CalibrationCurveAdjustment {
  const input_probability = clampProbability(probability)
  const populatedBins = report.bins.filter((bin) => bin.sample_weight > 0 && bin.predicted_mean !== null && bin.actual_rate !== null)
  if (populatedBins.length === 0) {
    return {
      input_probability,
      output_probability: input_probability,
      source: 'no_data',
      matching_bins: [],
    }
  }

  const ordered = [...populatedBins].sort((left, right) => (left.predicted_mean ?? 0) - (right.predicted_mean ?? 0))
  const exact = ordered.find((bin) => Math.abs((bin.predicted_mean ?? 0) - input_probability) <= 1e-6)
  if (exact) {
    return {
      input_probability,
      output_probability: clampProbability(exact.actual_rate ?? input_probability),
      source: 'nearest_bin',
      matching_bins: [exact.bin_index],
    }
  }

  if (input_probability <= (ordered[0].predicted_mean ?? 0)) {
    return {
      input_probability,
      output_probability: clampProbability(ordered[0].actual_rate ?? input_probability),
      source: 'nearest_bin',
      matching_bins: [ordered[0].bin_index],
    }
  }
  if (input_probability >= (ordered[ordered.length - 1].predicted_mean ?? 1)) {
    const last = ordered[ordered.length - 1]
    return {
      input_probability,
      output_probability: clampProbability(last.actual_rate ?? input_probability),
      source: 'nearest_bin',
      matching_bins: [last.bin_index],
    }
  }

  for (let index = 0; index < ordered.length - 1; index += 1) {
    const left = ordered[index]
    const right = ordered[index + 1]
    const leftMean = left.predicted_mean ?? 0
    const rightMean = right.predicted_mean ?? 1
    if (input_probability < leftMean || input_probability > rightMean) continue
    const span = rightMean - leftMean
    const alpha = span <= 0 ? 0 : (input_probability - leftMean) / span
    const output_probability = clampProbability(
      (left.actual_rate ?? input_probability) * (1 - alpha) + (right.actual_rate ?? input_probability) * alpha,
    )
    return {
      input_probability,
      output_probability,
      source: 'interpolated',
      matching_bins: [left.bin_index, right.bin_index],
    }
  }

  const nearest = ordered.reduce((best, candidate) => {
    const candidateDistance = Math.abs((candidate.predicted_mean ?? 0) - input_probability)
    const bestDistance = Math.abs((best.predicted_mean ?? 0) - input_probability)
    return candidateDistance < bestDistance ? candidate : best
  }, ordered[0])

  return {
    input_probability,
    output_probability: clampProbability(nearest.actual_rate ?? input_probability),
    source: 'nearest_bin',
    matching_bins: [nearest.bin_index],
  }
}

export function applyCalibrationCurve(
  probability: number,
  report: CalibrationReport,
): CalibrationCurveAdjustment {
  return calibrateProbability(probability, report)
}
