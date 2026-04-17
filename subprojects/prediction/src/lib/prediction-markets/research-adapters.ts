import type { PredictionMarketResearchSignalInput } from './research'

export type PredictionMarketResearchAdapterSource =
  | 'WorldOSINT'
  | 'worldmonitor.app'
  | 'Hack23/cia'
  | 'codeforamerica/open-civic-datasets'

export type PredictionMarketResearchAdapterPacket = {
  source: PredictionMarketResearchAdapterSource
  signals: PredictionMarketResearchSignalInput[]
  summary: string
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : undefined
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((entry): entry is string => typeof entry === 'string' && entry.trim().length > 0)
    : []
}

export function adaptWorldOsintPacket(input: Record<string, unknown>): PredictionMarketResearchAdapterPacket {
  const title = asString(input.title) ?? asString(input.headline) ?? 'WorldOSINT signal'
  const summary = asString(input.summary) ?? asString(input.message) ?? 'WorldOSINT discovery signal.'
  const url = asString(input.url)
  const tags = asStringArray(input.tags)

  return {
    source: 'WorldOSINT',
    signals: [{
      kind: 'alert',
      title,
      summary,
      source_name: 'WorldOSINT',
      source_url: url,
      captured_at: asString(input.captured_at) ?? new Date().toISOString(),
      tags,
      stance: asString(input.stance) ?? 'unknown',
      confidence: typeof input.confidence === 'number' ? input.confidence : undefined,
      severity: asString(input.severity) ?? 'medium',
      payload: {
        adapter_source: 'WorldOSINT',
      },
    }],
    summary: `WorldOSINT adapter produced 1 normalized alert signal${url ? ` from ${url}` : ''}.`,
  }
}

export function adaptWorldMonitorPacket(input: Record<string, unknown>): PredictionMarketResearchAdapterPacket {
  const title = asString(input.title) ?? asString(input.headline) ?? 'WorldMonitor signal'
  const summary = asString(input.summary) ?? asString(input.message) ?? 'WorldMonitor situational signal.'

  return {
    source: 'worldmonitor.app',
    signals: [{
      kind: 'worldmonitor',
      title,
      summary,
      source_name: 'worldmonitor.app',
      source_url: asString(input.url) ?? 'https://www.worldmonitor.app',
      captured_at: asString(input.captured_at) ?? new Date().toISOString(),
      tags: asStringArray(input.tags),
      stance: asString(input.stance) ?? 'unknown',
      confidence: typeof input.confidence === 'number' ? input.confidence : undefined,
      severity: asString(input.severity) ?? 'medium',
      payload: {
        adapter_source: 'worldmonitor.app',
      },
    }],
    summary: 'worldmonitor.app adapter produced 1 normalized discovery signal.',
  }
}

export function adaptHack23CiaPacket(input: Record<string, unknown>): PredictionMarketResearchAdapterPacket {
  const title = asString(input.title) ?? asString(input.headline) ?? 'Hack23/cia context'
  const summary = asString(input.summary) ?? asString(input.message) ?? 'Hack23/cia contextual intelligence signal.'

  return {
    source: 'Hack23/cia',
    signals: [{
      kind: 'news',
      title,
      summary,
      source_name: 'Hack23/cia',
      source_url: asString(input.url) ?? 'https://github.com/Hack23/cia',
      captured_at: asString(input.captured_at) ?? new Date().toISOString(),
      tags: asStringArray(input.tags),
      stance: asString(input.stance) ?? 'neutral',
      confidence: typeof input.confidence === 'number' ? input.confidence : undefined,
      severity: asString(input.severity) ?? 'low',
      payload: {
        adapter_source: 'Hack23/cia',
      },
    }],
    summary: 'Hack23/cia adapter produced 1 normalized contextual signal.',
  }
}

export function adaptOpenCivicDatasetPacket(input: Record<string, unknown>): PredictionMarketResearchAdapterPacket {
  const title = asString(input.title) ?? 'Open civic dataset reference'
  const summary = asString(input.summary) ?? 'Verified civic/open data reference.'

  return {
    source: 'codeforamerica/open-civic-datasets',
    signals: [{
      kind: 'news',
      title,
      summary,
      source_name: 'codeforamerica/open-civic-datasets',
      source_url: asString(input.url) ?? 'https://github.com/codeforamerica/open-civic-datasets',
      captured_at: asString(input.captured_at) ?? new Date().toISOString(),
      tags: asStringArray(input.tags),
      stance: asString(input.stance) ?? 'neutral',
      confidence: typeof input.confidence === 'number' ? input.confidence : undefined,
      severity: asString(input.severity) ?? 'low',
      payload: {
        adapter_source: 'codeforamerica/open-civic-datasets',
      },
    }],
    summary: 'Open civic datasets adapter produced 1 normalized reference signal.',
  }
}
