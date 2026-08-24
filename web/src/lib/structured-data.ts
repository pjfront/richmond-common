export const SITE_URL = 'https://richmondcommons.org'

const CITY_WEBSITE_URL = 'https://www.richmondca.gov/'

type JsonPrimitive = string | number | boolean | null
export type JsonLdValue =
  | JsonPrimitive
  | JsonLdValue[]
  | { [key: string]: JsonLdValue | undefined }

type JsonLdObject = { [key: string]: JsonLdValue | undefined }

/** Build one canonical URL on the apex host. */
export function canonicalUrl(path = '/'): string {
  if (path === '/' || path === '') return SITE_URL
  return `${SITE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

/** Serialize JSON-LD without allowing sourced text to close the script tag. */
export function serializeJsonLd(value: JsonLdValue): string {
  return JSON.stringify(value)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026')
}

function safeHttpUrl(value: string | null): string | undefined {
  if (!value) return undefined
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:'
      ? url.toString()
      : undefined
  } catch {
    return undefined
  }
}

export function siteStructuredData(): JsonLdValue {
  const organizationId = `${SITE_URL}/#organization`
  const websiteId = `${SITE_URL}/#website`

  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': organizationId,
        name: 'Richmond Commons',
        url: SITE_URL,
        logo: {
          '@type': 'ImageObject',
          url: `${SITE_URL}/icon.svg`,
        },
        description:
          'An independent civic information project that makes Richmond, California city government easier to understand.',
        areaServed: {
          '@type': 'City',
          name: 'Richmond, California',
        },
      },
      {
        '@type': 'WebSite',
        '@id': websiteId,
        name: 'Richmond Commons',
        url: SITE_URL,
        inLanguage: 'en-US',
        publisher: { '@id': organizationId },
      },
    ],
  }
}

interface CouncilProfileInput {
  name: string
  role: string
  seat: string | null
  slug: string
  isCurrent: boolean
}

function roleTitle(role: string): string {
  const normalized = role
    .trim()
    .toLowerCase()
    .replaceAll('-', '_')
    .replaceAll(' ', '_')
  const knownTitles: Record<string, string> = {
    mayor: 'Mayor',
    vice_mayor: 'Vice Mayor',
    councilmember: 'City Council Member',
    council_member: 'City Council Member',
    city_town_council_member: 'City Council Member',
  }
  return knownTitles[normalized]
    ?? role.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function councilProfileStructuredData(
  official: CouncilProfileInput,
): JsonLdValue {
  const url = canonicalUrl(`/council/${encodeURIComponent(official.slug)}`)
  const jobTitle = roleTitle(official.role)
  const personId = `${url}#person`
  const person: JsonLdObject = {
    '@type': 'Person',
    '@id': personId,
    name: official.name,
    description: official.isCurrent
      ? (official.seat ? `${jobTitle}, ${official.seat}` : jobTitle)
      : `Richmond council voting record associated with the filed role ${jobTitle}${official.seat ? `, ${official.seat}` : ''}.`,
    url,
  }
  if (official.isCurrent) {
    person.jobTitle = jobTitle
    person.affiliation = {
      '@type': 'GovernmentOrganization',
      name: 'City of Richmond, California',
      url: CITY_WEBSITE_URL,
    }
  }

  return {
    '@context': 'https://schema.org',
    '@type': 'ProfilePage',
    '@id': `${url}#webpage`,
    name: `${official.name} voting record and council profile`,
    url,
    isPartOf: { '@id': `${SITE_URL}/#website` },
    mainEntity: person,
  }
}

interface MeetingEventInput {
  id: string
  meetingDate: string
  meetingType: string
  bodyName: string | null
  agendaUrl: string | null
  cancelledAt: string | null
}

export function meetingEventStructuredData(
  meeting: MeetingEventInput,
): JsonLdValue {
  const url = canonicalUrl(`/meetings/${encodeURIComponent(meeting.id)}`)
  const bodyName = meeting.bodyName?.trim() || 'Richmond public body'
  const normalizedType = meeting.meetingType
    .trim()
    .toLowerCase()
    .replaceAll('_', ' ')
  const typeLabel = normalizedType === 'regular'
    ? ''
    : `${normalizedType.replace(/\b\w/g, (letter) => letter.toUpperCase())} `
  const eventName = `${bodyName} ${typeLabel}meeting`
  const page: JsonLdObject = {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    '@id': `${url}#webpage`,
    name: eventName,
    description: `Record page for the ${eventName} scheduled on ${meeting.meetingDate}.`,
    url,
    isPartOf: { '@id': `${SITE_URL}/#website` },
  }

  // A closed session has a public record page, but should not be advertised
  // to crawlers as an attendable public event.
  if (normalizedType.includes('closed session')) return page

  const event: JsonLdObject = {
    '@type': 'Event',
    '@id': `${url}#meeting`,
    name: eventName,
    startDate: meeting.meetingDate,
    url,
    organizer: {
      '@type': 'GovernmentOrganization',
      name: 'City of Richmond, California',
      url: CITY_WEBSITE_URL,
    },
  }
  const agendaUrl = safeHttpUrl(meeting.agendaUrl)
  if (agendaUrl) event.sameAs = agendaUrl
  if (meeting.cancelledAt) {
    event.eventStatus = 'https://schema.org/EventCancelled'
  }
  page.mainEntity = event
  return page
}

interface ElectionPageInput {
  name: string
  electionDate: string
  slug: string
  description: string
  sourceUrl: string | null
}

export function electionPageStructuredData(
  election: ElectionPageInput,
): JsonLdValue {
  const url = canonicalUrl(`/elections/${encodeURIComponent(election.slug)}`)
  const electionEvent: JsonLdObject = {
    '@type': 'Event',
    '@id': `${url}#election`,
    name: election.name,
    startDate: election.electionDate,
    location: {
      '@type': 'City',
      name: 'Richmond, California',
    },
  }
  const sourceUrl = safeHttpUrl(election.sourceUrl)
  if (sourceUrl) electionEvent.sameAs = sourceUrl

  return {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    '@id': `${url}#webpage`,
    name: election.name,
    description: election.description,
    url,
    isPartOf: { '@id': `${SITE_URL}/#website` },
    about: electionEvent,
  }
}
