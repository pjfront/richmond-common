import type { StageVoteSourceReview } from '@/lib/stage-vote-source-review'

export default function VoteSourceReviewNotice({ review }: { review: StageVoteSourceReview }) {
  return <aside className="my-4 rounded-lg border border-amber-300 bg-amber-50 p-4 text-base leading-relaxed text-slate-800" role="note">
    <p className="font-semibold">Vote records held for source review</p>
    <p className="mt-2">{review.reason}</p>
    <p className="mt-2">Source checked {review.checkedAt}. The hold does not establish that no vote occurred.</p>
    <a href={`${review.sourceUrl}#page=9`} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">Read the official minutes, page 9</a>
  </aside>
}
