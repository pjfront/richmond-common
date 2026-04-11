'use client'

import type { PublicCommentDetail, ThemeNarrative } from '@/lib/types'

interface CommunityVoiceSectionProps {
  comments: PublicCommentDetail[]
  themeNarratives: ThemeNarrative[]
  spokenCount: number
  writtenCount: number
  commentSource: string | null
  commentExtractedAt: string | null
}

/** Channel-aware count label: "5 spoke · 3 wrote" or "8 spoke" or "4 wrote" */
function channelLabel(spoken: number, written: number): string {
  if (spoken > 0 && written > 0) return `${spoken} spoke · ${written} wrote`
  if (written > 0) return `${written} wrote`
  return `${spoken} spoke`
}

/** Compute spoken/written breakdown for a theme from individual comments */
function themeChannelCounts(
  themeSlug: string,
  comments: PublicCommentDetail[],
): { spoken: number; written: number } {
  let spoken = 0
  let written = 0
  for (const c of comments) {
    if (c.theme_slug !== themeSlug) continue
    if (c.comment_type === 'written') written++
    else spoken++
  }
  return { spoken, written }
}

function sourceLabel(source: string | null): string {
  switch (source) {
    case 'youtube_transcript': return 'the city meeting recording (KCRT)'
    case 'granicus_transcript': return 'the city meeting recording'
    case 'minutes': return 'official minutes'
    default: return 'meeting record'
  }
}

const KCRT_URL = 'https://www.ci.richmond.ca.us/1604/KCRT-702'

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

  // Summary line
  const parts: string[] = []
  if (spokenCount > 0) parts.push(`${spokenCount} spoke at the meeting`)
  if (writtenCount > 0) parts.push(`${writtenCount} submitted written comments`)

  return (
    <section>
      <h2 className="text-lg font-semibold text-civic-navy mb-1">
        Themes From Comments
      </h2>
      <p className="text-sm text-slate-600 mb-4">
        {total} {total === 1 ? 'person' : 'people'} raised {themeNarratives.length}{' '}
        {themeNarratives.length === 1 ? 'topic' : 'topics'}
        {parts.length > 0 && <> ({parts.join(', ')})</>}
      </p>

      <div className="space-y-3">
        {themeNarratives.map((tn) => (
          <ThemeCard key={tn.theme.slug} narrative={tn} comments={comments} />
        ))}
      </div>

      {/* AI attribution (U8) + source (U1) + recording link */}
      <p className="text-xs text-slate-400 mt-4 italic">
        Theme groupings and summaries are auto-generated from {sourceLabel(commentSource)}.
        {commentExtractedAt && <> Extracted {formatExtractedDate(commentExtractedAt)}.</>}
      </p>
      {commentSource === 'youtube_transcript' && (
        <p className="text-xs mt-1">
          <a
            href={KCRT_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-civic-navy-light hover:text-civic-navy underline"
          >
            Watch meeting recordings on KCRT
          </a>
        </p>
      )}
    </section>
  )
}

// ── Theme card (narrative + count, no individual names) ─────

function ThemeCard({ narrative: tn, comments }: { narrative: ThemeNarrative; comments: PublicCommentDetail[] }) {
  const lowConfidence = tn.confidence < 0.9
  const { spoken, written } = themeChannelCounts(tn.theme.slug, comments)

  return (
    <div className="border border-slate-200 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-2">
        <h3 className="text-sm font-semibold text-civic-navy">
          {tn.theme.label}
        </h3>
        <span className="text-xs text-slate-400">
          {channelLabel(spoken, written)}
        </span>
      </div>

      <p className="text-sm text-slate-600 leading-relaxed">
        {tn.narrative}
      </p>

      {lowConfidence && (
        <p className="text-xs text-amber-600 mt-1">
          Lower confidence grouping. Review recommended.
        </p>
      )}
    </div>
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
  const total = comments.length

  const parts: string[] = []
  if (spokenCount > 0) parts.push(`${spokenCount} spoke at the meeting`)
  if (writtenCount > 0) parts.push(`${writtenCount} submitted written comments`)

  return (
    <section>
      <h2 className="text-lg font-semibold text-civic-navy mb-3">
        Public Comments
      </h2>
      <p className="text-sm text-slate-600">
        {total} {total === 1 ? 'person' : 'people'} commented
        {parts.length > 0 && <> ({parts.join(', ')})</>}.
      </p>
    </section>
  )
}
