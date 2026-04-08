import { createHash, randomUUID } from 'node:crypto'

export type AgentRunStep = {
  id: string
  type: string
  [key: string]: unknown
}

export type AgentRun = {
  id: string
  workspace_id?: number
  agent_id?: string
  agent_name?: string
  runtime?: string
  model?: string
  status: string
  outcome?: string | null
  trigger?: string
  started_at?: string
  ended_at?: string
  duration_ms?: number
  parent_run_id?: string
  steps?: AgentRunStep[]
  tools_available?: string[]
  cost?: Record<string, unknown>
  provenance?: Record<string, unknown>
  tags?: string[]
  error?: string
  metadata?: Record<string, unknown>
  [key: string]: unknown
}

const RUNS = new Map<string, AgentRun>()

export function createRun(input: Partial<AgentRun> = {}, workspaceId?: number): AgentRun {
  const run: AgentRun = {
    id: input.id ?? randomUUID(),
    workspace_id: input.workspace_id ?? workspaceId,
    status: input.status ?? 'created',
    steps: input.steps ?? [],
    tags: input.tags ?? [],
    metadata: input.metadata ?? {},
    ...input,
  }
  RUNS.set(run.id, run)
  return run
}

export function updateRun(id: string, patch: Partial<AgentRun>, workspaceId?: number): AgentRun | null {
  const existing = RUNS.get(id)
  if (!existing) return null
  const updated: AgentRun = {
    ...existing,
    ...patch,
    workspace_id: patch.workspace_id ?? existing.workspace_id ?? workspaceId,
    metadata: {
      ...(existing.metadata ?? {}),
      ...(patch.metadata ?? {}),
    },
  }
  RUNS.set(id, updated)
  return updated
}

export function getRun(id: string, _workspaceId?: number): AgentRun | null {
  return RUNS.get(id) ?? null
}

export function computeConfigHash(input: unknown): string {
  return createHash('sha256')
    .update(JSON.stringify(input ?? null))
    .digest('hex')
}
