export type OperatorSessionState = boolean | null

/**
 * Resolve operator state only from a successful, well-shaped server response.
 * `null` is deliberately fail-closed: callers must keep analytics and
 * operator-only UI suppressed while the session boundary is unknown.
 */
export async function probeOperatorSession(
  fetcher: typeof fetch = fetch,
): Promise<OperatorSessionState> {
  try {
    const response = await fetcher('/api/operator/session', {
      credentials: 'same-origin',
      cache: 'no-store',
    })
    if (!response.ok) return null

    const data: unknown = await response.json()
    if (
      typeof data !== 'object'
      || data === null
      || typeof (data as { isOperator?: unknown }).isOperator !== 'boolean'
    ) {
      return null
    }

    return (data as { isOperator: boolean }).isOperator
  } catch {
    return null
  }
}
