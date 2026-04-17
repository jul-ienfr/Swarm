import { getPredictionMarketP1CRuntimeSummary } from './external-runtime'
import type { PredictionMarketWorldStateGeoContext } from './world-state'

export type PredictionMarketCopReadModel = {
  read_only: true
  runtime_summary: string
  overlays: string[]
  alert_channels: string[]
  geo_context_present: boolean
  summary: string
}

export function buildPredictionMarketCopReadModel(input: {
  geo_context?: PredictionMarketWorldStateGeoContext | null
  source_refs?: string[] | null
} = {}): PredictionMarketCopReadModel {
  const runtime = getPredictionMarketP1CRuntimeSummary({
    geo_context_present: input.geo_context != null,
  })
  const overlays = [
    input.geo_context ? 'geo_overlay' : null,
    'source_heatmap',
    'triage_cards',
    'operator_alert_stack',
  ].filter((value): value is string => value != null)

  return {
    read_only: true,
    runtime_summary: runtime.summary,
    overlays,
    alert_channels: ['dashboard_events', 'dashboard_read_models', 'source_audit'],
    geo_context_present: input.geo_context != null,
    summary: [
      runtime.summary,
      `${overlays.length} read-only overlay(s) available.`,
      input.geo_context ? `Geo context covers ${input.geo_context.adcodes.length} region(s).` : 'No geo overlay is currently attached.',
    ].join(' '),
  }
}
