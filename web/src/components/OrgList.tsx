/** Shared legacy list shell for union and company indexes. */

import Link from 'next/link'
import type { OrgAggregate } from '@/lib/types'

function OrgCard({ org }: { org: OrgAggregate }) {
  return (
    <Link
      href={`/orgs/${org.slug}`}
      className="group block min-h-11 rounded-lg border border-slate-200 p-5 transition-colors hover:border-civic-navy/40 hover:bg-civic-navy/[0.01] focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-civic-navy group-hover:text-civic-navy-light">
            {org.display_name}
          </h2>

          {org.sponsor_disclosure ? (
            <p className="mt-1.5 text-sm font-medium text-amber-800">
              {org.sponsor_disclosure}
            </p>
          ) : null}

          <p className="mt-2 text-sm leading-relaxed text-slate-700">
            {org.current_cycle_total > 0
              ? 'Public campaign records show contributions in the current election cycle.'
              : 'Open the profile to review the available public campaign records.'}
          </p>
        </div>

        <span
          aria-hidden="true"
          className="shrink-0 self-center text-xl text-slate-300 transition-colors group-hover:text-civic-navy-light"
        >
          &rarr;
        </span>
      </div>
    </Link>
  )
}

interface OrgListProps {
  orgs: OrgAggregate[]
  heading: string
  description: string
}

export default function OrgList({ orgs, heading, description }: OrgListProps) {
  return (
    <>
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-civic-navy">{heading}</h1>
        <p className="text-slate-600 mt-2 leading-relaxed max-w-3xl">
          {description}
        </p>
      </header>

      {orgs.length > 0 ? (
        <div className="space-y-3">
          {orgs.map((org) => (
            <OrgCard key={org.slug} org={org} />
          ))}
        </div>
      ) : (
        <p className="rounded-lg border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">
          No organization records are available yet.
        </p>
      )}
    </>
  )
}
