import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('dashboard contract wording', () => {
  it('anchors preflight-only, double approval, and SSE/events wording for the dashboard', () => {
    const root = resolve(process.cwd())
    const contract = readFileSync(resolve(root, 'docs/dashboard-contract.md'), 'utf8')
    const readme = readFileSync(resolve(root, 'README.md'), 'utf8')
    const guide = readFileSync(resolve(root, 'docs/cli-agent-control.md'), 'utf8')

    expect(contract).toContain('preflight-only')
    expect(contract).toContain('proof chain')
    expect(contract).toContain('advisor-first')
    expect(contract).toContain('kill criteria')
    expect(contract).toContain('double approval')
    expect(contract).toContain('SSE/events')

    expect(readme).toContain('preflight-only')
    expect(readme).toContain('proof chain')
    expect(readme).toContain('advisor-first')
    expect(readme).toContain('kill criteria')
    expect(readme).toContain('SSE')

    expect(guide).toContain('preflight-only')
    expect(guide).toContain('proof chain')
    expect(guide).toContain('advisor-first')
    expect(guide).toContain('kill criteria')
    expect(guide).toContain('SSE')
    expect(guide).toContain('events')
  })
})
