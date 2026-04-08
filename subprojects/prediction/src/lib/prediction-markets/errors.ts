import { ZodError } from 'zod'

export class PredictionMarketsError extends Error {
  status: number
  code: string

  constructor(message: string, options?: { status?: number; code?: string }) {
    super(message)
    this.name = 'PredictionMarketsError'
    this.status = options?.status ?? 500
    this.code = options?.code ?? 'prediction_markets_error'
  }
}

export function toPredictionMarketsErrorResponse(
  error: unknown,
  fallbackMessage: string,
): { status: number; body: { error: string; code?: string; details?: unknown } } {
  if (error instanceof PredictionMarketsError) {
    return {
      status: error.status,
      body: {
        error: error.message,
        code: error.code,
      },
    }
  }

  if (error instanceof ZodError) {
    return {
      status: 400,
      body: {
        error: 'Invalid prediction markets request',
        code: 'invalid_request',
        details: error.flatten(),
      },
    }
  }

  return {
    status: 500,
    body: {
      error: error instanceof Error ? error.message : fallbackMessage,
      code: 'internal_error',
    },
  }
}
