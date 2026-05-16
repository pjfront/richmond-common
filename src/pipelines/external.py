"""
external pipeline module — extracted from data_sync.py (Phase 2.3).

Each sync_X function is registered in data_sync.SYNC_SOURCES and dispatched
by data_sync.run_sync. Module-level helpers (external-specific) live alongside.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import psycopg2

from city_config import get_city_config, list_configured_cities
from db import (
    get_connection,
    create_sync_log,
    complete_sync_log,
    load_contributions_to_db,
    load_expenditures_to_db,
)
from pipeline_journal import PipelineJournal, check_anomalies

DEFAULT_FIPS = "0660620"


def sync_courts(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    **extra,
) -> dict:
    """Sync court records from Tyler Odyssey portal.

    Searches for officials, donors, and Form 700 filers by name.
    Stores discovered cases and cross-references against known entities.
    """
    from courts_scraper import lookup_entities

    print("  Running court records lookup...")
    result = lookup_entities(city_fips=city_fips)

    return {
        "records_fetched": result.get("names_searched", 0),
        "records_new": result.get("cases_saved", 0),
        "records_updated": result.get("cases_updated", 0),
        "matches_found": result.get("matches_found", 0),
    }


def sync_propublica(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync nonprofit organization data from ProPublica Nonprofit Explorer.

    Resolves donor employers against ProPublica's nonprofit database.
    Creates organization records and entity links for matched nonprofits.
    """
    from propublica_client import batch_resolve_employers
    from db import (
        load_organizations_to_db,
        load_entity_links_to_db,
        resolve_entity_link_ids,
    )

    # 1. Fetch distinct employer names from donors table
    with conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT employer FROM donors
               WHERE city_fips = %s
                 AND employer IS NOT NULL
                 AND employer != ''
               ORDER BY employer""",
            (city_fips,),
        )
        employers = [row[0] for row in cur.fetchall()]

    print(f"  Found {len(employers)} distinct employer names to resolve...")

    # 2. Resolve against ProPublica
    matches = batch_resolve_employers(employers, state="CA")
    print(f"  Matched {len(matches)} employers to nonprofits")

    if not matches:
        return {
            "records_fetched": len(employers),
            "records_new": 0,
            "records_updated": 0,
            "entities_resolved": 0,
        }

    # 3. Load matched organizations
    org_records = []
    for m in matches:
        org_records.append({
            "name": m["name"],
            "entity_number": str(m["ein"]),
            "entity_type": "nonprofit",
            "jurisdiction": "US",
            "status": "active" if m.get("has_filings") else None,
            "source": "propublica_990",
            "source_url": f"https://projects.propublica.org/nonprofits/organizations/{m['ein']}",
            "metadata": {
                "ntee_code": m.get("ntee_code"),
                "city": m.get("city"),
                "state": m.get("state"),
                "matched_employer": m.get("matched_employer"),
                "match_confidence": m.get("confidence"),
            },
        })

    org_stats = load_organizations_to_db(conn, org_records, city_fips=city_fips)
    print(f"  Organizations: {org_stats['inserted']} new, {org_stats['updated']} updated")

    # 4. Create entity links (employer name -> organization)
    # The "person" here is the employer name — it links to the org.
    # For ProPublica, we don't have individual officer names from the API.
    # The link represents "this donor works at this nonprofit org."
    link_records = []
    with conn.cursor() as cur:
        for m in matches:
            # Find the organization we just loaded
            cur.execute(
                """SELECT id FROM organizations
                   WHERE city_fips = %s AND source = 'propublica_990'
                     AND entity_number = %s""",
                (city_fips, str(m["ein"])),
            )
            org_row = cur.fetchone()
            if not org_row:
                continue

            # Find donors with this employer
            norm_employer = " ".join(m["matched_employer"].lower().split())
            cur.execute(
                """SELECT DISTINCT name, normalized_name FROM donors
                   WHERE city_fips = %s
                     AND normalized_employer = %s""",
                (city_fips, norm_employer),
            )
            for donor_row in cur.fetchall():
                link_records.append({
                    "person_name": donor_row[0],
                    "organization_id": org_row[0],
                    "role": "employee",
                    "role_detail": f"Employer: {m['matched_employer']}",
                    "confidence": m.get("confidence", 0.80),
                    "source": "propublica_990",
                    "source_url": f"https://projects.propublica.org/nonprofits/organizations/{m['ein']}",
                })

    link_stats = load_entity_links_to_db(conn, link_records, city_fips=city_fips)
    print(f"  Entity links: {link_stats['inserted']} new, {link_stats['updated']} updated")

    # 5. Resolve links to existing donor/official IDs
    resolve_stats = resolve_entity_link_ids(conn, city_fips=city_fips)
    print(f"  Resolved: {resolve_stats['donor_resolved']} donors, {resolve_stats['official_resolved']} officials")

    return {
        "records_fetched": len(employers),
        "records_new": org_stats["inserted"],
        "records_updated": org_stats["updated"],
        "entity_links_created": link_stats["inserted"],
        "entities_resolved": resolve_stats["donor_resolved"] + resolve_stats["official_resolved"],
    }


def sync_form803_behested(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    **kwargs,
) -> dict:
    """Sync FPPC Form 803 behested payment disclosures.

    Fetches from FPPC portal, loads to behested_payments table.
    """
    from fppc_form803_client import fetch_behested_payments
    from db import load_behested_to_db

    print(f"  Fetching behested payments from FPPC (sync_type={sync_type})...")

    payments = fetch_behested_payments(city_fips=city_fips)
    print(f"  Fetched {len(payments)} behested payment records")

    if not payments:
        return {"records_fetched": 0, "records_new": 0, "records_updated": 0}

    stats = load_behested_to_db(conn, payments, city_fips=city_fips)
    print(f"  Loaded: {stats['inserted']} new, {stats['updated']} updated, {stats['skipped']} skipped")

    return {
        "records_fetched": len(payments),
        "records_new": stats["inserted"],
        "records_updated": stats["updated"],
        "records_skipped": stats["skipped"],
    }


def sync_lobbyist_registrations(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    **kwargs,
) -> dict:
    """Sync lobbyist registration records.

    Fetches from City Clerk website and optionally CA SOS portal,
    loads to lobbyist_registrations table.
    """
    from lobbyist_client import fetch_lobbyist_registrations
    from db import load_lobbyists_to_db

    print(f"  Fetching lobbyist registrations (sync_type={sync_type})...")

    registrations = fetch_lobbyist_registrations(city_fips=city_fips)
    print(f"  Fetched {len(registrations)} lobbyist registration records")

    if not registrations:
        return {"records_fetched": 0, "records_new": 0, "records_updated": 0}

    stats = load_lobbyists_to_db(conn, registrations, city_fips=city_fips)
    print(f"  Loaded: {stats['inserted']} new, {stats['updated']} updated, {stats['skipped']} skipped")

    return {
        "records_fetched": len(registrations),
        "records_new": stats["inserted"],
        "records_updated": stats["updated"],
        "records_skipped": stats["skipped"],
    }


def sync_opencorporates(
    conn,
    city_fips: str = DEFAULT_FIPS,
    sync_type: str = "incremental",
    **kwargs,
) -> dict:
    """Resolve business entity names from donors against OpenCorporates.

    Finds entity-like donor names (LLC/Inc/Corp/etc), deduplicates,
    and resolves each against the OpenCorporates API with rate limiting.
    Requires OPENCORPORATES_API_TOKEN env var.
    """
    from opencorporates_client import (
        looks_like_entity, resolve_entity, normalize_entity_name,
        RateLimitTracker,
    )

    print(f"[opencorporates] Resolving business entities for {city_fips}...")

    # Find entity-like donor names
    cur = conn.cursor()
    cur.execute(
        """SELECT DISTINCT name FROM donors
           WHERE city_fips = %s AND name IS NOT NULL""",
        (city_fips,),
    )
    all_donors = [row[0] for row in cur.fetchall()]
    entity_names = [n for n in all_donors if looks_like_entity(n)]

    # Deduplicate by normalized name
    seen: dict[str, str] = {}
    for name in entity_names:
        norm = normalize_entity_name(name)
        if norm not in seen:
            seen[norm] = name

    unique_names = list(seen.values())
    print(f"  {len(entity_names)} entity-like donors → {len(unique_names)} unique after normalization")

    # Resolve each against OpenCorporates
    tracker = RateLimitTracker(db_conn=conn)
    resolved = 0
    skipped = 0
    rate_limited = 0

    for name in unique_names:
        allowed, reason = tracker.can_call()
        if not allowed:
            rate_limited += len(unique_names) - resolved - skipped
            print(f"  Rate limit reached: {reason}. {rate_limited} entities queued for next run.")
            break

        result = resolve_entity(
            name, city_fips=city_fips, rate_tracker=tracker, db_conn=conn,
        )
        if result.cached:
            skipped += 1
        elif result.matched:
            resolved += 1
        else:
            skipped += 1

    print(f"  Resolved: {resolved}, Cached: {skipped}, Rate-limited: {rate_limited}")
    print(f"  {tracker.budget_status()}")

    return {
        "records_fetched": len(unique_names),
        "records_new": resolved,
        "records_skipped": skipped,
        "rate_limited": rate_limited,
    }


