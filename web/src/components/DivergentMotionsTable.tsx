'use client'

import Link from 'next/link'
import type { DivergentMotion } from '@/lib/types'

interface DivergentMotionsTableProps {
  motions: DivergentMotion[]
  officials: Array<{ id: string; name: string }>  // column order
  selectedOfficials: Set<string>
}

function lastName(full: string): string {
  return full.trim().split(/\s+/).pop() ?? full
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function shortText(text: string | null, max = 110): string {
  if (!text) return ''
  const clean = text.replace(/\s+/g, ' ').trim()
  if (clean.length <= max) return clean
  const sliced = clean.slice(0, max)
  const lastSpace = sliced.lastIndexOf(' ')
  return (lastSpace > 60 ? sliced.slice(0, lastSpace) : sliced) + '…'
}

const voteCellStyles: Record<string, string> = {
  aye: 'bg-vote-aye/10 text-vote-aye border-vote-aye/30',
  nay: 'bg-vote-nay/10 text-vote-nay border-vote-nay/30',
  abstain: 'bg-vote-abstain/10 text-vote-abstain border-vote-abstain/30',
  absent: 'bg-slate-50 text-slate-400 border-slate-200',
}

const voteCellLabel: Record<string, string> = {
  aye: 'Yes',
  nay: 'No',
  abstain: 'Abstain',
  absent: '—',
}

export default function DivergentMotionsTable({
  motions,
  officials,
  selectedOfficials,
}: DivergentMotionsTableProps) {
  const visibleOfficials = officials.filter((o) => selectedOfficials.has(o.id))

  if (motions.length === 0) {
    return (
      <p className="text-sm italic text-slate-500">
        No split votes match the current filters.
      </p>
    )
  }

  if (visibleOfficials.length === 0) {
    return (
      <p className="text-sm italic text-slate-500">
        Select at least one member to see how they voted.
      </p>
    )
  }

  return (
    <div className="overflow-x-auto bg-white rounded-lg border border-slate-200">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 border-b border-slate-200">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider sticky left-0 bg-slate-50 z-10 min-w-[260px]">
              What was voted on
            </th>
            <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">
              Date
            </th>
            {visibleOfficials.map((o) => (
              <th
                key={o.id}
                className="px-2 py-3 text-center text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap"
                title={o.name}
              >
                {lastName(o.name)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {motions.map((m) => {
            const motionLabel = m.motion_text || m.agenda_item_title
            const itemContext = m.motion_text && m.agenda_item_title !== m.motion_text
              ? m.agenda_item_title
              : null
            return (
              <tr key={m.motion_id} className="hover:bg-slate-50/60 transition-colors">
                <td className="px-4 py-3 align-top sticky left-0 bg-white z-10 min-w-[260px]">
                  <Link
                    href={`/meetings/${m.meeting_id}#item-${m.agenda_item_id}`}
                    className="block group"
                  >
                    <div className="flex items-start gap-2 mb-0.5">
                      {m.is_procedural && (
                        <span className="inline-flex items-center text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200 whitespace-nowrap mt-0.5">
                          Procedural
                        </span>
                      )}
                      <span className="font-medium text-slate-800 group-hover:text-civic-navy">
                        {shortText(motionLabel)}
                      </span>
                    </div>
                    {itemContext && (
                      <div className="text-xs text-slate-500 mt-0.5">
                        On: {shortText(itemContext, 90)}
                      </div>
                    )}
                    {m.motion_result && (
                      <div className="text-xs text-slate-400 mt-0.5 capitalize">
                        Result: {m.motion_result.toLowerCase()}
                      </div>
                    )}
                  </Link>
                </td>
                <td className="px-3 py-3 align-top text-xs text-slate-500 whitespace-nowrap">
                  {formatDate(m.meeting_date)}
                </td>
                {visibleOfficials.map((o) => {
                  const choice = m.votes[o.id] ?? 'absent'
                  return (
                    <td key={o.id} className="px-2 py-3 align-top text-center">
                      <span
                        className={`inline-block text-xs font-semibold px-2 py-1 rounded border min-w-[3rem] ${
                          voteCellStyles[choice] ?? voteCellStyles.absent
                        }`}
                        title={`${o.name}: ${voteCellLabel[choice] ?? choice}`}
                      >
                        {voteCellLabel[choice] ?? choice}
                      </span>
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
