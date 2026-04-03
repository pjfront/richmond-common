'use client'

import { useState } from 'react'
import * as Collapsible from '@radix-ui/react-collapsible'
import type { PublicCommentDetail, ThemeNarrative } from '@/lib/types'

interface CommunityVoiceSectionProps {
  comments: PublicCommentDetail[]
  themeNarratives: ThemeNarrative[]
  spokenCount: number
  writtenCount: number
  commentSource: string | null
  commentExtractedAt: string | null
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

/** Normalize a comment summary for template comparison */
function normalizeSummary(s: string | null): string {
  if (!s) return ''
  return s.toLowerCase().trim().replace(/\s+/g, ' ')
}

/** Detect form-letter campaigns in written comments */
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

function sourceLabel(source: string | null): string {
  switch (source) {
    case 'youtube_transcript': return 'KCRT YouTube meeting recording'
    case 'granicus_transcript': return 'Granicus meeting recording'
    case 'minutes': return 'official minutes'
    default: return 'meeting record'
  }
}

function formatExtractedDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

/**
 * Community Voice: theme-grouped public comment display (S21).
 * Progressively enhances: themes → speaker list → nothing.
 */
export default function CommunityVoiceSection({
  comments,
  themeNarratives,
  spokenCount,
  writtenCount,
  commentSource,
  commentExtractedAt,
}: CommunityVoiceSectionProps) {
  if (comments.length === 0) return null

  // ── Theme-grouped view ────────────────────────────────────
  if (themeNarratives.length > 0) {
    return (
      <ThemeView
        comments={comments}
        themeNarratives={themeNarratives}
        spokenCount={spokenCount}
        writtenCount={writtenCount}
        commentSource={commentSource}
        commentExtractedAt={commentExtractedAt}
      />
    )
  }

  // ── Fallback: spoken/written split ────────────────────────
  return (
    <FallbackView
      comments={comments}
      spokenCount={spokenCount}
      writtenCount={writtenCount}
    />
  )
}

// ── Theme-grouped view ──────────────────────────────────────

function ThemeView({
  comments,
  themeNarratives,
  spokenCount,
  writtenCount,
  commentSource,
  commentExtractedAt,
}: CommunityVoiceSectionProps) {
  const total = comments.length

  // Group comments by theme_slug
  const byTheme = new Map<string, PublicCommentDetail[]>()
  const unthemed: PublicCommentDetail[] = []
  for (const c of comments) {
    if (c.theme_slug) {
      const arr = byTheme.get(c.theme_slug) ?? []
      arr.push(c)
      byTheme.set(c.theme_slug, arr)
    } else {
      unthemed.push(c)
    }
  }

  // Summary line
  const parts: string[] = []
  if (spokenCount > 0) parts.push(`${spokenCount} spoke at the meeting`)
  if (writtenCount > 0) parts.push(`${writtenCount} submitted written comments`)

  return (
    <section>
      <h2 className="text-lg font-semibold text-civic-navy mb-1">
        Community Voice
      </h2>
      <p className="text-sm text-slate-600 mb-4">
        {total} {total === 1 ? 'speaker' : 'speakers'} raised {themeNarratives.length}{' '}
        {themeNarratives.length === 1 ? 'topic' : 'topics'}
        {parts.length > 0 && <> &mdash; {parts.join(', ')}</>}
      </p>

      <div className="space-y-4">
        {themeNarratives.map((tn, idx) => (
          <ThemeGroup
            key={tn.theme.slug}
            narrative={tn}
            comments={byTheme.get(tn.theme.slug) ?? []}
            defaultOpen={idx === 0}
          />
        ))}

        {unthemed.length > 0 && (
          <ThemeGroupSimple
            label="Other speakers"
            comments={unthemed}
          />
        )}
      </div>

      {/* AI attribution (U8) + source (U1) */}
      <p className="text-xs text-slate-400 mt-4 italic">
        Theme groupings and summaries are AI-generated from {sourceLabel(commentSource)}.
        {commentExtractedAt && <> Extracted {formatExtractedDate(commentExtractedAt)}.</>}
        {' '}Individual speakers listed from public record.
      </p>
    </section>
  )
}

// ── Individual theme group with Collapsible ─────────────────

function ThemeGroup({
  narrative: tn,
  comments,
  defaultOpen,
}: {
  narrative: ThemeNarrative
  comments: PublicCommentDetail[]
  defaultOpen: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const lowConfidence = tn.confidence < 0.9

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}>
      <div className="border border-slate-200 rounded-lg p-4">
        <Collapsible.Trigger asChild>
          <button className="flex items-center justify-between w-full text-left group">
            <div className="flex items-center gap-2">
              <span className="text-slate-400 text-sm w-4">{open ? '\u2212' : '+'}</span>
              <h3 className="text-sm font-semibold text-civic-navy group-hover:text-civic-navy-light transition-colors">
                {tn.theme.label}
              </h3>
              <span className="text-xs text-slate-400">
                {tn.comment_count} {tn.comment_count === 1 ? 'speaker' : 'speakers'}
              </span>
            </div>
          </button>
        </Collapsible.Trigger>

        {/* Narrative text — always visible (D6: narrative over numbers) */}
        <p className="text-sm text-slate-600 mt-2 leading-relaxed">
          {tn.narrative}
        </p>

        {lowConfidence && (
          <p className="text-xs text-amber-600 mt-1">
            Lower confidence grouping &mdash; review recommended
          </p>
        )}

        <Collapsible.Content className="collapsible-content overflow-hidden">
          <div className="mt-3 pt-3 border-t border-slate-100">
            <SpeakerList comments={comments} />
          </div>
        </Collapsible.Content>
      </div>
    </Collapsible.Root>
  )
}

/** Simple collapsible group for unthemed comments (no narrative) */
function ThemeGroupSimple({
  label,
  comments,
}: {
  label: string
  comments: PublicCommentDetail[]
}) {
  const [open, setOpen] = useState(false)

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}>
      <div className="border border-slate-200 rounded-lg p-4">
        <Collapsible.Trigger asChild>
          <button className="flex items-center gap-2 w-full text-left group">
            <span className="text-slate-400 text-sm w-4">{open ? '\u2212' : '+'}</span>
            <h3 className="text-sm font-semibold text-slate-600 group-hover:text-civic-navy transition-colors">
              {label}
            </h3>
            <span className="text-xs text-slate-400">
              {comments.length} {comments.length === 1 ? 'speaker' : 'speakers'}
            </span>
          </button>
        </Collapsible.Trigger>
        <Collapsible.Content className="collapsible-content overflow-hidden">
          <div className="mt-3 pt-3 border-t border-slate-100">
            <SpeakerList comments={comments} />
          </div>
        </Collapsible.Content>
      </div>
    </Collapsible.Root>
  )
}

// ── Fallback: spoken/written split (no themes) ──────────────

function FallbackView({
  comments,
  spokenCount,
  writtenCount,
}: {
  comments: PublicCommentDetail[]
  spokenCount: number
  writtenCount: number
}) {
  const [spokenOpen, setSpokenOpen] = useState(true)
  const [writtenOpen, setWrittenOpen] = useState(true)
  const total = comments.length

  const spoken = comments.filter((c) => c.comment_type !== 'written')
  const written = comments.filter((c) => c.comment_type === 'written')
  const templateCount = detectTemplateCount(written)

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
        <Collapsible.Root open={spokenOpen} onOpenChange={setSpokenOpen} className="mb-4">
          <Collapsible.Trigger asChild>
            <button className="flex items-center gap-2 text-sm font-medium text-slate-700 hover:text-civic-navy transition-colors w-full text-left">
              <span className="text-slate-400">{spokenOpen ? '\u2212' : '+'}</span>
              Spoken at meeting ({spokenCount})
            </button>
          </Collapsible.Trigger>
          <Collapsible.Content className="collapsible-content overflow-hidden">
            <SpeakerList comments={spoken} />
          </Collapsible.Content>
        </Collapsible.Root>
      )}

      {written.length > 0 && (
        <Collapsible.Root open={writtenOpen} onOpenChange={setWrittenOpen} className="mb-4">
          <Collapsible.Trigger asChild>
            <button className="flex items-center gap-2 text-sm font-medium text-slate-700 hover:text-civic-navy transition-colors w-full text-left">
              <span className="text-slate-400">{writtenOpen ? '\u2212' : '+'}</span>
              Written comments ({writtenCount})
            </button>
          </Collapsible.Trigger>
          <Collapsible.Content className="collapsible-content overflow-hidden">
            <>
              {templateCount > 0 && (
                <p className="text-xs text-slate-500 italic mt-2 mb-1">
                  {templateCount} of {written.length} used a similar template
                </p>
              )}
              <SpeakerList comments={written} />
            </>
          </Collapsible.Content>
        </Collapsible.Root>
      )}
    </section>
  )
}
