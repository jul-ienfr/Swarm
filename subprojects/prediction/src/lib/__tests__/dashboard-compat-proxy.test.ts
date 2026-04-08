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

function normalizeHeaderValue(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) return value.join(',')
  return value
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

describe('dashboard compat proxy', () => {
  const children: Array<ReturnType<typeof spawn>> = []

  afterEach(() => {
    for (const child of children.splice(0, children.length)) {
      if (!child.killed) {
        child.kill('SIGTERM')
      }
    }
  })

  it('keeps the dashboard same-origin and forwards proxied auth headers and JSON bodies', async () => {
    let capturedRequest: {
      method: string
      path: string
      headers: Record<string, string | undefined>
      body: string
    } | null = null

    const upstreamServer = createServer((request, response) => {
      const url = new URL(request.url ?? '/', 'http://127.0.0.1')
      const chunks: Buffer[] = []

      request.on('data', (chunk) => chunks.push(Buffer.from(chunk)))
      request.on('end', () => {
        capturedRequest = {
          method: request.method ?? 'GET',
          path: `${url.pathname}${url.search}`,
          headers: {
            accept: normalizeHeaderValue(request.headers.accept),
            authorization: normalizeHeaderValue(request.headers.authorization),
            'content-type': normalizeHeaderValue(request.headers['content-type']),
            'x-prediction-role': normalizeHeaderValue(request.headers['x-prediction-role']),
            'x-prediction-workspace-id': normalizeHeaderValue(request.headers['x-prediction-workspace-id']),
            'x-prediction-dashboard-actor': normalizeHeaderValue(request.headers['x-prediction-dashboard-actor']),
          },
          body: Buffer.concat(chunks).toString('utf8'),
        }

        response.writeHead(201, { 'content-type': 'application/json' })
        response.end(JSON.stringify({ ok: true }))
      })
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

      expect(rootResponse.status).toBe(200)
      expect(rootHtml).toContain('data-dashboard-mode="standalone-proxy:http://127.0.0.1:')
      expect(rootHtml).toContain('data-api-base="/proxy/api/v1/prediction-markets"')

      const proxyResponse = await fetch(
        `http://127.0.0.1:${dashboardPort}/proxy/api/v1/prediction-markets/dashboard/live-intents`,
        {
          method: 'POST',
          headers: {
            accept: 'application/json',
            authorization: 'Bearer dashboard-token',
            'content-type': 'application/json',
            'x-prediction-role': 'operator',
            'x-prediction-workspace-id': '7',
            'x-prediction-dashboard-actor': 'Dashboard Bot',
          },
          body: JSON.stringify({ run_id: 'run-compat-001', note: 'compat smoke' }),
        },
      )
      const proxyBody = await proxyResponse.json() as { ok: boolean }

      expect(proxyResponse.status).toBe(201)
      expect(proxyBody).toEqual({ ok: true })
      expect(capturedRequest).toEqual({
        method: 'POST',
        path: '/api/v1/prediction-markets/dashboard/live-intents',
        headers: {
          accept: 'application/json',
          authorization: 'Bearer dashboard-token',
          'content-type': 'application/json',
          'x-prediction-role': 'operator',
          'x-prediction-workspace-id': '7',
          'x-prediction-dashboard-actor': 'Dashboard Bot',
        },
        body: JSON.stringify({ run_id: 'run-compat-001', note: 'compat smoke' }),
      })
    } finally {
      await new Promise<void>((resolveClose) => {
        upstreamServer.close(() => resolveClose())
      })
      child.kill('SIGTERM')
      await wait(100)
    }
  })
})
