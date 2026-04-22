import { listPredictionMarketUniverse } from '../service'

import {
  predictionCryptoMarketSeeds,
  predictionCryptoScope,
} from './market-spec'
import type {
  PredictionCryptoAsset,
  PredictionCryptoExecutionProfile,
  PredictionCryptoMarketArchetype,
  PredictionCryptoVenue,
} from './universe'

const CRYPTO_SCREENER_SCHEMA_VERSION = '1.0.0'
const CRYPTO_SCREENER_SNAPSHOT_ID = 'crypto-screener-seeded-v1'
const CRYPTO_SCREENER_LIVE_SNAPSHOT_ID = 'crypto-screener-live-v1'
const CRYPTO_SCREENER_GENERATED_AT = '2026-04-21T00:00:00.000Z'

type PredictionCryptoScreenerSourceMode = 'seeded' | 'live' | 'auto'

interface PredictionMarketUniverseMarket {
  venue: PredictionCryptoVenue
  market_id: string
  slug?: string
  question: string
  end_at?: string
  liquidity_usd?: number | null
  volume_24h_usd?: number | null
  last_trade_price?: number | null
  best_bid?: number | null
  best_ask?: number | null
  source_urls: string[]
}

const assetDepthWeight: Record<PredictionCryptoAsset, number> = {
  BTC: 30,
  ETH: 26,
  SOL: 22,
  XRP: 18,
  HYPE: 14,
}

const venueReadinessWeight: Record<PredictionCryptoVenue, number> = {
  polymarket: 21,
  kalshi: 24,
}

const archetypeWeight: Record<PredictionCryptoMarketArchetype, number> = {
  'short-horizon up-down': 14,
  'date-bounded price targets': 26,
  'range buckets': 23,
  'expiry-harvest': 17,
  'cross-venue crypto dislocations': 28,
}

const executionWeight: Record<PredictionCryptoExecutionProfile, number> = {
  'manual-research': 12,
  'semi-systematic': 19,
  'systematic-monitoring': 24,
}

const assetArchetypeSynergy: Partial<Record<`${PredictionCryptoAsset}:${PredictionCryptoMarketArchetype}`, number>> = {
  'BTC:date-bounded price targets': 8,
  'BTC:cross-venue crypto dislocations': 10,
  'SOL:range buckets': 9,
  'ETH:expiry-harvest': 7,
  'XRP:short-horizon up-down': 6,
}

const venueExecutionSynergy: Partial<Record<`${PredictionCryptoVenue}:${PredictionCryptoExecutionProfile}`, number>> = {
  'polymarket:semi-systematic': 5,
  'kalshi:systematic-monitoring': 7,
  'kalshi:manual-research': 2,
}

const assetAliases: Record<PredictionCryptoAsset, string[]> = {
  BTC: ['BTC', 'Bitcoin'],
  ETH: ['ETH', 'Ethereum'],
  SOL: ['SOL', 'Solana'],
  XRP: ['XRP', 'Ripple'],
  HYPE: ['HYPE', 'Hyperliquid'],
}

const archetypeKeywords: Record<PredictionCryptoMarketArchetype, string[]> = {
  'short-horizon up-down': ['up or down', 'higher or lower', 'up', 'down'],
  'date-bounded price targets': ['reach', 'hit', 'above', 'over', 'at least'],
  'range buckets': ['between', 'range', 'band', 'from', 'to'],
  'expiry-harvest': ['by', 'on', 'before', 'end of', 'expire'],
  'cross-venue crypto dislocations': ['price', 'market', 'trading', 'odds'],
}

export interface PredictionCryptoScoreComponent {
  key:
    | 'asset_depth'
    | 'venue_readiness'
    | 'archetype_fit'
    | 'execution_fit'
    | 'asset_archetype_synergy'
    | 'venue_execution_synergy'
    | 'live_market_support'
    | 'live_liquidity'
    | 'live_price_signal'
  label: string
  value: number
  rationale: string
}

export interface PredictionCryptoLiveMarketSummary {
  market_id: string
  question: string
  slug?: string
  end_at?: string
  liquidity_usd?: number | null
  volume_24h_usd?: number | null
  last_trade_price?: number | null
  best_bid?: number | null
  best_ask?: number | null
  source_urls: string[]
}

export interface PredictionCryptoScreenerOpportunity {
  opportunity_id: string
  rank: number
  score: number
  conviction: 'high' | 'medium'
  venue: PredictionCryptoVenue
  base_asset: PredictionCryptoAsset
  archetype: PredictionCryptoMarketArchetype
  execution_profile: PredictionCryptoExecutionProfile
  label: string
  thesis: string
  summary: string
  explanation: string[]
  score_breakdown: PredictionCryptoScoreComponent[]
  source_mode: Exclude<PredictionCryptoScreenerSourceMode, 'auto'>
  matched_market_count: number
  matched_market_ids: string[]
  source_urls: string[]
  top_market: PredictionCryptoLiveMarketSummary | null
  filters: {
    venue: PredictionCryptoVenue
    asset: PredictionCryptoAsset
    archetype: PredictionCryptoMarketArchetype
    execution_profile: PredictionCryptoExecutionProfile
  }
}

export interface PredictionCryptoScreenerResult {
  schema_version: string
  snapshot_id: string
  generated_at: string
  scope: {
    id: typeof predictionCryptoScope.id
    name: typeof predictionCryptoScope.name
    venues: readonly PredictionCryptoVenue[]
    assets: readonly PredictionCryptoAsset[]
    archetypes: readonly PredictionCryptoMarketArchetype[]
  }
  total: number
  opportunities: PredictionCryptoScreenerOpportunity[]
}

export interface PredictionCryptoScreenerFilters {
  venue?: PredictionCryptoVenue
  asset?: PredictionCryptoAsset
  archetype?: PredictionCryptoMarketArchetype
  execution_profile?: PredictionCryptoExecutionProfile
  limit?: number
  source_mode?: PredictionCryptoScreenerSourceMode
}

function toSlug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
}

function buildOpportunityId(input: {
  venue: PredictionCryptoVenue
  base_asset: PredictionCryptoAsset
  archetype: PredictionCryptoMarketArchetype
}) {
  return `crypto:${input.venue}:${input.base_asset.toLowerCase()}:${toSlug(input.archetype)}`
}

function buildSeedScoreComponents(input: {
  venue: PredictionCryptoVenue
  base_asset: PredictionCryptoAsset
  archetype: PredictionCryptoMarketArchetype
  execution_profile: PredictionCryptoExecutionProfile
}): PredictionCryptoScoreComponent[] {
  const assetArchetypeKey = `${input.base_asset}:${input.archetype}` as const
  const venueExecutionKey = `${input.venue}:${input.execution_profile}` as const

  return [
    {
      key: 'asset_depth',
      label: 'Asset depth',
      value: assetDepthWeight[input.base_asset],
      rationale: `${input.base_asset} sits inside the seeded CRYPTO focus set with deterministic depth weighting.`,
    },
    {
      key: 'venue_readiness',
      label: 'Venue readiness',
      value: venueReadinessWeight[input.venue],
      rationale: `${input.venue} receives a fixed readiness weight from the local venue map.`,
    },
    {
      key: 'archetype_fit',
      label: 'Archetype fit',
      value: archetypeWeight[input.archetype],
      rationale: `${input.archetype} carries a static fit score in the seeded archetype map.`,
    },
    {
      key: 'execution_fit',
      label: 'Execution fit',
      value: executionWeight[input.execution_profile],
      rationale: `${input.execution_profile} is ranked by deterministic execution preference.`,
    },
    {
      key: 'asset_archetype_synergy',
      label: 'Asset/archetype synergy',
      value: assetArchetypeSynergy[assetArchetypeKey] ?? 0,
      rationale:
        assetArchetypeSynergy[assetArchetypeKey] != null
          ? `${input.base_asset} and ${input.archetype} match a seeded synergy boost.`
          : 'No extra seeded synergy boost applies to this asset/archetype pair.',
    },
    {
      key: 'venue_execution_synergy',
      label: 'Venue/execution synergy',
      value: venueExecutionSynergy[venueExecutionKey] ?? 0,
      rationale:
        venueExecutionSynergy[venueExecutionKey] != null
          ? `${input.venue} and ${input.execution_profile} match a seeded execution synergy boost.`
          : 'No extra seeded synergy boost applies to this venue/execution pair.',
    },
  ]
}

function buildThesis(input: {
  base_asset: PredictionCryptoAsset
  archetype: PredictionCryptoMarketArchetype
  venue: PredictionCryptoVenue
  label: string
  sourceMode: Exclude<PredictionCryptoScreenerSourceMode, 'auto'>
}) {
  if (input.sourceMode === 'live') {
    return `${input.label} prioritizes ${input.base_asset} ${input.archetype} setups on ${input.venue} using live venue market discovery with seeded CRYPTO ranking overlays.`
  }

  return `${input.label} prioritizes ${input.base_asset} ${input.archetype} setups on ${input.venue} using only local CRYPTO seed metadata.`
}

function buildExplanation(scoreBreakdown: PredictionCryptoScoreComponent[]) {
  return scoreBreakdown
    .filter((component) => component.value > 0)
    .sort((left, right) => right.value - left.value)
    .slice(0, 3)
    .map((component) => `${component.label} +${component.value}: ${component.rationale}`)
}

function buildSummary(input: {
  score: number
  venue: PredictionCryptoVenue
  base_asset: PredictionCryptoAsset
  archetype: PredictionCryptoMarketArchetype
  sourceMode: Exclude<PredictionCryptoScreenerSourceMode, 'auto'>
  matchedMarketCount: number
  topMarketQuestion?: string
}) {
  if (input.sourceMode === 'live' && input.topMarketQuestion) {
    return `Score ${input.score} for ${input.base_asset} ${input.archetype} on ${input.venue}, backed by ${input.matchedMarketCount} live market match(es); top match: ${input.topMarketQuestion}`
  }

  return `Score ${input.score} for ${input.base_asset} ${input.archetype} on ${input.venue}.`
}

function mapTopMarket(market: PredictionMarketUniverseMarket | null): PredictionCryptoLiveMarketSummary | null {
  if (!market) return null

  return {
    market_id: market.market_id,
    question: market.question,
    slug: market.slug,
    end_at: market.end_at,
    liquidity_usd: market.liquidity_usd ?? null,
    volume_24h_usd: market.volume_24h_usd ?? null,
    last_trade_price: market.last_trade_price ?? null,
    best_bid: market.best_bid ?? null,
    best_ask: market.best_ask ?? null,
    source_urls: market.source_urls,
  }
}

function normalizeQuestion(value: string) {
  return value.trim().toLowerCase()
}

function scoreLiveMarketMatch(input: {
  market: PredictionMarketUniverseMarket
  asset: PredictionCryptoAsset
  archetype: PredictionCryptoMarketArchetype
}) {
  const question = normalizeQuestion(input.market.question)
  const aliases = assetAliases[input.asset].map((alias) => alias.toLowerCase())
  const keywords = archetypeKeywords[input.archetype]

  let score = 0
  if (aliases.some((alias) => question.includes(alias))) score += 30
  for (const keyword of keywords) {
    if (question.includes(keyword)) score += 8
  }
  if (input.market.liquidity_usd != null) {
    if (input.market.liquidity_usd >= 100_000) score += 10
    else if (input.market.liquidity_usd >= 25_000) score += 6
    else if (input.market.liquidity_usd >= 5_000) score += 3
  }
  if (input.market.volume_24h_usd != null) {
    if (input.market.volume_24h_usd >= 25_000) score += 6
    else if (input.market.volume_24h_usd >= 5_000) score += 3
    else if (input.market.volume_24h_usd > 0) score += 1
  }
  if (input.market.last_trade_price != null || input.market.best_bid != null || input.market.best_ask != null) {
    score += 4
  }

  return score
}

function buildLiveOverlayComponents(matches: PredictionMarketUniverseMarket[]): PredictionCryptoScoreComponent[] {
  const topMarket = matches[0] ?? null
  const maxLiquidity = Math.max(0, ...matches.map((market) => market.liquidity_usd ?? 0))
  const hasPriceSignal = matches.some((market) =>
    market.last_trade_price != null || market.best_bid != null || market.best_ask != null,
  )

  const liveSupportValue = matches.length === 0 ? 0 : Math.min(12, 4 + (matches.length * 2))
  const liveLiquidityValue = maxLiquidity >= 100_000 ? 8 : maxLiquidity >= 25_000 ? 5 : maxLiquidity >= 5_000 ? 3 : maxLiquidity > 0 ? 1 : 0
  const livePriceSignalValue = hasPriceSignal ? 4 : 0

  return [
    {
      key: 'live_market_support',
      label: 'Live market support',
      value: liveSupportValue,
      rationale:
        matches.length > 0
          ? `${matches.length} live market match(es) were discovered from the venue adapter for this CRYPTO setup.`
          : 'No live venue market match was attached to this seeded CRYPTO setup.',
    },
    {
      key: 'live_liquidity',
      label: 'Live liquidity',
      value: liveLiquidityValue,
      rationale:
        topMarket && topMarket.liquidity_usd != null
          ? `Top live match exposes roughly ${Math.round(topMarket.liquidity_usd).toLocaleString('en-US')} USD of liquidity.`
          : 'No meaningful live liquidity metric was attached to the top market match.',
    },
    {
      key: 'live_price_signal',
      label: 'Live price signal',
      value: livePriceSignalValue,
      rationale:
        hasPriceSignal
          ? 'The live venue match carries bid/ask or last-trade pricing, which improves immediate screenability.'
          : 'No bid/ask or last-trade pricing was available on the attached live market matches.',
    },
  ]
}

function filterSeeds(filters: PredictionCryptoScreenerFilters) {
  return predictionCryptoMarketSeeds.filter((seed) => {
    if (filters.venue && seed.venue !== filters.venue) return false
    if (filters.asset && seed.base_asset !== filters.asset) return false
    if (filters.archetype && seed.archetype !== filters.archetype) return false
    if (filters.execution_profile && seed.execution_profile !== filters.execution_profile) return false
    return true
  })
}

function buildSeededOpportunities(filters: PredictionCryptoScreenerFilters): PredictionCryptoScreenerOpportunity[] {
  const limit = filters.limit ?? 10

  return filterSeeds(filters)
    .map((seed) => {
      const score_breakdown = buildSeedScoreComponents(seed)
      const score = score_breakdown.reduce((total, component) => total + component.value, 0)
      const explanation = buildExplanation(score_breakdown)

      return {
        opportunity_id: buildOpportunityId(seed),
        rank: 0,
        score,
        conviction: score >= 100 ? 'high' : 'medium',
        venue: seed.venue,
        base_asset: seed.base_asset,
        archetype: seed.archetype,
        execution_profile: seed.execution_profile,
        label: seed.label,
        thesis: buildThesis({ ...seed, sourceMode: 'seeded' }),
        summary: buildSummary({
          score,
          venue: seed.venue,
          base_asset: seed.base_asset,
          archetype: seed.archetype,
          sourceMode: 'seeded',
          matchedMarketCount: 0,
        }),
        explanation,
        score_breakdown,
        source_mode: 'seeded',
        matched_market_count: 0,
        matched_market_ids: [],
        source_urls: [],
        top_market: null,
        filters: {
          venue: seed.venue,
          asset: seed.base_asset,
          archetype: seed.archetype,
          execution_profile: seed.execution_profile,
        },
      } satisfies PredictionCryptoScreenerOpportunity
    })
    .sort((left, right) => {
      if (right.score !== left.score) return right.score - left.score
      return left.opportunity_id.localeCompare(right.opportunity_id)
    })
    .slice(0, limit)
    .map((opportunity, index) => ({
      ...opportunity,
      rank: index + 1,
    }))
}

function buildResult(input: {
  snapshotId: string
  opportunities: PredictionCryptoScreenerOpportunity[]
}) {
  return {
    schema_version: CRYPTO_SCREENER_SCHEMA_VERSION,
    snapshot_id: input.snapshotId,
    generated_at: CRYPTO_SCREENER_GENERATED_AT,
    scope: predictionCryptoScope,
    total: input.opportunities.length,
    opportunities: input.opportunities,
  } satisfies PredictionCryptoScreenerResult
}

async function fetchLiveVenueMarkets(filters: PredictionCryptoScreenerFilters) {
  const seeds = filterSeeds(filters)
  const requestedAssets = Array.from(new Set(seeds.map((seed) => seed.base_asset)))
  const requestedVenues = Array.from(new Set(seeds.map((seed) => seed.venue)))
  const marketMap = new Map<string, PredictionMarketUniverseMarket[]>()

  await Promise.all(
    requestedVenues.flatMap((venue) =>
      requestedAssets.flatMap((asset) =>
        assetAliases[asset].map(async (alias) => {
          const result = await listPredictionMarketUniverse({
            venue,
            limit: 25,
            search: alias,
          })

          const key = `${venue}:${asset}`
          const existing = marketMap.get(key) ?? []
          const normalized = result.markets.map((market) => ({
            venue,
            market_id: market.market_id,
            slug: market.slug,
            question: market.question,
            end_at: market.end_at,
            liquidity_usd: market.liquidity_usd ?? null,
            volume_24h_usd: market.volume_24h_usd ?? null,
            last_trade_price: market.last_trade_price ?? null,
            best_bid: market.best_bid ?? null,
            best_ask: market.best_ask ?? null,
            source_urls: market.source_urls,
          }))

          const deduped = new Map(existing.concat(normalized).map((market) => [market.market_id, market]))
          marketMap.set(key, Array.from(deduped.values()))
        }),
      ),
    ),
  )

  return marketMap
}

export function buildPredictionCryptoScreener(
  filters: PredictionCryptoScreenerFilters = {},
): PredictionCryptoScreenerResult {
  return buildResult({
    snapshotId: CRYPTO_SCREENER_SNAPSHOT_ID,
    opportunities: buildSeededOpportunities({ ...filters, source_mode: 'seeded' }),
  })
}

export async function buildPredictionCryptoScreenerLive(
  filters: PredictionCryptoScreenerFilters = {},
): Promise<PredictionCryptoScreenerResult> {
  const requestedMode = filters.source_mode ?? 'auto'
  if (requestedMode === 'seeded') {
    return buildPredictionCryptoScreener(filters)
  }

  const limit = filters.limit ?? 10
  const seeds = filterSeeds(filters)

  try {
    const marketMap = await fetchLiveVenueMarkets(filters)

    const ranked = seeds
      .map((seed) => {
        const liveCandidates = (marketMap.get(`${seed.venue}:${seed.base_asset}`) ?? [])
          .map((market) => ({
            market,
            matchScore: scoreLiveMarketMatch({
              market,
              asset: seed.base_asset,
              archetype: seed.archetype,
            }),
          }))
          .filter((entry) => entry.matchScore >= 30)
          .sort((left, right) => right.matchScore - left.matchScore)
          .map((entry) => entry.market)

        const score_breakdown = [
          ...buildSeedScoreComponents(seed),
          ...buildLiveOverlayComponents(liveCandidates),
        ]
        const score = score_breakdown.reduce((total, component) => total + component.value, 0)
        const explanation = buildExplanation(score_breakdown)
        const sourceUrls = Array.from(new Set(liveCandidates.flatMap((market) => market.source_urls)))
        const topMarket = mapTopMarket(liveCandidates[0] ?? null)

        return {
          opportunity_id: buildOpportunityId(seed),
          rank: 0,
          score,
          conviction: score >= 100 ? 'high' : 'medium',
          venue: seed.venue,
          base_asset: seed.base_asset,
          archetype: seed.archetype,
          execution_profile: seed.execution_profile,
          label: seed.label,
          thesis: buildThesis({ ...seed, sourceMode: liveCandidates.length > 0 ? 'live' : 'seeded' }),
          summary: buildSummary({
            score,
            venue: seed.venue,
            base_asset: seed.base_asset,
            archetype: seed.archetype,
            sourceMode: liveCandidates.length > 0 ? 'live' : 'seeded',
            matchedMarketCount: liveCandidates.length,
            topMarketQuestion: topMarket?.question,
          }),
          explanation,
          score_breakdown,
          source_mode: liveCandidates.length > 0 ? 'live' : 'seeded',
          matched_market_count: liveCandidates.length,
          matched_market_ids: liveCandidates.map((market) => market.market_id),
          source_urls: sourceUrls,
          top_market: topMarket,
          filters: {
            venue: seed.venue,
            asset: seed.base_asset,
            archetype: seed.archetype,
            execution_profile: seed.execution_profile,
          },
        } satisfies PredictionCryptoScreenerOpportunity
      })
      .sort((left, right) => {
        if (right.score !== left.score) return right.score - left.score
        return left.opportunity_id.localeCompare(right.opportunity_id)
      })
      .slice(0, limit)
      .map((opportunity, index) => ({
        ...opportunity,
        rank: index + 1,
      }))

    const hasLiveMatch = ranked.some((opportunity) => opportunity.source_mode === 'live')
    if (!hasLiveMatch && requestedMode === 'auto') {
      return buildPredictionCryptoScreener(filters)
    }

    return buildResult({
      snapshotId: hasLiveMatch ? CRYPTO_SCREENER_LIVE_SNAPSHOT_ID : CRYPTO_SCREENER_SNAPSHOT_ID,
      opportunities: ranked,
    })
  } catch {
    return buildPredictionCryptoScreener(filters)
  }
}

export async function getPredictionCryptoScreenerOpportunity(
  opportunityId: string,
  filters: PredictionCryptoScreenerFilters = {},
) {
  const seeded = buildPredictionCryptoScreener({
    ...filters,
    limit: predictionCryptoMarketSeeds.length,
  }).opportunities.find((opportunity) => opportunity.opportunity_id === opportunityId) ?? null

  if ((filters.source_mode ?? 'auto') === 'seeded') {
    return seeded
  }

  const live = (await buildPredictionCryptoScreenerLive({
    ...filters,
    limit: predictionCryptoMarketSeeds.length,
  })).opportunities.find((opportunity) => opportunity.opportunity_id === opportunityId) ?? null

  return live ?? seeded
}
