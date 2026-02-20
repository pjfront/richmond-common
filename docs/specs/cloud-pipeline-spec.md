# Cloud Pipeline Infrastructure Spec

*Created: 2026-02-20*
*Status: Draft — awaiting review before implementation*

---

## 1. Motivation

The pipeline currently runs locally on a developer machine: Python scripts read/write files in `src/data/`, push to Supabase via `--load-db`, and GitHub Actions triggers it weekly. This creates three problems:

1. **Local machine dependency.** If the developer's laptop is off, the pipeline doesn't run. Contribution data goes stale. Pre-meeting comments get missed.
2. **File-based state is fragile.** Intermediate results live on disk (`src/data/raw/`, `src/data/extracted/`, `src/data/audit_runs/`). If the disk is wiped or files get out of sync, recovery is manual.
3. **No temporal integrity.** The conflict scanner doesn't track *when* data was available. Re-running with new contributions produces different results with no way to distinguish "known before this meeting" from "learned after the fact."

This spec eliminates the local machine from the production data path. The target architecture:

```
Data Sources → n8n Cloud (orchestration) → GitHub Actions (heavy compute) → Supabase (sole data store) → Vercel (frontend)
```

No local files. No laptop in the loop. The developer's machine is for development only.

### Scope

This spec covers four tightly coupled concerns:

- **A. Cloud migration:** Moving all pipeline execution off the local machine
- **B. Data freshness:** Scheduled syncing of all data sources at appropriate intervals
- **C. Temporal integrity:** Scan versioning, prospective/retrospective modes, immutable audit trails
- **D. NextRequest/CPRA ingestion:** Scraping public records requests and released documents

These belong in one spec because they share infrastructure (n8n workflows, GitHub Actions runners, Supabase schema changes) and have ordering dependencies (you can't do temporal integrity without cloud storage; you can't do data freshness without cloud orchestration).

### Monetization filter

- **Path A (Freemium):** Always-fresh data, historical scan comparisons, CPRA document access — ✓
- **Path B (Horizontal):** n8n workflows are city-agnostic, scan versioning scales to any city — ✓
- **Path C (Data Infrastructure):** Immutable scan audit trail, structured CPRA data, contribution snapshots — ✓

All three. Foundational infrastructure.

---

## 2. Architecture

### 2.1 Component Roles

| Component | Role | Why |
|-----------|------|-----|
| **n8n Cloud** | Orchestration, scheduling, HTTP-based data collection | Visual workflow builder, cron triggers, webhook receivers, built-in HTTP/JSON nodes. Already in CLAUDE.md tech stack. |
| **GitHub Actions** | Heavy Python compute (Claude API calls, conflict scanning, PDF extraction) | Full Python environment, pip dependencies, secrets management, 6-hour timeout. Already working (`sync-pipeline.yml`). |
| **Supabase** | Sole persistent data store (all layers) | Already serves the frontend. PostgreSQL = SQL + pgvector. Row-level security for future multi-tenant. |
| **Vercel** | Frontend hosting | ISR pages, no changes needed to deployment. |

### 2.2 Why Hybrid (Not n8n-Only)

n8n Cloud runs JavaScript/Python code nodes with limited execution time (~30s), no pip dependencies, and no filesystem. The pipeline needs:

- PyMuPDF for PDF text extraction
- Claude Sonnet API calls (10-30s per meeting extraction)
- Large JSON manipulation (27K+ contribution records)
- Conflict scanner with complex matching logic

These require a full Python environment. n8n triggers GitHub Actions for this work, then reads the results from Supabase.

### 2.3 Data Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│                     n8n Cloud                           │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ NetFile  │  │ eSCRIBE  │  │ CAL-     │  ...more    │
│  │ Sync     │  │ Agenda   │  │ ACCESS   │  collectors │
│  │ (cron)   │  │ (cron)   │  │ (cron)   │             │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘             │
│       │              │              │                   │
│       ▼              ▼              ▼                   │
│  ┌──────────────────────────────────────┐              │
│  │   Write raw data to Supabase        │              │
│  │   (documents table, Layer 1)        │              │
│  └──────────────┬───────────────────────┘              │
│                 │                                       │
│                 ▼                                       │
│  ┌──────────────────────────────────────┐              │
│  │  Trigger GitHub Actions workflow     │              │
│  │  (via repository_dispatch)           │              │
│  └──────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                  GitHub Actions                          │
│                                                         │
│  1. Read raw data from Supabase                         │
│  2. Extract text from PDFs (PyMuPDF)                    │
│  3. Claude API extraction (structured JSON)             │
│  4. Conflict scan against Supabase contributions        │
│  5. Generate public comment                             │
│  6. Write results to Supabase (Layer 2 + scan_runs)     │
│  7. Upload audit artifacts                              │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                      Supabase                           │
│                                                         │
│  Layer 1: documents (raw PDFs, HTML, JSON)              │
│  Layer 2: meetings, agenda_items, votes, contributions  │
│  New:     scan_runs, nextrequest_*, data_sync_log       │
│  Layer 3: chunks (pgvector, future)                     │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                       Vercel                            │
│  Next.js frontend reads from Supabase                   │
│  (no changes needed)                                    │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Data Model Changes

### 3.1 New Table: `scan_runs`

Immutable audit log of every conflict scan execution. Each scan produces one row. Results in `conflict_flags` reference back to the scan that produced them.

```sql
CREATE TABLE scan_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    meeting_id UUID REFERENCES meetings(id),
    scan_mode VARCHAR(20) NOT NULL,  -- 'prospective', 'retrospective'
    data_cutoff_date DATE,           -- for prospective: only contributions filed on or before this date
    model_version VARCHAR(100),      -- Claude model used (e.g. 'claude-sonnet-4-20250514')
    prompt_version VARCHAR(50),      -- extraction prompt version tag
    scanner_version VARCHAR(50),     -- conflict_scanner.py version or git SHA
    contributions_count INTEGER,     -- how many contributions were considered
    contributions_sources JSONB,     -- e.g. {"calaccess": 4892, "netfile": 22143}
    form700_count INTEGER,
    flags_found INTEGER NOT NULL DEFAULT 0,
    flags_by_tier JSONB,            -- e.g. {"tier1": 0, "tier2": 1, "tier3": 3}
    clean_items_count INTEGER,
    enriched_items_count INTEGER,
    execution_time_seconds NUMERIC(8, 2),
    triggered_by VARCHAR(50),        -- 'scheduled', 'manual', 'reanalysis', 'data_refresh'
    pipeline_run_id VARCHAR(100),    -- GitHub Actions run ID or n8n execution ID
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'  -- audit sidecar data (bias signals, filter funnel)
);

CREATE INDEX idx_scan_runs_city ON scan_runs(city_fips);
CREATE INDEX idx_scan_runs_meeting ON scan_runs(meeting_id);
CREATE INDEX idx_scan_runs_mode ON scan_runs(scan_mode);
CREATE INDEX idx_scan_runs_created ON scan_runs(created_at);
```

### 3.2 Additions to `conflict_flags`

```sql
ALTER TABLE conflict_flags
    ADD COLUMN scan_run_id UUID REFERENCES scan_runs(id),
    ADD COLUMN scan_mode VARCHAR(20),        -- denormalized for query convenience
    ADD COLUMN data_cutoff_date DATE,        -- denormalized
    ADD COLUMN superseded_by UUID REFERENCES conflict_flags(id),  -- if a later scan replaces this flag
    ADD COLUMN is_current BOOLEAN NOT NULL DEFAULT TRUE;

CREATE INDEX idx_flags_scan_run ON conflict_flags(scan_run_id);
CREATE INDEX idx_flags_current ON conflict_flags(meeting_id) WHERE is_current = TRUE;
```

### 3.3 New Table: `data_sync_log`

Tracks every data collection run (n8n or manual). Essential for knowing "what data was available when."

```sql
CREATE TABLE data_sync_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    source VARCHAR(50) NOT NULL,          -- 'netfile', 'calaccess', 'escribemeetings', 'archive_center', 'socrata', 'nextrequest'
    sync_type VARCHAR(30) NOT NULL,       -- 'full', 'incremental', 'manual'
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    records_fetched INTEGER,
    records_new INTEGER,
    records_updated INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'running',  -- 'running', 'completed', 'failed'
    error_message TEXT,
    triggered_by VARCHAR(50),             -- 'n8n_cron', 'github_actions', 'manual'
    n8n_execution_id VARCHAR(100),
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_sync_log_city ON data_sync_log(city_fips);
CREATE INDEX idx_sync_log_source ON data_sync_log(source);
CREATE INDEX idx_sync_log_status ON data_sync_log(status);
```

### 3.4 New Tables: NextRequest/CPRA

```sql
-- Public records requests tracked on NextRequest portal
CREATE TABLE nextrequest_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    request_number VARCHAR(50) NOT NULL,    -- e.g. "25-123"
    request_text TEXT NOT NULL,
    requester_name VARCHAR(200),            -- public field on NextRequest
    department VARCHAR(200),
    status VARCHAR(50) NOT NULL,            -- 'new', 'in_progress', 'completed', 'closed', 'overdue'
    submitted_date DATE,
    due_date DATE,
    closed_date DATE,
    days_to_close INTEGER,                  -- computed: closed_date - submitted_date
    document_count INTEGER DEFAULT 0,
    portal_url TEXT,                         -- link back to NextRequest page
    metadata JSONB NOT NULL DEFAULT '{}',   -- timeline events, notes, etc.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_nextrequest UNIQUE (city_fips, request_number)
);

CREATE INDEX idx_nextrequest_city ON nextrequest_requests(city_fips);
CREATE INDEX idx_nextrequest_status ON nextrequest_requests(status);
CREATE INDEX idx_nextrequest_dept ON nextrequest_requests(department);
CREATE INDEX idx_nextrequest_submitted ON nextrequest_requests(submitted_date);

-- Documents released through CPRA/NextRequest
CREATE TABLE nextrequest_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL REFERENCES nextrequest_requests(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id),  -- link to Layer 1 if we download the PDF
    filename VARCHAR(500),
    file_type VARCHAR(50),                       -- 'pdf', 'xlsx', 'docx', etc.
    file_size_bytes INTEGER,
    page_count INTEGER,
    download_url TEXT,
    has_redactions BOOLEAN,
    released_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_nextrequest_docs_request ON nextrequest_documents(request_id);
```

---

## 4. Temporal Integrity

### 4.1 The Problem

The conflict scanner currently runs once per meeting and produces a flat list of flags. If new contribution data arrives after the meeting (late filings, corrections), re-running the scanner would overwrite the original results. This creates two problems:

1. **Lost history:** "What did we report to the public before this meeting?" is unanswerable.
2. **Unfair retroactive flagging:** A donation filed *after* a vote can't be a "conflict" at the time of the vote. But the scanner treats all contributions equally.

### 4.2 Two Scan Modes

**Prospective scan** (`scan_mode = 'prospective'`):
- Runs before a meeting (typically 48-72 hours prior)
- Uses `data_cutoff_date = meeting_date`
- Only considers contributions with `contribution_date <= data_cutoff_date`
- Results are what we publish in the public comment
- Immutable after creation — never overwritten

**Retrospective scan** (`scan_mode = 'retrospective'`):
- Runs periodically after the meeting (weekly, monthly, or on-demand)
- Uses ALL current data regardless of filing date
- Compares against the original prospective scan to surface new findings
- Flags what "we missed" or "what changed" — valuable for ongoing accountability
- Creates new `conflict_flags` rows (not overwriting prospective ones)

### 4.3 Versioning Rules

1. Each scan creates exactly one `scan_runs` row.
2. Each flag created by a scan references that `scan_runs.id`.
3. Prospective scan flags are marked `is_current = TRUE` until a newer prospective scan for the same meeting supersedes them.
4. Retrospective scan flags are always `is_current = TRUE` (additive — they don't replace prospective flags).
5. When a retrospective scan finds a flag that matches an existing prospective flag, it links them via `superseded_by` (the retrospective confirms the prospective).
6. The frontend shows prospective flags by default. A "retrospective findings" toggle reveals post-meeting discoveries.

### 4.4 Contribution Filtering for Prospective Mode

```python
# In conflict_scanner.py (pseudocode for cloud version)
if scan_mode == 'prospective':
    contributions = supabase.from_('contributions')
        .select('*')
        .eq('city_fips', city_fips)
        .lte('contribution_date', data_cutoff_date)
        .execute()
else:
    contributions = supabase.from_('contributions')
        .select('*')
        .eq('city_fips', city_fips)
        .execute()
```

---

## 5. Data Freshness Schedules

### 5.1 Data Source Update Cadences

| Source | Update Frequency | Pipeline Type | Orchestrator |
|--------|-----------------|---------------|-------------|
| **NetFile (local contributions)** | Weekly + daily during meeting weeks | HTTP collection | n8n cron |
| **CAL-ACCESS (state PAC/IE)** | Weekly (bulk download every 4 weeks; incremental checks weekly) | Heavy compute | GitHub Actions |
| **eSCRIBE (agenda packets)** | Weekly scan; daily during meeting weeks | HTTP collection | n8n cron |
| **Archive Center (approved minutes)** | Weekly (new minutes appear 2-4 weeks after meeting) | HTTP collection | n8n cron |
| **Socrata payroll** | Annually (January) | HTTP collection | n8n cron |
| **Socrata expenditures** | Monthly | HTTP collection | n8n cron |
| **NextRequest (CPRA)** | Daily | HTTP collection | n8n cron |
| **Form 700** | Annually (April 1 deadline) + ad hoc | Manual or n8n | n8n cron |

### 5.2 Pipeline Triggers

**Scheduled (n8n cron):**
```
Every Sunday 10pm Pacific:
  → NetFile incremental sync
  → eSCRIBE upcoming meeting check
  → Archive Center new minutes check
  → NextRequest new/updated requests

Every Monday 6am UTC (existing):
  → Full pre-meeting pipeline (if Tuesday meeting detected)

First Monday of each month:
  → CAL-ACCESS bulk download check (if stale > 30 days)
  → Socrata expenditures sync

January annually:
  → Socrata payroll refresh

April annually:
  → Form 700 filing deadline reminder + check
```

**Event-driven (n8n webhooks/polling):**
```
New eSCRIBE agenda detected:
  → Trigger GitHub Actions: extract → scan → generate comment

New contributions detected (NetFile or CAL-ACCESS):
  → Trigger retrospective re-scan of most recent meeting
  → If contribution_date <= upcoming_meeting_date, mark for prospective scan inclusion

New NextRequest documents released:
  → Download PDFs → Supabase documents table
  → Index for RAG search (future)
```

### 5.3 Staleness Monitoring

The `data_sync_log` table enables a dashboard showing when each source was last successfully synced. Alert thresholds:

| Source | Alert if stale > |
|--------|-----------------|
| NetFile | 14 days |
| eSCRIBE | 7 days before a scheduled meeting |
| CAL-ACCESS | 45 days |
| NextRequest | 7 days |
| Archive Center | 60 days |

---

## 6. NextRequest Ingestion

### 6.1 Why NextRequest

Richmond uses NextRequest (https://cityofrichmondca.nextrequest.com) for all California Public Records Act requests. Every request, response, timeline event, and released document is publicly visible. This is a goldmine:

1. **Pre-vetted public records.** Someone already asked for and received these documents. They're confirmed releasable.
2. **Request pattern analysis.** Which departments get the most requests? Which are slowest to respond? Who's asking?
3. **Compliance monitoring.** CPRA requires response within 10 days. We can track actual compliance rates.
4. **Automation path.** Understanding the portal's structure enables us to *submit* CPRA requests when documents are missing.

### 6.2 Technical Approach

NextRequest is a JavaScript SPA. Three options for ingestion:

**Option A: Playwright scraping** (most likely needed)
- Navigate pages with Playwright in headless mode
- Parse rendered HTML for request details, timeline, documents
- Download released PDFs
- Runs in GitHub Actions (Playwright has good CI support)

**Option B: Undocumented API discovery**
- Use browser DevTools to find API endpoints that the SPA calls
- If found, bypass the SPA entirely with direct HTTP requests
- Can run in n8n HTTP nodes (preferred for scheduling)

**Option C: City cooperation** (stretch goal)
- NextRequest has an admin API. Request API access via Phillip's Personnel Board connection.
- Would provide structured data without scraping fragility.
- Try this in parallel with Option A.

Recommend: **Start with Option A (Playwright in GitHub Actions), attempt Option B during implementation, pursue Option C diplomatically.**

### 6.3 Ingestion Pipeline

```
1. List all requests (paginate through portal)
2. For each request:
   a. Extract: request number, text, requester, department, dates, status
   b. Extract timeline events (submitted, acknowledged, extended, completed)
   c. List released documents (filename, date, size)
   d. Download PDFs → Supabase Storage (or documents table as BYTEA)
   e. Extract text from PDFs (PyMuPDF)
   f. Store structured data in nextrequest_requests + nextrequest_documents
   g. Store raw documents in Layer 1 documents table
3. Incremental sync: on subsequent runs, only process new/updated requests
   (track by request_number + updated_at comparison)
```

### 6.4 CPRA Automation (Phase B — Future)

Once we understand the portal's structure, we can automate CPRA submissions:

1. **Missing document detection.** Agenda item references "Resolution 123-25" but no PDF is in our documents table → auto-generate CPRA request text.
2. **Templated requests.** Pre-built request templates for common scenarios (meeting minutes, budget documents, contracts over $X).
3. **Status tracking.** Monitor our submitted requests and escalate if no response within CPRA's 10-day deadline.
4. **Existing `cpra_requests` table integration.** The schema already has a `cpra_requests` table — link it to `nextrequest_requests` when we submit through the portal.

This is Phase B — not in scope for initial implementation. But the ingestion pipeline (Phase A) is a prerequisite.

---

## 7. Pipeline Refactoring

### 7.1 What Changes in `run_pipeline.py`

The current pipeline reads/writes local files at every step. For cloud execution, all intermediate state moves to Supabase:

| Current (local) | Cloud (Supabase) |
|------------------|------------------|
| `src/data/raw/escribemeetings/{date}/meeting_data.json` | `documents` table (source_type='escribemeetings', raw content as JSONB in metadata) |
| `src/data/extracted/{date}_pipeline.json` | `extraction_runs` table (extracted_data JSONB) |
| `src/data/combined_contributions.json` | `contributions` table (queried live) |
| `src/data/audit_runs/{uuid}.json` | `scan_runs` table (metadata JSONB) |
| `data/comment_{date}_auto.txt` | `documents` table (source_type='generated_comment') or Supabase Storage |

### 7.2 New Script: `cloud_pipeline.py`

Replaces `run_pipeline.py` for cloud execution. Key differences:

1. **No local file paths.** All data read from / written to Supabase.
2. **Accepts `scan_mode` parameter** (`prospective` or `retrospective`).
3. **Creates `scan_runs` row** at start of execution; updates on completion.
4. **Queries contributions from Supabase** with optional `data_cutoff_date` filter.
5. **Writes `conflict_flags` with `scan_run_id`** for full traceability.
6. **Logs to `data_sync_log`** for observability.

The original `run_pipeline.py` remains for local development/testing.

### 7.3 GitHub Actions Workflow Changes

Rename `sync-pipeline.yml` → keep as legacy. Add new workflow:

**`cloud-pipeline.yml`:**
```yaml
name: Cloud Pipeline

on:
  repository_dispatch:
    types: [run-pipeline]  # triggered by n8n
  workflow_dispatch:
    inputs:
      meeting_date:
        description: 'Meeting date (YYYY-MM-DD)'
        required: true
      scan_mode:
        description: 'prospective or retrospective'
        required: false
        default: 'prospective'
      trigger_source:
        description: 'What triggered this run'
        required: false
        default: 'manual'

jobs:
  pipeline:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - run: pip install -r requirements.txt
      - name: Run cloud pipeline
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
        run: |
          cd src
          python cloud_pipeline.py \
            --date "${{ github.event.inputs.meeting_date || github.event.client_payload.meeting_date }}" \
            --scan-mode "${{ github.event.inputs.scan_mode || github.event.client_payload.scan_mode || 'prospective' }}" \
            --triggered-by "${{ github.event.inputs.trigger_source || 'n8n' }}"
```

**`data-sync.yml`** (new — for contribution syncs triggered by n8n):
```yaml
name: Data Sync

on:
  repository_dispatch:
    types: [sync-data]
  workflow_dispatch:
    inputs:
      source:
        description: 'Data source to sync'
        required: true
        type: choice
        options: [netfile, calaccess, socrata-payroll, socrata-expenditures]

jobs:
  sync:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - run: pip install -r requirements.txt
      - name: Run sync
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
        run: |
          cd src
          python data_sync.py \
            --source "${{ github.event.inputs.source || github.event.client_payload.source }}" \
            --city-fips 0660620
```

---

## 8. n8n Workflow Designs

### 8.1 Weekly Pre-Meeting Pipeline

```
Trigger: Cron (Sunday 10pm Pacific)
  │
  ├─→ HTTP Node: Check eSCRIBE for upcoming meetings this week
  │     URL: POST https://pub-richmond.escribemeetings.com/MeetingsCalendarView.aspx/GetCalendarMeetings
  │     Headers: Content-Type: application/json, X-Requested-With: XMLHttpRequest
  │     Body: { calendarStartDate: "YYYY-MM-DD", calendarEndDate: "YYYY-MM-DD" }
  │
  ├─→ IF Node: Meeting found for this week?
  │     YES ──→ HTTP Node: Trigger GitHub Actions (repository_dispatch)
  │              URL: POST https://api.github.com/repos/{owner}/{repo}/dispatches
  │              Body: { event_type: "run-pipeline", client_payload: { meeting_date: "...", scan_mode: "prospective" } }
  │     NO ───→ (end)
  │
  ├─→ HTTP Node: NetFile incremental sync
  │     URL: POST https://netfile.com/Connect2/api/public/campaign/search/transaction/query
  │     Process: Upsert new contributions to Supabase via REST API
  │
  └─→ HTTP Node: NextRequest check (new/updated requests)
        URL: (discovered during implementation)
        Process: Upsert to Supabase nextrequest_requests table
```

### 8.2 Monthly Data Refresh

```
Trigger: Cron (1st of month, 6am UTC)
  │
  ├─→ HTTP Node: Trigger GitHub Actions — CAL-ACCESS bulk sync
  │
  ├─→ HTTP Node: Socrata expenditures sync
  │     URL: https://www.transparentrichmond.org/resource/{dataset_id}.json
  │     Process: Upsert to Supabase
  │
  └─→ HTTP Node: Log sync run to data_sync_log via Supabase REST API
```

### 8.3 Retrospective Re-analysis

```
Trigger: Cron (every 2 weeks) OR webhook (new contribution data detected)
  │
  ├─→ Supabase Query: Find meetings in last 90 days with prospective scans
  │
  ├─→ For Each meeting:
  │     HTTP Node: Trigger GitHub Actions
  │       event_type: "run-pipeline"
  │       client_payload: { meeting_date: "...", scan_mode: "retrospective" }
  │
  └─→ (Results written to Supabase by GitHub Actions)
```

---

## 9. Implementation Plan

### Phase A: Cloud Pipeline Foundation (Week 1-2)

1. **Schema migration:** Add `scan_runs`, `data_sync_log`, alter `conflict_flags` with new columns.
2. **Create `cloud_pipeline.py`:** Fork from `run_pipeline.py`, replace file I/O with Supabase calls.
3. **Create `data_sync.py`:** Unified script for syncing any data source to Supabase.
4. **Add `cloud-pipeline.yml` and `data-sync.yml`** GitHub Actions workflows.
5. **Test:** Run cloud pipeline manually via `workflow_dispatch` against a known meeting date.

### Phase B: n8n Orchestration (Week 3)

6. **Set up n8n Cloud account** and connect to GitHub repo (for `repository_dispatch`).
7. **Build weekly pre-meeting workflow** (eSCRIBE check → trigger pipeline).
8. **Build weekly data sync workflow** (NetFile incremental → Supabase).
9. **Build staleness monitor** (query `data_sync_log`, alert if thresholds exceeded).

### Phase C: Temporal Integrity (Week 3-4)

10. **Add scan mode to conflict scanner** (`--scan-mode prospective|retrospective`).
11. **Implement contribution date filtering** for prospective mode.
12. **Wire up scan_runs creation** in cloud_pipeline.py.
13. **Build retrospective re-analysis n8n workflow.**
14. **Frontend: add "Retrospective Findings" toggle** on transparency report pages.

### Phase D: NextRequest Ingestion (Week 4-5)

15. **Discover NextRequest API/scraping approach** (Playwright spike in GitHub Actions).
16. **Build `nextrequest_scraper.py`** — list requests, extract details, download documents.
17. **Add to n8n daily sync workflow.**
18. **Create NextRequest dashboard page** on frontend (request counts, compliance rates, department breakdown).

### Phase E: Retire Local Pipeline (Week 5-6)

19. **Verify all data flows work end-to-end in cloud.**
20. **Deprecate local `run_pipeline.py` for production use** (keep for development).
21. **Remove local `src/data/` from production path** (still useful for dev/testing).
22. **Update CLAUDE.md** with new cloud architecture documentation.

---

## 10. What This Spec Does NOT Cover

- **RAG search / pgvector embeddings** — separate concern, uses the same Supabase data but has its own pipeline.
- **Email alert subscriptions** — depends on cloud pipeline being in place, but is its own feature.
- **Multi-city scaling** — this spec is Richmond-first. City-agnostic architecture is a design principle, not an implementation target.
- **n8n self-hosting vs. cloud** — this spec assumes n8n Cloud. Self-hosting is a cost optimization for later.
- **Frontend changes beyond retrospective toggle** — the cloud migration is invisible to the frontend except for scan metadata.

---

## 11. Cost Estimates

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| n8n Cloud (Starter) | ~$24/mo | 5 active workflows, 2,500 executions/month. Sufficient for Richmond. |
| GitHub Actions | $0 | Public repo = free. Private repo = 2,000 min/mo free tier. |
| Supabase (Pro) | $25/mo | Already paying this for the frontend. 8GB storage should suffice. |
| Claude API (pipeline) | ~$2-5/mo | ~$0.06/meeting × 24 meetings + re-scans + extractions. |
| **Total incremental** | **~$24-29/mo** | n8n is the only new cost. |

---

## 12. File Locations

| File | Purpose |
|------|---------|
| `src/cloud_pipeline.py` | Cloud-native pipeline orchestrator (replaces run_pipeline.py for production) |
| `src/data_sync.py` | Unified data source sync script |
| `src/nextrequest_scraper.py` | NextRequest portal ingestion |
| `.github/workflows/cloud-pipeline.yml` | GitHub Actions for pipeline execution |
| `.github/workflows/data-sync.yml` | GitHub Actions for data source syncing |
| `docs/specs/cloud-pipeline-spec.md` | This spec |
