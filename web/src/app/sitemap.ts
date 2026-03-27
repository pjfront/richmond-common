import type { MetadataRoute } from 'next'
import { getMeetings, getOfficials, getAgendaItemSlugs } from '@/lib/queries'

const BASE_URL = 'https://richmondcommons.org'

function officialSlug(name: string): string {
  return name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
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
  const itemSlugs = await getAgendaItemSlugs()
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
