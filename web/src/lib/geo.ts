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

export async function geocodeAddress(
  address: string,
): Promise<GeocodingResult> {
  const params = new URLSearchParams({ address })

  const res = await fetch(`/api/geocode?${params}`)
  if (!res.ok) {
    throw new Error('Address lookup service is temporarily unavailable. Please try again.')
  }

  const data = await res.json()
  const matches = data?.result?.addressMatches
  if (!matches || matches.length === 0) {
    throw new Error(
      'Address not found. Try the full format: "123 Main St, Richmond, CA 94801"',
    )
  }

  const match = matches[0]
  return {
    lng: match.coordinates.x,
    lat: match.coordinates.y,
    matchedAddress: match.matchedAddress,
  }
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
