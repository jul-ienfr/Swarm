import { randomUUID } from 'node:crypto'

import { NextRequest, NextResponse } from 'next/server'

import { requireRole } from '@/lib/auth'
import { readLimiter } from '@/lib/rate-limit'
import { logger } from '@/lib/logger'
import { ensurePredictionDashboardArbitragePolling } from '@/lib/prediction-markets/arbitrage-scanner'
import {
  buildPredictionDashboardVenueSnapshot,
  comparePredictionDashboardVenueSnapshots,
  ensurePredictionDashboardVenuePolling,
  formatPredictionDashboardEventAsSse,
  formatPredictionDashboardSseComment,
  getPredictionDashboardEventHistory,
  subscribePredictionDashboardEvents,
  type PredictionDashboardEvent,
  type PredictionDashboardVenueSnapshot,
} from '@/lib/prediction-markets/dashboard-events'
import { listPredictionMarketVenues, type PredictionMarketVenueId } from '@/lib/prediction-markets/venue-ops'

export const dynamic = 'force-dynamic'
export const revalidate = 0

type DashboardEventsMode = 'live' | 'replay'

type DashboardSseConnection = {
  write: (chunk: string) => void
  close: () => void
}

function parseMode(value: string | null): DashboardEventsMode {
  return value === 'replay' ? 'replay' : 'live'
}

function parseLimit(value: string | null, fallback: number): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback
  return Math.max(1, Math.min(250, Math.round(parsed)))
}

function resolveVenueFilter(value: string | null): PredictionMarketVenueId | 'all' {
  if (!value || value === 'all') return 'all'
  const knownVenues = new Set(listPredictionMarketVenues())
  if (!knownVenues.has(value as PredictionMarketVenueId)) {
    throw new Error(`Unsupported dashboard venue filter: ${value}`)
  }
  return value as PredictionMarketVenueId
}

function matchesVenueScope(eventVenue: string | null, venueFilter: PredictionMarketVenueId | 'all') {
  if (venueFilter === 'all') return true
  return eventVenue == null || eventVenue === 'all' || eventVenue === venueFilter
}

function materializeBootstrapEvent(input: Omit<PredictionDashboardEvent, 'event_id' | 'emitted_at'>): PredictionDashboardEvent {
  return {
    ...input,
    event_id: `dash_boot_${randomUUID()}`,
    emitted_at: new Date().toISOString(),
  }
}

function filterHistoryEvents(
  workspaceId: number,
  venueFilter: PredictionMarketVenueId | 'all',
  historyLimit: number,
) {
  return getPredictionDashboardEventHistory({
    workspaceId,
    venue: venueFilter,
    limit: historyLimit,
  })
}

function createSseConnection(controller: ReadableStreamDefaultController<Uint8Array>): DashboardSseConnection {
  const encoder = new TextEncoder()
  let closed = false

  return {
    write(chunk: string) {
      if (closed) return
      controller.enqueue(encoder.encode(chunk))
    },
    close() {
      if (closed) return
      closed = true
      controller.close()
    },
  }
}

async function buildBootstrap(
  workspaceId: number,
  venueFilter: PredictionMarketVenueId | 'all',
  snapshotLimit: number,
) {
  const venues = venueFilter === 'all' ? listPredictionMarketVenues() : [venueFilter]
  const snapshots: PredictionDashboardVenueSnapshot[] = []
  const events: PredictionDashboardEvent[] = []

  for (const venue of venues) {
    try {
      const snapshot = await buildPredictionDashboardVenueSnapshot({
        workspaceId,
        venue,
        limit: snapshotLimit,
      })
      snapshots.push(snapshot)
      events.push(
        ...comparePredictionDashboardVenueSnapshots(null, snapshot).map(materializeBootstrapEvent),
      )
    } catch (error) {
      events.push(
        materializeBootstrapEvent({
          type: 'runs_refresh_hint',
          severity: 'warn',
          workspace_id: workspaceId,
          venue,
          run_id: null,
          intent_id: null,
          source: 'system',
          summary: `Dashboard snapshot unavailable for ${venue}.`,
          payload: {
            error: error instanceof Error ? error.message : String(error),
          },
        }),
      )
    }
  }

  return { venues, snapshots, events }
}

export async function GET(request: NextRequest) {
  const auth = requireRole(request, 'viewer')
  if ('error' in auth) return NextResponse.json({ error: auth.error }, { status: auth.status })

  const rateCheck = readLimiter(request)
  if (rateCheck) return rateCheck

  const url = new URL(request.url)
  const mode = parseMode(url.searchParams.get('mode'))
  const historyLimit = parseLimit(url.searchParams.get('history_limit'), 50)
  const snapshotLimit = parseLimit(url.searchParams.get('snapshot_limit'), 25)
  const pollIntervalMs = parseLimit(url.searchParams.get('poll_interval_ms'), 5000)
  const heartbeatMs = parseLimit(url.searchParams.get('heartbeat_ms'), 15000)
  let venueFilter: PredictionMarketVenueId | 'all'

  try {
    venueFilter = resolveVenueFilter(url.searchParams.get('venue'))
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : 'Invalid dashboard venue filter',
      },
      { status: 400 },
    )
  }

  const workspaceId = auth.user.workspace_id ?? 1
  const activeVenues = venueFilter === 'all' ? listPredictionMarketVenues() : [venueFilter]
  let cleanup: Array<() => void> = []

  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      const stream = createSseConnection(controller)
      let bootstrapSnapshots: PredictionDashboardVenueSnapshot[] = []

      const writeEvent = (event: PredictionDashboardEvent) => {
        stream.write(formatPredictionDashboardEventAsSse(event))
      }

      const writeComment = (comment: string) => {
        stream.write(formatPredictionDashboardSseComment(comment))
      }

      try {
        writeComment(`prediction-markets dashboard events connected workspace=${workspaceId} mode=${mode}`)

        const bootstrap = await buildBootstrap(workspaceId, venueFilter, snapshotLimit)
        bootstrapSnapshots = bootstrap.snapshots

        for (const event of bootstrap.events) {
          writeEvent(event)
        }

        const history = filterHistoryEvents(workspaceId, venueFilter, historyLimit)
        for (const event of history) {
          if (matchesVenueScope(event.venue, venueFilter)) {
            writeEvent(event)
          }
        }

        if (mode === 'replay') {
          stream.close()
          return
        }

        for (const snapshot of bootstrapSnapshots) {
          cleanup.push(
            ensurePredictionDashboardVenuePolling({
              workspaceId,
              venue: snapshot.venue,
              limit: snapshotLimit,
              pollIntervalMs,
              initialSnapshot: snapshot,
            }),
          )
        }

        ensurePredictionDashboardArbitragePolling({ workspaceId })

        const unsubscribe = subscribePredictionDashboardEvents((event) => {
          if (event.workspace_id != null && event.workspace_id !== workspaceId) return
          if (!matchesVenueScope(event.venue, venueFilter)) return
          writeEvent(event)
        })
        cleanup.push(unsubscribe)

        const heartbeat = setInterval(() => {
          writeComment(`heartbeat workspace=${workspaceId} venues=${activeVenues.join(',')}`)
        }, heartbeatMs)
        cleanup.push(() => clearInterval(heartbeat))

        request.signal.addEventListener('abort', () => {
          for (const stop of cleanup.splice(0, cleanup.length)) {
            try {
              stop()
            } catch {
              // Best-effort cleanup.
            }
          }
          stream.close()
        })
      } catch (error) {
        logger.error({ err: error }, 'prediction dashboard SSE stream failed')
        writeComment(`stream error: ${error instanceof Error ? error.message : String(error)}`)
        for (const stop of cleanup.splice(0, cleanup.length)) {
          try {
            stop()
          } catch {
            // Best-effort cleanup.
          }
        }
        stream.close()
      }
    },
    cancel() {
      for (const stop of cleanup.splice(0, cleanup.length)) {
        try {
          stop()
        } catch {
          // Best-effort cleanup.
        }
      }
    },
  })

  return new Response(body, {
    status: 200,
    headers: {
      'content-type': 'text/event-stream; charset=utf-8',
      'cache-control': 'no-cache, no-transform',
      connection: 'keep-alive',
      'x-accel-buffering': 'no',
      'x-prediction-markets-api': 'v1',
    },
  })
}
