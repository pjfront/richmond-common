'use client'

import { useState } from 'react'
import Link from 'next/link'
import type { ContributionMatrix, ContributionBucketKey, ContributorTypeKey } from '@/lib/types'
import { BUCKETS, SOURCE_TYPES } from '@/lib/contributionBuckets'

interface Props {
  matrix: ContributionMatrix
  /** First name only — used in the narrative so it reads naturally. */
  firstName: string
}

/**
 * Plain-language bucket display for a candidate's contributions.
 *
 * Two layers:
 *   1. A 1–2 sentence narrative leading with the money story (per
 *      DESIGN-RULES D6 — narrative over numbers).
 *   2. An expandable 5×4 table of dollar totals and contribution counts,
 *      keyed on regulatory thresholds (lib/contributionBuckets.ts).
 *
 * The numbers in the table are honest about what's in the candidate's
 * filings — no aggregation tricks, no rolling-up unique donors. Each
 * cell answers "how many contributions in this size range came from
 * this kind of giver, and how many dollars did they total?"
 */
export default function CandidateContributionBuckets({
  matrix,
  firstName,
}: Props) {
  const [expanded, setExpanded] = useState(false)

  if (matrix.total_count === 0) return null

  const narrative = buildBucketNarrative(matrix, firstName)
  const dominantSource = pickDominantSource(matrix)

  return (
    <div className="mt-3">
      <p className="text-xs text-slate-500 leading-relaxed">{narrative}</p>

      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-2 text-xs text-civic-navy hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-civic-navy/40 rounded"
        aria-expanded={expanded}
      >
        {expanded ? 'Hide breakdown' : 'Show breakdown by source and amount'}
      </button>

      {expanded && (
        <div className="mt-3">
          <BucketTable matrix={matrix} dominantSource={dominantSource} />
          <p className="text-[10px] text-slate-400 mt-2 leading-relaxed">
            Source: NetFile public filings.{' '}
            <Link
              href="/elections/methodology"
              className="text-civic-navy hover:underline"
            >
              Why these amounts?
            </Link>
          </p>
        </div>
      )}
    </div>
  )
}

// ─── Narrative builder ─────────────────────────────────────────────────

/**
 * Always covers the same two questions:
 *   1. Did anyone max out? If so, how many and from what source?
 *   2. How much of the money came from small donors (under $100)?
 *
 * This shape works whether the candidate has 5 contributions or 500 —
 * the two facts are always defined, and they tell the "concentrated vs.
 * broad-base" story the bucket UI is designed to surface.
 */
function buildBucketNarrative(
  matrix: ContributionMatrix,
  firstName: string,
): string {
  const sentences: string[] = []

  const cap = sumBucket(matrix, 'at_2500_cap')
  const small = sumBucket(matrix, 'under_100')

  // Sentence 1: who maxed out (if anyone)
  if (cap.count > 0) {
    const sources = topSourcesAtBucket(matrix, 'at_2500_cap')
    const sourceList = formatSourceList(sources)
    sentences.push(
      cap.count === 1
        ? `One contribution maxed out at the $2,500 Richmond cap` +
            (sourceList ? ` (from ${sourceList})` : '') +
            `.`
        : `${cap.count} contributions of $2,500 each — the Richmond per-cycle cap — account for $${fmt(cap.dollars)} of ${firstName}’s fundraising` +
            (sourceList ? `, mostly from ${sourceList}` : '') +
            `.`,
    )
  }

  // Sentence 2: how broad the small-donor base is
  if (small.count > 0) {
    const smallPct = Math.round((small.count / matrix.total_count) * 100)
    if (smallPct >= 25) {
      sentences.push(
        `${smallPct}% of contributions were under $100 — donations that small don’t require the donor’s name on filings.`,
      )
    } else {
      sentences.push(
        `${small.count} contributions were under $100, totaling $${fmt(small.dollars)}.`,
      )
    }
  } else if (cap.count === 0) {
    // No max-outs and no under-$100s — describe the middle.
    const dominant = pickDominantSource(matrix)
    if (dominant) {
      const cell = sumSource(matrix, dominant)
      const sourceLabel = SOURCE_TYPES.find((s) => s.key === dominant)?.label?.toLowerCase() ?? dominant
      const pct = Math.round((cell.dollars / matrix.total_dollars) * 100)
      sentences.push(
        `${pct}% of ${firstName}’s funds came from ${sourceLabel} donors.`,
      )
    }
  }

  if (sentences.length === 0) {
    return `${firstName}’s committee has ${matrix.total_count} recorded contribution${matrix.total_count !== 1 ? 's' : ''} totaling $${fmt(matrix.total_dollars)}.`
  }
  return sentences.join(' ')
}

function sumBucket(
  matrix: ContributionMatrix,
  bucket: ContributionBucketKey,
): { count: number; dollars: number } {
  let count = 0
  let dollars = 0
  for (const s of SOURCE_TYPES) {
    const cell = matrix.cells[s.key][bucket]
    count += cell.count
    dollars += cell.dollars
  }
  return { count, dollars }
}

function sumSource(
  matrix: ContributionMatrix,
  source: ContributorTypeKey,
): { count: number; dollars: number } {
  let count = 0
  let dollars = 0
  for (const b of BUCKETS) {
    const cell = matrix.cells[source][b.key]
    count += cell.count
    dollars += cell.dollars
  }
  return { count, dollars }
}

/** Return source types with non-zero contributions at a bucket, in descending dollar order. */
function topSourcesAtBucket(
  matrix: ContributionMatrix,
  bucket: ContributionBucketKey,
): ContributorTypeKey[] {
  return [...SOURCE_TYPES]
    .map((s) => ({ key: s.key, dollars: matrix.cells[s.key][bucket].dollars }))
    .filter((r) => r.dollars > 0)
    .sort((a, b) => b.dollars - a.dollars)
    .map((r) => r.key)
}

/** Plain-language list: "individuals", "unions", "individuals and unions", "individuals, unions, and PACs". */
function formatSourceList(sources: ContributorTypeKey[]): string {
  if (sources.length === 0) return ''
  const labels = sources.map((k) => {
    const s = SOURCE_TYPES.find((x) => x.key === k)
    if (!s) return k
    // Pluralize for narrative voice ("individuals", "unions", "businesses", "PACs")
    if (s.key === 'business') return 'businesses'
    if (s.key === 'pac') return 'PACs'
    return s.label.toLowerCase() + 's'
  })
  if (labels.length === 1) return labels[0]
  if (labels.length === 2) return `${labels[0]} and ${labels[1]}`
  return `${labels.slice(0, -1).join(', ')}, and ${labels[labels.length - 1]}`
}

/** Pick the source type that contributed the most dollars, or null if all zero. */
function pickDominantSource(
  matrix: ContributionMatrix,
): ContributorTypeKey | null {
  let best: ContributorTypeKey | null = null
  let bestDollars = 0
  for (const s of SOURCE_TYPES) {
    const total = sumSource(matrix, s.key).dollars
    if (total > bestDollars) {
      bestDollars = total
      best = s.key
    }
  }
  return best
}

// ─── Detail table ──────────────────────────────────────────────────────

function BucketTable({
  matrix,
  dominantSource,
}: {
  matrix: ContributionMatrix
  dominantSource: ContributorTypeKey | null
}) {
  // Hide an entire source-type column if it has zero contributions — keeps
  // the table compact for small-data candidates (e.g., a candidate with
  // only individual donors gets a 1-column table, not 4).
  const visibleSources = SOURCE_TYPES.filter(
    (s) => sumSource(matrix, s.key).count > 0,
  )
  if (visibleSources.length === 0) return null

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="border-b border-slate-200">
            <th
              scope="col"
              className="text-left py-2 pr-2 font-medium text-slate-500"
            >
              Amount
            </th>
            {visibleSources.map((s) => (
              <th
                key={s.key}
                scope="col"
                className={`text-right py-2 px-2 font-medium ${
                  s.key === dominantSource
                    ? 'text-civic-navy'
                    : 'text-slate-500'
                }`}
                title={s.description}
              >
                {s.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {BUCKETS.map((b) => {
            const rowSum = sumBucket(matrix, b.key)
            if (rowSum.count === 0) return null  // hide empty rows too
            return (
              <tr key={b.key} className="border-b border-slate-100">
                <th
                  scope="row"
                  className="text-left py-2 pr-2 font-normal text-slate-600 align-top"
                  title={b.rationale}
                >
                  {b.shortLabel}
                </th>
                {visibleSources.map((s) => {
                  const cell = matrix.cells[s.key][b.key]
                  return (
                    <td
                      key={s.key}
                      className="text-right py-2 px-2 tabular-nums align-top"
                    >
                      {cell.count === 0 ? (
                        <span className="text-slate-300" aria-label="none">
                          —
                        </span>
                      ) : (
                        <>
                          <span className="text-slate-700 font-medium">
                            ${fmt(cell.dollars)}
                          </span>
                          <span className="text-slate-400 ml-1">
                            ({cell.count})
                          </span>
                        </>
                      )}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
        <tfoot>
          <tr>
            <th
              scope="row"
              className="text-left pt-2 pr-2 font-medium text-slate-600"
            >
              All amounts
            </th>
            {visibleSources.map((s) => {
              const total = sumSource(matrix, s.key)
              return (
                <td
                  key={s.key}
                  className="text-right pt-2 px-2 tabular-nums font-medium text-civic-navy"
                >
                  ${fmt(total.dollars)}
                  <span className="text-slate-400 ml-1 font-normal">
                    ({total.count})
                  </span>
                </td>
              )
            })}
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function fmt(n: number): string {
  return Math.round(n).toLocaleString('en-US')
}
