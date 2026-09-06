import Link from 'next/link'
import { formatObservedDate, observedVoteSummary, type ObservedVoteRecord } from '@/lib/observed-vote-records'

interface BioSummaryProps {
  officialName: string
  votes: ObservedVoteRecord[]
  recordHref?: string
}

/** The same input rows power this description and the voting record below. */
export default function BioSummary({ officialName, votes, recordHref = '#votes' }: BioSummaryProps) {
  const summary = observedVoteSummary(votes)
  return <section className="mb-8" aria-label={`${officialName}'s recorded council activity`}>
    <h2 className="mb-3 text-xl font-semibold text-slate-800">Council record</h2>
    <p className="leading-relaxed text-slate-700">
      {summary.recordCount > 0 ? <>
        The records shown here cover {summary.itemCount.toLocaleString()} agenda {summary.itemCount === 1 ? 'item' : 'items'}
        {' '}across {summary.meetingCount.toLocaleString()} {summary.meetingCount === 1 ? 'meeting' : 'meetings'}
        {summary.firstDate && summary.lastDate && <> from <time dateTime={summary.firstDate}>{formatObservedDate(summary.firstDate)}</time>
          {' '}to <time dateTime={summary.lastDate}>{formatObservedDate(summary.lastDate)}</time></>}.
        {' '}Each entry shows the motion and the recorded choice. Coverage depends on the meeting records available here.
      </> : <>No voting records are available here yet. This does not establish that no votes were taken.</>}
    </p>
    {summary.undatedCount > 0 && <p className="mt-2 text-sm text-slate-600">Some records have no usable meeting date.</p>}
    <Link href={recordHref} className="mt-2 inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">Read the voting records and meeting sources →</Link>
  </section>
}
