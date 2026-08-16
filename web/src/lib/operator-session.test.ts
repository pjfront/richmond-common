import { describe, expect, it, vi } from 'vitest'
import { probeOperatorSession } from './operator-session-probe'

function response(ok: boolean, body: unknown): Response {
  return {
    ok,
    json: vi.fn(async () => body),
  } as unknown as Response
}

describe('probeOperatorSession', () => {
  it('resolves a proven public session', async () => {
    const fetcher = vi.fn(async () => response(true, { isOperator: false }))
    await expect(probeOperatorSession(fetcher as typeof fetch)).resolves.toBe(false)
  })

  it('resolves a proven operator session', async () => {
    const fetcher = vi.fn(async () => response(true, { isOperator: true }))
    await expect(probeOperatorSession(fetcher as typeof fetch)).resolves.toBe(true)
  })

  it('fails closed on a non-OK response', async () => {
    const fetcher = vi.fn(async () => response(false, { isOperator: false }))
    await expect(probeOperatorSession(fetcher as typeof fetch)).resolves.toBeNull()
  })

  it('fails closed on a rejected request', async () => {
    const fetcher = vi.fn(async () => { throw new Error('network unavailable') })
    await expect(probeOperatorSession(fetcher as typeof fetch)).resolves.toBeNull()
  })

  it.each([{}, { isOperator: 'false' }, null])(
    'fails closed on malformed JSON: %j',
    async (body) => {
      const fetcher = vi.fn(async () => response(true, body))
      await expect(probeOperatorSession(fetcher as typeof fetch)).resolves.toBeNull()
    },
  )
})
