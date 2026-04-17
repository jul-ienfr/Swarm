import service from './index'

/**
 * Get current active settings (API key masked)
 */
export const getSettings = () => {
  return service.get('/api/settings')
}

/**
 * Update settings at runtime
 * @param {Object} data - { llm: { provider, base_url, model_name, api_key }, neo4j: { uri, user, password } }
 */
export const updateSettings = (data) => {
  return service.post('/api/settings', data)
}

/**
 * Test the current LLM connection
 * @returns {Promise<{ success, model, latency_ms, error }>}
 */
export const testLlmConnection = () => {
  return service.post('/api/settings/test-llm')
}
