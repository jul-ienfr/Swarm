import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('dashboard runtime views smoke', () => {
  it('keeps the runtime dashboard view files present', () => {
    const root = resolve(process.cwd())
    const expected = [
      'dashboard-ui/src/views/RuntimeHomeView.vue',
      'dashboard-ui/src/views/Home.vue',
      'dashboard-ui/src/views/MainView.vue',
      'dashboard-ui/src/views/SimulationView.vue',
      'dashboard-ui/src/views/SimulationRunView.vue',
      'dashboard-ui/src/views/ReportView.vue',
    ]

    for (const relativePath of expected) {
      expect(existsSync(resolve(root, relativePath)), relativePath).toBe(true)
    }
  })
})
