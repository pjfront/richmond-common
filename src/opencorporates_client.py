"""
Richmond Common — OpenCorporates Business Entity Resolution Client

Resolves business entity names from campaign finance, permits, and contracts
against the OpenCorporates registry (aggregated from CA Secretary of State).
Supports LLC ownership chain detection, donor-vendor cross-reference, and
permit-donor conflict signals for the conflict scanner.

OpenCorporates API v0.4: https://api.opencorporates.com/v0.4/
- Free tier for open data projects: 50 requests/day, 200 requests/month
- Data licensed under ODbL (Open Database License)
- Attribution required: "from OpenCorporates" with link

Usage:
    # Search for a company by name
    python opencorporates_client.py --search "ChevronTexaco Corporation"

    # Get company details by CA SOS number
    python opencorporates_client.py --detail C0186725

    # Search for officers by name
    python opencorporates_client.py --officers "John Smith"

    # Resolve entity names from donors table
    python opencorporates_client.py --resolve --city-fips 0660620

    # Show API budget status
    python opencorporates_client.py --budget
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)

# --- Configuration (defaults — California) ---

API_BASE = "https://api.opencorporates.com/v0.4"
DEFAULT_JURISDICTION = "us_ca"
DEFAULT_FIPS = "0660620"  # Richmond, CA

# Rate limits (free/open data tier)
DAILY_LIMIT = int(os.getenv("OPENCORPORATES_DAILY_LIMIT", "50"))
MONTHLY_LIMIT = int(os.getenv("OPENCORPORATES_MONTHLY_LIMIT", "200"))

# Cache TTL: entity data is slow-moving (LLC biennial filings)
CACHE_TTL_DAYS = 90

# Polite delay between requests
REQUEST_DELAY = 1.0  # seconds

# Business name suffixes for entity detection
_ENTITY_SUFFIX_PATTERN = re.compile(
    r'[,.]?\s*\b(?:inc\.?|incorporated|llc|l\.l\.c\.?|corp\.?|corporation|'
    r'ltd\.?|limited|co\.?|company|lp|l\.p\.?|llp|l\.l\.p\.?|associates|'
    r'group|holdings|enterprises)\s*\.?\s*$',
    re.IGNORECASE,
)

# Broader detection pattern (includes mid-string matches like "X, A Delaware LLC")
_ENTITY_DETECT_PATTERN = re.compile(
    r'\b(?:llc|l\.l\.c|inc|incorporated|corp|corporation|ltd|limited|'
    r'lp|l\.p|llp|l\.l\.p)\b',
    re.IGNORECASE,
)


# --- Data Classes ---

@dataclass
class CompanySearchResult:
    """A company from OpenCorporates search results."""
    name: str
    company_number: str | None
    jurisdiction_code: str
    company_type: str | None
    current_status: str | None
    incorporation_date: str | None
    dissolution_date: str | None
    registered_address: str | None
    opencorporates_url: str | None
    source_publisher: str | None = None
    source_retrieved_at: str | None = None


@dataclass
class OfficerRecord:
    """An officer/director/agent from a company or officer search."""
    name: str
    position: str | None
    start_date: str | None
    end_date: str | None
    is_inactive: bool = False
    opencorporates_id: int | None = None
    company_name: str | None = None
    company_number: str | None = None


@dataclass
class CompanyDetail(CompanySearchResult):
    """Full company details including officers and agent info."""
    agent_name: str | None = None
    agent_address: str | None = None
    officers: list[OfficerRecord] = field(default_factory=list)
    previous_names: list[dict] = field(default_factory=list)
    raw_response: dict = field(default_factory=dict)


@dataclass
class EntityResolution:
    """Result of resolving a source name to a business entity."""
    source_name: str
    matched: bool
    company: CompanyDetail | None = None
    confidence: float = 0.0
    match_method: str = "none"  # exact, normalized, fuzzy, entity_number
    cached: bool = False  # True if result came from DB cache


# --- Rate Limit Tracking ---

class RateLimitTracker:
    """Tracks API usage against daily/monthly budgets.

    Uses the opencorporates_api_usage table in the database when a connection
    is available, falling back to in-memory tracking for testing/offline use.
    """

    def __init__(
        self,
        daily_limit: int = DAILY_LIMIT,
        monthly_limit: int = MONTHLY_LIMIT,
        db_conn=None,
    ):
        self.daily_limit = daily_limit
        self.monthly_limit = monthly_limit
        self._db_conn = db_conn
        # In-memory fallback
        self._calls: list[datetime] = []

    def can_call(self) -> tuple[bool, str]:
        """Check if an API call is within budget.

        Returns:
            (allowed, reason) — reason explains the denial if not allowed.
        """
        daily, monthly = self.get_usage()
        if daily >= self.daily_limit:
            return False, f"Daily limit reached ({daily}/{self.daily_limit})"
        if monthly >= self.monthly_limit:
            return False, f"Monthly limit reached ({monthly}/{self.monthly_limit})"
        return True, "OK"

    def record_call(self, endpoint: str, query_params: dict | None = None,
                    status_code: int = 200) -> None:
        """Record an API call for rate tracking."""
        now = datetime.now(timezone.utc)
        self._calls.append(now)

        if self._db_conn:
            try:
                cur = self._db_conn.cursor()
                cur.execute(
                    """INSERT INTO opencorporates_api_usage
                       (endpoint, query_params, response_status, called_at)
                       VALUES (%s, %s, %s, %s)""",
                    (endpoint, json.dumps(query_params or {}), status_code, now),
                )
                self._db_conn.commit()
            except Exception as e:
                logger.warning("Failed to record API usage to DB: %s", e)

    def get_usage(self) -> tuple[int, int]:
        """Get (daily_count, monthly_count) of API calls."""
        if self._db_conn:
            try:
                cur = self._db_conn.cursor()
                cur.execute("""
                    SELECT
                        COUNT(*) FILTER (WHERE called_at > NOW() - INTERVAL '1 day') as daily,
                        COUNT(*) FILTER (WHERE called_at > NOW() - INTERVAL '1 month') as monthly
                    FROM opencorporates_api_usage
                """)
                row = cur.fetchone()
                return (row[0] or 0, row[1] or 0)
            except Exception as e:
                logger.warning("Failed to read API usage from DB: %s", e)

        # In-memory fallback
        now = datetime.now(timezone.utc)
        day_ago = now - timedelta(days=1)
        month_ago = now - timedelta(days=30)
        daily = sum(1 for c in self._calls if c > day_ago)
        monthly = sum(1 for c in self._calls if c > month_ago)
        return daily, monthly

    def budget_status(self) -> str:
        """Human-readable budget status for pipeline logs."""
        daily, monthly = self.get_usage()
        return (
            f"OpenCorporates API budget: "
            f"{daily}/{self.daily_limit} daily, "
            f"{monthly}/{self.monthly_limit} monthly"
        )


# --- Name Normalization ---

def normalize_entity_name(name: str) -> str:
    """Normalize a business entity name for comparison.

    Strips suffixes (LLC, Inc, Corp, etc.), punctuation, extra whitespace.
    Uppercases for case-insensitive matching.

    This is intentionally similar to conflict_scanner.normalize_business_name()
    but focused on entity resolution matching rather than donor-to-agenda matching.
    """
    # Strip common business suffixes
    result = _ENTITY_SUFFIX_PATTERN.sub('', name.strip()).strip()
    if not result:
        result = name.strip()
    # Remove punctuation, collapse whitespace, uppercase
    result = re.sub(r'[,.\'"!?;:()\[\]{}\-/]', ' ', result)
    result = re.sub(r'\s+', ' ', result).strip().upper()
    return result


def looks_like_entity(name: str) -> bool:
    """Check if a name looks like a business entity (has LLC/Inc/Corp/etc)."""
    return bool(_ENTITY_DETECT_PATTERN.search(name))


def token_similarity(name_a: str, name_b: str) -> float:
    """Token-based similarity score between two names.

    Uses Jaccard similarity on word tokens after normalization.
    Better than edit distance for entity names with variable-length
    components (e.g., "ABC Construction" vs "ABC Construction Services LLC").
    """
    tokens_a = set(normalize_entity_name(name_a).split())
    tokens_b = set(normalize_entity_name(name_b).split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


# --- API Client ---

def _get_api_token() -> str | None:
    """Get OpenCorporates API token from environment."""
    return os.getenv("OPENCORPORATES_API_TOKEN")


def _api_get(
    path: str,
    params: dict | None = None,
    rate_tracker: RateLimitTracker | None = None,
    retries: int = 3,
) -> dict | None:
    """Make a GET request to the OpenCorporates API.

    Handles rate limiting, retries with exponential backoff, and
    API token injection.

    Returns:
        Parsed JSON response dict, or None if request failed.
    """
    # Check rate limit budget
    if rate_tracker:
        allowed, reason = rate_tracker.can_call()
        if not allowed:
            logger.warning("OpenCorporates rate limit: %s", reason)
            return None

    token = _get_api_token()
    if not token:
        logger.error(
            "OPENCORPORATES_API_TOKEN not set. "
            "Apply at https://opencorporates.com/api_accounts/new"
        )
        return None

    url = f"{API_BASE}/{path.lstrip('/')}"
    all_params = {**(params or {}), "api_token": token}

    for attempt in range(retries):
        try:
            resp = requests.get(
                url,
                params=all_params,
                timeout=30,
                headers={"User-Agent": "RichmondCommon/1.0 (civic transparency)"},
            )

            if rate_tracker:
                rate_tracker.record_call(
                    endpoint=path,
                    query_params={k: v for k, v in all_params.items() if k != "api_token"},
                    status_code=resp.status_code,
                )

            if resp.status_code == 200:
                time.sleep(REQUEST_DELAY)
                return resp.json()

            if resp.status_code == 401:
                logger.error("OpenCorporates API: Invalid or expired token")
                return None

            if resp.status_code == 403:
                logger.error("OpenCorporates API: Rate limit exceeded (server-side)")
                return None

            if resp.status_code == 404:
                logger.debug("OpenCorporates: No results for %s", path)
                return None

            if resp.status_code >= 500 and attempt < retries - 1:
                wait = 2 ** attempt
                logger.warning(
                    "OpenCorporates API %d on %s, retry %d/%d in %ds",
                    resp.status_code, path, attempt + 1, retries, wait,
                )
                time.sleep(wait)
                continue

            resp.raise_for_status()

        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                wait = 2 ** attempt
                logger.warning("OpenCorporates timeout on %s, retry in %ds", path, wait)
                time.sleep(wait)
                continue
            logger.error("OpenCorporates: Timeout after %d retries for %s", retries, path)

        except requests.exceptions.RequestException as e:
            logger.error("OpenCorporates request failed: %s", e)
            return None

    return None


def _parse_company(data: dict) -> CompanySearchResult:
    """Parse a company dict from OC API response into a CompanySearchResult."""
    source = data.get("source", {}) or {}
    return CompanySearchResult(
        name=data.get("name", ""),
        company_number=data.get("company_number"),
        jurisdiction_code=data.get("jurisdiction_code", ""),
        company_type=data.get("company_type"),
        current_status=data.get("current_status"),
        incorporation_date=data.get("incorporation_date"),
        dissolution_date=data.get("dissolution_date"),
        registered_address=data.get("registered_address_in_full"),
        opencorporates_url=data.get("opencorporates_url"),
        source_publisher=source.get("publisher"),
        source_retrieved_at=source.get("retrieved_at"),
    )


def _parse_officer(data: dict) -> OfficerRecord:
    """Parse an officer dict from OC API response."""
    company = data.get("company", {}) or {}
    return OfficerRecord(
        name=data.get("name", ""),
        position=data.get("position"),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        is_inactive=data.get("inactive", False),
        opencorporates_id=data.get("id"),
        company_name=company.get("name"),
        company_number=company.get("company_number"),
    )


# --- Public API ---

def search_company(
    name: str,
    jurisdiction: str = DEFAULT_JURISDICTION,
    rate_tracker: RateLimitTracker | None = None,
) -> list[CompanySearchResult]:
    """Search OpenCorporates for companies matching a name.

    Args:
        name: Company name to search for.
        jurisdiction: Jurisdiction code (default: us_ca).
        rate_tracker: Rate limit tracker instance.

    Returns:
        List of matching companies, ordered by relevance.
    """
    params = {
        "q": name,
        "jurisdiction_code": jurisdiction,
        "order": "score",
    }
    resp = _api_get("companies/search", params=params, rate_tracker=rate_tracker)
    if not resp:
        return []

    companies_data = resp.get("results", {}).get("companies", [])
    return [_parse_company(c.get("company", {})) for c in companies_data]


def get_company(
    company_number: str,
    jurisdiction: str = DEFAULT_JURISDICTION,
    sparse: bool = False,
    rate_tracker: RateLimitTracker | None = None,
) -> CompanyDetail | None:
    """Get full details for a specific company by registration number.

    Args:
        company_number: CA SOS entity number (e.g., 'C3268102').
        jurisdiction: Jurisdiction code (default: us_ca).
        sparse: If True, skip filings/data sections (faster).
        rate_tracker: Rate limit tracker instance.

    Returns:
        CompanyDetail with officers, agent, etc., or None if not found.
    """
    path = f"companies/{jurisdiction}/{company_number}"
    params = {}
    if sparse:
        params["sparse"] = "true"

    resp = _api_get(path, params=params, rate_tracker=rate_tracker)
    if not resp:
        return None

    data = resp.get("results", {}).get("company", {})
    if not data:
        return None

    base = _parse_company(data)
    officers = [
        _parse_officer(o.get("officer", {}))
        for o in (data.get("officers") or [])
    ]

    return CompanyDetail(
        **{k: v for k, v in base.__dict__.items()},
        agent_name=data.get("agent_name"),
        agent_address=data.get("agent_address"),
        officers=officers,
        previous_names=data.get("previous_names") or [],
        raw_response=data,
    )


def search_officers(
    name: str,
    jurisdiction: str = DEFAULT_JURISDICTION,
    rate_tracker: RateLimitTracker | None = None,
) -> list[OfficerRecord]:
    """Search for officers/directors by name.

    Use for reverse lookups: given a person, find their corporate roles.

    Args:
        name: Person name to search.
        jurisdiction: Jurisdiction code (default: us_ca).
        rate_tracker: Rate limit tracker instance.

    Returns:
        List of officer records with company associations.
    """
    params = {
        "q": name,
        "jurisdiction_code": jurisdiction,
    }
    resp = _api_get("officers/search", params=params, rate_tracker=rate_tracker)
    if not resp:
        return []

    officers_data = resp.get("results", {}).get("officers", [])
    return [_parse_officer(o.get("officer", {})) for o in officers_data]


def resolve_entity(
    name: str,
    city_fips: str = DEFAULT_FIPS,
    jurisdiction: str = DEFAULT_JURISDICTION,
    rate_tracker: RateLimitTracker | None = None,
    db_conn=None,
    auto_match_threshold: float = 0.80,
) -> EntityResolution:
    """High-level entity resolution: search, match, cache, return best match.

    This is the primary entry point for the conflict scanner integration.
    Handles the full resolution pipeline:
    1. Check local cache (business_entities table)
    2. If cache miss/stale, search OpenCorporates API
    3. Score matches using token similarity
    4. Cache the result locally
    5. Return best match with confidence score

    Args:
        name: Entity name from source record (contribution, permit, etc.)
        city_fips: FIPS code for tagging stored records.
        jurisdiction: Jurisdiction code for API search.
        rate_tracker: Rate limit tracker instance.
        db_conn: Database connection for caching. None = no caching.
        auto_match_threshold: Minimum similarity for automatic matching.

    Returns:
        EntityResolution with match details and confidence.
    """
    normalized = normalize_entity_name(name)

    # 1. Check local cache
    if db_conn:
        cached = _check_cache(normalized, jurisdiction, db_conn)
        if cached:
            return EntityResolution(
                source_name=name,
                matched=True,
                company=cached,
                confidence=0.95,  # Cache hit = previously validated
                match_method="cached",
                cached=True,
            )

    # 2. Search OpenCorporates
    results = search_company(name, jurisdiction=jurisdiction, rate_tracker=rate_tracker)
    if not results:
        return EntityResolution(source_name=name, matched=False)

    # 3. Score matches
    best_match = None
    best_score = 0.0
    best_method = "none"

    for result in results:
        # Exact match (after normalization)
        if normalize_entity_name(result.name) == normalized:
            best_match = result
            best_score = 0.95
            best_method = "exact"
            break

        # Token similarity
        score = token_similarity(name, result.name)
        if score > best_score:
            best_score = score
            best_match = result
            best_method = "fuzzy" if score < 0.95 else "normalized"

    if not best_match or best_score < 0.50:
        return EntityResolution(
            source_name=name,
            matched=False,
            confidence=best_score,
            match_method=best_method,
        )

    # 4. Get full details if we have a good match with a company number
    detail = None
    if best_match.company_number and best_score >= auto_match_threshold:
        detail = get_company(
            best_match.company_number,
            jurisdiction=jurisdiction,
            rate_tracker=rate_tracker,
        )

    if detail is None:
        # Convert search result to a minimal CompanyDetail
        detail = CompanyDetail(**{k: v for k, v in best_match.__dict__.items()})

    # 5. Cache the result
    if db_conn and best_score >= auto_match_threshold:
        _store_entity(detail, city_fips, db_conn)

    return EntityResolution(
        source_name=name,
        matched=best_score >= auto_match_threshold,
        company=detail,
        confidence=best_score,
        match_method=best_method,
        cached=False,
    )


# --- Database Cache ---

def _check_cache(
    normalized_name: str,
    jurisdiction: str,
    db_conn,
) -> CompanyDetail | None:
    """Check if we have a cached entity match within TTL."""
    try:
        cur = db_conn.cursor()
        cur.execute(
            """SELECT entity_name, entity_number, jurisdiction_code, entity_type,
                      current_status, incorporation_date, dissolution_date,
                      registered_address, agent_name, agent_address,
                      opencorporates_url, source_publisher, retrieved_at,
                      raw_response, id
               FROM business_entities
               WHERE UPPER(entity_name) = %s
                 AND jurisdiction_code = %s
                 AND extracted_at > NOW() - INTERVAL '%s days'
               ORDER BY extracted_at DESC
               LIMIT 1""",
            (normalized_name, jurisdiction, CACHE_TTL_DAYS),
        )
        row = cur.fetchone()
        if not row:
            return None

        # Also fetch officers
        entity_id = row[14]
        cur.execute(
            """SELECT officer_name, position, start_date, end_date,
                      is_inactive, opencorporates_officer_id
               FROM business_entity_officers
               WHERE business_entity_id = %s""",
            (entity_id,),
        )
        officer_rows = cur.fetchall()
        officers = [
            OfficerRecord(
                name=r[0], position=r[1], start_date=str(r[2]) if r[2] else None,
                end_date=str(r[3]) if r[3] else None, is_inactive=r[4] or False,
                opencorporates_id=r[5],
            )
            for r in officer_rows
        ]

        return CompanyDetail(
            name=row[0],
            company_number=row[1],
            jurisdiction_code=row[2],
            company_type=row[3],
            current_status=row[4],
            incorporation_date=str(row[5]) if row[5] else None,
            dissolution_date=str(row[6]) if row[6] else None,
            registered_address=row[7],
            opencorporates_url=row[10],
            source_publisher=row[11],
            source_retrieved_at=str(row[12]) if row[12] else None,
            agent_name=row[8],
            agent_address=row[9],
            officers=officers,
            raw_response=row[13] or {},
        )
    except Exception as e:
        logger.warning("Cache lookup failed: %s", e)
        return None


def _store_entity(
    detail: CompanyDetail,
    city_fips: str,
    db_conn,
) -> None:
    """Store a resolved entity in the local cache."""
    try:
        cur = db_conn.cursor()
        cur.execute(
            """INSERT INTO business_entities
               (city_fips, entity_name, entity_number, jurisdiction_code,
                entity_type, current_status, incorporation_date, dissolution_date,
                registered_address, agent_name, agent_address, opencorporates_url,
                raw_response, source_url, source_publisher, source_tier,
                retrieved_at, confidence_score)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (entity_number, jurisdiction_code)
               WHERE entity_number IS NOT NULL
               DO UPDATE SET
                   entity_name = EXCLUDED.entity_name,
                   entity_type = EXCLUDED.entity_type,
                   current_status = EXCLUDED.current_status,
                   agent_name = EXCLUDED.agent_name,
                   agent_address = EXCLUDED.agent_address,
                   raw_response = EXCLUDED.raw_response,
                   retrieved_at = EXCLUDED.retrieved_at,
                   updated_at = NOW()
               RETURNING id""",
            (
                city_fips,
                detail.name,
                detail.company_number,
                detail.jurisdiction_code,
                detail.company_type,
                detail.current_status,
                detail.incorporation_date,
                detail.dissolution_date,
                detail.registered_address,
                detail.agent_name,
                detail.agent_address,
                detail.opencorporates_url,
                json.dumps(detail.raw_response) if detail.raw_response else None,
                detail.opencorporates_url or "https://api.opencorporates.com",
                detail.source_publisher or "California Secretary of State",
                1,  # source_tier
                detail.source_retrieved_at or datetime.now(timezone.utc).isoformat(),
                None,  # confidence_score set by match, not by storage
            ),
        )
        result = cur.fetchone()
        entity_id = result[0] if result else None

        # Store officers
        if entity_id and detail.officers:
            for officer in detail.officers:
                cur.execute(
                    """INSERT INTO business_entity_officers
                       (business_entity_id, officer_name, position,
                        start_date, end_date, is_inactive,
                        opencorporates_officer_id, source_url, retrieved_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT DO NOTHING""",
                    (
                        entity_id,
                        officer.name,
                        officer.position,
                        officer.start_date,
                        officer.end_date,
                        officer.is_inactive,
                        officer.opencorporates_id,
                        detail.opencorporates_url or "https://api.opencorporates.com",
                        detail.source_retrieved_at or datetime.now(timezone.utc).isoformat(),
                    ),
                )

        db_conn.commit()
        logger.info("Cached entity: %s (%s)", detail.name, detail.company_number)

    except Exception as e:
        logger.warning("Failed to cache entity: %s", e)
        try:
            db_conn.rollback()
        except Exception:
            pass


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(
        description="OpenCorporates business entity resolution"
    )
    parser.add_argument("--search", help="Search for a company by name")
    parser.add_argument("--detail", help="Get company details by CA SOS number")
    parser.add_argument("--officers", help="Search for officers by name")
    parser.add_argument("--resolve", action="store_true",
                        help="Resolve entity-like donor names from database")
    parser.add_argument("--budget", action="store_true",
                        help="Show API budget status")
    parser.add_argument("--city-fips", default=DEFAULT_FIPS,
                        help="City FIPS code (default: Richmond 0660620)")
    parser.add_argument("--jurisdiction", default=DEFAULT_JURISDICTION,
                        help="Jurisdiction code (default: us_ca)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be resolved without making API calls")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    tracker = RateLimitTracker()

    if args.budget:
        print(tracker.budget_status())
        return

    if args.search:
        results = search_company(args.search, args.jurisdiction, rate_tracker=tracker)
        print(f"\n{len(results)} results for '{args.search}':\n")
        for r in results:
            status = r.current_status or "Unknown"
            print(f"  {r.name} ({r.company_type or '?'}) — {status}")
            if r.company_number:
                print(f"    CA SOS #: {r.company_number}")
            if r.registered_address:
                print(f"    Address: {r.registered_address}")
            print()
        print(tracker.budget_status())
        return

    if args.detail:
        detail = get_company(args.detail, args.jurisdiction, rate_tracker=tracker)
        if detail:
            print(f"\n{detail.name}")
            print(f"  Type: {detail.company_type}")
            print(f"  Status: {detail.current_status}")
            print(f"  CA SOS #: {detail.company_number}")
            print(f"  Agent: {detail.agent_name}")
            if detail.officers:
                print(f"\n  Officers ({len(detail.officers)}):")
                for o in detail.officers:
                    status = " (inactive)" if o.is_inactive else ""
                    print(f"    {o.name} — {o.position}{status}")
        else:
            print(f"No company found for {args.detail}")
        print(f"\n{tracker.budget_status()}")
        return

    if args.officers:
        results = search_officers(args.officers, args.jurisdiction, rate_tracker=tracker)
        print(f"\n{len(results)} officer records for '{args.officers}':\n")
        for o in results:
            status = " (inactive)" if o.is_inactive else ""
            print(f"  {o.name} — {o.position}{status}")
            if o.company_name:
                print(f"    at {o.company_name} ({o.company_number})")
            print()
        print(tracker.budget_status())
        return

    if args.resolve:
        print("Entity resolution requires database connection.")
        print("Use --search or --detail for standalone lookups.")
        print("Full resolution pipeline will be run via data_sync.py.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
