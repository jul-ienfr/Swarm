import type {
  PredictionMarketVenue,
  PredictionMarketVenueType,
  VenueCapabilities,
} from '@/lib/prediction-markets/schemas'

export type PredictionMarketComplianceMode = 'discovery' | 'paper' | 'shadow' | 'live'
export type PredictionMarketComplianceStatus = 'authorized' | 'degraded' | 'blocked'
export type PredictionMarketComplianceSeverity = 'warning' | 'error'
export type PredictionMarketComplianceReasonCode =
  | 'experimental_venue_type'
  | 'reference_only_venue_type'
  | 'discovery_not_supported'
  | 'metadata_not_supported'
  | 'paper_mode_native_unavailable'
  | 'orderbook_not_supported'
  | 'trade_history_not_supported'
  | 'execution_not_supported'
  | 'manual_review_before_live'
  | 'read_only_automation_constraint'
  | 'jurisdiction_restricted'
  | 'jurisdiction_unknown'
  | 'account_type_not_ready_for_shadow'
  | 'account_type_not_ready_for_live'
  | 'kyc_not_approved'
  | 'api_key_missing'
  | 'trading_disabled'
  | 'manual_review_required'
  | 'mode_downgraded'

export type PredictionMarketComplianceReason = {
  code: PredictionMarketComplianceReasonCode
  severity: PredictionMarketComplianceSeverity
  message: string
}

export type PredictionMarketJurisdictionStatus = 'allowed' | 'restricted' | 'unknown'
export type PredictionMarketComplianceAccountType = 'viewer' | 'paper' | 'shadow' | 'trading' | string
export type PredictionMarketComplianceKycStatus = 'approved' | 'pending' | 'rejected' | 'unknown' | string

export type PredictionMarketComplianceCapabilities = Partial<Pick<
  VenueCapabilities,
  | 'supports_discovery'
  | 'supports_metadata'
  | 'supports_orderbook'
  | 'supports_trades'
  | 'supports_execution'
  | 'supports_paper_mode'
  | 'automation_constraints'
>>

export type PredictionMarketComplianceInput = {
  venue: PredictionMarketVenue
  venue_type: PredictionMarketVenueType
  mode: PredictionMarketComplianceMode
  capabilities?: PredictionMarketComplianceCapabilities
  jurisdiction?: string
  account_type?: PredictionMarketComplianceAccountType
  kyc_status?: PredictionMarketComplianceKycStatus
  api_key_present?: boolean
  trading_enabled?: boolean
  manual_review_required?: boolean
}

export type PredictionMarketAccountReadiness = {
  jurisdiction_status: PredictionMarketJurisdictionStatus
  account_type: PredictionMarketComplianceAccountType
  kyc_status: PredictionMarketComplianceKycStatus
  api_key_present: boolean
  trading_enabled: boolean
  manual_review_required: boolean
  ready_for_paper: boolean
  ready_for_shadow: boolean
  ready_for_live: boolean
}

export type PredictionMarketComplianceDecision = {
  venue: PredictionMarketVenue
  venue_type: PredictionMarketVenueType
  requested_mode: PredictionMarketComplianceMode
  effective_mode: PredictionMarketComplianceMode
  status: PredictionMarketComplianceStatus
  allowed: boolean
  summary: string
  reasons: PredictionMarketComplianceReason[]
  account_readiness: PredictionMarketAccountReadiness
}

export type PredictionMarketComplianceMatrix = {
  venue: PredictionMarketVenue
  venue_type: PredictionMarketVenueType
  highest_authorized_mode: PredictionMarketComplianceMode | null
  account_readiness: PredictionMarketAccountReadiness
  decisions: Record<PredictionMarketComplianceMode, PredictionMarketComplianceDecision>
}

function pushReason(
  reasons: PredictionMarketComplianceReason[],
  code: PredictionMarketComplianceReasonCode,
  severity: PredictionMarketComplianceSeverity,
  message: string,
) {
  reasons.push({ code, severity, message })
}

function normalizeConstraints(constraints: string[] | undefined): string[] {
  return (constraints ?? [])
    .map((constraint) => constraint.trim().toLowerCase())
    .filter((constraint) => constraint.length > 0)
}

function normalizeJurisdictionStatus(jurisdiction: string | undefined): PredictionMarketJurisdictionStatus {
  const normalized = jurisdiction?.trim().toLowerCase()
  if (!normalized) return 'unknown'
  if (['restricted', 'blocked', 'forbidden', 'unavailable'].includes(normalized)) return 'restricted'
  return 'allowed'
}

function buildAccountReadiness(input: PredictionMarketComplianceInput): PredictionMarketAccountReadiness {
  const jurisdictionStatus = normalizeJurisdictionStatus(input.jurisdiction)
  const accountType = input.account_type ?? 'viewer'
  const kycStatus = input.kyc_status ?? 'unknown'
  const apiKeyPresent = input.api_key_present === true
  const tradingEnabled = input.trading_enabled !== false
  const manualReviewRequired = input.manual_review_required === true
  const kycApproved = String(kycStatus).toLowerCase() === 'approved'
  const shadowAccount = accountType === 'shadow' || accountType === 'trading'
  const liveAccount = accountType === 'trading'

  const readyForPaper = jurisdictionStatus !== 'restricted'
  const readyForShadow = jurisdictionStatus === 'allowed' &&
    shadowAccount &&
    kycApproved &&
    apiKeyPresent &&
    tradingEnabled
  const readyForLive = jurisdictionStatus === 'allowed' &&
    liveAccount &&
    kycApproved &&
    apiKeyPresent &&
    tradingEnabled &&
    !manualReviewRequired

  return {
    jurisdiction_status: jurisdictionStatus,
    account_type: accountType,
    kyc_status: kycStatus,
    api_key_present: apiKeyPresent,
    trading_enabled: tradingEnabled,
    manual_review_required: manualReviewRequired,
    ready_for_paper: readyForPaper,
    ready_for_shadow: readyForShadow,
    ready_for_live: readyForLive,
  }
}

function summarizeDecision(input: {
  mode: PredictionMarketComplianceMode
  status: PredictionMarketComplianceStatus
  effectiveMode: PredictionMarketComplianceMode
  reasons: PredictionMarketComplianceReason[]
}): string {
  const label = `${input.mode[0].toUpperCase()}${input.mode.slice(1)}`

  if (input.status === 'authorized') {
    return `${label} mode is authorized.`
  }

  if (input.status === 'blocked') {
    return `${label} mode is blocked: ${input.reasons[0]?.message ?? 'constraints prevent this mode.'}`
  }

  const firstReason = input.reasons[0]?.message ?? 'constraints require a safer operating mode.'
  return `${label} mode is degraded to ${input.effectiveMode}: ${firstReason}`
}

function addModeDowngradeReason(
  reasons: PredictionMarketComplianceReason[],
  requestedMode: PredictionMarketComplianceMode,
  effectiveMode: PredictionMarketComplianceMode,
) {
  pushReason(
    reasons,
    'mode_downgraded',
    'warning',
    `${requestedMode} mode was downgraded to ${effectiveMode}.`,
  )
}

function buildDecision(input: PredictionMarketComplianceInput): PredictionMarketComplianceDecision {
  const reasons: PredictionMarketComplianceReason[] = []
  const capabilities = input.capabilities ?? {}
  const constraints = normalizeConstraints(capabilities.automation_constraints)
  const readiness = buildAccountReadiness(input)

  const discoverySupported = capabilities.supports_discovery !== false
  const metadataSupported = capabilities.supports_metadata !== false
  const orderbookSupported = capabilities.supports_orderbook !== false
  const tradesSupported = capabilities.supports_trades !== false
  const executionSupported = capabilities.supports_execution === true
  const nativePaperSupported = capabilities.supports_paper_mode
  const readOnlyConstraint = constraints.some((constraint) =>
    constraint.includes('read-only') || constraint.includes('advisory mode only'),
  )
  const manualReviewBeforeLive = constraints.some((constraint) =>
    constraint.includes('manual review') && constraint.includes('live'),
  )

  let effectiveMode = input.mode
  let status: PredictionMarketComplianceStatus = 'authorized'
  let allowed = true

  const downgrade = (nextMode: PredictionMarketComplianceMode | null) => {
    if (!nextMode) {
      status = 'blocked'
      allowed = false
      effectiveMode = input.mode
      return
    }

    status = 'degraded'
    effectiveMode = nextMode
    allowed = true
    addModeDowngradeReason(reasons, input.mode, nextMode)
  }

  if (!discoverySupported) {
    pushReason(
      reasons,
      'discovery_not_supported',
      'error',
      `Discovery support is missing on ${input.venue}.`,
    )
    if (input.mode === 'discovery') {
      status = 'blocked'
      allowed = false
    } else {
      downgrade(null)
    }
  }

  if (allowed && input.mode !== 'discovery' && !metadataSupported) {
    pushReason(
      reasons,
      'metadata_not_supported',
      'error',
      `Metadata support is missing on ${input.venue}.`,
    )
    downgrade(discoverySupported ? 'discovery' : null)
  }

  if (allowed && input.venue_type === 'reference-only' && (input.mode === 'shadow' || input.mode === 'live')) {
    pushReason(
      reasons,
      'reference_only_venue_type',
      'warning',
      `${input.venue} is reference-only and cannot be used beyond paper mode.`,
    )
    downgrade('paper')
  }

  if (allowed && input.venue_type === 'experimental' && (input.mode === 'shadow' || input.mode === 'live')) {
    pushReason(
      reasons,
      'experimental_venue_type',
      'warning',
      `${input.venue} is experimental and should not be trusted beyond paper mode yet.`,
    )
    downgrade('paper')
  }

  if (allowed && readOnlyConstraint && input.mode !== 'discovery' && input.mode !== 'paper') {
    pushReason(
      reasons,
      'read_only_automation_constraint',
      'warning',
      `${input.venue} is constrained to read-only advisory use.`,
    )
    downgrade('paper')
  }

  if (allowed && effectiveMode === 'paper' && input.mode === 'paper' && nativePaperSupported === false) {
    pushReason(
      reasons,
      'paper_mode_native_unavailable',
      'warning',
      `Paper mode is degraded because ${input.venue} has no native paper support.`,
    )
    status = 'degraded'
  }

  if (allowed && (effectiveMode === 'shadow' || effectiveMode === 'live') && !orderbookSupported) {
    pushReason(
      reasons,
      'orderbook_not_supported',
      'warning',
      `${input.mode} mode requires order book support on ${input.venue}.`,
    )
    downgrade('paper')
  }

  if (allowed && (effectiveMode === 'shadow' || effectiveMode === 'live') && !tradesSupported) {
    pushReason(
      reasons,
      'trade_history_not_supported',
      'warning',
      `${input.mode} mode requires trade history support on ${input.venue}.`,
    )
    downgrade('paper')
  }

  if (allowed && effectiveMode === 'live' && !executionSupported) {
    pushReason(
      reasons,
      'execution_not_supported',
      'warning',
      `Live mode is degraded to shadow because execution is not supported on ${input.venue}.`,
    )
    downgrade('shadow')
  }

  if (allowed && effectiveMode === 'live' && manualReviewBeforeLive) {
    pushReason(
      reasons,
      'manual_review_before_live',
      'warning',
      `Live mode is degraded to shadow because manual review before execution is allowed.`,
    )
    downgrade('shadow')
  }

  if (allowed && readiness.jurisdiction_status === 'restricted' && (effectiveMode === 'shadow' || effectiveMode === 'live')) {
    pushReason(
      reasons,
      'jurisdiction_restricted',
      'warning',
      `Jurisdiction is restricted for ${input.venue}, so only paper mode remains allowed.`,
    )
    downgrade('paper')
  }

  if (allowed && effectiveMode === 'live' && readiness.manual_review_required) {
    pushReason(
      reasons,
      'manual_review_required',
      'warning',
      'Live mode is degraded to shadow because upstream manual review is still required.',
    )
    downgrade('shadow')
  }

  if (allowed && input.mode === 'shadow' && effectiveMode === 'shadow' && !readiness.ready_for_shadow) {
    if (readiness.account_type !== 'shadow' && readiness.account_type !== 'trading') {
      pushReason(
        reasons,
        'account_type_not_ready_for_shadow',
        'warning',
        `Account type ${readiness.account_type} is not ready for shadow mode.`,
      )
    }
    if (!readiness.api_key_present) {
      pushReason(
        reasons,
        'api_key_missing',
        'warning',
        'API key is missing for shadow mode.',
      )
    }
    if (!readiness.trading_enabled) {
      pushReason(
        reasons,
        'trading_disabled',
        'warning',
        'Trading is disabled for shadow mode.',
      )
    }
    if (String(readiness.kyc_status).toLowerCase() !== 'approved') {
      pushReason(
        reasons,
        'kyc_not_approved',
        'warning',
        'KYC is not approved for shadow mode.',
      )
    }
    if (reasons.length > 0) {
      downgrade('paper')
    }
  }

  if (allowed && input.mode === 'live' && effectiveMode === 'live' && !readiness.ready_for_live) {
    if (reasons.length === 0) {
      if (readiness.account_type !== 'trading') {
        pushReason(
          reasons,
          'account_type_not_ready_for_live',
          'warning',
          `Account type ${readiness.account_type} is not ready for live mode.`,
        )
      } else if (!readiness.api_key_present) {
        pushReason(
          reasons,
          'api_key_missing',
          'warning',
          'API key is missing for live mode.',
        )
      } else if (!readiness.trading_enabled) {
        pushReason(
          reasons,
          'trading_disabled',
          'warning',
          'Trading is disabled for live mode.',
        )
      } else if (String(readiness.kyc_status).toLowerCase() !== 'approved') {
        pushReason(
          reasons,
          'kyc_not_approved',
          'warning',
          'KYC is not approved for live mode.',
        )
      } else if (readiness.jurisdiction_status === 'unknown') {
        pushReason(
          reasons,
          'jurisdiction_unknown',
          'warning',
          'Jurisdiction status is unknown for live mode.',
        )
      }
      if (reasons.length > 0) {
        downgrade('shadow')
      }
    }
  }

  const summary = summarizeDecision({
    mode: input.mode,
    status,
    effectiveMode,
    reasons,
  })

  return {
    venue: input.venue,
    venue_type: input.venue_type,
    requested_mode: input.mode,
    effective_mode: effectiveMode,
    status,
    allowed,
    summary,
    reasons,
    account_readiness: readiness,
  }
}

export function evaluatePredictionMarketCompliance(
  input: PredictionMarketComplianceInput,
): PredictionMarketComplianceDecision {
  return buildDecision(input)
}

export function evaluatePredictionMarketComplianceMatrix(
  input: Omit<PredictionMarketComplianceInput, 'mode'>,
): PredictionMarketComplianceMatrix {
  const decisions = {
    discovery: buildDecision({ ...input, mode: 'discovery' }),
    paper: buildDecision({ ...input, mode: 'paper' }),
    shadow: buildDecision({ ...input, mode: 'shadow' }),
    live: buildDecision({ ...input, mode: 'live' }),
  }

  const highestAuthorizedMode = (['live', 'shadow', 'paper', 'discovery'] as const).find((mode) =>
    decisions[mode].allowed && decisions[mode].status !== 'blocked',
  ) ?? null

  return {
    venue: input.venue,
    venue_type: input.venue_type,
    highest_authorized_mode: highestAuthorizedMode,
    account_readiness: decisions.live.account_readiness,
    decisions,
  }
}
