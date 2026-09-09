import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import CommunityVoiceSection, { commentRecordCounts } from './CommunityVoiceSection'
import TopicBoard from './TopicBoard'
import type { AgendaItemWithMotions, PublicCommentDetail, ThemeNarrative } from '@/lib/types'

const record = (id: string, method: string, comment_type = 'public'): PublicCommentDetail => ({
  id, speaker_name: 'Same reported name', method, comment_type, summary: null, is_notable: false, theme_slug: 'housing',
})
describe('observed comment records', () => {
  it('counts records rather than names, deduplicates row IDs, and preserves unknown or conflicting channels', () => {
    const comments = [record('a', 'in_person'), record('a', 'in_person'), record('b', 'email', 'written'),
      record('c', 'unknown'), record('d', 'zoom', 'written')]
    expect(commentRecordCounts(comments)).toEqual({ total: 4, spoken: 1, written: 1, unknown: 2 })
    expect(commentRecordCounts([record('a', 'phone'), record('a', 'email'), record('a', 'phone')])).toEqual({ total: 1, spoken: 0, written: 0, unknown: 1 })
    const html = renderToStaticMarkup(<CommunityVoiceSection comments={comments} themeNarratives={[]}
      spokenCount={999} writtenCount={888} commentSource={null} commentExtractedAt={null} />)
    expect(html).toContain('4 comment records available here')
    expect(html).toContain('2 with channel not established')
    expect(html).not.toMatch(/999|888|people commented|spoke at the meeting|person commented/)
  })
  it('labels themes as AI groupings and uses current assigned record IDs instead of stored narrative counts', () => {
    const theme = { theme: { id: 'theme-1', slug: 'housing', label: 'Housing', description: null },
      narrative: 'A generated summary.', comment_count: 987, confidence: 0.95, generated_at: '2026-09-06' } as ThemeNarrative
    const html = renderToStaticMarkup(<CommunityVoiceSection comments={[record('a', 'in_person'), record('a', 'in_person')]}
      themeNarratives={[theme]} commentSource={null} commentExtractedAt={null} />)
    expect(html).toContain('AI-grouped themes')
    expect(html).toContain('1 assigned comment record')
    expect(html).not.toMatch(/987|people raised|person raised/)
  })
  it('keeps agenda order regardless of speaker estimates or vote margin', () => {
    const items = ['10', '2'].map((item_number, index) => ({ id: item_number, meeting_id: 'm', item_number,
      title: `Agenda item ${item_number}`, category: 'housing', motions: [], public_comment_count: index ? 0 : 987,
    } as unknown as AgendaItemWithMotions))
    const html = renderToStaticMarkup(<TopicBoard items={items} flags={[]} significanceMap={new Map()} />)
    expect(html.indexOf('Agenda item 2')).toBeLessThan(html.indexOf('Agenda item 10'))
    expect(html).not.toMatch(/987|Most public comments/)
  })
})
