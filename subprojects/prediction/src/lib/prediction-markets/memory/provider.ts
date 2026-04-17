import { randomUUID } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'

export const PREDICTION_MARKETS_MEMORY_SCHEMA_VERSION = '1.0.0'
export const PREDICTION_MARKETS_MEMORY_SCOPE = 'prediction-markets' as const

export type PredictionMarketMemoryProviderKind = 'memory' | 'file'

export type PredictionMarketMemoryEntry = {
  memory_id: string
  namespace: string
  kind: string
  subject_id: string
  content: unknown
  tags: string[]
  source_ref: string | null
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

export type PredictionMarketMemoryFilter = {
  namespace?: string | null
  kind?: string | null
  subject_id?: string | null
  text?: string | null
  tags?: string[] | null
  metadata?: Record<string, unknown> | null
  limit?: number | null
}

export type PredictionMarketMemoryUpsertInput = {
  memory_id?: string | null
  namespace: string
  kind: string
  subject_id: string
  content: unknown
  tags?: readonly string[] | null
  source_ref?: string | null
  metadata?: Record<string, unknown> | null
  created_at?: string | null
}

export type PredictionMarketMemorySnapshot = {
  schema_version: typeof PREDICTION_MARKETS_MEMORY_SCHEMA_VERSION
  provider_kind: PredictionMarketMemoryProviderKind
  scope: typeof PREDICTION_MARKETS_MEMORY_SCOPE
  generated_at: string
  entries: PredictionMarketMemoryEntry[]
}

export interface PredictionMarketMemoryProvider {
  readonly provider_kind: PredictionMarketMemoryProviderKind
  readonly scope: typeof PREDICTION_MARKETS_MEMORY_SCOPE
  list(filter?: PredictionMarketMemoryFilter): PredictionMarketMemoryEntry[]
  get(memory_id: string): PredictionMarketMemoryEntry | null
  upsert(input: PredictionMarketMemoryUpsertInput): PredictionMarketMemoryEntry
  delete(memory_id: string): boolean
  clear(filter?: PredictionMarketMemoryFilter): number
  snapshot(): PredictionMarketMemorySnapshot
  restore(snapshot: PredictionMarketMemorySnapshot): void
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>()
  const out: string[] = []

  for (const value of values) {
    const normalized = String(value ?? '').trim()
    if (!normalized || seen.has(normalized)) continue
    seen.add(normalized)
    out.push(normalized)
  }

  return out
}

function toRecord(value: unknown): Record<string, unknown> {
  if (value == null || typeof value !== 'object' || Array.isArray(value)) return {}
  return value as Record<string, unknown>
}

function valueMatchesFilter(actual: unknown, expected: unknown): boolean {
  if (expected == null) return true
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual)) return false
    return expected.every((item, index) => valueMatchesFilter(actual[index], item))
  }

  if (typeof expected === 'object') {
    const actualRecord = toRecord(actual)
    const expectedRecord = toRecord(expected)
    return Object.entries(expectedRecord).every(([key, value]) =>
      valueMatchesFilter(actualRecord[key], value))
  }

  return actual === expected
}

function stringifyContent(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value

  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function matchesText(entry: PredictionMarketMemoryEntry, text: string): boolean {
  const haystack = uniqueStrings([
    entry.memory_id,
    entry.namespace,
    entry.kind,
    entry.subject_id,
    entry.source_ref,
    entry.created_at,
    entry.updated_at,
    ...entry.tags,
    stringifyContent(entry.content),
    stringifyContent(entry.metadata),
  ]).join(' ').toLowerCase()

  return text.trim().length === 0 || haystack.includes(text.trim().toLowerCase())
}

function matchesFilter(entry: PredictionMarketMemoryEntry, filter?: PredictionMarketMemoryFilter): boolean {
  if (!filter) return true
  if (filter.namespace && entry.namespace !== filter.namespace) return false
  if (filter.kind && entry.kind !== filter.kind) return false
  if (filter.subject_id && entry.subject_id !== filter.subject_id) return false
  if (filter.tags && filter.tags.length > 0) {
    const wanted = uniqueStrings(filter.tags)
    if (!wanted.every((tag) => entry.tags.includes(tag))) return false
  }
  if (filter.text && !matchesText(entry, filter.text)) return false
  if (filter.metadata && !valueMatchesFilter(entry.metadata, filter.metadata)) return false
  return true
}

function sortEntries(entries: PredictionMarketMemoryEntry[]): PredictionMarketMemoryEntry[] {
  return [...entries].sort((left, right) => {
    const updatedDelta = Date.parse(right.updated_at) - Date.parse(left.updated_at)
    if (updatedDelta !== 0) return updatedDelta
    const createdDelta = Date.parse(right.created_at) - Date.parse(left.created_at)
    if (createdDelta !== 0) return createdDelta
    return left.memory_id.localeCompare(right.memory_id)
  })
}

function cloneSnapshot(snapshot: PredictionMarketMemorySnapshot): PredictionMarketMemorySnapshot {
  return JSON.parse(JSON.stringify(snapshot)) as PredictionMarketMemorySnapshot
}

export class PredictionMarketInMemoryProvider implements PredictionMarketMemoryProvider {
  readonly provider_kind: PredictionMarketMemoryProviderKind = 'memory'
  readonly scope = PREDICTION_MARKETS_MEMORY_SCOPE
  protected readonly entries = new Map<string, PredictionMarketMemoryEntry>()

  list(filter?: PredictionMarketMemoryFilter): PredictionMarketMemoryEntry[] {
    const limit = filter?.limit == null ? Number.POSITIVE_INFINITY : Math.max(0, filter.limit)
    return sortEntries([...this.entries.values()].filter((entry) => matchesFilter(entry, filter))).slice(0, limit)
  }

  get(memory_id: string): PredictionMarketMemoryEntry | null {
    return this.entries.get(memory_id) ?? null
  }

  upsert(input: PredictionMarketMemoryUpsertInput): PredictionMarketMemoryEntry {
    const now = new Date().toISOString()
    const normalizedTags = uniqueStrings(input.tags ? [...input.tags] : [])
    const existing = input.memory_id
      ? this.entries.get(input.memory_id)
      : [...this.entries.values()].find((entry) =>
        entry.namespace === input.namespace &&
        entry.kind === input.kind &&
        entry.subject_id === input.subject_id,
      )

    const entry: PredictionMarketMemoryEntry = {
      memory_id: existing?.memory_id ?? input.memory_id ?? randomUUID(),
      namespace: input.namespace,
      kind: input.kind,
      subject_id: input.subject_id,
      content: input.content,
      tags: normalizedTags,
      source_ref: input.source_ref ?? existing?.source_ref ?? null,
      created_at: existing?.created_at ?? input.created_at ?? now,
      updated_at: now,
      metadata: {
        ...(existing?.metadata ?? {}),
        ...(input.metadata ?? {}),
      },
    }

    this.entries.set(entry.memory_id, entry)
    return entry
  }

  delete(memory_id: string): boolean {
    return this.entries.delete(memory_id)
  }

  clear(filter?: PredictionMarketMemoryFilter): number {
    const ids = this.list(filter).map((entry) => entry.memory_id)
    let removed = 0
    for (const memoryId of ids) {
      if (this.entries.delete(memoryId)) removed += 1
    }
    return removed
  }

  snapshot(): PredictionMarketMemorySnapshot {
    return cloneSnapshot({
      schema_version: PREDICTION_MARKETS_MEMORY_SCHEMA_VERSION,
      provider_kind: this.provider_kind,
      scope: this.scope,
      generated_at: new Date().toISOString(),
      entries: sortEntries([...this.entries.values()]),
    })
  }

  restore(snapshot: PredictionMarketMemorySnapshot): void {
    this.entries.clear()
    for (const entry of snapshot.entries ?? []) {
      const normalized: PredictionMarketMemoryEntry = {
        memory_id: String(entry.memory_id ?? randomUUID()),
        namespace: String(entry.namespace ?? '').trim() || 'research',
        kind: String(entry.kind ?? '').trim() || 'note',
        subject_id: String(entry.subject_id ?? '').trim() || String(entry.memory_id ?? randomUUID()),
        content: entry.content,
        tags: uniqueStrings(entry.tags ?? []),
        source_ref: entry.source_ref ?? null,
        created_at: String(entry.created_at ?? new Date().toISOString()),
        updated_at: String(entry.updated_at ?? entry.created_at ?? new Date().toISOString()),
        metadata: toRecord(entry.metadata),
      }
      this.entries.set(normalized.memory_id, normalized)
    }
  }
}

export class PredictionMarketFileProvider extends PredictionMarketInMemoryProvider {
  readonly provider_kind: PredictionMarketMemoryProviderKind = 'file'
  readonly file_path: string

  constructor(filePath: string, seedSnapshot?: PredictionMarketMemorySnapshot | null) {
    super()
    this.file_path = resolve(filePath)

    const loaded = this.loadFromDisk()
    if (loaded) {
      super.restore(loaded)
    } else if (seedSnapshot) {
      super.restore(seedSnapshot)
      this.persist()
    }
  }

  override upsert(input: PredictionMarketMemoryUpsertInput): PredictionMarketMemoryEntry {
    const entry = super.upsert(input)
    this.persist()
    return entry
  }

  override delete(memory_id: string): boolean {
    const removed = super.delete(memory_id)
    if (removed) this.persist()
    return removed
  }

  override clear(filter?: PredictionMarketMemoryFilter): number {
    const removed = super.clear(filter)
    if (removed > 0) this.persist()
    return removed
  }

  override restore(snapshot: PredictionMarketMemorySnapshot): void {
    super.restore(snapshot)
    this.persist()
  }

  private loadFromDisk(): PredictionMarketMemorySnapshot | null {
    if (!existsSync(this.file_path)) return null

    try {
      const raw = readFileSync(this.file_path, 'utf8')
      if (!raw.trim()) return null
      const parsed = JSON.parse(raw) as Partial<PredictionMarketMemorySnapshot> & {
        entries?: PredictionMarketMemoryEntry[]
      }
      if (!Array.isArray(parsed.entries)) return null

      return {
        schema_version: PREDICTION_MARKETS_MEMORY_SCHEMA_VERSION,
        provider_kind: 'file',
        scope: PREDICTION_MARKETS_MEMORY_SCOPE,
        generated_at: typeof parsed.generated_at === 'string' ? parsed.generated_at : new Date().toISOString(),
        entries: parsed.entries,
      }
    } catch {
      return null
    }
  }

  private persist(): void {
    const snapshot = this.snapshot()
    mkdirSync(dirname(this.file_path), { recursive: true })
    const tempPath = `${this.file_path}.${process.pid}.tmp`
    writeFileSync(tempPath, `${JSON.stringify(snapshot, null, 2)}\n`, 'utf8')
    renameSync(tempPath, this.file_path)
  }
}
