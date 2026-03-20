"""FPPC Form 803 (Behested Payments) Client.

Fetches behested payment disclosures from the FPPC's public search portal.
Behested payments (CA Gov Code §82015) are payments made at the request of
elected officials to third parties. Officials must file Form 803 with the
FPPC within 30 days.

Data source: FPPC eFiling portal (form803.fppc.ca.gov) or the search interface
at cal-access.sos.ca.gov. Tier 1 source (official government filings).

Usage:
    from fppc_form803_client import fetch_behested_payments
    payments = fetch_behested_payments(official_name="Eduardo Martinez")
    payments = fetch_behested_payments(agency_name="City of Richmond")
"""

from __future__ import annotations

import json
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

# FPPC Behested Payments search endpoints
# The FPPC provides a public search interface for Form 803 filings.
# Primary: https://www.fppc.ca.gov/transparency/behested-payments.html
# Search API: Powers the public search page
FPPC_BEHESTED_SEARCH_URL = "https://fppc.ca.gov/api/behested-payments/search"
FPPC_BEHESTED_DETAIL_URL = "https://fppc.ca.gov/api/behested-payments/{filing_id}"
# Fallback: FPPC form search page (structured HTML scraping)
FPPC_FORM_SEARCH_URL = "https://www.fppc.ca.gov/transparency/behested-payments.html"

# Known Richmond, California official name variants for matching
RICHMOND_AGENCY_NAMES = [
    "City of Richmond",
    "Richmond",
    "Richmond City Council",
]

# Request settings
REQUEST_TIMEOUT = 30
RETRY_COUNT = 3
RETRY_BACKOFF = 2.0


def _resolve_config(city_fips: str | None = None) -> tuple[dict, str]:
    """Resolve Form 803 config from city registry or use defaults.

    Returns:
        Tuple of (config dict, fips code).
    """
    if city_fips is not None:
        from city_config import get_data_source_config

        try:
            cfg = get_data_source_config(city_fips, "form803_behested")
            return cfg, city_fips
        except Exception:
            pass
    return {
        "agency_name": "City of Richmond",
        "agency_names": RICHMOND_AGENCY_NAMES,
    }, DEFAULT_FIPS


def _make_request(
    url: str,
    *,
    method: str = "GET",
    params: dict | None = None,
    json_body: dict | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> requests.Response:
    """Make HTTP request with retry logic."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Richmond Common Transparency Project)",
        "Accept": "application/json, text/html",
    }

    for attempt in range(RETRY_COUNT):
        try:
            if method == "POST":
                resp = requests.post(
                    url, headers=headers, json=json_body, params=params, timeout=timeout,
                )
            else:
                resp = requests.get(
                    url, headers=headers, params=params, timeout=timeout,
                )
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
    logger.warning("Could not parse date: %s", date_str)
    return None


def _normalize_name(name: str) -> str:
    """Normalize a person/org name for matching."""
    if not name:
        return ""
    # Strip whitespace, collapse multiple spaces
    name = re.sub(r"\s+", " ", name.strip())
    return name


def fetch_behested_payments_api(
    *,
    agency_name: str | None = None,
    official_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Fetch behested payments from FPPC API search endpoint.

    Args:
        agency_name: Filter by agency (e.g., "City of Richmond").
        official_name: Filter by official name.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).

    Returns:
        List of normalized payment dicts.
    """
    params = {}
    if agency_name:
        params["agency"] = agency_name
    if official_name:
        params["filerName"] = official_name
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date

    try:
        resp = _make_request(FPPC_BEHESTED_SEARCH_URL, params=params)
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        logger.warning("FPPC API search failed: %s. Falling back to HTML scrape.", e)
        return []

    results = []
    items = data if isinstance(data, list) else data.get("results", data.get("items", []))

    for item in items:
        payment = _normalize_api_record(item)
        if payment:
            results.append(payment)

    logger.info("FPPC API returned %d behested payment records", len(results))
    return results


def _normalize_api_record(item: dict) -> dict | None:
    """Normalize a single API result into our standard schema."""
    official_name = _normalize_name(
        item.get("filerName", "") or item.get("officialName", "") or ""
    )
    if not official_name:
        return None

    payor_name = _normalize_name(
        item.get("payorName", "") or item.get("sourceOfPayment", "") or ""
    )
    payee_name = _normalize_name(
        item.get("payeeName", "") or item.get("payeeOrganization", "") or ""
    )

    if not payor_name and not payee_name:
        return None

    amount = None
    raw_amount = item.get("amount") or item.get("paymentAmount")
    if raw_amount is not None:
        try:
            amount = float(str(raw_amount).replace(",", "").replace("$", ""))
        except (ValueError, TypeError):
            pass

    filing_id = str(item.get("filingId", "") or item.get("id", "") or "")

    return {
        "official_name": official_name,
        "payor_name": payor_name,
        "payor_city": (item.get("payorCity") or "").strip() or None,
        "payor_state": (item.get("payorState") or "").strip() or None,
        "payee_name": payee_name,
        "payee_description": (item.get("payeeDescription") or "").strip() or None,
        "amount": amount,
        "payment_date": _parse_date(item.get("paymentDate") or item.get("dateOfPayment")),
        "filing_date": _parse_date(item.get("filingDate") or item.get("dateFiled")),
        "description": (item.get("description") or item.get("purpose") or "").strip() or None,
        "filing_id": filing_id or None,
        "source_identifier": filing_id or f"{official_name}_{payor_name}_{payee_name}_{amount}",
        "source_url": item.get("url") or item.get("sourceUrl") or None,
        "metadata": {
            k: v for k, v in {
                "agency": item.get("agency") or item.get("agencyName"),
                "position": item.get("position") or item.get("officialPosition"),
                "form_type": item.get("formType", "803"),
                "raw_record": {
                    k: v for k, v in item.items()
                    if k not in (
                        "filerName", "officialName", "payorName", "sourceOfPayment",
                        "payeeName", "payeeOrganization", "amount", "paymentAmount",
                    )
                },
            }.items()
            if v
        },
    }


def fetch_behested_payments_html(
    *,
    agency_name: str = "City of Richmond",
) -> list[dict]:
    """Scrape behested payments from FPPC HTML search page.

    Fallback when the API endpoint isn't available. Parses the public
    search results page.

    Args:
        agency_name: Agency name to search for.

    Returns:
        List of normalized payment dicts.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("beautifulsoup4 required for HTML scraping. Install with: pip install beautifulsoup4")
        return []

    try:
        resp = _make_request(
            FPPC_FORM_SEARCH_URL,
            params={"agency": agency_name},
        )
    except requests.RequestException as e:
        logger.error("FPPC HTML scrape failed: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    # Parse table rows from search results
    table = soup.find("table", class_=re.compile(r"behested|results|data", re.I))
    if not table:
        # Try any table with relevant headers
        for t in soup.find_all("table"):
            headers = [th.get_text(strip=True).lower() for th in t.find_all("th")]
            if any(h in headers for h in ("official", "payor", "payee", "amount")):
                table = t
                break

    if not table:
        logger.warning("No behested payments table found in FPPC HTML response")
        return []

    headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
    for row in table.find_all("tr")[1:]:  # skip header row
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if len(cells) < len(headers):
            continue

        record = dict(zip(headers, cells))

        # Extract link from row if present
        link = row.find("a", href=True)
        source_url = link["href"] if link else None
        if source_url and not source_url.startswith("http"):
            source_url = f"https://www.fppc.ca.gov{source_url}"

        official = _normalize_name(
            record.get("official", "") or record.get("filer", "") or ""
        )
        payor = _normalize_name(
            record.get("payor", "") or record.get("source of payment", "") or ""
        )
        payee = _normalize_name(
            record.get("payee", "") or record.get("payee organization", "") or ""
        )

        if not official:
            continue

        amount = None
        raw_amt = record.get("amount", "")
        if raw_amt:
            try:
                amount = float(raw_amt.replace(",", "").replace("$", ""))
            except ValueError:
                pass

        payment = {
            "official_name": official,
            "payor_name": payor or "Unknown",
            "payor_city": None,
            "payor_state": None,
            "payee_name": payee or "Unknown",
            "payee_description": None,
            "amount": amount,
            "payment_date": _parse_date(record.get("date", "") or record.get("payment date", "")),
            "filing_date": _parse_date(record.get("filing date", "") or record.get("date filed", "")),
            "description": record.get("description") or record.get("purpose"),
            "filing_id": None,
            "source_identifier": f"html_{official}_{payor}_{payee}_{amount}",
            "source_url": source_url,
            "metadata": {"source_method": "html_scrape", "raw_record": record},
        }
        results.append(payment)

    logger.info("FPPC HTML scrape returned %d behested payment records", len(results))
    return results


def fetch_behested_payments(
    *,
    city_fips: str | None = None,
    official_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Fetch behested payments for a city's officials.

    Tries API first, falls back to HTML scraping. Filters results
    to match the city's known officials.

    Args:
        city_fips: FIPS code (default: Richmond CA).
        official_name: Specific official to search for.
        start_date: Start date filter (YYYY-MM-DD).
        end_date: End date filter (YYYY-MM-DD).

    Returns:
        List of normalized payment dicts ready for load_behested_to_db().
    """
    config, fips = _resolve_config(city_fips)
    agency_name = config.get("agency_name", "City of Richmond")
    agency_names = config.get("agency_names", RICHMOND_AGENCY_NAMES)

    all_payments = []

    # Strategy 1: Search by agency name via API
    for name in agency_names:
        payments = fetch_behested_payments_api(
            agency_name=name,
            official_name=official_name,
            start_date=start_date,
            end_date=end_date,
        )
        all_payments.extend(payments)

    # Strategy 2: If API returned nothing, try HTML scrape
    if not all_payments:
        for name in agency_names:
            payments = fetch_behested_payments_html(agency_name=name)
            all_payments.extend(payments)

    # Deduplicate by source_identifier
    seen = set()
    unique_payments = []
    for p in all_payments:
        key = p.get("source_identifier", "")
        if key and key not in seen:
            seen.add(key)
            unique_payments.append(p)

    logger.info(
        "Total behested payments for %s: %d (after dedup from %d)",
        agency_name, len(unique_payments), len(all_payments),
    )
    return unique_payments


# ── CLI ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch FPPC Form 803 behested payments")
    parser.add_argument("--city-fips", default=DEFAULT_FIPS, help="FIPS code")
    parser.add_argument("--official", help="Official name to search")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    payments = fetch_behested_payments(
        city_fips=args.city_fips,
        official_name=args.official,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    print(f"\nFound {len(payments)} behested payment(s):")
    for p in payments:
        print(f"  {p['official_name']}: ${p.get('amount', '?'):,.2f} from {p['payor_name']} → {p['payee_name']}")
        if p.get("payment_date"):
            print(f"    Date: {p['payment_date']}")
        if p.get("description"):
            print(f"    Purpose: {p['description']}")
