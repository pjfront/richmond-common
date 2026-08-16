import { describe, expect, it } from 'vitest'
import {
  buildElectionFrontDoorCard,
  buildMeetingFrontDoorCard,
} from './front-door'
import type { Election } from '@/lib/types'
import type { FrontDoorMeeting } from '@/lib/queries/meetings'

function election(overrides: Partial<Election> = {}): Election {
  return {
    id: 'election-1',
    city_fips: '0660620',
    election_date: '2026-11-03',
    election_name: '2026 General Election',
    election_type: 'general',
    filing_deadline: null,
    jurisdiction: 'Richmond, California',
    notes: null,
    source: 'City of Richmond',
    source_tier: 1,
    source_url: 'https://www.ci.richmond.ca.us/4771/ELECTION-2026',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    ...overrides,
  }
}

describe('buildElectionFrontDoorCard', () => {
  it('builds the current election card from sourced election data', () => {
    const card = buildElectionFrontDoorCard(election(), '2026-general')

    expect(card.href).toBe('/elections/2026-general')
    expect(card.title).toBe('2026 General Election')
    expect(card.description).toContain('November 3, 2026')
    expect(card.source).toEqual({
      tier: 1,
      name: 'City of Richmond',
      url: 'https://www.ci.richmond.ca.us/4771/ELECTION-2026',
      updatedAt: '2026-08-01T00:00:00Z',
    })
  })

  it('falls back to the evergreen elections route when none is upcoming', () => {
    expect(buildElectionFrontDoorCard(null, null)).toEqual({
      href: '/elections',
      eyebrow: 'Elections',
      title: 'Election information',
      description: 'Find election dates, candidates, and voter information.',
      source: null,
    })
  })

  it('derives a plain title when the election has no display name', () => {
    const card = buildElectionFrontDoorCard(
      election({ election_name: null, election_type: 'special' }),
      '2026-special',
    )

    expect(card.title).toBe('2026 Special')
  })

  it('does not publish a dynamic election claim without trusted provenance', () => {
    const card = buildElectionFrontDoorCard(
      election({ source_url: null, source_tier: 3 }),
      '2026-general',
    )

    expect(card.href).toBe('/elections')
    expect(card.source).toBeNull()
  })

  it('does not expose an internal seed label as public provenance', () => {
    const card = buildElectionFrontDoorCard(
      election({ source: 'seed' }),
      '2026-general',
    )

    expect(card.source?.name).toBe('Official election record')
  })
})

describe('buildMeetingFrontDoorCard', () => {
  const meeting: FrontDoorMeeting = {
    id: 'meeting-1',
    meeting_date: '2026-08-18',
    meeting_type: 'regular',
    agenda_url: 'https://pub-richmond.escribemeetings.com/Meeting.aspx?Id=1',
    extracted_at: '2026-08-12T00:00:00Z',
    body_name: 'Richmond City Council',
  }

  it('links directly to the next sourced meeting record', () => {
    expect(buildMeetingFrontDoorCard(meeting, '2026-08-15')).toEqual({
      href: '/meetings/meeting-1',
      eyebrow: 'Next meeting',
      title: 'Richmond City Council meeting',
      description: 'Tuesday, August 18, 2026',
      source: {
        tier: 1,
        name: 'City of Richmond agenda',
        url: meeting.agenda_url,
        updatedAt: meeting.extracted_at,
      },
    })
  })

  it('labels a sourced past record as the latest meeting', () => {
    expect(buildMeetingFrontDoorCard(meeting, '2026-08-20').eyebrow).toBe('Latest meeting')
  })

  it('falls back to a claim-free meeting index card', () => {
    expect(buildMeetingFrontDoorCard(null, '2026-08-15')).toEqual({
      href: '/meetings',
      eyebrow: 'Meetings',
      title: 'Meeting records',
      description: 'Browse public meeting agendas and votes.',
      source: null,
    })
  })
})
