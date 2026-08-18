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
// root layout's cadence was a major Vercel + Supabase egress driver.
export const revalidate = 86400

const BASE_URL = 'https://richmondcommons.org'
const DB_PAGE_SIZE = 1_000
const MAX_SITEMAP_URLS = 50_000
export const MAX_AGENDA_ITEM_SITEMAP_ROWS = 10_000

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

/** Return the inclusive calendar-date cutoff for a rolling 24-month UTC window. */
export function agendaItemSitemapCutoffUtc(asOf: Date): string {
  if (Number.isNaN(asOf.getTime())) {
    throw new TypeError('Agenda-item sitemap cutoff requires a valid date')
  }

  const targetYear = asOf.getUTCFullYear() - 2
  const targetMonth = asOf.getUTCMonth()
  const lastDayOfTargetMonth = new Date(Date.UTC(targetYear, targetMonth + 1, 0)).getUTCDate()
  const targetDay = Math.min(asOf.getUTCDate(), lastDayOfTargetMonth)

  return [
    targetYear.toString().padStart(4, '0'),
    (targetMonth + 1).toString().padStart(2, '0'),
    targetDay.toString().padStart(2, '0'),
  ].join('-')
}

/** Page through PostgREST's row cap and fail loudly before silent truncation. */
export async function collectPaginated<T>(
  loadPage: (from: number, to: number) => Promise<T[]>,
  options: {
    maxRowsExclusive?: number
    datasetLabel?: string
  } = {},
): Promise<T[]> {
  const {
    maxRowsExclusive = MAX_SITEMAP_URLS,
    datasetLabel = 'Sitemap dataset',
  } = options
  if (
    !Number.isSafeInteger(maxRowsExclusive)
    || maxRowsExclusive <= 0
    || maxRowsExclusive % DB_PAGE_SIZE !== 0
  ) {
    throw new TypeError('Sitemap row guard must be a positive multiple of the database page size')
  }

  const rows: T[] = []
  const maxPages = maxRowsExclusive / DB_PAGE_SIZE
  for (let page = 0; page < maxPages; page++) {
    const from = page * DB_PAGE_SIZE
    const batch = await loadPage(from, from + DB_PAGE_SIZE - 1)
    rows.push(...batch)
    if (rows.length >= maxRowsExclusive) {
      throw new Error(
        `${datasetLabel} reached ${maxRowsExclusive.toLocaleString('en-US')} rows; keep it below the configured guard.`,
      )
    }
    if (batch.length < DB_PAGE_SIZE) return rows
  }
  throw new Error(`${datasetLabel} exhausted its pagination guard.`)
}

export async function buildSitemap(asOf: Date): Promise<MetadataRoute.Sitemap> {
  const agendaItemCutoff = agendaItemSitemapCutoffUtc(asOf)
  const staticPages: MetadataRoute.Sitemap = PUBLIC_STATIC_PATHS.map((path) => ({
    url: path === '/' ? BASE_URL : `${BASE_URL}${path}`,
    changeFrequency: path === '/' || path === '/meetings' ? 'weekly' : 'monthly',
    priority: path === '/' ? 1 : path === '/meetings' ? 0.9 : 0.6,
  }))

  // Keep sitemap reads parallel and bounded to lightweight public datasets.
  // Heavy PAC/donor/org profile aggregations remain discoverable from their
  // linked public indexes.
  const dynamicData = await Promise.all([
    collectPaginated(getSitemapMeetingsPage),
    collectPaginated(
      (from, to) => getSitemapAgendaItemsPage(from, to, agendaItemCutoff),
      {
        maxRowsExclusive: MAX_AGENDA_ITEM_SITEMAP_ROWS,
        datasetLabel: 'Rolling agenda-item sitemap dataset',
      },
    ),
    collectPaginated(getSitemapOfficialsPage),
    collectPaginated(getSitemapElectionsPage),
    getPromotedTopics(),
  ]).catch((error: unknown) => {
    // CI deliberately supplies an unreachable Supabase URL to prove builds
    // do not depend on production data. Preserve the stable public routes in
    // that explicit environment. Everywhere else, throw so ISR keeps serving
    // the last complete sitemap instead of replacing it with a partial one.
    if (process.env.RICHMOND_BUILD_USES_PRODUCTION_DATA === 'false') {
      console.warn('Dynamic sitemap data unavailable during inert build; using stable routes only.')
      return null
    }
    throw error
  })

  if (!dynamicData) return staticPages
  const [meetings, itemSlugs, officials, elections, topics] = dynamicData

  const meetingPages: MetadataRoute.Sitemap = meetings.map((meeting) => ({
    url: `${BASE_URL}/meetings/${meeting.id}`,
    lastModified: meeting.meeting_date,
    changeFrequency: 'monthly' as const,
    priority: 0.7,
  }))

  const itemPages: MetadataRoute.Sitemap = itemSlugs.map((item) => ({
    url: `${BASE_URL}/meetings/${item.meeting_id}/items/${encodeURIComponent(item.item_number.toLowerCase())}`,
    lastModified: item.meeting_date,
    changeFrequency: 'monthly' as const,
    priority: 0.6,
  }))

  const councilPages: MetadataRoute.Sitemap = officials.map((official) => ({
    url: `${BASE_URL}/council/${officialSlug(official.name)}`,
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

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  return buildSitemap(new Date())
}
