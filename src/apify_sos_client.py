"""
Apify CA Secretary of State business entity resolution client.

Calls the parseforge/sos-scraper Apify actor to search the CA SOS bizfile
(https://bizfileonline.sos.ca.gov/search/business) for business entity
registrations. Replaces OpenCorporates (API denied, rate-limited to 50/day).

Reads from: Apify parseforge/sos-scraper actor (CA SOS bizfile).
Does NOT read from any database table or derivative artifact.

Apify output schema (discovered 2026-07-06):
  entityName       — "CHEVRON CORPORATION" or null if not found
  entityNumber     — "117531" or null
  url              — generic bizfile search page (not entity-specific)
  searchTerm       — the name we searched for
  entityType       — "Stock Corporation - Out of State - Stock"
  status           — "Active", "Dissolved", etc.
  riskLevel        — "low", "medium", "high"
  formationDate    — "02/02/1926" (MM/DD/YYYY)
  registeredAgent  — "1505 Corporation" or "Individual"
  principalAddress — full street address
  signals[]        — [{type, severity, description}]
  scrapedAt        — ISO 8601 timestamp

Usage:
    python apify_sos_client.py "Chevron Corporation"
    python apify_sos_client.py "Chevron Corp" "SEIU Local 1021" "RPOA"
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from opencorporates_client import normalize_entity_name, token_similarity

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────

APIFY_API_BASE = "https://api.apify.com/v2"
ACTOR_PATH = "acts/parseforge~sos-scraper"
SYNC_ENDPOINT = f"{APIFY_API_BASE}/{ACTOR_PATH}/run-sync-get-dataset-items"
RUNS_ENDPOINT = f"{APIFY_API_BASE}/{ACTOR_PATH}/runs"
DEFAULT_MAX_ITEMS = 5
REQUEST_TIMEOUT = 300  # seconds (5 min — sync endpoint cap)
ASYNC_POLL_INTERVAL = 10  # seconds between polling run status
ASYNC_MAX_WAIT = 600  # seconds (10 min) max wait for async run
MAX_RETRIES = 3

# ── Field mapping: Apify camelCase → business_entities column ──
_FIELD_MAP: dict[str, str] = {
    "entityName": "entity_name",
    "entityNumber": "entity_number",
    "entityType": "entity_type",
    "status": "current_status",
    "formationDate": "incorporation_date",
    "registeredAgent": "agent_name",
    "principalAddress": "registered_address",
    # url omitted — Apify returns the generic bizfile search page.
    # We construct an entity-specific source_url in normalize_result().
    "scrapedAt": "retrieved_at",
}


def _get_token() -> str:
    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        raise RuntimeError("APIFY_API_TOKEN not set in .env")
    return token


# ── API client ─────────────────────────────────────────────────

def run_sos_search(
    business_names: list[str],
    max_items: int = DEFAULT_MAX_ITEMS,
) -> list[dict]:
    """Search CA SOS bizfile for business entity registrations.

    Calls the Apify actor synchronously (waits up to 5 min for results).
    Returns a list of result dicts, one per search hit. Names that aren't
    found return a dict with entityName=null and a "not_found" signal.

    Retries on 5xx with exponential backoff. Returns empty list on
    auth failure or timeout.
    """
    if not business_names:
        return []

    token = _get_token()
    payload = {
        "businessNames": list(business_names),
        "maxItems": max_items,
    }

    last_error: str | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                SYNC_ENDPOINT,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 401:
                logger.error("Apify: authentication failed (invalid token)")
                return []
            if response.status_code == 429:
                logger.warning("Apify: rate limited, retrying in %ds", 2 ** attempt)
                time.sleep(2 ** attempt)
                continue
            if response.status_code >= 500:
                logger.warning("Apify: server error %d, retrying", response.status_code)
                time.sleep(2 ** attempt)
                continue

            response.raise_for_status()
            results = response.json()
            if isinstance(results, list):
                return results
            # Apify sometimes wraps in {"data": [...]}
            if isinstance(results, dict):
                for key in ("data", "items", "results"):
                    if key in results and isinstance(results[key], list):
                        return results[key]
                logger.warning("Apify: unexpected response shape: %s", list(results.keys())[:5])
                return []
            return []

        except requests.exceptions.Timeout:
            last_error = f"timeout after {REQUEST_TIMEOUT}s"
            logger.warning("Apify: %s (attempt %d/%d)", last_error, attempt + 1, MAX_RETRIES)
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            logger.warning("Apify: %s (attempt %d/%d)", e, attempt + 1, MAX_RETRIES)
            time.sleep(2 ** attempt)

    logger.error("Apify: all %d attempts failed. Last error: %s", MAX_RETRIES, last_error)
    return []


def run_sos_search_async(
    business_names: list[str],
    max_items: int = DEFAULT_MAX_ITEMS,
) -> list[dict]:
    """Search CA SOS bizfile via the async Apify actor endpoint.

    Submits the run, polls for completion, then fetches the dataset.
    No 5-min timeout — suitable for larger batches.
    """
    if not business_names:
        return []

    token = _get_token()
    payload = {
        "businessNames": list(business_names),
        "maxItems": max_items,
    }

    # 1. Submit the run
    try:
        response = requests.post(
            RUNS_ENDPOINT,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        if response.status_code == 401:
            logger.error("Apify async: authentication failed")
            return []
        response.raise_for_status()
        run_data = response.json()
    except requests.exceptions.RequestException as e:
        logger.error("Apify async: submit failed: %s", e)
        return []

    run_id = run_data.get("data", {}).get("id")
    dataset_id = run_data.get("data", {}).get("defaultDatasetId")
    if not run_id:
        logger.error("Apify async: no run ID in response")
        return []

    logger.info("Apify async: submitted run %s (%d names)", run_id, len(business_names))

    # 2. Poll for completion
    status_url = f"{RUNS_ENDPOINT}/{run_id}"
    elapsed = 0
    while elapsed < ASYNC_MAX_WAIT:
        time.sleep(ASYNC_POLL_INTERVAL)
        elapsed += ASYNC_POLL_INTERVAL
        try:
            r = requests.get(
                status_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            if r.status_code != 200:
                logger.warning("Apify async: poll returned %d", r.status_code)
                continue
            status_data = r.json()
            status = status_data.get("data", {}).get("status", "")
            logger.debug("Apify async: run %s status=%s (%ds)", run_id, status, elapsed)
            if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                logger.info(
                    "Apify async: run %s %s after %ds",
                    run_id, status, elapsed,
                )
                if status != "SUCCEEDED":
                    return []
                break
        except requests.exceptions.RequestException:
            continue
    else:
        logger.error("Apify async: run %s timed out after %ds", run_id, ASYNC_MAX_WAIT)
        return []

    # 3. Fetch results
    ds_id = dataset_id or run_data.get("data", {}).get("defaultDatasetId")
    if not ds_id:
        logger.error("Apify async: no dataset ID for run %s", run_id)
        return []

    dataset_url = f"{APIFY_API_BASE}/datasets/{ds_id}/items"
    try:
        r = requests.get(
            dataset_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        r.raise_for_status()
        results = r.json()
        if isinstance(results, list):
            return results
        return []
    except requests.exceptions.RequestException as e:
        logger.error("Apify async: fetch results failed: %s", e)
        return []


# ── Result normalization ───────────────────────────────────────

def is_found(item: dict) -> bool:
    """Check if the Apify result represents a found entity."""
    if item.get("entityName") is None and item.get("entityNumber") is None:
        return False
    signals = item.get("signals") or []
    for s in signals:
        if s.get("type") == "not_found":
            return False
    return True


def normalize_result(item: dict) -> dict:
    """Map an Apify result dict to business_entities column values.

    Returns a dict keyed by business_entities column names, with
    additional keys 'raw_response' (the full item JSON) and
    'source_publisher' (always 'California Secretary of State').
    """
    result: dict[str, object] = {
        "source_publisher": "California Secretary of State",
        "jurisdiction_code": "us_ca",
        "raw_response": json.dumps(item, ensure_ascii=False),
        # Apify's url is the generic bizfile search page, not entity-specific.
        # Construct a search URL from the entity number when available.
        "source_url": f"https://bizfileonline.sos.ca.gov/search/business/{item.get('entityNumber', '')}",
        "confidence_score": 0.95,  # CA SOS is authoritative (Tier 1)
        "retrieved_at": item.get("scrapedAt", None),
    }

    for apify_key, db_col in _FIELD_MAP.items():
        val = item.get(apify_key)
        if val is not None and val != "":
            result[db_col] = val

    # Parse formationDate from MM/DD/YYYY to date string
    if "incorporation_date" in result:
        raw_date = str(result["incorporation_date"])
        try:
            parts = raw_date.split("/")
            if len(parts) == 3:
                result["incorporation_date"] = f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
        except (ValueError, IndexError):
            pass  # leave as-is, DB will reject or we skip

    return result


# ── Name matching ──────────────────────────────────────────────

def match_entity(
    session_results: list[dict],
    donor_name: str,
    normalized_donor: Optional[str] = None,
    threshold: float = 0.80,
) -> tuple[dict | None, float, str]:
    """Score Apify results against a donor name.

    Args:
        session_results: Raw Apify results from one batch call.
        donor_name: The donor name we're trying to resolve.
        normalized_donor: Pre-computed normalized donor name (optional).
        threshold: Minimum confidence to return a match.

    Returns:
        (normalized_result_dict, confidence, method) — method is one of
        "exact", "fuzzy", or "none" (below threshold).
    """
    if normalized_donor is None:
        normalized_donor = normalize_entity_name(donor_name)

    best: tuple[dict | None, float, str] = (None, 0.0, "none")

    for item in session_results:
        if not is_found(item):
            continue

        entity_name = item.get("entityName") or ""
        if not entity_name.strip():
            continue

        # Try exact match on normalized names first
        normalized_result = normalize_entity_name(entity_name)
        if normalized_result == normalized_donor:
            return (normalize_result(item), 0.95, "exact")

        # Token similarity for fuzzy matches
        score = token_similarity(donor_name, entity_name)
        if score > best[1]:
            best = (normalize_result(item), round(score, 2), "fuzzy")

    if best[1] >= threshold:
        return best
    return (best[0], best[1], "none")


# ── Cost formatting ────────────────────────────────────────────

def format_cost_estimate(result_count: int) -> str:
    """Human-readable cost estimate for Apify usage."""
    cost = result_count * 0.008  # ~$8/1000 results
    return f"~${cost:.2f} ({result_count} results @ ~$8/1000)"


# ── CLI ────────────────────────────────────────────────────────

def main() -> None:
    """CLI: quick entity lookup against CA SOS.

    Usage:
        python apify_sos_client.py "Chevron Corporation"
        python apify_sos_client.py "Chevron Corp" "SEIU Local 1021"
    """
    if len(sys.argv) < 2:
        print("Usage: python apify_sos_client.py NAME [NAME...]")
        print()
        print("Search CA SOS bizfile for business entity registrations via Apify.")
        sys.exit(1)

    names = sys.argv[1:]
    print(f"Searching {len(names)} name(s) against CA SOS bizfile...")
    results = run_sos_search(names, max_items=DEFAULT_MAX_ITEMS)

    found = [r for r in results if is_found(r)]
    not_found = [r for r in results if not is_found(r)]

    print(f"\nResults: {len(found)} found, {len(not_found)} not found")
    print(f"Cost: {format_cost_estimate(len(results))}\n")

    for item in found:
        norm = normalize_result(item)
        print(f"  {norm.get('entity_name', '?')}")
        print(f"    #:     {norm.get('entity_number', '?')}")
        print(f"    Type:  {norm.get('entity_type', '?')}")
        print(f"    Status:{norm.get('current_status', '?')}")
        print(f"    Formed:{norm.get('incorporation_date', '?')}")
        print(f"    Agent: {norm.get('agent_name', '?')}")
        print(f"    Addr:  {norm.get('registered_address', '?')}")
        print()

    for item in not_found:
        print(f"  NOT FOUND: {item.get('searchTerm', '?')}")

    print(f"\n{format_cost_estimate(len(results))}")


if __name__ == "__main__":
    main()
