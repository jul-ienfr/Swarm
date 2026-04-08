import { describe, expect, it } from 'vitest'

import { buildPredictionMarketsDashboardHtml } from '@/lib/prediction-markets/dashboard'
import { GET } from '@/app/prediction-markets/dashboard/route'

describe('prediction markets dashboard route', () => {
  it('builds the dashboard html with the configured api base and mode', () => {
    const html = buildPredictionMarketsDashboardHtml({
      apiBasePath: '/proxy/api/v1/prediction-markets',
      title: 'Prediction Markets Dashboard',
      mode: 'standalone-proxy',
    })

    expect(html).toContain('Prediction Markets Dashboard')
    expect(html).toContain('data-api-base="/proxy/api/v1/prediction-markets"')
    expect(html).toContain('data-dashboard-mode="standalone-proxy"')
    expect(html).toContain('Execution Desk')
    expect(html).toContain('Research &amp; Benchmark')
    expect(html).toContain('Strategy Engine')
    expect(html).toContain('Primary Strategy')
    expect(html).toContain('Market Regime')
    expect(html).toContain('Execution Intent Preview')
    expect(html).toContain('Cross-Venue &amp; Arbitrage')
    expect(html).toContain('Desk state')
    expect(html).toContain('Trader desk alert')
    expect(html).toContain('Reset arbitrage')
    expect(html).toContain('Venue &amp; Ops')
    expect(html).toContain('/runs/')
    expect(html).toContain('data-theme-option="dark"')
  })

  it('serves the embedded dashboard route as no-store html', async () => {
    const response = await GET(new Request('http://localhost/prediction-markets/dashboard'))
    const html = await response.text()

    expect(response.status).toBe(200)
    expect(response.headers.get('content-type')).toContain('text/html')
    expect(response.headers.get('cache-control')).toBe('no-store')
    expect(html).toContain('Prediction Markets Dashboard')
    expect(html).toContain('data-api-base="/api/v1/prediction-markets"')
    expect(html).toContain('data-dashboard-mode="embedded-app-route"')
    expect(html).toContain('Theme mode')
    expect(html).toContain('Cross-Venue &amp; Arbitrage')
    expect(html).toContain('arbitrageStatusFilter')
    expect(html).toContain('strategyFilter')
    expect(html).toContain('regimeFilter')
    expect(html).toContain('Strategy Engine')
  })
})
