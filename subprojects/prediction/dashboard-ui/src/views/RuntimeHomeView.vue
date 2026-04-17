<template>
  <div class="runtime-page">
    <section class="hero">
      <div class="hero-copy panel">
        <div class="eyebrow-row">
          <span class="eyebrow">Prediction runtime</span>
          <span class="eyebrow-muted">Live dashboard + quick console</span>
        </div>
        <h1>Home / Runtime</h1>
        <p class="hero-text">
          A live control room for the current prediction stack: runtime health, recent runs, benchmark state, and a fast prediction console for the active venue.
        </p>

        <div class="hero-actions">
          <button class="primary-btn" @click="openPredictConsole">
            Open full analyzer
          </button>
          <button class="secondary-btn" @click="router.push('/trade')">
            Go to paper trading
          </button>
          <button class="ghost-btn" @click="reloadOverview()">
            {{ refreshing ? 'Refreshing...' : 'Refresh runtime' }}
          </button>
        </div>
      </div>

      <div class="hero-side">
        <div class="panel side-panel">
          <div class="panel-top">
            <div>
              <p class="panel-kicker">Venue</p>
              <h2>{{ venueLabel }}</h2>
            </div>
            <div class="venue-switch">
              <button
                v-for="option in venueOptions"
                :key="option.value"
                class="venue-chip"
                :class="{ active: venue === option.value }"
                @click="venue = option.value"
              >
                {{ option.label }}
              </button>
            </div>
          </div>

          <div class="status-stack">
            <div class="status-row">
              <span>Freshness</span>
              <strong :class="'freshness-' + freshness">{{ freshnessLabel }}</strong>
            </div>
            <div class="status-row">
              <span>Last sync</span>
              <strong>{{ lastUpdatedLabel }}</strong>
            </div>
            <div class="status-row">
              <span>Selected path</span>
              <strong>{{ selectedPathLabel }}</strong>
            </div>
            <div class="status-row">
              <span>Runtime summary</span>
              <strong class="wrap">{{ runtimeSummary }}</strong>
            </div>
          </div>
        </div>

        <div class="panel pulse-panel">
          <div class="pulse-label">Current mode</div>
          <div class="pulse-value">{{ currentModeLabel }}</div>
          <div class="pulse-subtext">{{ currentModeHint }}</div>
        </div>
      </div>
    </section>

    <section v-if="error" class="panel error-banner">
      {{ error }}
    </section>

    <section class="grid-two">
      <article class="panel console-panel">
        <div class="panel-top">
          <div>
            <p class="panel-kicker">Runtime console</p>
            <h2>Run a market check</h2>
          </div>
          <div class="mode-toggle">
            <button class="mode-btn" :class="{ active: predictionMode === 'quick' }" @click="predictionMode = 'quick'" :disabled="predictionLoading">
              Quick
            </button>
            <button class="mode-btn" :class="{ active: predictionMode === 'deep' }" @click="predictionMode = 'deep'" :disabled="predictionLoading">
              Deep
            </button>
          </div>
        </div>

        <div class="console-form">
          <input
            v-model="predictionSlug"
            type="text"
            class="slug-input"
            placeholder="Paste a Polymarket URL or event slug..."
            :disabled="predictionLoading"
            @keyup.enter="runPrediction"
          />

          <div class="form-actions">
            <button class="primary-btn" @click="runPrediction" :disabled="!canRunPrediction">
              <span v-if="!predictionLoading">Run prediction</span>
              <span v-else>{{ deepPolling ? 'Polling deep run...' : 'Running...' }}</span>
            </button>
            <button class="secondary-btn" @click="clearPrediction" :disabled="predictionLoading && !predictionResult">
              Clear
            </button>
          </div>
        </div>

        <div v-if="predictionLoading" class="progress-box">
          <div
            v-for="(step, idx) in progressSteps"
            :key="step"
            class="progress-step"
            :class="{
              completed: idx < progressIndex,
              active: idx === progressIndex,
              pending: idx > progressIndex
            }"
          >
            <span class="step-dot"></span>
            <span>{{ step }}</span>
          </div>
        </div>

        <div v-if="predictionError" class="error-box">
          {{ predictionError }}
        </div>

        <div v-if="predictionResult" class="prediction-card">
          <div class="prediction-header">
            <div>
              <p class="prediction-question">{{ predictionResult.question }}</p>
              <p class="prediction-meta">{{ predictionResult.mode.toUpperCase() }} mode · {{ formatTime(predictionResult.timestamp) }}</p>
            </div>
            <span class="mode-pill" :class="predictionResult.mode === 'deep' ? 'pill-deep' : 'pill-quick'">
              {{ predictionResult.mode === 'deep' ? 'Deep' : 'Quick' }}
            </span>
          </div>

          <div class="prediction-comparison">
            <div class="prediction-col">
              <span class="label">Market</span>
              <strong>{{ formatPercent(predictionResult.marketOdds) }}</strong>
            </div>
            <div class="prediction-edge">
              <span class="label">Edge</span>
              <strong :class="edgeClass(predictionResult.edge)">{{ formatSignedPercent(predictionResult.edge) }}</strong>
            </div>
            <div class="prediction-col">
              <span class="label">Model</span>
              <strong>{{ formatPercent(predictionResult.prediction) }}</strong>
            </div>
          </div>

          <div class="prediction-details">
            <div class="detail-item">
              <span>Status</span>
              <strong>{{ predictionResult.status || 'completed' }}</strong>
            </div>
            <div class="detail-item">
              <span>Confidence</span>
              <strong>{{ formatConfidence(predictionResult.confidence) }}</strong>
            </div>
            <div class="detail-item">
              <span>Signal</span>
              <strong>{{ predictionResult.signal || 'n/a' }}</strong>
            </div>
          </div>

          <div v-if="predictionResult.reasoning" class="prediction-reasoning">
            {{ predictionResult.reasoning }}
          </div>
        </div>

        <div v-else class="empty-state">
          Drop in a market slug, run a quick check, and the latest result will appear here.
        </div>
      </article>

      <article class="panel metrics-panel">
        <div class="panel-top">
          <div>
            <p class="panel-kicker">Snapshot</p>
            <h2>Runtime health</h2>
          </div>
          <span class="small-badge" :class="'freshness-' + freshness">{{ freshnessLabel }}</span>
        </div>

        <div class="metric-grid">
          <div class="metric-card">
            <span class="metric-label">Runs</span>
            <strong>{{ metricValue(metrics.runs) }}</strong>
          </div>
          <div class="metric-card">
            <span class="metric-label">Bet</span>
            <strong>{{ metricValue(metrics.bet) }}</strong>
          </div>
          <div class="metric-card">
            <span class="metric-label">Wait</span>
            <strong>{{ metricValue(metrics.wait) }}</strong>
          </div>
          <div class="metric-card">
            <span class="metric-label">No trade</span>
            <strong>{{ metricValue(metrics.no_trade) }}</strong>
          </div>
          <div class="metric-card">
            <span class="metric-label">Benchmark ready</span>
            <strong>{{ metricValue(metrics.benchmark_ready) }}</strong>
          </div>
          <div class="metric-card">
            <span class="metric-label">Live promotable</span>
            <strong>{{ metricValue(metrics.live_promotable) }}</strong>
          </div>
        </div>

        <div class="sub-panels">
          <div class="mini-panel">
            <p class="mini-label">Venue health</p>
            <strong>{{ venueSnapshot?.venue_health_status || 'n/a' }}</strong>
            <span>{{ venueSnapshot?.venue_capabilities || 'Capabilities unavailable' }}</span>
          </div>
          <div class="mini-panel">
            <p class="mini-label">Benchmark gate</p>
            <strong>{{ benchmark?.benchmark?.status || benchmark?.comparison?.benchmark_gate_summary || 'n/a' }}</strong>
            <span>{{ benchmark?.comparison?.selected_path_effective_mode || benchmark?.comparison?.selected_path || 'No selected path' }}</span>
          </div>
        </div>

        <div class="capability-strip">
          <span class="capability-pill" :class="{ on: venueSnapshot?.venue_supports_execution }">Execution</span>
          <span class="capability-pill" :class="{ on: venueSnapshot?.venue_supports_paper_mode }">Paper</span>
          <span class="capability-pill" :class="{ on: !!venueSnapshot?.latest_live_route_allowed }">Live route</span>
        </div>
      </article>
    </section>

    <section class="grid-two">
      <article class="panel list-panel">
        <div class="panel-top">
          <div>
            <p class="panel-kicker">Runs</p>
            <h2>Recent runtime runs</h2>
          </div>
          <span class="small-badge">{{ recentRuns.length }} items</span>
        </div>

        <div v-if="recentRuns.length" class="run-list">
          <div v-for="run in recentRuns" :key="run.run_id" class="run-row">
            <div class="run-main">
              <div class="run-id">{{ run.run_id }}</div>
              <div class="run-subline">
                <span>{{ run.recommendation || 'n/a' }}</span>
                <span>·</span>
                <span>{{ run.execution_summary || run.selected_path_effective_mode || 'No summary' }}</span>
              </div>
            </div>
            <div class="run-side">
              <span class="run-stat">{{ formatPercent(run.probability_yes) }}</span>
              <span class="run-stat">{{ formatBps(run.edge_bps) }}</span>
              <span class="run-stat">{{ run.benchmark_state }}</span>
            </div>
          </div>
        </div>
        <div v-else class="empty-state compact">
          No runs returned yet for this venue.
        </div>
      </article>

      <article class="panel activity-panel">
        <div class="panel-top">
          <div>
            <p class="panel-kicker">Activity</p>
            <h2>Alerts, events, and intents</h2>
          </div>
          <span class="small-badge">{{ recentEvents.length }} events</span>
        </div>

        <div v-if="alerts.length" class="alert-list">
          <div v-for="alert in alerts" :key="alert.code" class="alert-row" :class="alert.severity">
            <strong>{{ alert.title }}</strong>
            <span>{{ alert.summary }}</span>
          </div>
        </div>

        <div class="timeline">
          <div v-for="event in recentEvents" :key="event.event_id" class="timeline-row">
            <div class="timeline-head">
              <strong>{{ event.summary }}</strong>
              <span>{{ event.type }}</span>
            </div>
            <div class="timeline-meta">
              <span>{{ event.run_id || event.intent_id || 'global' }}</span>
              <span>{{ formatIso(event.emitted_at) }}</span>
            </div>
          </div>
        </div>

        <div v-if="liveIntents.length" class="intent-stack">
          <div v-for="intent in liveIntents.slice(0, 3)" :key="intent.intent_id || intent.id" class="intent-row">
            <strong>{{ intent.intent_id || intent.id || 'intent' }}</strong>
            <span>{{ intent.status || intent.state || 'pending' }}</span>
          </div>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getRuntimeOverview, runDeepPrediction, runQuickPrediction } from '../api/runtime'

const router = useRouter()

const venueOptions = [
  { value: 'polymarket', label: 'Polymarket' },
  { value: 'kalshi', label: 'Kalshi' },
]

const venue = ref('polymarket')
const overview = ref(null)
const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const lastUpdatedAt = ref(null)

const predictionMode = ref('quick')
const predictionSlug = ref('')
const predictionLoading = ref(false)
const deepPolling = ref(false)
const predictionError = ref('')
const predictionResult = ref(null)
const progressIndex = ref(0)

const quickSteps = [
  'Reading market metadata',
  'Fetching supporting signals',
  'Synthesizing answer',
  'Done',
]

const deepSteps = [
  'Reading market metadata',
  'Building market context',
  'Running deep analysis',
  'Polling task status',
  'Extracting prediction',
  'Done',
]

const progressSteps = computed(() => (predictionMode.value === 'deep' ? deepSteps : quickSteps))
const canRunPrediction = computed(() => predictionSlug.value.trim().length > 0 && !predictionLoading.value)
const venueLabel = computed(() => venueOptions.find((item) => item.value === venue.value)?.label ?? venue.value)
const metrics = computed(() => overview.value?.metrics ?? {})
const recentRuns = computed(() => overview.value?.runs ?? [])
const recentEvents = computed(() => overview.value?.recent_events ?? [])
const liveIntents = computed(() => overview.value?.live_intents ?? [])
const alerts = computed(() => overview.value?.alerts ?? [])
const venueSnapshot = computed(() => overview.value?.venue_snapshot ?? null)
const benchmark = computed(() => overview.value?.benchmark ?? null)
const selectedPathLabel = computed(() => {
  return benchmark.value?.comparison?.selected_path_effective_mode
    || benchmark.value?.comparison?.selected_path
    || venueSnapshot.value?.latest_selected_path
    || 'n/a'
})
const runtimeSummary = computed(() => {
  return benchmark.value?.comparison?.benchmark_gate_summary
    || benchmark.value?.benchmark?.summary
    || venueSnapshot.value?.latest_recommendation
    || 'Runtime ready'
})
const freshness = computed(() => overview.value?.freshness ?? 'warm')
const freshnessLabel = computed(() => (freshness.value || 'warm').toUpperCase())
const currentModeLabel = computed(() => predictionMode.value === 'deep' ? 'Deep runtime' : 'Quick runtime')
const currentModeHint = computed(() => predictionMode.value === 'deep'
  ? 'Deep mode follows the full prediction workflow and polls for completion.'
  : 'Quick mode is a fast runtime check that returns the market edge immediately.')
const lastUpdatedLabel = computed(() => {
  if (!lastUpdatedAt.value) return 'n/a'
  return new Date(lastUpdatedAt.value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
})

const formatIso = (value) => {
  if (!value) return 'n/a'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'n/a'
  return date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const formatTime = (value) => {
  if (!value) return 'n/a'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'n/a'
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

const formatPercent = (value) => {
  if (value == null || !Number.isFinite(Number(value))) return '--'
  return `${(Number(value) * 100).toFixed(1)}%`
}

const formatSignedPercent = (value) => {
  if (value == null || !Number.isFinite(Number(value))) return '--'
  const n = Number(value) * 100
  return `${n > 0 ? '+' : ''}${n.toFixed(1)}%`
}

const formatBps = (value) => {
  if (value == null || !Number.isFinite(Number(value))) return '--'
  return `${Math.round(Number(value))} bps`
}

const formatConfidence = (value) => {
  if (value == null || !Number.isFinite(Number(value))) return '--'
  return `${(Number(value) * 100).toFixed(0)}%`
}

const metricValue = (value) => {
  if (value == null) return '--'
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  return String(value)
}

const edgeClass = (value) => {
  if (value == null) return 'edge-neutral'
  if (value > 0) return 'edge-up'
  if (value < 0) return 'edge-down'
  return 'edge-neutral'
}

const extractSlug = (input) => {
  const trimmed = input.trim()
  try {
    const url = new URL(trimmed)
    const parts = url.pathname.split('/').filter(Boolean)
    if (parts.length >= 2) return parts[parts.length - 1]
    if (parts.length === 1) return parts[0]
  } catch {
    // Treat the input as a plain slug.
  }
  return trimmed
}

const normalizePredictionResult = (payload, slug, mode) => {
  const d = payload?.data ?? payload ?? {}
  const market = d.market ?? {}
  const prediction = d.predicted_prob ?? d.prediction?.probability ?? null
  const marketOdds = market.current_odds ?? d.market_prob ?? null

  return {
    question: market.question || d.question || slug,
    marketOdds,
    prediction,
    edge: d.edge ?? (prediction != null && marketOdds != null ? prediction - marketOdds : null),
    signal: d.signal || d.prediction?.signal || null,
    reasoning: d.message || d.reasoning || null,
    confidence: d.confidence ?? d.prediction?.confidence ?? null,
    status: d.status || 'completed',
    mode,
    timestamp: Date.now(),
  }
}

const reloadOverview = async (opts = { silent: false }) => {
  const silent = opts?.silent === true
  if (!silent) {
    loading.value = true
  } else {
    refreshing.value = true
  }

  try {
    const data = await getRuntimeOverview(venue.value, 12)
    overview.value = data
    lastUpdatedAt.value = Date.now()
    error.value = ''
  } catch (err) {
    if (!overview.value) {
      error.value = err?.message || 'Failed to load runtime overview.'
    }
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

let refreshTimer = null
let pollTimer = null

const finishPrediction = () => {
  predictionLoading.value = false
  deepPolling.value = false
  progressIndex.value = progressSteps.value.length - 1
}

const runQuickMode = async (slug) => {
  predictionLoading.value = true
  predictionError.value = ''
  predictionResult.value = null
  progressIndex.value = 0

  let step = 0
  pollTimer = window.setInterval(() => {
    step += 1
    if (step < quickSteps.length - 1) {
      progressIndex.value = step
      return
    }
    window.clearInterval(pollTimer)
    pollTimer = null
  }, 1200)

  try {
    const res = await runQuickPrediction(slug)
    predictionResult.value = normalizePredictionResult(res, slug, 'quick')
    finishPrediction()
  } catch (err) {
    predictionError.value = err?.message || 'Quick prediction failed.'
    finishPrediction()
  } finally {
    if (pollTimer) {
      window.clearInterval(pollTimer)
      pollTimer = null
    }
  }
}

const deepStepMap = {
  fetching_market: 0,
  building_graph: 1,
  knowledge_graph: 1,
  setting_up: 2,
  setup: 2,
  running_simulation: 3,
  simulation: 3,
  generating_report: 4,
  report: 4,
  extracting_prediction: 4,
  extracting: 4,
  completed: 5,
  done: 5,
}

const pollDeepPrediction = (taskId, slug) => {
  deepPolling.value = true

  const poll = async () => {
    try {
      const res = await fetch(`/api/polymarket/predict/deep/${taskId}`)
      if (!res.ok) {
        throw new Error(`Polling failed (${res.status})`)
      }

      const data = await res.json()
      if (data.step && deepStepMap[data.step] !== undefined) {
        progressIndex.value = deepStepMap[data.step]
      }

      if (data.status === 'completed' || data.status === 'done') {
        predictionResult.value = normalizePredictionResult(data, slug, 'deep')
        finishPrediction()
        return
      }

      if (data.status === 'failed' || data.status === 'error') {
        throw new Error(data.message || data.error || 'Deep prediction failed.')
      }

      pollTimer = window.setTimeout(poll, 2500)
    } catch (err) {
      predictionError.value = err?.message || 'Lost connection while polling deep prediction.'
      finishPrediction()
    }
  }

  pollTimer = window.setTimeout(poll, 1500)
}

const runDeepMode = async (slug) => {
  predictionLoading.value = true
  predictionError.value = ''
  predictionResult.value = null
  progressIndex.value = 0

  try {
    const res = await runDeepPrediction(slug)
    const taskId = res?.task_id ?? res?.data?.task_id

    if (!taskId) {
      predictionResult.value = normalizePredictionResult(res, slug, 'deep')
      finishPrediction()
      return
    }

    pollDeepPrediction(taskId, slug)
  } catch (err) {
    predictionError.value = err?.message || 'Deep prediction failed.'
    finishPrediction()
  }
}

const runPrediction = () => {
  if (!canRunPrediction.value) return
  const slug = extractSlug(predictionSlug.value)

  if (pollTimer) {
    window.clearTimeout(pollTimer)
    window.clearInterval(pollTimer)
    pollTimer = null
  }

  if (predictionMode.value === 'deep') {
    runDeepMode(slug)
    return
  }

  runQuickMode(slug)
}

const clearPrediction = () => {
  predictionSlug.value = ''
  predictionError.value = ''
  predictionResult.value = null
  progressIndex.value = 0
}

const openPredictConsole = () => {
  router.push('/predict')
}

watch(venue, () => {
  reloadOverview()
})

onMounted(() => {
  reloadOverview()
  refreshTimer = window.setInterval(() => reloadOverview({ silent: true }), 30000)
})

onBeforeUnmount(() => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (pollTimer) {
    window.clearTimeout(pollTimer)
    window.clearInterval(pollTimer)
    pollTimer = null
  }
})
</script>

<style scoped>
.runtime-page {
  min-height: 100vh;
  padding: 32px 24px 72px;
  background:
    radial-gradient(circle at top left, rgba(255, 109, 24, 0.16), transparent 28%),
    radial-gradient(circle at top right, rgba(0, 0, 0, 0.08), transparent 22%),
    linear-gradient(180deg, #f7f1ea 0%, #ffffff 52%, #f7f7f5 100%);
}

.panel {
  border: 1px solid rgba(0, 0, 0, 0.08);
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(16px);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.06);
  border-radius: 24px;
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 20px;
  margin: 0 auto 20px;
  max-width: 1400px;
}

.error-banner {
  max-width: 1400px;
  margin: 0 auto 20px;
  padding: 14px 18px;
  border-left: 4px solid #b91c1c;
  color: #b91c1c;
}

.hero-copy {
  padding: 30px 30px 28px;
}

.eyebrow-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.eyebrow,
.eyebrow-muted,
.panel-kicker,
.small-badge,
.venue-chip,
.mode-btn,
.capability-pill,
.mode-pill {
  font-family: 'JetBrains Mono', monospace;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  background: #111111;
  color: #ffffff;
  border-radius: 999px;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.eyebrow-muted {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  color: #1c1c1c;
  background: rgba(255, 109, 24, 0.1);
  border-radius: 999px;
  font-size: 0.7rem;
  letter-spacing: 0.04em;
}

.hero-copy h1 {
  margin: 0;
  font-size: clamp(2.4rem, 5vw, 4.5rem);
  line-height: 0.98;
  letter-spacing: -0.06em;
}

.hero-text {
  margin: 18px 0 0;
  max-width: 760px;
  color: #4b4b4b;
  font-size: 1.02rem;
  line-height: 1.7;
}

.hero-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 22px;
}

.primary-btn,
.secondary-btn,
.ghost-btn {
  border: 0;
  border-radius: 14px;
  padding: 12px 16px;
  cursor: pointer;
  font: inherit;
  transition: transform 0.16s ease, background 0.16s ease, color 0.16s ease, opacity 0.16s ease;
}

.primary-btn:hover,
.secondary-btn:hover,
.ghost-btn:hover,
.venue-chip:hover,
.mode-btn:hover {
  transform: translateY(-1px);
}

.primary-btn {
  background: #111111;
  color: #ffffff;
}

.primary-btn:disabled,
.secondary-btn:disabled,
.ghost-btn:disabled,
.mode-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.secondary-btn {
  background: rgba(17, 17, 17, 0.06);
  color: #111111;
}

.ghost-btn {
  background: transparent;
  color: #555555;
  border: 1px solid rgba(0, 0, 0, 0.12);
}

.hero-side {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.side-panel,
.pulse-panel,
.console-panel,
.metrics-panel,
.list-panel,
.activity-panel {
  padding: 20px;
}

.panel-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.panel-kicker {
  margin: 0 0 6px;
  color: #8a5b3c;
  text-transform: uppercase;
  font-size: 0.72rem;
  letter-spacing: 0.14em;
}

.panel-top h2 {
  margin: 0;
  font-size: 1.12rem;
}

.venue-switch {
  display: inline-flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.venue-chip,
.mode-btn {
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: rgba(255, 255, 255, 0.88);
  color: #555555;
  border-radius: 999px;
  padding: 8px 12px;
  font-size: 0.78rem;
  cursor: pointer;
}

.venue-chip.active,
.mode-btn.active {
  background: #111111;
  color: #ffffff;
  border-color: #111111;
}

.status-stack {
  margin-top: 18px;
  display: grid;
  gap: 10px;
}

.status-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  color: #555555;
  font-size: 0.94rem;
}

.status-row strong {
  color: #111111;
  text-align: right;
}

.wrap {
  max-width: 210px;
}

.freshness-fresh {
  color: #0f7a3b;
}

.freshness-warm {
  color: #b26a0b;
}

.freshness-stale {
  color: #b91c1c;
}

.pulse-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: linear-gradient(140deg, #111111 0%, #2b2b2b 100%);
  color: #ffffff;
}

.pulse-label {
  font-family: 'JetBrains Mono', monospace;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 0.72rem;
  color: rgba(255, 255, 255, 0.7);
}

.pulse-value {
  font-size: 1.6rem;
  font-weight: 700;
}

.pulse-subtext {
  color: rgba(255, 255, 255, 0.8);
  line-height: 1.6;
}

.grid-two {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  max-width: 1400px;
  margin: 0 auto 20px;
}

.console-panel,
.metrics-panel,
.list-panel,
.activity-panel {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.console-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.slug-input {
  border: 1px solid rgba(0, 0, 0, 0.14);
  background: rgba(255, 255, 255, 0.92);
  border-radius: 16px;
  padding: 14px 16px;
  font: inherit;
  outline: none;
}

.slug-input:focus {
  border-color: #111111;
}

.form-actions,
.mode-toggle {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.progress-box {
  display: grid;
  gap: 10px;
  padding: 16px;
  border-radius: 16px;
  background: rgba(17, 17, 17, 0.04);
}

.progress-step {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #777777;
  font-size: 0.9rem;
}

.progress-step.active {
  color: #111111;
  font-weight: 600;
}

.progress-step.completed {
  color: #0f7a3b;
}

.step-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: currentColor;
  flex: none;
}

.error-box {
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(185, 28, 28, 0.08);
  color: #b91c1c;
}

.prediction-card {
  display: grid;
  gap: 14px;
  padding: 18px;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(17, 17, 17, 0.96), rgba(33, 33, 33, 0.96));
  color: #ffffff;
}

.prediction-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.prediction-question {
  margin: 0;
  font-size: 1.05rem;
  line-height: 1.4;
}

.prediction-meta {
  margin: 4px 0 0;
  color: rgba(255, 255, 255, 0.7);
  font-size: 0.85rem;
}

.mode-pill {
  display: inline-flex;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 0.72rem;
}

.pill-quick {
  background: rgba(255, 160, 90, 0.18);
  color: #ffd7be;
}

.pill-deep {
  background: rgba(144, 202, 249, 0.16);
  color: #dbeeff;
}

.prediction-comparison {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 12px;
  align-items: center;
}

.prediction-col,
.prediction-edge {
  padding: 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.06);
}

.label {
  display: block;
  margin-bottom: 4px;
  color: rgba(255, 255, 255, 0.65);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.prediction-col strong,
.prediction-edge strong {
  font-size: 1.2rem;
}

.edge-up {
  color: #9be7b0;
}

.edge-down {
  color: #ffb6b6;
}

.edge-neutral {
  color: #f0f0f0;
}

.prediction-details {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.detail-item {
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.06);
}

.detail-item span {
  display: block;
  color: rgba(255, 255, 255, 0.62);
  font-size: 0.78rem;
  margin-bottom: 4px;
}

.prediction-reasoning {
  padding: 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.06);
  line-height: 1.65;
}

.empty-state {
  padding: 20px;
  border-radius: 16px;
  background: rgba(17, 17, 17, 0.04);
  color: #666666;
  line-height: 1.65;
}

.empty-state.compact {
  padding: 14px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.metric-card {
  padding: 14px;
  border-radius: 16px;
  background: rgba(17, 17, 17, 0.04);
  min-height: 88px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.metric-label,
.mini-label {
  font-family: 'JetBrains Mono', monospace;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 0.72rem;
  color: #8a5b3c;
}

.metric-card strong {
  font-size: 1.35rem;
}

.sub-panels {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.mini-panel {
  padding: 14px;
  border-radius: 16px;
  background: rgba(17, 17, 17, 0.04);
  display: grid;
  gap: 6px;
}

.mini-panel strong {
  font-size: 1rem;
}

.mini-panel span {
  color: #666666;
  line-height: 1.5;
}

.capability-strip {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.capability-pill {
  padding: 7px 10px;
  border-radius: 999px;
  background: rgba(17, 17, 17, 0.04);
  color: #666666;
  font-size: 0.74rem;
}

.capability-pill.on {
  background: rgba(15, 122, 59, 0.12);
  color: #0f7a3b;
}

.small-badge {
  display: inline-flex;
  align-items: center;
  padding: 7px 10px;
  border-radius: 999px;
  background: rgba(17, 17, 17, 0.06);
  color: #444444;
  font-size: 0.72rem;
}

.run-list,
.timeline,
.intent-stack,
.alert-list {
  display: grid;
  gap: 10px;
}

.run-row,
.timeline-row,
.intent-row,
.alert-row {
  padding: 14px;
  border-radius: 16px;
  background: rgba(17, 17, 17, 0.04);
}

.run-row {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.run-id {
  font-weight: 700;
  margin-bottom: 6px;
}

.run-subline,
.timeline-meta,
.intent-row,
.alert-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #666666;
  font-size: 0.88rem;
}

.run-side {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
  text-align: right;
}

.run-stat {
  padding: 6px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.74rem;
}

.timeline-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.timeline-head span,
.timeline-meta {
  color: #7b7b7b;
  font-size: 0.82rem;
}

.alert-row {
  flex-direction: column;
}

.alert-row.low {
  border-left: 4px solid #0f7a3b;
}

.alert-row.medium {
  border-left: 4px solid #b26a0b;
}

.alert-row.high,
.alert-row.critical {
  border-left: 4px solid #b91c1c;
}

@media (max-width: 1100px) {
  .hero,
  .grid-two {
    grid-template-columns: 1fr;
  }

  .hero-side {
    flex-direction: row;
  }

  .side-panel,
  .pulse-panel {
    flex: 1;
  }
}

@media (max-width: 760px) {
  .runtime-page {
    padding: 20px 14px 56px;
  }

  .hero-copy,
  .side-panel,
  .pulse-panel,
  .console-panel,
  .metrics-panel,
  .list-panel,
  .activity-panel {
    padding: 18px;
  }

  .hero-side,
  .prediction-comparison,
  .prediction-details,
  .metric-grid,
  .sub-panels {
    grid-template-columns: 1fr;
    display: grid;
  }

  .hero-side {
    flex-direction: column;
  }

  .run-row,
  .timeline-head,
  .prediction-header,
  .panel-top {
    flex-direction: column;
  }

  .run-side {
    justify-content: flex-start;
    text-align: left;
  }
}
</style>
