import { describe, expect, it } from 'vitest'
import { buildElectionFrontDoorCard } from './front-door'
import type { Election } from '@/lib/types'

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
})
