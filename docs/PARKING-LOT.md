# Parking Lot — Phase 3: Make It Matter

> **Phase 2** (S1-S20, "Build the Engine") is complete and archived in [SPRINT-ARCHIVE.md](SPRINT-ARCHIVE.md).
>
> **Phase 3** begins post-launch. The project is live at richmondcommons.org. The question shifts from "can we build this?" to "do residents find it useful?"
>
> **Two parallel tracks:**
> - **Track A: Citizen Experience** — features residents see and use
> - **Track B: Intelligence Depth** — scanner precision, entity resolution, operator tools
>
> **Scoring:** Paths **A** = Freemium Platform, **B** = Horizontal Scaling, **C** = Data Infrastructure. Three paths = highest priority. Zero = scope creep.
>
> **Publication tiers:** Public (citizens see it), Operator-only (operator validates first), Graduated (starts operator-only, promoted after review).

---

## Phase 2 Summary

| Sprint | Theme | Key Outcome |
|--------|-------|-------------|
| **S1** | Visibility + Data Foundation | Feature gating, table sorting, commission pages, archive expansion, CI/CD |
| **S2** | Vote Intelligence | 14-category vote taxonomy, category display, AI-generated bios |
| **S3** | Citizen Clarity | Plain language summaries, "Explain This Vote" lite |
| **S4** | Data Quality | Fuzzy duplicate detection, freshness monitoring, alias wiring |
| **S5** | Financial Intelligence | Form 700 ingestion, contribution context enrichment |
| **S6** | Pattern Detection | Coalition analysis, cross-meeting patterns, time-spent stats |
| **S7** | Operator Layer | Decision queue, decision packets, judgment audit, autonomy zones Phase A |
| **S8** | Data Source Expansion | Socrata (5 datasets), court records (dormant), commission meetings (53), body type context |
| **S9** | Scanner v3 | RawSignal architecture, 8 signal detectors, composite confidence, 93.5% false-positive reduction |
| **S10** | Citizen Discovery (Basic) | Full-text search, feedback button, data quality checks. RAG → S22. |
| **S11** | Information Design | Nav restructure (13→5 groups), CivicTerm + SourceBadge, plain English UX, local issue taxonomy |
| **S12** | Citizen Experience v2 | R1: 11,687 items regenerated with v5 prompt. S12.2/S12.5 dropped (subsumed by S14). |
| **S13** | Influence Transparency | Form 803, lobbyist registry (48 records), behested payment loop detector. Entity resolution → S24. |
| **S14** | Discovery & Depth | Meetings redesign (topic board, mini-calendar, calendar grid, category drill-through). Influence map (item + official centers, sentence narratives). |
| **S15** | Pipeline Autonomy | 4-tier scheduled sync (18 sources), sync health dashboard, retry with backoff |
| — | Public/Operator Split | Public nav: Meetings + Council + About. 9 pages + scanner gated behind OperatorGate. |
| **S16** | Content That Clicks | Topic labels (1-2 word subjects per item), plain English default, category badge fix |
| **S17** | Experience Polish | Agenda text formatting, OpenGraph, robots.txt + sitemap, custom 404, responsive polish |
| **S17B** | Election Cycle Accuracy | Election history on cards + profiles, district display, term dates, candidacy status |
| **S19** | Content Depth | Post-meeting minutes (27 linked), scanner cleanup (D27/D23/D17), meeting summaries (I43), category recategorization (4,460 items) |
| **S20** | Public Comment Pipeline | YouTube + Granicus transcripts. 201 items across 71 meetings with verified speaker counts. |
| **S18** | Go Live | richmondcommons.org. Security headers, version 1.0.0, DNS (7 domains), OG social preview. |

> Full details: [SPRINT-ARCHIVE.md](SPRINT-ARCHIVE.md) · 733 commits · 487 tests · 15+ Python modules · 9 pages · 28+ components

---

## Phase 3 Roadmap

### S21 — Community Voice *(Track A)*

*Theme-based comment display replacing speaker counts. First post-launch feature.*

Enhanced transcript extraction (speaker names + summaries) → theme clustering by substantive point → "Community Voice" frontend component. Graceful degradation: themes → raw comments → count only. Publication: Graduated.

**Spec:** `docs/specs/community-voice-spec.md` · **Depends on:** S18 ✅, S20 ✅ · **Est. cost:** ~$10-20 Batch API backfill

**Status:** Phase A ✅ (extractor + migration 068 + 19 tests). Phase B ✅ (theme extractor + prompt + 19 tests, validated on Flock Safety item: 7 themes, 78 assignments). Phase C ✅ (CommunityVoiceSection → "Themes From Comments" component, OperatorGate, query extended with theme joins). Phase D ✅ (backfill complete: 15,883 public_comments, 571 themes, 3,958 assignments, 816 item narratives). Phase E ✅ (written comment extraction pipeline: `written_comment_extractor.py` parses emails from Archive Center PDFs + eSCRIBE eComments via AJAX, 40 tests, $0 API cost). **Graduation pending:** operator review of theme output quality + framing (judgment call).

### S21.5 — Election Season *(Track A, urgent)*

*Use the June 2 primary as the natural hook for citizen discovery and retention. Ship features that make the platform indispensable during election season and retain users afterward.*

**Hard deadline:** June 2, 2026 primary (voter registration deadline May 18). Races: Mayor (5 candidates), District 2 (uncontested), District 3 (2 candidates), District 4 (3 candidates).

**Reference:** [Grandview Independent "On the Agenda" format](https://www.grandviewindependent.com/on-the-agenda-immigration-enforcement-limits-childrens-fund-future-and-a-packed-consent-calendar/) · **Paths:** A, B, C

#### Phase 1: Design Foundation (weeks 1-2)

- **S21.5.1 — Topic/tag UI design audit** — `/frontend-design` critical review of topic label display across the platform. Current rainbow pill tags are visually noisy with arbitrary colors and no hierarchy. Evaluate: semantic color assignment, information hierarchy (not all tags deserve equal weight), density reduction, mobile rendering, alternative patterns to tag clouds. This is foundational — the "On the Agenda" orientation depends on topics communicating clearly.
- **S21.5.2 — Election page promotion** — The `/influence/elections/[id]` page already shows candidate fundraising. Promote it out of OperatorGate to a public-facing `/election/2026-primary` route. Add candidate bios from city website data.

#### Phase 2: Content Engine (weeks 2-4)

- **S21.5.3 — "On the Agenda" meeting orientation** — AI-generated pre-meeting preview highlighting: (1) items with public comment history, (2) big-ticket items (highest financial amounts), (3) long-term impact items that might otherwise be overlooked (land use, contracts, policy changes). Consent calendar collapsed with "items worth watching" called out. New pipeline module + page/component. Uses existing data: `financial_amount`, `public_comment_count`, themes, `category`, `topic_label`. Needs LLM prompt for narrative generation. Publication: Public.
- **S21.5.4 — Meeting recap** — Post-meeting complement: what happened, how each member voted on key items, what the public said. Built on existing vote data + meeting summaries + community voice themes. Publication: Public.

#### Phase 3: Distribution (weeks 3-5)

- **S21.5.5 — Email list** ✅ — `email_subscribers` table (migration 079), Resend integration, `/subscribe` landing page, `/api/subscribe` (POST subscribe + GET unsubscribe), `SubscribeCTA` on meetings + elections pages. Welcome email on subscribe. Service-role RLS. Publication: Public. **Remaining:** Resend account setup + domain verification (human action), weekly digest content (S23).
- **S21.5.6 — Subscription center** — Topic/district/candidate follow preferences. "We'll notify you when new ways to follow Richmond become available." Extends email list with `email_preferences` table. Internal name: "subscriptions" (public-facing name TBD — judgment call).

#### Phase 4: Election-Specific (weeks 4-7)

- **S21.5.7 — Candidate discovery** — Enhanced `/election/2026-primary`: voting record (incumbents), donor profiles (all candidates via NetFile), official statements, "Follow the Money" per candidate. Existing `election_candidates` table + `getElectionWithCandidates()` query provide the foundation. SEO target: "Richmond 2026 election candidates."
- **S21.5.8 — "Find my district"** ✅ — Address lookup → district number → council member + candidates. Extracted 6 district + 36 neighborhood polygons from official ArcGIS redistricting map, Census geocoder proxy, client-side PIP. At `/elections/find-my-district` behind OperatorGate.

#### Other election hooks (weave in as capacity allows)

- **"Your Council Member's Record"** — SEO-optimized entry points for "[council member name] Richmond voting record" searches. Incumbents running for re-election will get searched.
- **"Richmond 101"** — Brief orientation: how city government works, what the council does, when meetings happen, how to participate. Permanent content especially useful for election-season newcomers.
- **"Upcoming meeting" banner** — Persistent site-wide element showing next meeting date/time with link to orientation preview.

**Status:** Wave 3 in progress (2026-04-06).
- ✅ S21.5.1 — Topic/tag UI redesign: replaced rainbow pills with hierarchical proportion-bar layout + muted inline labels
- ✅ S21.5.2 — Election page graduated to public `/elections/2026-primary` with all 11 candidates, fundraising data, voter registration deadline
- ✅ "Upcoming meeting" banner — persistent site-wide element, auto-hides when next meeting is >14 days out
- ✅ Elections added to public nav
- ✅ Election pipeline fix: prefer primary elections over general for candidate matching
- ✅ Migration 071: seed 2026 primary candidates not yet on NetFile (Martinez, Anderson, Wassberg, Bana, Gallon)
- ✅ S21.5.3 — "On the Agenda" orientation: AI-generated pre-meeting preview (3-5 paragraphs, forward-looking narrative with historical topic threading). `generate_orientation_previews.py` + prompt + migration 075 + sky-teal section on meeting detail page. 18 tests. Wired into enrichment pipeline. Publication: Public.
- ✅ S21.5.4 — Meeting recap: AI-generated post-meeting narrative (4-6 paragraphs) covering decisions, split-vote callouts, community voice themes, and continued items. `generate_meeting_recaps.py` + prompt + migration 078 + emerald section on meeting detail page (replaces bullet summary when present). 30 tests. Wired into enrichment pipeline. Publication: Graduated.

### S22 — Search & Similarity *(Track A)*

*Make 15K+ agenda items findable by meaning, not just keywords. Activates Layer 3 of the three-layer DB.*

- **pgvector embedding pipeline** — generate embeddings for agenda items (title + summary + explainer), meeting summaries, and bios. Batch backfill ~$5-10.
- **Semantic search (RAG)** — augment existing `/search` with meaning-based results. Hybrid ranking: keyword matches boosted, semantic matches fill gaps.
- **"Similar Discussions"** — 3-5 related items on item detail pages, weighted by controversy score.
- **Proceeding type classification** — new `proceeding_type` column (censure, resolution, contract, hearing, etc.). LLM classifier following S2.1 pattern. Backfill ~$8-12.
- **Search query analytics** — zero-result tracking, popular entities, operator-only dashboard.

**Depends on:** pgvector extension in Supabase (enabled). · **Paths:** A, B, C

### S23 — Topic Timeline & Digest *(Track A)*

*Let citizens follow issues over time. Builds on S21.5 email infrastructure.*

- **Topic landing pages** — `/topics` index + `/topics/[slug]` chronological timeline with item cards. Builds on S16 topic labels + S21.5.1 tag redesign.
- **"Most Debated" page** — top controversial items across all topics. Uses existing `get_controversial_items()` RPC.
- **Topic-based digest enhancements** — Extend S21.5.5 weekly digest with per-topic summaries for subscribers who follow specific topics.
- **AI comment summaries** — 2-3 sentence narrative synthesis per agenda item. ~$2-5 backfill.

**Depends on:** S21 (for comment summaries). S21.5 (email infrastructure, tag redesign). S16 topic labels ✅. · **Paths:** A, B, C

### S24 — Entity Resolution & Scanner v4 *(Track B, parallel with S21.5)*

*Replace fuzzy text matching with authoritative entity data. Biggest scanner precision improvement since v3.*

- **CA SOS bulk data** — $100 BizFile bulk download (CSV) replaces blocked API/OpenCorporates path. Match 91 entity-like donors against business registry. `business_entities` + `business_entity_officers` tables (migration 040 exists).
- **Contract entity tracking** — `city_contracts` table: vendor, description, annual cost, approval/expiration dates. Cross-reference with contributions and Form 700.
- **Influence pattern taxonomy** — encode 5 of 10 documented patterns as signal detectors (pay-to-play, contract steering, COI in zoning, nonprofit shell, selective enforcement).
- **Full batch rescan** — 800+ meetings, validate against 1,359-flag baseline. ~7 min runtime.
- **Contract frontend** — operator-gated contracts-by-entity page extending influence map.

**Depends on:** $100 CA SOS bulk data purchase (replaces OC/API dependency). · **Paths:** A, B, C

**API status (2026-04-04):** OpenCorporates API denied. CA SOS CBC API application submitted 2026-03-15, still pending — no published SLA. Bulk download is the unblocked path.

### S25 — Open Source & Polish *(Both tracks)*

*Prepare for community contribution. Graduate validated features. Close design debt.*

- **Open source prep** — CONTRIBUTING.md, issue templates, BSL 1.1 license (3-year → Apache 2.0), repo audit for secrets.
- **Feature graduation review** — systematic pass over operator-only features. Each graduation is a judgment call.
- **Guide page** — `/guide`: interactive walkthrough for new visitors linking to real data.
- **Council member photos** — real headshots from city website, `photo_url` on `officials`.
- **Design debt sweep** — items from `docs/design/DESIGN-DEBT.md`.

**Depends on:** S22-S24 operational 1-2 weeks (for graduation review). · **Paths:** A, B, C

---

## Backlog

*Organized by strategic concern. Pulled into sprints during milestone reviews.*

### Data Depth

| ID | Item | Paths | Notes |
|----|------|-------|-------|
| B.8 | Video transcription backfill (Granicus 2006-2021) | A, C | Budget-dependent |
| B.39 | Pre-2022 minutes OCR (Type3-font PDFs) | A, C | 703/706 docs loaded. OCR for empty `raw_text` remaining. |
| B.54 | Bulk document download (~33K docs, 8-15GB corpus) | A, B, C | NextRequest + Archive Center. See AI-PL I50, R9. |
| B.55 | Local LLM triage + Claude deep analysis pipeline | A, B, C | Two-pass: Ollama triage → Claude surgical pass. ~$200-460 vs ~$2,300. |
| S16.4 | Topic label regeneration (~12K items) | A, B, C | ~$40 Batch API. Needs `supabase db push` + backfill sequence. |
| S8.4 | Paper-filed Form 700s | A, C | Gap analysis: cross-ref e-filers vs designated filer list. |

### Intelligence

| ID | Item | Paths | Notes |
|----|------|-------|-------|
| B.47 | Influence pattern taxonomy (remaining 5 of 10 patterns) | A, B, C | After S24 encodes first 5. |
| B.48 | Property transaction timing analysis | A, B, C | CC County CCMAP + RecorderWorks. Form 700 cross-ref. |
| B.53 | Signal type expansion (expenditure patterns, revolving door) | A, B, C | 2 of 4 new signal types complete (permit, license). |
| B.56 | Domain/WHOIS analysis for advocacy orgs | A, B, C | Astroturf indicator. |
| B.57 | OpenCorporates / LittleSis / OpenSecrets integration | A, B, C | Shell org tracing. |
| B.58 | Public comment template analysis | A, B, C | Templated campaign detection. |
| B.59 | Fiscal sponsorship chain detection | A, B, C | 990 Schedule I, "a project of" language. |
| B.60 | Political spend trend detection & early warning | A, B, C | Z-score anomaly on rolling spend windows. |
| B.40-42 | Autonomy zones Phase B-D | A, B, C | Self-healing infrastructure. Phase A (journal) complete. |
| S13.4 | Cross-jurisdiction speaker tracking | A, B, C | Richmond + Oakland + SF. Depends on S13.2. |

### Citizen Experience

| ID | Item | Paths | Notes |
|----|------|-------|-------|
| B.61 | Public comment sentiment + vote alignment | A, B, C | Value: Representation. Graduated. |
| B.62 | Community comment submission to public record | A, B, C | Value: Representation. Spec exists. 5 open decisions. |
| B.9 | Email alert subscriptions | A, B | Requires user accounts (B.33). |
| B.37 | Custom topic trackers (paid) | A, B | Revenue path. Requires B.33. |
| B.43 | Historical cohort filtering for governing bodies | A, B, C | Term data in civic_roles. |
| I44 | Yes/No vote structure in summaries | A, B, C | Depends on R7 (complete). |

### Scale & Future

| ID | Item | Paths | Notes |
|----|------|-------|-------|
| B.20 | Civic Transparency SDK (5-layer, open-core) | B, C | Phase A: formalize conventions. Phase B: extract to package. |
| B.16 | Cross-city policy comparison | A, B, C | Needs 3+ cities + AI topic curation. |
| B.14 | External API / MCP Server | B, C | Civic data as infrastructure. |
| B.33 | User profiles + auth (Supabase Auth) | A, B | Replaces cookie-based OperatorGate. |
| B.23 | Civic role history (`civic_roles` table) | A, B, C | Full public service trajectory per person. |
| B.26 | Unified decision index + chain linking | A, B, C | Cross-body decision tracking. |
| B.27 | Municipal code versioning | A, B, C | Municode snapshots + ordinance linkage. |
| B.28 | Newsletter discovery & ingestion | A, B, C | Tom Butt E-Forum as test case. |
| B.29 | Cityside/Richmondside partnership | A, B, C | Post-validation. |
| B.30 | B2B Municipal Data API | B, C | Revenue: same pipeline, different consumer. |
| B.34 | CLAUDE.md management (multi-level LLM docs) | B, C | Meta-system for AI collaboration quality. |

### Data Foundation (remaining)

| ID | Item | Paths | Notes |
|----|------|-------|-------|
| B.2 | Board/commission member profiles | A, B, C | Extend `officials` beyond council. 30+ commissions. |
| B.3 | Website change monitoring | B, C | Periodic snapshots, diff detection. |
| B.4-7 | Media pipeline (research → registry → linking → monitoring) | A, B, C | Four-stage media integration. |
| B.11 | City Charter compliance engine | A, B, C | Charter as city's CLAUDE.md. Depends on RAG. |
| B.12 | Stakeholder mapping & coalition graph | A, C | Graph problem. Depends on RAG + Form 700. |
| B.13 | "What Are We Not Seeing?" audit | A, B, C | Gap analysis. Needs 6 months ground truth. |
| B.25 | Position ledger + stance timeline | A, B, C | Track positions per person over time. |
| B.31 | Agenda vs. minutes diff | A, B, C | "What was planned vs. what happened." |
| B.35 | Org-candidate support mapping (IEs, endorsements) | A, B, C | Non-contribution political signals. |
| B.50 | Contract & agreement entity tracking | A, B, C | `city_contracts` table. Feeds S24. |

### Hygiene (weave in as needed)

| ID | Item | Trigger |
|----|------|---------|
| H.3 | Auto-documentation of decisions | Next skill refinement |
| H.4 | Research session auto-persist | Next pure research session |
| H.5 | System writes its own CLAUDE.md | After restructuring stabilizes |
| H.6 | Automated prompt regression testing | Next prompt change. Related: H.13 |
| H.7 | Session continuity optimization | Next context-loss incident |
| H.8 | AI-driven persona testing | After frontend MVP stable |
| H.13 | Prompt quality system (registry + eval loop) | After 2-3 manual prompt iterations |

---

## Pipeline Rerun Milestones

*Planned full-pipeline reruns at points where accumulated changes justify the cost.*

**Standing rule:** Any prompt template voice/framing change → regenerate all outputs for that prompt type. AI-delegable. The prompt change itself may be a judgment call.

| ID | Trigger | What to rerun | Est. cost | Depends on | Notes |
|----|---------|---------------|-----------|------------|-------|
| ✅ **R1** | S12.3 (new prompt) | All summaries + headlines (11,687) | ✅ Executed | S12.3 | v5 prompt. 0 errors. |
| ~~**R2**~~ | ~~S12.5~~ | ~~Meeting summaries~~ | — | — | Dropped with S12.5. |
| **R3** | S13.5 (astroturf detectors) | Full scanner rescan (~800 meetings) | ~$0 (CPU) | S13.1-S13.4 | 5 new signal types. ~7 min. |
| **R4** | S24 (entity resolution + patterns) | Full scanner rescan | ~$0 (CPU) | S24.1-S24.4 | Biggest precision improvement since v3. |
| **R5** | H.13 (prompt quality system) | Summaries + explainers + bios | ~$60-100 | Operator feedback console | First data-driven prompt iteration. |

**Cost controls:** Batch API (50% discount) for LLM reruns. Scanner-only reruns free. `--dry-run` to estimate first.

---

## Schema Reservations

Nullable fields already in schema for future features:

| Table | Field | Type | Purpose |
|-------|-------|------|---------|
| `agenda_items` | `discussion_duration_minutes` | INTEGER | Time-spent analytics (S6.3) |
| `agenda_items` | `public_comment_count` | INTEGER | Controversy signal |
| `agenda_items` | `plain_language_summary` | TEXT | Summaries (S3.1) |
| `agenda_items` | `summary_headline` | TEXT | Short-form for cards (S12.3/S14-A) |
| `agenda_items` | `category` | TEXT | Vote categorization (S2.1) |
| `speakers` | `speaking_duration_seconds` | INTEGER | Speaker analytics (B.15) |

### Tables Created

| Table | Status | Migration |
|-------|--------|-----------|
| `elections` + `election_candidates` | ✅ Active | 051 |
| `bodies` | ✅ Active | 035 |

### Future Tables

| Table | Purpose | Depends On |
|-------|---------|------------|
| `civic_roles` | Person role history | B.23 |
| `positions` | Position ledger (stance tracking) | B.25 |
| `city_contracts` | Vendor contracts + spend | B.50 / S24.2 |
| `decision_chains` | Cross-body decision linking | B.26 |
| `code_snapshots` / `code_sections` | Municipal code versioning | B.27 |

---

## Readiness Signals

_Run `cd src && python system_health.py` for the latest._

### Outward-facing (product quality)

| Signal | Measures | Status |
|--------|----------|--------|
| Data accuracy score | Conflict flags vs ground truth | Unvalidated — highest priority gap |
| Pages live & validated | Public pages with validated data | 3 public sections (Meetings, Council, About) |
| Time-to-useful for new visitor | Learn something valuable in 60s? | Needs real user feedback |

### Inward-facing (system health)

| Signal | Measures | Baseline |
|--------|----------|----------|
| Doc benchmark score | CLAUDE.md tree context coverage | 93% |
| Test coverage | Modules with tests | 60% (44/73 tested) |
| Sprint velocity | S1-S20 complete, S21 in progress | 20 sprints in ~30 days |
| City #2 onboarding friction | Hours to add second city | Not tested |

### Risk register

| Risk | Signal to watch | Current status |
|------|----------------|---------------|
| Navel-gazing | Meta-commit ratio > 30% | At boundary |
| Credibility cliff | Data accuracy on published flags | Unvalidated |
| Over-abstraction | `city_config` coupling count | 15 importers |
| Unfunded mandate | Time to onboard city #2 | Unknown |

---

## Reprioritization Cadence

- **Milestone-triggered:** After completing any sprint, review the next sprint's items and the backlog.
- **Weekly fallback:** If no milestone in 7 days, lightweight review of sprint order and backlog.
- **Evidence-based:** Run `python system_health.py` at session start. If regression, investigate before building.
- **Deep restructure:** When significant new capabilities change what's possible.

### Change Log

- **2026-03-27 Phase 3 restructure:** Archived S1-S20 to SPRINT-ARCHIVE.md (810 lines). Introduced dual-track model (Track A: Citizen Experience, Track B: Intelligence Depth). Added S22-S25. Reorganized backlog by strategic concern. Lighter sprint format for Phase 3. Phase 2 change log preserved in archive.
