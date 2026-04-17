import service from './index'

export function getRuntimeOverview(venue = 'polymarket', limit = 12) {
  return service.get('/api/v1/prediction-markets/dashboard/overview', {
    params: { venue, limit },
  })
}

export function runQuickPrediction(slug) {
  return fetch('/api/polymarket/predict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slug }),
  }).then(async (response) => {
    const data = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(data?.message || data?.error || `Request failed (${response.status})`)
    }
    return data
  })
}

export function runDeepPrediction(slug) {
  return fetch('/api/polymarket/predict/deep', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slug }),
  }).then(async (response) => {
    const data = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(data?.message || data?.error || `Request failed (${response.status})`)
    }
    return data
  })
}
