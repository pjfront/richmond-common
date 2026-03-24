'use client'

import { useState } from 'react'

interface ExpandableOfficialTextProps {
  title: string
  description: string | null
}

/**
 * Expandable official agenda text — collapsed by default.
 *
 * On influence map pages, the plain-language headline + summary convey
 * the item's meaning more clearly than the official title. The raw
 * official text is available for users who want the original wording
 * (lawyers, journalists, activists who need exact text for citations).
 */
export default function ExpandableOfficialText({ title, description }: ExpandableOfficialTextProps) {
  const [expanded, setExpanded] = useState(false)

  const hasContent = title || description

  if (!hasContent) return null

  return (
    <div className="mt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-xs text-slate-400 hover:text-slate-600 transition-colors"
      >
        {expanded ? '▾ Hide official agenda text' : '▸ Show official agenda text'}
      </button>
      {expanded && (
        <div className="mt-2 border-l-2 border-slate-200 pl-3">
          {title && (
            <p className="text-sm text-slate-600 leading-relaxed font-medium">
              {title}
            </p>
          )}
          {description && (
            <div className="text-sm text-slate-500 leading-relaxed mt-1 whitespace-pre-line">
              {description}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
