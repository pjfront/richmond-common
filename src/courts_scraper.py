"""
Richmond Common -- Court Records Scraper (Tyler Odyssey)

Targeted name-based lookup tool for Contra Costa County civil court records.
Searches the Tyler Odyssey Smart Search portal for names of officials, donors,
and contractors to find civil case involvement.

Architecture:
  - Config resolution: _resolve_courts_config()
  - Session layer: _create_session(), _extract_hidden_fields()
  - Search: search_by_name(), _parse_search_results()
  - Case detail: fetch_case_detail(), _parse_case_parties()
  - Name list: build_search_list()
  - Cross-reference: cross_reference_parties()
  - Orchestration: lookup_entities()
  - Storage: save_cases_to_db()
  - CLI: --search-name, --search-all, --dry-run, --stats

Data source:
  - Tyler Odyssey Portal (Contra Costa County): civil cases only
  - Post-2022 security hardened (judyrecords incident)
  - Targeted lookups only (20-50 names), not bulk scraping

Usage:
  python courts_scraper.py --search-name "Eduardo Martinez"
  python courts_scraper.py --search-all --dry-run
  python courts_scraper.py --search-all
  python courts_scraper.py --stats
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────

CITY_FIPS = "0660620"
DEFAULT_PORTAL_URL = "https://odyportal.cc-courts.org/portal"
DEFAULT_SEARCH_PATH = "/Portal/Home/Dashboard/29"
DEFAULT_COUNTY_FIPS = "06013"  # Contra Costa County

DEFAULT_SEARCH_DELAY = 3.0   # seconds between name searches
DEFAULT_CASE_DELAY = 2.0     # seconds between case detail fetches
MAX_RESULTS_PER_NAME = 50    # cap results per name search

# Confidence scores for match types
CONFIDENCE_EXACT = 0.9
CONFIDENCE_CONTAINS = 0.7
CONFIDENCE_FUZZY = 0.5
CONFIDENCE_LAST_NAME = 0.3

# Default user agent mimicking a real browser
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


# ── Config resolution ────────────────────────────────────────

def _resolve_courts_config(
    city_fips: str | None = None,
) -> tuple[str, str, str, str]:
    """Resolve portal URL, search path, county_fips, and city_fips.

    Returns (portal_url, search_path, county_fips, city_fips).
    """
    if city_fips is not None:
        from city_config import get_data_source_config
        cfg = get_data_source_config(city_fips, "courts")
        return (
            cfg["portal_url"],
            cfg.get("smart_search_path", DEFAULT_SEARCH_PATH),
            cfg["county_fips"],
            city_fips,
        )
    return DEFAULT_PORTAL_URL, DEFAULT_SEARCH_PATH, DEFAULT_COUNTY_FIPS, CITY_FIPS


# ── Date parsing ─────────────────────────────────────────────

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


# ── Name normalization ───────────────────────────────────────

def _normalize_name(name: str) -> str:
    """Normalize a name for matching: lowercase, strip punctuation, collapse whitespace."""
    if not name:
        return ""
    text = name.lower().strip()
    text = re.sub(r'[,.\'"!?;:()\[\]{}]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _detect_organization(name: str) -> bool:
    """Heuristic: detect if a party name is likely an organization."""
    org_indicators = [
        'inc', 'llc', 'corp', 'ltd', 'company', 'co.', 'association',
        'foundation', 'trust', 'bank', 'insurance', 'services',
        'group', 'partners', 'enterprises', 'holdings', 'solutions',
        'city of', 'county of', 'state of', 'department', 'commission',
        'board of', 'authority', 'district', 'agency',
    ]
    lower = name.lower()
    return any(ind in lower for ind in org_indicators)


# ── Session layer ────────────────────────────────────────────

def _create_session(verify_ssl: bool = True) -> requests.Session:
    """Create a requests session with browser-like headers."""
    session = requests.Session()
    session.verify = verify_ssl
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


# ── Search layer ─────────────────────────────────────────────

def search_by_name(
    session: requests.Session,
    name: str,
    portal_url: str,
    search_path: str,
) -> list[dict]:
    """Search the Odyssey Smart Search for a person/entity name.

    Steps:
      1. GET the search page to capture any ViewState/tokens
      2. POST or GET the search with the name query
      3. Parse results HTML for case listings
      4. Handle pagination if results span multiple pages

    Returns list of case summary dicts with keys:
      case_number, case_type, filing_date, case_status, case_title, detail_url
    """
    search_url = portal_url.rstrip("/") + search_path

    try:
        # Step 1: Load the search page to establish session/cookies
        resp = session.get(search_url, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        hidden_fields = _extract_hidden_fields(soup)

        # Step 2: Submit search
        # Tyler Odyssey Smart Search typically uses query parameters or form POST
        # Try form-based search first (ASP.NET pattern)
        form = soup.find("form")
        form_action = search_url  # default

        if form and form.get("action"):
            action = form["action"]
            if action.startswith("/"):
                # Build absolute URL from portal base
                from urllib.parse import urlparse
                parsed = urlparse(portal_url)
                form_action = f"{parsed.scheme}://{parsed.netloc}{action}"
            elif not action.startswith("http"):
                form_action = portal_url.rstrip("/") + "/" + action

        # Build search form data
        form_data = dict(hidden_fields)

        # Look for the name search input field
        name_input = soup.find("input", attrs={"type": "text"})
        if name_input:
            input_name = name_input.get("name", "")
            if input_name:
                form_data[input_name] = name

        # Look for a search/submit button
        submit_btn = soup.find("input", attrs={"type": "submit"})
        if submit_btn:
            btn_name = submit_btn.get("name", "")
            btn_value = submit_btn.get("value", "Search")
            if btn_name:
                form_data[btn_name] = btn_value

        # POST the search form
        search_resp = session.post(
            form_action,
            data=form_data,
            timeout=30,
            allow_redirects=True,
        )
        search_resp.raise_for_status()

        # Step 3: Parse results
        all_cases = _parse_search_results(search_resp.text)

        # Step 4: Handle pagination (follow additional pages up to MAX_RESULTS)
        page = 1
        while len(all_cases) < MAX_RESULTS_PER_NAME:
            next_url = _find_next_page_url(search_resp.text, portal_url)
            if not next_url:
                break
            page += 1
            time.sleep(1)  # Brief delay between pages
            search_resp = session.get(next_url, timeout=30)
            search_resp.raise_for_status()
            page_cases = _parse_search_results(search_resp.text)
            if not page_cases:
                break
            all_cases.extend(page_cases)

        return all_cases[:MAX_RESULTS_PER_NAME]

    except requests.RequestException as e:
        logger.error(f"Search failed for {name!r}: {e}")
        return []


def _parse_search_results(html: str) -> list[dict]:
    """Parse search results page HTML into case summary dicts.

    Tyler Odyssey case listings typically use a table or card layout with:
    - Case number (linked)
    - Case type / category
    - Filing date
    - Status
    - Parties (plaintiff v. defendant)

    Falls back to generic table parsing if the exact structure varies.
    """
    soup = BeautifulSoup(html, "html.parser")
    cases = []

    # Strategy 1: Look for case result cards/rows
    # Odyssey portals typically use specific CSS classes for results
    result_rows = soup.select(
        "tr.case-row, tr.search-result, tr.case-result, "
        ".caseSearchResults tr, "
        "div[class*='case-row'], div[class*='case-result'], "
        "div[class*='search-result']"
    )

    # Filter out non-data rows (headers, footers, pagination)
    result_rows = [
        r for r in result_rows
        if not r.find_parent(class_=re.compile(r'pag|head|foot|nav'))
        and r.find("a")  # Must have at least one link
    ]

    if result_rows:
        for row in result_rows:
            case = _parse_result_row(row)
            if case:
                cases.append(case)
        return cases

    # Strategy 2: Find data tables with case-like content
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # Check if headers look like case data
        header_row = rows[0]
        header_text = header_row.get_text(strip=True).lower()
        if any(kw in header_text for kw in ("case", "filed", "party", "status")):
            col_map = _build_case_column_map(
                [cell.get_text(strip=True).lower() for cell in header_row.find_all(["th", "td"])]
            )
            for row in rows[1:]:
                case = _parse_table_case_row(row, col_map)
                if case:
                    cases.append(case)
            if cases:
                return cases

    # Strategy 3: Look for links that look like case detail URLs
    # Odyssey case URLs typically contain case IDs
    case_links = soup.find_all("a", href=re.compile(
        r'(?:CaseDetail|case|docket)', re.IGNORECASE
    ))
    for link in case_links:
        href = link.get("href", "")
        text = link.get_text(strip=True)
        if text and href:
            case_number = text if re.match(r'^[A-Z0-9]+-', text) else ""
            cases.append({
                "case_number": case_number or text,
                "case_type": "",
                "filing_date": None,
                "case_status": "",
                "case_title": "",
                "detail_url": href,
            })

    # Check for "no results" messages
    no_results_patterns = [
        "no cases found", "no results", "no records found",
        "0 results", "no matching", "your search returned no",
    ]
    page_text = soup.get_text(strip=True).lower()
    for pattern in no_results_patterns:
        if pattern in page_text:
            return []

    return cases


def _parse_result_row(row) -> dict | None:
    """Parse a single result row/card into a case summary dict."""
    # Extract case number from first link
    link = row.find("a")
    if not link:
        return None

    case_number = ""
    detail_url = link.get("href", "")
    link_text = link.get_text(strip=True)

    # Case numbers typically match patterns like "C24-01234" or "MSC24-01234"
    if re.match(r'^[A-Z]{0,4}\d{2}-\d+', link_text):
        case_number = link_text
    else:
        case_number = link_text

    # Extract other fields from the row text
    cells = row.find_all(["td", "span", "div"])
    row_text = [cell.get_text(strip=True) for cell in cells if cell.get_text(strip=True)]

    # Try to identify fields by content patterns
    filing_date = None
    case_type = ""
    case_status = ""
    case_title = ""

    for text in row_text:
        if not text:
            continue
        # Date pattern
        if re.match(r'\d{1,2}/\d{1,2}/\d{4}', text) and not filing_date:
            filing_date = _parse_date(text)
        # Status keywords
        elif text.lower() in ("open", "closed", "disposed", "pending", "active"):
            case_status = text
        # Case type keywords
        elif text.lower() in ("civil", "small claims", "probate", "unlawful detainer",
                               "contract", "personal injury", "other civil"):
            case_type = text
        # Longer text might be case title (e.g., "Smith v. Jones")
        elif " v. " in text or " vs. " in text or " vs " in text:
            case_title = text

    return {
        "case_number": case_number,
        "case_type": case_type,
        "filing_date": filing_date,
        "case_status": case_status,
        "case_title": case_title,
        "detail_url": detail_url,
    }


def _build_case_column_map(headers: list[str]) -> dict[str, int]:
    """Map header text to field names by column index."""
    col_map: dict[str, int] = {}
    for i, h in enumerate(headers):
        if "case" in h and ("number" in h or "no" in h or "#" in h):
            col_map["case_number"] = i
        elif "type" in h or "category" in h:
            col_map["case_type"] = i
        elif "filed" in h or "date" in h:
            col_map["filing_date"] = i
        elif "status" in h or "disposition" in h:
            col_map["case_status"] = i
        elif "caption" in h or "title" in h or "party" in h or "parties" in h:
            col_map["case_title"] = i
    return col_map


def _parse_table_case_row(row, col_map: dict[str, int]) -> dict | None:
    """Parse a single table row into a case summary dict."""
    cells = row.find_all("td")
    if not cells or len(cells) < 2:
        return None

    def get_cell(field: str) -> str:
        idx = col_map.get(field)
        if idx is not None and idx < len(cells):
            return cells[idx].get_text(strip=True)
        return ""

    case_number = get_cell("case_number")
    if not case_number:
        return None

    # Extract detail URL from any link in the row
    detail_url = ""
    link = row.find("a")
    if link:
        detail_url = link.get("href", "")

    return {
        "case_number": case_number,
        "case_type": get_cell("case_type"),
        "filing_date": _parse_date(get_cell("filing_date")),
        "case_status": get_cell("case_status"),
        "case_title": get_cell("case_title"),
        "detail_url": detail_url,
    }


def _find_next_page_url(html: str, portal_url: str) -> str | None:
    """Find the URL for the next page of results, if any."""
    soup = BeautifulSoup(html, "html.parser")

    # Look for "Next" or ">" pagination links
    next_links = soup.find_all("a", string=re.compile(r'Next|›|»|>', re.IGNORECASE))
    for link in next_links:
        href = link.get("href", "")
        if href and href != "#":
            if href.startswith("http"):
                return href
            if href.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(portal_url)
                return f"{parsed.scheme}://{parsed.netloc}{href}"
    return None


# ── Case detail layer ────────────────────────────────────────

def fetch_case_detail(
    session: requests.Session,
    case_url: str,
    portal_url: str = "",
) -> dict | None:
    """Fetch full case details including all parties.

    Returns dict with keys:
      case_number, case_type, case_category, case_title, filing_date,
      case_status, disposition, disposition_date, court_name, judge,
      parties: list[{party_name, party_type, is_organization, attorney}],
      source_url
    """
    # Build absolute URL if relative
    if case_url.startswith("/"):
        from urllib.parse import urlparse
        parsed = urlparse(portal_url)
        case_url = f"{parsed.scheme}://{parsed.netloc}{case_url}"

    try:
        resp = session.get(case_url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch case detail {case_url}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    detail: dict[str, Any] = {
        "case_number": "",
        "case_type": "",
        "case_category": "",
        "case_title": "",
        "filing_date": None,
        "case_status": "",
        "disposition": "",
        "disposition_date": None,
        "court_name": "",
        "judge": "",
        "parties": [],
        "source_url": case_url,
    }

    # Extract case header information
    # Odyssey case detail pages typically show key fields as label/value pairs
    _extract_case_header(soup, detail)

    # Extract parties
    detail["parties"] = _parse_case_parties(soup)

    return detail


def _extract_case_header(soup: BeautifulSoup, detail: dict) -> None:
    """Extract case metadata from the detail page header section."""
    # Look for label/value pairs in definition lists, tables, or divs
    # Pattern 1: <dt>/<dd> pairs
    dts = soup.find_all("dt")
    for dt in dts:
        label = dt.get_text(strip=True).lower().rstrip(":")
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        value = dd.get_text(strip=True)
        _map_header_field(label, value, detail)

    # Pattern 2: <th>/<td> pairs in a details table
    for th in soup.find_all("th"):
        label = th.get_text(strip=True).lower().rstrip(":")
        td = th.find_next_sibling("td")
        if not td:
            continue
        value = td.get_text(strip=True)
        _map_header_field(label, value, detail)

    # Pattern 3: <label>/<span> or <label>/<div> pairs
    for lbl in soup.find_all("label"):
        label = lbl.get_text(strip=True).lower().rstrip(":")
        sibling = lbl.find_next_sibling(["span", "div"])
        if not sibling:
            continue
        value = sibling.get_text(strip=True)
        _map_header_field(label, value, detail)

    # Try to extract case title from page heading
    if not detail["case_title"]:
        h1 = soup.find(["h1", "h2", "h3"])
        if h1:
            title_text = h1.get_text(strip=True)
            # Case titles often contain "v." pattern
            if " v. " in title_text or " vs" in title_text.lower():
                detail["case_title"] = title_text


def _map_header_field(label: str, value: str, detail: dict) -> None:
    """Map a label/value pair to the detail dict."""
    if not value:
        return

    if "case number" in label or "case no" in label or label == "case #":
        detail["case_number"] = value
    elif label in ("case type", "type"):
        detail["case_type"] = value
    elif label in ("category", "case category"):
        detail["case_category"] = value
    elif "file" in label and "date" in label:
        detail["filing_date"] = _parse_date(value)
    elif label in ("status", "case status"):
        detail["case_status"] = value
    elif label in ("disposition", "disposed"):
        detail["disposition"] = value
    elif "disposition" in label and "date" in label:
        detail["disposition_date"] = _parse_date(value)
    elif label in ("court", "court name", "location"):
        detail["court_name"] = value
    elif label in ("judge", "judicial officer", "assigned judge"):
        detail["judge"] = value
    elif "caption" in label or "title" in label:
        detail["case_title"] = value


def _parse_case_parties(soup: BeautifulSoup) -> list[dict]:
    """Extract party information from case detail page.

    Returns list of dicts with: party_name, party_type, is_organization, attorney.
    """
    parties = []

    # Strategy 1: Look for a parties section/table
    parties_section = soup.find(
        ["div", "section", "table"],
        class_=re.compile(r'part(?:y|ies)', re.IGNORECASE)
    )
    if not parties_section:
        # Try heading-based detection
        for heading in soup.find_all(["h2", "h3", "h4"]):
            if "part" in heading.get_text(strip=True).lower():
                parties_section = heading.find_next(["table", "div", "ul"])
                break

    if parties_section:
        # If it's a table, parse rows
        if parties_section.name == "table":
            rows = parties_section.find_all("tr")
            for row in rows[1:] if len(rows) > 1 else rows:
                party = _parse_party_row(row)
                if party:
                    parties.append(party)
        else:
            # Look for name/type pairs in divs or list items
            items = parties_section.find_all(["li", "div", "tr"])
            for item in items:
                party = _parse_party_item(item)
                if party:
                    parties.append(party)

    # Strategy 2: Parse from case title ("Smith v. Jones")
    if not parties:
        page_text = soup.get_text()
        # Look for "Plaintiff" / "Defendant" labeled sections
        for match in re.finditer(
            r'(Plaintiff|Defendant|Petitioner|Respondent|Cross-Complainant)\s*[:\-]?\s*([^\n]+)',
            page_text, re.IGNORECASE
        ):
            party_type = match.group(1).lower()
            name = match.group(2).strip().rstrip(",;")
            if name and len(name) > 1:
                parties.append({
                    "party_name": name,
                    "party_type": party_type,
                    "is_organization": _detect_organization(name),
                    "attorney": "",
                })

    return parties


def _parse_party_row(row) -> dict | None:
    """Parse a table row as a party entry."""
    cells = row.find_all("td")
    if not cells:
        return None

    texts = [cell.get_text(strip=True) for cell in cells]
    texts = [t for t in texts if t]

    if not texts:
        return None

    # Heuristic: first text is name, type is nearby
    party_name = texts[0]
    party_type = ""
    attorney = ""

    for t in texts[1:]:
        lower = t.lower()
        if lower in ("plaintiff", "defendant", "petitioner", "respondent",
                      "cross-complainant", "cross-defendant", "intervenor"):
            party_type = lower
        elif "attorney" in lower or "counsel" in lower:
            attorney = t
        elif not party_type:
            # Could be party type
            party_type = t

    return {
        "party_name": party_name,
        "party_type": party_type,
        "is_organization": _detect_organization(party_name),
        "attorney": attorney,
    }


def _parse_party_item(item) -> dict | None:
    """Parse a div/li item as a party entry."""
    text = item.get_text(strip=True)
    if not text or len(text) < 2:
        return None

    # Try to split "Name - Type" or "Type: Name" patterns
    party_name = text
    party_type = ""

    # "Name (Plaintiff)" pattern
    paren_match = re.match(r'^(.+?)\s*\((\w+)\)\s*$', text)
    if paren_match:
        party_name = paren_match.group(1).strip()
        party_type = paren_match.group(2).lower()

    # "Plaintiff: Name" pattern
    colon_match = re.match(
        r'^(Plaintiff|Defendant|Petitioner|Respondent)\s*:\s*(.+)$',
        text, re.IGNORECASE
    )
    if colon_match:
        party_type = colon_match.group(1).lower()
        party_name = colon_match.group(2).strip()

    return {
        "party_name": party_name,
        "party_type": party_type,
        "is_organization": _detect_organization(party_name),
        "attorney": "",
    }


# ── Name list builder ────────────────────────────────────────

def build_search_list(
    conn,
    city_fips: str,
    include_officials: bool = True,
    include_donors: bool = True,
    include_form700_filers: bool = True,
    min_contribution_total: float = 5000.0,
    max_names: int = 50,
) -> list[dict]:
    """Build the list of names to search from Layer 2 tables.

    Queries:
      - officials (current first, then former)
      - donors (by total contributions DESC, above min threshold)
      - form700_filings (unique filer names not already in list)

    Returns list of dicts: {name, entity_type, entity_id, priority}
    Deduplicates by normalized name across sources.
    """
    names: list[dict] = []
    seen_normalized: set[str] = set()

    with conn.cursor() as cur:
        # 1. Officials (current first, then former)
        if include_officials:
            cur.execute(
                """SELECT id, name, is_current
                   FROM officials
                   WHERE city_fips = %s
                   ORDER BY is_current DESC, name""",
                (city_fips,),
            )
            for row in cur.fetchall():
                norm = _normalize_name(row[1])
                if norm and norm not in seen_normalized:
                    seen_normalized.add(norm)
                    names.append({
                        "name": row[1],
                        "entity_type": "official",
                        "entity_id": str(row[0]),
                        "priority": 1 if row[2] else 2,
                    })

        # 2. Top donors by contribution total
        if include_donors:
            cur.execute(
                """SELECT d.id, d.name, SUM(c.amount) as total
                   FROM donors d
                   JOIN contributions c ON c.donor_id = d.id
                   WHERE d.city_fips = %s
                   GROUP BY d.id, d.name
                   HAVING SUM(c.amount) >= %s
                   ORDER BY total DESC""",
                (city_fips, min_contribution_total),
            )
            for row in cur.fetchall():
                norm = _normalize_name(row[1])
                if norm and norm not in seen_normalized:
                    seen_normalized.add(norm)
                    names.append({
                        "name": row[1],
                        "entity_type": "donor",
                        "entity_id": str(row[0]),
                        "priority": 3,
                    })

        # 3. Form 700 filers not already in list
        if include_form700_filers:
            cur.execute(
                """SELECT DISTINCT filer_name
                   FROM form700_filings
                   WHERE city_fips = %s AND filer_name IS NOT NULL
                   ORDER BY filer_name""",
                (city_fips,),
            )
            for row in cur.fetchall():
                norm = _normalize_name(row[0])
                if norm and norm not in seen_normalized:
                    seen_normalized.add(norm)
                    names.append({
                        "name": row[0],
                        "entity_type": "form700_filer",
                        "entity_id": None,
                        "priority": 4,
                    })

    # Sort by priority and cap
    names.sort(key=lambda x: x["priority"])
    return names[:max_names]


# ── Database storage ─────────────────────────────────────────

def save_cases_to_db(
    conn,
    cases: list[dict],
    city_fips: str,
    county_fips: str,
) -> dict:
    """Save discovered cases and parties to Layer 2 tables.

    Upserts court_cases by (county_fips, case_number).
    Inserts court_case_parties.
    Returns stats: {cases_saved, cases_updated, parties_saved}.
    """
    stats = {"cases_saved": 0, "cases_updated": 0, "parties_saved": 0}

    with conn.cursor() as cur:
        for case in cases:
            case_number = (case.get("case_number") or "").strip()
            if not case_number:
                continue

            case_id = uuid.uuid4()

            # Upsert court_cases
            cur.execute(
                """INSERT INTO court_cases
                   (id, city_fips, county_fips, case_number, case_type,
                    case_category, case_title, filing_date, case_status,
                    disposition, disposition_date, court_name, judge,
                    source_url, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (county_fips, case_number)
                   DO UPDATE SET
                     case_type = COALESCE(EXCLUDED.case_type, court_cases.case_type),
                     case_category = COALESCE(EXCLUDED.case_category, court_cases.case_category),
                     case_title = COALESCE(EXCLUDED.case_title, court_cases.case_title),
                     case_status = COALESCE(EXCLUDED.case_status, court_cases.case_status),
                     disposition = COALESCE(EXCLUDED.disposition, court_cases.disposition),
                     disposition_date = COALESCE(EXCLUDED.disposition_date, court_cases.disposition_date),
                     judge = COALESCE(EXCLUDED.judge, court_cases.judge),
                     updated_at = NOW()
                   RETURNING id, (xmax = 0) AS is_insert""",
                (
                    case_id, city_fips, county_fips, case_number,
                    case.get("case_type"), case.get("case_category"),
                    case.get("case_title"), case.get("filing_date"),
                    case.get("case_status"), case.get("disposition"),
                    case.get("disposition_date"),
                    case.get("court_name", "Contra Costa County Superior Court"),
                    case.get("judge"), case.get("source_url"),
                    json.dumps(case.get("metadata", {})),
                ),
            )
            result = cur.fetchone()
            actual_case_id = result[0]
            is_insert = result[1]

            if is_insert:
                stats["cases_saved"] += 1
            else:
                stats["cases_updated"] += 1

            # Insert parties (delete existing first for clean refresh)
            parties = case.get("parties", [])
            if parties:
                cur.execute(
                    "DELETE FROM court_case_parties WHERE case_id = %s",
                    (actual_case_id,),
                )
                for party in parties:
                    party_name = (party.get("party_name") or "").strip()
                    if not party_name:
                        continue
                    cur.execute(
                        """INSERT INTO court_case_parties
                           (id, case_id, party_name, normalized_name,
                            party_type, is_organization, attorney, metadata)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (
                            uuid.uuid4(), actual_case_id,
                            party_name, _normalize_name(party_name),
                            party.get("party_type", "unknown"),
                            party.get("is_organization", False),
                            party.get("attorney", ""),
                            json.dumps(party.get("metadata", {})),
                        ),
                    )
                    stats["parties_saved"] += 1

    conn.commit()
    return stats


# ── Cross-reference matching ─────────────────────────────────

def cross_reference_parties(
    conn,
    city_fips: str,
) -> dict:
    """Match court case parties against known entities.

    For each unmatched party in court_case_parties:
      1. Normalize name
      2. Check officials table (exact, then fuzzy)
      3. Check donors table (exact, then fuzzy)
      4. Score confidence based on match_type

    Inserts matches into court_case_matches.
    Returns stats: {matches_found, by_type: {exact: N, contains: N, ...}}.
    """
    from conflict_scanner import normalize_text, names_match

    stats: dict[str, Any] = {
        "matches_found": 0,
        "by_type": {"exact": 0, "contains": 0, "fuzzy": 0, "last_name_only": 0},
    }

    with conn.cursor() as cur:
        # Get all unmatched parties from cases linked to this city
        cur.execute(
            """SELECT cp.id, cp.case_id, cp.party_name, cp.normalized_name
               FROM court_case_parties cp
               JOIN court_cases cc ON cp.case_id = cc.id
               LEFT JOIN court_case_matches cm ON cm.court_party_id = cp.id
               WHERE cc.city_fips = %s AND cm.id IS NULL""",
            (city_fips,),
        )
        unmatched = cur.fetchall()

        if not unmatched:
            return stats

        # Load all officials and donors for matching
        cur.execute(
            """SELECT id, name, normalized_name FROM officials WHERE city_fips = %s""",
            (city_fips,),
        )
        officials = cur.fetchall()

        cur.execute(
            """SELECT id, name, normalized_name FROM donors WHERE city_fips = %s""",
            (city_fips,),
        )
        donors = cur.fetchall()

        for party_id, case_id, party_name, party_norm in unmatched:
            best_match = None
            best_confidence = 0.0

            # Check against officials
            for off_id, off_name, off_norm in officials:
                is_match, match_type = names_match(party_name, off_name)
                if is_match:
                    confidence = {
                        "exact": CONFIDENCE_EXACT,
                        "contains": CONFIDENCE_CONTAINS,
                    }.get(match_type, CONFIDENCE_FUZZY)

                    if confidence > best_confidence:
                        best_match = {
                            "official_id": off_id,
                            "donor_id": None,
                            "entity_type": "official",
                            "entity_name": off_name,
                            "match_type": match_type,
                            "confidence": confidence,
                        }
                        best_confidence = confidence

            # Check against donors
            for don_id, don_name, don_norm in donors:
                is_match, match_type = names_match(party_name, don_name)
                if is_match:
                    confidence = {
                        "exact": CONFIDENCE_EXACT,
                        "contains": CONFIDENCE_CONTAINS,
                    }.get(match_type, CONFIDENCE_FUZZY)

                    if confidence > best_confidence:
                        best_match = {
                            "official_id": None,
                            "donor_id": don_id,
                            "entity_type": "donor",
                            "entity_name": don_name,
                            "match_type": match_type,
                            "confidence": confidence,
                        }
                        best_confidence = confidence

            # Last-name-only check (low confidence)
            if not best_match:
                party_words = party_norm.split()
                if party_words:
                    last_name = party_words[-1]
                    if len(last_name) >= 4:  # Skip very short last names
                        for off_id, off_name, off_norm in officials:
                            off_words = off_norm.split()
                            if off_words and off_words[-1] == last_name:
                                best_match = {
                                    "official_id": off_id,
                                    "donor_id": None,
                                    "entity_type": "official",
                                    "entity_name": off_name,
                                    "match_type": "last_name_only",
                                    "confidence": CONFIDENCE_LAST_NAME,
                                }
                                break

            # Save match
            if best_match:
                cur.execute(
                    """INSERT INTO court_case_matches
                       (id, city_fips, court_party_id, case_id,
                        official_id, donor_id, entity_type, entity_name,
                        match_type, confidence, metadata)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        uuid.uuid4(), city_fips, party_id, case_id,
                        best_match["official_id"], best_match["donor_id"],
                        best_match["entity_type"], best_match["entity_name"],
                        best_match["match_type"], best_match["confidence"],
                        json.dumps({}),
                    ),
                )
                stats["matches_found"] += 1
                stats["by_type"][best_match["match_type"]] = (
                    stats["by_type"].get(best_match["match_type"], 0) + 1
                )

    conn.commit()
    return stats


# ── Orchestration ────────────────────────────────────────────

def lookup_entities(
    city_fips: str | None = None,
    dry_run: bool = False,
    search_delay: float = DEFAULT_SEARCH_DELAY,
    case_delay: float = DEFAULT_CASE_DELAY,
    max_names: int = 50,
    verify_ssl: bool = True,
) -> dict:
    """Full orchestration: build name list, search portal, save, cross-reference.

    Steps:
      1. Build search list from DB
      2. For each name: search portal, fetch case details
      3. Save cases and parties to DB
      4. Run cross-reference matching
      5. Return summary stats
    """
    import psycopg2

    portal_url, search_path, county_fips, city_fips = _resolve_courts_config(city_fips)

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        # Step 1: Build search list
        search_list = build_search_list(conn, city_fips, max_names=max_names)
        print(f"\n  Court records lookup: {len(search_list)} names to search")

        if dry_run:
            print("\n  DRY RUN - would search for:")
            for i, entry in enumerate(search_list, 1):
                print(f"    {i:3d}. [{entry['entity_type']:15s}] {entry['name']}")
            return {
                "names_searched": 0,
                "dry_run": True,
                "search_list_size": len(search_list),
            }

        # Step 2-3: Search and save
        session = _create_session(verify_ssl=verify_ssl)
        total_cases = 0
        total_parties = 0
        errors = 0
        all_stats = {"cases_saved": 0, "cases_updated": 0, "parties_saved": 0}

        for i, entry in enumerate(search_list, 1):
            name = entry["name"]
            print(f"  [{i}/{len(search_list)}] Searching: {name}")

            try:
                # Search portal for this name
                cases = search_by_name(session, name, portal_url, search_path)
                print(f"    Found {len(cases)} case(s)")

                # Fetch case details for cases with detail URLs
                detailed_cases = []
                for case_summary in cases:
                    detail_url = case_summary.get("detail_url", "")
                    if detail_url:
                        time.sleep(case_delay)
                        detail = fetch_case_detail(session, detail_url, portal_url)
                        if detail:
                            detailed_cases.append(detail)
                        else:
                            # Use summary data as fallback
                            detailed_cases.append(case_summary)
                    else:
                        detailed_cases.append(case_summary)

                # Save to database
                if detailed_cases:
                    save_stats = save_cases_to_db(
                        conn, detailed_cases, city_fips, county_fips,
                    )
                    all_stats["cases_saved"] += save_stats["cases_saved"]
                    all_stats["cases_updated"] += save_stats["cases_updated"]
                    all_stats["parties_saved"] += save_stats["parties_saved"]
                    total_cases += len(detailed_cases)

            except Exception as e:
                logger.error(f"Error searching for {name!r}: {e}")
                errors += 1

            # Rate limit between name searches
            if i < len(search_list):
                time.sleep(search_delay)

        # Step 4: Cross-reference
        print("\n  Running cross-reference matching...")
        xref_stats = cross_reference_parties(conn, city_fips)

        result = {
            "names_searched": len(search_list),
            "total_cases_found": total_cases,
            "cases_saved": all_stats["cases_saved"],
            "cases_updated": all_stats["cases_updated"],
            "parties_saved": all_stats["parties_saved"],
            "matches_found": xref_stats["matches_found"],
            "match_types": xref_stats["by_type"],
            "errors": errors,
        }

        print(f"\n  Results:")
        print(f"    Names searched:  {result['names_searched']}")
        print(f"    Cases found:     {result['total_cases_found']}")
        print(f"    Cases saved:     {result['cases_saved']}")
        print(f"    Cases updated:   {result['cases_updated']}")
        print(f"    Parties saved:   {result['parties_saved']}")
        print(f"    Matches found:   {result['matches_found']}")
        if xref_stats["by_type"]:
            for mt, count in xref_stats["by_type"].items():
                if count > 0:
                    print(f"      {mt}: {count}")
        if errors:
            print(f"    Errors:          {errors}")

        return result

    finally:
        conn.close()


def get_stats(city_fips: str | None = None) -> dict:
    """Get summary statistics for court records data."""
    import psycopg2

    _, _, _, city_fips = _resolve_courts_config(city_fips)
    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    try:
        with conn.cursor() as cur:
            stats: dict[str, Any] = {}

            cur.execute(
                "SELECT COUNT(*) FROM court_cases WHERE city_fips = %s",
                (city_fips,),
            )
            stats["total_cases"] = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(*) FROM court_case_parties cp "
                "JOIN court_cases cc ON cp.case_id = cc.id "
                "WHERE cc.city_fips = %s",
                (city_fips,),
            )
            stats["total_parties"] = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(*) FROM court_case_matches WHERE city_fips = %s",
                (city_fips,),
            )
            stats["total_matches"] = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(*) FROM court_case_matches "
                "WHERE city_fips = %s AND reviewed = FALSE",
                (city_fips,),
            )
            stats["unreviewed_matches"] = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(*) FROM court_case_matches "
                "WHERE city_fips = %s AND false_positive = TRUE",
                (city_fips,),
            )
            stats["false_positives"] = cur.fetchone()[0]

            cur.execute(
                """SELECT entity_type, COUNT(*), AVG(confidence)
                   FROM court_case_matches
                   WHERE city_fips = %s AND (false_positive IS NOT TRUE)
                   GROUP BY entity_type""",
                (city_fips,),
            )
            stats["matches_by_type"] = {
                row[0]: {"count": row[1], "avg_confidence": float(row[2])}
                for row in cur.fetchall()
            }

            cur.execute(
                """SELECT case_type, COUNT(*)
                   FROM court_cases
                   WHERE city_fips = %s AND case_type IS NOT NULL
                   GROUP BY case_type ORDER BY COUNT(*) DESC""",
                (city_fips,),
            )
            stats["cases_by_type"] = {row[0]: row[1] for row in cur.fetchall()}

        return stats
    finally:
        conn.close()


# ── CLI ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Court records lookup (Tyler Odyssey)"
    )
    parser.add_argument(
        "--search-name",
        help="Search for a specific name",
    )
    parser.add_argument(
        "--search-all",
        action="store_true",
        help="Search for all officials/donors/filers",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show search list without querying portal",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show court records statistics",
    )
    parser.add_argument(
        "--city-fips",
        default=CITY_FIPS,
        help=f"City FIPS code (default: {CITY_FIPS})",
    )
    parser.add_argument(
        "--max-names",
        type=int,
        default=50,
        help="Maximum names to search (default: 50)",
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Disable SSL verification (for cert issues)",
    )
    parser.add_argument(
        "--search-delay",
        type=float,
        default=DEFAULT_SEARCH_DELAY,
        help=f"Seconds between name searches (default: {DEFAULT_SEARCH_DELAY})",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.stats:
        stats = get_stats(args.city_fips)
        print(f"\nCourt Records Stats (FIPS: {args.city_fips})")
        print(f"  Total cases:        {stats['total_cases']}")
        print(f"  Total parties:      {stats['total_parties']}")
        print(f"  Total matches:      {stats['total_matches']}")
        print(f"  Unreviewed:         {stats['unreviewed_matches']}")
        print(f"  False positives:    {stats['false_positives']}")
        if stats["matches_by_type"]:
            print(f"\n  Matches by entity type:")
            for etype, info in stats["matches_by_type"].items():
                print(f"    {etype}: {info['count']} (avg confidence: {info['avg_confidence']:.2f})")
        if stats["cases_by_type"]:
            print(f"\n  Cases by type:")
            for ctype, count in stats["cases_by_type"].items():
                print(f"    {ctype}: {count}")
        return

    if args.search_name:
        portal_url, search_path, county_fips, city_fips = _resolve_courts_config(
            args.city_fips
        )
        session = _create_session(verify_ssl=not args.no_verify_ssl)
        print(f"\nSearching for: {args.search_name}")
        cases = search_by_name(session, args.search_name, portal_url, search_path)
        print(f"Found {len(cases)} case(s):")
        for case in cases:
            print(f"  {case['case_number']:20s} {case.get('case_type', ''):15s} "
                  f"{case.get('filing_date') or 'N/A':12s} {case.get('case_status', '')}")
        return

    if args.search_all:
        result = lookup_entities(
            city_fips=args.city_fips,
            dry_run=args.dry_run,
            search_delay=args.search_delay,
            max_names=args.max_names,
            verify_ssl=not args.no_verify_ssl,
        )
        return

    parser.print_help()


if __name__ == "__main__":
    main()
