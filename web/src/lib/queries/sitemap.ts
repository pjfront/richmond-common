import { RICHMOND_FIPS, supabase } from './_shared'

const COLS_SITEMAP_AGENDA_ITEM =
  'meeting_id, item_number, meetings!inner(meeting_date, city_fips, source_cancelled_at)'

/**
 * The approved rolling sitemap must fail closed before it can silently hit
 * Supabase's 10,000-row response ceiling.
 */
const MAX_AGENDA_ITEM_SITEMAP_ROWS = 10_000

export interface SitemapAgendaItemRow {
  meeting_id: string
  item_number: string
  meeting_date: string
}

/**
 * Load every active agenda item in the bounded sitemap window.
 *
 * `count: exact` plus the length check makes a response-cap change visible:
 * a partial sitemap is rejected instead of being published as complete.
 */
export async function getRecentAgendaItemSlugs(
  meetingDateCutoff: string,
  cityFips = RICHMOND_FIPS,
): Promise<SitemapAgendaItemRow[]> {
  const { data, error, count } = await supabase
    .from('agenda_items')
    .select(COLS_SITEMAP_AGENDA_ITEM, { count: 'exact' })
    .is('agenda_source_retired_at', null)
    .is('meetings.source_cancelled_at', null)
    .eq('meetings.city_fips', cityFips)
    .gte('meetings.meeting_date', meetingDateCutoff)
    .order('id')

  if (error) {
    console.error('getRecentAgendaItemSlugs query failed:', error)
    throw error
  }
  if (count === null) {
    throw new Error('Agenda-item sitemap query did not return an exact row count.')
  }
  if (count >= MAX_AGENDA_ITEM_SITEMAP_ROWS) {
    throw new Error(
      `Rolling agenda-item sitemap dataset reached ${MAX_AGENDA_ITEM_SITEMAP_ROWS.toLocaleString('en-US')} rows.`,
    )
  }

  const rows = data ?? []
  if (rows.length !== count) {
    throw new Error(
      `Agenda-item sitemap query returned ${rows.length.toLocaleString('en-US')} of ${count.toLocaleString('en-US')} rows.`,
    )
  }

  return rows.map((row) => {
    const meeting = row.meetings as unknown as { meeting_date: string }
    return {
      meeting_id: row.meeting_id as string,
      item_number: row.item_number as string,
      meeting_date: meeting.meeting_date,
    }
  })
}
