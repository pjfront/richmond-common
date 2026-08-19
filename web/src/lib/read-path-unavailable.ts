/**
 * Marks a database-backed public read as unavailable rather than empty.
 *
 * Callers use this distinction to avoid turning a timeout into a false
 * "nothing found" or 404 response.
 */
export class ReadPathUnavailableError extends Error {
  readonly readPath: string
  readonly originalError: unknown

  constructor(readPath: string, originalError: unknown) {
    super(`${readPath} is temporarily unavailable`)
    this.name = 'ReadPathUnavailableError'
    this.readPath = readPath
    this.originalError = originalError
  }
}

export function failReadPath(readPath: string, error: unknown): never {
  console.error(`${readPath} query failed:`, error)
  throw new ReadPathUnavailableError(readPath, error)
}
