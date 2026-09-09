import type { PublicCommentDetail, ThemeNarrative } from '@/lib/types'
import { commentSourceToProvenance } from '@/lib/provenance'
import { ThemeAttribution } from './SourceAttribution'

interface CommunityVoiceSectionProps {
  comments: PublicCommentDetail[]
  themeNarratives: ThemeNarrative[]
  // Retained for callers; all displayed counts now come from comments below.
  spokenCount?: number
  writtenCount?: number
  commentSource: string | null
  commentExtractedAt: string | null
}

type Channel = 'spoken' | 'written' | 'unknown'
function channel(record: PublicCommentDetail): Channel {
  const method = record.method?.trim().toLowerCase()
  const type = record.comment_type?.trim().toLowerCase()
  const spoken = ['in_person', 'zoom', 'phone'].includes(method)
  const written = type === 'written' || ['email', 'ecomment', 'mail'].includes(method)
  if (spoken && written) return 'unknown'
  return spoken ? 'spoken' : written ? 'written' : 'unknown'
}

/** Count source-record IDs, never unique people. Conflicting channels stay unknown. */
export function commentRecordCounts(comments: PublicCommentDetail[]) {
  const channels = new Map<string, Channel>()
  comments.forEach((comment, index) => {
    const key = comment.id || `missing:${index}`
    const value = channel(comment)
    const previous = channels.get(key)
    channels.set(key, previous && previous !== value ? 'unknown' : value)
  })
  const counts = { total: channels.size, spoken: 0, written: 0, unknown: 0 }
  for (const value of channels.values()) counts[value]++
  return counts
}

function channelLabel(counts: ReturnType<typeof commentRecordCounts>): string {
  const parts = []
  if (counts.spoken) parts.push(`${counts.spoken} recorded as spoken`)
  if (counts.written) parts.push(`${counts.written} recorded as written`)
  if (counts.unknown) parts.push(`${counts.unknown} with channel not established`)
  return parts.join(' · ')
}

export default function CommunityVoiceSection({ comments, themeNarratives, commentSource, commentExtractedAt }: CommunityVoiceSectionProps) {
  if (!comments.length) return null
  const counts = commentRecordCounts(comments)
  const extractedDate = commentExtractedAt ? new Date(commentExtractedAt) : null
  return <section>
    <h2 className="mb-2 text-lg font-semibold text-civic-navy">Comment records</h2>
    <p className="text-sm leading-relaxed text-slate-600">
      {counts.total} comment {counts.total === 1 ? 'record' : 'records'} available here. {channelLabel(counts)}.
      {' '}One person can appear in several records; this is not a count of residents or a measure of public opinion.
    </p>
    {themeNarratives.length > 0 && <>
      <h3 className="mb-3 mt-5 font-medium text-slate-700">AI-grouped themes</h3>
      <div className="space-y-3">{themeNarratives.map(narrative => {
        const assigned = comments.filter(comment => comment.theme_slug === narrative.theme.slug)
        const assignedCounts = commentRecordCounts(assigned)
        return <div key={narrative.theme.slug} className="rounded-lg border border-slate-200 p-4">
          <h4 className="font-medium text-civic-navy">{narrative.theme.label}</h4>
          <p className="mt-1 text-xs text-slate-500">{assignedCounts.total > 0
            ? `${assignedCounts.total} assigned comment ${assignedCounts.total === 1 ? 'record' : 'records'} · ${channelLabel(assignedCounts)}`
            : 'Assigned comment records are not available in this view.'}</p>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">{narrative.narrative}</p>
          {narrative.confidence < 0.9 && <p className="mt-2 text-xs text-amber-700">This AI grouping has lower confidence.</p>}
        </div>
      })}</div>
      <p className="mt-4 text-xs leading-relaxed text-slate-500"><ThemeAttribution p={commentSourceToProvenance(commentSource)} /> A record may belong to more than one theme.
        {extractedDate && Number.isFinite(extractedDate.valueOf()) && <> Extracted {extractedDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })}.</>}
      </p>
    </>}
  </section>
}
