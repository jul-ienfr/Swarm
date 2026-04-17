import { getPredictionMarketP1BRuntimeSummary } from './external-runtime'

export type PredictionMarketForecastGovernanceArtifact = {
  read_only: true
  runtime_summary: string
  dissent_enabled: boolean
  benchmark_discipline_enabled: boolean
  source_refs: string[]
  notes: string[]
  summary: string
}

export function buildPredictionMarketForecastGovernanceArtifact(input: {
  operator_thesis_present?: boolean | null
  research_pipeline_trace_present?: boolean | null
  benchmark_summary?: string | null
} = {}): PredictionMarketForecastGovernanceArtifact {
  const runtime = getPredictionMarketP1BRuntimeSummary({
    operator_thesis_present: input.operator_thesis_present ?? false,
    research_pipeline_trace_present: input.research_pipeline_trace_present ?? false,
  })

  return {
    read_only: true,
    runtime_summary: runtime.summary,
    dissent_enabled: Boolean(input.research_pipeline_trace_present),
    benchmark_discipline_enabled: Boolean(input.benchmark_summary),
    source_refs: runtime.integration.profile_ids,
    notes: [
      input.research_pipeline_trace_present ? 'research_pipeline_trace_available' : 'research_pipeline_trace_missing',
      input.operator_thesis_present ? 'operator_thesis_available' : 'operator_thesis_missing',
      input.benchmark_summary ? `benchmark_summary:${input.benchmark_summary}` : 'benchmark_summary_missing',
    ],
    summary: [
      runtime.summary,
      input.research_pipeline_trace_present
        ? 'Dissent and counterfactual governance are available in read-only mode.'
        : 'Dissent governance remains catalog-only until research pipeline trace is present.',
      input.benchmark_summary
        ? 'Benchmark governance is attached to local evaluation artifacts.'
        : 'Benchmark governance remains local-only until a benchmark summary is attached.',
    ].join(' '),
  }
}
