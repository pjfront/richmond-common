import { parseAgendaText, hasStructure, sanitizeBulletChars, type TextSegment } from '@/lib/format-agenda-text'

interface FormattedDescriptionProps {
  description: string | null
}

function Segment({ segment }: { segment: TextSegment }) {
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
        <p className="text-sm text-slate-600 leading-relaxed">
          {segment.text}
        </p>
      </div>
    )
  }

  if (segment.type === 'list-item') {
    return (
      <li className="text-sm text-slate-600 leading-relaxed ml-4">
        {segment.text}
      </li>
    )
  }

  return (
    <p className="text-sm text-slate-600 leading-relaxed">
      {segment.text}
    </p>
  )
}

/**
 * Renders agenda item description text with smart formatting.
 * Handles PDF-extracted staff report text by detecting section headers,
 * rejoining broken lines, and rendering flowing prose.
 *
 * Used on the item detail page when no plain language summary exists
 * (so the description is the primary content, not expandable).
 */
export default function FormattedDescription({ description }: FormattedDescriptionProps) {
  if (!description) return null

  const useStructured = hasStructure(description)
  if (!useStructured) {
    return (
      <div className="text-sm text-slate-600 leading-relaxed whitespace-pre-line">
        {sanitizeBulletChars(description)}
      </div>
    )
  }

  const segments = parseAgendaText(description)
  const grouped = groupListItems(segments)

  return (
    <div className="space-y-2">
      {grouped.map((group, i) => {
        if (Array.isArray(group)) {
          return (
            <ul key={i} className="list-disc space-y-1">
              {group.map((seg, j) => (
                <Segment key={j} segment={seg} />
              ))}
            </ul>
          )
        }
        return <Segment key={i} segment={group} />
      })}
    </div>
  )
}

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
