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

  it('uses the City only as a council affiliation or meeting organizer', () => {
    const profile = councilProfileStructuredData({
      name: 'Example Member',
      role: 'council_member',
      seat: 'District 1',
      slug: 'example-member',
    }) as { mainEntity: { affiliation: { '@type': string } } }
    const meeting = meetingEventStructuredData({
      id: 'meeting-1',
      meetingDate: '2026-08-11',
      meetingType: 'regular',
      agendaUrl: null,
      cancelledAt: null,
    }) as { organizer: { '@type': string } }

    expect(profile.mainEntity.affiliation['@type']).toBe('GovernmentOrganization')
    expect(meeting.organizer['@type']).toBe('GovernmentOrganization')
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
