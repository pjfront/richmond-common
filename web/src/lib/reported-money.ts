/** Fixed decimal dollars become integer cents before addition. No inferred zero. */
export function reportedCents(value: string): number {
  if (!/^\d{1,10}\.\d{2}$/.test(value)) throw new Error('Invalid reviewed financial amount')
  const [dollars, cents] = value.split('.')
  return Number(dollars) * 100 + Number(cents)
}

export function formatReportedMoney(value: string | number): string {
  const cents = typeof value === 'string' ? reportedCents(value) : value
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD',
    minimumFractionDigits: cents % 100 ? 2 : 0, maximumFractionDigits: 2 }).format(cents / 100)
}
