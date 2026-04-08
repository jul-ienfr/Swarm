import {
  capitalLedgerSnapshotSchema,
  type CapitalLedgerSnapshot,
  type PredictionMarketVenue,
} from '@/lib/prediction-markets/schemas'

export type CapitalLedgerPositionInput = {
  position_id?: string
  market_id?: string
  exposure_usd?: number
  notional_usd?: number
  collateral_locked?: number
  collateral_locked_usd?: number
  margin_locked_usd?: number
  unrealized_pnl_usd?: number
  status?: 'open' | 'closed'
}

export type CapitalLedgerSourceInput = {
  venue: PredictionMarketVenue
  captured_at?: string
  collateral_currency?: string
  cash_available?: number
  cash_available_usd?: number
  available_balance?: number
  free_collateral?: number
  balance?: number
  cash_locked?: number
  cash_locked_usd?: number
  reserved_balance?: number
  margin_locked?: number
  locked_collateral?: number
  withdrawable_amount?: number
  withdrawable_amount_usd?: number
  withdrawable_balance?: number
  open_exposure_usd?: number
  transfer_latency_estimate_ms?: number
  positions?: CapitalLedgerPositionInput[]
}

export type NormalizedCapitalLedgerPosition = {
  position_id: string
  market_id: string | null
  exposure_usd: number
  collateral_locked_usd: number
  unrealized_pnl_usd: number
  status: 'open' | 'closed'
}

export type CapitalLedgerTotals = {
  cash_total_usd: number
  exposure_total_usd: number
  locked_collateral_usd: number
  unrealized_pnl_usd: number
  open_positions: number
  utilization_ratio: number
}

export type CapitalLedgerNormalizationNoteCode =
  | 'alias_used'
  | 'derived_from_positions'
  | 'default_applied'
  | 'input_override'

export type CapitalLedgerNormalizationNote = {
  code: CapitalLedgerNormalizationNoteCode
  message: string
}

export type NormalizedCapitalLedgerResult = {
  snapshot: CapitalLedgerSnapshot
  totals: CapitalLedgerTotals
  positions: NormalizedCapitalLedgerPosition[]
  notes: CapitalLedgerNormalizationNote[]
}

const DEFAULT_TRANSFER_LATENCY_MS: Record<PredictionMarketVenue, number> = {
  polymarket: 15_000,
  kalshi: 60_000,
}

function roundUsd(value: number): number {
  return Number(value.toFixed(2))
}

function roundRatio(value: number): number {
  return Number(value.toFixed(6))
}

function finiteNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function firstFinite(entries: Array<[string, unknown]>): { value: number | undefined; source: string | null } {
  for (const [source, rawValue] of entries) {
    const value = finiteNumber(rawValue)
    if (value != null) {
      return { value, source }
    }
  }

  return { value: undefined, source: null }
}

function pushNote(
  notes: CapitalLedgerNormalizationNote[],
  code: CapitalLedgerNormalizationNoteCode,
  message: string,
) {
  notes.push({ code, message })
}

function normalizePosition(
  position: CapitalLedgerPositionInput,
  index: number,
): NormalizedCapitalLedgerPosition {
  const exposureUsd = Math.abs(
    finiteNumber(position.exposure_usd) ??
    finiteNumber(position.notional_usd) ??
    0,
  )
  const collateralLockedUsd = Math.max(
    finiteNumber(position.collateral_locked_usd) ??
    finiteNumber(position.collateral_locked) ??
    finiteNumber(position.margin_locked_usd) ??
    0,
    0,
  )
  const unrealizedPnlUsd = finiteNumber(position.unrealized_pnl_usd) ?? 0
  const status = position.status ?? (exposureUsd > 0 || collateralLockedUsd > 0 ? 'open' : 'closed')

  return {
    position_id: position.position_id ?? `position-${index + 1}`,
    market_id: position.market_id ?? null,
    exposure_usd: roundUsd(exposureUsd),
    collateral_locked_usd: roundUsd(collateralLockedUsd),
    unrealized_pnl_usd: roundUsd(unrealizedPnlUsd),
    status,
  }
}

export function computeCapitalLedgerTotals(input: {
  snapshot: CapitalLedgerSnapshot
  positions?: readonly NormalizedCapitalLedgerPosition[]
}): CapitalLedgerTotals {
  const positions = input.positions ?? []
  const openPositions = positions.filter((position) => position.status === 'open')
  const exposureFromPositions = roundUsd(
    openPositions.reduce((total, position) => total + Math.abs(position.exposure_usd), 0),
  )
  const lockedCollateralUsd = roundUsd(
    openPositions.reduce((total, position) => total + position.collateral_locked_usd, 0),
  )
  const unrealizedPnlUsd = roundUsd(
    openPositions.reduce((total, position) => total + position.unrealized_pnl_usd, 0),
  )
  const exposureTotalUsd = positions.length > 0
    ? exposureFromPositions
    : roundUsd(input.snapshot.open_exposure_usd)
  const cashTotalUsd = roundUsd(input.snapshot.cash_available + input.snapshot.cash_locked)
  const utilizationRatio = cashTotalUsd > 0
    ? roundRatio(exposureTotalUsd / cashTotalUsd)
    : exposureTotalUsd > 0
      ? 1
      : 0

  return {
    cash_total_usd: cashTotalUsd,
    exposure_total_usd: exposureTotalUsd,
    locked_collateral_usd: positions.length > 0
      ? lockedCollateralUsd
      : roundUsd(input.snapshot.cash_locked),
    unrealized_pnl_usd: unrealizedPnlUsd,
    open_positions: openPositions.length,
    utilization_ratio: utilizationRatio,
  }
}

export function normalizeCapitalLedgerSnapshot(input: CapitalLedgerSourceInput): NormalizedCapitalLedgerResult {
  const notes: CapitalLedgerNormalizationNote[] = []
  const positions = (input.positions ?? []).map(normalizePosition)
  const exposureFromPositions = roundUsd(
    positions
      .filter((position) => position.status === 'open')
      .reduce((total, position) => total + Math.abs(position.exposure_usd), 0),
  )
  const lockedFromPositions = roundUsd(
    positions
      .filter((position) => position.status === 'open')
      .reduce((total, position) => total + position.collateral_locked_usd, 0),
  )

  const cashAvailableEntry = firstFinite([
    ['cash_available', input.cash_available],
    ['cash_available_usd', input.cash_available_usd],
    ['available_balance', input.available_balance],
    ['free_collateral', input.free_collateral],
    ['balance', input.balance],
  ])
  const cashLockedEntry = firstFinite([
    ['cash_locked', input.cash_locked],
    ['cash_locked_usd', input.cash_locked_usd],
    ['reserved_balance', input.reserved_balance],
    ['margin_locked', input.margin_locked],
    ['locked_collateral', input.locked_collateral],
  ])
  const withdrawableEntry = firstFinite([
    ['withdrawable_amount', input.withdrawable_amount],
    ['withdrawable_amount_usd', input.withdrawable_amount_usd],
    ['withdrawable_balance', input.withdrawable_balance],
  ])
  const exposureEntry = firstFinite([
    ['open_exposure_usd', input.open_exposure_usd],
  ])
  const transferLatencyEntry = firstFinite([
    ['transfer_latency_estimate_ms', input.transfer_latency_estimate_ms],
  ])

  if (cashAvailableEntry.source && cashAvailableEntry.source !== 'cash_available') {
    pushNote(notes, 'alias_used', `cash_available normalized from ${cashAvailableEntry.source}.`)
  }

  if (cashLockedEntry.source && cashLockedEntry.source !== 'cash_locked') {
    pushNote(notes, 'alias_used', `cash_locked normalized from ${cashLockedEntry.source}.`)
  }

  if (withdrawableEntry.source && withdrawableEntry.source !== 'withdrawable_amount') {
    pushNote(notes, 'alias_used', `withdrawable_amount normalized from ${withdrawableEntry.source}.`)
  }

  const cashAvailable = roundUsd(Math.max(cashAvailableEntry.value ?? 0, 0))
  let cashLocked = cashLockedEntry.value
  if (cashLocked == null && lockedFromPositions > 0) {
    cashLocked = lockedFromPositions
    pushNote(notes, 'derived_from_positions', 'cash_locked was derived from open position collateral.')
  }

  const normalizedCashLocked = roundUsd(Math.max(cashLocked ?? 0, 0))

  let openExposureUsd = exposureEntry.value
  if (openExposureUsd == null) {
    openExposureUsd = exposureFromPositions
    pushNote(notes, 'derived_from_positions', 'open_exposure_usd was derived from open positions.')
  } else if (positions.length > 0 && Math.abs(openExposureUsd - exposureFromPositions) > 0.01) {
    pushNote(notes, 'input_override', 'open_exposure_usd input overrides the exposure derived from positions.')
  }

  let withdrawableAmount = withdrawableEntry.value
  if (withdrawableAmount == null) {
    withdrawableAmount = cashAvailable
    pushNote(notes, 'default_applied', 'withdrawable_amount defaulted to cash_available.')
  }

  let transferLatencyEstimateMs = transferLatencyEntry.value
  if (transferLatencyEstimateMs == null) {
    transferLatencyEstimateMs = DEFAULT_TRANSFER_LATENCY_MS[input.venue]
    pushNote(
      notes,
      'default_applied',
      `transfer_latency_estimate_ms defaulted for ${input.venue}.`,
    )
  }

  const snapshot = capitalLedgerSnapshotSchema.parse({
    venue: input.venue,
    captured_at: input.captured_at ?? new Date().toISOString(),
    collateral_currency: input.collateral_currency ?? 'USD',
    cash_available: cashAvailable,
    cash_locked: normalizedCashLocked,
    open_exposure_usd: roundUsd(Math.max(openExposureUsd ?? 0, 0)),
    withdrawable_amount: roundUsd(Math.max(withdrawableAmount, 0)),
    transfer_latency_estimate_ms: Math.max(Math.round(transferLatencyEstimateMs), 0),
  })

  return {
    snapshot,
    totals: computeCapitalLedgerTotals({
      snapshot,
      positions,
    }),
    positions,
    notes,
  }
}
