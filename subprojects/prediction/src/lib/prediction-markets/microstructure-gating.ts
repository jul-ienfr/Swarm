import type {
  MicrostructureLabReport,
  MicrostructureRecommendedMode,
} from '@/lib/prediction-markets/microstructure-lab'
import type { MarketRecommendationPacket } from '@/lib/prediction-markets/schemas'

export type PredictionMarketExecutionGateMode = 'paper' | 'shadow' | 'live'

export type MicrostructurePathSignals = {
  blockers: string[]
  warnings: string[]
  slippage_penalty_bps: number
  fill_confidence_penalty: number
  notes: string[]
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function scaledSlippagePenalty(input: {
  mode: PredictionMarketExecutionGateMode
  executableDeteriorationBps: number
}): number {
  const factor = input.mode === 'paper'
    ? 0.15
    : input.mode === 'shadow'
      ? 0.4
      : 0.6

  return Math.max(0, Math.round(input.executableDeteriorationBps * factor))
}

function scaledFillPenalty(input: {
  mode: PredictionMarketExecutionGateMode
  qualityScore: number
}): number {
  const base = input.mode === 'paper'
    ? 0.04
    : input.mode === 'shadow'
      ? 0.12
      : 0.18

  const qualityPenalty = 1 - clamp(input.qualityScore, 0, 1)
  return Number((base * qualityPenalty).toFixed(4))
}

function preferredModeWarning(
  preferredMode: MicrostructureRecommendedMode,
  mode: PredictionMarketExecutionGateMode,
): string | null {
  if (preferredMode === 'wait') {
    return mode === 'paper'
      ? 'microstructure:paper_dry_run_only'
      : 'microstructure:recommended_wait'
  }

  if (preferredMode === 'paper' && mode === 'shadow') {
    return 'microstructure:paper_first_before_shadow'
  }

  if (preferredMode === 'paper' && mode === 'live') {
    return 'microstructure:paper_first_before_live'
  }

  if (preferredMode === 'shadow' && mode === 'live') {
    return 'microstructure:shadow_first_before_live'
  }

  return null
}

export function buildMicrostructurePathSignals(input: {
  mode: PredictionMarketExecutionGateMode
  recommendation: Pick<MarketRecommendationPacket, 'action'>
  microstructureLab?: MicrostructureLabReport | null
}): MicrostructurePathSignals {
  const report = input.microstructureLab
  if (!report || input.recommendation.action !== 'bet') {
    return {
      blockers: [],
      warnings: [],
      slippage_penalty_bps: 0,
      fill_confidence_penalty: 0,
      notes: [],
    }
  }

  const summary = report.summary
  const preferredMode = summary.recommended_mode
  const blockers: string[] = []
  const warnings: string[] = []
  const notes: string[] = [
    `microstructure_recommended_mode:${preferredMode}`,
    `microstructure_worst_case:${summary.worst_case_kind}:${summary.worst_case_severity}`,
    `microstructure_execution_quality_score:${summary.execution_quality_score}`,
  ]

  if (preferredMode === 'wait' && input.mode !== 'paper') {
    blockers.push('microstructure:recommended_wait')
  } else {
    const warning = preferredModeWarning(preferredMode, input.mode)
    if (warning) warnings.push(warning)
  }

  const lowQuality = summary.execution_quality_score < 0.55
  const highStress = preferredMode === 'wait' || lowQuality || summary.worst_case_severity === 'critical'
  const slippagePenalty = highStress
    ? scaledSlippagePenalty({
      mode: input.mode,
      executableDeteriorationBps: summary.executable_deterioration_bps,
    })
    : 0
  const fillPenalty = highStress
    ? scaledFillPenalty({
      mode: input.mode,
      qualityScore: summary.execution_quality_score,
    })
    : 0

  if (preferredMode === 'wait' && input.mode === 'paper') {
    warnings.push('microstructure:paper_dry_run_only')
  }

  if (summary.scenario_overview.length > 0) {
    notes.push(`microstructure_overview:${summary.scenario_overview[0]}`)
  }

  return {
    blockers,
    warnings,
    slippage_penalty_bps: slippagePenalty,
    fill_confidence_penalty: fillPenalty,
    notes,
  }
}
