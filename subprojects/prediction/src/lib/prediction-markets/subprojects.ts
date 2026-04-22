import type { PredictionMarketVenueId } from '@/lib/prediction-markets/venue-ops'
import { predictionCryptoSubprojectManifest } from '@/lib/prediction-markets/crypto/manifest'
import { predictionCryptoMarketSeeds, predictionCryptoPlaybookSeeds, predictionCryptoScope } from '@/lib/prediction-markets/crypto/market-spec'
import { predictionSportSubprojectManifest } from '@/lib/prediction-markets/sport/manifest'
import { predictionSportMarketSeeds, predictionSportScope } from '@/lib/prediction-markets/sport/market-spec'
import { predictionMeteoSubprojectManifest } from '@/lib/prediction-markets/meteo/manifest'

export type PredictionMarketSubprojectSnapshot = {
  id: string
  name: string
  parent_subproject: 'prediction'
  mission: string
  venue_supported: boolean
  venues: PredictionMarketVenueId[]
  focus: string[]
  market_families: string[]
  seeded_markets_total: number
  seeded_markets_for_venue: number
  seeded_playbooks_total: number
  execution_profiles: string[]
  summary: string
}

function countForVenue<T extends { venue: PredictionMarketVenueId }>(
  items: readonly T[],
  venue: PredictionMarketVenueId,
): number {
  return items.filter((item) => item.venue === venue).length
}

export function listPredictionMarketSubprojects(
  venue?: PredictionMarketVenueId,
): PredictionMarketSubprojectSnapshot[] {
  const cryptoVenue = venue ?? predictionCryptoScope.venues[0]
  const sportVenue = venue ?? predictionSportScope.venues[0]
  const meteoVenue = venue ?? predictionMeteoSubprojectManifest.venues[0]

  return [
    {
      id: predictionCryptoSubprojectManifest.id,
      name: predictionCryptoSubprojectManifest.name,
      parent_subproject: predictionCryptoSubprojectManifest.parent_subproject,
      mission: predictionCryptoSubprojectManifest.mission,
      venue_supported: predictionCryptoSubprojectManifest.venues.includes(cryptoVenue),
      venues: [...predictionCryptoSubprojectManifest.venues],
      focus: [...predictionCryptoScope.assets],
      market_families: [...predictionCryptoSubprojectManifest.market_families],
      seeded_markets_total: predictionCryptoMarketSeeds.length,
      seeded_markets_for_venue: countForVenue(predictionCryptoMarketSeeds, cryptoVenue),
      seeded_playbooks_total: predictionCryptoPlaybookSeeds.length,
      execution_profiles: [...predictionCryptoScope.execution_profiles],
      summary: `CRYPTO covers ${predictionCryptoScope.assets.length} focus assets across ${predictionCryptoMarketSeeds.length} seeded market maps and ${predictionCryptoPlaybookSeeds.length} playbooks.`,
    },
    {
      id: predictionSportSubprojectManifest.id,
      name: predictionSportSubprojectManifest.name,
      parent_subproject: predictionSportSubprojectManifest.parent_subproject,
      mission: predictionSportSubprojectManifest.mission,
      venue_supported: predictionSportSubprojectManifest.venues.includes(sportVenue),
      venues: [...predictionSportSubprojectManifest.venues],
      focus: [...predictionSportScope.sports],
      market_families: [...predictionSportSubprojectManifest.market_families],
      seeded_markets_total: predictionSportMarketSeeds.length,
      seeded_markets_for_venue: countForVenue(predictionSportMarketSeeds, sportVenue),
      seeded_playbooks_total: 0,
      execution_profiles: Array.from(new Set(predictionSportMarketSeeds.map((seed) => seed.execution_profile))),
      summary: `Sport covers ${predictionSportScope.sports.length} sports across ${predictionSportMarketSeeds.length} seeded venue maps focused on matchup clusters, totals, and live execution patterns.`,
    },
    {
      id: predictionMeteoSubprojectManifest.id,
      name: predictionMeteoSubprojectManifest.name,
      parent_subproject: predictionMeteoSubprojectManifest.parent_subproject,
      mission: predictionMeteoSubprojectManifest.mission,
      venue_supported: predictionMeteoSubprojectManifest.venues.includes(meteoVenue),
      venues: [...predictionMeteoSubprojectManifest.venues],
      focus: [...predictionMeteoSubprojectManifest.focus_assets],
      market_families: [...predictionMeteoSubprojectManifest.market_families],
      seeded_markets_total: 0,
      seeded_markets_for_venue: 0,
      seeded_playbooks_total: 0,
      execution_profiles: [...predictionMeteoSubprojectManifest.execution_profiles],
      summary: 'Météo covers discrete weather contracts with multi-provider forecast aggregation, pricing, and future settlement-aware execution hooks.',
    },
  ]
}
