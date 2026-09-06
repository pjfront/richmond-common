import type { MotionWithVotes } from '@/lib/types'
import VoteBadge from './VoteBadge'
import ReportErrorLink from './ReportErrorLink'
import { formalMotionResult, motionKindLabel, motionTallyLabel } from '@/lib/vote-records'

/**
 * Compute vote tally from individual vote records rather than the stored
 * vote_tally text, which can incorrectly count absent/abstain as nay votes.
 */
function computeTally(votes: MotionWithVotes['votes']): string | null {
  return motionTallyLabel(votes)
}

export default function VoteBreakdown({ motion }: { motion: MotionWithVotes }) {
  const result = formalMotionResult(motion)
  const resultColor = result === 'passed'
    ? 'text-vote-aye'
    : result === 'failed'
    ? 'text-vote-nay'
    : 'text-slate-600'

  const tally = computeTally(motion.votes)

  return (
    <div className="border-t border-slate-200 pt-3 mt-4 first:mt-1">
      <div className="flex items-start justify-between gap-2 sm:gap-4">
        <div className="flex-1 min-w-0">
          <p className="mb-1 text-sm font-medium text-slate-600">{motionKindLabel(motion)} · {motion.source === 'minutes' ? 'Official minutes' : 'Tentative record'}</p>
          <p className="text-sm text-slate-700 break-words">{motion.motion_text}</p>
          <div className="flex gap-3 mt-1 text-xs text-slate-500">
            {motion.moved_by && <span>Moved by: {motion.moved_by}</span>}
            {motion.seconded_by && <span>Seconded by: {motion.seconded_by}</span>}
          </div>
        </div>
        <div className="max-w-[45%] text-right shrink-0">
          <span className={`font-semibold text-sm ${resultColor}`}>
            {result === 'unknown' ? 'Outcome unverified' : result.charAt(0).toUpperCase() + result.slice(1)}
          </span>
          {tally && (
            <p className="text-xs text-slate-500 mt-0.5">{tally}</p>
          )}
        </div>
      </div>

      {motion.votes.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-2">
          {motion.votes.map((v) => (
            <div key={v.id} className="flex items-center gap-1">
              <span className="text-xs text-slate-600">{v.official_name}</span>
              <VoteBadge choice={v.vote_choice} />
            </div>
          ))}
        </div>
      )}

      {motion.vote_explainer && result !== 'unknown' && (
        <div className="bg-blue-50 border border-blue-100 rounded-md p-3 mt-3">
          <p className="text-xs font-medium text-blue-600 mb-1">Why This Vote Matters</p>
          <p className="text-sm text-slate-700 leading-relaxed">
            {motion.vote_explainer}
          </p>
          <p className="text-[10px] text-slate-400 mt-2">
            Auto-generated context based on {motion.source === 'minutes' ? 'official minutes' : 'a tentative transcript record'}.
          </p>
        </div>
      )}

      <div className="mt-2">
        <ReportErrorLink
          entityId={motion.id}
          entityType="motion"
          currentContext={motion.vote_tally ?? ''}
        />
      </div>
    </div>
  )
}
