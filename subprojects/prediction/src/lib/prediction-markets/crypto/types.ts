import { predictionCryptoSubprojectName } from './manifest'
import {
  type PredictionCryptoAsset,
  type PredictionCryptoExecutionProfile,
  type PredictionCryptoExecutionStyle,
  type PredictionCryptoMarketArchetype,
  type PredictionCryptoRiskBucket,
  type PredictionCryptoSignalClass,
  type PredictionCryptoStrategicFamily,
  type PredictionCryptoTradingHorizon,
  type PredictionCryptoVenue,
} from './universe'

export type PredictionCryptoSubprojectId = 'crypto'

export interface PredictionCryptoPlaybookSpec {
  id: string
  title: string
  slug: string
  strategic_family: PredictionCryptoStrategicFamily
  primary_horizon: PredictionCryptoTradingHorizon
  signal_classes: readonly PredictionCryptoSignalClass[]
  execution_style: PredictionCryptoExecutionStyle
  execution_profile: PredictionCryptoExecutionProfile
  risk_bucket: PredictionCryptoRiskBucket
  preferred_venues: readonly PredictionCryptoVenue[]
  focus_assets: readonly PredictionCryptoAsset[]
  archetypes: readonly PredictionCryptoMarketArchetype[]
  thesis: string
  operator_focus: string
  tags: readonly string[]
}

export interface PredictionCryptoMarketSpec {
  id: string
  playbook_id: PredictionCryptoPlaybookSpec['id']
  venue: PredictionCryptoVenue
  base_asset: PredictionCryptoAsset
  archetype: PredictionCryptoMarketArchetype
  strategic_family: PredictionCryptoStrategicFamily
  primary_horizon: PredictionCryptoTradingHorizon
  signal_class: PredictionCryptoSignalClass
  execution_style: PredictionCryptoExecutionStyle
  execution_profile: PredictionCryptoExecutionProfile
  risk_bucket: PredictionCryptoRiskBucket
  label: string
  thesis: string
}

export interface PredictionCryptoScope {
  id: PredictionCryptoSubprojectId
  name: typeof predictionCryptoSubprojectName
  venues: readonly PredictionCryptoVenue[]
  assets: readonly PredictionCryptoAsset[]
  archetypes: readonly PredictionCryptoMarketArchetype[]
  strategic_families: readonly PredictionCryptoStrategicFamily[]
  trading_horizons: readonly PredictionCryptoTradingHorizon[]
  signal_classes: readonly PredictionCryptoSignalClass[]
  execution_styles: readonly PredictionCryptoExecutionStyle[]
  execution_profiles: readonly PredictionCryptoExecutionProfile[]
  risk_buckets: readonly PredictionCryptoRiskBucket[]
}
