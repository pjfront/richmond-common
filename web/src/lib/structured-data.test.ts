import { describe, expect, it } from 'vitest'
import {
  canonicalUrl,
  councilProfileStructuredData,
  electionPageStructuredData,
  meetingEventStructuredData,
  serializeJsonLd,
  siteStructuredData,
} from './structured-data'

describe('structured data', () => {
  it('uses only canonical apex URLs', () => {
    expect(canonicalUrl()).toBe('https://richmondcommons.org')
    expect(canonicalUrl('/meetings')).toBe('https://richmondcommons.org/meetings')
    expect(canonicalUrl('council/example')).toBe(
      'https://richmondcommons.org/council/example',
    )
  })

  it('identifies Richmond Commons as an independent Organization and WebSite', () => {
    const data = siteStructuredData() as {
      '@graph': Array<{
        '@type': string
        description?: string
        potentialAction?: unknown
      }>
    }
    expect(data['@graph'].map((entry) => entry['@type'])).toEqual([
      'Organization',
      'WebSite',
    ])
    expect(data['@graph'][0].description).toContain('independent')
    expect(data['@graph'].some((entry) => entry['@type'] === 'GovernmentOrganization'))
      .toBe(false)
    // Search is intentionally not advertised to crawlers: it is a
    // force-dynamic resident tool, not a bounded canonical content surface.
    expect(data['@graph'][1].potentialAction).toBeUndefined()
  })

  it('uses the filed council role as job title and keeps the seat in context', () => {
    const profile = councilProfileStructuredData({
      name: 'Example Member',
      role: 'council_member',
      seat: 'District 1',
      slug: 'example-member',
      isCurrent: true,
    }) as {
      url: string
      mainEntity: {
        jobTitle: string
        description: string
        affiliation: { '@type': string }
      }
    }

    expect(profile.url).toBe('https://richmondcommons.org/council/example-member')
    expect(profile.mainEntity.jobTitle).toBe('City Council Member')
    expect(profile.mainEntity.description).toBe('City Council Member, District 1')
    expect(profile.mainEntity.affiliation['@type']).toBe('GovernmentOrganization')
  })

  it('does not present a historical council record as a current job', () => {
    const profile = councilProfileStructuredData({
      name: 'Former Member',
      role: 'council_member',
      seat: 'District 1',
      slug: 'former-member',
      isCurrent: false,
    }) as {
      mainEntity: { jobTitle?: string; affiliation?: unknown; description: string }
    }

    expect(profile.mainEntity.jobTitle).toBeUndefined()
    expect(profile.mainEntity.affiliation).toBeUndefined()
    expect(profile.mainEntity.description).toContain('filed role')
  })

  it('describes a public-body meeting without claiming Richmond Commons runs it', () => {
    const page = meetingEventStructuredData({
      id: 'meeting-1',
      meetingDate: '2026-08-11',
      meetingType: 'regular',
      bodyName: 'Planning Commission',
      agendaUrl: 'https://www.richmondca.gov/agenda',
      cancelledAt: null,
    }) as {
      '@type': string
      mainEntity: {
        '@type': string
        name: string
        organizer: { '@type': string; name: string }
        sameAs: string
        isAccessibleForFree?: boolean
      }
    }

    expect(page['@type']).toBe('WebPage')
    expect(page.mainEntity['@type']).toBe('Event')
    expect(page.mainEntity.name).toBe('Planning Commission meeting')
    expect(page.mainEntity.organizer).toEqual({
      '@type': 'GovernmentOrganization',
      name: 'City of Richmond, California',
      url: 'https://www.richmondca.gov/',
    })
    expect(page.mainEntity.sameAs).toBe('https://www.richmondca.gov/agenda')
    expect(page.mainEntity.isAccessibleForFree).toBeUndefined()
  })

  it('does not describe a closed session as a public Event', () => {
    const meeting = meetingEventStructuredData({
      id: 'meeting-closed',
      meetingDate: '2026-08-11',
      meetingType: 'closed_session',
      bodyName: 'Richmond City Council',
      agendaUrl: 'https://example.com/agenda',
      cancelledAt: null,
    }) as { '@type': string; mainEntity?: unknown }

    expect(meeting['@type']).toBe('WebPage')
    expect(meeting.mainEntity).toBeUndefined()
  })

  it('marks a cancelled public meeting and rejects a non-http source URL', () => {
    const meeting = meetingEventStructuredData({
      id: 'meeting-cancelled',
      meetingDate: '2026-08-12',
      meetingType: 'special',
      bodyName: 'Planning Commission',
      agendaUrl: 'javascript:alert(1)',
      cancelledAt: '2026-08-10T12:00:00Z',
    }) as {
      mainEntity: { eventStatus: string; sameAs?: string }
    }

    expect(meeting.mainEntity.eventStatus).toBe(
      'https://schema.org/EventCancelled',
    )
    expect(meeting.mainEntity.sameAs).toBeUndefined()
  })

  it('describes an election without claiming Richmond Commons administers it', () => {
    const data = electionPageStructuredData({
      name: '2026 General Election',
      electionDate: '2026-11-03',
      slug: '2026-general',
      description: 'Richmond election information.',
      sourceUrl: 'https://www.richmondca.gov/elections',
    }) as {
      '@type': string
      url: string
      about: { '@type': string; sameAs: string }
      organizer?: unknown
    }

    expect(data['@type']).toBe('WebPage')
    expect(data.url).toBe('https://richmondcommons.org/elections/2026-general')
    expect(data.about['@type']).toBe('Event')
    expect(data.about.sameAs).toBe('https://www.richmondca.gov/elections')
    expect(data.organizer).toBeUndefined()
  })

  it('escapes script-closing input', () => {
    const serialized = serializeJsonLd({
      name: '</script><script>alert(1)</script>&',
    })
    expect(serialized).not.toContain('<')
    expect(serialized).not.toContain('>')
    expect(serialized).not.toContain('&')
    expect(serialized).toContain('\\u003c/script\\u003e')
  })
})
