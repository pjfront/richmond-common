'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import SourceBadge from '@/components/SourceBadge'

export type TimeWindow = 'current' | 'last2' | 'tracked'

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
  activity_before_tracked_window: boolean
  source_url: string
  extracted_at: string
  source_tier: 1
  source_label: string
  confidence_score: number
}

interface CampaignEntityIndexClientProps {
  items: CampaignEntityIndexItem[]
  currentCycle: number
  singularLabel: string
  pluralLabel: string
}

interface CampaignEntityIndexViewProps extends CampaignEntityIndexClientProps {
  selectedWindow: TimeWindow
}

const PUBLIC_CONFIDENCE = 0.9

export function normalizeTimeWindow(raw: string | undefined): TimeWindow {
  if (raw === 'last2' || raw === 'tracked') return raw
  return 'current'
}

export function timeWindowHref(window: TimeWindow): string {
  return `?period=${window}`
}

function trackedWindowStart(currentCycle: number): number {
  return currentCycle - 8
}

function cyclesInWindow(
  item: CampaignEntityIndexItem,
  window: TimeWindow,
  currentCycle: number,
) {
  const trackedStart = trackedWindowStart(currentCycle)
  if (window === 'current') {
    return item.cycleBars.filter((bar) => bar.cycle === currentCycle)
  }
  if (window === 'last2') {
    return item.cycleBars.filter(
      (bar) => bar.cycle >= currentCycle - 2 && bar.cycle <= currentCycle,
    )
  }
  return item.cycleBars.filter(
    (bar) => bar.cycle >= trackedStart && bar.cycle <= currentCycle,
  )
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

function hasActivity(
  item: CampaignEntityIndexItem,
  window: TimeWindow,
  currentCycle: number,
): boolean {
  const totals = totalsInWindow(item, window, currentCycle)
  return totals.received + totals.given > 0
}

function periodText(window: TimeWindow, currentCycle: number): string {
  if (window === 'current') return `in the ${currentCycle} cycle`
  if (window === 'last2') {
    return `across the ${currentCycle - 2} and ${currentCycle} cycles`
  }
  return `across the ${currentCycle - 8}–${currentCycle} tracked cycles`
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

function confidenceLabel(score: number): string {
  return score >= 0.95 ? 'Verified' : 'High confidence'
}

function isPublicReady(item: CampaignEntityIndexItem): boolean {
  return Boolean(
    item.source_url &&
      item.extracted_at &&
      item.source_tier === 1 &&
      Number.isFinite(item.confidence_score) &&
      item.confidence_score >= PUBLIC_CONFIDENCE,
  )
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
    <article className="rounded-lg border border-slate-200 bg-white p-4">
      <Link
        href={item.href}
        className="group flex min-h-11 items-start gap-4 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-navy focus-visible:ring-offset-2"
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

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
        <a
          href={item.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-h-11 items-center rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-navy focus-visible:ring-offset-2"
        >
          <SourceBadge
            tier={item.source_tier}
            source={item.source_label}
            extractedAt={item.extracted_at}
          />
        </a>
        <span className="text-sm text-slate-600">
          {confidenceLabel(item.confidence_score)}
        </span>
      </div>
    </article>
  )
}

export default function CampaignEntityIndexClient(
  props: CampaignEntityIndexClientProps,
) {
  const searchParams = useSearchParams()
  return (
    <CampaignEntityIndexView
      {...props}
      selectedWindow={normalizeTimeWindow(searchParams.get('period') ?? undefined)}
    />
  )
}

export function CampaignEntityIndexView({
  items,
  currentCycle,
  singularLabel,
  pluralLabel,
  selectedWindow,
}: CampaignEntityIndexViewProps) {
  const publicItems = items.filter(isPublicReady)
  const trackedItems = publicItems.filter((item) =>
    hasActivity(item, 'tracked', currentCycle),
  )
  const visibleItems = trackedItems
    .filter((item) => hasActivity(item, selectedWindow, currentCycle))
    .slice()
    .sort((left, right) =>
      left.name.localeCompare(right.name, 'en-US', { sensitivity: 'base' }),
    )
  const hiddenWithinTrackedCount =
    selectedWindow === 'tracked'
      ? 0
      : trackedItems.length - visibleItems.length
  const olderOnlyCount = publicItems.filter(
    (item) =>
      item.activity_before_tracked_window &&
      !hasActivity(item, 'tracked', currentCycle),
  ).length
  const hasWithheldRows = publicItems.length !== items.length

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
            const active = selectedWindow === option.value
            return (
              <Link
                key={option.value}
                href={timeWindowHref(option.value)}
                aria-current={active ? 'page' : undefined}
                scroll={false}
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
              </Link>
            )
          })}
        </div>
      </fieldset>

      <div className="mb-4 space-y-2 text-sm text-slate-600">
        <p role="status" aria-live="polite">
          Showing <strong>{visibleItems.length}</strong>{' '}
          {visibleItems.length === 1 ? singularLabel : pluralLabel} with
          reported activity {periodText(selectedWindow, currentCycle)}.
        </p>
        {hiddenWithinTrackedCount > 0 && (
          <Link
            href={timeWindowHref('tracked')}
            scroll={false}
            className="inline-flex min-h-11 items-center font-medium text-civic-navy underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-navy focus-visible:ring-offset-2"
          >
            Show {hiddenWithinTrackedCount} more from the last five cycles
          </Link>
        )}
        {olderOnlyCount > 0 && (
          <p>
            {olderOnlyCount} additional{' '}
            {olderOnlyCount === 1 ? singularLabel : pluralLabel}{' '}
            {olderOnlyCount === 1 ? 'has' : 'have'} reported activity only
            before the five-cycle view and{' '}
            {olderOnlyCount === 1 ? 'is' : 'are'} not included in these
            filters.
          </p>
        )}
        {hasWithheldRows && (
          <p>
            Entries without complete provenance or at least 90% confidence are
            withheld from this summary.
          </p>
        )}
      </div>

      {visibleItems.length > 0 ? (
        <div className="grid gap-3">
          {visibleItems.map((item) => (
            <CampaignEntityRow
              key={item.id}
              item={item}
              window={selectedWindow}
              currentCycle={currentCycle}
            />
          ))}
        </div>
      ) : (
        <div
          role="status"
          className="rounded-lg border border-slate-200 bg-slate-50 p-6 text-center text-base text-slate-600"
        >
          No fully attributed, high-confidence {pluralLabel} have reported
          activity in this time period.
        </div>
      )}
    </section>
  )
}
