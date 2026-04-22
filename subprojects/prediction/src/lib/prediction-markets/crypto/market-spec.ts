import { predictionCryptoSubprojectManifest } from './manifest'
import type { PredictionCryptoMarketSpec, PredictionCryptoPlaybookSpec, PredictionCryptoScope } from './types'
import { getPredictionCryptoArchetypeDescriptor } from './universe'

export const predictionCryptoScope: PredictionCryptoScope = {
  id: 'crypto',
  name: predictionCryptoSubprojectManifest.name,
  venues: predictionCryptoSubprojectManifest.venues,
  assets: predictionCryptoSubprojectManifest.focus_assets,
  archetypes: predictionCryptoSubprojectManifest.market_families,
  strategic_families: predictionCryptoSubprojectManifest.strategic_families,
  trading_horizons: predictionCryptoSubprojectManifest.trading_horizons,
  signal_classes: predictionCryptoSubprojectManifest.signal_classes,
  execution_styles: predictionCryptoSubprojectManifest.execution_styles,
  execution_profiles: predictionCryptoSubprojectManifest.execution_profiles,
  risk_buckets: predictionCryptoSubprojectManifest.risk_buckets,
}

export const predictionCryptoPlaybookSeeds: readonly PredictionCryptoPlaybookSpec[] = [
  {
    id: 'btc-strike-catalyst-ladder',
    title: 'BTC strike catalyst ladder',
    slug: 'btc-strike-catalyst-ladder',
    strategic_family: 'event-driven-catalyst',
    primary_horizon: 'monthly-expiry',
    signal_classes: ['catalyst-and-governance', 'price-action'],
    execution_style: 'manual-discretionary',
    execution_profile: 'manual-research',
    risk_bucket: 'headline-risk',
    preferred_venues: ['polymarket', 'kalshi'],
    focus_assets: ['BTC', 'ETH'],
    archetypes: ['date-bounded price targets'],
    thesis:
      'Map catalyst windows, macro prints, and narrative acceleration into strike ladders with explicit expiry discipline.',
    operator_focus:
      'Refresh strike grids weekly, compare implied narrative dispersion across venues, and only engage around scheduled catalysts.',
    tags: ['btc', 'eth', 'strike-map', 'macro-catalyst', 'expiry'],
  },
  {
    id: 'sol-vol-regime-buckets',
    title: 'SOL volatility regime buckets',
    slug: 'sol-vol-regime-buckets',
    strategic_family: 'volatility-and-range',
    primary_horizon: 'multi-day',
    signal_classes: ['volatility-regime', 'flow-and-positioning'],
    execution_style: 'semi-systematic',
    execution_profile: 'semi-systematic',
    risk_bucket: 'convex-long-vol',
    preferred_venues: ['polymarket'],
    focus_assets: ['SOL', 'XRP'],
    archetypes: ['range buckets', 'short-horizon up-down'],
    thesis:
      'Exploit compression-to-expansion transitions by comparing realized range against market-implied bucket spacing.',
    operator_focus:
      'Track realized volatility drift, monitor momentum exhaustion, and rotate only when buckets misprice regime change.',
    tags: ['sol', 'xrp', 'range', 'volatility', 'breakout'],
  },
  {
    id: 'cross-venue-dislocation-watch',
    title: 'Cross-venue dislocation watch',
    slug: 'cross-venue-dislocation-watch',
    strategic_family: 'relative-value-and-dislocation',
    primary_horizon: 'event-window',
    signal_classes: ['basis-and-spread', 'flow-and-positioning'],
    execution_style: 'systematic-monitoring',
    execution_profile: 'systematic-monitoring',
    risk_bucket: 'basis-risk',
    preferred_venues: ['polymarket', 'kalshi'],
    focus_assets: ['BTC', 'ETH', 'SOL'],
    archetypes: ['cross-venue crypto dislocations', 'expiry-harvest'],
    thesis:
      'Identify mismatched pricing created by venue microstructure, listing cadence, or settlement framing before convergence.',
    operator_focus:
      'Run deterministic spread comparisons, tag stale books, and escalate only when convergence path is operationally clear.',
    tags: ['cross-venue', 'spread', 'basis', 'microstructure', 'monitoring'],
  },
  {
    id: 'expiry-structure-harvest',
    title: 'Expiry structure harvest',
    slug: 'expiry-structure-harvest',
    strategic_family: 'carry-and-structure',
    primary_horizon: 'monthly-expiry',
    signal_classes: ['flow-and-positioning', 'basis-and-spread'],
    execution_style: 'systematic-monitoring',
    execution_profile: 'systematic-monitoring',
    risk_bucket: 'carry-harvest',
    preferred_venues: ['polymarket'],
    focus_assets: ['BTC', 'ETH', 'HYPE'],
    archetypes: ['expiry-harvest', 'range buckets'],
    thesis:
      'Harvest decaying event premia into expiry when settlement path is simple and liquidity remains two-sided.',
    operator_focus:
      'Prefer defined calendars, avoid binary headline clusters, and cut exposure when carry is no longer dominant.',
    tags: ['expiry', 'carry', 'settlement', 'theta', 'harvest'],
  },
] as const

export const predictionCryptoMarketSeeds: readonly PredictionCryptoMarketSpec[] = [
  {
    id: 'btc-monthly-strike-map',
    playbook_id: 'btc-strike-catalyst-ladder',
    venue: 'polymarket',
    base_asset: 'BTC',
    archetype: 'date-bounded price targets',
    strategic_family: getPredictionCryptoArchetypeDescriptor('date-bounded price targets').strategic_family,
    primary_horizon: getPredictionCryptoArchetypeDescriptor('date-bounded price targets').primary_horizon,
    signal_class: getPredictionCryptoArchetypeDescriptor('date-bounded price targets').primary_signal_class,
    execution_style: getPredictionCryptoArchetypeDescriptor('date-bounded price targets').execution_style,
    execution_profile: 'manual-research',
    risk_bucket: getPredictionCryptoArchetypeDescriptor('date-bounded price targets').risk_bucket,
    label: 'BTC monthly strike map',
    thesis: 'Express BTC catalyst views through dated strike ladders rather than open-ended spot conviction.',
  },
  {
    id: 'sol-range-bucket-monitor',
    playbook_id: 'sol-vol-regime-buckets',
    venue: 'polymarket',
    base_asset: 'SOL',
    archetype: 'range buckets',
    strategic_family: getPredictionCryptoArchetypeDescriptor('range buckets').strategic_family,
    primary_horizon: getPredictionCryptoArchetypeDescriptor('range buckets').primary_horizon,
    signal_class: getPredictionCryptoArchetypeDescriptor('range buckets').primary_signal_class,
    execution_style: getPredictionCryptoArchetypeDescriptor('range buckets').execution_style,
    execution_profile: 'semi-systematic',
    risk_bucket: getPredictionCryptoArchetypeDescriptor('range buckets').risk_bucket,
    label: 'SOL range bucket monitor',
    thesis: 'Track SOL regime shifts by comparing realized range expansion against currently listed bucket spacing.',
  },
  {
    id: 'btc-cross-venue-dislocation-watch',
    playbook_id: 'cross-venue-dislocation-watch',
    venue: 'kalshi',
    base_asset: 'BTC',
    archetype: 'cross-venue crypto dislocations',
    strategic_family: getPredictionCryptoArchetypeDescriptor('cross-venue crypto dislocations').strategic_family,
    primary_horizon: getPredictionCryptoArchetypeDescriptor('cross-venue crypto dislocations').primary_horizon,
    signal_class: getPredictionCryptoArchetypeDescriptor('cross-venue crypto dislocations').primary_signal_class,
    execution_style: getPredictionCryptoArchetypeDescriptor('cross-venue crypto dislocations').execution_style,
    execution_profile: 'systematic-monitoring',
    risk_bucket: getPredictionCryptoArchetypeDescriptor('cross-venue crypto dislocations').risk_bucket,
    label: 'BTC cross-venue dislocation watch',
    thesis: 'Continuously compare BTC event framing across venues and escalate only when settlement assumptions diverge.',
  },
  {
    id: 'eth-expiry-structure-harvest',
    playbook_id: 'expiry-structure-harvest',
    venue: 'polymarket',
    base_asset: 'ETH',
    archetype: 'expiry-harvest',
    strategic_family: getPredictionCryptoArchetypeDescriptor('expiry-harvest').strategic_family,
    primary_horizon: getPredictionCryptoArchetypeDescriptor('expiry-harvest').primary_horizon,
    signal_class: getPredictionCryptoArchetypeDescriptor('expiry-harvest').primary_signal_class,
    execution_style: getPredictionCryptoArchetypeDescriptor('expiry-harvest').execution_style,
    execution_profile: 'systematic-monitoring',
    risk_bucket: getPredictionCryptoArchetypeDescriptor('expiry-harvest').risk_bucket,
    label: 'ETH expiry structure harvest',
    thesis: 'Prioritize ETH expiry markets where decay dominates and catalyst density is low into settlement.',
  },
] as const

export function getPredictionCryptoPlaybookById(
  playbookId: PredictionCryptoPlaybookSpec['id'],
): PredictionCryptoPlaybookSpec | undefined {
  return predictionCryptoPlaybookSeeds.find((playbook) => playbook.id === playbookId)
}

export function listPredictionCryptoPlaybooksForAsset(
  asset: PredictionCryptoMarketSpec['base_asset'],
): readonly PredictionCryptoPlaybookSpec[] {
  return predictionCryptoPlaybookSeeds.filter((playbook) => playbook.focus_assets.includes(asset))
}

export function listPredictionCryptoMarketSeedsByFamily(
  family: PredictionCryptoMarketSpec['strategic_family'],
): readonly PredictionCryptoMarketSpec[] {
  return predictionCryptoMarketSeeds.filter((seed) => seed.strategic_family === family)
}
