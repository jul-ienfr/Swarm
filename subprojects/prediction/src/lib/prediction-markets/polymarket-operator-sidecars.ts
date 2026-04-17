import { getPredictionMarketP0ARuntimeSummary } from './external-runtime'

export type PredictionMarketOperatorWrapperStatus = {
  profile_id: string
  enabled: boolean
  endpoint: string | null
  scope: 'read_only_alerting' | 'operator_read_only'
  summary: string
}

export type PredictionMarketOrderReadbackParitySummary = {
  official_references: string[]
  canonical_gate: 'execution_projection'
  orderbook_available: boolean
  history_available: boolean
  readback_ready: boolean
  coverage: string[]
  summary: string
}

export type PredictionMarketPolymarketOperatorSidecarSurface = {
  read_only: true
  runtime_summary: string
  wrappers: PredictionMarketOperatorWrapperStatus[]
  order_readback_parity: PredictionMarketOrderReadbackParitySummary
  summary: string
}

function readEnvText(...names: string[]): string | null {
  for (const name of names) {
    const value = process.env[name]
    if (typeof value === 'string' && value.trim().length > 0) return value.trim()
  }
  return null
}

function readEnvTruthy(...names: string[]): boolean {
  for (const name of names) {
    const value = process.env[name]
    if (typeof value !== 'string') continue
    const normalized = value.trim().toLowerCase()
    if (['1', 'true', 'yes', 'on', 'enabled', 'active'].includes(normalized)) return true
  }
  return false
}

export function buildPolymarketOrderReadbackParitySummary(input: {
  has_orderbook?: boolean | null
  has_history?: boolean | null
} = {}): PredictionMarketOrderReadbackParitySummary {
  const orderbookAvailable = input.has_orderbook !== false
  const historyAvailable = input.has_history !== false
  const readbackReady = orderbookAvailable && historyAvailable

  return {
    official_references: ['Polymarket/clob-client', 'Polymarket/py-clob-client'],
    canonical_gate: 'execution_projection',
    orderbook_available: orderbookAvailable,
    history_available: historyAvailable,
    readback_ready: readbackReady,
    coverage: [
      orderbookAvailable ? 'orderbook_snapshot' : null,
      historyAvailable ? 'history_readback' : null,
      'paper_shadow_live_parity_reference',
    ].filter((value): value is string => value != null),
    summary: readbackReady
      ? 'Read-only orderbook/history readback parity is available for Polymarket adapters.'
      : 'Readback parity is degraded because orderbook or history coverage is missing.',
  }
}

export function getPolymarketOperatorSidecarSurface(): PredictionMarketPolymarketOperatorSidecarSurface {
  const runtimeSummary = getPredictionMarketP0ARuntimeSummary()
  const tremorEndpoint = readEnvText('PREDICTION_MARKETS_POLYMARKET_TREMOR_URL', 'PREDICTION_MARKETS_TREMOR_URL')
  const mcpEndpoint = readEnvText('PREDICTION_MARKETS_POLYMARKET_MCP_URL')
  const mcpAnalyticsEndpoint = readEnvText('PREDICTION_MARKETS_POLYMARKET_MCP_ANALYTICS_URL')
  const wrappers: PredictionMarketOperatorWrapperStatus[] = [
    {
      profile_id: 'tremor',
      enabled: tremorEndpoint != null || readEnvTruthy('PREDICTION_MARKETS_POLYMARKET_TREMOR_ENABLED'),
      endpoint: tremorEndpoint,
      scope: 'read_only_alerting',
      summary: 'Tremor remains an operator-bound, read-only alerting sidecar.',
    },
    {
      profile_id: 'polymarket-mcp',
      enabled: mcpEndpoint != null || readEnvTruthy('PREDICTION_MARKETS_POLYMARKET_MCP_ENABLED'),
      endpoint: mcpEndpoint,
      scope: 'operator_read_only',
      summary: 'Polymarket MCP remains an operator wrapper for read-only inspection.',
    },
    {
      profile_id: 'polymarket-mcp-analytics',
      enabled: mcpAnalyticsEndpoint != null || readEnvTruthy('PREDICTION_MARKETS_POLYMARKET_MCP_ANALYTICS_ENABLED'),
      endpoint: mcpAnalyticsEndpoint,
      scope: 'operator_read_only',
      summary: 'Analytics MCP remains an operator wrapper for read-only analytics and holder inspection.',
    },
  ]
  const orderReadbackParity = buildPolymarketOrderReadbackParitySummary()

  return {
    read_only: true,
    runtime_summary: runtimeSummary.summary,
    wrappers,
    order_readback_parity: orderReadbackParity,
    summary: [
      runtimeSummary.summary,
      orderReadbackParity.summary,
      `${wrappers.filter((wrapper) => wrapper.enabled).length} operator wrapper(s) currently configured.`,
    ].join(' '),
  }
}
