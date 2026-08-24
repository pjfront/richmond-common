const RICHMOND_TIME_ZONE = 'America/Los_Angeles'

const RICHMOND_DATE_PARTS = new Intl.DateTimeFormat('en-US', {
  timeZone: RICHMOND_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

/** Return Richmond's current civil date as YYYY-MM-DD. */
export function richmondDateKey(now = new Date()): string {
  const parts = RICHMOND_DATE_PARTS.formatToParts(now)
  const year = parts.find((part) => part.type === 'year')?.value
  const month = parts.find((part) => part.type === 'month')?.value
  const day = parts.find((part) => part.type === 'day')?.value

  if (!year || !month || !day) {
    throw new Error('Could not determine the Richmond calendar date')
  }

  return `${year}-${month}-${day}`
}
