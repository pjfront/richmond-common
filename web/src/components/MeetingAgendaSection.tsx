'use client'

import { useState, useMemo } from 'react'
import AgendaItemCard from './AgendaItemCard'
import type { AgendaItemWithMotions } from '@/lib/types'

const PROCEDURAL = 'procedural'

interface MeetingAgendaSectionProps {
  items: AgendaItemWithMotions[]
}

export default function MeetingAgendaSection({ items }: MeetingAgendaSectionProps) {
  const [showProcedural, setShowProcedural] = useState(false)

  const { consentItems, regularItems, proceduralCount } = useMemo(() => {
    const visible = showProcedural
      ? items
      : items.filter((i) => i.category !== PROCEDURAL)

    return {
      consentItems: visible.filter((i) => i.is_consent_calendar),
      regularItems: visible.filter((i) => !i.is_consent_calendar),
      proceduralCount: items.filter((i) => i.category === PROCEDURAL).length,
    }
  }, [items, showProcedural])

  const substantiveCount = items.length - proceduralCount

  return (
    <>
      {/* Procedural toggle */}
      {proceduralCount > 0 && (
        <div className="mb-4 text-sm text-slate-500">
          {showProcedural ? (
            <span>
              Showing all {items.length} items &middot;{' '}
              <button
                onClick={() => setShowProcedural(false)}
                className="text-civic-navy hover:underline"
              >
                hide {proceduralCount} procedural
              </button>
            </span>
          ) : (
            <span>
              {substantiveCount} substantive items &middot;{' '}
              {proceduralCount} procedural hidden &middot;{' '}
              <button
                onClick={() => setShowProcedural(true)}
                className="text-civic-navy hover:underline"
              >
                show
              </button>
            </span>
          )}
        </div>
      )}

      {/* Consent Calendar */}
      {consentItems.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-semibold text-slate-800 mb-3">
            Consent Calendar ({consentItems.length} items)
          </h2>
          <p className="text-sm text-slate-500 mb-3">
            Items approved as a group. Click to expand individual items.
          </p>
          <div className="space-y-2">
            {consentItems.map((item) => (
              <AgendaItemCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      )}

      {/* Regular Agenda */}
      {regularItems.length > 0 && (
        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-3">
            Agenda Items ({regularItems.length})
          </h2>
          <div className="space-y-2">
            {regularItems.map((item) => (
              <AgendaItemCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      )}
    </>
  )
}
