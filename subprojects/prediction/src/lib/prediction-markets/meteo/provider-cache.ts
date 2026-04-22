import type { MeteoFetchLike } from '@/lib/prediction-markets/meteo/types'

type CacheEntry = {
  expiresAt: number
  payload: unknown
}

const providerCache = new Map<string, CacheEntry>()

export async function fetchJsonWithMeteoProviderCache<T>(input: {
  url: string
  fetchImpl?: MeteoFetchLike
  init?: RequestInit
  cacheTtlMs?: number
  retryCount?: number
}): Promise<T> {
  const cacheKey = buildCacheKey(input.url, input.init)
  const now = Date.now()
  const cached = providerCache.get(cacheKey)
  if (cached && cached.expiresAt > now) {
    return cached.payload as T
  }

  const fetchImpl = input.fetchImpl ?? fetch
  const attempts = Math.max(1, (input.retryCount ?? 1) + 1)

  let lastError: unknown
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetchImpl(input.url, input.init)
      if (!response.ok) {
        throw new Error(`Provider request failed: ${response.status}`)
      }
      const payload = await response.json() as T
      providerCache.set(cacheKey, {
        expiresAt: now + Math.max(1_000, input.cacheTtlMs ?? 300_000),
        payload,
      })
      return payload
    } catch (error) {
      lastError = error
      if (attempt + 1 >= attempts) break
      await sleep(100 * (attempt + 1))
    }
  }

  throw lastError instanceof Error ? lastError : new Error('Provider request failed')
}

export function clearMeteoProviderCache(): void {
  providerCache.clear()
}

function buildCacheKey(url: string, init?: RequestInit): string {
  const method = init?.method ?? 'GET'
  const headers = init?.headers ? JSON.stringify(normalizeHeaders(init.headers)) : ''
  return `${method}:${url}:${headers}`
}

function normalizeHeaders(headers: HeadersInit): Record<string, string> {
  if (headers instanceof Headers) {
    return Object.fromEntries(headers.entries())
  }
  if (Array.isArray(headers)) {
    return Object.fromEntries(headers.map(([key, value]) => [key, String(value)]))
  }
  return Object.fromEntries(Object.entries(headers).map(([key, value]) => [key, String(value)]))
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
