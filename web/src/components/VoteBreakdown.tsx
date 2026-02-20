import type { MotionWithVotes } from '@/lib/types'
import VoteBadge from './VoteBadge'

export default function VoteBreakdown({ motion }: { motion: MotionWithVotes }) {
  const resultColor = motion.result === 'passed'
    ? 'text-vote-aye'
    : motion.result === 'failed'
    ? 'text-vote-nay'
    : 'text-slate-600'

  return (
    <div className="border-t border-slate-100 pt-3 mt-3">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <p className="text-sm text-slate-700">{motion.motion_text}</p>
          <div className="flex gap-3 mt-1 text-xs text-slate-500">
            {motion.moved_by && <span>Moved by: {motion.moved_by}</span>}
            {motion.seconded_by && <span>Seconded by: {motion.seconded_by}</span>}
          </div>
        </div>
        <div className="text-right shrink-0">
          <span className={`font-semibold text-sm ${resultColor}`}>
            {motion.result.charAt(0).toUpperCase() + motion.result.slice(1)}
          </span>
          {motion.vote_tally && (
            <p className="text-xs text-slate-500 mt-0.5">{motion.vote_tally}</p>
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
    </div>
  )
}
