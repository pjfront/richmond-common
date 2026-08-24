import type { MetadataRoute } from 'next'
import { electionToSlug } from '@/lib/queries/elections'
import { nameToSlug } from '@/lib/queries/_shared'
import {
  getRecentAgendaItemSlugs,
  getSitemapCommissions,
  getSitemapDonorSlugs,
  getSitemapElections,
  getSitemapMeetings,
  getSitemapOfficials,
  getSitemapOrganizationSlugs,
} from '@/lib/queries/sitemap'
import { SITE_URL } from '@/lib/structured-data'

// Sitemap regeneration is deliberately daily. Dynamic URL enumeration is a
// bounded database read, and pipeline writes explicitly revalidate changed
// public pages without making crawlers rebuild this inventory every hour.
export const revalidate = 86400

const MAX_SITEMAP_URLS = 50_000

/**
 * Canonical, indexable, non-redirecting public routes.
 *
 * Search, tokenized subscription management, operator/API trees, the retired
 * mayor-funding artifact, and PR109's noindex/operator routes stay out. PAC
 * detail slugs remain discoverable from /pac because deriving the truthful set
 * requires a heavy 10-year contribution aggregation; repeating that work in a
 * daily sitemap would recreate the November cost problem.
 */
export const PUBLIC_STATIC_PATHS = [
  '/',
  '/meetings',
  '/meetings/most-discussed',
  '/council',
  '/council/analytics',
  '/topics',
  '/elections/find-my-district',
  '/elections/districts',
  '/elections/methodology',
  '/commissions',
  '/public-records',
  '/pac',
  '/unions',
  '/corporations',
  '/donors',
  '/influence/methodology',
  '/subscribe',
  '/about',
] as const

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
  const staticPages: MetadataRoute.Sitemap = PUBLIC_STATIC_PATHS.map((path) => ({
    url: path === '/' ? SITE_URL : `${SITE_URL}${path}`,
    changeFrequency: path === '/' || path === '/meetings' ? 'weekly' : 'monthly',
    priority: path === '/' ? 1 : path === '/meetings' ? 0.9 : 0.6,
  }))

  const dynamicData = await Promise.all([
    getSitemapMeetings(),
    getRecentAgendaItemSlugs(agendaItemSitemapCutoffUtc(asOf)),
    getSitemapOfficials(),
    getSitemapElections(),
    getSitemapCommissions(),
    getSitemapDonorSlugs(),
    getSitemapOrganizationSlugs(),
  ]).catch((error: unknown) => {
    // Pull-request builds deliberately use an inert database. Only that exact
    // boundary may emit stable routes alone. Production throws so ISR keeps
    // serving the last complete sitemap after a transient read failure.
    if (process.env.RICHMOND_BUILD_USES_PRODUCTION_DATA === 'false') {
      console.warn(
        'Dynamic sitemap data unavailable during inert build; using stable routes only.',
      )
      return null
    }
    throw error
  })

  if (!dynamicData) return staticPages
  const [
    meetings,
    itemSlugs,
    officials,
    elections,
    commissions,
    donorSlugs,
    organizationSlugs,
  ] = dynamicData

  const meetingPages: MetadataRoute.Sitemap = meetings.map((meeting) => ({
    url: `${SITE_URL}/meetings/${encodeURIComponent(meeting.id)}`,
    changeFrequency: 'monthly' as const,
    priority: 0.7,
  }))

  // Preserve the approved exact rolling 24-month agenda-item behavior.
  const itemPages: MetadataRoute.Sitemap = itemSlugs.map((item) => ({
    url: `${SITE_URL}/meetings/${encodeURIComponent(item.meeting_id)}/items/${encodeURIComponent(item.item_number.toLowerCase())}`,
    lastModified: item.meeting_date,
    changeFrequency: 'monthly' as const,
    priority: 0.6,
  }))

  const councilPages: MetadataRoute.Sitemap = officials.map((official) => ({
    url: `${SITE_URL}/council/${nameToSlug(official.name)}`,
    changeFrequency: 'monthly' as const,
    priority: 0.7,
  }))

  const electionPages: MetadataRoute.Sitemap = elections.map((election) => ({
    url: `${SITE_URL}/elections/${electionToSlug(election)}`,
    lastModified: election.updated_at,
    changeFrequency: 'weekly' as const,
    priority: 0.8,
  }))

  const commissionPages: MetadataRoute.Sitemap = commissions.map((commission) => ({
    url: `${SITE_URL}/commissions/${encodeURIComponent(commission.id)}`,
    lastModified: commission.last_modified,
    changeFrequency: 'monthly' as const,
    priority: 0.6,
  }))

  const donorPages: MetadataRoute.Sitemap = donorSlugs.map((donor) => ({
    url: `${SITE_URL}/donors/${encodeURIComponent(donor.slug)}`,
    lastModified: donor.created_at,
    changeFrequency: 'monthly' as const,
    priority: 0.5,
  }))

  const organizationPages: MetadataRoute.Sitemap = organizationSlugs.map((org) => ({
    url: `${SITE_URL}/orgs/${encodeURIComponent(org.slug)}`,
    lastModified: org.created_at,
    changeFrequency: 'monthly' as const,
    priority: 0.5,
  }))

  const entries: MetadataRoute.Sitemap = [
    ...staticPages,
    ...meetingPages,
    ...itemPages,
    ...councilPages,
    ...electionPages,
    ...commissionPages,
    ...donorPages,
    ...organizationPages,
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
