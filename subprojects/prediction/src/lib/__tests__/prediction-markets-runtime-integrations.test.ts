import { describe, expect, it } from 'vitest'
import { getPolymarketOperatorSidecarSurface } from '@/lib/prediction-markets/polymarket-operator-sidecars'
import {
  adaptHack23CiaPacket,
  adaptOpenCivicDatasetPacket,
  adaptWorldMonitorPacket,
  adaptWorldOsintPacket,
} from '@/lib/prediction-markets/research-adapters'
import { buildPredictionMarketForecastGovernanceArtifact } from '@/lib/prediction-markets/forecast-governance'
import { buildPredictionMarketCopReadModel } from '@/lib/prediction-markets/cop-read-models'
import { buildPredictionMarketWatchlistAudit } from '@/lib/prediction-markets/watchlist-audit'

describe('prediction markets runtime integration surfaces', () => {
  it('exposes operator sidecars as read-only runtime surfaces', () => {
    const surface = getPolymarketOperatorSidecarSurface()

    expect(surface.read_only).toBe(true)
    expect(surface.order_readback_parity.canonical_gate).toBe('execution_projection')
    expect(surface.wrappers.map((wrapper) => wrapper.profile_id)).toEqual(
      expect.arrayContaining(['tremor', 'polymarket-mcp', 'polymarket-mcp-analytics']),
    )
  })

  it('normalizes concrete P1-A research adapters into signal packets', () => {
    const worldosint = adaptWorldOsintPacket({ title: 'Signal', summary: 'Alert', url: 'https://worldosint.com/foo' })
    const worldmonitor = adaptWorldMonitorPacket({ title: 'Signal', summary: 'Discovery' })
    const cia = adaptHack23CiaPacket({ title: 'Context', summary: 'Political context' })
    const civic = adaptOpenCivicDatasetPacket({ title: 'Dataset', summary: 'Public evidence' })

    expect(worldosint.signals[0]).toMatchObject({ kind: 'alert', source_name: 'WorldOSINT' })
    expect(worldmonitor.signals[0]).toMatchObject({ kind: 'worldmonitor', source_name: 'worldmonitor.app' })
    expect(cia.signals[0]).toMatchObject({ kind: 'news', source_name: 'Hack23/cia' })
    expect(civic.signals[0]).toMatchObject({ kind: 'news', source_name: 'codeforamerica/open-civic-datasets' })
  })

  it('builds additive governance, COP, and watchlist artifacts', () => {
    const governance = buildPredictionMarketForecastGovernanceArtifact({
      operator_thesis_present: true,
      research_pipeline_trace_present: true,
      benchmark_summary: 'benchmark ready',
    })
    const cop = buildPredictionMarketCopReadModel()
    const watchlist = buildPredictionMarketWatchlistAudit()

    expect(governance.read_only).toBe(true)
    expect(governance.summary).toContain('P1-B runtime summary')
    expect(cop.summary).toContain('P1-C runtime summary')
    expect(watchlist.diff_only_entries).toHaveLength(3)
    expect(watchlist.discovery_backlog).toHaveLength(2)
  })
})
