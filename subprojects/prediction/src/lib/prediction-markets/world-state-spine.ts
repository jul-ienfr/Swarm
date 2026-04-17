import {
  type PredictionMarketCatalystTimeline,
  type PredictionMarketCatalystTimelineInput,
  buildPredictionMarketCatalystTimeline,
} from './catalyst-timeline'
import {
  type PredictionMarketRulesLineage,
  type PredictionMarketRulesLineageInput,
  buildPredictionMarketRulesLineage,
} from './rules-lineage'
import {
  type PredictionMarketSourceAudit,
  type PredictionMarketSourceAuditInput,
  buildPredictionMarketSourceAudit,
} from './source-audit'
import {
  type PredictionMarketPriceSignal,
  type PredictionMarketWorldStateSnapshot,
  buildPredictionMarketWorldState,
} from './world-state'
import { type PredictionMarketTicketPayload, buildPredictionMarketTicketPayload } from './ticket-payload'

export interface PredictionMarketWorldStateSpineInput {
  market_id: string
  market_question: string
  venue?: string | null
  as_of?: string
  regime?: string | null
  source_audit: PredictionMarketSourceAuditInput
  rules_lineage: PredictionMarketRulesLineageInput
  catalyst_timeline: PredictionMarketCatalystTimelineInput
  price_signal?: PredictionMarketPriceSignal | null
  ticket_id?: string | null
  ticket_kind?: 'analysis' | 'approval' | 'execution' | null
  action?: 'bet' | 'wait' | 'no_trade' | 'escalate' | null
  size_usd?: number | null
  limit_price_yes?: number | null
  created_at?: string | null
  operator_notes?: string[] | null
}

export interface PredictionMarketWorldStateSpine {
  source_audit: PredictionMarketSourceAudit
  rules_lineage: PredictionMarketRulesLineage
  catalyst_timeline: PredictionMarketCatalystTimeline
  world_state: PredictionMarketWorldStateSnapshot
  ticket_payload: PredictionMarketTicketPayload
}

export function buildPredictionMarketWorldStateSpine(
  input: PredictionMarketWorldStateSpineInput,
): PredictionMarketWorldStateSpine {
  const source_audit = buildPredictionMarketSourceAudit(input.source_audit)
  const rules_lineage = buildPredictionMarketRulesLineage(input.rules_lineage)
  const catalyst_timeline = buildPredictionMarketCatalystTimeline(input.catalyst_timeline)
  const world_state = buildPredictionMarketWorldState({
    market_id: input.market_id,
    market_question: input.market_question,
    venue: input.venue,
    as_of: input.as_of,
    regime: input.regime,
    source_audit,
    rules_lineage,
    catalyst_timeline,
    price_signal: input.price_signal,
  })
  const ticket_payload = buildPredictionMarketTicketPayload({
    world_state,
    ticket_id: input.ticket_id,
    ticket_kind: input.ticket_kind,
    action: input.action,
    size_usd: input.size_usd,
    limit_price_yes: input.limit_price_yes,
    created_at: input.created_at,
    operator_notes: input.operator_notes,
  })

  return {
    source_audit,
    rules_lineage,
    catalyst_timeline,
    world_state,
    ticket_payload,
  }
}
