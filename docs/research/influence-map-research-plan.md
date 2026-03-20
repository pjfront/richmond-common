# Influence Map — Research Plan for Claude Chat

Six research sessions to inform the Influence Map + Meetings Redesign (Sprint 14).
Each includes the prompt, recommended model, and what to do with the output.

**Important:** These prompts are designed for Claude Chat (claude.ai) in the Richmond Common project context. Chat has the full project loaded but can't save files — copy the output and save it to the indicated file path in Claude Code or manually.

---

## A. Civic Information Design Precedents

**Priority:** High — grounds our design decisions in evidence
**Model:** Claude Sonnet 4.6 with extended thinking
**Why this model:** Needs web search for current state of civic tech tools + analytical comparison. Extended thinking helps synthesize across many sources.

### Prompt

```
This is research for Richmond Common's Sprint 14 (Influence Map + Meetings Redesign).
We're designing a new "Influence Map" that shows financial connections between campaign
donors, city council voting records, and agenda items using sentence-based narrative
display instead of tables or graph visualizations. The full spec is at
docs/specs/influence-map-meetings-redesign-spec.md.

I need to understand what the best civic transparency tools do for information design.
Use web search to research these specific tools and their current UX patterns:

1. ProPublica Represent (projects.propublica.org/represent/)
2. Open States (openstates.org)
3. GovTrack (govtrack.us)
4. Councilmatic / Open Civic Data
5. CalMatters (California-specific)
6. Follow The Money / OpenSecrets
7. MapLight (if still active)
8. Ballotpedia

For each, analyze:
- How do they present the relationship between a legislative item and the people who
  voted on it?
- Do any of them show financial connections alongside votes? How?
- What is their primary navigation model — bill-centered, person-centered, or something
  else?
- Do any use sentence-based narrative display for financial data (vs. tables/charts)?
- What do they do well that I should learn from?
- What do they do poorly or generically?

Our specific design bet: each financial connection is expressed as a plain-language
sentence like "Council Member Martinez voted yes. His campaign received $4,200 from
Acme Development PAC across 3 contributions between 2022-2024." rather than a table
row. Has anyone done this before? Is there research on whether narrative or tabular
display is more effective for civic financial data?

Also: are there any local-level (city/county) tools doing this, not just
state/federal? Most of the above are state or federal. We're building for city
council, 19,000 US cities.

Format the output as a research document I can save to docs/research/civic-design-precedents.md.
```

### What to do with output
- Copy from Chat, save to `docs/research/civic-design-precedents.md`
- Compare our "sentences not tables" bet against precedent
- Identify navigation patterns we should adopt or avoid

---

## B. Calendar UI for Sparse Event Data

**Priority:** Medium — informs Phase B implementation
**Model:** Claude Sonnet 4.6 (standard, no extended thinking needed)
**Why this model:** Straightforward design pattern research, no deep analysis needed

### Prompt

```
This is research for Richmond Common's Sprint 14 — specifically Phase B (Calendar View)
of the Influence Map + Meetings Redesign spec (docs/specs/influence-map-meetings-redesign-spec.md).

I'm designing a calendar view for Richmond City Council's meeting schedule. The key
constraint: there are only about 2 meetings per month (sometimes 0, sometimes 3).
This is very sparse compared to typical calendar UIs. Richmond has ~240 meetings total
from 2020-2026 across regular, special, closed session, and joint meeting types.

Research calendar and timeline UI patterns that work well for sparse, high-importance
events. Specifically:

1. Is a monthly grid calendar (like Google Calendar) the right choice for ~2 events/month,
   or would a vertical timeline, event list, or other pattern work better?
2. How should empty months be handled? (Show empty grid vs. skip to next event)
3. What interaction pattern works for clicking on an event in a calendar? We're considering
   "inline expansion below the calendar row" (the row expands to show a meeting summary
   with hero item teaser without navigating away, per our design rule U6: no interstitial
   pages). Are there good examples of this pattern?
4. For very sparse calendars, what visual treatment prevents the grid from feeling empty
   or wasteful?
5. Should the calendar show only meetings, or should it also show other civic dates
   (filing deadlines, election dates, public comment periods)?

Design constraints:
- Built with CSS grid (no heavy calendar library — ~35 cells is simple enough)
- Next.js 16 + React 19 + Tailwind CSS v4
- Must be responsive (mobile + desktop)
- URL must encode month/year for shareable views (/meetings?month=2024-03)
- Must be accessible (keyboard navigable, screen reader compatible, per design rule A2)
- Calendar is navigation (not data visualization), so our design rule T7 (narrative over
  numbers) is respected — it's a way to find meetings, not a dashboard
- Meeting types need visual encoding: regular, special, closed session, joint. Color
  paired with shape/label for accessibility.

Please include specific examples of sparse-event calendars done well, from any domain
(civic, cultural, event venues, etc.).

Format the output as a research document I can save to docs/research/calendar-ui-patterns.md.
```

### What to do with output
- Copy from Chat, save to `docs/research/calendar-ui-patterns.md`
- Decide: monthly grid vs. timeline vs. hybrid
- Identify the interaction pattern for day-click expansion

---

## C. Plain Language Political Finance Disclosure

**Priority:** High — protects project credibility
**Model:** Claude Opus 4.6 with extended thinking
**Why this model:** Needs careful legal/regulatory analysis + deep synthesis of framing risks. This is the highest-stakes research — getting framing wrong could damage the project. Opus for depth.

### Prompt

```
This is high-stakes research for Richmond Common — a civic transparency platform for
Richmond, California. I sit on Richmond's Personnel Board, so maintaining a collaborative
(not adversarial) relationship with city government is critical. The project's core value
is "governance assistant, not adversarial watchdog."

We're building an "Influence Map" (Sprint 14) that shows financial connections between
campaign contributors and city council votes as plain-language sentences. Example:

"Council Member Martinez voted yes. His campaign received $4,200 from Acme Development
PAC across 3 contributions between 2022-2024. Strong confidence. Source: NetFile (Tier 1)."

Each connection has a confidence score (Strong ≥85%, Moderate 70-85%, Low <70%), and
we only show ≥90% confidence in summary views. We currently use the framing:
"A connection does not imply wrongdoing — it identifies financial relationships relevant
to public transparency."

Our data sources are all public records: NetFile (local campaign finance, Tier 1),
CAL-ACCESS (state campaign finance, Tier 1), FPPC Form 700 (economic interests, Tier 1),
city expenditure data via Socrata, business license records.

I need thorough research on:

1. **Legal standards for campaign finance disclosure presentation:**
   - Does California's FPPC have rules about how campaign finance data must be
     presented to the public? What about the Fair Political Practices Act (Gov Code 81000+)?
   - Are there FEC guidelines for third-party tools that present campaign finance data?
   - What disclaimers or framing language do platforms like OpenSecrets, CalMatters,
     or Follow The Money use? Use web search to find their actual disclaimer text.

2. **Framing risks — what has gotten transparency organizations in trouble:**
   - Has any transparency org faced legal challenges for how they presented financial
     connection data? (Defamation, implied accusations, etc.)
   - What's the difference between "X donated to Y's campaign" and "X has a financial
     connection to Y" legally?
   - What framing has been criticized as misleading even if technically accurate?
     (Cherry-picking, implying causation, missing context)

3. **Research on citizen comprehension:**
   - How do citizens actually process campaign finance disclosure information?
   - Sunlight Foundation, Ash Center (Harvard), or similar research on what makes
     civic financial data understandable vs. misleading?
   - Is there evidence that narrative framing ("X donated to Y") is more or less
     likely to be misinterpreted than tabular data?

4. **Best practices for "connection does not imply wrongdoing" disclaimers:**
   - What language do established platforms use? Find actual examples via web search.
   - Where should disclaimers appear — once per page? Per connection? In tooltips?
   - Is there a standard for presenting confidence levels on financial connections?

5. **California-specific context:**
   - How does California's strong public records tradition affect what can be presented?
   - Are there specific California statutes (Government Code, Political Reform Act)
     that govern how campaign finance data can be republished by third parties?
   - What does the FPPC say about third-party platforms presenting Form 700 data?

I need practical, actionable guidance. What specific language should we use in our
influence map, what should we avoid, and what disclaimers are necessary? Draft
recommended disclaimer text that fits our "governance assistant" framing.

Format the output as a research document I can save to docs/research/financial-disclosure-framing.md.
```

### What to do with output
- Copy from Chat, save to `docs/research/financial-disclosure-framing.md`
- Draft standard disclaimer language for the influence map
- Review our sentence templates against legal/framing risks

---

## D. Entity-Centered Navigation UX

**Priority:** Medium — informs the "two centers" navigation pattern
**Model:** Claude Sonnet 4.6 with extended thinking
**Why this model:** Needs synthesis across knowledge graph UX, information architecture, and civic tech. Extended thinking for cross-domain analysis.

### Prompt

```
This is research for Richmond Common's Sprint 14 — specifically the "two centers"
navigation pattern in the Influence Map design (docs/specs/influence-map-meetings-redesign-spec.md).

We've designed a system where users can explore the same financial connection data from
two different "centers":

1. **Agenda Item center** (/influence/item/[id]): Start from a city council vote, see
   all the officials, donors, and organizations connected to it. Each connection is
   a plain-language sentence.
2. **Official center** (/council/[slug]): Start from a council member, see all the
   agenda items, donors, and organizations connected to them.

Every entity in one view links to the other view — clicking an official name in the
item view takes you to their profile, and vice versa. The same data, different topology.

The user journey looks like:
Meeting page → Agenda item card → Item Influence Map → click official name →
Official profile → click agenda item → different Item Influence Map → ...

Research:

1. **Knowledge graph UIs:** How do tools like Neo4j Bloom, Kumu, Maltego, or Palantir
   handle switching between node types as the "center" of a view? What patterns work
   for non-technical users (our audience is Richmond residents, not analysts)?

2. **Hub-and-spoke vs. faceted navigation:** In information architecture, when is
   hub-and-spoke (center + spokes) better than faceted search (filter by multiple
   dimensions)? Our use case has relatively few entity types (agenda items, officials,
   donors, organizations) but many relationships between them.

3. **Breadcrumb and back-navigation in graph-like structures:** When a user goes
   Item → Official → different Item → different Official, what navigation patterns
   prevent disorientation? Traditional breadcrumbs break because the path isn't
   hierarchical. What should we use instead?

4. **Civic/political examples:** Do any political analysis tools use this dual-center
   pattern? (e.g., start from a bill OR start from a legislator, see the same
   relationship data) Use web search to find examples.

5. **Cognitive load research:** What does UX research say about how many "hops" users
   will tolerate in an entity-navigation system before they lose context? We're
   considering unlimited cross-linking — should we cap depth?

Important: we're specifically NOT building a visual graph/network diagram. The display
is structured narrative text (sentences describing connections), not nodes and edges.
But the navigation between entities is graph-like.

Format the output as a research document I can save to docs/research/entity-navigation-patterns.md.
```

### What to do with output
- Copy from Chat, save to `docs/research/entity-navigation-patterns.md`
- Refine the breadcrumb/back-navigation design for influence map pages
- Decide how many hops deep the cross-linking should go

---

## E. Local Issue Taxonomy Auto-Generation

**Priority:** Low — future multi-city scaling, not needed for Richmond
**Model:** Claude Sonnet 4.6 (standard)
**Why this model:** Exploratory research, doesn't need deep analysis

### Prompt

```
This is future-looking research for Richmond Common's multi-city scaling plans. Not
needed for current sprint work, but important for architecture decisions.

Currently for Richmond, California, we hand-curated 14 "local issues" — hyper-local
political fault lines that residents actually talk about. Examples:
- "Point Molate" — former Navy fuel depot, decades of development proposals
- "Chevron & the Refinery" — largest employer, political spender, 2012 fire
- "Rent Board & Tenants" — rent control since 2016
- "The Hilltop" — closed mall, redevelopment into housing
- "Police & Community Safety" — ONS, community policing reform, CPRC

These are matched via keyword detection against city council agenda item titles and
descriptions (see web/src/lib/local-issues.ts). They're separate from our 14 generic
civic categories (housing, budget, zoning, etc.) — they're the *specific* places,
institutions, and tensions that define a city's politics.

We want to scale to 19,000 US cities. Research:

1. How would you auto-generate a local issue taxonomy for a new city from meeting
   minutes and agenda text? What NLP approaches work?
   - Topic modeling (LDA, BERTopic)?
   - Named entity recognition + clustering?
   - LLM-based extraction ("read these 100 meeting titles, identify the recurring
     political fault lines")?

2. What data sources beyond meeting minutes could inform a local issue taxonomy?
   - Local news (which stories get the most coverage?)
   - Public comments (what do residents talk about?)
   - Land use / planning documents
   - Election campaign materials (what issues do candidates run on?)

3. How do you validate an auto-generated taxonomy? How do you know your 14 issues
   for City X are the RIGHT 14?

4. Are there existing datasets of city-level political issues? (Urban Institute,
   National League of Cities, ICMA, etc.)

5. What's the minimum data needed to generate a useful taxonomy? (e.g., how many
   meetings' worth of minutes?)

Format the output as a research document I can save to docs/research/local-issue-taxonomy-scaling.md.
```

### What to do with output
- Copy from Chat, save to `docs/research/local-issue-taxonomy-scaling.md`
- Reference during multi-city work (future sprint)

---

## F. Accessibility for Civic Financial Data

**Priority:** Low — important but not blocking design
**Model:** Claude Haiku 4.5 (standard)
**Why this model:** Focused, well-documented topic. Doesn't need deep reasoning.

### Prompt

```
This is research for Richmond Common's Influence Map feature (Sprint 14). We present
campaign finance connections as plain-language sentences inside expandable card
components. Example:

"Council Member Martinez voted yes on the Acme Development agreement. His campaign
received $4,200 from Acme Development PAC across 3 contributions between 2022-2024.
Strong confidence. Source: NetFile (Tier 1)."

Each card has: expandable evidence details, a "Provide context" link, source attribution
badge (SourceBadge component), and confidence badge (ConfidenceBadge component — green
Strong, yellow Moderate, red Low). Above the cards is a filter bar of "local issue"
pills that filter the view when clicked.

Our design rules mandate: shadcn/ui + Radix UI primitives only (design rule D3),
WCAG AA compliance, no custom div onClick reimplementations.

Research WCAG 2.1 AA compliance specifically for this type of content:

1. How should screen readers handle these connection cards? What ARIA roles and
   landmarks are appropriate?
2. The cards are expandable (click to show evidence details). What's the accessible
   pattern for expand/collapse with nested content? Which Radix primitive?
3. Confidence badges use color (green/yellow/red for Strong/Moderate/Low). What's the
   accessible alternative beyond just adding text labels? We already pair color with
   text per design rule A2.
4. Source attribution badges (tier 1-4 with color coding) — same color question.
5. The "Provide context" and "View filing" links — should these be buttons or links?
   What ARIA labels do they need?
6. For the local issue filter bar (pills like [Chevron · 2] [Point Molate · 1] that
   filter the view when clicked), what's the accessible pattern? Toggle buttons,
   checkboxes, or something else? Which Radix primitive?
7. Any civic-specific accessibility considerations? (Government data platforms have
   higher obligations for accessibility under Section 508.)

Format the output as a research document I can save to docs/research/accessibility-civic-data.md.
```

### What to do with output
- Copy from Chat, save to `docs/research/accessibility-civic-data.md`
- Apply ARIA patterns to component designs during implementation

---

## Research Execution Plan

| Session | Topic | Model | Extended Thinking | Priority | Est. Time |
|---------|-------|-------|-------------------|----------|-----------|
| 1 | C: Financial Disclosure Framing | Opus 4.6 | Yes | HIGH | 15-20 min |
| 2 | A: Civic Design Precedents | Sonnet 4.6 | Yes | HIGH | 10-15 min |
| 3 | D: Entity Navigation UX | Sonnet 4.6 | Yes | MEDIUM | 10-15 min |
| 4 | B: Calendar UI Patterns | Sonnet 4.6 | No | MEDIUM | 5-10 min |
| 5 | E: Local Issue Taxonomy | Sonnet 4.6 | No | LOW | 5-10 min |
| 6 | F: Accessibility Patterns | Haiku 4.5 | No | LOW | 5 min |

**Run C first** — it's the highest stakes (framing mistakes are hard to recover from)
and informs the sentence templates we're designing. A second, because it validates or
challenges our core design bet. The rest can run in any order.

**Workflow:** Copy prompt from here → paste into Claude Chat (in this project) → select
the recommended model → enable extended thinking if indicated → copy the output → save
to the indicated `docs/research/` file path using Claude Code.
