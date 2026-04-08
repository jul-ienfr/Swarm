import { createServer } from 'node:http'
import { createServer as createNetServer } from 'node:net'
import { spawn } from 'node:child_process'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'

function getFreePort(): Promise<number> {
  return new Promise((resolvePort, reject) => {
    const server = createNetServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      const port = typeof address === 'object' && address ? address.port : 0
      server.close(() => resolvePort(port))
    })
  })
}

function wait(ms: number) {
  return new Promise((resolveDelay) => {
    setTimeout(resolveDelay, ms)
  })
}

async function waitForReady(url: string, attempts = 40): Promise<void> {
  for (let index = 0; index < attempts; index += 1) {
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch {
      // keep polling
    }
    await wait(100)
  }

  throw new Error(`Timed out waiting for ${url}`)
}

describe('dashboard smoke helper', () => {
  const children: Array<ReturnType<typeof spawn>> = []

  afterEach(() => {
    for (const child of children.splice(0, children.length)) {
      if (!child.killed) {
        child.kill('SIGTERM')
      }
    }
  })

  it('serves the dashboard page and proxies api calls from the standalone helper', async () => {
    const upstreamServer = createServer((request, response) => {
      const url = new URL(request.url ?? '/', 'http://127.0.0.1')

      if (url.pathname === '/api/v1/prediction-markets/runs') {
        response.writeHead(200, { 'content-type': 'application/json' })
        response.end(JSON.stringify({
          runs: [{ run_id: 'run-smoke-1', benchmark_promotion_ready: true }],
        }))
        return
      }

      response.writeHead(404, { 'content-type': 'application/json' })
      response.end(JSON.stringify({ error: 'not_found' }))
    })

    const upstreamPort = await new Promise<number>((resolvePort) => {
      upstreamServer.listen(0, '127.0.0.1', () => {
        const address = upstreamServer.address()
        resolvePort(typeof address === 'object' && address ? address.port : 0)
      })
    })

    const dashboardPort = await getFreePort()
    const scriptPath = resolve(process.cwd(), 'scripts/prediction-dashboard.cjs')
    const child = spawn(process.execPath, [
      scriptPath,
      '--host',
      '127.0.0.1',
      '--port',
      String(dashboardPort),
      '--upstream',
      `http://127.0.0.1:${upstreamPort}`,
    ], {
      cwd: process.cwd(),
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    children.push(child)

    try {
      await waitForReady(`http://127.0.0.1:${dashboardPort}/healthz`)

      const rootResponse = await fetch(`http://127.0.0.1:${dashboardPort}/`)
      const rootHtml = await rootResponse.text()
      const proxyResponse = await fetch(`http://127.0.0.1:${dashboardPort}/proxy/api/v1/prediction-markets/runs`)
      const proxyBody = await proxyResponse.json() as { runs: Array<{ run_id: string }> }

      expect(rootResponse.status).toBe(200)
      expect(rootHtml).toContain('Prediction Markets Dashboard')
      expect(rootHtml).toContain('data-dashboard-mode="standalone-proxy:http://127.0.0.1:')
      expect(rootHtml).toContain('dispatch/paper/shadow/live')
      expect(rootHtml).toContain('live_trade_intent_preview')
      expect(rootHtml).toContain('Strategy Engine')
      expect(rootHtml).toContain('Primary Strategy')
      expect(rootHtml).toContain('Market Regime')
      expect(rootHtml).toContain('Cross-Venue / Arbitrage')
      expect(rootHtml).toContain('Trader desk alert')
      expect(rootHtml).toContain('Reset arbitrage')
      expect(proxyResponse.status).toBe(200)
      expect(proxyBody.runs).toEqual([
        expect.objectContaining({
          run_id: 'run-smoke-1',
        }),
      ])
    } finally {
      await new Promise<void>((resolveClose) => {
        upstreamServer.close(() => resolveClose())
      })
      child.kill('SIGTERM')
      await wait(100)
    }
  })
})
