"""
calaccess pipeline module — extracted from data_sync.py (Phase 2.3).

Each sync_X function is registered in data_sync.SYNC_SOURCES and dispatched
by data_sync.run_sync. Module-level helpers (calaccess-specific) live alongside.
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


def sync_calaccess(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync contributions and independent expenditures from CAL-ACCESS bulk data.

    Downloads the full bulk ZIP (~1.5GB) and processes Richmond-related
    contributions (RCPT_CD) and independent expenditures (EXPN_CD).
    IE data connects PACs (e.g., Chevron's committees) to specific candidates.
    This is a heavy operation — run monthly.
    """
    from calaccess_client import (
        download_bulk_data,
        find_richmond_filers,
        find_richmond_filing_ids,
        get_richmond_contributions,
        get_richmond_expenditures,
    )

    print("  Downloading CAL-ACCESS bulk ZIP (uses cache if available)...")
    zip_path = download_bulk_data(force=(sync_type == "full"))
    print(f"  ZIP at {zip_path}")

    print("  Finding Richmond filers...")
    filers = find_richmond_filers(zip_path)
    print(f"  Found {len(filers)} Richmond-area filers")

    print("  Finding Richmond filing IDs...")
    filing_map = find_richmond_filing_ids(zip_path)

    print("  Extracting contributions...")
    contributions = get_richmond_contributions(zip_path, filing_map=filing_map)
    print(f"  Found {len(contributions):,} contributions")

    print("  Loading contributions into database...")
    stats = load_contributions_to_db(conn, contributions, city_fips=city_fips)

    print("  Extracting independent expenditures...")
    expenditures = get_richmond_expenditures(zip_path, filing_map=filing_map)
    print(f"  Found {len(expenditures):,} independent expenditures")

    print("  Loading expenditures into database...")
    exp_stats = load_expenditures_to_db(conn, expenditures, city_fips=city_fips)

    # Counter accuracy (Phase D-2, 2026-05-16): records_new now reflects
    # ACTUAL rows inserted, not "execute statements that ran." Both legs
    # of the sync — contributions (via load_contributions_to_db's existing
    # xmax=0 path) and expenditures (via load_expenditures_to_db's new
    # xmax=0 path after the migration-112 unique constraint) — return
    # honest insert/update counts. The pre-fix counter (loaded += 1)
    # inflated by 96% on the IE leg; cf. audit B1.
    return {
        "records_fetched": len(contributions) + len(expenditures),
        "records_new": stats["contributions"] + exp_stats["inserted"],
        "records_updated": stats.get("updated", 0) + exp_stats["updated"],
        "donors_created": stats["donors"],
        "committees_created": stats["committees"],
        "skipped": stats["skipped"] + exp_stats["skipped"],
        "expenditures_fetched": len(expenditures),
        "expenditures_inserted": exp_stats["inserted"],
        "expenditures_updated": exp_stats["updated"],
    }


