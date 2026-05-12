"""
nextrequest pipeline module — extracted from data_sync.py (Phase 2.3).

Each sync_X function is registered in data_sync.SYNC_SOURCES and dispatched
by data_sync.run_sync. Module-level helpers (nextrequest-specific) live alongside.
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


def sync_nextrequest(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync CPRA requests from NextRequest portal.

    Uses NextRequest's public client JSON API (no Playwright needed).
    For incremental: fetches requests since last sync.
    For full: fetches all requests with skip_details for speed.
    """
    from nextrequest_scraper import scrape_all, save_to_db

    print("  Fetching from NextRequest client API...")
    since_date = None
    if sync_type == "incremental":
        # Find last successful sync date
        with conn.cursor() as cur:
            cur.execute(
                """SELECT MAX(completed_at) FROM data_sync_log
                   WHERE source = 'nextrequest' AND status = 'completed'
                     AND city_fips = %s""",
                (city_fips,),
            )
            row = cur.fetchone()
            if row and row[0]:
                since_date = row[0].strftime("%Y-%m-%d")

    # For full sync, skip per-request detail calls (much faster).
    # For incremental, fetch details to get closed_date from timeline.
    skip_details = sync_type == "full" and since_date is None

    results = scrape_all(
        since_date=since_date,
        download_docs=False,
        extract_text=False,
        skip_details=skip_details,
    )

    print(f"  Fetched {results['stats']['total_found']} requests"
          + (f", {results['stats']['details_scraped']} with details"
             if results['stats']['details_scraped'] > 0 else ""))

    print("  Saving to database...")
    stats = save_to_db(conn, results, city_fips)

    return {
        "records_fetched": results["stats"]["total_found"],
        "records_new": stats["requests_saved"],
        "records_updated": 0,
        "documents_saved": stats["documents_saved"],
    }


