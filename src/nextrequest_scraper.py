"""
Richmond Common — NextRequest/CPRA Scraper

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

        title_el = item.select_one(".request-title")
        if not title_el:
            # Fallback: use .request-link but exclude nested .request-number
            link_el = item.select_one(".request-link")
            if link_el:
                # Clone and remove nested number span to get clean title
                num_span = link_el.select_one(".request-number")
                if num_span:
                    num_span.extract()
                title = link_el.get_text(strip=True)
            else:
                title = ""
        else:
            title = title_el.get_text(strip=True)

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


def _parse_document_list(html: str, *, base_url: str | None = None) -> list[dict]:
    """Parse documents from a request detail page.

    Returns list of dicts with: filename, download_url, file_size, released_date.
    """
    _base = base_url or BASE_URL
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
            download_url = f"{_base}{download_url}"

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


async def _fetch_request_list(page, page_num: int = 1, *, base_url: str | None = None) -> str:
    """Fetch request list page HTML via Playwright.

    Thin layer — replaceable with API call later.
    """
    _base = base_url or BASE_URL
    url = f"{_base}/requests?page={page_num}"
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


async def _fetch_request_detail(page, request_id: str, *, base_url: str | None = None) -> str:
    """Fetch request detail page HTML via Playwright.

    Thin layer — replaceable with API call later.
    """
    _base = base_url or BASE_URL
    url = f"{_base}/requests/{request_id}"
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


async def scrape_request_detail(page, request_id: str, *, city_fips: str | None = None) -> dict:
    """Scrape full detail for a single request.

    Returns RequestDetail dict with documents.
    """
    base_url, _fips = _resolve_nextrequest_config(city_fips)
    html = await _fetch_request_detail(page, request_id, base_url=base_url)
    detail = _parse_request_detail(html)
    documents = _parse_document_list(html, base_url=base_url)
    detail["documents"] = documents
    detail["portal_url"] = f"{base_url}/requests/{request_id}"
    return detail


async def scrape_all(
    since_date: str | None = None,
    download_docs: bool = False,
    extract_text: bool = False,
    city_fips: str | None = None,
) -> dict:
    """Full scrape: list requests, get details, optionally download docs.

    Returns result dict with city_fips, source, scraped_at, requests, stats.
    """
    base_url, resolved_fips = _resolve_nextrequest_config(city_fips)
    pw, browser, context = await create_browser()
    page = await context.new_page()

    try:
        # Step 1: Get request list
        all_summaries = []
        page_num = 1

        while page_num <= 50:
            html = await _fetch_request_list(page, page_num, base_url=base_url)
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
                detail = await scrape_request_detail(page, req_id, city_fips=city_fips)

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
        "city_fips": resolved_fips,
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
        description="Richmond Common — NextRequest/CPRA Scraper",
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
