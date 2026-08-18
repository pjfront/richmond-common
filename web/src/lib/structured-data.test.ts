import { describe, expect, it } from 'vitest'
import {
  councilProfileStructuredData,
  electionPageStructuredData,
  meetingEventStructuredData,
  serializeJsonLd,
  siteStructuredData,
} from './structured-data'

describe('structured data', () => {
  it('identifies Richmond Commons as an independent Organization and WebSite', () => {
    const data = siteStructuredData() as {
      '@graph': Array<{
        '@type': string
        description?: string
        potentialAction?: { '@type': string; target: { urlTemplate: string } }
      }>
    }
    expect(data['@graph'].map((entry) => entry['@type'])).toEqual([
      'Organization',
      'WebSite',
    ])
    expect(data['@graph'][0].description).toContain('independent')
    expect(data['@graph'].some((entry) => entry['@type'] === 'GovernmentOrganization')).toBe(false)
    expect(data['@graph'][1].potentialAction).toEqual({
      '@type': 'SearchAction',
      target: {
        '@type': 'EntryPoint',
        urlTemplate: 'https://richmondcommons.org/search?q={search_term_string}',
      },
      'query-input': 'required name=search_term_string',
    })
  })

  it('uses the official role as jobTitle and keeps the district in description', () => {
    const profile = councilProfileStructuredData({
      name: 'Example Member',
      role: 'council_member',
      seat: 'District 1',
      slug: 'example-member',
    }) as {
      mainEntity: {
        jobTitle: string
        description: string
        affiliation: { '@type': string }
      }
    }

    expect(profile.mainEntity.jobTitle).toBe('City Council Member')
    expect(profile.mainEntity.description).toBe('City Council Member, District 1')
    expect(profile.mainEntity.affiliation['@type']).toBe('GovernmentOrganization')
  })

  it('names the actual public body as the meeting organizer context', () => {
    const meeting = meetingEventStructuredData({
      id: 'meeting-1',
      meetingDate: '2026-08-11',
      meetingType: 'regular',
      bodyName: 'Planning Commission',
      agendaUrl: null,
      cancelledAt: null,
    }) as { name: string; organizer: { '@type': string } }

    expect(meeting.name).toBe('Planning Commission meeting')
    expect(meeting.organizer['@type']).toBe('GovernmentOrganization')
  })

  it('does not describe a closed session as a free public Event', () => {
    const meeting = meetingEventStructuredData({
      id: 'meeting-closed',
      meetingDate: '2026-08-11',
      meetingType: 'closed_session',
      bodyName: 'Richmond City Council',
      agendaUrl: 'https://example.com/agenda',
      cancelledAt: null,
    }) as { '@type': string; isAccessibleForFree?: boolean; organizer?: unknown }

    expect(meeting['@type']).toBe('WebPage')
    expect(meeting.isAccessibleForFree).toBeUndefined()
    expect(meeting.organizer).toBeUndefined()
  })

  it('describes an election page without claiming Richmond Commons runs it', () => {
    const data = electionPageStructuredData({
      name: '2026 General Election',
      electionDate: '2026-11-03',
      slug: '2026-general',
      description: 'Richmond election information.',
    }) as { '@type': string; about: { '@type': string }; organizer?: unknown }

    expect(data['@type']).toBe('WebPage')
    expect(data.about['@type']).toBe('Event')
    expect(data.organizer).toBeUndefined()
  })

  it('escapes script-closing input', () => {
    const serialized = serializeJsonLd({ name: '</script><script>alert(1)</script>' })
    expect(serialized).not.toContain('<')
    expect(serialized).toContain('\\u003c/script>')
  })
})
