'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { MapContainer, TileLayer, GeoJSON, useMap } from 'react-leaflet'
import type { Layer, LeafletMouseEvent, PathOptions } from 'leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { loadDistricts, loadNeighborhoods, findDistrict } from '@/lib/geo'
import type { GeoJSONCollection } from '@/lib/geo'
import type { Official, NeighborhoodCouncil } from '@/lib/types'
import { getDistrictStyle, getDistrictColor, DISTRICT_COLORS } from '@/lib/district-colors'
import DistrictInfoPanel from './DistrictInfoPanel'

// ─── Types ──────────────────────────────────────────────────────────────────

interface DistrictMapClientProps {
  officials: Official[]
  neighborhoodCouncils: NeighborhoodCouncil[]
}

interface DistrictFeatureProperties {
  district: number
  population: number
}

// ─── Helpers ────────────────────────────────────────────────────────────────

/** Match officials to district numbers via their seat field ("District 1", etc.) */
function buildOfficialMap(officials: Official[]): Map<number, Official> {
  const map = new Map<number, Official>()
  for (const o of officials) {
    if (o.seat?.startsWith('District ')) {
      const num = parseInt(o.seat.replace('District ', ''), 10)
      if (!isNaN(num)) map.set(num, o)
    }
  }
  return map
}

/** Compute rough centroid of a polygon (average of vertices) */
function polygonCentroid(coords: number[][][]): [number, number] {
  const ring = coords[0] // exterior ring
  let sumLng = 0
  let sumLat = 0
  for (const [lng, lat] of ring) {
    sumLng += lng
    sumLat += lat
  }
  return [sumLat / ring.length, sumLng / ring.length] // [lat, lng]
}

/** Map neighborhood councils to districts using polygon centroids */
function mapNCsToDistricts(
  neighborhoodCouncils: NeighborhoodCouncil[],
  neighborhoodsGeoJSON: GeoJSONCollection,
  districtsGeoJSON: GeoJSONCollection,
): Map<number, NeighborhoodCouncil[]> {
  const result = new Map<number, NeighborhoodCouncil[]>()
  for (let d = 1; d <= 6; d++) result.set(d, [])

  // Build code → district map from neighborhood GeoJSON centroids
  const codeToDistrict = new Map<number, number>()
  for (const feature of neighborhoodsGeoJSON.features) {
    const code = feature.properties.code as number
    if (code == null) continue
    const [lat, lng] = polygonCentroid(feature.geometry.coordinates)
    const match = findDistrict(lat, lng, districtsGeoJSON)
    if (match) codeToDistrict.set(code, match.district)
  }

  // Assign NCs to districts based on their geojson_codes
  for (const nc of neighborhoodCouncils) {
    if (!nc.geojson_codes?.length) continue
    // Use the first code's district (most NCs span one district)
    for (const code of nc.geojson_codes) {
      const district = codeToDistrict.get(code)
      if (district) {
        const list = result.get(district)!
        if (!list.some((existing) => existing.id === nc.id)) {
          list.push(nc)
        }
      }
    }
  }

  return result
}

// ─── District number labels on the map ──────────────────────────────────────

/**
 * Hand-tuned label positions for each district.
 * Computed centroids fail for irregular shapes (District 2 lands in the bay,
 * District 4 drifts into hills). These are placed at the visual center of
 * each district's populated core. Only 6 districts, stable until ~2031 redistricting.
 */
const DISTRICT_LABEL_POSITIONS: Record<number, [number, number]> = {
  1: [37.940, -122.358],   // Iron Triangle / Belding Woods area
  2: [37.955, -122.362],   // Hilltop / north central Richmond
  3: [37.933, -122.352],   // Coronado / south central
  4: [37.953, -122.308],   // East Richmond Heights / hills
  5: [37.920, -122.338],   // Richmond Annex / south
  6: [37.945, -122.340],   // East Richmond core
}

function DistrictLabels({ geojson }: { geojson: GeoJSONCollection }) {
  const map = useMap()

  useEffect(() => {
    const markers: L.Marker[] = []
    for (const feature of geojson.features) {
      const district = feature.properties.district as number
      const pos = DISTRICT_LABEL_POSITIONS[district]
      if (!pos) continue
      const [lat, lng] = pos
      const color = getDistrictColor(district)
      const icon = L.divIcon({
        className: 'district-label',
        html: `<span style="display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:8px;background:white;border:2px solid ${color};color:${color};font-weight:700;font-size:14px;box-shadow:0 1px 3px rgba(0,0,0,0.15);">${district}</span>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
      })
      const marker = L.marker([lat, lng], { icon, interactive: false })
      marker.addTo(map)
      markers.push(marker)
    }
    return () => {
      markers.forEach((m) => m.remove())
    }
  }, [map, geojson])

  return null
}

// ─── Main Component ─────────────────────────────────────────────────────────

export default function DistrictMapClient({
  officials,
  neighborhoodCouncils,
}: DistrictMapClientProps) {
  const [districts, setDistricts] = useState<GeoJSONCollection | null>(null)
  const [neighborhoods, setNeighborhoods] = useState<GeoJSONCollection | null>(null)
  const [selectedDistrict, setSelectedDistrict] = useState<number | null>(null)
  const [hoveredDistrict, setHoveredDistrict] = useState<number | null>(null)
  const [showTable, setShowTable] = useState(false)
  const geoJsonRef = useRef<L.GeoJSON | null>(null)

  const officialMap = buildOfficialMap(officials)

  // Load GeoJSON data
  useEffect(() => {
    Promise.all([loadDistricts(), loadNeighborhoods()]).then(([d, n]) => {
      setDistricts(d)
      setNeighborhoods(n)
    })
  }, [])

  // Compute NC mapping once data is loaded
  const ncByDistrict =
    districts && neighborhoods
      ? mapNCsToDistricts(neighborhoodCouncils, neighborhoods, districts)
      : new Map<number, NeighborhoodCouncil[]>()

  // Style each district polygon
  const styleFeature = useCallback(
    (feature: GeoJSON.Feature | undefined): PathOptions => {
      if (!feature?.properties) return {}
      const d = feature.properties.district as number
      const state =
        d === selectedDistrict ? 'selected' : d === hoveredDistrict ? 'hover' : 'normal'
      return getDistrictStyle(d, state)
    },
    [selectedDistrict, hoveredDistrict],
  )

  // Bind hover + click to each feature
  const onEachFeature = useCallback(
    (feature: GeoJSON.Feature, layer: Layer) => {
      const d = feature.properties?.district as number
      const official = officialMap.get(d)
      const tooltipContent = `<strong>District ${d}</strong>${official ? `<br/>${official.name}` : ''}`

      layer.bindTooltip(tooltipContent, {
        sticky: true,
        direction: 'top',
        className: 'district-tooltip',
      })

      layer.on({
        mouseover: (e: LeafletMouseEvent) => {
          setHoveredDistrict(d)
          e.target.bringToFront()
        },
        mouseout: () => {
          setHoveredDistrict(null)
        },
        click: () => {
          setSelectedDistrict((prev) => (prev === d ? null : d))
        },
      })
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [officials],
  )

  // Update layer styles when hover/selection changes
  useEffect(() => {
    if (!geoJsonRef.current) return
    geoJsonRef.current.eachLayer((layer) => {
      const feature = (layer as L.GeoJSON & { feature?: GeoJSON.Feature }).feature
      if (feature?.properties) {
        const d = feature.properties.district as number
        const state =
          d === selectedDistrict ? 'selected' : d === hoveredDistrict ? 'hover' : 'normal'
        ;(layer as L.Path).setStyle(getDistrictStyle(d, state))
      }
    })
  }, [selectedDistrict, hoveredDistrict])

  // Selected district data
  const selectedFeature = districts?.features.find(
    (f) => f.properties.district === selectedDistrict,
  )

  if (!districts) {
    return (
      <div className="w-full bg-slate-100 rounded-lg animate-pulse" style={{ height: 480 }}>
        <div className="flex items-center justify-center h-full text-slate-400">
          Loading map...
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* Leaflet overrides */}
      <style>{`
        .leaflet-interactive { cursor: pointer !important; }
        .district-tooltip {
          background: white;
          border: none;
          border-radius: 8px;
          padding: 6px 10px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.15);
          font-family: var(--font-sans), system-ui, sans-serif;
          font-size: 13px;
          line-height: 1.4;
        }
        .district-tooltip .leaflet-tooltip-tip { display: none; }
        .district-label { background: none !important; border: none !important; }
      `}</style>
      {/* Map */}
      <div className="w-full rounded-xl overflow-hidden border border-slate-200 shadow-sm" style={{ height: 480 }}>
        <MapContainer
          center={[37.935, -122.348]}
          zoom={12}
          scrollWheelZoom={true}
          style={{ height: '100%', width: '100%' }}
          zoomControl={true}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          />
          <GeoJSON
            ref={geoJsonRef}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            data={districts as any}
            style={styleFeature}
            onEachFeature={onEachFeature}
          />
          <DistrictLabels geojson={districts} />
        </MapContainer>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-2 mt-3">
        {Object.entries(DISTRICT_COLORS).map(([d, color]) => {
          const num = parseInt(d, 10)
          const official = officialMap.get(num)
          const isActive = selectedDistrict === num
          return (
            <button
              key={d}
              onClick={() => setSelectedDistrict((prev) => (prev === num ? null : num))}
              className={`flex items-center gap-2 text-sm pl-2.5 pr-3 py-1.5 rounded-lg border transition-all ${
                isActive
                  ? 'bg-slate-50 border-slate-300 shadow-sm'
                  : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
              }`}
            >
              <span
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: color }}
                aria-hidden="true"
              />
              <span className="text-civic-slate">
                D{d}
                {official && (
                  <span className="text-slate-400 hidden sm:inline"> {official.name.split(' ').pop()}</span>
                )}
              </span>
            </button>
          )
        })}
      </div>

      {/* Info Panel */}
      {selectedDistrict && selectedFeature && (
        <div className="mt-4">
          <DistrictInfoPanel
            district={selectedDistrict}
            population={selectedFeature.properties.population as number}
            official={officialMap.get(selectedDistrict)}
            neighborhoodCouncils={ncByDistrict.get(selectedDistrict) ?? []}
          />
        </div>
      )}

      {/* Accessible table toggle */}
      <div className="mt-6">
        <button
          onClick={() => setShowTable((v) => !v)}
          className="text-sm text-civic-navy hover:underline"
          aria-expanded={showTable}
          aria-controls="district-table"
        >
          {showTable ? 'Hide table view' : 'View as table'}
        </button>

        {showTable && (
          <div id="district-table" className="mt-3 overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <caption className="sr-only">
                Richmond city council districts with representatives and population
              </caption>
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="text-left py-2 pr-4 font-semibold text-civic-navy">District</th>
                  <th className="text-left py-2 pr-4 font-semibold text-civic-navy">Representative</th>
                  <th className="text-right py-2 pr-4 font-semibold text-civic-navy">Population</th>
                  <th className="text-left py-2 font-semibold text-civic-navy">Neighborhood Councils</th>
                </tr>
              </thead>
              <tbody>
                {districts.features.map((f) => {
                  const d = f.properties.district as number
                  const pop = f.properties.population as number
                  const official = officialMap.get(d)
                  const ncs = ncByDistrict.get(d) ?? []
                  return (
                    <tr key={d} className="border-b border-slate-100">
                      <td className="py-2 pr-4">
                        <span className="flex items-center gap-2">
                          <span
                            className="w-3 h-3 rounded-sm flex-shrink-0"
                            style={{ backgroundColor: getDistrictColor(d) }}
                            aria-hidden="true"
                          />
                          District {d}
                        </span>
                      </td>
                      <td className="py-2 pr-4 text-civic-slate">
                        {official?.name ?? 'Vacant'}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums text-slate-500">
                        {pop.toLocaleString()}
                      </td>
                      <td className="py-2 text-slate-500">
                        {ncs.length > 0
                          ? ncs.map((nc) => nc.short_name ?? nc.name).join(', ')
                          : 'None mapped'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
