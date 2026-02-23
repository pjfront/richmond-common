# src/CLAUDE.md — Pipeline Practical Knowledge

Run scripts from `src/` directory. Use `python-dotenv` with `load_dotenv(Path(__file__).parent.parent / ".env", override=True)`. NULL-safe pattern: `(row.get("FIELD") or "").strip()`.

## Richmond Archive Center (Council Minutes)

- **Base URL:** `https://www.ci.richmond.ca.us/ArchiveCenter/`
- **Minutes archive:** `?AMID=31` — Document links use `ADID=` (Archive Document ID)
- **Direct PDF:** `https://www.ci.richmond.ca.us/Archive.aspx?ADID={id}` — serves raw PDF, no intermediate page
- 149 total archive modules, 9,000+ documents. Key AMIDs: 67 (resolutions, 2844), 66 (ordinances, 537), 87 (City Manager reports, 769), 132/133 (Personnel Board), 168/169 (Rent Board), 61/77 (Design Review)

## PDF Parsing

**Use PyMuPDF (`fitz`), NOT pdfplumber.** Government PDFs use Type3 fonts that pdfplumber can't decode (`(cid:XX)` garbled output). PyMuPDF handles TrueType correctly. Type3 fonts (image-based) still need OCR (future work). Older meetings (pre-2024) extract cleanly. Pipeline detects Type3 per page and logs warning.

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

- Playwright-based scraper — NextRequest is SPA, needs headless browser
- Self-healing selector hook (`_try_selectors`) for when CivicPlus updates UI
- Session-based pagination. Portal configs per city in `PORTAL_CONFIGS`
- API v2 exists at `/api/v2/` (confirmed by 401, not 404) but requires Admin API key from City Clerk/CivicPlus Support
- Abstract behind `NextRequestClient` interface for future API swap

## Conflict Scanner — Key Lessons

- **Generic employer filter is critical.** "City of Richmond", "Alameda County" etc. match every agenda item. Filter by prefix ("city of", "county of", "state of"), suffix (" county", " city"), and specific names.
- **Council member names cause false positives.** Sitting council members who are also donors — their names appear in agenda text as mover/seconder. Build name set from meeting data + city config, skip those matches.
- **CAL-ACCESS has duplicate filings.** Dedup by (donor_name, amount, date, committee) tuple.
- **Field name compatibility.** CAL-ACCESS: `contributor_name`/`contributor_employer`/`committee`. Test fixtures: `donor_name`/`donor_employer`/`committee_name`. Scanner accepts both via `or` fallback.
- **Government entity donors cause false positives.** "City of Richmond Finance Department" as donor matches every "Richmond" agenda item. Filter with same prefix/suffix patterns.
- **Temporal correlation (post-vote donations):** Time-decay confidence (1.0x at 0-90 days -> 0.3x at 2-5 years). Aye-votes only. 5-year lookback. Runs in retrospective scan path.

## Cloud Pipeline & Data Sync

- **`cloud_pipeline.py`** = production Supabase-native orchestrator. 7 steps: scrape eSCRIBE -> load contributions -> extract agenda (Claude API) -> scan conflicts -> save flags -> generate comment -> store.
- **`run_pipeline.py`** = development only (local files). Both remain in repo.
- **Prospective scans** filter contributions by `contribution_date < meeting_date`. **Retrospective** uses all data. Stored in `scan_runs.scan_mode`.
- **Flag supersession:** `supersede_flags_for_meeting()` sets `is_current = FALSE` on old flags. Frontend filters `is_current = TRUE`.
- **`data_sync.py` registry pattern:** `SYNC_SOURCES = {"netfile": sync_netfile, ...}`. Functions use **lazy imports** (import inside function body). Test with `patch.dict(SYNC_SOURCES, {...})`, NOT `@patch("data_sync.sync_netfile")`.
- **GitHub Actions triggers:** `cloud-pipeline.yml` has triple-trigger: `schedule` (weekly cron), `repository_dispatch` (n8n), `workflow_dispatch` (manual). Input resolution: `${{ github.event.inputs.X || github.event.client_payload.X }}`.
- **`sync-pipeline.yml` is DEPRECATED.** Prints warning and exits.
- **n8n -> GitHub dispatch:** POST to `https://api.github.com/repos/{owner}/{repo}/dispatches`. Returns 204 (empty body). Requires fine-grained PAT with Contents: Read and Write.
- **n8n schedules (4 workflows):** (1) Weekly sync: Sunday 10pm Pacific. (2) Monthly CAL-ACCESS: 1st Monday. (3) Pre-meeting pipeline: Monday 6am UTC. (4) Retrospective: after Workflow 1.
- **Migrations:** `src/migrations/00N_description.sql`. All idempotent. Run manually in Supabase SQL Editor. Health check: `/api/health` probes 18 tables across 5 groups.
- **NetFile sync:** ~18 min first run (32K+ transactions). GitHub Actions 45-min timeout sufficient.
- **Supabase in GitHub Actions:** `SUPABASE_SERVICE_KEY` (service_role, bypasses RLS) — appropriate since pipeline also uses `DATABASE_URL` (direct Postgres).

## Commissions & Board Members

- Richmond has 30+ commissions. 17 seeded in `src/ground_truth/officials.json`. Major: Planning, Rent Board, Design Review, Police, Housing Authority.
- **Roster scraper:** HTML table parsing from `ci.richmond.ca.us/Boards` pages. Pure `requests` + BeautifulSoup, no Playwright.
- **Term date formats vary:** "MM/DD/YYYY", "Month YYYY", "Pleasure of the Mayor". Scraper normalizes all.
- **Appointment extraction:** Claude API `tool_use` mode on council meeting JSONs. Patterns: "Motion to appoint [person] to [commission]", reappointments, resignations. ~$0.02/meeting.
- **eSCRIBE discover-types:** `--discover-types` catalogs MeetingName values with counts/dates. Maps to `commissions_escribemeetings` in city config. 5 confirmed: Planning Commission, Rent Board, Design Review, Police Commission, Housing Authority.
- **Migration 005** (skipped 004, reserved for city-employees).

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

## Cost Estimates

- Single meeting extraction: ~$0.06 (Claude Sonnet, ~10.5K input + ~8.9K output tokens)
- Single agenda extraction: ~$0.07 (~6K input + ~3.5K output tokens)
- Commission appointment extraction: ~$0.02/meeting
- 24 meetings/year: ~$1.44/year for Richmond minutes extraction
- NetFile first sync: ~18 min, subsequent: seconds
