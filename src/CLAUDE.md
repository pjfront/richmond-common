# src/CLAUDE.md — Pipeline Practical Knowledge

Run scripts from `src/` directory. Use `python-dotenv` with `load_dotenv(Path(__file__).parent.parent / ".env", override=True)`. NULL-safe pattern: `(row.get("FIELD") or "").strip()`.

**Source-closest artifact rule.** When writing a generator/extractor, read from the source-closest persisted artifact, not a derivative. When debugging incorrect generator output, the FIRST question is "what artifact is this reading?" — not "what's wrong with the prompt?" Reference table and full rule in `.claude/rules/conventions.md` "Source-Closest Artifact" section. Reference pattern: `extract_transcript_votes.py` reads `data/transcripts/{date}_clean.txt` (raw), falls back to `meetings.transcript_recap` (derivative) only when raw is unavailable. Every generator's module docstring must declare its input artifact ("Reads from X. Does NOT read from Y").

## Richmond Archive Center (Council Minutes)

- **Base URL:** `https://www.ci.richmond.ca.us/ArchiveCenter/`
- **Minutes archive:** `?AMID=31` — Document links use `ADID=` (Archive Document ID)
- **Direct PDF:** `https://www.ci.richmond.ca.us/Archive.aspx?ADID={id}` — serves raw PDF, no intermediate page
- 149 total archive modules, 9,000+ documents. Key AMIDs: 67 (resolutions, 2844), 66 (ordinances, 537), 87 (City Manager reports, 769), 132/133 (Personnel Board), 168/169 (Rent Board), 61/77 (Design Review)

## PDF Parsing

**Use PyMuPDF (`fitz`), NOT pdfplumber.** Government PDFs use Type3 fonts that pdfplumber can't decode (`(cid:XX)` garbled output). PyMuPDF handles TrueType correctly. Image-only NetFile Form 497 Part 1 filings have one narrow exception: render at most four pages locally, run the pinned offline RapidOCR/ONNX packages, require positive Part 1/date/money evidence, then send only the OCR transcript through the existing DeepSeek text extractor. Images do not leave the runner during that local-OCR stage. If the local-OCR/DeepSeek path fails and `MOONSHOT_API_KEY` is separately configured, the pre-existing optional Kimi fallback may render and send the filing's page images to that provider; this change does not enable or configure it. Other Type3 PDFs remain pending unless their separately approved extraction route is configured. Older meetings (pre-2024) extract cleanly. Pipeline detects Type3 per page and logs warning.

## Socrata API (Transparent Richmond)

- **Domain:** `www.transparentrichmond.org` (NOT `data.ci.richmond.ca.us`)
- **142 actual datasets** (637 total including derived views). No auth required; app token optional for rate limits
- Uses `sodapy` library. Dataset IDs in `socrata_client.py` DATASETS dict

## CAL-ACCESS (State Campaign Finance)

- **No REST API.** Download statewide bulk ZIP (~1.5GB) from `campaignfinance.cdn.sos.ca.gov/dbwebexport.zip` → ~10GB expanded (80 TSV tables)
- **Key tables:** `FILERNAME_CD` (17MB), `CVR_CAMPAIGN_DISCLOSURE_CD` (42MB), `RCPT_CD` (562MB), `EXPN_CD` (370MB)
- **CRITICAL:** `RCPT_CD` has NO `FILER_ID` column. Join path: `CVR_CAMPAIGN_DISCLOSURE_CD` (find Richmond filing IDs) -> `RCPT_CD` (match by `FILING_ID`)
- **Individual council candidates file locally with City Clerk, NOT CAL-ACCESS.** CAL-ACCESS has PACs, IE committees, ballot measures only
- Filter for Richmond by keyword matching on filer name, city, jurisdiction in CVR_CAMPAIGN_DISCLOSURE_CD
- Top PAC donors: SEIU Local 1021 ($1.2M+), Richmond Police Officers Assoc ($184K), ChevronTexaco ($137K)

## NetFile (Local Campaign Finance — City Clerk E-Filing)

- **API Base:** `https://netfile.com/Connect2/api` — public, no auth. Agency ID: 163, shortcut: `RICH`
- **Public portal:** `https://public.netfile.com/pub2/?AID=RICH`
- Richmond adopted NetFile January 2018. **Council candidates file HERE, not CAL-ACCESS.**
- **Transaction search:** `POST /public/campaign/search/transaction/query?format=json` with `{"Agency": 163, "TransactionType": 0, "PageSize": 1000, "CurrentPageIndex": 0, "SortOrder": 1}`
- **FPPC types:** F460A (type 0) = Monetary, F460C (type 1) = Non-Monetary, F460E (type 6) = Payments, F497P1 (type 20) = Late Contributions
- **CRITICAL:** API intermittently returns HTTP 500. Implement retry with exponential backoff. Types 6 and 20 especially unreliable.
- **Deduplication needed:** Amended filings create duplicates. Dedup by (contributor_name, amount, date, committee), keep highest filing_id
- 22,143 unique contributions, $5.79M total. Top local donors: Chevron ($635K), SEIU ($607K combined), Richmond POA ($831K combined)

## eSCRIBE Meeting Portal (Full Agenda Packets)

- **URL:** `https://pub-richmond.escribemeetings.com/`
- **No Playwright needed.** Individual meeting pages return parseable HTML with `requests` + BeautifulSoup (browser-like User-Agent). Only calendar listing is JS-rendered.
- **Meeting discovery:** `POST /MeetingsCalendarView.aspx/GetCalendarMeetings` with `{"calendarStartDate": "YYYY-MM-DD", "calendarEndDate": "YYYY-MM-DD"}`. Requires `Content-Type: application/json` + `X-Requested-With: XMLHttpRequest`. Returns ASP.NET `{"d": [...]}` with GUIDs.
- **CRITICAL:** Must GET calendar page first (for session cookies). Parameter names must be exactly `calendarStartDate`/`calendarEndDate` — anything else returns 500.
- **Meeting page:** `Meeting.aspx?Id={GUID}&Agenda=Agenda&lang=English`
- **Documents:** `filestream.ashx?DocumentId={id}` — raw PDFs
- **HTML structure:** `.AgendaItemContainer` (may nest) -> `.AgendaItemCounter` -> `.AgendaItemTitle a` -> `.AgendaItemDescription` + `.RichText` -> `.AgendaItemAttachment a[href*=filestream.ashx]`
- **Deduplication required:** Parent containers include all child attachments due to HTML nesting. Assign each DocumentId to deepest/most-specific item.
- 240 meetings (2020-2026): 217 regular + 21 Special + 2 Swearing In

## NextRequest (CPRA/Public Records)

- **No Playwright needed.** Public client JSON API discovered from SPA network calls (March 2026). Simple `requests` library.
- **List API:** `GET /client/requests?page_number=N` — 100 per page, returns `{total_count, requests}`. Fields: id, request_state, request_text, department_names, poc_name, request_date, due_date
- **Detail API:** `GET /client/requests/{id}` — full request with HTML request_text, requester info, field values
- **Timeline API:** `GET /client/requests/{id}/timeline` — status history, closed_date extraction from "Request Closed" events
- **Documents API:** `GET /client/request_documents?request_id={id}&page_number=N` — 25 docs/page. Returns doc id, title, file_extension, S3 `asset_url` for direct download, visibility, upload_date. Discovered April 2026 by reverse-engineering Vue.js SPA bundle (`api-CqnnFGtv.js`). Wired into `get_request_detail(include_documents=True)`.
- **Proof of concept:** Request 24-428 (Divestment Policy CPRA) — 115 docs, 68 MB, 93% text extraction yield via PyMuPDF. Search tool: `search_nextrequest_docs.py`.
- **2,382 requests** (June 2022–present), 24 pages. Full sync: ~30 seconds.
- Portal configs per city in `city_config.py`. Multi-city: same API on `{city_slug}.nextrequest.com`
- API v2 also exists at `/api/v2/` but requires Admin API key (not needed — client API sufficient)

## Conflict Scanner — Key Lessons

- **Generic employer filter is critical.** "City of Richmond", "Alameda County" etc. match every agenda item. Filter by prefix ("city of", "county of", "state of"), suffix (" county", " city"), and specific names.
- **Council member names cause false positives.** Sitting council members who are also donors — their names appear in agenda text as mover/seconder. Build name set from meeting data + city config, skip those matches.
- **CAL-ACCESS has duplicate filings.** Dedup by (donor_name, amount, date, committee) tuple.
- **Field name compatibility.** CAL-ACCESS: `contributor_name`/`contributor_employer`/`committee`. Test fixtures: `donor_name`/`donor_employer`/`committee_name`. Scanner accepts both via `or` fallback.
- **Government entity donors cause false positives.** "City of Richmond Finance Department" as donor matches every "Richmond" agenda item. Filter with same prefix/suffix patterns.
- **Temporal correlation (post-vote donations):** Time-decay confidence (1.0x at 0-90 days -> 0.3x at 2-5 years). Aye-votes only. 5-year lookback. Runs in retrospective scan path.

## Cloud Pipeline & Data Sync

- **`cloud_pipeline.py`** = production Supabase-native orchestrator. 7 steps: scrape eSCRIBE -> load contributions -> extract agenda (DeepSeek API) -> scan conflicts -> save flags -> generate comment -> store.
- **`run_pipeline.py`** = development only (local files). Both remain in repo.
- **Prospective scans** filter contributions by `contribution_date < meeting_date`. **Retrospective** uses all data. Stored in `scan_runs.scan_mode`.
- **Flag supersession:** `supersede_flags_for_meeting()` sets `is_current = FALSE` on old flags. Frontend filters `is_current = TRUE`.
- **`data_sync.py` registry pattern:** `SYNC_SOURCES = {"netfile": sync_netfile, ...}`. Functions use **lazy imports** (import inside function body). Test with `patch.dict(SYNC_SOURCES, {...})`, NOT `@patch("data_sync.sync_netfile")`. Enrichments (topic_tagging, summary_generation, conflict_scanning, etc.) are also in SYNC_SOURCES — same contract, detect their own new work.
- **Reactive enrichments:** `--enrich` flag on data_sync.py runs all downstream enrichments after a source sync, using the pipeline manifest DAG. `--enrich-only` runs all enrichments without syncing. The DAG is walked via `pipeline_map.PipelineGraph.trace_downstream()`.
- **GitHub Actions triggers:** `cloud-pipeline.yml` runs from its weekly/quarterly schedules or the repository-owner-only typed trusted-main `operator-cloud-pipeline` event; the manual path is prospective-only and accepts at most one validated meeting date. `change-detector.yml` keeps scheduled dispatch behavior, while its repository-owner-only `operator-source-change-check` event is read-only and requires `dry_run=true`. `data-sync.yml` accepts only typed default-branch `repository_dispatch` events: `sync-data` from the scheduled in-repo change detector (using its short-lived, run-scoped `GITHUB_TOKEN`) and `operator-sync-data` for a repository-owner-only repair slice. The operator sync event is incremental-only, cannot cascade enrichments, permits only fixed-window eSCRIBE work, and requires a 1–100 limit for minutes extraction or stale-minutes refresh. Bulk sources, derived sweeps, and full replay require a separately reviewed bounded path. Never restore branch-selectable `workflow_dispatch` on a secret-bearing write path.
- **`data-sync.yml` scheduled jobs (P0.2 rewire, 2026-07; source-reconciliation update, 2026-08):** Event-driven sources (eSCRIBE calendar, netfile, calaccess, and socrata_*) are dispatched by **change-detector** (15-min cron). NextRequest fingerprints are observation-only; its bounded daily/weekly jobs own portal reconciliation. The crons cover what dispatched fingerprints cannot prove: (1) **Daily** (`30 7 * * *` UTC): NextRequest catch-up + eSCRIBE agenda/attachment reconciliation + archive_center → written_comments (S24.24, mid-week comment PDFs) + escribemeetings_minutes → minutes_extraction. The eSCRIBE job must remain daily because agendas, cancellations, and in-place attachment revisions can change without changing calendar membership. (2) **Weekly** (Mon `0 8 * * 1`): completeness sweep — archive_center + refresh_stale_minutes + minutes_extraction + written_comments + meeting_summaries + escribemeetings + escribemeetings_minutes + netfile + nextrequest + socrata_expenditures + socrata_payroll + enrichment sweep (`--enrich-only`). (3) **Monthly** (15th `0 9 15 * *`): calaccess (1.5GB) + 5 socrata datasets. (4) **Quarterly** (1st of Jan/Apr/Jul/Oct `0 10 1 1,4,7,10 *`): form700 + form803_behested + lobbyist_registrations + propublica. `daily-netfile` is gated `if: false` pending the D61 keeper-selection fix. Every LLM-calling job carries `RICHMOND_API_BUDGET_LOCK` + `RICHMOND_API_MONTHLY_CAP_USD` env (P0.0) — lock/cap hits are graceful exit-0 skips recorded as `enrichment_skipped` journal entries (P0.9). A manual source sync uses the typed `operator-sync-data` default-branch event and never authorizes bulk or cascading work.
- **External n8n orchestration is retired.** GitHub Actions schedules own recurring pipeline execution; the change detector dispatches event-driven `data-sync.yml` runs without a long-lived PAT.
- **Migrations:** `src/migrations/00N_description.sql` (source of truth) + `supabase/migrations/` (CLI copies with timestamps). All idempotent. Run via `supabase db push` (AI-delegable). Health check: `/api/health` probes 18 tables across 5 groups.
- **Migration-ledger lockstep:** when applying a migration **directly** (psycopg2/`execute_sql`, not `db push`), the `supabase_migrations.schema_migrations` row you insert MUST use `version` = the committed `supabase/migrations/` timestamp prefix — never a hand-picked timestamp. A mismatch hard-breaks `db push` for every future migration. `python src/migration_ledger.py` checks it (and `--fix` repairs safe drift); the SessionStart brief shows `Migration ledger: in sync`/`>> DRIFT <<` every session. Full rule in `.claude/rules/conventions.md` "Database Migrations".
- **NetFile sync:** ~18 min first run (32K+ transactions). GitHub Actions 45-min timeout sufficient.
- **Supabase in GitHub Actions:** `SUPABASE_SERVICE_KEY` (service_role, bypasses RLS) — appropriate since pipeline also uses `DATABASE_URL` (direct Postgres).

## Commissions & Board Members

- Richmond has 30+ commissions. 17 seeded in `src/ground_truth/officials.json`. Major: Planning, Rent Board, Design Review, Police, Housing Authority.
- **Roster scraper:** HTML table parsing from `ci.richmond.ca.us/Boards` pages. Pure `requests` + BeautifulSoup, no Playwright.
- **Term date formats vary:** "MM/DD/YYYY", "Month YYYY", "Pleasure of the Mayor". Scraper normalizes all.
- **Appointment extraction:** LLM tool-calling mode on council meeting JSONs. Patterns: "Motion to appoint [person] to [commission]", reappointments, resignations. Check `cost_digest.py` for observed cost.
- **eSCRIBE discover-types:** `--discover-types` catalogs MeetingName values with counts/dates. As of 2026-03, eSCRIBE only has City Council meetings (regular, special, swearing in). No commission meetings are published through eSCRIBE — commission minutes come from Archive Center AMIDs instead. The `commissions_escribemeetings` config maps body names for future use if commissions are added to eSCRIBE.
- **Migration 005** (skipped 004, reserved for city-employees).

## Pipeline Lineage (static structure)

- **`pipeline_map.py`** — CLI for tracing data flows from source to frontend. Reads `docs/pipeline-manifest.yaml`.
- **`trace <table>`** — Full upstream/downstream chain (e.g., `trace contributions` shows NetFile + CAL-ACCESS upstream, conflict_scanner + 3 pages downstream)
- **`impact <module>`** — What tables, queries, and pages are affected if a module changes
- **`rerun <table>`** — What sync sources need rerunning to refresh a table's data
- **`validate`** — Check manifest against actual SYNC_SOURCES, queries.ts exports, and migration tables. Also runs in SessionStart health check.
- **`diagram`** — Generate Mermaid flowchart to `docs/pipeline-diagram.md`
- **Manifest must be updated in the same commit as any pipeline change** (AI-delegable, same pattern as PARKING-LOT sync).

## Pipeline Liveness (runtime reality)

Static lineage answers "where could data go?" Liveness answers "did the latest record actually flow through?" These are separate questions and need separate machinery — the missing piece that lets bugs like the 2026-04 missing-recap silent-failure go undetected for weeks.

- **`pipeline_map.py liveness`** — Run all expectation SQL checks against the live DB. Returns rows where each check FAILED (empty = passing).
- **`pipeline_map.py liveness --severity high`** — Filter to one severity. Use `--owner <name>` to filter to one source/enrichment.
- **`pipeline_map.py liveness --create-decisions`** — Push failing expectations into the operator decision_queue. Deduplicates by `liveness:{expectation_id}` so repeated runs don't multiply pending decisions.
- **Expectations live in `docs/pipeline-manifest.yaml`** under the top-level `expectations:` block. Each: `{id, owner, severity, description, rationale, check}`. The check is a `SELECT` that returns the failing rows (empty result = passing).
- **Coverage enforced** by `tests/test_pipeline_manifest.py::TestLivenessExpectations`. Critical owners (escribemeetings, netfile, recap_generation, orientation_generation, conflict_scanning, topic_tagging) must declare at least one expectation.
- **Surfaced** in the SessionStart health report under "Pipeline Liveness" via `system_health.analyze_pipeline_liveness()`. Operator sees passing/failing counts and the worst failures inline every session.
- **Anon visibility (Layer 3):** `tests/test_anon_visibility.py` queries each public-facing table via the anon Supabase client. Catches the RLS-policy-gap pattern (data exists, but RLS blocks the public from seeing it; see Entry 20 in JOURNAL.md). When adding a new public table, add it to `PUBLIC_TABLES` in that test.

## Multi-City Config Registry

- **`city_config.py`** is the central registry. Keyed by FIPS code. Each city has `name`, `state`, `fips_code`, `data_sources`, `council_members`.
- **Adding a city:** Add dict entry with platform-specific source configs. Pipeline checks `if source in cfg["data_sources"]`.
- **Config resolution:** Entry points call `get_city_config(fips)`. Raises `CityNotConfiguredError` for unknown. `DEFAULT_FIPS = "0660620"` for backward compat.
- **Scraper pattern:** Each has `resolve_config(city_fips=None)` — registry when FIPS provided, module defaults when None.

## Bias Audit Pipeline

- **Audit sidecars:** `src/data/audit_runs/{uuid}.json` after every scan. All matching decisions + filter funnel stats + surname tier distributions. ~33MB per scan. Gitignored.
- **Census data:** `src/data/census/surname_freq.json` (162K surnames, 2.3MB, committed). Raw CSV/ZIP gitignored.
- **Ground truth CLI:** `--review --latest` — interactive T/F/S/N verdicts. Stored in sidecar JSON.
- **Periodic audit:** `bias_audit.py` requires 100+ ground-truthed decisions (pre-registered threshold).
- **Bias signals:** Compound surname, diacritics, token count, Census surname frequency tier. Structural properties, NOT demographic inference.

## Source Change Detector (Near-Live Polling)

- **`change_detector.py`** — stdlib-only Python (no pip install). Polls 5 external sources for changes every 15 min via GitHub Actions cron.
- **Architecture:** Lightweight fingerprint checks (counts, timestamps, ETags) → compare against `source_watch_state` table (Supabase REST API) → `repository_dispatch` to `data-sync.yml` when changes detected.
- **Sources watched:** eSCRIBE (meeting count + keys), NetFile (transaction counts by type), Socrata (7 dataset modification timestamps), NextRequest (request/document fingerprints, observation-only), CAL-ACCESS (bulk file Last-Modified header). NextRequest's bounded daily/weekly jobs own reconciliation; the 15-minute watcher must not dispatch portal work.
- **Socrata special handling:** Per-dataset comparison. Only changed datasets trigger individual syncs (e.g., `socrata_expenditures`, not all 7).
- **First check seeds state** without dispatching — avoids triggering a full sync on first deployment.
- **Dispatch payload:** `{"event_type": "sync-data", "client_payload": {"source": "...", "sync_type": "incremental", "trigger_source": "change_detector", "enrich": "true"}}`. The `enrich: "true"` flag triggers downstream enrichments (topic tagging, summaries, conflict scanning) after the source sync.
- **Workflow:** `.github/workflows/change-detector.yml` — 15-min cron (`3,18,33,48 * * * *`), sparse checkout, 2-min timeout, no pip install.
- **State table:** `source_watch_state` (migration 070) — `source TEXT PK`, `fingerprint JSONB`, `last_checked_at`, `last_changed_at`. Service-role-only RLS.
- **CLI:** `python change_detector.py` (all sources), `--dry-run` (no dispatches), `--source escribemeetings` (single source).

## Cost Estimates

⚠️ Per-call figures are illustrative. For actual spend by call site, run `python cost_digest.py` — it reads per-call costs from `pipeline_journal`. Routing is explicit and fail-closed: routine work uses direct DeepSeek V4 Flash; high-consequence extraction and explicit reasoning use direct DeepSeek V4 Pro; Kimi K3 is an opt-in challenger; Kimi K2.6 is the optional vision route. OpenAI Luna has exactly two representative-Richmond-benchmarked call sites: failed negated-motion vote explainers and bounded image-only Form 460 summary recovery. No broader OpenAI or Kimi route is authorized without its own Richmond benchmark. GPT-5 nano is excluded because its current snapshot is scheduled for retirement on 2026-12-11.

- Direct DeepSeek V4 Flash: $0.14/M cache-miss input, $0.28/M output ($0.0028/M cache-hit input).
- Direct DeepSeek V4 Pro: $0.435/M cache-miss input, $0.87/M output ($0.003625/M cache-hit input).
- A 10.5K-input / 8.9K-output extraction is approximately $0.00396 on Pro before cache savings.
- Kimi routes are optional and materially more expensive; use them only for vision or a measured challenger evaluation.
- NetFile first sync: ~18 min, subsequent: seconds

## API Budget Rails

- `RICHMOND_API_BUDGET_LOCK=true` → every LLM call raises (hard kill switch).
- `RICHMOND_API_MONTHLY_CAP_USD` (default `5.00`) → calls raise when month-to-date journal spend >= cap. DeepSeek pricing means $5 goes much further than before.
- `RICHMOND_EVENT_BUDGET_USD` → calls raise when this process's cumulative spend >= cap.
- Every **synchronous** LLM call is auto-logged to `pipeline_journal` (entry_type=api_cost) via `src/llm_budget_lock.py` (enforcement built into `src/llm_client.py` wrapper — no monkey-patching needed). Attribution: `_detect_caller()` walks the stack.
- **Provider batch execution is quarantined.** The old Anthropic-shaped upload/status/result contract is not assumed to work on DeepSeek or Kimi. Existing batch utilities fail explicitly before spending; use the synchronous routed client until a provider's batch contract has integration tests. Historical batch-result accounting remains available through `llm_budget_lock.log_batch_cost(...)` and applies no assumed discount.
- **Cost digest:** `python cost_digest.py [--days N] [--since YYYY-MM-DD] [--json]` summarizes journal spend by call site / day / model vs the monthly cap. A compact MTD top-spenders line is surfaced in the SessionStart health brief (`system_health` → `cost_digest.compact_mtd_summary`).
- change_detector includes a per-source budget field for traceability, but `data-sync.yml` distrusts that field and derives the enforced cap from its own source allowlist. NextRequest is observation-only at this cadence. Cloud Pipeline, Post-Meeting Recap, and Data Quality retain their schedules; their bounded manual paths use repository-owner-only typed trusted-main events rather than branch-selectable workflow dispatches. The manual Data Quality event runs only the two read-only quality reports; self-assessment, its LLM call, cost-journal write, and decision creation remain schedule-only.
