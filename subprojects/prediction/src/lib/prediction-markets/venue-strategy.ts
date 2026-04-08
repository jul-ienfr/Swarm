import type { PredictionMarketVenueId } from '@/lib/prediction-markets/venue-ops'

export type PredictionMarketVenueSourceOfTruth = 'official_docs' | 'community_repos'
export type PredictionMarketVenueSourceRole = 'source_of_truth' | 'community_reference'
export type PredictionMarketVenueRole = 'execution-equivalent' | 'reference-only' | 'signal-only' | 'watchlist'

export type PredictionMarketVenueSourceHierarchyEntry = {
  source: PredictionMarketVenueSourceOfTruth
  role: PredictionMarketVenueSourceRole
  priority: number
  execution_eligible: boolean
  notes: string[]
}

export type PredictionMarketVenueStrategy = {
  venue: PredictionMarketVenueId
  source_of_truth: PredictionMarketVenueSourceOfTruth
  role: PredictionMarketVenueRole
  execution_eligible: boolean
  source_of_truth_priority: PredictionMarketVenueSourceOfTruth[]
  source_hierarchy: PredictionMarketVenueSourceHierarchyEntry[]
  community_reference: PredictionMarketVenueSourceHierarchyEntry
  notes: string[]
}

const DEFAULT_SOURCE_OF_TRUTH_PRIORITY: PredictionMarketVenueSourceOfTruth[] = [
  'official_docs',
  'community_repos',
]

function buildExecutionEquivalentStrategy(venue: PredictionMarketVenueId): PredictionMarketVenueStrategy {
  const sourceHierarchy: PredictionMarketVenueSourceHierarchyEntry[] = [
    {
      source: 'official_docs',
      role: 'source_of_truth',
      priority: 1,
      execution_eligible: true,
      notes: [
        'Primary implementation authority for contracts, APIs, and product behavior.',
        'Use this layer to define runtime behavior and operational policy.',
      ],
    },
    {
      source: 'community_repos',
      role: 'community_reference',
      priority: 2,
      execution_eligible: false,
      notes: [
        'Useful for patterns, examples, and edge-case discovery.',
        'Do not use as implementation authority when it conflicts with official docs.',
      ],
    },
  ]

  return {
    venue,
    source_of_truth: 'official_docs',
    role: 'execution-equivalent',
    execution_eligible: true,
    source_of_truth_priority: DEFAULT_SOURCE_OF_TRUTH_PRIORITY,
    source_hierarchy: sourceHierarchy,
    community_reference: sourceHierarchy[1],
    notes: [
      'Official venue docs are the implementation source of truth.',
      'Community repos are a secondary reference layer, not implementation policy.',
      'Venue remains execution-equivalent at the strategy layer, even when runtime is preflight-only.',
    ],
  }
}

export function getPredictionMarketVenueStrategy(
  venue: PredictionMarketVenueId,
): PredictionMarketVenueStrategy {
  switch (venue) {
    case 'polymarket':
      return buildExecutionEquivalentStrategy(venue)
    case 'kalshi':
      return buildExecutionEquivalentStrategy(venue)
    default:
      throw new Error(`Unsupported prediction market venue: ${venue}`)
  }
}
