import service from './index'

/**
 * List all available simulation templates (summaries only)
 */
export const listTemplates = () => {
  return service.get('/api/templates/list')
}

/**
 * Get a single template by ID (includes full seed_document)
 * @param {string} templateId
 */
export const getTemplate = (templateId) => {
  return service.get(`/api/templates/${templateId}`)
}
