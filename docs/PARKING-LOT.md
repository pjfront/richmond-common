# Parking Lot — Feature & Improvement Backlog

> All items organized by priority group. Paths: **A** = Freemium Platform, **B** = Horizontal Scaling, **C** = Data Infrastructure. Three paths = highest priority. Zero = scope creep.
>
> **Publication tiers:** Public (citizens see it), Operator-only (Phillip validates first), Graduated (starts operator-only, promoted after review).

---

## Group 0 — Meta/Infrastructure

Process improvements and developer infrastructure. No user-facing features.

### 0.1 CI/CD: Vercel Auto-Deploy + GitHub Actions Tests (HIGH PRIORITY)
- **Problem:** Vercel deploys are manual (`npx vercel --prod`). After PR merges, site serves stale builds. Tests don't run on PRs.
- **Fix:** Connect Vercel to GitHub repo (auto-deploy on push to main, PR previews). Add `.github/workflows/test.yml` (pytest on PR). Add branch protection.
- **Scope:** ~10 min Vercel dashboard + 1 workflow file. No code changes.

### 0.2 Clean Up Deprecated sync-pipeline.yml
- **Problem:** `.github/workflows/sync-pipeline.yml` is deprecated but still in repo. Confusing.
- **Fix:** Delete or rename to `.deprecated`.
- **Scope:** 1 minute housekeeping.

### 0.3 Architecture Self-Assessment ("Tenets Audit")
- **Paths:** B, C
- **Description:** Automated assessment that evaluates the codebase against the four foundational tenets. Detects: hardcoded Richmond logic without city abstraction, missing FIPS columns, human-unique boundary drift, decision velocity bottlenecks.
- **Implementation:** Cron job or CI check. Claude Code has full context to determine what this evaluates and how.
- **Revisit:** First CI pipeline setup, or first architectural drift detected manually.

### 0.4 Auto-Documentation of Decisions and TODOs
- **Problem:** Claude makes architectural choices during implementation without logging to DECISIONS.md or flagging deferred work. Human catches it, violating AI-native philosophy.
- **Fix:** Add step to executing-plans skill: "after each task, check if any new conventions/deferred work were introduced — if so, log in DECISIONS.md before committing." Or CLAUDE.md convention: "every commit introducing a new data structure field or deferred TODO must include a DECISIONS.md entry."
- **Revisit:** Next skill/process refinement session.

### 0.5 Research Session Auto-Persist
- **Problem:** Pure research sessions (web fetches, no code) almost complete without documenting findings. Violates AI-native principle.
- **Fix:** Skill or hook that detects research sessions and auto-writes findings to `docs/research/{topic}.md`.
- **Scope:** `.claude/skills/` or `.claude/hooks/` addition.

### 0.6 System Writes Its Own CLAUDE.md
- **Description:** After each significant feature, the system proposes updates to CLAUDE.md files — new conventions discovered, gotchas learned, architectural patterns. Human reviews diff, not the content.
- **Publication:** Operator-only (Phillip approves all CLAUDE.md changes).
- **Revisit:** After this restructuring stabilizes.

### 0.7 Automated Prompt Regression Testing
- **Paths:** B, C
- **Description:** When extraction prompts change, automatically re-run against a golden set of meetings and diff the output. Catch regressions before they corrupt production data.
- **Implementation:** Store golden input/output pairs in `tests/golden/`. CI step: re-extract -> diff -> fail on unexpected changes.
- **Revisit:** Next prompt template change.

### 0.8 Session Continuity Optimization
- **Description:** Reduce context loss between Claude Code sessions. Auto-generate session handoff notes, maintain a running "state of the world" doc, ensure todo lists persist correctly.
- **Revisit:** Next time a session runs out of context during critical work.

---

## Group 1 — Operator Layer

Tools for Phillip to make faster, better decisions. NOT citizen-facing.

### 1.1 Operator Decision Queue
- **Paths:** A, B
- **Description:** Dashboard showing everything that needs human decision — flags to review, findings to publish, data quality issues, staleness alerts. Pre-digested packets presenting minimum information for fastest correct decision.
- **Publication:** Operator-only.
- **Revisit:** After user feedback system generates enough data to queue.

### 1.2 Pre-Digested Decision Packets
- **Paths:** A, B
- **Description:** For each decision point, the system assembles: the finding, all evidence, comparable past decisions, confidence assessment, and a recommended action — in a format optimized for rapid human judgment.
- **Publication:** Operator-only.
- **Implementation:** Could be a Slack notification, email digest, or web dashboard. Format matters more than channel.
- **Revisit:** Alongside 1.1.

### 1.3 "What Are We Not Seeing?" Audit
- **Paths:** A, B, C
- **Description:** Periodic self-examination that asks: what patterns would exist in this data that our current tools can't detect? What types of conflicts does our scanner structurally miss? Generates a gap analysis with recommended new detection capabilities.
- **Publication:** Operator-only. Feeds roadmap.
- **Revisit:** After 6 months of ground truth data.

### 1.4 Human-Unique Boundary Audit
- **Paths:** B
- **Description:** System periodically reviews all processes marked "requires human" and challenges each one: has technology improved enough to automate this? Conversely, reviews automated processes for ones that should have human oversight.
- **Implementation:** Part of self-advancing system. Cross-reference with tenet #2.
- **Revisit:** Quarterly.

---

## Group 2 — Category Unlock

Categorized votes enable coalition analysis, time-spent stats, and trend tracking. High-leverage unlock.

### 2.1 Vote Categorization Taxonomy & Classifier
- **Paths:** A, B, C
- **Phase:** Next up
- **Description:** Taxonomy of vote categories (land use, public safety, budget, contracts, personnel, etc.). LLM classifier prompt to tag each agenda item/vote. `category` field on `agenda_items` and `votes`.
- **Prerequisite for:** 2.2, 2.3, 2.4, 3.1.

### 2.2 Coalition/Voting Pattern Analysis
- **Paths:** A, B, C
- **Description:** Falls out automatically once vote categorization exists. SQL aggregation on categorized votes — who votes together on what issues, progressive vs. business-aligned blocs, historical alignment shifts.
- **Publication:** Graduated. Start operator-only (coalition framing is politically sensitive).
- **Revisit:** When 2.1 is validated.

### 2.3 Council Time-Spent Stats
- **Paths:** A, B, C
- **Two versions:** (1) Free: category distribution, vote counts by category, controversy score (split vs. unanimous). Just SQL on categorized data. (2) New data: actual minutes per item, public comment duration. Needs transcript quality.
- **Schema ready:** `discussion_duration_minutes` and `public_comment_count` nullable fields on `agenda_items`.
- **Revisit:** Version 1 with 2.1. Version 2 after transcription validated.

### 2.4 Plain Language Agenda Summaries
- **Paths:** A, B, C
- **Description:** `plain_language_summary` field on `agenda_items`. Dedicated prompt template file. Validate on 3-5 pilot meetings.
- **Publication:** Public.

### 2.5 Form 700 Ingestion
- **Paths:** A, B, C
- **Description:** Parse FPPC Form 700 PDFs for economic interest disclosures. Cross-reference against agenda items for council AND commission members. Highest-value conflict detection signal.
- **Research:** `docs/research/form-700-research.md`
- **Revisit:** After commission pipeline stable.

### 2.6 AI-Generated Council Member Bios
- **Paths:** A, B, C
- **Description:** Synthesis prompt combining voting record, campaign filings, committee assignments. "Sunlight not surveillance" framing critical.
- **Publication:** Graduated. Operator-only until framing validated.

---

## Group 3 — Deep Conflict Intelligence

Cross-referencing and pattern detection beyond simple donor-vote matching.

### 3.1 Cross-Meeting Pattern Detection
- **Paths:** A, B, C
- **Description:** "Same donor appears in 3 meetings in 6 months, always on infrastructure items." Patterns invisible in single-meeting view. Time-series analysis over the structured core.
- **Publication:** Graduated.
- **Prerequisite:** Vote categorization (2.1) for meaningful pattern grouping.

### 3.2 Contribution Context Intelligence
- **Paths:** A, B, C
- **Description:** Enrich each contribution flag with context: is this donor's $500 one of many small donations (grassroots) or their only political contribution (targeted)? Does this employer have a pattern of employees donating to the same official? Context transforms raw flags into intelligence.
- **Publication:** Graduated.

### 3.3 Court Records / Tyler Odyssey Integration
- **Paths:** A, B, C
- **Description:** Tyler Technologies' Odyssey platform hosts court records for most US courts. Cross-reference officials, donors, and city contractors against court filings (lawsuits, liens, judgments). Contra Costa County likely uses Odyssey.
- **Implementation:** Start with research — confirm Odyssey availability for Contra Costa County, assess API vs. scraping viability. Platform profile pattern (like eSCRIBE).
- **Publication:** Graduated (legal data requires careful framing).
- **Revisit:** After media pipeline and Form 700.

### 3.4 City Charter Compliance Engine
- **Paths:** A, B, C
- **Description:** Ingest City Charter as structured metadata — the city's `CLAUDE.md`. Continuously diff reality against it. "Charter says Planning Commission shall meet monthly; no meeting in 90 days." "Charter requires 5 Rent Board seats; only 3 filled."
- **Prerequisites:** Commissions + city employees features, RAG search.
- **Revisit:** After commissions and Form 700 ship.

### 3.5 Stakeholder Mapping & Coalition Graph
- **Paths:** A, C
- **Description:** Map stakeholders to positions on issues (including nuanced: "supports goal but opposes implementation"). Enables nay-vote donation correlation, opposition landscape analysis. Graph problem populated from public comments, news, transcripts.
- **Prerequisites:** RAG search, Form 700.
- **Revisit:** After temporal correlation v1 and RAG search operational.

---

## Group 4 — Citizen-Facing Richness

Features that make the public platform more useful and engaging.

### 4.1 Table Sorting/Filtering on All Views
- **Paths:** A, B
- **Phase:** Pure frontend. One afternoon with TanStack Table or similar.
- **Revisit:** Beginning of next frontend sprint.

### 4.2 "Explain This Vote" (AI-Powered)
- **Paths:** A, B
- **Description:** Per-vote explainer: "What was this about? Why did it matter? How did each member vote and why might they have voted that way?" Generated from agenda item + staff report + vote breakdown + historical context.
- **Publication:** Graduated. Inference about motives requires careful framing.
- **Revisit:** After plain language summaries (2.4) validated.

### 4.3 RAG Search (pgvector)
- **Paths:** A, B, C
- **Description:** Natural language search over all documents. Embedding pipeline + search UI page. Uses pgvector in PostgreSQL (no separate vector DB).
- **Prerequisite for:** 3.4, 3.5, and many Group 5 items.

### 4.4 Commission Pages
- **Paths:** A, B
- **Description:** Frontend pages for commission/board data. Member lists, meeting history, appointment tracking, vacancy alerts.
- **Prerequisites:** Commission migration 005 done. Needs commission meeting scraping and frontend components.

### 4.5 Board/Commission Member Profiles
- **Paths:** A, B, C
- **Description:** Expand official profiles beyond council members. 30+ commissions = significant data expansion.
- **Schema ready:** `officials` table accommodates any official type.
- **Revisit:** After council member profile pipeline stable.

### 4.6 Email Alert Subscriptions
- **Paths:** A, B
- **Description:** Topic/official/geography-based alerts. Requires user accounts.
- **Revisit:** After RAG search and user feedback system mature.

### 4.7 AI-Assisted Persona Testing
- **Paths:** A
- **Description:** Use Deep Research to simulate user personas (engaged resident, journalist, council member, new resident) testing the platform.
- **Revisit:** After Phase 2 frontend MVP stable.

### 4.8 Document Completeness Dashboard
- **Paths:** A, B
- **Description:** Track missing/late/incomplete documents per commission and council.
- **Revisit:** After commission meeting scraping operational.

---

## Group 5 — Data Foundation

New data sources and monitoring infrastructure.

### 5.1 Website Change Monitoring & Caching
- **Paths:** B, C
- **Description:** Monitor city government website pages for changes. Cache historical versions. Detect when pages are quietly modified (policy changes, commission roster updates, removed documents). Wayback Machine-style archive for local government.
- **Implementation:** Periodic snapshots + diff detection + alert on significant changes. Start with high-value pages (commission rosters, policy pages, budget documents).
- **Publication:** Public (change notifications). Operator-only (interpretation of changes).

### 5.2 Media Source Research Pipeline
- **Paths:** B, C
- **Description:** Automated discovery and classification of local media sources per city. Search for local news, university journalism programs (Richmond Confidential pattern), corporate-funded outlets (Chevron/Richmond Standard pattern), council member blogs, state press associations. Assign credibility tiers.
- **Challenge:** Reliable tier assignment with ownership/bias disclosure requires editorial judgment that doesn't fully scale with LLMs yet.
- **Revisit:** Second city onboarding or LLM improvement for source classification.

### 5.3 Per-City Media Source Registry
- **Paths:** B, C
- **Description:** Structured `media_sources` table mapping each outlet to credibility tier, ownership/funding, publication frequency, known biases. Richmond's registry becomes the template.
- **Depends on:** 5.2 for automated discovery.

### 5.4 News Integration & Article Linking
- **Paths:** A, B, C
- **Description:** Associate agenda items with relevant news articles. `news_items` table + `agenda_item_news` junction + `news_item_officials` junction. Matching: keyword/entity-based initially, LLM-refined later.
- **Richmond sources:** Richmond Confidential, East Bay Times, KQED (Tier 2); Tom Butt E-Forum, Richmond Standard (Tier 3, disclose bias).
- **Depends on:** 5.3 for multi-city scaling.

### 5.5 Local Media Monitoring & Investigation Triggers
- **Paths:** A, B, C
- **Description:** Monitor local news to detect emerging topics, then automatically assemble relevant meeting history, votes, contributions, contracts. Framed as "automated context building."
- **Depends on:** 5.3, 5.4.

### 5.6 Archive Center Expansion (CivicPlus Document Discovery)
- **Paths:** B, C
- **Description:** Expand from AMID=31 to all 149 active archive modules. Download PDFs for high-priority AMIDs (resolutions, ordinances, commission minutes) into Layer 1. Defer extraction until RAG search needs it.
- **Already decided:** See DECISIONS.md 2026-02-22 entry.

### 5.7 Video Transcription Backfill
- **Paths:** A, C
- **Description:** Granicus archive (2006-2021) via Deepgram/Whisper. Extends historical record significantly.
- **Revisit:** After current pipeline stable and budget allows.

---

## Group 6 — Future/Scale

Long-horizon items for multi-city scaling and platform maturity.

### 6.1 External API / MCP Server
- **Paths:** B, C
- **Description:** Expose structured civic data as API and/or MCP server for third-party tools, journalists, researchers. Position as civic data infrastructure.
- **Revisit:** Stable schema, multiple cities onboarded, external interest.

### 6.2 Speaker Diarization Analytics (Paid Feature Candidate)
- **Paths:** A, B, C
- **Description:** Speaker identification + speaking time analytics. Expensive (~$0.50-1.00/meeting hour). Free tier = transcripts/summaries/votes. Paid tier = speaking analytics, time breakdowns, trends.
- **Schema ready:** `speaking_duration_seconds` nullable field on `speakers`.
- **Quick test:** Richmond YouTube auto-captions have timestamps. Test if they approximate item-level timing cheaply.
- **Revisit:** Transcription pipeline working, cost reduction, or paid tier development.

### 6.3 Cross-City Policy Comparison
- **Paths:** A, B, C
- **Description:** Search/compare policies, ordinances, proclamations, and resolutions across cities. "Find other cities that passed similar rent control ordinances." "What did Oakland do about this?" Semantic similarity over structured civic data from multiple cities.
- **Implementation:** Requires RAG search (4.3) + multi-city data + document type classification. Could be the killer feature for horizontal scaling — journalists and policy researchers would use this.
- **Revisit:** After 3+ cities onboarded with RAG search.

### 6.4 Civic Website Modernization Platform
- **Paths:** A, B, C
- **Description:** Use scraping framework to generate modern, accessible city websites. Offer free, host on clean domains. Business: license cities to adopt, or sell data access to journalists. Craigslist-kills-classifieds play.
- **Note:** Different product, different buyer (city IT vs. citizens). Government sales cycles 6-18 months. Requires rock-solid multi-city data first.
- **Revisit:** 5-10 cities running.

### 6.5 Civic Knowledge Graph
- **Paths:** B, C
- **Description:** Entity-relationship graph connecting officials, donors, organizations, agenda items, votes, news articles, court records, contracts. Enables questions like "show me everything connected to this developer" or "what's the full network of this PAC?"
- **Prerequisites:** Multiple data sources cross-referenced, RAG search, stakeholder mapping (3.5).
- **Revisit:** After Form 700, court records, and news integration.

### 6.6 Domain Strategy
- **Description:** .city, .fyi, .ai extensions. City-agnostic domain vs. per-city subdomains. Credibility signaling.
- **Revisit:** Before public launch.

### 6.7 System Definition Portability (Model Migration Tool)
- **Paths:** B
- **Description:** Abstract the CLAUDE.md hierarchy and all system self-knowledge into model-agnostic metadata stored in the cloud. Currently, the system's identity (architecture principles, conventions, practical knowledge, context rules) is coupled to Claude Code's CLAUDE.md convention. Portable metadata format enables: (1) periodic benchmarking against other models (Gemini, GPT, open-source) without rewriting system prompts, (2) migration to a different AI platform if economics or capabilities shift, (3) model-to-model A/B testing on the same extraction tasks. Build a migration tool that translates system definition → target model's prompt format and runs comparison benchmarks.
- **Connects to:** Architecture principle #8 (build now, optimize compute later) and self-advancing system (model adaptation). This is the infrastructure layer that makes model adaptation possible.
- **Revisit:** When a competing model significantly outperforms Claude on extraction benchmarks, or when the project needs vendor independence for institutional credibility.

---

## Schema Fields to Add Now (Future-proof)

Nullable fields to include in current schema so future features don't need migrations:

| Table | Field | Type | Purpose |
|-------|-------|------|---------|
| `agenda_items` | `discussion_duration_minutes` | INTEGER (nullable) | Time-spent analytics (2.3) |
| `agenda_items` | `public_comment_count` | INTEGER (nullable) | Controversy signal (2.3) |
| `agenda_items` | `plain_language_summary` | TEXT (nullable) | Summaries (2.4) |
| `agenda_items` | `category` | TEXT (nullable) | Vote categorization (2.1) |
| `speakers` | `speaking_duration_seconds` | INTEGER (nullable) | Speaker analytics (6.2) |
| `officials` | (design for any official type) | — | Board/commission expansion (4.5) |
