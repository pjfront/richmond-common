'use client'

import { useState } from 'react'
import type { PublicCommentDetail } from '@/lib/types'

interface CommentBreakdownSectionProps {
  comments: PublicCommentDetail[]
  spokenCount: number
  writtenCount: number
}

/** Normalize a comment summary for template comparison */
function normalizeSummary(s: string | null): string {
  if (!s) return ''
  return s.toLowerCase().trim().replace(/\s+/g, ' ')
}

/**
 * Detect groups of written comments that share near-identical summaries,
 * indicating a form-letter or template campaign.
 * Returns the count of comments that used the most common template,
 * or 0 if no template pattern detected (requires 2+ identical summaries).
 */
function detectTemplateCount(written: PublicCommentDetail[]): number {
  if (written.length < 2) return 0

  const groups = new Map<string, number>()
  for (const c of written) {
    const key = normalizeSummary(c.summary)
    if (!key) continue
    groups.set(key, (groups.get(key) ?? 0) + 1)
  }

  let maxGroup = 0
  for (const count of groups.values()) {
    if (count > maxGroup) maxGroup = count
  }

  return maxGroup >= 2 ? maxGroup : 0
}

/** Human-friendly label for the comment delivery method */
function methodLabel(method: string): string {
  switch (method) {
    case 'in_person': return 'In person'
    case 'zoom': return 'Via Zoom'
    case 'phone': return 'By phone'
    case 'email': return 'Email'
    case 'ecomment': return 'eComment'
    default: return method
  }
}

function SpeakerList({ comments }: { comments: PublicCommentDetail[] }) {
  if (comments.length === 0) return null
  return (
    <ul className="mt-2 space-y-1">
      {comments.map((c) => (
        <li key={c.id} className="text-sm text-slate-700 flex items-baseline gap-2">
          <span className="font-medium">{c.speaker_name || 'Anonymous'}</span>
          <span className="text-xs text-slate-400">{methodLabel(c.method)}</span>
          {c.is_notable && c.notable_role && (
            <span className="text-xs text-civic-navy bg-civic-navy/10 px-1.5 py-0.5 rounded">
              {c.notable_role}
            </span>
          )}
        </li>
      ))}
    </ul>
  )
}

/**
 * Displays public comments grouped by spoken vs written,
 * with speaker names and delivery method labels.
 */
export default function CommentBreakdownSection({
  comments,
  spokenCount,
  writtenCount,
}: CommentBreakdownSectionProps) {
  const [spokenExpanded, setSpokenExpanded] = useState(true)
  const [writtenExpanded, setWrittenExpanded] = useState(true)
  const total = comments.length

  if (total === 0) return null

  const spoken = comments.filter((c) => c.comment_type !== 'written')
  const written = comments.filter((c) => c.comment_type === 'written')
  const templateCount = detectTemplateCount(written)

  // Build summary text
  const parts: string[] = []
  if (spokenCount > 0) parts.push(`${spokenCount} spoken`)
  if (writtenCount > 0) parts.push(`${writtenCount} written`)
  const summaryDetail = parts.length > 0 ? ` — ${parts.join(', ')}` : ''

  return (
    <section>
      <h2 className="text-lg font-semibold text-civic-navy mb-3">
        Public Comments
      </h2>
      <p className="text-sm text-slate-600 mb-4">
        {total} public {total === 1 ? 'comment' : 'comments'}{summaryDetail}
      </p>

      {spoken.length > 0 && (
        <div className="mb-4">
          <button
            onClick={() => setSpokenExpanded(!spokenExpanded)}
            className="flex items-center gap-2 text-sm font-medium text-slate-700 hover:text-civic-navy transition-colors w-full text-left"
          >
            <span className="text-slate-400">{spokenExpanded ? '\u2212' : '+'}</span>
            Spoken at meeting ({spokenCount})
          </button>
          {spokenExpanded && <SpeakerList comments={spoken} />}
        </div>
      )}

      {written.length > 0 && (
        <div className="mb-4">
          <button
            onClick={() => setWrittenExpanded(!writtenExpanded)}
            className="flex items-center gap-2 text-sm font-medium text-slate-700 hover:text-civic-navy transition-colors w-full text-left"
          >
            <span className="text-slate-400">{writtenExpanded ? '\u2212' : '+'}</span>
            Written comments ({writtenCount})
          </button>
          {writtenExpanded && (
            <>
              {templateCount > 0 && (
                <p className="text-xs text-slate-500 italic mt-2 mb-1">
                  {templateCount} of {written.length} used a similar template
                </p>
              )}
              <SpeakerList comments={written} />
            </>
          )}
        </div>
      )}
    </section>
  )
}
