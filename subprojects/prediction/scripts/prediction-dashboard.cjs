#!/usr/bin/env node

const http = require('node:http')
const { readFileSync } = require('node:fs')
const path = require('node:path')
const { Readable } = require('node:stream')
const { URL } = require('node:url')

const DEFAULT_HOST = process.env.PREDICTION_DASHBOARD_HOST || '127.0.0.1'
const DEFAULT_PORT = Number(process.env.PREDICTION_DASHBOARD_PORT || 4174)
const DEFAULT_UPSTREAM = process.env.PREDICTION_BASE_URL || process.env.MC_URL || 'http://127.0.0.1:3000'
const DASHBOARD_TEMPLATE_PATH = path.resolve(__dirname, '../dashboard/index.html')

function printHelp() {
  console.log(
    [
      'prediction-dashboard usage:',
      '  node scripts/prediction-dashboard.cjs [--host 127.0.0.1] [--port 4174] [--upstream http://127.0.0.1:3000]',
      '',
      'Serves the local prediction markets operator dashboard and proxies API calls to the upstream Swarm app.',
      '',
      'Flags:',
      '  --host       Host interface to bind.',
      '  --port       Local port to bind.',
      '  --upstream   Upstream base URL that already serves /api/v1/prediction-markets.',
      '  --help       Show this help.',
      '',
      'Environment:',
      `  PREDICTION_DASHBOARD_HOST=${DEFAULT_HOST}`,
      `  PREDICTION_DASHBOARD_PORT=${DEFAULT_PORT}`,
      `  PREDICTION_BASE_URL=${DEFAULT_UPSTREAM}`,
    ].join('\n'),
  )
}

function parseArgs(argv) {
  const options = {
    host: DEFAULT_HOST,
    port: DEFAULT_PORT,
    upstream: DEFAULT_UPSTREAM,
  }

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    const next = argv[index + 1]
    if (arg === '--help' || arg === '-h') {
      options.help = true
      continue
    }
    if (arg === '--host' && next) {
      options.host = next
      index += 1
      continue
    }
    if (arg === '--port' && next) {
      options.port = Number(next)
      index += 1
      continue
    }
    if (arg === '--upstream' && next) {
      options.upstream = next
      index += 1
      continue
    }
  }

  return options
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function buildDashboardHtml({ upstream }) {
  const template = readFileSync(DASHBOARD_TEMPLATE_PATH, 'utf8')
  return template
    .replaceAll('__PREDICTION_DASHBOARD_API_BASE__', escapeHtml('/proxy/api/v1/prediction-markets'))
    .replaceAll('__PREDICTION_DASHBOARD_TITLE__', escapeHtml('Prediction Markets Dashboard'))
    .replaceAll('__PREDICTION_DASHBOARD_MODE__', escapeHtml(`standalone-proxy:${upstream}`))
}

function collectRequestBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = []
    request.on('data', (chunk) => chunks.push(chunk))
    request.on('end', () => resolve(chunks.length > 0 ? Buffer.concat(chunks) : undefined))
    request.on('error', reject)
  })
}

async function proxyRequest(request, response, { upstream }) {
  const targetPath = request.url.replace(/^\/proxy/, '')
  const targetUrl = new URL(targetPath, upstream)
  const requestBody = await collectRequestBody(request)
  const headers = new Headers()

  for (const [key, value] of Object.entries(request.headers)) {
    if (value == null) continue
    if (key === 'host' || key === 'connection' || key === 'content-length') continue
    headers.set(key, Array.isArray(value) ? value.join(',') : value)
  }

  const proxied = await fetch(targetUrl, {
    method: request.method,
    headers,
    body: requestBody,
  })

  response.statusCode = proxied.status
  proxied.headers.forEach((value, key) => {
    if (key.toLowerCase() === 'content-encoding') return
    if (key.toLowerCase() === 'transfer-encoding') return
    response.setHeader(key, value)
  })

  if (!proxied.body) {
    response.end()
    return
  }

  const bodyStream = Readable.fromWeb(proxied.body)
  bodyStream.on('error', (error) => {
    try {
      response.destroy(error)
    } catch {
      // best-effort proxy shutdown
    }
  })
  bodyStream.pipe(response)
}

async function main() {
  const options = parseArgs(process.argv.slice(2))
  if (options.help) {
    printHelp()
    return
  }

  if (!options.port || Number.isNaN(options.port) || options.port < 1) {
    console.error('Invalid --port value')
    process.exitCode = 1
    return
  }

  const server = http.createServer(async (request, response) => {
    try {
      const requestUrl = new URL(request.url || '/', `http://${request.headers.host || 'localhost'}`)
      if (requestUrl.pathname === '/' || requestUrl.pathname === '/index.html') {
        response.statusCode = 200
        response.setHeader('content-type', 'text/html; charset=utf-8')
        response.setHeader('cache-control', 'no-store')
        response.end(buildDashboardHtml({ upstream: options.upstream }))
        return
      }

      if (requestUrl.pathname === '/healthz') {
        response.statusCode = 200
        response.setHeader('content-type', 'application/json; charset=utf-8')
        response.end(JSON.stringify({ ok: true, upstream: options.upstream }))
        return
      }

      if (requestUrl.pathname.startsWith('/proxy/')) {
        await proxyRequest(request, response, { upstream: options.upstream })
        return
      }

      response.statusCode = 404
      response.setHeader('content-type', 'application/json; charset=utf-8')
      response.end(JSON.stringify({ error: 'Not found' }))
    } catch (error) {
      response.statusCode = 502
      response.setHeader('content-type', 'application/json; charset=utf-8')
      response.end(JSON.stringify({ error: error instanceof Error ? error.message : String(error) }))
    }
  })

  server.listen(options.port, options.host, () => {
    console.log(`Prediction dashboard listening on http://${options.host}:${options.port}`)
    console.log(`Proxying prediction markets API to ${options.upstream}`)
  })

  const shutdown = () => server.close(() => process.exit(0))
  process.on('SIGINT', shutdown)
  process.on('SIGTERM', shutdown)
}

main()
