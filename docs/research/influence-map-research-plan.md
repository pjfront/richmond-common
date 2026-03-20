# Influence Map — Research Plan for Claude Chat

Six research sessions to inform the Influence Map + Meetings Redesign (Sprint 14).
Each includes the prompt, recommended model, and what to do with the output.

---

## A. Civic Information Design Precedents

**Priority:** High — grounds our design decisions in evidence
**Model:** Claude Sonnet 4.6 with extended thinking
**Why this model:** Needs web search for current state of civic tech tools + analytical comparison. Extended thinking helps synthesize across many sources.

### Prompt

```
I'm building a local government transparency platform that shows financial connections
between campaign donors, city council voting records, and agenda items. I need to
understand what the best civic transparency tools do for information design.

Research these specific tools and their current UX patterns:
1. ProPublica Represent (https://projects.propublica.org/represent/)
2. Open States (https://openstates.org/)
3. GovTrack (https://www.govtrack.us/)
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

I'm specifically considering a "sentence-based" approach where each financial connection
is expressed as a plain-language sentence like "Council Member X voted yes. Their campaign
received $4,200 from Acme Corp's CEO." rather than a table. Has anyone done this before?
Is there research on whether narrative or tabular display is more effective for civic
financial data?

Also: are there any local-level (city/county) tools doing this, not just
state/federal? Most of the above are state or federal.
```

### What to do with output
- Compare our "sentences not tables" bet against precedent
- Identify navigation patterns we should adopt or avoid
- Find any local-level tools to study more closely
- Save findings to `docs/research/civic-design-precedents.md`

---

## B. Calendar UI for Sparse Event Data

**Priority:** Medium — informs Phase B implementation
**Model:** Claude Sonnet 4.6 (standard, no extended thinking needed)
**Why this model:** Straightforward design pattern research, no deep analysis needed

### Prompt

```
I'm designing a calendar view for a city council meeting schedule. The key constraint:
there are only about 2 meetings per month (sometimes 0, sometimes 3). This is very
sparse compared to typical calendar UIs.

Research calendar and timeline UI patterns that work well for sparse, high-importance
events. Specifically:

1. Is a monthly grid calendar (like Google Calendar) the right choice for ~2 events/month,
   or would a vertical timeline, event list, or other pattern work better?
2. How should empty months be handled? (Show empty grid vs. skip to next event)
3. What interaction pattern works for clicking on an event in a calendar? I'm considering
   "inline expansion below the calendar row" (the row expands to show meeting details
   without navigating away). Are there good examples of this pattern?
4. For very sparse calendars, what visual treatment prevents the grid from feeling empty
   or wasteful?
5. Should the calendar show only meetings, or should it also show other civic dates
   (filing deadlines, election dates, public comment periods)?

Design constraints:
- Built with CSS grid (no heavy calendar library)
- Must be responsive (mobile + desktop)
- URL must encode month/year for shareable views
- Must be accessible (keyboard navigable, screen reader compatible)
- Calendar is navigation (not data visualization), so it should feel like a way to
  find meetings, not a dashboard

Please include specific examples of sparse-event calendars done well, from any domain
(civic, cultural, event venues, etc.).
```

### What to do with output
- Decide: monthly grid vs. timeline vs. hybrid
- Identify the interaction pattern for day-click expansion
- Save findings to `docs/research/calendar-ui-patterns.md`

---

## C. Plain Language Political Finance Disclosure

**Priority:** High — protects project credibility
**Model:** Claude Opus 4.6 with extended thinking
**Why this model:** Needs careful legal/regulatory analysis + deep synthesis of framing risks. This is the highest-stakes research — getting framing wrong could damage the project. Opus for depth.

### Prompt

```
I'm building a civic transparency platform that shows financial connections between
campaign contributors and city council votes. I need to understand the legal, ethical,
and practical landscape for how political finance connections should be described to
the public.

Research the following:

1. **Legal standards for campaign finance disclosure presentation:**
   - Does California's FPPC have rules about how campaign finance data must be
     presented to the public? What about the Fair Political Practices Act?
   - Are there FEC guidelines for third-party tools that present campaign finance data?
   - What disclaimers or framing language do platforms like OpenSecrets, CalMatters,
     or Follow The Money use?

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
   - What language do established platforms use?
   - Where should disclaimers appear — once per page? Per connection? In tooltips?
   - Is there a standard for presenting confidence levels on financial connections?

5. **California-specific context:**
   - How does California's strong public records tradition affect what can be presented?
   - Are there specific California statutes (Government Code, Political Reform Act)
     that govern how campaign finance data can be republished?
   - What does the FPPC say about third-party platforms presenting Form 700 data?

I need practical, actionable guidance, not just theory. What specific language should
I use, what should I avoid, and what disclaimers are necessary?
```

### What to do with output
- Draft standard disclaimer language for the influence map
- Review our sentence templates against legal/framing risks
- Identify any regulatory requirements we're not meeting
- Save findings to `docs/research/financial-disclosure-framing.md`

---

## D. Entity-Centered Navigation UX

**Priority:** Medium — informs the "two centers" navigation pattern
**Model:** Claude Sonnet 4.6 with extended thinking
**Why this model:** Needs synthesis across knowledge graph UX, information architecture, and civic tech. Extended thinking for cross-domain analysis.

### Prompt

```
I'm designing a navigation system where users can explore the same dataset from two
different "centers":

1. **Agenda Item center:** Start from a city council vote, see all the people, money,
   and organizations connected to it
2. **Official center:** Start from a council member, see all the votes, money, and
   organizations connected to them

Every entity in one view links to the other view — clicking an official in the item
view takes you to their official view, and vice versa. The same data, different topology.

Research:

1. **Knowledge graph UIs:** How do tools like Neo4j Bloom, Kumu, Maltego, or Palantir
   handle switching between node types as the "center" of a view? What patterns work
   for non-technical users?

2. **Hub-and-spoke vs. faceted navigation:** In information architecture, when is
   hub-and-spoke (center + spokes) better than faceted search (filter by multiple
   dimensions)? My use case has relatively few entity types (items, officials, donors,
   organizations) but many relationships.

3. **Breadcrumb and back-navigation in graph-like structures:** When a user goes
   Item → Official → different Item → different Official, what navigation patterns
   prevent disorientation? Traditional breadcrumbs break because the path isn't
   hierarchical.

4. **Civic/political examples:** Do any political analysis tools use this dual-center
   pattern? (e.g., start from a bill OR start from a legislator, see the same
   relationship data)

5. **Cognitive load research:** What does UX research say about how many "hops" users
   will tolerate in an entity-navigation system before they lose context?

I'm specifically NOT building a visual graph/network diagram. The display is structured
narrative text (sentences describing connections), not nodes and edges. But the
navigation between entities is graph-like.
```

### What to do with output
- Refine the breadcrumb/back-navigation design for influence map pages
- Decide how many hops deep the cross-linking should go
- Save findings to `docs/research/entity-navigation-patterns.md`

---

## E. Local Issue Taxonomy Auto-Generation

**Priority:** Low — future multi-city scaling, not needed for Richmond
**Model:** Claude Sonnet 4.6 (standard)
**Why this model:** Exploratory research, doesn't need deep analysis

### Prompt

```
I have a local government transparency platform currently serving one city (Richmond,
California). For that city, I hand-curated 14 "local issues" — hyper-local political
fault lines that residents actually talk about (e.g., "Point Molate" development,
"Chevron & the Refinery", "Rent Board & Tenants", "The Hilltop" mall redevelopment).

These are matched via keyword detection against city council agenda item titles and
descriptions. They're separate from generic civic categories (housing, budget, zoning)
— they're the *specific* places, institutions, and tensions that define that city's
politics.

I want to scale this to 19,000 US cities. Research:

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
```

### What to do with output
- Save to `docs/research/local-issue-taxonomy-scaling.md`
- Reference during multi-city work (future sprint)

---

## F. Accessibility for Civic Financial Data

**Priority:** Low — important but not blocking design
**Model:** Claude Haiku 4.5 (standard)
**Why this model:** Focused, well-documented topic. Doesn't need deep reasoning.

### Prompt

```
I'm building a civic transparency platform that presents campaign finance connections
as plain-language sentences. Example:

"Council Member Martinez voted yes on the Acme Development agreement. His campaign
received $4,200 from Acme Development PAC across 3 contributions between 2022-2024.
Strong confidence. Source: NetFile (Tier 1)."

Each sentence is inside a card component with expandable evidence details, a "Provide
context" link, and source attribution.

Research WCAG 2.1 AA compliance specifically for this type of content:

1. How should screen readers handle these connection cards? What ARIA roles and
   landmarks are appropriate?
2. The cards are expandable (click to show evidence details). What's the accessible
   pattern for expand/collapse with nested content?
3. Confidence badges use color (green/yellow/red). What's the accessible alternative
   beyond just adding text labels?
4. Source attribution badges (tier 1-4 with color coding) — same color question.
5. The "Provide context" and "View filing" links — should these be buttons or links?
   What ARIA labels do they need?
6. For the filter bar (local issue pills that filter the view), what's the accessible
   pattern? Are these toggle buttons, checkboxes, or something else?
7. Any civic-specific accessibility considerations? (Government data has a higher
   obligation for accessibility under Section 508)

I'm using shadcn/ui + Radix UI primitives. What specific Radix components should I
use for each of these patterns?
```

### What to do with output
- Apply ARIA patterns to component designs
- Save to `docs/research/accessibility-civic-data.md`
- Reference during implementation

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

**All outputs go to `docs/research/`** and get referenced in the spec.
