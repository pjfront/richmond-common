/**
 * Richmond Local Issue Taxonomy
 *
 * Hyper-local issue categories that map agenda item text to the political
 * fault lines Richmond residents actually talk about. These aren't generic
 * civic categories — they're the specific places, institutions, and tensions
 * that define Richmond politics.
 *
 * Design: keyword matching against agenda item titles/descriptions.
 * This is transparent (citizens can see which keywords triggered the tag)
 * and doesn't require pipeline changes.
 *
 * JUDGMENT CALL: The taxonomy itself (which issues to track, how to label
 * them) was approved by the operator. Adding or removing issues is a
 * judgment call. Expanding keywords within an existing issue is AI-delegable.
 */

export interface LocalIssue {
  id: string
  /** The label Richmond residents would use */
  label: string
  /** One-line insider context for tooltips */
  context: string
  /** Keywords that trigger this issue tag (case-insensitive, matched against title + description) */
  keywords: string[]
  /** Tailwind color classes for the issue tag */
  color: string
}

export const RICHMOND_LOCAL_ISSUES: LocalIssue[] = [
  // ─── THE BIG THREE: issues that define Richmond politics ───

  {
    id: 'chevron',
    label: 'Chevron & the Refinery',
    context: 'Chevron Richmond is the city\'s largest employer, taxpayer, and political spender. The 2012 refinery fire and $3.1M in 2014 election spending are defining events.',
    keywords: [
      'chevron', 'refinery', 'richmond refinery',
      'flaring', 'flare', 'crude oil', 'hydrogen',
      'community benefits agreement', 'cba',
      'richmond standard',
    ],
    color: 'bg-red-100 text-red-800',
  },
  {
    id: 'point_molate',
    label: 'Point Molate',
    context: 'Former Navy fuel depot on the Richmond shoreline. Decades of developer proposals, tribal interests, environmental concerns, and community debate.',
    keywords: [
      'point molate', 'pt. molate', 'pt molate',
      'winehaven', 'wine haven',
    ],
    color: 'bg-emerald-100 text-emerald-800',
  },
  {
    id: 'rent_board',
    label: 'Rent Board & Tenants',
    context: 'Richmond passed rent control in 2016. The Rent Board sets annual adjustments and hears eviction cases. Tenant protection is a defining progressive policy.',
    keywords: [
      'rent control', 'rent board', 'rent program',
      'rent stabilization', 'rent adjustment',
      'just cause', 'just cause eviction',
      'tenant', 'tenants', 'tenant protection',
      'eviction', 'relocation payment',
      'habitability', 'rental inspection',
    ],
    color: 'bg-violet-100 text-violet-800',
  },

  // ─── PLACE-BASED: the sites everyone's watching ───

  {
    id: 'hilltop',
    label: 'The Hilltop',
    context: 'Hilltop Mall closed in 2020. Its redevelopment into housing, retail, and community space is the biggest land-use question in the city.',
    keywords: [
      'hilltop', 'hilltop mall', 'hilltop district',
      'dream fleetwood',
    ],
    color: 'bg-amber-100 text-amber-800',
  },
  {
    id: 'terminal_port',
    label: 'Terminal 1 & the Port',
    context: 'Terminal 1 is being redeveloped for mixed use. The Port of Richmond handles shipping and is exploring ferry service and offshore wind.',
    keywords: [
      'terminal 1', 'terminal one',
      'port of richmond', 'port director',
      'maritime', 'ferry service', 'ferry terminal',
      'offshore wind', 'wharf',
    ],
    color: 'bg-sky-100 text-sky-800',
  },
  {
    id: 'ford_point',
    label: 'Ford Point & Richmond Village',
    context: 'The former Ford Assembly plant is now mixed-use (Craneway Pavilion, Assemble). Richmond Village is a major housing development nearby.',
    keywords: [
      'ford assembly', 'ford point', 'ford building',
      'richmond village', 'craneway',
      'assemble', 'marina bay',
    ],
    color: 'bg-cyan-100 text-cyan-800',
  },
  {
    id: 'macdonald',
    label: 'Macdonald Avenue',
    context: 'Richmond\'s main commercial corridor through the Iron Triangle. The Macdonald Avenue Corridor Task Force is driving revitalization.',
    keywords: [
      'macdonald avenue', 'macdonald corridor',
      'macdonald task force',
      'iron triangle',
      'downtown richmond',
    ],
    color: 'bg-orange-100 text-orange-800',
  },

  // ─── INSTITUTIONAL: the recurring policy battlegrounds ───

  {
    id: 'police_reform',
    label: 'Police & Community Safety',
    context: 'Richmond pioneered the Office of Neighborhood Safety and community policing reform. The Community Police Review Commission provides civilian oversight.',
    keywords: [
      'police', 'rpd', 'police department',
      'public safety', 'law enforcement',
      'officer involved', 'officer-involved',
      'use of force', 'body-worn camera', 'body worn camera',
      'community police review', 'cprc',
      'crisis intervention', 'crisis response',
      'neighborhood safety', 'ons',
      'gun violence', 'firearm',
      'crime report', 'crime prevention',
    ],
    color: 'bg-blue-100 text-blue-800',
  },
  {
    id: 'environment',
    label: 'Environmental Justice',
    context: 'As a refinery town, Richmond faces unique air quality and contamination challenges. Environmental justice is deeply tied to neighborhood health equity.',
    keywords: [
      'climate', 'environmental',
      'greenhouse', 'carbon', 'emissions',
      'air quality', 'air monitoring',
      'pollution', 'contamination', 'contaminated',
      'brownfield', 'remediation', 'superfund',
      'toxic', 'hazardous',
      'green new deal', 'solar', 'sustainability',
      'transformative climate',
      'urban greening', 'greenway', 'richmond greenway',
    ],
    color: 'bg-teal-100 text-teal-800',
  },
  {
    id: 'labor',
    label: 'Labor & City Workers',
    context: 'SEIU Local 1021 represents most city employees. MOU negotiations, overtime, pensions, and staffing levels are perennial budget tensions.',
    keywords: [
      'seiu', 'local 1021',
      'memorandum of understanding',
      'collective bargaining',
      'overtime report', 'pension',
      'opeb', 'other post-employment',
      'staffing', 'vacancy', 'vacancies',
      'cost of living increase',
    ],
    color: 'bg-indigo-100 text-indigo-800',
  },
  {
    id: 'cannabis',
    label: 'Cannabis',
    context: 'Richmond has gone back and forth on dispensary regulations. Cannabis tax revenue and social equity licensing are active debates.',
    keywords: [
      'cannabis', 'marijuana',
      'dispensary', 'dispensaries',
      'cannabis tax',
    ],
    color: 'bg-lime-100 text-lime-800',
  },
  {
    id: 'youth',
    label: 'Youth & Community Programs',
    context: 'Richmond invests heavily in youth programs — RYSE Center, Youth Outdoors, mentoring, workforce development. These are often consent calendar items with real budget weight.',
    keywords: [
      'youth', 'young adults',
      'youth outdoors richmond',
      'ryse', 'mentoring', 'mentor',
      'afterschool', 'after-school', 'after school',
      'workforce development board',
      'job training', 'job center',
      'american job centers',
    ],
    color: 'bg-pink-100 text-pink-800',
  },
  {
    id: 'political_statements',
    label: 'Political Statements',
    context: 'Richmond\'s council regularly passes resolutions on national and international issues — from foreign policy to civil rights. These are often the most debated non-local items.',
    keywords: [
      'opposing', 'condemning',
      'in support of', 'in opposition to',
      'urging', 'calling upon',
      'ceasefire', 'solidarity',
      'resolution declaring', 'resolution opposing',
      'resolution supporting', 'resolution urging',
      'sanctuary', 'immigrant', 'immigration',
      'juneteenth', 'pride month',
      'day of remembrance', 'black history',
      'military intervention',
    ],
    color: 'bg-fuchsia-100 text-fuchsia-800',
  },
  {
    id: 'housing_development',
    label: 'Housing & Homelessness',
    context: 'Beyond rent control, Richmond faces housing production pressure from the state, Homekey projects for homelessness, and Housing Element compliance.',
    keywords: [
      'affordable housing', 'housing element',
      'housing authority', 'homekey',
      'homeless', 'homelessness', 'encampment',
      'transitional housing', 'supportive housing',
      'section 8', 'housing voucher',
      'inclusionary',
    ],
    color: 'bg-purple-100 text-purple-800',
  },
]

/**
 * Detect which local issues an agenda item title matches.
 * Returns matching issues (can be multiple — e.g. a Chevron item
 * about air quality matches both "Chevron" and "Environmental Justice").
 */
export function detectLocalIssues(text: string): LocalIssue[] {
  const lower = text.toLowerCase()
  return RICHMOND_LOCAL_ISSUES.filter(issue =>
    issue.keywords.some(kw => lower.includes(kw))
  )
}
