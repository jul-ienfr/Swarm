import {
  arbPlanSchema,
  crossVenueOpportunityTypeSchema,
  crossVenueMatchSchema,
  executableEdgeSchema,
  marketEquivalenceProofSchema,
  type CrossVenueMarketRef,
  type CrossVenueMatch,
  type CrossVenueOpportunityType,
  type ArbPlan,
  type ExecutableEdge,
  type MarketEquivalenceProof,
  type MarketDescriptor,
  type MarketSnapshot,
} from '@/lib/prediction-markets/schemas'

const STOPWORDS = new Set([
  'a',
  'an',
  'and',
  'are',
  'at',
  'be',
  'by',
  'for',
  'from',
  'if',
  'in',
  'is',
  'it',
  'of',
  'on',
  'or',
  'the',
  'to',
  'vs',
  'what',
  'when',
  'will',
  'with',
])

const SUBJECT_VERBS = [
  'win',
  'wins',
  'be',
  'have',
  'has',
  'hit',
  'reach',
  'exceed',
  'pass',
  'receive',
  'score',
  'remain',
  'lose',
  'drop',
  'get',
]

const DEFAULT_MIN_SEMANTIC_SCORE = 0.58
const DEFAULT_MIN_COMPATIBILITY_SCORE = 0.72
const DEFAULT_MIN_ARBITRAGE_SPREAD_BPS = 150
const DEFAULT_EXECUTABLE_EDGE_FRESHNESS_BUDGET_MS = 15 * 60 * 1000
const DEFAULT_CAPITAL_FRAGMENTATION_PENALTY_BPS = 8
const DEFAULT_TRANSFER_LATENCY_PENALTY_PER_HOUR_BPS = 6
const DEFAULT_LOW_CONFIDENCE_PENALTY_BPS = 40
const NEGATION_MARKERS = [
  'no',
  'not',
  'never',
  'without',
  "won't",
  "can't",
  'cannot',
  'fail',
  'fails',
  'failed',
  'decline',
  'declines',
  'declined',
  'drop',
  'drops',
  'dropped',
  'below',
  'under',
]
const CURRENCY_HINTS = [
  { currency: 'USDC', pattern: /\busdc\b/ },
  { currency: 'USD', pattern: /\busd\b|\bus dollars?\b/ },
  { currency: 'EUR', pattern: /\beur\b|\beuros?\b/ },
  { currency: 'GBP', pattern: /\bgbp\b|\bpounds?\b/ },
  { currency: 'JPY', pattern: /\bjpy\b|\byen\b/ },
  { currency: 'CAD', pattern: /\bcad\b|\bcanadian dollars?\b/ },
  { currency: 'AUD', pattern: /\baud\b|\baustralian dollars?\b/ },
  { currency: 'CHF', pattern: /\bchf\b|\bswiss francs?\b/ },
]
const HARD_BLOCKING_REASONS = new Set([
  'same_venue_pair',
  'proposition_subject_mismatch',
  'time_horizon_mismatch',
  'polarity_mismatch',
  'non_binary_contract',
  'payout_shape_mismatch',
  'currency_incompatibility_explicit',
  'missing_time_horizon',
])
const OPPORTUNITY_TYPES = crossVenueOpportunityTypeSchema.options as CrossVenueOpportunityType[]

export type CrossVenueEvaluationInput = {
  left: MarketDescriptor
  right: MarketDescriptor
  leftSnapshot?: MarketSnapshot | null
  rightSnapshot?: MarketSnapshot | null
  asOfAt?: string
  minSemanticScore?: number
  minCompatibilityScore?: number
  minArbitrageSpreadBps?: number
}

export type FindCrossVenueMatchesInput = {
  markets: MarketDescriptor[]
  snapshots?: MarketSnapshot[]
  asOfAt?: string
  minSemanticScore?: number
  minCompatibilityScore?: number
  minArbitrageSpreadBps?: number
  includeManualReview?: boolean
  maxPairs?: number
}

export type CrossVenueArbitrageCandidate = {
  candidate_type: 'yes_yes_spread'
  opportunity_type: CrossVenueOpportunityType
  canonical_event_id: string
  canonical_event_key: string
  buy_ref: CrossVenueMarketRef
  sell_ref: CrossVenueMarketRef
  buy_price_yes: number
  sell_price_yes: number
  gross_spread_bps: number
  net_spread_bps: number
  confidence_score: number
  executable: boolean
  executable_edge: ExecutableEdge
  market_equivalence_proof: MarketEquivalenceProof
  arb_plan: ArbPlan
  reasons: string[]
}

export type CrossVenueEvaluation = {
  canonical_event_id: string
  canonical_event_key: string
  confidence_score: number
  compatible: boolean
  opportunity_type: CrossVenueOpportunityType
  market_equivalence_proof: MarketEquivalenceProof
  executable_edge: ExecutableEdge | null
  mismatch_reasons: string[]
  match: CrossVenueMatch
  arbitrage_candidate: CrossVenueArbitrageCandidate | null
}

export type CrossVenueOpsSummary = {
  total_pairs: number
  opportunity_type_counts: Record<CrossVenueOpportunityType, number>
  compatible: CrossVenueEvaluation[]
  manual_review: CrossVenueEvaluation[]
  comparison_only: CrossVenueEvaluation[]
  blocking_reasons: string[]
  highest_confidence_candidate: CrossVenueArbitrageCandidate | null
}

type CrossVenueEvaluationCore = {
  canonical_event_id: string
  canonical_event_key: string
  confidence_score: number
  compatible: boolean
  mismatch_reasons: string[]
  match: CrossVenueMatch
}

type PriceObservation = {
  price: number
  source:
    | 'best_ask_yes'
    | 'best_bid_yes'
    | 'midpoint_yes'
    | 'yes_price'
    | 'market_best_ask'
    | 'market_best_bid'
    | 'market_last_trade'
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function roundScore(value: number): number {
  return Number(clamp(value, 0, 1).toFixed(4))
}

function roundBps(value: number): number {
  return Number(value.toFixed(2))
}

function sanitizeText(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9$% ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function tokenize(value: string): string[] {
  return sanitizeText(value)
    .split(' ')
    .map((token) => token.trim())
    .filter((token) => token.length > 1 && !STOPWORDS.has(token))
}

function unique<T>(values: readonly T[]): T[] {
  return [...new Set(values)]
}

function jaccard(left: readonly string[], right: readonly string[]): number {
  const leftSet = new Set(left)
  const rightSet = new Set(right)
  const universe = new Set([...leftSet, ...rightSet])
  if (universe.size === 0) return 0

  let intersection = 0
  for (const token of leftSet) {
    if (rightSet.has(token)) intersection += 1
  }

  return intersection / universe.size
}

function extractNumericHints(value: string): string[] {
  const matches = sanitizeText(value).match(/\d+(?:\.\d+)?/g)
  return matches ? unique(matches) : []
}

function extractSubjectHint(question: string): string | undefined {
  const normalized = sanitizeText(question)
  const verbPattern = SUBJECT_VERBS.join('|')
  const match = normalized.match(new RegExp(`^will\\s+(.+?)\\s+(?:${verbPattern})\\b`))
  const subject = match?.[1]?.trim()
  if (!subject) return undefined

  const subjectTokens = tokenize(subject)
  if (subjectTokens.length === 0 || subjectTokens.length > 8) return undefined
  return subjectTokens.join(' ')
}

function hasNegationMarker(question: string): boolean {
  const normalized = sanitizeText(question)
  return NEGATION_MARKERS.some((marker) => normalized.includes(marker))
}

function getDateKey(market: MarketDescriptor): string | undefined {
  const raw = market.end_at ?? market.start_at
  if (!raw) return undefined

  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return undefined
  return parsed.toISOString().slice(0, 10)
}

function getDateDistanceDays(left: MarketDescriptor, right: MarketDescriptor): number | null {
  const leftRaw = left.end_at ?? left.start_at
  const rightRaw = right.end_at ?? right.start_at
  if (!leftRaw || !rightRaw) return null

  const leftDate = new Date(leftRaw)
  const rightDate = new Date(rightRaw)
  if (Number.isNaN(leftDate.getTime()) || Number.isNaN(rightDate.getTime())) return null

  return Math.abs(leftDate.getTime() - rightDate.getTime()) / 86_400_000
}

function inferCurrencyHint(market: MarketDescriptor): string | undefined {
  const haystack = sanitizeText([
    market.question,
    market.description ?? '',
    market.slug ?? '',
  ].filter(Boolean).join(' '))

  for (const { currency, pattern } of CURRENCY_HINTS) {
    if (pattern.test(haystack)) return currency
  }

  return undefined
}

function makeMarketRef(market: MarketDescriptor): CrossVenueMarketRef {
  return {
    venue: market.venue,
    market_id: market.market_id,
    venue_type: market.venue_type,
    slug: market.slug,
    question: market.question,
  }
}

function getSnapshotKey(venue: string, marketId: string): string {
  return `${venue}:${marketId}`
}

function indexSnapshots(snapshots: readonly MarketSnapshot[]): Map<string, MarketSnapshot> {
  const index = new Map<string, MarketSnapshot>()

  for (const snapshot of snapshots) {
    index.set(getSnapshotKey(snapshot.venue, snapshot.market.market_id), snapshot)
  }

  return index
}

function buildCanonicalEventKey(markets: readonly MarketDescriptor[]): string {
  const dateHints = unique(markets.map(getDateKey).filter((value): value is string => Boolean(value))).sort()
  const tokenSets = markets.map((market) => tokenize(market.question))
  const commonTokens = tokenSets.reduce<string[]>((accumulator, current, index) => {
    if (index === 0) return current
    const currentSet = new Set(current)
    return accumulator.filter((token) => currentSet.has(token))
  }, [])
  const fallbackTokens = unique(tokenSets.flat()).sort()
  const coreTokens = (commonTokens.length >= 2 ? commonTokens : fallbackTokens).slice(0, 8)
  const datePart = dateHints[0] ?? 'undated'
  const tokenPart = coreTokens.join('-') || 'unclassified-event'

  return `${datePart}:${tokenPart}`
}

function buildCanonicalEventId(markets: readonly MarketDescriptor[]): string {
  return `cve:${buildCanonicalEventKey(markets)}`
}

function getSemanticSimilarity(left: MarketDescriptor, right: MarketDescriptor, reasons: string[]): number {
  const questionScore = jaccard(tokenize(left.question), tokenize(right.question))
  const subjectLeft = extractSubjectHint(left.question)
  const subjectRight = extractSubjectHint(right.question)

  let subjectScore = 0.7
  if (subjectLeft && subjectRight) {
    subjectScore = jaccard(tokenize(subjectLeft), tokenize(subjectRight))
    if (subjectScore < 0.35) {
      reasons.push('proposition_subject_mismatch')
    }
  }

  const numbersLeft = extractNumericHints(left.question)
  const numbersRight = extractNumericHints(right.question)
  let thresholdScore = 1
  if (numbersLeft.length > 0 && numbersRight.length > 0) {
    thresholdScore = jaccard(numbersLeft, numbersRight)
    if (thresholdScore < 0.5) {
      reasons.push('numeric_threshold_mismatch')
    }
  }

  const semanticScore = (questionScore * 0.6) + (subjectScore * 0.25) + (thresholdScore * 0.15)
  return roundScore(semanticScore)
}

function getResolutionCompatibility(left: MarketDescriptor, right: MarketDescriptor, reasons: string[]): number {
  let score = 1

  if (!left.is_binary_yes_no || !right.is_binary_yes_no) {
    reasons.push('non_binary_contract')
    score -= 0.4
  }

  const dateDistanceDays = getDateDistanceDays(left, right)
  if (dateDistanceDays == null) {
    reasons.push('missing_time_horizon')
    score -= 0.1
  } else if (dateDistanceDays > 30) {
    reasons.push(`resolution_horizon_drift_gt_30d:${dateDistanceDays.toFixed(1)}`)
    reasons.push('time_horizon_mismatch')
    score -= 0.8
  } else if (dateDistanceDays > 14) {
    reasons.push(`resolution_horizon_drift_gt_14d:${dateDistanceDays.toFixed(1)}`)
    reasons.push('time_horizon_mismatch')
    score -= 0.6
  } else if (dateDistanceDays > 7) {
    reasons.push(`resolution_horizon_drift_gt_7d:${dateDistanceDays.toFixed(1)}`)
    reasons.push('time_horizon_mismatch')
    score -= 0.45
  } else if (dateDistanceDays > 2) {
    reasons.push('time_horizon_soft_mismatch')
    score -= 0.15
  }

  if (left.closed !== right.closed) {
    reasons.push('lifecycle_status_mismatch')
    score -= 0.1
  }

  return roundScore(score)
}

function getPayoutCompatibility(left: MarketDescriptor, right: MarketDescriptor, reasons: string[]): number {
  if (!left.is_binary_yes_no || !right.is_binary_yes_no) {
    reasons.push('payout_shape_mismatch')
    if (left.outcomes.length !== 2 || right.outcomes.length !== 2 || left.outcomes.length !== right.outcomes.length) {
      reasons.push(`payout_shape_strong_mismatch:${left.outcomes.length}_vs_${right.outcomes.length}`)
    }
    return 0.3
  }

  if (left.venue_type === 'experimental' || right.venue_type === 'experimental') {
    reasons.push('experimental_venue_requires_review')
    return 0.7
  }

  return 1
}

function getCurrencyCompatibility(left: MarketDescriptor, right: MarketDescriptor, reasons: string[]): number {
  const leftCurrency = inferCurrencyHint(left)
  const rightCurrency = inferCurrencyHint(right)

  if (leftCurrency && rightCurrency && leftCurrency !== rightCurrency) {
    reasons.push('currency_incompatibility_explicit')
    reasons.push(`currency_mismatch:${leftCurrency}_vs_${rightCurrency}`)
    return 0.2
  }

  // The current canonical contracts do not carry an explicit currency field.
  // If we cannot detect a concrete mismatch, stay neutral.
  return 1
}

function pickBuyYesPrice(market: MarketDescriptor, snapshot?: MarketSnapshot | null): PriceObservation | null {
  if (snapshot?.best_ask_yes != null) return { price: snapshot.best_ask_yes, source: 'best_ask_yes' }
  if (snapshot?.midpoint_yes != null) return { price: snapshot.midpoint_yes, source: 'midpoint_yes' }
  if (snapshot?.yes_price != null) return { price: snapshot.yes_price, source: 'yes_price' }
  if (market.best_ask != null) return { price: market.best_ask, source: 'market_best_ask' }
  if (market.last_trade_price != null) return { price: market.last_trade_price, source: 'market_last_trade' }
  if (market.best_bid != null) return { price: market.best_bid, source: 'market_best_bid' }
  return null
}

function pickSellYesPrice(market: MarketDescriptor, snapshot?: MarketSnapshot | null): PriceObservation | null {
  if (snapshot?.best_bid_yes != null) return { price: snapshot.best_bid_yes, source: 'best_bid_yes' }
  if (snapshot?.midpoint_yes != null) return { price: snapshot.midpoint_yes, source: 'midpoint_yes' }
  if (snapshot?.yes_price != null) return { price: snapshot.yes_price, source: 'yes_price' }
  if (market.best_bid != null) return { price: market.best_bid, source: 'market_best_bid' }
  if (market.last_trade_price != null) return { price: market.last_trade_price, source: 'market_last_trade' }
  if (market.best_ask != null) return { price: market.best_ask, source: 'market_best_ask' }
  return null
}

function isExecutableSource(source: PriceObservation['source']): boolean {
  return source === 'best_ask_yes' || source === 'best_bid_yes' || source === 'market_best_ask' || source === 'market_best_bid'
}

function estimateVenueFeeBps(venueType: MarketDescriptor['venue_type']): number {
  switch (venueType) {
    case 'execution-equivalent':
      return 8
    case 'reference-only':
      return 0
    case 'experimental':
      return 18
    default:
      return 12
  }
}

function estimateLegSlippageBps(input: {
  market: MarketDescriptor
  snapshot?: MarketSnapshot | null
  source: PriceObservation['source']
}): number {
  const marketSpreadBps = input.market.best_bid != null && input.market.best_ask != null
    ? Math.max(0, (input.market.best_ask - input.market.best_bid) * 10_000)
    : null
  const observedSpreadBps = input.snapshot?.spread_bps ?? marketSpreadBps
  const baseSpreadBps = observedSpreadBps ?? 40
  const multiplier = isExecutableSource(input.source) ? 0.25 : 0.4
  return roundBps(clamp(baseSpreadBps * multiplier, 2, 120))
}

function estimateHedgeRiskBps(input: {
  confidenceScore: number
  executable: boolean
  compatible: boolean
}) {
  const base = input.executable ? 6 : input.compatible ? 14 : 22
  const confidencePenalty = roundBps((1 - input.confidenceScore) * 20)
  return roundBps(clamp(base + confidencePenalty, 2, 80))
}

function parseTimestampMs(value: string | undefined | null): number | null {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : null
}

function resolveAsOfMs(value: string | undefined): number {
  return parseTimestampMs(value) ?? Date.now()
}

function getSnapshotObservationMs(snapshot?: MarketSnapshot | null): number | null {
  if (!snapshot) return null
  return parseTimestampMs(snapshot.book?.fetched_at ?? snapshot.captured_at)
}

function computeFreshnessAgeMs(input: {
  asOfMs: number
  leftSnapshot?: MarketSnapshot | null
  rightSnapshot?: MarketSnapshot | null
}): number {
  const observations = [
    getSnapshotObservationMs(input.leftSnapshot),
    getSnapshotObservationMs(input.rightSnapshot),
  ].filter((value): value is number => value != null)

  if (observations.length === 0) return 0

  const oldestObservationMs = Math.min(...observations)
  return Math.max(0, input.asOfMs - oldestObservationMs)
}

function buildExecutableEdgePenaltyBreakdown(input: {
  freshnessAgeMs: number
  freshnessBudgetMs: number
  left: MarketDescriptor
  right: MarketDescriptor
  confidenceScore: number
}): {
  capitalFragmentationPenaltyBps: number
  transferLatencyPenaltyBps: number
  lowConfidencePenaltyBps: number
  staleEdgePenaltyBps: number
  staleEdgeExpired: boolean
} {
  const staleEdgeExpired = input.freshnessAgeMs > input.freshnessBudgetMs
  const capitalFragmentationPenaltyBps = input.left.venue === input.right.venue
    ? 0
    : DEFAULT_CAPITAL_FRAGMENTATION_PENALTY_BPS
  const transferLatencyPenaltyBps = input.left.venue === input.right.venue
    ? 0
    : Math.min(
        30,
        Math.max(
          2,
          roundBps((input.freshnessAgeMs / 3_600_000) * DEFAULT_TRANSFER_LATENCY_PENALTY_PER_HOUR_BPS),
        ),
      )
  const lowConfidencePenaltyBps = roundBps((1 - input.confidenceScore) * DEFAULT_LOW_CONFIDENCE_PENALTY_BPS)
  const staleEdgePenaltyBps = staleEdgeExpired
    ? Math.min(80, Math.max(12, roundBps(((input.freshnessAgeMs - input.freshnessBudgetMs) / 60_000) * 2)))
    : 0

  return {
    capitalFragmentationPenaltyBps,
    transferLatencyPenaltyBps,
    lowConfidencePenaltyBps,
    staleEdgePenaltyBps,
    staleEdgeExpired,
  }
}

function buildMarketEquivalenceProof(input: {
  evaluation: CrossVenueEvaluationCore
  left: MarketDescriptor
  right: MarketDescriptor
}): MarketEquivalenceProof {
  const dateDistanceDays = getDateDistanceDays(input.left, input.right)
  const timingCompatibilityScore = dateDistanceDays == null
    ? 0.5
    : roundScore(clamp(1 - (dateDistanceDays / 30), 0, 1))
  const proofStatus = !input.evaluation.compatible
    ? 'blocked'
    : input.evaluation.match.manual_review_required || input.evaluation.confidence_score < 0.85
      ? 'partial'
      : 'proven'

  return marketEquivalenceProofSchema.parse({
    proof_id: `mep:${input.evaluation.canonical_event_id}`,
    canonical_event_id: input.evaluation.canonical_event_id,
    left_market_ref: makeMarketRef(input.left),
    right_market_ref: makeMarketRef(input.right),
    proof_status: proofStatus,
    resolution_compatibility_score: input.evaluation.match.resolution_compatibility_score,
    payout_compatibility_score: input.evaluation.match.payout_compatibility_score,
    currency_compatibility_score: input.evaluation.match.currency_compatibility_score,
    timing_compatibility_score: timingCompatibilityScore,
    manual_review_required: input.evaluation.match.manual_review_required,
    mismatch_reasons: unique(input.evaluation.mismatch_reasons),
    notes: unique([
      `canonical_event_key:${input.evaluation.canonical_event_key}`,
      `confidence_score:${input.evaluation.confidence_score.toFixed(4)}`,
      `compatible:${input.evaluation.compatible}`,
    ]),
  })
}

function buildExecutableEdge(input: {
  evaluation: CrossVenueEvaluationCore
  left: MarketDescriptor
  right: MarketDescriptor
  leftSnapshot?: MarketSnapshot | null
  rightSnapshot?: MarketSnapshot | null
  asOfAt?: string
}): ExecutableEdge | null {
  const asOfMs = resolveAsOfMs(input.asOfAt)
  const freshnessAgeMs = computeFreshnessAgeMs({
    asOfMs,
    leftSnapshot: input.leftSnapshot,
    rightSnapshot: input.rightSnapshot,
  })
  const freshnessBudgetMs = DEFAULT_EXECUTABLE_EDGE_FRESHNESS_BUDGET_MS
  const leftBuy = pickBuyYesPrice(input.left, input.leftSnapshot)
  const leftSell = pickSellYesPrice(input.left, input.leftSnapshot)
  const rightBuy = pickBuyYesPrice(input.right, input.rightSnapshot)
  const rightSell = pickSellYesPrice(input.right, input.rightSnapshot)

  if (!leftBuy || !leftSell || !rightBuy || !rightSell) {
    return null
  }

  const directions = [
    {
      buy_ref: makeMarketRef(input.left),
      sell_ref: makeMarketRef(input.right),
      buy_price_yes: leftBuy.price,
      sell_price_yes: rightSell.price,
      buy_source: leftBuy.source,
      sell_source: rightSell.source,
    },
    {
      buy_ref: makeMarketRef(input.right),
      sell_ref: makeMarketRef(input.left),
      buy_price_yes: rightBuy.price,
      sell_price_yes: leftSell.price,
      buy_source: rightBuy.source,
      sell_source: leftSell.source,
    },
  ]

  let bestDirection = directions[0]
  let bestNetEdge = -Infinity
  let bestFees = 0
  let bestSlippage = 0
  let bestHedgeRisk = 0
  let bestExecutable = false
  const penaltyBreakdown = buildExecutableEdgePenaltyBreakdown({
    freshnessAgeMs,
    freshnessBudgetMs,
    left: input.left,
    right: input.right,
    confidenceScore: input.evaluation.confidence_score,
  })

  for (const direction of directions) {
    const grossSpreadBps = roundBps((direction.sell_price_yes - direction.buy_price_yes) * 10_000)
    const feeBps = estimateVenueFeeBps(input.left.venue_type) + estimateVenueFeeBps(input.right.venue_type)
    const slippageBps = estimateLegSlippageBps({ market: input.left, snapshot: input.leftSnapshot, source: direction.buy_source }) +
      estimateLegSlippageBps({ market: input.right, snapshot: input.rightSnapshot, source: direction.sell_source })
    const hedgeRiskBps = estimateHedgeRiskBps({
      confidenceScore: input.evaluation.confidence_score,
      executable: isExecutableSource(direction.buy_source) && isExecutableSource(direction.sell_source),
      compatible: input.evaluation.compatible,
    })
    const executableEdgeBps = roundBps(
      grossSpreadBps -
      feeBps -
      slippageBps -
      hedgeRiskBps -
      penaltyBreakdown.capitalFragmentationPenaltyBps -
      penaltyBreakdown.transferLatencyPenaltyBps -
      penaltyBreakdown.lowConfidencePenaltyBps -
      penaltyBreakdown.staleEdgePenaltyBps,
    )
    const executable = !penaltyBreakdown.staleEdgeExpired &&
      isExecutableSource(direction.buy_source) &&
      isExecutableSource(direction.sell_source) &&
      executableEdgeBps > 0

    if (executableEdgeBps > bestNetEdge) {
      bestDirection = direction
      bestNetEdge = executableEdgeBps
      bestFees = feeBps
      bestSlippage = slippageBps
      bestHedgeRisk = hedgeRiskBps
      bestExecutable = executable
    }
  }

  const grossSpreadBps = roundBps((bestDirection.sell_price_yes - bestDirection.buy_price_yes) * 10_000)
  const executableEdgeBps = roundBps(bestNetEdge)

  return executableEdgeSchema.parse({
    edge_id: `edge:${input.evaluation.canonical_event_id}:${bestDirection.buy_ref.venue}-${bestDirection.sell_ref.venue}`,
    canonical_event_id: input.evaluation.canonical_event_id,
    opportunity_type: 'relative_value',
    buy_ref: bestDirection.buy_ref,
    sell_ref: bestDirection.sell_ref,
    buy_price_yes: bestDirection.buy_price_yes,
    sell_price_yes: bestDirection.sell_price_yes,
    gross_spread_bps: grossSpreadBps,
    fee_bps: bestFees,
    slippage_bps: bestSlippage,
    hedge_risk_bps: bestHedgeRisk,
    executable_edge_bps: executableEdgeBps,
    confidence_score: input.evaluation.confidence_score,
    executable: bestExecutable,
    evaluated_at: new Date(asOfMs).toISOString(),
    notes: unique([
      `buy_source:${bestDirection.buy_source}`,
      `sell_source:${bestDirection.sell_source}`,
      `compatible:${input.evaluation.compatible}`,
      `freshness_age_ms:${freshnessAgeMs}`,
      `freshness_budget_ms:${freshnessBudgetMs}`,
      `stale_edge_expired:${penaltyBreakdown.staleEdgeExpired}`,
      `capital_fragmentation_penalty_bps:${penaltyBreakdown.capitalFragmentationPenaltyBps}`,
      `transfer_latency_penalty_bps:${penaltyBreakdown.transferLatencyPenaltyBps}`,
      `low_confidence_penalty_bps:${penaltyBreakdown.lowConfidencePenaltyBps}`,
      `stale_edge_penalty_bps:${penaltyBreakdown.staleEdgePenaltyBps}`,
      `fee_bps:${bestFees}`,
      `slippage_bps:${bestSlippage}`,
      `hedge_risk_bps:${bestHedgeRisk}`,
    ]),
  })
}

function buildArbPlan(input: {
  evaluation: CrossVenueEvaluationCore
  executableEdge: ExecutableEdge
  opportunityType: CrossVenueOpportunityType
}): ArbPlan {
  const sizeUsd = input.executableEdge.executable_edge_bps > 0
    ? Math.min(1_000, Math.max(100, input.executableEdge.executable_edge_bps * 10))
    : 100

  return arbPlanSchema.parse({
    arb_plan_id: `arb:${input.evaluation.canonical_event_id}:${input.executableEdge.buy_ref.venue}-${input.executableEdge.sell_ref.venue}`,
    canonical_event_id: input.evaluation.canonical_event_id,
    opportunity_type: input.opportunityType,
    executable_edge: input.executableEdge,
    legs: [
      {
        leg_id: `${input.executableEdge.edge_id}:buy`,
        venue: input.executableEdge.buy_ref.venue,
        market_id: input.executableEdge.buy_ref.market_id,
        side: 'yes',
        action: 'buy',
        price: input.executableEdge.buy_price_yes,
        size_usd: sizeUsd,
        max_slippage_bps: Math.max(5, input.executableEdge.slippage_bps),
        max_unhedged_leg_ms: 1_000,
      },
      {
        leg_id: `${input.executableEdge.edge_id}:sell`,
        venue: input.executableEdge.sell_ref.venue,
        market_id: input.executableEdge.sell_ref.market_id,
        side: 'yes',
        action: 'sell',
        price: input.executableEdge.sell_price_yes,
        size_usd: sizeUsd,
        max_slippage_bps: Math.max(5, input.executableEdge.slippage_bps),
        max_unhedged_leg_ms: 1_000,
      },
    ],
    required_capital_usd: sizeUsd,
    break_even_after_fees_bps: input.executableEdge.executable_edge_bps,
    max_unhedged_leg_ms: 1_000,
    exit_policy: 'close_on_hedge_completion_or_stale_edge',
    manual_review_required: input.evaluation.match.manual_review_required,
    notes: unique([
      `confidence_score:${input.evaluation.confidence_score.toFixed(4)}`,
      `opportunity_type:${input.opportunityType}`,
    ]),
  })
}

function classifyCrossVenueOpportunity(input: {
  left: MarketDescriptor
  right: MarketDescriptor
  evaluation: CrossVenueEvaluationCore
  executableEdge: ExecutableEdge | null
  arbitrageCandidate: CrossVenueArbitrageCandidate | null
}): CrossVenueOpportunityType {
  if (input.left.venue === input.right.venue) {
    return 'comparison_only'
  }

  if (input.evaluation.mismatch_reasons.some((reason) => HARD_BLOCKING_REASONS.has(reason))) {
    return 'comparison_only'
  }

  if (input.arbitrageCandidate?.executable && input.executableEdge?.executable_edge_bps != null && input.executableEdge.executable_edge_bps > 0) {
    return 'true_arbitrage'
  }

  if (input.evaluation.compatible) {
    return 'relative_value'
  }

  if (input.evaluation.match.manual_review_required || input.evaluation.confidence_score >= 0.5) {
    return 'cross_venue_signal'
  }

  return 'comparison_only'
}

function buildArbitrageCandidate(input: {
  evaluation: CrossVenueEvaluationCore
  minArbitrageSpreadBps: number
  executableEdge: ExecutableEdge | null
  marketEquivalenceProof: MarketEquivalenceProof
}): CrossVenueArbitrageCandidate | null {
  if (!input.evaluation.compatible || input.evaluation.match.manual_review_required) {
    return null
  }

  if (!input.executableEdge) {
    return null
  }

  const grossSpreadBps = roundBps(input.executableEdge.gross_spread_bps)
  if (grossSpreadBps < input.minArbitrageSpreadBps) {
    return null
  }

  if (input.executableEdge.notes.includes('stale_edge_expired:true')) {
    return null
  }

  const reasons: string[] = []
  const executable = input.executableEdge.executable
  if (!executable) {
    reasons.push('insufficient_orderbook_for_executable_spread')
  }

  const netSpreadBps = input.executableEdge.executable_edge_bps

  return {
    candidate_type: 'yes_yes_spread',
    opportunity_type: executable && netSpreadBps > 0 ? 'true_arbitrage' : 'relative_value',
    canonical_event_id: input.evaluation.canonical_event_id,
    canonical_event_key: input.evaluation.canonical_event_key,
    buy_ref: input.executableEdge.buy_ref,
    sell_ref: input.executableEdge.sell_ref,
    buy_price_yes: input.executableEdge.buy_price_yes,
    sell_price_yes: input.executableEdge.sell_price_yes,
    gross_spread_bps: grossSpreadBps,
    net_spread_bps: netSpreadBps,
    confidence_score: input.evaluation.confidence_score,
    executable,
    executable_edge: {
      ...input.executableEdge,
      opportunity_type: executable && netSpreadBps > 0 ? 'true_arbitrage' : 'relative_value',
    },
    market_equivalence_proof: input.marketEquivalenceProof,
    arb_plan: buildArbPlan({
      evaluation: input.evaluation,
      executableEdge: input.executableEdge,
      opportunityType: executable && netSpreadBps > 0 ? 'true_arbitrage' : 'relative_value',
    }),
    reasons,
  }
}

export function evaluateCrossVenuePair(input: CrossVenueEvaluationInput): CrossVenueEvaluation {
  const mismatchReasons: string[] = []
  const minSemanticScore = input.minSemanticScore ?? DEFAULT_MIN_SEMANTIC_SCORE
  const minCompatibilityScore = input.minCompatibilityScore ?? DEFAULT_MIN_COMPATIBILITY_SCORE
  const minArbitrageSpreadBps = input.minArbitrageSpreadBps ?? DEFAULT_MIN_ARBITRAGE_SPREAD_BPS
  const left = input.left
  const right = input.right

  if (left.venue === right.venue) {
    mismatchReasons.push('same_venue_pair')
  }

  const semanticSimilarityScore = getSemanticSimilarity(left, right, mismatchReasons)
  const resolutionCompatibilityScore = getResolutionCompatibility(left, right, mismatchReasons)
  const payoutCompatibilityScore = getPayoutCompatibility(left, right, mismatchReasons)
  const currencyCompatibilityScore = getCurrencyCompatibility(left, right, mismatchReasons)

  if (semanticSimilarityScore < minSemanticScore) {
    mismatchReasons.push('low_semantic_similarity')
  }

  if (hasNegationMarker(left.question) !== hasNegationMarker(right.question) && semanticSimilarityScore >= 0.45) {
    mismatchReasons.push('polarity_mismatch')
  }

  const confidenceScore = roundScore(
    (semanticSimilarityScore * 0.4) +
    (resolutionCompatibilityScore * 0.25) +
    (payoutCompatibilityScore * 0.2) +
    (currencyCompatibilityScore * 0.15),
  )

  const compatible = (
    left.venue !== right.venue &&
    semanticSimilarityScore >= minSemanticScore &&
    resolutionCompatibilityScore >= minCompatibilityScore &&
    payoutCompatibilityScore >= minCompatibilityScore &&
    currencyCompatibilityScore >= minCompatibilityScore &&
    !mismatchReasons.includes('proposition_subject_mismatch') &&
    !mismatchReasons.includes('time_horizon_mismatch') &&
    !mismatchReasons.includes('polarity_mismatch')
  )

  const canonicalEventKey = buildCanonicalEventKey([left, right])
  const canonicalEventId = buildCanonicalEventId([left, right])
  const manualReviewRequired = !compatible || confidenceScore < 0.85 || mismatchReasons.length > 0

  const match = crossVenueMatchSchema.parse({
    canonical_event_id: canonicalEventId,
    left_market_ref: makeMarketRef(left),
    right_market_ref: makeMarketRef(right),
    semantic_similarity_score: semanticSimilarityScore,
    resolution_compatibility_score: resolutionCompatibilityScore,
    payout_compatibility_score: payoutCompatibilityScore,
    currency_compatibility_score: currencyCompatibilityScore,
    manual_review_required: manualReviewRequired,
    notes: unique([
      `canonical_event_key:${canonicalEventKey}`,
      `confidence_score:${confidenceScore.toFixed(4)}`,
      ...mismatchReasons,
    ]),
  })

  const baseEvaluation = {
    canonical_event_id: canonicalEventId,
    canonical_event_key: canonicalEventKey,
    confidence_score: confidenceScore,
    compatible,
    mismatch_reasons: unique(mismatchReasons),
    match,
  }

  const marketEquivalenceProof = buildMarketEquivalenceProof({
    evaluation: baseEvaluation,
    left,
    right,
  })
  const executableEdge = buildExecutableEdge({
    evaluation: baseEvaluation,
    left,
    right,
    leftSnapshot: input.leftSnapshot,
    rightSnapshot: input.rightSnapshot,
    asOfAt: input.asOfAt,
  })
  const arbitrageCandidate = buildArbitrageCandidate({
    evaluation: baseEvaluation,
    minArbitrageSpreadBps,
    executableEdge,
    marketEquivalenceProof,
  })
  const opportunityType = classifyCrossVenueOpportunity({
    left,
    right,
    evaluation: baseEvaluation,
    executableEdge,
    arbitrageCandidate,
  })

  return {
    ...baseEvaluation,
    opportunity_type: opportunityType,
    market_equivalence_proof: {
      ...marketEquivalenceProof,
      proof_status: opportunityType === 'true_arbitrage'
        ? 'proven'
        : marketEquivalenceProof.proof_status,
    },
    executable_edge: executableEdge
      ? {
          ...executableEdge,
          opportunity_type: opportunityType,
        }
      : null,
    arbitrage_candidate: arbitrageCandidate
      ? {
          ...arbitrageCandidate,
          opportunity_type: opportunityType,
          executable_edge: {
            ...arbitrageCandidate.executable_edge,
            opportunity_type: opportunityType,
          },
          arb_plan: {
            ...arbitrageCandidate.arb_plan,
            opportunity_type: opportunityType,
          },
        }
      : null,
  }
}

export function findCrossVenueMatches(input: FindCrossVenueMatchesInput): CrossVenueEvaluation[] {
  const snapshotIndex = indexSnapshots(input.snapshots ?? [])
  const seen = new Set<string>()
  const evaluations: CrossVenueEvaluation[] = []

  for (let i = 0; i < input.markets.length; i += 1) {
    for (let j = i + 1; j < input.markets.length; j += 1) {
      const left = input.markets[i]
      const right = input.markets[j]
      if (left.venue === right.venue) continue

      const pairKey = [getSnapshotKey(left.venue, left.market_id), getSnapshotKey(right.venue, right.market_id)]
        .sort()
        .join('|')

      if (seen.has(pairKey)) continue
      seen.add(pairKey)

      const evaluation = evaluateCrossVenuePair({
        left,
        right,
        leftSnapshot: snapshotIndex.get(getSnapshotKey(left.venue, left.market_id)) ?? null,
        rightSnapshot: snapshotIndex.get(getSnapshotKey(right.venue, right.market_id)) ?? null,
        asOfAt: input.asOfAt,
        minSemanticScore: input.minSemanticScore,
        minCompatibilityScore: input.minCompatibilityScore,
        minArbitrageSpreadBps: input.minArbitrageSpreadBps,
      })

      if (evaluation.compatible || input.includeManualReview) {
        evaluations.push(evaluation)
      }
    }
  }

  return evaluations
    .sort((left, right) => {
      const rightArb = right.arbitrage_candidate?.gross_spread_bps ?? -1
      const leftArb = left.arbitrage_candidate?.gross_spread_bps ?? -1
      if (right.compatible !== left.compatible) return Number(right.compatible) - Number(left.compatible)
      if (rightArb !== leftArb) return rightArb - leftArb
      return right.confidence_score - left.confidence_score
    })
    .slice(0, input.maxPairs ?? evaluations.length)
}

export function detectCrossVenueArbitrageCandidates(
  evaluations: readonly CrossVenueEvaluation[],
): CrossVenueArbitrageCandidate[] {
  return evaluations
    .map((evaluation) => evaluation.arbitrage_candidate)
    .filter((candidate): candidate is CrossVenueArbitrageCandidate => candidate != null && candidate.opportunity_type === 'true_arbitrage')
    .sort((left, right) => right.net_spread_bps - left.net_spread_bps)
}

function hasHardBlockingReason(evaluation: CrossVenueEvaluation): boolean {
  return evaluation.mismatch_reasons.some((reason) => HARD_BLOCKING_REASONS.has(reason))
}

function uniquePush(target: string[], value: string) {
  if (!target.includes(value)) {
    target.push(value)
  }
}

export function summarizeCrossVenueIntelligence(
  evaluations: readonly CrossVenueEvaluation[],
): CrossVenueOpsSummary {
  const compatible: CrossVenueEvaluation[] = []
  const manualReview: CrossVenueEvaluation[] = []
  const comparisonOnly: CrossVenueEvaluation[] = []
  const blockingReasons: string[] = []
  const opportunityTypeCounts = Object.fromEntries(
    OPPORTUNITY_TYPES.map((type) => [type, 0]),
  ) as Record<CrossVenueOpportunityType, number>

  for (const evaluation of evaluations) {
    opportunityTypeCounts[evaluation.opportunity_type] += 1

    if (evaluation.compatible && !evaluation.match.manual_review_required) {
      compatible.push(evaluation)
      continue
    }

    if (hasHardBlockingReason(evaluation)) {
      manualReview.push(evaluation)
      for (const reason of evaluation.mismatch_reasons) {
        if (HARD_BLOCKING_REASONS.has(reason)) {
          uniquePush(blockingReasons, reason)
        }
      }
      continue
    }

    comparisonOnly.push(evaluation)
  }

  const highestConfidenceCandidate = detectCrossVenueArbitrageCandidates(compatible)
    .sort((left, right) => {
      if (right.confidence_score !== left.confidence_score) {
        return right.confidence_score - left.confidence_score
      }
      if (right.net_spread_bps !== left.net_spread_bps) {
        return right.net_spread_bps - left.net_spread_bps
      }
      return right.gross_spread_bps - left.gross_spread_bps
    })[0] ?? null

  return {
    total_pairs: evaluations.length,
    opportunity_type_counts: opportunityTypeCounts,
    compatible,
    manual_review: manualReview,
    comparison_only: comparisonOnly,
    blocking_reasons: blockingReasons,
    highest_confidence_candidate: highestConfidenceCandidate,
  }
}

export function buildCanonicalCrossVenueEventKey(markets: readonly MarketDescriptor[]): string {
  return buildCanonicalEventKey(markets)
}

export function buildCanonicalCrossVenueEventId(markets: readonly MarketDescriptor[]): string {
  return buildCanonicalEventId(markets)
}
