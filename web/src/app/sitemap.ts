import type { MetadataRoute } from 'next'
import {
  electionToSlug,
  getPromotedTopics,
  getSitemapAgendaItemsPage,
  getSitemapElectionsPage,
  getSitemapMeetingsPage,
  getSitemapOfficialsPage,
} from '@/lib/queries'

// Sitemap regenerates daily — slug enumeration is expensive (every dynamic
// page → DB query) and crawlers hit /sitemap.xml constantly. Inheriting the
// root layout's hourly cadence was a major Vercel + Supabase egress driver.
export const revalidate = 86400

const BASE_URL = 'https://richmondcommons.org'
const DB_PAGE_SIZE = 1_000
const MAX_DB_PAGES = 50
const MAX_SITEMAP_URLS = 50_000

export const PUBLIC_STATIC_PATHS = [
  '/',
  '/meetings',
  '/meetings/most-discussed',
  '/council',
  '/topics',
  '/elections/find-my-district',
  '/elections/districts',
  '/elections/methodology',
  '/subscribe',
  '/about',
  '/pac',
  '/unions',
  '/corporations',
  '/donors',
] as const

function officialSlug(name: string): string {
  return name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
}

/** Page through PostgREST's row cap and fail loudly before silent truncation. */
export async function collectPaginated<T>(
  loadPage: (from: number, to: number) => Promise<T[]>,
): Promise<T[]> {
  const rows: T[] = []
  for (let page = 0; page < MAX_DB_PAGES; page++) {
    const from = page * DB_PAGE_SIZE
    const batch = await loadPage(from, from + DB_PAGE_SIZE - 1)
    rows.push(...batch)
    if (batch.length < DB_PAGE_SIZE) return rows
  }
  throw new Error('Sitemap dataset reached 50,000 rows; shard the sitemap before publishing more URLs.')
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticPages: MetadataRoute.Sitemap = PUBLIC_STATIC_PATHS.map((path) => ({
    url: path === '/' ? BASE_URL : `${BASE_URL}${path}`,
    changeFrequency: path === '/' || path === '/meetings' ? 'weekly' : 'monthly',
    priority: path === '/' ? 1 : path === '/meetings' ? 0.9 : 0.6,
  }))

  // Keep sitemap reads parallel and bounded to the same lightweight public
  // datasets already used by their index pages. Heavy PAC/donor/org profile
  // aggregations remain discoverable from their linked public indexes.
  const [meetings, itemSlugs, officials, elections, topics] =
    await Promise.all([
      collectPaginated(getSitemapMeetingsPage),
      collectPaginated(getSitemapAgendaItemsPage),
      collectPaginated(getSitemapOfficialsPage),
      collectPaginated(getSitemapElectionsPage),
      getPromotedTopics(),
    ])

  const meetingPages: MetadataRoute.Sitemap = meetings.map((m) => ({
    url: `${BASE_URL}/meetings/${m.id}`,
    lastModified: m.meeting_date,
    changeFrequency: 'monthly' as const,
    priority: 0.7,
  }))

  // Dynamic: agenda item pages
  const itemPages: MetadataRoute.Sitemap = itemSlugs.map((i) => ({
    url: `${BASE_URL}/meetings/${i.meeting_id}/items/${encodeURIComponent(i.item_number.toLowerCase())}`,
    lastModified: i.meeting_date,
    changeFrequency: 'monthly' as const,
    priority: 0.6,
  }))

  // Dynamic: council profile pages
  const councilPages: MetadataRoute.Sitemap = officials.map((o) => ({
    url: `${BASE_URL}/council/${officialSlug(o.name)}`,
    changeFrequency: 'monthly' as const,
    priority: 0.6,
  }))

  const electionPages: MetadataRoute.Sitemap = elections.map((election) => ({
    url: `${BASE_URL}/elections/${electionToSlug(election)}`,
    lastModified: election.updated_at ?? election.election_date,
    changeFrequency: 'weekly' as const,
    priority: 0.8,
  }))

  const topicPages: MetadataRoute.Sitemap = topics.map((topic) => ({
    url: `${BASE_URL}/topics/${topic.slug}`,
    lastModified: topic.latest_meeting_date,
    changeFrequency: 'weekly' as const,
    priority: 0.6,
  }))

  const entries: MetadataRoute.Sitemap = [
    ...staticPages,
    ...meetingPages,
    ...itemPages,
    ...councilPages,
    ...electionPages,
    ...topicPages,
  ]

  const uniqueEntries = Array.from(
    new Map(entries.map((entry) => [entry.url, entry])).values(),
  )
  if (uniqueEntries.length > MAX_SITEMAP_URLS) {
    throw new Error('Sitemap exceeds 50,000 URLs; split it with generateSitemaps().')
  }
  return uniqueEntries
}
