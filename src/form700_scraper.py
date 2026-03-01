"""
Richmond Transparency Project -- Form 700 (SEI) Scraper

Playwright-based scraper for NetFile's public SEI portal.
Discovers Form 700 filings, downloads PDFs, and stores in Layer 1.

Architecture:
  - Config resolution: _resolve_form700_config()
  - Fetch layer (Playwright): _fetch_filing_list(), _fetch_filing_pdf_url()
  - Parse layer (BeautifulSoup): _parse_filing_grid()
  - Orchestration: discover_filings(), download_filings()
  - Storage: save_filing_to_documents()
  - CLI: --discover, --download, --stats, --department, --filer-type

Data sources:
  - NetFile SEI Public Portal (2018+): local filers including 87200
  - FPPC DisclosureDocs (future): state-level 87200 filer filings

Usage:
  python form700_scraper.py --discover
  python form700_scraper.py --discover --department "City Council"
  python form700_scraper.py --download
  python form700_scraper.py --download --filing-year 2024
  python form700_scraper.py --stats
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────

NETFILE_SEI_URL = "https://public.netfile.com/pub/?AID=RICH"
CITY_FIPS = "0660620"
DATA_DIR = Path(__file__).parent / "data"
FORM700_DIR = DATA_DIR / "form700"

# Statement type mapping (portal label → our schema value)
STATEMENT_TYPES = {
    "annual": "annual",
    "annual statement": "annual",
    "assuming office": "assuming_office",
    "assuming office statement": "assuming_office",
    "leaving office": "leaving_office",
    "leaving office statement": "leaving_office",
    "candidate": "candidate",
    "candidate statement": "candidate",
    "amendment": "amendment",
}


# ── Config resolution ────────────────────────────────────────

def _resolve_form700_config(
    city_fips: str | None = None,
) -> tuple[str, str]:
    """Resolve portal URL and city_fips from registry or module defaults.

    Returns (portal_url, city_fips).
    """
    if city_fips is not None:
        from city_config import get_data_source_config
        cfg = get_data_source_config(city_fips, "form700")
        return cfg["netfile_sei_url"], city_fips
    return NETFILE_SEI_URL, CITY_FIPS


# ── Date parsing ──────────────────────────────────────────────

def _parse_date(date_str: str | None) -> str | None:
    """Parse various date formats to YYYY-MM-DD."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y",
                "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    logger.warning(f"Could not parse date: {date_str!r}")
    return None


def _normalize_statement_type(raw_type: str) -> str:
    """Normalize statement type to schema enum value."""
    if not raw_type:
        return "annual"
    key = raw_type.strip().lower()
    return STATEMENT_TYPES.get(key, "annual")


def _extract_filing_year(period_str: str | None, filing_date: str | None) -> int | None:
    """Extract the filing year from the period string or filing date.

    Period strings might look like "1/1/2024 - 12/31/2024" or "2024".
    """
    if period_str:
        # Try to find a 4-digit year
        years = re.findall(r'\b(20\d{2}|19\d{2})\b', period_str)
        if years:
            return int(years[-1])  # Use the end year of the period
    if filing_date:
        years = re.findall(r'\b(20\d{2}|19\d{2})\b', filing_date)
        if years:
            return int(years[0])
    return None


def _extract_period_dates(period_str: str | None) -> tuple[str | None, str | None]:
    """Extract start and end dates from a period string.

    Handles: "1/1/2024 - 12/31/2024", "01/01/2024-12/31/2024", etc.
    """
    if not period_str:
        return None, None
    # Split on dash/en-dash with optional whitespace
    parts = re.split(r'\s*[-–]\s*', period_str.strip())
    if len(parts) == 2:
        return _parse_date(parts[0]), _parse_date(parts[1])
    return None, None


# ── Parse layer (reusable) ────────────────────────────────────

def _parse_filing_grid(html: str) -> list[dict]:
    """Parse the filing list grid from portal HTML.

    Returns list of filing dicts with keys:
      filer_name, department, position, statement_type, filing_date,
      period, filing_year, period_start, period_end, detail_url, row_index
    """
    soup = BeautifulSoup(html, "html.parser")
    filings = []

    # Telerik RadGrid renders as a standard HTML table
    # Look for the main data grid
    grid = soup.select_one(
        ".RadGrid table, .rgMasterTable, table.rgMasterTable, "
        "[id*='GridView'] table, [id*='grid'] table, "
        "table[id*='Filing'], table.data-table"
    )
    if not grid:
        # Fallback: find the largest table on the page
        tables = soup.find_all("table")
        if tables:
            grid = max(tables, key=lambda t: len(t.find_all("tr")))

    if not grid:
        logger.warning("Could not find filing grid in HTML")
        return filings

    rows = grid.find_all("tr")
    if len(rows) < 2:
        return filings

    # Identify header row to map columns
    header_row = rows[0]
    headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

    # Map header text to our field names
    col_map = {}
    for i, h in enumerate(headers):
        if "name" in h or "filer" in h:
            col_map["filer_name"] = i
        elif "department" in h or "dept" in h:
            col_map["department"] = i
        elif "title" in h or "position" in h or "job" in h:
            col_map["position"] = i
        elif "caption" in h or "type" in h or "statement" in h:
            col_map["statement_type"] = i
        elif "date" in h and "period" not in h:
            col_map["filing_date"] = i
        elif "period" in h:
            col_map["period"] = i

    # Parse data rows
    for row_idx, row in enumerate(rows[1:], start=1):
        cells = row.find_all("td")
        if not cells or len(cells) < 2:
            continue

        def get_cell(field: str) -> str:
            idx = col_map.get(field)
            if idx is not None and idx < len(cells):
                return cells[idx].get_text(strip=True)
            return ""

        filer_name = get_cell("filer_name")
        if not filer_name:
            continue

        # Look for document/detail links in the row
        detail_url = None
        for link in row.find_all("a", href=True):
            href = link["href"]
            if "image" in href.lower() or "document" in href.lower() or "view" in href.lower():
                detail_url = href
                break
            # NetFile Connect2 image pattern
            if "Connect2/api/public/image" in href:
                detail_url = href
                break

        period = get_cell("period")
        filing_date = get_cell("filing_date")
        period_start, period_end = _extract_period_dates(period)
        filing_year = _extract_filing_year(period, filing_date)

        filings.append({
            "filer_name": filer_name,
            "department": get_cell("department"),
            "position": get_cell("position"),
            "statement_type": _normalize_statement_type(get_cell("statement_type")),
            "filing_date": _parse_date(filing_date),
            "period": period,
            "filing_year": filing_year,
            "period_start": period_start,
            "period_end": period_end,
            "detail_url": detail_url,
            "row_index": row_idx,
        })

    return filings


# ── Playwright fetch layer ────────────────────────────────────

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


async def _fetch_filing_list_page(
    page,
    portal_url: str,
    *,
    department: str | None = None,
    filer_type: str | None = None,
    statement_type: str | None = None,
    page_num: int = 1,
) -> str:
    """Fetch a page of the filing list from NetFile SEI portal.

    On first call (page_num=1), navigates to the portal and optionally
    sets filters. On subsequent calls, clicks the pagination control.

    Returns page HTML content.
    """
    if page_num == 1:
        await page.goto(portal_url, wait_until="networkidle", timeout=30000)
        # Wait for the grid to render
        await page.wait_for_timeout(3000)

        # Apply filters if specified
        if department:
            try:
                dept_selector = "[id*='Department'] input, [id*='department'] input, select[id*='Department']"
                dept_input = page.locator(dept_selector).first
                if await dept_input.count() > 0:
                    await dept_input.click()
                    await dept_input.fill(department)
                    await page.wait_for_timeout(1000)
                    # Select from dropdown if it appears
                    dropdown_item = page.locator(f"text='{department}'").first
                    if await dropdown_item.count() > 0:
                        await dropdown_item.click()
                        await page.wait_for_timeout(2000)
            except Exception as e:
                logger.warning(f"Could not set department filter: {e}")

        if filer_type:
            try:
                type_selector = "[id*='FilerType'] input, [id*='filerType'] input, select[id*='FilerType']"
                type_input = page.locator(type_selector).first
                if await type_input.count() > 0:
                    await type_input.click()
                    await type_input.fill(filer_type)
                    await page.wait_for_timeout(1000)
                    dropdown_item = page.locator(f"text='{filer_type}'").first
                    if await dropdown_item.count() > 0:
                        await dropdown_item.click()
                        await page.wait_for_timeout(2000)
            except Exception as e:
                logger.warning(f"Could not set filer type filter: {e}")

        # Click search/filter button if there is one
        try:
            search_btn = page.locator("input[type='submit'][value*='Search'], button:has-text('Search'), input[value*='Filter']").first
            if await search_btn.count() > 0:
                await search_btn.click()
                await page.wait_for_timeout(3000)
        except Exception as e:
            logger.debug(f"No search button found or click failed: {e}")

    else:
        # Navigate to next page via pagination
        try:
            next_btn = page.locator(
                f".rgPageNext, .rgNumPart a:has-text('{page_num}'), "
                f"a[title='Next Page'], .nextPage"
            ).first
            if await next_btn.count() > 0:
                await next_btn.click()
                await page.wait_for_timeout(3000)
            else:
                return ""  # No more pages
        except Exception as e:
            logger.warning(f"Could not navigate to page {page_num}: {e}")
            return ""

    return await page.content()


async def _extract_pdf_urls_from_page(page) -> list[dict]:
    """Extract PDF URLs from the current page by inspecting links.

    Some portals have direct PDF links; others require clicking a
    "View" button to get the PDF URL. This tries both approaches.
    """
    # Strategy 1: Find direct PDF/image links in the page
    links = await page.eval_on_selector_all(
        "a[href*='image'], a[href*='document'], a[href*='.pdf'], a[href*='Connect2']",
        """elements => elements.map(el => ({
            href: el.href,
            text: el.textContent.trim(),
            row_text: el.closest('tr') ? el.closest('tr').textContent.trim() : ''
        }))"""
    )
    return links


# ── Orchestration ─────────────────────────────────────────────

async def discover_filings(
    city_fips: str | None = None,
    department: str | None = None,
    filer_type: str | None = None,
    statement_type: str | None = None,
    max_pages: int = 20,
) -> list[dict]:
    """Discover all Form 700 filings from NetFile SEI portal.

    Returns list of filing metadata dicts.
    """
    portal_url, _fips = _resolve_form700_config(city_fips)
    pw, browser, context = await create_browser()
    page = await context.new_page()

    all_filings = []
    page_num = 1

    try:
        while page_num <= max_pages:
            html = await _fetch_filing_list_page(
                page, portal_url,
                department=department,
                filer_type=filer_type,
                statement_type=statement_type,
                page_num=page_num,
            )

            if not html:
                break

            filings = _parse_filing_grid(html)
            if not filings:
                if page_num == 1:
                    logger.warning("No filings found on first page. Check portal structure.")
                break

            # Try to extract PDF URLs for this page
            pdf_links = await _extract_pdf_urls_from_page(page)
            _attach_pdf_urls(filings, pdf_links)

            all_filings.extend(filings)
            logger.info(f"Page {page_num}: {len(filings)} filings discovered")

            page_num += 1
            await page.wait_for_timeout(1500)  # Rate limiting

    finally:
        await close_browser(pw, browser)

    logger.info(f"Total filings discovered: {len(all_filings)}")
    return all_filings


def _attach_pdf_urls(filings: list[dict], pdf_links: list[dict]) -> None:
    """Attach PDF URLs from extracted links to filing records.

    Matches by row proximity or filer name in the row text.
    """
    for filing in filings:
        if filing.get("detail_url"):
            continue  # Already has a URL from HTML parsing

        filer_lower = filing["filer_name"].lower()
        for link in pdf_links:
            row_text = link.get("row_text", "").lower()
            if filer_lower in row_text:
                filing["detail_url"] = link["href"]
                break


async def download_filing_pdf(
    url: str,
    dest_dir: Path | None = None,
    filer_name: str = "unknown",
    filing_year: int | None = None,
) -> Path | None:
    """Download a single Form 700 PDF.

    Returns the local file path, or None if download failed.
    """
    import requests

    dest_dir = dest_dir or FORM700_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename
    safe_name = re.sub(r'[^\w\-]', '_', filer_name.lower())
    year_str = str(filing_year) if filing_year else "unknown"
    filename = f"{safe_name}_{year_str}.pdf"
    filepath = dest_dir / filename

    if filepath.exists():
        logger.debug(f"Already downloaded: {filepath}")
        return filepath

    try:
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) RTP-Bot/1.0"
        })
        resp.raise_for_status()

        # Verify it looks like a PDF
        if resp.content[:4] != b'%PDF':
            logger.warning(f"Response for {filer_name} ({year_str}) is not a PDF (starts with {resp.content[:20]!r})")
            return None

        filepath.write_bytes(resp.content)
        logger.info(f"Downloaded: {filepath} ({len(resp.content):,} bytes)")
        return filepath

    except Exception as e:
        logger.error(f"Failed to download PDF for {filer_name} ({year_str}): {e}")
        return None


async def download_all_filings(
    filings: list[dict],
    dest_dir: Path | None = None,
    filing_year: int | None = None,
) -> list[dict]:
    """Download PDFs for all filings with URLs.

    Optionally filter by filing year.
    Returns list of filings with local_path added.
    """
    downloaded = []
    skipped = 0

    for filing in filings:
        # Filter by year if specified
        if filing_year and filing.get("filing_year") != filing_year:
            continue

        url = filing.get("detail_url")
        if not url:
            skipped += 1
            continue

        filepath = await download_filing_pdf(
            url,
            dest_dir=dest_dir,
            filer_name=filing["filer_name"],
            filing_year=filing.get("filing_year"),
        )
        if filepath:
            filing["local_path"] = str(filepath)
            downloaded.append(filing)

        # Rate limiting
        await asyncio.sleep(0.5)

    logger.info(f"Downloaded {len(downloaded)} PDFs, skipped {skipped} (no URL)")
    return downloaded


# ── Document storage ──────────────────────────────────────────

def save_filing_to_documents(
    conn,
    filing: dict,
    pdf_content: bytes,
    city_fips: str = CITY_FIPS,
) -> str | None:
    """Store a Form 700 PDF in Layer 1 via db.ingest_document().

    Returns the document UUID, or None if storage failed.
    """
    from db import ingest_document

    source_url = filing.get("detail_url", "")
    filer_name = filing.get("filer_name", "unknown")
    filing_year = filing.get("filing_year")

    try:
        doc_id = ingest_document(
            conn,
            city_fips=city_fips,
            source_type="form700",
            raw_content=pdf_content,
            credibility_tier=1,  # Tier 1: official government filings
            source_url=source_url,
            source_identifier=f"form700_{filer_name}_{filing_year}",
            mime_type="application/pdf",
            metadata={
                "filer_name": filer_name,
                "department": filing.get("department"),
                "position": filing.get("position"),
                "statement_type": filing.get("statement_type"),
                "filing_year": filing_year,
                "filing_date": filing.get("filing_date"),
                "period": filing.get("period"),
                "pipeline": "form700_scraper",
            },
        )
        return str(doc_id)
    except Exception as e:
        logger.error(f"Failed to store document for {filer_name}: {e}")
        return None


# ── Statistics ────────────────────────────────────────────────

def print_filing_stats(filings: list[dict]) -> None:
    """Print summary statistics for discovered filings."""
    if not filings:
        print("No filings found.")
        return

    # By department
    depts: dict[str, int] = {}
    for f in filings:
        dept = f.get("department") or "Unknown"
        depts[dept] = depts.get(dept, 0) + 1

    # By year
    years: dict[int, int] = {}
    for f in filings:
        y = f.get("filing_year")
        if y:
            years[y] = years.get(y, 0) + 1

    # By statement type
    types: dict[str, int] = {}
    for f in filings:
        st = f.get("statement_type") or "unknown"
        types[st] = types.get(st, 0) + 1

    # Count with PDF URLs
    with_url = sum(1 for f in filings if f.get("detail_url"))

    print(f"\n{'='*60}")
    print(f"Form 700 Filing Statistics")
    print(f"{'='*60}")
    print(f"Total filings:    {len(filings)}")
    print(f"With PDF URLs:    {with_url}")
    print(f"Unique filers:    {len({f['filer_name'] for f in filings})}")

    print(f"\nBy Department ({len(depts)} departments):")
    for dept, count in sorted(depts.items(), key=lambda x: -x[1])[:15]:
        print(f"  {dept:<40} {count:>4}")
    if len(depts) > 15:
        print(f"  ... and {len(depts) - 15} more")

    print(f"\nBy Filing Year:")
    for year in sorted(years.keys(), reverse=True):
        print(f"  {year}:  {years[year]:>4}")

    print(f"\nBy Statement Type:")
    for st, count in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  {st:<25} {count:>4}")

    print(f"{'='*60}\n")


# ── CLI ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Form 700 (Statement of Economic Interests) scraper"
    )
    parser.add_argument(
        "--discover", action="store_true",
        help="Discover filings from NetFile SEI portal"
    )
    parser.add_argument(
        "--download", action="store_true",
        help="Download PDFs for discovered filings"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Show filing statistics (requires prior --discover)"
    )
    parser.add_argument(
        "--department", type=str, default=None,
        help="Filter by department (e.g. 'City Council')"
    )
    parser.add_argument(
        "--filer-type", type=str, default=None,
        help="Filter by filer type (e.g. '87200 Filers Only')"
    )
    parser.add_argument(
        "--filing-year", type=int, default=None,
        help="Filter downloads by filing year"
    )
    parser.add_argument(
        "--city-fips", type=str, default=CITY_FIPS,
        help=f"City FIPS code (default: {CITY_FIPS})"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output JSON file for discovery results"
    )
    parser.add_argument(
        "--max-pages", type=int, default=20,
        help="Maximum pages to scrape (default: 20)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Verbose logging"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not (args.discover or args.download or args.stats):
        parser.print_help()
        sys.exit(1)

    output_file = Path(args.output) if args.output else FORM700_DIR / "filings.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if args.discover or args.download:
        # Discover filings
        filings = asyncio.run(discover_filings(
            city_fips=args.city_fips,
            department=args.department,
            filer_type=args.filer_type,
            max_pages=args.max_pages,
        ))

        # Save discovery results
        output_file.write_text(json.dumps(filings, indent=2, default=str))
        logger.info(f"Saved {len(filings)} filings to {output_file}")

        if args.stats or not args.download:
            print_filing_stats(filings)

        if args.download:
            downloaded = asyncio.run(download_all_filings(
                filings,
                filing_year=args.filing_year,
            ))
            logger.info(f"Downloaded {len(downloaded)} PDFs to {FORM700_DIR}")

    elif args.stats:
        # Load previously discovered filings
        if output_file.exists():
            filings = json.loads(output_file.read_text())
            print_filing_stats(filings)
        else:
            print(f"No filings data found at {output_file}. Run --discover first.")
            sys.exit(1)


if __name__ == "__main__":
    main()
