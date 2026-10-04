import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'

const mocks = vi.hoisted(() => ({ admin: vi.fn(), send: vi.fn() }))
vi.mock('@/lib/supabase-admin', () => ({ getSupabaseAdmin: mocks.admin }))
vi.mock('@/lib/email', async importOriginal => ({
  ...await importOriginal<typeof import('@/lib/email')>(), sendEmail: mocks.send,
}))
import { GET } from './route'

const ID = 'aaaaaaaa-1111-4111-8111-111111111111'
const CANARY = 'configured-canary@example.test'
const PROVIDER_KEY = 're_private-test-provider-key'
const fetchMock = vi.fn<typeof fetch>()
function request(query = `provider_id=${ID}`, authorized = true) {
  return new NextRequest(`https://example.test/api/email/send-digest?${query}`, {
    headers: authorized ? { authorization: 'Bearer test-secret' } : {},
  })
}
function providerEmail(overrides: Record<string, unknown> = {}) {
  return {
    object: 'email', id: ID, to: [CANARY],
    from: 'Richmond Commons <updates@richmondcommons.org>', cc: [], bcc: [],
    subject: '[CANARY] This week in Richmond: 2 reviewed updates',
    html: '<p>CANARY TEST — Richmond</p>\n', text: 'CANARY TEST — Richmond\n',
    last_event: 'delivered', reply_to: ['private-reply@example.test'],
    ...overrides,
  }
}
function respond(overrides: Record<string, unknown> = {}) {
  fetchMock.mockResolvedValue(Response.json(providerEmail(overrides)))
}
async function expectUnavailable(query = `provider_id=${ID}`) {
  const response = await GET(request(query))
  expect(response.status).toBe(503)
  expect(response.headers.get('Cache-Control')).toBe('private, no-store')
  expect(await response.json()).toEqual({ error: 'Canary provider proof unavailable' })
}

describe('authenticated, canary-only provider evidence', () => {
  beforeEach(() => {
    vi.stubEnv('API_SECRET', 'test-secret')
    vi.stubEnv('SUBSCRIBER_CANARY_EMAIL', CANARY)
    vi.stubEnv('RESEND_API_KEY', PROVIDER_KEY)
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    expect(mocks.admin).not.toHaveBeenCalled()
    expect(mocks.send).not.toHaveBeenCalled()
    for (const [, options] of fetchMock.mock.calls) expect(options?.method).toBe('GET')
    vi.clearAllMocks()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    vi.useRealTimers()
  })

  it('checks authentication before parsing identifiers or contacting the provider', async () => {
    const response = await GET(request('provider_id=malformed', false))
    expect(response.status).toBe(401)
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
    expect(await response.json()).toEqual({ error: 'Unauthorized' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('reports activated capability without contacting the provider', async () => {
    const response = await GET(request(''))
    expect(response.status).toBe(200)
    expect(await response.json()).toEqual({ capability: 'subscriber-weekly-digest-v1', canary_ready: true, broadcast_ready: true })
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it.each([
    'provider_id=', 'provider_id=not-a-uuid', 'provider_id=../../emails',
    `provider_id=${ID}&provider_id=${ID}`, `provider_id=${ID}&to=other@example.test`,
    'email_id=aaaaaaaa-1111-4111-8111-111111111111',
  ])('rejects malformed, duplicate, or extra query fields before provider access: %s', async query => {
    await expectUnavailable(query)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it.each(['RESEND_API_KEY', 'SUBSCRIBER_CANARY_EMAIL'])('fails closed without %s', async name => {
    vi.stubEnv(name, '')
    await expectUnavailable()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('makes exactly one fixed-origin GET and returns only five redacted proof fields with exact UTF-8 hashes', async () => {
    respond()
    const response = await GET(request())
    const proof = await response.json()
    expect(response.status).toBe(200)
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
    // Independently generated Python hashlib fixtures include Unicode and the
    // trailing newline. No trimming or HTML normalization can preserve these.
    expect(proof).toEqual({
      provider_id: ID, provider_last_event: 'delivered',
      subject: '[CANARY] This week in Richmond: 2 reviewed updates',
      html_sha256: '5f77b2ed79c71c9567726c9b59c39721de0beea7239b875147dea2cb58062ffa',
      text_sha256: '2a1127c0e8f7b3b8da405b1cf6e6dd0dc8c44374d0e99dc283702edbf6bd085a',
    })
    expect(JSON.stringify(proof)).not.toMatch(/example\.test|updates@|re_private|<p>|CANARY TEST/)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(`https://api.resend.com/emails/${ID}`, {
      method: 'GET', headers: { Authorization: `Bearer ${PROVIDER_KEY}`, Accept: 'application/json' },
      cache: 'no-store', redirect: 'error', signal: expect.any(AbortSignal),
    })
  })

  it.each(['sent', 'queued', 'delivery_delayed', 'bounced', 'failed'])('reports the actual %s event without claiming delivery', async last_event => {
    respond({ last_event })
    const response = await GET(request())
    const proof = await response.json()
    expect(response.status).toBe(200)
    expect(proof.provider_last_event).toBe(last_event)
    expect(proof).not.toHaveProperty('delivered')
  })

  it.each([
    { to: ['other@example.test'] }, { to: [CANARY, 'other@example.test'] },
    { to: CANARY }, { to: [] }, { to: undefined },
    { cc: ['other@example.test'] }, { bcc: ['other@example.test'] },
    { cc: null }, { bcc: undefined },
    { from: 'Other <updates@richmondcommons.org>' },
    { from: 'Richmond Commons <other@example.test>' },
    { subject: 'Welcome to Richmond Commons' },
    { subject: '[CANARY] This week in Richmond: private arbitrary title' },
    { subject: '[CANARY] This week in Richmond: 1 reviewed updates' },
    { subject: '[CANARY] This week in Richmond: 0 meetings' },
    { subject: '[CANARY] This week in Richmond: 2 reviewed updates\nprivate' },
    { id: 'bbbbbbbb-1111-4111-8111-111111111111' }, { object: 'other' },
    { html: null }, { text: null }, { html: '' }, { text: {} },
    { last_event: 'private-provider-error-or-unknown-event' },
  ])('withholds all proof for mismatched destinations or malformed record %#', async override => {
    respond(override)
    await expectUnavailable()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it.each([
    '[CANARY] This week in Richmond: 1 reviewed update',
    '[CANARY] This week in Richmond: 2 reviewed updates and 1 meeting',
    '[CANARY] This week in Richmond: 1 meeting',
    '[CANARY] This week in Richmond: 2 meetings',
  ])('recognizes the existing digest subject template: %s', async subject => {
    respond({ subject })
    expect((await GET(request())).status).toBe(200)
  })

  it.each([401, 403, 404, 429, 500, 503])('redacts a provider %s, including sending-only key permissions, without retrying', async status => {
    fetchMock.mockResolvedValue(Response.json({ error: `${PROVIDER_KEY} ${CANARY} private response` }, { status }))
    await expectUnavailable()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it.each([
    () => new Response('not-json', { headers: { 'Content-Type': 'application/json' } }),
    () => Response.json(null),
    () => Response.json([]),
    () => new Response('<html>private</html>', { headers: { 'Content-Type': 'text/html' } }),
    () => new Response(new Uint8Array([0xff]), { headers: { 'Content-Type': 'application/json' } }),
    () => new Response('{}', { headers: { 'Content-Type': 'application/json', 'Content-Length': '1048577' } }),
    () => Response.json(providerEmail({ html: 'x'.repeat(1_048_576) })),
  ])('bounds response bytes and rejects malformed payloads without leaking them %#', async response => {
    fetchMock.mockResolvedValue(response())
    await expectUnavailable()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('aborts a slow provider GET after eight seconds, with no second request or send', async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementation((_url, options) => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener('abort', () => reject(new Error(`Timeout ${PROVIDER_KEY}`)))
    }))
    const pending = GET(request())
    await vi.advanceTimersByTimeAsync(8_000)
    const response = await pending
    expect(response.status).toBe(503)
    expect(await response.json()).toEqual({ error: 'Canary provider proof unavailable' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true)
  })

  it('redacts transport and redirect failures without retrying', async () => {
    fetchMock.mockRejectedValue(new Error(`Private transport detail ${PROVIDER_KEY} ${CANARY}`))
    await expectUnavailable()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('keeps the same deadline while a provider response body stalls after headers', async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementation(async (_url, options) => new Response(new ReadableStream({
      start(controller) {
        options?.signal?.addEventListener('abort', () => controller.error(new Error('Body read aborted')))
      },
    }), { headers: { 'Content-Type': 'application/json' } }))
    const pending = GET(request())
    await vi.advanceTimersByTimeAsync(8_000)
    const response = await pending
    expect(response.status).toBe(503)
    expect(await response.json()).toEqual({ error: 'Canary provider proof unavailable' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true)
  })
})
