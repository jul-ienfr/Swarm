export const predictionMeteoSubprojectName = 'Météo' as const

export const predictionMeteoSubprojectManifest = {
  id: 'meteo',
  name: predictionMeteoSubprojectName,
  parent_subproject: 'prediction',
  mission:
    'Dedicated weather prediction-markets subproject for parsing temperature contracts, blending forecast providers, and preparing pricing workflows.',
  venues: ['polymarket', 'kalshi'],
  focus_assets: ['temperature', 'weather'],
  market_families: [
    'daily-high-temperature',
    'daily-low-temperature',
    'range-buckets',
    'city-date weather contracts',
  ],
  strategic_families: [
    'multi-provider-consensus',
    'forecast-vs-market mispricing',
    'historical calibration',
  ],
  trading_horizons: ['same-day', 'overnight', '1-3 day'],
  signal_classes: [
    'numerical-weather-models',
    'official-forecast-feeds',
    'historical-temperature-context',
  ],
  execution_styles: ['manual-discretionary', 'semi-systematic', 'systematic-monitoring'],
  execution_profiles: ['manual-research', 'semi-systematic', 'systematic-monitoring'],
  risk_buckets: ['forecast-drift', 'settlement-source', 'location-mismatch', 'model-dispersion'],
  excluded_families: ['politics', 'sports', 'crypto'],
} as const

export type PredictionMeteoSubprojectManifest = typeof predictionMeteoSubprojectManifest
