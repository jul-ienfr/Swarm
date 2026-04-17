import {
  clampNumber,
  compactParts,
  dedupeStrings,
  fingerprint,
  normalizeText,
  roundNumber,
  toFiniteNumber,
} from './prediction-market-spine-utils'
import type {
  PredictionMarketWorldStateRecommendation,
  PredictionMarketWorldStateSnapshot,
} from './world-state'

export type PredictionMarketTicketAction = PredictionMarketWorldStateRecommendation | 'escalate'
export type PredictionMarketTicketSide = 'yes' | 'no' | null
export type PredictionMarketTicketWorkflowStage = 'analysis' | 'approval' | 'execution'

export interface PredictionMarketTicketPayloadInput {
  world_state: PredictionMarketWorldStateSnapshot
  ticket_id?: string | null
  ticket_kind?: PredictionMarketTicketWorkflowStage | null
  action?: PredictionMarketTicketAction | null
  side?: PredictionMarketTicketSide
  size_usd?: number | null
  limit_price_yes?: number | null
  created_at?: string | null
  operator_notes?: string[] | null
}

export interface PredictionMarketTicketPayload {
  ticket_id: string
  ticket_kind: PredictionMarketTicketWorkflowStage
  market_id: string
  world_state_id: string
  action: PredictionMarketTicketAction
  side: PredictionMarketTicketSide
  size_usd: number
  limit_price_yes: number | null
  confidence: number
  edge_bps: number
  risk_flags: string[]
  source_refs: string[]
  rule_refs: string[]
  catalyst_refs: string[]
  rationale: string[]
  summary: string
  created_at: string
  world_state_summary: string
  fingerprint: string
}

export function buildPredictionMarketTicketPayload(
  input: PredictionMarketTicketPayloadInput,
): PredictionMarketTicketPayload {
  const world_state = input.world_state
  const action = input.action ?? world_state.recommended_action
  const ticket_kind = input.ticket_kind ?? (action === 'bet' ? 'approval' : 'analysis')
  const side = input.side ?? world_state.recommended_side
  const created_at = normalizeText(input.created_at) ?? world_state.as_of
  const edge_bps = world_state.market_gap_bps ?? 0
  const size_usd = roundNumber(
    clampNumber(toFiniteNumber(input.size_usd, action === 'bet' ? Math.max(10, 50 + Math.abs(edge_bps) / 40) : 0), 0, 10_000),
    2,
  )
  const limit_price_yes =
    typeof input.limit_price_yes === 'number' && Number.isFinite(input.limit_price_yes)
      ? roundNumber(clampNumber(input.limit_price_yes, 0, 1), 4)
      : world_state.market_gap_yes !== null && side === 'yes'
        ? roundNumber(clampNumber((world_state.market_gap_yes ?? 0) + 0.5, 0, 1), 4)
        : null

  const risk_flags = dedupeStrings([
    ...world_state.risk_flags,
    action === 'escalate' ? 'requires_escalation' : null,
    ticket_kind === 'approval' && action === 'wait' ? 'approval_wait' : null,
  ])
  const source_refs = dedupeStrings([
    world_state.world_state_id,
    ...world_state.source_refs,
    world_state.source_audit.audit_id,
    world_state.rules_lineage.lineage_id,
    world_state.catalyst_timeline.timeline_id,
  ])
  const rule_refs = dedupeStrings([
    ...world_state.rules_lineage.canonical_rule_ids,
    ...world_state.rules_lineage.clause_fingerprints,
  ])
  const catalyst_refs = dedupeStrings(world_state.catalyst_timeline.events.map((event) => event.catalyst_id))
  const rationale = dedupeStrings([
    world_state.recommendation_reason,
    `World-state bias: ${world_state.bias}.`,
    `Source alignment: ${world_state.source_alignment_score.toFixed(2)}.`,
    `Rule clarity: ${world_state.rule_clarity_score.toFixed(2)}.`,
    `Catalyst pressure: ${world_state.catalyst_pressure_score.toFixed(2)}.`,
    input.operator_notes?.length ? `Operator notes: ${input.operator_notes.join(' | ')}` : null,
  ])
  const summary = compactParts([
    `${ticket_kind} ticket`,
    `action=${action}`,
    side ? `side=${side}` : null,
    `edge=${edge_bps}bps`,
    `size=$${size_usd.toFixed(2)}`,
    world_state.market_question,
  ])
  const ticket_id = normalizeText(input.ticket_id) ?? `${world_state.world_state_id}:${ticket_kind}:${action}`

  return {
    ticket_id,
    ticket_kind,
    market_id: world_state.market_id,
    world_state_id: world_state.world_state_id,
    action,
    side,
    size_usd,
    limit_price_yes,
    confidence: world_state.confidence_score,
    edge_bps,
    risk_flags,
    source_refs,
    rule_refs,
    catalyst_refs,
    rationale,
    summary,
    created_at,
    world_state_summary: world_state.summary,
    fingerprint: fingerprint('prediction-ticket', {
      ticket_id,
      ticket_kind,
      market_id: world_state.market_id,
      world_state_id: world_state.world_state_id,
      action,
      side,
      size_usd,
      limit_price_yes,
      confidence: world_state.confidence_score,
      edge_bps,
      risk_flags,
      source_refs,
      rule_refs,
      catalyst_refs,
      created_at,
    }),
  }
}
