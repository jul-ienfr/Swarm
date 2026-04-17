<template>
  <div class="network-panel">
    <div class="panel-header">
      <span class="panel-title">Agent Network</span>
      <div class="header-tools">
        <span class="node-count" v-if="networkStats.nodes">{{ networkStats.nodes }} agents · {{ networkStats.edges }} links</span>
        <button class="tool-btn" @click="resetView" title="Reset View">
          <span class="icon-refresh">↻</span>
          <span class="btn-text">Reset</span>
        </button>
      </div>
    </div>

    <!-- Round Scrubber -->
    <div class="round-scrubber" v-if="maxRound > 0">
      <div class="scrubber-row">
        <button class="scrub-btn" @click="playPause">
          {{ isPlaying ? '⏸' : '▶' }}
        </button>
        <input
          type="range"
          class="round-slider"
          :min="0"
          :max="maxRound"
          v-model.number="currentRound"
          @input="onRoundChange"
        />
        <span class="round-label">
          <template v-if="currentRound === 0">ALL</template>
          <template v-else>R{{ currentRound }}/{{ maxRound }}</template>
        </span>
      </div>
    </div>

    <!-- Network Graph -->
    <div class="network-container" ref="networkContainer">
      <svg ref="networkSvg" class="network-svg"></svg>

      <!-- Selected Agent Detail -->
      <div v-if="selectedAgent" class="agent-detail">
        <div class="detail-header">
          <div class="agent-avatar" :style="{ background: selectedAgent.color }">{{ selectedAgent.name[0] }}</div>
          <div class="agent-meta">
            <span class="agent-name">{{ selectedAgent.name }}</span>
            <span class="agent-stats-line">{{ selectedAgent.actionCount }} actions · {{ selectedAgent.connections }} connections</span>
          </div>
          <button class="detail-close" @click="selectedAgent = null">×</button>
        </div>
        <div class="platform-breakdown">
          <div v-for="(count, platform) in selectedAgent.platforms" :key="platform" class="platform-bar">
            <span class="bar-label" :class="platform">{{ platform }}</span>
            <div class="bar-track">
              <div class="bar-fill" :class="platform" :style="{ width: (count / selectedAgent.actionCount * 100) + '%' }"></div>
            </div>
            <span class="bar-count">{{ count }}</span>
          </div>
        </div>
        <div class="interaction-types" v-if="selectedAgent.interactionTypes">
          <span v-for="(count, type) in selectedAgent.interactionTypes" :key="type" class="interaction-tag">
            {{ type }} <strong>{{ count }}</strong>
          </span>
        </div>
      </div>

      <!-- Empty State -->
      <div v-if="!hasData" class="empty-state">
        <div class="pulse-ring"></div>
        <span>Waiting for agent interactions...</span>
      </div>
    </div>

    <!-- Legend -->
    <div class="network-legend" v-if="hasData">
      <span class="legend-title">Platforms</span>
      <div class="legend-items">
        <div class="legend-item"><span class="legend-dot" style="background: #0A0A0A"></span><span>X</span></div>
        <div class="legend-item"><span class="legend-dot" style="background: #FF6B1A"></span><span>Reddit</span></div>
        <div class="legend-item"><span class="legend-dot" style="background: #43C165"></span><span>Polymarket</span></div>
      </div>
      <div class="legend-hint">Node size = activity · Edge thickness = interactions</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as d3 from 'd3'
import { getSimulationActions } from '../api/simulation'

const props = defineProps({
  simulationId: String,
  isSimulating: Boolean
})

const networkContainer = ref(null)
const networkSvg = ref(null)
const selectedAgent = ref(null)
const currentRound = ref(0) // 0 = show all rounds
const maxRound = ref(0)
const isPlaying = ref(false)
const allActions = ref([])
const hasData = ref(false)

let simulation = null
let playTimer = null
let pollTimer = null

const networkStats = computed(() => {
  const data = buildNetworkData()
  return { nodes: data.nodes.length, edges: data.edges.length }
})

// Build network from actions, filtered by current round
const buildNetworkData = () => {
  let actions = allActions.value
  if (currentRound.value > 0) {
    actions = actions.filter(a => a.round_num <= currentRound.value)
  }

  const agentMap = {}
  const edgeMap = {}

  // Build agent nodes
  actions.forEach(a => {
    if (!a.agent_name) return
    if (!agentMap[a.agent_name]) {
      agentMap[a.agent_name] = {
        id: a.agent_name,
        name: a.agent_name,
        actionCount: 0,
        platforms: {},
        interactionTypes: {},
        connections: 0
      }
    }
    const agent = agentMap[a.agent_name]
    agent.actionCount++
    agent.platforms[a.platform] = (agent.platforms[a.platform] || 0) + 1
    const actionLabel = a.action_type?.replace(/_/g, ' ').toLowerCase() || 'unknown'
    agent.interactionTypes[actionLabel] = (agent.interactionTypes[actionLabel] || 0) + 1
  })

  // Build edges from interactions
  actions.forEach(a => {
    if (!a.agent_name) return
    const src = a.agent_name

    // Reply/comment on someone's post
    let target = null
    if (a.action_type === 'CREATE_COMMENT' && a.action_args?.post_author_name) {
      target = a.action_args.post_author_name
    } else if (a.action_type === 'LIKE_POST' && a.action_args?.post_author_name) {
      target = a.action_args.post_author_name
    } else if (a.action_type === 'DISLIKE_POST' && a.action_args?.post_author_name) {
      target = a.action_args.post_author_name
    } else if (a.action_type === 'REPOST' && a.action_args?.original_author_name) {
      target = a.action_args.original_author_name
    } else if (a.action_type === 'QUOTE_POST' && a.action_args?.original_author_name) {
      target = a.action_args.original_author_name
    } else if (a.action_type === 'FOLLOW' && a.action_args?.target_user_name) {
      target = a.action_args.target_user_name
    } else if (a.action_type === 'LIKE_COMMENT' && a.action_args?.comment_author_name) {
      target = a.action_args.comment_author_name
    } else if (a.action_type === 'DISLIKE_COMMENT' && a.action_args?.comment_author_name) {
      target = a.action_args.comment_author_name
    }

    if (target && target !== src && agentMap[target]) {
      const edgeKey = [src, target].sort().join('|||')
      if (!edgeMap[edgeKey]) {
        edgeMap[edgeKey] = { source: src, target: target, weight: 0, types: {} }
      }
      edgeMap[edgeKey].weight++
      const typeKey = a.action_type?.replace(/_/g, ' ').toLowerCase() || 'unknown'
      edgeMap[edgeKey].types[typeKey] = (edgeMap[edgeKey].types[typeKey] || 0) + 1
    }
  })

  // Count connections per agent
  const edges = Object.values(edgeMap)
  edges.forEach(e => {
    if (agentMap[e.source]) agentMap[e.source].connections++
    if (agentMap[e.target]) agentMap[e.target].connections++
  })

  const nodes = Object.values(agentMap)

  // Assign colors based on dominant platform
  const platformColors = { twitter: '#0A0A0A', reddit: '#FF6B1A', polymarket: '#43C165' }
  nodes.forEach(n => {
    let maxP = ''
    let maxC = 0
    Object.entries(n.platforms).forEach(([p, c]) => {
      if (c > maxC) { maxC = c; maxP = p }
    })
    n.color = platformColors[maxP] || '#7A7A7A'
  })

  return { nodes, edges }
}

const renderNetwork = () => {
  if (!networkSvg.value || !networkContainer.value) return

  const data = buildNetworkData()
  if (data.nodes.length === 0) {
    hasData.value = false
    return
  }
  hasData.value = true

  if (simulation) simulation.stop()

  const container = networkContainer.value
  const width = container.clientWidth
  const height = container.clientHeight

  const svg = d3.select(networkSvg.value)
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', `0 0 ${width} ${height}`)

  svg.selectAll('*').remove()

  // Scale node radius by action count
  const maxActions = Math.max(...data.nodes.map(n => n.actionCount), 1)
  const radiusScale = d3.scaleSqrt().domain([1, maxActions]).range([6, 24])

  // Scale edge width by weight
  const maxWeight = Math.max(...data.edges.map(e => e.weight), 1)
  const widthScale = d3.scaleLinear().domain([1, maxWeight]).range([1, 6])

  // Deep copy nodes/edges for D3 mutation
  const nodes = data.nodes.map(n => ({ ...n }))
  const edges = data.edges.map(e => ({ ...e }))

  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id(d => d.id).distance(100))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collide', d3.forceCollide(d => radiusScale(d.actionCount) + 4))
    .force('x', d3.forceX(width / 2).strength(0.05))
    .force('y', d3.forceY(height / 2).strength(0.05))

  const g = svg.append('g')

  // Zoom
  svg.call(d3.zoom().scaleExtent([0.1, 4]).on('zoom', (event) => {
    g.attr('transform', event.transform)
  }))

  // Edges
  const link = g.append('g').selectAll('line')
    .data(edges)
    .enter().append('line')
    .attr('stroke', 'rgba(250,250,250,0.12)')
    .attr('stroke-width', d => widthScale(d.weight))

  // Nodes
  const node = g.append('g').selectAll('g')
    .data(nodes)
    .enter().append('g')
    .style('cursor', 'pointer')
    .call(d3.drag()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart()
        d.fx = d.x; d.fy = d.y
      })
      .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0)
        d.fx = null; d.fy = null
      })
    )
    .on('click', (event, d) => {
      event.stopPropagation()
      selectedAgent.value = d
    })

  // Node circles
  node.append('circle')
    .attr('r', d => radiusScale(d.actionCount))
    .attr('fill', d => d.color)
    .attr('stroke', 'rgba(10,10,10,0.6)')
    .attr('stroke-width', 2)

  // Node labels
  node.append('text')
    .text(d => d.name.length > 10 ? d.name.substring(0, 10) + '…' : d.name)
    .attr('font-size', '10px')
    .attr('fill', 'rgba(250,250,250,0.8)')
    .attr('font-weight', '500')
    .attr('dx', d => radiusScale(d.actionCount) + 4)
    .attr('dy', 4)
    .style('pointer-events', 'none')
    .style('font-family', "'Space Mono', 'Courier New', monospace")

  simulation.on('tick', () => {
    link
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y)

    node.attr('transform', d => `translate(${d.x},${d.y})`)
  })

  // Click blank to deselect
  svg.on('click', () => { selectedAgent.value = null })
}

const resetView = () => {
  currentRound.value = 0
  renderNetwork()
}

const onRoundChange = () => {
  isPlaying.value = false
  if (playTimer) { clearInterval(playTimer); playTimer = null }
  renderNetwork()
}

const playPause = () => {
  if (isPlaying.value) {
    isPlaying.value = false
    if (playTimer) { clearInterval(playTimer); playTimer = null }
    return
  }
  if (currentRound.value >= maxRound.value) currentRound.value = 0
  isPlaying.value = true
  playTimer = setInterval(() => {
    currentRound.value++
    renderNetwork()
    if (currentRound.value >= maxRound.value) {
      isPlaying.value = false
      clearInterval(playTimer)
      playTimer = null
    }
  }, 800)
}

// Fetch actions from API
const fetchActions = async () => {
  if (!props.simulationId) return
  try {
    const res = await getSimulationActions(props.simulationId, { limit: 5000 })
    if (res.success && res.data) {
      const actions = Array.isArray(res.data) ? res.data : (res.data.actions || [])
      allActions.value = actions
      const rounds = actions.map(a => a.round_num || 0)
      maxRound.value = rounds.length > 0 ? Math.max(...rounds) : 0
      renderNetwork()
    }
  } catch (e) {
    console.warn('Failed to fetch actions for network:', e)
  }
}

// Poll for new data during simulation
const startPolling = () => {
  if (pollTimer) return
  pollTimer = setInterval(fetchActions, 5000)
}

const stopPolling = () => {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

watch(() => props.isSimulating, (val) => {
  if (val) startPolling()
  else stopPolling()
}, { immediate: true })

watch(() => props.simulationId, () => {
  allActions.value = []
  maxRound.value = 0
  currentRound.value = 0
  fetchActions()
}, { immediate: true })

const handleResize = () => { nextTick(renderNetwork) }

let resizeObserver = null

onMounted(() => {
  window.addEventListener('resize', handleResize)
  if (networkContainer.value) {
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect.width > 0 && entry.contentRect.height > 0) {
          nextTick(renderNetwork)
        }
      }
    })
    resizeObserver.observe(networkContainer.value)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (resizeObserver) resizeObserver.disconnect()
  if (simulation) simulation.stop()
  if (playTimer) clearInterval(playTimer)
  stopPolling()
})
</script>

<style scoped>
.network-panel {
  position: relative;
  width: 100%;
  height: 100%;
  background-color: #0A0A0A;
  background-image:
    linear-gradient(rgba(255,107,26,0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,107,26,0.04) 1px, transparent 1px);
  background-size: 70px 70px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Corner markers */
.network-panel::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, #FF6B1A 40px, transparent 40px, transparent calc(100% - 40px), #FF6B1A calc(100% - 40px));
  z-index: 30;
  pointer-events: none;
}

.network-panel::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, #43C165 40px, transparent 40px, transparent calc(100% - 40px), #43C165 calc(100% - 40px));
  z-index: 30;
  pointer-events: none;
}

.panel-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding: 16px 20px;
  z-index: 10;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(to bottom, rgba(10,10,10,0.95), rgba(10,10,10,0));
  pointer-events: none;
}

.panel-title {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  color: rgba(250,250,250,0.5);
  text-transform: uppercase;
  letter-spacing: 3px;
  pointer-events: auto;
}

.header-tools {
  pointer-events: auto;
  display: flex;
  gap: 12px;
  align-items: center;
}

.node-count {
  font-family: var(--font-mono);
  font-size: 10px;
  color: rgba(250,250,250,0.35);
  text-transform: uppercase;
  letter-spacing: 2px;
}

.tool-btn {
  height: 32px;
  padding: 0 12px;
  border: 2px solid rgba(250,250,250,0.12);
  background: rgba(10,10,10,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  color: rgba(250,250,250,0.5);
  transition: all 0.2s;
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.tool-btn:hover {
  background: rgba(250,250,250,0.1);
  color: #FAFAFA;
  border-color: #FF6B1A;
}

.btn-text {
  font-size: 11px;
  font-family: var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 1px;
}

/* Round Scrubber */
.round-scrubber {
  position: absolute;
  top: 56px;
  left: 20px;
  right: 20px;
  z-index: 10;
  background: rgba(10,10,10,0.85);
  backdrop-filter: blur(8px);
  padding: 8px 14px;
  border: 2px solid rgba(250,250,250,0.08);
}

.scrubber-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.scrub-btn {
  width: 28px;
  height: 28px;
  border: 2px solid rgba(250,250,250,0.15);
  background: transparent;
  color: #FAFAFA;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}

.scrub-btn:hover {
  border-color: #FF6B1A;
  background: rgba(255,107,26,0.1);
}

.round-slider {
  flex: 1;
  -webkit-appearance: none;
  appearance: none;
  height: 4px;
  background: rgba(250,250,250,0.15);
  outline: none;
}

.round-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  background: #FF6B1A;
  cursor: pointer;
}

.round-slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  background: #FF6B1A;
  border: none;
  cursor: pointer;
}

.round-label {
  font-family: var(--font-mono);
  font-size: 11px;
  color: #FF6B1A;
  font-weight: 700;
  min-width: 60px;
  text-align: right;
  letter-spacing: 1px;
}

/* Network Container */
.network-container {
  flex: 1;
  width: 100%;
  position: relative;
}

.network-svg {
  width: 100%;
  height: 100%;
  display: block;
}

/* Agent Detail Panel */
.agent-detail {
  position: absolute;
  bottom: 24px;
  right: 24px;
  width: 280px;
  background: #FAFAFA;
  border: 2px solid rgba(10,10,10,0.08);
  z-index: 20;
  font-family: var(--font-mono);
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  background: var(--color-gray, #F5F5F5);
  border-bottom: 2px solid rgba(10,10,10,0.08);
}

.agent-avatar {
  width: 28px;
  height: 28px;
  min-width: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #FAFAFA;
  font-weight: 700;
  font-size: 13px;
  text-transform: uppercase;
}

.agent-meta {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.agent-detail .agent-name {
  font-size: 12px;
  font-weight: 600;
  color: #0A0A0A;
}

.agent-stats-line {
  font-size: 10px;
  color: rgba(10,10,10,0.4);
  letter-spacing: 1px;
}

.detail-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: rgba(10,10,10,0.4);
  padding: 0;
}

.detail-close:hover {
  color: rgba(10,10,10,0.7);
}

.platform-breakdown {
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.platform-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bar-label {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2px;
  min-width: 60px;
  color: rgba(10,10,10,0.5);
}

.bar-label.twitter { color: #0A0A0A; }
.bar-label.reddit { color: #FF6B1A; }
.bar-label.polymarket { color: #43C165; }

.bar-track {
  flex: 1;
  height: 6px;
  background: rgba(10,10,10,0.06);
}

.bar-fill {
  height: 100%;
  transition: width 0.3s;
}

.bar-fill.twitter { background: #0A0A0A; }
.bar-fill.reddit { background: #FF6B1A; }
.bar-fill.polymarket { background: #43C165; }

.bar-count {
  font-size: 10px;
  font-weight: 600;
  color: rgba(10,10,10,0.7);
  min-width: 20px;
  text-align: right;
}

.interaction-types {
  padding: 8px 14px 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  border-top: 1px solid rgba(10,10,10,0.06);
}

.interaction-tag {
  font-size: 9px;
  padding: 2px 6px;
  background: rgba(10,10,10,0.04);
  border: 1px solid rgba(10,10,10,0.08);
  color: rgba(10,10,10,0.5);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.interaction-tag strong {
  color: rgba(10,10,10,0.7);
  margin-left: 2px;
}

/* Empty State */
.empty-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  color: rgba(250,250,250,0.2);
  font-family: var(--font-mono);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 3px;
}

.pulse-ring {
  width: 32px;
  height: 32px;
  border: 2px solid #FF6B1A;
  animation: ripple 2s infinite;
}

@keyframes ripple {
  0% { transform: scale(0.8); opacity: 1; border-color: #FF6B1A; }
  100% { transform: scale(2.5); opacity: 0; border-color: rgba(255,107,26,0.1); }
}

/* Legend */
.network-legend {
  position: absolute;
  bottom: 24px;
  left: 24px;
  background: rgba(10,10,10,0.85);
  backdrop-filter: blur(8px);
  padding: 12px 16px;
  border: 2px solid rgba(250,250,250,0.08);
  z-index: 10;
}

.legend-title {
  display: block;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  color: #FF6B1A;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 3px;
}

.legend-items {
  display: flex;
  gap: 14px;
  margin-bottom: 6px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: rgba(250,250,250,0.5);
}

.legend-dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
}

.legend-hint {
  font-family: var(--font-mono);
  font-size: 9px;
  color: rgba(250,250,250,0.25);
  letter-spacing: 1px;
}
</style>
