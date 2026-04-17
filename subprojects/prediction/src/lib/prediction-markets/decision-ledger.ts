import { randomUUID } from 'node:crypto'

export type DecisionLedgerEntryType =
  | 'BET_PLACED'
  | 'BET_SKIPPED'
  | 'BET_RESOLVED'
  | 'DEEP_CONFIRMED'
  | 'DEEP_REJECTED'
  | 'PARAM_CHANGED'
  | 'CALIBRATION_UPDATE'
  | 'CYCLE_SUMMARY'

export type DecisionLedgerEntry = {
  id: string
  timestamp: string
  entry_type: DecisionLedgerEntryType
  market_id: string
  question: string
  data: Record<string, unknown>
  explanation: string
  cycle_id: string
  tags: string[]
  actor: string | null
  source: string | null
  confidence: number | null
}

export type DecisionLedgerEntryDraft = {
  entry_type: DecisionLedgerEntryType
  market_id?: string | null
  question?: string | null
  data?: Record<string, unknown> | null
  explanation?: string | null
  cycle_id?: string | null
  tags?: readonly string[] | null
  actor?: string | null
  source?: string | null
  confidence?: number | null
  timestamp?: string | null
  id?: string | null
}

export type DecisionLedgerFilter = {
  entry_type?: DecisionLedgerEntryType | DecisionLedgerEntryType[] | null
  market_id?: string | null
  cycle_id?: string | null
  q?: string | null
  tag?: string | null
  limit?: number | null
  offset?: number | null
}

export type DecisionLedgerSummary = {
  total_entries: number
  entry_types: Record<DecisionLedgerEntryType, number>
  cycle_count: number
  market_count: number
  latest_entry: DecisionLedgerEntry | null
  latest_timestamp: string | null
  active_cycles: string[]
  active_markets: string[]
  confidence_mean: number | null
  explanation_samples: string[]
}

const ENTRY_TYPES: readonly DecisionLedgerEntryType[] = [
  'BET_PLACED',
  'BET_SKIPPED',
  'BET_RESOLVED',
  'DEEP_CONFIRMED',
  'DEEP_REJECTED',
  'PARAM_CHANGED',
  'CALIBRATION_UPDATE',
  'CYCLE_SUMMARY',
]

function normalizeText(value: unknown): string {
  return String(value ?? '').trim()
}

function normalizeTags(value: readonly string[] | null | undefined): string[] {
  const seen = new Set<string>()
  const tags: string[] = []
  for (const item of value ?? []) {
    const tag = normalizeText(item)
    if (!tag || seen.has(tag)) continue
    seen.add(tag)
    tags.push(tag)
  }
  return tags
}

function normalizeEntryType(value: string): DecisionLedgerEntryType {
  const upper = value.trim().toUpperCase() as DecisionLedgerEntryType
  if (!ENTRY_TYPES.includes(upper)) {
    throw new Error(`Unsupported decision ledger entry type: ${value}`)
  }
  return upper
}

function normalizeConfidence(value: number | null | undefined): number | null {
  if (value === null || value === undefined) return null
  if (!Number.isFinite(value)) return null
  return Math.min(1, Math.max(0, Number(value)))
}

export function createDecisionLedgerEntry(draft: DecisionLedgerEntryDraft): DecisionLedgerEntry {
  const entry_type = normalizeEntryType(String(draft.entry_type))
  return {
    id: normalizeText(draft.id) || `ledger_${randomUUID().slice(0, 12)}`,
    timestamp: normalizeText(draft.timestamp) || new Date().toISOString(),
    entry_type,
    market_id: normalizeText(draft.market_id),
    question: normalizeText(draft.question),
    data: { ...(draft.data ?? {}) },
    explanation: normalizeText(draft.explanation),
    cycle_id: normalizeText(draft.cycle_id) || 'manual',
    tags: normalizeTags(draft.tags),
    actor: normalizeText(draft.actor) || null,
    source: normalizeText(draft.source) || null,
    confidence: normalizeConfidence(draft.confidence),
  }
}

export function appendDecisionLedgerEntry(
  entries: readonly DecisionLedgerEntry[],
  draft: DecisionLedgerEntryDraft,
): { entry: DecisionLedgerEntry; entries: DecisionLedgerEntry[] } {
  const entry = createDecisionLedgerEntry(draft)
  return {
    entry,
    entries: [...entries, entry],
  }
}

export function parseDecisionLedgerJsonl(text: string): DecisionLedgerEntry[] {
  const entries: DecisionLedgerEntry[] = []
  for (const line of String(text ?? '').split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed) continue
    try {
      const payload = JSON.parse(trimmed) as Partial<DecisionLedgerEntry>
      if (!payload || typeof payload !== 'object') continue
      entries.push(
        createDecisionLedgerEntry({
          entry_type: normalizeEntryType(String(payload.entry_type ?? 'BET_SKIPPED')),
          id: payload.id ?? null,
          timestamp: payload.timestamp ?? null,
          market_id: payload.market_id ?? null,
          question: payload.question ?? null,
          data: (payload.data as Record<string, unknown> | undefined) ?? null,
          explanation: payload.explanation ?? null,
          cycle_id: payload.cycle_id ?? null,
          tags: payload.tags ?? null,
          actor: payload.actor ?? null,
          source: payload.source ?? null,
          confidence: payload.confidence ?? null,
        }),
      )
    } catch {
      continue
    }
  }
  return entries
}

export function serializeDecisionLedgerJsonl(entries: readonly DecisionLedgerEntry[]): string {
  return entries.map((entry) => JSON.stringify(entry)).join('\n')
}

export function filterDecisionLedgerEntries(
  entries: readonly DecisionLedgerEntry[],
  filter: DecisionLedgerFilter = {},
): DecisionLedgerEntry[] {
  const normalizedTypes = filter.entry_type
    ? (Array.isArray(filter.entry_type) ? filter.entry_type : [filter.entry_type]).map((value) => normalizeEntryType(String(value)))
    : null
  const query = normalizeText(filter.q).toLowerCase()
  const tag = normalizeText(filter.tag).toLowerCase()
  const marketId = normalizeText(filter.market_id)
  const cycleId = normalizeText(filter.cycle_id)
  let filtered = [...entries]
  if (normalizedTypes && normalizedTypes.length > 0) {
    filtered = filtered.filter((entry) => normalizedTypes.includes(entry.entry_type))
  }
  if (marketId) {
    filtered = filtered.filter((entry) => entry.market_id === marketId)
  }
  if (cycleId) {
    filtered = filtered.filter((entry) => entry.cycle_id === cycleId)
  }
  if (tag) {
    filtered = filtered.filter((entry) => entry.tags.some((item) => item.toLowerCase() === tag))
  }
  if (query) {
    filtered = filtered.filter((entry) => {
      const haystack = [
        entry.id,
        entry.timestamp,
        entry.entry_type,
        entry.market_id,
        entry.question,
        entry.explanation,
        entry.actor ?? '',
        entry.source ?? '',
        entry.cycle_id,
        ...entry.tags,
        JSON.stringify(entry.data),
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(query)
    })
  }
  const offset = Math.max(0, Number(filter.offset ?? 0) || 0)
  const limit = filter.limit == null ? undefined : Math.max(0, Number(filter.limit) || 0)
  const sliced = filtered.slice(offset)
  return limit == null ? sliced : sliced.slice(0, limit)
}

export function summarizeDecisionLedgerEntries(
  entries: readonly DecisionLedgerEntry[],
): DecisionLedgerSummary {
  let latest_entry: DecisionLedgerEntry | null = null
  let latest_index = -1
  const entry_types = ENTRY_TYPES.reduce((acc, entryType) => {
    acc[entryType] = 0
    return acc
  }, {} as Record<DecisionLedgerEntryType, number>)
  const cycleSet = new Set<string>()
  const marketSet = new Set<string>()
  let confidenceTotal = 0
  let confidenceCount = 0
  const explanationSamples: string[] = []

  entries.forEach((entry, index) => {
    entry_types[entry.entry_type] += 1
    if (entry.cycle_id) cycleSet.add(entry.cycle_id)
    if (entry.market_id) marketSet.add(entry.market_id)
    if (entry.confidence !== null && Number.isFinite(entry.confidence)) {
      confidenceTotal += entry.confidence
      confidenceCount += 1
    }
    if (entry.explanation && explanationSamples.length < 5) {
      explanationSamples.push(entry.explanation)
    }
    if (
      latest_entry === null
      || entry.timestamp > latest_entry.timestamp
      || (entry.timestamp === latest_entry.timestamp && index > latest_index)
    ) {
      latest_entry = entry
      latest_index = index
    }
  })

  return {
    total_entries: entries.length,
    entry_types,
    cycle_count: cycleSet.size,
    market_count: marketSet.size,
    latest_entry,
    latest_timestamp: latest_entry?.timestamp ?? null,
    active_cycles: [...cycleSet.values()],
    active_markets: [...marketSet.values()],
    confidence_mean: confidenceCount > 0 ? Number((confidenceTotal / confidenceCount).toFixed(4)) : null,
    explanation_samples: explanationSamples,
  }
}
