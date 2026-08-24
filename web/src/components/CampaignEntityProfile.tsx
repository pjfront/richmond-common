import Link from 'next/link'
import type { ReactNode } from 'react'

interface CampaignEntityProfileProps {
  backHref: string
  backLabel: string
  name: string
  filedName?: string
  typeLabel: string
  filingId?: string | null
  sponsorDisclosure?: string | null
  summary: ReactNode
  sourceNote: ReactNode
  children: ReactNode
}

function initialsFor(name: string): string {
  const initials = name
    .split(/\s+/)
    .map((word) => word[0])
    .filter((letter) => /[A-Z]/i.test(letter ?? ''))
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return initials || 'RC'
}

/**
 * Shared public profile grammar for political committees, unions, and
 * companies. The filing narrative leads; sortable receipt detail follows.
 */
export default function CampaignEntityProfile({
  backHref,
  backLabel,
  name,
  filedName,
  typeLabel,
  filingId,
  sponsorDisclosure,
  summary,
  sourceNote,
  children,
}: CampaignEntityProfileProps) {
  return (
    <article className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Link
        href={backHref}
        className="inline-flex min-h-11 items-center gap-1 text-sm text-civic-navy/70 hover:text-civic-navy transition-colors"
      >
        <span aria-hidden="true">&larr;</span> {backLabel}
      </Link>

      <header className="mt-4 mb-8 flex items-start gap-4 sm:gap-5">
        <div
          aria-hidden="true"
          className="w-14 h-14 sm:w-16 sm:h-16 rounded-full bg-civic-navy text-white text-lg sm:text-xl font-bold flex items-center justify-center shrink-0"
        >
          {initialsFor(name)}
        </div>
        <div className="min-w-0">
          <h1 className="text-3xl sm:text-4xl font-bold text-civic-navy tracking-tight break-words">
            {name}
          </h1>
          {filedName && filedName !== name && (
            <p className="text-sm text-slate-600 mt-1.5 leading-snug">
              Filed as: {filedName}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <span className="px-2.5 py-1 text-xs font-semibold bg-slate-100 text-slate-700 rounded-full">
              {typeLabel}
            </span>
            {filingId && filingId !== 'Pending' && (
              <span className="text-xs text-slate-500 tabular-nums">
                Filer ID {filingId}
              </span>
            )}
          </div>
          {sponsorDisclosure && (
            <p className="text-sm text-amber-800 mt-3 font-medium">
              {sponsorDisclosure}
            </p>
          )}
        </div>
      </header>

      <section className="border-l-4 border-civic-navy bg-civic-navy/[0.02] rounded-r-lg p-5 sm:p-6 mb-7">
        <h2 className="text-lg font-semibold text-civic-navy mb-2">
          What the filings show
        </h2>
        <p className="text-base text-slate-700 leading-7">{summary}</p>
      </section>

      {children}

      <footer className="mt-12 pt-6 border-t border-slate-200 space-y-2">
        <p className="text-xs text-slate-600 leading-relaxed">
          Filing data from{' '}
          <a
            href="https://public.netfile.com/pub2/?AID=RICH"
            target="_blank"
            rel="noopener noreferrer"
            className="text-civic-navy underline-offset-2 hover:underline"
          >
            NetFile
          </a>{' '}
          (City of Richmond e-filing system) and CAL-ACCESS (California
          Secretary of State). Both are Tier 1 official sources.
        </p>
        <p className="text-xs text-slate-600 leading-relaxed">{sourceNote}</p>
        <p className="text-xs text-slate-500">
          Auto-generated from public records &middot; Updated after Richmond
          Commons checks the filing systems for new records
        </p>
      </footer>
    </article>
  )
}

interface CampaignEntitySectionProps {
  title: string
  summary: ReactNode
  children?: ReactNode
}

/** Consistent sentence-first wrapper for money received, money given, and IE receipts. */
export function CampaignEntitySection({
  title,
  summary,
  children,
}: CampaignEntitySectionProps) {
  return (
    <section className="mb-6">
      <div className="border border-slate-200 bg-white rounded-lg p-5 sm:p-6">
        <h2 className="text-lg font-semibold text-civic-navy mb-2">{title}</h2>
        <p className="text-base text-slate-700 leading-7">{summary}</p>
        {children && <div className="mt-4">{children}</div>}
      </div>
    </section>
  )
}
