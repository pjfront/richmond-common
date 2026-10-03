import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { AgendaRecord } from './CommonsSearchClient'
import AgendaItemCard from './AgendaItemCard'
import { holdStageVoteSourceRecords, stageVoteSourceReviewForItem } from '@/lib/stage-vote-source-review'
import type { AgendaItemWithMotions } from '@/lib/types'
import type { CommonsAgendaRecord } from '@/lib/commons-search'
vi.mock('./OperatorModeProvider', () => ({ useOperatorMode: () => ({ isOperator: false }) }))

const identity = { id: '9cf375c8-edc1-413c-8ee0-6485348fbc6f', meeting_id: '5f560013-daea-499a-8ecd-ca1a089c8a0c', item_number: 'J-2' }
const record: CommonsAgendaRecord = { kind: 'votes', id: identity.id, title: 'Point Molate LDA Extension', itemNumber: 'J-2',
  meetingDate: '2010-03-02', topic: null, category: null, url: `/meetings/${identity.meeting_id}/items/j-2`,
  sourceUrl: 'https://www.ci.richmond.ca.us/ArchiveCenter/ViewFile/Item/2809', minutesUrl: 'https://www.ci.richmond.ca.us/ArchiveCenter/ViewFile/Item/2809',
  recordingUrl: null, indexedAt: '2026-03-07T15:40:10Z', motions: [] }

describe('source-review display and extraction attribution', () => {
  afterEach(() => vi.unstubAllEnvs())
  it('keeps source/item links while clearly disclosing a held search result', () => {
    vi.stubEnv('RICHMOND_READ_ONLY_STAGE', 'true')
    const html = renderToStaticMarkup(<AgendaRecord record={{ ...record, voteSourceReview: stageVoteSourceReviewForItem(identity)! }} />)
    expect(html).toContain('Vote records held for source review')
    expect(html).toContain('The hold does not establish that no vote occurred')
    expect(html).toContain('href="https://www.ci.richmond.ca.us/ArchiveCenter/ViewFile/Item/2809#page=9"')
    expect(html).toContain(`href="/meetings/${identity.meeting_id}/items/j-2"`)
    expect(html).not.toMatch(/Recorded motions \(0\)|Recorded result:|Beckles|Tom Bates/)
  })
  it('shows ordinary recorded choices with explicit extraction language and accuracy caveat', () => {
    const html = renderToStaticMarkup(<AgendaRecord record={{ ...record, id: 'ordinary', motions: [{ id: 'ordinary-motion', text: 'Approve services', result: 'passed', source: 'minutes',
      indexedAt: record.indexedAt, votes: [{ id: 'ordinary-vote', name: 'Printed Member', choice: 'aye', source: 'minutes' }] }] }} />)
    expect(html).toContain('Printed Member')
    expect(html).toContain('aye')
    expect(html).toContain('Extracted from official minutes')
    expect(html).toContain('Names, choices, and results may contain errors')
    expect(html).toContain('Recorded motions (1)')
  })
  it('shows the same hold on the expanded meeting item without publishing generated outcomes', () => {
    vi.stubEnv('RICHMOND_READ_ONLY_STAGE', 'true')
    const item = holdStageVoteSourceRecords({ ...identity, title: record.title, summary_headline: 'False extracted result',
      plain_language_summary: 'Beckles abstained.', motions: [{ id: 'wrong-motion', result: 'passed', votes: [{ official_name: 'Tom Bates', vote_choice: 'aye' }] }],
    } as unknown as AgendaItemWithMotions)
    const html = renderToStaticMarkup(<AgendaItemCard item={item} forceExpanded />)
    expect(html).toContain('Vote records held for source review')
    expect(html).toContain('Read the official minutes, page 9')
    expect(html).not.toMatch(/False extracted result|Beckles|Tom Bates|Why This Vote Matters|Passed/)
  })
})
