import { createHash } from 'node:crypto'

export const PROVIDER_EMAIL_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const READ_TIMEOUT_MS = 8_000
const MAX_RESPONSE_BYTES = 1_048_576
const SENDER = 'Richmond Commons <updates@richmondcommons.org>'
const PROVIDER_EVENTS = new Set([
  'bounced', 'canceled', 'clicked', 'complained', 'delivered', 'delivery_delayed',
  'failed', 'opened', 'queued', 'scheduled', 'sent',
])

interface CanaryProviderProof {
  provider_id: string
  provider_last_event: string
  subject: string
  html_sha256: string
  text_sha256: string
}

function isCanaryDigestSubject(value: unknown): value is string {
  if (typeof value !== 'string') return false
  const counts = value.match(/^\[CANARY\] This week in Richmond: (?:([1-9][0-9]?) reviewed updates?(?: and ([1-9][0-9]?) meetings?)?|([1-9][0-9]?) meetings?)$/)
  if (!counts) return false
  const briefs = Number(counts[1] ?? 0)
  const meetings = Number(counts[2] ?? counts[3] ?? 0)
  const meetingLabel = `${meetings} meeting${meetings === 1 ? '' : 's'}`
  const expected = briefs
    ? `${briefs} reviewed update${briefs === 1 ? '' : 's'}${meetings ? ` and ${meetingLabel}` : ''}`
    : meetingLabel
  return value === `[CANARY] This week in Richmond: ${expected}`
}

async function readBoundedJson(response: Response): Promise<unknown> {
  if (response.status !== 200 || !response.headers.get('content-type')?.toLowerCase().startsWith('application/json')) {
    await response.body?.cancel()
    throw new Error('Provider proof unavailable')
  }
  const advertised = response.headers.get('content-length')
  if (advertised !== null && (!/^\d+$/.test(advertised) || Number(advertised) > MAX_RESPONSE_BYTES)) {
    await response.body?.cancel()
    throw new Error('Provider proof unavailable')
  }
  if (!response.body) throw new Error('Provider proof unavailable')
  const reader = response.body.getReader()
  const chunks: Uint8Array[] = []
  let length = 0
  try {
    while (true) {
      const chunk = await reader.read()
      if (chunk.done) break
      length += chunk.value.byteLength
      if (length > MAX_RESPONSE_BYTES) throw new Error('Provider proof unavailable')
      chunks.push(chunk.value)
    }
    const bytes = Buffer.concat(chunks, length)
    return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes))
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}

/** One fixed-origin, bounded provider GET. Never list emails, send, retry, log
 * provider payloads, or return recipient/body/key fields. API contract:
 * https://resend.com/docs/api-reference/emails/retrieve-email
 * The provider's event is reported verbatim; this helper never infers delivery.
 */
export async function readDigestCanaryProof(providerId: string, canaryEmail: string): Promise<CanaryProviderProof | null> {
  const apiKey = process.env.RESEND_API_KEY
  if (!PROVIDER_EMAIL_ID.test(providerId) || !canaryEmail || !apiKey) return null
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), READ_TIMEOUT_MS)
  try {
    const response = await fetch(`https://api.resend.com/emails/${providerId}`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${apiKey}`, Accept: 'application/json' },
      cache: 'no-store',
      redirect: 'error',
      signal: controller.signal,
    })
    const raw = await readBoundedJson(response)
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
    const email = raw as Record<string, unknown>
    if (email.object !== 'email' || email.id !== providerId
      || !Array.isArray(email.to) || email.to.length !== 1 || email.to[0] !== canaryEmail
      || email.from !== SENDER || !isCanaryDigestSubject(email.subject)
      || !Array.isArray(email.cc) || email.cc.length !== 0
      || !Array.isArray(email.bcc) || email.bcc.length !== 0
      || typeof email.last_event !== 'string' || !PROVIDER_EVENTS.has(email.last_event)
      || typeof email.html !== 'string' || !email.html.trim()
      || typeof email.text !== 'string' || !email.text.trim()) return null
    return {
      provider_id: providerId,
      provider_last_event: email.last_event,
      subject: email.subject,
      html_sha256: createHash('sha256').update(email.html, 'utf8').digest('hex'),
      text_sha256: createHash('sha256').update(email.text, 'utf8').digest('hex'),
    }
  } catch {
    // Includes sending-only API-key permissions, redirects, transport/timeout,
    // size/JSON failures, and malformed records. Do not expose provider errors.
    return null
  } finally {
    clearTimeout(timeout)
  }
}
