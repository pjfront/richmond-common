'use client'

/**
 * EconomicInterestsSection — S28.1 (interest-profiles spec, build order 1).
 *
 * Council-profile "Financial Disclosures" section, narrative-first per D6/T7:
 * a sentence-led lede in the PAC V2 grammar (orientation → most-recent-filing
 * action → history context), with the year-tabbed detail table below on
 * expansion. The "filed, but listed no reportable interests" state is
 * first-class — that absence is a meaningful Tier 1 fact, not an empty state.
 *
 * Lede privacy posture: descriptions in the detail table carry whatever the
 * filer reported (Schedule B includes property addresses — public record,
 * Gov. Code §81008); the lede itself only ever names cities and counts.
 * Whether the table should roll street addresses up to city level is an
 * operator framing call at graduation review (see operator-review-queue.yaml).
 *
 * D2/U13: counts appear in the lede only when the filing's confidence_score
 * is >= 0.90. API-loaded filings are 1.0 (structured portal line items, not
 * model output); pre-S28.1 Claude-extracted rows carry their own scores.
 */

import type { EconomicInterest, Form700Filing } from '@/lib/types'
import { CIVIC_GLOSSARY } from '@/data/civic-glossary'
import CivicTerm from './CivicTerm'
import SourceBadge from './SourceBadge'
import EconomicInterestsTable from './EconomicInterestsTable'

const CONFIDENCE_SUMMARY_THRESHOLD = 0.9

const STATEMENT_LABELS: Record<string, string> = {
  annual: 'annual filing',
  assuming_office: 'filing on assuming office',
  leaving_office: 'filing on leaving office',
  candidate: 'candidate filing',
  amendment: 'amended filing',
}

interface EconomicInterestsSectionProps {
  filings: Form700Filing[]
  interests: EconomicInterest[]
  officialName: string
}

/** "3 properties (Richmond, San Pablo)", "income from 2 sources", ... */
function summarizeInterests(interests: EconomicInterest[]): string {
  const byType = new Map<string, EconomicInterest[]>()
  for (const i of interests) {
    const arr = byType.get(i.interest_type) ?? []
    arr.push(i)
    byType.set(i.interest_type, arr)
  }

  const fragments: string[] = []
  const properties = byType.get('real_property') ?? []
  if (properties.length > 0) {
    const cities = Array.from(
      new Set(properties.map((p) => p.location).filter(Boolean))
    )
    const where = cities.length > 0 ? ` (${cities.join(', ')})` : ''
    fragments.push(
      properties.length === 1
        ? `an interest in real property${where}`
        : `interests in ${properties.length} properties${where}`
    )
  }
  const income = byType.get('income') ?? []
  if (income.length > 0) {
    fragments.push(
      income.length === 1 ? 'income from 1 source' : `income from ${income.length} sources`
    )
  }
  const investments = (byType.get('investment') ?? []).concat(
    byType.get('business_position') ?? []
  )
  if (investments.length > 0) {
    fragments.push(
      investments.length === 1
        ? '1 investment or business position'
        : `${investments.length} investments or business positions`
    )
  }
  const gifts = byType.get('gift') ?? []
  if (gifts.length > 0) {
    fragments.push(gifts.length === 1 ? '1 gift' : `${gifts.length} gifts`)
  }
  const travel = byType.get('travel') ?? []
  if (travel.length > 0) {
    fragments.push(
      travel.length === 1 ? '1 travel payment' : `${travel.length} travel payments`
    )
  }

  if (fragments.length === 0) return ''
  if (fragments.length === 1) return fragments[0]
  return `${fragments.slice(0, -1).join(', ')}, and ${fragments[fragments.length - 1]}`
}

function periodLabel(filing: Form700Filing): string {
  const start = filing.period_start?.slice(0, 4)
  const end = filing.period_end?.slice(0, 4)
  if (start && end && start === end) return `covering ${start}`
  if (start && end) return `covering ${start}–${end}`
  return ''
}

export default function EconomicInterestsSection({
  filings,
  interests,
  officialName,
}: EconomicInterestsSectionProps) {
  const glossary = CIVIC_GLOSSARY['form-700']
  const latest = filings[0] ?? null
  const latestInterests = latest
    ? interests.filter((i) => i.filing_id === latest.id)
    : []

  const heading = (
    <h2 className="text-xl font-semibold text-slate-800 mb-3">
      Financial Disclosures
      {filings.length > 0 && (
        <span className="text-slate-400 font-normal text-base ml-2">
          ({filings.length} {filings.length === 1 ? 'filing' : 'filings'})
        </span>
      )}
    </h2>
  )

  // U9: explicit empty state — say why nothing is here, not just nothing.
  if (!latest) {
    return (
      <section id="disclosures" className="mb-8 scroll-mt-20">
        {heading}
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <p className="text-sm text-slate-600">
            No{' '}
            <CivicTerm
              term={glossary.term}
              category={glossary.category}
              definition={glossary.definition}
            >
              Form 700 financial disclosure
            </CivicTerm>{' '}
            filings for {officialName} are in our records. Filings are collected
            from the NetFile SEI public portal; officials who assumed office
            recently may not appear on the portal yet.
          </p>
        </div>
      </section>
    )
  }

  const filedLabel = STATEMENT_LABELS[latest.statement_type ?? ''] ?? 'filing'
  const period = periodLabel(latest)
  const filingRef = `their most recent ${filedLabel} (${latest.filing_year}${period ? `, ${period}` : ''})`
  const confidence = Number(latest.confidence_score ?? 0)
  const summary = summarizeInterests(latestInterests)

  let lede: React.ReactNode
  if (latestInterests.length === 0) {
    // First-class "filed, declared nothing reportable" state — Tier 1 fact.
    lede = (
      <>
        In {filingRef}, {officialName} listed{' '}
        <strong className="font-semibold">no reportable financial interests</strong>.
      </>
    )
  } else if (confidence >= CONFIDENCE_SUMMARY_THRESHOLD && summary) {
    lede = (
      <>
        In {filingRef}, {officialName} reported {summary}. Details, including
        earlier filings, are below.
      </>
    )
  } else {
    // D2: below-threshold extractions never feed summary counts.
    lede = (
      <>
        {officialName}&apos;s most recent {filedLabel} ({latest.filing_year}) is
        on record. The extracted details below have not met our verification
        threshold — review recommended.
      </>
    )
  }

  const historyYears = filings.map((f) => f.filing_year).filter(Boolean)
  const oldestYear = historyYears.length > 0 ? Math.min(...historyYears) : null

  return (
    <section id="disclosures" className="mb-8 scroll-mt-20">
      {heading}
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <p className="text-sm text-slate-700 mb-2">
          Every council member files an annual{' '}
          <CivicTerm
            term={glossary.term}
            category={glossary.category}
            definition={glossary.definition}
          >
            financial disclosure
          </CivicTerm>{' '}
          listing investments, property, income, and gifts. {lede}
        </p>
        {oldestYear && filings.length > 1 && (
          <p className="text-xs text-slate-500 mb-3">
            {filings.length} filings on record since {oldestYear}.
          </p>
        )}
        <div className="mb-4">
          <SourceBadge
            tier={1}
            source="NetFile SEI / FPPC Form 700 filings"
            extractedAt={latest.extracted_at}
          />
        </div>

        {interests.length > 0 && <EconomicInterestsTable interests={interests} />}

        <p className="text-xs text-slate-400 mt-4">
          Interests are the filer&apos;s own entries from {officialName}&apos;s
          Form 700 (Statement of Economic Interests) filings on the NetFile SEI
          public portal. A reported interest is a required disclosure, not an
          indication of wrongdoing.
        </p>
      </div>
    </section>
  )
}
