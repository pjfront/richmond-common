import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AgendaItemWithMotions } from './types'
import { holdStageVoteSourceRecords, stageVoteSourceReviewForItem } from './stage-vote-source-review'

const item = { id: '9cf375c8-edc1-413c-8ee0-6485348fbc6f', meeting_id: '5f560013-daea-499a-8ecd-ca1a089c8a0c',
  item_number: 'J-2', title: 'Point Molate LDA Extension with Upstream Point Molate LLC',
  summary_headline: 'Unsupported extracted result', plain_language_summary: 'Beckles abstained.',
  motions: [{ id: '87f3da0c-72ad-46dc-be37-f8581b204c58', result: 'passed', votes: [{ official_name: 'Jovanka Beckles', vote_choice: 'abstain' }] },
    { id: '1a5ba9fd-d167-47da-9b8e-cb5763c9106b', result: 'failed', votes: [] }],
} as unknown as AgendaItemWithMotions

describe('single-item stage source-review hold', () => {
  afterEach(() => vi.unstubAllEnvs())
  it('withholds both known incorrect motions and their summaries without mutating the source object', () => {
    vi.stubEnv('RICHMOND_READ_ONLY_STAGE', 'true')
    const held = holdStageVoteSourceRecords(item)
    expect(held).toMatchObject({ id: item.id, title: item.title, motions: [], summary_headline: null, plain_language_summary: null,
      voteSourceReview: { checkedAt: '2026-10-03', sourceUrl: 'https://www.ci.richmond.ca.us/ArchiveCenter/ViewFile/Item/2809' } })
    expect(JSON.stringify(held)).not.toMatch(/Beckles|87f3da0c|1a5ba9fd|Unsupported extracted result/)
    expect(item.motions).toHaveLength(2)
    expect(item.plain_language_summary).toBe('Beckles abstained.')
  })
  it('does not hold ordinary records, the same item label in another meeting, or normal mode', () => {
    vi.stubEnv('RICHMOND_READ_ONLY_STAGE', 'true')
    for (const ordinary of [{ ...item, id: 'another-item' }, { ...item, meeting_id: 'another-meeting' }, { ...item, item_number: 'J-3' }]) {
      expect(stageVoteSourceReviewForItem(ordinary)).toBeNull()
      expect(holdStageVoteSourceRecords(ordinary)).toBe(ordinary)
    }
    vi.stubEnv('RICHMOND_READ_ONLY_STAGE', 'false')
    expect(holdStageVoteSourceRecords(item)).toBe(item)
  })
})
