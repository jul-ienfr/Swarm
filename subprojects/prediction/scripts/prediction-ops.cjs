#!/usr/bin/env node

const { spawnSync } = require('node:child_process')
const path = require('node:path')

const CLI_PATH = path.resolve(__dirname, 'mc-cli.cjs')
const DEFAULT_URL = process.env.PREDICTION_BASE_URL || process.env.MC_URL || 'http://127.0.0.1:3000'
const DEFAULT_VENUE = process.env.PREDICTION_DEFAULT_VENUE || 'polymarket'

const COMMAND_ALIASES = new Map([
  ['runs', 'runs'],
  ['run', 'run'],
  ['markets', 'markets'],
  ['capabilities', 'capabilities'],
  ['health', 'health'],
  ['feed', 'health'],
  ['dispatch', 'dispatch'],
  ['paper', 'paper'],
  ['shadow', 'shadow'],
  ['live', 'live'],
  ['advise', 'advise'],
  ['replay', 'replay'],
])

const OPERATOR_SUMMARY_FLAGS = [
  '--execution-pathways-summary',
  '--research-summary',
  '--benchmark-summary',
  '--validation-summary',
  '--approval-ticket-summary',
  '--operator-thesis-summary',
  '--research-pipeline-trace-summary',
  '--live-dashboard-summary',
]

const FEED_BOOTSTRAP_SURFACES = new Set(['markets', 'capabilities', 'health', 'feed'])

function buildSurfaceSemantics(surface) {
  switch (surface) {
    case 'dispatch':
      return {
        surface_kind: 'operator_preflight',
        operator_surface: true,
        feed_bootstrap: false,
        preflight_only: true,
        benchmark_gated: false,
        default_venue_applies: false,
        execution_projection_path: 'selected',
        runtime_distinction: 'execution_projection_first',
        readiness_semantics: 'preflight_only_selected_path_preview',
        promotion_semantics: 'not_applicable',
        feed_transport_semantics: null,
        summary: 'Dispatch stays preflight-only and reflects the selected execution_projection path without venue execution.',
      }
    case 'paper':
      return {
        surface_kind: 'operator_surface',
        operator_surface: true,
        feed_bootstrap: false,
        preflight_only: true,
        benchmark_gated: false,
        default_venue_applies: false,
        execution_projection_path: 'paper',
        runtime_distinction: 'execution_projection_first',
        readiness_semantics: 'preflight_only_paper_preview',
        promotion_semantics: 'not_applicable',
        feed_transport_semantics: null,
        summary: 'Paper stays preflight-only and reflects execution_projection.projected_paths.paper.',
      }
    case 'shadow':
      return {
        surface_kind: 'operator_surface',
        operator_surface: true,
        feed_bootstrap: false,
        preflight_only: true,
        benchmark_gated: false,
        default_venue_applies: false,
        execution_projection_path: 'shadow',
        runtime_distinction: 'execution_projection_first',
        readiness_semantics: 'preflight_only_shadow_preview',
        promotion_semantics: 'not_applicable',
        feed_transport_semantics: null,
        summary: 'Shadow stays preflight-only and reflects execution_projection.projected_paths.shadow.',
      }
    case 'live':
      return {
        surface_kind: 'operator_surface',
        operator_surface: true,
        feed_bootstrap: false,
        preflight_only: true,
        benchmark_gated: true,
        default_venue_applies: false,
        execution_projection_path: 'live',
        runtime_distinction: 'execution_projection_first',
        readiness_semantics: 'blocked_until_live_path_benchmark_and_transport_ready',
        promotion_semantics: 'benchmark_gated_governed_live_materialization',
        feed_transport_semantics: null,
        summary: 'Live remains the canonical preflight surface for governed routing; it stays benchmark-gated by default, and real venue execution can be materialized with execution_mode=live after an approved live intent.',
      }
    case 'capabilities':
      return {
        surface_kind: 'feed_bootstrap',
        operator_surface: false,
        feed_bootstrap: true,
        preflight_only: false,
        benchmark_gated: false,
        default_venue_applies: true,
        execution_projection_path: null,
        runtime_distinction: 'read_only_bootstrap',
        readiness_semantics: 'read_only_operator_bootstrap',
        promotion_semantics: 'not_applicable',
        feed_transport_semantics: 'contract_surface_only',
        summary: 'Capabilities stays read-only and exposes venue contracts, automation constraints, and budget envelopes for operator bootstrap.',
      }
    case 'health':
      return {
        surface_kind: 'feed_bootstrap',
        operator_surface: false,
        feed_bootstrap: true,
        preflight_only: false,
        benchmark_gated: false,
        default_venue_applies: true,
        execution_projection_path: null,
        runtime_distinction: 'read_only_bootstrap',
        readiness_semantics: 'read_only_feed_bootstrap',
        promotion_semantics: 'not_applicable',
        feed_transport_semantics: 'market_and_user_feed_via_local_cache_rtds_unavailable',
        summary: 'Health/feed stays read-only and reflects local market/user feed transport state plus RTDS availability for operator bootstrap.',
      }
    case 'markets':
      return {
        surface_kind: 'feed_bootstrap',
        operator_surface: false,
        feed_bootstrap: true,
        preflight_only: false,
        benchmark_gated: false,
        default_venue_applies: true,
        execution_projection_path: null,
        runtime_distinction: 'discovery_bootstrap',
        readiness_semantics: 'read_only_discovery_bootstrap',
        promotion_semantics: 'not_applicable',
        feed_transport_semantics: 'discovery_snapshot_polling',
        summary: 'Markets is the discovery/bootstrap surface for market listings and venue-scoped search.',
      }
    case 'runs':
    case 'run':
      return {
        surface_kind: 'run_readback',
        operator_surface: true,
        feed_bootstrap: false,
        preflight_only: false,
        benchmark_gated: false,
        default_venue_applies: false,
        execution_projection_path: null,
        runtime_distinction: 'runtime_readback',
        readiness_semantics: 'readback_only',
        promotion_semantics: 'readback_only',
        feed_transport_semantics: null,
        summary: 'Run readback surfaces expose stored runtime hints, artifacts, and operator summaries.',
      }
    case 'advise':
    case 'replay':
      return {
        surface_kind: 'runtime_execution',
        operator_surface: true,
        feed_bootstrap: false,
        preflight_only: false,
        benchmark_gated: false,
        default_venue_applies: false,
        execution_projection_path: null,
        runtime_distinction: 'runtime_entrypoint',
        readiness_semantics: 'runtime_entrypoint',
        promotion_semantics: 'runtime_dependent',
        feed_transport_semantics: null,
        summary: 'Advise and replay are runtime entrypoints, not preflight-only operator surfaces.',
      }
    default:
      return {
        surface_kind: 'unknown',
        operator_surface: false,
        feed_bootstrap: false,
        preflight_only: false,
        benchmark_gated: false,
        default_venue_applies: false,
        execution_projection_path: null,
        runtime_distinction: 'unknown',
        readiness_semantics: 'unknown',
        promotion_semantics: 'unknown',
        feed_transport_semantics: null,
        summary: `No surface semantics registered for ${surface}.`,
      }
  }
}

function formatSurfaceSummaryLine(surface, request, semantics) {
  return [
    'prediction_surface:',
    `surface=${surface}`,
    `kind=${semantics.surface_kind}`,
    `method=${request.method}`,
    `path=${request.path}`,
    `preflight=${semantics.preflight_only ? 'yes' : 'no'}`,
    `benchmark=${semantics.benchmark_gated ? 'yes' : 'no'}`,
    `default_venue=${semantics.default_venue_applies ? 'yes' : 'no'}`,
    semantics.execution_projection_path
      ? `projection=${semantics.execution_projection_path}`
      : null,
    `runtime=${semantics.runtime_distinction}`,
  ]
    .filter(Boolean)
    .join(' ')
}

function formatSurfaceSemanticsLine(semantics) {
  return [
    'prediction_surface_semantics:',
    `readiness=${semantics.readiness_semantics}`,
    `promotion=${semantics.promotion_semantics}`,
    `transport=${semantics.feed_transport_semantics ?? 'none'}`,
  ].join(' ')
}

function formatRequestPreviewLine(request) {
  const url = new URL(request.url)
  return `prediction_request_preview: ${request.method} ${url.pathname}${url.search}`
}

function getNamedFlagValue(args, name) {
  for (let index = 0; index < args.length; index += 1) {
    const value = args[index]
    if (value === name) {
      const next = args[index + 1]
      return next !== undefined && !next.startsWith('--') ? next : true
    }
    if (value.startsWith(`${name}=`)) {
      return value.slice(name.length + 1)
    }
  }

  return undefined
}

function appendMissingFlag(args, name, value = true) {
  if (hasNamedFlag(args, name)) return
  if (value === true) {
    args.push(name)
    return
  }
  args.push(name, value)
}

function toRequestDescriptor(surface, args, baseUrl) {
  const runId = getNamedFlagValue(args, '--run-id')
  const venue = getNamedFlagValue(args, '--venue')
  const marketId = getNamedFlagValue(args, '--market-id')
  const recommendation = getNamedFlagValue(args, '--recommendation')
  const limit = getNamedFlagValue(args, '--limit')
  const search = getNamedFlagValue(args, '--search')
  const url = new URL(baseUrl)
  let method = 'GET'
  let path = '/api/v1/prediction-markets/runs'
  let body = null

  switch (surface) {
    case 'run':
      path = `/api/v1/prediction-markets/runs/${runId ?? '<run-id>'}`
      break
    case 'markets':
      path = '/api/v1/prediction-markets/markets'
      if (venue) url.searchParams.set('venue', venue)
      if (search && typeof search === 'string') url.searchParams.set('search', search)
      if (limit && typeof limit === 'string') url.searchParams.set('limit', limit)
      break
    case 'capabilities':
    case 'health':
      path = `/api/v1/prediction-markets/${surface}`
      if (venue) url.searchParams.set('venue', venue)
      break
    case 'dispatch':
    case 'paper':
    case 'shadow':
    case 'live':
      method = 'POST'
      path = `/api/v1/prediction-markets/runs/${runId ?? '<run-id>'}/${surface}`
      break
    case 'advise':
      method = 'POST'
      path = '/api/v1/prediction-markets/advise'
      body = {
        market_id: typeof marketId === 'string' ? marketId : undefined,
        venue: typeof venue === 'string' ? venue : undefined,
      }
      break
    case 'replay':
      method = 'POST'
      path = '/api/v1/prediction-markets/replay'
      body = {
        run_id: typeof runId === 'string' ? runId : undefined,
      }
      break
    case 'runs':
    default:
      path = '/api/v1/prediction-markets/runs'
      if (venue) url.searchParams.set('venue', venue)
      if (recommendation && typeof recommendation === 'string') {
        url.searchParams.set('recommendation', recommendation)
      }
      if (limit && typeof limit === 'string') url.searchParams.set('limit', limit)
      break
  }

  url.pathname = path

  return {
    method,
    path,
    url: url.toString(),
    body,
  }
}

function hasNamedFlag(args, name) {
  return args.includes(name) || args.some((value) => value.startsWith(`${name}=`))
}

function printUsage(stream = process.stdout) {
  stream.write(
    [
      'prediction-ops usage:',
      '  node scripts/prediction-ops.cjs <surface> [args]',
      '',
      'Surfaces:',
      `  ${[...COMMAND_ALIASES.keys()].join(', ')}`,
      '',
      'Examples:',
      '  node scripts/prediction-ops.cjs runs --json',
      '  node scripts/prediction-ops.cjs capabilities --venue polymarket --json',
      '  node scripts/prediction-ops.cjs live --run-id run-123 --execution-pathways-summary',
      '  node scripts/prediction-ops.cjs live --run-id run-123 --operator-summary',
      '  node scripts/prediction-ops.cjs feed --print-request',
      '',
      'Environment:',
      '  PREDICTION_BASE_URL=http://127.0.0.1:3000',
      '  PREDICTION_DEFAULT_VENUE=polymarket',
      '',
      'Debug:',
      '  --print-command prints the resolved mc-cli command as JSON without executing it.',
      '  --print-request prints the resolved HTTP request as JSON without executing it.',
      '  --print-summary prints a compact human-readable surface summary without executing it.',
      '  --operator-json expands to --operator-summary plus --json.',
    ].join('\n') + '\n',
  )
}

function resolveCommand(argv) {
  if (argv.length === 0 || argv[0] === '--help' || argv[0] === '-h') {
    return { help: true }
  }

  const [rawSurface, ...rawArgs] = argv
  const surface = COMMAND_ALIASES.get(rawSurface)

  if (!surface) {
    return { error: `Unknown prediction operator surface: ${rawSurface}` }
  }

  const printOnly = rawArgs.includes('--print-command')
  const printRequest = rawArgs.includes('--print-request')
  const printSummary = rawArgs.includes('--print-summary')
  const withPresets = rawArgs.filter(
    (value) =>
      value !== '--print-command' &&
      value !== '--print-request' &&
      value !== '--print-summary' &&
      value !== '--operator-summary' &&
      value !== '--operator-json',
  )
  const args = [...withPresets]
  if (rawArgs.includes('--operator-summary') || rawArgs.includes('--operator-json')) {
    for (const flag of OPERATOR_SUMMARY_FLAGS) {
      appendMissingFlag(args, flag)
    }
  }
  if (rawArgs.includes('--operator-json')) {
    appendMissingFlag(args, '--json')
  }
  if (FEED_BOOTSTRAP_SURFACES.has(rawSurface)) {
    appendMissingFlag(args, '--venue', DEFAULT_VENUE)
  }
  if (!hasNamedFlag(args, '--url') && DEFAULT_URL) {
    args.push('--url', DEFAULT_URL)
  }
  const resolvedUrl = getNamedFlagValue(args, '--url')
  const request = toRequestDescriptor(
    surface,
    args,
    typeof resolvedUrl === 'string' ? resolvedUrl : DEFAULT_URL,
  )
  const semantics = buildSurfaceSemantics(surface)

  return {
    help: false,
    printOnly,
    printRequest,
    printSummary,
    exec: process.execPath,
    args: [CLI_PATH, 'prediction-markets', surface, ...args],
    surface,
    request,
    semantics,
  }
}

const resolved = resolveCommand(process.argv.slice(2))

if (resolved.help) {
  printUsage()
  process.exit(0)
}

if (resolved.error) {
  printUsage(process.stderr)
  process.stderr.write(`${resolved.error}\n`)
  process.exit(2)
}

if (resolved.printSummary) {
  process.stdout.write(`${formatSurfaceSummaryLine(resolved.surface, resolved.request, resolved.semantics)}\n`)
  process.stdout.write(`${formatSurfaceSemanticsLine(resolved.semantics)}\n`)
  process.stdout.write(`${formatRequestPreviewLine(resolved.request)}\n`)
  process.stdout.write(`prediction_surface_summary: ${resolved.semantics.summary}\n`)
  process.exit(0)
}

if (resolved.printOnly || resolved.printRequest || process.env.PREDICTION_OPS_DRY_RUN === '1') {
  process.stdout.write(`${JSON.stringify({
    exec: resolved.exec,
    args: resolved.args,
    surface: resolved.surface,
    request: resolved.request,
    request_preview: `${resolved.request.method} ${new URL(resolved.request.url).pathname}${new URL(resolved.request.url).search}`,
    surface_summary: resolved.semantics.summary,
    semantics: resolved.semantics,
  })}\n`)
  process.exit(0)
}

const child = spawnSync(resolved.exec, resolved.args, {
  stdio: 'inherit',
  env: process.env,
})

if (child.error) {
  process.stderr.write(`${child.error.message}\n`)
  process.exit(1)
}

process.exit(child.status ?? 1)
