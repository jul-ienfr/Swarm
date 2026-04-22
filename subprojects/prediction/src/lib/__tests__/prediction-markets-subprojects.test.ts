import { describe, expect, it } from 'vitest'

import { listPredictionMarketSubprojects } from '@/lib/prediction-markets/subprojects'

describe('prediction market subproject registry', () => {
  it('exposes canonical crypto, sport, and meteo snapshots for polymarket', () => {
    const subprojects = listPredictionMarketSubprojects('polymarket')

    expect(subprojects.map((subproject) => subproject.id)).toEqual(['crypto', 'sport', 'meteo'])

    expect(subprojects.find((subproject) => subproject.id === 'crypto')).toMatchObject({
      name: 'CRYPTO',
      venue_supported: true,
      seeded_markets_total: 4,
      seeded_markets_for_venue: 3,
      seeded_playbooks_total: 4,
      focus: ['BTC', 'ETH', 'SOL', 'XRP', 'HYPE'],
    })

    expect(subprojects.find((subproject) => subproject.id === 'sport')).toMatchObject({
      name: 'Sport',
      venue_supported: true,
      seeded_markets_total: 4,
      seeded_markets_for_venue: 3,
      seeded_playbooks_total: 0,
      focus: ['football', 'basketball', 'tennis', 'combat'],
      execution_profiles: ['semi-systematic', 'live-monitoring', 'manual-research'],
    })

    expect(subprojects.find((subproject) => subproject.id === 'meteo')).toMatchObject({
      name: 'Météo',
      venue_supported: true,
      seeded_markets_total: 0,
      seeded_markets_for_venue: 0,
      seeded_playbooks_total: 0,
      focus: ['temperature', 'weather'],
      execution_profiles: ['manual-research', 'semi-systematic', 'systematic-monitoring'],
    })
  })

  it('marks unsupported venues deterministically', () => {
    const subprojects = listPredictionMarketSubprojects('manifold' as never)

    expect(subprojects.every((subproject) => subproject.venue_supported === false)).toBe(true)
  })
})
