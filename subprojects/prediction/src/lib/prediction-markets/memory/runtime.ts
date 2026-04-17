import { resolve } from 'node:path'
import { PredictionMarketResearchMemoryAdapter } from '@/lib/prediction-markets/memory/adapter'
import {
  PredictionMarketFileProvider,
  PredictionMarketInMemoryProvider,
  type PredictionMarketMemoryProvider,
  type PredictionMarketMemoryProviderKind,
  type PredictionMarketMemorySnapshot,
} from '@/lib/prediction-markets/memory/provider'
import { PredictionMarketCrossSimulationMemoryStore } from '@/lib/prediction-markets/memory/cross-simulation'

type PredictionMarketResearchMemoryRuntime = {
  provider_kind: PredictionMarketMemoryProviderKind
  provider: PredictionMarketMemoryProvider
  adapter: PredictionMarketResearchMemoryAdapter
  cross_simulation: PredictionMarketCrossSimulationMemoryStore
}

export type PredictionMarketResearchMemoryRuntimeOptions = {
  provider_kind?: PredictionMarketMemoryProviderKind | null
  file_path?: string | null
  seed_snapshot?: PredictionMarketMemorySnapshot | null
}

let singleton: PredictionMarketResearchMemoryRuntime | null = null

function readEnvText(...keys: string[]): string | null {
  for (const key of keys) {
    const value = process.env[key]
    if (typeof value === 'string' && value.trim().length > 0) {
      return value.trim()
    }
  }
  return null
}

function resolveProviderKind(): PredictionMarketMemoryProviderKind {
  const requested = readEnvText('PREDICTION_MARKETS_RESEARCH_MEMORY_BACKEND')
  return requested === 'file' ? 'file' : 'memory'
}

function resolveFilePath(): string {
  return resolve(
    readEnvText('PREDICTION_MARKETS_RESEARCH_MEMORY_FILE')
      ?? '/tmp/prediction-markets-research-memory.json',
  )
}

function createProvider(options: PredictionMarketResearchMemoryRuntimeOptions = {}): {
  provider_kind: PredictionMarketMemoryProviderKind
  provider: PredictionMarketMemoryProvider
} {
  const provider_kind = options.provider_kind ?? resolveProviderKind()
  const seed_snapshot = options.seed_snapshot ?? null
  if (provider_kind === 'file') {
    return {
      provider_kind,
      provider: new PredictionMarketFileProvider(options.file_path ?? resolveFilePath(), seed_snapshot),
    }
  }
  const provider = new PredictionMarketInMemoryProvider()
  if (seed_snapshot) provider.restore(seed_snapshot)
  return { provider_kind, provider }
}

export function createPredictionMarketResearchMemoryRuntime(
  options: PredictionMarketResearchMemoryRuntimeOptions = {},
): PredictionMarketResearchMemoryRuntime {
  const { provider_kind, provider } = createProvider(options)
  const adapter = new PredictionMarketResearchMemoryAdapter(provider)
  return {
    provider_kind,
    provider,
    adapter,
    cross_simulation: adapter.cross_simulation,
  }
}

export function getPredictionMarketResearchMemoryRuntime(): PredictionMarketResearchMemoryRuntime {
  if (singleton) return singleton
  singleton = createPredictionMarketResearchMemoryRuntime()
  return singleton
}

export function resetPredictionMarketResearchMemoryRuntimeForTests(): void {
  singleton = null
}
