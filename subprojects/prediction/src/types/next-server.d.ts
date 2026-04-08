declare module 'next/server' {
  export class NextRequest extends Request {
    readonly nextUrl: URL
    constructor(input: string | URL | Request, init?: RequestInit & { nextUrl?: URL })
  }

  export class NextResponse extends Response {
    static json(data: unknown, init?: ResponseInit): NextResponse
  }
}
