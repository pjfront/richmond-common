import { failReadPath } from './read-path-unavailable'
import { isInertBuild } from './read-path-cache'

type RecordPage<T> = { data: T[] | null; error: unknown; count: number | null }

/** Never turn a failed or server-truncated page into a complete set of records. */
export async function readCompleteRecords<T extends { id: string }>(
  label: string,
  readPage: (from: number, to: number) => PromiseLike<RecordPage<T>>,
  options: { maxRows?: number; maxPages?: number } = {},
): Promise<T[]> {
  const maxRows = options.maxRows ?? 10_000
  const maxPages = options.maxPages ?? 20
  if (!Number.isSafeInteger(maxRows) || maxRows < 1 || maxRows > 50_000
    || !Number.isSafeInteger(maxPages) || maxPages < 1 || maxPages > 100) {
    throw new RangeError('Invalid complete record read limits')
  }
  // Isolated PR builds have no database. Do not attempt or cache a failed read.
  if (isInertBuild()) return []
  const records: T[] = []
  const seen = new Set<string>()
  let expected: number | null = null
  for (let page = 0; page < maxPages; page++) {
    const from = records.length
    const to = Math.min(from + 499, maxRows - 1)
    const { data, error, count } = await readPage(from, to)
    if (error) failReadPath(label, error)
    if (!data || count === null || !Number.isSafeInteger(count) || count < 0 || count > maxRows
      || (expected !== null && count !== expected)) failReadPath(label, 'Incomplete or changing record count')
    if (data.length > to - from + 1) failReadPath(label, 'Record page exceeded its requested size')
    expected = count
    for (const row of data) {
      if (!row.id || seen.has(row.id)) failReadPath(label, 'Repeated or missing record identity')
      seen.add(row.id)
      records.push(row)
    }
    if (records.length === expected) return records
    if (records.length > expected || data.length === 0) failReadPath(label, 'Record count did not match the response')
  }
  return failReadPath(label, 'Record read exceeded its bounded page count')
}
