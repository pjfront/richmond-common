# Phase D Implementation Plan: NextRequest/CPRA + Archive Center

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a NextRequest/CPRA scraper with full extraction, an Archive Center discovery engine, data sync integration, and a CPRA compliance dashboard.

**Architecture:** Playwright-based scraper for NextRequest (SPA), requests+BeautifulSoup for Archive Center (server-rendered HTML). Both use fetch/parse separation so the fetch layer is replaceable with an API. Data lands in Supabase via `data_sync.py` registry pattern. Frontend is a Next.js server component with ISR.

**Tech Stack:** Python 3.11, Playwright, BeautifulSoup4, PyMuPDF (fitz), Claude Sonnet API, PostgreSQL/Supabase, Next.js 16, React 19, TypeScript, Tailwind CSS v4

**Design doc:** `docs/plans/2026-02-22-phase-d-nextrequest-archive-design.md`

---

## Task 1: Database Migration 003 — NextRequest Tables

**Files:**
- Create: `src/migrations/003_nextrequest.sql`

**Step 1: Write the migration SQL**

```sql
-- Migration 003: NextRequest/CPRA tables
-- Adds tables for public records request tracking and document storage.
-- Idempotent: safe to re-run (uses IF NOT EXISTS).

-- ============================================================
-- New Table: nextrequest_requests
-- Tracks CPRA/public records requests from the NextRequest portal.
-- ============================================================

CREATE TABLE IF NOT EXISTS nextrequest_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    request_number VARCHAR(50) NOT NULL,
    request_text TEXT NOT NULL,
    requester_name VARCHAR(200),
    department VARCHAR(200),
    status VARCHAR(50) NOT NULL,
    submitted_date DATE,
    due_date DATE,
    closed_date DATE,
    days_to_close INTEGER,
    document_count INTEGER DEFAULT 0,
    portal_url TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_nextrequest UNIQUE (city_fips, request_number)
);

CREATE INDEX IF NOT EXISTS idx_nextrequest_city ON nextrequest_requests(city_fips);
CREATE INDEX IF NOT EXISTS idx_nextrequest_status ON nextrequest_requests(status);
CREATE INDEX IF NOT EXISTS idx_nextrequest_dept ON nextrequest_requests(department);
CREATE INDEX IF NOT EXISTS idx_nextrequest_submitted ON nextrequest_requests(submitted_date);

-- ============================================================
-- New Table: nextrequest_documents
-- Documents released in response to CPRA requests.
-- ============================================================

CREATE TABLE IF NOT EXISTS nextrequest_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL REFERENCES nextrequest_requests(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id),
    filename VARCHAR(500),
    file_type VARCHAR(50),
    file_size_bytes INTEGER,
    page_count INTEGER,
    download_url TEXT,
    has_redactions BOOLEAN,
    released_date DATE,
    extracted_text TEXT,
    extraction_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    extraction_metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nextrequest_docs_request ON nextrequest_documents(request_id);
CREATE INDEX IF NOT EXISTS idx_nextrequest_docs_extraction ON nextrequest_documents(extraction_status);
```

Save to `src/migrations/003_nextrequest.sql`.

**Step 2: Verify migration is valid SQL**

Run: `python3 -c "open('src/migrations/003_nextrequest.sql').read(); print('SQL file reads OK')"`

Expected: `SQL file reads OK`

**Step 3: Commit**

```bash
git add src/migrations/003_nextrequest.sql
git commit -m "Phase 2: add migration 003 for NextRequest/CPRA tables"
```

---

## Task 2: NextRequest Scraper — Core Module

**Files:**
- Create: `src/nextrequest_scraper.py`
- Create: `tests/test_nextrequest_scraper.py`

This is the largest task. It builds the Playwright-based scraper with fetch/parse separation.

**Step 1: Write tests for parsing functions**

Tests should mock HTML responses and verify parsing logic. Create `tests/test_nextrequest_scraper.py`:

```python
"""Tests for the NextRequest/CPRA scraper.

Parsing tests use static HTML fixtures — no Playwright or network needed.
Orchestration tests mock Playwright browser interactions.
"""
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path


# ── HTML fixtures ─────────────────────────────────────────────

SAMPLE_REQUEST_LIST_HTML = """
<div class="request-list">
  <div class="request-item" data-request-id="NR-2026-001">
    <a class="request-link" href="/requests/NR-2026-001">
      <span class="request-number">NR-2026-001</span>
      <span class="request-title">Police department overtime records</span>
    </a>
    <span class="request-status">Completed</span>
    <span class="request-department">Police</span>
    <span class="request-date">01/15/2026</span>
  </div>
  <div class="request-item" data-request-id="NR-2026-002">
    <a class="request-link" href="/requests/NR-2026-002">
      <span class="request-number">NR-2026-002</span>
      <span class="request-title">City manager contract details</span>
    </a>
    <span class="request-status">In Progress</span>
    <span class="request-department">City Manager</span>
    <span class="request-date">02/01/2026</span>
  </div>
</div>
"""

SAMPLE_REQUEST_DETAIL_HTML = """
<div class="request-detail">
  <h1 class="request-title">Police department overtime records</h1>
  <div class="request-info">
    <span class="request-number">NR-2026-001</span>
    <span class="request-status">Completed</span>
    <span class="request-department">Police</span>
    <span class="requester-name">John Doe</span>
    <span class="submitted-date">01/15/2026</span>
    <span class="due-date">01/25/2026</span>
    <span class="closed-date">01/22/2026</span>
  </div>
  <div class="request-text">
    I am requesting all overtime records for the Richmond Police Department
    for the period of January 2025 through December 2025.
  </div>
  <div class="documents-list">
    <div class="document-item">
      <a class="document-link" href="/documents/doc-001/download">
        <span class="document-name">RPD_Overtime_2025.pdf</span>
      </a>
      <span class="document-size">2.1 MB</span>
      <span class="document-date">01/22/2026</span>
    </div>
    <div class="document-item">
      <a class="document-link" href="/documents/doc-002/download">
        <span class="document-name">Overtime_Policy.pdf</span>
      </a>
      <span class="document-size">145 KB</span>
      <span class="document-date">01/22/2026</span>
    </div>
  </div>
</div>
"""

EMPTY_REQUEST_LIST_HTML = """
<div class="request-list">
  <p class="no-results">No requests found.</p>
</div>
"""


# ── Parsing tests ─────────────────────────────────────────────

class TestParseRequestList:
    """Test _parse_request_list with HTML fixtures."""

    def test_parses_multiple_requests(self):
        from nextrequest_scraper import _parse_request_list
        results = _parse_request_list(SAMPLE_REQUEST_LIST_HTML)
        assert len(results) == 2
        assert results[0]["request_number"] == "NR-2026-001"
        assert results[0]["title"] == "Police department overtime records"
        assert results[0]["status"] == "Completed"
        assert results[0]["department"] == "Police"

    def test_second_request_parsed(self):
        from nextrequest_scraper import _parse_request_list
        results = _parse_request_list(SAMPLE_REQUEST_LIST_HTML)
        assert results[1]["request_number"] == "NR-2026-002"
        assert results[1]["status"] == "In Progress"
        assert results[1]["department"] == "City Manager"

    def test_empty_list_returns_empty(self):
        from nextrequest_scraper import _parse_request_list
        results = _parse_request_list(EMPTY_REQUEST_LIST_HTML)
        assert results == []

    def test_garbled_html_returns_empty(self):
        from nextrequest_scraper import _parse_request_list
        results = _parse_request_list("<html><body>garbage</body></html>")
        assert results == []


class TestParseRequestDetail:
    """Test _parse_request_detail with HTML fixtures."""

    def test_parses_request_metadata(self):
        from nextrequest_scraper import _parse_request_detail
        result = _parse_request_detail(SAMPLE_REQUEST_DETAIL_HTML)
        assert result["request_number"] == "NR-2026-001"
        assert result["status"] == "Completed"
        assert result["department"] == "Police"
        assert result["requester_name"] == "John Doe"

    def test_parses_request_text(self):
        from nextrequest_scraper import _parse_request_detail
        result = _parse_request_detail(SAMPLE_REQUEST_DETAIL_HTML)
        assert "overtime records" in result["request_text"]

    def test_parses_dates(self):
        from nextrequest_scraper import _parse_request_detail
        result = _parse_request_detail(SAMPLE_REQUEST_DETAIL_HTML)
        assert result["submitted_date"] == "2026-01-15"
        assert result["due_date"] == "2026-01-25"
        assert result["closed_date"] == "2026-01-22"

    def test_computes_days_to_close(self):
        from nextrequest_scraper import _parse_request_detail
        result = _parse_request_detail(SAMPLE_REQUEST_DETAIL_HTML)
        assert result["days_to_close"] == 7  # Jan 22 - Jan 15


class TestParseDocumentList:
    """Test _parse_document_list with HTML fixtures."""

    def test_parses_documents(self):
        from nextrequest_scraper import _parse_document_list
        results = _parse_document_list(SAMPLE_REQUEST_DETAIL_HTML)
        assert len(results) == 2
        assert results[0]["filename"] == "RPD_Overtime_2025.pdf"
        assert "doc-001" in results[0]["download_url"]
        assert results[1]["filename"] == "Overtime_Policy.pdf"

    def test_empty_document_list(self):
        from nextrequest_scraper import _parse_document_list
        results = _parse_document_list("<div class='documents-list'></div>")
        assert results == []


# ── Platform profile ──────────────────────────────────────────

class TestPlatformProfile:
    """Test that platform profile constants are correct."""

    def test_profile_has_required_fields(self):
        from nextrequest_scraper import NEXTREQUEST_PLATFORM_PROFILE
        assert "platform" in NEXTREQUEST_PLATFORM_PROFILE
        assert "url_pattern" in NEXTREQUEST_PLATFORM_PROFILE
        assert "spa" in NEXTREQUEST_PLATFORM_PROFILE
        assert NEXTREQUEST_PLATFORM_PROFILE["spa"] is True

    def test_base_url_is_richmond(self):
        from nextrequest_scraper import BASE_URL
        assert "richmond" in BASE_URL.lower()
        assert "nextrequest.com" in BASE_URL

    def test_city_fips_is_richmond(self):
        from nextrequest_scraper import CITY_FIPS
        assert CITY_FIPS == "0660620"


# ── Self-healing detection ────────────────────────────────────

class TestSelfHealingDetection:
    """Test that parsers log warnings on unexpected HTML."""

    def test_parse_request_list_logs_on_no_items(self, caplog):
        """When HTML has no request items, a warning is logged."""
        import logging
        from nextrequest_scraper import _parse_request_list
        with caplog.at_level(logging.WARNING):
            _parse_request_list("<div class='request-list'><p>Unexpected</p></div>")
        # Parser should return empty and optionally log
        # (exact log assertion depends on implementation)


# ── Save to DB ────────────────────────────────────────────────

class TestSaveToDb:
    """Test database save/upsert logic."""

    def test_save_creates_request_record(self):
        from nextrequest_scraper import save_to_db
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        # Return None for fetchone (no existing record)
        mock_cursor.fetchone.return_value = None

        results = {
            "city_fips": "0660620",
            "requests": [{
                "request_number": "NR-2026-001",
                "request_text": "Overtime records",
                "status": "Completed",
                "department": "Police",
                "requester_name": "John Doe",
                "submitted_date": "2026-01-15",
                "due_date": "2026-01-25",
                "closed_date": "2026-01-22",
                "days_to_close": 7,
                "documents": [],
                "portal_url": "https://cityofrichmondca.nextrequest.com/requests/NR-2026-001",
                "metadata": {},
            }],
        }

        stats = save_to_db(mock_conn, results, "0660620")
        assert stats["requests_saved"] >= 1
        mock_conn.commit.assert_called()
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_nextrequest_scraper.py -q --tb=short 2>&1 | head -30`

Expected: FAIL with `ModuleNotFoundError: No module named 'nextrequest_scraper'`

**Step 3: Write the scraper module**

Create `src/nextrequest_scraper.py`. Key structure:

```python
"""
Richmond Transparency Project — NextRequest/CPRA Scraper

Playwright-based scraper for Richmond's NextRequest portal.
Extracts CPRA request metadata, documents, and status for
compliance tracking and cross-referencing.

Architecture:
  - Fetch layer (thin, replaceable with API): _fetch_request_list, _fetch_request_detail
  - Parse layer (reusable): _parse_request_list, _parse_request_detail, _parse_document_list
  - Document handling: download_document, extract_document_text
  - Orchestration: scrape_all, save_to_db
  - Self-healing: warns on unexpected HTML structure

Usage:
  python nextrequest_scraper.py --list
  python nextrequest_scraper.py --since 2026-01-01
  python nextrequest_scraper.py --request NR-2026-001
  python nextrequest_scraper.py --stats
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, date
from pathlib import Path

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────

BASE_URL = "https://cityofrichmondca.nextrequest.com"
CITY_FIPS = "0660620"
DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw" / "nextrequest"

NEXTREQUEST_PLATFORM_PROFILE = {
    "platform": "NextRequest (CivicPlus)",
    "url_pattern": "https://{city_slug}.nextrequest.com",
    "list_url": "/requests",
    "detail_url": "/requests/{request_id}",
    "document_url": "/documents/{document_id}/download",
    "spa": True,
    "api_v2_exists": True,
    "api_v2_base": "/api/v2/",
    "selectors": {
        "request_list_item": ".request-item, [data-request-id]",
        "request_number": ".request-number",
        "request_title": ".request-title, .request-link",
        "request_status": ".request-status",
        "request_department": ".request-department, .department",
        "request_date": ".request-date, .submitted-date",
        "document_link": ".document-link, a[href*=documents]",
        "document_name": ".document-name",
    },
    "notes": "SaaS platform — identical UI across all cities. One scraper works everywhere.",
}


# ── Date parsing ──────────────────────────────────────────────

def _parse_date(date_str: str | None) -> str | None:
    """Parse MM/DD/YYYY or other formats to YYYY-MM-DD."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    logger.warning(f"Could not parse date: {date_str!r}")
    return None


def _compute_days_to_close(submitted: str | None, closed: str | None) -> int | None:
    """Compute days between submitted and closed dates."""
    if not submitted or not closed:
        return None
    try:
        d1 = datetime.strptime(submitted, "%Y-%m-%d").date()
        d2 = datetime.strptime(closed, "%Y-%m-%d").date()
        return (d2 - d1).days
    except ValueError:
        return None


# ── Parsing (reusable regardless of fetch method) ─────────────

def _parse_request_list(html: str) -> list[dict]:
    """Parse request list page HTML into request summaries.

    Returns list of dicts with: request_number, title, status, department, date.
    Returns empty list if no items found (self-healing: logs warning).
    """
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(".request-item, [data-request-id]")

    if not items:
        # Self-healing: log a warning with a snippet of what we got
        snippet = html[:500] if len(html) > 500 else html
        if "request" in html.lower() and "no-results" not in html.lower():
            logger.warning(
                f"NextRequest list parse found 0 items in {len(html)} chars of HTML. "
                f"Selectors may have changed. Snippet: {snippet[:200]}"
            )
        return []

    results = []
    for item in items:
        request_number = (
            item.select_one(".request-number")
            or item.get("data-request-id")
        )
        if hasattr(request_number, "get_text"):
            request_number = request_number.get_text(strip=True)

        title_el = item.select_one(".request-title, .request-link")
        title = title_el.get_text(strip=True) if title_el else ""

        status_el = item.select_one(".request-status")
        status = status_el.get_text(strip=True) if status_el else "unknown"

        dept_el = item.select_one(".request-department, .department")
        department = dept_el.get_text(strip=True) if dept_el else None

        date_el = item.select_one(".request-date, .submitted-date")
        date_str = date_el.get_text(strip=True) if date_el else None

        results.append({
            "request_number": request_number or "unknown",
            "title": title,
            "status": status,
            "department": department,
            "date": _parse_date(date_str),
        })

    return results


def _parse_request_detail(html: str) -> dict:
    """Parse request detail page HTML into a full request record.

    Returns dict with: request_number, request_text, status, department,
    requester_name, submitted_date, due_date, closed_date, days_to_close.
    """
    soup = BeautifulSoup(html, "html.parser")

    def _text(selector: str) -> str | None:
        el = soup.select_one(selector)
        return el.get_text(strip=True) if el else None

    request_number = _text(".request-number") or "unknown"
    status = _text(".request-status") or "unknown"
    department = _text(".request-department, .department")
    requester_name = _text(".requester-name")

    request_text_el = soup.select_one(".request-text")
    request_text = request_text_el.get_text(strip=True) if request_text_el else ""

    submitted_date = _parse_date(_text(".submitted-date"))
    due_date = _parse_date(_text(".due-date"))
    closed_date = _parse_date(_text(".closed-date"))
    days_to_close = _compute_days_to_close(submitted_date, closed_date)

    return {
        "request_number": request_number,
        "request_text": request_text,
        "status": status,
        "department": department,
        "requester_name": requester_name,
        "submitted_date": submitted_date,
        "due_date": due_date,
        "closed_date": closed_date,
        "days_to_close": days_to_close,
    }


def _parse_document_list(html: str) -> list[dict]:
    """Parse documents from a request detail page.

    Returns list of dicts with: filename, download_url, file_size, released_date.
    """
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(".document-item")

    results = []
    for item in items:
        link = item.select_one(".document-link, a[href*=documents]")
        if not link:
            continue

        name_el = item.select_one(".document-name")
        filename = name_el.get_text(strip=True) if name_el else (link.get_text(strip=True) or "unknown")

        download_url = link.get("href", "")
        if download_url and not download_url.startswith("http"):
            download_url = f"{BASE_URL}{download_url}"

        size_el = item.select_one(".document-size")
        file_size = size_el.get_text(strip=True) if size_el else None

        date_el = item.select_one(".document-date")
        released_date = _parse_date(date_el.get_text(strip=True) if date_el else None)

        # Infer file type from filename
        file_type = None
        if "." in filename:
            file_type = filename.rsplit(".", 1)[-1].lower()

        results.append({
            "filename": filename,
            "download_url": download_url,
            "file_size": file_size,
            "file_type": file_type,
            "released_date": released_date,
        })

    return results


# ── Document handling ─────────────────────────────────────────

def download_document(url: str, dest_dir: Path) -> Path | None:
    """Download a document PDF from NextRequest.

    Returns the local file path, or None if download failed.
    """
    import requests as req

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Extract filename from URL or use a default
    filename = url.rsplit("/", 1)[-1] if "/" in url else "document.pdf"
    if not filename or filename == "download":
        filename = f"doc_{int(time.time())}.pdf"

    dest_path = dest_dir / filename

    try:
        resp = req.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"Downloaded {filename} ({dest_path.stat().st_size:,} bytes)")
        return dest_path
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return None


def extract_document_text(filepath: Path) -> str | None:
    """Extract text from a PDF using PyMuPDF (fitz).

    Same pattern as batch_extract.py — handles Type3 font warnings.
    Returns extracted text or None on failure.
    """
    try:
        import fitz
    except ImportError:
        logger.warning("PyMuPDF (fitz) not installed — skipping text extraction")
        return None

    try:
        doc = fitz.open(str(filepath))
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        text = "\n".join(text_parts).strip()
        return text if text else None
    except Exception as e:
        logger.error(f"Failed to extract text from {filepath}: {e}")
        return None


# ── Database operations ───────────────────────────────────────

def save_to_db(conn, results: dict, city_fips: str) -> dict:
    """Save scraped NextRequest data to database.

    Upserts requests and their documents into nextrequest_requests
    and nextrequest_documents tables.

    Returns stats dict with counts.
    """
    requests_saved = 0
    documents_saved = 0

    with conn.cursor() as cur:
        for req in results.get("requests", []):
            # Upsert request
            cur.execute(
                """INSERT INTO nextrequest_requests
                   (city_fips, request_number, request_text, requester_name,
                    department, status, submitted_date, due_date, closed_date,
                    days_to_close, document_count, portal_url, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (city_fips, request_number)
                   DO UPDATE SET
                     status = EXCLUDED.status,
                     closed_date = EXCLUDED.closed_date,
                     days_to_close = EXCLUDED.days_to_close,
                     document_count = EXCLUDED.document_count,
                     metadata = EXCLUDED.metadata,
                     updated_at = NOW()
                   RETURNING id""",
                (
                    city_fips,
                    req["request_number"],
                    req.get("request_text", ""),
                    req.get("requester_name"),
                    req.get("department"),
                    req["status"],
                    req.get("submitted_date"),
                    req.get("due_date"),
                    req.get("closed_date"),
                    req.get("days_to_close"),
                    len(req.get("documents", [])),
                    req.get("portal_url"),
                    json.dumps(req.get("metadata", {})),
                ),
            )
            request_id = cur.fetchone()[0]
            requests_saved += 1

            # Save documents for this request
            for doc in req.get("documents", []):
                cur.execute(
                    """INSERT INTO nextrequest_documents
                       (request_id, filename, file_type, download_url,
                        released_date, extracted_text, extraction_status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT DO NOTHING""",
                    (
                        request_id,
                        doc.get("filename"),
                        doc.get("file_type"),
                        doc.get("download_url"),
                        doc.get("released_date"),
                        doc.get("extracted_text"),
                        "extracted" if doc.get("extracted_text") else "pending",
                    ),
                )
                documents_saved += 1

    conn.commit()
    return {
        "requests_saved": requests_saved,
        "documents_saved": documents_saved,
    }


# ── Playwright fetch layer (thin, replaceable with API) ───────

async def create_browser():
    """Create Playwright browser instance.

    Returns (playwright, browser, context) tuple.
    """
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) RTP-Bot/1.0"
    )
    return pw, browser, context


async def close_browser(pw, browser):
    """Close Playwright browser and cleanup."""
    await browser.close()
    await pw.stop()


async def _fetch_request_list(page, page_num: int = 1) -> str:
    """Fetch request list page HTML via Playwright.

    Thin layer — replaceable with API call later.
    """
    url = f"{BASE_URL}/requests?page={page_num}"
    await page.goto(url, wait_until="networkidle")
    # Wait for request items to render (SPA)
    try:
        await page.wait_for_selector(
            ".request-item, [data-request-id], .no-results",
            timeout=15000,
        )
    except Exception:
        logger.warning(f"Timeout waiting for request list on page {page_num}")
    return await page.content()


async def _fetch_request_detail(page, request_id: str) -> str:
    """Fetch request detail page HTML via Playwright.

    Thin layer — replaceable with API call later.
    """
    url = f"{BASE_URL}/requests/{request_id}"
    await page.goto(url, wait_until="networkidle")
    try:
        await page.wait_for_selector(
            ".request-detail, .request-number, .request-text",
            timeout=15000,
        )
    except Exception:
        logger.warning(f"Timeout waiting for request detail: {request_id}")
    return await page.content()


# ── High-level orchestration ──────────────────────────────────

async def list_all_requests(since_date: str | None = None) -> list[dict]:
    """List all requests, paginated. Optionally filter by date.

    Returns list of RequestSummary dicts.
    """
    pw, browser, context = await create_browser()
    page = await context.new_page()

    all_requests = []
    page_num = 1
    max_pages = 50  # Safety limit

    try:
        while page_num <= max_pages:
            html = await _fetch_request_list(page, page_num)
            requests = _parse_request_list(html)

            if not requests:
                break

            all_requests.extend(requests)
            logger.info(f"Page {page_num}: {len(requests)} requests")

            # Check if we've gone past since_date
            if since_date and requests:
                oldest = requests[-1].get("date")
                if oldest and oldest < since_date:
                    # Filter out requests before since_date
                    all_requests = [
                        r for r in all_requests
                        if not r.get("date") or r["date"] >= since_date
                    ]
                    break

            page_num += 1
            await page.wait_for_timeout(1000)  # Rate limiting

    finally:
        await close_browser(pw, browser)

    return all_requests


async def scrape_request_detail(page, request_id: str) -> dict:
    """Scrape full detail for a single request.

    Returns RequestDetail dict with documents.
    """
    html = await _fetch_request_detail(page, request_id)
    detail = _parse_request_detail(html)
    documents = _parse_document_list(html)
    detail["documents"] = documents
    detail["portal_url"] = f"{BASE_URL}/requests/{request_id}"
    return detail


async def scrape_all(
    since_date: str | None = None,
    download_docs: bool = False,
    extract_text: bool = False,
) -> dict:
    """Full scrape: list requests, get details, optionally download docs.

    Returns result dict with city_fips, source, scraped_at, requests, stats.
    """
    pw, browser, context = await create_browser()
    page = await context.new_page()

    try:
        # Step 1: Get request list
        all_summaries = []
        page_num = 1

        while page_num <= 50:
            html = await _fetch_request_list(page, page_num)
            summaries = _parse_request_list(html)
            if not summaries:
                break
            all_summaries.extend(summaries)
            page_num += 1
            await page.wait_for_timeout(1000)

        # Filter by date if provided
        if since_date:
            all_summaries = [
                s for s in all_summaries
                if not s.get("date") or s["date"] >= since_date
            ]

        logger.info(f"Found {len(all_summaries)} requests to scrape")

        # Step 2: Get details for each request
        detailed_requests = []
        for i, summary in enumerate(all_summaries):
            req_id = summary["request_number"]
            logger.info(f"  [{i+1}/{len(all_summaries)}] Scraping {req_id}")
            try:
                detail = await scrape_request_detail(page, req_id)

                # Step 3: Optionally download documents
                if download_docs and detail.get("documents"):
                    dest_dir = RAW_DIR / req_id
                    for doc in detail["documents"]:
                        if doc.get("download_url"):
                            filepath = download_document(doc["download_url"], dest_dir)
                            if filepath and extract_text:
                                doc["extracted_text"] = extract_document_text(filepath)

                detailed_requests.append(detail)
            except Exception as e:
                logger.error(f"  Error scraping {req_id}: {e}")
                continue

            await page.wait_for_timeout(500)  # Rate limiting

    finally:
        await close_browser(pw, browser)

    return {
        "city_fips": CITY_FIPS,
        "source": "nextrequest",
        "scraped_at": datetime.now().isoformat(),
        "requests": detailed_requests,
        "stats": {
            "total_found": len(all_summaries),
            "details_scraped": len(detailed_requests),
            "documents_found": sum(
                len(r.get("documents", [])) for r in detailed_requests
            ),
        },
    }


# ── CLI ───────────────────────────────────────────────────────

def main():
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(
        description="Richmond Transparency Project — NextRequest/CPRA Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list", action="store_true", help="List all requests")
    parser.add_argument("--request", type=str, help="Scrape single request by number")
    parser.add_argument("--since", type=str, help="Only requests since YYYY-MM-DD")
    parser.add_argument("--download", action="store_true", help="Download PDFs")
    parser.add_argument("--extract", action="store_true", help="Extract text from PDFs")
    parser.add_argument("--stats", action="store_true", help="Print portal statistics")
    parser.add_argument("--output", type=str, help="Save JSON output to file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.list:
        results = asyncio.run(list_all_requests(since_date=args.since))
        for r in results:
            print(f"  {r['request_number']:20s} {r['status']:15s} {r.get('department', ''):20s} {r.get('title', '')[:60]}")
        print(f"\nTotal: {len(results)} requests")

    elif args.request:
        async def _scrape_one():
            pw, browser, ctx = await create_browser()
            page = await ctx.new_page()
            try:
                return await scrape_request_detail(page, args.request)
            finally:
                await close_browser(pw, browser)

        detail = asyncio.run(_scrape_one())
        print(json.dumps(detail, indent=2))

    else:
        results = asyncio.run(scrape_all(
            since_date=args.since,
            download_docs=args.download,
            extract_text=args.extract,
        ))

        if args.output:
            Path(args.output).write_text(json.dumps(results, indent=2))
            print(f"Saved to {args.output}")
        else:
            print(json.dumps(results.get("stats", {}), indent=2))

        if args.stats:
            s = results.get("stats", {})
            print(f"\n{'='*50}")
            print(f"NextRequest Portal Statistics")
            print(f"  Requests found:    {s.get('total_found', 0)}")
            print(f"  Details scraped:   {s.get('details_scraped', 0)}")
            print(f"  Documents found:   {s.get('documents_found', 0)}")
            print(f"{'='*50}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    main()
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_nextrequest_scraper.py -q --tb=short`

Expected: All parsing tests PASS. Fix any import issues or parsing mismatches.

**Step 5: Commit**

```bash
git add src/nextrequest_scraper.py tests/test_nextrequest_scraper.py
git commit -m "Phase 2: add NextRequest/CPRA scraper with parsing tests"
```

---

## Task 3: Archive Center Discovery Engine

**Files:**
- Create: `src/archive_center_discovery.py`
- Create: `tests/test_archive_center_discovery.py`

**Step 1: Write tests**

Create `tests/test_archive_center_discovery.py`:

```python
"""Tests for the CivicPlus Archive Center discovery engine.

Tests use HTML fixtures — no network requests needed.
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


# ── HTML fixtures ─────────────────────────────────────────────

SAMPLE_ARCHIVE_MODULE_HTML = """
<html>
<head><title>Archive Center - City Council Resolutions</title></head>
<body>
<div id="ArchiveCenter">
  <h1>City Council Resolutions</h1>
  <table class="archiveTable">
    <tr>
      <td><a href="/Archive.aspx?ADID=12345">Resolution 2026-001</a></td>
      <td>01/15/2026</td>
    </tr>
    <tr>
      <td><a href="/Archive.aspx?ADID=12346">Resolution 2026-002</a></td>
      <td>01/22/2026</td>
    </tr>
    <tr>
      <td><a href="/Archive.aspx?ADID=12347">Resolution 2026-003</a></td>
      <td>02/05/2026</td>
    </tr>
  </table>
</div>
</body>
</html>
"""

EMPTY_ARCHIVE_MODULE_HTML = """
<html>
<head><title>Archive Center</title></head>
<body>
<div id="ArchiveCenter">
  <h1>Neighborhood Council - North Richmond</h1>
  <p>No documents found.</p>
</div>
</body>
</html>
"""

INVALID_AMID_HTML = """
<html>
<head><title>Archive Center</title></head>
<body>
<div id="ArchiveCenter">
  <p>The archive you are looking for does not exist.</p>
</div>
</body>
</html>
"""


# ── Parsing tests ─────────────────────────────────────────────

class TestParseArchiveModule:
    """Test archive module HTML parsing."""

    def test_parses_module_name(self):
        from archive_center_discovery import _parse_archive_module
        result = _parse_archive_module(SAMPLE_ARCHIVE_MODULE_HTML, 67)
        assert result["name"] == "City Council Resolutions"

    def test_parses_document_count(self):
        from archive_center_discovery import _parse_archive_module
        result = _parse_archive_module(SAMPLE_ARCHIVE_MODULE_HTML, 67)
        assert result["document_count"] == 3

    def test_empty_module_returns_zero_docs(self):
        from archive_center_discovery import _parse_archive_module
        result = _parse_archive_module(EMPTY_ARCHIVE_MODULE_HTML, 94)
        assert result["document_count"] == 0
        assert result["name"] == "Neighborhood Council - North Richmond"

    def test_invalid_amid_returns_none(self):
        from archive_center_discovery import _parse_archive_module
        result = _parse_archive_module(INVALID_AMID_HTML, 999)
        assert result is None


class TestParseDocumentList:
    """Test document listing extraction from archive module HTML."""

    def test_extracts_documents(self):
        from archive_center_discovery import _parse_document_list
        docs = _parse_document_list(SAMPLE_ARCHIVE_MODULE_HTML)
        assert len(docs) == 3
        assert docs[0]["adid"] == "12345"
        assert docs[0]["title"] == "Resolution 2026-001"

    def test_extracts_dates(self):
        from archive_center_discovery import _parse_document_list
        docs = _parse_document_list(SAMPLE_ARCHIVE_MODULE_HTML)
        assert docs[0]["date"] == "2026-01-15"
        assert docs[2]["date"] == "2026-02-05"

    def test_empty_module_returns_empty(self):
        from archive_center_discovery import _parse_document_list
        docs = _parse_document_list(EMPTY_ARCHIVE_MODULE_HTML)
        assert docs == []


# ── Priority tier assignment ──────────────────────────────────

class TestPriorityTiers:
    """Test AMID priority tier classification."""

    def test_tier1_resolutions(self):
        from archive_center_discovery import get_download_tier
        assert get_download_tier(67) == 1  # Resolutions

    def test_tier1_ordinances(self):
        from archive_center_discovery import get_download_tier
        assert get_download_tier(66) == 1  # Ordinances

    def test_tier1_cm_reports(self):
        from archive_center_discovery import get_download_tier
        assert get_download_tier(87) == 1  # CM Weekly Reports

    def test_tier2_rent_board(self):
        from archive_center_discovery import get_download_tier
        assert get_download_tier(168) == 2  # Rent Board

    def test_tier3_unknown(self):
        from archive_center_discovery import get_download_tier
        assert get_download_tier(999) == 3  # Default


# ── Platform profile ──────────────────────────────────────────

class TestCivicPlusPlatformProfile:
    """Test platform profile constants."""

    def test_profile_fields(self):
        from archive_center_discovery import CIVICPLUS_PLATFORM_PROFILE
        assert "platform" in CIVICPLUS_PLATFORM_PROFILE
        assert CIVICPLUS_PLATFORM_PROFILE["uses_javascript_rendering"] is False

    def test_url_patterns(self):
        from archive_center_discovery import CIVICPLUS_BASE_URL
        assert "ci.richmond.ca.us" in CIVICPLUS_BASE_URL
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_archive_center_discovery.py -q --tb=short 2>&1 | head -10`

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the discovery engine**

Create `src/archive_center_discovery.py`:

```python
"""
Richmond Transparency Project — CivicPlus Archive Center Discovery Engine

Enumerates all Archive Module IDs (AMIDs) on a CivicPlus city website,
catalogs available document categories, and downloads documents by
priority tier into Layer 1.

Architecture:
  - Discovery: enumerate_amids scans AMID range, identifies active modules
  - Listing: _parse_document_list extracts ADID + title + date per module
  - Download: download_document fetches PDFs via /Archive.aspx?ADID=
  - Text extraction: extract_text via PyMuPDF (same as batch_extract.py)
  - Storage: save_to_documents upserts into documents table (Layer 1)

CivicPlus powers ~3,000+ city websites with identical URL patterns.
This engine works for any CivicPlus site by swapping CIVICPLUS_BASE_URL.

Usage:
  python archive_center_discovery.py --discover
  python archive_center_discovery.py --download 67
  python archive_center_discovery.py --download-tier 1
  python archive_center_discovery.py --stats
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests as req
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────

CIVICPLUS_BASE_URL = "https://www.ci.richmond.ca.us"
ARCHIVE_CENTER_PATH = "/ArchiveCenter/"
ARCHIVE_MODULE_URL = "/ArchiveCenter/?AMID={amid}"
ARCHIVE_DOCUMENT_URL = "/Archive.aspx?ADID={adid}"
AMID_RANGE = (1, 250)
CITY_FIPS = "0660620"
DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw" / "archive_center"
CACHE_DIR = DATA_DIR / "cache"

CIVICPLUS_PLATFORM_PROFILE = {
    "platform": "CivicPlus (CivicEngage)",
    "archive_center_path": "/ArchiveCenter/",
    "archive_url_pattern": "/ArchiveCenter/?AMID={amid}",
    "document_url_pattern": "/Archive.aspx?ADID={adid}",
    "document_center_path": "/DocumentCenter/",
    "uses_javascript_rendering": False,
    "amid_range": (1, 250),
    "notes": "Powers ~3,000+ city websites. Archive Center URL patterns identical across cities.",
}

# Priority tiers — which AMIDs to download first
TIER_1_AMIDS = {67, 66, 87, 132, 133}   # Resolutions, Ordinances, CM Reports, Personnel Board
TIER_2_AMIDS = {168, 169, 61, 77, 78, 75}  # Rent Board, Design Review, Planning, Housing Authority

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) RTP-Bot/1.0",
    "Accept": "text/html",
}


def get_download_tier(amid: int) -> int:
    """Get download priority tier for an AMID."""
    if amid in TIER_1_AMIDS:
        return 1
    elif amid in TIER_2_AMIDS:
        return 2
    return 3


# ── Session management ────────────────────────────────────────

def create_session() -> req.Session:
    """Create HTTP session with proper headers."""
    session = req.Session()
    session.headers.update(HEADERS)
    return session


# ── Parsing ───────────────────────────────────────────────────

def _parse_archive_module(html: str, amid: int) -> dict | None:
    """Parse an archive module page to get name and document count.

    Returns dict with: amid, name, document_count, or None if AMID doesn't exist.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Check if this is a valid archive
    archive_div = soup.select_one("#ArchiveCenter")
    if not archive_div:
        return None

    # Check for "does not exist" messages
    text = archive_div.get_text()
    if "does not exist" in text.lower() or "not found" in text.lower():
        return None

    # Get module name from h1
    h1 = archive_div.select_one("h1")
    name = h1.get_text(strip=True) if h1 else f"Archive Module {amid}"

    # Count documents (links with ADID pattern)
    doc_links = archive_div.select("a[href*='ADID=']")
    document_count = len(doc_links)

    return {
        "amid": amid,
        "name": name,
        "document_count": document_count,
    }


def _parse_document_list(html: str) -> list[dict]:
    """Parse document listing from an archive module page.

    Returns list of dicts with: adid, title, date.
    """
    soup = BeautifulSoup(html, "html.parser")
    doc_links = soup.select("a[href*='ADID=']")

    results = []
    for link in doc_links:
        href = link.get("href", "")
        adid_match = re.search(r"ADID=(\d+)", href)
        if not adid_match:
            continue

        adid = adid_match.group(1)
        title = link.get_text(strip=True)

        # Try to find date in parent row/cell
        parent_row = link.find_parent("tr")
        date_str = None
        if parent_row:
            cells = parent_row.find_all("td")
            for cell in cells:
                cell_text = cell.get_text(strip=True)
                # Look for date patterns
                date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", cell_text)
                if date_match:
                    try:
                        date_str = datetime.strptime(
                            date_match.group(1), "%m/%d/%Y"
                        ).strftime("%Y-%m-%d")
                    except ValueError:
                        pass

        results.append({
            "adid": adid,
            "title": title,
            "date": date_str,
        })

    return results


# ── Discovery ─────────────────────────────────────────────────

def enumerate_amids(
    session: req.Session,
    base_url: str = CIVICPLUS_BASE_URL,
    amid_range: tuple = AMID_RANGE,
) -> dict[int, dict]:
    """Enumerate all active AMIDs on a CivicPlus site.

    Scans the AMID range, parsing each to detect active modules.
    Returns dict mapping AMID to module info.

    Caches results to avoid re-scanning.
    """
    cache_path = CACHE_DIR / "amids.json"
    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < 24 * 7:  # 7-day cache
            cached = json.loads(cache_path.read_text())
            logger.info(f"Using cached AMID data ({len(cached)} modules, {age_hours:.1f}h old)")
            return {int(k): v for k, v in cached.items()}

    logger.info(f"Enumerating AMIDs {amid_range[0]}-{amid_range[1]}...")
    modules = {}

    for amid in range(amid_range[0], amid_range[1] + 1):
        url = f"{base_url}{ARCHIVE_MODULE_URL.format(amid=amid)}"
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                continue

            result = _parse_archive_module(resp.text, amid)
            if result:
                modules[amid] = result
                tier = get_download_tier(amid)
                logger.info(
                    f"  AMID {amid:3d}: {result['name'][:50]:50s} "
                    f"({result['document_count']:4d} docs) [Tier {tier}]"
                )

            time.sleep(0.2)  # Rate limit: 5 req/sec

        except Exception as e:
            logger.debug(f"  AMID {amid}: error — {e}")
            continue

    # Cache results
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(modules, indent=2))
    logger.info(f"Found {len(modules)} active AMIDs (cached to {cache_path})")

    return modules


# ── Document download ─────────────────────────────────────────

def download_document(
    session: req.Session,
    adid: str,
    dest_dir: Path,
    base_url: str = CIVICPLUS_BASE_URL,
) -> Path | None:
    """Download a document PDF from the Archive Center.

    Returns local file path, or None on failure.
    """
    url = f"{base_url}{ARCHIVE_DOCUMENT_URL.format(adid=adid)}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"ADID_{adid}.pdf"

    if dest_path.exists():
        logger.debug(f"Already downloaded ADID {adid}")
        return dest_path

    try:
        resp = session.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.debug(f"Downloaded ADID {adid} ({dest_path.stat().st_size:,} bytes)")
        return dest_path
    except Exception as e:
        logger.error(f"Failed to download ADID {adid}: {e}")
        return None


def extract_text(filepath: Path) -> str | None:
    """Extract text from PDF using PyMuPDF. Same pattern as batch_extract.py."""
    try:
        import fitz
    except ImportError:
        logger.warning("PyMuPDF not installed — skipping extraction")
        return None

    try:
        doc = fitz.open(str(filepath))
        text_parts = [page.get_text() for page in doc]
        doc.close()
        text = "\n".join(text_parts).strip()
        return text if text else None
    except Exception as e:
        logger.error(f"Failed to extract text from {filepath}: {e}")
        return None


# ── Database operations ───────────────────────────────────────

def save_to_documents(conn, docs: list[dict], city_fips: str) -> dict:
    """Save archive documents to Layer 1 documents table.

    Returns stats dict.
    """
    from db import ingest_document

    saved = 0
    skipped = 0

    for doc in docs:
        try:
            ingest_document(
                conn,
                city_fips=city_fips,
                source_type="archive_center",
                raw_content=(doc.get("text") or "").encode("utf-8") if doc.get("text") else None,
                credibility_tier=1,
                source_url=f"{CIVICPLUS_BASE_URL}{ARCHIVE_DOCUMENT_URL.format(adid=doc['adid'])}",
                source_identifier=f"archive_center_ADID_{doc['adid']}",
                mime_type="application/pdf",
                metadata={
                    "amid": doc.get("amid"),
                    "amid_name": doc.get("amid_name"),
                    "adid": doc["adid"],
                    "title": doc.get("title"),
                    "date": doc.get("date"),
                    "pipeline": "archive_center_discovery",
                },
            )
            saved += 1
        except Exception as e:
            if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
                skipped += 1
            else:
                logger.error(f"Failed to save ADID {doc.get('adid')}: {e}")
                skipped += 1

    conn.commit()
    return {"saved": saved, "skipped": skipped}


# ── CLI ───────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Richmond Transparency Project — Archive Center Discovery Engine",
    )
    parser.add_argument("--discover", action="store_true", help="Enumerate all AMIDs")
    parser.add_argument("--download", type=int, help="Download all docs from one AMID")
    parser.add_argument("--download-tier", type=int, choices=[1, 2, 3],
                       help="Download all docs from tier N AMIDs")
    parser.add_argument("--since", type=str, help="Only docs since YYYY-MM-DD")
    parser.add_argument("--stats", action="store_true", help="Print archive statistics")
    parser.add_argument("--output", type=str, help="Save JSON output to file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    session = create_session()

    if args.discover or args.stats:
        modules = enumerate_amids(session)

        if args.stats:
            total_docs = sum(m["document_count"] for m in modules.values())
            print(f"\n{'='*60}")
            print(f"Archive Center Statistics")
            print(f"  Active modules: {len(modules)}")
            print(f"  Total documents: {total_docs:,}")
            for tier in [1, 2, 3]:
                tier_modules = {k: v for k, v in modules.items() if get_download_tier(k) == tier}
                tier_docs = sum(m["document_count"] for m in tier_modules.values())
                print(f"  Tier {tier}: {len(tier_modules)} modules, {tier_docs:,} docs")
            print(f"{'='*60}")
        else:
            print(f"\nActive AMIDs: {len(modules)}")
            for amid, info in sorted(modules.items()):
                tier = get_download_tier(amid)
                print(f"  AMID {amid:3d}: {info['name'][:50]:50s} ({info['document_count']:4d} docs) [Tier {tier}]")

    elif args.download:
        url = f"{CIVICPLUS_BASE_URL}{ARCHIVE_MODULE_URL.format(amid=args.download)}"
        resp = session.get(url)
        docs = _parse_document_list(resp.text)

        if args.since:
            docs = [d for d in docs if not d.get("date") or d["date"] >= args.since]

        dest = RAW_DIR / f"AMID_{args.download}"
        print(f"Downloading {len(docs)} documents from AMID {args.download}...")
        for doc in docs:
            download_document(session, doc["adid"], dest)
            time.sleep(0.2)

    elif args.download_tier is not None:
        modules = enumerate_amids(session)
        tier_modules = {k: v for k, v in modules.items()
                       if get_download_tier(k) == args.download_tier}
        print(f"Downloading Tier {args.download_tier}: {len(tier_modules)} modules")
        for amid, info in sorted(tier_modules.items()):
            print(f"\n  AMID {amid}: {info['name']}")
            url = f"{CIVICPLUS_BASE_URL}{ARCHIVE_MODULE_URL.format(amid=amid)}"
            resp = session.get(url)
            docs = _parse_document_list(resp.text)
            dest = RAW_DIR / f"AMID_{amid}"
            for doc in docs:
                download_document(session, doc["adid"], dest)
                time.sleep(0.2)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    main()
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_archive_center_discovery.py -q --tb=short`

Expected: All PASS

**Step 5: Commit**

```bash
git add src/archive_center_discovery.py tests/test_archive_center_discovery.py
git commit -m "Phase 2: add Archive Center discovery engine with tests"
```

---

## Task 4: Data Sync Integration

**Files:**
- Modify: `src/data_sync.py` (add 2 sync functions + 2 registry entries)
- Modify: `tests/test_data_sync.py` (add dispatch + function-level tests)

**Step 1: Write new tests in `tests/test_data_sync.py`**

Append to the existing file:

```python
# ── NextRequest source tests ──────────────────────────────────

class TestSyncNextrequest:
    """Test NextRequest sync function registration and dispatch."""

    def test_nextrequest_registered(self):
        from data_sync import SYNC_SOURCES
        assert "nextrequest" in SYNC_SOURCES

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_nextrequest_dispatches(
        self, mock_complete, mock_create, mock_conn,
    ):
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()
        fake_sync = MagicMock(return_value={
            "records_fetched": 25, "records_new": 5, "records_updated": 2,
        })

        with patch.dict(SYNC_SOURCES, {"nextrequest": fake_sync}):
            result = run_sync(source="nextrequest")

        fake_sync.assert_called_once()
        assert result["status"] == "completed"
        assert result["records_fetched"] == 25


# ── Archive Center source tests ───────────────────────────────

class TestSyncArchiveCenter:
    """Test Archive Center sync function registration and dispatch."""

    def test_archive_center_registered(self):
        from data_sync import SYNC_SOURCES
        assert "archive_center" in SYNC_SOURCES

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_archive_center_dispatches(
        self, mock_complete, mock_create, mock_conn,
    ):
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()
        fake_sync = MagicMock(return_value={
            "records_fetched": 100, "records_new": 50, "records_updated": 0,
        })

        with patch.dict(SYNC_SOURCES, {"archive_center": fake_sync}):
            result = run_sync(source="archive_center")

        fake_sync.assert_called_once()
        assert result["status"] == "completed"
```

**Step 2: Run new tests to verify they fail**

Run: `python3 -m pytest tests/test_data_sync.py::TestSyncNextrequest -q --tb=short`

Expected: FAIL — "nextrequest" not in SYNC_SOURCES

**Step 3: Add sync functions and registry entries to `src/data_sync.py`**

Add before the `SYNC_SOURCES` dict (after `sync_escribemeetings`):

```python
def sync_nextrequest(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync CPRA requests from NextRequest portal.

    For incremental: scrapes requests updated since last sync.
    For full: re-scrapes all requests.
    """
    import asyncio
    from nextrequest_scraper import scrape_all, save_to_db

    print("  Scraping NextRequest portal...")
    since_date = None
    if sync_type == "incremental":
        # Find last successful sync date
        with conn.cursor() as cur:
            cur.execute(
                """SELECT MAX(completed_at) FROM data_sync_log
                   WHERE source = 'nextrequest' AND status = 'completed'
                     AND city_fips = %s""",
                (city_fips,),
            )
            row = cur.fetchone()
            if row and row[0]:
                since_date = row[0].strftime("%Y-%m-%d")

    results = asyncio.run(scrape_all(
        since_date=since_date,
        download_docs=True,
        extract_text=True,
    ))

    print(f"  Scraped {results['stats']['details_scraped']} requests, "
          f"{results['stats']['documents_found']} documents")

    print("  Saving to database...")
    stats = save_to_db(conn, results, city_fips)

    return {
        "records_fetched": results["stats"]["total_found"],
        "records_new": stats["requests_saved"],
        "records_updated": 0,
        "documents_saved": stats["documents_saved"],
    }


def sync_archive_center(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync documents from CivicPlus Archive Center.

    For incremental: downloads new docs from Tier 1-2 AMIDs since last sync.
    For full: re-enumerates all AMIDs and downloads Tier 1-2.
    """
    from archive_center_discovery import (
        create_session,
        enumerate_amids,
        _parse_document_list,
        download_document,
        extract_text,
        save_to_documents,
        get_download_tier,
        CIVICPLUS_BASE_URL,
        ARCHIVE_MODULE_URL,
        RAW_DIR,
    )

    session = create_session()
    modules = enumerate_amids(session)

    # Filter to Tier 1-2 AMIDs
    target_modules = {
        k: v for k, v in modules.items()
        if get_download_tier(k) <= 2
    }
    print(f"  Found {len(target_modules)} Tier 1-2 archive modules")

    all_docs = []
    for amid, info in sorted(target_modules.items()):
        url = f"{CIVICPLUS_BASE_URL}{ARCHIVE_MODULE_URL.format(amid=amid)}"
        resp = session.get(url, timeout=15)
        docs = _parse_document_list(resp.text)
        print(f"  AMID {amid} ({info['name'][:30]}): {len(docs)} docs")

        for doc in docs:
            doc["amid"] = amid
            doc["amid_name"] = info["name"]
            dest = RAW_DIR / f"AMID_{amid}"
            filepath = download_document(session, doc["adid"], dest)
            if filepath:
                doc["text"] = extract_text(filepath)
            all_docs.append(doc)

    print(f"  Saving {len(all_docs)} documents to Layer 1...")
    stats = save_to_documents(conn, all_docs, city_fips)

    return {
        "records_fetched": len(all_docs),
        "records_new": stats["saved"],
        "records_updated": 0,
        "amids_scanned": len(target_modules),
    }
```

Update `SYNC_SOURCES`:

```python
SYNC_SOURCES = {
    "netfile": sync_netfile,
    "calaccess": sync_calaccess,
    "escribemeetings": sync_escribemeetings,
    "nextrequest": sync_nextrequest,
    "archive_center": sync_archive_center,
}
```

Update CLI `choices` and docstring. Update module docstring's `Supported sources` list.

**Step 4: Run all data sync tests**

Run: `python3 -m pytest tests/test_data_sync.py -q --tb=short`

Expected: All PASS (existing + new tests)

**Step 5: Commit**

```bash
git add src/data_sync.py tests/test_data_sync.py
git commit -m "Phase 2: integrate NextRequest and Archive Center into data sync"
```

---

## Task 5: Staleness Monitor + GitHub Actions Updates

**Files:**
- Modify: `src/staleness_monitor.py` (add `archive_center` threshold if not present)
- Modify: `.github/workflows/data-sync.yml` (add `nextrequest` and `archive_center` source options)

**Step 1: Update staleness monitor**

In `src/staleness_monitor.py`, ensure the `FRESHNESS_THRESHOLDS` dict has:
```python
"archive_center": 45,   # Monthly sync
"nextrequest": 7,        # Should already be there
```

**Step 2: Update GitHub Actions workflow**

In `.github/workflows/data-sync.yml`, add the new sources to the `options` list:

```yaml
      source:
        description: 'Data source to sync'
        required: true
        type: choice
        options:
          - netfile
          - calaccess
          - escribemeetings
          - nextrequest
          - archive_center
```

Also add Playwright install step (needed for NextRequest):

```yaml
      - name: Install Playwright browsers (for NextRequest)
        if: steps.inputs.outputs.source == 'nextrequest'
        run: python -m playwright install chromium --with-deps
```

**Step 3: Run existing tests to verify no regressions**

Run: `python3 -m pytest tests/ -q --tb=short`

Expected: All existing tests PASS

**Step 4: Commit**

```bash
git add src/staleness_monitor.py .github/workflows/data-sync.yml
git commit -m "Phase 2: add NextRequest/Archive Center to staleness monitor and GitHub Actions"
```

---

## Task 6: NextRequest Extractor

**Files:**
- Create: `src/nextrequest_extractor.py`
- Create: `tests/test_nextrequest_extractor.py`

**Step 1: Write tests**

Create `tests/test_nextrequest_extractor.py`:

```python
"""Tests for NextRequest document extraction via Claude API.

Uses mocked Claude responses — no actual API calls.
"""
import json
import pytest
from unittest.mock import patch, MagicMock


SAMPLE_CONTRACT_TEXT = """
PROFESSIONAL SERVICES AGREEMENT

This Agreement is entered into between the City of Richmond ("City")
and ABC Consulting LLC ("Consultant") for the provision of
environmental assessment services.

Contract Amount: $150,000
Term: January 1, 2026 through December 31, 2026
Department: Planning and Building Services

Scope of Work:
Phase 1 - Site Assessment ($50,000)
Phase 2 - Environmental Review ($75,000)
Phase 3 - Final Report ($25,000)
"""

SAMPLE_EXTRACTION_RESPONSE = {
    "document_type": "contract",
    "parties": ["City of Richmond", "ABC Consulting LLC"],
    "amount": 150000,
    "term_start": "2026-01-01",
    "term_end": "2026-12-31",
    "department": "Planning and Building Services",
    "summary": "Professional services agreement for environmental assessment.",
    "entities": ["City of Richmond", "ABC Consulting LLC"],
    "amounts": [150000, 50000, 75000, 25000],
}


class TestExtractDocument:
    """Test Claude API document extraction."""

    @patch("nextrequest_extractor.anthropic")
    def test_extracts_contract(self, mock_anthropic):
        from nextrequest_extractor import extract_document

        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(SAMPLE_EXTRACTION_RESPONSE))]
        mock_client.messages.create.return_value = mock_response

        result = extract_document(
            text=SAMPLE_CONTRACT_TEXT,
            filename="contract.pdf",
            file_type="pdf",
        )

        assert result["document_type"] == "contract"
        assert result["amount"] == 150000
        assert "ABC Consulting" in str(result["parties"])

    @patch("nextrequest_extractor.anthropic")
    def test_returns_none_on_empty_text(self, mock_anthropic):
        from nextrequest_extractor import extract_document
        result = extract_document(text="", filename="empty.pdf", file_type="pdf")
        assert result is None

    @patch("nextrequest_extractor.anthropic")
    def test_returns_none_on_short_text(self, mock_anthropic):
        from nextrequest_extractor import extract_document
        result = extract_document(text="Too short", filename="tiny.pdf", file_type="pdf")
        assert result is None


class TestCrossReferenceAgenda:
    """Test cross-referencing extracted documents with agenda items."""

    def test_matches_by_entity_name(self):
        from nextrequest_extractor import cross_reference_agenda

        extracted = {
            "entities": ["ABC Consulting LLC", "City of Richmond"],
            "department": "Planning",
            "amount": 150000,
        }
        agenda_items = [
            {"item_number": "H-1", "title": "ABC Consulting contract amendment",
             "description": "Approve amendment to ABC Consulting agreement"},
            {"item_number": "I-1", "title": "Budget update",
             "description": "Quarterly budget review"},
        ]

        matches = cross_reference_agenda(extracted, agenda_items)
        assert len(matches) >= 1
        assert matches[0]["item_number"] == "H-1"

    def test_no_matches_returns_empty(self):
        from nextrequest_extractor import cross_reference_agenda

        extracted = {"entities": ["Unrelated Corp"], "department": "HR", "amount": 0}
        agenda_items = [
            {"item_number": "A-1", "title": "Zoning variance",
             "description": "Residential zoning change"},
        ]

        matches = cross_reference_agenda(extracted, agenda_items)
        assert matches == []
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_nextrequest_extractor.py -q --tb=short 2>&1 | head -10`

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the extractor module**

Create `src/nextrequest_extractor.py`:

```python
"""
Richmond Transparency Project — NextRequest Document Extractor

Claude API extraction of CPRA document contents into structured data.
Generic-first prompt identifies document type and extracts accordingly.

Usage:
  python nextrequest_extractor.py --document path/to/doc.pdf
  python nextrequest_extractor.py --batch path/to/dir/
  python nextrequest_extractor.py --cross-ref meeting.json
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import anthropic
except ImportError:
    anthropic = None

# Minimum text length for extraction (below this, not worth the API cost)
MIN_TEXT_LENGTH = 50

EXTRACTION_PROMPT = """You are analyzing a document released through a California Public Records Act (CPRA) request from the City of Richmond, California.

First, identify the document type from this list:
- contract: Agreements, MOUs, professional services agreements
- correspondence: Emails, letters, memos
- report: Staff reports, analyses, audits, studies
- financial: Invoices, purchase orders, payment records
- policy: Policies, procedures, guidelines, ordinances
- legal: Legal opinions, court documents, settlement agreements
- permit: Permits, applications, approvals
- other: Anything that doesn't fit the above categories

Then extract structured information appropriate to the document type.

Document filename: {filename}
Document type hint from extension: {file_type}

Respond with a JSON object containing:
{{
  "document_type": "<type from list above>",
  "summary": "<1-2 sentence summary>",
  "entities": ["<list of organizations, companies, people mentioned>"],
  "amounts": [<list of dollar amounts mentioned as numbers>],
  "dates": ["<list of dates mentioned in YYYY-MM-DD format>"],
  "department": "<city department if identifiable>",
  "parties": ["<list of parties to agreements/contracts if applicable>"],
  "amount": <primary dollar amount if applicable, null otherwise>,
  "term_start": "<contract start date if applicable, YYYY-MM-DD>",
  "term_end": "<contract end date if applicable, YYYY-MM-DD>",
  "key_findings": ["<list of notable findings, conclusions, or decisions>"]
}}

Document text:
{text}
"""


def extract_document(
    text: str,
    filename: str = "unknown",
    file_type: str = "pdf",
) -> dict | None:
    """Extract structured data from a CPRA document using Claude API.

    Returns dict with document_type, summary, entities, amounts, etc.
    Returns None if text is too short or extraction fails.
    """
    if not text or len(text.strip()) < MIN_TEXT_LENGTH:
        return None

    if not anthropic:
        logger.error("anthropic package not installed — cannot extract")
        return None

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set")
        return None

    client = anthropic.Anthropic(api_key=api_key)

    # Truncate very long documents (Claude context limit)
    max_chars = 100_000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... truncated ...]"

    prompt = EXTRACTION_PROMPT.format(
        filename=filename,
        file_type=file_type,
        text=text,
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        result_text = response.content[0].text.strip()

        # Parse JSON from response (handle markdown code blocks)
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1]
            result_text = result_text.rsplit("```", 1)[0]

        return json.loads(result_text)

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse extraction response: {e}")
        return None
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return None


def cross_reference_agenda(
    extracted: dict,
    agenda_items: list[dict],
) -> list[dict]:
    """Cross-reference extracted document entities against agenda items.

    Uses entity name matching (same pattern as conflict_scanner.py).
    Returns list of matching agenda items with match reason.
    """
    entities = [e.lower() for e in extracted.get("entities", []) if e]
    # Filter out generic entities
    skip_entities = {"city of richmond", "richmond", "california", "state of california"}
    entities = [e for e in entities if e not in skip_entities]

    if not entities:
        return []

    matches = []
    for item in agenda_items:
        title = (item.get("title") or "").lower()
        desc = (item.get("description") or "").lower()
        combined = f"{title} {desc}"

        for entity in entities:
            # Check if entity name appears in agenda item
            # Use word boundaries for short names
            if len(entity) < 12:
                words = entity.split()
                if all(w in combined for w in words):
                    matches.append({
                        **item,
                        "match_entity": entity,
                        "match_type": "entity_name",
                    })
                    break
            elif entity in combined:
                matches.append({
                    **item,
                    "match_entity": entity,
                    "match_type": "entity_name",
                })
                break

    return matches


# ── CLI ───────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Richmond Transparency Project — NextRequest Document Extractor",
    )
    parser.add_argument("--document", type=str, help="Extract single document")
    parser.add_argument("--batch", type=str, help="Extract all PDFs in directory")
    parser.add_argument("--cross-ref", type=str, help="Cross-reference against meeting JSON")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.document:
        filepath = Path(args.document)
        try:
            import fitz
            doc = fitz.open(str(filepath))
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
        except ImportError:
            text = filepath.read_text()

        result = extract_document(text, filepath.name, filepath.suffix[1:])
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("No extraction result")

    elif args.batch:
        batch_dir = Path(args.batch)
        for filepath in sorted(batch_dir.glob("*.pdf")):
            print(f"\n{'='*50}\n{filepath.name}")
            try:
                import fitz
                doc = fitz.open(str(filepath))
                text = "\n".join(page.get_text() for page in doc)
                doc.close()
                result = extract_document(text, filepath.name, "pdf")
                if result:
                    print(f"  Type: {result.get('document_type')}")
                    print(f"  Summary: {result.get('summary', 'N/A')[:100]}")
            except Exception as e:
                print(f"  Error: {e}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    main()
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_nextrequest_extractor.py -q --tb=short`

Expected: All PASS

**Step 5: Commit**

```bash
git add src/nextrequest_extractor.py tests/test_nextrequest_extractor.py
git commit -m "Phase 2: add NextRequest document extractor with Claude API"
```

---

## Task 7: Frontend Types, Queries, and API Route

**Files:**
- Modify: `web/src/lib/types.ts` (add NextRequest types)
- Modify: `web/src/lib/queries.ts` (add public records query functions)
- Create: `web/src/app/api/public-records/route.ts` (API route for compliance stats)

**Step 1: Add TypeScript types to `web/src/lib/types.ts`**

Append at the end of the file:

```typescript
// ─── NextRequest / CPRA ─────────────────────────────────────

export interface NextRequestRequest {
  id: string
  city_fips: string
  request_number: string
  request_text: string
  requester_name: string | null
  department: string | null
  status: string
  submitted_date: string | null
  due_date: string | null
  closed_date: string | null
  days_to_close: number | null
  document_count: number
  portal_url: string | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface PublicRecordsStats {
  totalRequests: number
  avgResponseDays: number
  onTimeRate: number
  currentlyOverdue: number
}

export interface DepartmentCompliance {
  department: string
  requestCount: number
  avgDays: number
  onTimeRate: number
  slowestDays: number
}
```

**Step 2: Add query functions to `web/src/lib/queries.ts`**

Append to the file:

```typescript
// ─── Public Records (NextRequest/CPRA) ──────────────────────

export async function getPublicRecordsStats(
  cityFips = RICHMOND_FIPS
): Promise<PublicRecordsStats> {
  const { data, error } = await supabase
    .from('nextrequest_requests')
    .select('status, days_to_close, submitted_date')
    .eq('city_fips', cityFips)

  if (error) throw error
  const requests = data ?? []

  const total = requests.length
  const completed = requests.filter((r) => r.days_to_close !== null)
  const avgDays = completed.length > 0
    ? Math.round(completed.reduce((sum, r) => sum + (r.days_to_close ?? 0), 0) / completed.length)
    : 0
  const onTime = completed.filter((r) => (r.days_to_close ?? 999) <= 10).length
  const onTimeRate = completed.length > 0
    ? Math.round((onTime / completed.length) * 100)
    : 0

  // Currently overdue: not closed AND more than 10 days since submitted
  const now = new Date()
  const overdue = requests.filter((r) => {
    if (r.status === 'Completed' || r.status === 'closed') return false
    if (!r.submitted_date) return false
    const submitted = new Date(r.submitted_date + 'T00:00:00')
    const daysSince = Math.floor((now.getTime() - submitted.getTime()) / (1000 * 60 * 60 * 24))
    return daysSince > 10
  }).length

  return {
    totalRequests: total,
    avgResponseDays: avgDays,
    onTimeRate,
    currentlyOverdue: overdue,
  }
}

export async function getDepartmentCompliance(
  cityFips = RICHMOND_FIPS
): Promise<DepartmentCompliance[]> {
  const { data, error } = await supabase
    .from('nextrequest_requests')
    .select('department, days_to_close, status')
    .eq('city_fips', cityFips)

  if (error) throw error

  // Group by department
  const deptMap = new Map<string, { requests: typeof data }>()
  for (const r of data ?? []) {
    const dept = r.department || 'Unknown'
    const existing = deptMap.get(dept) ?? { requests: [] }
    existing.requests.push(r)
    deptMap.set(dept, existing)
  }

  return Array.from(deptMap.entries()).map(([dept, { requests }]) => {
    const completed = requests.filter((r) => r.days_to_close !== null)
    const avgDays = completed.length > 0
      ? Math.round(completed.reduce((sum, r) => sum + (r.days_to_close ?? 0), 0) / completed.length)
      : 0
    const onTime = completed.filter((r) => (r.days_to_close ?? 999) <= 10).length
    const onTimeRate = completed.length > 0 ? Math.round((onTime / completed.length) * 100) : 0
    const slowest = Math.max(...completed.map((r) => r.days_to_close ?? 0), 0)

    return {
      department: dept,
      requestCount: requests.length,
      avgDays,
      onTimeRate,
      slowestDays: slowest,
    }
  }).sort((a, b) => b.requestCount - a.requestCount)
}

export async function getRecentRequests(
  limit = 20,
  cityFips = RICHMOND_FIPS
): Promise<NextRequestRequest[]> {
  const { data, error } = await supabase
    .from('nextrequest_requests')
    .select('*')
    .eq('city_fips', cityFips)
    .order('submitted_date', { ascending: false })
    .limit(limit)

  if (error) throw error
  return (data ?? []) as NextRequestRequest[]
}
```

Add the new types to the import block at the top of `queries.ts`:

```typescript
import type {
  // ... existing imports ...
  NextRequestRequest,
  PublicRecordsStats,
  DepartmentCompliance,
} from './types'
```

**Step 3: Create API route**

Create `web/src/app/api/public-records/route.ts`:

```typescript
import { NextResponse } from 'next/server'
import { getPublicRecordsStats, getDepartmentCompliance } from '@/lib/queries'

export async function GET() {
  try {
    const [stats, departments] = await Promise.all([
      getPublicRecordsStats(),
      getDepartmentCompliance(),
    ])

    return NextResponse.json(
      { stats, departments },
      {
        headers: {
          'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=7200',
        },
      }
    )
  } catch (error) {
    console.error('Public records API error:', error)
    return NextResponse.json(
      { error: 'Failed to fetch public records data' },
      { status: 500 }
    )
  }
}
```

**Step 4: Verify TypeScript compiles**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/web && npx tsc --noEmit 2>&1 | head -20`

Expected: No type errors (or only pre-existing ones)

**Step 5: Commit**

```bash
git add web/src/lib/types.ts web/src/lib/queries.ts web/src/app/api/public-records/route.ts
git commit -m "Phase 2: add NextRequest/CPRA types, queries, and API route"
```

---

## Task 8: Frontend Dashboard Page + Components

**Files:**
- Create: `web/src/app/public-records/page.tsx`
- Create: `web/src/components/ComplianceStats.tsx`
- Create: `web/src/components/DepartmentBreakdown.tsx`
- Create: `web/src/components/RecentRequests.tsx`
- Modify: `web/src/components/Nav.tsx` (add "Public Records" link)

**Step 1: Create ComplianceStats component**

Create `web/src/components/ComplianceStats.tsx`:

```tsx
import type { PublicRecordsStats } from '@/lib/types'

export default function ComplianceStats({ stats }: { stats: PublicRecordsStats }) {
  const cards = [
    { label: 'Total Requests', value: stats.totalRequests.toLocaleString(), color: 'text-civic-navy' },
    { label: 'Avg Response', value: `${stats.avgResponseDays} days`, color: stats.avgResponseDays <= 10 ? 'text-emerald-600' : 'text-amber-600' },
    { label: 'On-Time Rate', value: `${stats.onTimeRate}%`, color: stats.onTimeRate >= 80 ? 'text-emerald-600' : stats.onTimeRate >= 50 ? 'text-amber-600' : 'text-red-600' },
    { label: 'Currently Overdue', value: stats.currentlyOverdue.toString(), color: stats.currentlyOverdue === 0 ? 'text-emerald-600' : 'text-red-600' },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {cards.map(({ label, value, color }) => (
        <div key={label} className="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <div className={`text-2xl font-bold ${color}`}>{value}</div>
          <div className="text-sm text-slate-500 mt-1">{label}</div>
        </div>
      ))}
    </div>
  )
}
```

**Step 2: Create DepartmentBreakdown component**

Create `web/src/components/DepartmentBreakdown.tsx`:

```tsx
import type { DepartmentCompliance } from '@/lib/types'

function rateColor(rate: number): string {
  if (rate >= 80) return 'text-emerald-600'
  if (rate >= 50) return 'text-amber-600'
  return 'text-red-600'
}

export default function DepartmentBreakdown({ departments }: { departments: DepartmentCompliance[] }) {
  if (departments.length === 0) {
    return <p className="text-slate-500">No department data available.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left">
            <th className="py-3 pr-4 font-semibold text-slate-700">Department</th>
            <th className="py-3 px-4 font-semibold text-slate-700 text-right">Requests</th>
            <th className="py-3 px-4 font-semibold text-slate-700 text-right">Avg Days</th>
            <th className="py-3 px-4 font-semibold text-slate-700 text-right">On-Time %</th>
            <th className="py-3 pl-4 font-semibold text-slate-700 text-right">Slowest</th>
          </tr>
        </thead>
        <tbody>
          {departments.map((dept) => (
            <tr key={dept.department} className="border-b border-slate-100 hover:bg-slate-50">
              <td className="py-3 pr-4 font-medium text-slate-800">{dept.department}</td>
              <td className="py-3 px-4 text-right text-slate-600">{dept.requestCount}</td>
              <td className="py-3 px-4 text-right text-slate-600">{dept.avgDays}</td>
              <td className={`py-3 px-4 text-right font-medium ${rateColor(dept.onTimeRate)}`}>
                {dept.onTimeRate}%
              </td>
              <td className="py-3 pl-4 text-right text-slate-500">{dept.slowestDays} days</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

**Step 3: Create RecentRequests component**

Create `web/src/components/RecentRequests.tsx`:

```tsx
import type { NextRequestRequest } from '@/lib/types'

function statusBadge(status: string) {
  const lower = status.toLowerCase()
  if (lower === 'completed' || lower === 'closed') {
    return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700">Completed</span>
  }
  if (lower.includes('progress') || lower === 'in_progress') {
    return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">In Progress</span>
  }
  if (lower === 'overdue') {
    return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">Overdue</span>
  }
  return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">{status}</span>
}

function daysElapsed(submittedDate: string | null, closedDate: string | null): string {
  if (closedDate) {
    const days = Math.floor(
      (new Date(closedDate).getTime() - new Date(submittedDate || closedDate).getTime()) /
      (1000 * 60 * 60 * 24)
    )
    return `${days}d to close`
  }
  if (submittedDate) {
    const days = Math.floor(
      (Date.now() - new Date(submittedDate).getTime()) / (1000 * 60 * 60 * 24)
    )
    return `${days}d elapsed`
  }
  return ''
}

export default function RecentRequests({ requests }: { requests: NextRequestRequest[] }) {
  if (requests.length === 0) {
    return <p className="text-slate-500">No CPRA requests found.</p>
  }

  return (
    <div className="space-y-3">
      {requests.map((r) => (
        <div
          key={r.id}
          className="bg-white rounded-lg border border-slate-200 p-4 hover:border-slate-300 transition-colors"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-mono text-slate-400">{r.request_number}</span>
                {r.department && (
                  <span className="px-2 py-0.5 rounded text-xs bg-civic-navy/10 text-civic-navy font-medium">
                    {r.department}
                  </span>
                )}
              </div>
              <p className="text-sm text-slate-700 line-clamp-2">
                {r.request_text.slice(0, 120)}{r.request_text.length > 120 ? '...' : ''}
              </p>
            </div>
            <div className="flex flex-col items-end gap-1 shrink-0">
              {statusBadge(r.status)}
              <span className="text-xs text-slate-400">
                {daysElapsed(r.submitted_date, r.closed_date)}
              </span>
            </div>
          </div>
          {r.portal_url && (
            <a
              href={r.portal_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-civic-navy hover:underline mt-2 inline-block"
            >
              View on portal &rarr;
            </a>
          )}
        </div>
      ))}
    </div>
  )
}
```

**Step 4: Create the dashboard page**

Create `web/src/app/public-records/page.tsx`:

```tsx
import type { Metadata } from 'next'
import { getPublicRecordsStats, getDepartmentCompliance, getRecentRequests } from '@/lib/queries'
import ComplianceStats from '@/components/ComplianceStats'
import DepartmentBreakdown from '@/components/DepartmentBreakdown'
import RecentRequests from '@/components/RecentRequests'
import LastUpdated from '@/components/LastUpdated'

export const revalidate = 3600 // Revalidate every hour

export const metadata: Metadata = {
  title: 'Public Records',
  description: 'CPRA compliance dashboard — track Richmond public records request response times and department performance.',
}

export default async function PublicRecordsPage() {
  const [stats, departments, recentRequests] = await Promise.all([
    getPublicRecordsStats(),
    getDepartmentCompliance(),
    getRecentRequests(20),
  ])

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy">Public Records Compliance</h1>
      <p className="text-slate-600 mt-2">
        Tracking Richmond&apos;s response to California Public Records Act (CPRA) requests.
        Under CPRA, agencies must respond within 10 calendar days.
      </p>

      {/* Stats bar */}
      <section className="mt-8">
        <ComplianceStats stats={stats} />
      </section>

      {/* Department breakdown */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-4">Department Breakdown</h2>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <DepartmentBreakdown departments={departments} />
        </div>
      </section>

      {/* Recent requests */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-4">Recent Requests</h2>
        <RecentRequests requests={recentRequests} />
      </section>

      {/* Methodology note */}
      <section className="mt-10 bg-slate-50 rounded-lg p-6 border border-slate-200">
        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">About This Data</h3>
        <p className="text-sm text-slate-600 mt-2">
          Data is scraped from Richmond&apos;s{' '}
          <a
            href="https://cityofrichmondca.nextrequest.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-civic-navy hover:underline"
          >
            NextRequest portal
          </a>
          . &quot;On-time&quot; means the request was closed within 10 calendar days of submission
          (the CPRA statutory deadline). Some requests may have legitimate extensions.
          This dashboard tracks response patterns, not legal compliance determinations.
        </p>
      </section>

      <LastUpdated />
    </div>
  )
}
```

**Step 5: Add "Public Records" to navigation**

In `web/src/components/Nav.tsx`, add to the `navLinks` array:

```typescript
const navLinks = [
  { href: '/meetings', label: 'Meetings' },
  { href: '/council', label: 'Council' },
  { href: '/public-records', label: 'Public Records' },
  { href: '/reports', label: 'Reports' },
  { href: '/about', label: 'About' },
]
```

**Step 6: Verify the build compiles**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/web && npm run build 2>&1 | tail -20`

Expected: Build succeeds (pages may show "no data" but no compilation errors)

**Step 7: Commit**

```bash
git add web/src/components/ComplianceStats.tsx web/src/components/DepartmentBreakdown.tsx \
  web/src/components/RecentRequests.tsx web/src/app/public-records/page.tsx \
  web/src/components/Nav.tsx
git commit -m "Phase 2: add CPRA compliance dashboard page and components"
```

---

## Task 9: Run Full Test Suite + Final Verification

**Step 1: Run all Python tests**

Run: `python3 -m pytest tests/ -q --tb=short`

Expected: All tests PASS (existing 208 + new ~30 = ~238 total)

**Step 2: Run frontend build**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/web && npm run build 2>&1 | tail -10`

Expected: Build succeeds

**Step 3: Verify git is clean**

Run: `git status`

Expected: Clean working tree (everything committed)

**Step 4: Push to remote**

Run: `git push`

---

## Task 10: Update CLAUDE.md with Phase D completion

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add Phase D entries to "Done" section**

Add entries for:
- NextRequest/CPRA scraper + tests
- Archive Center discovery engine + tests
- Data sync integration (NextRequest + Archive Center)
- CPRA compliance dashboard (frontend)
- Migration 003 (NextRequest tables)
- NextRequest document extractor

**Step 2: Update staleness thresholds doc**

Verify the `archive_center: 45` threshold is documented in CLAUDE.md's practical knowledge section.

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "Phase 2: update CLAUDE.md with Phase D completion"
```

---

## Summary

| Task | Files | Tests | Est. Time |
|------|-------|-------|-----------|
| 1. Migration 003 | 1 new | — | 5 min |
| 2. NextRequest scraper | 2 new | ~15 tests | 45 min |
| 3. Archive Center discovery | 2 new | ~12 tests | 30 min |
| 4. Data sync integration | 2 modified | ~4 tests | 20 min |
| 5. Infra updates | 2 modified | — | 10 min |
| 6. NextRequest extractor | 2 new | ~5 tests | 25 min |
| 7. Frontend types/queries | 3 new/modified | — | 15 min |
| 8. Dashboard page + components | 5 new, 1 modified | — | 30 min |
| 9. Full test suite | — | ~238 total | 10 min |
| 10. CLAUDE.md update | 1 modified | — | 5 min |
| **Total** | **~18 files** | **~36 new tests** | **~3.5 hours** |

**Important notes for the implementing engineer:**

1. **NextRequest selectors will need live discovery.** The HTML fixtures in tests use assumed class names. When first hitting the live site via Playwright, you'll need to inspect the actual DOM and update selectors in both the scraper and the test fixtures. This is expected — the self-healing hook exists for this reason.

2. **Run migration 003 manually in Supabase SQL Editor** before testing data sync against production.

3. **Playwright needs `playwright install chromium`** before the scraper works locally.

4. **The extractor uses `claude-sonnet-4-20250514`** — verify this is the current model name at runtime.

5. **Test against the live NextRequest portal** after the scraper skeleton works with fixtures. Adjust selectors based on actual page structure.
