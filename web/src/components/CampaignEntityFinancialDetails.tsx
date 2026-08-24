import PACDonorTable from '@/app/pac/[slug]/PACDonorTable'
import PACIndependentExpendituresTable from '@/app/pac/[slug]/PACIndependentExpendituresTable'
import PACOutgoingTable from '@/app/pac/[slug]/PACOutgoingTable'
import { CampaignEntitySection } from '@/components/CampaignEntityProfile'
import type { EntityUrlMap } from '@/components/EntityLink'
import type {
  PACContributionRow,
  PACIndependentExpenditureRow,
  PACOutgoingRow,
} from '@/lib/types'

interface CampaignEntityFinancialDetailsProps {
  /** Undefined for donor organizations, which do not have an incoming-money view. */
  incoming?: PACContributionRow[]
  outgoing: PACOutgoingRow[]
  independentExpenditures: PACIndependentExpenditureRow[]
  entityDisplay: string
  entityNoun: 'committee' | 'organization'
  entityUrlMap: EntityUrlMap | null
}

function fmt(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

function sumAmounts(rows: Array<{ amount: number }>): number {
  return rows.reduce((total, row) => total + row.amount, 0)
}

export default function CampaignEntityFinancialDetails({
  incoming,
  outgoing,
  independentExpenditures,
  entityDisplay,
  entityNoun,
  entityUrlMap,
}: CampaignEntityFinancialDetailsProps) {
  const outgoingRecipients = new Set(
    outgoing.map((row) => row.recipient_committee_name),
  )
  const ieCandidates = new Set(
    independentExpenditures
      .map((row) => row.candidate_name)
      .filter((name): name is string => Boolean(name)),
  )

  return (
    <>
      {incoming !== undefined && (
        <CampaignEntitySection
          title="Money received"
          summary={
            incoming.length > 0 ? (
              <>
                The sortable filing detail below lists named donors to{' '}
                <strong>{entityDisplay}</strong>, with each donor&apos;s reported
                total, contribution count, and filing dates.
              </>
            ) : (
              <>
                No incoming contributions are available for{' '}
                <strong>{entityDisplay}</strong> in the tracked filings.
              </>
            )
          }
        >
          {incoming.length > 0 && (
            <>
              <PACDonorTable
                contributions={incoming}
                pacUrlMap={entityUrlMap}
              />
              <p className="text-xs text-slate-500 mt-4 pt-3 border-t border-slate-100 leading-relaxed">
                These rows come from contribution records filed by this
                {` ${entityNoun}`} in NetFile or CAL-ACCESS.
              </p>
            </>
          )}
        </CampaignEntitySection>
      )}

      <CampaignEntitySection
        title="Money given"
        summary={
          outgoing.length > 0 ? (
            <>
              <strong>{entityDisplay}</strong> appears as a donor on{' '}
              <strong>{outgoing.length.toLocaleString()}</strong>{' '}
              contribution record{outgoing.length === 1 ? '' : 's'} totaling{' '}
              <strong>{fmt(sumAmounts(outgoing))}</strong> across{' '}
              <strong>{outgoingRecipients.size.toLocaleString()}</strong>{' '}
              recipient committee{outgoingRecipients.size === 1 ? '' : 's'}.
            </>
          ) : (
            <>
              No contributions from <strong>{entityDisplay}</strong> appear in
              the tracked recipient filings.
            </>
          )
        }
      >
        {outgoing.length > 0 && (
          <>
            <PACOutgoingTable
              outgoing={outgoing}
              pacUrlMap={entityUrlMap}
            />
            <p className="text-xs text-slate-500 mt-4 pt-3 border-t border-slate-100 leading-relaxed">
              These rows come from recipient committees&apos; filings that
              listed this {entityNoun} as a donor. Committee-name matching can
              join similarly named organizations; the official filing remains
              the authoritative record.
            </p>
          </>
        )}
      </CampaignEntitySection>

      {independentExpenditures.length > 0 && (
        <CampaignEntitySection
          title="Independent spending"
          summary={
            <>
              Official filings report{' '}
              <strong>{fmt(sumAmounts(independentExpenditures))}</strong> in{' '}
              <strong>{independentExpenditures.length.toLocaleString()}</strong>{' '}
              independent expenditure
              {independentExpenditures.length === 1 ? '' : 's'} by{' '}
              <strong>{entityDisplay}</strong>
              {ieCandidates.size > 0 ? (
                <>
                  {' '}naming <strong>{ieCandidates.size}</strong> candidate
                  {ieCandidates.size === 1 ? '' : 's'} as supported or opposed
                </>
              ) : null}
              . These payments went to vendors, not to candidate campaigns.
            </>
          }
        >
          <PACIndependentExpendituresTable
            expenditures={independentExpenditures}
            pacUrlMap={entityUrlMap}
          />
          <p className="text-xs text-slate-500 mt-4 pt-3 border-t border-slate-100 leading-relaxed">
            Data from CAL-ACCESS Form 460 Schedule D and Form 496 filings
            (FPPC, Tier 1). Each row reflects a reported payment to a vendor
            that names a candidate as supported or opposed.
          </p>
        </CampaignEntitySection>
      )}
    </>
  )
}
