export const predictionCryptoSubprojectName = 'CRYPTO' as const

export const predictionCryptoSubprojectManifest = {
  id: 'crypto',
  name: predictionCryptoSubprojectName,
  parent_subproject: 'prediction',
  mission:
    'Dedicated crypto prediction-markets subproject for market selection, research, execution patterns, and operator workflows.',
  venues: ['polymarket', 'kalshi'],
  focus_assets: ['BTC', 'ETH', 'SOL', 'XRP', 'HYPE'],
  market_families: [
    'short-horizon up-down',
    'date-bounded price targets',
    'range buckets',
    'expiry-harvest',
    'cross-venue crypto dislocations',
  ],
  strategic_families: [
    'directional-momentum',
    'volatility-and-range',
    'event-driven-catalyst',
    'relative-value-and-dislocation',
    'carry-and-structure',
  ],
  trading_horizons: ['intraday', 'multi-day', 'event-window', 'monthly-expiry'],
  signal_classes: [
    'price-action',
    'volatility-regime',
    'basis-and-spread',
    'flow-and-positioning',
    'catalyst-and-governance',
  ],
  execution_styles: ['manual-discretionary', 'semi-systematic', 'systematic-monitoring'],
  execution_profiles: ['manual-research', 'semi-systematic', 'systematic-monitoring'],
  risk_buckets: ['defined-risk', 'convex-long-vol', 'carry-harvest', 'basis-risk', 'headline-risk'],
  excluded_families: ['politics', 'sports', 'culture', 'weather'],
} as const

export type PredictionCryptoSubprojectManifest = typeof predictionCryptoSubprojectManifest
