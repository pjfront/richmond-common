/**
 * Public political-committee profile.
 *
 * Uses the same sentence-first profile grammar as union and company pages:
 * orientation, one filing-based summary, then sortable receipt detail.
 */

import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import {
  getPACBySlug,
  getPACList,
  getPACContributions,
  getPACOutgoing,
  getPACIndependentExpenditures,
} from '@/lib/queries'
import CampaignEntityFinancialDetails from '@/components/CampaignEntityFinancialDetails'
import CampaignEntityProfile from '@/components/CampaignEntityProfile'
import type { EntityUrlMap } from '@/components/EntityLink'

interface PageProps {
  params: Promise<{ slug: string }>
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params
  const pac = await getPACBySlug(slug)
  if (!pac) return { title: 'Committee not found' }
  const display = displayName(pac.name)
  return {
    title: `${display}: Political committee`,
    description: pac.sponsor_disclosure
      ? `${display} (${pac.sponsor_disclosure}). Public campaign-finance filings.`
      : `${display}: Richmond political committee filings.`,
  }
}

export default async function PACProfilePage({ params }: PageProps) {
  const { slug } = await params
  const pac = await getPACBySlug(slug)
  if (!pac) notFound()

  const [pacList, contributions, outgoing, independentExpenditures] =
    await Promise.all([
      getPACList(),
      getPACContributions(pac.member_ids),
      getPACOutgoing(pac.name),
      getPACIndependentExpenditures(pac.name),
    ])

  // Build name→URL map for cross-linking (S28.5). Maps both the
  // full registered name and the display name (before comma) since
  // donor records use either form.
  const pacUrlMap: EntityUrlMap = {}
  for (const p of pacList) {
    const key = p.name.toLowerCase().trim()
    pacUrlMap[key] = `/pac/${p.slug}`
    const siblingDisplay = p.name.split(',')[0].trim().toLowerCase()
    if (siblingDisplay !== key) {
      pacUrlMap[siblingDisplay] = `/pac/${p.slug}`
    }
  }

  const display = displayName(pac.name)

  return (
    <CampaignEntityProfile
      backHref="/pac"
      backLabel="All political committees"
      name={display}
      filedName={pac.name}
      typeLabel="Political committee"
      filingId={pac.filer_id}
      sponsorDisclosure={pac.sponsor_disclosure}
      summary={renderLede(
        pac,
        display,
        outgoing.length,
        independentExpenditures,
      )}
      sourceNote={
        <>
          Sponsor descriptions come from the committee name as filed. The
          Chevron disclosure for Coalition for Richmond&apos;s Future follows
          the project&apos;s source-disclosure rule.
        </>
      }
    >
      <CampaignEntityFinancialDetails
        incoming={contributions}
        outgoing={outgoing}
        independentExpenditures={independentExpenditures}
        entityDisplay={display}
        entityNoun="committee"
        entityUrlMap={pacUrlMap}
      />
    </CampaignEntityProfile>
  )
}

// ─── Helpers ───────────────────────────────────────────────────────────

/** Trim the verbose registered name down to a display label.
 *  "Foo Committee, sponsored by Bar" → "Foo Committee". */
function displayName(name: string): string {
  const beforeComma = name.split(',')[0].trim()
  return beforeComma.length >= 6 ? beforeComma : name
}

// ─── Narrative builders ────────────────────────────────────────────────

function renderLede(
  pac: { total_raised: number; donor_count: number; earliest_contribution_date: string | null; latest_contribution_date: string | null },
  display: string,
  outgoingCount: number,
  ieRows: Array<{ amount: number; candidate_name: string | null; support_or_oppose: string | null }>,
): ReactNode {
  const activities = [
    pac.total_raised > 0 ? 'money received' : null,
    outgoingCount > 0 ? 'contributions to other committees' : null,
    ieRows.length > 0 ? 'independent expenditures' : null,
  ].filter((activity): activity is string => Boolean(activity))

  if (activities.length === 0) {
    return <>Open the structured detail below to review the available public campaign records for <strong>{display}</strong>.</>
  }

  const lastActivity = activities.at(-1)
  const leadingActivities = activities.slice(0, -1)
  return (
    <>
      Public campaign records show{' '}
      {leadingActivities.length > 0 ? `${leadingActivities.join(', ')} and ` : ''}
      {lastActivity} for <strong>{display}</strong>. The structured detail below
      provides reported amounts, dates, recipients, and direction when the
      source record supplies it.
    </>
  )
}

