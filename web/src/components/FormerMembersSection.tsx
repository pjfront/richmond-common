'use client'

import { useState } from 'react'
import type { Official } from '@/lib/types'
import OfficialCard from './OfficialCard'

interface FormerMembersSectionProps {
  officials: Official[]
}

export default function FormerMembersSection({ officials }: FormerMembersSectionProps) {
  const [show, setShow] = useState(false)

  return (
    <section>
      <button
        onClick={() => setShow(!show)}
        className="flex items-center gap-2 text-sm text-slate-500 hover:text-civic-navy transition-colors py-2"
      >
        <svg
          className={`w-4 h-4 transition-transform duration-200 ${show ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        {show ? 'Hide' : 'Show'} former members ({officials.length})
      </button>

      {show && (
        <div className="grid gap-4 sm:grid-cols-2 mt-4">
          {officials.map((o) => (
            <OfficialCard key={o.id} official={o} />
          ))}
        </div>
      )}
    </section>
  )
}
