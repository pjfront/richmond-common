import { unstable_cache } from 'next/cache'
import { ANDERSON_FILER, VERIFIED_ANDERSON_FILINGS, type CandidateFiling, type CandidateFilingCoverage } from '@/data/anderson-paper-filings'
import { JIMENEZ_FINANCE, VERIFIED_JIMENEZ_FILINGS } from '@/lib/jimenez-finance'

const PORTAL = 'https://netfile.com/api/public/sites/api'
const CONNECT = 'https://netfile.com/Connect2/api/public'
const MAX_ROWS = 100
const MAX_BYTES = 256 * 1024
const REVALIDATE_SECONDS = 3600
type FilerConfig = { portalFilerId: string; committeeId: string; committeeName: string; verified: CandidateFilingCoverage }
const andersonConfig: FilerConfig = { ...ANDERSON_FILER, verified: VERIFIED_ANDERSON_FILINGS }
const jimenezConfig: FilerConfig = {
  portalFilerId: JIMENEZ_FINANCE.committee.portal_filer_id,
  committeeId: JIMENEZ_FINANCE.committee.fppc_id,
  committeeName: JIMENEZ_FINANCE.committee.name,
  verified: VERIFIED_JIMENEZ_FILINGS,
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid filing metadata')
  return value as Record<string, unknown>
}

function sourceDate(value: unknown): string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}(?:T|$)/.test(value)) throw new Error('Invalid filing date')
  const day = value.slice(0, 10)
  const parsed = new Date(`${day}T12:00:00Z`)
  if (!Number.isFinite(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== day) throw new Error('Invalid filing date')
  return day
}

async function boundedJson(url: string, fetcher: typeof fetch): Promise<unknown> {
  const response = await fetcher(url, { signal: AbortSignal.timeout(2500), cache: 'no-store', redirect: 'error' })
  if (!response.ok || !response.body) throw new Error('Official filing service unavailable')
  const reader = response.body.getReader()
  let size = 0
  const chunks: Uint8Array[] = []
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > MAX_BYTES) throw new Error('Official filing response exceeds limit')
      chunks.push(value)
    }
  } finally {
    await reader.cancel()
  }
  const bytes = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength }
  return JSON.parse(new TextDecoder().decode(bytes)) as unknown
}

/** Fixed internal filer configs only. Two metadata GETs, no PDF or money parsing. */
async function acquireFilingCoverage(config: FilerConfig, fetcher: typeof fetch, now: Date): Promise<CandidateFilingCoverage> {
  const paperIds = new Set([config.verified.latestPeriodic, ...config.verified.recentRapid]
    .filter(filing => filing.paperVerified).map(filing => filing.id))
  const inventory = object(await boundedJson(`${PORTAL}/filings/byFiler?agencyCode=RICH&filerId=${config.portalFilerId}&isArchived=false`, fetcher))
  if (!Array.isArray(inventory.filings) || !inventory.filings.length || inventory.filings.length > MAX_ROWS) throw new Error('Filing inventory is empty, malformed, or exceeds limit')
  // The official portal returns totalCount=0 alongside nonempty filings. Its
  // own UI uses the array. Neither field proves economic/reporting completeness.
  if (typeof inventory.totalCount !== 'number' || !Number.isInteger(inventory.totalCount) || inventory.totalCount < 0
    || (inventory.totalCount > 0 && inventory.totalCount !== inventory.filings.length)) throw new Error('Filing inventory may be incomplete')
  const identifiers = new Set<string>()
  const filings: CandidateFiling[] = []
  for (const value of inventory.filings) {
    const row = object(value)
    if (typeof row.id !== 'string' || !/^\d+$/.test(row.id) || identifiers.has(row.id)) throw new Error('Filing identity is ambiguous')
    identifiers.add(row.id)
    const form = ['FPPC 460', 'FPPC 460 (Amendment)'].includes(String(row.formName)) ? '460'
      : ['FPPC Form 497', 'FPPC Form 497 (Amendment)'].includes(String(row.formName)) ? '497' : null
    // An older Form 410 may carry an earlier legal name. It is not used here;
    // every relevant 460/497 still requires the exact configured current name.
    if (!form) continue
    if (row.filerName !== config.committeeName) throw new Error('Filing identity is ambiguous')
    const filedAt = sourceDate(row.filingDate)
    if (filedAt > now.toISOString().slice(0, 10)) throw new Error('Filing date is in the future')
    filings.push({ id: row.id, form, filedAt,
      periodStart: form === '460' ? sourceDate(row.periodStart) : null,
      periodEnd: form === '460' ? sourceDate(row.periodEnd) : null,
      sourceUrl: `${CONNECT}/image/${row.id}`, paperVerified: paperIds.has(row.id) })
  }
  const periodic = filings.filter(filing => filing.form === '460')
    .sort((a, b) => (b.periodEnd ?? '').localeCompare(a.periodEnd ?? ''))
  const latest = periodic[0]
  if (!latest || latest.periodStart! > latest.periodEnd! || latest.periodEnd! > latest.filedAt
    || (periodic[1]?.periodEnd === latest.periodEnd)) throw new Error('Latest periodic report is missing or ambiguous')
  // The fixed portal ID was resolved from the identity filing's official byId
  // response. Recheck the latest report against the separate FPPC ID contract.
  const info = object(await boundedJson(`${CONNECT}/filing/info/${latest.id}?format=json`, fetcher))
  const sourceForm = object(inventory.filings.find(row => object(row).id === latest.id)).formId
  if (String(info.filingId) !== latest.id || info.agency !== 'RICH' || info.sosFilerId !== config.committeeId
    || info.filerName !== config.committeeName || typeof info.isEfiled !== 'boolean'
    || typeof sourceForm !== 'string' || info.formId !== sourceForm
    || info.amendedBy !== null || sourceDate(info.dateStart) !== latest.periodStart
    || sourceDate(info.dateEnd) !== latest.periodEnd || sourceDate(info.filingDate) !== latest.filedAt) throw new Error('Official filing identity or period did not match')
  return {
    status: 'available', checkedAt: now.toISOString(), latestPeriodic: { ...latest, paperVerified: !info.isEfiled },
    recentRapid: filings.filter(filing => filing.form === '497' && filing.filedAt > latest.periodEnd!)
      .sort((a, b) => b.filedAt.localeCompare(a.filedAt) || a.id.localeCompare(b.id)).slice(0, 4),
  }
}

export async function acquireAndersonFilingCoverage(fetcher: typeof fetch = fetch, now = new Date()): Promise<CandidateFilingCoverage> {
  return acquireFilingCoverage(andersonConfig, fetcher, now)
}

export async function acquireJimenezFilingCoverage(fetcher: typeof fetch = fetch, now = new Date()): Promise<CandidateFilingCoverage> {
  return acquireFilingCoverage(jimenezConfig, fetcher, now)
}

const readCachedAndersonCoverage = unstable_cache(acquireAndersonFilingCoverage, ['candidate-paper-1481105-v1'],
  { revalidate: REVALIDATE_SECONDS, tags: ['candidate-paper-1481105'] })
const readCachedJimenezCoverage = unstable_cache(acquireJimenezFilingCoverage, ['candidate-filings-1488504-v1'],
  { revalidate: REVALIDATE_SECONDS, tags: ['candidate-filings-1488504'] })

/** A failed refresh keeps the dated, verified baseline, never a zero-money finding. */
async function cachedCoverage(read: () => Promise<CandidateFilingCoverage>, verified: CandidateFilingCoverage): Promise<CandidateFilingCoverage> {
  try {
    const coverage = await read()
    return Date.now() - Date.parse(coverage.checkedAt) > REVALIDATE_SECONDS * 2000
      ? { ...coverage, status: 'stale' } : coverage
  } catch {
    return { ...verified, status: 'unavailable' }
  }
}

export async function getAndersonFilingCoverage(): Promise<CandidateFilingCoverage> {
  return cachedCoverage(readCachedAndersonCoverage, VERIFIED_ANDERSON_FILINGS)
}

export async function getJimenezFilingCoverage(): Promise<CandidateFilingCoverage> {
  return cachedCoverage(readCachedJimenezCoverage, VERIFIED_JIMENEZ_FILINGS)
}
