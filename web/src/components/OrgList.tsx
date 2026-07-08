/**
 * Shared org listing component — used by /unions and /corporations.
 *
 * I164: extracted from /orgs/page.tsx so each entity type gets its own
 * route, nav item, and metadata without duplicating the card/section markup.
 */

import Link from 'next/link'
import type { OrgAggregate } from '@/lib/types'

function fmt(n: number): string {
  return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

function fmtDate(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', {
    month: 'short',
    year: 'numeric',
  })
}

function OrgCard({ org }: { org: OrgAggregate }) {
  return (
    <Link
      href={`/orgs/${org.slug}`}
      className="block border border-slate-200 rounded-lg p-5 hover:border-civic-navy/40 hover:bg-civic-navy/[0.01] transition-colors group"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-civic-navy group-hover:text-civic-navy-light truncate">
            {org.display_name}
          </h2>

          {org.sponsor_disclosure && (
            <p className="text-xs text-civic-amber mt-1.5 font-medium">
              {org.sponsor_disclosure}
            </p>
          )}

          <p className="text-sm text-slate-600 mt-2 leading-relaxed">
            <strong>${fmt(org.total_contributed)}</strong> in tracked
            contributions
            {org.earliest_contribution_date &&
              org.latest_contribution_date && (
                <>
                  {' '}
                  from {fmtDate(org.earliest_contribution_date)} to{' '}
                  {fmtDate(org.latest_contribution_date)}
                </>
              )}
            {org.recipient_count > 0 && (
              <>
                {' '}
                across <strong>{org.recipient_count}</strong> recipient
                {org.recipient_count === 1 ? '' : 's'}
              </>
            )}
            .
          </p>
        </div>

        <div className="shrink-0 self-center">
          <span
            aria-hidden="true"
            className="text-slate-300 group-hover:text-civic-navy-light transition-colors text-xl"
          >
            →
          </span>
        </div>
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
  if (orgs.length === 0) {
    return (
      <div className="border border-slate-200 rounded-lg p-10 text-center">
        <p className="text-slate-500">
          No organization data available yet. Entity typing is running — check
          back soon.
        </p>
      </div>
    )
  }

  return (
    <>
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-civic-navy">{heading}</h1>
        <p className="text-slate-600 mt-2 leading-relaxed max-w-3xl">
          {description}
        </p>
      </header>

      <p className="text-xs text-slate-500 mb-4">
        {orgs.length} organization{orgs.length === 1 ? '' : 's'} with tracked
        contributions
      </p>

      <div className="space-y-3">
        {orgs.map((org) => (
          <OrgCard key={org.slug} org={org} />
        ))}
      </div>
    </>
  )
}
