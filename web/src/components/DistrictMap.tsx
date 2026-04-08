'use client'

import dynamic from 'next/dynamic'
import type { Official, NeighborhoodCouncil } from '@/lib/types'

const DistrictMapClient = dynamic(() => import('./DistrictMapClient'), {
  ssr: false,
  loading: () => (
    <div className="w-full bg-slate-100 rounded-lg animate-pulse" style={{ height: 480 }}>
      <div className="flex items-center justify-center h-full text-slate-400">
        Loading map...
      </div>
    </div>
  ),
})

interface DistrictMapProps {
  officials: Official[]
  neighborhoodCouncils: NeighborhoodCouncil[]
}

export default function DistrictMap({ officials, neighborhoodCouncils }: DistrictMapProps) {
  return <DistrictMapClient officials={officials} neighborhoodCouncils={neighborhoodCouncils} />
}
