import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('dashboard documentation coverage', () => {
  it('documents the dashboard route, proxy helper, surfaces, and live-intent previews', () => {
    const root = resolve(process.cwd())
    const readme = readFileSync(resolve(root, 'README.md'), 'utf8')
    const guide = readFileSync(resolve(root, 'docs/cli-agent-control.md'), 'utf8')

    expect(readme).toContain('/prediction-markets/dashboard')
    expect(readme).toContain('proof chain')
    expect(readme).toContain('advisor-first')
    expect(readme).toContain('kill criteria')
    expect(readme).toContain('execution_projection_selected_preview')
    expect(readme).toContain('live_trade_intent_preview')
    expect(readme).toContain('trade_intent_guard')
    expect(readme).toContain('ne dépend pas d\'un canal SSE dédié')

    expect(guide).toContain('/prediction-markets/dashboard')
    expect(guide).toContain('proof chain')
    expect(guide).toContain('advisor-first')
    expect(guide).toContain('kill criteria')
    expect(guide).toContain('prediction-dashboard.cjs --upstream')
    expect(guide).toContain('execution_projection_selected_preview')
    expect(guide).toContain('live_trade_intent_preview')
    expect(guide).toContain('SSE')
  })
})
