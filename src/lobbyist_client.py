"""Richmond Lobbyist Registration Client.

Fetches lobbyist registration records per Richmond Municipal Code Chapter 2.54
("Regulation of Lobbyists"). Three lobbyist types: Contract ($1K/month or
$3K/year or 10+ contacts), Business/Organization (compensated employees with
10+ contacts), and Expenditure ($3K+/year direct spending).

The *absence* of registration by vendor representatives who are influencing
procurement is itself a finding — this is one of S13's key transparency signals.

Data access strategy:
1. Download PDF registration lists from City Clerk Document Center (FID=389)
   via direct Document ID URLs (no JavaScript rendering needed)
2. Extract lobbyist-year grid from PDFs using Claude Vision API
3. Optionally cross-reference with CA Secretary of State lobbyist portal

The Document Center folder loads its file list via JavaScript, so HTML scraping
returns nothing. Direct PDF download by Document ID bypasses this entirely.

Tier 1 source (official government records).

Usage:
    from lobbyist_client import fetch_lobbyist_registrations
    registrations = fetch_lobbyist_registrations()
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)

DEFAULT_FIPS = "0660620"

# CivicPlus Document Center base URL for Richmond
DOCUMENT_CENTER_BASE = "https://www.ci.richmond.ca.us/DocumentCenter/View"

# Known PDF Document IDs containing lobbyist registration lists.
# These are stable CivicPlus identifiers — each new upload gets a new ID.
# Updated 2026-03-21: discovered via browser rendering of FID=389 folder.
RICHMOND_LOBBYIST_DOCS = {
    75427: {
        "title": "List of Registered Lobbyists from 2014-2025",
        "year_range": (2014, 2025),
        "uploaded": "2025-06-25",
    },
    27460: {
        "title": "List of Registered Lobbyists from 2000-2013",
        "year_range": (2000, 2013),
        "uploaded": "2013-08-12",
    },
}

# California Secretary of State lobbyist portal (state-level cross-reference)
CA_SOS_LOBBYIST_URL = "https://cal-access.sos.ca.gov/Lobbying/"
CA_SOS_LOBBYIST_SEARCH = "https://cal-access.sos.ca.gov/Lobbying/Employers/list.aspx"

REQUEST_TIMEOUT = 30
RETRY_COUNT = 3
RETRY_BACKOFF = 2.0

# Claude Vision extraction prompt
EXTRACTION_PROMPT = """You are extracting lobbyist registration data from a City of Richmond PDF.

This PDF contains a table/grid of lobbyist names and years they were registered.
Each row is a lobbyist (person or organization). Columns are years.
Checkmarks (✓ or similar marks/images) indicate the lobbyist was registered that year.

Extract ALL lobbyists from this page. For each, return:
- "name": The lobbyist's name exactly as shown (person name or organization name)
- "years": Array of integer years where a checkmark appears

Return ONLY a JSON array. No explanation, no markdown fences. Example:
[{"name": "Chevron U.S.A", "years": [2014, 2015, 2020]}, {"name": "John Smith", "years": [2018, 2019]}]

If the page has no lobbyist data (e.g., it's a header-only page or blank), return: []

IMPORTANT: Each row is ONE lobbyist. Names may span multiple lines. Do not merge
adjacent rows. Do not split one multi-line name into multiple entries."""


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
        "document_ids": list(RICHMOND_LOBBYIST_DOCS.keys()),
        "agency_name": "City of Richmond",
    }, DEFAULT_FIPS


def _make_request(url: str, *, timeout: int = REQUEST_TIMEOUT) -> requests.Response:
    """Make HTTP GET request with retry logic."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Richmond Common Transparency Project)",
        "Accept": "text/html, application/pdf, application/json",
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


def _normalize_name(name: str) -> str:
    """Normalize a person/org name."""
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.strip())


# ── PDF Download + Vision Extraction ──────────────────────────


def download_lobbyist_pdf(doc_id: int) -> bytes:
    """Download a lobbyist registration PDF by CivicPlus Document ID.

    Args:
        doc_id: CivicPlus Document Center document ID.

    Returns:
        Raw PDF bytes.

    Raises:
        requests.RequestException: If download fails after retries.
    """
    url = f"{DOCUMENT_CENTER_BASE}/{doc_id}"
    logger.info("Downloading lobbyist PDF: doc_id=%d from %s", doc_id, url)
    resp = _make_request(url, timeout=60)

    if not resp.content[:5] == b"%PDF-":
        raise ValueError(f"Document {doc_id} is not a PDF (got {resp.headers.get('content-type', 'unknown')})")

    logger.info("Downloaded %d bytes for doc_id=%d", len(resp.content), doc_id)
    return resp.content


def extract_lobbyists_from_pdf(
    pdf_bytes: bytes,
    doc_id: int,
    *,
    model: str = "claude-sonnet-4-20250514",
) -> list[dict]:
    """Extract lobbyist registration data from a PDF using Claude Vision API.

    Sends the PDF as a base64-encoded document to Claude, which reads the
    checkmark grid and returns structured JSON.

    Args:
        pdf_bytes: Raw PDF file content.
        doc_id: Document ID (for logging/source tracking).
        model: Claude model to use for extraction.

    Returns:
        List of {"name": str, "years": list[int]} dicts.
    """
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set — cannot extract lobbyist PDF")
        return []

    client = anthropic.Anthropic(api_key=api_key)
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    logger.info("Sending doc_id=%d to Claude Vision for extraction...", doc_id)

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    )

    response_text = message.content[0].text
    logger.info(
        "Vision extraction for doc_id=%d: %d input tokens, %d output tokens",
        doc_id, message.usage.input_tokens, message.usage.output_tokens,
    )

    return _parse_vision_response(response_text, doc_id)


def _parse_vision_response(response_text: str, doc_id: int) -> list[dict]:
    """Parse Claude Vision response into lobbyist records.

    Args:
        response_text: Raw text response from Claude.
        doc_id: Document ID for error context.

    Returns:
        List of {"name": str, "years": list[int]} dicts.
    """
    text = response_text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Vision response for doc_id=%d: %s", doc_id, e)
        logger.debug("Raw response: %s", response_text[:500])
        return []

    if not isinstance(data, list):
        logger.error("Vision response for doc_id=%d is not a list: %s", doc_id, type(data))
        return []

    results = []
    for item in data:
        name = _normalize_name(item.get("name", ""))
        years = item.get("years", [])
        if not name:
            continue
        if not isinstance(years, list):
            continue
        # Filter to valid year integers
        valid_years = [y for y in years if isinstance(y, int) and 1990 <= y <= 2050]
        if valid_years:
            results.append({"name": name, "years": sorted(valid_years)})

    logger.info("Parsed %d lobbyist entities from doc_id=%d", len(results), doc_id)
    return results


def _vision_records_to_registrations(
    records: list[dict],
    doc_id: int,
    source_url: str,
) -> list[dict]:
    """Convert Vision extraction records to registration dicts for DB loader.

    Each Vision record is {"name": str, "years": [int, ...]}.
    We produce one registration dict per lobbyist (not per year).
    Years go into metadata; earliest year becomes registration_date.

    Args:
        records: Output from extract_lobbyists_from_pdf() or _parse_vision_response().
        doc_id: Document ID for source tracking.
        source_url: Full URL of the source PDF.

    Returns:
        List of registration dicts compatible with load_lobbyists_to_db().
    """
    current_year = datetime.now().year
    registrations = []

    for record in records:
        name = record["name"]
        years = record["years"]
        earliest = min(years)
        latest = max(years)
        is_current = current_year in years

        registrations.append({
            "lobbyist_name": name,
            "lobbyist_firm": None,
            "client_name": "See registration filing",
            "registration_date": f"{earliest}-01-01",
            "expiration_date": f"{latest}-12-31" if not is_current else None,
            "topics": None,
            "city_agencies": None,
            "lobbyist_address": None,
            "lobbyist_phone": None,
            "lobbyist_email": None,
            "status": "active" if is_current else "expired",
            "source": "city_clerk",
            "source_identifier": f"doc_{doc_id}_{name}",
            "source_url": source_url,
            "metadata": {
                "source_method": "pdf_vision_extraction",
                "document_id": doc_id,
                "years_registered": years,
                "earliest_year": earliest,
                "latest_year": latest,
            },
        })

    return registrations


def fetch_lobbyist_registrations_pdf(
    *,
    city_fips: str | None = None,
) -> list[dict]:
    """Fetch lobbyist registrations by downloading and extracting PDF lists.

    Downloads known registration list PDFs from the City Clerk Document Center
    and extracts structured data using Claude Vision API.

    Returns:
        List of normalized registration dicts.
    """
    config, fips = _resolve_config(city_fips)
    doc_ids = config.get("document_ids", list(RICHMOND_LOBBYIST_DOCS.keys()))

    all_registrations = []

    for doc_id in doc_ids:
        doc_meta = RICHMOND_LOBBYIST_DOCS.get(doc_id, {})
        source_url = f"{DOCUMENT_CENTER_BASE}/{doc_id}"

        try:
            pdf_bytes = download_lobbyist_pdf(doc_id)
        except (requests.RequestException, ValueError) as e:
            logger.warning("Failed to download doc_id=%d: %s", doc_id, e)
            continue

        records = extract_lobbyists_from_pdf(pdf_bytes, doc_id)
        if not records:
            logger.warning("No lobbyist data extracted from doc_id=%d (%s)",
                           doc_id, doc_meta.get("title", "unknown"))
            continue

        registrations = _vision_records_to_registrations(records, doc_id, source_url)
        logger.info(
            "Extracted %d registrations from doc_id=%d (%s)",
            len(registrations), doc_id, doc_meta.get("title", "unknown"),
        )
        all_registrations.extend(registrations)

    return all_registrations


# ── CA Secretary of State (State-Level Cross-Reference) ───────


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

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if not cells:
                continue
            row_text = " ".join(cells).lower()
            if "richmond" not in row_text:
                continue

            link = row.find("a", href=True)
            detail_url = link["href"] if link else None
            if detail_url and not detail_url.startswith("http"):
                detail_url = f"https://cal-access.sos.ca.gov{detail_url}"

            results.append({
                "lobbyist_name": cells[0] if cells else "Unknown",
                "lobbyist_firm": None,
                "client_name": cells[1] if len(cells) > 1 else "Unknown",
                "registration_date": None,
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


# ── Main Entry Point ──────────────────────────────────────────


def fetch_lobbyist_registrations(
    *,
    city_fips: str | None = None,
    include_state: bool = True,
) -> list[dict]:
    """Fetch all lobbyist registrations for a city.

    Combines local City Clerk PDF data with optional state-level cross-reference.

    Args:
        city_fips: FIPS code (default: Richmond CA).
        include_state: Also search CA SOS lobbyist portal.

    Returns:
        List of normalized registration dicts ready for load_lobbyists_to_db().
    """
    config, fips = _resolve_config(city_fips)

    # Primary: City Clerk PDF registration lists
    registrations = fetch_lobbyist_registrations_pdf(city_fips=city_fips)

    # Secondary: CA Secretary of State (state-level lobbyists)
    if include_state:
        state_records = fetch_ca_sos_lobbyists(
            employer_name=config.get("agency_name", "City of Richmond"),
        )
        for record in state_records:
            record["source"] = "ca_sos_lobbying"
        registrations.extend(state_records)

    # Deduplicate by source_identifier
    seen: set[str] = set()
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
        years = (r.get("metadata") or {}).get("years_registered", [])
        status = r.get("status", "unknown")
        years_str = f" ({', '.join(str(y) for y in years)})" if years else ""
        print(f"  [{status}] {r['lobbyist_name']}{years_str}")
        if r.get("lobbyist_firm"):
            print(f"    Firm: {r['lobbyist_firm']}")
        if r.get("client_name") and r["client_name"] != "See registration filing":
            print(f"    Client: {r['client_name']}")
