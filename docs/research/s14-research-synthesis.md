# S14 Research Synthesis: Influence Map + Meetings Redesign

**Research completed:** 6/6 sessions (A–F)
**Synthesized:** 2026-03-19

This document maps findings from the six S14 research sessions against the spec (`docs/specs/influence-map-meetings-redesign-spec.md`) and identifies what's validated, what changes, and what's new.

---

## Executive Summary

The spec's three core design bets are validated by research:

1. **Sentences, not tables** — UX research shows ~47% comprehension improvement for non-expert audiences with narrative vs. raw data. No active tool does this for vote-money correlation. We're in genuinely uncharted territory.
2. **Two centers (item + official)** — The "Wikipedia model" of entity-centric pages with inline hyperlinks is the strongest pattern for non-technical audiences. Visual graph UIs consistently fail with civic audiences.
3. **Meeting as navigation, not center** — Research confirms meetings are launchpads. The "next meeting" question dominates user intent.

However, research surfaces **five spec changes needed**, **three new requirements**, and **two deferred decisions** that should be resolved before implementation begins.

---

## Part 1: What the Research Validates

### The narrative sentence approach (Research A, C)

**Strongly validated.** No active tool connects campaign money to legislative votes at any level. MapLight was the only one, frozen since 2017. The gap is real.

- MapLight itself used narrative sentences in its reports ("Senators voting against the amendment received 11× more from pro-gun groups")
- ProPublica's Opportunity Gap auto-generated plain-English paragraphs for 52K schools — the closest technical precedent for automated narrative
- Academic research: narrative improves comprehension by 47% and civic engagement willingness by 32% vs. traditional presentation
- The "TableTale" study (2025) found narrative + progressive disclosure to underlying data was optimal — exactly our architecture

**Risk acknowledged:** Cognitive science shows narrative framing amplifies implied causation (illusory correlation, confirmation bias, availability heuristic). This is manageable with framing discipline — see Part 2.

### Two-center navigation (Research D)

**Validated with clear implementation guidance.** The entity-centric page model with inline hyperlinks ("Wikipedia model") is the research-backed approach for non-technical audiences.

- Knowledge graph practitioners report end users "ultimately preferred simple table-based KG representations over custom-built interactive graph interfaces" (IEEE TVCG 2023)
- The pivot operation (switching from item-center to official-center) should be invisible — just a link click, not an explicit operation
- Hub pages serve as entry points; entity pages allow free lateral traversal
- MapLight Classic and Councilmatic are the closest precedents

### Unlimited navigation depth (Research D)

**Validated.** The 3-click rule is debunked (Joshua Porter, 2003). Information foraging theory says users self-regulate based on "information scent," not depth. Working memory research (Cowan's 4±1) says externalize memory through navigation aids rather than capping exploration.

**Key requirement:** Every entity link must carry enough context (name, type, key fact) to maintain information scent.

### Progressive disclosure architecture (Research A, F)

**Validated.** Nielsen Norman Group recommends 2–3 disclosure layers. GovTrack, CalMatters, and Councilmatic all implement variants. Our spec's Layer 1 (sentence) → Layer 2 (source/confidence) → Layer 3 (evidence details) maps to this.

Research suggests adding a Layer 4: raw data access (links to original filing documents, downloadable datasets).

### Accessibility approach (Research F)

**Our design rule D3 (shadcn/ui + Radix) is confirmed as the right foundation.** Specific primitive mapping is clear:
- Card expand/collapse → Radix Collapsible (Disclosure pattern)
- Card list → `<article>` in `<ul>`
- Filter pills → Radix ToggleGroup with manual ARIA overrides
- "Provide context" → Radix Dialog
- "View filing" → native `<a href>`

**Legal urgency:** California's ADA Title II deadline is **April 2026** — one month away. WCAG 2.1 AA is mandatory for platforms associated with city government.

---

## Part 2: Spec Changes Required

### Change 1: Sentence framing order (HIGH PRIORITY)

**Spec says:** "Council Member Martinez voted yes. His campaign received $4,200 from Acme Development PAC."

**Research says:** Leading with the vote then showing the donation structurally implies the vote was a consequence. This is the highest-risk framing pattern identified.

**New framing:** Lead with the contribution record, then the vote. Add contextual data.

```
According to NetFile filings, Acme Development PAC made 3 contributions
totaling $4,200 to the Martinez campaign committee between 2022-2024.
Council Member Martinez voted yes on [item].
```

Additional context required per connection (from MapLight criticism):
- Donation as percentage of total campaign fundraising
- Whether other council members who received no contributions voted the same way
- Whether the official voted against the contributor's interest on other occasions

**Affects:** Phase C (C1 sentence templates), Phase D (D1 council profile sentences)

### Change 2: Replace "financial connection" terminology (HIGH PRIORITY)

**Spec says:** "Financial connections," "N financial connections >"

**Research says:** "Connection" implies broader relationships beyond documented campaign contributions. "Financial ties" is worse.

**New terminology:** "Campaign contribution record" or "campaign finance relationship." The section heading "Financial Context" in spec C2 should become "Campaign Finance Context."

**Affects:** All phases — this is a global find-replace in the spec and all UI copy.

### Change 3: Calendar default view (MEDIUM PRIORITY)

**Spec says:** Phase B uses a monthly calendar grid as default, with list view as toggle.

**Research says:** Grid calendars underperform list/agenda views when density drops below ~1 event/week. At 2 meetings/month, 95% of cells are empty. Court dockets, TheyWorkForYou, Councilmatic, and most civic platforms use lists.

**New design:** Invert the default.
- **Primary:** Grouped agenda list (month-grouped, accordion-expandable)
- **Secondary:** Mini-calendar as navigation aid (sidebar on desktop, top strip on mobile)
- **Tertiary:** Full grid as toggle for users who want it
- **New element:** "Next Meeting" persistent card above everything — the dominant user question

The inline expansion pattern (B2) still works — it just applies to the list items rather than calendar cells. The URL pattern (`/meetings?month=2024-03`) and shareable views are unchanged.

**Affects:** Phase B (B1 calendar grid → B1 agenda list + mini-calendar, B3 list toggle → grid toggle)

### Change 4: Breadcrumb strategy (MEDIUM PRIORITY)

**Spec says:** Phase C2 uses "Meeting date > Item title" breadcrumbs. Phase E2 adds back-navigation breadcrumbs.

**Research says:** Traditional breadcrumbs break for graph-like traversal. The path isn't hierarchical. A composite strategy is needed:

1. **Contextual back link** with entity type header ("← Back to [Previous Entity Name]")
2. **Canonical location breadcrumb** (fixed hierarchy regardless of how user arrived: `Home > Meetings > Jan 15 Meeting > Budget Amendment`)
3. **Related entities section** (backlinks — all entities connected to this one)
4. **Recently visited panel** (last 5–8 entities with type icons, desktop sidebar / mobile expandable)
5. **Persistent search bar** as escape hatch
6. **Visual entity type differentiation** (distinct colors/icons per entity type)

**Affects:** Phase C (C2 page structure), Phase D, Phase E (E2 bidirectional navigation)

### Change 5: Disclaimer placement and content (MEDIUM PRIORITY)

**Spec says:** Section C2.4 includes "A connection does not imply wrongdoing..." framing prose.

**Research says:** Disclaimer language needs to be more specific and placed at multiple levels:

- **Global disclaimer** (every influence map page, above data, not in footer) — drafted in research C
- **Per-connection tooltip** (info icon on each connection)
- **Confidence score explanation** (once per page, linked from every badge) — must explain scores measure *match certainty*, not *likelihood of influence*
- **Methodology page** (linked from every influence map page)

The specific draft disclaimer text from research C should replace the spec's placeholder framing.

**Affects:** Phase C (C2 section 4, C2 section 7), Phase D

---

## Part 3: New Requirements Surfaced

### New Requirement 1: Contextual data per connection

MapLight's biggest criticism was showing donations next to votes without context. Every connection must include:

- Contribution as % of total campaign fundraising
- Total number of contributions from all sources during the same period
- Whether the official voted against the contributor's interest on other occasions
- Whether other council members who received no donations from this source voted the same way

This requires **new queries** beyond what the spec lists in C2. The existing `getConflictFlagsDetailed()` doesn't carry this context.

### New Requirement 2: Entity type visual differentiation system

Research D strongly recommends distinct colors, icons, and layout patterns per entity type to reduce disorientation during graph-like navigation. This should be designed as a system:

| Entity type | Color suggestion | Icon |
|---|---|---|
| Agenda item | Green | Document |
| Official | Blue | Person |
| Donor/Organization | Orange | Building/dollar |
| Meeting | Gray | Calendar |

This becomes a design system component (like CivicTerm/SourceBadge) used across all influence map pages.

### New Requirement 3: Meeting type encoding (3-channel)

Research B provides a specific accessible encoding system for meeting types in the calendar:

| Type | Color | Shape | Border | Badge |
|---|---|---|---|---|
| Regular | Blue | ● Circle | Solid | "Regular" |
| Special | Orange | ★ Star | Dashed | "Special" |
| Closed | Purple | ■ Square/🔒 | Dotted | "Closed" |
| Joint | Teal | ◆ Diamond | Double | "Joint" |

Blue/orange pairing is the most universally distinguishable across color vision deficiencies.

---

## Part 4: Deferred Decisions

### Decision 1: Radix ToggleGroup vs. custom implementation for filter pills

Research F documents a known ARIA spec violation in Radix ToggleGroup `type="single"` (GitHub #3188): `role="radio"` inside `role="group"` instead of `role="radiogroup"`, plus radiogroup semantics forbid deselection (which our design requires).

**Options:**
- A) Use ToggleGroup with manual ARIA overrides
- B) Use individual Toggle.Root components in a manual `role="group"` wrapper with custom single-select state management

Research recommends Option B for correctness. Decision can wait until Phase A implementation.

### Decision 2: CalMatters-style comparative framing

Research A highlights CalMatters' comparative framing ("396% higher than average legislators") as highly effective. Should the influence map include comparative context like "received 3.2× more from real estate interests than the average council member"?

This adds significant query complexity (need citywide averages per industry/sector) but dramatically improves interpretability. Could be a Phase E polish item rather than blocking initial implementation.

---

## Part 5: Research Highlights for Future Work

### Multi-city scaling (Research E)

The local issue taxonomy research is LOW priority for S14 but architecturally significant:
- LLMs solve the cold-start problem (usable taxonomies from 50 agenda titles)
- Legistar API covers ~70% of largest US cities
- The tiered approach (2K full pipeline / 5K BERTopic+LLM / 5K TopicGen / 7K transfer) is the scaling plan
- **No ground-truth dataset of city-specific political fault lines exists for US cities** — building one would be publishable

### Key precedent: CalMatters Digital Democracy (Research A)

The single most important active precedent. Won the Punch Sulzberger Prize. Places financial data on legislator profiles alongside legislative activity. Cross-entity search where searching "Chevron" reveals donations, lobbying, gifts, and bill positions. Our influence map is the city-council equivalent of what CalMatters does for the California legislature.

### Legal foundation is strong (Research C)

California Government Code §81008 imposes "no conditions whatsoever" on inspecting campaign finance filings. No transparency org has faced a successful defamation lawsuit for presenting campaign finance data. Anti-SLAPP protections, fair report privilege, and actual malice standard provide robust defense. The risk is reputational (credibility damage from implied causation), not legal.

---

## Implementation Priority Adjustment

Based on research findings, the spec's phase order (A → B → C → D → E) remains correct, but within phases:

**Phase A** — Add meeting type 3-channel encoding to the topic board cards. Design the entity type color/icon system early since it propagates everywhere.

**Phase B** — Flip the default: agenda list primary, mini-calendar secondary. Add "Next Meeting" card. The CSS Grid calendar is still built but as an optional view.

**Phase C** — This is the highest-stakes phase. Sentence template must be revised per Change 1. Contextual data per connection (New Req 1) adds query complexity. Disclaimer system (Change 5) must be designed before building the page.

**Phase D** — Same sentence template changes cascade here. The comparative framing decision (Deferred Decision 2) affects the council profile restructure.

**Phase E** — Composite navigation strategy (Change 4) is the main addition. Recently-visited panel and entity type differentiation system are new scope.
