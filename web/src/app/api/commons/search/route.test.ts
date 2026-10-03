import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { NextRequest } from 'next/server'
const mocks = vi.hoisted(() => ({ search: vi.fn() }))
vi.mock('@/lib/queries/commons-search', () => ({ searchCommons: mocks.search }))
import { GET } from './route'
const request = (query: string) => ({ nextUrl: new URL(`http://localhost/api/commons/search?${query}`) }) as NextRequest

describe('public read-only staged search API', () => {
  beforeEach(() => vi.clearAllMocks())
  it('validates dates and modes before reading any public records', async () => {
    const response = await GET(request('mode=chat'))
    expect(response.status).toBe(400)
    expect(mocks.search).not.toHaveBeenCalled()
    expect(response.headers.get('Cache-Control')).toBe('no-store')
  })
  it('returns an honest unavailable state without caching failure as zero results', async () => {
    mocks.search.mockRejectedValueOnce(new Error('database timeout'))
    const response = await GET(request('q=housing'))
    expect(response.status).toBe(503)
    expect(response.headers.get('Cache-Control')).toBe('no-store')
    expect(await response.json()).toEqual({ error: 'The source records could not be loaded. Please try again later.' })
  })
  it('keeps query-bearing responses out of shared caches', async () => {
    mocks.search.mockResolvedValueOnce({ records: [], limited: true })
    const response = await GET(request('q=Who+voted+on+housing%3F'))
    expect(response.status).toBe(200)
    expect(mocks.search).toHaveBeenCalledWith(expect.objectContaining({ mode: 'votes', keywords: 'housing' }))
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
  })
})
