'use client'

import { useId } from 'react'
import * as Tooltip from '@radix-ui/react-tooltip'

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
  const descriptionId = `civic-term-${useId().replace(/:/g, '')}-description`

  return (
    <Tooltip.Provider delayDuration={0}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span
            className="border-b border-dotted border-slate-400 cursor-help"
            tabIndex={0}
            role="term"
            aria-describedby={descriptionId}
          >
            {children}
          </span>
        </Tooltip.Trigger>

        <span id={descriptionId} className="sr-only">
          Official term: {term}.
          {category ? ` Category: ${category}.` : ''}
          {definition ? ` ${definition}` : ''}
        </span>

        <Tooltip.Portal>
          <Tooltip.Content
            side="bottom"
            sideOffset={8}
            collisionPadding={12}
            className="z-50 w-64 bg-white border border-slate-200 rounded-lg shadow-lg p-3 text-left"
          >
            <div className="text-xs font-semibold text-civic-navy">{term}</div>
            {definition && (
              <div className="text-xs text-slate-600 mt-1.5 leading-relaxed">{definition}</div>
            )}
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
