import Link from 'next/link'
import { Suspense, type ReactNode } from 'react'
import CampaignEntityIndexClient from '@/components/CampaignEntityIndexClient'
import type { CampaignEntityIndexItem } from '@/components/CampaignEntityIndexClient'

export type CampaignEntityDirectoryAvailability =
  | 'ready'
  | 'query-error'
  | 'incomplete'
  | 'missing-trust-fields'

interface CampaignEntityIndexProps {
  heading: string
  description: string
  items: CampaignEntityIndexItem[]
  currentCycle: number
  singularLabel: string
  pluralLabel: string
  availability: CampaignEntityDirectoryAvailability
  afterList?: ReactNode
  sourceNote?: ReactNode
}

/** Shared directory grammar for committees and unions. */
export default function CampaignEntityIndex({
  heading,
  description,
  items,
  currentCycle,
  singularLabel,
  pluralLabel,
  availability,
  afterList,
  sourceNote,
}: CampaignEntityIndexProps) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-civic-navy">{heading}</h1>
        <p className="mt-2 max-w-3xl text-base leading-7 text-slate-700">
          {description}
        </p>
      </header>

      {availability === 'ready' ? (
        <Suspense fallback={<DirectoryLoading pluralLabel={pluralLabel} />}>
          <CampaignEntityIndexClient
            items={items}
            currentCycle={currentCycle}
            singularLabel={singularLabel}
            pluralLabel={pluralLabel}
          />
        </Suspense>
      ) : (
        <DirectoryUnavailable availability={availability} />
      )}

      {afterList && <div className="mt-8 max-w-3xl">{afterList}</div>}

      <footer className="mt-12 space-y-2 border-t border-slate-200 pt-6">
        <p className="text-sm leading-6 text-slate-600">
          Sources: official campaign-finance filings from{' '}
          <Link
            href="https://public.netfile.com/pub2/?AID=RICH"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 items-center font-medium text-civic-navy underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-navy focus-visible:ring-offset-2"
          >
            NetFile
          </Link>{' '}
          (City of Richmond) and CAL-ACCESS (California Secretary of State).
          Both are Tier 1 sources.
        </p>
        <p className="text-sm leading-6 text-slate-600">
          These legacy records do not include a reliable direct source link or
          extraction time for every row. The directory does not invent either;
          profile tables include the filing identifiers that are available.
        </p>
        {sourceNote && (
          <p className="text-sm leading-6 text-slate-600">{sourceNote}</p>
        )}
      </footer>
    </div>
  )
}

function DirectoryLoading({ pluralLabel }: { pluralLabel: string }) {
  return (
    <section aria-live="polite" aria-busy="true">
      <p className="sr-only">Loading {pluralLabel} directory filters.</p>
      <div className="mb-6 flex flex-wrap gap-2" aria-hidden="true">
        {[0, 1, 2].map((key) => (
          <span
            key={key}
            className="h-16 w-32 animate-pulse rounded-lg border border-slate-200 bg-slate-100"
          />
        ))}
      </div>
      <div
        aria-hidden="true"
        className="h-24 max-w-3xl animate-pulse rounded-lg border border-slate-200 bg-slate-100"
      />
    </section>
  )
}

function DirectoryUnavailable({
  availability,
}: {
  availability: Exclude<CampaignEntityDirectoryAvailability, 'ready'>
}) {
  const copy = {
    'query-error':
      'The official filing records could not be loaded. The directory is withheld rather than reporting no activity. Please try again later.',
    incomplete:
      'Only part of the official filing records was returned. Partial results are withheld rather than presented as a complete directory.',
    'missing-trust-fields':
      'This directory is not public yet. Its legacy aggregate does not provide complete row-level source links, extraction times, source tiers, and numeric confidence scores, so the entries and counts are withheld.',
  }[availability]

  return (
    <section
      aria-labelledby="campaign-entity-unavailable-heading"
      role={availability === 'missing-trust-fields' ? 'status' : 'alert'}
      className="max-w-3xl rounded-lg border border-amber-200 bg-amber-50 p-5 text-slate-700"
    >
      <h2
        id="campaign-entity-unavailable-heading"
        className="text-lg font-semibold text-civic-navy"
      >
        Directory unavailable
      </h2>
      <p className="mt-2 text-base leading-7">{copy}</p>
    </section>
  )
}

export type { CampaignEntityIndexItem }
