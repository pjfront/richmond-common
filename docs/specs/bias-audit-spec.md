# Bias Audit Instrumentation Spec

*Created: 2026-02-18*
*Status: Draft — awaiting review before implementation*

---

## 1. Motivation

The conflict scanner matches donor names and employers against agenda item text
to flag potential conflicts of interest. The matching logic has structural
properties that can produce disparate false positive and false negative rates
across demographic groups:

- **Short-name threshold (12 chars for substring, 4 chars for entity):**
  Systematically disadvantages shorter names common in some East Asian cultures
  (Wu, Li, Kim). These donors are invisible to the scanner.
- **Common-surname false positives:** High-frequency surnames (Nguyen, Garcia,
  Martinez, Smith) produce more spurious matches against unrelated agenda text,
  over-flagging people with common names.
- **Hyphenated/compound surname handling:** Punctuation stripping turns
  "Garcia-Lopez" into "garcia lopez", which may fail to match "Garcia" or
  "Lopez" individually. Affects Hispanic and married women's names
  disproportionately.
- **Diacritics loss:** Source data inconsistency (CAL-ACCESS TSV vs. NetFile
  JSON vs. PDF extraction) can strip diacritics, causing "Nguyen" != "Nguyễn".
- **Western business-name regex:** `extract_entity_names()` assumes
  English-language corporate suffixes and capitalization patterns.

These are not hypothetical — Richmond is majority Latino with significant Black,
Asian, and Pacific Islander communities. The scanner's output becomes public
comment. Disproportionate flagging rates are both a fairness problem and a
credibility problem.

### Design principle

Separate collection from evaluation. We don't have enough matched decisions yet
to detect bias statistically, but we can instrument now so the analysis is
straightforward later. The work now is logging; the audit comes after we
accumulate ~100+ ground-truthed decisions.

---

## 2. What Gets Logged

### 2.1 Decision-level: `matching_decisions` table

Log one row for every match that **passes initial filtering** — i.e., every
`VendorDonorMatch` or `ConflictFlag` produced by `scan_meeting_json()` or
`scan_meeting_db()`. Do NOT log the millions of non-matching comparisons.

Also log significant **near-misses**: matches that were suppressed by the
council-member-name filter, government-employer filter, or government-donor
filter. These are important for bias analysis because the filters themselves
may have demographic skew.

```sql
CREATE TABLE matching_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    meeting_id UUID REFERENCES meetings(id),
    scan_run_id UUID NOT NULL,  -- groups all decisions from one scan

    -- What was compared
    model_type VARCHAR(30) NOT NULL CHECK (model_type IN (
        'name_resolution', 'conflict_detection', 'entity_extraction', 'speaker_id'
    )),
    input_donor_name VARCHAR(300) NOT NULL,
    input_donor_employer VARCHAR(300),
    input_agenda_text_preview VARCHAR(500),  -- first 500 chars of item text
    agenda_item_number VARCHAR(20),

    -- Match result
    match_type VARCHAR(30) NOT NULL,  -- 'exact', 'contains', 'employer_match', 'suppressed_council_member', 'suppressed_govt_employer', 'suppressed_govt_donor'
    confidence FLOAT NOT NULL,
    matched BOOLEAN NOT NULL,  -- TRUE = flag produced, FALSE = suppressed

    -- Structural risk signals (computed at write time)
    donor_name_has_compound_surname BOOLEAN NOT NULL DEFAULT FALSE,
    donor_name_has_diacritics BOOLEAN NOT NULL DEFAULT FALSE,
    donor_name_token_count SMALLINT NOT NULL,
    donor_name_char_count SMALLINT NOT NULL,
    donor_surname_frequency_tier SMALLINT,  -- 1=top-100, 2=top-1000, 3=top-10000, 4=rare, NULL=unknown

    -- Ground truth (populated during manual review)
    ground_truth BOOLEAN,           -- TRUE=correct match, FALSE=false positive, NULL=unreviewed
    ground_truth_source VARCHAR(50), -- 'manual_review', 'certified_minutes', etc.
    reviewed_at TIMESTAMPTZ,
    audit_notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_matching_city ON matching_decisions(city_fips);
CREATE INDEX idx_matching_scan_run ON matching_decisions(scan_run_id);
CREATE INDEX idx_matching_unreviewed ON matching_decisions(city_fips)
    WHERE ground_truth IS NULL;
CREATE INDEX idx_matching_surname_tier ON matching_decisions(donor_surname_frequency_tier);
```

### 2.2 Aggregate-level: `scan_audit_summary` table

One row per scan run. Captures filter-stage statistics without logging every
non-matching comparison.

```sql
CREATE TABLE scan_audit_summary (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    scan_run_id UUID NOT NULL UNIQUE,
    meeting_id UUID REFERENCES meetings(id),
    meeting_date DATE,

    -- Volume
    total_agenda_items INTEGER NOT NULL,
    total_contributions_compared INTEGER NOT NULL,
    total_comparisons INTEGER NOT NULL,  -- items x contributions

    -- Filter funnel (how many comparisons were eliminated at each stage)
    filtered_no_text_match INTEGER NOT NULL DEFAULT 0,
    filtered_short_name INTEGER NOT NULL DEFAULT 0,       -- below 12-char threshold
    filtered_council_member INTEGER NOT NULL DEFAULT 0,   -- donor is a council member
    filtered_govt_employer INTEGER NOT NULL DEFAULT 0,    -- generic government employer
    filtered_govt_donor INTEGER NOT NULL DEFAULT 0,       -- government entity as donor name
    filtered_dedup INTEGER NOT NULL DEFAULT 0,            -- duplicate filing records
    passed_to_flag INTEGER NOT NULL DEFAULT 0,            -- became a ConflictFlag
    suppressed_near_miss INTEGER NOT NULL DEFAULT 0,      -- passed text match but hit a filter

    -- Surname frequency distribution of ALL donors compared (not just matches)
    -- Lets us check: "are top-100 surnames over-represented in flags vs. input?"
    donors_surname_tier_1 INTEGER NOT NULL DEFAULT 0,  -- top 100
    donors_surname_tier_2 INTEGER NOT NULL DEFAULT 0,  -- top 1000
    donors_surname_tier_3 INTEGER NOT NULL DEFAULT 0,  -- top 10000
    donors_surname_tier_4 INTEGER NOT NULL DEFAULT 0,  -- rare
    donors_surname_unknown INTEGER NOT NULL DEFAULT 0, -- not in census data

    -- Same breakdown but only for donors that produced flags
    flagged_surname_tier_1 INTEGER NOT NULL DEFAULT 0,
    flagged_surname_tier_2 INTEGER NOT NULL DEFAULT 0,
    flagged_surname_tier_3 INTEGER NOT NULL DEFAULT 0,
    flagged_surname_tier_4 INTEGER NOT NULL DEFAULT 0,
    flagged_surname_unknown INTEGER NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_scan_audit_city ON scan_audit_summary(city_fips);
```

---

## 3. Structural Risk Signals

Computed at match-decision write time. These are properties of **strings**, not
demographic inference about people. The distinction matters ethically and
practically.

### 3.1 `compute_bias_risk_signals(name: str) -> dict`

```python
import string
import unicodedata

def compute_bias_risk_signals(name: str) -> dict:
    """
    Structural string properties that correlate with known matching
    failure modes. NOT demographic inference.

    Returns:
        dict with keys:
            has_compound_surname: bool  -- hyphenated or >3 tokens
            has_diacritics: bool        -- non-ASCII letters present
            token_count: int            -- number of space-separated tokens
            char_count: int             -- total characters
            surname_frequency_tier: int|None  -- 1-4 from census data
    """
    tokens = name.strip().split()
    has_compound = "-" in name or len(tokens) > 3

    has_diacritics = False
    for c in name:
        if c.isalpha() and c not in string.ascii_letters:
            has_diacritics = True
            break

    surname = tokens[-1] if tokens else ""
    tier = lookup_surname_frequency_tier(surname)

    return {
        "has_compound_surname": has_compound,
        "has_diacritics": has_diacritics,
        "token_count": len(tokens),
        "char_count": len(name),
        "surname_frequency_tier": tier,
    }
```

### 3.2 Surname frequency tiers

**Data source:** US Census Bureau 2010 Surnames file
(`Names_2010Census.csv`), available at
`https://www2.census.gov/topics/genealogy/2010surnames/names.zip`.

Contains ~162,000 surnames with frequency counts and race/ethnicity
distribution. We use ONLY the frequency rank, not the race/ethnicity columns.

| Tier | Rank Range | Example Surnames | Count in File |
|------|-----------|-----------------|---------------|
| 1 | 1-100 | Smith, Johnson, Garcia, Nguyen | 100 |
| 2 | 101-1,000 | Reeves, Barton, Maier | ~900 |
| 3 | 1,001-10,000 | Lipscomb, Turek | ~9,000 |
| 4 | 10,001+ | (rare) | ~152,000 |

```python
# Loaded once at module import from data/census/surname_freq.json
# Pre-processed from Names_2010Census.csv to {normalized_surname: tier}
SURNAME_FREQ: dict[str, int] = {}

def lookup_surname_frequency_tier(surname: str) -> int | None:
    """Look up surname frequency tier from Census 2010 data.
    Returns 1-4 or None if surname not found."""
    normalized = surname.lower().strip()
    return SURNAME_FREQ.get(normalized)
```

**Pre-processing step:** Download Census file, extract surname + rank, compute
tier, save as `data/census/surname_freq.json` (~2MB). This is a one-time setup
step.

---

## 4. Confidence Thresholds (Pre-Registered)

Set BEFORE seeing bias audit results. Changing these after seeing results
requires a DECISIONS.md entry explaining why.

```python
MATCHING_THRESHOLDS = {
    "conflict_detection": {
        # High bar — output becomes public comment with reputational impact
        "auto_accept": 0.85,   # include in public comment without manual review
        "human_review": 0.50,  # flag for Phillip's review before inclusion
        "reject": 0.49,        # do not include in output
    },
    "name_resolution": {
        # Lower stakes — internal entity resolution
        "auto_accept": 0.90,
        "human_review": 0.70,
        "reject": 0.69,
    },
}
```

### Current effective thresholds in `conflict_scanner.py`

For reference, these are the implicit thresholds in the existing code:

- Exact name match: confidence 0.7 base (+ 0.1 if amount >= $1K, + 0.1 if >= $5K)
- Contains/substring match: confidence 0.5 base (same bonuses)
- Employer match: confidence 0.5 base (same bonuses)
- Form 700 real property: confidence 0.4 (fixed)
- Form 700 income/investment: confidence 0.5 (fixed)

The comment generator currently includes ALL flags in the output regardless of
confidence. The thresholds above formalize the review process: flags below
`human_review` are excluded from public comment, flags between `human_review`
and `auto_accept` require Phillip's manual review.

---

## 5. Ground Truth Strategy

### 5.1 Primary source: manual flag review

Every time the pipeline generates flags for a meeting, Phillip reviews each flag
and records a verdict:

- **TRUE** — this is a genuine donor/vendor/interest match (correct flag)
- **FALSE** — this is a false positive (wrong entity, coincidental name match)

This happens naturally as part of the public comment review workflow. The
`ground_truth` column in `matching_decisions` gets populated during this review.

### 5.2 Secondary source: council member entity list

Seed from the 21 already-extracted meetings. Known council members with verified
name variants:

```python
GROUND_TRUTH_OFFICIALS = [
    {
        "canonical": "Eduardo Martinez",
        "variants": ["Mayor Martinez", "E. Martinez", "Eduardo A. Martinez"],
        "city_fips": "0660620",
        "role": "mayor",
    },
    {
        "canonical": "Tom Butt",
        "variants": ["Councilmember Butt", "T. Butt", "Thomas Butt"],
        "city_fips": "0660620",
        "role": "councilmember",
    },
    # ... all 7 current + notable former members
]
```

This validates name RESOLUTION (variant -> canonical), but not conflict
DETECTION (donor -> agenda item). The primary source above covers detection.

### 5.3 Review workflow (how ground truth gets recorded)

Phase 1 volume is ~1-10 flags per meeting, reviewed by one person (Phillip).
The workflow must be dead simple — no web UI, no separate tool. Two modes:

#### Mode A: Interactive CLI review (primary)

The conflict scanner's CLI gets a `--review` flag. After printing each flag,
it prompts for a verdict:

```
  [1] Item C.3: Contract with Acme Environmental Services
      Type: campaign_contribution
      Confidence: 0.70
      Cheryl Maier (Acme Environmental) contributed $250.00 to
      Richmond Progressive Alliance on 2023-04-15

      Verdict? [T]rue match / [F]alse positive / [S]kip / [N]otes: _
```

- **T** — writes `ground_truth = TRUE` to `matching_decisions`
- **F** — writes `ground_truth = FALSE` to `matching_decisions`
- **S** — leaves `ground_truth = NULL` (come back later)
- **N** — prompts for free-text note, then re-prompts for T/F/S

This runs after the scan, not during. The scan produces flags as normal; the
review pass iterates over the `matching_decisions` rows for that `scan_run_id`
and updates them in place.

CLI usage:
```bash
# Scan first (produces flags + logs matching_decisions)
python conflict_scanner.py meeting.json --contributions combined.json

# Review after (updates ground_truth on existing rows)
python conflict_scanner.py --review --scan-run <scan_run_id>

# Or review the most recent scan run
python conflict_scanner.py --review --latest
```

#### Mode B: JSON sidecar file (pre-database fallback)

Before the database is running, verdicts are written to a JSON sidecar file
alongside the scan output:

```json
// meeting_2026-02-17_review.json
{
  "scan_run_id": "a1b2c3d4-...",
  "reviewed_by": "phillip",
  "reviewed_at": "2026-02-18T10:30:00Z",
  "verdicts": [
    {
      "flag_index": 0,
      "donor_name": "Cheryl Maier",
      "agenda_item": "C.3",
      "ground_truth": true,
      "notes": "Confirmed — same person, employer matches contract vendor"
    },
    {
      "flag_index": 1,
      "donor_name": "Garcia Construction LLC",
      "agenda_item": "C.7",
      "ground_truth": false,
      "notes": "Different Garcia — donor is residential, this is commercial"
    }
  ]
}
```

When the database comes online, these sidecar files can be bulk-loaded into
`matching_decisions` via a one-time migration script.

#### Review guidelines

When deciding T/F, the reviewer should ask:

1. **Is this the same entity?** Does the donor name/employer refer to the same
   person or organization mentioned in the agenda item? Not just a name
   collision.
2. **Would a reasonable reader consider this a potential conflict?** The
   standard is not legal certainty — it's whether the financial relationship
   is relevant to disclose.
3. **When uncertain, mark TRUE with a note.** False negatives (missing real
   conflicts) are worse than false positives (flagging coincidences) for a
   transparency tool. The public comment already includes confidence levels
   and disclaimers.

Expected time: ~30 seconds per flag, ~5-10 minutes per meeting.

### 5.4 What this does NOT cover

- Speaker identification (no audio pipeline yet — future work)
- Entity extraction precision (which entities `extract_entity_names()` finds
  vs. misses — would need manually annotated agenda items)
- Cross-city generalization (only measurable at Phase 2+ scale)

---

## 6. Audit Process

### 6.1 Per-meeting review (Phase 1 — current)

After every scan run:
1. Run `--review --latest` to verdict each flag (see section 5.3)
2. Eyeball the `scan_audit_summary` for anomalies:
   - Is `filtered_short_name` growing? How many real donors are we missing?
   - Is `flagged_surname_tier_1` disproportionate to `donors_surname_tier_1`?
     (Are common surnames over-represented in flags?)

### 6.2 Periodic bias audit (after 100+ ground-truthed decisions)

At approximately 100 ground-truthed decisions, run the bias audit query:

```python
def bias_audit(conn, city_fips: str) -> dict:
    """
    Compare false positive and false negative rates across structural
    name properties. Requires ground_truth populated on a sample.

    Returns dict with:
        - overall_precision: float
        - overall_recall: float (if false negatives are measurable)
        - breakdown_by_compound_surname: {True: {tp, fp, fn}, False: {...}}
        - breakdown_by_diacritics: same
        - breakdown_by_surname_tier: {1: {...}, 2: {...}, 3: {...}, 4: {...}}
        - breakdown_by_name_length_bucket: {"short_1_5": {...}, "medium_6_12": {...}, "long_13+": {...}}
        - filter_stage_demographics: {stage: {tier: count}}
    """
```

Specific questions this answers:
- Do compound surnames have a higher false negative rate? (hyphenation bug)
- Do tier-1 (common) surnames have a higher false positive rate? (over-matching)
- Do short names (<12 chars) have a higher false negative rate? (threshold bug)
- Are names with diacritics systematically missing from matches? (encoding bug)

### 6.3 Audit trigger

Run the periodic audit when ANY of:
- 100+ ground-truthed decisions accumulated
- A new city is onboarded (compare cross-city rates)
- The matching logic in `conflict_scanner.py` changes (regression check)
- Annually, regardless of volume

### 6.4 Response protocol

If the audit reveals disparate rates (>2x difference in false positive or false
negative rate between any two demographic groups):

1. Log the finding in `docs/DECISIONS.md`
2. Investigate root cause (threshold? filter? data encoding?)
3. Fix the root cause (prefer fixing the matching logic over adding demographic
   adjustments)
4. Re-run audit to confirm the fix
5. Do NOT tune thresholds to equalize rates without understanding why they differ

---

## 7. Implementation Plan

### Step 1: Census surname data setup
- Download `Names_2010Census.csv`
- Pre-process to `data/census/surname_freq.json`: `{surname: tier}`
- Write `src/surname_lookup.py` with `lookup_surname_frequency_tier()`

### Step 2: Schema additions
- Add `matching_decisions` and `scan_audit_summary` tables to `src/schema.sql`
- Include `city_fips` on both (non-negotiable)

### Step 3: Instrumentation in `conflict_scanner.py`
- Add `compute_bias_risk_signals()` function
- In `scan_meeting_json()`: generate a `scan_run_id`, count filter-stage stats,
  log each flag AND each suppressed near-miss to `matching_decisions`,
  write `scan_audit_summary` at end of scan
- Return the `scan_run_id` in `ScanResult` (add field)
- Keep the scanner's core logic unchanged — instrumentation is additive

### Step 4: Ground truth review CLI
- Add `--review` flag to `conflict_scanner.py` CLI
- `--review --scan-run <id>` reviews a specific scan run
- `--review --latest` reviews the most recent scan run
- Interactive prompt per flag: `[T]rue / [F]alse positive / [S]kip / [N]otes`
- Writes verdicts to `matching_decisions.ground_truth` (DB mode) or to a
  JSON sidecar file (pre-database mode, bulk-loadable later)
- See section 5.3 for full workflow specification

### Step 5: Audit query module
- `src/bias_audit.py` with `bias_audit(conn, city_fips)` function
- CLI: `python bias_audit.py --city-fips 0660620`
- Output: plain text report + optional JSON for programmatic use

### Step 6: Documentation
- `docs/DECISIONS.md` entry
- Reference this spec from `CLAUDE.md` Phase 1 "Done" section when implemented

---

## 8. What This Spec Does NOT Cover

- **ASR/transcription bias** — not yet applicable (no audio pipeline). When
  audio is added, WER must be measured by speaker demographics. Note this in
  the spec for the transcription pipeline.
- **LLM extraction bias** — whether Claude's entity extraction from PDFs has
  demographic skew. Would require annotated ground truth for extraction (not
  just matching). Future work.
- **Demographic inference** — we deliberately avoid inferring race/ethnicity of
  donors. The audit uses structural string properties and Census surname
  frequency as proxies. If a direct demographic audit is ever needed, it would
  use the Census surname file's race/ethnicity probability columns with
  appropriate statistical methods (BISG — Bayesian Improved Surname
  Geocoding), but that's a Phase 3+ concern.

---

## 9. File Locations

| Artifact | Path |
|----------|------|
| This spec | `docs/specs/bias-audit-spec.md` |
| Schema additions | `src/schema.sql` (append) |
| Surname lookup | `src/surname_lookup.py` |
| Bias risk signals | `src/bias_signals.py` |
| Audit queries | `src/bias_audit.py` |
| Census data (raw) | `data/census/Names_2010Census.csv` |
| Census data (processed) | `data/census/surname_freq.json` |
| Ground truth officials | `src/ground_truth/officials.json` |
