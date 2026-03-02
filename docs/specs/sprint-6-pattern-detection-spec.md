# Sprint 6: Pattern Detection — Spec

> Cross-referencing that finds what single-meeting analysis can't see.

**Phase:** 2 (Beta)
**Dependencies:** S2.1 (vote categorization), S5 (financial intelligence) — both complete.
**Execution order:** S6.3 → S6.1 → S6.2

---

## Terminology

These terms are used throughout the sprint for neutral, factual framing:

| Term | Meaning | Usage |
|------|---------|-------|
| **Voting bloc** | Members who frequently vote together | Group label when alignment is high |
| **Aligned** | High agreement percentage on a category | Factual characterization of a pair |
| **Divergent** | Low agreement percentage on a category | Opposite of aligned, no conflict implied |
| **Split** | Consistently opposite votes on a category | Describes the voting pattern, not the relationship |

These terms apply in all public-facing output. No ideology labels, no "progressive vs. business-aligned" framing, no value judgments on voting patterns.

---

## S6.3 — Council Time-Spent Stats v1

**Paths:** A, B, C
**Publication tier:** Public (factual statistics).
**Why first:** Simplest of the three. Pure SQL aggregation. Builds the query patterns S6.1 reuses.

### What it answers

- What topics does the council spend its time on?
- Which categories generate the most split votes?
- Which items draw the most public comment?
- How controversial is each policy area?

### Data sources (all available now)

| Data | Source | Status |
|------|--------|--------|
| Category per agenda item | `agenda_items.category` | Populated (S2.1) |
| Vote tallies | `motions.vote_tally` + `motions.result` | Populated |
| Individual votes | `votes.vote_choice` | Populated |
| Public comment count | `public_comments` table, JOIN on `agenda_item_id` | Derivable from existing data |
| Discussion duration | Minutes PDFs | **Not available** — requires video transcription (B.8). NULL for v1. |

### Controversy score formula

Composite 0-10 score per agenda item:

```
controversy_score = (
    split_vote_weight * 6.0     # 0-6 points from vote closeness
  + comment_weight * 3.0        # 0-3 points from public comment volume
  + multiple_motions_weight * 1.0  # 0-1 point for procedural complexity
)
```

**Split vote weight (0.0 to 1.0):**
- 7-0: 0.0 (unanimous)
- 6-1: 0.17
- 5-2: 0.43
- 4-3: 0.71
- 3-4 (failed): 1.0

Formula: `1 - abs(ayes - nays) / total_votes` where total_votes = ayes + nays (excluding abstain/absent).

Consent calendar items that were NOT pulled for separate vote: controversy_score = 0.

**Comment weight (0.0 to 1.0):**
Normalized against the meeting's most-commented item. If item X has 8 comments and the meeting max is 10, weight = 0.8.

**Multiple motions weight (0 or 1):**
1 if the item had more than one motion (substitute motions, reconsiderations, friendly amendments). 0 otherwise.

### Aggregation levels

1. **Council-wide by category** — primary view. For each of the 14 categories: total items, total votes, split vote count, average controversy score, total public comments.
2. **Per-meeting breakdown** — secondary view. Same stats scoped to a single meeting.
3. **Time series** — category distribution by quarter/year. How the council's agenda composition shifts over time.

### Schema changes

**Migration 011:** Add two nullable columns to `agenda_items`.

```sql
ALTER TABLE agenda_items ADD COLUMN IF NOT EXISTS
    discussion_duration_minutes INTEGER;
-- Populated from video transcription (B.8). NULL until then.

ALTER TABLE agenda_items ADD COLUMN IF NOT EXISTS
    public_comment_count INTEGER;
-- Materialized from public_comments JOIN. NULL = not yet computed.
```

`public_comment_count` is optional materialization. v1 computes it at query time via JOIN. The column exists for future denormalization if performance requires it.

### TypeScript types

```typescript
interface CategoryStats {
  category: string
  item_count: number
  vote_count: number
  split_vote_count: number
  unanimous_vote_count: number
  avg_controversy_score: number
  max_controversy_score: number
  total_public_comments: number
  percentage_of_agenda: number
}

interface ControversyItem {
  agenda_item_id: string
  meeting_date: string
  item_number: string
  title: string
  category: string
  controversy_score: number
  vote_tally: string
  result: string
  public_comment_count: number
  motion_count: number
}
```

### Frontend

**New page:** `/council/stats` (or section on existing council page).

Components:
- **`CategoryStatsTable`** — TanStack Table. Columns: category, item count, % of agenda, split votes, avg controversy, public comments. Sortable on all columns.
- **`ControversyLeaderboard`** — Top 10 most controversial items across all meetings. Click to navigate to meeting detail.
- **`CategoryTrendChart`** — Optional. Category distribution over time (quarters). Shows if the council's focus areas are shifting.

### Acceptance criteria

- [ ] Category distribution shows all 14 categories with correct counts
- [ ] Controversy score formula produces sensible results (consent calendar = 0, 4-3 votes rank highest)
- [ ] Public comment counts match manual spot-check of 3 meetings
- [ ] Table sorts correctly on all columns
- [ ] Time series shows quarterly breakdown (if implemented in v1)
- [ ] Page loads in < 2s

---

## S6.1 — Coalition/Voting Pattern Analysis

**Paths:** A, B, C
**Publication tier:** Graduated (politically sensitive framing). Operator-only until framing validated.
**Why second:** Highest "wow" factor. Builds on the same query patterns as S6.3.

### What it answers

- Which council members vote together most often?
- On which topics do voting blocs form?
- On which topics do aligned members diverge?
- How have alignment patterns shifted over time?

### Analysis approach

**Pairwise alignment matrix.** For every pair of council members (21 pairs from 7 members), compute:

```
agreement_rate = votes_same_direction / total_shared_votes
```

Where:
- `votes_same_direction` = both voted aye OR both voted nay
- `total_shared_votes` = motions where both cast a substantive vote (exclude absent/abstain)
- Minimum threshold: at least 5 shared votes to show a percentage (below that, show "insufficient data")

### Three views

**1. Overall alignment matrix**
- 7x7 grid (or triangular since A-B = B-A)
- Cell value = agreement percentage
- Color scale: high agreement (green) → low agreement (red)
- Click cell to drill into the pair's voting history

**2. Category alignment**
- Same matrix, filtered by category
- Dropdown to select category (or show all as small multiples)
- This is where real patterns emerge: "aligned on everything except housing"

**3. Category divergence highlights**
- For each pair, surface the categories where they diverge most
- "Martinez and Butt: 92% aligned overall, but only 45% aligned on zoning"
- Sorted by divergence gap (overall alignment minus category alignment)

### Blocs

A **voting bloc** is a group of 3+ members who are mutually aligned above a threshold. Not just A-B and B-C, but A-B and A-C and B-C all above threshold.

Suggested thresholds (operator-configurable):
- **Strong bloc:** 85%+ mutual agreement
- **Moderate bloc:** 70-84% mutual agreement
- **Divergent pair:** below 50% agreement

Bloc detection is a clique-finding problem on the alignment graph. For 7 members this is trivial (max 35 pairs to check).

### Time dimension

Alignment by time period:
- **Annual:** alignment percentage per year
- **Rolling window:** 6-month rolling average to smooth meeting-to-meeting variance
- Shows if blocs are forming, strengthening, or dissolving

### TypeScript types

```typescript
interface PairwiseAlignment {
  official_a_id: string
  official_a_name: string
  official_b_id: string
  official_b_name: string
  category: string | null       // null = overall
  agreement_count: number
  disagreement_count: number
  total_shared_votes: number
  agreement_rate: number         // 0.0 to 1.0
}

interface VotingBloc {
  members: Array<{ id: string; name: string }>
  category: string | null
  avg_mutual_agreement: number
  bloc_strength: 'strong' | 'moderate'
}

interface AlignmentShift {
  official_a_id: string
  official_b_id: string
  period: string                 // e.g., "2024-Q1"
  agreement_rate: number
  shared_vote_count: number
}
```

### Frontend

**New page:** `/council/coalitions` (operator-gated for Graduated tier).

Components:
- **`AlignmentMatrix`** — Heatmap grid. Rows and columns are council members. Cell = agreement %. Color-coded. Click to drill.
- **`AlignmentDetail`** — For a selected pair: list of shared votes, grouped by agreement/disagreement. Filter by category.
- **`BlocSummary`** — Detected blocs with members, strength, and category context.
- **`AlignmentTimeline`** — Line chart of a pair's agreement rate over time. Overlay key events (elections, new members).

### Framing guardrails

- No ideology labels ("progressive," "conservative," "business-friendly")
- No motive inference ("they vote together because...")
- No "should" language
- Present alignment as a factual pattern: "voted the same direction on X% of [category] items"
- Always show the data behind the number (click to see actual votes)
- Transparency disclaimer: "Alignment percentages reflect recorded votes only. Absent or abstaining members are excluded from the calculation."

### Acceptance criteria

- [ ] Alignment matrix shows correct percentages (spot-check 3 pairs manually)
- [ ] Category filter changes the matrix values
- [ ] Divergence highlights correctly identify categories where aligned pairs disagree
- [ ] Bloc detection finds groups of 3+ mutually aligned members
- [ ] Insufficient data shown when pair has < 5 shared votes
- [ ] Drill-through shows actual vote records
- [ ] No ideology labels or motive inference anywhere in the UI
- [ ] Operator gate enforced (not visible to public)

---

## S6.2 — Cross-Meeting Pattern Detection

**Paths:** A, B, C
**Publication tier:** Graduated. Most sensitive of the three. Correlations between money and votes require careful framing.
**Why third:** Most complex. Crosses two data domains (financial + legislative). Benefits from the query infrastructure built in S6.3 and S6.1.

### What it answers

- Do the same donors appear repeatedly in connection with specific policy areas?
- Are contribution patterns temporally correlated with agenda items?
- Which donors are category-concentrated (all their recipients vote on similar issues)?

### Pattern types

**Pattern 1: Recurring Donor-Category Correlation**
"Donor X contributed to 3 council members. All 3 voted on infrastructure items in the next 6 months."

Query: For each donor, get the categories of agenda items where their recipients cast votes. Measure category concentration.

```
donor_category_concentration = max_category_count / total_vote_count
```

A donor whose recipients only vote on infrastructure has concentration = 1.0. A donor whose recipients vote across all categories has concentration ≈ 0.07 (1/14).

Flag donors with concentration > 0.3 AND total contributions > $1,000.

**Pattern 2: Temporal Contribution-Vote Proximity**
"Donor Y contributed $5,000 on March 1. A contract benefiting Donor Y's employer appeared on the March 15 agenda."

This is the most sensitive pattern type. Requirements:
- Temporal window: contribution within 90 days before an agenda item involving the donor's employer or industry
- Matching: donor employer name fuzzy-matched against agenda item title/description
- Confidence scoring: exact employer match = high, industry match = medium, no match = excluded
- **Never imply causation.** Framing: "This contribution and this agenda item occurred within [N] days of each other."

**Pattern 3: Cross-Official Donor Overlap**
"Donor Z contributed to 4 of 7 council members in 2024."

Query: Donors who contribute to multiple officials. Sorted by breadth (recipient count) and depth (total amount).

This overlaps with existing donor analysis (S5.2) but adds the cross-meeting dimension: did the shared donors' recipients vote the same way on issues related to the donor's industry?

### Data model

No new tables. Patterns are computed at query time from existing data:
- `contributions` + `donors` (who gave what, when)
- `committees` (links contributions to officials)
- `agenda_items` + `motions` + `votes` (what was voted on, when, by whom)
- `donor_pattern_badges` (S5.2 enrichment: grassroots, targeted, mega, pac)

### TypeScript types

```typescript
interface DonorCategoryPattern {
  donor_id: string
  donor_name: string
  donor_pattern: string | null     // from S5.2
  total_contributed: number
  recipient_count: number
  top_category: string
  category_concentration: number   // 0.0 to 1.0
  category_breakdown: Array<{ category: string; vote_count: number }>
}

interface TemporalCorrelation {
  donor_id: string
  donor_name: string
  donor_employer: string | null
  contribution_date: string
  contribution_amount: number
  recipient_official_id: string
  recipient_name: string
  agenda_item_id: string
  agenda_item_title: string
  agenda_item_category: string
  meeting_date: string
  days_apart: number
  match_type: 'employer_exact' | 'employer_fuzzy' | 'industry'
  confidence: number               // 0.0 to 1.0
}

interface DonorOverlap {
  donor_id: string
  donor_name: string
  total_contributed: number
  recipients: Array<{
    official_id: string
    official_name: string
    amount: number
    contribution_count: number
  }>
  shared_vote_categories: string[]
}
```

### Frontend

**New page:** `/patterns` (operator-gated for Graduated tier).

Components:
- **`DonorCategoryTable`** — TanStack Table of donors sorted by category concentration. Click to expand category breakdown.
- **`TemporalCorrelationTimeline`** — For a selected donor: timeline showing contributions (dots) and related agenda items (bars). Visual proximity = temporal proximity.
- **`DonorOverlapMatrix`** — Which donors contribute to which officials. Small multiples or connected dot plot.

### Framing guardrails (strongest of the three items)

- **Never imply causation.** "These events occurred within [N] days" not "this contribution led to this vote."
- **Always show the full context.** If a donor contributed to 4 members, show the 3 who didn't receive contributions too.
- **Disclose the methodology.** "Temporal proximity does not imply influence. Contributions and agenda items are matched by date and employer name."
- **Confidence scores visible.** Every pattern shows its confidence level. Users can filter by confidence.
- **Suppress low-confidence patterns from default view.** Show only high-confidence (>0.7) by default. "Show all" toggle for lower confidence.

### Acceptance criteria

- [ ] Donor-category concentration correctly identifies category-focused donors
- [ ] Temporal correlation window is configurable (default 90 days)
- [ ] Employer matching uses fuzzy match with confidence scoring
- [ ] No causation language anywhere in the UI
- [ ] Methodology disclosure present on the page
- [ ] Confidence filter works (default high-confidence only)
- [ ] Cross-official overlap matches manual spot-check
- [ ] Operator gate enforced

---

## Implementation Sequence

### Step 1: Schema + Migration (S6.3 foundation)
- Migration 011: add `discussion_duration_minutes` (nullable, stays NULL) and `public_comment_count` (nullable, optional materialization) to `agenda_items`
- Add TypeScript types for all three items

### Step 2: S6.3 Query Layer + Frontend
- Supabase queries for category stats, controversy scoring, leaderboard
- `/council/stats` page with `CategoryStatsTable` and `ControversyLeaderboard`
- Publication: Public

### Step 3: S6.1 Query Layer + Frontend
- Pairwise alignment computation (SQL or application-level)
- Bloc detection algorithm
- `/council/coalitions` page with `AlignmentMatrix`, `BlocSummary`
- Publication: Graduated (operator-gated)

### Step 4: S6.2 Query Layer + Frontend
- Donor-category concentration queries
- Temporal correlation matching
- `/patterns` page with pattern tables and timeline
- Publication: Graduated (operator-gated)

### Step 5: Validation + Documentation
- Spot-check all pattern outputs against known voting records
- Document controversy score formula in methodology page
- Update PARKING-LOT.md to mark S6 items complete
- Log decisions in DECISIONS.md

---

## Upgrade paths (parked)

| Upgrade | Trigger | Notes |
|---------|---------|-------|
| Discussion duration from video | B.8 (video transcription) | Populates `discussion_duration_minutes`, improves controversy score |
| Historical context in coalitions | H.16 (vote explainer Option C) | "This is the 4th time this pair has diverged on housing" |
| Stance timeline | B.25 (position ledger) | Track individual positions over time, not just pairwise alignment |
| Commission coalition analysis | B.36 (commission meetings) | Extend alignment matrix to commission votes |
