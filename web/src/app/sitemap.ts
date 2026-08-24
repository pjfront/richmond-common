import type { MetadataRoute } from 'next'
import { getMeetings, getOfficials, getRecentAgendaItemSlugs } from '@/lib/queries'

// Sitemap regenerates daily — slug enumeration is expensive (every dynamic
// page → DB query) and crawlers hit /sitemap.xml constantly. Inheriting the
// root layout's hourly cadence was a major Vercel + Supabase egress driver.
export const revalidate = 86400

const BASE_URL = 'https://richmondcommons.org'

function officialSlug(name: string): string {
  return name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
}

/** Return the inclusive calendar-date cutoff for a rolling 24-month UTC window. */
export function agendaItemSitemapCutoffUtc(asOf: Date): string {
  if (Number.isNaN(asOf.getTime())) {
    throw new TypeError('Agenda-item sitemap cutoff requires a valid date')
  }

  const targetYear = asOf.getUTCFullYear() - 2
  const targetMonth = asOf.getUTCMonth()
  const lastDayOfTargetMonth = new Date(
    Date.UTC(targetYear, targetMonth + 1, 0),
  ).getUTCDate()
  const targetDay = Math.min(asOf.getUTCDate(), lastDayOfTargetMonth)

  return [
    targetYear.toString().padStart(4, '0'),
    (targetMonth + 1).toString().padStart(2, '0'),
    targetDay.toString().padStart(2, '0'),
  ].join('-')
}

export async function buildSitemap(asOf: Date): Promise<MetadataRoute.Sitemap> {
  // Static pages
  const staticPages: MetadataRoute.Sitemap = [
    { url: BASE_URL, changeFrequency: 'weekly', priority: 1.0 },
    { url: `${BASE_URL}/meetings`, changeFrequency: 'weekly', priority: 0.9 },
    { url: `${BASE_URL}/council`, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${BASE_URL}/about`, changeFrequency: 'monthly', priority: 0.5 },
  ]

  // Dynamic: meeting pages
  const meetings = await getMeetings()
  const meetingPages: MetadataRoute.Sitemap = meetings.map((m) => ({
    url: `${BASE_URL}/meetings/${m.id}`,
    lastModified: m.meeting_date,
    changeFrequency: 'monthly' as const,
    priority: 0.7,
  }))

  // Dynamic: agenda item pages
  let itemSlugs: Awaited<ReturnType<typeof getRecentAgendaItemSlugs>>
  try {
    itemSlugs = await getRecentAgendaItemSlugs(
      agendaItemSitemapCutoffUtc(asOf),
    )
  } catch (error) {
    // Pull-request builds deliberately point Supabase at an inert loopback
    // URL. Production must throw so ISR preserves the prior complete sitemap.
    if (process.env.RICHMOND_BUILD_USES_PRODUCTION_DATA !== 'false') {
      throw error
    }
    console.warn(
      'Agenda-item sitemap rows unavailable during inert build; using stable routes only.',
    )
    itemSlugs = []
  }
  const itemPages: MetadataRoute.Sitemap = itemSlugs.map((i) => ({
    url: `${BASE_URL}/meetings/${i.meeting_id}/items/${encodeURIComponent(i.item_number.toLowerCase())}`,
    lastModified: i.meeting_date,
    changeFrequency: 'monthly' as const,
    priority: 0.6,
  }))

  // Dynamic: council profile pages
  const officials = await getOfficials(undefined, { councilOnly: true })
  const councilPages: MetadataRoute.Sitemap = officials.map((o) => ({
    url: `${BASE_URL}/council/${officialSlug(o.name)}`,
    changeFrequency: 'monthly' as const,
    priority: 0.6,
  }))

  return [...staticPages, ...meetingPages, ...itemPages, ...councilPages]
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  return buildSitemap(new Date())
}
