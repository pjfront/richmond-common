/**
 * geo.ts — Client-side geographic utilities for district lookup.
 *
 * All computation happens in the browser. The user's address is sent
 * directly to the Census Bureau geocoder — our server never sees it.
 */

// ─── Types ──────────────────────────────────────────────────────────────────

export interface GeoJSONFeature {
  type: 'Feature'
  properties: Record<string, unknown>
  geometry: {
    type: 'Polygon' | 'MultiPolygon'
    coordinates: number[][][]  // Polygon: ring[] of [lng, lat]
  }
}

export interface GeoJSONCollection {
  type: 'FeatureCollection'
  features: GeoJSONFeature[]
}

export interface GeocodingResult {
  lat: number
  lng: number
  matchedAddress: string
}

export interface DistrictMatch {
  district: number
  population: number
}

export interface NeighborhoodMatch {
  name: string
  code: string
}

// ─── Census Geocoder (via API proxy) ────────────────────────────────────────
// Census API lacks CORS headers, so we proxy through /api/geocode.
// The proxy does not log or store the address — it passes straight through.
//
// The Census geocoder is strict about format. We normalize the input to
// maximize hit rate: auto-append "Richmond, CA", expand abbreviations,
// and retry with variations if the first attempt fails.

const RICHMOND_SUFFIXES = [
  ', Richmond, CA',
  ', Richmond, California',
]

// Common abbreviations the Census geocoder may not handle
const ABBREVIATIONS: [RegExp, string][] = [
  [/\bSt\b\.?(?!\w)/gi, 'Street'],
  [/\bAve\b\.?(?!\w)/gi, 'Avenue'],
  [/\bBlvd\b\.?(?!\w)/gi, 'Boulevard'],
  [/\bDr\b\.?(?!\w)/gi, 'Drive'],
  [/\bCt\b\.?(?!\w)/gi, 'Court'],
  [/\bPl\b\.?(?!\w)/gi, 'Place'],
  [/\bLn\b\.?(?!\w)/gi, 'Lane'],
  [/\bRd\b\.?(?!\w)/gi, 'Road'],
  [/\bPkwy\b\.?(?!\w)/gi, 'Parkway'],
  [/\bCir\b\.?(?!\w)/gi, 'Circle'],
  [/\bWy\b\.?(?!\w)/gi, 'Way'],
  [/\bHwy\b\.?(?!\w)/gi, 'Highway'],
]

function hasCity(input: string): boolean {
  const lower = input.toLowerCase()
  // "richmond" in a street name (e.g., "130 W Richmond Ave") doesn't count —
  // look for ", Richmond" or "Richmond, CA" patterns that indicate a city field
  const hasCityRichmond =
    /,\s*richmond/i.test(input) || /richmond\s*,\s*ca/i.test(input)
  return (
    hasCityRichmond ||
    lower.includes(', ca') ||
    lower.includes('california') ||
    /\b\d{5}\b/.test(input) // has a zip code
  )
}

function expandAbbreviations(input: string): string {
  let result = input
  for (const [pattern, replacement] of ABBREVIATIONS) {
    result = result.replace(pattern, replacement)
  }
  return result
}

function buildCandidates(raw: string): string[] {
  const trimmed = raw.trim().replace(/\s+/g, ' ')
  const candidates: string[] = []

  if (hasCity(trimmed)) {
    // User included city/zip — try as-is first, then with expanded abbreviations
    candidates.push(trimmed)
    const expanded = expandAbbreviations(trimmed)
    if (expanded !== trimmed) candidates.push(expanded)
  } else {
    // No city — append Richmond, CA and try variations
    for (const suffix of RICHMOND_SUFFIXES) {
      candidates.push(trimmed + suffix)
    }
    const expanded = expandAbbreviations(trimmed)
    if (expanded !== trimmed) {
      for (const suffix of RICHMOND_SUFFIXES) {
        candidates.push(expanded + suffix)
      }
    }
  }

  return candidates
}

async function tryGeocode(address: string): Promise<GeocodingResult | null> {
  const params = new URLSearchParams({ address })
  const res = await fetch(`/api/geocode?${params}`)
  if (!res.ok) return null

  const data = await res.json()
  const matches = data?.result?.addressMatches
  if (!matches || matches.length === 0) return null

  return {
    lng: matches[0].coordinates.x,
    lat: matches[0].coordinates.y,
    matchedAddress: matches[0].matchedAddress,
  }
}

export async function geocodeAddress(
  address: string,
): Promise<GeocodingResult> {
  const candidates = buildCandidates(address)

  for (const candidate of candidates) {
    const result = await tryGeocode(candidate)
    if (result) return result
  }

  throw new Error(
    'We couldn\u2019t find that address. Try something like "300 23rd St" \u2014 we\u2019ll add Richmond for you.',
  )
}

// ─── Point-in-Polygon (Ray Casting) ─────────────────────────────────────────
// Jordan curve theorem: cast a ray from the point, count edge crossings.
// Odd = inside. Handles multi-ring polygons (exterior + holes).

function pointInRing(
  lng: number,
  lat: number,
  ring: number[][],
): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1]
    const xj = ring[j][0], yj = ring[j][1]

    if (
      yi > lat !== yj > lat &&
      lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi
    ) {
      inside = !inside
    }
  }
  return inside
}

function pointInPolygon(
  lng: number,
  lat: number,
  coordinates: number[][][],
): boolean {
  // Ring 0 = exterior boundary, rings 1+ = holes
  if (!pointInRing(lng, lat, coordinates[0])) return false
  for (let i = 1; i < coordinates.length; i++) {
    if (pointInRing(lng, lat, coordinates[i])) return false // inside a hole
  }
  return true
}

// ─── District / Neighborhood Lookup ─────────────────────────────────────────

export function findDistrict(
  lat: number,
  lng: number,
  geojson: GeoJSONCollection,
): DistrictMatch | null {
  for (const feature of geojson.features) {
    if (pointInPolygon(lng, lat, feature.geometry.coordinates)) {
      return {
        district: feature.properties.district as number,
        population: feature.properties.population as number,
      }
    }
  }
  return null
}

export function findNeighborhood(
  lat: number,
  lng: number,
  geojson: GeoJSONCollection,
): NeighborhoodMatch | null {
  for (const feature of geojson.features) {
    if (pointInPolygon(lng, lat, feature.geometry.coordinates)) {
      return {
        name: feature.properties.name as string,
        code: feature.properties.code as string,
      }
    }
  }
  return null
}

// ─── GeoJSON Loader (lazy, cached) ──────────────────────────────────────────

let districtCache: GeoJSONCollection | null = null
let neighborhoodCache: GeoJSONCollection | null = null

export async function loadDistricts(): Promise<GeoJSONCollection> {
  if (districtCache) return districtCache
  const res = await fetch('/data/richmond-districts.geojson')
  districtCache = await res.json()
  return districtCache!
}

export async function loadNeighborhoods(): Promise<GeoJSONCollection> {
  if (neighborhoodCache) return neighborhoodCache
  const res = await fetch('/data/richmond-neighborhoods.geojson')
  neighborhoodCache = await res.json()
  return neighborhoodCache!
}
