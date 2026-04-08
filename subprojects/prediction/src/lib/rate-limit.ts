import { type NextRequest, NextResponse } from 'next/server'

export function readLimiter(_request: NextRequest): NextResponse | null {
  return null
}

export function heavyLimiter(_request: NextRequest): NextResponse | null {
  return null
}
