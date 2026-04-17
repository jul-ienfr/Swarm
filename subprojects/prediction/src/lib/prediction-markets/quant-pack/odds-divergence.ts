import { clamp, mean, round, tokenize, uniqueStrings } from './helpers'
import type { BookmakerQuote, MarketQuotePack } from './types'

export type OddsDivergenceAssessment = {
  read_only: true
  kind: 'odds_divergence'
  viable: boolean
  market_id: string | null
  question: string | null
  side: 'yes' | 'no' | 'neutral'
  market_yes_price: number
  market_no_price: number
  consensus_yes_prob: number
  consensus_no_prob: number
  sharp_yes_prob: number | null
  sharp_no_prob: number | null
  fair_value: number
  fee_rate: number
  edge: number
  edge_bps: number
  num_books: number
  sharp_books: string[]
  consensus_books: string[]
  blockers: string[]
  reasons: string[]
  summary: string
}

function isYesOutcome(outcome: string): boolean {
  const t = tokenize(outcome).join(' ')
  return /(^| )(yes|bull|long|positive|support|up|win)( |$)/.test(` ${t} `)
}

function isNoOutcome(outcome: string): boolean {
  const t = tokenize(outcome).join(' ')
  return /(^| )(no|bear|short|negative|oppose|down|lose)( |$)/.test(` ${t} `)
}

function impliedProbability(quote: BookmakerQuote): number {
  if (typeof quote.implied_prob === 'number' && Number.isFinite(quote.implied_prob)) {
    return clamp(quote.implied_prob, 0, 1)
  }
  if (quote.decimal_odds > 0) {
    return clamp(1 / quote.decimal_odds, 0, 1)
  }
  return 0
}

export function assessOddsDivergence(input: MarketQuotePack): OddsDivergenceAssessment {
  const feeRate = clamp(Number(input.fee_rate ?? 0.02), 0, 0.5)
  const marketYesPrice = clamp(Number(input.market_yes_price), 0, 1)
  const marketNoPrice = clamp(1 - marketYesPrice, 0, 1)
  const quotes = input.bookmaker_quotes ?? []
  const yesQuotes = quotes.filter((quote) => isYesOutcome(quote.outcome))
  const noQuotes = quotes.filter((quote) => isNoOutcome(quote.outcome))
  const consensusYesSource = yesQuotes.length > 0 ? yesQuotes : quotes
  const consensusNoSource = noQuotes.length > 0 ? noQuotes : []
  const consensusYesProb = clamp(mean(consensusYesSource.map(impliedProbability)), 0, 1)
  const consensusNoProb = clamp(
    consensusNoSource.length > 0 ? mean(consensusNoSource.map(impliedProbability)) : 1 - consensusYesProb,
    0,
    1,
  )
  const sharpYesSource = consensusYesSource.filter((quote) => Boolean(quote.is_sharp))
  const sharpNoSource = consensusNoSource.filter((quote) => Boolean(quote.is_sharp))
  const sharpYesProb = sharpYesSource.length > 0 ? clamp(mean(sharpYesSource.map(impliedProbability)), 0, 1) : null
  const sharpNoProb = sharpNoSource.length > 0 ? clamp(mean(sharpNoSource.map(impliedProbability)), 0, 1) : null
  const fairYes = sharpYesProb ?? consensusYesProb
  const fairNo = sharpNoProb ?? consensusNoProb
  const yesEdge = fairYes - marketYesPrice - feeRate
  const noEdge = fairNo - marketNoPrice - feeRate
  const side = yesEdge >= noEdge && yesEdge > 0 ? 'yes' : noEdge > 0 ? 'no' : 'neutral'
  const fairValue = side === 'yes' ? fairYes : side === 'no' ? fairNo : marketYesPrice
  const edge = side === 'yes' ? yesEdge : side === 'no' ? noEdge : 0
  const sharpBooks = uniqueStrings((sharpYesSource.length > 0 ? sharpYesSource : sharpNoSource).map((quote) => quote.bookmaker))
  const consensusBooks = uniqueStrings((consensusYesSource.length > 0 ? consensusYesSource : quotes).map((quote) => quote.bookmaker))
  const blockers = uniqueStrings([
    quotes.length === 0 ? 'no_bookmaker_quotes' : null,
    side === 'neutral' ? 'no_positive_divergence' : null,
    edge <= 0 ? 'edge_below_fee' : null,
  ])
  const reasons = uniqueStrings([
    `consensus_yes=${round(consensusYesProb, 4)}`,
    `consensus_no=${round(consensusNoProb, 4)}`,
    sharpYesProb != null ? `sharp_yes=${round(sharpYesProb, 4)}` : null,
    sharpNoProb != null ? `sharp_no=${round(sharpNoProb, 4)}` : null,
    `market_yes=${round(marketYesPrice, 4)}`,
    `market_no=${round(marketNoPrice, 4)}`,
  ])

  return {
    read_only: true,
    kind: 'odds_divergence',
    viable: blockers.length === 0,
    market_id: input.market_id ?? null,
    question: input.question ?? null,
    side,
    market_yes_price: round(marketYesPrice, 4),
    market_no_price: round(marketNoPrice, 4),
    consensus_yes_prob: round(consensusYesProb, 4),
    consensus_no_prob: round(consensusNoProb, 4),
    sharp_yes_prob: sharpYesProb == null ? null : round(sharpYesProb, 4),
    sharp_no_prob: sharpNoProb == null ? null : round(sharpNoProb, 4),
    fair_value: round(fairValue, 4),
    fee_rate: round(feeRate, 4),
    edge: round(edge, 4),
    edge_bps: round(edge * 10_000, 1),
    num_books: quotes.length,
    sharp_books: sharpBooks,
    consensus_books: consensusBooks,
    blockers,
    reasons,
    summary: side === 'neutral'
      ? `No actionable bookmaker divergence: consensus_yes=${round(consensusYesProb, 3)} market_yes=${round(marketYesPrice, 3)}`
      : `${side.toUpperCase()} divergence with edge=${round(edge * 10_000, 1)}bps across ${quotes.length} books`,
  }
}

export function scanOddsDivergence(markets: readonly MarketQuotePack[]): OddsDivergenceAssessment[] {
  return markets.map((market) => assessOddsDivergence(market))
}

