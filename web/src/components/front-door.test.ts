import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  buildElectionFrontDoorCard,
  buildMeetingFrontDoorCard,
} from './front-door'
import FrontDoorCard from './FrontDoorCard'
import SourceBadge from './SourceBadge'
import type { FrontDoorElection, FrontDoorMeeting } from '@/lib/queries/front-door'

function election(overrides: Partial<FrontDoorElection> = {}): FrontDoorElection {
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
    extracted_at: '2026-01-01T00:00:00Z',
    confidence_score: 1,
    ...overrides,
  }
}

describe('buildElectionFrontDoorCard', () => {
  it('builds a sourced current-election card', () => {
    const card = buildElectionFrontDoorCard(election(), '2026-general')

    expect(card.href).toBe('/elections/2026-general')
    expect(card.title).toBe('2026 General Election')
    expect(card.description).toContain('November 3, 2026')
    expect(card.source).toEqual({
      tier: 1,
      name: 'City of Richmond',
      url: 'https://www.ci.richmond.ca.us/4771/ELECTION-2026',
      extractedAt: '2026-01-01T00:00:00Z',
      freshnessLabel: 'Source recorded',
    })
  })

  it('uses a claim-light fallback when no upcoming election exists', () => {
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

  it('does not expose internal source labels as public provenance', () => {
    const card = buildElectionFrontDoorCard(election({ source: 'seed' }), '2026-general')

    expect(card.source?.name).toBe('Official election record')
  })
})

describe('buildMeetingFrontDoorCard', () => {
  const meeting: FrontDoorMeeting = {
    id: 'meeting-1',
    meeting_date: '2026-08-18',
    meeting_type: 'regular',
    source_url: 'https://pub-richmond.escribemeetings.com/Meeting.aspx?Id=1',
    extracted_at: '2026-08-12T00:00:00Z',
    source_tier: 1,
    confidence_score: 1,
    body_name: 'Richmond City Council',
  }

  it('links directly to the next sourced meeting record', () => {
    expect(buildMeetingFrontDoorCard(meeting)).toEqual({
      href: '/meetings/meeting-1',
      eyebrow: 'Meeting',
      title: 'Richmond City Council meeting',
      description: 'Tuesday, August 18, 2026',
      source: {
        tier: 1,
        name: 'City of Richmond agenda',
        url: meeting.source_url,
        extractedAt: meeting.extracted_at,
      },
    })
  })

  it('uses a cache-stable label for a sourced record', () => {
    expect(buildMeetingFrontDoorCard(meeting).eyebrow).toBe('Meeting')
  })

  it('uses a claim-light fallback when no sourced meeting is available', () => {
    expect(buildMeetingFrontDoorCard(null)).toEqual({
      href: '/meetings',
      eyebrow: 'Meetings',
      title: 'Meeting records',
      description: 'Browse public meeting agendas and votes.',
      source: null,
    })
  })
})

describe('SourceBadge', () => {
  it('renders the exact source as a keyboard-focusable, AA-contrast link', () => {
    const html = renderToStaticMarkup(SourceBadge({
      tier: 1,
      source: 'City of Richmond agenda',
      sourceUrl: 'https://example.test/agenda',
      extractedAt: '2026-08-12T00:00:00Z',
    }))

    expect(html).toContain('href="https://example.test/agenda"')
    expect(html).toContain('text-sm text-slate-600')
    expect(html).toContain('min-h-11')
    expect(html).toContain('focus:ring-2')
  })

  it('distinguishes a source-record timestamp from update freshness', () => {
    const html = renderToStaticMarkup(SourceBadge({
      tier: 1,
      source: 'City of Richmond election record',
      sourceUrl: 'https://example.test/election',
      extractedAt: '2026-08-12T00:00:00Z',
      freshnessLabel: 'Source recorded',
    }))

    expect(html).toContain('Source recorded')
    expect(html).not.toContain('Updated')
  })
})

describe('FrontDoorCard', () => {
  it('keeps a visible detail action when source metadata is present', () => {
    const html = renderToStaticMarkup(
      FrontDoorCard({
        href: '/meetings/meeting-1',
        eyebrow: 'Next meeting',
        title: 'Richmond City Council meeting',
        description: 'Tuesday, August 18, 2026',
        children: 'Official source',
      }),
    )

    expect(html).toContain('Official source')
    expect(html).toContain('View details')
    expect(html.match(/href="\/meetings\/meeting-1"/g)).toHaveLength(2)
  })
})
