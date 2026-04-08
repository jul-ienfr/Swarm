import { type NextRequest } from 'next/server'

export type AuthenticatedUser = {
  workspace_id: number
  username: string
  role: string
}

const ROLE_RANK: Record<string, number> = {
  viewer: 1,
  operator: 2,
  admin: 3,
}

function getHeader(request: NextRequest, key: string): string | null {
  try {
    return request.headers.get(key)
  } catch {
    return null
  }
}

function resolveWorkspaceId(request: NextRequest): number {
  const candidates = [
    getHeader(request, 'x-prediction-workspace-id'),
    getHeader(request, 'x-workspace-id'),
  ]

  for (const candidate of candidates) {
    const parsed = Number(candidate)
    if (Number.isFinite(parsed) && parsed > 0) {
      return Math.round(parsed)
    }
  }

  return 1
}

function resolveUsername(request: NextRequest): string {
  const candidates = [
    getHeader(request, 'x-prediction-actor'),
    getHeader(request, 'x-dashboard-actor'),
    getHeader(request, 'x-operator-name'),
    getHeader(request, 'x-user'),
  ]

  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim().length > 0) {
      return candidate.trim()
    }
  }

  return 'local-operator'
}

function resolveRole(request: NextRequest, fallbackRole: string): string {
  const candidates = [
    getHeader(request, 'x-prediction-role'),
    getHeader(request, 'x-dashboard-role'),
    getHeader(request, 'x-role'),
  ]

  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim().length > 0) {
      return candidate.trim()
    }
  }

  return fallbackRole
}

export function requireRole(
  request: NextRequest,
  role: string,
): { user: AuthenticatedUser } | { error: string; status: number } {
  const resolvedRole = resolveRole(request, role)
  const requestedRank = ROLE_RANK[role] ?? Number.MAX_SAFE_INTEGER
  const resolvedRank = ROLE_RANK[resolvedRole] ?? 0

  if (resolvedRank < requestedRank) {
    return {
      error: `Forbidden: ${resolvedRole} cannot access ${role} route`,
      status: 403,
    }
  }

  return {
    user: {
      workspace_id: resolveWorkspaceId(request),
      username: resolveUsername(request),
      role: resolvedRole,
    },
  }
}
