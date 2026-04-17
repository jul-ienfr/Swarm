const fs = require('node:fs')
const path = require('node:path')
const { randomUUID } = require('node:crypto')

function json(response, status, payload) {
  response.statusCode = status
  response.setHeader('content-type', 'application/json; charset=utf-8')
  response.setHeader('cache-control', 'no-store')
  response.end(JSON.stringify(payload))
}

function text(response, status, payload, contentType = 'text/plain; charset=utf-8') {
  response.statusCode = status
  response.setHeader('content-type', contentType)
  response.setHeader('cache-control', 'no-store')
  response.end(payload)
}

function collectBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = []
    request.on('data', (chunk) => chunks.push(chunk))
    request.on('end', () => resolve(chunks.length > 0 ? Buffer.concat(chunks) : undefined))
    request.on('error', reject)
  })
}

function safeJsonParse(value, fallback = {}) {
  if (!value) return fallback
  try {
    return JSON.parse(String(value))
  } catch {
    return fallback
  }
}

function nowIso() {
  return new Date().toISOString()
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

function makeId(prefix, namespace) {
  return `${namespace}-${prefix}-${randomUUID().slice(0, 8)}`
}

function buildGraphData(graphId, title) {
  const nodes = [
    { id: `${graphId}-topic`, label: title, type: 'topic', size: 26 },
    { id: `${graphId}-risk`, label: 'Risk', type: 'constraint', size: 18 },
    { id: `${graphId}-execution`, label: 'Execution', type: 'process', size: 18 },
    { id: `${graphId}-agents`, label: 'Agents', type: 'social', size: 18 },
    { id: `${graphId}-report`, label: 'Report', type: 'artifact', size: 16 },
  ]
  const edges = [
    { source: `${graphId}-topic`, target: `${graphId}-risk`, label: 'bounded_by' },
    { source: `${graphId}-topic`, target: `${graphId}-execution`, label: 'implemented_by' },
    { source: `${graphId}-execution`, target: `${graphId}-agents`, label: 'driven_by' },
    { source: `${graphId}-agents`, target: `${graphId}-report`, label: 'summarized_in' },
  ]
  return {
    graph_id: graphId,
    node_count: nodes.length,
    edge_count: edges.length,
    nodes,
    edges,
    metadata: {
      generated_at: nowIso(),
      title,
      version: 'compat-v1',
    },
  }
}

function defaultProfiles(namespace) {
  return [
    {
      agent_id: 0,
      name: `${namespace.toUpperCase()} Analyst`,
      role: 'market_analyst',
      stance: 'balanced',
      influence: 0.81,
      active_hours: [8, 9, 10, 14, 15, 16, 20],
      background: 'Tracks market structure, catalysts, and execution risk.',
    },
    {
      agent_id: 1,
      name: `${namespace.toUpperCase()} Risk`,
      role: 'risk_manager',
      stance: 'defensive',
      influence: 0.72,
      active_hours: [7, 8, 13, 14, 18, 19],
      background: 'Focuses on loss prevention, exposure, and invalidation.',
    },
    {
      agent_id: 2,
      name: `${namespace.toUpperCase()} Operator`,
      role: 'operator',
      stance: 'pragmatic',
      influence: 0.69,
      active_hours: [9, 11, 12, 16, 17, 21],
      background: 'Keeps the run executable and action-oriented.',
    },
  ]
}

function defaultSimulationConfig(namespace, simulationId) {
  return {
    simulation_id: simulationId,
    platform: 'polymarket',
    max_rounds: 12,
    narrative_direction: `${namespace} compatibility simulation`,
    environment: {
      venue: 'dashboard',
      mode: 'compatibility',
      freshness_budget_ms: 1500,
    },
    agent_config: {
      profile_count: 3,
      diversity_mode: 'balanced',
    },
    event_config: {
      initial_posts: [
        {
          agent_id: 0,
          platform: 'polymarket',
          text: `Compatibility run bootstrapped for ${namespace}.`,
          round_num: 0,
        },
      ],
    },
  }
}

function defaultActions(simulationId, profiles) {
  return [
    {
      id: `${simulationId}-action-1`,
      round_num: 1,
      timestamp: nowIso(),
      platform: 'polymarket',
      action_type: 'ANALYZE',
      agent_id: profiles[0]?.agent_id ?? 0,
      agent_name: profiles[0]?.name ?? 'Analyst',
      content: 'Reviewed the current market state and updated baseline odds.',
    },
    {
      id: `${simulationId}-action-2`,
      round_num: 2,
      timestamp: nowIso(),
      platform: 'polymarket',
      action_type: 'CHALLENGE',
      agent_id: profiles[1]?.agent_id ?? 1,
      agent_name: profiles[1]?.name ?? 'Risk',
      content: 'Raised execution and liquidity caveats before promotion.',
    },
    {
      id: `${simulationId}-action-3`,
      round_num: 3,
      timestamp: nowIso(),
      platform: 'polymarket',
      action_type: 'SYNTHESIZE',
      agent_id: profiles[2]?.agent_id ?? 2,
      agent_name: profiles[2]?.name ?? 'Operator',
      content: 'Condensed the debate into a practical recommendation.',
    },
  ]
}

function buildTimeline(actions) {
  const byRound = new Map()
  for (const action of actions) {
    const round = action.round_num || 0
    const existing = byRound.get(round) || {
      round_num: round,
      total_actions: 0,
      unique_agents: new Set(),
    }
    existing.total_actions += 1
    existing.unique_agents.add(action.agent_name || action.agent_id)
    byRound.set(round, existing)
  }
  return [...byRound.values()]
    .sort((left, right) => left.round_num - right.round_num)
    .map((item) => ({
      round_num: item.round_num,
      total_actions: item.total_actions,
      unique_agents: item.unique_agents.size,
    }))
}

function buildAgentStats(profiles, actions) {
  return {
    agents: profiles.map((profile) => {
      const mine = actions.filter((action) => action.agent_id === profile.agent_id)
      return {
        agent_id: profile.agent_id,
        name: profile.name,
        role: profile.role,
        influence: profile.influence,
        action_count: mine.length,
        connections: clamp(profiles.length - 1, 0, 10),
      }
    }),
    total_agents: profiles.length,
  }
}

function buildInfluence(profiles, actions) {
  const stats = buildAgentStats(profiles, actions)
  return {
    agents: stats.agents
      .map((agent) => ({
        agent_id: agent.agent_id,
        name: agent.name,
        influence_score: Number((agent.influence * 100).toFixed(1)),
        action_count: agent.action_count,
      }))
      .sort((left, right) => right.influence_score - left.influence_score),
    total_agents: stats.total_agents,
  }
}

function defaultLegacyStore(namespace, title) {
  return {
    initialized: false,
    settings: {
      llm_provider: 'openai',
      llm_model: 'gpt-5.4-mini',
      memory_mode: 'compact',
      fallback_enabled: false,
      observability_enabled: true,
    },
    templates: [
      {
        id: `${namespace}-strategy-review`,
        title: `${title} Strategy Review`,
        description: 'Launches a multi-step analysis and meeting loop.',
        simulation_requirement: 'Review the current plan, challenge assumptions, and produce action items.',
      },
      {
        id: `${namespace}-live-ops`,
        title: `${title} Live Ops`,
        description: 'Focuses on runtime health, resilience, and operator visibility.',
        simulation_requirement: 'Stress the runtime and report operational blockers.',
      },
    ],
    projects: new Map(),
    graphs: new Map(),
    simulations: new Map(),
    reports: new Map(),
    tasks: new Map(),
  }
}

function createDashboardLegacyCompat({ namespace = 'swarm', title = 'Swarm Dashboard', dataRoot } = {}) {
  const store = defaultLegacyStore(namespace, title)
  const stateDir = dataRoot || path.resolve(__dirname, '..', 'data', 'dashboard-legacy', namespace)
  const stateFile = path.join(stateDir, 'state.json')
  const graphsDir = path.join(stateDir, 'graphs')
  const reportsDir = path.join(stateDir, 'reports')

  function ensureDirs() {
    fs.mkdirSync(stateDir, { recursive: true })
    fs.mkdirSync(graphsDir, { recursive: true })
    fs.mkdirSync(reportsDir, { recursive: true })
  }

  function snapshotStore() {
    return {
      initialized: store.initialized,
      settings: store.settings,
      templates: store.templates,
      projects: [...store.projects.values()],
      graphs: [...store.graphs.values()],
      simulations: [...store.simulations.values()],
      reports: [...store.reports.values()],
      tasks: [...store.tasks.values()],
    }
  }

  function normalizeCollection(value) {
    if (Array.isArray(value)) return value
    if (value instanceof Map) return [...value.values()]
    if (value && typeof value === 'object') return Object.values(value)
    return []
  }

  function restoreStore(snapshot) {
    const fallback = defaultLegacyStore(namespace, title)
    store.initialized = snapshot?.initialized === true
    store.settings = snapshot?.settings || fallback.settings
    store.templates = Array.isArray(snapshot?.templates) ? snapshot.templates : fallback.templates
    store.projects = new Map(normalizeCollection(snapshot?.projects).map((item) => [item.project_id, item]))
    store.graphs = new Map(normalizeCollection(snapshot?.graphs).map((item) => [item.graph_id, item]))
    store.simulations = new Map(normalizeCollection(snapshot?.simulations).map((item) => [item.simulation_id, item]))
    store.reports = new Map(normalizeCollection(snapshot?.reports).map((item) => [item.report_id, item]))
    store.tasks = new Map(normalizeCollection(snapshot?.tasks).map((item) => [item.task_id, item]))
  }

  function writeGraphArtifact(graph) {
    ensureDirs()
    fs.writeFileSync(path.join(graphsDir, `${graph.graph_id}.json`), JSON.stringify(graph, null, 2))
  }

  function writeReportArtifact(report) {
    ensureDirs()
    fs.writeFileSync(path.join(reportsDir, `${report.report_id}.md`), report.report_content || report.content || '')
  }

  function persistStore() {
    ensureDirs()
    fs.writeFileSync(stateFile, JSON.stringify(snapshotStore(), null, 2))
    for (const graph of store.graphs.values()) writeGraphArtifact(graph)
    for (const report of store.reports.values()) writeReportArtifact(report)
  }

  function loadStore() {
    ensureDirs()
    try {
      const raw = fs.readFileSync(stateFile, 'utf8')
      restoreStore(safeJsonParse(raw, {}))
    } catch {
      restoreStore(defaultLegacyStore(namespace, title))
    }
  }

  function ensureSeed() {
    if (!store.initialized) {
      loadStore()
    }
    if (store.initialized) return
    store.initialized = true

    const projectId = `${namespace}-demo-project`
    const graphId = `${namespace}-demo-graph`
    const simulationId = `${namespace}-demo-simulation`
    const reportId = `${namespace}-demo-report`
    const profiles = defaultProfiles(namespace)
    const actions = defaultActions(simulationId, profiles)
    const timeline = buildTimeline(actions)
    const project = {
      project_id: projectId,
      name: `${title} Demo Project`,
      status: 'graph_completed',
      graph_id: graphId,
      created_at: nowIso(),
      updated_at: nowIso(),
      files: [
        { name: 'brief.md', type: 'markdown', size: 2048 },
      ],
      simulation_requirement: `Demonstrate the ${namespace} compatibility dashboard flow end-to-end.`,
    }
    const simulation = {
      simulation_id: simulationId,
      project_id: projectId,
      status: 'completed',
      platform: 'polymarket',
      profiles,
      config: defaultSimulationConfig(namespace, simulationId),
      current_round: timeline.at(-1)?.round_num ?? 3,
      total_rounds: timeline.at(-1)?.round_num ?? 3,
      total_actions: actions.length,
      actions,
      timeline,
      created_at: nowIso(),
      updated_at: nowIso(),
      report_id: reportId,
      env_alive: false,
    }
    const report = {
      report_id: reportId,
      simulation_id: simulationId,
      project_id: projectId,
      status: 'completed',
      summary: `${title} compatibility report completed successfully.`,
      content: `# ${title}\n\nThis is a compatibility report generated by the vendored dashboard shim.`,
      report_content: `# ${title}\n\nThis is a compatibility report generated by the vendored dashboard shim.`,
      generated_at: nowIso(),
      agent_log: actions.map((action, index) => ({
        line: index + 1,
        action: action.action_type.toLowerCase(),
        agent_name: action.agent_name,
        text: action.content,
        timestamp: action.timestamp,
      })),
      console_log: [
        { line: 1, level: 'info', text: `${title} compatibility report bootstrapped.`, timestamp: nowIso() },
      ],
    }

    store.projects.set(projectId, project)
    store.graphs.set(graphId, buildGraphData(graphId, project.name))
    store.simulations.set(simulationId, simulation)
    store.reports.set(reportId, report)
    persistStore()
  }

  function projectById(projectId) {
    ensureSeed()
    return store.projects.get(projectId) || [...store.projects.values()][0]
  }

  function simulationById(simulationId) {
    ensureSeed()
    return store.simulations.get(simulationId) || [...store.simulations.values()][0]
  }

  function reportById(reportId) {
    ensureSeed()
    return store.reports.get(reportId) || [...store.reports.values()][0]
  }

  function taskById(taskId) {
    ensureSeed()
    return store.tasks.get(taskId)
  }

  async function readJsonBody(request) {
    const body = await collectBody(request)
    return safeJsonParse(body ? body.toString('utf8') : '', {})
  }

  async function handle(request, response, requestUrl) {
    ensureSeed()
    const pathname = requestUrl.pathname
    const method = request.method || 'GET'

    if (method === 'GET' && pathname === '/api/settings') {
      json(response, 200, { success: true, data: store.settings })
      return true
    }

    if (method === 'POST' && pathname === '/api/settings') {
      const body = await readJsonBody(request)
      store.settings = { ...store.settings, ...(body || {}) }
      persistStore()
      json(response, 200, { success: true, data: store.settings })
      return true
    }

    if (method === 'POST' && pathname === '/api/settings/test-llm') {
      json(response, 200, {
        success: true,
        data: {
          provider: store.settings.llm_provider,
          model: store.settings.llm_model,
          status: 'ok',
          latency_ms: 184,
        },
      })
      return true
    }

    if (method === 'GET' && pathname === '/api/templates/list') {
      json(response, 200, { success: true, data: store.templates })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/templates/')) {
      const templateId = decodeURIComponent(pathname.slice('/api/templates/'.length))
      const found = store.templates.find((template) => template.id === templateId) || store.templates[0]
      json(response, 200, { success: true, data: found })
      return true
    }

    if (method === 'POST' && pathname === '/api/graph/ontology/generate') {
      const projectId = makeId('project', namespace)
      const graphId = makeId('graph', namespace)
      const project = {
        project_id: projectId,
        name: `${title} Imported Project`,
        status: 'ontology_generated',
        graph_id: null,
        created_at: nowIso(),
        updated_at: nowIso(),
        files: [{ name: 'upload.md', type: 'markdown', size: 1024 }],
        simulation_requirement: 'Imported via compatibility upload.',
      }
      store.projects.set(projectId, project)
      store.graphs.set(graphId, buildGraphData(graphId, project.name))
      persistStore()
      json(response, 200, { success: true, data: project })
      return true
    }

    if (method === 'POST' && pathname === '/api/graph/build') {
      const body = await readJsonBody(request)
      const project = projectById(body.project_id)
      const taskId = makeId('graph-task', namespace)
      const graphId = project.graph_id || makeId('graph', namespace)
      project.status = 'graph_completed'
      project.graph_id = graphId
      project.updated_at = nowIso()
      store.projects.set(project.project_id, project)
      if (!store.graphs.has(graphId)) {
        store.graphs.set(graphId, buildGraphData(graphId, project.name))
      }
      store.tasks.set(taskId, {
        task_id: taskId,
        status: 'completed',
        progress: 100,
        message: 'Graph build completed.',
        graph_id: graphId,
        project_id: project.project_id,
      })
      persistStore()
      json(response, 200, { success: true, data: { task_id: taskId, graph_id: graphId, project_id: project.project_id } })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/graph/task/')) {
      const taskId = decodeURIComponent(pathname.slice('/api/graph/task/'.length))
      const task = taskById(taskId) || {
        task_id: taskId,
        status: 'completed',
        progress: 100,
        message: 'Task completed.',
      }
      json(response, 200, { success: true, data: task })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/graph/data/')) {
      const graphId = decodeURIComponent(pathname.slice('/api/graph/data/'.length))
      const graph = store.graphs.get(graphId) || [...store.graphs.values()][0]
      json(response, 200, { success: true, data: graph })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/graph/project/')) {
      const projectId = decodeURIComponent(pathname.slice('/api/graph/project/'.length))
      json(response, 200, { success: true, data: projectById(projectId) })
      return true
    }

    if (method === 'POST' && pathname === '/api/graph/fetch-url') {
      const body = await readJsonBody(request)
      const url = body.url || 'https://example.com'
      json(response, 200, {
        success: true,
        data: {
          url,
          title: 'Fetched compatibility document',
          text: `Compatibility snapshot extracted from ${url}.`,
          char_count: 64,
        },
      })
      return true
    }

    if (method === 'POST' && pathname === '/api/simulation/create') {
      const body = await readJsonBody(request)
      const project = projectById(body.project_id)
      const simulationId = makeId('simulation', namespace)
      const reportId = makeId('report', namespace)
      const profiles = defaultProfiles(namespace)
      const actions = defaultActions(simulationId, profiles)
      const timeline = buildTimeline(actions)
      const simulation = {
        simulation_id: simulationId,
        project_id: project.project_id,
        report_id: reportId,
        status: 'created',
        platform: body.enable_twitter ? 'twitter' : body.enable_reddit ? 'reddit' : 'polymarket',
        profiles,
        config: defaultSimulationConfig(namespace, simulationId),
        current_round: 0,
        total_rounds: timeline.at(-1)?.round_num ?? 3,
        total_actions: actions.length,
        actions,
        timeline,
        created_at: nowIso(),
        updated_at: nowIso(),
        env_alive: false,
      }
      store.simulations.set(simulationId, simulation)
      store.reports.set(reportId, {
        ...reportById(`${namespace}-demo-report`),
        report_id: reportId,
        simulation_id: simulationId,
        project_id: project.project_id,
      })
      persistStore()
      json(response, 200, { success: true, data: simulation })
      return true
    }

    if (method === 'POST' && pathname === '/api/simulation/prepare') {
      const body = await readJsonBody(request)
      const simulation = simulationById(body.simulation_id)
      const taskId = makeId('prepare-task', namespace)
      simulation.status = 'prepared'
      simulation.updated_at = nowIso()
      store.simulations.set(simulation.simulation_id, simulation)
      store.tasks.set(taskId, {
        task_id: taskId,
        status: 'completed',
        progress: 100,
        message: 'Profiles and environment prepared.',
        generation_stage: 'completed',
        simulation_id: simulation.simulation_id,
      })
      persistStore()
      json(response, 200, { success: true, data: { task_id: taskId, simulation_id: simulation.simulation_id } })
      return true
    }

    if (method === 'POST' && pathname === '/api/simulation/prepare/status') {
      const body = await readJsonBody(request)
      const task = taskById(body.task_id) || {
        task_id: body.task_id || makeId('prepare-task', namespace),
        status: 'completed',
        progress: 100,
        generation_stage: 'completed',
        message: 'Preparation complete.',
        data: {
          profiles_generated: 3,
        },
      }
      json(response, 200, { success: true, data: task })
      return true
    }

    if (method === 'GET' && pathname === '/api/simulation/list') {
      const items = [...store.simulations.values()]
      json(response, 200, { success: true, data: items })
      return true
    }

    if (method === 'GET' && pathname === '/api/simulation/history') {
      const items = [...store.simulations.values()].map((simulation) => ({
        simulation_id: simulation.simulation_id,
        project_id: simulation.project_id,
        report_id: simulation.report_id,
        created_at: simulation.created_at,
        current_round: simulation.current_round,
        total_rounds: simulation.total_rounds,
        files: projectById(simulation.project_id)?.files || [],
        simulation_requirement: projectById(simulation.project_id)?.simulation_requirement || '',
      }))
      json(response, 200, { success: true, data: items })
      return true
    }

    if (method === 'POST' && pathname === '/api/simulation/start') {
      const body = await readJsonBody(request)
      const simulation = simulationById(body.simulation_id)
      simulation.status = 'completed'
      simulation.current_round = Number(body.max_rounds || simulation.total_rounds || 3)
      simulation.total_rounds = simulation.current_round
      simulation.updated_at = nowIso()
      store.simulations.set(simulation.simulation_id, simulation)
      persistStore()
      json(response, 200, { success: true, data: { simulation_id: simulation.simulation_id, status: simulation.status } })
      return true
    }

    if (method === 'POST' && (pathname === '/api/simulation/stop' || pathname === '/api/simulation/close-env')) {
      const body = await readJsonBody(request)
      const simulation = simulationById(body.simulation_id)
      simulation.status = 'stopped'
      simulation.env_alive = false
      simulation.updated_at = nowIso()
      store.simulations.set(simulation.simulation_id, simulation)
      persistStore()
      json(response, 200, { success: true, data: { simulation_id: simulation.simulation_id, status: simulation.status } })
      return true
    }

    if (method === 'POST' && pathname === '/api/simulation/restart-env') {
      const body = await readJsonBody(request)
      const simulation = simulationById(body.simulation_id)
      simulation.env_alive = true
      store.simulations.set(simulation.simulation_id, simulation)
      persistStore()
      json(response, 200, { success: true, data: { simulation_id: simulation.simulation_id, env_alive: true } })
      return true
    }

    if (method === 'POST' && pathname === '/api/simulation/env-status') {
      const body = await readJsonBody(request)
      const simulation = simulationById(body.simulation_id)
      json(response, 200, {
        success: true,
        data: {
          simulation_id: simulation.simulation_id,
          env_alive: Boolean(simulation.env_alive),
          status: simulation.status,
        },
      })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/simulation/') && pathname.endsWith('/profiles/realtime')) {
      const simulationId = decodeURIComponent(pathname.split('/')[3] || '')
      const simulation = simulationById(simulationId)
      json(response, 200, { success: true, data: { profiles: simulation.profiles || [] } })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/simulation/') && pathname.endsWith('/profiles')) {
      const simulationId = decodeURIComponent(pathname.split('/')[3] || '')
      const simulation = simulationById(simulationId)
      json(response, 200, { success: true, data: simulation.profiles || [] })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/simulation/') && pathname.endsWith('/config/realtime')) {
      const simulationId = decodeURIComponent(pathname.split('/')[3] || '')
      const simulation = simulationById(simulationId)
      json(response, 200, { success: true, data: { config: simulation.config } })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/simulation/') && pathname.endsWith('/config')) {
      const simulationId = decodeURIComponent(pathname.split('/')[3] || '')
      const simulation = simulationById(simulationId)
      json(response, 200, { success: true, data: simulation.config })
      return true
    }

    if (method === 'POST' && pathname.startsWith('/api/simulation/') && pathname.endsWith('/config/retry')) {
      const simulationId = decodeURIComponent(pathname.split('/')[3] || '')
      const simulation = simulationById(simulationId)
      json(response, 200, { success: true, data: simulation.config })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/simulation/') && pathname.endsWith('/run-status/detail')) {
      const simulationId = decodeURIComponent(pathname.split('/')[3] || '')
      const simulation = simulationById(simulationId)
      json(response, 200, {
        success: true,
        data: {
          simulation_id: simulation.simulation_id,
          status: simulation.status,
          current_round: simulation.current_round,
          total_rounds: simulation.total_rounds,
          all_actions: simulation.actions,
          recent_actions: simulation.actions.slice(-10),
        },
      })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/simulation/') && pathname.endsWith('/run-status')) {
      const simulationId = decodeURIComponent(pathname.split('/')[3] || '')
      const simulation = simulationById(simulationId)
      json(response, 200, {
        success: true,
        data: {
          simulation_id: simulation.simulation_id,
          status: simulation.status,
          current_round: simulation.current_round,
          total_rounds: simulation.total_rounds,
          actions_count: simulation.total_actions,
        },
      })
      return true
    }

    if (method === 'GET' && pathname === '/api/simulation/compare') {
      const id1 = requestUrl.searchParams.get('id1')
      const id2 = requestUrl.searchParams.get('id2')
      const sim1 = simulationById(id1)
      const sim2 = simulationById(id2 || [...store.simulations.keys()][1] || sim1.simulation_id)
      json(response, 200, {
        success: true,
        data: {
          sim1: {
            simulation_id: sim1.simulation_id,
            profiles_count: sim1.profiles.length,
            total_actions: sim1.actions.length,
            timeline: sim1.timeline,
          },
          sim2: {
            simulation_id: sim2.simulation_id,
            profiles_count: sim2.profiles.length,
            total_actions: sim2.actions.length,
            timeline: sim2.timeline,
          },
        },
      })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/simulation/') && pathname.endsWith('/posts')) {
      const simulationId = decodeURIComponent(pathname.split('/')[3] || '')
      const simulation = simulationById(simulationId)
      const posts = simulation.actions.map((action) => ({
        id: action.id,
        round_num: action.round_num,
        text: action.content,
        agent_name: action.agent_name,
        platform: action.platform,
        timestamp: action.timestamp,
      }))
      json(response, 200, { success: true, data: { posts, total: posts.length } })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/simulation/') && pathname.endsWith('/timeline')) {
      const simulationId = decodeURIComponent(pathname.split('/')[3] || '')
      const simulation = simulationById(simulationId)
      json(response, 200, { success: true, data: simulation.timeline })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/simulation/') && pathname.endsWith('/agent-stats')) {
      const simulationId = decodeURIComponent(pathname.split('/')[3] || '')
      const simulation = simulationById(simulationId)
      json(response, 200, { success: true, data: buildAgentStats(simulation.profiles, simulation.actions) })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/simulation/') && pathname.endsWith('/actions')) {
      const simulationId = decodeURIComponent(pathname.split('/')[3] || '')
      const simulation = simulationById(simulationId)
      json(response, 200, { success: true, data: { actions: simulation.actions } })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/simulation/') && pathname.endsWith('/influence')) {
      const simulationId = decodeURIComponent(pathname.split('/')[3] || '')
      const simulation = simulationById(simulationId)
      json(response, 200, { success: true, data: buildInfluence(simulation.profiles, simulation.actions) })
      return true
    }

    if (method === 'GET' && pathname.startsWith('/api/simulation/') && pathname.endsWith('/export')) {
      const simulationId = decodeURIComponent(pathname.split('/')[3] || '')
      const simulation = simulationById(simulationId)
      text(response, 200, JSON.stringify(simulation, null, 2), 'application/json; charset=utf-8')
      return true
    }

    if (method === 'POST' && pathname === '/api/simulation/interview/batch') {
      const body = await readJsonBody(request)
      const interviews = Array.isArray(body.interviews) ? body.interviews : []
      json(response, 200, {
        success: true,
        data: {
          responses: interviews.map((item, index) => ({
            agent_id: item.agent_id ?? index,
            prompt: item.prompt || '',
            response: 'Compatibility interview response generated locally.',
          })),
        },
      })
      return true
    }

    if (method === 'GET' && /^\/api\/simulation\/[^/]+$/.test(pathname)) {
      const simulationId = decodeURIComponent(pathname.split('/')[3] || '')
      json(response, 200, { success: true, data: simulationById(simulationId) })
      return true
    }

    if (method === 'POST' && pathname === '/api/report/generate') {
      const body = await readJsonBody(request)
      const simulation = simulationById(body.simulation_id)
      const reportId = simulation.report_id || makeId('report', namespace)
      store.reports.set(reportId, {
        report_id: reportId,
        simulation_id: simulation.simulation_id,
        project_id: simulation.project_id,
        status: 'completed',
        summary: `${title} report generated from simulation ${simulation.simulation_id}.`,
        content: `# ${title}\n\nGenerated report for ${simulation.simulation_id}.`,
        report_content: `# ${title}\n\nGenerated report for ${simulation.simulation_id}.`,
        generated_at: nowIso(),
        agent_log: simulation.actions.map((action, index) => ({
          line: index + 1,
          action: action.action_type.toLowerCase(),
          agent_name: action.agent_name,
          text: action.content,
          timestamp: action.timestamp,
        })),
        console_log: [
          { line: 1, level: 'info', text: 'Report generated successfully.', timestamp: nowIso() },
        ],
      })
      simulation.report_id = reportId
      store.simulations.set(simulation.simulation_id, simulation)
      persistStore()
      json(response, 200, { success: true, data: { report_id: reportId, simulation_id: simulation.simulation_id } })
      return true
    }

    if (method === 'GET' && pathname === '/api/report/generate/status') {
      const reportId = requestUrl.searchParams.get('report_id') || `${namespace}-demo-report`
      json(response, 200, { success: true, data: { report_id: reportId, status: 'completed', progress: 100 } })
      return true
    }

    if (method === 'GET' && /^\/api\/report\/[^/]+\/agent-log$/.test(pathname)) {
      const reportId = decodeURIComponent(pathname.split('/')[3] || '')
      const fromLine = Number(requestUrl.searchParams.get('from_line') || '0')
      const report = reportById(reportId)
      const logs = (report.agent_log || []).filter((entry) => entry.line >= fromLine)
      json(response, 200, { success: true, data: { logs, lines: logs, next_line: logs.length + fromLine } })
      return true
    }

    if (method === 'GET' && /^\/api\/report\/[^/]+\/console-log$/.test(pathname)) {
      const reportId = decodeURIComponent(pathname.split('/')[3] || '')
      const fromLine = Number(requestUrl.searchParams.get('from_line') || '0')
      const report = reportById(reportId)
      const logs = (report.console_log || []).filter((entry) => entry.line >= fromLine)
      json(response, 200, { success: true, data: { logs, lines: logs, next_line: logs.length + fromLine } })
      return true
    }

    if (method === 'POST' && pathname === '/api/report/chat') {
      const body = await readJsonBody(request)
      json(response, 200, {
        success: true,
        data: {
          reply: `Compatibility chat reply: ${body.message || 'No question provided.'}`,
          messages: [
            ...(Array.isArray(body.chat_history) ? body.chat_history : []),
            { role: 'assistant', content: `Compatibility chat reply: ${body.message || 'No question provided.'}` },
          ],
        },
      })
      return true
    }

    if (method === 'GET' && /^\/api\/report\/[^/]+$/.test(pathname)) {
      const reportId = decodeURIComponent(pathname.split('/')[3] || '')
      json(response, 200, { success: true, data: reportById(reportId) })
      return true
    }

    if (method === 'GET' && pathname === '/api/observability/events') {
      const simulationId = requestUrl.searchParams.get('simulation_id')
      const simulation = simulationById(simulationId)
      const events = (simulation.actions || []).map((action, index) => ({
        line: index + 1,
        event_type: index === 0 ? 'llm_call' : index === 1 ? 'agent_decision' : 'tool_result',
        timestamp: action.timestamp,
        simulation_id: simulation.simulation_id,
        agent_name: action.agent_name,
        payload: action,
      }))
      json(response, 200, { success: true, data: { events } })
      return true
    }

    if (method === 'GET' && pathname === '/api/observability/stats') {
      json(response, 200, {
        success: true,
        data: {
          llm_calls: 3,
          tokens_input: 2100,
          tokens_output: 1200,
          tokens_total: 3300,
          avg_latency_ms: 842,
          errors: 0,
          events_by_type: { llm_call: 1, agent_decision: 1, tool_result: 1 },
          models_used: { 'gpt-5.4-mini': 3 },
        },
      })
      return true
    }

    if (method === 'GET' && pathname === '/api/observability/llm-calls') {
      json(response, 200, {
        success: true,
        data: {
          calls: [
            {
              id: `${namespace}-llm-1`,
              caller: 'compatibility',
              model: 'gpt-5.4-mini',
              latency_ms: 842,
              tokens_input: 700,
              tokens_output: 400,
              timestamp: nowIso(),
            },
          ],
        },
      })
      return true
    }

    if (method === 'GET' && pathname === '/api/observability/events/stream') {
      response.writeHead(200, {
        'Content-Type': 'text/event-stream; charset=utf-8',
        'Cache-Control': 'no-store',
        Connection: 'keep-alive',
      })
      const payload = JSON.stringify({
        event_type: 'compatibility_ready',
        namespace,
        timestamp: nowIso(),
      })
      response.write(`data: ${payload}\n\n`)
      const timer = setInterval(() => {
        try {
          response.write(': keepalive\n\n')
        } catch {
          clearInterval(timer)
        }
      }, 15000)
      request.on('close', () => clearInterval(timer))
      return true
    }

    return false
  }

  return { handle }
}

module.exports = { createDashboardLegacyCompat }
