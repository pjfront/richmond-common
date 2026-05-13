/**
 * Permanent redirect to the canonical meeting URL.
 *
 * Phase 2.6 of the re-architecture folded the per-meeting financial-
 * contribution report into the canonical meeting page (`/meetings/[id]`) as
 * an operator-gated <MeetingConflictsSection>. The old standalone report
 * URL now 308-redirects there, with `#conflicts` as the scroll target.
 *
 * Why we keep a page file (vs. a `next.config.ts` rewrite): keeping the
 * redirect alongside `influence/item/[id]` makes the consolidation pattern
 * uniform — both old routes redirect from a server component, both honor
 * the existing route filesystem, and both are easy to delete in a single
 * cleanup pass once analytics tell us nobody hits these URLs anymore.
 *
 * The destination param name matches the source (`meetingId`), so no
 * lookup is required.
 */
import { permanentRedirect } from 'next/navigation'

export default async function LegacyReportDetailPage({
  params,
}: {
  params: Promise<{ meetingId: string }>
}) {
  const { meetingId } = await params
  permanentRedirect(`/meetings/${meetingId}#conflicts`)
}
