import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'
const mocks = vi.hoisted(() => ({ flags: vi.fn(), admin: vi.fn(), session: { isOperator: false }, client: { from: vi.fn() } }))
vi.mock('@/lib/queries', () => ({ getConflictFlagsDetailed: mocks.flags }))
vi.mock('@/lib/supabase-admin', () => ({ getSupabaseAdmin: mocks.admin }))
vi.mock('next/headers', () => ({ cookies: async () => ({}) }))
vi.mock('iron-session', () => ({ getIronSession: async () => mocks.session }))
vi.mock('@/lib/operator-session', () => ({ getOperatorSessionOptions: () => ({ password: 'x'.repeat(32), cookieName: 'test' }) }))
import { GET } from './route'
const id = '11111111-1111-4111-8111-111111111111'
const req = (meeting = id) => new NextRequest(`https://example.test/api/operator/meeting-context?meeting_id=${meeting}`)
describe('private flag review after public eligibility restriction', () => {
  beforeEach(() => { mocks.flags.mockReset(); mocks.admin.mockReset(); mocks.admin.mockReturnValue(mocks.client); mocks.session.isOperator = false })
  it('rejects anonymous callers before constructing admin or reading flags', async () => {
    expect((await GET(req())).status).toBe(401)
    expect(mocks.admin).not.toHaveBeenCalled()
    expect(mocks.flags).not.toHaveBeenCalled()
  })
  it('validates identity before obtaining the privileged client', async () => {
    mocks.session.isOperator = true
    expect((await GET(req('bad'))).status).toBe(400)
    expect(mocks.admin).not.toHaveBeenCalled()
    expect(mocks.flags).not.toHaveBeenCalled()
  })
  it('preserves private current-flag review only after successful operator authentication', async () => {
    mocks.session.isOperator = true
    mocks.flags.mockResolvedValue([{ id, confidence: 0.4 }])
    const response = await GET(req())
    expect(response.status).toBe(200)
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
    expect(await response.json()).toEqual({ flags: [{ id, confidence: 0.4 }] })
    expect(mocks.flags).toHaveBeenCalledWith(id, undefined, mocks.client)
  })
})
