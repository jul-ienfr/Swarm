import { NextResponse, type NextRequest } from 'next/server'
import { type z } from 'zod'

type ValidationSuccess<T> = {
  data: T
}

type ValidationFailure = {
  error: Response
}

export async function validateBody<TSchema extends z.ZodTypeAny>(
  request: NextRequest,
  schema: TSchema,
): Promise<ValidationSuccess<z.output<TSchema>> | ValidationFailure> {
  try {
    const body = await request.json()
    const parsed = schema.safeParse(body)

    if (!parsed.success) {
      return {
        error: NextResponse.json(
          {
            error: 'Invalid request body',
            issues: parsed.error.flatten(),
          },
          { status: 400 },
        ),
      }
    }

    return { data: parsed.data }
  } catch (error) {
    return {
      error: NextResponse.json(
        {
          error: error instanceof Error ? error.message : 'Invalid request body',
        },
        { status: 400 },
      ),
    }
  }
}
