"""
Richmond Common — NextRequest/CPRA Scraper

Uses NextRequest's public client JSON API to fetch CPRA request
metadata, documents, and status for compliance tracking and
cross-referencing. No Playwright or browser required.

API endpoints (discovered from SPA network calls):
  - GET /client/requests?page_number=N  → paginated list (100/page)
  - GET /client/requests/{id}           → request detail
  - GET /client/requests/{id}/timeline  → request timeline/history

Architecture:
  - Fetch layer: _fetch_request_list, _fetch_request_detail (HTTP JSON)
  - Transform layer: _transform_list_item, _transform_detail
  - Document handling: download_document, extract_document_text
  - Orchestration: scrape_all, save_to_db
  - DB operations: save_to_db (upsert)

Usage:
  python nextrequest_scraper.py --list
  python nextrequest_scraper.py --since 2026-01-01
  python nextrequest_scraper.py --request 26-414
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

import requests as http_client
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────

BASE_URL = "https://cityofrichmondca.nextrequest.com"
CLIENT_API = "/client/requests"
CITY_FIPS = "0660620"
DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw" / "nextrequest"
PAGE_SIZE = 100  # NextRequest returns 100 per page

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RichmondCommon/1.0",
    "Accept": "application/json",
}

RATE_LIMIT_MS = 500  # ms between API calls

NEXTREQUEST_PLATFORM_PROFILE = {
    "platform": "NextRequest (CivicPlus)",
    "url_pattern": "https://{city_slug}.nextrequest.com",
    "client_api": "/client/requests",
    "detail_api": "/client/requests/{request_id}",
    "timeline_api": "/client/requests/{request_id}/timeline",
    "document_url": "/documents/{document_id}/download",
    "spa": True,
    "api_v2_exists": True,
    "api_v2_base": "/api/v2/",
    "notes": "SaaS platform — public client JSON API discovered from SPA. Identical across all cities.",
}


# ── Config resolution ────────────────────────────────────────

def _resolve_nextrequest_config(
    city_fips: str | None = None,
) -> tuple[str, str]:
    """Resolve base_url and city_fips from registry or module defaults.

    Returns (base_url, city_fips).
    """
    if city_fips is not None:
        from city_config import get_data_source_config
        cfg = get_data_source_config(city_fips, "nextrequest")
        return cfg["base_url"], city_fips
    return BASE_URL, CITY_FIPS


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


def _strip_html(html_str: str | None) -> str:
    """Strip HTML tags from a string, returning plain text."""
    if not html_str:
        return ""
    return BeautifulSoup(html_str, "html.parser").get_text(separator=" ", strip=True)


# ── JSON API fetch layer ─────────────────────────────────────

def _fetch_request_list(
    page_number: int = 1,
    *,
    base_url: str | None = None,
) -> dict:
    """Fetch paginated request list from client API.

    Returns raw JSON: {"total_count": N, "requests": [...]}.
    """
    _base = base_url or BASE_URL
    url = f"{_base}{CLIENT_API}"
    params = {}
    if page_number > 1:
        params["page_number"] = page_number

    resp = http_client.get(url, headers=HTTP_HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _fetch_request_detail(
    request_id: str,
    *,
    base_url: str | None = None,
) -> dict:
    """Fetch single request detail from client API.

    Returns raw JSON with full request fields.
    """
    _base = base_url or BASE_URL
    url = f"{_base}{CLIENT_API}/{request_id}"
    resp = http_client.get(url, headers=HTTP_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _fetch_request_timeline(
    request_id: str,
    *,
    base_url: str | None = None,
) -> dict:
    """Fetch request timeline (status history) from client API.

    Returns raw JSON: {"total_count": N, "timeline": [...], "pinned": [...]}.
    """
    _base = base_url or BASE_URL
    url = f"{_base}{CLIENT_API}/{request_id}/timeline"
    resp = http_client.get(url, headers=HTTP_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ── Transform layer (JSON → internal format) ─────────────────

def _transform_list_item(item: dict, *, base_url: str | None = None) -> dict:
    """Transform a list API item into our internal RequestSummary format.

    API fields: id, request_state, request_text, department_names,
    poc_name, request_date, due_date, staff_cost, visibility, request_path.
    """
    _base = base_url or BASE_URL
    submitted_date = _parse_date(item.get("request_date"))

    return {
        "request_number": item.get("id", "unknown"),
        "request_text": (item.get("request_text") or "").strip(),
        "status": item.get("request_state", "unknown"),
        "department": (item.get("department_names") or "").strip() or None,
        "submitted_date": submitted_date,
        "due_date": _parse_date(item.get("due_date")),
        "poc_name": item.get("poc_name"),
        "portal_url": f"{_base}{item['request_path']}" if item.get("request_path") else None,
    }


def _transform_detail(detail: dict, *, base_url: str | None = None) -> dict:
    """Transform a detail API response into our internal RequestDetail format.

    Extracts closed_date from timeline if available. The detail API
    returns HTML in request_text, so we strip tags for plain text.
    """
    _base = base_url or BASE_URL
    request_id = detail.get("pretty_id", "unknown")
    submitted_date = _parse_date(detail.get("request_date"))
    due_date = _parse_date(detail.get("request_due_date"))

    # Department: detail API returns "None assigned" for empty
    dept = (detail.get("department_names") or "").strip()
    if dept.lower() in ("none assigned", ""):
        dept = None

    # Requester info
    requester = detail.get("requester") or {}
    requester_name = requester.get("name")

    # Point of contact
    poc = detail.get("poc") or {}
    poc_name = poc.get("email_or_name")

    # Request text is HTML in detail view
    request_text = _strip_html(detail.get("request_text"))

    return {
        "request_number": request_id,
        "request_text": request_text,
        "status": detail.get("request_state", "unknown"),
        "department": dept,
        "requester_name": requester_name,
        "poc_name": poc_name,
        "submitted_date": submitted_date,
        "due_date": due_date,
        "closed_date": None,  # Populated from timeline
        "days_to_close": None,  # Computed after closed_date is known
        "portal_url": f"{_base}/requests/{request_id}",
        "documents": [],
        "metadata": {
            "visibility": detail.get("visibility"),
            "staff_hours": detail.get("request_staff_hours"),
            "staff_cost": detail.get("request_staff_cost"),
            "field_values": [
                {
                    "name": fv.get("display_name"),
                    "value": fv.get("value"),
                }
                for fv in (detail.get("request_field_values") or [])
                if fv.get("value")
            ],
        },
    }


def _extract_closed_date_from_timeline(timeline_data: dict) -> str | None:
    """Extract closed date from timeline entries.

    Looks for "Request Closed" event and parses its date.
    """
    for entry in timeline_data.get("timeline", []):
        if entry.get("timeline_name") == "Request Closed":
            byline = entry.get("timeline_byline", "")
            # Format: "March 16, 2026,  2:12pm by Staff"
            # Extract just the date part before the comma+time
            match = re.match(r"(\w+ \d+, \d{4})", byline)
            if match:
                return _parse_date(match.group(1))
    return None


# ── Document handling ─────────────────────────────────────────

def download_document(url: str, dest_dir: Path) -> Path | None:
    """Download a document PDF from NextRequest.

    Returns the local file path, or None if download failed.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Extract filename from URL or use a default
    filename = url.rsplit("/", 1)[-1] if "/" in url else "document.pdf"
    if not filename or filename == "download":
        filename = f"doc_{int(time.time())}.pdf"

    dest_path = dest_dir / filename

    try:
        resp = http_client.get(url, timeout=60, stream=True)
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
            # Truncate department to fit VARCHAR(200) column
            # (multi-department strings can exceed 200 chars)
            dept = req.get("department")
            if dept and len(dept) > 200:
                dept = dept[:197] + "..."

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
                    dept,
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


# ── High-level orchestration ──────────────────────────────────

def list_all_requests(
    since_date: str | None = None,
    city_fips: str | None = None,
) -> list[dict]:
    """List all requests via client API, paginated.

    Returns list of RequestSummary dicts.
    """
    base_url, _fips = _resolve_nextrequest_config(city_fips)
    all_requests: list[dict] = []
    page_num = 1
    max_pages = 50

    while page_num <= max_pages:
        data = _fetch_request_list(page_num, base_url=base_url)
        total_count = data.get("total_count", 0)
        items = data.get("requests", [])

        if not items:
            break

        for item in items:
            transformed = _transform_list_item(item, base_url=base_url)
            all_requests.append(transformed)

        logger.info(
            f"Page {page_num}: {len(items)} requests "
            f"({len(all_requests)}/{total_count} total)"
        )

        # Check if we've fetched all pages
        if len(all_requests) >= total_count:
            break

        # Early stop if we've gone past since_date
        if since_date and items:
            oldest_date = _parse_date(items[-1].get("request_date"))
            if oldest_date and oldest_date < since_date:
                break

        page_num += 1
        time.sleep(RATE_LIMIT_MS / 1000)

    # Filter by since_date
    if since_date:
        all_requests = [
            r for r in all_requests
            if not r.get("submitted_date") or r["submitted_date"] >= since_date
        ]

    return all_requests


def get_request_detail(
    request_id: str,
    *,
    city_fips: str | None = None,
    include_timeline: bool = True,
) -> dict:
    """Fetch full detail for a single request via client API.

    Returns RequestDetail dict. If include_timeline is True,
    also fetches timeline to extract closed_date.
    """
    base_url, _fips = _resolve_nextrequest_config(city_fips)
    raw_detail = _fetch_request_detail(request_id, base_url=base_url)
    detail = _transform_detail(raw_detail, base_url=base_url)

    # Get closed_date from timeline
    if include_timeline and detail["status"] == "Closed":
        try:
            timeline = _fetch_request_timeline(request_id, base_url=base_url)
            closed_date = _extract_closed_date_from_timeline(timeline)
            if closed_date:
                detail["closed_date"] = closed_date
                detail["days_to_close"] = _compute_days_to_close(
                    detail["submitted_date"], closed_date
                )
        except Exception as e:
            logger.warning(f"Could not fetch timeline for {request_id}: {e}")

    return detail


def scrape_all(
    since_date: str | None = None,
    download_docs: bool = False,
    extract_text: bool = False,
    city_fips: str | None = None,
    skip_details: bool = False,
) -> dict:
    """Full scrape: list requests, optionally get details and download docs.

    When skip_details=True, uses list data only (much faster for initial sync
    where we just need request metadata without timeline/documents).

    Returns result dict with city_fips, source, scraped_at, requests, stats.
    """
    base_url, resolved_fips = _resolve_nextrequest_config(city_fips)

    # Step 1: Get all request summaries
    summaries = list_all_requests(since_date=since_date, city_fips=city_fips)
    logger.info(f"Found {len(summaries)} requests")

    if skip_details:
        # Use list data directly — no per-request detail calls
        return {
            "city_fips": resolved_fips,
            "source": "nextrequest",
            "scraped_at": datetime.now().isoformat(),
            "requests": summaries,
            "stats": {
                "total_found": len(summaries),
                "details_scraped": 0,
                "documents_found": 0,
            },
        }

    # Step 2: Get details for each request
    detailed_requests: list[dict] = []
    for i, summary in enumerate(summaries):
        req_id = summary["request_number"]
        logger.info(f"  [{i+1}/{len(summaries)}] Fetching detail for {req_id}")
        try:
            detail = get_request_detail(req_id, city_fips=city_fips)

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
            logger.error(f"  Error fetching {req_id}: {e}")
            continue

        time.sleep(RATE_LIMIT_MS / 1000)

    return {
        "city_fips": resolved_fips,
        "source": "nextrequest",
        "scraped_at": datetime.now().isoformat(),
        "requests": detailed_requests,
        "stats": {
            "total_found": len(summaries),
            "details_scraped": len(detailed_requests),
            "documents_found": sum(
                len(r.get("documents", [])) for r in detailed_requests
            ),
        },
    }


# ── CLI ───────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Richmond Common — NextRequest/CPRA Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list", action="store_true", help="List all requests")
    parser.add_argument("--request", type=str, help="Fetch single request by ID (e.g., 26-414)")
    parser.add_argument("--since", type=str, help="Only requests since YYYY-MM-DD")
    parser.add_argument("--download", action="store_true", help="Download PDFs")
    parser.add_argument("--extract", action="store_true", help="Extract text from PDFs")
    parser.add_argument("--stats", action="store_true", help="Print portal statistics")
    parser.add_argument("--skip-details", action="store_true", help="List-only mode (no per-request detail calls)")
    parser.add_argument("--output", type=str, help="Save JSON output to file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.list:
        results = list_all_requests(since_date=args.since)
        for r in results:
            dept = (r.get("department") or "")[:20]
            text = (r.get("request_text") or "")[:60]
            print(f"  {r['request_number']:12s} {r['status']:15s} {dept:20s} {text}")
        print(f"\nTotal: {len(results)} requests")

    elif args.request:
        detail = get_request_detail(args.request)
        print(json.dumps(detail, indent=2, default=str))

    else:
        results = scrape_all(
            since_date=args.since,
            download_docs=args.download,
            extract_text=args.extract,
            skip_details=args.skip_details,
        )

        if args.output:
            Path(args.output).write_text(
                json.dumps(results, indent=2, default=str), encoding="utf-8"
            )
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
