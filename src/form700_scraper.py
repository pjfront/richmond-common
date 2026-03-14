"""
Richmond Common -- Form 700 (SEI) Scraper

Requests-based scraper for NetFile's public SEI portal.
Discovers Form 700 filings, downloads PDFs, and stores in Layer 1.

Architecture:
  - Config resolution: _resolve_form700_config()
  - Fetch layer (requests + Session): _get_portal_session(), _search_filings(), _paginate()
  - Parse layer (BeautifulSoup): _parse_filing_grid()
  - Orchestration: discover_filings(), download_filing_pdf()
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

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────

NETFILE_SEI_URL = "https://public.netfile.com/pub/?AID=RICH"
NETFILE_SEI_BASE = "https://public.netfile.com/pub/"
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

# Default user agent mimicking a real browser
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


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


# ── Fetch layer (requests + Session) ─────────────────────────

def _create_session() -> requests.Session:
    """Create a requests session with browser-like headers."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return session


def _extract_hidden_fields(soup: BeautifulSoup) -> dict[str, str]:
    """Extract all hidden form fields from page HTML.

    ASP.NET WebForms requires ViewState and related hidden fields
    to be posted back with every form submission.
    """
    fields: dict[str, str] = {}
    for inp in soup.find_all("input", type="hidden"):
        name = inp.get("name", "")
        if name:
            fields[name] = inp.get("value", "")
    return fields


def _build_search_form_data(
    hidden_fields: dict[str, str],
    *,
    filer_name: str = "",
    job_title: str = "",
    department: str = "",
    statement_type: str = "All",
    filer_type: str = "All",
    start_date: str = "1/1/2018",
    end_date: str = "",
) -> dict[str, str]:
    """Build the POST form data for a search submission.

    Combines ASP.NET hidden fields with search filter values.
    """
    if not end_date:
        end_date = datetime.now().strftime("%-m/%-d/%Y")

    form_data = dict(hidden_fields)  # Start with ViewState etc.
    form_data.update({
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "ctl00$phBody$filingSearch$tbFilerName": filer_name,
        "ctl00$phBody$filingSearch$searchJob": job_title,
        "ctl00$phBody$filingSearch$DepartmentDropDown": department,
        "ctl00$phBody$filingSearch$StatementTypeDropDown": statement_type,
        "ctl00$phBody$filingSearch$FilerTypeDropDown": filer_type,
        "ctl00$phBody$filingSearch$searchSD$dateInput": start_date,
        "ctl00$phBody$filingSearch$searchED$dateInput": end_date,
        "ctl00$phBody$filingSearch$btnSearch": "Search",
    })
    return form_data


def _extract_pagination_targets(soup: BeautifulSoup) -> list[str]:
    """Extract __doPostBack targets for pagination links.

    Returns list of EVENTTARGET strings for pages beyond the current one.
    The current page is shown as a span (not a link), so only
    clickable page links are returned.
    """
    targets = []
    # Telerik RadGrid pager uses .rgNumPart for page number links
    pager_links = soup.select(".rgNumPart a")
    for link in pager_links:
        href = link.get("href", "")
        # Extract target from: javascript:__doPostBack('target','')
        match = re.search(r"__doPostBack\('([^']+)'", href)
        if match:
            targets.append(match.group(1))
    return targets


def _get_current_page_number(soup: BeautifulSoup) -> int:
    """Get the current page number from the RadGrid pager."""
    current = soup.select_one(".rgCurrentPage, .rgNumPart span")
    if current:
        try:
            return int(current.get_text(strip=True))
        except ValueError:
            pass
    return 1


# ── Parse layer ──────────────────────────────────────────────

def _parse_filing_grid(html: str) -> list[dict]:
    """Parse the filing list grid from portal HTML.

    Uses Telerik RadGrid CSS classes (.rgRow, .rgAltRow) for
    reliable row selection, falling back to generic table parsing.

    Returns list of filing dicts with keys:
      filer_name, department, position, statement_type, filing_date,
      period, filing_year, period_start, period_end, detail_url, row_index
    """
    soup = BeautifulSoup(html, "html.parser")
    filings = []

    # Strategy 1: RadGrid data rows (most reliable)
    data_rows = soup.select(".rgRow, .rgAltRow")

    if data_rows:
        # Get headers from the parent table of the data rows.
        # We avoid .rgHeader selector because Telerik RadDatePicker
        # widgets on the page also use that class, causing false matches.
        headers = []
        parent_table = data_rows[0].find_parent("table")
        if parent_table:
            first_row = parent_table.find("tr")
            if first_row:
                th_cells = first_row.find_all("th")
                if th_cells:
                    headers = [th.get_text(strip=True).lower() for th in th_cells]
                else:
                    # Some grids use <td> for headers in the first row
                    headers = [td.get_text(strip=True).lower() for td in first_row.find_all("td")]

        col_map = _build_column_map(headers)

        for row_idx, row in enumerate(data_rows, start=1):
            filing = _parse_data_row(row, col_map, row_idx)
            if filing:
                filings.append(filing)

        return filings

    # Strategy 2: Fallback to generic table parsing
    grid = soup.select_one(
        ".RadGrid table, .rgMasterTable, table.rgMasterTable, "
        "[id*='GridView'] table, [id*='grid'] table, "
        "table[id*='Filing'], table.data-table"
    )
    if not grid:
        tables = soup.find_all("table")
        if tables:
            grid = max(tables, key=lambda t: len(t.find_all("tr")))

    if not grid:
        logger.warning("Could not find filing grid in HTML")
        return filings

    rows = grid.find_all("tr")
    if len(rows) < 2:
        return filings

    headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
    col_map = _build_column_map(headers)

    for row_idx, row in enumerate(rows[1:], start=1):
        filing = _parse_data_row(row, col_map, row_idx)
        if filing:
            filings.append(filing)

    return filings


def _build_column_map(headers: list[str]) -> dict[str, int]:
    """Map header text to field names by column index."""
    col_map: dict[str, int] = {}
    for i, h in enumerate(headers):
        if "name" in h or "filer" in h:
            col_map["filer_name"] = i
        elif "department" in h or "dept" in h:
            col_map["department"] = i
        elif "title" in h or "position" in h or "job" in h:
            col_map["position"] = i
        elif "caption" in h or "type" in h or "statement" in h:
            col_map["statement_type"] = i
        elif ("date" in h or h == "filed") and "period" not in h:
            col_map["filing_date"] = i
        elif "period" in h:
            col_map["period"] = i
        elif "view" in h:
            col_map["view"] = i
    return col_map


def _parse_data_row(
    row, col_map: dict[str, int], row_idx: int
) -> dict | None:
    """Parse a single data row into a filing dict."""
    cells = row.find_all("td")
    if not cells or len(cells) < 2:
        return None

    def get_cell(field: str) -> str:
        idx = col_map.get(field)
        if idx is not None and idx < len(cells):
            return cells[idx].get_text(strip=True)
        return ""

    filer_name = get_cell("filer_name")
    if not filer_name:
        return None

    # Extract PDF link from the row
    detail_url = None
    for link in row.find_all("a", href=True):
        href = link["href"]
        if "getdocument" in href.lower() or "image" in href.lower() or "document" in href.lower():
            # Make absolute URL if relative
            if not href.startswith("http"):
                detail_url = NETFILE_SEI_BASE + href
            else:
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

    return {
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
    }


# ── Orchestration ─────────────────────────────────────────────

async def discover_filings(
    city_fips: str | None = None,
    department: str | None = None,
    filer_type: str | None = None,
    statement_type: str | None = None,
    max_pages: int = 20,
    start_date: str = "1/1/2018",
) -> list[dict]:
    """Discover all Form 700 filings from NetFile SEI portal.

    Uses requests (not Playwright) to handle the ASP.NET WebForms
    portal. Steps:
      1. GET portal page to capture ViewState
      2. POST search form to get first page of results
      3. POST pagination targets for subsequent pages

    Returns list of filing metadata dicts.
    """
    portal_url, _fips = _resolve_form700_config(city_fips)
    session = _create_session()

    # Step 1: GET initial page to capture ViewState
    logger.info(f"Fetching portal: {portal_url}")
    try:
        resp = session.get(portal_url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch portal: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    hidden_fields = _extract_hidden_fields(soup)

    if "__VIEWSTATE" not in hidden_fields:
        logger.error("No __VIEWSTATE found in portal page. Portal structure may have changed.")
        return []

    # Step 2: POST search form
    end_date = datetime.now().strftime("%-m/%-d/%Y")
    form_data = _build_search_form_data(
        hidden_fields,
        department=department or "",
        filer_type=filer_type or "All",
        statement_type=statement_type or "All",
        start_date=start_date,
        end_date=end_date,
    )

    logger.info(f"Submitting search: {start_date} to {end_date}")
    try:
        resp = session.post(portal_url, data=form_data, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Search POST failed: {e}")
        return []

    # Parse page 1
    soup = BeautifulSoup(resp.text, "html.parser")
    all_filings = _parse_filing_grid(resp.text)
    logger.info(f"Page 1: {len(all_filings)} filings discovered")

    if not all_filings:
        logger.warning("No filings found on first page. Check portal structure or date range.")
        return []

    # Step 3: Paginate through remaining pages
    # Track visited targets to prevent cycling (RadGrid pager shows
    # a sliding window of page links that can loop back to earlier pages)
    visited_targets: set[str] = set()
    page_num = 1
    while page_num < max_pages:
        # Find the next unvisited page link after the current page indicator
        next_target = None
        pager_links = soup.select(".rgNumPart a, .rgNumPart span")
        found_current = False
        for el in pager_links:
            if el.name == "span" or "rgCurrentPage" in el.get("class", []):
                found_current = True
                continue
            if found_current:
                href = el.get("href", "")
                match = re.search(r"__doPostBack\('([^']+)'", href)
                if match:
                    target = match.group(1)
                    if target not in visited_targets:
                        next_target = target
                        break

        if not next_target:
            # No more unvisited pages
            break

        visited_targets.add(next_target)

        # Build pagination POST data
        hidden_fields = _extract_hidden_fields(soup)
        page_data = dict(hidden_fields)
        page_data["__EVENTTARGET"] = next_target
        page_data["__EVENTARGUMENT"] = ""
        # Keep search fields populated
        page_data["ctl00$phBody$filingSearch$tbFilerName"] = ""
        page_data["ctl00$phBody$filingSearch$searchJob"] = ""
        page_data["ctl00$phBody$filingSearch$DepartmentDropDown"] = department or ""
        page_data["ctl00$phBody$filingSearch$StatementTypeDropDown"] = statement_type or "All"
        page_data["ctl00$phBody$filingSearch$FilerTypeDropDown"] = filer_type or "All"
        page_data["ctl00$phBody$filingSearch$searchSD$dateInput"] = start_date
        page_data["ctl00$phBody$filingSearch$searchED$dateInput"] = end_date

        page_num += 1
        logger.info(f"Fetching page {page_num}...")

        try:
            resp = session.post(portal_url, data=page_data, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"Pagination to page {page_num} failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        page_filings = _parse_filing_grid(resp.text)
        if not page_filings:
            break

        all_filings.extend(page_filings)
        logger.info(f"Page {page_num}: {len(page_filings)} filings discovered")

        # Rate limiting
        time.sleep(1)

    logger.info(f"Total filings discovered: {len(all_filings)}")
    return all_filings


async def download_filing_pdf(
    url: str,
    dest_dir: Path | None = None,
    filer_name: str = "unknown",
    filing_year: int | None = None,
) -> Path | None:
    """Download a single Form 700 PDF.

    Returns the local file path, or None if download failed.
    """
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
            "User-Agent": _USER_AGENT,
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
        "--start-date", type=str, default="1/1/2018",
        help="Start date for filing search (default: 1/1/2018)"
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
            start_date=args.start_date,
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
