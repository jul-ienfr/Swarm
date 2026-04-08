#!/usr/bin/env node

const { URL } = require('node:url')

const DEFAULT_URL = 'http://127.0.0.1:3000'
const SURFACES = ['dispatch', 'paper', 'shadow', 'live']

function yesNo(value) {
  return value ? 'yes' : 'no'
}

function firstDefined(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null) return value
  }
  return undefined
}

function asArray(value) {
  if (Array.isArray(value)) return value
  if (value === undefined || value === null) return []
  return [value]
}

function asRecord(value) {
  if (value && typeof value === 'object' && !Array.isArray(value)) return value
  return null
}

function compactText(value, maxLength = 80) {
  const text = String(value)
  if (text.length <= maxLength) return text
  if (maxLength <= 3) return text.slice(0, maxLength)
  return `${text.slice(0, maxLength - 3)}...`
}

function compactValue(value, maxLength = 80) {
  if (value === undefined || value === null) return null
  if (typeof value === 'string') return compactText(value, maxLength)
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    const items = value
      .map((item) => compactValue(item, Math.max(24, Math.floor(maxLength / 2))))
      .filter(Boolean)
    if (items.length === 0) return null
    const limited = items.slice(0, 4)
    return items.length > 4 ? `${limited.join('|')}|+${items.length - 4}` : limited.join('|')
  }
  if (typeof value === 'object') {
    const preferred = firstDefined(value.kind, value.type, value.name, value.code, value.reason, value.summary)
    if (preferred !== undefined && preferred !== null && preferred !== value) {
      return compactValue(preferred, maxLength)
    }
    const entries = Object.entries(value)
      .filter(([, entryValue]) => entryValue !== undefined && entryValue !== null)
      .slice(0, 4)
      .map(([key, entryValue]) => `${key}=${compactValue(entryValue, Math.max(24, Math.floor(maxLength / 2)))}`)
      .filter(Boolean)
    return entries.length > 0 ? entries.join('|') : null
  }
  return compactText(value, maxLength)
}

function compactCountsValue(value) {
  if (value === undefined || value === null) return null
  if (Array.isArray(value)) return `n=${value.length}`
  if (typeof value === 'object') {
    const entries = Object.entries(value)
      .filter(([, entryValue]) => entryValue !== undefined && entryValue !== null)
      .slice(0, 5)
      .map(([key, entryValue]) => `${key}=${compactValue(entryValue, 32)}`)
      .filter(Boolean)
    return entries.length > 0 ? entries.join('|') : null
  }
  return compactValue(value, 48)
}

function parseMaybeJson(value) {
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

function parseArgs(argv) {
  const args = argv.slice(2)
  if (args[0] !== 'prediction-markets') {
    return { group: null, command: null, flags: {}, positionals: args }
  }

  args.shift()
  const command = args.shift() ?? null
  const flags = {
    json: false,
    researchSignalsSummary: false,
    researchSummary: false,
    benchmarkSummary: false,
    executionReadinessSummary: false,
    executionPathwaysSummary: false,
    artifactAuditSummary: false,
    url: process.env.MC_URL ?? DEFAULT_URL,
    researchSignals: [],
    researchSignal: [],
  }
  const positionals = []

  for (let index = 0; index < args.length; index += 1) {
    const token = args[index]
    if (!token.startsWith('--')) {
      positionals.push(token)
      continue
    }

    const name = token.slice(2)
    const next = args[index + 1]
    const hasValue = next !== undefined && !next.startsWith('--')

    switch (name) {
      case 'json':
        flags.json = true
        break
      case 'research-signals-summary':
        flags.researchSignalsSummary = true
        break
      case 'research-summary':
        flags.researchSummary = true
        break
      case 'benchmark-summary':
        flags.benchmarkSummary = true
        break
      case 'execution-readiness-summary':
        flags.executionReadinessSummary = true
        break
      case 'execution-pathways-summary':
        flags.executionPathwaysSummary = true
        break
      case 'artifact-audit-summary':
        flags.artifactAuditSummary = true
        break
      case 'url':
        if (hasValue) {
          flags.url = next
          index += 1
        }
        break
      case 'run-id':
      case 'market-id':
      case 'venue':
      case 'recommendation':
      case 'limit':
      case 'execution-mode':
        if (hasValue) {
          flags[name.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = next
          index += 1
        }
        break
      case 'research-signals':
        if (hasValue) {
          const parsed = parseMaybeJson(next)
          if (Array.isArray(parsed)) flags.researchSignals.push(...parsed)
          else flags.researchSignals.push(parsed)
          index += 1
        }
        break
      case 'research-signal':
        if (hasValue) {
          flags.researchSignal.push(parseMaybeJson(next))
          index += 1
        }
        break
      default:
        if (hasValue) {
          flags[name.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = next
          index += 1
        } else {
          flags[name.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = true
        }
        break
    }
  }

  return { group: 'prediction-markets', command, flags, positionals }
}

function joinList(values, separator = '|', fallback = 'none') {
  const list = values.filter((value) => value !== undefined && value !== null && value !== '')
  return list.length > 0 ? list.join(separator) : fallback
}

function hasCanonicalBenchmarkSignal(source) {
  return [
    source.benchmark_gate_summary,
    source.benchmark_gate_status,
    source.benchmark_status,
    source.benchmark_promotion_status,
    source.benchmark_promotion,
    source.benchmark_promotion_ready,
    source.benchmark_ready,
    source.benchmark_uplift_bps,
    source.benchmark_gate_uplift_bps,
    source.benchmark_gate_blockers,
    source.benchmark_blockers,
    source.benchmark_gate_reasons,
    source.benchmark_reasons,
    source.benchmark_preview_available,
    source.benchmark_promotion_evidence,
    source.benchmark_evidence_level,
    source.benchmark_promotion_gate_kind,
    source.benchmark_promotion_blocker_summary,
    source.benchmark_verdict,
  ].some((value) => value !== undefined && value !== null)
}

function pickBenchmarkField(source, benchmarkValue, researchValue, fallback) {
  if (benchmarkValue !== undefined && benchmarkValue !== null) return benchmarkValue
  if (!hasCanonicalBenchmarkSignal(source) && researchValue !== undefined && researchValue !== null) return researchValue
  return fallback
}

function formatResearchLine(source) {
  const research = extractResearchContext(source)
  if (!research) return null

  return [
    'research:',
    `mode=${research.mode}`,
    `pipeline=${research.pipelineId}`,
    research.version ? `v=${research.version}` : null,
    research.forecasters !== undefined ? `forecasters=${research.forecasters}` : null,
    research.weighted !== undefined ? `weighted=${research.weighted}` : null,
    research.coverage !== undefined ? `coverage=${research.coverage}` : null,
    research.preferred ? `compare=${research.preferred}` : null,
    research.abstention ? `abstention=${research.abstention}` : null,
    `blocks=${research.blocksForecast ? 'yes' : 'no'}`,
    research.forecastHint !== undefined ? `forecast=${research.forecastHint}` : null,
    `summary="${research.summary}"`,
  ]
    .filter(Boolean)
    .join(' ')
}

function extractResearchContext(source) {
  if (!source) return null
  const pipelineId = firstDefined(source.research_pipeline_id, source.researchPipelineId)
  if (!pipelineId) return null

  const version = firstDefined(source.research_pipeline_version, source.research_version)
  const forecasters = firstDefined(source.research_forecaster_count, source.research_forecasters)
  const weighted = firstDefined(source.research_weighted_probability_yes, source.research_weighted_yes)
  const coverage = firstDefined(source.research_weighted_coverage, source.research_coverage)
  const preferred = firstDefined(source.research_compare_preferred_mode, source.research_preferred_mode)
  const mode = preferred === 'market_only' ? 'market_only' : 'research_driven'
  const abstention = firstDefined(source.research_abstention_policy_version, source.research_abstention_policy)
  const blocksForecast = firstDefined(source.research_abstention_policy_blocks_forecast, source.research_blocks_forecast)
  const forecastHint = firstDefined(source.research_forecast_probability_yes_hint, source.research_forecast_hint)
  const summary = firstDefined(source.research_compare_summary, source.research_summary, 'Preferred mode: aggregate.')
  const recommendation = firstDefined(source.recommendation, source.research_recommendation)
  const abstentionEffect = blocksForecast === true
    ? 'flipped_to_wait'
    : preferred === 'abstention'
      ? 'preferred_abstention'
      : mode === 'market_only'
        ? 'market_baseline'
        : 'clear'

  return {
    pipelineId,
    version,
    forecasters,
    weighted,
    coverage,
    preferred,
    mode,
    abstention,
    blocksForecast: blocksForecast === true,
    forecastHint,
    summary,
    recommendation,
    abstentionEffect,
  }
}

function formatResearchOriginLine(source) {
  const research = extractResearchContext(source)
  if (!research) return null

  return [
    'research_origin:',
    `origin=${research.mode}`,
    research.recommendation ? `recommendation=${research.recommendation}` : null,
    `abstention_effect=${research.abstentionEffect}`,
  ]
    .filter(Boolean)
    .join(' ')
}

function formatBenchmarkLine(source) {
  if (!source) return null
  const status = pickBenchmarkField(
    source,
    firstDefined(source.benchmark_gate_status, source.benchmark_status),
    firstDefined(source.research_benchmark_gate_status, source.research_benchmark_status),
  )
  if (!status) return null
  const promotion = pickBenchmarkField(
    source,
    firstDefined(source.benchmark_promotion_status, source.benchmark_promotion),
    firstDefined(source.research_benchmark_promotion_status, source.research_benchmark_promotion),
  )
  const ready = pickBenchmarkField(
    source,
    firstDefined(source.benchmark_promotion_ready, source.benchmark_ready),
    firstDefined(source.research_benchmark_promotion_ready, source.research_benchmark_ready),
  )
  const uplift = pickBenchmarkField(
    source,
    firstDefined(source.benchmark_uplift_bps, source.benchmark_gate_uplift_bps),
    firstDefined(source.research_benchmark_uplift_bps, source.research_benchmark_gate_uplift_bps),
  )
  const blockers = asArray(firstDefined(
    source.benchmark_gate_blockers,
    source.benchmark_blockers,
    source.research_benchmark_gate_blockers,
    source.research_benchmark_blockers,
  ))
  const reasons = asArray(firstDefined(
    source.benchmark_gate_reasons,
    source.benchmark_reasons,
    source.research_benchmark_gate_reasons,
    source.research_benchmark_reasons,
  ))

  return [
    `benchmark: status=${status}`,
    promotion ? `promotion=${promotion}` : null,
    `ready=${yesNo(ready)}`,
    uplift !== undefined ? `uplift=${uplift}bps` : null,
    `blockers=${joinList(blockers, '|')}`,
    `reasons=${joinList(reasons, '|')}`,
  ]
    .filter(Boolean)
    .join(' ')
}

function formatBenchmarkEvidenceLine(source) {
  if (!source) return null
  const status = pickBenchmarkField(
    source,
    firstDefined(source.benchmark_gate_status, source.benchmark_status),
    firstDefined(source.research_benchmark_gate_status, source.research_benchmark_status),
  )
  if (!status) return null
  const promotionStatus = pickBenchmarkField(
    source,
    firstDefined(source.benchmark_promotion_status, source.benchmark_promotion),
    firstDefined(source.research_benchmark_promotion_status, source.research_benchmark_promotion),
  )
  const ready = pickBenchmarkField(
    source,
    firstDefined(source.benchmark_promotion_ready, source.benchmark_ready),
    firstDefined(source.research_benchmark_promotion_ready, source.research_benchmark_ready),
  )
  const previewAvailable = pickBenchmarkField(
    source,
    source.benchmark_preview_available,
    source.research_benchmark_preview_available,
    true,
  )
  const promotionEvidence = pickBenchmarkField(
    source,
    source.benchmark_promotion_evidence,
    source.research_benchmark_promotion_evidence,
    ready === true ? 'local_benchmark' : 'unproven',
  )

  return [
    'benchmark_evidence:',
    `preview=${yesNo(previewAvailable)}`,
    `promotion_evidence=${promotionEvidence ?? 'unproven'}`,
    promotionStatus ? `promotion_status=${promotionStatus}` : null,
    `ready=${yesNo(ready)}`,
    `out_of_sample=${promotionEvidence ?? 'unproven'}`,
  ]
    .filter(Boolean)
    .join(' ')
}

function formatBenchmarkStateLine(source) {
  if (!source) return null
  const gateStatus = pickBenchmarkField(
    source,
    firstDefined(source.benchmark_gate_status, source.benchmark_status),
    firstDefined(source.research_benchmark_gate_status, source.research_benchmark_status),
  )
  const promotionStatus = pickBenchmarkField(
    source,
    firstDefined(source.benchmark_promotion_status, source.benchmark_promotion),
    firstDefined(source.research_benchmark_promotion_status, source.research_benchmark_promotion),
  )
  const promotionReady = pickBenchmarkField(
    source,
    firstDefined(source.benchmark_promotion_ready, source.benchmark_ready),
    firstDefined(source.research_benchmark_promotion_ready, source.research_benchmark_ready),
  )
  const promotionEvidence = pickBenchmarkField(
    source,
    source.benchmark_promotion_evidence,
    source.research_benchmark_promotion_evidence,
    promotionReady === true ? 'local_benchmark' : 'unproven',
  )
  const evidenceLevel = pickBenchmarkField(
    source,
    source.benchmark_evidence_level,
    source.research_benchmark_evidence_level,
    promotionEvidence === 'local_benchmark' ? 'out_of_sample_promotion_evidence' : 'benchmark_preview',
  )
  const promotionGateKind = pickBenchmarkField(
    source,
    source.benchmark_promotion_gate_kind,
    source.research_promotion_gate_kind,
    promotionEvidence === 'local_benchmark' ? 'local_benchmark' : 'preview_only',
  )
  const blockerSummary = pickBenchmarkField(
    source,
    firstDefined(source.benchmark_promotion_blocker_summary, source.benchmark_promotion_summary),
    source.research_benchmark_promotion_blocker_summary,
    joinList(asArray(firstDefined(
      hasCanonicalBenchmarkSignal(source) ? source.benchmark_gate_blockers : source.research_benchmark_gate_blockers,
    )), '; '),
  ) ?? pickBenchmarkField(
    source,
    joinList(asArray(source.benchmark_gate_reasons), '; '),
    joinList(asArray(source.research_benchmark_gate_reasons), '; '),
  )
  const hasBenchmarkSignal = gateStatus != null || promotionStatus != null || promotionReady != null || evidenceLevel != null || blockerSummary != null || promotionGateKind != null
  const verdict = firstDefined(
    source.benchmark_verdict,
    hasCanonicalBenchmarkSignal(source) ? undefined : source.research_benchmark_verdict,
    gateStatus === 'blocked_by_abstention'
      ? 'blocked_by_abstention'
      : promotionReady === true
        ? 'local_benchmark_ready'
        : promotionStatus === 'blocked' || (promotionStatus === 'eligible' && promotionReady === false)
          ? 'local_benchmark_blocked'
          : promotionEvidence === 'local_benchmark'
            ? 'local_benchmark_blocked'
            : hasBenchmarkSignal
              ? 'preview_only'
              : null,
  )
  if (verdict == null && promotionReady == null && evidenceLevel == null && blockerSummary == null) return null

  return [
    'benchmark_state:',
    verdict ? `verdict=${verdict}` : null,
    promotionGateKind ? `promotion_gate_kind=${promotionGateKind}` : null,
    promotionReady != null ? `ready=${yesNo(promotionReady)}` : null,
    evidenceLevel ? `evidence_level=${evidenceLevel}` : null,
    blockerSummary ? `promotion_blocker_summary=${blockerSummary}` : null,
  ]
    .filter(Boolean)
    .join(' ')
}

function formatExecutionPathwaysLine(entry) {
  const pathways = asArray(entry.execution_pathways?.pathways)
  const count = pathways.length
  const summary = entry.execution_pathways?.summary
  const highest = entry.execution_pathways?.highest_actionable_mode
  const entries = pathways.map((path) => `${path.mode}:${path.status}`).join(' | ')
  return [
    `execution_pathways: highest_actionable_mode=${highest ?? 'unknown'}`,
    `count=${count}`,
    `entries=${entries || 'none'}`,
    summary ? `summary="${summary}"` : null,
  ]
    .filter(Boolean)
    .join(' ')
}

function formatArtifactAuditLine(audit, prefix = '') {
  if (!audit) return null
  return `${prefix}artifact_audit: manifest=${audit.manifest_ref_count ?? 0} observed=${audit.observed_ref_count ?? 0} canonical=${audit.canonical_ref_count ?? 0} duplicates=${(audit.duplicate_artifact_ids ?? []).length} manifest_only=${(audit.manifest_only_artifact_ids ?? []).length} observed_only=${(audit.observed_only_artifact_ids ?? []).length}`
}

function formatArtifactReadbackLine(readback, prefix = '') {
  if (!readback) return null
  return `${prefix}artifact_readback: run_manifest=${readback.run_manifest_ref?.artifact_id ?? 'unknown'} manifest=${(readback.manifest_artifact_refs ?? []).length} observed=${(readback.observed_artifact_refs ?? []).length} canonical=${(readback.canonical_artifact_refs ?? []).length}`
}

function extractProjection(source) {
  const projection = source.execution_projection ?? source
  const preflight = source.execution_projection_preflight_summary ?? projection.preflight_summary ?? null
  const selectedPathHint = firstDefined(source.execution_projection_selected_path, projection.selected_path)
  const projectedPaths = projection.projected_paths ?? (
    selectedPathHint
      ? {
        [selectedPathHint]: {
          status: firstDefined(
            source.execution_projection_selected_path_status,
            projection.selected_path_status,
            null,
          ),
          effective_mode: firstDefined(
            source.execution_projection_selected_path_effective_mode,
            projection.selected_path_effective_mode,
            selectedPathHint,
          ),
          reason_summary: firstDefined(
            source.execution_projection_selected_path_reason_summary,
            projection.selected_path_reason_summary,
            null,
          ),
          canonical_trade_intent_preview: source.execution_projection_selected_preview ?? null,
          sizing_signal: source.execution_projection_selected_sizing_signal ?? null,
        },
      }
      : {}
  )
  const selectedPath = firstDefined(source.execution_projection_selected_path, projection.selected_path)
  const selectedPathData = selectedPath ? projectedPaths[selectedPath] ?? null : null
  const selectedPreview = firstDefined(source.execution_projection_selected_preview, projection.selected_preview, null)
  const requestedPath = firstDefined(source.execution_projection_requested_path, projection.requested_path)
  const verdict = firstDefined(source.execution_projection_verdict, projection.verdict)
  const highestSafe = firstDefined(source.execution_projection_highest_safe_requested_mode, projection.highest_safe_requested_mode)
  const recommended = firstDefined(source.execution_projection_recommended_effective_mode, projection.recommended_effective_mode)
  const manualReview = firstDefined(source.execution_projection_manual_review_required, projection.manual_review_required)
  const ttlMs = firstDefined(source.execution_projection_ttl_ms, projection.ttl_ms)
  const summary = firstDefined(source.execution_projection_summary, projection.summary)
  const basis = firstDefined(preflight?.basis, projection.basis, {})
  const counts = firstDefined(preflight?.counts, projection.preflight_summary?.counts, null)
  const sourceRefs = asArray(firstDefined(preflight?.source_refs, projection.preflight_summary?.source_refs, []))
  const blockers = asArray(firstDefined(preflight?.blockers, projection.preflight_summary?.blockers, source.execution_projection_blocking_reasons, []))
  const downgrades = asArray(firstDefined(preflight?.downgrade_reasons, projection.preflight_summary?.downgrade_reasons, source.execution_projection_downgrade_reasons, []))

  const basisParts = []
  if (basis.uses_execution_readiness) basisParts.push('readiness')
  if (basis.uses_compliance) basisParts.push('compliance')
  if (basis.uses_capital) basisParts.push('capital')
  if (basis.uses_reconciliation) basisParts.push('reconciliation')

  return {
    source,
    projection,
    preflight,
    projectedPaths,
    selectedPath,
    selectedPathData,
    selectedPreview,
    requestedPath,
    verdict,
    highestSafe,
    recommended,
    manualReview,
    ttlMs,
    summary,
    basis,
    basisParts,
    counts,
    sourceRefs,
    blockers,
    downgrades,
  }
}

function formatProjectionLine(source, extracted, options = {}) {
  if (!extracted.requestedPath || !extracted.selectedPath) return null
  const modes = ['paper', 'shadow', 'live']
    .filter((mode) => extracted.projectedPaths[mode] || extracted.projection?.modes?.[mode])
    .join('|')
  const projectedPaths = ['paper', 'shadow', 'live']
    .filter((mode) => extracted.projectedPaths[mode])
    .map((mode) => `${mode}:${extracted.projectedPaths[mode].status}`)
    .join('|')

  return [
    `execution_projection: requested=${extracted.requestedPath}`,
    `selected=${extracted.selectedPath}`,
    `verdict=${extracted.verdict}`,
    `highest_safe=${extracted.highestSafe}`,
    `recommended=${extracted.recommended}`,
    `manual_review=${yesNo(extracted.manualReview)}`,
    `gate=execution_projection`,
    `preflight=yes`,
    extracted.ttlMs !== undefined ? `ttl_ms=${extracted.ttlMs}` : null,
    options.includeModeCount === false ? null : (modes ? `modes=${modes.split('|').length}` : null),
    `basis=${extracted.basisParts.join(',') || 'unknown'}`,
    extracted.basis?.capital_status ? `capital=${extracted.basis.capital_status}` : null,
    extracted.basis?.reconciliation_status ? `reconciliation=${extracted.basis.reconciliation_status}` : null,
    projectedPaths ? `projected_paths=${projectedPaths}` : null,
    extracted.summary ? `summary="${extracted.summary}"` : null,
  ]
    .filter(Boolean)
    .join(' ')
}

function formatProjectionCompactLine(extracted) {
  if (!extracted.requestedPath || !extracted.selectedPath) return null
  const modes = ['paper', 'shadow', 'live']
    .filter((mode) => extracted.projectedPaths[mode] || extracted.projection?.modes?.[mode])
    .join('|')

  return [
    `execution_projection: requested=${extracted.requestedPath}`,
    `selected=${extracted.selectedPath}`,
    `verdict=${extracted.verdict}`,
    `highest_safe=${extracted.highestSafe}`,
    `recommended=${extracted.recommended}`,
    `manual_review=${yesNo(extracted.manualReview)}`,
    `gate=execution_projection`,
    `preflight=yes`,
    extracted.ttlMs !== undefined ? `ttl_ms=${extracted.ttlMs}` : null,
    modes ? `modes=${modes.split('|').length}` : null,
    `basis=${extracted.basisParts.join(',') || 'unknown'}`,
    extracted.summary ? `summary="${extracted.summary}"` : null,
  ]
    .filter(Boolean)
    .join(' ')
}

function formatSelectedPathStateLine(extracted) {
  if (!extracted.selectedPath) return null
  const selectedPath = extracted.selectedPathData ?? {}
  const shadowSimulation =
    firstDefined(
      selectedPath.simulation?.shadow_arbitrage,
      selectedPath.shadow_arbitrage_signal,
      null,
    ) != null
  return [
    `execution_projection selected: mode=${extracted.selectedPath}`,
    `status=${selectedPath.status ?? 'n/a'}`,
    `effective=${selectedPath.effective_mode ?? extracted.selectedPath}`,
    `shadow_sim=${shadowSimulation ? 'yes' : 'no'}`,
  ].join(' ')
}

function formatProjectionPreflightLine(extracted) {
  if (!extracted.requestedPath || !extracted.selectedPath) return null
  return [
    `execution_projection preflight: gate=execution_projection`,
    `verdict=${extracted.verdict}`,
    `requested=${extracted.requestedPath}`,
    `selected=${extracted.selectedPath}`,
    `highest_safe=${extracted.highestSafe}`,
    `recommended=${extracted.recommended}`,
    `manual_review=${yesNo(extracted.manualReview)}`,
    extracted.ttlMs !== undefined ? `ttl_ms=${extracted.ttlMs}` : null,
  ]
    .filter(Boolean)
    .join(' ')
}

function formatProjectionDetailsLine(extracted) {
  if (!extracted.counts) return null
  return [
    `execution_projection preflight details: eligible=${extracted.counts.eligible}/${extracted.counts.total}`,
    `counts=ready:${extracted.counts.ready}|degraded:${extracted.counts.degraded}|blocked:${extracted.counts.blocked}`,
    `basis=${extracted.basisParts.join(',') || 'unknown'}`,
    `refs=${extracted.sourceRefs.length}`,
    `blockers=${extracted.blockers.length}`,
    `downgrades=${extracted.downgrades.length}`,
  ].join(' ')
}

function formatSelectedPreviewLine(extracted) {
  const preview = extracted.selectedPreview
  if (!preview) return null
  const previewKind = firstDefined(preview.kind, preview.preview_kind)
  const previewSource = sourcePreviewLabel(extracted)
  return [
    'execution_projection selected preview:',
    previewKind != null ? `kind=${previewKind}` : null,
    `source=${previewSource}`,
    `size=${preview.size_usd ?? preview.canonical_size_usd ?? 'unknown'}`,
    `via=runtime_hint`,
    preview.limit_price !== undefined ? `limit=${preview.limit_price}` : null,
    preview.time_in_force ? `tif=${preview.time_in_force}` : null,
    preview.max_slippage_bps !== undefined ? `slip=${preview.max_slippage_bps}bps` : null,
  ]
    .filter(Boolean)
    .join(' ')
}

function sourcePreviewLabel(extracted) {
  return firstDefined(
    extracted.source.execution_projection_selected_preview_source,
    extracted.source.paper_trade_intent_preview_source,
    extracted.source.shadow_trade_intent_preview_source,
    extracted.source.live_trade_intent_preview_source,
    'canonical_trade_intent_preview',
  )
}

function formatStrategyLayerLine(source, extracted = null) {
  if (!source) return null

  const strategyRoot = asRecord(firstDefined(
    source.strategy_layer,
    source.strategy_hints,
    source.execution_strategy,
    source.execution_projection?.strategy_layer,
    source.execution_projection?.strategy,
    source.execution_pathways?.strategy,
    source.multi_venue_execution?.strategy,
    source.trade_intent_guard?.strategy,
    source.strategy,
  ))

  const primaryStrategy = firstDefined(
    strategyRoot?.primary_strategy,
    strategyRoot?.primary,
    strategyRoot?.name,
    typeof source.strategy === 'string' ? source.strategy : null,
    source.primary_strategy,
    source.strategy_primary,
    source.strategy_name,
    source.execution_projection_primary_strategy,
  )

  const marketRegime = firstDefined(
    strategyRoot?.market_regime,
    strategyRoot?.regime,
    source.market_regime,
    source.strategy_market_regime,
    source.execution_projection_market_regime,
    source.execution_pathways_market_regime,
  )

  const strategyCounts = firstDefined(
    strategyRoot?.strategy_counts,
    strategyRoot?.counts,
    source.strategy_counts,
    source.strategy_count,
    source.execution_projection_strategy_counts,
    source.execution_pathways_strategy_counts,
  )

  const strategyShadowSummary = firstDefined(
    strategyRoot?.strategy_shadow_summary,
    strategyRoot?.shadow_summary,
    source.strategy_shadow_summary,
    source.shadow_summary,
    source.execution_projection_strategy_shadow_summary,
    source.execution_pathways_shadow_summary,
  )

  const resolutionAnomalies = firstDefined(
    strategyRoot?.resolution_anomalies,
    strategyRoot?.anomalies,
    source.resolution_anomalies,
    source.resolution_anomaly_summary,
    source.strategy_resolution_anomalies,
    source.execution_projection_resolution_anomalies,
    source.execution_pathways_resolution_anomalies,
  )

  const preview = asRecord(firstDefined(
    extracted?.selectedPreview,
    source.execution_intent_preview,
    source.execution_projection_selected_preview,
    source.execution_surface_preview,
    source.trade_intent_guard?.trade_intent_preview,
    source.paper_trade_intent_preview,
    source.shadow_trade_intent_preview,
    source.live_trade_intent_preview,
  ))
  const previewKind = firstDefined(
    preview?.kind,
    preview?.preview_kind,
    preview?.type,
    source.execution_intent_preview_kind,
    source.execution_projection_selected_preview_kind,
    source.execution_surface_preview_kind,
    source.trade_intent_preview_kind,
  )
  const previewSource = firstDefined(
    source.execution_projection_selected_preview_source,
    source.execution_surface_preview_source,
    source.execution_intent_preview_source,
    source.trade_intent_preview_source,
    source.live_trade_intent_preview_source,
    source.paper_trade_intent_preview_source,
    source.shadow_trade_intent_preview_source,
    source.trade_intent_guard?.metadata?.trade_intent_preview_source,
  )

  if (
    primaryStrategy == null
    && marketRegime == null
    && strategyCounts == null
    && strategyShadowSummary == null
    && resolutionAnomalies == null
    && previewKind == null
    && previewSource == null
  ) {
    return null
  }

  return [
    'strategy_layer:',
    primaryStrategy != null ? `primary=${compactValue(primaryStrategy)}` : null,
    marketRegime != null ? `regime=${compactValue(marketRegime)}` : null,
    strategyCounts != null ? `counts=${compactCountsValue(strategyCounts)}` : null,
    strategyShadowSummary != null ? `shadow=${compactValue(strategyShadowSummary, 96)}` : null,
    resolutionAnomalies != null ? `anomalies=${compactValue(resolutionAnomalies, 96)}` : null,
    previewKind != null ? `preview_kind=${compactValue(previewKind, 48)}` : null,
    previewSource != null ? `preview_source=${compactValue(previewSource, 48)}` : null,
  ]
    .filter(Boolean)
    .join(' ')
}

function formatSelectedOpsLine(extracted) {
  const preview = extracted.selectedPreview
  if (!preview) return null
  const selectedPath = extracted.selectedPathData ?? {}
  const sizing = selectedPath.sizing_signal ?? extracted.source.execution_projection_selected_sizing_signal ?? null
  const canonicalSize = firstDefined(
    selectedPath.canonical_trade_intent_preview?.size_usd,
    preview.canonical_size_usd,
    preview.size_usd,
  )
  const previewSize = firstDefined(sizing?.preview_size_usd, preview.preview_size_usd, preview.size_usd)
  const parts = [`execution_projection selected ops: canonical_size=${canonicalSize}`]
  if (previewSize !== undefined && previewSize !== canonicalSize) {
    parts.push(`capped_from=${previewSize}`)
  }
  parts.push(`source=${sizing?.source ?? 'trade_intent_preview'}`)
  parts.push(`tif=${preview.time_in_force ?? sizing?.time_in_force ?? 'n/a'}`)

  const shadowSignal = firstDefined(
    selectedPath.shadow_arbitrage_signal,
    selectedPath.simulation?.shadow_arbitrage_signal,
    selectedPath.simulation?.shadow_arbitrage,
    null,
  )
  if (shadowSignal) {
    const edge = firstDefined(
      shadowSignal.shadow_edge_bps,
      shadowSignal.base_executable_edge_bps,
      shadowSignal.executable_edge_bps,
    )
    const pnl = firstDefined(shadowSignal.estimated_net_pnl_bps, shadowSignal.estimated_pnl_bps)
    const worst = firstDefined(shadowSignal.worst_case_kind, shadowSignal.worst_case)
    const size = firstDefined(shadowSignal.recommended_size_usd, shadowSignal.size_usd)
    parts.push(
      `shadow_signal=edge=${edge}|size=${size}|pnl=${pnl}bps|worst=${worst}`,
    )
  }

  return parts.join(' ')
}

function formatMicrostructureLabLine(source) {
  const lab = source.microstructure_lab ?? source.execution_projection?.microstructure_lab
  const summary = lab?.summary
  if (!lab || !summary) return null

  const keyEvents = ['partial_fill', 'one_leg_fill', 'cancel_replace', 'queue_miss']
    .filter((event) => (summary.event_counts?.[event] ?? 0) > 0)
    .map((event) => `${event}:${summary.event_counts[event]}`)

  return [
    `microstructure_lab: market=${lab.market_id ?? 'unknown'}`,
    `venue=${lab.venue ?? 'unknown'}`,
    `base_edge=${summary.base_executable_edge_bps ?? 'unknown'}`,
    `worst=${summary.worst_case_kind ?? 'unknown'}:${summary.worst_case_severity ?? 'unknown'}:${summary.worst_case_executable_edge_bps ?? 'unknown'}`,
    `deterioration=${summary.executable_deterioration_bps ?? 'unknown'}`,
    `recommended=${summary.recommended_mode ?? 'unknown'}`,
    summary.execution_quality_score !== undefined ? `quality=${summary.execution_quality_score}` : null,
    keyEvents.length > 0 ? `events=${keyEvents.join('|')}` : null,
  ]
    .filter(Boolean)
    .join(' ')
}

function formatShadowArbitrageLine(source) {
  const report =
    source.shadow_arbitrage
    ?? source.execution_projection?.projected_paths?.shadow?.simulation?.shadow_arbitrage
    ?? source.execution_projection?.projected_paths?.live?.simulation?.shadow_arbitrage
    ?? null
  if (!report?.executable_edge || !report?.summary || !report?.sizing) return null

  return [
    `shadow_arbitrage: market=${report.executable_edge.buy_ref?.market_id ?? 'unknown'}`,
    `venue=${report.executable_edge.buy_ref?.venue ?? 'unknown'}`,
    `base_edge=${report.summary.base_executable_edge_bps ?? 'unknown'}`,
    `shadow_edge=${report.summary.shadow_edge_bps ?? 'unknown'}`,
    `hedge_success=${report.summary.hedge_success_probability ?? 'unknown'}`,
    `net_pnl=${report.summary.estimated_net_pnl_bps ?? 'unknown'}bps/${report.summary.estimated_net_pnl_usd ?? 'unknown'}usd`,
    `size=${report.sizing.recommended_size_usd ?? 'unknown'}`,
    `penalized_from=${report.sizing.base_size_usd ?? 'unknown'}`,
    report.sizing.size_multiplier !== undefined ? `x=${Number(report.sizing.size_multiplier).toFixed(2)}` : null,
    `worst=${report.summary.worst_case_kind ?? 'unknown'}`,
    `failure_cases=${report.summary.failure_case_count ?? 0}`,
  ]
    .filter(Boolean)
    .join(' ')
}

function formatPathStateLine(surface, source) {
  const surfacePath = firstDefined(source[`${surface}_path`], source[`${surface}_surface`], null)
  const preview = surfacePath?.canonical_trade_intent_preview ?? surfacePath?.trade_intent_preview ?? source[`${surface}_trade_intent_preview`] ?? null
  const requested = firstDefined(source.execution_projection_requested_path, surfacePath?.requested_mode, surface)
  const selected = firstDefined(source.execution_projection_selected_path, surfacePath?.requested_mode, surface)
  const status = firstDefined(surfacePath?.status, source[`${surface}_status`], 'unknown')
  const effective = firstDefined(surfacePath?.effective_mode, selected)
  const blockers = asArray(firstDefined(surfacePath?.blockers, source[`${surface}_blocking_reasons`], []))
  const size = firstDefined(preview?.size_usd, preview?.canonical_size_usd, source[`${surface}_trade_intent_preview`]?.size_usd)
  const researchMode = firstDefined(
    source.research_runtime_mode,
    source.research_compare_preferred_mode === 'market_only' ? 'market_only' : 'research_driven',
    null,
  )
  const researchOrigin = researchMode

  return [
    `${surface}_surface: status=${firstDefined(source[`${surface}_status`], status)}`,
    `gate=${firstDefined(source.gate_name, `execution_projection_${surface}`)}`,
    `preflight=yes`,
    `run_id=${source.run_id}`,
    `requested=${requested}`,
    `path_status=${status}`,
    `effective_mode=${effective}`,
    `selected=${selected}`,
    researchMode ? `research_mode=${researchMode}` : null,
    researchOrigin ? `research_origin=${researchOrigin}` : null,
    `blockers=${blockers.length}`,
    size !== undefined ? `size=${size}` : null,
  ]
    .filter(Boolean)
    .join(' ')
}

function formatSurfaceCompactLine(surface, source) {
  const requested = firstDefined(source.execution_projection_requested_path, source.execution_projection?.requested_path, surface)
  const selected = firstDefined(source.execution_projection_selected_path, source.execution_projection?.selected_path, surface)
  const blockers = asArray(firstDefined(source[`${surface}_blocking_reasons`], []))
  const researchMode = firstDefined(
    source.research_runtime_mode,
    source.research_compare_preferred_mode === 'market_only' ? 'market_only' : 'research_driven',
    null,
  )
  const researchOrigin = researchMode

  return [
    `${surface}_surface_compact:`,
    `gate=${firstDefined(source.gate_name, `execution_projection_${surface}`)}`,
    'preflight=yes',
    `run_id=${source.run_id}`,
    `requested=${requested}`,
    `selected=${selected}`,
    researchMode ? `research_mode=${researchMode}` : null,
    researchOrigin ? `research_origin=${researchOrigin}` : null,
    `blockers=${blockers.length}`,
  ].join(' ')
}

function formatSurfaceProjectionSummary(source, surface) {
  const projection = source.execution_projection ?? {}
  const requested = firstDefined(source.execution_projection_requested_path, projection.requested_path)
  const selected = firstDefined(source.execution_projection_selected_path, projection.selected_path)
  const verdict = firstDefined(source.execution_projection_verdict, projection.verdict)
  if (!requested || !selected || !verdict) return null
  return `execution_projection: requested=${requested} selected=${selected} verdict=${verdict}`
}

function formatProjectionTrail(source) {
  const projection = source.execution_projection ?? {}
  const projectedPaths = projection.projected_paths ?? {}
  if (!Object.keys(projectedPaths).length) return null
  return ['paper', 'shadow', 'live']
    .filter((mode) => projectedPaths[mode])
    .map((mode) => `${mode}:${projectedPaths[mode].status}`)
    .join('|')
}

function formatExecutionProjectionSourceLine() {
  return 'execution_projection source: canonical gate=execution_projection recalc=no modes=paper|shadow|live'
}

function formatRunEntrySummary(entry, flags, prefix = '') {
  const lines = []
  if (flags.artifactAuditSummary && entry.artifact_audit) {
    lines.push(formatArtifactAuditLine(entry.artifact_audit, prefix))
  }
  if (flags.executionPathwaysSummary && entry.execution_pathways) {
    lines.push(`${prefix}execution_pathways: ${formatExecutionPathwaysLine(entry)}`)
  }
  if (flags.executionPathwaysSummary && entry.execution_projection) {
    const extracted = extractProjection(entry)
    lines.push(
      `${prefix}${formatProjectionLine(entry, extracted)}`,
      `${prefix}${formatProjectionPreflightLine(extracted)}`,
      `${prefix}${formatProjectionDetailsLine(extracted)}`,
      `${prefix}${formatSelectedPreviewLine(extracted)}`,
      `${prefix}${formatSelectedOpsLine(extracted)}`,
      `${prefix}${formatStrategyLayerLine(entry, extracted)}`,
      `${prefix}execution_projection source: canonical gate=execution_projection recalc=no modes=paper|shadow|live`,
    )
  }
  if ((flags.researchSummary || flags.executionPathwaysSummary) && formatResearchLine(entry)) {
    lines.push(`${prefix}${formatResearchLine(entry)}`)
  }
  if ((flags.benchmarkSummary || flags.executionPathwaysSummary) && formatBenchmarkLine(entry)) {
    lines.push(`${prefix}${formatBenchmarkLine(entry)}`)
    const benchmarkEvidenceLine = formatBenchmarkEvidenceLine(entry)
    if (benchmarkEvidenceLine) {
      lines.push(`${prefix}${benchmarkEvidenceLine}`)
    }
    const benchmarkStateLine = formatBenchmarkStateLine(entry)
    if (benchmarkStateLine) {
      lines.push(`${prefix}${benchmarkStateLine}`)
    }
  }
  return lines.filter(Boolean)
}

function formatCommandResponse(command, responseData, flags, requestBody) {
  const payload = responseData?.data ?? {}
  const source = payload?.prediction_run ?? payload ?? {}
  const lines = []
  const method = SURFACES.includes(command) ? 'POST' : command === 'runs' || command === 'run' || command === 'markets' || command === 'capabilities' || command === 'health' ? 'GET' : 'POST'
  lines.push(`OK ${responseData?.status ?? 200} ${method}`)

  if ((command === 'advise' || command === 'replay') && flags.researchSignalsSummary) {
    const injectedSignals = asArray(requestBody?.research_signals)
    lines.push(`Injected research signals: ${injectedSignals.length}`)
  }

  if ((command === 'advise' || command === 'replay') && flags.researchSummary) {
    const researchLine = formatResearchLine(source)
    if (researchLine) lines.push(researchLine)
    const researchOriginLine = formatResearchOriginLine(source)
    if (researchOriginLine) lines.push(researchOriginLine)
  }

  if ((command === 'advise' || command === 'replay') && (flags.researchSummary || flags.benchmarkSummary)) {
    const benchmarkLine = formatBenchmarkLine(source)
    if (benchmarkLine) lines.push(benchmarkLine)
    const benchmarkEvidenceLine = formatBenchmarkEvidenceLine(source)
    if (benchmarkEvidenceLine) lines.push(benchmarkEvidenceLine)
    const benchmarkStateLine = formatBenchmarkStateLine(source)
    if (benchmarkStateLine) lines.push(benchmarkStateLine)
  }

  if (SURFACES.includes(command)) {
    lines.push(formatPathStateLine(command, source))
    lines.push(formatSurfaceCompactLine(command, source))
    const previewSource = firstDefined(source[`${command}_trade_intent_preview_source`], source.execution_projection_selected_preview_source)
    if (previewSource) {
      lines.push(`${command}_preview: source=${previewSource}`)
    }
    if (source.summary) {
      lines.push(`${command}_summary: summary="${source.summary}"`)
    }
    const surfaceSummary = formatSurfaceProjectionSummary(source, command)
    if (surfaceSummary) lines.push(surfaceSummary)
    const strategyLayerSummary = formatStrategyLayerLine(source)
    if (strategyLayerSummary) lines.push(strategyLayerSummary)

    const extracted = extractProjection(source)
    if (flags.executionPathwaysSummary || command === 'dispatch' || command === 'paper' || command === 'shadow' || command === 'live') {
      if (extracted.requestedPath && extracted.selectedPath) {
        lines.push(formatProjectionLine(source, extracted))
        lines.push(formatProjectionPreflightLine(extracted))
        lines.push(formatProjectionDetailsLine(extracted))
        lines.push(formatSelectedPathStateLine(extracted))
        lines.push(formatSelectedPreviewLine(extracted))
        lines.push(formatSelectedOpsLine(extracted))
        lines.push(formatExecutionProjectionSourceLine())
        lines.push(formatMicrostructureLabLine(source))
        lines.push(formatShadowArbitrageLine(source))
        const trail = formatProjectionTrail(source)
        if (trail && (command === 'paper' || command === 'shadow' || command === 'live')) {
          lines.push(trail)
        }
      }
    }

    if (flags.researchSummary || flags.executionPathwaysSummary) {
      const researchLine = formatResearchLine(source)
      if (researchLine) lines.push(researchLine)
      const researchOriginLine = formatResearchOriginLine(source)
      if (researchOriginLine) lines.push(researchOriginLine)
    }
    if (flags.researchSummary || flags.benchmarkSummary || flags.executionPathwaysSummary) {
      const benchmarkLine = formatBenchmarkLine(source)
      if (benchmarkLine) lines.push(benchmarkLine)
      const benchmarkEvidenceLine = formatBenchmarkEvidenceLine(source)
      if (benchmarkEvidenceLine) lines.push(benchmarkEvidenceLine)
      const benchmarkStateLine = formatBenchmarkStateLine(source)
      if (benchmarkStateLine) lines.push(benchmarkStateLine)
    }
  }

  if (command === 'run') {
    if (flags.artifactAuditSummary && source.artifact_audit) {
      lines.push(formatArtifactAuditLine(source.artifact_audit))
      lines.push(formatArtifactReadbackLine(source.artifact_readback))
    }
    if (flags.executionPathwaysSummary) {
      if (source.execution_pathways) {
        lines.push(`execution_pathways: ${formatExecutionPathwaysLine(source)}`)
      }
      if (source.execution_projection) {
        const extracted = extractProjection(source)
        lines.push(formatProjectionCompactLine(extracted))
        lines.push(formatProjectionLine(source, extracted))
        lines.push(formatProjectionPreflightLine(extracted))
        lines.push(formatProjectionDetailsLine(extracted))
        lines.push(formatSelectedPathStateLine(extracted))
        lines.push(formatSelectedPreviewLine(extracted))
        lines.push(formatSelectedOpsLine(extracted))
        lines.push(formatStrategyLayerLine(source, extracted))
        lines.push(formatExecutionProjectionSourceLine())
        lines.push(formatMicrostructureLabLine(source))
        lines.push(formatShadowArbitrageLine(source))
      }
    }
    if (flags.researchSummary || flags.executionPathwaysSummary) {
      const researchLine = formatResearchLine(source)
      if (researchLine) lines.push(researchLine)
      const researchOriginLine = formatResearchOriginLine(source)
      if (researchOriginLine) lines.push(researchOriginLine)
    }
    if (flags.researchSummary || flags.benchmarkSummary || flags.executionPathwaysSummary) {
      const benchmarkLine = formatBenchmarkLine(source)
      if (benchmarkLine) lines.push(benchmarkLine)
      const benchmarkEvidenceLine = formatBenchmarkEvidenceLine(source)
      if (benchmarkEvidenceLine) lines.push(benchmarkEvidenceLine)
      const benchmarkStateLine = formatBenchmarkStateLine(source)
      if (benchmarkStateLine) lines.push(benchmarkStateLine)
    }
    if (flags.executionReadinessSummary && source.execution_readiness) {
      lines.push(`execution_readiness: status=${source.execution_readiness.status ?? 'unknown'}`)
    }
  }

  if (command === 'runs') {
    const entries = asArray(payload?.runs)
    for (const entry of entries) {
      if (flags.artifactAuditSummary && entry.artifact_audit) {
        lines.push(`run ${entry.run_id} | ${formatArtifactAuditLine(entry.artifact_audit)}`)
      }
      if (flags.executionPathwaysSummary) {
        if (entry.execution_pathways) {
          lines.push(`run ${entry.run_id} | ${formatExecutionPathwaysLine(entry)}`)
        }
        const hasProjectionHints = entry.execution_projection
          || entry.execution_projection_requested_path
          || entry.execution_projection_selected_path
          || entry.execution_projection_verdict
        if (hasProjectionHints) {
          const extracted = extractProjection(entry)
          lines.push(`run ${entry.run_id} | ${formatProjectionLine(entry, extracted, { includeModeCount: false })}`)
          const projectionPreflight = formatProjectionPreflightLine(extracted)
          if (projectionPreflight) lines.push(`  ${projectionPreflight}`)
          const projectionDetails = formatProjectionDetailsLine(extracted)
          if (projectionDetails) lines.push(`  ${projectionDetails}`)
          lines.push(`  ${formatSelectedPathStateLine(extracted)}`)
          const selectedPreview = formatSelectedPreviewLine(extracted)
          if (selectedPreview) lines.push(`  ${selectedPreview}`)
          const selectedOps = formatSelectedOpsLine(extracted)
          if (selectedOps) lines.push(`  ${selectedOps}`)
          lines.push(`  ${formatExecutionProjectionSourceLine()}`)
          const microstructureLab = formatMicrostructureLabLine(entry)
          if (microstructureLab) lines.push(`  ${microstructureLab}`)
          const shadowArbitrage = formatShadowArbitrageLine(entry)
          if (shadowArbitrage) lines.push(`  ${shadowArbitrage}`)
          const trail = formatProjectionTrail(entry)
          if (trail) lines.push(`  ${trail}`)
        }
      }
    if (flags.researchSummary || flags.executionPathwaysSummary) {
      const researchLine = formatResearchLine(entry)
      if (researchLine) lines.push(researchLine)
      const researchOriginLine = formatResearchOriginLine(entry)
      if (researchOriginLine) lines.push(researchOriginLine)
    }
    if (flags.researchSummary || flags.benchmarkSummary || flags.executionPathwaysSummary) {
      const benchmarkLine = formatBenchmarkLine(entry)
      if (benchmarkLine) lines.push(benchmarkLine)
      const benchmarkEvidenceLine = formatBenchmarkEvidenceLine(entry)
      if (benchmarkEvidenceLine) lines.push(benchmarkEvidenceLine)
      const benchmarkStateLine = formatBenchmarkStateLine(entry)
      if (benchmarkStateLine) lines.push(benchmarkStateLine)
    }
  }
  }

  if (command === 'dispatch') {
    const payloadLine = `dispatch_preflight: status=${source.dispatch_status ?? 'unknown'}`
    lines.splice(1, 0, payloadLine)
  }

  if ((command === 'paper' || command === 'shadow' || command === 'live') && flags.executionPathwaysSummary) {
    const surfaceSummary = command === 'paper'
      ? `paper:ready|shadow:ready`
      : command === 'shadow'
        ? 'shadow:ready'
        : 'live:ready'
    lines.push(surfaceSummary)
  }

  if ((command === 'advise' || command === 'replay') && !flags.json) {
    lines.push(JSON.stringify({ ok: true }, null, 2))
  }

  return lines.filter(Boolean).join('\n')
}

async function makeRequest(baseUrl, method, pathname, body) {
  const url = new URL(pathname, baseUrl)
  if (body && method === 'GET') {
    for (const [key, value] of Object.entries(body)) {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value))
      }
    }
  }

  const response = await fetch(url, {
    method,
    headers: body && method !== 'GET' ? { 'content-type': 'application/json' } : undefined,
    body: body && method !== 'GET' ? JSON.stringify(body) : undefined,
  })
  const text = await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  return { ok: response.ok, status: response.status, data }
}

function buildRequestBody(command, flags) {
  if (command === 'advise') {
    const researchSignals = [...asArray(flags.researchSignals), ...asArray(flags.researchSignal)]
    const body = {}
    if (flags.marketId) body.market_id = flags.marketId
    if (flags.venue) body.venue = flags.venue
    if (researchSignals.length > 0) body.research_signals = researchSignals
    return body
  }

  if (command === 'replay' || SURFACES.includes(command)) {
    const body = {
      run_id: flags.runId,
    }
    if (command === 'live' && flags.executionMode) {
      body.execution_mode = flags.executionMode
    }
    return body
  }

  if (command === 'runs') {
    const query = {}
    if (flags.venue) query.venue = flags.venue
    if (flags.recommendation) query.recommendation = flags.recommendation
    if (flags.limit) query.limit = flags.limit
    return query
  }

  if (command === 'markets' || command === 'capabilities' || command === 'health') {
    const query = {}
    if (flags.venue) query.venue = flags.venue
    if (flags.marketId) query.market_id = flags.marketId
    if (flags.limit) query.limit = flags.limit
    if (flags.search) query.search = flags.search
    return query
  }

  return null
}

function buildPath(command, flags) {
  switch (command) {
    case 'advise':
      return '/api/v1/prediction-markets/advise'
    case 'replay':
      return '/api/v1/prediction-markets/replay'
    case 'run':
      return `/api/v1/prediction-markets/runs/${flags.runId ?? ''}`
    case 'runs':
      return '/api/v1/prediction-markets/runs'
    case 'dispatch':
    case 'paper':
    case 'shadow':
    case 'live':
      return `/api/v1/prediction-markets/runs/${flags.runId ?? ''}/${command}`
    case 'markets':
      return '/api/v1/prediction-markets/markets'
    case 'capabilities':
      return '/api/v1/prediction-markets/capabilities'
    case 'health':
      return '/api/v1/prediction-markets/health'
    default:
      return null
  }
}

async function main() {
  const parsed = parseArgs(process.argv)
  const { command, flags } = parsed

  if (!command) {
    console.error('Usage: mc-cli.cjs prediction-markets <command> [flags]')
    process.exitCode = 2
    return
  }

  const path = buildPath(command, flags)
  if (!path) {
    console.error(`Unsupported prediction-markets command: ${command}`)
    process.exitCode = 2
    return
  }

  const method = command === 'run' || command === 'runs' || command === 'markets' || command === 'capabilities' || command === 'health'
    ? 'GET'
    : command === 'replay'
      ? 'POST'
      : SURFACES.includes(command)
        ? 'POST'
        : 'POST'

  const requestBody = buildRequestBody(command, flags)
  const response = await makeRequest(flags.url, method, path, requestBody)
  const payload = response.data

  if (flags.json) {
    const json = {
      ok: response.ok,
      status: response.status,
      data: payload,
    }
    process.stdout.write(`${JSON.stringify(json, null, 2)}\n`)
    return
  }

  const text = formatCommandResponse(command, response, flags, requestBody)
  process.stdout.write(`${text}\n`)
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error))
  process.exitCode = 1
})
