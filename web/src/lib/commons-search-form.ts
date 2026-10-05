import { commonsSearchParams, planCommonsSearch } from './commons-search'
import type { CommonsMode, CommonsSearchFilters } from './commons-search'

export type CommonsSearchDraft = Omit<CommonsSearchFilters, 'mode'> & { mode: CommonsMode | 'auto' }

/** Keep inferred filters out of editable controls so the next question can change its scope. */
export function commonsSearchDraft(params: URLSearchParams): CommonsSearchDraft {
  const plan = planCommonsSearch(params)
  return {
    q: plan.q,
    mode: params.get('mode') || params.get('type') ? plan.mode : 'auto',
    topic: plan.topic,
    from: params.get('from') || '',
    to: params.get('to') || '',
    page: plan.page,
  }
}

export function commonsDraftParams(draft: CommonsSearchDraft, page = 1): URLSearchParams {
  const params = commonsSearchParams({ ...draft, page, mode: draft.mode === 'auto' ? 'agenda' : draft.mode })
  if (draft.mode === 'auto') params.delete('mode')
  planCommonsSearch(params)
  return params
}

export function commonsPageParams(params: URLSearchParams, page: number): URLSearchParams {
  return commonsDraftParams(commonsSearchDraft(params), page)
}
