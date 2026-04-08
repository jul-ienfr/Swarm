type RunRow = {
  run_id: string
  source_run_id: string | null
  workspace_id: number
  venue: string
  mode: string
  market_id: string
  market_slug: string | null
  status: 'running' | 'completed' | 'failed'
  recommendation: 'bet' | 'no_trade' | 'wait' | null
  side: 'yes' | 'no' | null
  confidence: number | null
  probability_yes: number | null
  market_price_yes: number | null
  edge_bps: number | null
  manifest_json: string
  artifact_index_json: string
  created_at: number
  updated_at: number
}

type ArtifactRow = {
  artifact_id: string
  workspace_id: number
  run_id: string
  artifact_type: string
  sha256: string
  payload_json: string
  created_at: number
}

export type PredictionMarketDashboardLiveIntentStatus = 'pending_approval' | 'approved' | 'rejected'

export type PredictionMarketDashboardLiveIntentRow = {
  intent_id: string
  workspace_id: number
  run_id: string
  venue: string
  status: PredictionMarketDashboardLiveIntentStatus
  created_by: string
  approved_by: string | null
  rejected_by: string | null
  created_at: number
  updated_at: number
  approved_at: number | null
  rejected_at: number | null
  selected_path: string | null
  selected_preview_json: string | null
  benchmark_gate_summary: string | null
  benchmark_gate_blockers_json: string
  benchmark_promotion_ready: boolean
  live_route_allowed: boolean
  expected_action: string
  summary: string
  approval_note: string | null
  rejection_reason: string | null
}

export type PredictionMarketDashboardEventSeverity = 'info' | 'warn' | 'error' | 'success'

export type PredictionMarketDashboardEventRow = {
  event_id: string
  workspace_id: number
  event_type: string
  intent_id: string | null
  run_id: string | null
  venue: string | null
  actor: string | null
  severity: PredictionMarketDashboardEventSeverity
  summary: string
  payload_json: string
  created_at: number
}

type DbState = {
  runs: Map<string, RunRow>
  artifacts: Map<string, ArtifactRow>
  liveIntents: Map<string, PredictionMarketDashboardLiveIntentRow>
  dashboardEvents: PredictionMarketDashboardEventRow[]
  tick: number
}

const STATES = new Map<string, DbState>()

function resolveStateKey() {
  return process.env.PREDICTION_DB_PATH ?? 'prediction:test'
}

function getState(): DbState {
  const key = resolveStateKey()
  const existing = STATES.get(key)
  if (existing) return existing

  const state: DbState = {
    runs: new Map(),
    artifacts: new Map(),
    liveIntents: new Map(),
    dashboardEvents: [],
    tick: 1,
  }
  STATES.set(key, state)
  return state
}

function nextTick(state: DbState) {
  const value = state.tick
  state.tick += 1
  return value
}

function cloneLiveIntent(row: PredictionMarketDashboardLiveIntentRow): PredictionMarketDashboardLiveIntentRow {
  return {
    ...row,
    benchmark_gate_blockers_json: row.benchmark_gate_blockers_json,
  }
}

function cloneDashboardEvent(row: PredictionMarketDashboardEventRow): PredictionMarketDashboardEventRow {
  return {
    ...row,
    payload_json: row.payload_json,
  }
}

export function upsertPredictionMarketDashboardLiveIntent(
  row: PredictionMarketDashboardLiveIntentRow,
): PredictionMarketDashboardLiveIntentRow {
  const state = getState()
  const nextRow = cloneLiveIntent(row)
  state.liveIntents.set(nextRow.intent_id, nextRow)
  return cloneLiveIntent(nextRow)
}

export function getPredictionMarketDashboardLiveIntent(
  intentId: string,
  workspaceId: number,
): PredictionMarketDashboardLiveIntentRow | null {
  const state = getState()
  const row = state.liveIntents.get(intentId)
  if (!row || row.workspace_id !== workspaceId) return null
  return cloneLiveIntent(row)
}

export function listPredictionMarketDashboardLiveIntents(
  workspaceId: number,
  input: {
    runId?: string
    status?: PredictionMarketDashboardLiveIntentStatus
    limit?: number
  } = {},
): PredictionMarketDashboardLiveIntentRow[] {
  const state = getState()
  const limit = input.limit ?? 25
  return [...state.liveIntents.values()]
    .filter((row) =>
      row.workspace_id === workspaceId
      && (input.runId == null || row.run_id === input.runId)
      && (input.status == null || row.status === input.status))
    .sort((left, right) => right.updated_at - left.updated_at)
    .slice(0, limit)
    .map((row) => cloneLiveIntent(row))
}

export function appendPredictionMarketDashboardEvent(
  row: PredictionMarketDashboardEventRow,
): PredictionMarketDashboardEventRow {
  const state = getState()
  const nextRow = cloneDashboardEvent(row)
  state.dashboardEvents.push(nextRow)
  if (state.dashboardEvents.length > 400) {
    state.dashboardEvents.splice(0, state.dashboardEvents.length - 400)
  }
  return cloneDashboardEvent(nextRow)
}

export function listPredictionMarketDashboardEvents(
  workspaceId: number,
  input: {
    runId?: string
    intentId?: string
    limit?: number
  } = {},
): PredictionMarketDashboardEventRow[] {
  const state = getState()
  const limit = input.limit ?? 100
  return state.dashboardEvents
    .filter((row) =>
      row.workspace_id === workspaceId
      && (input.runId == null || row.run_id === input.runId)
      && (input.intentId == null || row.intent_id === input.intentId))
    .sort((left, right) => left.created_at - right.created_at)
    .slice(-limit)
    .map((row) => cloneDashboardEvent(row))
}

class Statement {
  constructor(
    private readonly state: DbState,
    private readonly sql: string,
  ) {}

  run(...args: any[]) {
    if (this.sql.includes('INSERT OR REPLACE INTO prediction_market_artifacts')) {
      const [artifact_id, workspace_id, run_id, artifact_type, sha256, payload_json] = args
      const existing = this.state.artifacts.get(artifact_id)
      this.state.artifacts.set(artifact_id, {
        artifact_id,
        workspace_id,
        run_id,
        artifact_type,
        sha256,
        payload_json,
        created_at: existing?.created_at ?? nextTick(this.state),
      })
      return { changes: 1 }
    }

    if (this.sql.includes('INSERT INTO prediction_market_runs')) {
      const [
        run_id,
        source_run_id,
        workspace_id,
        venue,
        mode,
        market_id,
        market_slug,
        status,
        recommendation,
        side,
        confidence,
        probability_yes,
        market_price_yes,
        edge_bps,
        manifest_json,
        artifact_index_json,
        created_at,
        updated_at,
      ] = args

      const existing = this.state.runs.get(run_id)
      this.state.runs.set(run_id, {
        run_id,
        source_run_id,
        workspace_id,
        venue,
        mode,
        market_id,
        market_slug,
        status,
        recommendation,
        side,
        confidence,
        probability_yes,
        market_price_yes,
        edge_bps,
        manifest_json,
        artifact_index_json,
        created_at: existing?.created_at ?? created_at ?? nextTick(this.state),
        updated_at: updated_at ?? nextTick(this.state),
      })
      return { changes: 1 }
    }

    throw new Error(`Unsupported run() SQL in prediction db shim: ${this.sql}`)
  }

  get(...args: any[]) {
    if (this.sql.includes('FROM prediction_market_runs') && this.sql.includes('WHERE run_id = ? AND workspace_id = ?')) {
      const [runId, workspaceId] = args
      const row = this.state.runs.get(runId)
      return row && row.workspace_id === workspaceId ? { ...row } : undefined
    }

    throw new Error(`Unsupported get() SQL in prediction db shim: ${this.sql}`)
  }

  all(...args: any[]) {
    if (this.sql.includes('FROM prediction_market_artifacts')) {
      const [runId, workspaceId] = args
      return [...this.state.artifacts.values()]
        .filter((row) => row.run_id === runId && row.workspace_id === workspaceId)
        .sort((a, b) => a.created_at - b.created_at)
        .map((row) => ({ ...row }))
    }

    if (this.sql.includes("status = 'completed'")) {
      const [workspaceId, venue, marketId, mode] = args
      return [...this.state.runs.values()]
        .filter((row) =>
          row.workspace_id === workspaceId
          && row.venue === venue
          && row.market_id === marketId
          && row.mode === mode
          && row.status === 'completed')
        .sort((a, b) => b.updated_at - a.updated_at)
        .slice(0, 25)
        .map((row) => ({ ...row }))
    }

    if (this.sql.includes('FROM prediction_market_runs')) {
      const [workspaceId, ...rest] = args
      const limit = Number(rest.at(-1) ?? 20)
      const maybeVenue = this.sql.includes('AND venue = ?') ? rest.shift() : undefined
      const maybeRecommendation = this.sql.includes('AND recommendation = ?') ? rest.shift() : undefined

      return [...this.state.runs.values()]
        .filter((row) =>
          row.workspace_id === workspaceId
          && (maybeVenue === undefined || row.venue === maybeVenue)
          && (maybeRecommendation === undefined || row.recommendation === maybeRecommendation))
        .sort((a, b) => b.created_at - a.created_at)
        .slice(0, limit)
        .map((row) => ({ ...row }))
    }

    throw new Error(`Unsupported all() SQL in prediction db shim: ${this.sql}`)
  }
}

class PredictionTestDatabase {
  constructor(private readonly state: DbState) {}

  prepare(sql: string) {
    return new Statement(this.state, sql)
  }

  transaction<T>(fn: () => T) {
    return () => fn()
  }
}

export function getDatabase() {
  return new PredictionTestDatabase(getState())
}
