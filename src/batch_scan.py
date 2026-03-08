"""
Batch conflict scanner — run scan_meeting_db across all meetings.

Resolves ConflictFlag name/number fields to database UUIDs and saves
to conflict_flags table via save_conflict_flag().

Usage:
  cd src && python3 batch_scan.py
  cd src && python3 batch_scan.py --dry-run
  cd src && python3 batch_scan.py --meeting-id <uuid>
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection, save_conflict_flag, supersede_flags_for_meeting, create_scan_run, complete_scan_run
from conflict_scanner import scan_meeting_db, ScanResult

DEFAULT_FIPS = "0660620"


def resolve_official_id(conn, name: str, city_fips: str, cache: dict) -> uuid.UUID | None:
    """Resolve a council member name to an official UUID."""
    if name in cache:
        return cache[name]

    with conn.cursor() as cur:
        # Try exact match first
        cur.execute(
            "SELECT id FROM officials WHERE name = %s AND city_fips = %s",
            (name, city_fips),
        )
        row = cur.fetchone()
        if row:
            cache[name] = row[0]
            return row[0]

        # Try case-insensitive / partial match
        cur.execute(
            "SELECT id FROM officials WHERE LOWER(name) = LOWER(%s) AND city_fips = %s",
            (name, city_fips),
        )
        row = cur.fetchone()
        if row:
            cache[name] = row[0]
            return row[0]

    cache[name] = None
    return None


def resolve_agenda_item_id(conn, meeting_id: str, item_number: str, cache: dict) -> uuid.UUID | None:
    """Resolve an agenda item number within a meeting to its UUID."""
    key = (meeting_id, item_number)
    if key in cache:
        return cache[key]

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM agenda_items WHERE meeting_id = %s AND item_number = %s",
            (meeting_id, item_number),
        )
        row = cur.fetchone()
        if row:
            cache[key] = row[0]
            return row[0]

    cache[key] = None
    return None


def run_batch_scan(
    city_fips: str = DEFAULT_FIPS,
    dry_run: bool = False,
    single_meeting_id: str | None = None,
    scan_mode: str = "retrospective",
):
    conn = get_connection()

    # Get all meetings
    with conn.cursor() as cur:
        if single_meeting_id:
            cur.execute(
                "SELECT id, meeting_date FROM meetings WHERE id = %s AND city_fips = %s",
                (single_meeting_id, city_fips),
            )
        else:
            cur.execute(
                "SELECT id, meeting_date FROM meetings WHERE city_fips = %s ORDER BY meeting_date",
                (city_fips,),
            )
        meetings = cur.fetchall()

    print(f"Found {len(meetings)} meetings to scan")
    if not meetings:
        print("No meetings found. Exiting.")
        conn.close()
        return

    # Create a scan run record using the existing helper
    scan_run_id = None
    if not dry_run:
        scan_run_id = create_scan_run(
            conn,
            city_fips=city_fips,
            scan_mode=scan_mode,
            data_cutoff_date=date.today(),
            triggered_by="batch_scan",
        )

    # Caches for name/ID resolution
    official_cache: dict = {}
    item_cache: dict = {}

    total_flags = 0
    total_skipped = 0
    meetings_with_flags = 0
    meetings_scanned = 0
    errors = 0
    start_time = time.time()

    for i, (meeting_id, meeting_date) in enumerate(meetings, 1):
        try:
            result = scan_meeting_db(conn, str(meeting_id), city_fips)
            meetings_scanned += 1

            if result.flags:
                meetings_with_flags += 1

                if not dry_run:
                    # Supersede any existing flags for this meeting
                    supersede_flags_for_meeting(conn, meeting_id, scan_run_id, scan_mode)

                for flag in result.flags:
                    official_id = resolve_official_id(conn, flag.council_member, city_fips, official_cache)
                    item_id = resolve_agenda_item_id(conn, str(meeting_id), flag.agenda_item_number, item_cache)

                    if official_id is None:
                        total_skipped += 1
                        continue

                    if dry_run:
                        print(f"  [DRY] {meeting_date} | {flag.council_member} | {flag.flag_type} | {flag.confidence:.0%} | {flag.agenda_item_title[:60]}")
                    else:
                        save_conflict_flag(
                            conn,
                            city_fips=city_fips,
                            meeting_id=meeting_id,
                            scan_run_id=scan_run_id,
                            flag_type=flag.flag_type,
                            description=flag.description,
                            evidence=[{"text": e} for e in flag.evidence],
                            confidence=flag.confidence,
                            scan_mode=scan_mode,
                            data_cutoff_date=date.today(),
                            agenda_item_id=item_id,
                            official_id=official_id,
                            legal_reference=flag.legal_reference,
                        )

                    total_flags += 1

            # Progress update every 50 meetings
            if i % 50 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed
                remaining = (len(meetings) - i) / rate
                print(f"  [{i}/{len(meetings)}] {total_flags} flags so far | {elapsed:.0f}s elapsed | ~{remaining:.0f}s remaining")

        except Exception as e:
            errors += 1
            print(f"  ERROR scanning meeting {meeting_id} ({meeting_date}): {e}", file=sys.stderr)
            # Reconnect if the connection died
            try:
                conn.rollback()
            except Exception:
                conn = get_connection()

    # Complete the scan run using the existing helper
    elapsed = time.time() - start_time
    if not dry_run and scan_run_id:
        complete_scan_run(
            conn,
            scan_run_id=scan_run_id,
            flags_found=total_flags,
            flags_by_tier={},
            clean_items_count=meetings_scanned - meetings_with_flags,
            enriched_items_count=meetings_with_flags,
            execution_time_seconds=elapsed,
            metadata={
                "meetings_scanned": meetings_scanned,
                "total_flags": total_flags,
                "skipped": total_skipped,
                "errors": errors,
            },
            error_message=f"{errors} meetings failed" if errors else None,
        )

    if dry_run:
        elapsed = time.time() - start_time
    print(f"\n{'DRY RUN ' if dry_run else ''}BATCH SCAN COMPLETE")
    print(f"  Meetings scanned: {meetings_scanned}/{len(meetings)}")
    print(f"  Meetings with flags: {meetings_with_flags}")
    print(f"  Total flags saved: {total_flags}")
    print(f"  Skipped (unresolved official): {total_skipped}")
    print(f"  Errors: {errors}")
    print(f"  Time: {elapsed:.1f}s")
    if not dry_run:
        print(f"  Scan run ID: {scan_run_id}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch conflict scanner")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be saved without writing")
    parser.add_argument("--meeting-id", help="Scan a single meeting by UUID")
    parser.add_argument("--city-fips", default=DEFAULT_FIPS, help="City FIPS code")
    args = parser.parse_args()

    run_batch_scan(
        city_fips=args.city_fips,
        dry_run=args.dry_run,
        single_meeting_id=args.meeting_id,
    )
