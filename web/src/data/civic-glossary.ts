/**
 * Civic Glossary — Seed Data for CivicTerm Tooltips
 *
 * Plain-language definitions of government jargon, filing types, and legal
 * concepts used throughout Richmond Common. Each entry maps a slug to the
 * data that CivicTerm needs: an official term, regulatory category, and
 * a one-sentence definition at approximately grade 6 reading level.
 *
 * Design rule D4: "Plain language is the visible label. Technical precision
 * lives in structured tooltips and CSV/API column names."
 *
 * This file serves two purposes:
 * 1. Direct import by CivicTerm components (zero API calls, build-time safe)
 * 2. Seed data for the eventual civic_glossary database table (T5 compliance)
 *
 * JUDGMENT CALL: Adding or removing terms is AI-delegable (factual/regulatory
 * definitions). Changing the plain-language label a citizen sees is a judgment
 * call requiring operator review.
 */

export interface CivicGlossaryEntry {
  /** The official/technical term (shown bold in tooltip) */
  term: string
  /** Regulatory or filing category (shown gray in tooltip) */
  category: string
  /** Plain-language label for UI display (~grade 6 reading level) */
  plainLabel: string
  /** One-sentence definition (shown in tooltip body) */
  definition: string
  /** Statutory or regulatory reference (for methodology page) */
  legalReference?: string
  /** URL to authoritative source */
  sourceUrl?: string
}

/**
 * Glossary entries keyed by slug. Slugs match the IDs used in component
 * imports: `CIVIC_GLOSSARY['behested-payment']`.
 */
export const CIVIC_GLOSSARY: Record<string, CivicGlossaryEntry> = {
  // ─── Behested Payments & Influence Transparency (S13) ────────

  'behested-payment': {
    term: 'Behested Payment',
    category: 'FPPC / Gov Code §82015',
    plainLabel: 'requested payment',
    definition:
      'A payment made to a third party (usually a nonprofit or government entity) at the request of an elected official. California requires disclosure when the total reaches $5,000 or more in a calendar year.',
    legalReference: 'California Government Code §82015',
    sourceUrl:
      'https://www.fppc.ca.gov/transparency/form-700-filed-by-public-officials/behested-payments2.html',
  },

  'form-803': {
    term: 'FPPC Form 803',
    category: 'FPPC Filing',
    plainLabel: 'payment disclosure form',
    definition:
      'The form elected officials file with the Fair Political Practices Commission to disclose payments they requested others to make. Must be filed within 30 days of the payment.',
    legalReference: 'California Government Code §82015(b)',
    sourceUrl:
      'https://www.fppc.ca.gov/transparency/form-700-filed-by-public-officials/behested-payments2.html',
  },

  'behested-payor': {
    term: 'Payor (Behested Payment)',
    category: 'FPPC / Form 803',
    plainLabel: 'the person or company who paid',
    definition:
      'The company or person who made a payment at an elected official\'s request. The payment goes to a third party, not to the official.',
  },

  'behested-payee': {
    term: 'Payee (Behested Payment)',
    category: 'FPPC / Form 803',
    plainLabel: 'the organization that received the payment',
    definition:
      'The third party — often a nonprofit, charity, or community organization — that received the payment an official requested.',
  },

  // ─── Lobbyist Registration ──────────────────────────────────

  'lobbyist-registration': {
    term: 'Lobbyist Registration',
    category: 'Richmond Municipal Code Ch. 2.54',
    plainLabel: 'lobbyist registration',
    definition:
      'Registration required when someone is paid to communicate with city officials to influence government decisions. Three types: contract lobbyists, business/organization lobbyists, and expenditure lobbyists. Filed with City Clerk as paper/PDF forms.',
    legalReference: 'Richmond Municipal Code Chapter 2.54',
  },

  // ─── Campaign Finance ───────────────────────────────────────

  'campaign-contribution': {
    term: 'Campaign Finance Filing',
    category: 'CAL-ACCESS / NetFile',
    plainLabel: 'campaign donation records',
    definition:
      'A mandatory disclosure of campaign contributions and expenditures filed with the state (CAL-ACCESS) or local (NetFile) registrar. All filings are public record under California Government Code §81008.',
    legalReference: 'California Government Code §81008',
  },

  'independent-expenditure': {
    term: 'Independent Expenditure',
    category: 'CAL-ACCESS / FPPC',
    plainLabel: 'spending for or against a candidate',
    definition:
      'Money spent to support or oppose a candidate or ballot measure without coordinating with their campaign. Must be reported when it exceeds $1,000.',
    legalReference: 'California Government Code §82031',
  },

  // ─── Conflicts & Ethics ─────────────────────────────────────

  'conflict-of-interest': {
    term: 'Financial Conflict of Interest',
    category: 'Gov Code §87100',
    plainLabel: 'conflict of interest',
    definition:
      'When an official has a financial interest in a decision they are voting on. California law requires the official to publicly disclose the conflict and abstain from the vote.',
    legalReference: 'California Government Code §87100',
  },

  'recusal': {
    term: 'Recusal / Disqualification',
    category: 'Gov Code §87105',
    plainLabel: 'recusal',
    definition:
      'When an official must step aside from a decision because of a financial conflict of interest. The official leaves the room and does not participate in discussion or voting.',
    legalReference: 'California Government Code §87105',
  },

  'form-700': {
    term: 'Statement of Economic Interests (Form 700)',
    category: 'FPPC Filing',
    plainLabel: 'financial disclosure',
    definition:
      'An annual filing where public officials disclose their investments, real property, income, and business positions. Used to identify potential conflicts of interest.',
    legalReference: 'California Government Code §87200',
    sourceUrl: 'https://www.fppc.ca.gov/form-700.html',
  },

  // ─── Meeting Types ─────────────────────────────────────────

  'meeting-regular': {
    term: 'Regular Meeting',
    category: 'Brown Act / Council Procedure',
    plainLabel: 'Regular',
    definition:
      'A regularly scheduled council meeting held on a fixed calendar (usually 1st and 3rd Tuesdays). The agenda is posted 72 hours in advance under the Brown Act.',
    legalReference: 'California Government Code §54954.2',
  },

  'meeting-special': {
    term: 'Special Meeting',
    category: 'Brown Act / Council Procedure',
    plainLabel: 'Special',
    definition:
      'A meeting called outside the regular schedule to address a specific, urgent topic. Only 24 hours notice is required, and the council can only discuss items listed in the special meeting notice.',
    legalReference: 'California Government Code §54956',
  },

  'meeting-closed-session': {
    term: 'Closed Session',
    category: 'Brown Act / Council Procedure',
    plainLabel: 'Closed',
    definition:
      'A meeting closed to the public, allowed only for specific topics like pending lawsuits, labor negotiations, real estate deals, or personnel matters. The council must publicly report any action taken.',
    legalReference: 'California Government Code §54957',
  },

  'meeting-joint': {
    term: 'Joint Meeting',
    category: 'Council Procedure',
    plainLabel: 'Joint',
    definition:
      'A meeting held together with another public body (such as a commission, school board, or neighboring city council) to discuss matters of shared interest.',
  },

  // ─── Government Process ─────────────────────────────────────

  'consent-calendar': {
    term: 'Consent Calendar',
    category: 'Council Procedure',
    plainLabel: 'routine items approved together',
    definition:
      'A group of routine agenda items approved in a single vote without individual discussion. Any council member can pull an item off consent for separate debate.',
  },

  'cpra': {
    term: 'California Public Records Act (CPRA)',
    category: 'Gov Code §7920',
    plainLabel: 'public records request',
    definition:
      'California law that gives the public the right to access government records. Agencies must respond within 10 days.',
    legalReference: 'California Government Code §7920 et seq.',
  },
} as const satisfies Record<string, CivicGlossaryEntry>

/**
 * Look up a glossary entry by slug. Returns undefined if not found.
 */
export function getGlossaryEntry(slug: string): CivicGlossaryEntry | undefined {
  return CIVIC_GLOSSARY[slug]
}

/**
 * Get all glossary entries as an array, sorted alphabetically by term.
 */
export function getAllGlossaryEntries(): (CivicGlossaryEntry & { slug: string })[] {
  return Object.entries(CIVIC_GLOSSARY)
    .map(([slug, entry]) => ({ slug, ...entry }))
    .sort((a, b) => a.term.localeCompare(b.term))
}
