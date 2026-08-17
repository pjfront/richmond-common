'use client'

import { useEffect, useState } from 'react'
import type { ItemInfluenceMapData } from '@/lib/types'
import InfluenceMapItemSection from './InfluenceMapItemSection'

interface OperatorAgendaItemContext {
  data: ItemInfluenceMapData | null
}

export default function OperatorAgendaItemSections({
  agendaItemId,
  meetingId,
}: {
  agendaItemId: string
  meetingId: string
}) {
  const [context, setContext] = useState<OperatorAgendaItemContext | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/operator/agenda-item-context?agenda_item_id=${encodeURIComponent(agendaItemId)}`, {
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error('Operator agenda-item context request failed')
        return response.json() as Promise<OperatorAgendaItemContext>
      })
      .then(setContext)
      .catch((requestError: unknown) => {
        if (requestError instanceof DOMException && requestError.name === 'AbortError') return
        setError(true)
      })

    return () => controller.abort()
  }, [agendaItemId])

  if (error) {
    return <p role="alert" className="text-sm text-red-700 mb-6">Operator context could not be loaded.</p>
  }
  if (!context) {
    return <p aria-live="polite" className="text-sm text-slate-500 mb-6">Loading operator context…</p>
  }
  if (!context.data) return null

  return (
    <>
      {context.data.total_flags > 0 && (
        <div className="bg-civic-amber/10 border border-civic-amber/30 rounded-lg p-4 mb-6">
          <h3 className="font-semibold text-civic-amber">
            {context.data.total_flags} Campaign Contribution{' '}
            {context.data.total_flags !== 1 ? 'Records' : 'Record'} Identified
          </h3>
          <p className="text-sm text-slate-700 mt-1">
            The scanner found overlaps between this item, campaign contributions, and financial disclosures.
            A campaign contribution does not imply wrongdoing.
          </p>
        </div>
      )}
      <InfluenceMapItemSection data={context.data} meetingId={meetingId} />
    </>
  )
}
