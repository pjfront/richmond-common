"""FPPC Form 803 (Behested Payments) Client.

Fetches behested payment disclosures from the FPPC's published data.
Behested payments (CA Gov Code §82015) are payments made at the request of
elected officials to third parties. Officials must file Form 803 with the
FPPC within 30 days.

Data source: FPPC bulk Excel download — the FPPC publishes a complete
spreadsheet of all Form 803 filings at:
  https://www.fppc.ca.gov/siteassets/documents/tad/published_800s/803/BehestedPayments.xls

This dataset covers **state-level officials** (Assembly/Senate). Local
officials (city council, mayors) may file separately. We filter for
Richmond-related entries by matching payor city, payee city, or known
official names.

Tier 1 source (official government filings).

Usage:
    from fppc_form803_client import fetch_behested_payments
    payments = fetch_behested_payments()
    payments = fetch_behested_payments(official_name="Buffy Wicks")
"""

from __future__ import annotations

import io
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)

DEFAULT_FIPS = "0660620"

# FPPC publishes a complete Excel file of all Form 803 behested payments.
# ~14,500 rows, ~3MB, updated periodically. This is the authoritative source.
FPPC_BEHESTED_XLS_URL = (
    "https://www.fppc.ca.gov/siteassets/documents/tad/"
    "published_800s/803/BehestedPayments.xls"
)
# Columns in the XLS: Official, OfficialType, DateOFPayment (Excel serial),
# payor, payorcity, payee, payeecity, payeestate, amount, description,
# LgcPurpose, PaymentYear

# Known Richmond, California city name variants for matching
RICHMOND_CITY_NAMES = [
    "richmond",
]

# Known Richmond, California official name variants for matching
RICHMOND_AGENCY_NAMES = [
    "City of Richmond",
    "Richmond",
    "Richmond City Council",
]

# Request settings
REQUEST_TIMEOUT = 60  # XLS is ~3MB, give it time
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
        "city_names": RICHMOND_CITY_NAMES,
    }, DEFAULT_FIPS


def _make_request(
    url: str,
    *,
    timeout: int = REQUEST_TIMEOUT,
) -> requests.Response:
    """Make HTTP GET request with retry logic."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Richmond Common Transparency Project)",
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


def _excel_serial_to_date(serial: float | int) -> str | None:
    """Convert Excel date serial number to YYYY-MM-DD string.

    Excel serial dates count days from 1900-01-01 (with the Lotus 1-2-3
    leap year bug where 1900 is incorrectly treated as a leap year).
    """
    if not serial or serial < 1:
        return None
    try:
        serial = int(serial)
        # Excel epoch: 1899-12-30 (accounting for the 1900 leap year bug)
        base = datetime(1899, 12, 30)
        dt = base + timedelta(days=serial)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return None


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


def _normalize_api_record(item: dict) -> dict | None:
    """Normalize a single API/dict result into our standard schema.

    Works with both the XLS row dicts and any future API responses.
    """
    official_name = _normalize_name(
        item.get("filerName", "") or item.get("officialName", "")
        or item.get("Official", "") or ""
    )
    if not official_name:
        return None

    payor_name = _normalize_name(
        item.get("payorName", "") or item.get("sourceOfPayment", "")
        or item.get("payor", "") or ""
    )
    payee_name = _normalize_name(
        item.get("payeeName", "") or item.get("payeeOrganization", "")
        or item.get("payee", "") or ""
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
        "payor_city": (item.get("payorCity") or item.get("payorcity") or "").strip() or None,
        "payor_state": (item.get("payorState") or "").strip() or None,
        "payee_name": payee_name,
        "payee_description": (item.get("payeeDescription") or "").strip() or None,
        "amount": amount,
        "payment_date": _parse_date(
            item.get("paymentDate") or item.get("dateOfPayment")
        ) if not item.get("_date_from_serial") else item.get("_date_from_serial"),
        "filing_date": _parse_date(item.get("filingDate") or item.get("dateFiled")),
        "description": (
            item.get("description") or item.get("purpose") or ""
        ).strip() or None,
        "filing_id": filing_id or None,
        "source_identifier": (
            filing_id
            or f"{official_name}_{payor_name}_{payee_name}_{amount}"
        ),
        "source_url": item.get("url") or item.get("sourceUrl") or None,
        "metadata": {
            k: v for k, v in {
                "agency": item.get("agency") or item.get("agencyName"),
                "position": (
                    item.get("position")
                    or item.get("officialPosition")
                    or item.get("OfficialType")
                ),
                "form_type": item.get("formType", "803"),
                "lgc_purpose": item.get("LgcPurpose"),
                "payment_year": item.get("PaymentYear"),
                "payee_city": item.get("payeecity"),
                "payee_state": item.get("payeestate"),
            }.items()
            if v
        },
    }


def fetch_behested_payments_xls(
    *,
    city_names: list[str] | None = None,
    official_names: list[str] | None = None,
) -> list[dict]:
    """Download and parse FPPC bulk XLS of all behested payments.

    Filters for rows where payor city, payee city, or official name
    matches the target city.

    Args:
        city_names: City name variants to match (case-insensitive).
        official_names: Official name patterns to match (case-insensitive).

    Returns:
        List of normalized payment dicts.
    """
    try:
        import xlrd
    except ImportError:
        logger.error("xlrd required for XLS parsing. Install with: pip install xlrd")
        return []

    try:
        resp = _make_request(FPPC_BEHESTED_XLS_URL, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        logger.error("FPPC XLS download failed: %s", e)
        return []

    try:
        wb = xlrd.open_workbook(file_contents=resp.content)
        ws = wb.sheet_by_index(0)
    except Exception as e:
        logger.error("Failed to parse FPPC XLS: %s", e)
        return []

    # Read headers
    headers = [ws.cell_value(0, c) for c in range(ws.ncols)]
    logger.info(
        "FPPC XLS: %d rows, %d cols. Headers: %s",
        ws.nrows - 1, ws.ncols, headers,
    )

    # Build filter sets (lowercase for case-insensitive matching)
    city_filter = {n.lower() for n in (city_names or RICHMOND_CITY_NAMES)}
    official_filter = {n.lower() for n in (official_names or [])}

    results = []
    for r in range(1, ws.nrows):
        row = {headers[c]: ws.cell_value(r, c) for c in range(ws.ncols)}

        # Check if this row is Richmond-related
        payor_city = str(row.get("payorcity", "")).strip().lower()
        payee_city = str(row.get("payeecity", "")).strip().lower()
        official = str(row.get("Official", "")).strip().lower()

        is_match = (
            payor_city in city_filter
            or payee_city in city_filter
            or (official_filter and official in official_filter)
        )
        if not is_match:
            continue

        # Convert Excel date serial to YYYY-MM-DD
        date_serial = row.get("DateOFPayment")
        row["_date_from_serial"] = _excel_serial_to_date(date_serial) if date_serial else None

        # Normalize into standard schema
        payment = _normalize_api_record(row)
        if payment:
            # Set source URL to FPPC behested payments page
            payment["source_url"] = (
                "https://www.fppc.ca.gov/transparency/"
                "form-700-filed-by-public-officials/behested-payments2.html"
            )
            payment["metadata"]["source_method"] = "fppc_bulk_xls"
            results.append(payment)

    logger.info(
        "FPPC XLS: %d Richmond-related records (from %d total)",
        len(results), ws.nrows - 1,
    )
    return results


def fetch_behested_payments(
    *,
    city_fips: str | None = None,
    official_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Fetch behested payments for a city's officials.

    Primary strategy: Download FPPC bulk XLS and filter for Richmond-
    related entries (payor city, payee city, or official name match).

    Args:
        city_fips: FIPS code (default: Richmond CA).
        official_name: Specific official to search for (post-filter).
        start_date: Start date filter (YYYY-MM-DD, post-filter).
        end_date: End date filter (YYYY-MM-DD, post-filter).

    Returns:
        List of normalized payment dicts ready for load_behested_to_db().
    """
    config, fips = _resolve_config(city_fips)
    agency_name = config.get("agency_name", "City of Richmond")
    city_names = config.get("city_names", RICHMOND_CITY_NAMES)

    # Primary: FPPC bulk XLS download
    all_payments = fetch_behested_payments_xls(city_names=city_names)

    # Post-filter by official name if specified
    if official_name:
        name_lower = official_name.lower()
        all_payments = [
            p for p in all_payments
            if name_lower in p["official_name"].lower()
        ]

    # Post-filter by date range if specified
    if start_date:
        all_payments = [
            p for p in all_payments
            if p.get("payment_date") and p["payment_date"] >= start_date
        ]
    if end_date:
        all_payments = [
            p for p in all_payments
            if p.get("payment_date") and p["payment_date"] <= end_date
        ]

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
        amt = p.get("amount")
        amt_str = f"${amt:,.2f}" if amt else "$?"
        print(f"  {p['official_name']}: {amt_str} from {p['payor_name']} -> {p['payee_name']}")
        if p.get("payment_date"):
            print(f"    Date: {p['payment_date']}")
        if p.get("description"):
            print(f"    Purpose: {p['description'][:100]}")
