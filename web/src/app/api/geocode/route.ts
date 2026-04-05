import { NextRequest, NextResponse } from 'next/server'

/**
 * Thin proxy for the Census Bureau Geocoder.
 *
 * Why: The Census API doesn't set CORS headers, so browser-side fetch fails.
 * This route forwards the request server-side. We do not log, store, or
 * inspect the address — it passes straight through to Census and back.
 */

const CENSUS_URL =
  'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress'

export async function GET(request: NextRequest) {
  const address = request.nextUrl.searchParams.get('address')
  if (!address) {
    return NextResponse.json(
      { error: 'Missing address parameter' },
      { status: 400 },
    )
  }

  const params = new URLSearchParams({
    address,
    benchmark: 'Public_AR_Current',
    format: 'json',
  })

  try {
    const res = await fetch(`${CENSUS_URL}?${params}`, {
      next: { revalidate: 0 }, // no caching of address lookups
    })

    if (!res.ok) {
      return NextResponse.json(
        { error: 'Census geocoding service unavailable' },
        { status: 502 },
      )
    }

    const data = await res.json()
    return NextResponse.json(data)
  } catch {
    return NextResponse.json(
      { error: 'Census geocoding service unavailable' },
      { status: 502 },
    )
  }
}
