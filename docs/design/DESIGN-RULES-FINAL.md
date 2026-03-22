# RTP Design Rules — Final

_Binding design rules for Claude Code. Every rule is derived from resolved design positions documented in `DESIGN-POSITIONS.md` and pressure-tested against five user personas. Rules are testable — if you can't verify compliance by inspecting the output, the rule isn't doing its job._

_When two rules conflict, the priority order in the Conflict Resolution section is binding. Trust infrastructure > Accessibility > Plain language > Scannability > Information density > Aesthetics._

---

## Universal Rules

These apply to every page, component, and view in the application.

**U1. Every user-visible data point ships with source attribution.**
Every number, date, name, or claim rendered in the UI must display: (a) a source link or label, (b) an extraction/freshness timestamp, and (c) a source tier badge (Tier 1–4). These fields are non-nullable in the API schema. Data missing any of the three stays operator-only until attributed. No exceptions, no "we'll add citations later."
`[Why: Fogg credibility; Moesta anxiety reduction. Position #9. Survived all five personas unchallenged.]`

**U2. Accessibility is infrastructure, not a feature.**
Every interactive element uses shadcn/ui + Radix UI primitives — no custom `<div onClick>` reimplementations of buttons, dropdowns, modals, tabs, or menus. Every page has a correct heading hierarchy (h1 → h2 → h3, no skipped levels). All text meets WCAG AA contrast (4.5:1 body text, 3:1 large text and UI components). Color is never the sole means of conveying information — always pair with pattern, shape, or label. There is no separate "accessible mode." The default *is* the accessible version.
`[Why: Holmes curb-cut effect; Elavsky accessible redundancy; WCAG 2.1 AA. Position #4, #10. Survived all personas; extended by Dorothy — see A1–A4.]`

**U3. Maximum 3 KPIs per summary card. One focal point per section. Visual hierarchy within the three.**
Summary-level cards (council member cards, meeting summaries, entity overview cards) display exactly 3 key metrics. Choosing which three is an editorial decision made per card type. The single most important metric is visually dominant (larger font size, top position). The other two are visually subordinate. Each page section has one visual focal point that a scanning user lands on within 2 seconds.
`[Why: Krug scanning/satisficing; Few dashboard constraint. Position #2. Robert: hierarchy within the three matters.]`

**U4. Every collapsed section signals its depth.**
Section headers include a count: "Donations (47)" not "Donations." Summary cards include quantity signals: "3 of 47 donations shown." Every Layer 1 element communicates the existence and approximate size of Layer 2. No dead ends, no blank walls.
`[Why: Pirolli & Card information scent; Norman gulf of execution. Position #5.]`

**U5. Maximum 2 clicks from any summary to its raw data.**
From a summary card, one click reaches the full detail view. From the detail view, one click reaches raw data (CSV download or API link). Export and download affordances are visible in the toolbar of every detail view — never behind a kebab menu or progressive disclosure.
`[Why: Shneiderman details on demand. Position #5. Maria: "You had me at 'never behind a kebab menu.'"]`

**U6. No interstitial pages, onboarding flows, or gated explainers. Ever.**
Search results and data views load immediately. Context is delivered *alongside* data (inline benchmarks, confidence badges, one-sentence labels), never *before* it. "Learn more" expands inline via accordion — it does not navigate to a separate page. No "Welcome to…" splash text. No "How to read this data" that blocks access.
`[Why: ProPublica/BallotReady action-first entry; Wurman modified. Position #12. Survived unchallenged.]`

**U7. Page-level chrome follows Norman. Chart interiors follow Tufte.**
Cards, navigation, layout containers, and section backgrounds use polished shadcn/ui styling with consistent spacing tokens — they should feel warm and professional. Inside chart data areas: no gradients, no 3D effects, no decorative elements. Axes, labels, and data marks earn their pixels. No illustrations, mascots, or decorative imagery anywhere in the application.
`[Why: Norman aesthetic-usability; Fogg 50ms credibility; Tufte data-ink ratio (charts only). Position #1.]`

**U8. AI-generated content is always identified.**
Any text produced by Claude (meeting summaries, conflict explanations, "so what?" annotations) must be visually marked as AI-generated with a small, consistent indicator. Phrasing: "AI-generated summary" not "Summary." This applies to all publication tiers. The label is never omissible for public-tier content.
`[Why: RTP ethics convention; Fogg earned credibility. Survived unchallenged — Dr. Patel and James depend on it.]`

**U9. Loading, empty, and error states are first-class citizens.**
Every data-fetching component defines all three states explicitly. Loading states show a skeleton that matches the layout of the loaded state (no spinners on blank pages). Empty states explain *why* there's no data and what the user can do ("No campaign finance records found for this candidate. Records are sourced from NetFile and CAL-ACCESS."). Error states identify the failure without jargon and preserve whatever data already loaded. All state changes are announced to assistive technology: loading states use `aria-live="polite"` with descriptive text; error states use `role="alert"`; filter updates announce result counts via `role="status"`.
`[Why: Norman conceptual models; Krug system state. Dorothy: without ARIA live regions, state changes are invisible to screen readers.]`

**U10. Every detail page and filtered view has a permanent, shareable URL.**
Detail pages use human-readable slugs (`/people/eduardo-martinez` not `/entity/47291`). Filter state, sort order, and date ranges are encoded in URL query parameters so any view can be shared. Old URLs redirect to new locations rather than 404. Every page includes a "Copy link" affordance. Every page footer includes a pre-formatted citation string with URL, access date, and data freshness timestamp.
`[Why: Fogg verifiability; journalist citation workflow. Maria (primary), Dr. Patel. Without stable URLs, the platform is uncitable.]`

**U11. Minimum touch target size: 44×44 CSS pixels. Layouts reflow at 200% zoom without horizontal scroll.**
Interactive elements (buttons, links, toggles, table sort headers) are at least 44×44px. Data tables on narrow viewports convert to a card/list layout rather than requiring horizontal scroll. Body text is minimum 16px and respects the user's system font size preference (iOS Dynamic Type, browser zoom). No layout breaks below 320px viewport width.
`[Why: WCAG 2.1 SC 2.5.5; Holmes persona spectrum. Robert: iPad is his primary device. Mobile is the majority civic access pattern.]`

**U12. Public methodology documentation for every computed metric.**
Every score, flag, confidence value, benchmark, or derived data point links to a methodology page documenting: (a) computation method and formula, (b) input data sources and their freshness, (c) known limitations and edge cases. When methodology changes, previously computed values are annotated with the methodology version under which they were produced. Methodology documentation is public regardless of the data's publication tier.
`[Why: Fogg earned credibility; academic citation standards. Dr. Patel (primary), Maria, James. Trust infrastructure (U1) handles display; this handles documentation.]`

**U13. Low-confidence data does not appear in Layer 1 summary counts or flags.**
Data points with confidence below 90% ("Extracted — review recommended") are available at Layer 2 detail views with their confidence indicator, but do not increment summary-level counts (e.g., "Conflicts flagged: 3"), appear in "Top findings" summaries, or populate summary cards. Promoting low-confidence findings to Layer 1 visibility requires manual review and explicit approval.
`[Why: "Sunlight, not surveillance" — a summary-level flag is a reputation claim. James: "A 'Conflicts flagged: 3' badge has already done its damage by the time anyone sees the confidence warning."]`

**U14. Every profile and finding includes correction and context mechanisms.**
Every official's profile page includes a visible "Submit a correction" link. Every flagged finding about a named official includes a "Provide context" mechanism. Corrections are reviewed within a stated timeframe. Accepted corrections display a visible correction notice with the date. Official context responses are displayed alongside the finding — not hidden behind a click — with a label: "Official response from [Name/Office], [date]." Unresolved disputes display both the platform's finding and the official's response.
`[Why: Fogg "make it easy to contact"; procedural fairness; "sunlight, not surveillance." James (primary), Maria, Dr. Patel. The first uncorrected error becomes the argument against the platform.]`

---

## Component-Level Rules

These apply to specific UI patterns. When building a new instance of any pattern below, follow these constraints.

**C1. Charts: static default must stand alone. Annotations are factual, never interpretive.**
Every chart ships with at least one visible text annotation (not a tooltip) highlighting the most significant data point. The default view tells a story without any user interaction. Filter controls are visible but in a secondary/collapsed position — the chart loads in its annotated default state, not in a "configure your view" state. Annotation content is structured data in the database, not hardcoded strings. Annotations state what the data shows ("Highest quarterly total since 2020"), never what it means ("Unprecedented spending surge"). The platform describes patterns; annotation authors do not editorialize.
`[Why: Aisch interactivity as bonus; Segel & Heer martini glass narrative. Position #8. Maria: "If the platform's annotations editorialize, I can't trust the charts as neutral evidence."]`

**C2. Charts: accessible by construction.**
Every chart includes a "View as table" toggle revealing a `<table>` with proper `<th>`, `<caption>`, and `<tbody>` elements. Categorical data uses color + pattern (hatching, dots, dashes). Bar and line charts use direct labels instead of legends wherever space permits. The chart color palette is tested against protanopia, deuteranopia, and tritanopia with minimum 3:1 contrast between adjacent data series. Zero-baseline on all bar charts.
`[Why: Elavsky accessible redundancy; Holmes persona spectrum; Tufte honest proportions. Position #4.]`

**C3. Data tables: keyboard-navigable, sortable, exportable.**
All data tables are sortable by column. Tab key navigates between interactive elements within the table. A "Download CSV" button is visible in the table toolbar (not behind a menu). Column headers use plain-language labels; the CSV export uses official technical column names with a schema reference. Every table has a `<caption>` describing its contents for screen readers.
`[Why: Shneiderman extract task. Position #5, #6, #10.]`

**C4. `<CivicTerm>`: plain language label + technical tooltip.**
Every domain-specific label (filing categories, legal terms, government jargon) is wrapped in a `<CivicTerm>` component. The visible text is plain language (reading level ~grade 6). The tooltip shows: (1) official term, (2) filing/regulatory category, (3) one-sentence definition. Tooltip content is stored as structured glossary data, not ad hoc strings. Screen readers access the technical term via `aria-describedby`.
`[Why: GOV.UK reading age; NNGroup plain language +124%; Morville & Rosenfeld controlled vocabulary. Position #6. Robert: "Every government website makes me feel stupid."]`

**C5. `<CivicMetric>`: number + benchmark + source + methodology reference.**
Every potentially misleading metric is rendered via a `<CivicMetric>` component that displays: the number, an inline comparison benchmark (average, median, legal limit, or historical baseline), and a source indicator. Benchmarks include their computation method (mean/median), time range, and data source, either inline or as a linked methodology reference. Benchmarks are structured data in the database, not hardcoded. Example: "$50,000 — median for this seat: $35,000 (contested races 2016–2024) · limit: $75,000."
`[Why: Wurman modified; Fogg credibility through context. Position #12. Dr. Patel: "A benchmark without methodology is just a number."]`

**C6. Source attribution badges.**
The `<SourceBadge>` component renders a compact indicator showing source tier (1–4) and freshness ("Updated Mar 10, 2026" or "2 days ago"). Tier 3 sources always include a bias disclosure — e.g., "Richmond Standard (funded by Chevron)." Tier 4 sources display "Community source — not independently verified." Badge is present on every card, table row header, and detail section.
`[Why: Fogg surface credibility; RTP source tier architecture. Position #9. James: even-handed disclosure builds trust.]`

**C7. Navigation: search persists everywhere.**
A search input ("Search a name, address, or topic") is present in the top navigation of every page. Homepage hero is the search bar with 2–3 curated editorial cards below (latest meeting, upcoming election, flagged item). Top nav includes an "Explore" link to the Shneiderman-style overview with filters and facets. The search bar is never more than one interaction away from any page.
`[Why: Van Ham & Perer search-first; Krug satisficing. Position #3.]`

**C8. Confidence indicators.**
When extraction confidence is below 90%, a visible indicator appears next to the data point. Phrasing scale: "Verified" (≥95%), "High confidence" (90–95%), "Extracted — review recommended" (<90%). Confidence is computed during extraction and stored as a numeric field. No data point displays confidence language without a corresponding numeric score in the database. See also U13: data below 90% does not appear in Layer 1 summary counts.
`[Why: Moesta anxiety reduction; Fogg earned credibility. Position #9. James: confidence thresholds gate Layer 1 visibility.]`

---

## Content Rules

These apply to all text, labels, copy, tooltips, and AI-generated content.

**T1. Navigation and page labels use plain language.**
"Money" not "Campaign Finance." "Votes" not "Roll Call Actions." "Meetings" not "Legislative Sessions." "People" not "Officials Index." Technical terms appear only in tooltips (via `<CivicTerm>`), CSV column headers, and API field names — never in navigation, page titles, or section headings.
`[Why: GOV.UK grade 6 reading level. Position #6. Survived unchallenged.]`

**T2. Every metric that could mislead includes an inline benchmark.**
A dollar figure without context can be weaponized. A vote count without turnout context can mislead. Any metric shown publicly that involves money, percentages, or comparisons must include at least one benchmark: an average, median, legal limit, historical baseline, or denominator. Benchmarks are structured data, not editorial strings.
`[Why: Wurman understanding accompanies action; "sunlight, not surveillance." Position #12. James: benchmarks protect officials and the public equally.]`

**T3. Bias disclosure is mandatory for Tier 3 sources, automatic and consistent.**
Every Tier 3 source renders with a parenthetical disclosure. These are stored as structured data attached to the source entity. Examples: "Tom Butt E-Forum (council member newsletter)." "Richmond Standard (funded by Chevron Richmond)." Disclosure text uses the same phrasing every time the source appears — no ad hoc rewording.
`[Why: Fogg earned credibility; RTP source tier convention. Survived unchallenged.]`

**T4. AI-generated summaries use hedged, factual language.**
AI summaries never state opinions or make characterizations. Use: "The motion passed 5-2" not "The motion easily passed." Use: "Three speakers opposed the project" not "The project faced significant opposition." Use: "Council Member X voted differently from their stated position on [date]" not "Council Member X contradicted themselves." The platform describes patterns; it does not characterize them.
`[Why: RTP "sunlight, not surveillance" principle. James: "This is the rule that matters most to me."]`

**T5. Tooltip content is structured and consistent.**
Every `<CivicTerm>` tooltip pulls from a centralized civic glossary (database-backed). Tooltip format is fixed: **Line 1:** Official term. **Line 2:** Filing or regulatory category. **Line 3:** One-sentence plain-language definition. Tooltips are never written inline as one-off strings. If a term doesn't exist in the glossary, it gets added to the glossary — it doesn't get an ad hoc tooltip.
`[Why: Morville & Rosenfeld controlled vocabulary; Norman consistent signifiers. Position #6.]`

**T6. Page composition does not create accusatory framing.**
A page can be factually accurate in every individual data point but still misleading through selection and arrangement. Profile pages for named officials must not lead with conflict flags, negative findings, or anomaly counts before establishing baseline context (role, district, tenure, meeting attendance). The visual hierarchy of a profile page presents identity and role context first, activity data second, and flagged findings third — each with full attribution and benchmarks. No summary card for a named official leads with a conflict count as its primary metric.
`[Why: Compositional framing is as important as sentence-level framing. James: leading with "Conflicts flagged: 3" creates an accusatory frame even when every individual element is neutral.]`

**T7. Narrative over numbers.**
Public-facing output defaults to short, plain-language descriptions of what happened and why it may matter — not data visualizations, charts, graphs, bar charts, color-coded displays, or raw statistics. Numbers appear only when materially important to understanding (dollar amounts, vote counts, dates). Technical precision and quantitative detail remain available on interaction (click/expand), not as the primary presentation layer. The design assumption is that any number or visualization *will* be stripped of context and misrepresented; narrative descriptions carry their own context. This is responsible information dissemination — design to protect against decontextualization.
`[Why: Numbers without context are noise. Visualizations are the worst medium for civic accountability — they get screenshotted, decontextualized, and weaponized. A narrative sentence is harder to misrepresent because the context travels with the claim. Design principle: assume content will be consumed by people acting in bad faith with no data literacy. Protect against decontextualization by making the context inseparable from the claim.]`

---

## Accessibility Rules

_Consolidated from across all categories for audit purposes. These overlap with rules above by design — this section exists so an accessibility audit can check a single list._

**A1. Semantic HTML and component library compliance.**
Every interactive element uses shadcn/ui + Radix UI primitives. No custom `<div onClick>` reimplementations. Every page has correct heading hierarchy (h1 → h2 → h3, no skipped levels). All form inputs have associated `<label>` elements. All images have `alt` text (decorative images use `alt=""`).
`[Source: U2. WCAG 2.1 SC 1.1.1, 1.3.1, 4.1.2.]`

**A2. Color and contrast.**
All text meets WCAG AA contrast (4.5:1 body text, 3:1 large text and UI components). Color is never the sole means of conveying information — always pair with pattern, shape, or label. Chart color palettes are tested against protanopia, deuteranopia, and tritanopia with minimum 3:1 contrast between adjacent data series. All focus indicators meet 3:1 contrast against adjacent colors.
`[Source: U2, C2. WCAG 2.1 SC 1.4.3, 1.4.1, 2.4.7.]`

**A3. Keyboard and focus management.**
All interactive elements are keyboard-accessible. Tab order is logical. When content changes dynamically (accordion expand, search results load, filter applied, error state, modal open/close): (a) focus moves to the new content or a summary of the change, (b) the focus target is documented per component. Focus is never lost (no focus sent to `<body>` after a dynamic update). Modals trap focus and return it to the trigger on close. Skip-to-content links are present on every page.
`[Source: U2. Dorothy: principles need teeth. WCAG 2.1 SC 2.4.3, 2.4.7, 2.1.1.]`

**A4. ARIA live regions and motion.**
Loading states use `aria-live="polite"` with descriptive text. Error states use `role="alert"`. Filter updates announce result counts via `role="status"`. All motion respects `prefers-reduced-motion`. No information is conveyed solely through animation.
`[Source: U9 extended. Dorothy: a skeleton loader is silence for VoiceOver without a live region. WCAG 2.1 SC 4.1.3, 2.3.3.]`

**A5. Touch targets and responsive reflow.**
Minimum interactive target size: 44×44 CSS pixels. Layouts reflow at 200% zoom without horizontal scrolling. Data tables convert to card/list layouts on narrow viewports. Body text minimum 16px, respects system font size preferences. No layout breaks below 320px viewport width.
`[Source: U11. WCAG 2.1 SC 2.5.5, 1.4.10.]`

**A6. Chart and data table accessibility.**
Every chart includes a "View as table" toggle with proper `<th>`, `<caption>`, and `<tbody>`. Categorical data uses color + pattern. Direct labels instead of legends where space permits. Every data table has a `<caption>`, is keyboard-navigable, and has a visible "Download CSV" button.
`[Source: C2, C3. Elavsky accessible redundancy.]`

---

## Conflict Resolution

If two rules seem to conflict during implementation, apply this priority order:

1. **Trust infrastructure** (U1, C6, C8, U12, U14) — without trust, nothing else matters
2. **Accessibility** (U2, A1–A6) — legal requirement and curb-cut multiplier
3. **Plain language** (C4, T1) — comprehension drives adoption
4. **Non-adversarial framing** (T4, T6, U13) — collaborative transparency is load-bearing
5. **Scannability** (U3, U4) — don't overwhelm the entry layer
6. **Information density** (U5, C3) — serve the power user at deeper layers
7. **Aesthetics** (U7) — important but never at the cost of the above

---

## Changelog — Persona Feedback Incorporation

### Accepted

| Change | Source | Reasoning |
|--------|--------|-----------|
| **U3 amended**: visual hierarchy within 3 KPIs — dominant metric larger, subordinate metrics smaller | Robert | Good refinement. Three equal-weight numbers still require scanning; a clear primary metric reduces cognitive load. |
| **U9 amended**: ARIA live regions added for all state changes | Dorothy | Without live regions, loading/error/filter states are invisible to screen readers. The principle of U9 was correct but the implementation spec was incomplete. |
| **U10 added**: permanent URLs, URL-encoded filter state, citation strings | Maria, Dr. Patel | Without stable URLs, the platform is uncitable. Journalists and researchers — our highest-value distribution channels — depend on this. |
| **U11 added**: touch targets, responsive reflow, minimum text size | Robert, Dorothy | Mobile is the majority civic access pattern. The original rules assumed desktop-first interaction. |
| **U12 added**: public methodology documentation for computed metrics | Dr. Patel, Maria, James | Trust infrastructure (U1) handles display of provenance; this handles documentation of how provenance is generated. Three expert personas independently identified this as the biggest gap. |
| **U13 added**: low-confidence data excluded from Layer 1 summaries | James | A summary-level flag is a reputation claim. Gating Layer 1 visibility on confidence thresholds prevents the platform from making unverified accusations at the headline level. Directly serves "sunlight, not surveillance." |
| **U14 added**: correction and official response mechanisms | James, Maria, Dr. Patel | The first uncorrected error becomes the argument against the platform. Without this, even best-intentioned transparency becomes adversarial. |
| **C1 amended**: annotations must be factual/descriptive, never interpretive | Maria | Aligns with T4. "Most newsworthy" is editorial language; "most significant data point" with factual description is neutral. |
| **C5 amended**: benchmarks must include methodology reference | Dr. Patel | A benchmark without methodology is uncitable. Extends the structured data principle already in C5. |
| **T6 added**: page composition must not create accusatory framing | James | T4 governs sentence-level language; T6 governs page-level arrangement. A profile page that leads with conflict counts before role context creates adversarial framing even when every individual element follows the rules. |
| **A1–A6 consolidated**: accessibility section added for audit purposes | Dorothy, structural | Rules were scattered across U2, C2, C3, U9. Consolidation enables a single-pass accessibility audit without cross-referencing. |
| **T7 added**: narrative over numbers for public-facing output | Phillip | Numbers and visualizations get decontextualized and misrepresented. Short narrative descriptions carry their own context. Technical precision available on click, not as primary presentation. |

### Rejected

| Suggestion | Source | Reasoning |
|------------|--------|-----------|
| Cross-entity query rules (search donations ↔ votes ↔ meetings) | Maria | Valid feature requirement, but this is a feature spec — not a design rule. Belongs in a sprint backlog item for cross-referencing tools. Design rules govern how results are displayed, not what queries the system supports. |
| Embed codes and screenshot-friendly chart export | Maria | Good idea, but a feature spec. Charts following C1 (annotated defaults) and C2 (accessible construction) are already screenshot-friendly by design. Embed codes belong in a feature backlog. |
| Bulk data access and API documentation standards | Dr. Patel | Already covered by existing architecture conventions (API schema requires source fields per U1). API documentation standards belong in an API spec, not the design rules. |
| "Find my council member" as a named entry point rule | Robert | Already addressed by Position #3 (search-first with address lookup) and C7 (search persists everywhere). The search bar accepts addresses. This is an implementation detail of C7, not a separate rule. |
| Data versioning with DOI-like persistent identifiers | Dr. Patel | Valuable long-term but premature for Phase 2 scope. U10 (permanent URLs) and U12 (methodology versioning) cover the critical citation needs. Full dataset versioning belongs in a `DATA-LIFECYCLE-SPEC.md` when the platform has enough data history to warrant it. |

---

## Rules Considered But Not Included

**"No page may display more than 3 data visualizations without user-initiated expansion."**
Too rigid. Layer 2 detail pages legitimately need 4–5 simultaneous panels for cross-referencing. The progressive disclosure architecture (Position #2) already handles this. *Promote if Layer 2 pages feel overwhelming in testing.*

**"Every page must render meaningfully within 2 seconds on a 3G connection."**
Performance requirement, not a design rule. Belongs in a performance budget spec. *Promote when adding a performance spec.*

**"Color palette limited to 5 semantic tokens plus 3 data-visualization accent colors."**
Premature. The right number depends on how many data categories charts need to distinguish. *Promote if chart color proliferation becomes a problem.*

**"Every page includes a 'Report an error' link in the footer."**
Feature spec, not design rule. Now partially addressed by U14's correction mechanism. *Remainder belongs in sprint backlog.*

**"Summary text ('so what?') required above every data table and chart."**
Conflicts with Position #8's annotation approach. C1's in-chart annotations are the "so what?" *Promote if user testing reveals annotations alone aren't sufficient.*

**"DATA-LIFECYCLE-RULES.md covering versioning, correction, citation, methodology, and official response."**
The pressure test synthesis correctly identified that the rules are strongest on rendering and weakest on post-rendering lifecycle. U10, U12, and U14 address the highest-priority lifecycle gaps. A dedicated lifecycle spec is warranted when the platform has production data and active external users. *Promote after public launch.*
