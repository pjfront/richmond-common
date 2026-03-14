/**
 * Richmond Local Issue Taxonomy (S11.5)
 *
 * Maps agenda item text to Richmond-specific political fault lines.
 * These are recurring local issues that cut across generic policy categories.
 *
 * Design: keyword matching against agenda item titles/descriptions.
 * This is transparent (citizens can see which keywords triggered the tag)
 * and doesn't require pipeline changes.
 *
 * JUDGMENT CALL: The taxonomy itself (which issues to track) was approved
 * by the operator. Adding or removing issues is a judgment call.
 */

export interface LocalIssue {
  id: string
  label: string
  /** Keywords that trigger this issue tag (case-insensitive, matched against item title) */
  keywords: string[]
  /** Color for the issue tag */
  color: string
}

export const RICHMOND_LOCAL_ISSUES: LocalIssue[] = [
  {
    id: 'point_molate',
    label: 'Point Molate',
    keywords: ['point molate', 'winehaven', 'pt. molate', 'pt molate'],
    color: 'bg-emerald-100 text-emerald-800',
  },
  {
    id: 'chevron',
    label: 'Chevron',
    keywords: ['chevron', 'refinery', 'richmond refinery'],
    color: 'bg-red-100 text-red-800',
  },
  {
    id: 'police',
    label: 'Police & Public Safety',
    keywords: ['police', 'rpd', 'public safety', 'law enforcement', 'officer involved', 'use of force'],
    color: 'bg-blue-100 text-blue-800',
  },
  {
    id: 'housing',
    label: 'Rent & Housing',
    keywords: ['rent control', 'tenant', 'eviction', 'affordable housing', 'rent board', 'rent stabilization', 'housing element'],
    color: 'bg-violet-100 text-violet-800',
  },
  {
    id: 'cannabis',
    label: 'Cannabis',
    keywords: ['cannabis', 'marijuana', 'dispensary', 'dispensaries'],
    color: 'bg-lime-100 text-lime-800',
  },
  {
    id: 'environment',
    label: 'Environment & Climate',
    keywords: ['climate', 'environmental', 'greenhouse', 'carbon', 'green new deal', 'solar', 'sustainability'],
    color: 'bg-teal-100 text-teal-800',
  },
  {
    id: 'development',
    label: 'Development',
    keywords: ['hilltop', 'terminal 1', 'terminal one', 'marina bay', 'ford assembly', 'iron triangle'],
    color: 'bg-orange-100 text-orange-800',
  },
]

/**
 * Detect which local issues an agenda item title matches.
 * Returns matching issue IDs (can be multiple).
 */
export function detectLocalIssues(title: string): LocalIssue[] {
  const lower = title.toLowerCase()
  return RICHMOND_LOCAL_ISSUES.filter(issue =>
    issue.keywords.some(kw => lower.includes(kw))
  )
}
