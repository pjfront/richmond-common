/**
 * Organization index — list all tracked unions and corporations.
 *
 * S28.3, Graduated tier.  Sorted by total contributed, same shape as
 * the PAC index: one row per entity, with type badge and cycle summary.
 */

import type { Metadata } from 'next'
import Link from 'next/link'
import { getOrgList } from '@/lib/queries'
import OperatorGate from '@/components/OperatorGate'

export const metadata: Metadata = {
  title: 'Organizations | Richmond Commons',
  description:
    'Unions and corporations that contribute to Richmond political campaigns. See who gives, how much, and which candidates and committees receive the money.',
}

function fmt(n: number): string {
  return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

function fmtDate(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', {
    month: 'short',
    year: 'numeric',
  })
}

const TYPE_LABELS: Record<string, string> = {
  union: 'Union',
  corporation: 'Corporation',
}

export default async function OrgIndexPage() {
  const orgs = await getOrgList()

  return (
    <OperatorGate>
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <header className="mb-6">
          <h1 className="text-3xl font-bold text-civic-navy">
            Unions &amp; corporations
          </h1>
          <p className="text-slate-600 mt-2 leading-relaxed max-w-3xl">
            Organizations that give to Richmond political campaigns —
            unions, companies, and trade associations. Each row links to a
            profile with giving history, top recipients, and independent
            expenditures.
          </p>
        </header>

        {orgs.length === 0 ? (
          <div className="border border-slate-200 rounded-lg p-10 text-center">
            <p className="text-slate-500">
              No organization data available yet. Entity typing is running —
              check back soon.
            </p>
          </div>
        ) : (
          <>
            <p className="text-xs text-slate-500 mb-4">
              {orgs.length} organization{orgs.length === 1 ? '' : 's'} with
              tracked contributions
            </p>

            <div className="space-y-3">
              {orgs.map((org) => (
                <Link
                  key={org.slug}
                  href={`/orgs/${org.slug}`}
                  className="block border border-slate-200 rounded-lg p-5 hover:border-civic-navy/40 hover:bg-civic-navy/[0.01] transition-colors group"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <h2 className="text-lg font-semibold text-civic-navy group-hover:text-civic-navy-light truncate">
                          {org.display_name}
                        </h2>
                        <span className="px-2 py-0.5 text-[11px] font-semibold bg-civic-amber/10 text-civic-amber rounded-full uppercase tracking-wide shrink-0">
                          {TYPE_LABELS[org.entity_type] ?? org.entity_type}
                        </span>
                      </div>

                      {org.sponsor_disclosure && (
                        <p className="text-xs text-civic-amber mt-1.5 font-medium">
                          {org.sponsor_disclosure}
                        </p>
                      )}

                      <p className="text-sm text-slate-600 mt-2 leading-relaxed">
                        <strong>${fmt(org.total_contributed)}</strong> in
                        tracked contributions
                        {org.earliest_contribution_date &&
                          org.latest_contribution_date && (
                            <>
                              {' '}
                              from{' '}
                              {fmtDate(org.earliest_contribution_date)} to{' '}
                              {fmtDate(org.latest_contribution_date)}
                            </>
                          )}
                        {org.recipient_count > 0 && (
                          <>
                            {' '}
                            across{' '}
                            <strong>
                              {org.recipient_count}
                            </strong>{' '}
                            recipient
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
              ))}
            </div>
          </>
        )}

        <footer className="mt-12 pt-6 border-t border-slate-100 space-y-2">
          <p className="text-xs text-slate-400 leading-relaxed">
            Contribution data from{' '}
            <a
              href="https://public.netfile.com/pub2/?AID=RICH"
              target="_blank"
              rel="noopener noreferrer"
              className="text-civic-navy hover:underline"
            >
              NetFile
            </a>{' '}
            (City of Richmond e-filing system, Tier 1 source) and CAL-ACCESS
            (California Secretary of State, Tier 1 source). Organization
            classification is auto-generated from name patterns and public
            records.
          </p>
          <p className="text-xs text-slate-400">
            Auto-generated from public records &middot; Updated within ~15
            minutes of any new filing
          </p>
        </footer>
      </div>
    </OperatorGate>
  )
}
