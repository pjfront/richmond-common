import Link from 'next/link'
import type { DivergentMotion } from '@/lib/types'
import { agendaItemPath } from '@/lib/format'
import { formatObservedDate } from '@/lib/observed-vote-records'

interface DivergentMotionsTableProps {
  motions: DivergentMotion[]
  officials: Array<{ id: string; name: string }>
}

const choiceLabels: Record<string, string> = { aye: 'Yes', nay: 'No', abstain: 'Abstained', absent: 'Recorded absent', recused: 'Recused' }

/** One source motion at a time; no missing-member or overall-outcome inference. */
export default function DivergentMotionsTable({ motions, officials }: DivergentMotionsTableProps) {
  if (!motions.length) return <p className="rounded-lg border border-slate-200 p-5 text-slate-600">
    No motion records match this view. Available records and filters limit what appears here.
  </p>
  const names = new Map(officials.map(official => [official.id, official.name]))
  return <ol className="space-y-5">{motions.map(motion => <li key={motion.motion_id} className="rounded-lg border border-slate-200 p-5">
    <p className="mb-2 text-sm text-slate-600"><time dateTime={motion.meeting_date}>{formatObservedDate(motion.meeting_date)}</time>
      {' · '}{motion.source === 'minutes' ? 'Extracted from official minutes' : motion.source === 'transcript' ? 'Tentative transcript extraction' : 'Source not identified'}
    </p>
    <h2 className="text-lg font-semibold leading-relaxed text-civic-navy">{motion.motion_text || motion.agenda_item_title}</h2>
    {motion.motion_text && motion.motion_text !== motion.agenda_item_title && <p className="mt-2 text-sm text-slate-600">Agenda item: {motion.agenda_item_title}</p>}
    <dl className="mt-4 grid gap-x-6 gap-y-2 sm:grid-cols-2">{Object.entries(motion.votes).map(([id, choice]) => <div key={id} className="flex justify-between gap-4 border-b border-slate-100 py-2">
      <dt className="text-slate-700">{names.get(id) ?? 'Name unavailable'}</dt><dd className="font-medium text-slate-800">{choiceLabels[choice] ?? 'Choice not recorded'}</dd>
    </div>)}</dl>
    <div className="mt-3 flex flex-wrap gap-x-5">
      <Link href={motion.agenda_item_number ? agendaItemPath(motion.meeting_id, motion.agenda_item_number) : `/meetings/${motion.meeting_id}`}
        className="inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">Read the agenda item and all motions →</Link>
      {motion.source_url ? <a href={motion.source_url} className="inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">Original {motion.source === 'minutes' ? 'minutes' : 'meeting video'} →</a>
        : <p className="self-center text-sm text-slate-600">Original source link unavailable.</p>}
    </div>
  </li>)}</ol>
}
