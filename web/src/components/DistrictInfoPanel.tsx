import Link from 'next/link'
import type { Official, NeighborhoodCouncil } from '@/lib/types'
import { officialToSlug } from '@/lib/queries'
import { getDistrictColor } from '@/lib/district-colors'

interface DistrictInfoPanelProps {
  district: number
  population: number
  official: Official | undefined
  neighborhoodCouncils: NeighborhoodCouncil[]
}

export default function DistrictInfoPanel({
  district,
  population,
  official,
  neighborhoodCouncils,
}: DistrictInfoPanelProps) {
  const color = getDistrictColor(district)
  const activeNCs = neighborhoodCouncils.filter((nc) => nc.is_active)

  return (
    <div
      className="bg-white border border-slate-200 rounded-lg p-5 animate-in fade-in duration-200"
      style={{ borderLeft: `4px solid ${color}` }}
    >
      <div className="flex items-center gap-3 mb-3">
        <span
          className="inline-flex items-center justify-center w-10 h-10 rounded-lg text-white font-bold text-lg"
          style={{ backgroundColor: color }}
          aria-hidden="true"
        >
          {district}
        </span>
        <div>
          <h3 className="text-lg font-semibold text-civic-navy">
            District {district}
          </h3>
          <p className="text-sm text-slate-500">
            Population: {population.toLocaleString()}
          </p>
        </div>
      </div>

      {official ? (
        <p className="text-base text-civic-slate mb-4">
          District {district} is represented by{' '}
          <Link
            href={`/council/${officialToSlug(official.name)}`}
            className="font-semibold text-civic-navy hover:underline"
          >
            {official.name}
          </Link>
          {official.term_end && (
            <span className="text-sm text-slate-400">
              {' '}(term ends {new Date(official.term_end).getFullYear()})
            </span>
          )}
        </p>
      ) : (
        <p className="text-base text-civic-slate mb-4">
          No current representative on file for District {district}.
        </p>
      )}

      {activeNCs.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-civic-slate mb-2">
            Neighborhood councils in this district
          </h4>
          <ul className="space-y-1">
            {activeNCs.map((nc) => (
              <li key={nc.id} className="text-sm text-slate-600">
                {nc.city_page_url ? (
                  <a
                    href={nc.city_page_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-civic-navy hover:underline"
                  >
                    {nc.short_name ?? nc.name}
                  </a>
                ) : (
                  <span>{nc.short_name ?? nc.name}</span>
                )}
                {nc.president && (
                  <span className="text-slate-400"> &middot; President: {nc.president}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 pt-3 border-t border-slate-100">
        <Link
          href="/elections/find-my-district"
          className="text-sm text-civic-navy hover:underline"
        >
          Look up your exact address &rarr;
        </Link>
      </div>
    </div>
  )
}
