import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'
const mocks = vi.hoisted(() => ({ revalidatePath: vi.fn(), revalidateTag: vi.fn(), enforceRateLimit: vi.fn() }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath, revalidateTag: mocks.revalidateTag }))
vi.mock('@/lib/rate-limit', () => ({ clientKey: () => 'test', enforceRateLimit: mocks.enforceRateLimit }))
import { POST } from './route'
import { SPLIT_MOTIONS_CACHE_TAG } from '@/lib/read-path-cache'

function request(body: object) {
  return new NextRequest('https://example.test/api/revalidate', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
}
describe('source revalidation expires the compact split-motion projection', () => {
  beforeEach(() => {
    vi.clearAllMocks(); vi.stubEnv('REVALIDATION_SECRET', 'fixture-secret')
    mocks.enforceRateLimit.mockResolvedValue({ allowed: true })
  })
  afterEach(() => vi.unstubAllEnvs())
  it('uses the existing source-sync all contract to expire the tag immediately and include analytics', async () => {
    const response = await POST(request({ all: true, secret: 'fixture-secret' }))
    expect(response.status).toBe(200)
    expect(mocks.revalidateTag).toHaveBeenCalledExactlyOnceWith(SPLIT_MOTIONS_CACHE_TAG, { expire: 0 })
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/council/analytics')
  })
  it.each(['/meetings/meeting-id', '/council/member', '/council/analytics'])('expires source-sensitive records for %s', async path => {
    expect((await POST(request({ paths: [path], secret: 'fixture-secret' }))).status).toBe(200)
    expect(mocks.revalidateTag).toHaveBeenCalledExactlyOnceWith(SPLIT_MOTIONS_CACHE_TAG, { expire: 0 })
  })
  it('does not invalidate the projection for unrelated pages or rejected credentials', async () => {
    expect((await POST(request({ paths: ['/about'], secret: 'fixture-secret' }))).status).toBe(200)
    expect(mocks.revalidateTag).not.toHaveBeenCalled()
    vi.clearAllMocks()
    expect((await POST(request({ all: true, secret: 'wrong' }))).status).toBe(401)
    expect(mocks.revalidatePath).not.toHaveBeenCalled()
    expect(mocks.revalidateTag).not.toHaveBeenCalled()
  })
})
