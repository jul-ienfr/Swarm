import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  buildMeteoBestBetsSummary,
  buildMeteoForecastConsensus,
  buildMeteoForecastPointsFromProviders,
  buildMeteoPricingReport,
  buildMeteoPricingReportFromProviders,
  clearMeteoProviderCache,
  fetchJsonWithMeteoProviderCache,
  fetchMeteostatHistoricalPoint,
  fetchNwsForecastPoint,
  fetchOpenMeteoForecastPoint,
  normalizeMeteostatDailyPayload,
  normalizeNwsTemperaturePayload,
  normalizeOpenMeteoTemperaturePayload,
  parseMeteoQuestion,
} from '@/lib/prediction-markets/meteo'

describe('prediction markets meteo', () => {
  beforeEach(() => {
    clearMeteoProviderCache()
  })

  it('parses a weather market question into a normalized meteo spec', () => {
    const spec = parseMeteoQuestion('What will the highest temperature in Los Angeles, CA on Apr 21, 2026 be: 66F-67F, 68F-69F, or 70F+?')

    expect(spec.city).toBe('Los Angeles')
    expect(spec.countryOrRegion).toBe('CA')
    expect(spec.marketDate).toBe('Apr 21, 2026')
    expect(spec.kind).toBe('high')
    expect(spec.unit).toBe('f')
    expect(spec.bins.map((bin) => bin.label)).toEqual(['66-67F', '68-69F', '70+F'])
  })

  it('normalizes open-meteo daily payloads into forecast points', () => {
    const point = normalizeOpenMeteoTemperaturePayload({
      kind: 'high',
      payload: {
        model: 'gfs',
        daily: {
          temperature_2m_max: [69.2, 68.7, 70.1],
        },
        daily_units: {
          temperature_2m_max: '°F',
        },
      },
      weight: 0.6,
    })

    expect(point.provider).toBe('open-meteo:gfs')
    expect(point.mean).toBe(69.2)
    expect(point.weight).toBe(0.6)
    expect(point.stddev).toBeGreaterThan(0.7)
  })

  it('normalizes nws periods into forecast points', () => {
    const point = normalizeNwsTemperaturePayload({
      kind: 'high',
      payload: {
        provider: 'nws',
        periods: [
          { name: 'Tonight', isDaytime: false, temperature: 51, temperatureUnit: 'F' },
          { name: 'Tuesday', isDaytime: true, temperature: 68, temperatureUnit: 'F' },
        ],
      },
      weight: 0.4,
    })

    expect(point.provider).toBe('nws')
    expect(point.mean).toBe(68)
    expect(point.stddev).toBe(1.8)
    expect(point.weight).toBe(0.4)
  })

  it('normalizes meteostat daily payloads into historical points', () => {
    const point = normalizeMeteostatDailyPayload({
      kind: 'high',
      payload: {
        meta: { units: 'imperial' },
        data: [
          { date: '2026-04-20', tavg: 68.2, tmin: 61.1, tmax: 73.9 },
        ],
      },
      weight: 0.25,
      sourceLabel: 'meteostat:historical',
    })

    expect(point.provider).toBe('meteostat:historical')
    expect(point.mean).toBe(73.9)
    expect(point.weight).toBe(0.25)
    expect(point.stddev).toBeGreaterThanOrEqual(1.4)
  })

  it('caches provider JSON responses', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }))

    const first = await fetchJsonWithMeteoProviderCache<{ ok: boolean }>({
      url: 'https://example.test/weather',
      fetchImpl,
      cacheTtlMs: 60_000,
    })
    const second = await fetchJsonWithMeteoProviderCache<{ ok: boolean }>({
      url: 'https://example.test/weather',
      fetchImpl,
      cacheTtlMs: 60_000,
    })

    expect(first.ok).toBe(true)
    expect(second.ok).toBe(true)
    expect(fetchImpl).toHaveBeenCalledTimes(1)
  })

  it('retries provider requests before failing', async () => {
    const fetchImpl = vi.fn()
      .mockRejectedValueOnce(new Error('temporary outage'))
      .mockResolvedValueOnce(new Response(JSON.stringify({ daily: { temperature_2m_max: [71.4, 72.1, 70.9] } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))

    const point = await fetchOpenMeteoForecastPoint({
      latitude: 40.7128,
      longitude: -74.006,
      kind: 'high',
      model: 'ecmwf',
      weight: 0.7,
      fetchImpl,
      retryCount: 1,
    })

    expect(fetchImpl).toHaveBeenCalledTimes(2)
    expect(point.provider).toBe('open-meteo:ecmwf')
    expect(point.mean).toBe(71.4)
  })

  it('fetches and normalizes open-meteo forecasts with an injected fetch', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({
      model: 'ecmwf',
      daily: {
        temperature_2m_max: [71.4, 72.1, 70.9],
      },
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))

    const point = await fetchOpenMeteoForecastPoint({
      latitude: 40.7128,
      longitude: -74.006,
      kind: 'high',
      model: 'ecmwf',
      weight: 0.7,
      fetchImpl,
    })

    expect(fetchImpl).toHaveBeenCalledTimes(1)
    expect(point.provider).toBe('open-meteo:ecmwf')
    expect(point.mean).toBe(71.4)
    expect(point.weight).toBe(0.7)
  })

  it('fetches and normalizes nws forecasts with injected fetches', async () => {
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/points/')) {
        return new Response(JSON.stringify({
          properties: {
            forecast: 'https://api.weather.gov/gridpoints/OKX/33,35/forecast',
            forecastHourly: 'https://api.weather.gov/gridpoints/OKX/33,35/forecast/hourly',
            gridId: 'OKX',
            gridX: 33,
            gridY: 35,
          },
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/geo+json' },
        })
      }

      return new Response(JSON.stringify({
        properties: {
          periods: [
            { name: 'Tonight', isDaytime: false, temperature: 59, temperatureUnit: 'F' },
            { name: 'Tuesday', isDaytime: true, temperature: 74, temperatureUnit: 'F' },
          ],
        },
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/geo+json' },
      })
    })

    const point = await fetchNwsForecastPoint({
      latitude: 40.7128,
      longitude: -74.006,
      kind: 'high',
      weight: 0.3,
      fetchImpl,
    })

    expect(fetchImpl).toHaveBeenCalledTimes(2)
    expect(String(fetchImpl.mock.calls[1]?.[0])).toContain('/forecast')
    expect(String(fetchImpl.mock.calls[1]?.[0])).not.toContain('/forecast/hourly')
    expect(point.provider).toBe('nws')
    expect(point.mean).toBe(74)
    expect(point.weight).toBe(0.3)
  })

  it('keeps raw bin probabilities for non-exhaustive temperature markets', () => {
    const spec = parseMeteoQuestion('What will the highest temperature in Los Angeles, CA on Apr 21, 2026 be: 70F+?')
    const report = buildMeteoPricingReport({
      spec,
      forecastPoints: [
        { provider: 'open-meteo:ecmwf', mean: 68.4, stddev: 1.1, weight: 1 },
      ],
      marketPrices: {
        '70+F': 0.09,
      },
    })

    expect(report.bins).toHaveLength(1)
    expect(report.bins[0]?.label).toBe('70+F')
    expect(report.bins[0]?.probability).toBeLessThan(1)
    expect(report.bins[0]?.fairYesPrice).toBe(report.bins[0]?.probability)
    expect(report.bins[0]?.fairNoPrice).toBeCloseTo(1 - (report.bins[0]?.fairYesPrice ?? 0), 4)
  })

  it('supports under bins without inflating them to 100 percent', () => {
    const spec = parseMeteoQuestion('What will the lowest temperature in Los Angeles, CA on Apr 21, 2026 be: under 60F?')
    const report = buildMeteoPricingReport({
      spec,
      forecastPoints: [
        { provider: 'open-meteo:ecmwf', mean: 57.5, stddev: 2.2, weight: 1 },
      ],
      marketPrices: {
        'under-60F': 0.62,
      },
    })

    expect(report.bins).toHaveLength(1)
    expect(report.bins[0]?.label).toBe('under-60F')
    expect(report.bins[0]?.probability).toBeLessThan(1)
    expect(report.bins[0]?.fairYesPrice).toBe(report.bins[0]?.probability)
  })

  it('normalizes daily nws periods by selecting the daytime high', () => {
    const point = normalizeNwsTemperaturePayload({
      kind: 'high',
      payload: {
        provider: 'nws',
        periods: [
          { name: 'Tonight', isDaytime: false, temperature: 51, temperatureUnit: 'F' },
          { name: 'Tuesday', isDaytime: true, temperature: 68, temperatureUnit: 'F' },
          { name: 'Tuesday Night', isDaytime: false, temperature: 49, temperatureUnit: 'F' },
        ],
      },
      weight: 0.4,
    })

    expect(point.mean).toBe(68)
  })

  it('normalizes daily nws periods by selecting the nighttime low', () => {
    const point = normalizeNwsTemperaturePayload({
      kind: 'low',
      payload: {
        provider: 'nws',
        periods: [
          { name: 'Tuesday', isDaytime: true, temperature: 68, temperatureUnit: 'F' },
          { name: 'Tuesday Night', isDaytime: false, temperature: 49, temperatureUnit: 'F' },
        ],
      },
      weight: 0.4,
    })

    expect(point.mean).toBe(49)
  })

  it('prefers the daily nws forecast over forecastHourly metadata', async () => {
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/points/')) {
        return new Response(JSON.stringify({
          properties: {
            forecast: 'https://api.weather.gov/gridpoints/OKX/33,35/forecast',
            forecastHourly: 'https://api.weather.gov/gridpoints/OKX/33,35/forecast/hourly',
          },
        }), { status: 200, headers: { 'Content-Type': 'application/geo+json' } })
      }

      if (url.includes('/forecast/hourly')) {
        return new Response(JSON.stringify({
          properties: {
            periods: [
              { name: '10 AM', isDaytime: true, temperature: 70, temperatureUnit: 'F' },
            ],
          },
        }), { status: 200, headers: { 'Content-Type': 'application/geo+json' } })
      }

      return new Response(JSON.stringify({
        properties: {
          periods: [
            { name: 'Tuesday', isDaytime: true, temperature: 76, temperatureUnit: 'F' },
            { name: 'Tuesday Night', isDaytime: false, temperature: 58, temperatureUnit: 'F' },
          ],
        },
      }), { status: 200, headers: { 'Content-Type': 'application/geo+json' } })
    })

    const point = await fetchNwsForecastPoint({
      latitude: 40.7128,
      longitude: -74.006,
      kind: 'high',
      fetchImpl,
    })

    expect(point.mean).toBe(76)
    expect(String(fetchImpl.mock.calls[1]?.[0])).toContain('/forecast')
    expect(String(fetchImpl.mock.calls[1]?.[0])).not.toContain('/forecast/hourly')
  })

  it('uses hourly metadata only when daily nws forecast metadata is absent', async () => {
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/points/')) {
        return new Response(JSON.stringify({
          properties: {
            forecastHourly: 'https://api.weather.gov/gridpoints/OKX/33,35/forecast/hourly',
          },
        }), { status: 200, headers: { 'Content-Type': 'application/geo+json' } })
      }

      return new Response(JSON.stringify({
        properties: {
          periods: [
            { name: '10 AM', isDaytime: true, temperature: 70, temperatureUnit: 'F' },
          ],
        },
      }), { status: 200, headers: { 'Content-Type': 'application/geo+json' } })
    })

    const point = await fetchNwsForecastPoint({
      latitude: 40.7128,
      longitude: -74.006,
      kind: 'high',
      fetchImpl,
    })

    expect(point.mean).toBe(70)
    expect(String(fetchImpl.mock.calls[1]?.[0])).toContain('/forecast/hourly')
  })

  it('builds forecast points from multiple providers with injected fetch', async () => {
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('api.open-meteo.com')) {
        if (url.includes('models=ecmwf')) {
          return new Response(JSON.stringify({ daily: { temperature_2m_max: [71.1, 70.9, 71.6] } }), { status: 200 })
        }
        return new Response(JSON.stringify({ daily: { temperature_2m_max: [72.4, 72.1, 72.8] } }), { status: 200 })
        }
      if (url.includes('meteostat.p.rapidapi.com')) {
        return new Response(JSON.stringify({
          meta: { units: 'imperial' },
          data: [{ date: '2026-04-20', tavg: 67.8, tmin: 61.2, tmax: 73.4 }],
        }), { status: 200 })
      }
      if (url.includes('/points/')) {
        return new Response(JSON.stringify({
          properties: {
            forecastHourly: 'https://api.weather.gov/gridpoints/OKX/33,35/forecast/hourly',
          },
        }), { status: 200 })
      }
      return new Response(JSON.stringify({
        properties: {
          periods: [
            { name: 'Tonight', isDaytime: false, temperature: 61, temperatureUnit: 'F' },
            { name: 'Tuesday', isDaytime: true, temperature: 73, temperatureUnit: 'F' },
          ],
        },
      }), { status: 200 })
    })

    const points = await buildMeteoForecastPointsFromProviders({
      latitude: 40.7128,
      longitude: -74.006,
      kind: 'high',
      openMeteoModels: ['ecmwf', 'gfs'],
      includeNws: true,
      includeMeteostat: true,
      meteostatStart: '2026-04-20',
      meteostatEnd: '2026-04-22',
      meteostatApiKey: 'test-key',
      fetchImpl,
    })

    expect(points).toHaveLength(4)
    expect(points.map((point) => point.provider)).toEqual(['open-meteo:ecmwf', 'open-meteo:gfs', 'nws', 'meteostat:historical'])
  })

  it('fetches and normalizes meteostat history with injected fetch', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({
      meta: { units: 'imperial' },
      data: [{ date: '2026-04-20', tavg: 68.1, tmin: 60.4, tmax: 74.5 }],
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))

    const point = await fetchMeteostatHistoricalPoint({
      latitude: 40.7128,
      longitude: -74.006,
      start: '2026-04-20',
      end: '2026-04-22',
      kind: 'high',
      weight: 0.2,
      fetchImpl,
      apiKey: 'test-key',
    })

    expect(fetchImpl).toHaveBeenCalledTimes(1)
    expect(point.provider).toBe('meteostat:historical')
    expect(point.mean).toBe(74.5)
    expect(point.weight).toBe(0.2)
  })

  it('builds forecast points from multiple providers with injected fetch', async () => {
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('api.open-meteo.com')) {
        if (url.includes('models=ecmwf')) {
          return new Response(JSON.stringify({ daily: { temperature_2m_max: [71.1, 70.9, 71.6] } }), { status: 200 })
        }
        return new Response(JSON.stringify({ daily: { temperature_2m_max: [72.4, 72.1, 72.8] } }), { status: 200 })
      }
      if (url.includes('meteostat.p.rapidapi.com')) {
        return new Response(JSON.stringify({
          meta: { units: 'imperial' },
          data: [{ date: '2026-04-20', tavg: 67.8, tmin: 61.2, tmax: 73.4 }],
        }), { status: 200 })
      }
      if (url.includes('/points/')) {
        return new Response(JSON.stringify({
          properties: {
            forecastHourly: 'https://api.weather.gov/gridpoints/OKX/33,35/forecast/hourly',
          },
        }), { status: 200 })
      }
      return new Response(JSON.stringify({
        properties: {
          periods: [
            { name: 'Tonight', isDaytime: false, temperature: 61, temperatureUnit: 'F' },
            { name: 'Tuesday', isDaytime: true, temperature: 73, temperatureUnit: 'F' },
          ],
        },
      }), { status: 200 })
    })

    const points = await buildMeteoForecastPointsFromProviders({
      latitude: 40.7128,
      longitude: -74.006,
      kind: 'high',
      openMeteoModels: ['ecmwf', 'gfs'],
      includeNws: true,
      includeMeteostat: true,
      meteostatStart: '2026-04-20',
      meteostatEnd: '2026-04-22',
      meteostatApiKey: 'test-key',
      fetchImpl,
    })

    expect(points).toHaveLength(4)
    expect(points.map((point) => point.provider)).toEqual(['open-meteo:ecmwf', 'open-meteo:gfs', 'nws', 'meteostat:historical'])
  })

  it('builds a pricing report directly from providers', async () => {
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('api.open-meteo.com')) {
        return new Response(JSON.stringify({ daily: { temperature_2m_max: [70.8, 71.3, 70.2] } }), { status: 200 })
      }
      if (url.includes('meteostat.p.rapidapi.com')) {
        return new Response(JSON.stringify({
          meta: { units: 'imperial' },
          data: [{ date: '2026-04-20', tavg: 68.6, tmin: 60.8, tmax: 72.9 }],
        }), { status: 200 })
      }
      if (url.includes('/points/')) {
        return new Response(JSON.stringify({
          properties: {
            forecastHourly: 'https://api.weather.gov/gridpoints/OKX/33,35/forecast/hourly',
          },
        }), { status: 200 })
      }
      return new Response(JSON.stringify({
        properties: {
          periods: [
            { name: 'Tonight', isDaytime: false, temperature: 59, temperatureUnit: 'F' },
            { name: 'Tuesday', isDaytime: true, temperature: 72, temperatureUnit: 'F' },
          ],
        },
      }), { status: 200 })
    })

    const result = await buildMeteoPricingReportFromProviders({
      question: 'What will the highest temperature in New York, NY on Apr 22, 2026 be: 70F-71F, 72F-73F, or 74F+?',
      latitude: 40.7128,
      longitude: -74.006,
      openMeteoModels: ['ecmwf'],
      includeNws: true,
      includeMeteostat: true,
      meteostatStart: '2026-04-20',
      meteostatEnd: '2026-04-22',
      meteostatApiKey: 'test-key',
      fetchImpl,
      marketPrices: {
        '70-71F': 0.39,
        '72-73F': 0.31,
        '74+F': 0.11,
      },
    })

    expect(result.spec.kind).toBe('high')
    expect(result.forecastPoints).toHaveLength(3)
    expect(result.report.provenance.providerCount).toBe(3)
    expect(result.report.bins).toHaveLength(3)
    expect(result.report.marketSnapshot).toEqual({
      pricedBinCount: 3,
      yesPriceSum: 0.81,
      overround: -0.19,
    })
    expect(result.report.opportunities.length).toBeGreaterThan(0)
  })

  it('builds a stable deterministic consensus and surfaces provenance in pricing', () => {
    const spec = parseMeteoQuestion('What will the highest temperature in Los Angeles, CA on Apr 21, 2026 be: 66F-67F, 68F-69F, or 70F+?')
    const openMeteo = normalizeOpenMeteoTemperaturePayload({
      kind: 'high',
      payload: {
        model: 'ecmwf',
        daily: {
          temperature_2m_max: [69.1, 68.8, 69.4],
        },
      },
      weight: 0.55,
    })
    const nws = normalizeNwsTemperaturePayload({
      kind: 'high',
      payload: {
        provider: 'nws',
        periods: [
          { name: 'Tuesday', isDaytime: true, temperature: 68, temperatureUnit: 'F' },
        ],
      },
      weight: 0.30,
    })
    const meteostat = normalizeMeteostatDailyPayload({
      kind: 'high',
      payload: {
        meta: { units: 'imperial' },
        data: [{ date: '2026-04-20', tavg: 67.8, tmin: 60.9, tmax: 72.3 }],
      },
      weight: 0.15,
      sourceLabel: 'meteostat:historical',
    })

    const consensus = buildMeteoForecastConsensus([openMeteo, nws, meteostat])
    const report = buildMeteoPricingReport({
      spec,
      forecastPoints: [openMeteo, nws, meteostat],
      marketPrices: {
        '66-67F': 0.24,
        '68-69F': 0.41,
        '70+F': 0.18,
      },
    })

    const totalProbability = report.bins.reduce((sum, bin) => sum + bin.probability, 0)

    expect(consensus.providers).toEqual(['open-meteo:ecmwf', 'nws', 'meteostat:historical'])
    expect(consensus.totalWeight).toBe(1)
    expect(consensus.mean).toBeGreaterThan(68)
    expect(report.provenance.providerCount).toBe(3)
    expect(report.provenance.providers).toEqual(['open-meteo:ecmwf', 'nws', 'meteostat:historical'])
    expect(report.provenance.contributions).toHaveLength(3)
    expect(totalProbability).toBeLessThan(1)
    expect(report.marketSnapshot).toEqual({
      pricedBinCount: 3,
      yesPriceSum: 0.83,
      overround: -0.17,
    })

    const tailBin = report.bins.find((bin) => bin.label === '70+F')
    expect(tailBin?.edge).toBeGreaterThan(0)
    expect(tailBin?.fairNoPrice).toBeCloseTo(1 - (tailBin?.fairYesPrice ?? 0), 4)
    expect(tailBin?.marketNoPrice).toBe(0.82)
    expect(tailBin?.yesEdge).toBeGreaterThan(0)
    expect(tailBin?.noEdge).toBeLessThan(0)
    expect(tailBin?.expectedValueYes).toBe(tailBin?.yesEdge)
    expect(tailBin?.recommendedSide).toBe('yes')

    expect(report.opportunities[0]).toMatchObject({
      label: '70+F',
      side: 'yes',
    })
  })

  it('builds a best-bets summary from pricing opportunities', () => {
    const spec = parseMeteoQuestion('What will the highest temperature in Los Angeles, CA on Apr 21, 2026 be: 66F-67F, 68F-69F, or 70F+?')
    const report = buildMeteoPricingReport({
      spec,
      forecastPoints: [
        { provider: 'open-meteo:ecmwf', mean: 68.4, stddev: 1.1, weight: 1 },
      ],
      marketPrices: {
        '66-67F': 0.22,
        '68-69F': 0.67,
        '70+F': 0.09,
      },
    })

    const bestBets = buildMeteoBestBetsSummary(report, { limit: 2 })

    expect(bestBets.actionableCount).toBe(report.opportunities.length)
    expect(bestBets.strongestOpportunity).toEqual(report.opportunities[0])
    expect(bestBets.topOpportunities).toEqual(report.opportunities.slice(0, 2))
    expect(bestBets.recommendedSideCounts).toEqual({ yes: 1, no: 2, pass: 0 })
    expect(bestBets.noTradeLabels).toEqual([])
    expect(bestBets.summary).toContain('Top météo bet:')
  })
})
