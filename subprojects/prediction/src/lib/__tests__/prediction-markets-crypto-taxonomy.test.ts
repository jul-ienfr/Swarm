import { describe, expect, it } from 'vitest'

import {
  getPredictionCryptoArchetypeDescriptor,
  getPredictionCryptoPlaybookById,
  listPredictionCryptoMarketSeedsByFamily,
  listPredictionCryptoPlaybooksForAsset,
  predictionCryptoMarketSeeds,
  predictionCryptoPlaybookSeeds,
} from '@/lib/prediction-markets/crypto'

describe('prediction CRYPTO taxonomy helpers', () => {
  it('maps each playbook to coherent seeded markets and assets', () => {
    for (const marketSeed of predictionCryptoMarketSeeds) {
      const playbook = getPredictionCryptoPlaybookById(marketSeed.playbook_id)

      expect(playbook).toBeDefined()
      expect(playbook?.focus_assets).toContain(marketSeed.base_asset)
      expect(playbook?.archetypes).toContain(marketSeed.archetype)
      expect(playbook?.strategic_family).toBe(marketSeed.strategic_family)
      expect(playbook?.risk_bucket).toBe(marketSeed.risk_bucket)
    }
  })

  it('keeps asset and family helper queries deterministic', () => {
    expect(listPredictionCryptoPlaybooksForAsset('SOL')).toEqual([predictionCryptoPlaybookSeeds[1], predictionCryptoPlaybookSeeds[2]])
    expect(listPredictionCryptoPlaybooksForAsset('HYPE')).toEqual([predictionCryptoPlaybookSeeds[3]])
    expect(listPredictionCryptoMarketSeedsByFamily('carry-and-structure')).toEqual([predictionCryptoMarketSeeds[3]])
    expect(listPredictionCryptoMarketSeedsByFamily('event-driven-catalyst')).toEqual([predictionCryptoMarketSeeds[0]])
  })

  it('provides operator summaries for every archetype descriptor', () => {
    for (const seed of predictionCryptoMarketSeeds) {
      const descriptor = getPredictionCryptoArchetypeDescriptor(seed.archetype)
      expect(descriptor.summary.length).toBeGreaterThan(20)
    }
  })
})
