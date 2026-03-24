'use client'

import { useState } from 'react'
import { parseAgendaText, hasStructure, type TextSegment } from '@/lib/format-agenda-text'

interface ExpandableOfficialTextProps {
  title: string
  description: string | null
}

function FormattedSegment({ segment }: { segment: TextSegment }) {
  if (segment.type === 'clause') {
    return (
      <div className="pl-4 border-l-2 border-slate-300 py-1">
        {segment.keyword && (
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
            {segment.keyword}
          </span>
        )}
        <p className="text-sm text-slate-500 leading-relaxed">
          {segment.text}
        </p>
      </div>
    )
  }

  if (segment.type === 'list-item') {
    return (
      <p className="text-sm text-slate-500 leading-relaxed pl-4">
        {segment.text}
      </p>
    )
  }

  return (
    <p className="text-sm text-slate-500 leading-relaxed">
      {segment.text}
    </p>
  )
}

/**
 * Expandable official agenda text — collapsed by default.
 *
 * Detects WHEREAS/RESOLVED clauses, numbered lists, and paragraph breaks
 * for structured rendering. Falls back to plain text for unstructured content.
 */
export default function ExpandableOfficialText({ title, description }: ExpandableOfficialTextProps) {
  const [expanded, setExpanded] = useState(false)

  const hasContent = title || description

  if (!hasContent) return null

  const useStructured = description ? hasStructure(description) : false
  const segments = useStructured && description ? parseAgendaText(description) : []

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
          {useStructured ? (
            <div className="mt-1 space-y-2">
              {segments.map((seg, i) => (
                <FormattedSegment key={i} segment={seg} />
              ))}
            </div>
          ) : description ? (
            <div className="text-sm text-slate-500 leading-relaxed mt-1 whitespace-pre-line">
              {description}
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
