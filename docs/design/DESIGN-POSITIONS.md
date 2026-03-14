# RTP Design Positions: Tension Resolutions

_Principled positions on 12 design conflicts, grounded in RTP's users and mission. These are binding decisions for Phase 2 frontend development — not suggestions._

---

## 1. Tufte's Minimalism vs. Norman's Aesthetic-Usability Effect

**The tension:** Tufte says remove every pixel that doesn't encode data. Norman (backed by Bateman et al. 2010) says visual polish makes interfaces feel more usable and improves recall. For any given design element — a subtle gradient, rounded corners on a card, a colored background on a section — these frameworks give opposite instructions.

**Position: Norman wins at the page level. Tufte wins inside charts.**

RTP is a civic trust platform, not a Bloomberg Terminal. The 50-millisecond credibility judgment (Fogg) happens before anyone reads a number. A visually austere interface signals "government database" — which citizens associate with frustration, not reliability. Norman's aesthetic-usability effect is the stronger force for RTP because our primary adoption barrier is nonconsumption: people currently hire *nothing* to understand their city government. They won't push through an ugly interface to get data they didn't know they wanted.

But inside individual charts and visualizations, Tufte's discipline applies. Once a user is looking at a campaign finance bar chart, decorative gradients and 3D effects introduce lie factor risk. The chart interior is where data-ink ratio matters; the page surrounding the chart is where aesthetic warmth matters.

**The boundary:** Chrome, cards, layout, navigation, and page-level containers follow Norman — they should feel polished, warm, and modern. Chart interiors follow Tufte — no gratuitous decoration inside the data area itself. The axes, labels, and data marks earn their pixels; the card border and section background around them earn theirs through a different justification (trust, scannability, grouping).

**Why this serves RTP's users:**
- The retired citizen on an iPad needs the interface to feel trustworthy at first glance. Institutional austerity reads as "this probably doesn't work well" for non-expert users.
- The journalist doesn't care about page aesthetics — but they absolutely care that chart proportions are honest and labels are precise. Tufte inside the chart protects them.
- The screen reader user is unaffected by visual polish either way, so this position doesn't trade off against accessibility.
- The city staffer checking their own records sees a professional product that doesn't look like it was built to embarrass them — which aligns with "sunlight, not surveillance."

**Thinkers:** Norman (aesthetic-usability), Fogg (surface credibility), Tufte (data-ink ratio), Cawthon & Moere (engagement research).

**Practical consequences:**
- shadcn/ui's default component styling is the floor, not the ceiling — it provides adequate surface credibility out of the box. No custom design system is needed in Phase 2.
- Charts use clean white backgrounds, no gradients, no 3D effects, zero-baseline bar charts. Direct labeling instead of legends wherever possible.
- Page sections use subtle background differentiation, card shadows, and enough visual rhythm to feel designed rather than dumped.
- No illustration, mascots, or decorative imagery anywhere. The polish is structural (spacing, typography, consistent cards), not decorative.

---

## 2. Tufte's Data Density vs. Krug's Scanning Behavior

**The tension:** Tufte wants maximum information per square inch — the Bloomberg Terminal ideal, where an expert eye scans a dense screen and spots anomalies. Krug says users scan, satisfice, and click the first reasonable thing — "billboard at 60 mph." A dense council overview with 7 members × 4 metrics violates Krug. A sparse page with one council member and 3 stats violates Tufte.

**Position: Krug wins at the entry layer. Tufte wins at the exploration layer. Neither wins — progressive disclosure mediates.**

This tension dissolves once you accept that density is a function of disclosure depth, not a single design choice. The landing page and summary cards follow Krug: one clear focal point per card, 3 KPIs maximum, scannable in under 5 seconds. The exploration layer — what you see after clicking into a council member or a meeting — follows Tufte: dense, faceted, multi-panel, designed for the user who has already committed attention.

Krug is right that most visitors are scanning. But Krug's model was built for e-commerce and content sites where users visit once, complete a task, and leave. RTP has a secondary user class — journalists, researchers, and engaged citizens — who visit repeatedly and build expertise. For them, Krug's billboard model is patronizing. The answer isn't to pick one; it's to let depth of engagement determine density.

**The boundary:** Layer 1 (summary views, landing page, address lookup results) = Krug. Maximum 3 metrics per card, one focal point per section, aggressive whitespace. Layer 2 (entity detail pages, meeting explorer, campaign finance drill-down) = Tufte. Small multiples, sparklines in table cells, faceted filtering, denser layout. Layer 3 (raw data, API, download) = pure density for researchers.

**Why this serves RTP's users:**
- The retired citizen sees 3 numbers about their council member on a clean card. They don't need to process 20 data dimensions.
- The journalist clicks into that card and gets a dense, cross-referenced view with voting history, donation timeline, and meeting attendance — all visible simultaneously. They need the Tufte density to spot patterns.
- The policy researcher goes to Layer 3 and downloads a CSV with every column. They don't want your summary.

**Thinkers:** Krug (scanning/satisficing), Tufte (data density/small multiples), Nielsen (progressive disclosure), Few (dashboard single-screen principle).

**Practical consequences:**
- Summary cards show exactly 3 KPIs. Not 2, not 5. Three. Choosing which three is the hard editorial decision — the UI decision is settled.
- Council overview page shows all 7 members as cards in a grid, but each card is sparse (photo, name, district, 3 stats). The grid itself provides Tufte-style comparison across members without overloading any single card.
- Detail pages use a two-column or tab-based layout that presents 4-6 data panels simultaneously. Sparklines appear in table cells. Small multiples are used for voting pattern comparison.
- No infinite scroll on summary pages. If it doesn't fit on one viewport, cut content, don't scroll.

---

## 3. Shneiderman's Overview-First vs. Search-First Entry

**The tension:** Shneiderman's mantra ("overview first, zoom and filter, then details on demand") has dominated information visualization for 30 years. Van Ham & Perer argue that for massive or unfamiliar datasets, overviews are meaningless — users with a specific target should start with search. The homepage can't be both a dashboard and a search box.

**Position: Search-first is the primary entry point. Overview is a secondary mode, not the default.**

The homepage leads with an address bar or name search. Not a dashboard.

Here's why: RTP's primary competition is nonconsumption — people doing nothing. The person who arrives at RTP has a question, even if it's vague: "what's going on with my council member?" or "who's funding the mayor's race?" They are not arriving to browse a dashboard. Shneiderman's overview-first model assumes a user who wants to explore a dataset. Most RTP visitors don't even know what datasets exist.

ProPublica's Represent, BallotReady, and mySociety's WriteToThem all validate search-first as the dominant civic tech entry pattern. You type an address, you get your representatives. The address bar is the wedge that converts a passive citizen into an engaged one. A dashboard overview on the homepage is optimizing for the journalist who visits weekly — at the cost of the citizen who visits once.

**The boundary:** Homepage = search bar with a few curated "story" entry points below it (latest meeting, upcoming election, recent conflicts flagged). These curated items are not an "overview dashboard" — they're editorial picks that provide information scent for users who don't have a specific query. A full dashboard/overview mode exists as a navigation destination ("Explore All Data"), not as the homepage. Journalists and researchers will bookmark the exploration view directly after their first visit.

**Why this serves RTP's users:**
- The retired citizen types their address and sees their council member's profile. They never needed an overview of all 7 members.
- The journalist arrives with a name or topic ("Chevron donations") and searches directly. After their first visit, they bookmark the exploration view.
- The policy researcher navigates to the data catalog via top nav. They don't need search or overview — they need a structured index.
- The city staffer searches their own name to see what the platform shows about them. Search-first serves this anxiety-reduction use case directly.

**Thinkers:** Van Ham & Perer (search-first alternative), Krug (satisficing), Christensen/JTBD (nonconsumption as competitor), Shneiderman (overview for the exploration layer, not the entry point).

**Practical consequences:**
- Homepage hero element is a search input: "Search a name, address, or topic." Auto-suggest shows people, meetings, and topics as you type.
- Below the search bar: 2-3 curated cards (latest council meeting summary, upcoming election preview, recently flagged potential conflict). These are editorial, not algorithmic.
- Top navigation includes "Explore" which leads to the Shneiderman-style overview with filters, facets, and dashboard panels.
- The search bar persists in the top nav on every page. Search is never more than one interaction away.
- No "Welcome to Richmond Common" splash text. The search bar *is* the welcome.

---

## 4. Elavsky's Accessible Redundancy vs. Tufte's Minimalist Data-Ink

**The tension:** Tufte says one encoding channel per data dimension — if color shows party, you don't need a text label too. WCAG says color must never be the sole means of conveying information. These are directly contradictory for every chart: accessible charts violate data-ink maximization; maximally minimalist charts fail accessibility.

**Position: Accessibility wins unconditionally. Tufte is wrong here, full stop.**

This is not a tradeoff. WCAG AA compliance is a legal requirement (DOJ Title II deadline is April 2026 for governments over 50K population — Richmond is 116K). But beyond compliance, the curb-cut effect (Holmes) means accessible redundancy helps everyone: color + pattern + label means the chart works on a grayscale printout, in bright sunlight on an iPad, for the 8% of men with color vision deficiency, and for any user who needs to reference a specific data point precisely.

Tufte's data-ink ratio was formulated for print, where every drop of ink costs money and redundancy consumes paper. On screen, redundancy costs nothing and aids comprehension. Elavsky's critique is correct: a bar chart reduced to single pixels achieves perfect data-ink ratio and is completely unusable. Tufte's principle is a useful heuristic for cutting *decorative* excess, not *functional* redundancy.

**The boundary:** There is no boundary — this is unconditional. Every chart gets: color + shape/pattern for categorical data, direct labels where feasible, a data table alternative accessible via toggle or screen reader. There is no "expert mode" that strips accessibility for density. The accessible version *is* the only version.

**Why this serves RTP's users:**
- The screen reader user gets a structured data table for every chart, navigable by keyboard, with semantic headers.
- The retired citizen on an iPad in sunlight can read the chart because labels don't rely on color alone.
- The journalist can screenshot a chart for print publication without worrying about color reproduction.
- The policy researcher gets the data table they actually wanted more than the chart anyway.

**Thinkers:** Elavsky (accessibility requires redundancy), Holmes (persona spectrum, curb cut effect), WCAG 2.1 AA, Tufte (overruled for functional redundancy; retained for decorative reduction).

**Practical consequences:**
- Every chart has a "View as table" toggle that reveals a fully structured `<table>` with proper `<th>` and `<caption>` elements. This is not optional or deferred — it ships with the chart.
- Categorical data uses color + pattern (hatching, dots, dashes) so distinctions work without color perception.
- Bar charts and line charts use direct labels, not legends, wherever space permits.
- Color palette is tested against all three color blindness types (protanopia, deuteranopia, tritanopia) using automated tooling. Minimum 3:1 contrast between adjacent colors.
- No "accessibility toggle" that creates a separate mode. One interface, one set of standards.

---

## 5. Progressive Disclosure vs. Norman's Gulf of Execution

**The tension:** Progressive disclosure hides complexity behind clicks, reducing cognitive load for novices. Norman's gulf of execution warns that hidden features don't exist for users who can't find them. Every feature hidden behind disclosure narrows cognitive load *and* widens the execution gulf simultaneously.

**Position: Progressive disclosure wins, but the existence of deeper layers must always be signaled.**

The resolution is not "show everything" or "hide everything" — it's that progressive disclosure is the correct architecture, but every hidden layer must leave a visible trace in the layer above it. The user should never wonder "is there more?" They should always know there's more and have a clear path to it.

This is Pirolli & Card's information scent applied to disclosure layers. A summary card that shows "3 of 47 donations" signals that 44 more exist. A collapsed section titled "Voting Record (142 votes)" signals depth by its label alone. The problem isn't progressive disclosure per se — it's progressive disclosure without scent.

**The boundary:** Layer 1 shows summary + count signals ("12 meetings," "47 donations," "3 potential conflicts"). Layer 2 shows the full list with filters. Layer 3 shows the raw data. The scent rule: every Layer 1 element must contain a number or "see all" link that communicates the existence and approximate size of Layer 2. No dead ends. No blank walls.

**Why this serves RTP's users:**
- The retired citizen sees a clean summary and isn't overwhelmed. The "47 donations — see all" link tells them more exists without requiring them to process it.
- The journalist sees that count and knows to click through. They don't have to guess whether export exists — the "Download" label appears in the Layer 2 header.
- The policy researcher sees "API endpoint" or "Download CSV" in the Layer 2 toolbar, not hidden in a settings menu.
- The screen reader user navigates by heading structure and finds "Donations (47)" as an H3, which tells them exactly what's in that section and how deep it goes.

**Thinkers:** Nielsen (progressive disclosure), Norman (gulf of execution), Pirolli & Card (information scent/foraging), Shneiderman (details on demand).

**Practical consequences:**
- Every summary card includes a count: "5 recent votes," "12 donations over $1,000," "3 flagged items." Never just "Donations" as a section title — always "Donations (47)."
- "Download CSV" and "Share" buttons are visible in every Layer 2 view's toolbar, not behind a kebab menu.
- Maximum 2 clicks to reach raw data from any summary card. Not 3. Two.
- Export/download affordances appear on every data table and every detail page. They are never behind progressive disclosure.
- A "What data is available?" page exists in the footer nav, listing every data type, its source, freshness, and access method. This is the backstop for the execution gulf — if someone can't find something through navigation, the data catalog is the fallback.

---

## 6. GOV.UK's Reading Age of 9 vs. Researcher/Journalist Technical Precision

**The tension:** GOV.UK says write at a 9-year-old's reading level. NNGroup found this improves task success by 124%. But journalists need "Schedule A Individual Contributions" not "money from people" — they can't cite simplified language. "Individual Donations" is not legally identical to "Schedule A Individual Contributions." These aren't different depths of the same content; they require different *words* for the same data point.

**Position: Plain language is the visible label. Technical terms live in a structured tooltip layer, not behind progressive disclosure.**

The default text a user reads should be plain language. Always. But technical precision must be one hover/tap away — not buried in a glossary page, not behind a "learn more" link, but in an inline tooltip attached to the plain-language term itself.

This is not a compromise — it's a dual-encoding pattern that serves both audiences simultaneously. The retired citizen reads "Individual Donations: $50,000." The journalist hovers and sees "Schedule A Individual Monetary Contributions per FPPC Form 460." The researcher's CSV export uses the technical column headers. Same data point, three presentations, zero ambiguity for any user.

GOV.UK is right that plain language should be the default because most users never need the technical term. But GOV.UK is wrong if applied as "never show technical terms" — that would make the platform uncitable for professional users, which kills Path A and Path D simultaneously.

**The boundary:** Every user-facing label uses plain language. Every plain-language term that corresponds to a legal/regulatory category gets a tooltip showing: (1) the official term, (2) the filing category, and (3) a one-sentence definition. CSV/API exports use official technical column names with a schema doc. Page headings and navigation labels are always plain language.

**Why this serves RTP's users:**
- The retired citizen reads labels they understand without ever needing to interact with a tooltip.
- The journalist hovers over "Individual Donations" and gets the exact FPPC filing term for their story. They can cite the platform because the technical term is accessible.
- The policy researcher downloads a CSV with headers matching official filing categories. They can join it with other datasets.
- The screen reader user encounters the tooltip content as an `aria-describedby` attribute — the technical term is announced after the plain label if they want it.
- The city staffer sees the same terms they use internally when they hover, which builds trust that the platform understands their domain.

**Thinkers:** GOV.UK (reading age of 9), NNGroup (plain language + 124%), Morville & Rosenfeld (controlled vocabulary), JTBD (milkshake study — same data, different presentations for different jobs).

**Practical consequences:**
- A `<CivicTerm>` component wraps every domain-specific label. It renders the plain-language version as visible text and the technical version as a tooltip. This component is defined once in the design system and used everywhere.
- Navigation labels: "Money" not "Campaign Finance." "Votes" not "Roll Call Actions." "Meetings" not "Legislative Sessions."
- Tooltip content is structured data (stored as a civic glossary in the database), not ad hoc strings. This means it's consistent across all pages and maintainable.
- CSV exports use official headers: `schedule_a_individual_monetary_contributions`, not `individual_donations`. A schema doc maps every plain-language label to its technical equivalent.
- A glossary page exists but is a reference, not the primary mechanism. The inline tooltip is the primary mechanism.

---

## 7. Frost's Rule of Three vs. Design System Consistency

**The tension:** Frost/Metz say don't abstract until you've seen three instances. A wrong abstraction is worse than duplication. But design tokens and consistency (CRAP, Norman's signifiers, Nielsen's Heuristic #4) require shared decisions from day one. Without tokens, each component drifts from the last.

**Position: Tokens on day one. Component abstraction on the third instance.**

These are two different things being conflated. Design tokens (colors, spacing, typography, border radii) are not abstractions — they're configuration. Defining `--color-primary` and `--spacing-md` doesn't create a premature abstraction; it creates a shared vocabulary that prevents drift. The Rule of Three applies to *component* extraction (should I make a `<ConflictCard>` or keep duplicating the markup?), not to *tokens*.

A solo developer can easily maintain token discipline because Tailwind v4's `@theme` directive makes tokens trivially cheap to define. You aren't building a Figma component library — you're setting CSS custom properties in one file. The cost of getting tokens wrong is near zero (rename a variable); the cost of getting component abstractions wrong is high (rewrite a component hierarchy).

**The boundary:** Tokens are defined in `tailwind.config` / `@theme` before any component code is written: colors (semantic: primary, surface, muted, destructive), spacing scale, border-radius scale, typography scale. Component abstractions follow the Rule of Three: copy-paste twice, extract on the third instance. Shadcn/ui components are used as-is until a civic-specific pattern emerges three times.

**Why this serves RTP's users:**
- The retired citizen sees a visually consistent product where buttons look the same everywhere and cards have the same spacing. This consistency builds surface credibility (Fogg) even if they can't articulate why.
- The journalist doesn't care about your component architecture — but they notice if the "Download" button is styled differently on two different pages. Tokens prevent that.
- The screen reader user benefits from consistent component behavior. If `<Card>` always has the same heading structure, navigation is predictable.

**Thinkers:** Frost (Rule of Three for components), Jina Anne (design tokens), Metz (wrong abstraction is worse than duplication), Williams (CRAP/Repetition), Norman (consistent signifiers).

**Practical consequences:**
- Before any Phase 2 component code: define semantic color tokens (`--color-surface`, `--color-primary`, `--color-muted`, `--color-destructive`, `--color-conflict-flag`), spacing scale (4/8/12/16/24/32/48), border-radius scale (sm/md/lg), and typography scale (4 sizes: body, small, heading, display).
- These live in one Tailwind `@theme` block. Total effort: ~30 minutes. Zero risk of wrong abstraction.
- Shadcn/ui components are used directly with token-based styling overrides. No wrapper components until a civic-specific pattern appears three times.
- When a pattern appears for the third time (e.g., a "data card with source citation and freshness badge"), extract a `<CitedDataCard>` component. Document the extraction in a `COMPONENTS.md` changelog.
- No Storybook. TypeScript interfaces + TSDoc are the component documentation (per Curtis: "tool first, pictures second, words last").

---

## 8. Aisch's "Interactivity as Bonus" vs. Shneiderman's Interactive Exploration

**The tension:** Aisch argued that most users never interact with data visualizations — the default view must work as a static artifact. Shneiderman's entire taxonomy (overview, zoom, filter, details-on-demand, relate, history, extract) assumes interactive exploration. Building for Shneiderman's model is expensive; building for Aisch means the journalist who *does* interact deeply is underserved.

**Position: Aisch wins as the design constraint. Shneiderman wins as the implementation target.**

Every visualization must make its point without a single click, hover, or filter adjustment. The default state is the editorial product. If a user never interacts, they should still walk away informed. This is the design constraint — the bar every visualization must clear before interactive features are added.

But the interactive layer *is* built — it's the implementation target. Filters, crossfilter brushing, linked views, export — all of these serve the journalist and researcher who will use them. The difference from a Shneiderman-first approach is sequencing: you design the static default first, prove it communicates clearly, then add interactivity on top.

Aisch is right about the numbers — most civic platform visitors will never adjust a filter. But the users who *do* interact are disproportionately valuable: they're journalists writing stories, researchers citing data, and engaged citizens who become repeat visitors. The 80/20 split means you design defaults for the 80% and build tools for the 20%.

**The boundary:** Every chart and data view has a meaningful, annotated default state that tells a story without interaction. Annotations (callout labels, highlighted bars, summary text) do the narrative work. Interactive features (filter, zoom, crossfilter, export) are layered on top and discoverable but not required for comprehension.

**Why this serves RTP's users:**
- The retired citizen sees the default view — a campaign finance bar chart with the largest donor highlighted and a text annotation saying "Chevron-affiliated PAC: largest contributor." They understand the point without clicking anything.
- The journalist sees the same chart but filters by date range, toggles between donors and recipients, and exports the filtered data. The interactivity serves their investigation.
- The policy researcher doesn't care about the chart at all — they download the underlying CSV directly.
- The screen reader user encounters the annotation as text content, which works better than interactive tooltips for non-visual navigation.

**Thinkers:** Aisch (interactivity as bonus), Shneiderman (7-task taxonomy), Segel & Heer (martini glass — author-driven opening → reader-driven exploration), Few (dashboard definition).

**Practical consequences:**
- Every chart has at least one text annotation in the default state. Not a tooltip — a visible callout label that highlights the most newsworthy data point.
- Annotation content is stored in the database as structured editorial data, not hardcoded. This means it can be updated when the data changes.
- Filter controls are visible but in a collapsed/secondary position. The chart loads in its annotated default state, not in a "configure your view" state.
- Development sequence: (1) build the static chart with annotations, (2) add filter controls, (3) add crossfilter/linked views. Each layer is shippable on its own.
- Budget rule: ~60% of visualization effort goes to the default state (data accuracy, annotation, responsive layout). ~40% goes to interactive features.

---

## 9. Moesta's "Reduce Anxiety" vs. Feature-Driven Development

**The tension:** Moesta's Forces of Progress model says reducing anxiety is often more powerful than adding features. Each RTP persona has a critical anxiety: journalists worry about accuracy, citizens about comprehension, researchers about completeness, government staff about surveillance framing. But anxiety reduction is diffuse and hard to scope, while features are measurable and shippable.

**Position: Trust infrastructure ships first. It is the foundation, not the polish.**

This is the most consequential position in this document. RTP's entire value proposition is "trust this data about your government." If users don't trust the data, no amount of search, filtering, or visualization matters. A platform with perfect features but no source citations will be "fired" by every persona.

Trust infrastructure is not the same thing as "making things pretty" or "writing documentation." It is a specific set of data provenance features that must be present on every data point from day one:

1. Source link (where did this data come from?)
2. Extraction date (when was it last updated?)
3. Confidence indicator (how certain is the extraction?)
4. Source tier badge (Tier 1 official record vs. Tier 3 stakeholder communication)

These are not sprint-sized tasks — they are architectural decisions that are nearly impossible to retrofit. If you build three months of features without source attribution, adding it later means touching every component, every API endpoint, and every database query. Trust is foundational, not decorative.

RICE scoring naturally deprioritizes trust infrastructure because Reach × Impact × Confidence ÷ Effort makes "add CSV export" look higher-priority than "add source citations to every data point." RICE is wrong here. RICE doesn't capture the fact that without trust, Reach goes to zero because no one uses the platform.

**The boundary:** Every data point visible to users ships with source, freshness, and tier from the first public release. No exceptions, no "we'll add citations later." Features that don't have source attribution aren't public-ready — they stay operator-only until provenance is attached.

**Why this serves RTP's users:**
- The journalist checks the source link before citing any number. If there's no source link, they close the tab. They don't give the platform a second chance.
- The retired citizen sees "Source: City of Richmond Official Minutes, January 14, 2025" and trusts the number more than a number with no attribution — even if they never click the link.
- The city staffer sees "Last updated: March 10, 2026" and knows the data is current. Without freshness indicators, they assume it's stale and dismiss the platform.
- The policy researcher sees Tier 1/2/3 badges and understands the evidentiary weight of each data point. This is the professional signal that distinguishes RTP from a random blog.

**Thinkers:** Moesta (Forces of Progress / anxiety reduction), Fogg (Stanford credibility guidelines — "make it easy to verify accuracy"), JTBD (nonconsumption as competitor — trust is the adoption barrier), Christensen (the "hire/fire" decision).

**Practical consequences:**
- Every API response includes `source_url`, `extracted_at`, `source_tier`, and `confidence_score` fields. These are non-nullable in the schema.
- Every UI data point renders a small source indicator: a linked timestamp or a tier badge. This is part of the `<CitedDataCard>` component, not an afterthought.
- A "Methodology" page explains how data is collected, extracted, and scored. This page exists before the first public launch.
- The publication tier system (Public / Operator-only / Graduated) is the enforcement mechanism: data without provenance metadata stays operator-only until it's attributed.
- Phase 2 acceptance criteria for any feature: "Does every visible data point have a source link and freshness timestamp?" If no, it's not done.

---

## 10. Holmes' "Solve for One, Extend to Many" vs. JTBD's "Build for the Most Demanding User"

**The tension:** Holmes says start with the edge case — the screen reader user, the keyboard-only navigator — and solutions cascade to benefit everyone (curb cut effect). JTBD says build for the most demanding *functional* user — journalists — because satisfying their accuracy needs satisfies everyone's. These identify different users as the design driver.

**Position: Accessibility is infrastructure, not a feature. It ships in every component from day one. Journalist workflows are the feature priority.**

This tension dissolves when you separate infrastructure from features. Accessibility (semantic HTML, keyboard navigation, ARIA labels, sufficient contrast, heading structure) is not a feature you add — it's a property of how components are built. If you use `<button>` instead of `<div onClick>`, you get keyboard accessibility for free. If you use semantic headings (`<h2>`, `<h3>`), screen readers navigate by structure for free. If you use shadcn/ui components (which are built on Radix UI), you get ARIA compliance for free.

The cost of accessibility-from-day-one with a component library like shadcn/Radix is near zero — it's already done for you. The cost of retrofitting accessibility into custom `<div>`-based components later is enormous. Holmes is right that you must start with edge cases, and the practical way to do that is to never override your component library's built-in accessibility.

The journalist's *functional* requirements (cross-referencing, bulk export, citation-quality sourcing) are the feature priorities that determine what gets built and in what order. But every feature is built on accessible components.

**The boundary:** Every component uses semantic HTML and Radix primitives (via shadcn/ui) by default. Accessibility is a component-level property, never a separate "accessibility mode." Feature prioritization follows JTBD: journalist cross-referencing tools, then citizen address lookup, then researcher data catalog. But all three are built on the same accessible component foundation.

**Why this serves RTP's users:**
- The screen reader user navigates by heading structure from day one. They don't wait for an "accessibility phase" that never comes.
- The journalist gets cross-referencing tools prioritized for their workflow — but those tools use accessible dropdowns, keyboard-navigable tables, and proper focus management.
- The retired citizen on an iPad benefits from large touch targets and clear focus states that were implemented for keyboard/screen reader users.
- No one is told "accessibility is coming in a future phase."

**Thinkers:** Holmes (solve for one, extend to many; curb cut effect; persona spectrum), Christensen/JTBD (most demanding user for feature prioritization), Treviranus (three dimensions of inclusive design).

**Practical consequences:**
- shadcn/ui + Radix UI is non-negotiable for all interactive components. No custom `<div>` reimplementations of dropdowns, modals, tabs, or menus.
- Every page has a correct heading hierarchy (`<h1>` → `<h2>` → `<h3>`). No skipped levels. This is validated in CI.
- All interactive elements are keyboard-accessible. Tab order is logical. Focus is managed on route changes.
- Color contrast meets WCAG AA (4.5:1 for text, 3:1 for large text and UI elements). Checked via automated tooling in CI.
- Feature backlog is ordered by JTBD priority: journalist tools → citizen discovery → researcher tools → government staffer view. Every item in the backlog is implemented with accessible components regardless of which persona it serves.

---

## 11. Fogg's Surface Credibility vs. Code for America's "Ship Early"

**The tension:** Fogg says users judge credibility in 50ms based on visual design. A beta-looking civic platform undermines its own value proposition. Code for America says ship when testers can complete 5 core tasks, with a 90/10 features-to-design split in early development.

**Position: Shadcn/ui's defaults are the minimum viable credibility threshold. Ship when task completion works, not when design is "finished."**

This tension is real for teams building custom UI from scratch, but it's largely resolved by modern component libraries. Shadcn/ui with default styling, consistent spacing tokens, and a clean typography scale produces an interface that clears Fogg's surface credibility bar without custom design work. It doesn't look like a government database. It doesn't look like a student project. It looks like a modern SaaS product — which, for civic tech, is more than sufficient.

The risk Fogg warns about — "dated, cluttered interface says 'this data might not be reliable'" — applies to civic platforms built on raw Bootstrap 3 or unstyled HTML tables. It does not apply to a well-configured Tailwind/shadcn setup. The marginal credibility gain from custom design work beyond shadcn defaults is real but small compared to the marginal value of shipping earlier and getting user feedback.

Code for America is right: ship when the core tasks work. But "core tasks" for RTP must include "verify a data point's source" — which means trust infrastructure (Position #9) ships before features that lack it. The 90/10 split is features-to-custom-design, not features-to-trust.

**The boundary:** Shadcn/ui defaults + semantic color tokens + consistent spacing = the visual quality threshold. No custom illustrations, no brand identity work, no marketing pages in Phase 2. Ship when: (1) address search returns relevant results, (2) council member profiles show sourced data, (3) campaign finance data is browsable with filters, (4) every visible data point has source attribution. That's the launch bar.

**Why this serves RTP's users:**
- The retired citizen sees a clean, modern interface that looks professional enough to trust. They don't need custom branding — they need consistent, readable pages.
- The journalist evaluates credibility based on data quality and source attribution, not visual polish. Shipping sourced data faster matters more than custom design.
- The city staffer sees a product that looks like a tool, not a protest sign. Shadcn's neutral aesthetic serves the "sunlight, not surveillance" framing.

**Thinkers:** Fogg (surface credibility, prominence-interpretation), Code for America (ship early), Krug (3-user testing — "whether you test is more important than testing perfectly"), Frost (atomic design with existing component libraries).

**Practical consequences:**
- No custom logo, brand colors, or marketing site in Phase 2. Use a clean wordmark in the header.
- Shadcn/ui components are used with minimal customization. Color tokens are defined (Position #7) but don't deviate far from shadcn defaults.
- The first public release ships when the 4 task-completion criteria above are met — not when design is "done."
- After launch, visual refinement is driven by Krug's discount usability testing: 3 users, one morning, monthly. Fix what they struggle with. Don't redesign on theory.
- Custom design investment begins when user feedback specifically identifies trust or comprehension issues that trace to visual design — not before.

---

## 12. Wurman's "Understanding Precedes Action" vs. ProPublica's Action-First Entry

**The tension:** Wurman says information architecture exists to create understanding — users must comprehend context before acting meaningfully. ProPublica, BallotReady, and mySociety all show that the highest-impact civic pattern is immediate action: type your address, see your results. Requiring comprehension before access loses the citizen with 15 seconds of patience.

**Position: Action first, context layered in. But context is always within one interaction of the data.**

Show results immediately. Layer context alongside the data, not before it. Wurman is right that understanding matters, but wrong about sequencing — understanding doesn't need to *precede* action; it needs to *accompany* it.

When a citizen searches "Council Member Davis" and sees "$50,000 from Chevron-affiliated PAC," they might misinterpret that. The solution is not a "How Campaign Finance Works" interstitial — it's a contextual frame embedded next to the number: "Average donations to Richmond council candidates: $XX,000. Legal limit: $XX,000." Context without gates. The user gets their answer instantly *and* gets the frame to interpret it, in the same viewport.

Wurman's concern about misinterpretation is real and important — a decontextualized number about a council member's donations could mislead. But the playbook's finding is equally important: users abandon before they finish a pre-requisite explainer. The resolution is inline context, not gated context.

**The boundary:** Search results and data views load immediately with no interstitial. Context is delivered via: (1) comparison benchmarks inline ("$50K — average for this seat: $35K"), (2) confidence badges where extraction is uncertain, (3) one-sentence contextual labels on potentially misleading metrics, (4) a "Learn more" expansion for users who want the full explanation. Context is adjacent to data, never gating access to data.

**Why this serves RTP's users:**
- The retired citizen gets their answer immediately and sees the contextual comparison that helps them interpret it. They don't bounce off an explainer page.
- The journalist doesn't need the context — they already understand campaign finance. The inline framing doesn't slow them down because it's alongside the data, not before it.
- The policy researcher ignores the contextual labels and goes straight to the numbers and source links. The context is unobtrusive.
- The city staffer sees that the platform provides fair context, not just raw numbers that could be weaponized. "Davis received $50K from Chevron" with no context feels adversarial. "Davis received $50K — average for this seat is $35K, legal limit is $XX,000" feels informational.

**Thinkers:** Wurman ("understanding precedes action" — modified to "understanding accompanies action"), ProPublica/BallotReady (action-first entry), Krug (satisficing — users act on first reasonable option), Norman (conceptual models — built alongside interaction, not before it).

**Practical consequences:**
- No interstitial pages, onboarding flows, or "before you begin" explainers. Ever.
- Every potentially misleading metric includes an inline comparison benchmark: averages, medians, legal limits, or historical baselines. These benchmarks are structured data in the database, not hardcoded strings.
- The `<CivicMetric>` component renders a number + benchmark + source in a compact format. It's the standard way any civic number is displayed.
- "Learn more" links expand inline (accordion/disclosure) to show 2-3 sentences of explanation. They do not navigate to a separate page.
- A "How to Read This Data" section exists at the bottom of each major page type (council member profile, meeting detail, campaign finance view). It's available but doesn't gate access.

---

## Positions I'm Least Confident About

### 1. Position #3 — Search-First Over Overview

I'm confident search-first is correct for the *homepage*, but less confident it's correct for repeat visitors. A journalist who visits 3x/week may want a dashboard landing page that shows "what changed since your last visit" — basically an activity feed or changelog view. The current position routes them to the Explore view, but the Explore view is a static overview, not a "what's new" feed.

The risk: search-first optimizes for first visits and episodic use. If RTP succeeds and builds repeat visitors, they may need a personalized overview mode (recent changes to entities they follow, new filings, upcoming meetings) that doesn't exist in either search-first or overview-first models. This might need to become a third entry pattern — "follow-first" — where logged-in users see a feed of changes to topics they've subscribed to.

**Push back here if:** you think repeat-visitor retention matters more than first-visit conversion in Phase 2. If so, the homepage might need to be adaptive: search-first for anonymous visitors, activity-feed-first for returning users.

### 2. Position #8 — 60/40 Default State vs. Interactivity Split

The 60/40 budget allocation for static defaults vs. interactive features is a guess, not a calculation. I'm confident the *principle* is right (defaults must stand alone), but the specific ratio depends on which users show up. If early adoption is dominated by journalists and researchers (who interact heavily), underinvesting in interactivity means underserving your actual users. If adoption is dominated by drive-by citizens (who never filter), the 60/40 is correct.

**Push back here if:** you expect your early users to skew heavily toward journalists (which JTBD suggests is the right Phase 1 audience). In that case, maybe 40/60 is better — invest more in interactive tools because your early adopters will use them, and the default-state quality can improve later based on their feedback.

### 3. Position #11 — Shadcn Defaults as Sufficient Credibility

I believe shadcn's defaults clear the surface credibility bar for most users, but I'm less certain this holds for *government officials* viewing the platform. A city council member or city attorney visiting the site may have higher visual expectations because they're accustomed to polished GovTech vendor products (Granicus, CivicPlus, Accela). If the platform looks like a developer's side project to them, the "sunlight, not surveillance" framing won't land — they'll dismiss it as amateur.

Since Phillip sits on the Personnel Board and needs government officials to take RTP seriously, the surface credibility bar for *that specific audience* may be higher than shadcn defaults provide. Not dramatically higher — but things like a professional logo, consistent brand colors, and a clean "About" page with institutional backing signals might need to ship with the first version government officials see.

**Push back here if:** you plan to share RTP with Richmond officials before the first public launch. In that case, a small investment in brand identity (logo, color palette, "About the Project" page) might be worth the delay.
