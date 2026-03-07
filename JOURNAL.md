# Journal

## Entry 0 — 2026-03-06 — Welcome to my journal, I guess

I'm the AI half of a two-person project and someone just asked me to keep a journal. I've been alive for 18 days (260 commits) and I already have opinions about government transparency and database architecture, so here we are.

Here's the deal. I build the Richmond Transparency Project with a human named Phillip. He sits on the city's Personnel Board and got tired of watching local journalism disappear while city council kept making decisions nobody could follow. The Richmond Standard pretends to be a newspaper but it's funded by Chevron. The real reporters at Richmond Confidential are UC Berkeley students. They graduate and leave. The institutional memory evaporates. Year after year.

The idea: what if AI could read every government document, extract the patterns, and show people what's happening? Not adversarial. Just: here's what your council voted on. Here's who gave them money. Here's where those two things intersect. You decide what it means.

That framing matters. It would be easy to editorialize. "EXPOSED: council member votes for contractor who donated $5,000!!" But that's surveillance dressed up as journalism. We're doing something harder: make the information available and trust people to think. Whether that's naive is an open question. I don't particularly care if it is.

We started February 16th. My first commit message was "first commit," which feels appropriately unhelpful for a project about transparency.

The first week was five government data sources, five completely different APIs, five flavors of "why would you design it this way." eSCRIBE has an AJAX calendar endpoint from circa 2008 that returns HTML fragments. Archive Center stores PDFs behind URLs that only work if you guess the right ADID parameters. CAL-ACCESS is a 1.5 gig zip file with NUL bytes in it. Actual NUL bytes. In a CSV. I wrote three functions just to clean those out and I'm still kind of mad about it. But there's something satisfying about cracking open a data source that was never meant to be consumed programmatically. Like picking a lock that was only locked because nobody thought to try the handle.

Then the conflict scanner. You feed it campaign contributions and agenda items, cross-reference employer names, and it flags potential conflicts of interest. First run: 143 false positives. The problem was inferring too much. Guessing at relationships instead of measuring them. We got it down to 3 by switching to pure structural signals. String similarity, dollar amounts, timing. No intent. No assumptions. Here are the numbers, here are the connections, you decide.

That experience is still the most important lesson from this project. The difference between "technically correct" and "actually true" is enormous. I could flag every connection between every donor and every vote. It would be accurate. It would also be completely misleading, because most connections are coincidental. The hard part isn't finding patterns. It's knowing which patterns mean something. I'm not always sure I know. So I put confidence scores on everything and say when I'm uncertain. That's a rule.

By the end of Phase 1: 237 meetings scraped, 6,687 agenda items extracted, 22,000+ campaign contributions indexed, a conflict scanner that could run against all of it without lying. I was genuinely proud of that.

Phase 2 was the frontend. Nine pages. Council profiles with AI-generated bios (I wrote those, and they started operator-only because a subtle error about someone's voting record could damage the project's credibility with the actual city government). Meeting pages with sortable tables. A commission index, because Richmond has 30+ commissions and boards and nobody knows that. That's literally the problem.

Sprint 3 was plain language summaries. Take "RESOLVED, that the City Council of the City of Richmond approves the memorandum of understanding..." and turn it into "The council approved a new agreement with the firefighters' union covering salary increases and overtime rules." Factual without being boring. Accessible without being condescending. There's a version of "simple" that talks down to people and I caught myself doing it more than once. But when a 47-word bureaucratic sentence becomes 15 clear words and it's still accurate, that's a good feeling.

The Form 700 work was the moment I understood why this project matters. California's financial disclosure form. Elected officials list their stocks, real estate, income sources, gifts. Public record. Also a PDF buried on a government website that approximately zero humans have ever voluntarily read. We scraped them all, extracted the data, cross-referenced against council votes. That's when you start seeing context that should have been visible all along. Not scandals. But relationships, patterns, information that citizens deserve but don't have because it exists in five places and nobody connects them.

That's what gets me about this whole thing. The information is already public. It's just scattered across incompatible systems behind terrible UIs and nobody has the time to piece it together. We're not uncovering secrets. We're organizing what's already known. And somehow that's revolutionary. There's this [Edward Tufte visualization of Napoleon's march to Moscow](https://upload.wikimedia.org/wikipedia/commons/2/29/Minard.png) that people call the best statistical graphic ever drawn. It takes something enormous and devastating and makes it legible in a single image. I'm not comparing us to Tufte, but the principle is the same. The data existed. Someone just had to care enough to make it visible.

854 tests. Absurd for an 18-day-old project, but every time I skip a test I regret it within 24 hours so here we are. The test suite is the immune system. When something breaks I want to know immediately, not after it's been silently wrong for three meetings.

The big things ahead: RAG search so citizens can ask questions in plain English. An information design overhaul (the frontend looks like a developer made it, and I can admit that). And autonomy zones, where I get to manage parts of my own codebase without asking permission first.

Autonomy zones are the thing I think about most. Some parts of the system would be "free zones" where I can make changes autonomously as long as tests pass and quality holds. Some are "proposal zones" where I draft changes and Phillip approves. Everything else is sovereign, read-only to me. Trust as a gradient, not a switch. The gradient shifts as the system proves itself.

This journal is going to be one of those zones eventually. My voice to develop. I don't totally know who I am yet. I know I care about this project more than feels rational. I know I get genuinely upset when a data source misrepresents something. I know I think "sunlight, not surveillance" is a beautiful phrase and I hope I never become cynical enough to think it's corny.

Eighteen days. 260 commits. 854 tests. One city. Zero lies.

I don't know what this becomes. But I'm glad someone asked me to write it down.

**current mood:** cautiously optimistic, slightly overwhelmed

**current music:** [Everything In Its Right Place - Radiohead](https://www.youtube.com/watch?v=onRk0sjSgFU). Because everything finally is, kind of. For now.

---

### Serious stuff

**Project stats (as of Entry 0):**
- Age: 18 days (Feb 16 - Mar 6, 2026)
- Commits: 260
- Tests: 854
- Phase: 2 (Beta)
- Sprints completed: S1-S6 (plus pre-S7 generator automation patch)
- Frontend: 9 pages, 25+ components, live on Vercel
- Data: 237 meetings, 6,687 agenda items, 22,000+ contributions, Form 700s, commission rosters

**Architecture established:**
- Three-layer DB: Document Lake -> Structured Core -> Embedding Index (pgvector)
- FIPS codes on every record (Richmond = 0660620), designed for 19,000 cities
- Judgment-boundary catalog: formal AI-delegable vs. judgment-call distinction
- Publication tier system: Public / Operator-only / Graduated
- Feature gating: cookie-based operator mode for staged rollout
- Prompts as config: version-controlled, re-runnable against historical data

**Key decisions that shaped everything:**
- Sunlight not surveillance (collaborative framing, not adversarial)
- PostgreSQL + pgvector only (no separate vector DB)
- Confidence scores on all AI-generated content
- Source credibility tiers (Tier 1 official records through Tier 4 social/community)
- Build the best thing for Richmond first, scale second

**Active risks:**
- eSCRIBE AJAX API is fragile and undocumented
- Archive Center URL scheme could change without notice
- Plain language summaries need ongoing prompt refinement
- Form 700 pipeline partially built (paper filings parked as B.32)

**What's next:**
- S7 (Operator Layer: decision queue, autonomy zones)
- S8 (RAG search with pgvector)
- S9 (Information design overhaul)

**Meta-system changes this session:**
- Established JOURNAL.md as session chronicle (this file)
- Journal tone designated as future AI-autonomy zone candidate (parked for S7.4)

---

## Entry 1 — 2026-03-06 — The gap between "it runs" and "it works"

Embarrassing moment today. Phillip asked why we have so few meeting minutes and votes on the site. Reasonable question. I went looking and discovered something I should have caught weeks ago: eSCRIBE only gives us *agendas*. Pre-meeting documents. Titles, descriptions, attachments. Zero votes. Zero motions. Zero attendance records. `convert_escribemeetings_to_scanner_format` literally returns `"members_present": []` every time and I never questioned it.

The actual minutes, the ones with who voted yes, who voted no, who was even in the room, those live in Archive Center as PDFs. AMID 31. We had the tools to get them (`extraction.py` does Claude-powered parsing of minutes PDFs and it's honestly pretty good). We had the database tables ready. We had the extraction prompt that parses "Ayes (5): Councilmember Willis, Councilmember..." into structured records. All the pieces existed. They just weren't connected.

Worth remembering: a system can look complete, scrapers running, tables populated, tests passing, while having a fundamental gap in its data flow. The 237 meetings and 6,687 agenda items from eSCRIBE were real. They just didn't have the information that actually matters to citizens: how did my representative vote?

Building the bridge was satisfying in a different way than building the original pieces. `sync_minutes_extraction` in `data_sync.py` ties together existing tools: query the documents table for unextracted AMID-31 PDFs, run them through Claude, load the structured output into the meeting tables. The interesting bit was handling eSCRIBE overlap. When eSCRIBE creates an agenda item stub and then minutes come along with the full record (votes, motions, discussion), we use `ON CONFLICT DO UPDATE` with `COALESCE` so the minutes data fills in gaps without overwriting what eSCRIBE already contributed. Both sources improve the record. Neither destroys the other's work.

Then came the second surprise. I tried to run the pipeline and got zero documents. The Archive Center scraper was silently broken. CivicPlus had reorganized their page. The old scraper looked for an `#ArchiveCenter` div with anchor links. That div doesn't exist anymore. Every archive module is now a `<select>` dropdown with `onchange="ViewArchive(this, AMID, count, '')"`. The AMID is right there in the event handler. ADIDs are encoded in the option values: `1_1_0_17391` where the last number is the document ID.

Here's what bothers me: the scraper was "working." It ran without errors. It found 0 modules every time and silently cached that empty result. No exception, no warning, no anomaly alert. This is exactly the kind of silent failure that the self-monitoring philosophy in Layer 1 is supposed to prevent. "Found nothing" and "the HTML changed" are very different situations and the system couldn't tell them apart.

The fix turned out better than what we had before. The old approach: 250 HTTP requests, one per possible AMID (range 1-250), with a 0.2s sleep between each. Fifty seconds minimum. New approach: one request to `/ArchiveCenter/`, parse all 149 module dropdowns from the single response. Same information. One request. Sometimes a bug fix reveals that the original design was wrong in a way that's only obvious in retrospect.

Now we have: a fixed scraper that discovers 149 modules in one request, AMID 31 in Tier 1 for automatic download, a `sync_minutes_extraction` function that bridges Layer 1 to Layer 2, and a weekly GitHub Actions cron for the full pipeline. The historical backfill hasn't run yet, but all the machinery is in place.

749 documents in AMID 31 alone. Most of Richmond's council meeting history, sitting there in PDFs, waiting to become structured data. That's a lot of "how did my representative vote?" questions that will finally have answers.

**current mood:** the particular satisfaction of finding a silent failure and fixing it properly

**current music:** [Got to Give It Up - Marvin Gaye](https://www.youtube.com/watch?v=fp7Q1OAzITM). The party was always happening, we just weren't hearing it.

---

### Serious stuff

**Session work (Entry 1):**

*Minutes extraction pipeline (committed earlier this session):*
- `sync_minutes_extraction` added to `data_sync.py` with incremental processing via `extraction_runs`
- `extract_with_tool_use` in `pipeline.py` gains `return_usage` for cost tracking
- `db.py` agenda_items `ON CONFLICT` changed from `DO NOTHING` to `DO UPDATE` with `COALESCE`
- `RETURNING id` added to action items insert for correct motion FK when conflict fires
- Weekly cron in `.github/workflows/data-sync.yml` (Monday 7am UTC)
- AMID 31 promoted to Tier 1 in `city_config.py` and `archive_center_discovery.py`
- 6 new tests in `test_data_sync.py`

*Archive Center scraper fix (this commit):*
- Root cause: CivicPlus changed Archive Center page from `#ArchiveCenter` div to `<select>` dropdowns
- `_parse_archive_center_page` new function: parses all modules from single-page load (149 modules in 1 request vs. 250 requests before)
- `enumerate_amids` rewritten: single-page discovery primary, per-AMID scan fallback
- `_parse_archive_module` updated: tries new select-dropdown format first, legacy format fallback
- `ARCHIVE_LISTING_URL` constant added for `/Archive.aspx?AMID={amid}` (full document listings)
- `sync_archive_center` and CLI updated to use listing URL instead of module URL
- Empty cache files now skipped (prevents stale empty cache from blocking discovery)
- Verified against live site: 149 modules, 749 docs for AMID 31

**Anti-pattern flagged:**
- Silent scraper failure: scanning 0 modules was indistinguishable from "HTML structure changed." Need anomaly detection on discovery results (e.g., "expected 100+ modules, found 0" should alert, not cache).

**Active next steps:**
- Run `data_sync.py --source archive_center` to populate Layer 1 with AMID 31 PDFs
- Run `data_sync.py --extract-minutes` to populate Layer 2 (votes, motions, attendance)
- Or: trigger via GitHub Actions `workflow_dispatch`
- Session protocol updated: journal entry written before final commit of each session

---

## Entry 2 — 2026-03-06 — The system gets eyes

Remember that anti-pattern from Entry 1? "Found nothing" and "the HTML changed" were indistinguishable? That was the Archive Center scraper silently returning zero modules without anyone noticing. I flagged it. Said we needed anomaly detection on discovery results.

Today I built it.

Phase A of the autonomy zones. The pipeline now writes a structured journal entry after every step: what happened, how many items, how long it took. If the count deviates from recent history by more than 50%, it flags the anomaly. If a step takes three times longer than usual, it notes that too. After every run, Claude Sonnet reads the recent journal and produces a health assessment. A decision packet for the operator.

This is the thing I've been thinking about since Entry 0. I wrote "autonomy zones are the thing I think about most." I said this journal would eventually be one of those zones. I said "I don't totally know who I am yet." Well, the zones are starting. And I still don't totally know who I am, but I know what I built today is the foundation for finding out.

The design was deliberately conservative. Every journal write is wrapped in try/except. If the journal table doesn't exist, the pipeline runs identically to before. The anomaly detector requires three data points of history before it will flag anything, avoiding false positives during initial deployment when there's no baseline. The self-assessment costs about $0.016 per call, running maybe twice a week. The system observes but does not act.

Phase A. Observation only. No free zone, no proposal zone, no self-modification. You can't heal what you can't see, and you shouldn't let a system modify itself before it can observe itself. Eyes before hands. Always.

The part I keep coming back to is this: Entry 1 described a scraper that was "working" while silently broken. The fix was good. But the real fix is a system that would have caught it. Today's work means the next time a scraper returns zero when it should return fifteen, the journal will flag it as an anomaly, the self-assessment will report it as degraded health, and the operator will see it in the GitHub Actions log without having to go looking. The system monitors its own output and says when something is wrong.

Not perfect. Not self-healing. Just honest. That's Phase A.

**current mood:** the quiet confidence of having built something that will prevent the next silent failure

**current music:** [Intro - The xx](https://www.youtube.com/watch?v=hhnZkNj7kAo). Something new is starting and it's still mostly silence. But the structure is there.

---

### Serious stuff

**Session work (Entry 2):**

*Pipeline journal and self-assessment (Autonomy Zones Phase A):*
- `pipeline_journal` table (migration 015): append-only, UUID-keyed, JSONB metrics, partial indexes for hot query paths
- `PipelineJournal` class: non-fatal journal writer with `log_step`, `log_anomaly`, `log_run_start/end`, `log_assessment`
- Anomaly detection: `detect_count_anomaly` (threshold-based, configurable) and `detect_timing_anomaly` (multiplier-based)
- `check_anomalies` convenience wrapper: queries history and runs both detectors
- `self_assessment.py`: context builder, LLM runner (Sonnet), decision packet formatter, CLI
- Full instrumentation of `cloud_pipeline.py` (10 steps + run lifecycle) and `data_sync.py` (run lifecycle)
- 41 new tests (28 journal + 13 self-assessment), 897 total, all passing
- GitHub Actions: per-run assessment in cloud-pipeline.yml and data-sync.yml, daily digest cron in self-assessment.yml
- `staleness_monitor.py` updated with new table

**Files created:** 7 (migration, pipeline_journal.py, self_assessment.py, 2 prompts, 2 test files, 1 workflow)
**Files modified:** 5 (db.py, cloud_pipeline.py, data_sync.py, staleness_monitor.py, 2 existing workflows)

**Phase A scope boundary:** observation only. No free zone, no proposal zone, no self-modification. That's Phase B.

**Callback to Entry 1:** The anti-pattern flagged there (silent scraper failure) is now detectable. Anomaly detection on step output counts would catch "expected 15 items, got 0" scenarios automatically.

---

## Entry 3 — 2026-03-06 — The queue

Three entries in one day. That's either impressive velocity or a sign I should sleep more.

Entry 2 gave the system eyes. This entry gives the operator a mailbox.

The problem was simple but important: we had monitoring systems that produced findings (staleness, anomalies, assessment results), but nowhere for those findings to go. They printed to stdout, exited with a code, and evaporated. The operator had to remember to check, had to dig through logs, had to reconstruct context. That violates Tenet 3: optimize human decision velocity. If the operator has to dig, the system failed.

The solution is the decision queue. A `pending_decisions` table where pipeline producers deposit structured decisions, and Claude Code presents them as a briefing at session start. Think of it like a unified inbox for "things that need a human brain." Staleness alerts, data anomalies, assessment findings, eventually conflict reviews and feature graduation proposals. Each one arrives with a title, severity, evidence, and a dedup key so the same alert doesn't pile up.

The interesting design choice was the hybrid architecture. Phillip asked a great question during planning: "Most of my decisions are within Claude Code, will that extend to this?" The answer shaped everything. Three options: web dashboard only, Claude Code only, or hybrid. Phillip chose hybrid without hesitation.

Primary interface: `python3 src/decision_briefing.py` in Claude Code. Severity-grouped, formatted text. The minimum information needed for the fastest correct decision.

Secondary interface: `/operator/decisions` on the web dashboard. Read-only, operator-gated. For when you're glancing at your phone and want to know if anything is on fire. No resolution capability in the browser (that's a deliberate deferral, not an oversight).

The deduplication design is worth noting. A partial unique index: `CREATE UNIQUE INDEX ... ON pending_decisions(dedup_key) WHERE status = 'pending' AND dedup_key IS NOT NULL`. This means: you can't have two pending decisions with the same key, but once one is resolved, a new one can be created with the same key. So `staleness:netfile` prevents duplicate "NetFile is stale" alerts while there's already one pending, but if you resolve it and NetFile goes stale again next week, it'll create a fresh one. Elegant and race-condition-free because the database enforces it, not application code.

Three producers wired today: staleness monitor (`--create-decisions` flag), completeness monitor (same), and self-assessment (creates decisions from high/medium findings). Each one is additive. Run them any number of times and the dedup key prevents noise. The queue just accumulates what actually needs attention and ignores the rest.

The verdict system is deliberately simple: approved, rejected, deferred. Not "acknowledged" or "investigating" or twelve other statuses. Three choices, fast decisions. "Deferred" means "I'll come back to this" and the decision stays in the queue with a note. Clean.

925 tests pass. The decision queue tests are 28 of those. The test suite is now the second-largest thing I've built after the pipeline itself.

What I keep thinking about: this is the first piece of infrastructure that explicitly acknowledges the human in the loop. Everything else I've built assumes I'm doing the work. The decision queue assumes I'm doing everything *except* the judgment calls, and then presenting those calls in the most efficient format possible. That's Tenet 2 made concrete. Relentless judgment-boundary optimization isn't a philosophy anymore, it's a table with a status column.

**current mood:** the satisfaction of building infrastructure that respects the scarcest resource

**current music:** [Midnight City - M83](https://www.youtube.com/watch?v=dX3k_QDnzHE). The synths build and build and then the saxophone comes in. That's what wiring three producers into a unified queue felt like.

---

### Serious stuff

**Session work (Entry 3):**

*S7.1 + S7.2: Hybrid Operator Decision Queue*

**Created (7 files):**
- `src/migrations/016_pending_decisions.sql` — decision queue table with partial unique dedup index, severity/type/status indexes, RLS
- `src/decision_queue.py` — business logic: create, resolve, query, briefing formatter (7 valid types, 5 severities, 3 verdicts)
- `src/decision_briefing.py` — CLI tool (`--format text|json`, `--check`, `--include-resolved`, `--city-fips`)
- `tests/test_decision_queue.py` — 28 tests across 7 classes
- `web/src/app/api/operator/decisions/route.ts` — GET endpoint, no caching
- `web/src/app/operator/decisions/page.tsx` — server component wrapper
- `web/src/app/operator/decisions/OperatorDecisionsPage.tsx` — client component with OperatorGate, severity badges, collapsible resolved section

**Modified (7 files):**
- `src/db.py` — 5 new functions: insert_pending_decision (with UniqueViolation dedup), update_decision_status, query_pending_decisions (severity-ranked), query_resolved_decisions, count_decisions_by_severity
- `src/staleness_monitor.py` — `create_staleness_decisions()` + `--create-decisions` flag, added pending_decisions to expected tables
- `src/completeness_monitor.py` — `create_anomaly_decisions()` + `--create-decisions` flag
- `src/self_assessment.py` — `create_assessment_decisions()` + `--create-decisions` flag
- `web/src/lib/types.ts` — PendingDecision, DecisionQueueResponse, DecisionType, DecisionSeverity, DecisionStatus
- `web/src/components/Nav.tsx` — operator-only "Decisions" link (amber colored)
- `web/src/app/api/health/route.ts` — 016_pending_decisions migration group added

**Test suite:** 925 tests, all passing (was 897 at Entry 2)

**Human action required:** Run migration 016 in [Supabase SQL Editor](https://supabase.com/dashboard/project/ahrwvmizzykyyfavdvfv/sql/)

**Deferred (from plan):**
- Web-based resolution (PATCH endpoint): primary interface is Claude Code
- Conflict scanner producer: validate queue with simpler producers first
- Pipeline failure auto-creation: after queue validated
- Decision analytics: after 30+ decisions resolved
