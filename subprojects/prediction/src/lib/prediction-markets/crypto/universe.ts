export const predictionCryptoVenues = ['polymarket', 'kalshi'] as const
export type PredictionCryptoVenue = (typeof predictionCryptoVenues)[number]

export const predictionCryptoAssetUniverse = ['BTC', 'ETH', 'SOL', 'XRP', 'HYPE'] as const
export type PredictionCryptoAsset = (typeof predictionCryptoAssetUniverse)[number]

export const predictionCryptoMarketArchetypes = [
  'short-horizon up-down',
  'date-bounded price targets',
  'range buckets',
  'expiry-harvest',
  'cross-venue crypto dislocations',
] as const
export type PredictionCryptoMarketArchetype = (typeof predictionCryptoMarketArchetypes)[number]

export const predictionCryptoStrategicFamilies = [
  'directional-momentum',
  'volatility-and-range',
  'event-driven-catalyst',
  'relative-value-and-dislocation',
  'carry-and-structure',
] as const
export type PredictionCryptoStrategicFamily = (typeof predictionCryptoStrategicFamilies)[number]

export const predictionCryptoTradingHorizons = [
  'intraday',
  'multi-day',
  'event-window',
  'monthly-expiry',
] as const
export type PredictionCryptoTradingHorizon = (typeof predictionCryptoTradingHorizons)[number]

export const predictionCryptoSignalClasses = [
  'price-action',
  'volatility-regime',
  'basis-and-spread',
  'flow-and-positioning',
  'catalyst-and-governance',
] as const
export type PredictionCryptoSignalClass = (typeof predictionCryptoSignalClasses)[number]

export const predictionCryptoExecutionStyles = [
  'manual-discretionary',
  'semi-systematic',
  'systematic-monitoring',
] as const
export type PredictionCryptoExecutionStyle = (typeof predictionCryptoExecutionStyles)[number]

export const predictionCryptoExecutionProfiles = [
  'manual-research',
  'semi-systematic',
  'systematic-monitoring',
] as const
export type PredictionCryptoExecutionProfile = (typeof predictionCryptoExecutionProfiles)[number]

export const predictionCryptoRiskBuckets = [
  'defined-risk',
  'convex-long-vol',
  'carry-harvest',
  'basis-risk',
  'headline-risk',
] as const
export type PredictionCryptoRiskBucket = (typeof predictionCryptoRiskBuckets)[number]

export interface PredictionCryptoArchetypeDescriptor {
  strategic_family: PredictionCryptoStrategicFamily
  primary_horizon: PredictionCryptoTradingHorizon
  primary_signal_class: PredictionCryptoSignalClass
  execution_style: PredictionCryptoExecutionStyle
  risk_bucket: PredictionCryptoRiskBucket
  summary: string
}

export const predictionCryptoArchetypeDescriptors: Readonly<
  Record<PredictionCryptoMarketArchetype, PredictionCryptoArchetypeDescriptor>
> = {
  'short-horizon up-down': {
    strategic_family: 'directional-momentum',
    primary_horizon: 'intraday',
    primary_signal_class: 'price-action',
    execution_style: 'semi-systematic',
    risk_bucket: 'defined-risk',
    summary: 'Binary direction trades around short-horizon price continuation or reversal setups.',
  },
  'date-bounded price targets': {
    strategic_family: 'event-driven-catalyst',
    primary_horizon: 'monthly-expiry',
    primary_signal_class: 'catalyst-and-governance',
    execution_style: 'manual-discretionary',
    risk_bucket: 'headline-risk',
    summary: 'Strike-based forecasts anchored to expiry dates, catalysts, and macro narrative windows.',
  },
  'range buckets': {
    strategic_family: 'volatility-and-range',
    primary_horizon: 'multi-day',
    primary_signal_class: 'volatility-regime',
    execution_style: 'semi-systematic',
    risk_bucket: 'convex-long-vol',
    summary: 'Bucketed distribution views around realized range, vol compression, and breakout risk.',
  },
  'expiry-harvest': {
    strategic_family: 'carry-and-structure',
    primary_horizon: 'monthly-expiry',
    primary_signal_class: 'flow-and-positioning',
    execution_style: 'systematic-monitoring',
    risk_bucket: 'carry-harvest',
    summary: 'Structured harvesting of expiry decay and stale pricing into settlement.',
  },
  'cross-venue crypto dislocations': {
    strategic_family: 'relative-value-and-dislocation',
    primary_horizon: 'event-window',
    primary_signal_class: 'basis-and-spread',
    execution_style: 'systematic-monitoring',
    risk_bucket: 'basis-risk',
    summary: 'Relative-value setups created by mismatched pricing, timing, or settlement assumptions across venues.',
  },
} as const

export function isPredictionCryptoVenue(value: string): value is PredictionCryptoVenue {
  return predictionCryptoVenues.includes(value as PredictionCryptoVenue)
}

export function isPredictionCryptoAsset(value: string): value is PredictionCryptoAsset {
  return predictionCryptoAssetUniverse.includes(value as PredictionCryptoAsset)
}

export function isPredictionCryptoMarketArchetype(value: string): value is PredictionCryptoMarketArchetype {
  return predictionCryptoMarketArchetypes.includes(value as PredictionCryptoMarketArchetype)
}

export function isPredictionCryptoStrategicFamily(value: string): value is PredictionCryptoStrategicFamily {
  return predictionCryptoStrategicFamilies.includes(value as PredictionCryptoStrategicFamily)
}

export function isPredictionCryptoTradingHorizon(value: string): value is PredictionCryptoTradingHorizon {
  return predictionCryptoTradingHorizons.includes(value as PredictionCryptoTradingHorizon)
}

export function isPredictionCryptoSignalClass(value: string): value is PredictionCryptoSignalClass {
  return predictionCryptoSignalClasses.includes(value as PredictionCryptoSignalClass)
}

export function isPredictionCryptoExecutionStyle(value: string): value is PredictionCryptoExecutionStyle {
  return predictionCryptoExecutionStyles.includes(value as PredictionCryptoExecutionStyle)
}

export function isPredictionCryptoExecutionProfile(value: string): value is PredictionCryptoExecutionProfile {
  return predictionCryptoExecutionProfiles.includes(value as PredictionCryptoExecutionProfile)
}

export function isPredictionCryptoRiskBucket(value: string): value is PredictionCryptoRiskBucket {
  return predictionCryptoRiskBuckets.includes(value as PredictionCryptoRiskBucket)
}

export function getPredictionCryptoArchetypeDescriptor(
  archetype: PredictionCryptoMarketArchetype,
): PredictionCryptoArchetypeDescriptor {
  return predictionCryptoArchetypeDescriptors[archetype]
}
