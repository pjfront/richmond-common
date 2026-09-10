import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/components/PublishedCivicBriefs', () => ({ default: () => null }))
import { renderToStaticMarkup } from 'react-dom/server'
import { CIVIC_STORIES } from '@/data/civic-stories'
import type { ResidentSnapshot, StoryAgendaEntry } from '@/lib/queries/civic-stories'

const mocks = vi.hoisted(() => ({ snapshot: vi.fn() }))
vi.mock('@/lib/queries/civic-stories', () => ({ getResidentSnapshot: mocks.snapshot }))
vi.mock('@/components/SuggestCorrectionLink', () => ({ default: () => <button>Suggest a correction</button> }))
import HomePage from '@/app/page'
import StoryPage from '@/app/stories/[slug]/page'
import { StoryAgenda } from './CivicStory'

const unavailable: ResidentSnapshot = { status: 'unavailable', fetchedAt: null, recent: [], upcoming: [], entries: {}, itemLimitReached: false }

const originalAgenda = 'https://pub-richmond.escribemeetings.com/Meeting.aspx?Id=source-one&Agenda=Agenda&lang=English'
function agendaEntry(overrides: Partial<StoryAgendaEntry> = {}): StoryAgendaEntry {
  return { id: 'entry-one', meeting_id: 'meeting-one', meeting_date: '2026-09-15', agenda_url: originalAgenda, item_number: 'X.1', title: 'APPROVE a Flock Safety contract amendment', topic_label: null, href: '/meetings/meeting-one/items/x.1', upcoming: true, ...overrides }
}
function snapshotWith(entries: StoryAgendaEntry[], overrides: Partial<ResidentSnapshot> = {}): ResidentSnapshot {
  return { ...unavailable, status: 'available', fetchedAt: '2026-09-10T20:00:00Z', entries: { [CIVIC_STORIES[2].slug]: entries }, ...overrides }
}

describe('resident journeys', () => {
  beforeEach(() => { mocks.snapshot.mockResolvedValue(unavailable) })

  it('keeps the homepage useful during an agenda outage, with election and story paths', async () => {
    const html = renderToStaticMarkup(await HomePage())
    for (const story of CIVIC_STORIES) expect(html).toContain(`/stories/${story.slug}`)
    expect(html).toContain('href="/elections/2026-general"')
    expect(html).toContain('The local calendar could not be loaded')
    expect(html).toContain('AI-written explanations')
    expect(html).toContain('Español')
    expect(html).toContain('ADID=17785')
    expect(html).toContain('ADID=17838')
    expect(html).not.toContain('fundraising total')
  })

  it('shows the exact Flock action and primary minutes while keeping later implementation open', async () => {
    const html = renderToStaticMarkup(await StoryPage({ params: Promise.resolve({ slug: CIVIC_STORIES[2].slug }) }))
    expect(html).toContain('4–3 to direct negotiations')
    expect(html).toContain('do not prove a final contract was signed')
    expect(html).toContain('ArchiveCenter/ViewFile/Item/17557#page=10')
    expect(html).toContain('Tier 1')
    expect(html).toContain('source-coverage gap')
    expect(html).toContain('href="#story-agenda"')
    expect(html).toContain('id="story-agenda"')
  })

  it('distinguishes successful no-match discovery from failed discovery', () => {
    const html = renderToStaticMarkup(<StoryAgenda story={CIVIC_STORIES[0]} snapshot={{ ...unavailable, status: 'available', fetchedAt: '2026-09-06T20:00:00Z' }} />)
    expect(html).toContain('No matching titles were found')
    expect(html).toContain('Related action may appear under another title')
    expect(html).not.toContain('could not be loaded')
    expect(html).toContain('No matching upcoming agenda item was found in the meetings checked')
    expect(html).toContain('That does not mean no action is planned')
  })

  it('puts the nearest matching meeting and its exact original agenda before the recent trail', () => {
    const earliest = agendaEntry()
    const later = agendaEntry({ id: 'later', meeting_id: 'later-meeting', meeting_date: '2026-09-22', title: 'Flock discussion at a later meeting' })
    const past = agendaEntry({ id: 'past', meeting_id: 'past-meeting', meeting_date: '2026-09-01', title: 'Prior Flock agenda entry', upcoming: false })
    const input = [later, past, earliest]
    const html = renderToStaticMarkup(<StoryAgenda story={CIVIC_STORIES[2]} snapshot={snapshotWith(input)} />)
    expect(html.indexOf(earliest.title)).toBeLessThan(html.indexOf(past.title))
    expect(html).not.toContain(later.title)
    expect(html).toContain('Other future meetings also matched')
    expect(html).toContain('Official agenda: time and how to take part')
    expect(html).toContain(originalAgenda.replaceAll('&', '&amp;'))
    expect(html).toContain('Tier 1 · Official agenda')
    expect(html).toContain('does not establish what the council adopted')
    expect(html).toContain('partial discovery aid')
    expect(html).not.toContain('Adopted action')
    expect(input).toEqual([later, past, earliest])
  })

  it('keeps distinct meetings on the same date separate and orders item identifiers numerically', () => {
    const itemTen = agendaEntry({ id: 'ten', item_number: 'X.10', title: 'Flock item ten' })
    const itemTwo = agendaEntry({ id: 'two', item_number: 'X.2', title: 'Flock item two' })
    const separate = agendaEntry({ id: 'separate', meeting_id: 'meeting-two', title: 'Separate meeting on the same date' })
    const html = renderToStaticMarkup(<StoryAgenda story={CIVIC_STORIES[2]} snapshot={snapshotWith([itemTen, separate, itemTwo])} />)
    expect(html.indexOf(itemTwo.title)).toBeLessThan(html.indexOf(itemTen.title))
    expect(html).not.toContain(separate.title)
  })

  it('retains eight recent entries independently of future matches and discloses both limits', () => {
    const recent = Array.from({ length: 9 }, (_, i) => agendaEntry({ id: `past-${i}`, title: `Historic source entry ${i}`, upcoming: false, meeting_id: `past-${i}`, meeting_date: `2026-08-${String(i + 1).padStart(2, '0')}` }))
    const html = renderToStaticMarkup(<StoryAgenda story={CIVIC_STORIES[2]} snapshot={snapshotWith([...recent, agendaEntry()], { itemLimitReached: true })} />)
    expect(html).toContain(agendaEntry().title)
    for (const row of recent.slice(1)) expect(html).toContain(row.title)
    expect(html).not.toContain(recent[0].title)
    expect(html).toContain('Showing the eight most recent matching agenda entries')
    expect(html).toContain('including earlier upcoming matches')
  })

  it('offers the city calendar when the original link is missing without inventing participation details', () => {
    const html = renderToStaticMarkup(<StoryAgenda story={CIVIC_STORIES[2]} snapshot={snapshotWith([agendaEntry({ agenda_url: null })])} />)
    expect(html).toContain('The original agenda link is unavailable here')
    expect(html).toContain('Open the city’s meeting calendar')
    expect(html).not.toContain('Official agenda: time and how to take part')
    expect(html).not.toContain('Tier 1 · Official agenda')
  })

  it('keeps unavailable discovery distinct from no matching upcoming action', () => {
    const html = renderToStaticMarkup(<StoryAgenda story={CIVIC_STORIES[2]} snapshot={unavailable} />)
    expect(html).toContain('role="status"')
    expect(html).toContain('source-coverage gap')
    expect(html).not.toContain('No matching upcoming agenda item')
    expect(html).not.toContain('Discovery window')
  })

})
