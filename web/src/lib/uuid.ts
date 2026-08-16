const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

/** Reject malformed crawler/user IDs before PostgREST casts them to uuid. */
export function isUuid(value: string): boolean {
  return UUID_PATTERN.test(value)
}
