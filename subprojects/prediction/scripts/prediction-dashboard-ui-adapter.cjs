#!/usr/bin/env node

const http = require('node:http')
const fs = require('node:fs')
const path = require('node:path')
const { Readable } = require('node:stream')
const { URL } = require('node:url')
const { randomUUID } = require('node:crypto')
const { createDashboardLegacyCompat } = require('../../../scripts/dashboard-legacy-compat.cjs')

const DEFAULT_HOST = process.env.PREDICTION_DASHBOARD_UI_ADAPTER_HOST || '127.0.0.1'
const DEFAULT_PORT = Number(process.env.PREDICTION_DASHBOARD_UI_ADAPTER_PORT || 5001)
const DEFAULT_UPSTREAM = process.env.PREDICTION_BASE_URL || process.env.MC_URL || 'http://127.0.0.1:3000'
const DEFAULT_VENUE = process.env.PREDICTION_DEFAULT_VENUE || 'polymarket'
const DEFAULT_LIMIT = 20
const PORTFOLIO_BASE_BALANCE = 10000
const DASHBOARD_UI_DIST_DIR = path.resolve(__dirname, '..', 'dashboard-ui', 'dist')
const DEFAULT_STATE_FILE = process.env.PREDICTION_DASHBOARD_UI_STATE_FILE || path.resolve(__dirname, '..', 'data', 'dashboard-ui-adapter-state.json')
const legacyCompat = createDashboardLegacyCompat({
  namespace: 'prediction',
  title: 'Prediction Dashboard',
})
let currentStateFile = DEFAULT_STATE_FILE

const DEFAULT_PRESETS = {
  balanced: {
    stages: {
      ontology: 'gpt-5.4-mini',
      graph: 'gpt-5.4-mini',
      profiles: 'gpt-5.4-mini',
      simulation: 'gpt-5.4',
      report: 'gpt-5.4-mini',
    },
  },
  quality: {
    stages: {
      ontology: 'gpt-5.4',
      graph: 'gpt-5.4',
      profiles: 'gpt-5.4',
      simulation: 'gpt-5.4',
      report: 'gpt-5.4-mini',
    },
  },
  cheap: {
    stages: {
      ontology: 'gpt-5.4-nano',
      graph: 'gpt-5.4-mini',
      profiles: 'gpt-5.4-mini',
      simulation: 'gpt-5.4-mini',
      report: 'gpt-5.4-nano',
    },
  },
}

function ensureStateDir() {
  fs.mkdirSync(path.dirname(currentStateFile), { recursive: true })
}

function createTaskId(prefix) {
  return `${prefix}_${randomUUID().slice(0, 10)}`
}

function defaultAdapterState() {
  return {
    seeded: false,
    pipeline_preset: 'balanced',
    presets: DEFAULT_PRESETS,
    autopilot: {
      max_deep_per_cycle: 3,
      max_cost_per_cycle: 15,
      min_edge_for_deep: 0.05,
      min_edge_for_bet: 0.03,
      cycle_interval_hours: 6,
      niche_focus: true,
      quick_research: false,
      max_markets_to_scan: 50,
      days_ahead: 7,
      min_volume: 500,
      cost_per_deep: 4,
    },
    strategy: {
      kelly_factor: 0.25,
      odds_range: [0.1, 0.9],
      max_bet_pct: 0.05,
      min_edge_threshold: 0.03,
      category_weights: {},
    },
    method_weights: {
      llm_weight: 0.5,
      quant_weight: 0.5,
    },
    custom: {
      max_rounds: 40,
      entity_type_limit: 20,
      deep_research: true,
      agent_diversity: true,
      prediction_method: 'combined',
      llm_weight_override: 0.5,
      engine_mode: 'quick',
      cash_reserve: 0.2,
      max_sector_exposure: 0.4,
      excluded_slugs: '',
      target_slugs: '',
      market_categories: ['politics', 'crypto', 'macro', 'sports', 'science'],
    },
    api_keys: {
      openai: false,
      anthropic: false,
      gemini: false,
      deepseek: false,
      zep: false,
      ollama: false,
    },
    portfolio: {
      balance: PORTFOLIO_BASE_BALANCE,
      open_positions: [],
      resolved: [],
      performance: {
        total_bets: 0,
        total_pnl: 0,
        win_rate: 0,
        roi: 0,
      },
    },
    knowledge_entries: [],
    ledger_entries: [],
    autopilot_runs: {},
    backtests: {
      latest: null,
      incremental: null,
      tasks: {},
    },
    deep_predictions: {},
    last_reset_at: null,
  }
}

function readAdapterState() {
  ensureStateDir()
  try {
    const raw = fs.readFileSync(currentStateFile, 'utf8')
    return {
      ...defaultAdapterState(),
      ...safeJsonParse(raw, {}),
    }
  } catch {
    return defaultAdapterState()
  }
}

function writeAdapterState(state) {
  ensureStateDir()
  fs.writeFileSync(currentStateFile, JSON.stringify(state, null, 2))
}

function printHelp() {
  console.log(
    [
      'prediction-dashboard-ui-adapter usage:',
      '  node scripts/prediction-dashboard-ui-adapter.cjs [--host 127.0.0.1] [--port 5001] [--upstream http://127.0.0.1:3000]',
      '',
      'Standalone adapter for copied dashboard UIs.',
      'It proxies the canonical prediction-markets runtime and synthesizes a few legacy /api/polymarket endpoints.',
      '',
      'Supported endpoints:',
      '  GET  /healthz',
      '  GET  /api/polymarket/stats',
      '  GET  /api/polymarket/calibration',
      '  GET  /api/polymarket/portfolio',
      '  GET  /api/polymarket/portfolio/history',
      '  GET  /api/polymarket/prediction/:id',
      '  POST /api/polymarket/predict',
      '  POST /api/polymarket/predict/deep',
      '',
      'Upstream proxy targets:',
      '  /api/v1/prediction-markets/*',
      '  /api/v1/prediction-markets/dashboard/*',
      '  /prediction-markets/dashboard',
      '',
      'Flags:',
      '  --host       Host interface to bind.',
      '  --port       Local port to bind.',
      '  --upstream   Upstream base URL that already serves prediction-markets v1 routes.',
      '  --state-file Optional isolated persistence file for adapter state.',
      '  --help       Show this help.',
      '',
      'Environment:',
      `  PREDICTION_DASHBOARD_UI_ADAPTER_HOST=${DEFAULT_HOST}`,
      `  PREDICTION_DASHBOARD_UI_ADAPTER_PORT=${DEFAULT_PORT}`,
      `  PREDICTION_BASE_URL=${DEFAULT_UPSTREAM}`,
      `  PREDICTION_DEFAULT_VENUE=${DEFAULT_VENUE}`,
      `  PREDICTION_DASHBOARD_UI_STATE_FILE=${DEFAULT_STATE_FILE}`,
    ].join('\n'),
  )
}

function parseArgs(argv) {
  const options = {
    host: DEFAULT_HOST,
    port: DEFAULT_PORT,
    upstream: DEFAULT_UPSTREAM,
    stateFile: DEFAULT_STATE_FILE,
    help: false,
  }

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    const next = argv[index + 1]

    if (arg === '--help' || arg === '-h') {
      options.help = true
      continue
    }
    if (arg === '--host' && next) {
      options.host = next
      index += 1
      continue
    }
    if (arg === '--port' && next) {
      options.port = Number(next)
      index += 1
      continue
    }
    if (arg === '--upstream' && next) {
      options.upstream = next
      index += 1
      continue
    }
    if (arg === '--state-file' && next) {
      options.stateFile = path.resolve(next)
      index += 1
      continue
    }
  }

  return options
}

function isObject(value) {
  return value != null && typeof value === 'object' && !Array.isArray(value)
}

function asArray(value) {
  if (Array.isArray(value)) return value
  if (value == null) return []
  return [value]
}

function firstDefined(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null) return value
  }
  return undefined
}

function asNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function pickNumber(...values) {
  for (const value of values) {
    const number = asNumber(value)
    if (number !== null) return number
  }
  return null
}

function pickString(...values) {
  for (const value of values) {
    if (typeof value !== 'string') continue
    const text = value.trim()
    if (text) return text
  }
  return null
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

function nowIso() {
  return new Date().toISOString()
}

function safeJsonParse(value) {
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

function mergeQueryParams(url, extraParams = {}) {
  const merged = new URL(url.toString())
  for (const [key, value] of Object.entries(extraParams)) {
    if (value == null) continue
    merged.searchParams.set(key, String(value))
  }
  return merged
}

function collectBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = []
    request.on('data', (chunk) => chunks.push(chunk))
    request.on('end', () => resolve(chunks.length > 0 ? Buffer.concat(chunks) : undefined))
    request.on('error', reject)
  })
}

async function readJsonBody(request) {
  const body = await collectBody(request)
  return safeJsonParse(body ? body.toString('utf8') : '', {})
}

function copyRequestHeaders(sourceHeaders) {
  const headers = new Headers()
  for (const [key, value] of Object.entries(sourceHeaders)) {
    if (value == null) continue
    const normalized = key.toLowerCase()
    if (
      normalized === 'host' ||
      normalized === 'connection' ||
      normalized === 'content-length' ||
      normalized === 'transfer-encoding' ||
      normalized === 'upgrade' ||
      normalized === 'accept-encoding'
    ) {
      continue
    }
    headers.set(key, Array.isArray(value) ? value.join(',') : value)
  }
  return headers
}

function copyResponseHeaders(source, response) {
  source.headers.forEach((value, key) => {
    const normalized = key.toLowerCase()
    if (
      normalized === 'content-encoding' ||
      normalized === 'transfer-encoding' ||
      normalized === 'connection' ||
      normalized === 'keep-alive' ||
      normalized === 'upgrade' ||
      normalized === 'content-length'
    ) {
      return
    }
    response.setHeader(key, value)
  })
}

async function readJsonResponse(response) {
  const contentType = response.headers.get('content-type') || ''
  const text = await response.text()
  if (!text) return null
  if (contentType.includes('application/json') || contentType.includes('+json')) {
    try {
      return JSON.parse(text)
    } catch {
      return { raw: text }
    }
  }
  return safeJsonParse(text)
}

async function fetchUpstreamJson(upstreamBase, pathname, { searchParams, headers, method = 'GET', body } = {}) {
  const url = new URL(pathname, upstreamBase)
  if (searchParams) {
    const params = searchParams instanceof URLSearchParams ? searchParams : new URLSearchParams(searchParams)
    for (const [key, value] of params.entries()) {
      url.searchParams.set(key, value)
    }
  }

  const response = await fetch(url, {
    method,
    headers,
    body,
  })

  const parsed = await readJsonResponse(response)
  return {
    ok: response.ok,
    status: response.status,
    headers: response.headers,
    json: parsed,
    url: url.toString(),
  }
}

function writeJson(response, status, payload, extraHeaders = {}) {
  response.statusCode = status
  response.setHeader('content-type', 'application/json; charset=utf-8')
  response.setHeader('cache-control', 'no-store')
  for (const [key, value] of Object.entries(extraHeaders)) {
    response.setHeader(key, value)
  }
  response.end(JSON.stringify(payload))
}

function writeText(response, status, payload, contentType = 'text/plain; charset=utf-8') {
  response.statusCode = status
  response.setHeader('content-type', contentType)
  response.setHeader('cache-control', 'no-store')
  response.end(payload)
}

function contentTypeFor(filePath) {
  const extension = path.extname(filePath).toLowerCase()
  if (extension === '.html') return 'text/html; charset=utf-8'
  if (extension === '.js') return 'application/javascript; charset=utf-8'
  if (extension === '.css') return 'text/css; charset=utf-8'
  if (extension === '.json') return 'application/json; charset=utf-8'
  if (extension === '.svg') return 'image/svg+xml'
  if (extension === '.png') return 'image/png'
  if (extension === '.jpg' || extension === '.jpeg') return 'image/jpeg'
  if (extension === '.woff') return 'font/woff'
  if (extension === '.woff2') return 'font/woff2'
  return 'application/octet-stream'
}

function tryServeStatic(response, baseDir, relativePath) {
  const safeRelative = relativePath.replace(/^\/+/, '') || 'index.html'
  const resolved = path.resolve(baseDir, safeRelative)
  if (!resolved.startsWith(baseDir + path.sep) && resolved !== path.join(baseDir, 'index.html')) {
    return false
  }
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
    return false
  }
  const payload = fs.readFileSync(resolved)
  writeText(response, 200, payload, contentTypeFor(resolved))
  return true
}

async function proxyToUpstream(request, response, upstreamBase, targetPath) {
  const requestUrl = new URL(request.url || '/', `http://${request.headers.host || 'localhost'}`)
  const body = request.method && request.method !== 'GET' && request.method !== 'HEAD' ? await collectBody(request) : undefined
  const headers = copyRequestHeaders(request.headers)
  const upstreamUrl = new URL(targetPath || requestUrl.pathname, upstreamBase)
  upstreamUrl.search = requestUrl.search

  const upstreamResponse = await fetch(upstreamUrl, {
    method: request.method,
    headers,
    body,
  })

  response.statusCode = upstreamResponse.status
  copyResponseHeaders(upstreamResponse, response)

  if (!upstreamResponse.body) {
    response.end()
    return
  }

  const stream = Readable.fromWeb(upstreamResponse.body)
  stream.on('error', (error) => {
    try {
      response.destroy(error)
    } catch {
      // best effort shutdown
    }
  })
  stream.pipe(response)
}

function normalizeRunRecord(record) {
  if (!isObject(record)) return null

  const predictionYes = pickNumber(
    record.probability_yes,
    record.prediction,
    record.predicted_prob,
    record.market_prob,
    record.current_odds,
    record.odds,
    record.confidence,
  )
  const edgeBps = pickNumber(record.edge_bps, record.edgeBps, record.benchmark_edge_bps)
  const marketOdds = pickNumber(record.market_odds, record.current_odds, record.odds, predictionYes)
  const prediction = pickNumber(record.prediction, record.predicted_prob, record.probability_yes, predictionYes)
  const question = pickString(
    record.question,
    record.market_question,
    record.market_title,
    record.title,
    record.summary,
    record.market_slug,
    record.slug,
    record.market_id,
    record.run_id,
  )
  const slug = pickString(record.market_slug, record.slug)
  const marketId = pickString(record.market_id, record.run_id, slug, question)
  const recommendation = pickString(record.recommendation, record.signal, record.decision)
  const resolvedOutcome = record.resolved_outcome ?? record.resolved ?? record.outcome ?? null
  const resolvedBoolean = typeof resolvedOutcome === 'boolean' ? resolvedOutcome : null
  const confidence = pickNumber(record.confidence, record.probability_yes, record.prediction_confidence)
  const side = pickString(record.side) ?? (prediction != null && marketOdds != null ? (prediction >= marketOdds ? 'YES' : 'NO') : null)

  return {
    raw: record,
    market_id: marketId,
    question,
    slug,
    mode: pickString(record.mode, record.selected_path_effective_mode, record.selected_path, recommendation) ?? 'quick',
    side: side ?? 'YES',
    odds: marketOdds,
    prediction,
    edge: prediction != null && marketOdds != null ? prediction - marketOdds : edgeBps != null ? edgeBps / 10000 : null,
    amount: estimateStakeUsd(edgeBps, confidence, recommendation),
    outcome: resolvedBoolean == null ? null : resolvedBoolean ? 'WIN' : 'LOSS',
    pnl: estimateExpectedPnl(estimateStakeUsd(edgeBps, confidence, recommendation), prediction, marketOdds, resolvedBoolean),
    placed_at: pickString(record.created_at, record.placed_at, record.updated_at),
    closes_at: pickString(record.closes_at, record.close_at, record.close_time),
    resolved: resolvedBoolean != null ? resolvedBoolean : false,
    report_summary: pickString(record.report_summary, record.reportSummary, record.execution_summary, record.strategy_summary),
    confidence,
    key_factors: asArray(record.key_factors || record.keyFactors).filter((value) => typeof value === 'string'),
  }
}

function estimateStakeUsd(edgeBps, confidence, recommendation) {
  const edgeComponent = edgeBps == null ? 0 : clamp(Math.abs(edgeBps) / 80, 0, 180)
  const confidenceComponent = confidence == null ? 0 : clamp(confidence * 120, 0, 120)
  const recommendationComponent = recommendation === 'bet' || recommendation === 'buy' ? 40 : 0
  const stake = 25 + edgeComponent + confidenceComponent + recommendationComponent
  return Math.round(clamp(stake, 25, 250))
}

function estimateExpectedPnl(amount, prediction, marketOdds, resolvedOutcome) {
  if (!Number.isFinite(amount) || amount <= 0) return 0
  if (typeof resolvedOutcome === 'boolean') {
    const direction = resolvedOutcome ? 1 : -1
    const probability = prediction ?? marketOdds ?? 0.5
    return Number((amount * direction * (probability - 0.5) * 2).toFixed(2))
  }
  if (prediction == null || marketOdds == null) return 0
  return Number((amount * (prediction - marketOdds)).toFixed(2))
}

function unwrapRuns(payload) {
  const root = isObject(payload) ? payload : {}
  const candidates = [
    root.runs,
    root.items,
    root.data?.runs,
    root.data?.items,
    root.overview?.runs,
    root.dashboard?.runs,
  ]
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) return candidate
  }
  return []
}

function unwrapObject(payload) {
  if (!isObject(payload)) return null
  if (isObject(payload.data)) return payload.data
  return payload
}

function buildStatsPayload({ overview, runs, benchmark, health }) {
  const overviewObject = unwrapObject(overview) || {}
  const benchmarkObject = unwrapObject(benchmark) || {}
  const healthObject = unwrapObject(health) || {}
  const runItems = unwrapRuns(runs)

  const totalPredictions = pickNumber(
    overviewObject.metrics?.runs,
    overviewObject.total,
    runs?.total,
    runItems.length,
  ) ?? 0

  const itemsWithSignals = runItems.filter((item) => {
    if (!isObject(item)) return false
    return [
      item.recommendation,
      item.signal,
      item.probability_yes,
      item.prediction,
      item.predicted_prob,
      item.edge_bps,
      item.edgeBps,
      item.confidence,
    ].some((value) => value !== undefined && value !== null)
  })

  const edgeValues = itemsWithSignals
    .map((item) => pickNumber(item.edge_bps, item.edgeBps))
    .filter((value) => value !== null)
    .map((value) => value / 10000)

  const accuracyValue = pickNumber(
    overviewObject.validation?.paper?.win_rate,
    overviewObject.validation?.backtest?.win_rate,
    benchmarkObject.validation?.paper?.win_rate,
    benchmarkObject.validation?.backtest?.win_rate,
    overviewObject.metrics?.accuracy,
  )

  const averageEdge = edgeValues.length > 0
    ? edgeValues.reduce((sum, value) => sum + value, 0) / edgeValues.length
    : pickNumber(overviewObject.metrics?.average_edge, benchmarkObject.average_edge)

  const payload = {
    success: true,
    venue: DEFAULT_VENUE,
    source: 'prediction-dashboard-ui-adapter',
    totalPredictions,
    total_predictions: totalPredictions,
    marketsWithSignals: itemsWithSignals.length,
    markets_with_signals: itemsWithSignals.length,
    averageEdge,
    average_edge: averageEdge,
    accuracy: accuracyValue == null ? null : accuracyValue > 1 ? accuracyValue / 100 : accuracyValue,
    generated_at: pickString(overviewObject.generated_at, benchmarkObject.generated_at) ?? new Date().toISOString(),
    upstream: {
      health: healthObject,
      overview: overviewObject,
      benchmark: benchmarkObject,
      run_count: runItems.length,
    },
    data: {
      totalPredictions,
      total_predictions: totalPredictions,
      marketsWithSignals: itemsWithSignals.length,
      markets_with_signals: itemsWithSignals.length,
      averageEdge,
      average_edge: averageEdge,
      accuracy: accuracyValue == null ? null : accuracyValue > 1 ? accuracyValue / 100 : accuracyValue,
    },
  }

  return payload
}

function bucketRange(lower, upper) {
  const start = Math.round(lower * 100)
  const end = Math.round(upper * 100)
  return `${start}-${end}%`
}

function buildCalibrationPayload({ benchmark, runs, overview }) {
  const benchmarkObject = unwrapObject(benchmark) || {}
  const overviewObject = unwrapObject(overview) || {}
  const runItems = unwrapRuns(runs)

  const scored = runItems
    .map((item) => {
      if (!isObject(item)) return null
      const predicted = pickNumber(item.probability_yes, item.prediction, item.predicted_prob, item.confidence)
      if (predicted == null) return null
      const actualBoolean = typeof item.resolved_outcome === 'boolean'
        ? item.resolved_outcome
        : typeof item.resolved === 'boolean'
          ? item.resolved
          : item.outcome === 'WIN'
            ? true
            : item.outcome === 'LOSS'
              ? false
              : item.result === 'win'
                ? true
                : item.result === 'loss'
                  ? false
                  : null
      return {
        predicted,
        actual: actualBoolean == null ? null : actualBoolean ? 1 : 0,
      }
    })
    .filter(Boolean)

  const bins = Array.from({ length: 10 }, (_, index) => {
    const lower = index / 10
    const upper = (index + 1) / 10
    const binItems = scored.filter((item) => item.predicted >= lower && (index === 9 ? item.predicted <= upper : item.predicted < upper))
    const actualItems = binItems.filter((item) => item.actual != null)
    const actualRate = actualItems.length > 0
      ? actualItems.reduce((sum, item) => sum + item.actual, 0) / actualItems.length
      : null
    return {
      range: bucketRange(lower, upper),
      predictedRange: bucketRange(lower, upper),
      actualRate,
      count: binItems.length,
    }
  }).filter((bin) => bin.count > 0 || bin.actualRate != null)

  const observedError = scored.filter((item) => item.actual != null).map((item) => Math.abs(item.predicted - item.actual))
  const brierScore = pickNumber(
    benchmarkObject.brier_score,
    overviewObject.validation?.backtest?.brier_score,
    overviewObject.validation?.paper?.brier_score,
    overviewObject.validation?.replay?.brier_score,
  )
  const calibrationError = pickNumber(
    benchmarkObject.ece,
    benchmarkObject.calibration_error,
    benchmarkObject.calibrationError,
  ) ?? (observedError.length > 0 ? observedError.reduce((sum, value) => sum + value, 0) / observedError.length : null)

  return {
    success: true,
    venue: DEFAULT_VENUE,
    source: 'prediction-dashboard-ui-adapter',
    brierScore,
    brier_score: brierScore,
    calibrationError,
    calibration_error: calibrationError,
    bins,
    generated_at: pickString(benchmarkObject.generated_at, overviewObject.generated_at) ?? new Date().toISOString(),
    upstream: {
      benchmark: benchmarkObject,
      overview: overviewObject,
      run_count: runItems.length,
    },
    data: {
      brierScore,
      brier_score: brierScore,
      calibrationError,
      calibration_error: calibrationError,
      bins,
    },
  }
}

function buildPortfolioPayload({ overview, runs, benchmark }) {
  const overviewObject = unwrapObject(overview) || {}
  const benchmarkObject = unwrapObject(benchmark) || {}
  const runItems = unwrapRuns(runs).map(normalizeRunRecord).filter(Boolean)

  const openPositions = runItems
    .filter((item) => item && (item.raw?.recommendation === 'bet' || item.raw?.selected_path === 'live' || item.raw?.live_promotable === true))
    .slice(0, 12)
    .map((item) => ({
      market_id: item.market_id,
      question: item.question,
      slug: item.slug,
      odds: item.odds,
      prediction: item.prediction,
      side: item.side,
      amount: item.amount,
      outcome: item.outcome,
      pnl: item.pnl,
      closes_at: item.closes_at,
      placed_at: item.placed_at,
      resolved: item.resolved,
    }))

  const totalStake = openPositions.reduce((sum, item) => sum + (Number(item.amount) || 0), 0)
  const totalPnl = openPositions.reduce((sum, item) => sum + (Number(item.pnl) || 0), 0)
  const wins = openPositions.filter((item) => item.outcome === 'WIN').length
  const resolvedCount = openPositions.filter((item) => item.outcome != null).length
  const winRate = resolvedCount > 0 ? (wins / resolvedCount) * 100 : pickNumber(
    overviewObject.validation?.paper?.win_rate,
    overviewObject.validation?.backtest?.win_rate,
    benchmarkObject.validation?.paper?.win_rate,
    benchmarkObject.validation?.backtest?.win_rate,
  )
  const roi = totalStake > 0 ? (totalPnl / totalStake) * 100 : totalPnl === 0 ? 0 : (totalPnl / PORTFOLIO_BASE_BALANCE) * 100
  const balance = Math.max(0, PORTFOLIO_BASE_BALANCE - totalStake)

  return {
    success: true,
    venue: DEFAULT_VENUE,
    source: 'prediction-dashboard-ui-adapter',
    data: {
      balance,
      total_value: Number((balance + totalStake + totalPnl).toFixed(2)),
      open_positions: openPositions,
      performance: {
        total_bets: openPositions.length,
        total_pnl: Number(totalPnl.toFixed(2)),
        win_rate: winRate == null ? null : winRate > 1 ? winRate : winRate * 100,
        roi: Number(roi.toFixed(2)),
      },
    },
    upstream: {
      overview: overviewObject,
      benchmark: benchmarkObject,
      run_count: runItems.length,
    },
  }
}

async function buildPredictionPayload(upstreamBase, request, id) {
  const headers = copyRequestHeaders(request.headers)
  const direct = await fetchUpstreamJson(upstreamBase, `/api/v1/prediction-markets/runs/${encodeURIComponent(id)}`, {
    headers,
  })

  let runPayload = direct.ok ? direct.json : null

  if (!runPayload || (isObject(runPayload) && runPayload.error)) {
    const listResponse = await fetchUpstreamJson(upstreamBase, '/api/v1/prediction-markets/runs', {
      headers,
      searchParams: { venue: DEFAULT_VENUE, limit: 100 },
    })
    const candidates = unwrapRuns(listResponse.json)
    const found = candidates.find((item) => {
      if (!isObject(item)) return false
      return [
        item.run_id,
        item.market_id,
        item.market_slug,
        item.slug,
      ].some((value) => String(value || '') === id)
    })
    if (!found) return null
    runPayload = found
  }

  const normalized = normalizeRunRecord(runPayload)
  if (!normalized) return null

  const simulation = {
    agent_count: pickNumber(runPayload?.strategy?.strategy_counts?.total, runPayload?.validation?.paper?.sample_count, 3),
    rounds: pickNumber(runPayload?.validation?.backtest?.window_count, runPayload?.validation?.paper?.sample_count, 0),
    total_interactions: pickNumber(runPayload?.validation?.monte_carlo?.trial_count, runPayload?.validation?.paper?.trial_count, 0),
  }

  return {
    success: true,
    data: {
      bet: {
        id: normalized.market_id,
        question: normalized.question,
        slug: normalized.slug,
        mode: normalized.mode,
        side: normalized.side,
        resolved: normalized.resolved,
        odds: normalized.odds,
        prediction: normalized.prediction,
        edge: normalized.edge,
        amount: normalized.amount,
        confidence: normalized.confidence,
        pnl: normalized.pnl,
        placed_at: normalized.placed_at,
        closes_at: normalized.closes_at,
        key_factors: normalized.key_factors,
        report_summary: normalized.report_summary,
      },
      simulation,
      run: runPayload,
      source: 'prediction-dashboard-ui-adapter',
    },
  }
}

async function fetchDashboardSnapshot(upstreamBase, headers) {
  const safeFetch = async (pathname, searchParams) => {
    try {
      return await fetchUpstreamJson(upstreamBase, pathname, { headers, searchParams })
    } catch {
      return { ok: false, status: 502, json: null, headers: new Headers() }
    }
  }

  const [overview, runs, benchmark, health] = await Promise.all([
    safeFetch('/api/v1/prediction-markets/dashboard/overview', { venue: DEFAULT_VENUE, limit: DEFAULT_LIMIT }),
    safeFetch('/api/v1/prediction-markets/dashboard/runs', { venue: DEFAULT_VENUE, limit: 100 }),
    safeFetch('/api/v1/prediction-markets/dashboard/benchmark', { venue: DEFAULT_VENUE }),
    safeFetch('/api/v1/prediction-markets/health', { venue: DEFAULT_VENUE }),
  ])

  return {
    overview: overview.json,
    runs: runs.json,
    benchmark: benchmark.json,
    health: health.json,
  }
}

function inferCategory(question = '') {
  const text = String(question).toLowerCase()
  if (text.includes('bitcoin') || text.includes('crypto') || text.includes('eth')) return 'crypto'
  if (text.includes('election') || text.includes('senate') || text.includes('trump') || text.includes('president')) return 'politics'
  if (text.includes('fed') || text.includes('inflation') || text.includes('rate') || text.includes('gdp')) return 'macro'
  if (text.includes('nba') || text.includes('nfl') || text.includes('world cup') || text.includes('goal')) return 'sports'
  if (text.includes('trial') || text.includes('drug') || text.includes('launch') || text.includes('science')) return 'science'
  return 'other'
}

function deriveConsensus(item) {
  const confidence = pickNumber(item.confidence, item.prediction)
  if (confidence == null) return 'mixed'
  if (confidence >= 0.7) return 'strong'
  if (confidence >= 0.55) return 'mixed'
  return 'weak'
}

function buildKnowledgeEntries(runItems) {
  return runItems.map((item, index) => ({
    id: item.market_id || `knowledge_${index}`,
    market_id: item.market_id,
    question: item.question,
    category: inferCategory(item.question),
    our_prediction: item.prediction,
    market_odds_at_prediction: item.odds,
    edge: item.edge,
    agent_consensus: deriveConsensus(item.raw || item),
    was_correct: item.outcome === 'WIN' ? true : item.outcome === 'LOSS' ? false : null,
    timestamp: item.placed_at || item.closes_at || nowIso(),
    slug: item.slug,
    key_factors: item.key_factors || [],
  }))
}

function buildKnowledgeStats(entries) {
  const categories = {}
  const outcomes = { correct: 0, incorrect: 0, pending: 0 }

  for (const entry of entries) {
    const category = entry.category || 'other'
    const bucket = categories[category] || { correct: 0, total: 0, pending: 0, accuracy: 0 }
    if (entry.was_correct === true) {
      bucket.correct += 1
      bucket.total += 1
      outcomes.correct += 1
    } else if (entry.was_correct === false) {
      bucket.total += 1
      outcomes.incorrect += 1
    } else {
      bucket.pending += 1
      outcomes.pending += 1
    }
    bucket.accuracy = bucket.total > 0 ? bucket.correct / bucket.total : 0
    categories[category] = bucket
  }

  return {
    total_entries: entries.length,
    categories,
    outcomes,
    accuracy: categories,
  }
}

function buildLedgerEntries(runItems) {
  const entries = []
  runItems.forEach((item, index) => {
    const cycleId = `seed-cycle-${Math.floor(index / 3) + 1}`
    entries.push({
      id: `ledger-place-${index}`,
      entry_type: 'BET_PLACED',
      cycle_id: cycleId,
      timestamp: item.placed_at || nowIso(),
      question: item.question,
      explanation: item.report_summary || 'Position opened from seeded runtime history.',
      data: {
        side: item.side,
        amount: item.amount,
        edge: item.edge,
        mode: item.mode,
        prediction: item.prediction,
        market_prob: item.odds,
        confidence: item.confidence,
      },
    })
    if (item.outcome != null) {
      entries.push({
        id: `ledger-resolve-${index}`,
        entry_type: 'BET_RESOLVED',
        cycle_id: cycleId,
        timestamp: item.closes_at || item.placed_at || nowIso(),
        question: item.question,
        explanation: `Resolved as ${item.outcome}.`,
        data: {
          won: item.outcome === 'WIN',
          pnl: item.pnl,
          resolved: 1,
          prediction: item.prediction,
          market_prob: item.odds,
        },
      })
    }
  })
  return entries.sort((left, right) => String(right.timestamp).localeCompare(String(left.timestamp)))
}

function buildPortfolioPerformance(openPositions, resolvedPositions) {
  const totalPnl = resolvedPositions.reduce((sum, item) => sum + (Number(item.pnl) || 0), 0)
  const totalBets = openPositions.length + resolvedPositions.length
  const resolvedCount = resolvedPositions.length
  const wins = resolvedPositions.filter((item) => item.outcome === 'WIN').length
  const totalStake = [...openPositions, ...resolvedPositions].reduce((sum, item) => sum + (Number(item.amount) || 0), 0)
  return {
    total_bets: totalBets,
    total_pnl: Number(totalPnl.toFixed(2)),
    win_rate: resolvedCount > 0 ? Number(((wins / resolvedCount) * 100).toFixed(2)) : 0,
    roi: totalStake > 0 ? Number(((totalPnl / totalStake) * 100).toFixed(2)) : 0,
  }
}

function ensureStateSeeded(state, snapshot) {
  if (
    state.seeded &&
    (state.knowledge_entries.length > 0 || state.portfolio.open_positions.length > 0 || state.portfolio.resolved.length > 0)
  ) {
    return state
  }

  let normalizedRuns = unwrapRuns(snapshot.runs).map(normalizeRunRecord).filter(Boolean)
  if (normalizedRuns.length === 0) {
    normalizedRuns = [
      {
        market_id: 'demo_btc_100k',
        question: 'Will BTC reach $100k this quarter?',
        slug: 'btc-100k-quarter',
        mode: 'deep',
        side: 'YES',
        odds: 0.44,
        prediction: 0.58,
        edge: 0.14,
        amount: 68,
        outcome: 'WIN',
        pnl: 11.2,
        placed_at: nowIso(),
        closes_at: nowIso(),
        resolved: true,
        report_summary: 'Macro + flow setup favored upside continuation.',
        confidence: 0.73,
        key_factors: ['ETF inflows', 'macro easing', 'derivatives positioning'],
        raw: { recommendation: 'bet', selected_path: 'paper', confidence: 0.73 },
      },
      {
        market_id: 'demo_election',
        question: 'Will the incumbent win the election?',
        slug: 'incumbent-election',
        mode: 'quick',
        side: 'NO',
        odds: 0.61,
        prediction: 0.48,
        edge: -0.13,
        amount: 52,
        outcome: 'LOSS',
        pnl: -7.8,
        placed_at: nowIso(),
        closes_at: nowIso(),
        resolved: true,
        report_summary: 'Polling dispersion and turnout risk argued for caution.',
        confidence: 0.61,
        key_factors: ['polling dispersion', 'turnout', 'regional weakness'],
        raw: { recommendation: 'bet', selected_path: 'paper', confidence: 0.61 },
      },
      {
        market_id: 'demo_fed',
        question: 'Will the Fed cut rates by September?',
        slug: 'fed-cut-september',
        mode: 'quick',
        side: 'YES',
        odds: 0.39,
        prediction: 0.46,
        edge: 0.07,
        amount: 41,
        outcome: null,
        pnl: 0,
        placed_at: nowIso(),
        closes_at: null,
        resolved: false,
        report_summary: 'Cooling data keeps a soft-dovish path alive.',
        confidence: 0.57,
        key_factors: ['inflation', 'labor market', 'policy guidance'],
        raw: { recommendation: 'bet', selected_path: 'paper', confidence: 0.57 },
      },
    ]
  }
  state.knowledge_entries = buildKnowledgeEntries(normalizedRuns)
  state.ledger_entries = buildLedgerEntries(normalizedRuns)
  state.portfolio.open_positions = normalizedRuns
    .filter((item) => item.outcome == null)
    .slice(0, 10)
    .map((item) => ({
      ...item,
      kelly_fraction: 0.12,
      agents_count: 3,
      rounds: 3,
      preset: state.pipeline_preset,
      simulation_model: DEFAULT_PRESETS[state.pipeline_preset]?.stages?.simulation || 'gpt-5.4',
      report_model: DEFAULT_PRESETS[state.pipeline_preset]?.stages?.report || 'gpt-5.4-mini',
      cost_usd: item.mode === 'quick' ? 0 : 2.7,
    }))
  state.portfolio.resolved = normalizedRuns
    .filter((item) => item.outcome != null)
    .slice(0, 50)
  const locked = state.portfolio.open_positions.reduce((sum, item) => sum + (Number(item.amount) || 0), 0)
  state.portfolio.performance = buildPortfolioPerformance(state.portfolio.open_positions, state.portfolio.resolved)
  state.portfolio.balance = Number((PORTFOLIO_BASE_BALANCE - locked).toFixed(2))
  state.seeded = true
  return state
}

function buildSettingsPayload(state) {
  return {
    autopilot: state.autopilot,
    pipeline_preset: state.pipeline_preset,
    presets: state.presets,
    strategy: state.strategy,
    method_weights: state.method_weights,
    custom: state.custom,
    api_keys: state.api_keys,
  }
}

function buildStrategyPayload(state) {
  return {
    engine_mode: state.custom.engine_mode || 'quick',
    active_preset: state.pipeline_preset,
    autopilot: state.autopilot,
    strategy: state.strategy,
    performance: state.portfolio.performance,
    open_positions: state.portfolio.open_positions.length,
    resolved_positions: state.portfolio.resolved.length,
    last_reset_at: state.last_reset_at,
  }
}

function buildCostComparePayload(state) {
  const presetName = state.pipeline_preset || 'balanced'
  const currentStages = [
    { stage: 'ontology', model: state.presets[presetName]?.stages?.ontology || 'gpt-5.4-mini', input_tokens: 2200, output_tokens: 600, cost_usd: 0.18 },
    { stage: 'graph', model: state.presets[presetName]?.stages?.graph || 'gpt-5.4-mini', input_tokens: 1800, output_tokens: 450, cost_usd: 0.14 },
    { stage: 'profiles', model: state.presets[presetName]?.stages?.profiles || 'gpt-5.4-mini', input_tokens: 2600, output_tokens: 900, cost_usd: 0.24 },
    { stage: 'simulation', model: state.presets[presetName]?.stages?.simulation || 'gpt-5.4', input_tokens: 5200, output_tokens: 1400, cost_usd: 0.86 },
    { stage: 'report', model: state.presets[presetName]?.stages?.report || 'gpt-5.4-mini', input_tokens: 2400, output_tokens: 700, cost_usd: 0.19 },
  ]
  const total_cost_usd = currentStages.reduce((sum, stage) => sum + stage.cost_usd, 0)
  const total_tokens = currentStages.reduce((sum, stage) => sum + stage.input_tokens + stage.output_tokens, 0)
  return {
    active_preset: presetName,
    current_hybrid: {
      stages: currentStages,
      total_tokens,
      total_cost_usd,
    },
    alternatives: {
      all_gpt4o: { cost_usd: 2.94 },
      all_gpt4o_mini: { cost_usd: 1.28 },
      all_deepseek: { cost_usd: 0.61 },
    },
    savings_vs_gpt4o_percent: Number((((2.94 - total_cost_usd) / 2.94) * 100).toFixed(1)),
  }
}

function buildLedgerStats(entries) {
  const entries_by_type = {}
  const cycleSet = new Set()
  for (const entry of entries) {
    entries_by_type[entry.entry_type] = (entries_by_type[entry.entry_type] || 0) + 1
    if (entry.cycle_id) cycleSet.add(entry.cycle_id)
  }
  return {
    total_entries: entries.length,
    total_cycles: cycleSet.size,
    entries_by_type,
  }
}

function buildAutopilotTask(state, snapshot, quickOnly) {
  const taskId = createTaskId('cycle')
  const seedCandidates = state.knowledge_entries
    .filter((entry) => typeof entry.edge === 'number')
    .sort((left, right) => Math.abs(right.edge || 0) - Math.abs(left.edge || 0))
    .slice(0, quickOnly ? 2 : Math.max(1, state.autopilot.max_deep_per_cycle))

  const cycleId = taskId
  const betsPlaced = []
  for (const entry of seedCandidates) {
    const side = (entry.our_prediction || 0.5) >= (entry.market_odds_at_prediction || 0.5) ? 'YES' : 'NO'
    const amount = Number((25 + Math.abs(entry.edge || 0) * 800).toFixed(2))
    betsPlaced.push({
      market_id: entry.market_id,
      question: entry.question,
      slug: entry.slug,
      odds: entry.market_odds_at_prediction,
      prediction: entry.our_prediction,
      side,
      amount,
      edge: entry.edge,
      outcome: null,
      pnl: 0,
      placed_at: nowIso(),
      closes_at: null,
      kelly_fraction: 0.12,
      confidence: deriveConsensus(entry) === 'strong' ? 0.78 : 0.62,
      mode: quickOnly ? 'quick' : 'deep',
      agents_count: quickOnly ? 0 : 3,
      rounds: quickOnly ? 0 : 3,
      preset: state.pipeline_preset,
      simulation_model: DEFAULT_PRESETS[state.pipeline_preset]?.stages?.simulation || 'gpt-5.4',
      report_model: DEFAULT_PRESETS[state.pipeline_preset]?.stages?.report || 'gpt-5.4-mini',
      cost_usd: quickOnly ? 0 : 2.7,
    })
  }

  state.portfolio.open_positions = [...betsPlaced, ...state.portfolio.open_positions].slice(0, 50)
  state.ledger_entries.unshift({
    id: `${taskId}-summary`,
    entry_type: 'CYCLE_SUMMARY',
    cycle_id: cycleId,
    timestamp: nowIso(),
    question: quickOnly ? 'Quick paper cycle' : 'Autopilot paper cycle',
    explanation: 'Synthetic cycle generated by the dashboard adapter for compatibility.',
    data: {
      scanned: 18,
      bets_placed: betsPlaced.length,
      predicted: seedCandidates.length,
      resolved: state.portfolio.resolved.length,
    },
  })
  betsPlaced.forEach((bet, index) => {
    state.ledger_entries.unshift({
      id: `${taskId}-bet-${index}`,
      entry_type: 'BET_PLACED',
      cycle_id: cycleId,
      timestamp: bet.placed_at,
      question: bet.question,
      explanation: `Placed ${bet.side} paper trade from ${quickOnly ? 'quick' : 'autopilot'} cycle.`,
      data: {
        side: bet.side,
        amount: bet.amount,
        edge: bet.edge,
        mode: bet.mode,
        predicted_prob: bet.prediction,
        market_prob: bet.odds,
      },
    })
  })

  const locked = state.portfolio.open_positions.reduce((sum, item) => sum + (Number(item.amount) || 0), 0)
  state.portfolio.performance = buildPortfolioPerformance(state.portfolio.open_positions, state.portfolio.resolved)
  state.portfolio.balance = Number((PORTFOLIO_BASE_BALANCE - locked).toFixed(2))
  state.autopilot_runs[taskId] = {
    success: true,
    task_id: taskId,
    status: 'completed',
    scanned: 18,
    predicted: seedCandidates.length,
    bets_placed: betsPlaced.length,
    started_at: nowIso(),
    mode: quickOnly ? 'quick' : 'autopilot',
  }
  return state.autopilot_runs[taskId]
}

function buildBacktestResult(mode = 'quick') {
  const market_results = Array.from({ length: mode === 'incremental' ? 50 : 20 }, (_, index) => ({
    market_id: `bt_${index + 1}`,
    question: `Backtest market ${index + 1}`,
    prediction: Number((0.42 + (index % 7) * 0.04).toFixed(2)),
    market_prob: Number((0.39 + (index % 5) * 0.05).toFixed(2)),
    edge: Number((0.03 + (index % 4) * 0.01).toFixed(2)),
    outcome: index % 6 === 0 ? 'skipped' : index % 2 === 0 ? 'win' : 'loss',
    pnl: Number(((index % 2 === 0 ? 1 : -1) * (12 + index)).toFixed(2)),
  }))
  const pnl = market_results.reduce((sum, item) => sum + (item.pnl || 0), 0)
  const settled = market_results.filter((item) => item.outcome !== 'skipped')
  const wins = settled.filter((item) => item.outcome === 'win').length
  return {
    total_markets: market_results.length,
    market_results,
    total_pnl: Number(pnl.toFixed(2)),
    pnl: Number(pnl.toFixed(2)),
    win_rate: settled.length > 0 ? Number((wins / settled.length).toFixed(3)) : 0,
    roi: Number((pnl / 10000).toFixed(4)),
  }
}

function startDeepPredictionTask(upstreamBase, headers, bodyBuffer) {
  const state = readAdapterState()
  const taskId = createTaskId('deep')
  state.deep_predictions[taskId] = {
    success: true,
    task_id: taskId,
    status: 'running',
    step: 'building_graph',
    created_at: nowIso(),
  }
  writeAdapterState(state)

  setTimeout(async () => {
    const nextState = readAdapterState()
    try {
      const upstream = await fetchUpstreamJson(upstreamBase, '/api/v1/prediction-markets/predict-deep', {
        headers,
        method: 'POST',
        body: bodyBuffer,
      })
      const result = unwrapObject(upstream.json) || upstream.json || {}
      nextState.deep_predictions[taskId] = {
        ...(isObject(result) ? result : {}),
        success: upstream.ok,
        task_id: taskId,
        status: upstream.ok ? 'completed' : 'failed',
        step: upstream.ok ? 'completed' : 'error',
        completed_at: nowIso(),
      }
    } catch (error) {
      nextState.deep_predictions[taskId] = {
        success: false,
        task_id: taskId,
        status: 'failed',
        step: 'error',
        error: error instanceof Error ? error.message : String(error),
        completed_at: nowIso(),
      }
    }
    writeAdapterState(nextState)
  }, 25)

  return taskId
}

function streamAdapterLogs(response) {
  response.writeHead(200, {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-store',
    Connection: 'keep-alive',
  })

  const state = readAdapterState()
  const events = [
    {
      ts: Math.floor(Date.now() / 1000),
      level: 'info',
      message: 'Prediction dashboard adapter connected.',
    },
    ...Object.values(state.autopilot_runs).slice(-5).map((run) => ({
      ts: Math.floor(new Date(run.started_at || Date.now()).getTime() / 1000),
      level: 'info',
      message: `Cycle ${run.task_id} completed: ${run.bets_placed} bets placed.`,
    })),
  ]

  for (const event of events) {
    response.write(`data: ${JSON.stringify(event)}\n\n`)
  }

  const timer = setInterval(() => {
    try {
      response.write(`data: ${JSON.stringify({ ts: Math.floor(Date.now() / 1000), level: 'debug', message: 'adapter heartbeat' })}\n\n`)
    } catch {
      clearInterval(timer)
    }
  }, 15000)

  return timer
}

async function handleLegacyRoute(request, response, upstreamBase, requestUrl) {
  const pathname = requestUrl.pathname
  if (request.method === 'GET' && pathname === '/healthz') {
    return writeJson(response, 200, {
      ok: true,
      adapter: 'prediction-dashboard-ui-adapter',
      upstream: upstreamBase,
      venue: DEFAULT_VENUE,
    })
  }

  if (request.method === 'GET' && pathname === '/') {
    if (fs.existsSync(path.join(DASHBOARD_UI_DIST_DIR, 'index.html')) && tryServeStatic(response, DASHBOARD_UI_DIST_DIR, 'index.html')) {
      return true
    }
    return writeJson(response, 200, {
      ok: true,
      adapter: 'prediction-dashboard-ui-adapter',
      upstream: upstreamBase,
      supported: [
        '/healthz',
        '/api/polymarket/stats',
        '/api/polymarket/calibration',
        '/api/polymarket/portfolio',
        '/api/polymarket/portfolio/history',
        '/api/polymarket/settings',
        '/api/polymarket/strategy',
        '/api/polymarket/knowledge/*',
        '/api/polymarket/ledger/*',
        '/api/polymarket/backtest/*',
        '/api/polymarket/prediction/:id',
        '/api/polymarket/predict',
        '/api/polymarket/predict/deep',
        '/api/polymarket/predict/deep/:task_id',
      ],
    })
  }

  if (
    request.method === 'GET' &&
    !pathname.startsWith('/api/') &&
    !pathname.startsWith('/prediction-markets/') &&
    fs.existsSync(path.join(DASHBOARD_UI_DIST_DIR, 'index.html'))
  ) {
    const relative = pathname === '/' ? 'index.html' : pathname.slice(1)
    if (tryServeStatic(response, DASHBOARD_UI_DIST_DIR, relative)) {
      return true
    }
    if (tryServeStatic(response, DASHBOARD_UI_DIST_DIR, 'index.html')) {
      return true
    }
  }

  const headers = copyRequestHeaders(request.headers)
  const snapshot = await fetchDashboardSnapshot(upstreamBase, headers)
  const state = ensureStateSeeded(readAdapterState(), snapshot)
  writeAdapterState(state)

  if (request.method === 'GET' && pathname === '/api/polymarket/logs/stream') {
    const timer = streamAdapterLogs(response)
    request.on('close', () => clearInterval(timer))
    return true
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/settings') {
    return writeJson(response, 200, {
      success: true,
      data: buildSettingsPayload(state),
    })
  }

  if (request.method === 'PUT' && pathname === '/api/polymarket/settings') {
    const body = await readJsonBody(request)
    if (isObject(body.autopilot)) state.autopilot = { ...state.autopilot, ...body.autopilot }
    if (isObject(body.strategy)) state.strategy = { ...state.strategy, ...body.strategy }
    if (isObject(body.custom)) state.custom = { ...state.custom, ...body.custom }
    if (typeof body.pipeline_preset === 'string' && body.pipeline_preset) {
      state.pipeline_preset = body.pipeline_preset
    }
    writeAdapterState(state)
    return writeJson(response, 200, { success: true, data: buildSettingsPayload(state) })
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/strategy') {
    return writeJson(response, 200, {
      success: true,
      data: buildStrategyPayload(state),
    })
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/autopilot/config') {
    return writeJson(response, 200, {
      success: true,
      data: state.autopilot,
    })
  }

  if (request.method === 'PUT' && pathname === '/api/polymarket/autopilot/config') {
    const body = await readJsonBody(request)
    state.autopilot = { ...state.autopilot, ...(isObject(body) ? body : {}) }
    writeAdapterState(state)
    return writeJson(response, 200, {
      success: true,
      data: state.autopilot,
    })
  }

  if (request.method === 'POST' && pathname === '/api/polymarket/autopilot/run') {
    const body = await readJsonBody(request)
    const task = buildAutopilotTask(state, snapshot, Boolean(body.quick_only))
    writeAdapterState(state)
    return writeJson(response, 202, task)
  }

  if (request.method === 'GET' && pathname.startsWith('/api/polymarket/autopilot/run/')) {
    const taskId = decodeURIComponent(pathname.slice('/api/polymarket/autopilot/run/'.length))
    const run = state.autopilot_runs[taskId]
    if (!run) {
      return writeJson(response, 404, { success: false, error: 'Task not found' })
    }
    return writeJson(response, 200, run)
  }

  if (request.method === 'POST' && pathname === '/api/polymarket/portfolio/reset') {
    state.portfolio = {
      balance: PORTFOLIO_BASE_BALANCE,
      open_positions: [],
      resolved: [],
      performance: {
        total_bets: 0,
        total_pnl: 0,
        win_rate: 0,
        roi: 0,
      },
    }
    state.last_reset_at = nowIso()
    writeAdapterState(state)
    return writeJson(response, 200, { success: true, data: state.portfolio })
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/knowledge/stats') {
    return writeJson(response, 200, {
      success: true,
      data: buildKnowledgeStats(state.knowledge_entries),
    })
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/knowledge/entries') {
    const limit = Number(requestUrl.searchParams.get('limit') || '500')
    return writeJson(response, 200, {
      success: true,
      data: {
        entries: state.knowledge_entries.slice(0, limit),
      },
    })
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/knowledge/related') {
    const query = String(requestUrl.searchParams.get('q') || '').toLowerCase()
    const limit = Number(requestUrl.searchParams.get('limit') || '10')
    const entries = state.knowledge_entries
      .filter((entry) => !query || String(entry.question || '').toLowerCase().includes(query) || String(entry.category || '').toLowerCase().includes(query))
      .slice(0, limit)
    return writeJson(response, 200, {
      success: true,
      data: { entries },
    })
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/ledger/stats') {
    return writeJson(response, 200, {
      success: true,
      data: buildLedgerStats(state.ledger_entries),
    })
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/ledger/recent') {
    const limit = Number(requestUrl.searchParams.get('limit') || '50')
    return writeJson(response, 200, {
      success: true,
      data: { entries: state.ledger_entries.slice(0, limit) },
    })
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/ledger/entries') {
    const type = requestUrl.searchParams.get('type')
    const limit = Number(requestUrl.searchParams.get('limit') || '50')
    const offset = Number(requestUrl.searchParams.get('offset') || '0')
    const entries = state.ledger_entries
      .filter((entry) => !type || entry.entry_type === type)
      .slice(offset, offset + limit)
    return writeJson(response, 200, {
      success: true,
      data: { entries },
    })
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/ledger/search') {
    const query = String(requestUrl.searchParams.get('q') || '').toLowerCase()
    const limit = Number(requestUrl.searchParams.get('limit') || '50')
    const entries = state.ledger_entries
      .filter((entry) => !query || String(entry.question || '').toLowerCase().includes(query) || String(entry.explanation || '').toLowerCase().includes(query))
      .slice(0, limit)
    return writeJson(response, 200, {
      success: true,
      data: { entries },
    })
  }

  if (request.method === 'GET' && pathname.startsWith('/api/polymarket/ledger/cycle/')) {
    const cycleId = decodeURIComponent(pathname.slice('/api/polymarket/ledger/cycle/'.length))
    const entries = state.ledger_entries.filter((entry) => entry.cycle_id === cycleId)
    return writeJson(response, 200, {
      success: true,
      data: { entries },
    })
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/cost/compare') {
    return writeJson(response, 200, {
      success: true,
      data: buildCostComparePayload(state),
    })
  }

  if (request.method === 'POST' && pathname === '/api/polymarket/backtest/run') {
    const taskId = createTaskId('backtest')
    const result = buildBacktestResult('quick')
    state.backtests.tasks[taskId] = {
      success: true,
      task_id: taskId,
      status: 'completed',
      progress: { current: result.total_markets, total: result.total_markets },
      result,
    }
    state.backtests.latest = result
    writeAdapterState(state)
    return writeJson(response, 202, { success: true, task_id: taskId })
  }

  if (request.method === 'POST' && pathname === '/api/polymarket/backtest/incremental') {
    const taskId = createTaskId('backtest_incremental')
    const batches = Array.from({ length: 5 }, (_, index) => ({
      batch_number: index + 1,
      market_results: buildBacktestResult('incremental').market_results.slice(index * 10, index * 10 + 10),
    }))
    const result = {
      summary: buildBacktestResult('incremental'),
      batches,
    }
    state.backtests.tasks[taskId] = {
      success: true,
      task_id: taskId,
      status: 'completed',
      progress: { current_batch: 5, total_batches: 5, batch_current: 10, batch_total: 10 },
      result,
    }
    state.backtests.incremental = result
    writeAdapterState(state)
    return writeJson(response, 202, { success: true, task_id: taskId })
  }

  if (request.method === 'GET' && pathname.startsWith('/api/polymarket/backtest/run/')) {
    const taskId = decodeURIComponent(pathname.slice('/api/polymarket/backtest/run/'.length))
    const task = state.backtests.tasks[taskId]
    if (!task) {
      return writeJson(response, 404, { success: false, error: 'Backtest task not found' })
    }
    return writeJson(response, 200, task)
  }

  if (request.method === 'POST' && pathname === '/api/polymarket/backtest/reset') {
    state.backtests = {
      latest: null,
      incremental: null,
      tasks: {},
    }
    writeAdapterState(state)
    return writeJson(response, 200, { success: true })
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/backtest/results') {
    return writeJson(response, 200, {
      success: true,
      data: {
        latest: state.backtests.latest,
        incremental: state.backtests.incremental,
      },
    })
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/stats') {
    return writeJson(response, 200, buildStatsPayload({
      overview: snapshot.overview,
      runs: snapshot.runs,
      benchmark: snapshot.benchmark,
      health: snapshot.health,
    }))
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/calibration') {
    return writeJson(response, 200, buildCalibrationPayload({
      overview: snapshot.overview,
      runs: snapshot.runs,
      benchmark: snapshot.benchmark,
    }))
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/portfolio') {
    const locked = state.portfolio.open_positions.reduce((sum, item) => sum + (Number(item.amount) || 0), 0)
    state.portfolio.performance = buildPortfolioPerformance(state.portfolio.open_positions, state.portfolio.resolved)
    return writeJson(response, 200, {
      success: true,
      venue: DEFAULT_VENUE,
      source: 'prediction-dashboard-ui-adapter',
      data: {
        balance: state.portfolio.balance,
        total_value: Number((state.portfolio.balance + locked + state.portfolio.performance.total_pnl).toFixed(2)),
        open_positions: state.portfolio.open_positions,
        performance: state.portfolio.performance,
      },
    })
  }

  if (request.method === 'GET' && pathname === '/api/polymarket/portfolio/history') {
    return writeJson(response, 200, {
      success: true,
      data: {
        resolved: state.portfolio.resolved,
      },
      source: 'prediction-dashboard-ui-adapter',
    })
  }

  if (request.method === 'GET' && pathname.startsWith('/api/polymarket/prediction/')) {
    const id = decodeURIComponent(pathname.slice('/api/polymarket/prediction/'.length))
    const payload = await buildPredictionPayload(upstreamBase, request, id)
    if (!payload) {
      return writeJson(response, 404, {
        success: false,
        error: 'Prediction not found',
      })
    }
    return writeJson(response, 200, payload)
  }

  if (request.method === 'POST' && pathname === '/api/polymarket/predict') {
    return proxyToUpstream(request, response, upstreamBase, '/api/v1/prediction-markets/predict')
  }

  if (request.method === 'POST' && pathname === '/api/polymarket/predict/deep') {
    const body = await collectBody(request)
    const taskId = startDeepPredictionTask(upstreamBase, headers, body)
    return writeJson(response, 202, {
      success: true,
      task_id: taskId,
      status: 'running',
      step: 'building_graph',
    })
  }

  if (request.method === 'GET' && pathname.startsWith('/api/polymarket/predict/deep/')) {
    const taskId = decodeURIComponent(pathname.slice('/api/polymarket/predict/deep/'.length))
    const currentState = readAdapterState()
    const task = currentState.deep_predictions[taskId]
    if (!task) {
      return writeJson(response, 404, {
        success: false,
        error: 'Deep prediction task not found',
      })
    }
    return writeJson(response, 200, task)
  }

  if (request.method === 'GET' && pathname.startsWith('/api/v1/prediction-markets/')) {
    return proxyToUpstream(request, response, upstreamBase)
  }

  if (request.method === 'GET' && pathname.startsWith('/prediction-markets/dashboard')) {
    return proxyToUpstream(request, response, upstreamBase)
  }

  if (await legacyCompat.handle(request, response, requestUrl)) {
    return true
  }

  return false
}

async function main() {
  const options = parseArgs(process.argv.slice(2))
  if (options.help) {
    printHelp()
    return
  }

  currentStateFile = options.stateFile || DEFAULT_STATE_FILE

  if (!options.port || Number.isNaN(options.port) || options.port < 1) {
    console.error('Invalid --port value')
    process.exitCode = 1
    return
  }

  const server = http.createServer(async (request, response) => {
    try {
      const base = `http://${request.headers.host || 'localhost'}`
      const requestUrl = new URL(request.url || '/', base)
      const handled = await handleLegacyRoute(request, response, options.upstream, requestUrl)
      if (handled === false) {
        writeJson(response, 404, { error: 'Not found' })
      }
    } catch (error) {
      writeJson(response, 502, {
        error: error instanceof Error ? error.message : String(error),
      })
    }
  })

  server.listen(options.port, options.host, () => {
    console.log(`Prediction dashboard UI adapter listening on http://${options.host}:${options.port}`)
    console.log(`Proxying prediction-markets runtime to ${options.upstream}`)
  })

  const shutdown = () => server.close(() => process.exit(0))
  process.on('SIGINT', shutdown)
  process.on('SIGTERM', shutdown)
}

main()
