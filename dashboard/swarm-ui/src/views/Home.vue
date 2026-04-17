<template>
  <div class="runtime-page">
    <nav class="topbar">
      <div class="brand-block">
        <div class="brand-mark">SWARM</div>
        <div class="brand-copy">
          <span class="brand-kicker">Runtime cockpit</span>
          <span class="brand-subtitle">Live health, artifacts, and campaign control</span>
        </div>
      </div>

      <div class="topbar-actions">
        <span class="endpoint-chip" :class="connectionTone">{{ connectionLabel }}</span>
        <button class="ghost-btn" @click="refreshRuntime" :disabled="refreshing">
          {{ refreshing ? 'Refreshing…' : 'Refresh' }}
        </button>
      </div>
    </nav>

    <main class="content-shell">
      <section class="hero card">
        <div class="hero-copy">
          <p class="eyebrow">Swarm runtime view</p>
          <h1>One screen for the live system.</h1>
          <p class="lede">
            This landing page pulls from `/api/swarm/*` by default, or from the backend pointed to by
            `VITE_API_BASE_URL`. It stays useful even when the legacy simulation pages are not wired.
          </p>

          <div class="hero-actions">
            <button class="primary-btn" @click="refreshRuntime" :disabled="loading || refreshing">
              {{ loading ? 'Booting…' : 'Sync runtime' }}
            </button>
            <a class="secondary-link" href="#artifacts">Artifacts</a>
            <a class="secondary-link" href="#campaigns">Campaigns</a>
          </div>
        </div>

        <div class="hero-status">
          <div class="orb" :class="healthTone">
            <span class="orb__label">{{ healthLabel }}</span>
            <span class="orb__value">{{ uptimeLabel }}</span>
          </div>
          <div class="status-meta">
            <span>Source: {{ snapshot.source || 'live' }}</span>
            <span>Last sync: {{ lastSyncLabel }}</span>
            <span>Latency: {{ latencyLabel }}</span>
          </div>
        </div>
      </section>

      <section class="stats-grid">
        <article class="stat-card card">
          <span class="stat-label">Health</span>
          <strong class="stat-value">{{ healthLabel }}</strong>
          <span class="stat-note">{{ healthMessage }}</span>
        </article>
        <article class="stat-card card">
          <span class="stat-label">Artifacts</span>
          <strong class="stat-value">{{ artifactCount }}</strong>
          <span class="stat-note">{{ artifactSummary }}</span>
        </article>
        <article class="stat-card card">
          <span class="stat-label">Campaigns</span>
          <strong class="stat-value">{{ campaignCount }}</strong>
          <span class="stat-note">{{ activeCampaignCount }} active right now</span>
        </article>
        <article class="stat-card card">
          <span class="stat-label">Backend</span>
          <strong class="stat-value">{{ backendLabel }}</strong>
          <span class="stat-note">{{ apiBaseLabel }}</span>
        </article>
      </section>

      <section class="dashboard-grid">
        <article class="panel card panel--health">
          <div class="panel-header">
            <div>
              <p class="panel-kicker">Service health</p>
              <h2>Runtime status</h2>
            </div>
            <span class="pill" :class="healthTone">{{ healthLabel }}</span>
          </div>

          <div v-if="healthLines.length" class="health-list">
            <div v-for="line in healthLines" :key="line.label" class="health-row">
              <span class="health-row__label">{{ line.label }}</span>
              <span class="health-row__value">{{ line.value }}</span>
            </div>
          </div>
          <div v-else class="empty-state">
            No health payload yet. The page will stay responsive while the backend comes online.
          </div>

          <div v-if="serviceChecks.length" class="service-grid">
            <div v-for="service in serviceChecks" :key="service.name" class="service-chip">
              <span class="service-chip__name">{{ service.name }}</span>
              <span class="service-chip__state" :class="service.tone">{{ service.state }}</span>
            </div>
          </div>
        </article>

        <article id="artifacts" class="panel card panel--artifacts">
          <div class="panel-header">
            <div>
              <p class="panel-kicker">Artifact index</p>
              <h2>Searchable index</h2>
            </div>
            <span class="pill">{{ visibleArtifacts.length }}/{{ artifactCount }}</span>
          </div>

          <label class="search-box">
            <span>Filter</span>
            <input v-model="artifactFilter" type="search" placeholder="name, tag, type, path" />
          </label>

          <div v-if="visibleArtifacts.length" class="artifact-list">
            <article v-for="artifact in visibleArtifacts" :key="artifact.id" class="artifact-card">
              <div class="artifact-card__head">
                <div>
                  <h3>{{ artifact.name }}</h3>
                  <p>{{ artifact.path || artifact.kind || 'Artifact' }}</p>
                </div>
                <span class="artifact-chip">{{ artifact.status }}</span>
              </div>
              <div class="artifact-card__body">
                <span v-if="artifact.sizeLabel">{{ artifact.sizeLabel }}</span>
                <span v-if="artifact.updatedLabel">{{ artifact.updatedLabel }}</span>
                <span v-if="artifact.version">{{ artifact.version }}</span>
              </div>
              <div v-if="artifact.tags.length" class="tag-row">
                <span v-for="tag in artifact.tags" :key="tag" class="tag-pill">{{ tag }}</span>
              </div>
            </article>
          </div>

          <div v-else class="empty-state">
            No artifacts matched the filter, or the backend has not returned an index yet.
          </div>
        </article>

        <article id="campaigns" class="panel card panel--campaigns">
          <div class="panel-header">
            <div>
              <p class="panel-kicker">Campaign dashboard</p>
              <h2>Execution flow</h2>
            </div>
            <span class="pill">{{ campaignSummary }}</span>
          </div>

          <div v-if="visibleCampaigns.length" class="campaign-grid">
            <article v-for="campaign in visibleCampaigns" :key="campaign.id" class="campaign-card">
              <div class="campaign-card__top">
                <div>
                  <h3>{{ campaign.name }}</h3>
                  <p>{{ campaign.reference }}</p>
                </div>
                <span class="pill" :class="campaign.tone">{{ campaign.status }}</span>
              </div>

              <div class="campaign-progress">
                <div class="campaign-progress__track">
                  <div class="campaign-progress__fill" :style="{ width: campaign.progress + '%' }"></div>
                </div>
                <div class="campaign-progress__meta">
                  <span>{{ campaign.progress }}%</span>
                  <span>{{ campaign.stage }}</span>
                </div>
              </div>

              <div class="campaign-meta">
                <span v-if="campaign.updatedLabel">Updated {{ campaign.updatedLabel }}</span>
                <span v-if="campaign.owner">Owner {{ campaign.owner }}</span>
                <span v-if="campaign.agents">Agents {{ campaign.agents }}</span>
              </div>
            </article>
          </div>

          <div v-else class="empty-state">
            Campaigns will appear here once the runtime backend exposes them.
          </div>
        </article>
      </section>

      <section v-if="error" class="alert card">
        <strong>Runtime fetch issue</strong>
        <p>{{ error }}</p>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getSwarmRuntimeSnapshot } from '../api/swarm'

const snapshot = ref({
  health: {},
  artifacts: [],
  campaigns: [],
  source: 'boot'
})
const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const artifactFilter = ref('')
const lastSync = ref(null)
const latencyMs = ref(null)
let refreshTimer = null
let requestSeq = 0

const apiBase = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

const unwrapValue = (value) => {
  if (value == null) return null
  if (typeof value === 'object' && !Array.isArray(value)) {
    return value.data ?? value.result ?? value.payload ?? value
  }
  return value
}

const toText = (value) => {
  if (value == null || value === '') return '—'
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : '—'
  return String(value)
}

const formatTime = (value) => {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}

const formatBytes = (value) => {
  const size = Number(value)
  if (!Number.isFinite(size) || size <= 0) return null
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let current = size
  let unit = 0
  while (current >= 1024 && unit < units.length - 1) {
    current /= 1024
    unit += 1
  }
  return `${current.toFixed(current >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`
}

const statusTone = (status) => {
  const value = String(status || '').toLowerCase()
  if (['healthy', 'ok', 'ready', 'running', 'online', 'live', 'green'].includes(value)) return 'is-healthy'
  if (['degraded', 'warning', 'partial', 'syncing'].includes(value)) return 'is-warn'
  if (['offline', 'down', 'error', 'failed', 'stopped'].includes(value)) return 'is-offline'
  return 'is-neutral'
}

const normalizeArtifact = (item, index) => {
  const raw = unwrapValue(item) || {}
  const name = raw.name || raw.title || raw.id || raw.path || `Artifact ${index + 1}`
  const tags = raw.tags || raw.labels || raw.categories || []
  return {
    id: raw.id || raw.path || name,
    name,
    path: raw.path || raw.location || raw.uri || '',
    kind: raw.kind || raw.type || raw.category || 'artifact',
    status: String(raw.status || raw.state || 'available'),
    version: raw.version || raw.revision || raw.commit || '',
    sizeLabel: formatBytes(raw.size || raw.size_bytes || raw.bytes),
    updatedLabel: formatTime(raw.updated_at || raw.updatedAt || raw.timestamp || raw.last_modified),
    tags: Array.isArray(tags) ? tags.map(tag => String(tag)).filter(Boolean) : String(tags || '').split(',').map(tag => tag.trim()).filter(Boolean)
  }
}

const normalizeCampaign = (item, index) => {
  const raw = unwrapValue(item) || {}
  const name = raw.name || raw.title || raw.id || `Campaign ${index + 1}`
  const progressValue = Number(raw.progress ?? raw.percent ?? raw.completion ?? 0)
  return {
    id: raw.id || raw.campaign_id || name,
    name,
    reference: raw.reference || raw.topic || raw.target || raw.goal || '',
    status: String(raw.status || raw.state || 'queued'),
    tone: statusTone(raw.status || raw.state),
    progress: Number.isFinite(progressValue) ? Math.max(0, Math.min(100, progressValue)) : 0,
    stage: raw.stage || raw.phase || raw.step || 'queued',
    updatedLabel: formatTime(raw.updated_at || raw.updatedAt || raw.last_activity || raw.timestamp),
    owner: raw.owner || raw.operator || raw.team || '',
    agents: raw.agent_count || raw.agents || raw.participants || ''
  }
}

const normalizedHealth = computed(() => {
  const raw = unwrapValue(snapshot.value.health) || {}
  const status = raw.status || raw.state || (raw.ok === false ? 'offline' : 'healthy')
  const uptimeSeconds = Number(raw.uptime_seconds ?? raw.uptimeSeconds ?? raw.uptime ?? 0)
  const services = raw.services || raw.components || raw.checks || {}

  const healthLines = [
    { label: 'Status', value: toText(status) },
    { label: 'Version', value: toText(raw.version || raw.build || raw.release) },
    { label: 'Commit', value: toText(raw.commit || raw.git_sha || raw.sha) },
    { label: 'Message', value: toText(raw.message || raw.detail || raw.description) }
  ].filter(line => line.value && line.value !== '—')

  const serviceChecks = Array.isArray(services)
    ? services.map((service, index) => {
      const item = unwrapValue(service) || {}
      return {
        name: item.name || item.service || `check-${index + 1}`,
        state: toText(item.status || item.state || 'unknown'),
        tone: statusTone(item.status || item.state)
      }
    })
    : Object.entries(services || {}).map(([name, value]) => {
      const item = unwrapValue(value) || {}
      const state = toText(item.status || item.state || item.ok || value)
      return {
        name,
        state,
        tone: statusTone(item.status || item.state || state)
      }
    })

  return {
    status,
    uptimeSeconds,
    healthLines,
    serviceChecks
  }
})

const artifactCount = computed(() => snapshot.value.artifacts.length)
const campaignCount = computed(() => snapshot.value.campaigns.length)
const activeCampaignCount = computed(() =>
  snapshot.value.campaigns.filter(campaign => !['done', 'completed', 'success', 'idle'].includes(String(campaign.status).toLowerCase())).length
)

const visibleArtifacts = computed(() => {
  const query = artifactFilter.value.trim().toLowerCase()
  const items = snapshot.value.artifacts.map(normalizeArtifact)
  if (!query) return items
  return items.filter(item => {
    const haystack = [
      item.name,
      item.path,
      item.kind,
      item.status,
      item.version,
      ...item.tags
    ].join(' ').toLowerCase()
    return haystack.includes(query)
  })
})

const visibleCampaigns = computed(() =>
  snapshot.value.campaigns
    .map(normalizeCampaign)
    .sort((a, b) => b.progress - a.progress)
)

const healthLabel = computed(() => toText(normalizedHealth.value.status).toUpperCase())
const healthTone = computed(() => statusTone(normalizedHealth.value.status))
const connectionTone = computed(() => {
  if (error.value) return 'is-offline'
  if (refreshing.value || loading.value) return 'is-warn'
  return healthTone.value
})

const connectionLabel = computed(() => {
  if (error.value) return 'Runtime degraded'
  if (refreshing.value || loading.value) return 'Connecting'
  return 'Runtime live'
})

const healthMessage = computed(() => {
  const lines = normalizedHealth.value.healthLines
  return lines.find(line => line.label === 'Message')?.value || 'Live runtime status'
})

const uptimeLabel = computed(() => {
  const seconds = normalizedHealth.value.uptimeSeconds
  if (!seconds) return 'uptime n/a'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return `${hours}h ${minutes}m uptime`
})

const lastSyncLabel = computed(() => lastSync.value ? formatTime(lastSync.value) : 'not yet synced')
const latencyLabel = computed(() => latencyMs.value == null ? 'pending' : `${latencyMs.value} ms`)
const apiBaseLabel = computed(() => apiBase || 'same-origin /api')
const backendLabel = computed(() => snapshot.value.source || 'live')
const artifactSummary = computed(() => {
  if (!artifactCount.value) return 'Index will populate once the backend responds'
  return 'Latest searchable artifacts'
})
const campaignSummary = computed(() => {
  if (!campaignCount.value) return 'No campaigns yet'
  return `${activeCampaignCount.value} active / ${campaignCount.value} total`
})
const healthLines = computed(() => normalizedHealth.value.healthLines)
const serviceChecks = computed(() => normalizedHealth.value.serviceChecks)

const refreshRuntime = async () => {
  const seq = ++requestSeq
  if (loading.value) {
    loading.value = true
  } else {
    refreshing.value = true
  }
  error.value = ''
  const started = performance.now()

  try {
    const next = await getSwarmRuntimeSnapshot()
    if (seq !== requestSeq) return
    snapshot.value = {
      health: next.health || {},
      artifacts: Array.isArray(next.artifacts) ? next.artifacts : [],
      campaigns: Array.isArray(next.campaigns) ? next.campaigns : [],
      source: next.source || 'live'
    }
    lastSync.value = new Date()
  } catch (err) {
    if (seq === requestSeq) {
      error.value = err?.message || 'Unable to load swarm runtime'
    }
  } finally {
    if (seq === requestSeq) {
      latencyMs.value = Math.max(0, Math.round(performance.now() - started))
      loading.value = false
      refreshing.value = false
    }
  }
}

onMounted(() => {
  refreshRuntime()
  refreshTimer = window.setInterval(refreshRuntime, 15000)
})

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
})
</script>

<style scoped>
.runtime-page {
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(67, 193, 101, 0.14), transparent 28%),
    radial-gradient(circle at top right, rgba(255, 107, 26, 0.12), transparent 32%),
    linear-gradient(180deg, #fafafa 0%, #f3f4ef 100%);
  color: var(--foreground);
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  padding: 20px 28px;
  background: rgba(250, 250, 250, 0.82);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid rgba(10, 10, 10, 0.08);
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-mark {
  font-family: var(--font-mono);
  font-weight: 700;
  letter-spacing: 0.28em;
  padding: 12px 14px;
  border: 2px solid var(--foreground);
  box-shadow: 4px 4px 0 rgba(10, 10, 10, 0.08);
}

.brand-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.brand-kicker,
.brand-subtitle,
.endpoint-chip,
.ghost-btn,
.eyebrow,
.panel-kicker,
.stat-label,
.stat-note,
.pill,
.health-row__label,
.health-row__value,
.artifact-card__body,
.campaign-card__top p,
.campaign-meta,
.search-box span,
.status-meta {
  font-family: var(--font-mono);
}

.brand-kicker {
  font-size: 11px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(10, 10, 10, 0.55);
}

.brand-subtitle {
  font-size: 14px;
  color: rgba(10, 10, 10, 0.72);
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.endpoint-chip,
.pill,
.artifact-chip,
.tag-pill,
.service-chip__state {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(10, 10, 10, 0.12);
  background: rgba(255, 255, 255, 0.72);
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  letter-spacing: 0.04em;
}

.ghost-btn,
.primary-btn,
.secondary-link {
  border: none;
  text-decoration: none;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}

.ghost-btn {
  padding: 10px 14px;
  border-radius: 999px;
  background: rgba(10, 10, 10, 0.06);
  color: var(--foreground);
}

.ghost-btn:hover,
.primary-btn:hover,
.secondary-link:hover {
  transform: translateY(-1px);
}

.content-shell {
  max-width: 1400px;
  margin: 0 auto;
  padding: 30px 24px 48px;
}

.card {
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(10, 10, 10, 0.08);
  box-shadow: 0 24px 64px rgba(10, 10, 10, 0.06);
  backdrop-filter: blur(8px);
}

.hero {
  display: grid;
  grid-template-columns: 1.3fr 0.8fr;
  gap: 28px;
  padding: 28px;
  animation: fade-in 0.5s ease-out;
}

.eyebrow {
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.24em;
  font-size: 11px;
  color: rgba(10, 10, 10, 0.55);
}

.hero h1 {
  font-family: var(--font-display);
  font-size: clamp(2.8rem, 5vw, 5rem);
  line-height: 0.95;
  font-weight: 400;
  margin: 0 0 16px;
}

.lede {
  font-family: var(--font-display);
  font-size: clamp(1.05rem, 1.5vw, 1.35rem);
  line-height: 1.65;
  max-width: 58ch;
  color: rgba(10, 10, 10, 0.74);
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 24px;
}

.primary-btn {
  padding: 14px 18px;
  border-radius: 999px;
  background: var(--foreground);
  color: var(--color-white);
  font-family: var(--font-mono);
  letter-spacing: 0.08em;
  box-shadow: 0 10px 24px rgba(10, 10, 10, 0.16);
}

.secondary-link {
  display: inline-flex;
  align-items: center;
  padding: 14px 18px;
  border-radius: 999px;
  background: rgba(67, 193, 101, 0.12);
  color: var(--foreground);
}

.hero-status {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 18px;
}

.orb {
  min-height: 250px;
  border-radius: 32px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 12px;
  padding: 28px;
  color: var(--color-white);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.12);
}

.orb::before {
  content: '';
  width: 94px;
  height: 94px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.18);
  box-shadow: inset 0 0 30px rgba(255, 255, 255, 0.2);
  margin-bottom: 18px;
}

.orb.is-healthy {
  background: linear-gradient(135deg, #1f7a46, #43c165);
}

.orb.is-warn {
  background: linear-gradient(135deg, #b66b14, #ffb347);
}

.orb.is-offline {
  background: linear-gradient(135deg, #8d2020, #ff4444);
}

.orb.is-neutral {
  background: linear-gradient(135deg, #202020, #494949);
}

.orb__label {
  font-family: var(--font-mono);
  font-size: clamp(1.1rem, 2vw, 1.75rem);
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.orb__value {
  font-family: var(--font-mono);
  opacity: 0.82;
}

.status-meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 12px;
  color: rgba(10, 10, 10, 0.6);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin: 18px 0;
}

.stat-card {
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 126px;
}

.stat-label {
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(10, 10, 10, 0.5);
}

.stat-value {
  font-family: var(--font-display);
  font-size: 2rem;
  font-weight: 400;
}

.stat-note {
  font-size: 12px;
  color: rgba(10, 10, 10, 0.64);
}

.dashboard-grid {
  display: grid;
  grid-template-columns: 0.9fr 1.1fr;
  gap: 18px;
}

.panel {
  padding: 22px;
}

.panel--campaigns {
  grid-column: 1 / -1;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 18px;
}

.panel-kicker {
  margin-bottom: 6px;
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(10, 10, 10, 0.48);
}

.panel h2 {
  font-family: var(--font-display);
  font-size: 1.8rem;
  font-weight: 400;
  margin: 0;
}

.pill {
  white-space: nowrap;
}

.health-list {
  display: grid;
  gap: 10px;
}

.health-row,
.campaign-card,
.artifact-card,
.service-chip {
  border: 1px solid rgba(10, 10, 10, 0.08);
  background: rgba(250, 250, 250, 0.86);
}

.health-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
}

.health-row__label {
  font-size: 12px;
  color: rgba(10, 10, 10, 0.5);
}

.health-row__value {
  font-size: 12px;
  color: var(--foreground);
  text-align: right;
}

.service-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}

.service-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 14px;
}

.service-chip__name {
  font-family: var(--font-mono);
  font-size: 12px;
}

.service-chip__state.is-healthy,
.pill.is-healthy,
.endpoint-chip.is-healthy,
.artifact-chip.is-healthy {
  color: #17633c;
}

.service-chip__state.is-warn,
.pill.is-warn,
.endpoint-chip.is-warn,
.artifact-chip.is-warn {
  color: #8a4e00;
}

.service-chip__state.is-offline,
.pill.is-offline,
.endpoint-chip.is-offline,
.artifact-chip.is-offline {
  color: #9b2020;
}

.service-chip__state.is-neutral,
.pill.is-neutral,
.endpoint-chip.is-neutral,
.artifact-chip.is-neutral {
  color: rgba(10, 10, 10, 0.7);
}

.search-box {
  display: grid;
  gap: 8px;
  margin-bottom: 16px;
}

.search-box input {
  width: 100%;
  border: 1px solid rgba(10, 10, 10, 0.12);
  background: rgba(255, 255, 255, 0.8);
  padding: 14px 16px;
  outline: none;
  font-family: var(--font-mono);
}

.artifact-list,
.campaign-grid {
  display: grid;
  gap: 12px;
}

.artifact-card,
.campaign-card {
  padding: 16px;
  border-radius: 18px;
}

.artifact-card__head,
.campaign-card__top {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.artifact-card h3,
.campaign-card h3 {
  font-family: var(--font-display);
  font-size: 1.2rem;
  font-weight: 400;
  margin: 0 0 4px;
}

.artifact-card p,
.campaign-card p {
  margin: 0;
  color: rgba(10, 10, 10, 0.6);
  font-size: 12px;
}

.artifact-card__body,
.campaign-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
  font-size: 11px;
  color: rgba(10, 10, 10, 0.58);
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.tag-pill {
  padding: 6px 10px;
  font-size: 11px;
  background: rgba(255, 107, 26, 0.08);
}

.artifact-chip {
  align-self: flex-start;
}

.campaign-progress {
  margin-top: 14px;
}

.campaign-progress__track {
  height: 10px;
  background: rgba(10, 10, 10, 0.06);
  border-radius: 999px;
  overflow: hidden;
}

.campaign-progress__fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--color-orange), var(--color-green));
}

.campaign-progress__meta {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-top: 8px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: rgba(10, 10, 10, 0.58);
}

.empty-state,
.alert {
  margin-top: 12px;
  padding: 16px;
  border: 1px dashed rgba(10, 10, 10, 0.16);
  background: rgba(255, 255, 255, 0.5);
  font-family: var(--font-mono);
  font-size: 12px;
  color: rgba(10, 10, 10, 0.68);
}

.alert strong {
  display: block;
  margin-bottom: 8px;
}

@media (max-width: 1080px) {
  .hero,
  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .topbar,
  .panel-header,
  .artifact-card__head,
  .campaign-card__top,
  .topbar-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .content-shell {
    padding-inline: 16px;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .hero {
    padding: 20px;
  }

  .panel {
    padding: 18px;
  }
}
</style>
