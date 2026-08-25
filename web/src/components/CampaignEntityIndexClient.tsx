'use client'

import Link from 'next/link'
import { useMemo, useState } from 'react'

type TimeWindow = 'current' | 'last2' | 'tracked'

export interface CampaignEntityIndexItem {
  id: string
  href: string
  name: string
  kind: 'committee' | 'union'
  sponsorDisclosure: string | null
  cycleBars: Array<{
    cycle: number
    received: number
    given: number
  }>
}

interface CampaignEntityIndexClientProps {
  items: CampaignEntityIndexItem[]
  currentCycle: number
  singularLabel: string
  pluralLabel: string
}

function cyclesInWindow(
  item: CampaignEntityIndexItem,
  window: TimeWindow,
  currentCycle: number,
) {
  if (window === 'current') {
    return item.cycleBars.filter((bar) => bar.cycle === currentCycle)
  }
  if (window === 'last2') {
    return item.cycleBars.filter((bar) => bar.cycle >= currentCycle - 2)
  }
  return item.cycleBars
}

function totalsInWindow(
  item: CampaignEntityIndexItem,
  window: TimeWindow,
  currentCycle: number,
) {
  return cyclesInWindow(item, window, currentCycle).reduce(
    (total, bar) => ({
      received: total.received + bar.received,
      given: total.given + bar.given,
    }),
    { received: 0, given: 0 },
  )
}

function periodText(window: TimeWindow, currentCycle: number): string {
  if (window === 'current') return `in the ${currentCycle} cycle`
  if (window === 'last2') {
    return `across the ${currentCycle - 2} and ${currentCycle} cycles`
  }
  return 'across the five tracked election cycles'
}

function activityText(
  item: CampaignEntityIndexItem,
  window: TimeWindow,
  currentCycle: number,
): string {
  const totals = totalsInWindow(item, window, currentCycle)
  const period = periodText(window, currentCycle)

  if (item.kind === 'union') {
    return `Reported contributions to campaign committees ${period}.`
  }
  if (totals.received > 0 && totals.given > 0) {
    return `Reported money received from donors and contributions to other committees ${period}.`
  }
  if (totals.received > 0) {
    return `Reported money received from donors ${period}.`
  }
  return `Reported contributions to other committees ${period}.`
}

function CampaignEntityRow({
  item,
  window,
  currentCycle,
}: {
  item: CampaignEntityIndexItem
  window: TimeWindow
  currentCycle: number
}) {
  const sponsorName = item.sponsorDisclosure
    ?.replace(/^sponsored by (?:the )?/i, '')
    .toLowerCase()
  const showSponsorDisclosure = Boolean(
    item.sponsorDisclosure &&
      sponsorName &&
      !item.name.toLowerCase().includes(sponsorName),
  )

  return (
    <Link
      href={item.href}
      className="group flex min-h-11 items-start gap-4 rounded-lg border border-slate-200 bg-white py-4 pl-4 pr-14 transition-colors hover:border-civic-navy/40 hover:bg-civic-navy/[0.01] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-navy focus-visible:ring-offset-2 sm:pr-4"
    >
      <p className="min-w-0 flex-1 text-base leading-7 text-slate-700">
        <span className="font-semibold text-civic-navy group-hover:underline">
          {item.name}
        </span>
        .{' '}
        {showSponsorDisclosure && item.sponsorDisclosure && (
          <>
            <span className="font-medium text-amber-800">
              {item.sponsorDisclosure.replace(/[.!?]+$/, '')}.
            </span>{' '}
          </>
        )}
        {activityText(item, window, currentCycle)}
      </p>
      <span
        aria-hidden="true"
        className="mt-0.5 shrink-0 text-xl text-slate-400 transition-colors group-hover:text-civic-navy"
      >
        &rarr;
      </span>
    </Link>
  )
}

export default function CampaignEntityIndexClient({
  items,
  currentCycle,
  singularLabel,
  pluralLabel,
}: CampaignEntityIndexClientProps) {
  const [window, setWindow] = useState<TimeWindow>('current')

  const { visibleItems, hiddenCount } = useMemo(() => {
    const visibleItems = items
      .filter((item) => {
        const totals = totalsInWindow(item, window, currentCycle)
        return totals.received + totals.given > 0
      })
      .sort((left, right) => {
        const leftTotals = totalsInWindow(left, window, currentCycle)
        const rightTotals = totalsInWindow(right, window, currentCycle)
        return (
          rightTotals.received +
          rightTotals.given -
          (leftTotals.received + leftTotals.given)
        )
      })

    return {
      visibleItems,
      hiddenCount: items.length - visibleItems.length,
    }
  }, [currentCycle, items, window])

  const options: Array<{
    value: TimeWindow
    label: string
    description: string
  }> = [
    {
      value: 'current',
      label: `${currentCycle} cycle`,
      description: 'Current filings',
    },
    {
      value: 'last2',
      label: `${currentCycle - 2}–${currentCycle}`,
      description: 'Last two cycles',
    },
    {
      value: 'tracked',
      label: 'Last five cycles',
      description: 'Ten-year view',
    },
  ]

  return (
    <section aria-labelledby="campaign-entity-directory-heading">
      <h2 id="campaign-entity-directory-heading" className="sr-only">
        Browse {pluralLabel}
      </h2>

      <fieldset className="mb-6">
        <legend className="mb-2 text-sm font-semibold text-slate-700">
          Time period
        </legend>
        <div className="flex flex-wrap items-stretch gap-2">
          {options.map((option) => {
            const active = window === option.value
            return (
              <button
                key={option.value}
                type="button"
                onClick={() => setWindow(option.value)}
                aria-pressed={active}
                className={`group flex min-h-11 flex-col items-start justify-center rounded-lg border px-4 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-navy focus-visible:ring-offset-2 ${
                  active
                    ? 'border-civic-navy bg-civic-navy text-white'
                    : 'border-slate-200 bg-white text-slate-700 hover:border-civic-navy/50 hover:bg-civic-navy/[0.02]'
                }`}
              >
                <span className="text-sm font-semibold tabular-nums">
                  {option.label}
                </span>
                <span
                  className={`mt-0.5 text-xs leading-tight ${
                    active ? 'text-white' : 'text-slate-600'
                  }`}
                >
                  {option.description}
                </span>
              </button>
            )
          })}
        </div>
      </fieldset>

      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-600">
        <p role="status" aria-live="polite">
          Showing <strong>{visibleItems.length}</strong>{' '}
          {visibleItems.length === 1 ? singularLabel : pluralLabel} with
          reported activity {periodText(window, currentCycle)}.
        </p>
        {hiddenCount > 0 && window !== 'tracked' && (
          <button
            type="button"
            onClick={() => setWindow('tracked')}
            className="inline-flex min-h-11 items-center font-medium text-civic-navy underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-navy focus-visible:ring-offset-2"
          >
            Show {hiddenCount} more from the last five cycles
          </button>
        )}
      </div>

      {visibleItems.length > 0 ? (
        <div className="grid gap-3">
          {visibleItems.map((item) => (
            <CampaignEntityRow
              key={item.id}
              item={item}
              window={window}
              currentCycle={currentCycle}
            />
          ))}
        </div>
      ) : (
        <div
          role="status"
          className="rounded-lg border border-slate-200 bg-slate-50 p-6 text-center text-base text-slate-600"
        >
          No {pluralLabel} have reported activity in this time period.
        </div>
      )}
    </section>
  )
}
