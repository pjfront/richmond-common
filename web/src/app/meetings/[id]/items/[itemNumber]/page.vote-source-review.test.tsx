import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { AgendaItemDetail } from '@/lib/types'
import { holdStageVoteSourceRecords } from '@/lib/stage-vote-source-review'
const mocks = vi.hoisted(() => ({ item: vi.fn() }))
vi.mock('@/lib/queries', () => ({ getAgendaItemDetail: mocks.item }))
vi.mock('@/components/OperatorGate', () => ({ default: () => null }))
vi.mock('@/components/SimilarDiscussions', () => ({ default: () => null }))
vi.mock('@/components/ReportErrorLink', () => ({ default: () => null }))
import AgendaItemDetailPage, { generateMetadata } from './page'

const item = { id: '9cf375c8-edc1-413c-8ee0-6485348fbc6f', meeting_id: '5f560013-daea-499a-8ecd-ca1a089c8a0c', item_number: 'J-2',
  title: 'Point Molate LDA Extension', summary_headline: 'False extracted result', plain_language_summary: 'Beckles abstained.',
  meeting_date: '2010-03-02', meeting_agenda_url: null, meeting_minutes_url: 'https://www.ci.richmond.ca.us/ArchiveCenter/ViewFile/Item/2809',
  motions: [{ id: '87f3da0c-72ad-46dc-be37-f8581b204c58', motion_text: 'Approve the item as presented', result: 'passed', source: 'minutes',
    votes: [{ id: 'bad-vote', official_name: 'Jovanka Beckles', official_id: 'Beckles', vote_choice: 'abstain' }] },
    { id: '1a5ba9fd-d167-47da-9b8e-cb5763c9106b', motion_text: 'Continue six months', result: 'failed', source: 'minutes', votes: [] }],
  comments: [], theme_narratives: [], continued_from_item: null, continued_to_item: null, prev_item: null, next_item: null,
} as unknown as AgendaItemDetail

describe('item detail source-review hold', () => {
  beforeEach(() => { mocks.item.mockReset(); vi.stubEnv('RICHMOND_READ_ONLY_STAGE', 'true') })
  afterEach(() => vi.unstubAllEnvs())
  it('does not reopen the disputed roll call or generated result through the item permalink or metadata', async () => {
    mocks.item.mockResolvedValue(holdStageVoteSourceRecords(item))
    const params = Promise.resolve({ id: item.meeting_id, itemNumber: 'j-2' })
    const html = renderToStaticMarkup(await AgendaItemDetailPage({ params }))
    const metadata = await generateMetadata({ params })
    expect(html).toContain('Point Molate LDA Extension')
    expect(html).toContain('Vote records held for source review')
    expect(html).toContain('href="https://www.ci.richmond.ca.us/ArchiveCenter/ViewFile/Item/2809#page=9"')
    expect(html).not.toMatch(/Beckles|False extracted result|Continue six months|Individual votes|Passed|Failed/)
    expect(JSON.stringify(metadata)).not.toMatch(/Beckles|False extracted result/)
  })
  it('preserves an ordinary item roll call with extraction attribution', async () => {
    const ordinary: AgendaItemDetail = { ...item, id: 'ordinary-item', item_number: 'G-1', title: 'Ordinary services', summary_headline: null, plain_language_summary: null,
      motions: [{ ...item.motions[0], id: 'ordinary-motion', votes: [{ ...item.motions[0].votes[0], official_name: 'Printed Member', vote_choice: 'aye' }] }] }
    mocks.item.mockResolvedValue(holdStageVoteSourceRecords(ordinary))
    const html = renderToStaticMarkup(await AgendaItemDetailPage({ params: Promise.resolve({ id: item.meeting_id, itemNumber: 'g-1' }) }))
    expect(html).toContain('Printed Member')
    expect(html).toContain('Extracted from official minutes')
    expect(html).toContain('Names, choices, and results may contain errors')
    expect(html).not.toContain('Vote records held for source review')
  })
})
