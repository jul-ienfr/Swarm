import { describe, expect, it } from 'vitest'
import {
  getPredictionMarketP0ARuntimeSummary,
  getPredictionMarketP1ARuntimeSummary,
  getPredictionMarketP1BRuntimeSummary,
  getPredictionMarketP1CRuntimeSummary,
  getPredictionMarketP2BRuntimeSummary,
  getPredictionMarketP2CRuntimeSummary,
} from '@/lib/prediction-markets/external-runtime'

describe('prediction markets external runtime summaries', () => {
  it('builds a stable P0-A runtime summary', () => {
    const summary = getPredictionMarketP0ARuntimeSummary()

    expect(summary.batch).toBe('P0-A')
    expect(summary.active_profile_ids).toEqual(expect.arrayContaining(['polymarket-clob-client', 'polymarket-py-clob-client']))
    expect(summary.integration.profile_ids).toEqual(expect.arrayContaining(['polymarket-clob-client', 'polymarket-py-clob-client', 'tremor']))
  })

  it('tracks active P1-A discovery profiles from matched research sources', () => {
    const summary = getPredictionMarketP1ARuntimeSummary({
      external_profile_ids: ['worldmonitor-app', 'hack23-cia', 'geomapdata-cn'],
    })

    expect(summary.batch).toBe('P1-A')
    expect(summary.active_profile_ids).toEqual(expect.arrayContaining(['worldmonitor-app', 'hack23-cia']))
    expect(summary.active_profile_ids).not.toContain('geomapdata-cn')
  })

  it('tracks governance/runtime batches without opening new canonical paths', () => {
    const p1b = getPredictionMarketP1BRuntimeSummary({
      operator_thesis_present: true,
      research_pipeline_trace_present: true,
    })
    const p1c = getPredictionMarketP1CRuntimeSummary({ geo_context_present: true })
    const p2b = getPredictionMarketP2BRuntimeSummary()
    const p2c = getPredictionMarketP2CRuntimeSummary()

    expect(p1b.integration.profile_ids).toEqual(expect.arrayContaining(['mirofish', 'views-platform', 'views-pipeline', 'socialpredict', 'mscft']))
    expect(p1c.integration.profile_ids).toEqual(expect.arrayContaining(['misp-dashboard', 'cloudtak', 'freetak', 'esri-dsa']))
    expect(p2b.watchlist_profile_ids).toEqual(expect.arrayContaining(['sjkncs-worldmonitor', 'sjkncs-worldmonitor-enhanced', 'worldmonitor-pro']))
    expect(p2c.configured_profile_ids).toEqual(expect.arrayContaining(['doctorfree-osint', 'awesome-intelligence']))
  })
})
