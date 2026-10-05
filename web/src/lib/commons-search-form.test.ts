import { describe, expect, it } from 'vitest'
import { commonsDraftParams, commonsPageParams, commonsSearchDraft } from './commons-search-form'
import { planCommonsSearch } from './commons-search'

describe('question-driven search form scope', () => {
  it('lets the next question infer a new record kind and year', () => {
    const housing = commonsSearchDraft(new URLSearchParams('q=Housing+decisions+in+2026'))
    expect(housing).toMatchObject({ mode: 'auto', from: '', to: '' })
    const nextQuestion = commonsDraftParams({ ...housing, q: 'Donations to Jimenez in 2025' })
    expect(nextQuestion.has('mode')).toBe(false)
    expect(nextQuestion.has('from')).toBe(false)
    expect(planCommonsSearch(nextQuestion)).toMatchObject({ mode: 'money', from: '2025-01-01', to: '2025-12-31' })
  })

  it('preserves a deliberately chosen record kind and date filter', () => {
    const draft = commonsSearchDraft(new URLSearchParams('q=Chevron&mode=money&from=2026-06-01&to=2026-09-30'))
    expect(draft).toMatchObject({ mode: 'money', from: '2026-06-01', to: '2026-09-30' })
    const params = commonsDraftParams({ ...draft, q: 'Anderson' })
    expect(planCommonsSearch(params)).toMatchObject({ mode: 'money', keywords: 'Anderson', from: '2026-06-01', to: '2026-09-30' })
  })

  it('keeps pagination on the same question without pinning inferred controls', () => {
    const params = commonsPageParams(new URLSearchParams('q=Who+voted+on+Point+Molate+in+2010'), 2)
    expect(params.get('page')).toBe('2')
    expect(params.has('mode')).toBe(false)
    expect(params.has('from')).toBe(false)
    expect(planCommonsSearch(params)).toMatchObject({ mode: 'votes', page: 2, from: '2010-01-01', to: '2010-12-31' })
  })

  it('validates editable filters before navigation and bounds result pages', () => {
    const draft = commonsSearchDraft(new URLSearchParams())
    expect(() => commonsDraftParams({ ...draft, from: '2026-02-30' })).toThrow()
    expect(() => commonsDraftParams({ ...draft, q: 'housing', topic: 'x'.repeat(101) })).toThrow()
    expect(() => commonsPageParams(new URLSearchParams('q=housing'), 101)).toThrow()
  })
})
