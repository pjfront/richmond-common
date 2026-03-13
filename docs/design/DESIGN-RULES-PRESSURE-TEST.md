# Design Rules Pressure Test — Persona Simulation

_Five personas react to `DESIGN-RULES.md` as a governing document. Testing the rules themselves, not a UI._

---

## 1. Maria, 34 — Investigative Journalist, Richmond Confidential

_Reads the rules asking: "Will this help me break a story or get in my way?"_

### Top 3 Things She Appreciates

1. **U1 (Source attribution on every data point)** — "This is the single most important rule for me. If I'm writing about a council member's voting pattern and citing your platform, I need to know *exactly* where the number comes from. Source link + timestamp + tier badge means I can verify your work before I stake my byline on it. Most civic data tools skip this."

2. **U5 (2 clicks from summary to raw data) + C3 (CSV export visible in toolbar)** — "You had me at 'never behind a kebab menu.' Every data tool I use buries export three menus deep. The fact that you've made a *rule* that export must be visible in the toolbar tells me someone on this project actually uses data for work."

3. **C1 (Charts with visible annotations, not tooltip-dependent)** — "The annotation approach is smart. When I screenshot a chart for my editor, tooltips disappear. A chart that tells its story without interaction means I can screenshot it and the context survives. That said — I have a concern about this one too (see below)."

### Top 3 Gaps or Concerns

1. **No permalink / stable URL rule.** I cite specific findings in articles. URLs that break when you redesign, or dynamic views with no shareable state, make the platform worthless for citation. I need: (a) every detail page has a permanent URL that won't change, (b) filtered/sorted views are URL-encoded so I can share an exact state, and (c) URLs contain human-readable slugs, not just IDs.

2. **No embed or screenshot-friendly output rule.** U5 handles export to CSV, but I also need to *show* a chart in my article or embed a live widget. The rules say nothing about: static image export from charts, embed codes for visualizations, or print-friendly/reader-mode rendering. If I have to screenshot a chart, I need it to look publication-ready without the surrounding chrome.

3. **No cross-entity query rules.** The rules handle individual data points well, but investigative journalism is about *connections*. I need to search "show me every vote where Council Member X voted yes AND Donor Y gave >$500 to their campaign in the preceding 6 months." The rules don't address cross-entity search, saved queries, or relationship views. U5 assumes a linear path (summary → detail → raw), but my workflow is lateral (donation table ↔ vote table ↔ meeting record).

### One Rule She'd Change

**C1** — Add: "Annotation content must be descriptive and factual, never interpretive. Annotations state what the data shows ('Highest single-quarter total since 2020'), not what it means ('Unprecedented spending surge')."

Maria's reasoning: "I appreciate structured annotations, but 'most newsworthy data point' is editorial language. Who decides what's newsworthy? If the platform's annotations editorialize, I can't trust the charts as neutral evidence. I want the platform to *describe* patterns and let me decide what's newsworthy."

### One Rule She'd Add

> **U10. Every detail page and filtered view has a permanent, shareable URL.**
> Detail pages use human-readable slugs (`/people/eduardo-martinez` not `/entity/47291`). Filter state, sort order, and date ranges are encoded in URL parameters. URLs are versioned — if a page is restructured, old URLs redirect to the new location. Every page includes an "Copy link" affordance. Citation format: the page footer includes a pre-formatted citation string (APA or AP style) that includes URL, access date, and data freshness timestamp.
> `[Journalist workflow. Fogg: verifiability. Position #5 extended.]`

### Overall Verdict

"If you build the cross-referencing and stable URLs, this becomes the best civic data tool I've ever used. Without them, I'll use it for leads but still have to do all the real work in spreadsheets."

---

## 2. Robert, 67 — Retired Richmond Resident, iPad User

_Reads the rules asking: "Will I be able to use this without asking my daughter for help?"_

### Top 3 Things He Appreciates

1. **T1 (Plain language navigation)** — "'Money' instead of 'Campaign Finance.' 'Votes' instead of 'Roll Call Actions.' Thank God. Every government website I visit makes me feel stupid. If you actually follow this rule, I might use this more than once."

2. **C4 (CivicTerm component)** — "So the regular words are what I see, but if I want the official term, I can tap and get it? That's perfect. I don't need to know the jargon to understand what's happening, but if I want to write a letter to the council I can use the right terminology."

3. **U6 (No onboarding, no interstitials)** — "I've closed so many apps that made me go through a tutorial before letting me do anything. The fact that this is a *rule* — 'No Welcome to... splash text' — that's someone who understands that I just want to look up my council member, not learn your whole system."

### Top 3 Gaps or Concerns

1. **No minimum text size rule.** U2 requires WCAG AA contrast but says nothing about minimum font size. On an iPad, I increase text size system-wide. The rules don't mention: minimum body text size, whether the layout respects iOS Dynamic Type / browser zoom, or whether text reflows properly at larger sizes. "WCAG AA" means nothing to me — I need to know the text will be big enough to read.

2. **No "find my council member" entry point rule.** C7 puts a search bar everywhere, which is great. But my actual first question is always "What has *my* council member done?" I don't know their name half the time — I know my address. The rules don't guarantee an address-based lookup that says "You live in District 3. Your council member is [name]. Here's what they've been doing." That's the one interaction that would keep me coming back.

3. **No mobile/touch interaction rules.** The rules mention keyboard navigation (C3) and screen readers (U2) but say nothing about touch targets, swipe gestures, or tablet-specific layout. I use my iPad for everything. Buttons that are too small, text that requires pinch-to-zoom, or tables that scroll off-screen horizontally without any indication — these are the things that make me give up. "Responsive design" should be a rule, not an assumption.

### One Rule He'd Change

**U3 (Maximum 3 KPIs per summary card)** — Change to: "Summary cards display 3 KPIs maximum, with the single most important number visually dominant (larger font, top position). The other two KPIs are visually subordinate."

Robert's reasoning: "Three numbers on a card is fine, but if they're all the same size and weight, I still don't know where to look. Make one of them the big one. If my council member voted 47 times, I want '47 votes' to be the thing I see first — then the two context numbers can be smaller underneath."

### One Rule He'd Add

> **U11. Minimum touch target size: 44×44 CSS pixels. All layouts reflow at 200% zoom without horizontal scrolling.**
> Interactive elements (buttons, links, toggle switches, table sort headers) are at least 44×44px per WCAG 2.1 SC 2.5.5. Data tables on narrow viewports reflow to a card/list layout rather than requiring horizontal scroll. Body text is minimum 16px and respects the user's system font size preference. No layout breaks below 320px viewport width.
> `[WCAG 2.1 SC 2.5.5. Holmes: persona spectrum. Robert's iPad workflow.]`

### Overall Verdict

"If the text is big enough and I can find my council member by typing my address, I'll use this every week. If I have to pinch and zoom or figure out which district I'm in, I'll never come back."

---

## 3. Dr. Ananya Patel, 41 — Policy Researcher, UC Berkeley Goldman School

_Reads the rules asking: "Can I trust this data enough to cite it in a peer-reviewed paper?"_

### Top 3 Things She Appreciates

1. **C8 (Confidence indicators with numeric scores)** — "This is rare and essential. Most platforms present extracted data as if it's ground truth. The fact that you store confidence as a numeric field and display it with calibrated language ('Verified' ≥95%, 'Extracted — review recommended' <90%) means I can make informed decisions about which data points are reliable enough to cite. Crucially, you require the numeric score to exist *before* the label can display — no hand-waving."

2. **U8 (AI-generated content always identified)** — "For any academic citing this platform, knowing which content was AI-extracted versus directly sourced from official records is non-negotiable. If I'm citing a vote count from certified minutes, that's one thing. If I'm citing an AI-generated summary of a meeting, I need to disclose that in my methodology section. This rule makes that possible."

3. **C5 (CivicMetric with benchmark and source)** — "Benchmarks stored as structured data, not editorial strings — this means I can evaluate whether your benchmarks are methodologically sound. If you're comparing a candidate's fundraising to 'the average for this seat,' I need to know: average over what time period? Adjusted for inflation? Median or mean? The fact that this is a component with structured fields rather than a freeform label suggests the methodology can be documented."

### Top 3 Gaps or Concerns

1. **No methodology documentation rule.** The rules require *displaying* confidence scores, source tiers, and benchmarks — but say nothing about *documenting how they're computed*. For academic citation, I need: a public methodology page explaining how extraction confidence is calculated, how conflict-of-interest flags are generated, what matching algorithms connect donors to officials, and what the false positive/negative rates are. C8 is the display layer; I need the documentation layer.

2. **No data versioning or changelog rule.** If I cite a data point on March 1 and you re-extract the same meeting minutes with an improved prompt on March 15, the data could change. The rules don't address: data versioning (can I access the version I cited?), changelogs (what changed and when?), or DOI-like persistent identifiers for datasets. Academic citation requires that the cited data remains accessible and unchanged at the cited URL.

3. **No bulk data access or API documentation rule.** U5 provides CSV download per table, and C3 makes export visible. But I need: bulk download of entire datasets (all votes 2020–2025), API access with rate limits and documentation, data dictionaries defining every field, and machine-readable formats (JSON, Parquet, not just CSV). The rules treat data access as a per-view affordance. Research requires dataset-level access.

### One Rule She'd Change

**C5 (CivicMetric)** — Add: "Every benchmark includes its methodology reference: computation method (mean, median, percentile), time range, population scope, and data source. Methodology references link to a public methodology page. Example: '$50,000 — median for this seat: $35,000 (median of contested races 2016–2024, NetFile data) · limit: $75,000.'"

Dr. Patel's reasoning: "A benchmark without methodology is just a number. '$35,000 average' is meaningless if I don't know whether it's mean or median, whether it includes uncontested races, or what time period it covers. The rule already requires benchmarks to be structured data — extend that structure to include provenance."

### One Rule She'd Add

> **U12. Public methodology documentation for every computed metric.**
> Every score, flag, confidence value, benchmark, or derived data point links to a methodology page documenting: (a) computation method and formula, (b) input data sources and their freshness, (c) known limitations and edge cases, (d) version history of the methodology itself. Methodology pages are versioned alongside the data. When a methodology changes, previously computed values are flagged as "computed under methodology v[N]." This documentation is public regardless of the data's publication tier.
> `[Academic citation standards. Fogg: earned credibility. Position #9 extended for expert users.]`

### Overall Verdict

"The trust infrastructure (U1, C8, U8) is stronger than anything else in the civic data space. Add methodology documentation and data versioning, and I'd build a research project around this platform. Without them, I'd use it for leads but re-verify everything independently — which defeats the purpose."

---

## 4. Dorothy, 78 — Richmond Resident, Screen Magnifier + VoiceOver

_Reads the rules asking: "Do these rules guarantee I can actually use this, or am I an afterthought?"_

### Top 3 Things She Appreciates

1. **U2 (Accessibility is infrastructure, not a feature)** — "The sentence 'There is no separate accessible mode. The default *is* the accessible version' — that's the most important sentence in this entire document. I've used too many websites where 'accessible mode' strips out everything useful and gives me a dumbed-down version. The fact that this is Rule #2, not a footnote, tells me the developer actually cares."

2. **C2 (Charts with table toggle, pattern + color, direct labels)** — "A chart I can't see is a chart that doesn't exist. The 'View as table' toggle with proper `<th>`, `<caption>`, and `<tbody>` means VoiceOver can actually read the data. Color + pattern for categories means my screen magnifier's high-contrast mode won't make categories indistinguishable. Direct labels instead of legends means I don't have to cross-reference a color key I can barely see."

3. **C3 (Keyboard-navigable, sortable tables with captions)** — "Tab key navigation between interactive elements — this is basic but so many sites get it wrong. The `<caption>` requirement means VoiceOver announces what the table contains before I start navigating cells. These aren't exciting rules, but they're the ones that determine whether I can use the site at all."

### Top 3 Gaps or Concerns

1. **No focus management rule for dynamic content.** U6 says accordions expand inline. C7 has search everywhere. But what happens to keyboard focus when: an accordion expands (does focus move to the new content or stay on the trigger?), search results load (does focus move to the results or stay in the search box?), a filter changes the table content (does screen reader announce the update?), or an error state replaces content (does focus move to the error message?)? Without explicit focus management rules, every dynamic interaction is a potential dead end for keyboard/screen reader users.

2. **No ARIA live region rule.** When data loads asynchronously, filters update a table, or an error appears, screen readers need to be notified. The rules don't mention `aria-live`, `role="status"`, or `role="alert"` for any dynamic content. U9 (loading/empty/error states) defines what to *show* but not how to *announce* state changes to assistive technology. A loading skeleton is visually clear but invisible to VoiceOver unless it has an `aria-live` region with "Loading results…" text.

3. **No animation/motion reduction rule.** If charts animate on load, accordions slide open, or loading skeletons pulse — none of that is harmful to sighted users, but it can cause nausea or disorientation for users with vestibular disorders. The rules should require that all motion respects `prefers-reduced-motion` and that no information is conveyed solely through animation.

### One Rule She'd Change

**U9 (Loading, empty, and error states)** — Add: "Loading, empty, and error states are announced to assistive technology via `aria-live` regions. Loading states use `aria-live='polite'` with descriptive text ('Loading campaign finance data…'). Error states use `role='alert'` to ensure immediate announcement. When content updates after a filter change, the result count is announced via a `role='status'` region ('Showing 12 of 47 results')."

Dorothy's reasoning: "The visual design of these states sounds thoughtful. But I'm using VoiceOver. A skeleton loader that matches the loaded layout is great for sighted users — for me, it's silence unless there's an announcement. And if an error replaces content, I won't know unless focus moves to it or it's in a live region."

### One Rule She'd Add

> **U13. Focus management follows a documented, testable pattern.**
> When content changes dynamically (accordion expand, search results load, filter applied, error state, modal open/close): (a) focus moves to the new content or a summary of the change, (b) the focus target is documented per component, (c) focus is never lost (no focus sent to `<body>` after a dynamic update). Modals trap focus and return it to the trigger on close. Skip-to-content links are present on every page. All focus indicators are visible and meet 3:1 contrast against adjacent colors. The focus management pattern for each component is listed in the component spec and tested with keyboard-only navigation.
> `[WCAG 2.1 SC 2.4.3 Focus Order, SC 2.4.7 Focus Visible. Norman: gulf of evaluation for non-visual users.]`

### Overall Verdict

"These rules are better than 95% of what I encounter on the web. U2 as a principle is exactly right. But principles need teeth — add focus management and ARIA live regions, and I can actually *rely* on this site instead of just *hoping* it works."

---

## 5. James, 45 — Richmond City Communications Director

_Reads the rules asking: "Is this a tool that helps us or one that's designed to embarrass us?"_

### Top 3 Things He Appreciates

1. **T4 (Hedged, factual language — no characterizations)** — "This is the rule that matters most to me. 'Council Member X voted differently from their stated position' instead of 'contradicted themselves' — that's the difference between a transparency tool and an opposition research platform. The fact that this is an enforceable rule and not a suggestion means the developer understands the political dynamics at play."

2. **T2 (Every misleading metric includes a benchmark)** — "Dollar figures without context are the single biggest source of manufactured outrage in local politics. A $50,000 donation sounds scandalous until you see the average is $35,000 and the limit is $75,000. The benchmark requirement protects the public *and* protects officials from misrepresentation. This is genuinely pro-transparency, not gotcha journalism."

3. **C6 + T3 (Source badges with mandatory bias disclosure)** — "The Richmond Standard disclosure ('funded by Chevron Richmond') tells me this platform is willing to label biased sources as biased — regardless of political direction. If you're disclosing bias on Chevron-funded media, you're also implicitly promising to disclose bias on the progressive side. That even-handedness is what separates a transparency tool from an advocacy tool."

### Top 3 Gaps or Concerns

1. **No error correction or dispute mechanism.** What happens when the platform gets something wrong? AI extraction (U8) will make mistakes. Confidence scores (C8) will sometimes say "High confidence" about incorrect data. The rules define how errors are *displayed* (C8's confidence levels) but not how errors are *corrected* after publication. Officials need: a way to flag factual errors with evidence, a documented response process with a timeline, a visible correction notice when errors are fixed (not silent edits), and an indication of whether disputed data points have been reviewed. Without this, a single high-profile error could permanently damage the platform's reputation *and* the city's trust in it.

2. **No rule about how findings are framed in aggregate.** T4 handles individual data point language. But what about page-level or section-level framing? A council member's profile page could be factually accurate in every data point but still create a misleading impression through *selection and arrangement*. If the page leads with "Conflicts flagged: 3" before showing any positive information, the visual hierarchy creates an accusatory frame even though every individual rule is followed. The rules don't address compositional framing — the overall story a page tells through the *ordering* of its truthful components.

3. **No "official response" integration rule.** When the platform surfaces a potential conflict of interest, the official has no way to provide context. Maybe there's a legitimate reason a council member voted on a project after receiving a donation from the developer — perhaps they consulted the city attorney and received clearance. The rules require displaying *data* but have no mechanism for displaying the *official's response to that data*. Without this, the platform tells one side of every story while claiming to be neutral.

### One Rule He'd Change

**C8 (Confidence indicators)** — Add: "Data points with confidence below 90% ('Extracted — review recommended') must not be included in any aggregated counts, flags, or summary statistics visible at Layer 1 (public summary cards). Low-confidence data is available at Layer 2 detail views with its confidence indicator, but it does not increment counts like 'Conflicts flagged: 3' or appear in 'Top findings' summaries. Promoting low-confidence findings to summary-level visibility requires manual review and explicit approval."

James's reasoning: "A 'Conflicts flagged: 3' badge on a council member's card is a reputation-affecting claim. If one of those three flags is based on a sub-90% confidence extraction that happens to be wrong, the summary card has already done its damage by the time anyone clicks through to see the confidence warning. Low-confidence data should exist at the detail level but never bubble up to the headline level."

### One Rule She'd Add

> **U14. Every profile and finding includes an accessible correction/context mechanism.**
> Every official's profile page includes a clearly visible "Submit a correction" link. Every flagged finding (conflict of interest, voting pattern, financial disclosure) includes a "Provide context" link that allows the named official (or their designee) to submit a response. Submitted corrections are reviewed within a stated timeframe. Accepted corrections display a visible correction notice with the date of correction. Official context responses are displayed alongside the finding (not hidden behind a click) with a label: "Official response from [Name/Office], [date]." Unresolved disputes display both the platform's finding and the official's response. This mechanism is visible at every publication tier.
> `[Fogg: make it easy to contact the organization. "Sunlight, not surveillance" principle. Procedural fairness.]`

### Overall Verdict

"The language rules (T4, T2) are exactly right, and they're what would make me cautiously support this rather than fight it. But without an error correction process and a way for officials to provide context, even the best-intentioned platform becomes adversarial the first time it gets something wrong."

---

## Synthesis

### Critical Gaps — Raised by 3+ Personas (Fix Before Finalizing)

**1. No methodology / provenance documentation rule (Maria, Dr. Patel, James)**
All three expert users need to understand *how* data is computed, not just *that* it's displayed with source attribution. Maria needs to verify before publishing. Dr. Patel needs it for academic citation. James needs it to evaluate whether flagged findings are methodologically sound before responding to public inquiries. This is the single biggest gap in the rules — the trust infrastructure (U1, C6, C8) handles *display* of credibility signals but not *documentation* of how those signals are generated.

**Recommendation:** Promote the "Cut" rule about methodology or create a new U-level rule requiring public methodology documentation for every computed metric, score, flag, and benchmark.

**2. No error correction / dispute mechanism (Maria, James, Dr. Patel)**
Maria needs to know if data has been corrected since she last cited it. James needs a way to flag errors with evidence and get a response. Dr. Patel needs version history to ensure cited data is stable. The rules are strong on *presenting* data accurately but silent on what happens when the data is wrong — which it inevitably will be, given AI extraction.

**Recommendation:** Create a new U-level rule covering error reporting, correction process, correction notices, and dispute resolution. This is load-bearing for the "sunlight, not surveillance" positioning — the first uncorrected error becomes the argument against the platform.

**3. No stable URL / data versioning rule (Maria, Dr. Patel, Robert implicitly)**
Maria needs permalinks for citation. Dr. Patel needs versioned datasets. Even Robert benefits from bookmarkable pages for his council member. The rules treat data access as a per-session activity but don't address the persistence layer — what happens when you come back tomorrow, or when you cite a URL in an article that needs to work six months later.

**Recommendation:** Create a new U-level rule requiring permanent URLs, URL-encoded view state, and data version identifiers. Consider whether this belongs alongside U5 (raw data access) or as a standalone rule.

### Persona-Specific Gaps — Raised by 1 Persona but High Severity

**Dorothy: Focus management and ARIA live regions** — Severity is high because without these, the accessibility infrastructure (U2) becomes aspirational rather than functional. The *principle* of U2 is exactly right, but the *implementation requirements* need focus management, live regions, and motion reduction to be complete. If these are missing, Dorothy can't use the site despite U2's promise. Recommend adding these as sub-rules under U2 or as a new component-level rule.

**James: Compositional framing / aggregate impression** — T4 prevents characterization at the sentence level, but a page that leads with "Conflicts flagged: 3" before any other information creates an accusatory frame even when every individual element follows the rules. This is a subtle design problem — the rules govern *components* but not *page composition*. Recommend adding a content rule about the ordering of information on profile pages, or a principle about "neutral composition."

**Robert: Touch targets and responsive behavior** — The rules assume a desktop-first interaction model (keyboard navigation, click-based interactions). An explicit mobile/touch rule would serve not just Robert but the majority of civic users who access information on phones. Recommend adding as a component-level rule or extending U2.

**Maria: Embed and screenshot-friendly output** — Journalists are a key distribution channel. If charts can't be screenshot-cleanly or embedded, the platform loses its most powerful amplification mechanism. Relatively easy to address with a component rule about chart export.

### Proposed Additions — New Rules Emerging from This Exercise

**1. Methodology Documentation (U12)**
_Motivated by: Dr. Patel (primary), Maria, James_

> Every score, flag, confidence value, benchmark, or derived data point links to a public methodology page documenting computation method, input sources, known limitations, and version history. When methodology changes, previously computed values are annotated.

**2. Error Correction and Official Response (U14)**
_Motivated by: James (primary), Maria, Dr. Patel_

> Every factual claim has a "Submit a correction" path. Every flagged finding about a named official includes a "Provide context" mechanism. Corrections are reviewed within a stated timeframe, display visible correction notices, and never silently alter published data. Official responses display alongside findings, not behind a click.

**3. Permanent URLs and Data Versioning (U10)**
_Motivated by: Maria (primary), Dr. Patel_

> Every detail page has a permanent URL with human-readable slugs. Filter/sort state is URL-encoded and shareable. Data versions are timestamped and accessible. Citation format strings are available on every page. Old URLs redirect rather than 404.

**4. Focus Management for Dynamic Content (U13)**
_Motivated by: Dorothy (primary)_

> All dynamic content changes (accordion, filter, search, error) follow documented focus management patterns. ARIA live regions announce state changes. All motion respects `prefers-reduced-motion`. Focus indicators are visible and meet 3:1 contrast.

**5. Touch Target and Responsive Layout (U11)**
_Motivated by: Robert (primary), Dorothy (secondary benefit)_

> Minimum touch targets of 44×44px. Layouts reflow at 200% zoom without horizontal scroll. Data tables convert to card layouts on narrow viewports. Body text minimum 16px, respects system font size preferences.

### Rules That Survived Cleanly — Strongest Foundations

These rules were appreciated by multiple personas and challenged by none:

| Rule | Why it survived |
|------|----------------|
| **U1** (Source attribution) | Every persona valued this. Maria for citation, Robert for trust, Dr. Patel for verification, Dorothy implicitly (structured data is screen-reader-parseable), James for accuracy-checking. |
| **U2** (Accessibility as infrastructure) | Dorothy praised it explicitly. No persona wanted it weakened. The principle is unassailable — the implementation details need extension (focus management, live regions) but the rule itself is solid. |
| **U6** (No interstitials or onboarding) | Robert and Maria both appreciated this. No persona wanted gated access. |
| **U8** (AI content always identified) | Dr. Patel and James both depend on this. No persona wanted AI content to be unmarked. |
| **T1** (Plain language navigation) | Robert praised it directly. No persona wanted more jargon. |
| **T3** (Mandatory bias disclosure for Tier 3) | James appreciated the even-handedness. Maria implicitly depends on it. No persona challenged the Chevron disclosure. |
| **T4** (Hedged, factual language) | James called it the most important rule for him. Maria's "newsworthy annotation" concern is adjacent but doesn't challenge T4 itself. |
| **C4** (CivicTerm) | Robert loved it. Dr. Patel benefits from the structured glossary. No conflicts. |
| **Conflict Resolution hierarchy** | No persona challenged the priority order. Trust > Accessibility > Plain Language > Scannability > Density > Aesthetics held up under all five lenses. |

### One Pattern Worth Noting

The rules are strongest on **what to display** and weakest on **what happens after display**. The entire document is oriented around rendering data correctly — source attribution, confidence, benchmarks, plain language, accessibility. But every persona who interacts with data *professionally* (Maria, Dr. Patel, James) raised concerns about the lifecycle *beyond* rendering: citation stability, methodology documentation, error correction, data versioning, official response. The rules treat data as a one-directional output. The missing layer is the *feedback loop* — what happens when the data is wrong, when it changes, when someone needs to cite it six months later, or when the subject of a finding wants to respond.

This isn't a design flaw — it's a scope boundary. The rules document correctly focuses on UI rendering conventions. But the gaps suggest a companion document is needed: something like `DATA-LIFECYCLE-RULES.md` covering versioning, correction, citation, methodology, and official response. That document would complete the trust infrastructure that `DESIGN-RULES.md` starts.
