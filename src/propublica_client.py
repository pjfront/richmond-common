"""
Richmond Common — ProPublica Nonprofit Explorer Client

Queries the ProPublica Nonprofit Explorer API to identify nonprofit organizations
and link them to campaign donors via employer matching. Part of the entity
resolution infrastructure (B.46).

ProPublica API v2: https://projects.propublica.org/nonprofits/api/v2/
- Free, no authentication required
- 1.8M+ IRS Form 990 filings
- Org search by name, detail by EIN
- Financial summaries per filing year
- NOTE: Officer names NOT available via API (requires IRS 990 XML bulk data)

Usage:
    # Search for nonprofits matching a name
    python propublica_client.py --search "Richmond Community Foundation"

    # Look up a specific org by EIN
    python propublica_client.py --ein 943337754

    # Batch resolve donor employers against ProPublica
    python propublica_client.py --resolve-employers --city-fips 0660620
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)

API_BASE = "https://projects.propublica.org/nonprofits/api/v2"
DEFAULT_DELAY = 0.5  # seconds between requests (be polite, no documented rate limit)
DEFAULT_FIPS = "0660620"


def _normalize_name(name: str) -> str:
    """Lowercase, strip whitespace, collapse spaces."""
    return " ".join(name.lower().split())


def search_organizations(
    query: str,
    state: str | None = None,
    page: int = 0,
    per_page: int = 25,
) -> dict:
    """Search ProPublica Nonprofit Explorer for organizations.

    Args:
        query: Search term (org name, keyword)
        state: Two-letter state code filter (e.g., 'CA')
        page: Page number (0-indexed)
        per_page: Results per page (max 25)

    Returns:
        API response dict with 'organizations', 'total_results', 'num_pages'
    """
    params = {"q": query, "page": page}
    if state:
        params["state[id]"] = state

    resp = requests.get(
        f"{API_BASE}/search.json",
        params=params,
        timeout=30,
        headers={"User-Agent": "RichmondCommon/1.0 (civic transparency project)"},
    )
    # ProPublica returns 404 when no results match (not a standard empty-list 200)
    if resp.status_code == 404:
        return {"organizations": [], "total_results": 0, "num_pages": 0}
    resp.raise_for_status()
    return resp.json()


def fetch_organization(ein: str | int) -> dict | None:
    """Fetch organization details by EIN.

    Args:
        ein: Employer Identification Number (with or without hyphen)

    Returns:
        Organization dict with financial data and filings, or None if not found.
    """
    # Strip hyphens from EIN
    clean_ein = str(ein).replace("-", "")

    resp = requests.get(
        f"{API_BASE}/organizations/{clean_ein}.json",
        timeout=30,
        headers={"User-Agent": "RichmondCommon/1.0 (civic transparency project)"},
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json().get("organization")


def search_all_pages(
    query: str,
    state: str | None = None,
    max_pages: int = 5,
    delay: float = DEFAULT_DELAY,
) -> list[dict]:
    """Search and paginate through all results up to max_pages.

    Returns:
        List of organization dicts from all pages.
    """
    all_orgs = []
    for page in range(max_pages):
        data = search_organizations(query, state=state, page=page)
        orgs = data.get("organizations", [])
        if not orgs:
            break
        all_orgs.extend(orgs)
        if page >= data.get("num_pages", 0) - 1:
            break
        time.sleep(delay)
    return all_orgs


def resolve_employer_to_nonprofit(
    employer_name: str,
    state: str = "CA",
    delay: float = DEFAULT_DELAY,
) -> dict | None:
    """Attempt to resolve a donor employer name to a ProPublica nonprofit.

    Uses a search + best-match approach:
    1. Search ProPublica for the employer name
    2. Score results by name similarity
    3. Return the best match if it meets confidence threshold

    Args:
        employer_name: Employer name from campaign contribution record
        state: State filter for search

    Returns:
        Dict with matched org info and confidence, or None if no match.
    """
    if not employer_name or len(employer_name.strip()) < 3:
        return None

    # Decode HTML entities that leak from web-form-sourced campaign finance data
    employer_name = html.unescape(employer_name)

    # Skip obviously non-nonprofit employers
    skip_prefixes = (
        "city of", "county of", "state of", "united states",
        "self", "retired", "none", "n/a", "not employed",
    )
    skip_suffixes = (
        " county", " city", " district", " school district",
        " unified school district", " department",
    )
    skip_keywords = (
        "police", "sheriff", "fire department", "public works",
        "social services", "behavioral health",
    )
    norm = _normalize_name(employer_name)
    if any(norm.startswith(p) for p in skip_prefixes):
        return None
    if any(norm.endswith(s) for s in skip_suffixes):
        return None
    if any(k in norm for k in skip_keywords):
        return None

    try:
        data = search_organizations(employer_name, state=state)
    except requests.RequestException as e:
        logger.debug("ProPublica search failed for %r: %s", employer_name, e)
        return None

    orgs = data.get("organizations", [])
    if not orgs:
        return None

    # Score each result by name similarity
    best_match = None
    best_score = 0.0

    norm_employer = _normalize_name(employer_name)
    for org in orgs:
        org_name = org.get("name", "")
        norm_org = _normalize_name(org_name)

        # Exact match
        if norm_org == norm_employer:
            score = 1.0
        # One contains the other
        elif norm_employer in norm_org or norm_org in norm_employer:
            shorter = min(len(norm_employer), len(norm_org))
            longer = max(len(norm_employer), len(norm_org))
            score = shorter / longer if longer > 0 else 0.0
        else:
            # Word overlap
            employer_words = set(norm_employer.split())
            org_words = set(norm_org.split())
            if not employer_words:
                continue
            overlap = employer_words & org_words
            score = len(overlap) / max(len(employer_words), len(org_words))

        # Boost if same state
        if org.get("state") == state:
            score *= 1.1

        if score > best_score:
            best_score = score
            best_match = org

    # Minimum confidence threshold
    if best_score < 0.6 or not best_match:
        return None

    confidence = min(best_score, 1.0)

    return {
        "ein": best_match.get("ein"),
        "strein": best_match.get("strein"),
        "name": best_match.get("name"),
        "city": best_match.get("city"),
        "state": best_match.get("state"),
        "ntee_code": best_match.get("ntee_code"),
        "has_filings": best_match.get("have_filings"),
        "confidence": round(confidence, 2),
        "matched_employer": employer_name,
    }


def batch_resolve_employers(
    employer_names: list[str],
    state: str = "CA",
    delay: float = DEFAULT_DELAY,
) -> list[dict]:
    """Resolve a batch of employer names to nonprofits.

    Args:
        employer_names: List of employer names to resolve
        state: State filter
        delay: Seconds between API calls

    Returns:
        List of successful match dicts (skips non-matches).
    """
    matches = []
    seen = set()

    for i, name in enumerate(employer_names):
        norm = _normalize_name(name)
        if norm in seen:
            continue
        seen.add(norm)

        match = resolve_employer_to_nonprofit(name, state=state, delay=delay)
        if match:
            matches.append(match)
            logger.info(
                "  [%d/%d] Matched %r -> %s (EIN: %s, confidence: %.2f)",
                i + 1, len(employer_names), name,
                match["name"], match["ein"], match["confidence"],
            )
        else:
            logger.debug("  [%d/%d] No match for %r", i + 1, len(employer_names), name)

        if i < len(employer_names) - 1:
            time.sleep(delay)

    return matches


# ── CLI ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ProPublica Nonprofit Explorer client")
    parser.add_argument("--search", help="Search for nonprofits by name")
    parser.add_argument("--ein", help="Look up organization by EIN")
    parser.add_argument("--state", default="CA", help="State filter (default: CA)")
    parser.add_argument(
        "--resolve-employers",
        action="store_true",
        help="Batch resolve donor employers from database",
    )
    parser.add_argument("--city-fips", default=DEFAULT_FIPS, help="City FIPS code")
    parser.add_argument("--output", help="Output file path (JSON)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    if args.search:
        data = search_organizations(args.search, state=args.state)
        orgs = data.get("organizations", [])
        print(f"Found {data.get('total_results', 0)} results ({len(orgs)} on this page):\n")
        for org in orgs:
            print(f"  {org.get('name', '?')}")
            print(f"    EIN: {org.get('strein', '?')} | {org.get('city', '?')}, {org.get('state', '?')}")
            print(f"    NTEE: {org.get('ntee_code', '?')} | Filings: {org.get('have_filings', '?')}")
            print()

    elif args.ein:
        org = fetch_organization(args.ein)
        if org:
            print(json.dumps(org, indent=2, default=str))
        else:
            print(f"No organization found for EIN {args.ein}")
            sys.exit(1)

    elif args.resolve_employers:
        from db import get_connection

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT DISTINCT employer FROM donors
                       WHERE city_fips = %s
                         AND employer IS NOT NULL
                         AND employer != ''
                       ORDER BY employer""",
                    (args.city_fips,),
                )
                employers = [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

        print(f"Resolving {len(employers)} distinct employer names...")
        matches = batch_resolve_employers(employers, state=args.state)
        print(f"\nMatched {len(matches)} of {len(employers)} employers to nonprofits.")

        if args.output:
            Path(args.output).write_text(
                json.dumps(matches, indent=2, default=str),
                encoding="utf-8",
            )
            print(f"Results saved to {args.output}")
        else:
            for m in matches:
                print(f"  {m['matched_employer']} -> {m['name']} (EIN: {m['ein']}, conf: {m['confidence']})")

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
