export const predictionSportSubprojectName = 'Sport' as const

export const predictionSportSubprojectManifest = {
  id: 'sport',
  name: predictionSportSubprojectName,
  parent_subproject: 'prediction',
  mission:
    'Dedicated sport prediction-markets subproject for matchup research, market clustering, live monitoring, and execution workflows.',
  venues: ['polymarket', 'kalshi'],
  market_families: [
    'moneyline and yes-no',
    'totals and player thresholds',
    'spread and handicap',
    'live microstructure dislocations',
    'cross-market match clusters',
  ],
} as const

export type PredictionSportSubprojectManifest = typeof predictionSportSubprojectManifest
