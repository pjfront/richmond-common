'use client'

import { useState } from 'react'
import { parseAgendaText, hasStructure, type TextSegment } from '@/lib/format-agenda-text'

interface ExpandableOfficialTextProps {
  title: string
  description: string | null
}

function FormattedSegment({ segment }: { segment: TextSegment }) {
  if (segment.type === 'section-header') {
    return (
      <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mt-4 mb-1 first:mt-0">
        {segment.keyword}
      </h4>
    )
  }

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
      <li className="text-sm text-slate-500 leading-relaxed ml-4">
        {segment.text}
      </li>
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
 * Detects WHEREAS/RESOLVED clauses, section headers, numbered lists,
 * and paragraph breaks for structured rendering. Handles PDF-extracted
 * staff report text by rejoining broken lines and stripping page artifacts.
 */
export default function ExpandableOfficialText({ title, description }: ExpandableOfficialTextProps) {
  const [expanded, setExpanded] = useState(false)

  const hasContent = title || description

  if (!hasContent) return null

  const useStructured = description ? hasStructure(description) : false
  const segments = useStructured && description ? parseAgendaText(description) : []

  // Group consecutive list items for proper <ul> rendering
  const groupedSegments = groupListItems(segments)

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
              {groupedSegments.map((group, i) => {
                if (Array.isArray(group)) {
                  return (
                    <ul key={i} className="list-disc space-y-1">
                      {group.map((seg, j) => (
                        <FormattedSegment key={j} segment={seg} />
                      ))}
                    </ul>
                  )
                }
                return <FormattedSegment key={i} segment={group} />
              })}
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

/**
 * Group consecutive list-item segments so they can be wrapped in a <ul>.
 * Returns a mixed array of TextSegments and TextSegment[] (list groups).
 */
function groupListItems(segments: TextSegment[]): (TextSegment | TextSegment[])[] {
  const result: (TextSegment | TextSegment[])[] = []
  let currentList: TextSegment[] = []

  for (const seg of segments) {
    if (seg.type === 'list-item') {
      currentList.push(seg)
    } else {
      if (currentList.length > 0) {
        result.push(currentList)
        currentList = []
      }
      result.push(seg)
    }
  }

  if (currentList.length > 0) {
    result.push(currentList)
  }

  return result
}
