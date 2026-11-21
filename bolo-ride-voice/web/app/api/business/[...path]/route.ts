import { NextResponse } from 'next/server'

const allowedRoutes = [
  { method: 'POST', pattern: /^fare-estimates$/ },
  { method: 'POST', pattern: /^bookings\/validate$/ },
  { method: 'POST', pattern: /^bookings$/ },
  { method: 'GET', pattern: /^bookings\/[0-9a-f-]{36}$/i },
  { method: 'POST', pattern: /^bookings\/[0-9a-f-]{36}\/cancel$/i },
  { method: 'POST', pattern: /^bookings\/[0-9a-f-]{36}\/simulate\/driver$/i },
  { method: 'POST', pattern: /^bookings\/[0-9a-f-]{36}\/simulate\/complete$/i },
  { method: 'POST', pattern: /^payment-orders$/ },
  { method: 'GET', pattern: /^payments\/[0-9a-f-]{36}$/i },
  { method: 'POST', pattern: /^payments\/[0-9a-f-]{36}\/simulate-result$/i },
  { method: 'POST', pattern: /^payments\/[0-9a-f-]{36}\/verify$/i },
] as const

type RouteContext = { params: Promise<{ path: string[] }> }

async function proxy(request: Request, context: RouteContext) {
  const { path } = await context.params
  const requestedPath = path.join('/')
  if (!allowedRoutes.some((route) => route.method === request.method && route.pattern.test(requestedPath))) {
    return NextResponse.json({ detail: 'Business API route not found.' }, { status: 404 })
  }

  const businessApiUrl = process.env.BUSINESS_API_URL?.trim().replace(/\/+$/, '')
  const apiKey = process.env.BUSINESS_API_KEY
  if (!businessApiUrl || !apiKey) {
    return NextResponse.json({ detail: 'Business API proxy is not configured on the server.' }, { status: 503 })
  }

  const headers = new Headers({ 'X-API-Key': apiKey })
  let body: string | undefined
  if (request.method !== 'GET') {
    const contentType = request.headers.get('content-type') ?? ''
    if (!contentType.toLowerCase().includes('application/json')) {
      return NextResponse.json({ detail: 'Expected a JSON request body.' }, { status: 415 })
    }
    body = await request.text()
    headers.set('Content-Type', 'application/json')
  }

  try {
    const upstream = await fetch(`${businessApiUrl}/v1/${requestedPath}`, {
      method: request.method,
      headers,
      body,
      cache: 'no-store',
      signal: AbortSignal.timeout(10_000),
    })
    const responseBody = await upstream.text()
    return new Response(responseBody, {
      status: upstream.status,
      headers: { 'Content-Type': upstream.headers.get('content-type') ?? 'application/json' },
    })
  } catch (error) {
    console.error('Business API proxy request failed:', error)
    return NextResponse.json({ detail: 'The business service is unavailable. Please try again.' }, { status: 502 })
  }
}

export const GET = proxy
export const POST = proxy
