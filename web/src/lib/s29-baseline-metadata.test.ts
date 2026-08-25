import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getOfficialBySlug: vi.fn(),
  getElectionBySlug: vi.fn(),
  getElectionWithCandidates: vi.fn(),
  getMeeting: vi.fn(),
}))

vi.mock('@/lib/queries', () => ({
  getOfficialBySlug: mocks.getOfficialBySlug,
  getElectionBySlug: mocks.getElectionBySlug,
  getElectionWithCandidates: mocks.getElectionWithCandidates,
  getMeeting: mocks.getMeeting,
}))

import { generateMetadata as councilMetadata } from '@/app/council/[slug]/page'
import { generateMetadata as electionMetadata } from '@/app/elections/[slug]/page'
import { generateMetadata as meetingMetadata } from '@/app/meetings/[id]/page'

describe('S29 baseline metadata hold', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('preserves council metadata without treatment canonical fields', async () => {
    mocks.getOfficialBySlug.mockResolvedValue({
      name: 'Example Member',
      role: 'council_member',
    })

    await expect(councilMetadata({
      params: Promise.resolve({ slug: 'example-member' }),
    })).resolves.toEqual({
      title: 'Example Member, Council Member',
      description: 'Voting record, attendance, and campaign finance data for Example Member, Richmond City Council.',
      openGraph: {
        title: 'Example Member, Council Member | Richmond Commons',
        description: 'Voting record, attendance, and campaign finance data for Example Member, Richmond City Council.',
        type: 'profile',
      },
    })
  })

  it('preserves candidate-enriched election metadata during baseline', async () => {
    mocks.getElectionBySlug.mockResolvedValue({
      id: 'election-1',
      election_name: '2026 Primary Election',
      election_date: '2026-06-02',
      election_type: 'primary',
    })
    mocks.getElectionWithCandidates.mockResolvedValue({
      candidates: [
        { candidate_name: 'Candidate One' },
        { candidate_name: 'Candidate Two' },
      ],
    })

    await expect(electionMetadata({
      params: Promise.resolve({ slug: '2026-primary' }),
    })).resolves.toEqual({
      title: '2026 Primary Election: Candidates & Campaign Finance | Richmond Commons',
      description: 'Richmond 2026 Primary Election: candidates, campaign fundraising, top donors, and voter information. Races: Mayor, District 2, District 3, District 4. Candidates: Candidate One, Candidate Two.',
      openGraph: {
        title: '2026 Primary Election | Richmond Commons',
        description: 'Track candidates, fundraising, and voter information for the 2026 Primary Election.',
      },
    })
  })

  it('preserves the production meeting title and description', async () => {
    mocks.getMeeting.mockResolvedValue({
      meeting_date: '2026-08-18',
      meeting_type: 'regular',
    })

    await expect(meetingMetadata({
      params: Promise.resolve({ id: 'meeting-1' }),
    })).resolves.toEqual({
      title: 'Tuesday, August 18, 2026 Meeting',
      description: 'Richmond City Council regular meeting on Tuesday, August 18, 2026. Agenda items, votes, and plain English summaries.',
      openGraph: {
        title: 'Tuesday, August 18, 2026 Meeting | Richmond Commons',
        description: 'Richmond City Council regular meeting on Tuesday, August 18, 2026. Agenda items, votes, and plain English summaries.',
        type: 'article',
      },
    })
  })
})
