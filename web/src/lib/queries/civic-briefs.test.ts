import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocked = vi.hoisted(() => ({ from: vi.fn() }))
vi.mock('@/lib/supabase', () => ({ supabase: { from: mocked.from } }))
vi.mock('next/cache', () => ({ unstable_cache: (fn: unknown) => fn }))
import { getPublishedCivicBriefVersion } from './civic-briefs'

const id = '11111111-1111-4111-8111-111111111111'
describe('published update email links', () => {
  beforeEach(() => vi.clearAllMocks())
  it('loads one exact publication independently of the six-item feed', async () => {
    const query = { select: vi.fn(), eq: vi.fn(), maybeSingle: vi.fn(async () => ({ data: { id, content_version: 3 }, error: null })) }
    query.select.mockReturnValue(query); query.eq.mockReturnValue(query); mocked.from.mockReturnValue(query)
    expect(await getPublishedCivicBriefVersion(id, '3', '2026-09-01T12:00:00.123456+00:00')).toEqual({ id, content_version: 3 })
    expect(query.eq.mock.calls).toEqual([['id', id], ['status', 'published'], ['content_version', 3], ['published_at', '2026-09-01T12:00:00.123456+00:00']])
    query.maybeSingle.mockResolvedValueOnce({ data: null as never, error: null })
    expect(await getPublishedCivicBriefVersion(id, '3', '2026-09-01T12:00:00Z')).toBeNull()
  })
  it('rejects incomplete or malformed version links before reading the database', async () => {
    for (const [linkId, version, published] of [[id, undefined, undefined], [id, '0', '2026-09-01'], [id, '1', 'invalid'], ['bad-id', '1', '2026-09-01']]) {
      expect(await getPublishedCivicBriefVersion(linkId!, version, published)).toBeNull()
    }
    expect(mocked.from).not.toHaveBeenCalled()
  })
  it('surfaces a source read failure instead of describing it as withdrawal', async () => {
    const query = { select: vi.fn(), eq: vi.fn(), maybeSingle: vi.fn(async () => ({ data: null, error: { code: 'timeout' } })) }
    query.select.mockReturnValue(query); query.eq.mockReturnValue(query); mocked.from.mockReturnValue(query)
    await expect(getPublishedCivicBriefVersion(id, '1', '2026-09-01')).rejects.toThrow('unavailable')
  })
})
