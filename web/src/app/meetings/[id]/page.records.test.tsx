import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { ReactNode } from 'react'
const mocks = vi.hoisted(() => ({ meeting: vi.fn() }))
vi.mock('@/lib/queries', () => ({ getMeeting: mocks.meeting,
  getAdjacentMeetings: async () => ({ previous: null, next: null }), getPromotedTopicLabels: async () => [] }))
vi.mock('@/components/MeetingPageLayout', () => ({ default: ({ children }: { children: ReactNode }) => <div>{children}</div> }))
vi.mock('@/components/SubscribeCTA', () => ({ default: () => null }))
vi.mock('@/components/OperatorGate', () => ({ default: () => null }))
import MeetingDetailPage from './page'

const id = '11111111-1111-4111-8111-111111111111'
const meeting = { id, meeting_date: '2026-07-28', meeting_type: 'regular', body_name: 'Richmond City Council',
  agenda_url: 'https://www.richmondca.gov/agenda.pdf', minutes_url: 'https://www.richmondca.gov/minutes.pdf',
  meeting_summary: 'Unsupported largest spending item.', meeting_recap: 'Housing for the twelfth time this year.',
  orientation_preview: 'The council will decide.', transcript_recap: 'An unsupported generated outcome.',
  attendance: [], total_public_comments: 555,
  agenda_items: [
    { id: 'item-1', category: 'procedural', is_consent_calendar: true, public_comment_count: 987, motions: [{ id: 'motion-1' }] },
    { id: 'item-2', category: 'housing', is_consent_calendar: false, public_comment_count: 0, motions: [{ id: 'motion-2' }] },
  ],
}
describe('public meeting record context', () => {
  beforeEach(() => { mocks.meeting.mockReset(); mocks.meeting.mockResolvedValue(meeting) })
  it('shows recorded agenda/motion counts and original sources even when stored narratives exist', async () => {
    const html = renderToStaticMarkup(await MeetingDetailPage({ params: Promise.resolve({ id }) }))
    expect(html).toContain('2 agenda items recorded')
    expect(html).toContain('2 motion records')
    expect(html).toContain('href="https://www.richmondca.gov/agenda.pdf"')
    expect(html).toContain('href="https://www.richmondca.gov/minutes.pdf"')
    expect(html).not.toMatch(/largest spending|twelfth time|council will decide|unsupported generated|987|555|2 votes/)
  })
  it('keeps missing motion evidence distinct from proof of no votes or unpublished minutes', async () => {
    mocks.meeting.mockResolvedValue({ ...meeting, agenda_items: [], minutes_url: null })
    const html = renderToStaticMarkup(await MeetingDetailPage({ params: Promise.resolve({ id }) }))
    expect(html).toContain('does not establish that the meeting had no votes')
    expect(html).not.toContain('Minutes not yet published by the City Clerk')
    expect(html).not.toContain('0 votes')
  })
})
