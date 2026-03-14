'use client'

import { useState, useRef, useEffect } from 'react'

/**
 * CivicTerm — Design Rule C4
 *
 * Wraps government jargon in a plain-language label with a tooltip
 * showing the official term, regulatory category, and definition.
 *
 * The visible text is plain language (~grade 6 reading level).
 * The tooltip provides the technical precision journalists and
 * researchers need.
 *
 * Usage:
 *   <CivicTerm
 *     term="Campaign Finance Filing"
 *     category="CAL-ACCESS / NetFile"
 *     definition="A mandatory disclosure of campaign contributions and expenditures filed with the state or local registrar."
 *   >
 *     donation records
 *   </CivicTerm>
 */

interface CivicTermProps {
  /** The official/technical term */
  term: string
  /** Filing or regulatory category (optional) */
  category?: string
  /** One-sentence plain-language definition (optional) */
  definition?: string
  /** The plain-language visible text (children) */
  children: React.ReactNode
}

export default function CivicTerm({ term, category, definition, children }: CivicTermProps) {
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<'above' | 'below'>('below')
  const triggerRef = useRef<HTMLSpanElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Determine tooltip position based on available space
  useEffect(() => {
    if (open && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect()
      const spaceBelow = window.innerHeight - rect.bottom
      setPosition(spaceBelow < 160 ? 'above' : 'below')
    }
  }, [open])

  const show = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    setOpen(true)
  }

  const hide = () => {
    timeoutRef.current = setTimeout(() => setOpen(false), 100)
  }

  const tooltipId = `civic-term-${term.replace(/\s+/g, '-').toLowerCase()}`

  return (
    <span className="relative inline">
      <span
        ref={triggerRef}
        className="border-b border-dotted border-slate-400 cursor-help"
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        tabIndex={0}
        role="term"
        aria-describedby={tooltipId}
      >
        {children}
      </span>

      {open && (
        <div
          ref={tooltipRef}
          id={tooltipId}
          role="tooltip"
          className={`absolute z-50 w-64 bg-white border border-slate-200 rounded-lg shadow-lg p-3 text-left ${
            position === 'above'
              ? 'bottom-full mb-2 left-1/2 -translate-x-1/2'
              : 'top-full mt-2 left-1/2 -translate-x-1/2'
          }`}
          onMouseEnter={show}
          onMouseLeave={hide}
        >
          <div className="text-xs font-semibold text-civic-navy">{term}</div>
          {category && (
            <div className="text-[10px] text-slate-400 mt-0.5 uppercase tracking-wider">{category}</div>
          )}
          {definition && (
            <div className="text-xs text-slate-600 mt-1.5 leading-relaxed">{definition}</div>
          )}
        </div>
      )}
    </span>
  )
}
