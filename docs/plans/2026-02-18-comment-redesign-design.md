# Comment Output Redesign — Design Document

**Date:** 2026-02-18
**Status:** Approved
**Scope:** comment_generator.py, conflict_scanner.py, COMMENT_TEMPLATE

## Problem

The current public comment output has three problems:

1. **Misleading terminology.** All findings are labeled "POTENTIAL CONFLICTS OF INTEREST" regardless of strength. A firefighter's $15/paycheck union dues and a contractor's $5,000 donation to a sitting council member who votes on their contract both get the same label and legal citation. This will confuse readers and damage credibility.

2. **Unreadable format.** The output looks like code — item numbers without names ("V.5: Fire Department"), raw confidence percentages, "Evidence:" bullet lists, empty fields. A city clerk or resident shouldn't need the agenda packet open to understand the comment.

3. **Bugs.** Empty "Recipient:" field on PAC contributions, `[email]` placeholder never filled, `(None)` displayed as employer string.

## Design Decisions

### Three-Tier Finding Classification

Findings are classified into three tiers based on the strength of the signal. The scanner detects all three tiers. The comment generator only publishes Tier 1 and Tier 2.

| Tier | Public Label | In Comment? | Criteria |
|------|-------------|-------------|----------|
| **1 — Potential Conflict of Interest** | "Potential Conflict of Interest" | Yes — primary section | Sitting council member who will vote on the item + direct donor/vendor name match + material contribution amount (≥$500) |
| **2 — Potential Financial Connection** | "Potential Financial Connection" | Yes — separate secondary section | Sitting council member but weaker match type (employer match, fuzzy), OR strong match but smaller amount (<$500) |
| **3 — Internal tracking** | *(none — not published)* | No — database only | Non-sitting recipients (former/failed candidates), union PAC payroll deductions from city employees, trivial amounts. Stored for longitudinal pattern analysis. |

#### Tier Assignment Logic

The scanner already computes a confidence score (0.0–1.0). The comment generator maps confidence to tiers:

```
confidence >= 0.6  AND  sitting_member  →  Tier 1 (Potential Conflict)
confidence >= 0.4  AND  sitting_member  →  Tier 2 (Financial Connection)
everything else                         →  Tier 3 (internal, suppressed)
```

Key conditions that push findings to Tier 3 (suppressed):
- `is_sitting_council_member()` returns False (donation went to a former/failed candidate)
- Contribution is to a union PAC from a city employee (employer = "City of Richmond" + PAC committee)
- Total aggregated contributions below $100 (already filtered by scanner)

#### Sitting Member Requirement

This is the most important filter. A donation to Oscar Garcia's failed 2022 campaign is not a conflict of interest because Oscar Garcia does not vote on city council items. The scanner already tracks `sitting` vs. non-sitting — the comment generator now uses this to suppress non-sitting findings from the public output.

### Narrative Format — "Reads Like an Investigative Report"

Each finding is a self-contained paragraph that a reader can understand without the agenda:

**Structure per finding:**
1. **Item name in plain English** — full title from agenda, not just the item number
2. **What the item is** — brief context (contract, purchase, agreement) + dollar amount
3. **What was found** — who donated, how much, to whom, when, filing reference woven into prose
4. **Why it matters** — whether the recipient is a sitting member who votes on the item
5. **Legal context** — plain English explanation of the relevant FPPC law, with Gov. Code citation
6. **Disclaimer** — "This report does not determine whether a legal conflict exists."

No raw confidence scores. No "Evidence:" bullet lists. No empty fields. The tier placement (which section it appears in) communicates the weight.

### Two Output Formats

The same finding data renders into two formats:

1. **Plain text** — submitted to `cityclerkdept@ci.richmond.ca.us` for the official meeting record. ASCII-only formatting (equals signs, dashes, indentation). This is the Phase 1 deliverable.

2. **HTML** — for subscriber email in Phase 2. Headers, bold, structured layout. Not implemented yet but the template architecture should support it cleanly (separate Jinja2 templates, same data model).

### Clean Items Section

Replace the current item-number listing with a summary count:

```
ITEMS WITH NO FINANCIAL CONNECTIONS IDENTIFIED
===============================================================

23 additional agenda items were scanned against 27,035 campaign
finance records (CAL-ACCESS and City Clerk NetFile filings,
2017-2025). No donor-vendor connections were identified.
```

### Example Output — Tier 1 (Potential Conflict)

```
POTENTIAL CONFLICTS OF INTEREST
===============================================================

1. Approve Professional Services Agreement with Maier Consulting
   for Library Renovation Design — $1,217,161
   (Agenda Item V.6.a, Library and Community Services)

   Cheryl Maier, the named contractor on this $1.2M library
   renovation agreement, donated $5,000 to Councilmember
   Sue Wilson's 2024 re-election campaign (NetFile Filing
   #211752889, January 6, 2024).

   Councilmember Wilson is a sitting member who will vote on
   this item.

   Under California's Political Reform Act (Gov. Code §87100),
   elected officials must disqualify themselves from governmental
   decisions that could financially benefit a source of income of
   $500 or more received in the prior 12 months. The FPPC defines
   "source of income" to include persons from whom the official
   received payments (2 Cal. Code Regs. §18700.3).

   This report does not determine whether a legal conflict exists.
   We disclose this connection so the public and Council can
   evaluate it independently.
```

### Example Output — Tier 2 (Financial Connection)

```
ADDITIONAL FINANCIAL CONNECTIONS
===============================================================

The following donor-vendor connections were identified in public
campaign finance records. These do not necessarily indicate
conflicts of interest but are disclosed for transparency.

1. Approve Annual Maintenance Contract with Pacific Environmental
   Services — $85,000
   (Agenda Item V.3.a, Public Works)

   James Torres, whose employer is listed as Pacific
   Environmental Services in campaign filings, donated $200 to
   Mayor Eduardo Martinez's 2022 campaign (CAL-ACCESS Filing
   #2345678, March 15, 2022).
```

### Example Output — Tier 3 (Not Published)

The following would NOT appear in the comment but would be stored for pattern tracking:

- Rico Rincon (City of Richmond employee) union dues to firefighter PAC → suppressed (city employee payroll deduction to own union)
- Cheryl Maier $100 to Shawn Dunning (failed 2024 candidate) → suppressed (non-sitting recipient)
- Cheryl Maier $100 to Oscar Garcia (failed 2022 candidate) → suppressed (non-sitting recipient)

Future: if Cheryl Maier appears in agenda items across multiple meetings AND has donated to multiple council candidates, the pattern-tracking system could surface this as a Tier 2 finding with a note: "This contractor has appeared in N agenda items over M months and has donated to K different council campaigns."

## Bug Fixes (Included in This Work)

### 1. Empty Recipient Field

**Problem:** When `extract_candidate_from_committee()` returns `None` (PAC contributions like "Independent PAC Local 188 International Association of Firefighters"), `council_member_label` stays empty, producing `Recipient: ` in the output.

**Fix:** In `conflict_scanner.py`, when `candidate` is `None`, set `council_member_label` to the committee/PAC name. Template should display "Contribution to: [PAC name]" instead of "Recipient:".

**Note:** This bug is moot for Tier 3 items (which won't appear in the comment), but should be fixed in the scanner for the internal report and database storage.

### 2. Email Placeholder

**Problem:** Template has `For questions or corrections: [email]`.

**Fix:** Replace with `For questions or corrections: pjfront@gmail.com`.

### 3. None Employer Display

**Problem:** Line 80 of current output shows "Cheryl Maier (None)" when employer is None/null.

**Fix:** In the description-building logic in `conflict_scanner.py`, filter out None, "n/a", "N/A", empty string, and "None" before adding the employer parenthetical.

## Files Changed

| File | Change |
|------|--------|
| `src/conflict_scanner.py` | Fix empty recipient bug. Fix None employer display. Add `publication_tier` field to `ConflictFlag` dataclass (1, 2, or 3). |
| `src/comment_generator.py` | New `COMMENT_TEMPLATE` with narrative format. Tier filtering logic (only publish Tier 1 + 2). Fix email placeholder. Add contribution count to clean items section. Architect for future HTML template. |
| `src/data/2026-02-17_comment.txt` | Regenerated output (for reference/testing). |
| `docs/DECISIONS.md` | Log the three-tier classification decision with rationale. |

## What This Does NOT Change

- **Scanner detection logic** — still casts a wide net, same matching algorithms
- **Confidence scoring** — same formulas, just mapped to tiers at the output layer
- **Database schema** — no schema changes (Tier 3 storage is future work)
- **CLI interface** — same flags and arguments
- **Email submission** — same SMTP path, just better content

## Future Work (Not in This PR)

- **Tier 3 database storage** — persist suppressed findings in a `scan_findings` table for longitudinal pattern analysis
- **Pattern detection** — "this contractor has appeared in N meetings" across stored findings
- **HTML template** — subscriber-facing email format (Phase 2, Path A)
- **Confidence calibration** — tune thresholds after seeing more real meetings
