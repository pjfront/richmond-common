import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'
import { getMeeting, getConflictFlagsDetailed } from '@/lib/queries'
import ConflictFlagCard from '@/components/ConflictFlagCard'
import { CONFIDENCE_STRONG, CONFIDENCE_MODERATE, CONFIDENCE_LOW } from '@/lib/thresholds'

export const revalidate = 3600 // Revalidate every hour

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

export async function generateMetadata(
  { params }: { params: Promise<{ meetingId: string }> }
): Promise<Metadata> {
  const { meetingId } = await params
  const meeting = await getMeeting(meetingId)
  if (!meeting) return { title: 'Report Not Found' }
  return {
    title: `Transparency Report — ${formatDate(meeting.meeting_date)}`,
    description: `Conflict of interest analysis for the Richmond City Council meeting on ${formatDate(meeting.meeting_date)}.`,
  }
}

export default async function ReportDetailPage({
  params,
}: {
  params: Promise<{ meetingId: string }>
}) {
  const { meetingId } = await params
  const [meeting, flags] = await Promise.all([
    getMeeting(meetingId),
    getConflictFlagsDetailed(meetingId),
  ])

  if (!meeting) notFound()

  const nonTemporalFlags = flags.filter((f) => f.flag_type !== 'post_vote_donation')
  const strongFlags = nonTemporalFlags.filter((f) => f.confidence >= CONFIDENCE_STRONG)
  const moderateFlags = nonTemporalFlags.filter((f) => f.confidence >= CONFIDENCE_MODERATE && f.confidence < CONFIDENCE_STRONG)
  const lowFlags = nonTemporalFlags.filter((f) => f.confidence >= CONFIDENCE_LOW && f.confidence < CONFIDENCE_MODERATE)
  const postVoteFlags = flags.filter((f) => f.flag_type === 'post_vote_donation')
  const publishedCount = strongFlags.length + moderateFlags.length + lowFlags.length + postVoteFlags.length
  const itemsScanned = meeting.agenda_items.length

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-6">
        <Link href="/reports" className="text-sm text-civic-navy-light hover:text-civic-navy">
          &larr; All Reports
        </Link>
        <h1 className="text-3xl font-bold text-civic-navy mt-2">
          Transparency Report
        </h1>
        <p className="text-slate-600 mt-1">{formatDate(meeting.meeting_date)}</p>
      </div>

      {/* Plain English intro — what is the reader looking at? */}
      <div className="bg-blue-50/50 border border-blue-100 rounded-lg p-4 mb-6">
        <p className="text-sm text-slate-700 leading-relaxed">
          {publishedCount > 0 ? (
            <>
              We scanned {itemsScanned} agenda items from this meeting against public campaign
              contribution records and financial disclosures. We found <strong>{publishedCount}</strong>{' '}
              case{publishedCount !== 1 ? 's' : ''} where a council member voted on an item connected
              to a campaign donor or financial interest. This doesn&apos;t mean anything improper
              happened — it means the connection exists and is worth knowing about.
            </>
          ) : (
            <>
              We scanned all {itemsScanned} agenda items from this meeting against public campaign
              contribution records and financial disclosures. No financial connections between
              voters and agenda items were identified.
            </>
          )}
        </p>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <p className="text-2xl font-bold text-civic-navy">{itemsScanned}</p>
          <p className="text-xs text-slate-500 mt-1">Items Scanned</p>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <p className={`text-2xl font-bold ${publishedCount > 0 ? 'text-civic-amber' : 'text-vote-aye'}`}>
            {publishedCount}
          </p>
          <p className="text-xs text-slate-500 mt-1">Connections Found</p>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <p className="text-2xl font-bold text-vote-aye">{itemsScanned - publishedCount}</p>
          <p className="text-xs text-slate-500 mt-1">No Connections</p>
        </div>
      </div>

      {/* Strong patterns */}
      {strongFlags.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-semibold text-red-800 mb-3">
            Strongest Connections ({strongFlags.length})
          </h2>
          <p className="text-sm text-slate-500 mb-3">
            Multiple independent sources confirm these financial connections.
          </p>
          <div className="space-y-3">
            {strongFlags.map((flag) => (
              <ConflictFlagCard key={flag.id} flag={flag} />
            ))}
          </div>
        </section>
      )}

      {/* Moderate patterns */}
      {moderateFlags.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-semibold text-yellow-800 mb-3">
            Notable Connections ({moderateFlags.length})
          </h2>
          <p className="text-sm text-slate-500 mb-3">
            Clear financial connections with supporting evidence.
          </p>
          <div className="space-y-3">
            {moderateFlags.map((flag) => (
              <ConflictFlagCard key={flag.id} flag={flag} />
            ))}
          </div>
        </section>
      )}

      {/* Low patterns */}
      {lowFlags.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-semibold text-green-800 mb-3">
            Possible Connections ({lowFlags.length})
          </h2>
          <p className="text-sm text-slate-500 mb-3">
            Weaker connections with limited evidence. Listed for transparency.
          </p>
          <div className="space-y-3">
            {lowFlags.map((flag) => (
              <ConflictFlagCard key={flag.id} flag={flag} />
            ))}
          </div>
        </section>
      )}

      {/* Post-Vote Donations */}
      {postVoteFlags.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-bold text-gray-900 mb-2">
            Post-Vote Donations ({postVoteFlags.length})
          </h2>
          <p className="text-sm text-gray-600 mb-4">
            Contributions filed after officials voted on related agenda items.
            Temporal proximity does not indicate wrongdoing.
          </p>
          <div className="space-y-4">
            {postVoteFlags.map((flag) => (
              <ConflictFlagCard key={flag.id} flag={flag} />
            ))}
          </div>
        </section>
      )}

      {/* Clean items note */}
      {publishedCount === 0 && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-8">
          <h3 className="font-semibold text-green-800">No Published Findings</h3>
          <p className="text-sm text-green-700 mt-1">
            All {itemsScanned} agenda items were scanned against campaign contributions and financial
            disclosures. No patterns meeting the publication threshold were identified.
          </p>
        </div>
      )}

      {/* Methodology sidebar */}
      <section className="bg-slate-50 rounded-lg border border-slate-200 p-4">
        <h3 className="font-semibold text-slate-700 mb-2">Methodology</h3>
        <p className="text-sm text-slate-600 leading-relaxed">
          This report was generated by cross-referencing agenda item text against campaign
          contributions from CAL-ACCESS (PAC/IE committees) and NetFile (local council candidate
          committees). Entity name matching uses normalized comparison with employer
          cross-referencing. Patterns are tiered by confidence: Strong (&ge;85%) indicates
          high-confidence patterns with corroborating signals, Moderate (&ge;70%) indicates clear
          patterns, and Low (&ge;50%) indicates possible patterns. Flags below 50% are tracked
          internally but not published.
        </p>
        <Link
          href="/about"
          className="text-sm text-civic-navy-light hover:text-civic-navy inline-block mt-2"
        >
          Learn more about our methodology &rarr;
        </Link>
      </section>

      {/* Link to meeting */}
      <div className="mt-6 text-sm text-slate-400">
        <Link href={`/meetings/${meeting.id}`} className="text-civic-navy-light hover:text-civic-navy">
          View full meeting details &rarr;
        </Link>
      </div>
    </div>
  )
}
