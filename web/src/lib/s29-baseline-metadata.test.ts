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

describe('released public metadata', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('includes canonical council metadata', async () => {
    mocks.getOfficialBySlug.mockResolvedValue({
      name: 'Example Member',
      role: 'council_member',
    })

    await expect(councilMetadata({
      params: Promise.resolve({ slug: 'example-member' }),
    })).resolves.toEqual({
      title: 'Example Member, Council Member',
      description: 'Voting record, attendance, and campaign finance data for Example Member, Richmond City Council.',
      alternates: { canonical: 'https://richmondcommons.org/council/example-member' },
      openGraph: {
        title: 'Example Member, Council Member | Richmond Commons',
        description: 'Voting record, attendance, and campaign finance data for Example Member, Richmond City Council.',
        type: 'profile',
        url: 'https://richmondcommons.org/council/example-member',
      },
    })
  })

  it('uses lightweight election metadata without candidate enrichment reads', async () => {
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
      title: '2026 Primary Election: Candidates & Campaign Finance',
      description: '2026 Primary Election information for Richmond, California, including candidates, voter information, and public campaign-finance filings when available.',
      alternates: { canonical: 'https://richmondcommons.org/elections/2026-primary' },
      openGraph: {
        title: '2026 Primary Election | Richmond Commons',
        description: '2026 Primary Election information for Richmond, California, including candidates, voter information, and public campaign-finance filings when available.',
        url: 'https://richmondcommons.org/elections/2026-primary',
      },
    })
    expect(mocks.getElectionWithCandidates).not.toHaveBeenCalled()
  })

  it('names the actual public body and canonical meeting URL', async () => {
    mocks.getMeeting.mockResolvedValue({
      meeting_date: '2026-08-18',
      meeting_type: 'regular',
      body_name: 'Richmond City Council',
    })

    await expect(meetingMetadata({
      params: Promise.resolve({ id: 'meeting-1' }),
    })).resolves.toEqual({
      title: 'Tuesday, August 18, 2026 — Richmond City Council',
      description: 'Richmond City Council regular meeting on Tuesday, August 18, 2026. Agenda items, votes, and plain-language summaries.',
      alternates: { canonical: 'https://richmondcommons.org/meetings/meeting-1' },
      openGraph: {
        title: 'Tuesday, August 18, 2026 — Richmond City Council | Richmond Commons',
        description: 'Richmond City Council regular meeting on Tuesday, August 18, 2026. Agenda items, votes, and plain-language summaries.',
        type: 'article',
        url: 'https://richmondcommons.org/meetings/meeting-1',
      },
    })
  })
})
