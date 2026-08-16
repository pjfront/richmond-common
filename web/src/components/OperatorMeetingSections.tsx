'use client'

import { useEffect, useState } from 'react'
import type { ConflictFlag } from '@/lib/types'
import MeetingConflictsSection from './MeetingConflictsSection'

type DetailedConflictFlag = ConflictFlag & {
  agenda_item_title: string | null
  agenda_item_number: string | null
  agenda_item_category: string | null
  official_name: string | null
}

interface OperatorMeetingContext {
  flags: DetailedConflictFlag[]
}

export default function OperatorMeetingSections({
  meetingId,
  agendaItemCount,
}: {
  meetingId: string
  agendaItemCount: number
}) {
  const [context, setContext] = useState<OperatorMeetingContext | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/operator/meeting-context?meeting_id=${encodeURIComponent(meetingId)}`, {
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error('Operator meeting context request failed')
        return response.json() as Promise<OperatorMeetingContext>
      })
      .then(setContext)
      .catch((requestError: unknown) => {
        if (requestError instanceof DOMException && requestError.name === 'AbortError') return
        setError(true)
      })

    return () => controller.abort()
  }, [meetingId])

  if (error) {
    return <p role="alert" className="text-sm text-red-700 mb-6">Operator context could not be loaded.</p>
  }
  if (!context) {
    return <p aria-live="polite" className="text-sm text-slate-500 mb-6">Loading operator context…</p>
  }

  return (
    <>
      {context.flags.length > 0 && (
        <div className="bg-civic-amber/10 border border-civic-amber/30 rounded-lg p-4 mb-6">
          <h3 className="font-semibold text-civic-amber">
            {context.flags.length} Campaign Contribution{' '}
            {context.flags.length !== 1 ? 'Records' : 'Record'} Identified
          </h3>
          <p className="text-sm text-slate-700 mt-1">
            The scanner found overlaps between agenda items, campaign contributions, and financial disclosures.
            A campaign contribution does not imply wrongdoing.
          </p>
        </div>
      )}
      <MeetingConflictsSection agendaItemCount={agendaItemCount} flags={context.flags} />
    </>
  )
}
