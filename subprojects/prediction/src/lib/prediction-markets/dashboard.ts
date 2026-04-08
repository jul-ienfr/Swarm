import { readFileSync } from 'node:fs'

type PredictionMarketsDashboardHtmlOptions = {
  apiBasePath?: string
  title?: string
  mode?: string
}

const DASHBOARD_TEMPLATE_URL = new URL('../../../dashboard/index.html', import.meta.url)

let cachedTemplate: string | null = null

function loadDashboardTemplate(): string {
  if (cachedTemplate == null) {
    cachedTemplate = readFileSync(DASHBOARD_TEMPLATE_URL, 'utf8')
  }

  return cachedTemplate
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

export function buildPredictionMarketsDashboardHtml(
  options: PredictionMarketsDashboardHtmlOptions = {},
): string {
  const apiBasePath = options.apiBasePath ?? '/api/v1/prediction-markets'
  const title = options.title ?? 'Prediction Markets Dashboard'
  const mode = options.mode ?? 'embedded'

  return loadDashboardTemplate()
    .replaceAll('__PREDICTION_DASHBOARD_API_BASE__', escapeHtml(apiBasePath))
    .replaceAll('__PREDICTION_DASHBOARD_TITLE__', escapeHtml(title))
    .replaceAll('__PREDICTION_DASHBOARD_MODE__', escapeHtml(mode))
}
