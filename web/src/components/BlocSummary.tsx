'use client'

import type { VotingBloc } from '@/lib/types'

interface BlocSummaryProps {
  blocs: VotingBloc[]
}

export default function BlocSummary({ blocs }: BlocSummaryProps) {
  if (blocs.length === 0) {
    return (
      <p className="text-slate-500 italic text-sm">
        No voting blocs detected at current thresholds (3+ members, 70%+ mutual agreement, 5+ shared votes).
      </p>
    )
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {blocs.map((bloc, i) => {
        const pct = Math.round(bloc.avg_mutual_agreement * 100)
        const isStrong = bloc.bloc_strength === 'strong'

        return (
          <div
            key={i}
            className={`rounded-lg border p-4 ${
              isStrong
                ? 'border-emerald-200 bg-emerald-50/50'
                : 'border-amber-200 bg-amber-50/50'
            }`}
          >
            <div className="flex items-center gap-2 mb-2">
              <span
                className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                  isStrong
                    ? 'bg-emerald-100 text-emerald-800'
                    : 'bg-amber-100 text-amber-800'
                }`}
              >
                {isStrong ? 'Strong' : 'Moderate'}
              </span>
              <span className="text-xs text-slate-500 tabular-nums">
                {pct}% avg agreement
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {bloc.members.map((m) => (
                <span
                  key={m.id}
                  className="text-sm font-medium text-slate-700 bg-white px-2 py-1 rounded border border-slate-200"
                >
                  {m.name}
                </span>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
