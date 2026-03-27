'use client'

import { useState, useRef, useEffect } from 'react'

/**
 * InfoTooltip — instant-hover tooltip for info/help icons.
 *
 * Uses the same hover pattern as CivicTerm but purpose-built for
 * small indicator icons (e.g. "?" circles on stat labels).
 * No dotted underline — the trigger is the children element itself.
 */

interface InfoTooltipProps {
  /** Tooltip text */
  text: string
  /** The trigger element (e.g. a "?" circle) */
  children: React.ReactNode
}

export default function InfoTooltip({ text, children }: InfoTooltipProps) {
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<'above' | 'below'>('below')
  const triggerRef = useRef<HTMLSpanElement>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (open && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect()
      const spaceBelow = window.innerHeight - rect.bottom
      setPosition(spaceBelow < 120 ? 'above' : 'below')
    }
  }, [open])

  const show = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    setOpen(true)
  }

  const hide = () => {
    timeoutRef.current = setTimeout(() => setOpen(false), 100)
  }

  return (
    <span className="relative inline-flex">
      <span
        ref={triggerRef}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        tabIndex={0}
        aria-label="More info"
      >
        {children}
      </span>

      {open && (
        <div
          role="tooltip"
          className={`absolute z-50 w-56 bg-white border border-slate-200 rounded-lg shadow-lg p-2.5 text-left ${
            position === 'above'
              ? 'bottom-full mb-2 left-1/2 -translate-x-1/2'
              : 'top-full mt-2 left-1/2 -translate-x-1/2'
          }`}
          onMouseEnter={show}
          onMouseLeave={hide}
        >
          <p className="text-xs text-slate-600 leading-relaxed">{text}</p>
        </div>
      )}
    </span>
  )
}
