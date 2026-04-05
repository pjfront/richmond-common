/**
 * extract-districts.ts
 *
 * One-time extraction of Richmond council district and neighborhood boundaries
 * from the city's official ArcGIS redistricting map.
 *
 * Source: NDCresearch ArcGIS web map (2021 Redistricting, Adopted Map 201)
 * Run: npx tsx scripts/extract-districts.ts
 *
 * Outputs:
 *   web/public/data/richmond-districts.geojson   (6 council district polygons)
 *   web/public/data/richmond-neighborhoods.geojson (36 neighborhood polygons)
 *
 * Boundaries change only after decennial redistricting (~2031).
 */

import { writeFileSync, mkdirSync } from 'fs'
import { join } from 'path'

const WEB_MAP_ID = 'b6cbce3a7fca4aa890af2c01faa4d938'
const PORTAL = 'https://NDCresearch.maps.arcgis.com'
const DATA_URL = `${PORTAL}/sharing/rest/content/items/${WEB_MAP_ID}/data?f=json`

const OUTPUT_DIR = join(__dirname, '..', 'web', 'public', 'data')

// ─── Reprojection: EPSG:3857 (Web Mercator) → EPSG:4326 (WGS84) ────────────
// Pure math — no library needed.

const EARTH_RADIUS = 6378137 // meters (WGS84 semi-major axis)
const MAX_EXTENT = Math.PI * EARTH_RADIUS // ~20037508.34

function webMercatorToWgs84(x: number, y: number): [number, number] {
  const lng = (x / MAX_EXTENT) * 180
  const lat =
    (Math.atan(Math.exp((y / MAX_EXTENT) * Math.PI)) * 360) / Math.PI - 90
  return [
    Math.round(lng * 1_000_000) / 1_000_000,
    Math.round(lat * 1_000_000) / 1_000_000,
  ]
}

function reprojectRings(
  rings: number[][][],
): [number, number][][] {
  return rings.map((ring) => ring.map(([x, y]) => webMercatorToWgs84(x, y)))
}

// ─── GeoJSON construction ───────────────────────────────────────────────────

interface ArcGISFeature {
  attributes: Record<string, unknown>
  geometry: { rings: number[][][] }
}

interface GeoJSONFeature {
  type: 'Feature'
  properties: Record<string, unknown>
  geometry: {
    type: 'Polygon'
    coordinates: [number, number][][]
  }
}

interface GeoJSONCollection {
  type: 'FeatureCollection'
  features: GeoJSONFeature[]
}

// Compute signed area of a ring (Shoelace formula).
// Positive = counter-clockwise (exterior in GeoJSON), negative = clockwise (hole).
function ringArea(ring: number[][]): number {
  let area = 0
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    area += ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1]
  }
  return area / 2
}

// ArcGIS ring ordering doesn't follow the GeoJSON spec.
// Reorder: largest ring (by absolute area) becomes Ring 0 (exterior),
// all others become holes.
function reorderRings(rings: [number, number][][]): [number, number][][] {
  if (rings.length <= 1) return rings
  const areas = rings.map((r) => Math.abs(ringArea(r)))
  const maxIdx = areas.indexOf(Math.max(...areas))
  const exterior = rings[maxIdx]
  const holes = rings.filter((_, i) => i !== maxIdx)
  return [exterior, ...holes]
}

function toGeoJSON(
  features: ArcGISFeature[],
  propertyExtractor: (attrs: Record<string, unknown>) => Record<string, unknown>,
): GeoJSONCollection {
  return {
    type: 'FeatureCollection',
    features: features.map((f) => ({
      type: 'Feature',
      properties: propertyExtractor(f.attributes),
      geometry: {
        type: 'Polygon',
        coordinates: reorderRings(reprojectRings(f.geometry.rings)),
      },
    })),
  }
}

// ─── Main ───────────────────────────────────────────────────────────────────

async function main() {
  console.log('Fetching web map data from ArcGIS...')
  const res = await fetch(DATA_URL)
  if (!res.ok) throw new Error(`Failed to fetch: ${res.status}`)
  const data = await res.json()

  const layers = data.operationalLayers as Array<{
    title: string
    featureCollection?: {
      layers: Array<{
        featureSet: { features: ArcGISFeature[] }
      }>
    }
  }>

  // Extract district boundaries
  const districtLayer = layers.find((l) => l.title === 'Adopted Map 201')
  if (!districtLayer?.featureCollection) {
    throw new Error('Could not find "Adopted Map 201" layer')
  }
  const districtFeatures =
    districtLayer.featureCollection.layers[0].featureSet.features

  const districts = toGeoJSON(districtFeatures, (attrs) => ({
    district: parseInt(attrs.DISTRICT as string, 10),
    population: attrs.POPULATION as number,
  }))

  // Extract neighborhood boundaries
  const nhLayer = layers.find((l) => l.title === 'Neighborhood_Council')
  if (!nhLayer?.featureCollection) {
    throw new Error('Could not find "Neighborhood_Council" layer')
  }
  const nhFeatures = nhLayer.featureCollection.layers[0].featureSet.features

  const neighborhoods = toGeoJSON(nhFeatures, (attrs) => ({
    name: attrs.NHNAME as string,
    code: attrs.NHCODE as string,
  }))

  // Write output
  mkdirSync(OUTPUT_DIR, { recursive: true })

  const districtPath = join(OUTPUT_DIR, 'richmond-districts.geojson')
  writeFileSync(districtPath, JSON.stringify(districts))
  console.log(
    `Wrote ${districts.features.length} districts → ${districtPath}`,
  )

  const nhPath = join(OUTPUT_DIR, 'richmond-neighborhoods.geojson')
  writeFileSync(nhPath, JSON.stringify(neighborhoods))
  console.log(
    `Wrote ${neighborhoods.features.length} neighborhoods → ${nhPath}`,
  )

  // Validation
  console.log('\nValidation:')
  for (const f of districts.features) {
    const d = f.properties.district
    const rings = f.geometry.coordinates.length
    const points = f.geometry.coordinates.reduce((s, r) => s + r.length, 0)
    const closed =
      JSON.stringify(f.geometry.coordinates[0][0]) ===
      JSON.stringify(
        f.geometry.coordinates[0][f.geometry.coordinates[0].length - 1],
      )
    console.log(
      `  District ${d}: ${rings} ring(s), ${points} points, closed=${closed}`,
    )
  }
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
