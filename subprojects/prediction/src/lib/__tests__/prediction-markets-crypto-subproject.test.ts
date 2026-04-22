import { describe, expect, it } from 'vitest'

import {
  getPredictionCryptoArchetypeDescriptor,
  getPredictionCryptoPlaybookById,
  isPredictionCryptoAsset,
  isPredictionCryptoExecutionProfile,
  isPredictionCryptoExecutionStyle,
  isPredictionCryptoMarketArchetype,
  isPredictionCryptoRiskBucket,
  isPredictionCryptoSignalClass,
  isPredictionCryptoStrategicFamily,
  isPredictionCryptoTradingHorizon,
  isPredictionCryptoVenue,
  listPredictionCryptoMarketSeedsByFamily,
  listPredictionCryptoPlaybooksForAsset,
  predictionCryptoArchetypeDescriptors,
  predictionCryptoAssetUniverse,
  predictionCryptoExecutionProfiles,
  predictionCryptoExecutionStyles,
  predictionCryptoMarketArchetypes,
  predictionCryptoMarketSeeds,
  predictionCryptoPlaybookSeeds,
  predictionCryptoRiskBuckets,
  predictionCryptoScope,
  predictionCryptoSignalClasses,
  predictionCryptoStrategicFamilies,
  predictionCryptoSubprojectManifest,
  predictionCryptoSubprojectName,
  predictionCryptoTradingHorizons,
  predictionCryptoVenues,
} from '@/lib/prediction-markets/crypto'

describe('prediction CRYPTO subproject taxonomy', () => {
  it('uses CRYPTO as the canonical product name', () => {
    expect(predictionCryptoSubprojectName).toBe('CRYPTO')
    expect(predictionCryptoSubprojectManifest.name).toBe('CRYPTO')
    expect(predictionCryptoSubprojectManifest.parent_subproject).toBe('prediction')
  })

  it('keeps a crypto-only scope with expanded taxonomy dimensions', () => {
    expect(predictionCryptoVenues).toEqual(['polymarket', 'kalshi'])
    expect(predictionCryptoAssetUniverse).toEqual(['BTC', 'ETH', 'SOL', 'XRP', 'HYPE'])
    expect(predictionCryptoMarketArchetypes).toContain('range buckets')
    expect(predictionCryptoMarketArchetypes).toContain('expiry-harvest')
    expect(predictionCryptoStrategicFamilies).toContain('relative-value-and-dislocation')
    expect(predictionCryptoTradingHorizons).toContain('monthly-expiry')
    expect(predictionCryptoSignalClasses).toContain('basis-and-spread')
    expect(predictionCryptoExecutionStyles).toContain('manual-discretionary')
    expect(predictionCryptoRiskBuckets).toContain('headline-risk')
    expect(predictionCryptoSubprojectManifest.excluded_families).toContain('sports')
    expect(predictionCryptoScope.id).toBe('crypto')
    expect(predictionCryptoScope.name).toBe('CRYPTO')
    expect(predictionCryptoScope.strategic_families).toEqual(predictionCryptoStrategicFamilies)
    expect(predictionCryptoScope.trading_horizons).toEqual(predictionCryptoTradingHorizons)
    expect(predictionCryptoScope.signal_classes).toEqual(predictionCryptoSignalClasses)
    expect(predictionCryptoScope.execution_styles).toEqual(predictionCryptoExecutionStyles)
    expect(predictionCryptoScope.risk_buckets).toEqual(predictionCryptoRiskBuckets)
  })

  it('provides seeded playbooks and market specs for the dedicated crypto lane', () => {
    expect(predictionCryptoPlaybookSeeds).toHaveLength(4)
    expect(predictionCryptoPlaybookSeeds.map((playbook) => playbook.id)).toContain('cross-venue-dislocation-watch')
    expect(predictionCryptoMarketSeeds).toHaveLength(4)
    expect(predictionCryptoMarketSeeds[0]?.label).toBe('BTC monthly strike map')
    expect(predictionCryptoMarketSeeds.map((seed) => seed.archetype)).toContain('range buckets')
    expect(predictionCryptoMarketSeeds.map((seed) => seed.archetype)).toContain('expiry-harvest')
    expect(predictionCryptoMarketSeeds.map((seed) => seed.venue)).toContain('kalshi')

  })

  it('exposes reusable guards and lookup helpers', () => {
    expect(isPredictionCryptoVenue('polymarket')).toBe(true)
    expect(isPredictionCryptoVenue('manifold')).toBe(false)
    expect(isPredictionCryptoAsset('BTC')).toBe(true)
    expect(isPredictionCryptoAsset('DOGE')).toBe(false)
    expect(isPredictionCryptoMarketArchetype('range buckets')).toBe(true)
    expect(isPredictionCryptoStrategicFamily('carry-and-structure')).toBe(true)
    expect(isPredictionCryptoTradingHorizon('event-window')).toBe(true)
    expect(isPredictionCryptoSignalClass('price-action')).toBe(true)
    expect(isPredictionCryptoExecutionStyle('manual-discretionary')).toBe(true)
    expect(isPredictionCryptoRiskBucket('basis-risk')).toBe(true)
    expect(isPredictionCryptoExecutionProfile('systematic-monitoring')).toBe(true)
    expect(predictionCryptoExecutionProfiles).toEqual([
      'manual-research',
      'semi-systematic',
      'systematic-monitoring',
    ])

    expect(getPredictionCryptoPlaybookById('cross-venue-dislocation-watch')?.risk_bucket).toBe('basis-risk')
    expect(listPredictionCryptoPlaybooksForAsset('ETH').map((playbook) => playbook.id)).toEqual([
      'btc-strike-catalyst-ladder',
      'cross-venue-dislocation-watch',
      'expiry-structure-harvest',
    ])
    expect(listPredictionCryptoMarketSeedsByFamily('relative-value-and-dislocation')).toEqual([
      predictionCryptoMarketSeeds[2],
    ])
  })

  it('keeps deterministic archetype descriptors aligned with market seeds', () => {
    expect(Object.keys(predictionCryptoArchetypeDescriptors)).toEqual(predictionCryptoMarketArchetypes)

    const dislocationDescriptor = getPredictionCryptoArchetypeDescriptor('cross-venue crypto dislocations')
    expect(dislocationDescriptor).toMatchObject({
      strategic_family: 'relative-value-and-dislocation',
      primary_horizon: 'event-window',
      primary_signal_class: 'basis-and-spread',
      execution_style: 'systematic-monitoring',
      risk_bucket: 'basis-risk',
    })

    for (const seed of predictionCryptoMarketSeeds) {
      const descriptor = getPredictionCryptoArchetypeDescriptor(seed.archetype)
      expect(seed.strategic_family).toBe(descriptor.strategic_family)
      expect(seed.primary_horizon).toBe(descriptor.primary_horizon)
      expect(seed.signal_class).toBe(descriptor.primary_signal_class)
      expect(seed.execution_style).toBe(descriptor.execution_style)
      expect(seed.risk_bucket).toBe(descriptor.risk_bucket)
    }
  })
})
