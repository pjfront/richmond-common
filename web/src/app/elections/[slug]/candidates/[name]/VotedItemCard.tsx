'use client'

import { useState } from 'react'
import type { CommentedVote } from '@/lib/queries'

const VOTE_COLORS: Record<string, string> = {
  aye: 'bg-vote-aye text-white',
  nay: 'bg-vote-nay text-white',
  abstain: 'bg-vote-abstain text-white',
  absent: 'bg-white text-slate-300 border border-dashed border-slate-300',
}

const VOTE_ALIASES: Record<string, string> = {
  noe: 'nay', no: 'nay', yes: 'aye', yea: 'aye',
}

function normalize(choice: string): string {
  const lower = choice.toLowerCase()
  return VOTE_ALIASES[lower] ?? lower
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/)
  return (parts[0][0] + (parts[parts.length - 1]?.[0] ?? '')).toUpperCase()
}

function getLastName(name: string): string {
  const parts = name.trim().split(/\s+/)
  return parts[parts.length - 1]
}

export default function VotedItemCard({
  vote,
  candidateName,
}: {
  vote: CommentedVote
  candidateName: string
}) {
  const [themesOpen, setThemesOpen] = useState(false)
  const candidateChoice = normalize(vote.candidate_vote)
  const candidateLabel = candidateChoice.charAt(0).toUpperCase() + candidateChoice.slice(1)

  // Sort roll call: candidate first, then alphabetical by last name
  const sortedRoll = [...vote.roll_call].sort((a, b) => {
    if (a.official_name === candidateName) return -1
    if (b.official_name === candidateName) return 1
    return getLastName(a.official_name).localeCompare(getLastName(b.official_name))
  })

  return (
    <div className="rounded-lg border border-slate-200 overflow-hidden">
      <div className="p-4">
        {/* Header: headline + candidate's vote badge */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-slate-800 leading-snug">
              {vote.summary_headline ?? vote.item_title}
            </p>
            <div className="flex items-center gap-2 flex-wrap mt-1.5">
              <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                vote.motion_result === 'passed'
                  ? 'bg-emerald-50 text-vote-aye border border-emerald-200'
                  : vote.motion_result === 'failed'
                  ? 'bg-red-50 text-vote-nay border border-red-200'
                  : 'bg-slate-50 text-slate-500 border border-slate-200'
              }`}>
                {vote.motion_result.charAt(0).toUpperCase() + vote.motion_result.slice(1)}
              </span>
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-civic-navy/10 text-civic-navy border border-civic-navy/20">
                {vote.public_comment_count} public {vote.public_comment_count === 1 ? 'speaker' : 'speakers'}
              </span>
              <span className="text-xs text-slate-400">
                {new Date(vote.meeting_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
              </span>
            </div>
          </div>
        </div>

        {/* Plain language summary */}
        {vote.plain_language_summary && (
          <div className="bg-slate-50 border border-slate-200 rounded-md p-3 mt-3">
            <p className="text-xs font-medium text-slate-500 mb-1">In Plain English</p>
            <p className="text-sm text-slate-700 leading-relaxed">
              {vote.plain_language_summary}
            </p>
          </div>
        )}

        {/* Roll call with candidate highlighted */}
        {sortedRoll.length > 0 && (
          <div className="mt-3">
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-400 mb-2">
              How they voted
            </p>
            <div className="flex flex-wrap gap-1.5">
              {sortedRoll.map((v) => {
                const choice = normalize(v.vote_choice)
                const isCandidate = v.official_name === candidateName
                return (
                  <span
                    key={v.official_name}
                    title={`${v.official_name} — ${choice.charAt(0).toUpperCase() + choice.slice(1)}`}
                    className={`inline-flex items-center justify-center w-8 h-8 rounded-full text-[10px] font-bold ${
                      VOTE_COLORS[choice] ?? VOTE_COLORS.absent
                    } ${isCandidate ? 'ring-2 ring-offset-1 ring-civic-navy scale-110' : ''}`}
                  >
                    {getInitials(v.official_name)}
                  </span>
                )
              })}
              <span className="flex items-center gap-2 ml-2 text-[10px] text-slate-400">
                <span className="inline-flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-vote-aye inline-block" />Aye
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-vote-nay inline-block" />Nay
                </span>
              </span>
            </div>
            <p className="text-[10px] text-slate-400 mt-1.5">
              {candidateName.split(' ')[0]} voted <strong className="font-semibold">{candidateLabel}</strong>
              {' · '}Highlighted with ring
            </p>
          </div>
        )}
      </div>

      {/* Expandable themes */}
      {vote.themes.length > 0 && (
        <div className="border-t border-slate-100">
          <button
            onClick={() => setThemesOpen(!themesOpen)}
            className="w-full flex items-center justify-between bg-gradient-to-r from-slate-50/80 to-transparent px-4 py-3 hover:from-civic-navy/[0.06] hover:to-transparent transition-all cursor-pointer"
          >
            <span className="text-[11px] font-medium uppercase tracking-widest text-slate-400">
              {vote.public_comment_count >= 10
                ? 'This drew significant public input'
                : 'The public weighed in on this'}
            </span>
            <svg
              className={`h-3.5 w-3.5 text-slate-300 transition-transform ${themesOpen ? 'rotate-180' : ''}`}
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.168l3.71-3.938a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06Z"
                clipRule="evenodd"
              />
            </svg>
          </button>
          {themesOpen && (
            <div className="px-4 pb-4 pt-1 space-y-2">
              <p className="text-xs text-slate-500 mb-2">
                {vote.themes.length} {vote.themes.length === 1 ? 'topic' : 'topics'} identified from public comment
              </p>
              {vote.themes.map((t) => (
                <div key={t.label} className="border border-slate-200 rounded-md px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-civic-navy">{t.label}</span>
                    {t.comment_count > 0 && (
                      <span className="text-xs text-slate-400">{t.comment_count} comments</span>
                    )}
                  </div>
                  <p className="text-sm text-slate-600 leading-relaxed mt-1">{t.narrative}</p>
                </div>
              ))}
              <p className="text-[10px] text-slate-400 italic mt-2">
                Theme groupings and summaries are auto-generated from meeting records.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
