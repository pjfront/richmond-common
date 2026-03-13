# Design Philosophy — Richmond Transparency Project

---

## What This Is and Who It's For

The Richmond Transparency Project is a civic technology platform that structures public records — meeting minutes, campaign finance filings, voting records, budget documents — so that anyone can understand how their city government works. We serve residents who want to know what their council member has been doing, journalists investigating influence patterns, researchers studying local governance, and government officials who want the public record to speak clearly. The platform is designed as a governance assistant, not a watchdog. Accountability is a natural byproduct of transparency, not our stated goal.

---

## Our Design Beliefs

### 1. Every pixel earns its place — but the definition of "earning" depends on where you are.

Edward Tufte's data-ink ratio principle argues that non-data elements — decorative gradients, 3D effects, redundant borders — actively harm comprehension in visualizations. We agree, inside charts. But Don Norman's aesthetic-usability effect (backed by Tractinsky et al. and Bateman et al.) shows that visual polish makes interfaces feel more trustworthy and more usable. BJ Fogg's research on web credibility found that users make trust judgments within 50 milliseconds — before reading a single data point. For a platform whose entire value proposition is "trust this data about your government," that 50ms judgment matters.

In practice, this means we maintain two standards. Page-level chrome — cards, navigation, spacing, typography — follows Norman: warm, polished, professional. Chart interiors follow Tufte: no gratuitous decoration, honest proportions, zero-baseline bar charts, direct labels instead of legends. The card border around a campaign finance chart earns its pixels through trust and scannability. The bars inside that chart earn theirs through data accuracy. No illustrations, mascots, or decorative imagery appear anywhere in the application. The polish is structural — consistent spacing, clean typography, well-grouped cards — not decorative.

### 2. Accessibility is infrastructure, not a feature.

Kat Holmes' inclusive design framework introduces the curb-cut effect: solutions designed for edge cases — the wheelchair user, the screen reader navigator — cascade to benefit everyone. A chart that works for a user with color vision deficiency also works on a grayscale printout and in bright sunlight on an iPad. A keyboard-navigable data table also works for the power user who never touches a mouse.

We build on this principle by treating accessible construction as non-negotiable infrastructure. Every interactive element uses shadcn/ui + Radix UI primitives, which ship with ARIA compliance built in. Every page has a correct heading hierarchy. Every chart includes a structured data table alternative. Color is never the sole means of conveying information. There is no "accessible mode" — the default product is the accessible product. Frank Elavsky's work on accessible data visualization confirms what Tufte got wrong: functional redundancy (color plus pattern plus label) is not waste — it's resilience.

### 3. Show the answer first, then the context to interpret it.

Richard Saul Wurman argued that understanding must precede action. ProPublica, BallotReady, and mySociety all proved that in civic technology, the highest-impact pattern is the opposite: type your address, see your results. Requiring comprehension before access loses the citizen with fifteen seconds of patience.

We resolve this tension through layered context, not gated context. When a resident searches their council member and sees "$50,000 from a Chevron-affiliated PAC," the number appears immediately — alongside a benchmark: "Average for this seat: $35,000. Legal limit: $75,000." The citizen gets their answer and the frame to interpret it in the same viewport. No interstitial pages, no onboarding flows, no "Welcome to…" splash text. Context accompanies data; it never gates access to data.

### 4. Plain language is the visible interface. Technical precision is one tap away.

GOV.UK's research showed that writing at a 9-year-old's reading level improves task success by 124%. But journalists need "Schedule A Individual Monetary Contributions" — not "money from people" — because simplified language isn't legally citable. Morville and Rosenfeld's information architecture work shows that controlled vocabularies serve both audiences when structured as dual encodings.

Every user-facing label uses plain language. Navigation says "Money" not "Campaign Finance," "Votes" not "Roll Call Actions." But every plain-language term is backed by a structured tooltip showing the official regulatory term, filing category, and a one-sentence definition. The retired resident reads labels they understand. The journalist hovers and gets the FPPC filing term for their story. The researcher downloads a CSV with official technical column headers. Same data point, three presentations, zero ambiguity for any user.

### 5. Trust is the foundation, not the polish.

Clayton Christensen's Jobs-to-Be-Done framework, as extended by Bob Moesta's Forces of Progress model, identifies anxiety as the most underestimated barrier to adoption. For RTP, every persona has a critical anxiety: journalists worry about accuracy, citizens about comprehension, researchers about completeness, government officials about adversarial framing. Fogg's web credibility guidelines specify the mechanisms that reduce these anxieties: source attribution, verifiability, and transparency about methods.

We treat trust infrastructure as foundational architecture, not a feature to add later. Every user-visible data point ships with a source link, an extraction timestamp, a source credibility tier, and a confidence score. These fields are non-nullable in our API schema. Data without complete provenance metadata stays operator-only until attributed. Features that display data without source citations aren't public-ready — they don't ship. This is expensive and it slows us down, but a civic data platform without citations is a rumor engine.

### 6. Density is a function of depth, not a single design choice.

Steve Krug observed that users scan, satisfice, and click the first reasonable thing — "billboard at 60 mph." Tufte wants maximum information density — the Bloomberg Terminal ideal where an expert eye spots anomalies in a dense display. Neither is universally correct; both are correct at different layers of engagement.

Our landing page and summary cards follow Krug: one focal point per section, three key metrics per card, aggressive whitespace. Our detail pages follow Tufte: dense, multi-panel, faceted — designed for the user who has committed attention. Raw data exports follow the researcher's need: every column, no editorial filter. Progressive disclosure mediates the tension, but every collapsed layer leaves a visible trace — "Donations (47)" not just "Donations." Pirolli and Card's information foraging theory says users follow scent; we make sure the scent is always present.

### 7. The static default must tell the story.

Gregor Aisch, a former New York Times graphics editor, argued that most users never interact with data visualizations — the default view must work as a static artifact. Shneiderman's interactive exploration taxonomy (overview, zoom, filter, details-on-demand) assumes users who interact deeply. Segel and Heer's narrative visualization research bridges these with the "martini glass" model: an author-driven opening that transitions to reader-driven exploration.

Every visualization we build makes its point without a single click, hover, or filter adjustment. The default state includes at least one visible text annotation — a factual, descriptive callout highlighting the most significant data point. Annotations state what the data shows ("Highest quarterly total since 2020"), never what it means ("Unprecedented spending surge"). Interactive features — filters, crossfilter brushing, export — are layered on top and discoverable, but never required for comprehension.

---

## How We Handle Tension

### Accessibility vs. Minimalism

Tufte's data-ink ratio and Elavsky's accessible data visualization framework give directly contradictory instructions for every chart: Tufte says one encoding channel per data dimension; WCAG says color must never be the sole means of conveying information. We resolve this unconditionally in favor of accessibility. Tufte's principle was formulated for print, where ink costs money and redundancy wastes paper. On screen, functional redundancy — color plus pattern plus label — costs nothing and serves everyone: the color-blind user, the journalist screenshotting for print, the resident reading on an iPad in sunlight. Tufte is retained for eliminating decorative excess; he is overruled for functional redundancy.

### Scanning Citizens vs. Dense-Data Journalists

A sparse interface designed for the scanning citizen (Krug) fails the journalist doing cross-referencing (Tufte). A dense interface designed for the journalist overwhelms the citizen who visited once with a vague question. Progressive disclosure resolves this by letting engagement depth determine density. Layer 1 is sparse and editorial. Layer 2 is dense and faceted. Layer 3 is raw data for researchers. The key architectural insight is that these are not separate products — they are views of the same data layer, optimized for different commitment levels.

### Search-First vs. Overview-First

Shneiderman's "overview first, zoom and filter, then details on demand" has dominated information visualization for thirty years. Van Ham and Perer argued that for unfamiliar datasets, users with a specific target should start with search. Our primary competition is nonconsumption — people doing nothing to understand their city government. They arrive with a question, not a desire to explore a dataset. The homepage leads with a search bar. A full dashboard/overview mode exists as a navigation destination for the journalist who visits weekly. Search converts passive citizens into engaged ones; dashboards serve users who are already engaged.

### Ship Early vs. Ship Credibly

Fogg says users judge credibility in 50 milliseconds. Code for America says ship when core tasks work. We resolve this through component libraries: shadcn/ui's default styling clears the surface credibility bar without custom design work. The product looks professional — not because we invested in brand identity, but because modern component libraries have raised the floor. Custom design investment begins when user feedback specifically identifies trust or comprehension issues that trace to visual design — not before. Ship when the data is sourced, attributed, and task-complete, not when the design is "finished."

---

## Our Users

We design for one data layer with audience-optimized views, not separate products.

**The resident** arrives with a question, usually vague: "What's going on with my council member?" They need plain language, clean cards with three numbers, and the confidence that the information comes from official sources. They scan, satisfice, and leave. If they find their answer in under thirty seconds, they'll come back. Anxiety about comprehension is their primary barrier.

**The journalist** arrives with a name, a topic, or a hunch. They need source attribution good enough to stake their byline on, raw data export visible in the toolbar, stable URLs they can cite in published articles, and the ability to cross-reference donations against votes. They interact deeply with the data and are the platform's most important distribution channel — a story citing RTP reaches more residents than the platform itself. Anxiety about accuracy is their primary barrier.

**The researcher** needs methodology documentation, versioned datasets, machine-readable exports, and confidence scores that let them assess data quality. They tolerate density, ignore editorial framing, and go straight to Layer 3. They will build on the platform if they can trust the data pipeline. Anxiety about completeness and reproducibility is their primary barrier.

**The city official** checks whether the platform represents them fairly. They need to see benchmarks alongside raw numbers, hedged language without characterizations, and a mechanism to provide context when findings involve their name. If the platform looks like opposition research, they will fight it. If it looks like a professional governance tool, they may become allies. Anxiety about adversarial framing is their primary barrier.

---

## What We Don't Do

### We don't characterize — we describe.

The platform states "Council Member X voted differently from their stated position on [date]." It never states "Council Member X contradicted themselves." It reports "Three speakers opposed the project." It never reports "The project faced significant opposition." Fogg's credibility framework establishes that trust is earned through neutrality and verifiability, not through editorial voice. AI-generated summaries use hedged, factual language — always. Every piece of AI-generated content is visibly marked as such. The platform describes patterns; it does not characterize them. "Sunlight, not surveillance" is not a marketing tagline — it is an enforceable content rule.

### We don't gate access behind comprehension.

No onboarding flows. No "How to Read This Data" interstitials. No "Welcome to the Richmond Transparency Project" splash text. Context is always within one interaction of the data — inline benchmarks, confidence badges, one-sentence labels — but it never blocks access. The resident who wants a number gets the number. The context to interpret it is right there, but they were never forced to read it first.

### We don't present data without provenance.

A number without a source link is a rumor. A campaign finance figure without a benchmark is a weapon. A confidence score without a numeric basis is hand-waving. Every user-visible data point includes its source, freshness, credibility tier, and extraction confidence. Data that can't meet this standard stays operator-only. We would rather show less data with full attribution than more data without it.

### We don't build a separate "accessible version."

There is no toggle that enables accessibility. The heading hierarchy, keyboard navigation, focus management, ARIA live regions, color-plus-pattern encoding, and touch-target sizing are built into every component from day one. Holmes' inclusive design research shows that "solve for one, extend to many" produces better products for everyone — not just the edge case. The accessible version is the only version.
