/** Accessible color palette for 6 council districts (colorblind-safe) */

export const DISTRICT_COLORS: Record<number, string> = {
  1: '#0d9488', // Teal
  2: '#2563eb', // Blue
  3: '#d97706', // Amber
  4: '#e11d48', // Rose
  5: '#7c3aed', // Purple
  6: '#16a34a', // Green
}

export const DISTRICT_LABELS: Record<number, string> = {
  1: 'Teal',
  2: 'Blue',
  3: 'Amber',
  4: 'Rose',
  5: 'Purple',
  6: 'Green',
}

export function getDistrictColor(district: number): string {
  return DISTRICT_COLORS[district] ?? '#6b7280'
}

export function getDistrictStyle(district: number, state: 'normal' | 'hover' | 'selected') {
  const color = getDistrictColor(district)
  const fillOpacity = state === 'normal' ? 0.3 : state === 'hover' ? 0.45 : 0.55
  const weight = state === 'normal' ? 2.5 : 3.5
  return {
    color,
    fillColor: color,
    fillOpacity,
    weight,
    opacity: 1,
  }
}
