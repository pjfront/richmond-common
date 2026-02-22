# Phase D Design: NextRequest/CPRA Ingestion + Archive Center Expansion

*Created: 2026-02-22*
*Status: Approved*

---

## 1. What We're Building

Two complementary document ingestion systems that together give RTP a comprehensive civic document lake:

1. **NextRequest/CPRA scraper** — Playwright-based scraper for Richmond's NextRequest portal (CPRA public records requests). Full depth: metadata, PDF downloads, Claude extraction for cross-referencing with agenda items and contributions. Powers a CPRA compliance dashboard on the frontend.

2. **CivicPlus Archive Center discovery engine** — Expands the existing `batch_extract.py` (currently AMID=31 only) into an automatic AMID enumerator that maps all 149 active archive modules on any CivicPlus site. Downloads and indexes PDFs into Layer 1. Defers Claude extraction until RAG search or specific cross-referencing needs.

### Monetization Filter

- **Path A (Freemium):** CPRA compliance dashboard is unique citizen-facing value. Archive search (future) makes the platform more comprehensive. ✓
- **Path B (Horizontal):** NextRequest (CivicPlus) and Archive Center (CivicPlus) both scale to 3,000+ cities with identical URL patterns. ✓
- **Path C (Data Infrastructure):** 9,000+ documents in Layer 1. Structured CPRA data. Cross-referenceable extracted content. ✓

All three. Foundational infrastructure.

---

## 2. Scope Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| NextRequest scrape depth | Full extraction (Option 3) | Incremental cost over metadata-only is ~$8/mo for ~80 docs/mo. Cross-referencing CPRA docs with agenda items is high investigative value. |
| NextRequest architecture | Simple functions with fetch/parse separation (not class hierarchy) | Matches eSCRIBE scraper patterns. Fetch layer is replaceable if API key obtained. No over-engineering for a solo project. |
| Archive Center scope | Enumerate all AMIDs, download high-priority, defer extraction | 30 min add-on for 9,000+ documents. Documents sit in Layer 1 for free, ready for RAG search later. |
| Frontend dashboard | CPRA compliance focus first | Wider audience than document search. Doesn't depend on extraction pipeline accumulation. Unique differentiator. |
| Dashboard: document search | Deferred to later session | Needs extracted text to accumulate first. Independent component, zero rework to add. |

---

## 3. New Files

| File | Purpose |
|------|---------|
| `src/nextrequest_scraper.py` | Playwright scraper — list requests, parse details, download docs, extract text |
| `src/nextrequest_extractor.py` | Claude API extraction of CPRA document contents into structured data |
| `src/archive_center_discovery.py` | CivicPlus Archive Center AMID enumerator + bulk document downloader |
| `src/migrations/003_nextrequest.sql` | `nextrequest_requests` + `nextrequest_documents` tables |
| `tests/test_nextrequest_scraper.py` | Scraper unit tests (mocked Playwright) |
| `tests/test_nextrequest_extractor.py` | Extraction tests |
| `tests/test_archive_center_discovery.py` | Discovery engine tests |
| `web/src/app/public-records/page.tsx` | CPRA compliance dashboard page |
| `web/src/app/api/public-records/route.ts` | API route for compliance stats |
| `web/src/components/ComplianceStats.tsx` | Stats bar component (total requests, avg response, on-time rate, overdue) |
| `web/src/components/DepartmentBreakdown.tsx` | Department compliance table |
| `web/src/components/RecentRequests.tsx` | Recent CPRA requests list with status badges |

## 4. Modified Files

| File | Change |
|------|--------|
| `src/data_sync.py` | Add `sync_nextrequest()` + `sync_archive_center()` + registry entries |
| `tests/test_data_sync.py` | Registry tests + function-level tests for both new sources |
| `web/src/app/layout.tsx` | Add "Public Records" to nav |
| `.github/workflows/data-sync.yml` | Add `nextrequest` and `archive_center` to source options |
| `web/src/lib/queries.ts` | Add `getPublicRecordsStats()`, `getDepartmentCompliance()`, `getRecentRequests()` |
| `web/src/lib/types.ts` | Add NextRequest TypeScript types |

---

## 5. Database Schema (Migration 003)

```sql
-- Migration 003: NextRequest/CPRA tables
-- Idempotent: safe to re-run

CREATE TABLE IF NOT EXISTS nextrequest_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    request_number VARCHAR(50) NOT NULL,
    request_text TEXT NOT NULL,
    requester_name VARCHAR(200),
    department VARCHAR(200),
    status VARCHAR(50) NOT NULL,  -- 'new', 'in_progress', 'completed', 'closed', 'overdue'
    submitted_date DATE,
    due_date DATE,
    closed_date DATE,
    days_to_close INTEGER,       -- computed: closed_date - submitted_date
    document_count INTEGER DEFAULT 0,
    portal_url TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',  -- timeline events, notes, etc.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_nextrequest UNIQUE (city_fips, request_number)
);

CREATE INDEX IF NOT EXISTS idx_nextrequest_city ON nextrequest_requests(city_fips);
CREATE INDEX IF NOT EXISTS idx_nextrequest_status ON nextrequest_requests(status);
CREATE INDEX IF NOT EXISTS idx_nextrequest_dept ON nextrequest_requests(department);
CREATE INDEX IF NOT EXISTS idx_nextrequest_submitted ON nextrequest_requests(submitted_date);

CREATE TABLE IF NOT EXISTS nextrequest_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL REFERENCES nextrequest_requests(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id),  -- link to Layer 1 if PDF downloaded
    filename VARCHAR(500),
    file_type VARCHAR(50),
    file_size_bytes INTEGER,
    page_count INTEGER,
    download_url TEXT,
    has_redactions BOOLEAN,
    released_date DATE,
    extracted_text TEXT,                -- PyMuPDF output
    extraction_status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- 'pending', 'extracted', 'failed'
    extraction_metadata JSONB NOT NULL DEFAULT '{}',  -- Claude extraction output
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nextrequest_docs_request ON nextrequest_documents(request_id);
CREATE INDEX IF NOT EXISTS idx_nextrequest_docs_extraction ON nextrequest_documents(extraction_status);
```

**Note:** `extraction_status` column is new vs. the original spec — enables incremental extraction (only send un-extracted docs to Claude on each sync). `extraction_metadata` stores Claude's structured output per document.

---

## 6. NextRequest Scraper Architecture

```
nextrequest_scraper.py
├── Constants
│   ├── BASE_URL = "https://cityofrichmondca.nextrequest.com"
│   ├── CITY_FIPS = "0660620"
│   ├── DATA_DIR, RAW_DIR
│   └── NEXTREQUEST_PLATFORM_PROFILE dict (URL patterns, selectors, multi-city scaling)
│
├── Browser management
│   ├── create_browser() → Playwright browser + context
│   └── close_browser(browser)
│
├── Fetching (thin layer — replaceable with API later)
│   ├── _fetch_request_list(page, page_num) → raw HTML
│   └── _fetch_request_detail(page, request_id) → raw HTML
│
├── Parsing (reusable regardless of fetch method)
│   ├── _parse_request_list(html) → [RequestSummary]
│   ├── _parse_request_detail(html) → RequestDetail
│   └── _parse_document_list(html) → [DocumentInfo]
│
├── Document handling
│   ├── download_document(url, dest_dir) → filepath
│   └── extract_document_text(filepath) → str  (PyMuPDF, same pattern as batch_extract.py)
│
├── High-level orchestration
│   ├── list_all_requests(since_date=None) → [RequestSummary]  (paginated)
│   ├── scrape_request_detail(page, request_id) → RequestDetail
│   ├── scrape_all(since_date=None) → full result dict
│   └── save_to_db(conn, results, city_fips) → upsert stats
│
├── Self-healing hook
│   └── When _parse_* returns empty/unexpected, log warning with raw HTML snippet
│       Phase 1: detect failure. Phase 2 (future): LLM selector regeneration.
│
└── CLI
    ├── --list              List all requests (summary)
    ├── --request <num>     Scrape single request detail
    ├── --since <date>      Incremental scrape
    ├── --download          Also download PDFs
    ├── --stats             Print portal statistics
    └── --output <file>     Save JSON output
```

### Platform Profile (for multi-city scaling)

```python
NEXTREQUEST_PLATFORM_PROFILE = {
    "platform": "NextRequest (CivicPlus)",
    "url_pattern": "https://{city_slug}.nextrequest.com",
    "list_url": "/requests",
    "detail_url": "/requests/{request_id}",
    "document_url": "/documents/{document_id}/download",
    "spa": True,  # requires Playwright, not requests
    "api_v2_exists": True,  # confirmed 401 not 404
    "api_v2_base": "/api/v2/",
    "selectors": {
        "request_list_item": "...",   # discovered during implementation
        "request_title": "...",
        "request_status": "...",
        "document_link": "...",
    },
    "notes": "SaaS platform — identical UI across all cities. One scraper works everywhere."
}
```

---

## 7. NextRequest Extractor

```
nextrequest_extractor.py
├── extract_document(text, filename, file_type) → structured dict
│   Generic-first prompt — LLM identifies document type and extracts accordingly:
│   - contracts → parties, amounts, terms, effective dates
│   - emails/correspondence → sender, recipients, subject, key content
│   - reports/analyses → title, findings, recommendations, cited amounts
│   - generic → summary, entities mentioned, dates, dollar amounts
│
├── cross_reference_agenda(extracted_doc, agenda_items) → [matches]
│   Entity name matching (same pattern as conflict_scanner.py)
│   against current/recent agenda items
│
└── CLI
    ├── --document <path>    Extract single document
    ├── --batch <dir>        Extract all pending documents
    └── --cross-ref <meeting.json>  Cross-reference against meeting
```

**Prompt strategy:** One generic prompt handles all document types. The prompt instructs Claude to first identify the document type, then extract type-appropriate fields. Split into specialized prompts only if generic produces poor results on specific document types. This is prompts-as-config — version-controlled, re-runnable.

---

## 8. Archive Center Discovery Engine

```
archive_center_discovery.py
├── Constants
│   ├── CIVICPLUS_BASE_URL = "https://www.ci.richmond.ca.us"
│   ├── ARCHIVE_CENTER_PATH = "/ArchiveCenter/"
│   ├── ARCHIVE_DOCUMENT_URL = "/Archive.aspx?ADID={adid}"
│   ├── AMID_RANGE = (1, 250)  # scan range for discovery
│   ├── CITY_FIPS = "0660620"
│   └── CIVICPLUS_PLATFORM_PROFILE dict
│
├── Discovery
│   ├── enumerate_amids(base_url) → {amid: ArchiveModule}
│   │   Try each AMID in range, parse category name + doc count
│   │   Cache results to avoid re-scanning
│   └── get_archive_module(amid) → ArchiveModule (name, doc_count, date_range)
│
├── Document listing
│   ├── list_documents(amid, since_date=None) → [ArchiveDocument]
│   │   Paginate through archive module, extract ADID + title + date
│   └── Uses requests + BeautifulSoup (not Playwright — Archive Center serves HTML)
│
├── Download
│   ├── download_document(adid, dest_dir) → filepath
│   │   Direct PDF download from /Archive.aspx?ADID={adid}
│   └── extract_text(filepath) → str  (PyMuPDF)
│
├── Database
│   └── save_to_documents(conn, docs, city_fips)
│       Upsert into Layer 1 documents table
│       source_type = 'archive_center'
│       metadata includes {amid, amid_name, adid}
│
├── Priority tiers (which AMIDs to download first)
│   ├── Tier 1 (download now): 67 (resolutions), 66 (ordinances),
│   │     87 (CM weekly reports), 132/133 (Personnel Board)
│   ├── Tier 2 (download next): 168/169 (Rent Board), 61/77 (Design Review),
│   │     78 (Planning minutes), 75 (Housing Authority)
│   └── Tier 3 (metadata only): everything else
│
└── CLI
    ├── --discover           Enumerate all AMIDs, print table
    ├── --download <amid>    Download all docs from one AMID
    ├── --download-tier <N>  Download all tier N AMIDs
    ├── --since <date>       Incremental (new docs since date)
    └── --stats              Print archive statistics
```

### CivicPlus Platform Profile

```python
CIVICPLUS_PLATFORM_PROFILE = {
    "platform": "CivicPlus (CivicEngage)",
    "archive_center_path": "/ArchiveCenter/",
    "archive_url_pattern": "/Archive.aspx?AMID={amid}",
    "document_url_pattern": "/Archive.aspx?ADID={adid}",
    "document_center_path": "/DocumentCenter/",
    "uses_javascript_rendering": False,  # Archive Center serves HTML directly
    "amid_range": (1, 250),
    "notes": "Powers ~3,000+ city websites. Archive Center URL patterns identical across cities."
}
```

---

## 9. Data Sync Integration

```python
# In data_sync.py — two new entries

def sync_nextrequest(conn, city_fips, sync_type="incremental", sync_log_id=None):
    from nextrequest_scraper import create_browser, scrape_all, save_to_db, close_browser
    # Incremental: requests updated since last sync
    # Full: re-scrape everything
    # Returns: {"records_fetched": N, "records_new": N, "records_updated": N}

def sync_archive_center(conn, city_fips, sync_type="incremental", sync_log_id=None):
    from archive_center_discovery import enumerate_amids, list_documents, download_document, save_to_documents
    # Incremental: new docs since last sync across all tier 1-2 AMIDs
    # Full: re-enumerate + download all tier 1-2
    # Returns: {"records_fetched": N, "records_new": N, "amids_scanned": N}

SYNC_SOURCES["nextrequest"] = sync_nextrequest
SYNC_SOURCES["archive_center"] = sync_archive_center
```

---

## 10. n8n Workflow Updates

**Existing Sunday 10pm workflow** — add NextRequest sync:
```
→ HTTP Node: Trigger GitHub Actions data-sync
  event_type: "sync-data"
  client_payload: { source: "nextrequest", sync_type: "incremental" }
```

**New daily workflow** — NextRequest has strict 10-day CPRA deadlines, near-real-time tracking is valuable:
```
Trigger: Cron (daily 8am UTC)
→ HTTP Node: Trigger GitHub Actions data-sync
  event_type: "sync-data"
  client_payload: { source: "nextrequest", sync_type: "incremental" }
```

**Monthly archive sync** — add to existing 1st-of-month workflow:
```
→ HTTP Node: Trigger GitHub Actions data-sync
  event_type: "sync-data"
  client_payload: { source: "archive_center", sync_type: "incremental" }
```

---

## 11. Frontend — CPRA Compliance Dashboard

**Route:** `/public-records`

### Stats Bar (top)
| Total Requests | Avg Response Time | On-Time Rate | Currently Overdue |
|:-:|:-:|:-:|:-:|
| 347 | 14 days | 68% | 12 |

- On-time = closed within 10 calendar days (CPRA statutory deadline)
- Overdue = status != closed AND days since submitted > 10

### Department Breakdown (table)
| Department | Requests | Avg Days | On-Time % | Slowest |
|------------|----------|----------|-----------|---------|
| Police | 89 | 22 | 41% | 67 days |
| Public Works | 42 | 8 | 89% | 14 days |
| Planning | 63 | 11 | 72% | 31 days |
| City Manager | 38 | 15 | 63% | 28 days |

- Sortable columns
- Color-coded on-time % (green >80%, amber 50-80%, red <50%)

### Recent Requests (list)
- Request number + title (truncated to ~80 chars)
- Department badge
- Status badge (color-coded: green=completed, amber=in_progress, red=overdue)
- Days elapsed or days to close
- Link to portal_url

### Design System
- Same civic design system (navy/amber palette, Inter font)
- ISR with 1hr revalidation (same as other pages)
- Server component with Supabase queries (same pattern as meetings page)

---

## 12. Staleness Thresholds

Already configured in `staleness_monitor.py`:
- `"nextrequest": 7` (7-day threshold)

Adding:
- `"archive_center": 45` (monthly sync, 45-day threshold)

---

## 13. Cost Estimates

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| NextRequest Playwright (GitHub Actions) | $0 | ~5 min execution, well within free tier |
| NextRequest Claude extraction | ~$8/mo | ~80 docs/mo × $0.10 |
| Archive Center download (GitHub Actions) | $0 | Initial bulk ~30 min, incremental ~2 min |
| Archive Center storage (Supabase) | $0 | PDFs fit in 8GB Pro tier |
| n8n daily NextRequest workflow | $0 | Within existing plan's execution limit |
| **Total incremental** | **~$8/mo** | Only Claude extraction costs anything |

---

## 14. Build Estimate (Vibe-Coding Time)

| Component | Sessions | Notes |
|-----------|----------|-------|
| NextRequest scraper + migration + tests | 1.5 | Playwright, parsing, DB integration |
| NextRequest extractor + tests | 1 | Prompt design, cross-referencing |
| Archive Center discovery + tests | 0.5 | Extends existing batch_extract.py patterns |
| Data sync integration | 0.5 | Two registry entries + sync functions |
| Frontend dashboard | 1 | Stats, department table, recent requests |
| n8n workflow updates | 0.5 | Configure daily + monthly workflows |
| **Total** | **~5 sessions** | ~10-20 hours of Phillip's time |

---

## 15. What This Does NOT Cover

- **Document search UI** — deferred until extracted text accumulates. Independent component, zero rework to add later.
- **CPRA automation** (submitting requests) — future feature, depends on understanding portal structure first.
- **Archive Center Claude extraction** — documents land in Layer 1 as raw text. Extraction waits for RAG search or specific cross-referencing needs.
- **Multi-city onboarding** — platform profiles are built, but actual multi-city execution is Phase E.
- **API key acquisition** — parallel track via email to City Clerk / CivicPlus. If obtained, replaces Playwright fetch layer with zero pipeline changes.
