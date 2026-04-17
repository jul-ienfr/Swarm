import type { CalibrationReport } from '@/lib/prediction-markets/calibration'
import type { DecisionLedgerEntry, DecisionLedgerSummary } from '@/lib/prediction-markets/decision-ledger'
import { getPredictionMarketP1BRuntimeSummary } from '@/lib/prediction-markets/external-runtime'

export type AutopilotCycleStage =
  | 'scan'
  | 'research'
  | 'forecast'
  | 'ticket'
  | 'approval'
  | 'execution'
  | 'reconcile'
  | 'monitor'
  | 'unknown'

export type AutopilotCycleStatus =
  | 'queued'
  | 'running'
  | 'blocked'
  | 'approved'
  | 'executed'
  | 'resolved'
  | 'failed'
  | 'skipped'

export type AutopilotCycleRecord = {
  cycle_id: string
  stage: AutopilotCycleStage
  status: AutopilotCycleStatus
  market_id: string | null
  action_type: string | null
  edge_bps: number | null
  pnl_usd: number | null
  cost_usd: number | null
  confidence: number | null
  created_at: string | null
  completed_at: string | null
  blocked_reason: string | null
  note: string | null
}

export type AutopilotCycleSummary = {
  cycle_id: string
  status: AutopilotCycleStatus
  stage_counts: Record<AutopilotCycleStage, number>
  status_counts: Record<AutopilotCycleStatus, number>
  action_counts: Record<string, number>
  record_count: number
  market_count: number
  blocked_count: number
  approval_count: number
  execution_count: number
  resolved_count: number
  skipped_count: number
  edge_bps_mean: number | null
  pnl_usd_total: number
  cost_usd_total: number
  roi_pct: number | null
  confidence_mean: number | null
  calibration_error: number | null
  ledger_entries: DecisionLedgerSummary | null
  notes: string[]
  first_created_at: string | null
  last_completed_at: string | null
  health: 'healthy' | 'degraded' | 'blocked'
}

export type AutopilotCycleSummaryReport = {
  total_cycles: number
  total_records: number
  cycles: AutopilotCycleSummary[]
  overview: {
    health: 'healthy' | 'degraded' | 'blocked'
    blocked_cycles: number
    executed_cycles: number
    resolved_cycles: number
    mean_roi_pct: number | null
    mean_edge_bps: number | null
    mean_calibration_error: number | null
  }
}

const STAGE_VALUES: readonly AutopilotCycleStage[] = ['scan', 'research', 'forecast', 'ticket', 'approval', 'execution', 'reconcile', 'monitor', 'unknown']
const STATUS_VALUES: readonly AutopilotCycleStatus[] = ['queued', 'running', 'blocked', 'approved', 'executed', 'resolved', 'failed', 'skipped']

function normalizeText(value: unknown): string {
  return String(value ?? '').trim()
}

function normalizeStage(value: string | null | undefined): AutopilotCycleStage {
  const normalized = normalizeText(value).toLowerCase() as AutopilotCycleStage
  return STAGE_VALUES.includes(normalized) ? normalized : 'unknown'
}

function normalizeStatus(value: string | null | undefined): AutopilotCycleStatus {
  const normalized = normalizeText(value).toLowerCase() as AutopilotCycleStatus
  return STATUS_VALUES.includes(normalized) ? normalized : 'queued'
}

function normalizeNumber(value: unknown): number | null {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function emptyStageCounts(): Record<AutopilotCycleStage, number> {
  return {
    scan: 0,
    research: 0,
    forecast: 0,
    ticket: 0,
    approval: 0,
    execution: 0,
    reconcile: 0,
    monitor: 0,
    unknown: 0,
  }
}

function emptyStatusCounts(): Record<AutopilotCycleStatus, number> {
  return {
    queued: 0,
    running: 0,
    blocked: 0,
    approved: 0,
    executed: 0,
    resolved: 0,
    failed: 0,
    skipped: 0,
  }
}

export function buildAutopilotCycleRecord(input: {
  cycle_id: string
  stage?: AutopilotCycleStage | string | null
  status?: AutopilotCycleStatus | string | null
  market_id?: string | null
  action_type?: string | null
  edge_bps?: number | null
  pnl_usd?: number | null
  cost_usd?: number | null
  confidence?: number | null
  created_at?: string | null
  completed_at?: string | null
  blocked_reason?: string | null
  note?: string | null
}): AutopilotCycleRecord {
  return {
    cycle_id: normalizeText(input.cycle_id) || 'manual',
    stage: normalizeStage(input.stage),
    status: normalizeStatus(input.status),
    market_id: normalizeText(input.market_id) || null,
    action_type: normalizeText(input.action_type) || null,
    edge_bps: normalizeNumber(input.edge_bps),
    pnl_usd: normalizeNumber(input.pnl_usd),
    cost_usd: normalizeNumber(input.cost_usd),
    confidence: normalizeNumber(input.confidence),
    created_at: normalizeText(input.created_at) || null,
    completed_at: normalizeText(input.completed_at) || null,
    blocked_reason: normalizeText(input.blocked_reason) || null,
    note: normalizeText(input.note) || null,
  }
}

export function buildAutopilotCycleSummary(
  records: readonly AutopilotCycleRecord[],
  options: {
    cycle_id?: string | null
    calibration_report?: CalibrationReport | null
    ledger_entries?: DecisionLedgerEntry[] | null
  } = {},
): AutopilotCycleSummary {
  const normalizedCycleId = normalizeText(options.cycle_id) || records[0]?.cycle_id || 'manual'
  const stage_counts = emptyStageCounts()
  const status_counts = emptyStatusCounts()
  const action_counts: Record<string, number> = {}
  const marketSet = new Set<string>()
  let blocked_count = 0
  let approval_count = 0
  let execution_count = 0
  let resolved_count = 0
  let skipped_count = 0
  let pnl_usd_total = 0
  let cost_usd_total = 0
  let edge_sum = 0
  let edge_count = 0
  let confidence_sum = 0
  let confidence_count = 0
  let first_created_at: string | null = null
  let last_completed_at: string | null = null
  const notes: string[] = []

  for (const record of records) {
    if (record.cycle_id !== normalizedCycleId) continue
    stage_counts[record.stage] += 1
    status_counts[record.status] += 1
    if (record.action_type) action_counts[record.action_type] = (action_counts[record.action_type] || 0) + 1
    if (record.market_id) marketSet.add(record.market_id)
    if (record.status === 'blocked') blocked_count += 1
    if (record.status === 'approved') approval_count += 1
    if (record.status === 'executed') execution_count += 1
    if (record.status === 'resolved') resolved_count += 1
    if (record.status === 'skipped') skipped_count += 1
    if (record.pnl_usd !== null) pnl_usd_total += record.pnl_usd
    if (record.cost_usd !== null) cost_usd_total += record.cost_usd
    if (record.edge_bps !== null) {
      edge_sum += record.edge_bps
      edge_count += 1
    }
    if (record.confidence !== null) {
      confidence_sum += record.confidence
      confidence_count += 1
    }
    if (record.created_at && (first_created_at === null || record.created_at < first_created_at)) {
      first_created_at = record.created_at
    }
    if (record.completed_at && (last_completed_at === null || record.completed_at > last_completed_at)) {
      last_completed_at = record.completed_at
    }
    if (record.blocked_reason) {
      notes.push(record.blocked_reason)
    }
    if (record.note) {
      notes.push(record.note)
    }
  }

  const record_count = Object.values(status_counts).reduce((sum, value) => sum + value, 0)
  const roi_pct = cost_usd_total > 0 ? Number(((pnl_usd_total / cost_usd_total) * 100).toFixed(4)) : null
  const edge_bps_mean = edge_count > 0 ? Number((edge_sum / edge_count).toFixed(4)) : null
  const confidence_mean = confidence_count > 0 ? Number((confidence_sum / confidence_count).toFixed(4)) : null
  const calibration_error = options.calibration_report?.calibration_error ?? null
  const ledgerSummary = options.ledger_entries ? summarizeLedgerForCycle(options.ledger_entries, normalizedCycleId) : null

  const health = blocked_count > 0 && execution_count === 0
    ? 'blocked'
    : (execution_count > 0 || resolved_count > 0)
      ? 'healthy'
      : 'degraded'

  if (calibration_error !== null && calibration_error >= 0.15) {
    notes.push('material_calibration_error')
  }
  if (ledgerSummary && ledgerSummary.total_entries === 0) {
    notes.push('no_ledger_entries')
  }
  if (record_count > 0) {
    notes.push(`external_governance:${getPredictionMarketP1BRuntimeSummary({
      operator_thesis_present: false,
      research_pipeline_trace_present: true,
    }).summary}`)
  }

  return {
    cycle_id: normalizedCycleId,
    status: (status_counts.executed > 0
      ? 'executed'
      : status_counts.resolved > 0
        ? 'resolved'
        : status_counts.blocked > 0
          ? 'blocked'
          : status_counts.approved > 0
            ? 'approved'
            : status_counts.running > 0
              ? 'running'
              : status_counts.failed > 0
                ? 'failed'
                : status_counts.skipped > 0
                  ? 'skipped'
                  : 'queued') as AutopilotCycleStatus,
    stage_counts,
    status_counts,
    action_counts,
    record_count,
    market_count: marketSet.size,
    blocked_count,
    approval_count,
    execution_count,
    resolved_count,
    skipped_count,
    edge_bps_mean,
    pnl_usd_total: Number(pnl_usd_total.toFixed(4)),
    cost_usd_total: Number(cost_usd_total.toFixed(4)),
    roi_pct,
    confidence_mean,
    calibration_error,
    ledger_entries: ledgerSummary,
    notes: Array.from(new Set(notes)).slice(0, 10),
    first_created_at,
    last_completed_at,
    health,
  }
}

export function summarizeAutopilotCycles(
  records: readonly AutopilotCycleRecord[],
  options: {
    calibration_report?: CalibrationReport | null
    ledger_entries?: DecisionLedgerEntry[] | null
  } = {},
): AutopilotCycleSummaryReport {
  const cycles = new Map<string, AutopilotCycleRecord[]>()
  for (const record of records) {
    const cycleId = normalizeText(record.cycle_id) || 'manual'
    const bucket = cycles.get(cycleId) || []
    bucket.push(record)
    cycles.set(cycleId, bucket)
  }

  const summaries = [...cycles.entries()].map(([cycleId, cycleRecords]) =>
    buildAutopilotCycleSummary(cycleRecords, {
      cycle_id: cycleId,
      calibration_report: options.calibration_report ?? null,
      ledger_entries: options.ledger_entries ?? null,
    }),
  )

  const total_records = records.length
  const blocked_cycles = summaries.filter((summary) => summary.health === 'blocked').length
  const executed_cycles = summaries.filter((summary) => summary.execution_count > 0).length
  const resolved_cycles = summaries.filter((summary) => summary.resolved_count > 0).length
  const mean_roi_pct = summaries.length > 0
    ? Number((summaries.reduce((sum, summary) => sum + (summary.roi_pct ?? 0), 0) / summaries.length).toFixed(4))
    : null
  const mean_edge_bps = summaries.length > 0
    ? Number((summaries.reduce((sum, summary) => sum + (summary.edge_bps_mean ?? 0), 0) / summaries.length).toFixed(4))
    : null
  const mean_calibration_error = options.calibration_report?.calibration_error ?? null

  const overviewHealth: AutopilotCycleSummaryReport['overview']['health'] = blocked_cycles > 0
    ? 'blocked'
    : executed_cycles > 0
      ? 'healthy'
      : 'degraded'

  return {
    total_cycles: summaries.length,
    total_records,
    cycles: summaries,
    overview: {
      health: overviewHealth,
      blocked_cycles,
      executed_cycles,
      resolved_cycles,
      mean_roi_pct,
      mean_edge_bps,
      mean_calibration_error,
    },
  }
}

export function ledgerEntriesToAutopilotRecords(entries: readonly DecisionLedgerEntry[]): AutopilotCycleRecord[] {
  return entries.map((entry) => buildAutopilotCycleRecord({
    cycle_id: entry.cycle_id,
    stage: normalizeStage(String(entry.data.stage ?? entry.data.stage_name ?? 'unknown')),
    status: normalizeStatus(String(entry.data.status ?? entry.data.entry_status ?? 'queued')),
    market_id: String(entry.market_id || entry.data.market_id || ''),
    action_type: String(entry.data.action_type ?? entry.entry_type),
    edge_bps: entry.data.edge_bps as number | null,
    pnl_usd: entry.data.pnl_usd as number | null,
    cost_usd: entry.data.cost_usd as number | null,
    confidence: entry.confidence,
    created_at: entry.timestamp,
    completed_at: typeof entry.data.completed_at === 'string' ? entry.data.completed_at : null,
    blocked_reason: typeof entry.data.blocked_reason === 'string' ? entry.data.blocked_reason : null,
    note: entry.explanation,
  }))
}

function summarizeLedgerForCycle(entries: readonly DecisionLedgerEntry[], cycle_id: string): DecisionLedgerSummary {
  const matching = entries.filter((entry) => entry.cycle_id === cycle_id)
  let latestEntry: DecisionLedgerEntry | null = null
  let latestIndex = -1
  matching.forEach((entry, index) => {
    if (
      latestEntry === null
      || entry.timestamp > latestEntry.timestamp
      || (entry.timestamp === latestEntry.timestamp && index > latestIndex)
    ) {
      latestEntry = entry
      latestIndex = index
    }
  })
  return {
    total_entries: matching.length,
    entry_types: matching.reduce((acc, entry) => {
      acc[entry.entry_type] = (acc[entry.entry_type] || 0) + 1
      return acc
    }, {} as Record<string, number>) as DecisionLedgerSummary['entry_types'],
    cycle_count: new Set(matching.map((entry) => entry.cycle_id)).size,
    market_count: new Set(matching.map((entry) => entry.market_id).filter(Boolean)).size,
    latest_entry: latestEntry,
    latest_timestamp: latestEntry?.timestamp ?? null,
    active_cycles: [...new Set(matching.map((entry) => entry.cycle_id))],
    active_markets: [...new Set(matching.map((entry) => entry.market_id).filter(Boolean))],
    confidence_mean: matching.length > 0
      ? Number((matching.reduce((sum, entry) => sum + (entry.confidence ?? 0), 0) / matching.length).toFixed(4))
      : null,
    explanation_samples: matching.slice(0, 5).map((entry) => entry.explanation),
  }
}
