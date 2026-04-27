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

#### Foundation: trust the system (precondition for everything else)

| ID | Item | Notes |
|----|------|-------|
| S24.0 | ✅ Pipeline liveness layer | Manifest `expectations:` block + `pipeline_map.py liveness` runner + `analyze_pipeline_liveness()` in SessionStart health report + Layer-3 anon-visibility test (`tests/test_anon_visibility.py`) + CI test enforcing critical-owner expectation coverage. Catches silent pipeline failures (e.g., the 2026-04 missing-recap bug that surfaced via Facebook reader feedback). 14 expectations declared at first commit. Triggered by 2026-04-25 reckoning: lineage system built 2026-03-17 traced *structure* but not *runtime reality*. |

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
| S24.14 | ✅ Automated agenda preview emails | `/api/email/send-orientation` (migration 090: `meetings.orientation_emailed_at`). Wired into `data-sync.yml` — broadcasts after each escribemeetings enrichment cascade. New subscribers also receive the next upcoming meeting's preview at signup (migration 091: `email_subscribers.last_orientation_meeting_id` prevents duplicates). Publication: graduated from operator-only to automated. |

#### Platform reliability

| ID | Item | Notes |
|----|------|-------|
| S24.11 | RPC audit | Audit all `supabase.rpc()` calls for silent-failure patterns. From AI-PL I117. |
| S24.12 | Pipeline post-sync ISR revalidation | Auto-revalidate affected paths after data sync. From AI-PL I104. |
| S24.13 | Design debt quick wins | Cherry-pick highest-impact items from `docs/design/DESIGN-DEBT.md`. |

#### Accuracy under public scrutiny *(triggered by 2026-04-25 first-reader feedback)*

A real user (Leisa Johnson) found the site organically and surfaced three accuracy issues. Each pointed at a deeper gap — see `JOURNAL.md` Entry 21+ for the full reckoning. S24.0 (foundation) ships first; the rest fan out in parallel after.

| ID | Item | Notes |
|----|------|-------|
| S24.15 | ✅ Vote display: motion text vs item title | Shipped 2026-04-25. Pass `motion.motion_text` through page.tsx to VotingRecordTable; render motion text below item title for single-motion rows; expand multi-motion groups inline showing each motion's vote choice + truncated text. |
| S24.16 | Procedural motion surfacing audit | After S24.15, audit every place agenda-item-title is rendered alongside vote data. Public-tier components first; defer operator-only. |
| S24.17a | ✅ NetFile sync cadence: weekly → daily | Shipped 2026-04-25. Added `daily-netfile` job in `.github/workflows/data-sync.yml` triggering on the existing 7am UTC daily cron with `--enrich`. |
| S24.17b | Type-20 (F497 late contributions) reconsideration | `netfile_client.py:431` skips type-20 due to API flake. Either enable with retry, or add transparent disclosure on candidate pages. Disclosure framing is a judgment call. |
| S24.18 | ✅ Investigation: 2024 contribution accuracy | Shipped 2026-04-25. Found 6 duplicate candidacies (Jamelia Brown, Claudia Jimenez 2024, Cesar Zepeda, Soheila Bana, Doria Robinson, +1) — same official, same election, two `election_candidates` rows with conflicting metadata (e.g., one "filed" with FPPC ID, one "elected" with FPPC NULL). DB has 154 contributions / $76,114 for Claudia's 2024 committee. Added `no_duplicate_candidacies_per_election` liveness expectation to surface these. **S24.18a follow-up** (deferred): reconcile each duplicate — merge metadata into the canonical (usually "elected") record, delete the orphan. |
| S24.19 | ✅ Do nothing on pre-launch posture | Operator decision 2026-04-25. Site stays fully indexable, no preview banner. |
| S24.20a | ✅ Recap pipeline state verification | `post-meeting-recap.yml` runs daily, `YOUTUBE_PROXY` secret is empty, KCRT video discovery fails on day-1 timing. 1 of 6 recent meetings has a transcript_recap. Documented in S24.20b–f. |
| S24.20b | ✅ YOUTUBE_COOKIES wired through transcript fetch | Shipped 2026-04-25. Cookies in GitHub secret + Deno + `--remote-components ejs:github` solves YouTube's n-challenge. yt-dlp can now fetch auto-captions from KCRT live-streams as soon as they're available. Plus `--video-id` workflow_dispatch input for manual override when title-based discovery fails (e.g., live-stream titles without dates). |
| S24.20c | Multi-day retry window for transcript fetch | Re-attempt for ~5 days after each meeting until success or give-up. KCRT uploads aren't always next-morning. Currently the daily cron only checks "yesterday's meeting." With cookies+Deno solver now working, this becomes worth doing — videos that didn't have captions on day 1 can be picked up day 3-5. |
| S24.20d | ✅ Refine recap liveness expectations (DAG was already correct) | Shipped 2026-04-25. Investigation showed DAG is wired (pipeline_map trace confirms recap_generation downstream of minutes_extraction). Real bottleneck is minutes_url=NULL on old meetings (city minutes scraper coverage). Split conflated expectation into `past_meetings_have_minutes_within_45_days` (escribemeetings_minutes, medium) and `meetings_with_motions_have_recap` (recap_generation, high). |
| S24.20e | Operator visibility panel for recap state | Per-meeting recap state (transcript? minutes? generated when? source?) so silent failures become visible. Complements S24.0 SessionStart liveness section. |
| S24.20f | ✅ Backfill 4/21 + 3/17 transcript recaps (3/24 partial) | Shipped 2026-04-25. After S24.20b unblocked: 4/21 (3,027 char recap, Craneway Pavilion) and 3/17 (3,143 char recap, $350K police radios) both backfilled via `--video-id` override. 3/24 still missing — KCRT discovery can't find the video via title regex; operator action required to either provide video URL or improve discovery (S24.20c follow-up). |
| S24.22 | ✅ Canonical names — fix transcript phonetic misspellings | Shipped 2026-04-25. Created `src/prompts/canonical_names.md` (auth-list of Richmond council + external civic figures with phonetic alias notes), wired into `transcript_recap`, `meeting_recap`, `comment_summary`, `theme_extraction` prompts. Triggered by Leisa-recap finding "John Joya" (auto-caption phonetic for "John Gioia"). Existing recaps regenerate with new prompt when cookies are refreshed. |
| S24.22b | ✅ Name-correction pass on existing recaps | Shipped 2026-04-25. Built `src/correct_recap_names.py` — Claude pass over existing recap text using `canonical_names.md` as authority. ~$0.05 per recap, no YouTube cookies needed. Migration 093 added `transcript_recap_corrected_at` column. Corrected 3 historical recaps: 4/21 (Joya→Gioia), 4/07 (Aleshire), 3/17 (Zapeda→Zepeda). |
| S24.22c | ✅ Canonical names from city payroll + auto-sync | Shipped 2026-04-26. Built `src/sync_canonical_names.py` — auto-regenerates the "Richmond City Council" and "Richmond Municipal Staff" sections of `canonical_names.md` from `officials` + `city_employees` DB tables. Preserves hand-curated "Often misheard as:" aliases. Idempotent. Replaced "to verify / add" placeholders with 18 verified municipal-staff entries (City Manager Kinshasa Curl, Finance Director Emily Combs, Fire Chief Aaron Osorio, Police Chief Bisa French + Timothy Simmons, etc.). Re-ran `correct_recap_names.py --all` → fixed Combmes→Combs in 4/21 and Tim→Timothy Simmons in 3/17. Total cost $0.05. |
| S24.24 | ✅ Daily archive_center sync + written_comments liveness | Shipped 2026-04-26. Added `daily-archive-center` job to `data-sync.yml` triggered on the 7am UTC daily cron; chains `archive_center → written_comments` with `if: always()`. Diagnosed via Leisa-finding for 4/21: city posted comment PDFs mid-week but our weekly Monday sync didn't catch them until 5 days later. New liveness expectation `past_meetings_have_written_comments_within_7_days` (owner=written_comments, severity=medium) flags any regular meeting >7 days old with zero `comment_type='written'` rows. Currently passing — all recent meetings have written comments after today's manual reload. |
| S24.23 | ✅ Transcript-based vote extraction (preliminary motions/votes) | Shipped 2026-04-26. Closes the 4-6 week minutes lag — vote outcomes from `transcript_recap` text now appear in the per-item vote display within 1-3 days of the meeting. Migration 094 added `source` columns to `motions`+`votes`. New `src/extract_transcript_votes.py` (Claude pass over recap text + agenda items + roster, ~$0.05/meeting) writes preliminary rows with `source='transcript'`. New prompt `src/prompts/transcript_vote_extraction_system.txt`. Wired into `data_sync.SYNC_SOURCES` + `pipeline-manifest.yaml` as enrichment downstream of `recap_generation`. `db.py::save_meeting_data` deletes `source='transcript'` rows before inserting `source='minutes'` (ground truth wins). Frontend (`VoteRollCall.tsx`) surfaces an amber "Tentative — auto-captioned recording" badge for transcript-sourced motions with explanatory tooltip. Backfill: 4/21 (Craneway 3-4 rejection + ALS 7-0 unanimous), 4/07 (Children & Youth Fund + ICE-free zone + Traffic Impact contract, all 7-0), 3/17 ("no extractable matches" — see S24.23b: this was wrong, the recap had omitted Flock entirely). 5 motions, 35 votes, $0.04 total. |
| S24.23c | ✅ Project-wide Anthropic temperature audit | Shipped 2026-04-26. Follow-up to S24.23b. The 5/0/4 variance on `extract_transcript_votes.py` was caused by the Anthropic SDK defaulting `temperature` to 1.0 when not set — operator asked whether the same bug existed elsewhere. Audited every `client.messages.create()` site in `src/` (25 files, 25 sites). 24 of 25 were missing `temperature=` entirely → SDK default 1.0. Set `temperature=0` explicitly at all 24 remaining sites: 15 STRUCTURED extractors (extract_agenda, pipeline, appointment_extractor, form700_extractor, lobbyist_client, nextrequest_extractor, granicus_transcripts, youtube_comments, correct_recap_names, data_sync proceeding-classifier, batch_classify_proceeding, batch_recategorize, theme_extractor, community_voice_extractor, self_assessment) — AI-delegable per `judgment-boundaries.md`; 9 CREATIVE generators (generate_meeting_recaps, generate_meeting_summaries, generate_comment_summaries, generate_orientation_previews, post_meeting_recap, plain_language_summarizer, batch_summarize, vote_explainer, bio_generator) — advisory opinion citing stewardship + representation, accepted by operator. Added convention to `.claude/rules/conventions.md` so future sites get caught without another audit. Tests unchanged (1992 passed, 11 pre-existing failures verified identical via `git stash` baseline). Cost: $0. Pattern: when fixing a bug rooted in a library default, ask whether the project depends on that default elsewhere — almost always yes. |
| S24.23b | ✅ Switch transcript-vote extraction to raw transcripts | Shipped 2026-04-26. Operator caught that the 3/17 meeting page displayed a `meeting_recap` saying "the council did not vote on any action items, including a Flock Safety contract extension" — but Flock actually passed 4-3 that night. Investigation revealed two stacked failures: (a) the curated `transcript_recap` had omitted Flock entirely (the most-discussed item), and (b) `extract_transcript_votes.py` was reading `transcript_recap` rather than the persisted raw auto-caption at `data/transcripts/{date}_clean.txt`. Fixes: (1) extractor now prefers raw transcript with recap fallback (raw 4/07 reliably returned 0 motions on a 354K-char input — recap fallback recovered all 3 substantive votes); temperature=0 for determinism. (2) Strengthened prompt to filter procedural/time-extension motions. (3) Tightened `generate_meeting_recaps.py` vote gate from "any motion" to "source='minutes' motion" — transcript-derived motions are no longer sufficient input. (4) `MeetingNarrative.tsx` now branches on `hasMinutesMotions` to show an honest source label ("agenda items, public comments, and the meeting recording — vote outcomes preliminary until minutes") instead of falsely claiming "official minutes and vote records". (5) NULLed the verifiably-wrong 3/17 `meeting_recap` (page now falls back to `transcript_recap` which has its own honest "KCRT recording" attribution). After re-extraction: 3/17 has 4 substantive motions (Flock 4-3 ✓, John Haley landmark 6-0-1, rail crossing procurement 7-0, mid-year budget 7-0). Cost ~$0.50 across all 3 meetings. |
| S24.21 | Auto paper-filing pipeline | RSS feed monitor → PDF download → Claude Vision extraction → auto-load. Currently manual (4 candidates loaded, others pending). Pre-primary high-value. ~$5/cycle Anthropic API cost. |
| S24.18a | ⚙ Reconcile 6 duplicate candidacies (4 done, 5 cases pending operator verification) | **2026-04-26 progress:** (1) Merged 4 clean dups (Bana, Jimenez, McLaughlin, Brown) — research row preserved, augmented with `fppc_id` + `is_incumbent` from netfile, netfile orphan deleted. (2) Patched `elections_client.py` netfile loader to UPSERT on `(official_id, election_id)` instead of `(election_id, normalized_name, office_sought)` so research-vs-netfile `office_sought` drift no longer creates duplicates. (3) Investigation of remaining "conflict" pairs (Doria, Cesar) revealed structural bug: research seeding linked the 2022 candidacies to the candidates' **2026 reelection committees**, not their 2022 election committees. NetFile rows were correct. (4) Found 3 more cases of cycle-mismatched committee links (Willis 2020 → 2024 committee; Bana's two 2026 candidacies → 2022 committee). (5) New liveness expectation `candidacy_committee_cycle_matches` (5 failures) catches this class of bug going forward. **Pending:** operator runs through `docs/research/2026-04-26-candidacy-committee-verification.md` (10-min NetFile portal eyeball check), confirms the 5 fixes; AI executes and the liveness check goes to 0 failures. |
| S24.20b-2 | Refresh YouTube cookies (parked) | Cookies rotated by YouTube during S24.20b testing. Required for fresh recap generation from YouTube auto-captions. **Currently parked — operator low-bandwidth.** Mitigation: `correct_recap_names.py` and `extract_transcript_votes.py` both work without cookies (operate on existing `transcript_recap` text), so 4/21 / 4/07 / 3/17 backfills are complete. Only impact of parked state: NEW meetings can't be recap'd until cookies refresh OR Granicus transcripts come online. Liveness expectation `past_meetings_have_transcript_recap_within_5_days` will keep flagging this until refreshed. Operator can refresh by extracting `cookies.txt` from a logged-in YouTube session and updating GitHub secret `YOUTUBE_COOKIES`. |
| S24.25 | ✅ Hide all donations from public view (council + candidates) until validation | Shipped 2026-04-26. Operator decision triggered by Leisa-finding for Claudia Jimenez 2024 contribution accuracy concern. New `DonationsUnderReview` placeholder component with links to NetFile + CAL-ACCESS source records. Wrapped in `OperatorGate` on every public-facing donations surface: council profile Campaign Contributions section, CandidateCard financial block, RaceSection narrative paragraphs, CandidateRosterStrip dollar/donor span, ElectionPage header narrative. Operators continue to see full data. Public sees the placeholder + source links. Re-enable for public by removing the OperatorGate wraps once underlying ingestion is verified. |
| S24.25-verify | ⚙ Donor data spot-check (Claudia + 2 others) | New `src/verify_donor_data.py` prints per-committee report cards (totals, top donors, recent contributions, NetFile portal URL) for any official, so the operator can compare line-by-line against NetFile in ~2 min. Usage: `python verify_donor_data.py --name "Claudia Jimenez"` or `--all-current`. Verification trigger for re-enabling S24.25 public donations. |

**Weave in as capacity allows:**
- Operator settings human-readable labels (AI-PL I102)
- Email delivery idempotency tracking (AI-PL I106)

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
