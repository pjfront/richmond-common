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

export default function CampaignEntityFinancialDetails({
  incoming,
  outgoing,
  independentExpenditures,
  entityDisplay,
  entityNoun,
  entityUrlMap,
}: CampaignEntityFinancialDetailsProps) {
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
              Public campaign records show <strong>{entityDisplay}</strong> as
              a donor to other committees. The structured detail below lists
              the reported recipients, dates, and amounts.
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
              Public campaign records show independent expenditures by{' '}
              <strong>{entityDisplay}</strong>. The structured detail below
              names candidates when the source record supplies one. These
              payments went to vendors, not to candidate campaigns.
            </>
          }
        >
          <PACIndependentExpendituresTable
            expenditures={independentExpenditures}
            pacUrlMap={entityUrlMap}
          />
          <p className="text-xs text-slate-500 mt-4 pt-3 border-t border-slate-100 leading-relaxed">
            Data from CAL-ACCESS Form 460 Schedule D and Form 496 filings
            (FPPC, Tier 1). Each row aggregates reported expenditures by
            candidate and by support-or-oppose direction when the filing
            supplies one.
          </p>
        </CampaignEntitySection>
      )}
    </>
  )
}
