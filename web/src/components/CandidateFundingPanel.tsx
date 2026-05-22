import CivicTerm from './CivicTerm'
import SourceBadge from './SourceBadge'
import type {
  CandidateFundingBreakdown,
  CandidateFundingBucket,
  CandidateIESupporter,
  ContributorTypeBucket,
} from '@/lib/types'

interface CandidateFundingPanelProps {
  candidateName: string
  officeSought: string
  breakdown: CandidateFundingBreakdown | null
  ieSupporters: CandidateIESupporter[]
}

const BUCKET_LABELS: Record<ContributorTypeBucket, { plain: string; technical: string }> = {
  individual: { plain: 'From individual donors', technical: 'Schedule A individuals (FPPC entity_cd IND)' },
  union: { plain: 'From labor unions', technical: 'Union PACs and labor councils' },
  corporate: { plain: 'From for-profit companies', technical: 'Incorporated for-profit entities (LLC, Inc, Corp)' },
  pac_ie: { plain: 'From other political committees', technical: 'Other PACs (party committees, ballot-measure committees)' },
  other: { plain: 'Other or unclassified', technical: 'Contributors that could not be classified' },
}

function fmtUSD(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
}

function fmtCount(n: number): string {
  return n.toLocaleString('en-US')
}

function pctOfTotal(part: number, total: number): string {
  if (total <= 0) return '0%'
  const pct = (part / total) * 100
  if (pct < 1) return '<1%'
  return `${Math.round(pct)}%`
}

/** Build the auto-generated narrative paragraph. Sentence-based, no charts,
 *  no jargon, no em-dashes. Each candidate gets the same structure so
 *  comparison stays apples-to-apples. */
function buildNarrative(
  candidateName: string,
  office: string,
  breakdown: CandidateFundingBreakdown,
  ieSupporters: CandidateIESupporter[],
): string {
  const buckets = new Map<ContributorTypeBucket, CandidateFundingBucket>()
  for (const b of breakdown.buckets) buckets.set(b.contributor_type, b)

  const individual = buckets.get('individual')
  const union = buckets.get('union')
  const corporate = buckets.get('corporate')
  const otherPac = buckets.get('pac_ie')

  const parts: string[] = []

  if (individual) {
    parts.push(
      `${candidateName} has raised ${fmtUSD(breakdown.total_raised)} for ${office} this cycle, ` +
        `with ${fmtUSD(individual.total_amount)} coming from ${fmtCount(individual.contribution_count)} individual donations.`,
    )
  } else {
    parts.push(`${candidateName} has raised ${fmtUSD(breakdown.total_raised)} for ${office} this cycle.`)
  }

  if (union) {
    const topNames = union.top_donors.slice(0, 3).map((d) => d.name).join(', ')
    const tail = union.top_donors.length > 3 ? ', and others' : ''
    parts.push(
      `Labor unions contributed ${fmtUSD(union.total_amount)} across ${fmtCount(union.contribution_count)} ` +
        `contribution${union.contribution_count === 1 ? '' : 's'}${topNames ? ` (${topNames}${tail})` : ''}.`,
    )
  }

  if (corporate) {
    const topNames = corporate.top_donors.slice(0, 3).map((d) => d.name).join(', ')
    parts.push(
      `For-profit companies contributed ${fmtUSD(corporate.total_amount)}${topNames ? ` (${topNames})` : ''}.`,
    )
  }

  if (otherPac) {
    parts.push(`Other political committees contributed ${fmtUSD(otherPac.total_amount)}.`)
  }

  // IE sentence: surface the biggest supporter only to keep the
  // narrative tight. The full IE list shows below in its own section.
  const supporting = ieSupporters.filter((s) => s.support_or_oppose !== 'O')
  if (supporting.length > 0) {
    const top = supporting[0]
    const spent = top.ie_funds_spent
    const raised = top.ie_funds_raised
    let ieClause: string
    if (spent > 0 && raised > 0) {
      ieClause =
        `has spent ${fmtUSD(spent)} and raised an additional ${fmtUSD(raised)} supporting ${candidateName}`
    } else if (spent > 0) {
      ieClause = `has spent ${fmtUSD(spent)} on materials supporting ${candidateName}`
    } else if (raised > 0) {
      ieClause = `has raised ${fmtUSD(raised)} to spend supporting ${candidateName}, with no expenditures filed yet`
    } else {
      ieClause = `is registered to support ${candidateName}`
    }
    const moreCount = supporting.length - 1
    const moreClause = moreCount > 0 ? ` ${moreCount} other independent committee${moreCount === 1 ? '' : 's'} also report${moreCount === 1 ? 's' : ''} activity for ${candidateName}.` : ''
    parts.push(
      `A separate independent expenditure committee, ${top.ie_committee_name}, ${ieClause}.${moreClause}`,
    )
  }

  return parts.join(' ')
}

/** Sentence describing IE activity in the supporter list row. */
function ieSupporterSentence(s: CandidateIESupporter, candidateName: string): string {
  const direction = s.support_or_oppose === 'O' ? 'opposing' : 'supporting'
  const fragments: string[] = []
  if (s.ie_funds_spent > 0) {
    fragments.push(`spent ${fmtUSD(s.ie_funds_spent)} ${direction} ${candidateName}`)
  }
  if (s.ie_funds_raised > 0) {
    fragments.push(`raised ${fmtUSD(s.ie_funds_raised)} for the committee`)
  }
  if (fragments.length === 0) return `Registered ${direction} ${candidateName}, no activity filed yet.`
  return fragments.join(', ') + '.'
}

export default function CandidateFundingPanel({
  candidateName,
  officeSought,
  breakdown,
  ieSupporters,
}: CandidateFundingPanelProps) {
  if (!breakdown) {
    return (
      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-civic-navy">{candidateName}</h2>
        <p className="mt-2 text-sm text-civic-slate">
          No contributions filed yet for {candidateName} this cycle.
        </p>
      </section>
    )
  }

  const narrative = buildNarrative(candidateName, officeSought, breakdown, ieSupporters)
  const totalRaised = breakdown.total_raised

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 sm:p-6">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold text-civic-navy">{candidateName}</h2>
        <span className="text-sm text-civic-slate">
          {officeSought} candidate, {fmtCount(breakdown.donor_count)} donors
        </span>
      </header>

      {/* Narrative paragraph (D6 narrative-over-numbers) */}
      <p className="mt-3 text-sm leading-relaxed text-civic-slate">{narrative}</p>

      {/* Breakdown table */}
      <div className="mt-5">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-civic-slate">
          Where the money came from
        </h3>
        <table className="mt-2 w-full text-sm">
          <thead className="text-left text-xs text-civic-slate/70">
            <tr>
              <th className="py-1 pr-2 font-normal">Source</th>
              <th className="py-1 pr-2 font-normal text-right">Amount</th>
              <th className="py-1 pr-2 font-normal text-right">Share</th>
              <th className="py-1 font-normal text-right">Contributions</th>
            </tr>
          </thead>
          <tbody>
            {breakdown.buckets.map((bucket) => {
              const label = BUCKET_LABELS[bucket.contributor_type]
              const topInline =
                bucket.contributor_type === 'individual' || bucket.top_donors.length === 0
                  ? null
                  : bucket.top_donors
                      .slice(0, 3)
                      .map((d) => d.name)
                      .join(', ')
              return (
                <tr key={bucket.contributor_type} className="border-t border-slate-100 align-top">
                  <td className="py-2 pr-2 text-civic-slate">
                    <CivicTerm term={label.technical} definition={label.technical}>
                      {label.plain}
                    </CivicTerm>
                    {topInline && (
                      <div className="text-xs text-civic-slate/70 mt-0.5">{topInline}</div>
                    )}
                  </td>
                  <td className="py-2 pr-2 text-right font-medium text-civic-navy tabular-nums">
                    {fmtUSD(bucket.total_amount)}
                  </td>
                  <td className="py-2 pr-2 text-right text-civic-slate tabular-nums">
                    {pctOfTotal(bucket.total_amount, totalRaised)}
                  </td>
                  <td className="py-2 text-right text-civic-slate tabular-nums">
                    {fmtCount(bucket.contribution_count)}
                  </td>
                </tr>
              )
            })}
            <tr className="border-t border-slate-200 bg-slate-50">
              <td className="py-2 pr-2 font-semibold text-civic-navy">Total raised</td>
              <td className="py-2 pr-2 text-right font-semibold text-civic-navy tabular-nums">
                {fmtUSD(totalRaised)}
              </td>
              <td className="py-2 pr-2 text-right text-civic-slate tabular-nums">100%</td>
              <td className="py-2 text-right font-semibold text-civic-navy tabular-nums">
                {fmtCount(breakdown.contribution_count)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Independent expenditure supporters */}
      {ieSupporters.length > 0 && (
        <div className="mt-5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-civic-slate">
            <CivicTerm
              term="Independent Expenditure"
              category="FPPC §82031"
              definition="Money spent to support or oppose a candidate without coordinating with the candidate's campaign. Filed by separate committees, not subject to per-candidate contribution limits."
            >
              Independent committees
            </CivicTerm>
          </h3>
          <ul className="mt-2 space-y-3">
            {ieSupporters.map((s) => (
              <li key={s.ie_committee_id ?? s.ie_committee_name} className="text-sm">
                <div className="font-medium text-civic-navy">{s.ie_committee_name}</div>
                <div className="text-civic-slate">{ieSupporterSentence(s, candidateName)}</div>
                {s.ie_top_funders.length > 0 && (
                  <div className="mt-1 text-xs text-civic-slate/70">
                    Funded by: {s.ie_top_funders.map((f) => `${f.name} (${fmtUSD(f.total)})`).join('; ')}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Source attribution (D1, D5) */}
      <footer className="mt-5 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
        <SourceBadge
          tier={1}
          source="NetFile via Richmond City Clerk"
          extractedAt={breakdown.last_updated_at ?? breakdown.last_contribution_date}
        />
        <span className="text-xs text-civic-slate/70">
          Auto-generated from campaign finance filings. Updates as new filings post.
        </span>
      </footer>
    </section>
  )
}
