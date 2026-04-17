import {
  average,
  compactParts,
  dedupeStrings,
  fingerprint,
  normalizeText,
  roundNumber,
} from './prediction-market-spine-utils'

export type PredictionMarketRuleStatus = 'active' | 'superseded' | 'conflicted' | 'draft'

export interface PredictionMarketRuleClauseInput {
  clause_id?: string | null
  rule_id: string
  title: string
  text: string
  source_refs?: string[] | null
  status?: PredictionMarketRuleStatus | null
  introduced_at?: string | null
  superseded_by?: string[] | null
}

export interface PredictionMarketRuleClause {
  clause_id: string
  rule_id: string
  title: string
  text: string
  status: PredictionMarketRuleStatus
  source_refs: string[]
  introduced_at: string | null
  superseded_by: string[]
  source_count: number
  fingerprint: string
}

export interface PredictionMarketRulesLineage {
  lineage_id: string
  market_id: string
  as_of: string
  rule_set_name: string
  clauses: PredictionMarketRuleClause[]
  active_clause_ids: string[]
  conflicted_clause_ids: string[]
  superseded_clause_ids: string[]
  canonical_rule_ids: string[]
  source_refs: string[]
  clause_fingerprints: string[]
  coherence_score: number
  summary: string
}

export interface PredictionMarketRulesLineageInput {
  market_id: string
  as_of?: string
  rule_set_name?: string
  clauses: PredictionMarketRuleClauseInput[]
}

function normalizeRuleStatus(status: PredictionMarketRuleStatus | null | undefined): PredictionMarketRuleStatus {
  if (status === 'active' || status === 'superseded' || status === 'conflicted' || status === 'draft') {
    return status
  }
  return 'draft'
}

export function buildPredictionMarketRulesLineage(
  input: PredictionMarketRulesLineageInput,
): PredictionMarketRulesLineage {
  const as_of = normalizeText(input.as_of) ?? new Date().toISOString()
  const rule_set_name = normalizeText(input.rule_set_name) ?? 'prediction-market-rule-set'

  const clauses = input.clauses
    .map<PredictionMarketRuleClause>((clause, index) => {
      const clause_id = normalizeText(clause.clause_id) ?? `${clause.rule_id}:${index + 1}`
      const rule_id = normalizeText(clause.rule_id) ?? `rule-${index + 1}`
      const title = normalizeText(clause.title) ?? rule_id
      const text = normalizeText(clause.text) ?? title
      const source_refs = dedupeStrings(clause.source_refs ?? [])
      const status = normalizeRuleStatus(clause.status)
      const introduced_at = normalizeText(clause.introduced_at)
      const superseded_by = dedupeStrings(clause.superseded_by ?? [])
      const fingerprintValue = fingerprint('rule-clause', {
        clause_id,
        rule_id,
        title,
        text,
        status,
        source_refs,
        introduced_at,
        superseded_by,
      })
      return {
        clause_id,
        rule_id,
        title,
        text,
        status,
        source_refs,
        introduced_at,
        superseded_by,
        source_count: source_refs.length,
        fingerprint: fingerprintValue,
      }
    })
    .sort((left, right) => {
      if (left.rule_id !== right.rule_id) {
        return left.rule_id.localeCompare(right.rule_id)
      }
      return left.clause_id.localeCompare(right.clause_id)
    })

  const active_clause_ids = clauses.filter((clause) => clause.status === 'active').map((clause) => clause.clause_id)
  const conflicted_clause_ids = clauses
    .filter((clause) => clause.status === 'conflicted')
    .map((clause) => clause.clause_id)
  const superseded_clause_ids = clauses
    .filter((clause) => clause.status === 'superseded')
    .map((clause) => clause.clause_id)
  const canonical_rule_ids = dedupeStrings(clauses.map((clause) => clause.rule_id))
  const source_refs = dedupeStrings(clauses.flatMap((clause) => clause.source_refs))
  const clause_fingerprints = clauses.map((clause) => clause.fingerprint)
  const lineage_id = fingerprint('rules-lineage', {
    market_id: input.market_id,
    as_of,
    rule_set_name,
    clause_fingerprints,
  })
  const coherence_score = roundNumber(
    Math.max(
      0,
      Math.min(
        1,
        average([
          clauses.length ? active_clause_ids.length / clauses.length : 0,
          clauses.length ? 1 - conflicted_clause_ids.length / clauses.length : 1,
          clauses.length ? 1 - superseded_clause_ids.length / clauses.length / 2 : 1,
        ]),
      ),
    ),
    4,
  )
  const summary = compactParts([
    `${clauses.length} clauses across ${canonical_rule_ids.length} rules`,
    `${active_clause_ids.length} active`,
    `${conflicted_clause_ids.length} conflicted`,
    `${superseded_clause_ids.length} superseded`,
    `coherence=${coherence_score.toFixed(2)}`,
  ])

  return {
    lineage_id,
    market_id: input.market_id,
    as_of,
    rule_set_name,
    clauses,
    active_clause_ids,
    conflicted_clause_ids,
    superseded_clause_ids,
    canonical_rule_ids,
    source_refs,
    clause_fingerprints,
    coherence_score,
    summary,
  }
}
