import Link from 'next/link'
import type { ReactNode } from 'react'
import CampaignEntityIndexClient from '@/components/CampaignEntityIndexClient'
import type { CampaignEntityIndexItem } from '@/components/CampaignEntityIndexClient'

interface CampaignEntityIndexProps {
  heading: string
  description: string
  items: CampaignEntityIndexItem[]
  currentCycle: number
  singularLabel: string
  pluralLabel: string
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

      <CampaignEntityIndexClient
        items={items}
        currentCycle={currentCycle}
        singularLabel={singularLabel}
        pluralLabel={pluralLabel}
      />

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

export type { CampaignEntityIndexItem }
