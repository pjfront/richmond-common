"""Standalone NetFile Connect2 API client.

Extracted from Richmond Common's netfile_client.py for use as a
standalone package. No database dependency. No dotenv. No file I/O.

NetFile Connect2 API: https://netfile.com/Connect2/api/
Public, no authentication required. Covers ~200 California local agencies.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# --- Configuration ---

API_BASE = "https://netfile.com/Connect2/api"

# Transaction type IDs (FPPC schedules)
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
            logger.warning(
                "NetFile 500 on type %s page %s — retry %d/%d in %ds",
                tx_type, page, attempt + 1, retries - 1, wait,
            )
            time.sleep(wait)
            continue
        if response.status_code == 500:
            tx_type = payload.get("TransactionType", "?")
            logger.warning(
                "NetFile API returned 500 for type %s after %d attempts — skipping",
                tx_type, retries,
            )
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
    agency_id: int,
    transaction_type: Optional[int] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    amount_low: Optional[float] = None,
    amount_high: Optional[float] = None,
    query_string: Optional[str] = None,
    page_size: int = 1000,
    page_index: int = 0,
    sort_order: int = 1,  # DateDescending
    api_base: str = API_BASE,
) -> dict:
    """Search transactions via the Connect2 API.

    Returns dict with 'totalMatchingCount', 'totalMatchingPages', 'results'.
    """
    payload: dict = {
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

    return api_post(
        "/public/campaign/search/transaction/query",
        payload,
        api_base=api_base,
    )


def fetch_all_transactions(
    agency_id: int,
    transaction_type: Optional[int] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    amount_low: Optional[float] = None,
    page_size: int = 1000,
    api_base: str = API_BASE,
) -> tuple[list[dict], int]:
    """Fetch all matching transactions, paginating through results.

    Returns (all_results, total_matching_count).
    """
    all_results: list[dict] = []
    page = 0

    data = search_transactions(
        agency_id=agency_id,
        transaction_type=transaction_type,
        date_start=date_start,
        date_end=date_end,
        amount_low=amount_low,
        page_size=page_size,
        page_index=page,
        api_base=api_base,
    )

    total = data.get("totalMatchingCount", 0)
    total_pages = data.get("totalMatchingPages", 0)
    results = data.get("results", [])
    all_results.extend(results)

    type_label = ALL_TYPES.get(transaction_type, "all") if transaction_type is not None else "all"
    logger.info("[%s] Total: %s records, %d pages", type_label, f"{total:,}", total_pages)

    while page + 1 < total_pages:
        page += 1
        time.sleep(REQUEST_DELAY)
        data = search_transactions(
            agency_id=agency_id,
            transaction_type=transaction_type,
            date_start=date_start,
            date_end=date_end,
            amount_low=amount_low,
            page_size=page_size,
            page_index=page,
            api_base=api_base,
        )
        results = data.get("results", [])
        all_results.extend(results)
        if page % 10 == 0:
            logger.info("  Page %d/%d (%s fetched)", page, total_pages, f"{len(all_results):,}")

    return all_results, total


# --- Data Processing ---

def normalize_transaction(tx: dict) -> dict:
    """Normalize a raw NetFile transaction into a clean format."""
    return {
        "contributor_name": (tx.get("name") or "").strip(),
        "contributor_employer": (tx.get("employer") or "").strip(),
        "amount": tx.get("amount", 0),
        "date": (tx.get("date") or "")[:10],  # ISO date only
        "committee": (tx.get("filerName") or "").strip(),
        "occupation": (tx.get("occupation") or "").strip(),
        "city": (tx.get("city") or "").strip(),
        "state": (tx.get("state") or "").strip(),
        "zip": (tx.get("zip") or "").strip(),
        "transaction_type": ALL_TYPES.get(tx.get("transactionType"), "unknown"),
        "filer_fppc_id": (tx.get("filerFppcId") or "").strip(),
        "filer_local_id": (tx.get("filerLocalId") or "").strip(),
        "filing_id": (tx.get("filingId") or "").strip(),
        "transaction_id": (tx.get("id") or "").strip(),
        "source": "netfile",
    }


def deduplicate_contributions(contributions: list[dict]) -> list[dict]:
    """Remove duplicate contributions from amended filings.

    Deduplicates by (contributor_name, amount, date, committee) tuple,
    keeping the record from the most recent filing (highest filing_id).
    """
    seen: dict[tuple, dict] = {}
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
    removed = len(contributions) - len(deduped)
    if removed > 0:
        logger.info("Deduplicated: %d -> %d (removed %d duplicates)", len(contributions), len(deduped), removed)
    return deduped


def extract_filers(transactions: list[dict]) -> list[dict]:
    """Extract unique filer (committee) info from normalized transactions."""
    filers: dict[str, dict] = {}
    for tx in transactions:
        fppc_id = tx.get("filer_fppc_id", "")
        if fppc_id and fppc_id not in filers:
            filers[fppc_id] = {
                "fppc_id": fppc_id,
                "local_id": tx.get("filer_local_id", ""),
                "name": tx.get("committee", ""),
            }
    return list(filers.values())
