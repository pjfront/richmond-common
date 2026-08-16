/**
 * Operator-gated conflict-of-interest report for a meeting.
 *
 * Folded into the canonical meeting page (`/meetings/[id]`) by Phase 2.6 of
 * the re-architecture. Previously rendered as a standalone page at
 * `/reports/[meetingId]`, which now permanently redirects here.
 *
 * Confidence-tiered grouping (Strong / Notable / Possible / Post-Vote) is
 * preserved from the old reports page. Tier 3 flags (< CONFIDENCE_LOW) are
 * suppressed in the UI; the methodology text discloses that they're tracked
 * internally.
 */
import { CONFIDENCE_STRONG, CONFIDENCE_MODERATE } from '@/lib/thresholds'
import type { ConflictFlag } from '@/lib/types'
import ConflictFlagCard from '@/components/ConflictFlagCard'
import Link from 'next/link'

interface Props {
  agendaItemCount: number
  flags: Array<ConflictFlag & {
    agenda_item_title: string | null
    agenda_item_number: string | null
    agenda_item_category: string | null
    official_name: string | null
  }>
}

export default function MeetingConflictsSection({ agendaItemCount, flags }: Props) {
  const nonTemporalFlags = flags.filter((f) => f.flag_type !== 'post_vote_donation')
  const strongFlags = nonTemporalFlags.filter((f) => f.confidence >= CONFIDENCE_STRONG)
  const moderateFlags = nonTemporalFlags.filter(
    (f) => f.confidence >= CONFIDENCE_MODERATE && f.confidence < CONFIDENCE_STRONG
  )
  const postVoteFlags = flags.filter((f) => f.flag_type === 'post_vote_donation')
  const publishedCount = strongFlags.length + moderateFlags.length + postVoteFlags.length

  if (publishedCount === 0) {
    return (
      <section id="conflicts" className="mb-8">
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <h3 className="font-semibold text-green-800">Financial Contribution Report</h3>
          <p className="text-sm text-green-700 mt-1">
            All {agendaItemCount} agenda items were scanned against campaign contributions and
            financial disclosures. No patterns meeting the publication threshold were identified.
          </p>
        </div>
      </section>
    )
  }

  return (
    <section id="conflicts" className="mb-8">
      <h2 className="text-2xl font-bold text-civic-navy mb-2">Financial Contribution Report</h2>
      <div className="bg-blue-50/50 border border-blue-100 rounded-lg p-4 mb-6">
        <p className="text-sm text-slate-700 leading-relaxed">
          We scanned {agendaItemCount} agenda items from this meeting against public campaign
          contribution records and financial disclosures. We found <strong>{publishedCount}</strong>{' '}
          case{publishedCount !== 1 ? 's' : ''} where a council member voted on an item connected to
          a campaign donor or financial interest. This doesn&apos;t mean anything improper happened.
          It means the connection exists and is worth knowing about.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <p className="text-2xl font-bold text-civic-navy">{agendaItemCount}</p>
          <p className="text-xs text-slate-500 mt-1">Items Scanned</p>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <p className="text-2xl font-bold text-civic-amber">{publishedCount}</p>
          <p className="text-xs text-slate-500 mt-1">Connections Found</p>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <p className="text-2xl font-bold text-vote-aye">{agendaItemCount - publishedCount}</p>
          <p className="text-xs text-slate-500 mt-1">No Connections</p>
        </div>
      </div>

      {strongFlags.length > 0 && (
        <div className="mb-8">
          <h3 className="text-xl font-semibold text-red-800 mb-3">
            Strongest Connections ({strongFlags.length})
          </h3>
          <p className="text-sm text-slate-500 mb-3">
            Multiple independent sources confirm these financial connections.
          </p>
          <div className="space-y-3">
            {strongFlags.map((flag) => (
              <ConflictFlagCard key={flag.id} flag={flag} />
            ))}
          </div>
        </div>
      )}

      {moderateFlags.length > 0 && (
        <div className="mb-8">
          <h3 className="text-xl font-semibold text-yellow-800 mb-3">
            Notable Connections ({moderateFlags.length})
          </h3>
          <p className="text-sm text-slate-500 mb-3">
            Clear financial connections with supporting evidence.
          </p>
          <div className="space-y-3">
            {moderateFlags.map((flag) => (
              <ConflictFlagCard key={flag.id} flag={flag} />
            ))}
          </div>
        </div>
      )}

      {postVoteFlags.length > 0 && (
        <div className="mb-8">
          <h3 className="text-xl font-bold text-gray-900 mb-2">
            Post-Vote Donations ({postVoteFlags.length})
          </h3>
          <p className="text-sm text-gray-600 mb-4">
            Contributions filed after officials voted on related agenda items. Temporal proximity
            does not indicate wrongdoing.
          </p>
          <div className="space-y-4">
            {postVoteFlags.map((flag) => (
              <ConflictFlagCard key={flag.id} flag={flag} />
            ))}
          </div>
        </div>
      )}

      <div className="bg-slate-50 rounded-lg border border-slate-200 p-4">
        <h3 className="font-semibold text-slate-700 mb-2">Methodology</h3>
        <p className="text-sm text-slate-600 leading-relaxed">
          This report was generated by cross-referencing agenda item text against campaign
          contributions from CAL-ACCESS (PAC/IE committees) and NetFile (local council candidate
          committees). Entity name matching uses normalized comparison with employer
          cross-referencing. Patterns are tiered by confidence: Strong (&ge;85%) indicates
          high-confidence patterns with corroborating signals. Moderate (&ge;70%) indicates clear
          patterns with supporting evidence. Weaker matches are tracked internally but not published.
        </p>
        <Link
          href="/about"
          className="text-sm text-civic-navy-light hover:text-civic-navy inline-block mt-2"
        >
          Learn more about our methodology &rarr;
        </Link>
      </div>
    </section>
  )
}
