'use client'

import { useState } from 'react'
import Link from 'next/link'
import type { ContributionNarrativeData } from '@/lib/types'
import ConfidenceBadge from './ConfidenceBadge'

interface ContributionNarrativeProps {
  narrative: ContributionNarrativeData
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

function formatDateRange(earliest: string, latest: string): string {
  const start = new Date(earliest + 'T00:00:00')
  const end = new Date(latest + 'T00:00:00')
  const startYear = start.getFullYear()
  const endYear = end.getFullYear()
  if (startYear === endYear) return String(startYear)
  return `${startYear}–${endYear}`
}

/**
 * ContributionNarrative — S14 C1
 *
 * Renders a single campaign contribution record as a plain-language sentence.
 * Follows the "contribution first, vote second" design principle from the spec.
 *
 * The sentence structure is deliberate: leading with the financial record and
 * following with the vote prevents the structural implication of causation
 * that "voted yes → received $X" creates. This is the single most important
 * framing decision in the influence map (per Research C: defamation by implication).
 */
export default function ContributionNarrative({ narrative }: ContributionNarrativeProps) {
  const [showDetails, setShowDetails] = useState(false)

  const n = narrative
  const dateRange = formatDateRange(n.earliest_date, n.latest_date)
  const pctLabel = n.percentage_of_fundraising > 0
    ? ` (${n.percentage_of_fundraising}% of total fundraising)`
    : ''

  // Build the main sentence — contribution first, vote second
  const isVendorExpenditure = n.flag_type === 'donor_vendor_expenditure'
  const isLlcChain = n.flag_type === 'llc_ownership_chain'
  const isEmployerMatch = n.entity_relationship === 'employer'

  // Count distinct individual donors in the contribution records (for employer aggregation)
  const uniqueDonors = new Set(n.contributions.map(c => c.donor_name.toLowerCase())).size

  let contributionSentence: string
  if (isVendorExpenditure && isEmployerMatch && n.entity_name) {
    // Vendor matched via employer — contributions from employees of the vendor
    const donorLabel = uniqueDonors > 1
      ? `${uniqueDonors} individuals employed by ${n.entity_name}`
      : `an individual employed by ${n.entity_name}`
    contributionSentence = `According to public filings, ${donorLabel} made ${n.contribution_count} contribution${n.contribution_count === 1 ? '' : 's'} totaling ${formatCurrency(n.total_contributed)} to ${n.official_name}'s campaign committee between ${dateRange}${pctLabel}.`
  } else if (isLlcChain && n.entity_name) {
    // LLC/org chain — donor linked through organization
    contributionSentence = n.contribution_count === 1
      ? `According to public filings, ${n.donor_name} (linked to ${n.entity_name}) contributed ${formatCurrency(n.total_contributed)} to the ${n.contributions[0]?.committee_name ?? 'campaign committee'} in ${dateRange}${pctLabel}.`
      : `According to public filings, ${n.donor_name} (linked to ${n.entity_name}) made ${n.contribution_count} contributions totaling ${formatCurrency(n.total_contributed)} to ${n.official_name}'s campaign committee between ${dateRange}${pctLabel}.`
  } else {
    contributionSentence = n.contribution_count === 1
      ? `According to NetFile filings, ${n.donor_name} contributed ${formatCurrency(n.total_contributed)} to the ${n.contributions[0]?.committee_name ?? 'campaign committee'} in ${dateRange}${pctLabel}.`
      : `According to NetFile filings, ${n.donor_name} made ${n.contribution_count} contributions totaling ${formatCurrency(n.total_contributed)} to ${n.official_name}'s campaign committee between ${dateRange}${pctLabel}.`
  }

  // Vendor expenditure context — the key enrichment for donor_vendor_expenditure flags
  const expenditureSentence = isVendorExpenditure && n.vendor_expenditure_total && n.entity_name
    ? `City expenditure records show ${n.entity_name} received ${formatCurrency(n.vendor_expenditure_total)} in city payments${n.vendor_expenditure_count ? ` across ${n.vendor_expenditure_count} transactions` : ''}.`
    : null

  const voteSentence = n.vote_choice
    ? `Council Member ${n.official_name} voted ${n.vote_choice.toLowerCase()} on this item.`
    : `Council Member ${n.official_name}'s vote was not recorded on this item.`

  // Context: same-way voters without contributions from this source
  const contextDonorLabel = isEmployerMatch && n.entity_name
    ? `employees of ${n.entity_name}`
    : n.donor_name
  const contextSentence = n.vote_choice && n.same_way_voter_count > 0
    ? `${n.same_way_without_contribution} of ${n.same_way_voter_count} other council members who voted ${n.vote_choice.toLowerCase()} received no contributions from ${contextDonorLabel}.`
    : null

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4 mb-3">
      {/* Main narrative */}
      <div className="space-y-1.5">
        <p className="text-base text-slate-700 leading-relaxed">
          {contributionSentence}
        </p>
        {expenditureSentence && (
          <p className="text-base text-slate-700 leading-relaxed">
            {expenditureSentence}
          </p>
        )}
        <p className="text-base text-slate-700 leading-relaxed">
          {voteSentence}
        </p>
        {contextSentence && (
          <p className="text-base text-slate-500 leading-relaxed">
            {contextSentence}
          </p>
        )}
      </div>

      {/* Meta line */}
      <div className="flex flex-wrap items-center gap-2 mt-3 text-xs text-slate-500">
        <ConfidenceBadge confidence={n.confidence} />
        <span>·</span>
        <span>{n.source_tier} ({n.flag_type === 'donor_vendor_expenditure' ? 'NetFile + City Expenditures' : n.flag_type === 'llc_ownership_chain' ? 'NetFile + Entity Registry' : 'NetFile'})</span>
        <span>·</span>
        <span>{n.source_date}</span>
        {n.source_url && (
          <>
            <span>·</span>
            <a
              href={n.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-civic-navy hover:underline"
            >
              View filing
            </a>
          </>
        )}
      </div>

      {/* Per-connection disclaimer (expandable) */}
      <div className="mt-2">
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="text-xs text-slate-400 hover:text-slate-600 transition-colors"
        >
          {showDetails ? '▾ Hide details' : '▸ Evidence details'} ({n.contribution_count} {n.contribution_count === 1 ? 'record' : 'records'})
        </button>

        {showDetails && (
          <div className="mt-2 space-y-2">
            {/* Per-connection disclaimer */}
            <p className="text-xs text-slate-400 italic leading-relaxed">
              This information comes from public campaign finance filings.
              A contribution to a campaign does not imply that the contributor
              influenced the officeholder&apos;s decisions.
            </p>

            {/* Individual contribution records */}
            <div className="border-t border-slate-100 pt-2">
              {n.contributions.map(c => (
                <div key={c.contribution_id} className="flex items-center justify-between py-1 text-xs text-slate-600">
                  <span>
                    {formatCurrency(c.amount)} · {c.contribution_date}
                    {isEmployerMatch
                      ? <span className="text-slate-400"> ({c.donor_name})</span>
                      : c.donor_employer && <span className="text-slate-400"> ({c.donor_employer})</span>
                    }
                  </span>
                  <span className="text-slate-400">{c.source}</span>
                </div>
              ))}
            </div>

            {/* Official profile link */}
            <Link
              href={`/council/${n.official_slug}`}
              className="inline-block text-xs text-civic-navy hover:underline mt-1"
            >
              View {n.official_name}&apos;s full profile →
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}
