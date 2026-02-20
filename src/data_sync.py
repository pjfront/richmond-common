"""
Richmond Transparency Project — Unified Data Source Sync

Syncs external data sources to Supabase with logging and observability.
Each sync creates a data_sync_log entry for tracking freshness.

Supported sources:
  - netfile: Local campaign contributions (NetFile Connect2 API)
  - calaccess: State PAC/IE contributions (CAL-ACCESS bulk download)
  - escribemeetings: Meeting agendas and documents
  - archive_center: Approved meeting minutes

Usage:
  python data_sync.py --source netfile
  python data_sync.py --source calaccess
  python data_sync.py --source netfile --triggered-by n8n
  python data_sync.py --source netfile --sync-type full
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from db import (
    get_connection,
    create_sync_log,
    complete_sync_log,
    load_contributions_to_db,
    RICHMOND_FIPS,
)


def sync_netfile(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync contributions from NetFile Connect2 API to Supabase.

    For incremental syncs, checks for new contributions since the last sync.
    For full syncs, downloads all contributions.
    """
    from netfile_client import fetch_contributions, normalize_contributions

    print("  Fetching contributions from NetFile API...")
    raw_contributions = fetch_contributions()
    contributions = normalize_contributions(raw_contributions)
    print(f"  Fetched {len(contributions):,} contribution records")

    print("  Loading into database...")
    stats = load_contributions_to_db(conn, contributions, city_fips=city_fips)

    return {
        "records_fetched": len(contributions),
        "records_new": stats["contributions"],
        "records_updated": 0,
        "donors_created": stats["donors"],
        "committees_created": stats["committees"],
        "skipped": stats["skipped"],
    }


def sync_calaccess(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync contributions from CAL-ACCESS bulk data to Supabase.

    Downloads the full bulk ZIP (~1.5GB) and processes Richmond-related
    contributions. This is a heavy operation — run monthly.
    """
    from calaccess_client import (
        download_bulk_zip,
        load_richmond_filers,
        search_contributions,
    )

    if sync_type == "full":
        print("  Downloading CAL-ACCESS bulk ZIP (this takes a while)...")
        zip_path = download_bulk_zip()
        print(f"  Downloaded to {zip_path}")

    print("  Loading Richmond filer index...")
    filers = load_richmond_filers()
    print(f"  Found {len(filers)} Richmond-area filers")

    print("  Searching for contributions...")
    contributions = search_contributions(filers)
    print(f"  Found {len(contributions):,} contributions")

    print("  Loading into database...")
    stats = load_contributions_to_db(conn, contributions, city_fips=city_fips)

    return {
        "records_fetched": len(contributions),
        "records_new": stats["contributions"],
        "records_updated": 0,
        "donors_created": stats["donors"],
        "committees_created": stats["committees"],
        "skipped": stats["skipped"],
    }


def sync_escribemeetings(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Check eSCRIBE for upcoming meetings and scrape new agenda packets.

    For incremental: only checks upcoming meetings in the next 14 days.
    For full: scans the full date range (2020-present).
    """
    from escribemeetings_scraper import (
        create_session,
        discover_meetings,
        scrape_meeting,
    )
    from db import ingest_document

    session = create_session()

    if sync_type == "full":
        print("  Discovering all meetings from eSCRIBE...")
        meetings = discover_meetings(session)
    else:
        print("  Checking eSCRIBE for upcoming meetings...")
        meetings = discover_meetings(session)
        # Filter to upcoming 14 days
        from datetime import timedelta
        today = datetime.now().date()
        cutoff = today + timedelta(days=14)
        meetings = [
            m for m in meetings
            if m.get("meeting_date") and today <= datetime.strptime(m["meeting_date"], "%Y-%m-%d").date() <= cutoff
        ]

    print(f"  Found {len(meetings)} meetings to process")

    new_count = 0
    for meeting in meetings:
        meeting_date = meeting.get("meeting_date", "unknown")
        # Check if we already have this meeting's raw data
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id FROM documents
                   WHERE city_fips = %s AND source_type = 'escribemeetings'
                     AND source_identifier = %s""",
                (city_fips, f"escribemeetings_{meeting_date}"),
            )
            if cur.fetchone():
                continue  # Already have this meeting

        print(f"  Scraping {meeting_date}...")
        try:
            data = scrape_meeting(session, meeting)
            raw_bytes = json.dumps(data, indent=2).encode("utf-8")
            ingest_document(
                conn,
                city_fips=city_fips,
                source_type="escribemeetings",
                raw_content=raw_bytes,
                credibility_tier=1,
                source_url=data.get("meeting_url"),
                source_identifier=f"escribemeetings_{meeting_date}",
                mime_type="application/json",
                metadata={
                    "meeting_date": meeting_date,
                    "meeting_name": data.get("meeting_name"),
                    "item_count": len(data.get("items", [])),
                    "pipeline": "data_sync",
                },
            )
            new_count += 1
        except Exception as e:
            print(f"  ERROR scraping {meeting_date}: {e}")

    return {
        "records_fetched": len(meetings),
        "records_new": new_count,
        "records_updated": 0,
    }


SYNC_SOURCES = {
    "netfile": sync_netfile,
    "calaccess": sync_calaccess,
    "escribemeetings": sync_escribemeetings,
}


def run_sync(
    source: str,
    city_fips: str = RICHMOND_FIPS,
    sync_type: str = "incremental",
    triggered_by: str = "manual",
    pipeline_run_id: str = None,
) -> dict:
    """Run a data sync for the specified source.

    Creates a data_sync_log entry, runs the sync, and updates the log.
    Returns a summary dict.
    """
    if source not in SYNC_SOURCES:
        raise ValueError(f"Unknown source '{source}'. Available: {', '.join(SYNC_SOURCES)}")

    start_time = time.time()
    conn = get_connection()

    print(f"\n{'='*60}")
    print(f"Data Sync: {source}")
    print(f"Type: {sync_type} | Triggered by: {triggered_by}")
    print(f"{'='*60}\n")

    sync_log_id = create_sync_log(
        conn,
        city_fips=city_fips,
        source=source,
        sync_type=sync_type,
        triggered_by=triggered_by,
        pipeline_run_id=pipeline_run_id,
    )
    print(f"Sync log: {sync_log_id}")

    try:
        sync_fn = SYNC_SOURCES[source]
        result = sync_fn(conn, city_fips, sync_type, sync_log_id)

        execution_time = time.time() - start_time
        complete_sync_log(
            conn,
            sync_log_id=sync_log_id,
            records_fetched=result.get("records_fetched"),
            records_new=result.get("records_new"),
            records_updated=result.get("records_updated"),
            metadata={"execution_seconds": round(execution_time, 2), **result},
        )

        print(f"\n{'='*60}")
        print(f"Sync complete: {source}")
        print(f"  Fetched: {result.get('records_fetched', 0)}")
        print(f"  New: {result.get('records_new', 0)}")
        print(f"  Time: {execution_time:.1f}s")
        print(f"{'='*60}")

        return {"sync_log_id": str(sync_log_id), "status": "completed", **result}

    except Exception as e:
        execution_time = time.time() - start_time
        print(f"\nERROR: Sync failed after {execution_time:.1f}s: {e}")
        complete_sync_log(
            conn,
            sync_log_id=sync_log_id,
            error_message=str(e),
        )
        return {"sync_log_id": str(sync_log_id), "status": "failed", "error": str(e)}
    finally:
        conn.close()


# ── CLI ──────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Richmond Transparency Project — Data Source Sync",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available sources: {', '.join(SYNC_SOURCES)}

Examples:
  python data_sync.py --source netfile
  python data_sync.py --source calaccess --sync-type full
  python data_sync.py --source escribemeetings --triggered-by n8n
        """,
    )
    parser.add_argument("--source", required=True, choices=list(SYNC_SOURCES), help="Data source to sync")
    parser.add_argument("--sync-type", choices=["full", "incremental"], default="incremental", help="Sync type")
    parser.add_argument("--triggered-by", default="manual", help="What triggered this sync")
    parser.add_argument("--city-fips", default=RICHMOND_FIPS, help="City FIPS code")
    parser.add_argument("--pipeline-run-id", help="GitHub Actions run ID or n8n execution ID")
    args = parser.parse_args()

    pipeline_run_id = args.pipeline_run_id or os.getenv("GITHUB_RUN_ID")

    result = run_sync(
        source=args.source,
        city_fips=args.city_fips,
        sync_type=args.sync_type,
        triggered_by=args.triggered_by,
        pipeline_run_id=pipeline_run_id,
    )

    print(f"\n::group::Sync Summary")
    print(json.dumps(result, indent=2, default=str))
    print(f"::endgroup::")

    if result.get("status") == "failed":
        sys.exit(1)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    main()
