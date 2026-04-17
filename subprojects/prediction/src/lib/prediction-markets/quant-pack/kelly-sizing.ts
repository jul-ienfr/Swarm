import { clamp, round, uniqueStrings } from './helpers'
import type { KellySizingRequest } from './types'

export type KellySizingResult = {
  read_only: true
  kind: 'kelly_sizing'
  viable: boolean
  market_id: string | null
  question: string | null
  recommended_side: 'yes' | 'no' | 'neutral'
  probability_yes: number
  market_yes_price: number
  market_no_price: number
  fee_rate: number
  edge_yes: number
  edge_no: number
  kelly_full: number
  kelly_fractional: number
  bankroll_usd: number
  max_position_usd: number
  position_usd: number
  blockers: string[]
  reasons: string[]
  summary: string
}

function kellyForBinary(probability: number, price: number): number {
  if (!(probability >= 0 && probability <= 1)) return 0
  if (!(price > 0 && price < 1)) return 0
  const b = (1 - price) / price
  const q = 1 - probability
  if (b <= 0) return 0
  return (b * probability - q) / b
}

export function calculateKellySizing(input: KellySizingRequest): KellySizingResult {
  const probabilityYes = clamp(Number(input.probability_yes), 0, 1)
  const marketYesPrice = clamp(Number(input.market_yes_price), 0, 1)
  const marketNoPrice = clamp(1 - marketYesPrice, 0, 1)
  const bankrollUsd = Math.max(0, Number(input.bankroll_usd) || 0)
  const fractionalKelly = clamp(Number(input.fractional_kelly ?? 0.25), 0, 1)
  const maxPositionUsd = Math.max(0, Number(input.max_position_usd ?? bankrollUsd))
  const feeRate = clamp(Number(input.fee_rate ?? 0.02), 0, 0.5)
  const edgeYes = probabilityYes - marketYesPrice - feeRate
  const edgeNo = (1 - probabilityYes) - marketNoPrice - feeRate
  const recommendedSide = input.preferred_side ?? (edgeYes >= edgeNo && edgeYes > 0 ? 'yes' : edgeNo > 0 ? 'no' : 'neutral')
  const kellyFull = recommendedSide === 'yes'
    ? kellyForBinary(probabilityYes, marketYesPrice)
    : recommendedSide === 'no'
      ? kellyForBinary(1 - probabilityYes, marketNoPrice)
      : 0
  const kellyFractional = Math.max(0, kellyFull) * fractionalKelly
  const positionUsd = Math.min(bankrollUsd * kellyFractional, maxPositionUsd)
  const blockers = uniqueStrings([
    recommendedSide === 'neutral' ? 'no_positive_edge' : null,
    positionUsd <= 0 ? 'no_position' : null,
    marketYesPrice <= 0 || marketYesPrice >= 1 ? 'invalid_price' : null,
  ])
  const reasons = uniqueStrings([
    `probability_yes=${round(probabilityYes, 4)}`,
    `market_yes_price=${round(marketYesPrice, 4)}`,
    `market_no_price=${round(marketNoPrice, 4)}`,
    `edge_yes=${round(edgeYes, 4)}`,
    `edge_no=${round(edgeNo, 4)}`,
    `kelly_full=${round(kellyFull, 4)}`,
    `fractional_kelly=${round(fractionalKelly, 4)}`,
  ])

  return {
    read_only: true,
    kind: 'kelly_sizing',
    viable: blockers.length === 0,
    market_id: input.market_id ?? null,
    question: input.question ?? null,
    recommended_side: recommendedSide,
    probability_yes: round(probabilityYes, 4),
    market_yes_price: round(marketYesPrice, 4),
    market_no_price: round(marketNoPrice, 4),
    fee_rate: round(feeRate, 4),
    edge_yes: round(edgeYes, 4),
    edge_no: round(edgeNo, 4),
    kelly_full: round(Math.max(0, kellyFull), 4),
    kelly_fractional: round(kellyFractional, 4),
    bankroll_usd: round(bankrollUsd, 2),
    max_position_usd: round(maxPositionUsd, 2),
    position_usd: round(positionUsd, 2),
    blockers,
    reasons,
    summary: recommendedSide === 'neutral'
      ? 'No positive Kelly edge; stay flat.'
      : `Kelly ${recommendedSide.toUpperCase()} sizing recommends $${round(positionUsd, 2)} on a ${round((recommendedSide === 'yes' ? edgeYes : edgeNo) * 10_000, 1)}bps edge`,
  }
}

