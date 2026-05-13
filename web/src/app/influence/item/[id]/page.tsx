/**
 * Permanent redirect to the canonical agenda-item URL.
 *
 * Phase 2.6 of the re-architecture consolidated the agenda-item URL surface
 * onto `/meetings/[id]/items/[itemNumber]`. The campaign-finance content that
 * used to render here is now folded into the canonical page as an
 * operator-gated <InfluenceMapItemSection>.
 *
 * Why we still need a page file instead of `next.config.ts` redirects: the
 * destination URL needs the meeting_id + item_number, which we have to look
 * up from the agenda_item id. Static rewrites can't do DB queries.
 *
 * When the lookup fails (deleted/unknown agenda item), `notFound()` renders
 * the standard 404 — better than redirecting to a broken meetings URL.
 */
import { permanentRedirect, notFound } from 'next/navigation'
import { getAgendaItemBasic } from '@/lib/queries'
import { agendaItemPath } from '@/lib/format'

export default async function LegacyInfluenceItemPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const item = await getAgendaItemBasic(id)
  if (!item) notFound()
  permanentRedirect(agendaItemPath(item.meeting_id, item.item_number))
}
