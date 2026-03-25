/**
 * Smart formatter for official government agenda text.
 *
 * Handles two zones:
 * 1. Recommended action text (clean, from eSCRIBE)
 * 2. Staff report text (messy, PDF-extracted after "[eSCRIBE Staff Report/Attachment Text]")
 *
 * PDF text has hard line breaks at column boundaries (~60-70 chars),
 * page headers/footers, and section labels split across lines.
 * This formatter rejoins broken lines, detects section headers,
 * cleans page artifacts, and produces flowing prose.
 */

export interface TextSegment {
  type: 'paragraph' | 'clause' | 'list-item' | 'section-header'
  /** For clauses: "WHEREAS" | "RESOLVED" | "NOW THEREFORE" etc. */
  /** For section-headers: the header text */
  keyword?: string
  text: string
}

const CLAUSE_PATTERN = /^(WHEREAS|RESOLVED|NOW,?\s*THEREFORE|BE IT FURTHER RESOLVED|BE IT RESOLVED),?\s*/i
const LIST_PATTERN = /^(\d+[\.\)]\s+|[a-z][\.\)]\s+|\([a-z0-9]+\)\s+)/i
const BULLET_PATTERN = /^[•▐◾◼■⬛▪►▸–—]\s*/

/** Government agenda section headers — commonly found in staff reports */
const SECTION_HEADERS = [
  'FINANCIAL IMPACT',
  'FISCAL IMPACT',
  'PREVIOUS COUNCIL ACTION',
  'STATEMENT OF THE ISSUE',
  'RECOMMENDED ACTION',
  'DISCUSSION',
  'BACKGROUND',
  'ALTERNATIVES',
  'CONCLUSION',
  'NEXT STEPS',
  'ENVIRONMENTAL REVIEW',
  'CEQA',
  'ATTACHMENTS',
  'EXHIBITS',
  'PUBLIC NOTICE',
]

/** Build a regex that matches section headers, allowing line breaks within them */
const SECTION_HEADER_PATTERN = new RegExp(
  '^(' + SECTION_HEADERS.map(h => h.replace(/\s+/g, '[:\\s]+')).join('|') + ')[:\\s]*$',
  'i'
)

/**
 * Patterns that indicate PDF page artifacts to strip:
 * - "Page N of M"
 * - "AGENDA" or "REPORT" as standalone lines (staff report header split across lines)
 * - Date-only lines like "March 24, 2026"
 * - Lines that are just whitespace
 */
const PAGE_ARTIFACT_PATTERN = /^(Page\s+\d+\s+of\s+\d+|AGENDA\s*\n?\s*REPORT|AGENDA|REPORT)$/i
const DATE_ONLY_PATTERN = /^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}$/i

/** The enrichment pipeline marker that separates clean text from PDF text */
const ENRICHMENT_MARKER = '[eSCRIBE Staff Report/Attachment Text]'

/**
 * Parse government text into structured segments.
 *
 * Handles both clean eSCRIBE text and messy PDF-extracted staff reports.
 * The enrichment marker splits the two zones.
 */
export function parseAgendaText(text: string): TextSegment[] {
  if (!text || !text.trim()) return []

  const markerIdx = text.indexOf(ENRICHMENT_MARKER)
  if (markerIdx >= 0) {
    const actionText = text.slice(0, markerIdx).trim()
    const reportText = text.slice(markerIdx + ENRICHMENT_MARKER.length).trim()

    const segments: TextSegment[] = []

    // Parse the clean recommended action text
    if (actionText) {
      segments.push(...parseCleanText(actionText))
    }

    // Parse the messy PDF staff report text
    if (reportText) {
      segments.push(...parsePdfText(reportText))
    }

    return segments
  }

  // No enrichment marker — use the original parsing logic
  return parseCleanText(text)
}

/**
 * Parse clean text (recommended action from eSCRIBE).
 * Original logic: clause detection, semicolon splitting, line-by-line.
 */
function parseCleanText(text: string): TextSegment[] {
  const rawLines = text.split(/\n+/).map(l => l.trim()).filter(Boolean)

  if (rawLines.length > 1) {
    return rawLines.flatMap(classifyLine)
  }

  // Single block — try clause boundaries
  const clauseSplit = text.split(/(?=\b(?:WHEREAS|RESOLVED|NOW,?\s*THEREFORE|BE IT FURTHER RESOLVED|BE IT RESOLVED)\b)/i)
  if (clauseSplit.length > 1) {
    return clauseSplit.map(s => s.trim()).filter(Boolean).flatMap(classifyLine)
  }

  // Try semicolons
  const semiParts = text.split(/;\s*/)
  if (semiParts.length >= 3) {
    return semiParts.map(s => s.trim()).filter(Boolean).flatMap(classifyLine)
  }

  return [{ type: 'paragraph', text: text.trim() }]
}

/**
 * Parse PDF-extracted staff report text.
 *
 * Strategy:
 * 1. Strip the metadata preamble (everything before first section header)
 * 2. Strip page artifacts (page numbers, headers, date-only lines)
 * 3. Detect section headers (FINANCIAL IMPACT, DISCUSSION, etc.)
 * 4. Rejoin lines broken at PDF column boundaries
 * 5. Detect bullet points and list items
 * 6. Produce flowing paragraphs with section structure
 */
function parsePdfText(text: string): TextSegment[] {
  // Strip the preamble: everything before the first section header is
  // PDF metadata (TO/FROM/DATE/Subject, department name, etc.)
  const strippedText = stripPreamble(text)
  const lines = strippedText.split('\n')
  const segments: TextSegment[] = []

  // First pass: clean and rejoin lines
  const cleaned = cleanAndRejoinLines(lines)

  // Second pass: classify into segments
  for (const block of cleaned) {
    if (!block.trim()) continue

    // Check for section header
    const headerMatch = block.trim().match(SECTION_HEADER_PATTERN)
    if (headerMatch) {
      segments.push({
        type: 'section-header',
        keyword: normalizeHeaderText(headerMatch[1]),
        text: '',
      })
      continue
    }

    // Check for WHEREAS/RESOLVED clause
    const clauseMatch = block.trim().match(CLAUSE_PATTERN)
    if (clauseMatch) {
      const keyword = clauseMatch[1].toUpperCase().replace(/,\s*$/, '')
      const rest = block.trim().slice(clauseMatch[0].length).trim()
      segments.push({ type: 'clause', keyword, text: rest || block.trim() })
      continue
    }

    // Check for bullet/list items
    const bulletMatch = block.trim().match(BULLET_PATTERN)
    if (bulletMatch) {
      segments.push({
        type: 'list-item',
        text: block.trim().replace(BULLET_PATTERN, '').trim(),
      })
      continue
    }

    const listMatch = block.trim().match(LIST_PATTERN)
    if (listMatch) {
      segments.push({ type: 'list-item', text: block.trim() })
      continue
    }

    // Regular paragraph
    segments.push({ type: 'paragraph', text: block.trim() })
  }

  return segments
}

/**
 * Clean PDF artifacts and rejoin lines broken at column boundaries.
 *
 * Returns an array of logical blocks (paragraphs, headers, list items).
 */
function cleanAndRejoinLines(lines: string[]): string[] {
  const blocks: string[] = []
  let currentBlock = ''

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim()

    // Skip empty lines — they indicate paragraph breaks
    if (!line) {
      if (currentBlock.trim()) {
        blocks.push(currentBlock.trim())
        currentBlock = ''
      }
      continue
    }

    // Skip page artifacts
    if (PAGE_ARTIFACT_PATTERN.test(line)) continue
    if (DATE_ONLY_PATTERN.test(line) && isLikelyPageHeader(lines, i)) continue

    // Skip metadata lines from PDF headers (TO:, FROM:, DATE:, Subject: blocks)
    // These appear at the top of staff reports and aren't useful content
    if (isPdfMetadataLine(line, lines, i)) continue

    // Check if this is a section header
    if (SECTION_HEADER_PATTERN.test(line)) {
      if (currentBlock.trim()) {
        blocks.push(currentBlock.trim())
        currentBlock = ''
      }
      blocks.push(line)
      continue
    }

    // Check for multi-line section headers (e.g., "PREVIOUS COUNCIL\nACTION:")
    if (i + 1 < lines.length) {
      const combined = (line + ' ' + lines[i + 1].trim()).replace(/\s+/g, ' ')
      if (SECTION_HEADER_PATTERN.test(combined)) {
        if (currentBlock.trim()) {
          blocks.push(currentBlock.trim())
          currentBlock = ''
        }
        blocks.push(combined)
        i++ // skip next line
        continue
      }
    }

    // Bullet/list items are their own blocks
    if (BULLET_PATTERN.test(line) || LIST_PATTERN.test(line)) {
      if (currentBlock.trim()) {
        blocks.push(currentBlock.trim())
        currentBlock = ''
      }
      // But a bullet item might continue on the next line
      let bulletText = line
      while (i + 1 < lines.length) {
        const nextLine = lines[i + 1].trim()
        if (!nextLine || BULLET_PATTERN.test(nextLine) || LIST_PATTERN.test(nextLine) ||
            SECTION_HEADER_PATTERN.test(nextLine) || PAGE_ARTIFACT_PATTERN.test(nextLine)) {
          break
        }
        // Join if it's a continuation OR the bullet text doesn't end with punctuation
        if (isContinuationLine(nextLine) || previousBlockIncomplete(bulletText)) {
          bulletText += ' ' + nextLine
          i++
        } else {
          break
        }
      }
      blocks.push(bulletText)
      continue
    }

    // Rejoin logic: join if the line is a continuation of the previous text.
    // Two signals: (a) the line itself looks like a continuation (lowercase start, etc.)
    // or (b) the previous block doesn't end with sentence-ending punctuation,
    // meaning the PDF broke a sentence across lines.
    const shouldJoin = currentBlock && (
      isContinuationLine(line) ||
      previousBlockIncomplete(currentBlock)
    )

    if (shouldJoin) {
      currentBlock += ' ' + line
    } else {
      if (currentBlock.trim()) {
        blocks.push(currentBlock.trim())
      }
      currentBlock = line
    }
  }

  if (currentBlock.trim()) {
    blocks.push(currentBlock.trim())
  }

  return blocks
}

/**
 * Determine if a line is a continuation of the previous line
 * (i.e., a mid-sentence PDF line break, not a new paragraph).
 *
 * Heuristics:
 * - Starts with lowercase letter → almost certainly a continuation
 * - Starts with a common mid-sentence word → likely continuation
 * - Previous block doesn't end with sentence-ending punctuation → likely continuation
 * - Short line (< 80 chars) that doesn't look like a header → possibly continuation
 */
function isContinuationLine(line: string): boolean {
  const trimmed = line.trim()
  if (!trimmed) return false

  // Starts with lowercase → continuation
  if (/^[a-z]/.test(trimmed)) return true

  // Starts with common continuation patterns
  if (/^(and |or |the |a |an |in |of |for |to |with |from |by |at |on |as |is |are |was |were |that |which |who |this |its |their |these |those |but |nor |yet |so |if |when |while |than |not |no |all |any |each |every |into |through |during |after |before |between |under |over |about |against |until |upon |also |however |therefore |furthermore |moreover |additionally |specifically )/i.test(trimmed)) return true

  return false
}

/**
 * Check if the current block ends mid-sentence, suggesting the next
 * line should be joined rather than starting a new paragraph.
 *
 * A block is "incomplete" if it doesn't end with sentence-ending
 * punctuation (., !, ?, :, ;) or a closing parenthesis/quote after punctuation.
 */
function previousBlockIncomplete(block: string): boolean {
  const trimmed = block.trim()
  if (!trimmed) return false

  // Ends with sentence-ending punctuation → complete
  if (/[.!?;:]["')\]]?\s*$/.test(trimmed)) return false

  // Ends with a closing parenthesis (could be complete)
  if (/\)\s*$/.test(trimmed)) return false

  // Otherwise, the sentence was probably broken by PDF column width
  return true
}

/**
 * Check if a date line is likely a page header rather than content.
 * Page headers typically appear near "Page N of M" lines.
 */
function isLikelyPageHeader(lines: string[], idx: number): boolean {
  // Check nearby lines for page artifacts
  for (let j = Math.max(0, idx - 3); j <= Math.min(lines.length - 1, idx + 3); j++) {
    if (j !== idx && PAGE_ARTIFACT_PATTERN.test(lines[j].trim())) return true
  }
  return false
}

/**
 * Detect PDF metadata blocks at the start of staff reports.
 * Lines like "TO:", "FROM:", "DATE:", "Subject:" with their values
 * are not useful content — the meeting/item context is already shown.
 */
function isPdfMetadataLine(line: string, lines: string[], idx: number): boolean {
  // Only strip metadata near the start of the text (first ~20 lines)
  if (idx > 25) return false

  // Department name as standalone line near the top
  if (idx < 5 && /^(Public Works|Finance|City Manager|Human Resources|Community Services|Economic Development|Planning|Police|Fire|City Attorney|City Clerk|Library)\s*$/i.test(line)) {
    return true
  }

  // TO:/FROM:/DATE:/Subject: labels (with or without inline values)
  if (/^(TO|FROM|DATE|Subject|RE)\s*:\s*/i.test(line)) return true

  // Values on the line after a label
  if (idx > 0) {
    const prev = lines[idx - 1]?.trim() || ''
    if (/^(TO|FROM|DATE|Subject|RE)\s*:/i.test(prev)) return true
    // Multi-line FROM values
    if (/^(TO|FROM)\s*:/i.test(prev) || (idx > 1 && /^(TO|FROM)\s*:/i.test(lines[idx - 2]?.trim() || ''))) {
      if (/^(Mayor|Council|City|Director|Assistant|Deputy|Manager|Chief)/i.test(line)) return true
    }
  }

  // "Mayor Martinez and Members of the City Council" — always metadata
  if (/^Mayor\s+\w+\s+and\s+Members/i.test(line)) return true

  return false
}

/**
 * Strip the metadata preamble from PDF staff report text.
 * Everything before the first recognized section header (FINANCIAL IMPACT,
 * STATEMENT OF THE ISSUE, etc.) is typically TO/FROM/DATE/Subject metadata
 * that duplicates information already shown in the UI.
 */
function stripPreamble(text: string): string {
  const lines = text.split('\n')

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim()

    // Check if this line is a section header
    if (SECTION_HEADER_PATTERN.test(line)) {
      return lines.slice(i).join('\n')
    }

    // Check multi-line headers
    if (i + 1 < lines.length) {
      const combined = (line + ' ' + lines[i + 1].trim()).replace(/\s+/g, ' ')
      if (SECTION_HEADER_PATTERN.test(combined)) {
        return lines.slice(i).join('\n')
      }
    }
  }

  // No section header found — return as-is (don't strip anything)
  return text
}

/** Normalize header text for display */
function normalizeHeaderText(raw: string): string {
  return raw
    .replace(/[:\s]+$/, '')
    .replace(/\s+/g, ' ')
    .trim()
    .split(' ')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ')
}

function classifyLine(line: string): TextSegment[] {
  const trimmed = line.trim()
  if (!trimmed) return []

  const clauseMatch = trimmed.match(CLAUSE_PATTERN)
  if (clauseMatch) {
    const keyword = clauseMatch[1].toUpperCase().replace(/,\s*$/, '')
    const rest = trimmed.slice(clauseMatch[0].length).trim()
    return [{ type: 'clause', keyword, text: rest || trimmed }]
  }

  const bulletMatch = trimmed.match(BULLET_PATTERN)
  if (bulletMatch) {
    return [{ type: 'list-item', text: trimmed.replace(BULLET_PATTERN, '').trim() }]
  }

  const listMatch = trimmed.match(LIST_PATTERN)
  if (listMatch) {
    return [{ type: 'list-item', text: trimmed }]
  }

  return [{ type: 'paragraph', text: trimmed }]
}

/**
 * Check if text has enough structure to warrant smart formatting.
 * Now always true for enriched text (has the marker).
 * For non-enriched text, uses the original heuristic.
 */
export function hasStructure(text: string): boolean {
  if (!text) return false

  // Enriched text always benefits from formatting
  if (text.includes(ENRICHMENT_MARKER)) return true

  const segments = parseAgendaText(text)
  return segments.some(s => s.type === 'clause' || s.type === 'list-item' || s.type === 'section-header') ||
    segments.length >= 3
}
