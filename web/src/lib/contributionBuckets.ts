// Single source of truth for contribution bucket boundaries + labels.
//
// The boundaries are real California campaign-finance rules verified in
// D56b (see docs/AI-PARKING-LOT.md, 2026-05-17 entry). Changing a number
// here means a rule changed (or our reading of the rule did) — never a
// UI tweak. Three consumers read from this module:
//
//   1. queries/elections.ts — buckets contribution rows server-side
//   2. components/CandidateContributionBuckets.tsx — labels + tooltips
//   3. app/elections/methodology/page.tsx — plain-language explanation
//   4. types.drift / regression test — boundary assertions
//
// If you add a bucket, update the ContributionBucketKey union in
// lib/types.ts and the test in web/src/lib/contributionBuckets.test.ts.

import type {
  ContributionBucketKey,
  ContributorTypeKey,
  ContributionMatrix,
  ContributionMatrixCell,
} from './types'

/**
 * Half-open boundaries: `min <= amount < max`. The last bucket has
 * Number.POSITIVE_INFINITY as max — there's no legal contribution above
 * Richmond's $2,500 per-cycle cap, but treating it as the catch-all
 * means we surface any over-cap aggregates as "at cap" rather than
 * dropping them entirely (which would silently under-count).
 */
export const BUCKETS: ReadonlyArray<{
  key: ContributionBucketKey
  min: number
  max: number
  /** Short label for compact UI rendering, e.g. table headers. */
  shortLabel: string
  /** Plain-language label (Leisa Johnson standard). */
  plainLabel: string
  /** Why this boundary exists (regulatory rationale, plain-language). */
  rationale: string
  /** Primary source citation, used by the methodology page. */
  source: string
}> = [
  {
    key: 'under_100',
    min: 0,
    max: 100,
    shortLabel: 'Under $100',
    plainLabel: 'Under $100',
    rationale:
      'Donations under $100 don’t have to list the donor’s name on filings. They’re reported as one combined total.',
    source: 'FPPC Campaign Manual 2, Chapter 3 (itemization threshold)',
  },
  {
    key: 'between_100_249',
    min: 100,
    max: 250,
    shortLabel: '$100–$249',
    plainLabel: '$100 to $249',
    rationale:
      'At $100 the donor’s name, employer, and occupation appear on the candidate’s public filings.',
    source: 'FPPC Campaign Manual 2, Chapter 3',
  },
  {
    key: 'between_250_999',
    min: 250,
    max: 1000,
    shortLabel: '$250–$999',
    plainLabel: '$250 to $999',
    rationale:
      'At $250 a state pay-to-play rule kicks in. A Richmond elected official can’t accept this much from anyone with business pending before the city without either returning the money within 14 days or stepping aside from the vote.',
    source: 'SB 1439 / California Gov. Code §84308 (since Jan 1, 2023)',
  },
  {
    key: 'between_1000_2499',
    min: 1000,
    max: 2500,
    shortLabel: '$1,000–$2,499',
    plainLabel: '$1,000 to $2,499',
    rationale:
      'In the 90 days before an election, donations of $1,000 or more trigger a 24-hour disclosure form. The candidate has one business day to report them publicly.',
    source: 'FPPC Form 497 (24-hour late-contribution report)',
  },
  {
    key: 'at_2500_cap',
    min: 2500,
    max: Number.POSITIVE_INFINITY,
    shortLabel: '$2,500 (cap)',
    plainLabel: 'At the $2,500 cap',
    rationale:
      'Richmond limits any one person, business, union, or PAC to $2,500 per candidate per election cycle. Anyone here has given the maximum allowed.',
    source: 'Richmond Municipal Code §2.42.050(a)(1)',
  },
] as const

export const SOURCE_TYPES: ReadonlyArray<{
  key: ContributorTypeKey
  label: string
  /** Plain-language description for methodology + tooltips. */
  description: string
}> = [
  {
    key: 'individual',
    label: 'Individual',
    description: 'A person giving their own money (a resident, business owner, employee — anyone donating in their personal capacity).',
  },
  {
    key: 'business',
    label: 'Business',
    description:
      'A company, partnership, or corporation donating from business funds. Includes LLCs, real-estate firms, consulting groups, and similar.',
  },
  {
    key: 'union',
    label: 'Union',
    description:
      'A labor union or its political arm — for example, SEIU Local 1021, Richmond Police Officers Association, IBEW, firefighters’ associations.',
  },
  {
    key: 'pac',
    label: 'PAC',
    description:
      'A political action committee — a separate organization that raises money to support candidates or ballot measures. Includes party committees and independent expenditure committees.',
  },
] as const

/** Map raw contributions.contributor_type column to a display key. */
export function classifyContributorType(
  raw: string | null | undefined,
): ContributorTypeKey {
  switch (raw) {
    case 'individual':
      return 'individual'
    case 'union':
      return 'union'
    case 'pac_ie':
      return 'pac'
    case 'corporate':
    case 'other':
    case null:
    case undefined:
    default:
      // 'other' rolls into 'business' per the same FPPC ENTITY_CD 'OTH'
      // convention (overwhelmingly businesses + orgs). Unclassified rows
      // also land here so they're never silently dropped.
      return 'business'
  }
}

/** Place an amount into its half-open bucket key. */
export function bucketKeyForAmount(amount: number): ContributionBucketKey {
  for (const b of BUCKETS) {
    if (amount >= b.min && amount < b.max) return b.key
  }
  // Defensive — BUCKETS already covers [0, +Inf) so this is unreachable
  // unless amount is NaN or negative. Negative amounts (refunds) are
  // rare but real on Form 460; bucket them with the smallest amounts so
  // they show up but don’t skew the visible totals.
  return 'under_100'
}

/** Build a zero-initialized dense matrix for accumulation. */
export function emptyMatrix(): ContributionMatrix {
  const cells = {} as Record<
    ContributorTypeKey,
    Record<ContributionBucketKey, ContributionMatrixCell>
  >
  for (const s of SOURCE_TYPES) {
    cells[s.key] = {} as Record<ContributionBucketKey, ContributionMatrixCell>
    for (const b of BUCKETS) {
      cells[s.key][b.key] = { count: 0, dollars: 0 }
    }
  }
  return { cells, total_count: 0, total_dollars: 0 }
}

/** Add one contribution row to a matrix in place. */
export function addToMatrix(
  matrix: ContributionMatrix,
  row: { amount: number; contributor_type: string | null | undefined },
): void {
  const source = classifyContributorType(row.contributor_type)
  const bucket = bucketKeyForAmount(row.amount)
  const cell = matrix.cells[source][bucket]
  cell.count += 1
  cell.dollars += row.amount
  matrix.total_count += 1
  matrix.total_dollars += row.amount
}
