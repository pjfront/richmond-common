import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { COUNCIL_RETURN_NOTICE, getCouncilReturnNotice } from './council-notices'
import type { ResidentSnapshot } from '@/lib/queries/civic-stories'

const mocks = vi.hoisted(() => ({ getResidentSnapshot: vi.fn() }))
vi.mock('@/lib/queries/civic-stories', () => mocks)
import HomePage from '@/app/page'

const empty: ResidentSnapshot = { status: 'available', fetchedAt: '2026-09-06', upcoming: [], recent: [], entries: {}, itemLimitReached: false }

describe('dated council recess notice', () => {
  afterEach(() => vi.useRealTimers())

  it('is available only before the meeting day in Richmond', () => {
    expect(getCouncilReturnNotice(empty, new Date('2026-09-14T23:00:00Z'))).toEqual(COUNCIL_RETURN_NOTICE)
    expect(getCouncilReturnNotice(empty, new Date('2026-09-15T06:59:59Z'))).toEqual(COUNCIL_RETURN_NOTICE)
    expect(getCouncilReturnNotice(empty, new Date('2026-09-15T07:00:00Z'))).toBeNull()
    expect(getCouncilReturnNotice(empty, new Date('2026-09-16T12:00:00Z'))).toBeNull()
    expect(getCouncilReturnNotice(empty, new Date('2026-09-01T12:00:00Z'))).toBeNull()
  })

  it('does not replace an upcoming database record or a calendar failure', () => {
    const now = new Date('2026-09-07T12:00:00Z')
    expect(getCouncilReturnNotice({ ...empty, status: 'unavailable' }, now)).toBeNull()
    expect(getCouncilReturnNotice({ ...empty, upcoming: [{ id: 'published', meeting_date: '2026-09-15', meeting_type: 'regular', agenda_url: 'https://pub-richmond.escribemeetings.com/', source_meeting_guid: 'source-guid' }] }, now)).toBeNull()
  })

  it('renders the official source and unpublished-agenda distinction on the homepage', async () => {
    vi.useFakeTimers().setSystemTime(new Date('2026-09-06T20:00:00Z'))
    mocks.getResidentSnapshot.mockResolvedValue(empty)
    const markup = renderToStaticMarkup(await HomePage())
    expect(markup).toContain('Council resumes September 15')
    expect(markup).toContain('An agenda is not yet available in the records here.')
    expect(markup).toContain('ADID=17876#page=3')
    expect(markup).not.toContain('/meetings/undefined')
    expect(COUNCIL_RETURN_NOTICE.text.es).toContain('Todavía no hay una agenda')
    expect(COUNCIL_RETURN_NOTICE.sourceLabel.es).toContain('página 3')
  })
})
