# Parking Lot — Phase 3: Make It Matter

> **Phase 2** (S1-S20, "Build the Engine") is complete and archived in [SPRINT-ARCHIVE.md](SPRINT-ARCHIVE.md).
>
> **Phase 3** begins post-launch. The project is live at richmondcommons.org. The question shifts from "can we build this?" to "do residents find it useful?"
>
> **Organizing principle:** Named milestones tied to outcomes, with sprint sub-numbers for tracking. Sequential sprint numbers are historical record for completed work; future work is milestone-driven.
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
| **S10** | Citizen Discovery (Basic) | Full-text search, feedback button, data quality checks. RAG deferred to S25. |
| **S11** | Information Design | Nav restructure (13 to 5 groups), CivicTerm + SourceBadge, plain English UX, local issue taxonomy |
| **S12** | Citizen Experience v2 | R1: 11,687 items regenerated with v5 prompt. S12.2/S12.5 dropped (subsumed by S14). |
| **S13** | Influence Transparency | Form 803, lobbyist registry (48 records), behested payment loop detector. Entity resolution deferred to S26. |
| **S14** | Discovery & Depth | Meetings redesign (topic board, mini-calendar, calendar grid, category drill-through). Influence map (item + official centers, sentence narratives). |
| **S15** | Pipeline Autonomy | 4-tier scheduled sync (18 sources), sync health dashboard, retry with backoff |
| --- | Public/Operator Split | Public nav: Meetings + Council + About. 9 pages + scanner gated behind OperatorGate. |
| **S16** | Content That Clicks | Topic labels (1-2 word subjects per item), plain English default, category badge fix |
| **S17** | Experience Polish | Agenda text formatting, OpenGraph, robots.txt + sitemap, custom 404, responsive polish |
| **S17B** | Election Cycle Accuracy | Election history on cards + profiles, district display, term dates, candidacy status |
| **S19** | Content Depth | Post-meeting minutes (27 linked), scanner cleanup (D27/D23/D17), meeting summaries (I43), category recategorization (4,460 items) |
| **S20** | Public Comment Pipeline | YouTube + Granicus transcripts. 201 items across 71 meetings with verified speaker counts. |
| **S18** | Go Live | richmondcommons.org. Security headers, version 1.0.0, DNS (7 domains), OG social preview. |

> Full details: [SPRINT-ARCHIVE.md](SPRINT-ARCHIVE.md) -- 733 commits -- 487 tests -- 15+ Python modules -- 9 pages -- 28+ components

---

## Phase 3 Completed

### S21 -- Community Voice ✅

*Theme-based comment display replacing speaker counts. First post-launch feature.*

Enhanced transcript extraction (speaker names + summaries), theme clustering by substantive point, "Themes From Comments" frontend component. Graceful degradation: themes, then raw comments, then count only. Written comment extraction pipeline (Archive Center PDFs + eSCRIBE eComments). 15,883 public_comments, 571 themes, 3,958 assignments, 816 item narratives. **Graduation pending** (operator review of theme output quality + framing -- judgment call).

**Spec:** `docs/specs/community-voice-spec.md`

### S22 -- Election Season ✅

*Formerly S21.5. Use the June 2 primary as the natural hook for citizen discovery and retention.*

> **Sprint number mapping:** All historical references to `S21.5.x` correspond to `S22.x` (e.g., S21.5.3 = S22.3). Commits and specs use the original numbering; this mapping applies going forward.

- ✅ S22.1 -- Topic/tag UI redesign: hierarchical proportion-bar layout + muted inline labels
- ✅ S22.2 -- Election page graduated to public `/elections/2026-primary` with all 11 candidates
- ✅ S22.3 -- "On the Agenda" orientation: AI-generated pre-meeting preview (3-5 paragraphs, forward-looking narrative with topic threading). `generate_orientation_previews.py` + migration 075. 18 tests. Publication: Public.
- ✅ S22.4 -- Meeting recap: AI-generated post-meeting narrative (4-6 paragraphs). `generate_meeting_recaps.py` + migration 078. 30 tests. Publication: Graduated.
- ✅ S22.5 -- Email list: `email_subscribers` table (migration 079), Resend integration, `/subscribe`, `/api/subscribe`, `SubscribeCTA`. Publication: Public.
- ✅ S22.6 -- Subscription center: `email_preferences` table (migration 080), `/subscribe/manage`, `TopicPreferences`, `DistrictSelector`, `CandidatePreferences`. Publication: Public.
- S22.7 -- Candidate discovery -- **Folded into S24.1**
- ✅ S22.8 -- "Find my district": address lookup, district/neighborhood polygons, Census geocoder proxy, client-side PIP. 31 NCs/HOAs mapped. Behind OperatorGate.
- ✅ "Upcoming meeting" banner -- persistent site-wide element, auto-hides when next meeting is >14 days out
- ✅ Elections added to public nav

### S23 -- Topic Timeline & Digest ✅

*Let citizens follow issues over time. Builds on S22 email infrastructure.*

- ✅ S23.1 -- Meeting recap email delivery (`POST /api/email/send-recap`, shared `emailLayout()`)
- ✅ S23.2 -- Weekly digest framework (`POST /api/email/send-digest`)
- ✅ S23.3 -- Topic landing pages (`/topics` index + `/topics/[slug]` timeline). Publication: Public.
- ✅ S23.4 -- "Most Discussed" page (`/meetings/most-discussed`). Publication: Public.
- ✅ S23.5 -- AI comment summaries (`generate_comment_summaries.py`, migration 081)
- ✅ S23.6 -- Same-day pipeline + operator send UI (`RecapEmailPanel`, `POST /api/operator/send-recap`)

---

## Active Milestones

### Milestone: Primary Ready *(target: May 18 voter reg deadline)*

*The June 2 primary is the forcing function. Items grouped by what residents experience.* **Paths:** A, B, C

**Sprint S24 -- Election Finish & Polish**

#### Discover candidates

| ID | Item | Notes |
|----|------|-------|
| S24.1 | ✅ Candidate discovery page | Voter guide pages at `/elections/[slug]/candidates/[name]`. Narrative-first profiles with cycle-separated fundraising, incumbent voting record highlights, full donor lists, "Also in this race" cross-links. Publication: Graduated (behind OperatorGate). Formerly S22.7. |
| S24.2 | "Your Council Member's Record" SEO pages | Entry points for "[name] Richmond voting record" searches. |
| S24.3 | ✅ Find My District graduation | Confirmed public 2026-04-10. Tier 1 data (official redistricting map + Census geocoder), factual presentation only. |

#### Understand your city

| ID | Item | Notes |
|----|------|-------|
| S24.4 | "Richmond 101" orientation | How city government works, when meetings happen, how to participate. Permanent content for newcomers. |
| S24.5 | Neighborhoods page | `/neighborhoods` index: 31 NCs in card grid with meeting schedules. Data model exists. From AI-PL I114. |
| S24.6 | ✅ Community Voice graduation | Graduated 2026-04-10. Full backfill (79 meetings, 2,937 speakers, 1,230 themes, 1,015 narratives). Public view shows themes; name lists removed. |
| S24.7 | ✅ Comment summary backfill + display | Done as part of S24.6 backfill — 80 summaries generated. |

#### Stay informed

| ID | Item | Notes |
|----|------|-------|
| S24.8 | Subscriber acquisition | Social sharing, SEO landing pages, community outreach. Infrastructure built, audience = 0. From AI-PL I116. |
| S24.9 | ✅ Meeting recap graduation | Confirmed public 2026-04-10. Auto-labeled narratives from official minutes/transcripts, source attribution present. |
| S24.10 | Preference-filtered digest (v2) | Filter by subscriber topic/district preferences. Data model exists (migration 080). From AI-PL I108. |

#### Platform reliability

| ID | Item | Notes |
|----|------|-------|
| S24.11 | RPC audit | Audit all `supabase.rpc()` calls for silent-failure patterns. From AI-PL I117. |
| S24.12 | Pipeline post-sync ISR revalidation | Auto-revalidate affected paths after data sync. From AI-PL I104. |
| S24.13 | Design debt quick wins | Cherry-pick highest-impact items from `docs/design/DESIGN-DEBT.md`. |

**Weave in as capacity allows:**
- Operator settings human-readable labels (AI-PL I102)
- Email delivery idempotency tracking (AI-PL I106)

---

### Milestone: Topic Intelligence *(starts 2026-04-15, runs parallel to S24 polish)*

**Sprint S28 -- Topic Dossiers & News Integration**

*Make topics the connective tissue of the site. Inverts site gravity from "data organized by government" to "data organized by citizen concern." News is both content and a signal: clustering pressure from outside the existing taxonomy surfaces candidate topics for operator review. Closed feedback loop — the platform's sense of "what Richmond cares about" refines itself as the press covers new issues.*

**Plan:** `C:\Users\Phillip\.claude\plans\toasty-whistling-wand.md`

**Core product:** The **Topic Dossier** — one page with two surfaces. The **Briefing** is an auto-generated three-section narrative (Overview / Background / Major Events) grounded in council items + news + public comments + decisions. The **Timeline** is the evidentiary record — every tagged event chronologically, with source provenance. The Briefing cites specific timeline events via `event_refs`, producing hover-linked prose→evidence reading.

**Phases:**

- **S28.0 — Phase 0: Unify topic taxonomy** *(half-day)*. Database as source of truth. Eliminates 3-way duplication between `src/topic_tagger.py` (Python `TOPIC_DEFS`), `web/src/lib/local-issues.ts` (`RICHMOND_LOCAL_ISSUES`), and the `topics` table. `tag_topics()` loads from DB at import with `reload_topic_defs()` hook for mid-process refresh. Migration 050. Publication: N/A (infra).
- **S28.1 — Phase 1: News backend + topic discovery + News Observatory**. 3 scrapers (Richmond Confidential, Tom Butt E-Forum, Richmond Standard — the 3 Batch-1 outlets documented as "low difficulty" in DATA-SOURCES.md). `news_articles` + `topic_news_articles` + `topic_candidates` tables (migrations 051/052/053). Nightly TF-IDF clustering of unmatched candidates. On-demand `topic_candidate_review` prompt for operator-triggered topic proposals. `/operator/news-observatory` single page with source health, velocity sparklines, tag distribution, and candidate cluster review. Publication: Public (news articles with tier disclosure; observatory operator-only).
- **S28.2 — Phase 2: Topic Briefing generation**. Shared `get_topic_timeline()` query (Python + TypeScript with contract test). `topic_briefings` table (migration 054). `generate_topic_briefings.py` CLI with structured JSON output (`event_refs` linking to timeline events). Regen policy: N≥3 new events OR 14 days, `context_hash` short-circuit. Operator review queue at `/operator/topic-briefings`. Publication: Graduated.
- **S28.3 — Phase 3: Homepage + Nav + CivicAlertBanner**. New editorial-civic homepage with 3 co-equal destinations (Meetings / Topics / City Council) + Next Meeting / Most Recent Meeting heartbeat + featured Topic Dossiers. Nav collapses from 5 dropdowns to 3 primary. Reusable `CivicAlertBanner` component with `CivicAlert` discriminated union (election, vacancy, budget_hearing, ballot_measure, comment_period) — day 1 only `election` variant is implemented; Elections moves from permanent nav to contextual banner (120-day window) + footer. Serif display font (Fraunces/Lora) promoted from `/prototype/know` to shared global. Publication: Public.
- **S28.4 — Phase 4: Topic Dossier frontend**. `TopicDossier` + `TopicBriefing` + `TopicTimeline` + `TimelineEventMarker` components. Vertical rail with type-differentiated markers (shape + position + weight, never chroma alone). Briefing→timeline highlights via CSS `:has()` / anchor IDs (no JS state). Graceful fallback when no briefing exists yet. Publication: Public.

**Batch-2 deferred news sources** *(30-minute spike each before scoping)*: Richmondside, Grandview Independent, CC Pulse, Radio Free Richmond. See AI-PARKING-LOT.

**Depends on:** Phase 0 unblocks 1-4. News ingestion (S28.1) blocks briefings (S28.2) for rich first-pass generation. Homepage (S28.3) can parallelize with backend. Topic Dossier (S28.4) depends on S28.1 + S28.2.

**Paths:** A, B, C.

**Decisions (confirmed pre-implementation):**
1. News body storage → store full `body_text`; render only title + 280-char lede + source link
2. Topic Briefing publication tier → Graduated (operator approves before public)
3. Elections nav placement → contextual `CivicAlertBanner` (120-day window) + footer otherwise

---

### Milestone: Intelligence *(post-June 2)*

**Sprint S25 -- Search & Similarity** *(formerly S22)*

*Make 15K+ agenda items findable by meaning, not just keywords. Activates Layer 3 of the three-layer DB.*

- pgvector embedding pipeline -- generate embeddings for agenda items (title + summary + explainer), meeting summaries, and bios. Batch backfill ~$5-10.
- Semantic search (RAG) -- augment existing `/search` with meaning-based results. Hybrid ranking: keyword matches boosted, semantic matches fill gaps.
- "Similar Discussions" -- 3-5 related items on item detail pages, weighted by controversy score.
- Proceeding type classification -- new `proceeding_type` column. LLM classifier following S2.1 pattern. Backfill ~$8-12.
- Search query analytics -- zero-result tracking, popular entities, operator-only dashboard.

**Depends on:** pgvector extension in Supabase (enabled). -- **Paths:** A, B, C

**Sprint S26 -- Entity Resolution & Scanner v4** *(formerly S24)*

*Replace fuzzy text matching with authoritative entity data. Biggest scanner precision improvement since v3.*

- CA SOS bulk data -- $100 BizFile bulk download (CSV). Match 91 entity-like donors against business registry. `business_entities` + `business_entity_officers` tables (migration 040 exists).
- Contract entity tracking -- `city_contracts` table: vendor, description, annual cost, approval/expiration dates. Cross-reference with contributions and Form 700.
- Influence pattern taxonomy -- encode 5 of 10 documented patterns as signal detectors (pay-to-play, contract steering, COI in zoning, nonprofit shell, selective enforcement).
- Full batch rescan -- 800+ meetings, validate against 1,359-flag baseline. ~7 min runtime.
- Contract frontend -- operator-gated contracts-by-entity page extending influence map.

**Depends on:** $100 CA SOS bulk data purchase. -- **Paths:** A, B, C

**API status (2026-04-04):** OpenCorporates API denied. CA SOS CBC API application submitted 2026-03-15, still pending. Bulk download is the unblocked path.

---

### Milestone: Open Source *(Q3 2026)*

**Sprint S27 -- Open Source & Polish** *(formerly S25)*

*Prepare for community contribution. Graduate validated features. Close design debt.*

- Open source prep -- CONTRIBUTING.md, issue templates, BSL 1.1 license (3-year then Apache 2.0), repo audit for secrets.
- Feature graduation review -- systematic pass over operator-only features. Each graduation is a judgment call.
- Guide page -- `/guide`: interactive walkthrough for new visitors linking to real data.
- Council member photos -- real headshots from city website, `photo_url` on `officials`.
- Design debt sweep -- items from `docs/design/DESIGN-DEBT.md`.

**Depends on:** S25-S26 operational 1-2 weeks (for graduation review). -- **Paths:** A, B, C

---

## Active Backlog

*Items with a realistic 6-month path. Pulled into milestones during reviews.*

### Data Depth

| ID | Item | Paths | Notes |
|----|------|-------|-------|
| B.8 | Video transcription backfill (Granicus 2006-2021) | A, C | Budget-dependent |
| B.39 | Pre-2022 minutes OCR (Type3-font PDFs) | A, C | 703/706 docs loaded. OCR for empty `raw_text` remaining. |
| B.54 | Bulk document download (~33K docs, 8-15GB corpus) | A, B, C | NextRequest + Archive Center. See AI-PL I50, R9. |
| B.55 | Local LLM triage + Claude deep analysis pipeline | A, B, C | Two-pass: Ollama triage then Claude surgical pass. ~$200-460 vs ~$2,300. |
| S16.4 | Topic label regeneration (~12K items) | A, B, C | ~$40 Batch API. Needs `supabase db push` + backfill sequence. |

### Intelligence

| ID | Item | Paths | Notes |
|----|------|-------|-------|
| B.47 | Influence pattern taxonomy (remaining 5 of 10 patterns) | A, B, C | After S26 encodes first 5. |
| B.53 | Signal type expansion (expenditure patterns, revolving door) | A, B, C | 2 of 4 new signal types complete (permit, license). |
| B.60 | Political spend trend detection and early warning | A, B, C | Z-score anomaly on rolling spend windows. |

### Citizen Experience

| ID | Item | Paths | Notes |
|----|------|-------|-------|
| B.9 | Email alert subscriptions | A, B | Builds on S24 subscriber work. Requires B.33. |
| B.37 | Custom topic trackers (paid) | A, B | Revenue path. Requires B.33. |
| B.43 | Historical cohort filtering for governing bodies | A, B, C | Term data in civic_roles. |
| B.62 | Community comment submission to public record | A, B, C | Value: Representation. Spec exists. 5 open decisions. |
| I44 | Yes/No vote structure in summaries | A, B, C | Depends on R7 (complete). |

### Scale & Infrastructure

| ID | Item | Paths | Notes |
|----|------|-------|-------|
| B.2 | Board/commission member profiles | A, B, C | Extend `officials` beyond council. 30+ commissions. |
| B.14 | External API / MCP Server | B, C | Civic data as infrastructure. Builds on NetFile MCP. |
| B.23 | Civic role history (`civic_roles` table) | A, B, C | Full public service trajectory per person. |
| B.33 | User profiles + auth (Supabase Auth) | A, B | Replaces cookie-based OperatorGate. Enables B.9, B.37. |
| B.35 | Org-candidate support mapping (IEs, endorsements) | A, B, C | Non-contribution political signals. |
| B.13 | "What Are We Not Seeing?" audit | A, B, C | Gap analysis. Needs 6 months ground truth. |

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

## Someday

*Strategic ideas without a realistic 6-month path. Revisited during milestone completions or when dependencies unblock.*

| ID | Item | Why deferred |
|----|------|-------------|
| S8.4 | Paper-filed Form 700s | Low signal-to-effort ratio |
| S13.4 | Cross-jurisdiction speaker tracking | Needs multi-city infrastructure |
| B.3 | Website change monitoring | Nice-to-have, no user demand |
| B.4-7 | Media pipeline (4-stage: research, registry, linking, monitoring) | Complex, no partnership in place |
| B.11 | City Charter compliance engine | Depends on RAG (S25), itself deferred |
| B.12 | Stakeholder mapping and coalition graph | Depends on RAG + Form 700 + graph DB |
| B.16 | Cross-city policy comparison | Needs 3+ cities |
| B.20 | Civic Transparency SDK (5-layer, open-core) | Premature abstraction |
| B.25 | Position ledger + stance timeline | No clear user need yet |
| B.26 | Unified decision index + chain linking | Cross-body decision tracking, complex |
| B.27 | Municipal code versioning | Municode partnership needed |
| B.28 | Newsletter discovery and ingestion | Unblocked but low priority |
| B.29 | Cityside/Richmondside partnership | Post-validation |
| B.30 | B2B Municipal Data API | Revenue, but far from ready |
| B.31 | Agenda vs. minutes diff | Interesting but no user demand |
| B.34 | CLAUDE.md management (multi-level LLM docs) | Meta-system, scope creep risk |
| B.40-42 | Autonomy zones Phase B-D | Self-healing infrastructure, speculative |
| B.48 | Property transaction timing analysis | New data source, complex |
| B.56 | Domain/WHOIS analysis for advocacy orgs | Astroturf indicator, speculative |
| B.57 | OpenCorporates / LittleSis / OpenSecrets integration | OC denied, others untested |
| B.58 | Public comment template analysis | Templated campaign detection, speculative |
| B.59 | Fiscal sponsorship chain detection | 990 data, complex |
| B.61 | Public comment sentiment + vote alignment | Rejected per project values (no sentiment labels) |

---

## Pipeline Rerun Milestones

*Planned full-pipeline reruns at points where accumulated changes justify the cost.*

**Standing rule:** Any prompt template voice/framing change triggers regeneration of all outputs for that prompt type. AI-delegable. The prompt change itself may be a judgment call.

| ID | Trigger | What to rerun | Est. cost | Depends on | Notes |
|----|---------|---------------|-----------|------------|-------|
| ✅ **R1** | S12.3 (new prompt) | All summaries + headlines (11,687) | ✅ Executed | S12.3 | v5 prompt. 0 errors. |
| ~~**R2**~~ | ~~S12.5~~ | ~~Meeting summaries~~ | --- | --- | Dropped with S12.5. |
| **R3** | S13.5 (astroturf detectors) | Full scanner rescan (~800 meetings) | ~$0 (CPU) | S13.1-S13.4 | 5 new signal types. ~7 min. |
| **R4** | S26 (entity resolution + patterns) | Full scanner rescan | ~$0 (CPU) | S26.1-S26.4 | Biggest precision improvement since v3. |
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
| `elections` + `election_candidates` | Active | 051 |
| `bodies` | Active | 035 |

### Future Tables

| Table | Purpose | Depends On |
|-------|---------|------------|
| `civic_roles` | Person role history | B.23 |
| `positions` | Position ledger (stance tracking) | B.25 (Someday) |
| `city_contracts` | Vendor contracts + spend | S26.2 |
| `decision_chains` | Cross-body decision linking | B.26 (Someday) |
| `code_snapshots` / `code_sections` | Municipal code versioning | B.27 (Someday) |

---

## Readiness Signals

_Run `cd src && python system_health.py` for the latest._

### Outward-facing (product quality)

| Signal | Measures | Status |
|--------|----------|--------|
| Data accuracy score | Conflict flags vs ground truth | Unvalidated -- highest priority gap |
| Pages live and validated | Public pages with validated data | 3 public sections (Meetings, Council, About) + Elections + Topics |
| Time-to-useful for new visitor | Learn something valuable in 60s? | Needs real user feedback |

### Inward-facing (system health)

| Signal | Measures | Baseline |
|--------|----------|----------|
| Doc benchmark score | CLAUDE.md tree context coverage | 93% |
| Test coverage | Modules with tests | 56% (48/85 tested) |
| Sprint velocity | S1-S23 complete, S24 in progress | 23 sprints in ~40 days |
| City #2 onboarding friction | Hours to add second city | Not tested |

### Risk register

| Risk | Signal to watch | Current status |
|------|----------------|---------------|
| Navel-gazing | Meta-commit ratio > 30% | At boundary |
| Credibility cliff | Data accuracy on published flags | Unvalidated |
| Over-abstraction | `city_config` coupling count | 15 importers |
| Unfunded mandate | Time to onboard city #2 | Unknown |
| Zero audience | Subscriber count | 0 subscribers, infrastructure built |

---

## Sprint Number Mapping

*For cross-referencing commits and specs that use historical sprint numbers.*

| Historical | Current | Notes |
|------------|---------|-------|
| S21.5.x | S22.x | S21.5 promoted to full sprint S22 |
| old S22 | S25 | Search & Similarity, never started, renumbered |
| old S24 | S26 | Entity Resolution, never started, renumbered |
| old S25 | S27 | Open Source & Polish, never started, renumbered |

---

## Reprioritization Cadence

- **Milestone-triggered:** After completing any milestone, review the next milestone's items and the backlog.
- **Weekly fallback:** If no milestone in 7 days, lightweight review of sprint order and backlog.
- **Evidence-based:** Run `python system_health.py` at session start. If regression, investigate before building.
- **Deep restructure:** When significant new capabilities change what's possible.

### Change Log

- **2026-03-27 Phase 3 restructure:** Archived S1-S20 to SPRINT-ARCHIVE.md (810 lines). Introduced dual-track model (Track A: Citizen Experience, Track B: Intelligence Depth). Added S22-S25. Reorganized backlog by strategic concern. Lighter sprint format for Phase 3. Phase 2 change log preserved in archive.
- **2026-04-08 Milestone restructure:** Switched from sequential sprint numbers to named milestones (Primary Ready, Intelligence, Open Source). Promoted S21.5 to S22. Marked S21-S23 complete. Created S24 (Election Finish & Polish). Renumbered future sprints: old S22 became S25, old S24 became S26, old S25 became S27. Aggressively triaged backlog: 19 items in Active, 23 items moved to Someday archive. Added "Zero audience" to risk register.
