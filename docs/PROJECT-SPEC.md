# Product Specification — Richmond Common

*Last updated: 2026-02-20*
*This is a living document. Update as features are scoped, validated, or deprioritized.*

---

## Mission

Replace the investigative function of disappeared local journalism with automated accountability infrastructure.

**One-liner:** A governance assistant that helps cities stay transparent by default.

---

## Vision & Positioning

This is NOT an adversarial "gotcha" tool. It's a **sunlight-as-disinfectant** platform that helps local government work better. Accountability is the *byproduct*, not the stated goal.

This framing is critical for two reasons:

1. **Phillip's Personnel Board seat.** Presenting as a fellow public servant improving the system, not an outsider attacking it. Warm introduction no startup can replicate.
2. **Adoption.** City clerks, council members, and staff are more likely to engage with (or at least not obstruct) a tool that frames itself as helping them do their jobs better.

The product serves citizens first, but the positioning must be collaborative. "We're making the information that's already public actually accessible."

---

## Core Features

### 1. Data Ingestion Pipeline
Automated collection of 15+ document types from city sources. Raw documents preserved exactly as received in Document Lake (Layer 1). Every document tagged with `city_fips` from day one.

**Document types:**
- Council meeting minutes and agendas
- Staff reports and resolutions
- Campaign finance filings (local + state)
- FPPC Form 700 economic interest statements
- CPRA request/response records
- Meeting video transcripts (audio → text)
- Planning Commission minutes
- Rent Board minutes
- Budget documents
- News articles (tiered by credibility)
- Council member newsletters
- Blog posts (Tom Butt, etc.)
- Community input / public comments
- Property records (later phase)
- Court records (later phase)

### 2. Structured Extraction
LLM-powered extraction of structured data from unstructured documents. Every vote, motion, speaker statement, dollar amount, and procedural action pulled into normalized database tables.

**What gets extracted:**
- Votes: who voted yes/no/abstain on what, final tally
- Motions: who moved, who seconded, what was proposed
- Speaker statements: who said what, during which agenda item
- Financial amounts: budgets, contracts, grants, fees
- Dates and deadlines: hearing dates, compliance deadlines
- References: cross-references to resolutions, ordinances, prior meetings

Richmond's minutes format is highly parseable: "Ayes: [names]. Noes: [names]. Abstentions: [names]." — this is a major advantage for the pilot.

### 3. Pre-Meeting Conflict Scanner (Flagship Feature)
Before each council meeting, automatically cross-reference the upcoming agenda against campaign finance records, Form 700 disclosures, property records, and voting history.

**Example output:**
> Agenda Item H-4: Rezone 1400 Marina Way for mixed-use development.
> ⚠️ Council Member [X] received $2,500 from [Developer Y] (CAL-ACCESS filing 2024-Q3).
> ⚠️ Council Member [Z] owns property within 500ft (Form 700, Schedule A-2).
> Neither has filed a recusal notice as of [date].

This is the feature that makes the product indispensable. No human journalist can do this cross-referencing at scale for every agenda item before every meeting.

### 4. Automated Public Comment Generation
Generate formal, citation-heavy public comments submitted before each council meeting. Comments are factual summaries — not advocacy, not opinion. Format follows Brown Act public comment requirements.

**Comment structure:**
- Header: project name, date, meeting reference
- Per-item analysis for flagged agenda items
- Specific citations to source documents (with links)
- Neutral, factual tone throughout
- Footer: methodology note, disclaimer

Comments are submitted during the public comment window and become part of the official record. This creates a permanent paper trail of accountability.

### 5. Council Member Profile Pages
Public-facing pages for each elected official aggregating:
- Complete voting record (with position changes highlighted)
- Campaign finance summary (top donors, total raised, by category)
- Attendance record
- Flagged conflicts of interest
- Statements on key issues (extracted from minutes)
- Comparison with stated platform positions

### 6. RAG-Powered Search
Citizens can ask natural language questions about their local government and get sourced answers.

**Example queries:**
- "How did Council Member X vote on housing issues?"
- "Who donated to the mayor's campaign?"
- "What happened with the Point Molate development?"
- "Has anyone on the council recused themselves from a vote in the last year?"

Powered by pgvector embeddings in PostgreSQL (no separate vector DB). Single query combines vector similarity search with SQL filtering for fast, accurate results.

### 7. Document Completeness Dashboard
Track which documents are missing, late, or incomplete. Surface patterns: "The Planning Commission has not published minutes for 3 of the last 5 meetings" or "Council Member X's Form 700 is 45 days overdue."

This makes institutional accountability visible without making accusations. The data speaks.

### 8. CPRA Request Automation
Semi-automated California Public Records Act requests when documents are missing or incomplete. Track request status, response times, and compliance patterns.

### 9. Alert Subscriptions
Citizens subscribe to topics, officials, or geographic areas. Get notified when:
- An agenda item affects their neighborhood
- A council member they follow votes on something
- A conflict of interest is detected
- A document they requested becomes available
- A meeting is scheduled on a topic they care about

### 10. News & Media Integration
Aggregate local news coverage and cross-reference with official records. Surface discrepancies between what officials say publicly and how they vote.

---

## Source Credibility Hierarchy

All ingested content is tagged with a credibility tier. This is critical for trust and for RAG retrieval weighting.

### Tier 1: Official Government Records (Highest Weight)
- Council minutes (approved by clerk)
- Adopted resolutions and ordinances
- Certified election results
- CAL-ACCESS filings (state-verified)
- Budget documents
- Court records

### Tier 2: Independent Journalism
- **Richmond Confidential** — UC Berkeley Graduate School of Journalism. Student reporters, professional editorial oversight. Independent, well-sourced, occasionally incomplete.
- **East Bay Times / Mercury News** — Regional professional outlet. Less Richmond-specific depth but strong institutional journalism.
- **KQED, Bay Area News Group** — Regional broadcast/print. Covers Richmond intermittently for major stories.

### Tier 3: Stakeholder Communications (Use With Disclosed Bias)
- **Tom Butt E-Forum** — 15+ years of Richmond political commentary. Extraordinary institutional knowledge but reflects personal views and political alliances. Former mayor, current council member. Cite as "according to Council Member Tom Butt's newsletter" — never as neutral fact.
- **Council member newsletters** — Official communications from elected officials. Useful for stated positions; reflect the author's perspective and priorities.
- **Richmond Standard** — Chevron-funded local news site. Professional quality; funding source disclosed per project convention. Always disclose: "Richmond Standard (funded by Chevron Richmond)."

### Tier 4: Community & Social (Context Only, Never Sole Source)
- Nextdoor posts
- Public comments at meetings
- Social media
- Community group communications

**Rule:** Tier 3-4 sources are never used as sole evidence for factual claims. They provide context, surface leads, and represent community perspective. Factual claims must be verified against Tier 1-2 sources.

---

## Richmond-Specific Context

### Why Richmond First

1. **Active, contested local politics.** Rent control fights, Chevron influence, development battles, police oversight. High stakes = high engagement potential.
2. **Digital-first records.** Minutes published as PDFs on Archive Center with predictable URLs. Socrata open data portal (Transparent Richmond) with 300+ datasets. Granicus video archive going back to 2006.
3. **Phillip's Personnel Board seat.** Built-in distribution channel and credibility. Fellow public servant, not outsider vendor.
4. **Manageable scale.** 7 council members, ~24 regular meetings/year, well-defined data sources. Small enough to get right, large enough to prove the concept.
5. **Richmond → Contra Costa County → Bay Area → California.** Natural geographic expansion path.

### Key Political Players (as of 2025)
- **Mayor Eduardo Martinez** — Progressive coalition. Elected 2022.
- **Tom Butt** — Longest-serving council member. Prolific communicator (E-Forum blog). Former mayor.
- **Richmond Confidential** — UC Berkeley journalism program covering Richmond. Key media partner/source.
- **Chevron Richmond** — Major political spender. Funds Richmond Standard. History of campaign spending in local elections.

### Data Characteristics
- Minutes follow highly consistent format post-2020 restructuring
- Vote recording: "Ayes: [names]. Noes: [names]." — extremely parseable
- Socrata portal well-maintained with API access
- Video archive on Granicus (2006-2021) provides rich historical data for backfill
- CAL-ACCESS provides state-level campaign finance going back decades

---

## Development Phases

### Phase 1: Personal Pilot (Months 1-3) ✅
**Goal:** Prove the extraction pipeline works reliably on Richmond data.

- [x] Extract and structure 10+ council meetings (21 meetings extracted)
- [x] Build campaign finance cross-reference (CAL-ACCESS + NetFile = 27,035 combined contributions)
- [x] Generate first real transparency comment and submit during public comment window (Feb 24, 2026)
- [x] Establish Socrata API connection for Transparent Richmond data
- [x] Build basic council member profiles from extracted data
- [x] Validate conflict detection against known cases

**Success metric:** Submit 3 public comments that cite real conflicts or patterns. Get at least 1 acknowledged in meeting minutes.

### Phase 2: Beta (Months 4-6, 50-200 users)
**Goal:** Other people can use it. Basic web interface, alert system, search.

**Completed:**
- [x] Next.js frontend with council member profiles and meeting summaries (7 pages, 21 components, Vercel + Supabase)
- [x] Council member profiles with voting records, top donors, attendance
- [x] Transparency report pages with tiered conflict flag display
- [x] About/methodology page with source credibility tiers and scanner methodology
- [x] Automated pipeline sync via GitHub Actions

**Remaining (priority order):**
1. [ ] Cloud pipeline infrastructure — n8n + GitHub Actions hybrid, Supabase-native data flow, temporal integrity with scan versioning, NextRequest/CPRA ingestion (spec: `docs/specs/cloud-pipeline-spec.md`)
2. [ ] User feedback system — flag accuracy voting, data corrections, tips, bias audit ground truth integration (spec: `docs/specs/user-feedback-spec.md`)
3. [ ] City leadership & top employees — Socrata payroll data, department org charts, staff-to-agenda linking (spec: `docs/specs/city-leadership-spec.md`)
4. [ ] Form 700 ingestion and cross-reference
5. [ ] Commissions & board members — 30+ boards, appointed officials, term tracking (spec: `docs/specs/commissions-board-members-spec.md`)
6. [ ] Document completeness dashboard
7. [ ] Coalition tracking (voting blocs, political faction analysis)
8. [ ] RAG search (pgvector) for natural language queries
9. [ ] Email alert subscriptions (topic + official + geography)
10. [ ] News integration (Richmond Confidential, East Bay Times)
11. [ ] Video transcription backfill (Granicus archive)

**Success metric:** 50 active weekly users. Featured in Richmond Confidential or presented at council meeting.

### Phase 3: Full Richmond (Months 7-12)
**Goal:** Comprehensive coverage. Every meeting, every filing, every vote. The tool residents rely on.

- [ ] Complete historical backfill (2015-present)
- [ ] Planning Commission + Rent Board coverage (partially addressed by commission spec in Phase 2)
- [ ] Property record cross-referencing
- [ ] Automated pre-meeting reports published 48hrs before each meeting
- [ ] Mobile-friendly interface
- [ ] API for external developers
- [ ] Self-healing scraper agents for all data sources

**Success metric:** 500+ active users. City staff or council members reference the tool. Grant funding secured.

### Phase 4: Scale (Year 2+)
**Goal:** Expand beyond Richmond. Prove the model works for any city.

- [ ] Add El Cerrito, San Pablo, or Berkeley as city #2
- [ ] Agent scraper architecture for arbitrary government websites
- [ ] State-level data source connectors (reusable across CA cities)
- [ ] Multi-city comparison features
- [ ] Professional/enterprise tier launch
- [ ] City #10, #50, #100...

**Success metric:** Operating in 5+ cities. Revenue covers operating costs. Clear path to self-sustainability.

---

## North Star for Feature Development

Every feature decision should be filtered through the three monetization paths (see [BUSINESS-MODEL.md](./BUSINESS-MODEL.md)):

1. **Does this make the citizen product more valuable?** (Path A — Freemium)
2. **Does this work for any city, not just Richmond?** (Path B — Horizontal Scaling)
3. **Does this add to the structured dataset?** (Path C — Data Infrastructure)

Features that hit all three are highest priority. Features that hit zero are scope creep.

**Example:** Pre-meeting conflict scanner hits all three. Custom Richmond-specific UI theme hits zero.

---

## What This Is NOT

- **Not a political advocacy tool.** No opinions, no endorsements, no "vote yes/no" recommendations.
- **Not a replacement for journalism.** It replaces the *investigative infrastructure* that local journalism provided. Human journalists are still needed for context, narrative, and accountability.
- **Not adversarial to government.** Framed as helping government work better — a governance assistant, not a watchdog.
- **Not a social network.** No comments section, no user-generated content, no engagement metrics. Information utility, not social platform.
- **Not just Richmond.** Richmond is the pilot. The architecture is city-agnostic from day one (FIPS codes, normalized schema, configurable scrapers).
