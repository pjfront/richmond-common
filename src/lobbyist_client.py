"""Richmond Lobbyist Registration Client.

Fetches lobbyist registration records per Richmond Municipal Code Chapter 2.38.
Lobbyists who communicate with city officials to influence government decisions
must register with the City Clerk.

The *absence* of registration by vendor representatives who are influencing
procurement is itself a finding — this is one of S13's key transparency signals.

Data access strategy (in priority order):
1. City Clerk website / lobbyist registry page (HTML scraping)
2. Socrata open data portal (if published as a dataset)
3. CPRA request results (if obtained via NextRequest)
4. California Secretary of State lobbyist portal (state-level, cross-reference)

Tier 1 source (official government records).

Usage:
    from lobbyist_client import fetch_lobbyist_registrations
    registrations = fetch_lobbyist_registrations()
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)

DEFAULT_FIPS = "0660620"

# Richmond City Clerk lobbyist registry
# The City Clerk maintains a list of registered lobbyists per Municipal Code 2.38
RICHMOND_LOBBYIST_URLS = [
    "https://www.ci.richmond.ca.us/1604/Lobbyist-Registration",
    "https://www.ci.richmond.ca.us/2066/Lobbyist-Information",
    "https://www.ci.richmond.ca.us/lobbying",
]

# California Secretary of State lobbyist portal (state-level cross-reference)
CA_SOS_LOBBYIST_URL = "https://cal-access.sos.ca.gov/Lobbying/"
CA_SOS_LOBBYIST_SEARCH = "https://cal-access.sos.ca.gov/Lobbying/Employers/list.aspx"

REQUEST_TIMEOUT = 30
RETRY_COUNT = 3
RETRY_BACKOFF = 2.0


def _resolve_config(city_fips: str | None = None) -> tuple[dict, str]:
    """Resolve lobbyist config from city registry or use defaults."""
    if city_fips is not None:
        from city_config import get_data_source_config

        try:
            cfg = get_data_source_config(city_fips, "lobbyist_registrations")
            return cfg, city_fips
        except Exception:
            pass
    return {
        "platform": "City Clerk",
        "registry_urls": RICHMOND_LOBBYIST_URLS,
        "agency_name": "City of Richmond",
    }, DEFAULT_FIPS


def _make_request(url: str, *, timeout: int = REQUEST_TIMEOUT) -> requests.Response:
    """Make HTTP GET request with retry logic."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Richmond Common Transparency Project)",
        "Accept": "text/html, application/json",
    }

    for attempt in range(RETRY_COUNT):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt < RETRY_COUNT - 1:
                wait = RETRY_BACKOFF ** (attempt + 1)
                logger.warning(
                    "Request to %s failed (attempt %d/%d): %s. Retrying in %.1fs...",
                    url, attempt + 1, RETRY_COUNT, e, wait,
                )
                time.sleep(wait)
            else:
                raise


def _parse_date(date_str: str | None) -> str | None:
    """Parse various date formats into YYYY-MM-DD."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _normalize_name(name: str) -> str:
    """Normalize a person/org name."""
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.strip())


def fetch_lobbyist_registrations_html(
    *,
    city_fips: str | None = None,
) -> list[dict]:
    """Scrape lobbyist registrations from City Clerk website.

    Tries multiple known URLs for the Richmond lobbyist registry page.
    Parses HTML tables or structured lists.

    Returns:
        List of normalized registration dicts.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("beautifulsoup4 required. Install with: pip install beautifulsoup4")
        return []

    config, fips = _resolve_config(city_fips)
    urls = config.get("registry_urls", RICHMOND_LOBBYIST_URLS)

    for url in urls:
        try:
            resp = _make_request(url)
        except requests.RequestException:
            logger.warning("Failed to fetch %s, trying next URL...", url)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        registrations = _parse_lobbyist_page(soup, url)

        if registrations:
            logger.info(
                "Found %d lobbyist registrations from %s", len(registrations), url,
            )
            return registrations

    logger.warning("No lobbyist registrations found from any URL")
    return []


def _parse_lobbyist_page(soup, source_url: str) -> list[dict]:
    """Parse lobbyist data from a CivicPlus/Richmond HTML page.

    Handles multiple page structures:
    1. HTML table with columns (lobbyist, client, date, etc.)
    2. Document links (PDFs of registration forms)
    3. Structured list elements
    """
    results = []

    # Strategy 1: Look for data tables
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        # Check if this looks like a lobbyist table
        lobbyist_headers = {"lobbyist", "client", "firm", "name", "employer", "registration"}
        if any(h in " ".join(headers) for h in lobbyist_headers):
            for row in table.find_all("tr")[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) < 2:
                    continue
                record = dict(zip(headers, cells))
                registration = _normalize_table_record(record, source_url)
                if registration:
                    results.append(registration)
            if results:
                return results

    # Strategy 2: Look for document links (PDFs of registration forms)
    pdf_links = soup.find_all("a", href=re.compile(r"\.pdf|DocumentCenter|Archive\.aspx", re.I))
    lobbyist_links = [
        link for link in pdf_links
        if re.search(r"lobbyist|registration|lobby", link.get_text(strip=True), re.I)
    ]
    for link in lobbyist_links:
        href = link.get("href", "")
        if not href.startswith("http"):
            href = f"https://www.ci.richmond.ca.us{href}"
        text = link.get_text(strip=True)
        # Extract what we can from the link text
        results.append({
            "lobbyist_name": text,
            "lobbyist_firm": None,
            "client_name": "See registration document",
            "registration_date": None,
            "expiration_date": None,
            "topics": None,
            "city_agencies": None,
            "lobbyist_address": None,
            "lobbyist_phone": None,
            "lobbyist_email": None,
            "status": "active",
            "source_identifier": f"pdf_{href}",
            "source_url": href,
            "metadata": {"source_method": "pdf_link", "link_text": text},
        })

    # Strategy 3: Look for structured content (div-based layouts)
    if not results:
        content = soup.find("div", class_=re.compile(r"content|widget|body", re.I))
        if content:
            # Look for patterns like "Name: John Doe" or "Client: Acme Corp"
            text = content.get_text()
            # Split on common section markers
            sections = re.split(r"\n(?=(?:Lobbyist|Name|Firm|Client):)", text)
            for section in sections:
                if len(section.strip()) < 10:
                    continue
                registration = _parse_text_section(section, source_url)
                if registration:
                    results.append(registration)

    return results


def _normalize_table_record(record: dict, source_url: str) -> dict | None:
    """Normalize a table row into standard registration dict."""
    name = _normalize_name(
        record.get("lobbyist", "") or record.get("name", "") or ""
    )
    client = _normalize_name(
        record.get("client", "") or record.get("employer", "") or ""
    )
    if not name:
        return None

    return {
        "lobbyist_name": name,
        "lobbyist_firm": _normalize_name(record.get("firm", "") or "").strip() or None,
        "client_name": client or "Unknown",
        "registration_date": _parse_date(
            record.get("registration date", "") or record.get("date", "")
        ),
        "expiration_date": _parse_date(
            record.get("expiration", "") or record.get("expiration date", "")
        ),
        "topics": (record.get("topics", "") or record.get("subject", "")).strip() or None,
        "city_agencies": (record.get("agencies", "") or record.get("department", "")).strip() or None,
        "lobbyist_address": (record.get("address", "")).strip() or None,
        "lobbyist_phone": (record.get("phone", "")).strip() or None,
        "lobbyist_email": (record.get("email", "")).strip() or None,
        "status": (record.get("status", "active")).strip(),
        "source_identifier": f"table_{name}_{client}",
        "source_url": source_url,
        "metadata": {"source_method": "html_table", "raw_record": record},
    }


def _parse_text_section(text: str, source_url: str) -> dict | None:
    """Extract lobbyist info from a free-text section."""
    fields = {}
    for pattern, key in [
        (r"(?:Lobbyist|Name)\s*:\s*(.+?)(?:\n|$)", "lobbyist_name"),
        (r"(?:Client|Employer)\s*:\s*(.+?)(?:\n|$)", "client_name"),
        (r"Firm\s*:\s*(.+?)(?:\n|$)", "lobbyist_firm"),
        (r"(?:Registration\s*)?Date\s*:\s*(.+?)(?:\n|$)", "registration_date"),
        (r"Topic[s]?\s*:\s*(.+?)(?:\n|$)", "topics"),
        (r"(?:Phone|Tel)\s*:\s*(.+?)(?:\n|$)", "lobbyist_phone"),
        (r"Email\s*:\s*(.+?)(?:\n|$)", "lobbyist_email"),
        (r"Address\s*:\s*(.+?)(?:\n|$)", "lobbyist_address"),
    ]:
        m = re.search(pattern, text, re.I)
        if m:
            fields[key] = m.group(1).strip()

    name = _normalize_name(fields.get("lobbyist_name", ""))
    if not name:
        return None

    client = _normalize_name(fields.get("client_name", ""))

    return {
        "lobbyist_name": name,
        "lobbyist_firm": fields.get("lobbyist_firm"),
        "client_name": client or "Unknown",
        "registration_date": _parse_date(fields.get("registration_date")),
        "expiration_date": None,
        "topics": fields.get("topics"),
        "city_agencies": None,
        "lobbyist_address": fields.get("lobbyist_address"),
        "lobbyist_phone": fields.get("lobbyist_phone"),
        "lobbyist_email": fields.get("lobbyist_email"),
        "status": "active",
        "source_identifier": f"text_{name}_{client}",
        "source_url": source_url,
        "metadata": {"source_method": "text_parse"},
    }


def fetch_ca_sos_lobbyists(
    *,
    employer_name: str = "City of Richmond",
) -> list[dict]:
    """Fetch lobbyist registrations from CA Secretary of State.

    State-level lobbyist data cross-references with local registrations.
    State lobbyists are registered under the Political Reform Act (Gov Code
    §82039), separate from local ordinances.

    This is supplementary data — the primary source is the City Clerk.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("beautifulsoup4 required")
        return []

    try:
        resp = _make_request(
            CA_SOS_LOBBYIST_SEARCH,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.warning("CA SOS lobbyist search failed: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    # The SOS portal lists lobbying employers and their lobbyists
    # We search for employers that match Richmond-related entities
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if not cells:
                continue
            # Check if any cell mentions Richmond
            row_text = " ".join(cells).lower()
            if "richmond" not in row_text:
                continue

            # Found a Richmond-related entry
            link = row.find("a", href=True)
            detail_url = link["href"] if link else None
            if detail_url and not detail_url.startswith("http"):
                detail_url = f"https://cal-access.sos.ca.gov{detail_url}"

            results.append({
                "lobbyist_name": cells[0] if cells else "Unknown",
                "lobbyist_firm": None,
                "client_name": cells[1] if len(cells) > 1 else "Unknown",
                "registration_date": _parse_date(cells[2] if len(cells) > 2 else None),
                "expiration_date": None,
                "topics": None,
                "city_agencies": None,
                "lobbyist_address": None,
                "lobbyist_phone": None,
                "lobbyist_email": None,
                "status": "active",
                "source_identifier": f"ca_sos_{cells[0]}_{cells[1] if len(cells) > 1 else ''}",
                "source_url": detail_url,
                "metadata": {"source_method": "ca_sos_search", "raw_cells": cells},
            })

    logger.info("CA SOS returned %d Richmond-related lobbyist records", len(results))
    return results


def fetch_lobbyist_registrations(
    *,
    city_fips: str | None = None,
    include_state: bool = True,
) -> list[dict]:
    """Fetch all lobbyist registrations for a city.

    Combines local City Clerk data with optional state-level cross-reference.

    Args:
        city_fips: FIPS code (default: Richmond CA).
        include_state: Also search CA SOS lobbyist portal.

    Returns:
        List of normalized registration dicts ready for load_lobbyists_to_db().
    """
    config, fips = _resolve_config(city_fips)

    # Primary: City Clerk local registry
    registrations = fetch_lobbyist_registrations_html(city_fips=city_fips)

    # Secondary: CA Secretary of State (state-level lobbyists)
    if include_state:
        state_records = fetch_ca_sos_lobbyists(
            employer_name=config.get("agency_name", "City of Richmond"),
        )
        for record in state_records:
            record["source"] = "ca_sos_lobbying"
        registrations.extend(state_records)

    # Deduplicate by source_identifier
    seen = set()
    unique = []
    for r in registrations:
        key = r.get("source_identifier", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(r)

    logger.info(
        "Total lobbyist registrations for FIPS %s: %d (after dedup from %d)",
        fips, len(unique), len(registrations),
    )
    return unique


# ── CLI ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch lobbyist registrations")
    parser.add_argument("--city-fips", default=DEFAULT_FIPS, help="FIPS code")
    parser.add_argument("--no-state", action="store_true", help="Skip CA SOS search")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    records = fetch_lobbyist_registrations(
        city_fips=args.city_fips,
        include_state=not args.no_state,
    )

    print(f"\nFound {len(records)} lobbyist registration(s):")
    for r in records:
        print(f"  {r['lobbyist_name']} → {r['client_name']}")
        if r.get("lobbyist_firm"):
            print(f"    Firm: {r['lobbyist_firm']}")
        if r.get("topics"):
            print(f"    Topics: {r['topics']}")
        if r.get("registration_date"):
            print(f"    Registered: {r['registration_date']}")
