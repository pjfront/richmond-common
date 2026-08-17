const DEFAULT_OPERATOR_DESTINATION = '/operator/settings'

/** Keep post-login navigation on a server-protected operator route. */
export function safeOperatorDestination(candidate: string | null): string {
  if (!candidate || !candidate.startsWith('/operator/') || candidate.includes('\\')) {
    return DEFAULT_OPERATOR_DESTINATION
  }

  try {
    const resolved = new URL(candidate, 'https://richmondcommons.org')
    if (
      resolved.origin !== 'https://richmondcommons.org'
      || !resolved.pathname.startsWith('/operator/')
    ) {
      return DEFAULT_OPERATOR_DESTINATION
    }
    return `${resolved.pathname}${resolved.search}${resolved.hash}`
  } catch {
    return DEFAULT_OPERATOR_DESTINATION
  }
}

/** Force a document navigation so client providers cannot retain public state. */
export function reloadIntoOperatorSession(
  destination: string,
  locationLike: Pick<Location, 'assign'> = window.location,
): void {
  locationLike.assign(safeOperatorDestination(destination))
}
