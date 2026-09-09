import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import MeetingListCard from './MeetingListCard'
import MeetingCard from './MeetingCard'
import MeetingAgendaList from './MeetingAgendaList'
import CommissionMeetingHistory from './CommissionMeetingHistory'
import type { MeetingWithCounts } from '@/lib/types'

const meeting: MeetingWithCounts = {
  id: 'meeting-1', city_fips: '0660620', body_id: 'body-1',
  meeting_date: '2026-07-28', meeting_type: 'regular', presiding_officer: null,
  agenda_url: 'https://www.richmondca.gov/agenda.pdf', minutes_url: null,
  created_at: '2026-07-20T12:00:00Z', agenda_item_count: 4,
  top_categories: [{ category: 'housing', count: 2 }],
  all_categories: [{ category: 'housing', count: 2 }],
  top_topic_labels: [{ label: 'Housing', count: 2 }],
  all_topic_labels: [{ label: 'Housing', count: 2 }],
}

describe('source-scoped meeting archive cards', () => {
  it('keeps the topic disclosure outside the meeting link with native Radix state and a 44px target', () => {
    const html = renderToStaticMarkup(<MeetingListCard meeting={meeting} />)
    const links = [...html.matchAll(/<a\b[^>]*>([\s\S]*?)<\/a>/g)]
    expect(links).toHaveLength(1)
    expect(links[0][0]).toContain('href="/meetings/meeting-1"')
    expect(links[0][1]).not.toContain('<button')
    expect(html).toMatch(/<button[^>]*aria-expanded="false"/)
    expect(html).toContain('h-11 w-11')
    expect(html).toContain('Show 1 topic assigned by AI for July 28')
    expect(html).toContain('Topics assigned by AI')
    expect(html).toContain('4 agenda entries in this archive')
  })

  it('does not turn legacy vote or flag totals into list badges', () => {
    const legacyExtras = { ...meeting, vote_count: 72, flagCount: 5 }
    const html = renderToStaticMarkup(<MeetingListCard meeting={legacyExtras} />)
    expect(html).not.toMatch(/72|contribution|recorded votes|votes recorded|Campaign Finance/)
  })

  it('describes an empty archive without claiming the city has no agenda or votes', () => {
    const html = renderToStaticMarkup(<MeetingListCard meeting={{ ...meeting, agenda_item_count: 0,
      top_topic_labels: [], all_topic_labels: [] }} />)
    expect(html).toContain('No agenda entries in this archive')
    expect(html).not.toContain('<button')
    expect(html).not.toMatch(/0 votes|0 agenda items|No agenda available|Topics assigned/)
  })

  it('uses the same archive scope and AI labels for commission meeting cards', () => {
    const html = renderToStaticMarkup(<MeetingCard id={meeting.id} meetingDate={meeting.meeting_date}
      meetingType={meeting.meeting_type} presidingOfficer={null} agendaItemCount={1}
      topCategories={meeting.top_categories} />)
    expect(html).toContain('1 agenda entry in this archive')
    expect(html).toContain('Topics assigned by AI')
    expect(html).not.toMatch(/votes recorded|vote count/)
    expect(renderToStaticMarkup(<CommissionMeetingHistory meetings={[]} />))
      .toContain('No meeting records are available in this archive.')
  })

  it('keeps archive context in grouped totals and disclosure buttons', () => {
    const html = renderToStaticMarkup(<MeetingAgendaList meetings={[meeting]} />)
    expect(html).toContain('4 agenda entries in this archive')
    const history = Array.from({ length: 6 }, (_, index) => ({ ...meeting, id: `meeting-${index}` }))
    const historyHtml = renderToStaticMarkup(<CommissionMeetingHistory meetings={history} />)
    expect(historyHtml).toContain('Show all 6 meetings')
    expect(historyHtml).toContain('min-h-11 min-w-11')
    expect(historyHtml.match(/href="\/meetings\//g)).toHaveLength(5)
  })

  it('never displays a category count without its label', () => {
    const html = renderToStaticMarkup(<MeetingCard id={meeting.id} meetingDate={meeting.meeting_date}
      meetingType={meeting.meeting_type} presidingOfficer={null} agendaItemCount={2}
      topCategories={[{ category: 'other', count: 2 }]} />)
    expect(html).toContain('Miscellaneous')
  })
})
