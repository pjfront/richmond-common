'use client'

/**
 * SpendingPatterns — detects notable patterns in an entity's outgoing
 * money and renders them as plain-language callout cards.
 *
 * Pure client-side analysis of already-fetched data. No new DB queries.
 * Only renders when a meaningful pattern is detected. No LLM.
 */

import type { PACOutgoingRow, PACIndependentExpenditureRow } from '@/lib/types'

interface Pattern {
  kind: 'concentrated' | 'broad' | 'top_heavy'
  description: string
}

interface Props {
  outgoing: PACOutgoingRow[]
  independentExpenditures: PACIndependentExpenditureRow[]
  entityDisplay: string
}

function fmt(n: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(n)
}

function pct(n: number, total: number): string {
  if (total <= 0) return '0%'
  return `${Math.round((n / total) * 100)}%`
}

function detectPatterns(
  outgoing: PACOutgoingRow[],
  ieRows: PACIndependentExpenditureRow[],
  entityDisplay: string,
): Pattern[] {
  const patterns: Pattern[] = []

  // Combine outgoing contributions + IE spending into one recipient view.
  // For IEs, the recipient is the candidate_name (beneficiary, not payee).
  const byRecipient = new Map<string, number>()

  for (const o of outgoing) {
    const key = o.recipient_candidate_name ?? o.recipient_committee_name
    byRecipient.set(key, (byRecipient.get(key) ?? 0) + o.amount)
  }
  for (const ie of ieRows) {
    if (!ie.candidate_name) continue
    const key = `(IE) ${ie.candidate_name}`
    byRecipient.set(key, (byRecipient.get(key) ?? 0) + ie.amount)
  }

  const total = Array.from(byRecipient.values()).reduce((s, v) => s + v, 0)
  if (total <= 0) return patterns

  const sorted = Array.from(byRecipient.entries()).sort((a, b) => b[1] - a[1])
  const recipientCount = sorted.length

  // Concentrated: >80% of spending to ≤2 recipients
  const top2 = sorted.slice(0, 2).reduce((s, [, v]) => s + v, 0)
  if (recipientCount >= 2 && top2 / total > 0.8) {
    const names = sorted.slice(0, 2).map(([n]) => n.replace(/^\(IE\) /, ''))
    patterns.push({
      kind: 'concentrated',
      description: `${entityDisplay}'s spending is concentrated: ${pct(top2, total)} went to ${names[0]} and ${names[1]}.`,
    })
  }

  // Top-heavy: single largest recipient gets >50%
  const top1 = sorted[0][1]
  if (recipientCount >= 2 && top1 / total > 0.5) {
    const name = sorted[0][0].replace(/^\(IE\) /, '')
    patterns.push({
      kind: 'top_heavy',
      description: `More than half of ${entityDisplay}'s spending (${pct(top1, total)}) went to a single recipient: ${name}.`,
    })
  }

  // Broad: ≥5 distinct recipients, none above 40%
  const top1Ratio = top1 / total
  if (recipientCount >= 5 && top1Ratio < 0.4) {
    patterns.push({
      kind: 'broad',
      description: `${entityDisplay} spread its spending across ${recipientCount} different recipients, with no single one getting more than ${pct(top1, total)}.`,
    })
  }

  return patterns
}

export default function SpendingPatterns({
  outgoing,
  independentExpenditures,
  entityDisplay,
}: Props) {
  const patterns = detectPatterns(outgoing, independentExpenditures, entityDisplay)
  if (patterns.length === 0) return null

  return (
    <section className="mb-6">
      <h2 className="text-xs font-semibold text-civic-navy uppercase tracking-widest mb-3">
        Things of note
      </h2>
      <div className="space-y-2">
        {patterns.map((p) => (
          <div
            key={p.kind}
            className="border border-civic-amber/30 bg-civic-amber/[0.03] rounded-lg px-4 py-3"
          >
            <p className="text-[14px] text-slate-700 leading-[1.7]">
              {p.description}
            </p>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-slate-400 mt-2">
        Auto-generated from public contribution and expenditure records.
        These are data patterns, not editorial judgments.
      </p>
    </section>
  )
}
