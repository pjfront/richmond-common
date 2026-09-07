/** Official metadata checked September 6. No extracted monetary values. */
export const ANDERSON_FILER = {
  committeeId: '1481105',
  portalFilerId: '214395297',
  committeeName: 'Anderson for Mayor 2026',
  identityFilingId: '217094857',
  checkedAt: '2026-09-06T16:45:39Z',
  sourceUrl: 'https://netfile.com/public/RICH/campaign/filingsByFiler/214395297-Anderson_for_Mayor_2026',
} as const

export type CandidateFiling = {
  id: string
  form: '460' | '497'
  filedAt: string
  periodStart: string | null
  periodEnd: string | null
  sourceUrl: string
  paperVerified: boolean
}

export type CandidateFilingCoverage = {
  status: 'available' | 'stale' | 'unavailable'
  checkedAt: string
  latestPeriodic: CandidateFiling
  recentRapid: CandidateFiling[]
}

export const VERIFIED_ANDERSON_FILINGS: CandidateFilingCoverage = {
  status: 'available',
  checkedAt: ANDERSON_FILER.checkedAt,
  latestPeriodic: {
    id: '217094857', form: '460', filedAt: '2026-07-29',
    periodStart: '2026-05-29', periodEnd: '2026-06-30',
    sourceUrl: 'https://netfile.com/Connect2/api/public/image/217094857', paperVerified: true,
  },
  recentRapid: [
    { id: '217352920', filedAt: '2026-09-03' },
    { id: '217332630', filedAt: '2026-08-31' },
    { id: '217243030', filedAt: '2026-08-17' },
    { id: '217243444', filedAt: '2026-08-17' },
  ].map(filing => ({ ...filing, form: '497', periodStart: null, periodEnd: null,
    sourceUrl: `https://netfile.com/Connect2/api/public/image/${filing.id}`, paperVerified: true })),
}
