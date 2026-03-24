/**
 * Smart formatter for official government agenda text.
 *
 * Detects structural patterns (WHEREAS/RESOLVED clauses, numbered lists,
 * paragraph breaks) and returns segments for structured rendering.
 * Conservative: only formats patterns we're confident about.
 */

export interface TextSegment {
  type: 'paragraph' | 'clause' | 'list-item'
  /** For clauses: "WHEREAS" | "RESOLVED" | "NOW THEREFORE" etc. */
  keyword?: string
  text: string
}

const CLAUSE_PATTERN = /^(WHEREAS|RESOLVED|NOW,?\s*THEREFORE|BE IT FURTHER RESOLVED|BE IT RESOLVED),?\s*/i
const LIST_PATTERN = /^(\d+[\.\)]\s+|[a-z][\.\)]\s+|\([a-z0-9]+\)\s+)/i

/**
 * Parse government text into structured segments.
 *
 * Splits on: explicit line breaks, semicolons followed by WHEREAS/RESOLVED,
 * and semicolons before numbered items. Falls back to paragraphs.
 */
export function parseAgendaText(text: string): TextSegment[] {
  if (!text || !text.trim()) return []

  // First split on explicit line breaks
  const rawLines = text.split(/\n+/).map(l => l.trim()).filter(Boolean)

  // If we got multiple lines from actual line breaks, process each
  if (rawLines.length > 1) {
    return rawLines.flatMap(classifyLine)
  }

  // Single block of text — try to split on clause boundaries
  // Split before WHEREAS/RESOLVED/BE IT keywords (case-insensitive)
  const clauseSplit = text.split(/(?=\b(?:WHEREAS|RESOLVED|NOW,?\s*THEREFORE|BE IT FURTHER RESOLVED|BE IT RESOLVED)\b)/i)

  if (clauseSplit.length > 1) {
    return clauseSplit
      .map(s => s.trim())
      .filter(Boolean)
      .flatMap(classifyLine)
  }

  // Try splitting on semicolons (common in government text for listing conditions)
  const semiParts = text.split(/;\s*/)
  if (semiParts.length >= 3) {
    return semiParts
      .map(s => s.trim())
      .filter(Boolean)
      .map(part => classifyLine(part))
      .flat()
  }

  // No structure detected — return as single paragraph
  return [{ type: 'paragraph', text: text.trim() }]
}

function classifyLine(line: string): TextSegment[] {
  const trimmed = line.trim()
  if (!trimmed) return []

  // Check for WHEREAS/RESOLVED clause
  const clauseMatch = trimmed.match(CLAUSE_PATTERN)
  if (clauseMatch) {
    const keyword = clauseMatch[1].toUpperCase().replace(/,\s*$/, '')
    const rest = trimmed.slice(clauseMatch[0].length).trim()
    return [{ type: 'clause', keyword, text: rest || trimmed }]
  }

  // Check for numbered/lettered list items
  const listMatch = trimmed.match(LIST_PATTERN)
  if (listMatch) {
    return [{ type: 'list-item', text: trimmed }]
  }

  return [{ type: 'paragraph', text: trimmed }]
}

/**
 * Check if text has enough structure to warrant smart formatting.
 * If false, just render with whitespace-pre-line as before.
 */
export function hasStructure(text: string): boolean {
  if (!text) return false
  const segments = parseAgendaText(text)
  // Worth formatting if we found clauses, list items, or 3+ segments
  return segments.some(s => s.type === 'clause' || s.type === 'list-item') ||
    segments.length >= 3
}
