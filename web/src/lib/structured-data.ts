const SITE_URL = 'https://richmondcommons.org'

type JsonPrimitive = string | number | boolean | null
export type JsonLdValue =
  | JsonPrimitive
  | JsonLdValue[]
  | { [key: string]: JsonLdValue | undefined }

/** Serialize JSON-LD without allowing a source value to close the script tag. */
export function serializeJsonLd(value: JsonLdValue): string {
  return JSON.stringify(value).replace(/</g, '\\u003c')
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
        logo: `${SITE_URL}/icon.svg`,
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
        potentialAction: {
          '@type': 'SearchAction',
          target: {
            '@type': 'EntryPoint',
            urlTemplate: `${SITE_URL}/search?q={search_term_string}`,
          },
          'query-input': 'required name=search_term_string',
        },
      },
    ],
  }
}

interface CouncilProfileInput {
  name: string
  role: string
  seat: string | null
  slug: string
}

function roleTitle(role: string): string {
  const normalized = role.trim().toLowerCase().replaceAll('-', '_').replaceAll(' ', '_')
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
  const url = `${SITE_URL}/council/${official.slug}`
  const jobTitle = roleTitle(official.role)
  const person: { [key: string]: JsonLdValue | undefined } = {
    '@type': 'Person',
    name: official.name,
    jobTitle,
    description: official.seat ? `${jobTitle}, ${official.seat}` : jobTitle,
    url,
    affiliation: {
      '@type': 'GovernmentOrganization',
      name: 'City of Richmond, California',
      url: 'https://www.ci.richmond.ca.us/',
    },
  }

  return {
    '@context': 'https://schema.org',
    '@type': 'ProfilePage',
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
  const url = `${SITE_URL}/meetings/${meeting.id}`
  const bodyName = meeting.bodyName?.trim() || 'Richmond public body'
  const normalizedType = meeting.meetingType.trim().toLowerCase().replaceAll('_', ' ')
  const typeLabel = normalizedType === 'regular'
    ? ''
    : `${normalizedType.replace(/\b\w/g, (letter) => letter.toUpperCase())} `
  const eventName = `${bodyName} ${typeLabel}meeting`

  if (normalizedType.includes('closed session')) {
    return {
      '@context': 'https://schema.org',
      '@type': 'WebPage',
      name: `${bodyName} closed-session record`,
      description: `Record page for the ${bodyName} closed session scheduled on ${meeting.meetingDate}.`,
      url,
      isPartOf: { '@id': `${SITE_URL}/#website` },
    }
  }

  const event: { [key: string]: JsonLdValue | undefined } = {
    '@context': 'https://schema.org',
    '@type': 'Event',
    name: eventName,
    description: `${eventName} on ${meeting.meetingDate}.`,
    startDate: meeting.meetingDate,
    url,
    isAccessibleForFree: true,
    organizer: {
      '@type': 'GovernmentOrganization',
      name: 'City of Richmond, California',
      url: 'https://www.ci.richmond.ca.us/',
    },
  }

  if (meeting.agendaUrl) event.sameAs = meeting.agendaUrl
  if (meeting.cancelledAt) {
    event.eventStatus = 'https://schema.org/EventCancelled'
  }

  return event
}

interface ElectionPageInput {
  name: string
  electionDate: string
  slug: string
  description: string
}

export function electionPageStructuredData(
  election: ElectionPageInput,
): JsonLdValue {
  const url = `${SITE_URL}/elections/${election.slug}`
  return {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: election.name,
    description: election.description,
    url,
    isPartOf: { '@id': `${SITE_URL}/#website` },
    about: {
      '@type': 'Event',
      name: election.name,
      startDate: election.electionDate,
      location: {
        '@type': 'City',
        name: 'Richmond, California',
      },
    },
  }
}
