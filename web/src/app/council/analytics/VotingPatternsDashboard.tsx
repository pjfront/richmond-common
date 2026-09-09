'use client'

import { useId, useMemo, useState } from 'react'
import DivergentMotionsTable from '@/components/DivergentMotionsTable'
import { formatObservedDate, recordedDate } from '@/lib/observed-vote-records'
import type { DivergentMotion } from '@/lib/types'

interface VotingPatternsDashboardProps {
  motions: DivergentMotion[]
  motionOfficials: Array<{ id: string; name: string }>
}

export default function VotingPatternsDashboard({ motions, motionOfficials }: VotingPatternsDashboardProps) {
  const searchId = useId()
  const memberId = useId()
  const [search, setSearch] = useState('')
  const [member, setMember] = useState('all')
  const filtered = useMemo(() => {
    const query = search.trim().toLocaleLowerCase()
    return motions.filter(motion => (member === 'all' || Object.hasOwn(motion.votes, member))
      && (!query || `${motion.motion_text ?? ''} ${motion.agenda_item_title}`.toLocaleLowerCase().includes(query)))
  }, [motions, search, member])
  const dates = motions.map(motion => recordedDate(motion.meeting_date)).filter((date): date is string => date !== null).sort()

  return <div>
    <p className="max-w-3xl leading-relaxed text-slate-700">
      Read individual motions where the records show both a yes and a no among people on today&apos;s council.
      Each motion has its own meaning: a procedural vote, amendment and final decision can concern the same agenda item.
    </p>
    <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-600">
      This is a collection of extracted records, not a complete history of council decisions.
      Minutes and tentative transcript records are identified separately. Missing choices do not establish absence.
    </p>
    {dates.length > 0 && <p className="mt-3 text-sm text-slate-600">Meeting dates in these records:{' '}
      <time dateTime={dates[0]}>{formatObservedDate(dates[0])}</time> to{' '}
      <time dateTime={dates.at(-1)!}>{formatObservedDate(dates.at(-1)!)}</time>.
    </p>}
    <div className="my-6 grid gap-4 sm:grid-cols-2">
      <div><label htmlFor={searchId} className="mb-2 block font-medium text-slate-700">Search the motions</label>
        <input id={searchId} type="search" value={search} onChange={event => setSearch(event.target.value)}
          className="min-h-11 w-full rounded-md border border-slate-300 px-3 py-2" /></div>
      <div><label htmlFor={memberId} className="mb-2 block font-medium text-slate-700">Member with a recorded choice</label>
        <select id={memberId} value={member} onChange={event => setMember(event.target.value)}
          className="min-h-11 w-full rounded-md border border-slate-300 bg-white px-3 py-2">
          <option value="all">All current members</option>
          {motionOfficials.map(official => <option key={official.id} value={official.id}>{official.name}</option>)}
        </select></div>
    </div>
    <p role="status" aria-live="polite" className="mb-4 text-sm text-slate-600">
      {filtered.length} of {motions.length} motion records shown.
    </p>
    <DivergentMotionsTable motions={filtered} officials={motionOfficials} />
  </div>
}
