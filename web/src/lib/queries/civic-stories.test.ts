import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CIVIC_STORIES, CIVIC_SOURCES, matchesCivicStory } from '@/data/civic-stories'

const mocks = vi.hoisted(() => ({ from: vi.fn(), cache: vi.fn((fn: unknown) => fn) }))
vi.mock('next/cache', () => ({ unstable_cache: mocks.cache }))
vi.mock('@/lib/supabase', () => ({ supabase: { from: mocks.from } }))

import { getResidentSnapshot, groupStoryAgendaEntries, richmondDate, uniqueResidentMeetings, type ResidentMeeting } from './civic-stories'

const meeting: ResidentMeeting = { id: 'meeting-one', meeting_date: '2026-03-17', meeting_type: 'regular', agenda_url: 'https://www.richmondca.gov/agenda', source_meeting_guid: 'source-one' }
function builder(result: object) {
  const query = {
    select: vi.fn(), eq: vi.fn(), is: vi.fn(), lt: vi.fn(), gte: vi.fn(), order: vi.fn(), limit: vi.fn(), in: vi.fn(),
    then: (resolve: (value: object) => unknown) => Promise.resolve(result).then(resolve),
  }
  for (const method of [query.select, query.eq, query.is, query.lt, query.gte, query.order, query.limit, query.in]) method.mockReturnValue(query)
  return query
}

describe('source-grounded resident discovery', () => {
  beforeEach(() => { mocks.from.mockReset() })

  it('groups reviewed issue aliases without matching partial words', () => {
    const flock = CIVIC_STORIES[2]
    expect(matchesCivicStory(flock, 'Flock Safety amendment', null)).toBe(true)
    expect(matchesCivicStory(flock, 'Automated license plate readers', null)).toBe(true)
    expect(matchesCivicStory(flock, 'A flocking treatment for city decorations', null)).toBe(false)
    expect(matchesCivicStory(flock, 'Budget adoption', null)).toBe(false)
  })

  it('deduplicates shared source identities but keeps distinct meetings on the same day', () => {
    const duplicate = { ...meeting, id: 'alias-one' }
    const different = { ...meeting, id: 'different', source_meeting_guid: 'source-two' }
    expect(uniqueResidentMeetings([meeting, duplicate, different]).map(row => row.id)).toEqual(['meeting-one', 'different'])
  })

  it('links to the exact agenda item and never turns its title into an outcome', () => {
    const result = groupStoryAgendaEntries([
      { id: 'item-one', meeting_id: meeting.id, item_number: 'X.2', title: 'APPROVE a Flock amendment', topic_label: null },
      { id: 'item-two', meeting_id: 'missing', item_number: 'A', title: 'Flock', topic_label: null },
    ], [meeting], '2026-03-17')
    expect(result[CIVIC_STORIES[2].slug]).toEqual([expect.objectContaining({ href: '/meetings/meeting-one/items/x.2', upcoming: true, title: 'APPROVE a Flock amendment' })])
    expect(result[CIVIC_STORIES[2].slug][0]).not.toHaveProperty('outcome')
  })

  it('uses the Richmond calendar day around midnight UTC', () => {
    expect(richmondDate(new Date('2026-09-07T01:00:00Z'))).toBe('2026-09-06')
  })

  it('bounds every source read and excludes cancelled and retired source rows', async () => {
    const past = builder({ data: [meeting], error: null })
    const future = builder({ data: [], error: null })
    const items = builder({ data: [], error: null })
    mocks.from.mockReturnValueOnce(past).mockReturnValueOnce(future).mockReturnValueOnce(items)
    const snapshot = await getResidentSnapshot()
    expect(snapshot.status).toBe('available')
    expect(past.limit).toHaveBeenCalledWith(16)
    expect(future.limit).toHaveBeenCalledWith(6)
    expect(items.limit).toHaveBeenCalledWith(1000)
    expect(past.eq).toHaveBeenCalledWith('city_fips', '0660620')
    expect(past.eq).toHaveBeenCalledWith('bodies.body_type', 'city_council')
    expect(past.is).toHaveBeenCalledWith('source_cancelled_at', null)
    expect(items.is).toHaveBeenCalledWith('agenda_source_retired_at', null)
    expect(items.in).toHaveBeenCalledWith('meeting_id', ['meeting-one'])
  })

  it('represents a database failure as unavailable, not a successful empty agenda', async () => {
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    mocks.from.mockReturnValueOnce(builder({ data: null, error: { message: 'offline' } })).mockReturnValueOnce(builder({ data: [], error: null }))
    expect((await getResidentSnapshot()).status).toBe('unavailable')
    expect(mocks.from).toHaveBeenCalledTimes(2)
    log.mockRestore()
  })

  it('keeps sources and both languages attached to every published event', () => {
    for (const story of CIVIC_STORIES) {
      expect(story.coverage.en.length).toBeGreaterThan(20)
      expect(story.coverage.es.length).toBeGreaterThan(20)
      for (const event of story.events) {
        expect(story.sourceIds).toContain(event.sourceId)
        expect(CIVIC_SOURCES[event.sourceId].url).toMatch(/^https:\/\//)
        expect(CIVIC_SOURCES[event.sourceId].tier).toBe(1)
      }
    }
    expect(CIVIC_STORIES[1].summary.en).toContain('two-thirds')
    expect(CIVIC_STORIES[1].coverage.en).toContain('not')
    expect(CIVIC_STORIES[2].coverage.en).toContain('do not prove a final contract')
  })
})
