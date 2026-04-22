import { predictionSportSubprojectManifest } from './manifest'

export type PredictionSportVenueId = (typeof predictionSportSubprojectManifest.venues)[number]
export type PredictionSportExecutionProfile = 'semi-systematic' | 'live-monitoring' | 'manual-research'

export type PredictionSportScope = {
  id: 'sport'
  name: typeof predictionSportSubprojectManifest.name
  venues: readonly PredictionSportVenueId[]
  sports: readonly string[]
  execution_profiles: readonly PredictionSportExecutionProfile[]
}

export type PredictionSportMarketSeed = {
  id: string
  venue: PredictionSportVenueId
  sport: string
  execution_profile: PredictionSportExecutionProfile
  label: string
}

export const predictionSportScope: PredictionSportScope = {
  id: 'sport',
  name: predictionSportSubprojectManifest.name,
  venues: predictionSportSubprojectManifest.venues,
  sports: ['football', 'basketball', 'tennis', 'combat'],
  execution_profiles: ['semi-systematic', 'live-monitoring', 'manual-research'],
}

export const predictionSportMarketSeeds: readonly PredictionSportMarketSeed[] = [
  {
    id: 'football-cluster-polymarket',
    venue: 'polymarket',
    sport: 'football',
    execution_profile: 'semi-systematic',
    label: 'Football cluster map',
  },
  {
    id: 'nba-live-kalshi',
    venue: 'kalshi',
    sport: 'basketball',
    execution_profile: 'live-monitoring',
    label: 'NBA live dislocation watch',
  },
  {
    id: 'tennis-tail-polymarket',
    venue: 'polymarket',
    sport: 'tennis',
    execution_profile: 'manual-research',
    label: 'Tennis middle-tail pricing',
  },
  {
    id: 'combat-micro-polymarket',
    venue: 'polymarket',
    sport: 'combat',
    execution_profile: 'live-monitoring',
    label: 'Combat live microstructure reversion',
  },
] as const
