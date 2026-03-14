"""
Richmond Common — NetFile Campaign Finance Client

Fetches local campaign finance data from the NetFile Connect2 API.
This covers contributions to Richmond City Council candidates that are
filed with the City Clerk (NOT in CAL-ACCESS, which only has PACs/IEs).

NetFile Connect2 API: https://netfile.com/Connect2/api/
Richmond Agency ID: 163 (shortcut: RICH)
Public portal: https://public.netfile.com/pub2/?AID=RICH

Transaction types (FPPC schedules):
  0  = F460A  — Monetary Contributions Received (Schedule A)
  1  = F460C  — Non-Monetary Contributions (Schedule C)
  5  = F460D  — Summary (expenditures summary)
  6  = F460E  — Payments Made (Schedule E)
  11 = F460F  — Accrued Expenses (Unpaid Bills)
  12 = F460B1 — Loans Received
  13 = F460B2 — Loans Made
  20 = F497P1 — Late Contribution Report: Contributions Received
  21 = F497P2 — Late Contribution Report: Contributions Made

Usage:
    # Download all monetary contributions for Richmond
    python netfile_client.py

    # Download contributions since a date
    python netfile_client.py --since 2024-01-01

    # Download specific transaction types
    python netfile_client.py --types 0,1,20

    # Show summary stats only
    python netfile_client.py --stats

    # Output as conflict-scanner-compatible JSON
    python netfile_client.py --output data/netfile/richmond_contributions.json
"""
from __future__ import annotations

import json
import os
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, date
from typing import Optional

import requests
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)


# --- Configuration (defaults — Richmond) ---

API_BASE = "https://netfile.com/Connect2/api"
RICHMOND_AGENCY_ID = 163
RICHMOND_AGENCY_SHORTCUT = "RICH"
CITY_FIPS = "0660620"  # Richmond, CA — always include


def _resolve_netfile_config(
    city_fips: str | None = None,
) -> tuple[str, int, str, str]:
    """Resolve NetFile API params from city registry or module defaults.

    Returns:
        (api_base, agency_id, agency_shortcut, city_fips)
    """
    if city_fips is not None:
        from city_config import get_data_source_config
        cfg = get_data_source_config(city_fips, "netfile")
        return (
            cfg.get("api_base", API_BASE),
            cfg["agency_id"],
            cfg.get("agency_shortcut", ""),
            city_fips,
        )
    return API_BASE, RICHMOND_AGENCY_ID, RICHMOND_AGENCY_SHORTCUT, CITY_FIPS

DATA_DIR = Path("./data/netfile")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Transaction type IDs for contributions
CONTRIBUTION_TYPES = {
    0: "F460A",   # Monetary Contributions Received
    1: "F460C",   # Non-Monetary Contributions
    20: "F497P1", # Late Contribution Report: Received
}

EXPENDITURE_TYPES = {
    6: "F460E",   # Payments Made
    11: "F460F",  # Accrued Expenses
    21: "F497P2", # Late Contribution Report: Made
}

ALL_TYPES = {**CONTRIBUTION_TYPES, **EXPENDITURE_TYPES}

# Rate limiting
REQUEST_DELAY = 0.5  # seconds between API calls


# --- API Client ---

def api_post(
    endpoint: str,
    payload: dict,
    retries: int = 3,
    api_base: str = API_BASE,
) -> dict:
    """Make a POST request to the NetFile Connect2 API.

    NetFile intermittently returns HTTP 500 on some requests.
    Retries with exponential backoff before giving up.
    """
    url = f"{api_base}{endpoint}?format=json"
    for attempt in range(retries):
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()
        if response.status_code == 500 and attempt < retries - 1:
            wait = 2 ** attempt  # 1s, 2s, 4s
            tx_type = payload.get("TransactionType", "?")
            page = payload.get("CurrentPageIndex", "?")
            print(f"    NetFile 500 on type {tx_type} page {page} — retry {attempt + 1}/{retries - 1} in {wait}s")
            time.sleep(wait)
            continue
        if response.status_code == 500:
            tx_type = payload.get("TransactionType", "?")
            print(f"  WARNING: NetFile API returned 500 for type {tx_type} after {retries} attempts — skipping")
            return {"totalMatchingCount": 0, "totalMatchingPages": 0, "results": []}
        response.raise_for_status()
    return {"totalMatchingCount": 0, "totalMatchingPages": 0, "results": []}


def get_agencies(api_base: str = API_BASE) -> list[dict]:
    """Get list of all agencies in NetFile."""
    data = api_post("/public/campaign/agencies", {}, api_base=api_base)
    return data.get("agencies", [])


def get_transaction_types(api_base: str = API_BASE) -> list[dict]:
    """Get list of transaction type codes."""
    data = api_post("/public/campaign/list/transaction/types", {}, api_base=api_base)
    return data.get("items", [])


def search_transactions(
    agency_id: int = RICHMOND_AGENCY_ID,
    transaction_type: Optional[int] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    amount_low: Optional[float] = None,
    amount_high: Optional[float] = None,
    query_string: Optional[str] = None,
    page_size: int = 1000,
    page_index: int = 0,
    sort_order: int = 1,  # DateDescending
    city_fips: Optional[str] = None,
) -> dict:
    """Search transactions via the Connect2 API.

    Returns dict with 'totalMatchingCount', 'totalMatchingPages', 'results'.
    When *city_fips* is provided, agency_id and api_base are resolved from
    the city registry (overriding the *agency_id* default).
    """
    resolved_base = API_BASE
    if city_fips is not None:
        resolved_base, agency_id, _, _ = _resolve_netfile_config(city_fips)

    payload = {
        "Agency": agency_id,
        "PageSize": page_size,
        "CurrentPageIndex": page_index,
        "SortOrder": sort_order,
    }
    if transaction_type is not None:
        payload["TransactionType"] = transaction_type
    if date_start:
        payload["DateStart"] = date_start
    if date_end:
        payload["DateEnd"] = date_end
    if amount_low is not None:
        payload["AmountLow"] = amount_low
    if amount_high is not None:
        payload["AmountHigh"] = amount_high
    if query_string:
        payload["QueryString"] = query_string

    return api_post("/public/campaign/search/transaction/query", payload, api_base=resolved_base)


def fetch_all_transactions(
    transaction_type: Optional[int] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    amount_low: Optional[float] = None,
    page_size: int = 1000,
    city_fips: Optional[str] = None,
) -> list[dict]:
    """Fetch all matching transactions, paginating through results."""
    all_results = []
    page = 0

    # First request to get total count
    data = search_transactions(
        transaction_type=transaction_type,
        date_start=date_start,
        date_end=date_end,
        amount_low=amount_low,
        page_size=page_size,
        page_index=page,
        city_fips=city_fips,
    )

    total = data.get("totalMatchingCount", 0)
    total_pages = data.get("totalMatchingPages", 0)
    results = data.get("results", [])
    all_results.extend(results)

    type_label = ALL_TYPES.get(transaction_type, "all") if transaction_type is not None else "all"
    print(f"  [{type_label}] Total: {total:,} records, {total_pages} pages")

    # Fetch remaining pages
    while page + 1 < total_pages:
        page += 1
        time.sleep(REQUEST_DELAY)
        data = search_transactions(
            transaction_type=transaction_type,
            date_start=date_start,
            date_end=date_end,
            amount_low=amount_low,
            page_size=page_size,
            page_index=page,
            city_fips=city_fips,
        )
        results = data.get("results", [])
        all_results.extend(results)
        if page % 10 == 0:
            print(f"    Page {page}/{total_pages} ({len(all_results):,} fetched)")

    return all_results


# --- Data Processing ---

def normalize_transaction(tx: dict, city_fips: str | None = None) -> dict:
    """Normalize a NetFile transaction into conflict-scanner-compatible format.

    The conflict scanner expects contributions with these fields:
        contributor_name, contributor_employer, amount, date, committee
    (also accepts donor_name, donor_employer, committee_name)
    """
    resolved_fips = city_fips if city_fips is not None else CITY_FIPS
    return {
        # Conflict scanner fields
        "contributor_name": (tx.get("name") or "").strip(),
        "contributor_employer": (tx.get("employer") or "").strip(),
        "amount": tx.get("amount", 0),
        "date": (tx.get("date") or "")[:10],  # ISO date only
        "committee": (tx.get("filerName") or "").strip(),
        # Extra fields for analysis
        "occupation": (tx.get("occupation") or "").strip(),
        "city": (tx.get("city") or "").strip(),
        "state": (tx.get("state") or "").strip(),
        "zip": (tx.get("zip") or "").strip(),
        "transaction_type": ALL_TYPES.get(tx.get("transactionType"), "unknown"),
        "filer_fppc_id": (tx.get("filerFppcId") or "").strip(),
        "filer_local_id": (tx.get("filerLocalId") or "").strip(),
        "filing_id": (tx.get("filingId") or "").strip(),
        "transaction_id": (tx.get("id") or "").strip(),
        # Source tracking
        "source": "netfile",
        "city_fips": resolved_fips,
    }


def deduplicate_contributions(contributions: list[dict]) -> list[dict]:
    """Remove duplicate contributions (from amended filings).

    NetFile may return both original and amended versions. Dedup by
    (contributor_name, amount, date, committee) tuple, keeping the
    record from the most recent filing.
    """
    seen = {}
    for c in contributions:
        key = (
            c["contributor_name"].lower(),
            c["amount"],
            c["date"],
            c["committee"].lower(),
        )
        existing = seen.get(key)
        if existing is None or c["filing_id"] > existing["filing_id"]:
            seen[key] = c

    deduped = list(seen.values())
    if len(contributions) != len(deduped):
        print(f"  Deduplicated: {len(contributions)} -> {len(deduped)} "
              f"(removed {len(contributions) - len(deduped)} duplicates)")
    return deduped


def extract_filers(transactions: list[dict], city_fips: str | None = None) -> list[dict]:
    """Extract unique filer (committee) info from transactions."""
    resolved_fips = city_fips if city_fips is not None else CITY_FIPS
    filers = {}
    for tx in transactions:
        fppc_id = tx.get("filer_fppc_id", "")
        if fppc_id and fppc_id not in filers:
            filers[fppc_id] = {
                "fppc_id": fppc_id,
                "local_id": tx.get("filer_local_id", ""),
                "name": tx.get("committee", ""),
                "source": "netfile",
                "city_fips": resolved_fips,
            }
    return list(filers.values())


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="Richmond Common — NetFile Campaign Finance Client"
    )
    parser.add_argument("--since", help="Only fetch contributions after this date (YYYY-MM-DD)")
    parser.add_argument("--types", default="0,1",
                        help="Transaction type IDs to fetch (default: 0,1 = contributions; type 20 intermittently broken on NetFile)")
    parser.add_argument("--all-types", action="store_true",
                        help="Fetch all transaction types (contributions + expenditures)")
    parser.add_argument("--min-amount", type=float, default=None,
                        help="Minimum contribution amount to include")
    parser.add_argument("--stats", action="store_true",
                        help="Show summary statistics only (no download)")
    parser.add_argument("--output", default=str(DATA_DIR / "richmond_contributions.json"),
                        help="Output file path")
    parser.add_argument("--filers-output", default=str(DATA_DIR / "richmond_filers.json"),
                        help="Filer index output path")

    args = parser.parse_args()

    # Parse transaction types
    if args.all_types:
        type_ids = list(ALL_TYPES.keys())
    else:
        type_ids = [int(t.strip()) for t in args.types.split(",")]

    print(f"NetFile Campaign Finance Client — Richmond, CA (Agency {RICHMOND_AGENCY_ID})")
    print(f"Transaction types: {[ALL_TYPES.get(t, f'type_{t}') for t in type_ids]}")
    if args.since:
        print(f"Date filter: since {args.since}")
    print()

    # Stats mode: just show counts
    if args.stats:
        print("Transaction counts by type:")
        total = 0
        for type_id, label in sorted(ALL_TYPES.items()):
            data = search_transactions(
                transaction_type=type_id,
                date_start=args.since,
                page_size=1,
            )
            count = data.get("totalMatchingCount", 0)
            total += count
            print(f"  {label:8s} (type {type_id:2d}): {count:>8,}")
            time.sleep(REQUEST_DELAY)
        print(f"  {'TOTAL':8s}          : {total:>8,}")
        return

    # Fetch all matching transactions
    all_transactions = []
    for type_id in type_ids:
        print(f"Fetching type {type_id} ({ALL_TYPES.get(type_id, '?')})...")
        txs = fetch_all_transactions(
            transaction_type=type_id,
            date_start=args.since,
            amount_low=args.min_amount,
        )
        all_transactions.extend(txs)
        time.sleep(REQUEST_DELAY)

    print(f"\nTotal raw transactions: {len(all_transactions):,}")

    # Normalize
    contributions = [normalize_transaction(tx) for tx in all_transactions]

    # Deduplicate
    contributions = deduplicate_contributions(contributions)

    # Filter zero-amount records
    nonzero = [c for c in contributions if c["amount"] != 0]
    if len(nonzero) < len(contributions):
        print(f"  Filtered out {len(contributions) - len(nonzero)} zero-amount records")
    contributions = nonzero

    # Extract filer index
    filers = extract_filers(contributions)

    # Summary
    total_amount = sum(c["amount"] for c in contributions)
    unique_donors = len(set(c["contributor_name"].lower() for c in contributions if c["contributor_name"]))
    unique_committees = len(set(c["committee"].lower() for c in contributions if c["committee"]))

    print(f"\n{'='*60}")
    print(f"Richmond NetFile Contributions Summary")
    print(f"{'='*60}")
    print(f"  Total contributions: {len(contributions):,}")
    print(f"  Total amount:        ${total_amount:,.2f}")
    print(f"  Unique donors:       {unique_donors:,}")
    print(f"  Unique committees:   {unique_committees:,} ({len(filers)} filers)")
    if contributions:
        dates = [c["date"] for c in contributions if c["date"]]
        if dates:
            print(f"  Date range:          {min(dates)} to {max(dates)}")
    print()

    # Top committees
    committee_totals = {}
    for c in contributions:
        comm = c["committee"]
        committee_totals[comm] = committee_totals.get(comm, 0) + c["amount"]
    top_committees = sorted(committee_totals.items(), key=lambda x: -x[1])[:15]
    print("Top 15 committees by total contributions:")
    for comm, total in top_committees:
        print(f"  ${total:>12,.2f}  {comm}")
    print()

    # Top donors
    donor_totals = {}
    for c in contributions:
        donor = c["contributor_name"]
        if donor:
            donor_totals[donor] = donor_totals.get(donor, 0) + c["amount"]
    top_donors = sorted(donor_totals.items(), key=lambda x: -x[1])[:15]
    print("Top 15 donors by total contributions:")
    for donor, total in top_donors:
        print(f"  ${total:>12,.2f}  {donor}")

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(contributions, f, indent=2, default=str)
    print(f"\nSaved {len(contributions):,} contributions to {output_path}")

    filers_path = Path(args.filers_output)
    with open(filers_path, "w", encoding="utf-8") as f:
        json.dump(filers, f, indent=2)
    print(f"Saved {len(filers)} filers to {filers_path}")


if __name__ == "__main__":
    main()
