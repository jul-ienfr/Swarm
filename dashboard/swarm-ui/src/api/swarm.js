const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const SWARM_PREFIX = '/api/swarm'

function buildUrl(path) {
  return `${API_BASE_URL}${path}`
}

async function requestJson(path, { method = 'GET', body, timeoutMs = 7000 } = {}) {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(buildUrl(path), {
      method,
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {})
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
      cache: 'no-store'
    })

    const raw = await response.text()
    const payload = raw ? JSON.parse(raw) : null

    if (!response.ok) {
      const message = payload?.error || payload?.message || response.statusText || 'Request failed'
      throw new Error(message)
    }

    return payload
  } finally {
    window.clearTimeout(timeout)
  }
}

function unwrap(value) {
  if (value == null) return null
  if (Array.isArray(value)) return value
  if (typeof value !== 'object') return value
  if ('success' in value && value.success === false) {
    throw new Error(value.error || value.message || 'Request failed')
  }
  if ('data' in value) return value.data
  if ('result' in value) return value.result
  if ('payload' in value) return value.payload
  return value
}

function normalizeArray(value, key) {
  const unwrapped = unwrap(value)
  if (Array.isArray(unwrapped)) return unwrapped
  if (unwrapped && typeof unwrapped === 'object') {
    const candidate = unwrapped[key] || unwrapped.items || unwrapped.list || unwrapped.records || []
    return Array.isArray(candidate) ? candidate : []
  }
  return []
}

function normalizeObject(value) {
  const unwrapped = unwrap(value)
  return unwrapped && typeof unwrapped === 'object' && !Array.isArray(unwrapped) ? unwrapped : {}
}

function flattenArtifacts(indexPayload) {
  const raw = normalizeObject(indexPayload)
  const buckets = [
    'campaigns',
    'comparisons',
    'exports',
    'benchmarks',
    'matrix_benchmarks',
    'matrix_benchmark_exports',
    'matrix_benchmark_comparisons',
    'matrix_benchmark_comparison_exports',
  ]

  return buckets.flatMap((bucket) => {
    const items = Array.isArray(raw[bucket]) ? raw[bucket] : []
    return items.map((item) => {
      const entry = normalizeObject(item)
      return {
        id: entry.export_id || entry.comparison_id || entry.campaign_id || entry.benchmark_id || entry.artifact_id || `${bucket}:${entry.created_at || 'artifact'}`,
        name: entry.export_id || entry.comparison_id || entry.campaign_id || entry.benchmark_id || entry.artifact_id || bucket,
        path: entry.content_path || entry.manifest_path || entry.report_path || entry.artifact_path || '',
        kind: entry.artifact_kind || bucket.replace(/s$/, ''),
        status: entry.status || (entry.comparable ? 'comparable' : 'stored'),
        updated_at: entry.updated_at || entry.created_at || null,
        tags: [bucket],
      }
    })
  })
}

function dashboardRowsToCampaigns(dashboardPayload) {
  const raw = normalizeObject(dashboardPayload)
  const rows = Array.isArray(raw.rows) ? raw.rows : []
  return rows.map((row) => {
    const entry = normalizeObject(row)
    return {
      campaign_id: entry.artifact_id,
      title: entry.artifact_id,
      topic: entry.artifact_kind,
      status: entry.status || 'stored',
      stage: entry.artifact_kind || 'artifact',
      updated_at: entry.created_at || null,
      progress: entry.comparable ? 100 : 45,
      agents: entry.metadata?.campaign_count || entry.metadata?.sample_count || '',
    }
  })
}

export async function getSwarmRuntimeSnapshot() {
  const [health, artifactIndex, campaignDashboard] = await Promise.allSettled([
    requestJson(`${SWARM_PREFIX}/health`).then(unwrap),
    requestJson(`${SWARM_PREFIX}/index`).then(unwrap),
    requestJson(`${SWARM_PREFIX}/dashboard`).then(unwrap)
  ])

  return {
    health: health.status === 'fulfilled' ? normalizeObject(health.value) : {},
    artifacts: artifactIndex.status === 'fulfilled' ? flattenArtifacts(artifactIndex.value) : [],
    campaigns: campaignDashboard.status === 'fulfilled' ? dashboardRowsToCampaigns(campaignDashboard.value) : [],
    source: 'swarm-dashboard'
  }
}

export async function refreshSwarmHealth() {
  return normalizeObject(await requestJson(`${SWARM_PREFIX}/health`))
}

export async function listSwarmArtifacts() {
  return flattenArtifacts(await requestJson(`${SWARM_PREFIX}/index`))
}

export async function listSwarmCampaigns() {
  return dashboardRowsToCampaigns(await requestJson(`${SWARM_PREFIX}/dashboard`))
}
