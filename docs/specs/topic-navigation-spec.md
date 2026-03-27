# Topic Navigation Layer — Spec Draft

**Status:** Proposal from Chat — needs Claude Code review against existing schema  
**Date:** 2026-03-21  
**Origin:** Chat conversation about adding topic-centric navigation  
**Path Score:** A+B+C (all three paths served)

---

## Problem Statement

Richmond Commons currently offers person-centric and meeting-centric views. There's no way to ask "show me everything about Point Molate" or "which policy areas have the most financial connections?" A topic-centric navigation layer would let users browse civic activity by subject area, see financial connections organized around policy themes, and discover which topics attract the most money and attention.

This feature serves all four user types: journalists get a "where to look" signal, citizens get a browsable subject directory, researchers get topic-level citation targets, and officials can see the full record on issues they work on.

## What We Think We Know (Check This)

S14 Phase A built a topic board with controversy scoring and hero items. This spec assumes:
- There's already a topic taxonomy or classification system tagging agenda items
- There's already some topic model in the database

**Claude Code: Before building anything, please verify:**
1. What does the current topic data model look like? What table(s), what fields?
2. How are topics assigned to agenda items currently — LLM extraction, manual, keyword matching?
3. Is there a controlled vocabulary, or are topics free-form / emergent?
4. Do topics have stable IDs suitable for persistent URLs?
5. Does the conflict scanner already carry contributor type data (corporate/union/individual/etc.), or is that net-new?

The answers to these questions may significantly reshape the phasing below.

---

## Proposed Architecture: Three Phases

### Phase 1: Contributor Classification + Topic-Financial Schema

**Goal:** Enrich financial records with contributor type classification; build the query path from topics to financial connections.

#### 1a. Contributor Classification

Classify every campaign finance contributor into five buckets:

| Type | Description | Primary Source Signal |
|------|-------------|---------------------|
| Corporate | Business entities, LLCs, corporate PACs | NetFile `entity_Cd`, CA SOS business filings |
| Union | Labor unions, union PACs | NetFile `entity_Cd`, committee name patterns |
| Individual | Natural persons | NetFile `entity_Cd` = IND |
| PAC/IE Committee | Independent expenditure committees, ballot measure committees | NetFile/CAL-ACCESS committee type codes |
| Other | Tribal, nonprofit, unclassifiable | Fallback bucket |

**Implementation notes & open questions:**
- NetFile's `entity_Cd` and CAL-ACCESS's `ENTITY_CD` already carry type codes — this is largely a mapping exercise
- LLCs are ambiguous: could be corporate or individual shell. Cross-reference against CA SOS business filings (already in pipeline) to resolve where possible
- Confidence scoring applies: ambiguous classifications get a lower confidence and stay operator-only until resolved
- **Question for Claude Code:** Where does this classification live? New column on an existing contributions table? Separate lookup table? What's the existing schema for campaign finance records?

#### 1b. Topic-Financial Query Path

Build the join path that connects topics to money:

```
topic → agenda_items tagged with topic → votes on those items → council_members who voted
  → contributions to those council_members → contributor_type classification
```

This may be a view, a materialized view, or a denormalized index depending on performance. The conflict scanner's existing detectors (campaign contribution matching, donor-vendor cross-reference) likely already traverse parts of this graph.

**Question for Claude Code:** Does the conflict scanner already have optimized query paths that cover parts of this join? Can we reuse those, or is this a separate query concern?

**Acceptance criteria:**
- Every campaign finance contributor record has a `contributor_type` field (5-value enum)
- Ambiguous classifications have confidence scores and don't surface in public-tier views below 0.90
- A query can return "all financial connections for topic X, grouped by contributor type" with acceptable performance (<2s for any single topic)
- All records carry `city_fips`

---

### Phase 2: Topic Timeline Page + Cross-Linking

**Goal:** A public-facing page per topic showing all tagged items chronologically, with financial connections overlaid. Plus, wire topics as connective tissue across existing pages.

#### 2a. Topic Timeline Page

For a given topic (e.g., "Point Molate"), display:
- All agenda items, votes, resolutions, and other civic artifacts tagged with that topic, in chronological order
- For each item: date, meeting source, vote outcome (if applicable), brief description
- Financial connections panel: contributors connected to this topic (via the Phase 1 query path), grouped by contributor type
- Provenance metadata per item (source_url, extracted_at, source_tier, confidence_score — per D1)
- Low-confidence items shown in detail view only, never in summary counts (per D2)

**Design considerations:**
- This is a narrative-over-numbers page (D6) — don't lead with charts or statistics. Lead with the timeline of what happened, with financial context woven in as supporting detail
- The financial connections panel should use plain language: "3 corporate contributors gave to council members who voted on Point Molate items" not "3 corporate financial linkages detected"
- Topic pages need persistent, citation-stable URLs (researcher requirement from persona pressure testing)
- Framing: "Financial connections around [Topic]" not "Money influencing [Topic]" — sunlight, not surveillance

#### 2b. Topic Directory (Browse + Search)

Entry point for topic navigation:
- Browsable list of all topics with: topic name, item count, date range (first item to most recent)
- Search/filter across topics
- **Do not** rank by connection density here — that's Phase 3. Keep the default sort alphabetical or by recency of last item

#### 2c. Cross-Linking from Existing Pages

Topics should be connective tissue, not a siloed section:
- **Meeting pages:** Agenda items link to their topic page(s)
- **Person pages:** "Topics this official has voted on" section with links to topic pages
- **Wherever agenda items already appear:** Add topic tag(s) as clickable links

**Question for Claude Code:** What's the current component structure for agenda item display? Is there a shared component we'd add topic tags to, or are agenda items rendered differently in different views?

**Acceptance criteria:**
- Every topic with ≥1 tagged item has a public page at a persistent URL
- Topic pages render the full chronological timeline with financial connections
- Topic directory is browsable and searchable
- Existing meeting and person pages link to relevant topic pages
- All provenance and confidence rules (D1, D2) are enforced
- AI-generated topic classifications are marked per disclosure requirements

---

### Phase 3: Connection Density Rankings + Discovery

**Goal:** Surface which topics and items have the most financial connections — the journalist's "where to look first" signal.

#### 3a. Connection Density Metrics

For each topic, compute:
- Total unique financial connections (deduplicated contributors)
- Connections by contributor type (corporate: N, union: N, individual: N, etc.)
- Connection trend: is financial activity around this topic increasing, stable, or decreasing?

For individual items (agenda items, votes), compute:
- How many financial connections touch this specific item (via council members who voted)

#### 3b. Discovery Features

- Topic directory gains a "most connected" sort option
- Topic pages surface "most connected items" within the topic
- **Potential:** A standalone "discovery" or "explore" view showing top topics by connection density — but this needs careful framing review. "Most money flowing around these topics" is powerful journalism, but it could feel adversarial if framed wrong. Sunlight-not-surveillance framing applies.

**Open question:** Is connection density alone the right signal, or should it be normalized somehow? A topic with 50 agenda items and 10 connections is different from a topic with 2 agenda items and 10 connections. The latter is probably more interesting to a journalist. Worth discussing what metric actually captures "disproportionate financial attention."

**Acceptance criteria:**
- Connection density metrics computed and queryable per topic and per item
- Topic directory supports sorting by connection density
- Framing review completed before any density rankings go public-tier
- Density metrics include provenance (how computed, what data sources contributed)

---

## Things We're NOT Building (Scope Boundaries)

- **No graph visualization.** Connection density is expressed narratively, not as a network graph. D6 (narrative over numbers) applies.
- **No automated "alert" or "watchdog" framing.** Discovery features surface information; they don't flag problems.
- **No topic creation by users.** Topics come from the controlled vocabulary + LLM classification pipeline. Users browse; they don't curate.
- **No real-time updates.** Topic pages update when the pipeline runs, same as all other data.

---

## Questions for Claude Code

Summarizing the open questions that depend on existing schema/architecture knowledge:

1. **Topic data model:** What tables/fields exist from S14? Controlled vocabulary or free-form? Stable IDs?
2. **Topic assignment method:** LLM extraction? Keyword? How's confidence tracked?
3. **Contributor type data:** Does the conflict scanner already classify contributors? What's the existing campaign finance schema?
4. **Query path overlap:** Does the conflict scanner already traverse the topic→vote→contributor join path?
5. **Agenda item component:** Shared component for agenda item display across views?
6. **Connection density normalization:** Any existing patterns for "disproportionate attention" metrics vs. raw counts?

Claude Code: Feel free to reshape the phasing, merge or split phases, or flag things that are easier/harder than this spec assumes given what you know about the codebase. This is a starting point for discussion, not a final blueprint.
