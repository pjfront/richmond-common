"""
Batch conflict scanner — run scan_meeting_db across all meetings.

Resolves ConflictFlag name/number fields to database UUIDs and saves
to conflict_flags table via save_conflict_flag().

Usage:
  cd src && python3 batch_scan.py
  cd src && python3 batch_scan.py --dry-run
  cd src && python3 batch_scan.py --meeting-id <uuid>
  cd src && python3 batch_scan.py --validate   # compare v2 vs existing flags
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from collections import Counter
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection, save_conflict_flag, supersede_flags_for_meeting, create_scan_run, complete_scan_run
from conflict_scanner import (
    scan_meeting_db, ScanResult, prefilter_contributions,
    _fetch_contributions_from_db, _fetch_form700_interests_from_db,
)

DEFAULT_FIPS = "0660620"


def _fresh_conn():
    """Get a fresh database connection."""
    return get_connection()


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

        # Try matching after stripping parenthetical suffixes like
        # "(sitting council member)" or "(not a current council member)"
        # that scan_meeting_json adds to council_member labels
        import re
        base_name = re.sub(r'\s*\(.*\)\s*$', '', name).strip()
        if base_name != name:
            cur.execute(
                "SELECT id FROM officials WHERE LOWER(name) = LOWER(%s) AND city_fips = %s",
                (base_name, city_fips),
            )
            row = cur.fetchone()
            if row:
                cache[name] = row[0]
                return row[0]

    cache[name] = None
    return None


def resolve_agenda_item_id(
    conn, meeting_id: str, item_number: str | None, cache: dict
) -> uuid.UUID | None:
    """Resolve an agenda item number to its UUID within a meeting."""
    if item_number is None:
        return None

    cache_key = (meeting_id, item_number)
    if cache_key in cache:
        return cache[cache_key]

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM agenda_items WHERE meeting_id = %s AND item_number = %s",
            (meeting_id, item_number),
        )
        row = cur.fetchone()
        if row:
            cache[cache_key] = row[0]
            return row[0]

    cache[cache_key] = None
    return None


def run_batch_scan(
    city_fips: str = DEFAULT_FIPS,
    dry_run: bool = False,
    single_meeting_id: str | None = None,
    scan_mode: str = "retrospective",
):
    conn = _fresh_conn()

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

    # Pre-load contributions and form700 interests once for the entire batch
    print("Loading contributions and Form 700 interests...")
    raw_contributions = _fetch_contributions_from_db(conn, city_fips)
    contributions = prefilter_contributions(raw_contributions)
    form700_interests = _fetch_form700_interests_from_db(conn, city_fips)
    print(f"  {len(raw_contributions):,} contributions -> {len(contributions):,} after prefilter, {len(form700_interests):,} Form 700 interests")

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
    consecutive_errors = 0
    tier_counts: Counter = Counter()  # tier -> count
    type_counts: Counter = Counter()  # flag_type -> count
    start_time = time.time()

    for i, (meeting_id, meeting_date) in enumerate(meetings, 1):
        try:
            # Reconnect every 100 meetings to prevent stale connections
            if i % 100 == 0:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = _fresh_conn()

            result = scan_meeting_db(
                conn, str(meeting_id), city_fips,
                contributions=contributions,
                form700_interests=form700_interests,
            )
            meetings_scanned += 1
            consecutive_errors = 0

            if not dry_run:
                # Supersede old flags for every scanned meeting (including 0-flag results)
                # Without this, meetings where v2 finds 0 flags keep their old flags active
                supersede_flags_for_meeting(conn, meeting_id, scan_run_id, scan_mode)

            if result.flags:
                meetings_with_flags += 1

                for flag in result.flags:
                    official_id = resolve_official_id(conn, flag.council_member, city_fips, official_cache)
                    item_id = resolve_agenda_item_id(conn, str(meeting_id), flag.agenda_item_number, item_cache)

                    if official_id is None:
                        total_skipped += 1
                        continue

                    tier_counts[flag.publication_tier] += 1
                    type_counts[flag.flag_type] += 1

                    if dry_run:
                        print(f"  [DRY] {meeting_date} | {flag.council_member} | {flag.flag_type} | T{flag.publication_tier} | {flag.confidence:.0%} | {flag.agenda_item_title[:60]}")
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
                            publication_tier=flag.publication_tier,
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
            consecutive_errors += 1
            print(f"  ERROR scanning meeting {meeting_id} ({meeting_date}): {e}", file=sys.stderr)
            # Always get a fresh connection after an error
            try:
                conn.close()
            except Exception:
                pass
            conn = _fresh_conn()
            if consecutive_errors >= 10:
                print("  FATAL: 10 consecutive errors. Stopping.", file=sys.stderr)
                break

    # Complete the scan run using the existing helper
    elapsed = time.time() - start_time
    tier_dict = {f"tier{k}": v for k, v in sorted(tier_counts.items())}
    if not dry_run and scan_run_id:
        complete_scan_run(
            conn,
            scan_run_id=scan_run_id,
            flags_found=total_flags,
            flags_by_tier=tier_dict,
            clean_items_count=meetings_scanned - meetings_with_flags,
            enriched_items_count=meetings_with_flags,
            execution_time_seconds=elapsed,
            metadata={
                "meetings_scanned": meetings_scanned,
                "total_flags": total_flags,
                "skipped": total_skipped,
                "errors": errors,
                "tier_counts": tier_dict,
                "type_counts": dict(type_counts),
            },
            error_message=f"{errors} meetings failed" if errors else None,
        )

    if dry_run:
        elapsed = time.time() - start_time
    print(f"\n{'DRY RUN ' if dry_run else ''}BATCH SCAN COMPLETE")
    print(f"  Meetings scanned: {meetings_scanned}/{len(meetings)}")
    print(f"  Meetings with flags: {meetings_with_flags}")
    print(f"  Total flags: {total_flags}")
    print(f"  By tier: {dict(sorted(tier_counts.items()))}")
    print(f"  By type: {dict(type_counts.most_common())}")
    print(f"  Skipped (unresolved official): {total_skipped}")
    print(f"  Errors: {errors}")
    print(f"  Time: {elapsed:.1f}s")
    if not dry_run:
        print(f"  Scan run ID: {scan_run_id}")

    conn.close()


def run_validation(city_fips: str = DEFAULT_FIPS, single_meeting_id: str | None = None):
    """Compare existing DB flags against what v2 scanner would produce.

    Runs a dry-run scan and compares against existing is_current=TRUE
    flags in the database. Produces a structured validation report
    showing the delta.
    """
    conn = _fresh_conn()

    # Step 1: Count existing flags in the database
    with conn.cursor() as cur:
        # Overall counts
        cur.execute(
            """SELECT COUNT(*), flag_type,
                      COUNT(*) FILTER (WHERE confidence >= 0.7) AS high_conf,
                      COUNT(*) FILTER (WHERE confidence >= 0.5 AND confidence < 0.7) AS mid_conf,
                      COUNT(*) FILTER (WHERE confidence < 0.5) AS low_conf
               FROM conflict_flags
               WHERE city_fips = %s AND is_current = TRUE
               GROUP BY flag_type
               ORDER BY flag_type""",
            (city_fips,),
        )
        existing_by_type = {}
        existing_total = 0
        existing_high = 0
        existing_mid = 0
        existing_low = 0
        for count, flag_type, high, mid, low in cur.fetchall():
            existing_by_type[flag_type] = {
                "total": count, "high_conf": high, "mid_conf": mid, "low_conf": low,
            }
            existing_total += count
            existing_high += high
            existing_mid += mid
            existing_low += low

        # Count meetings with flags
        cur.execute(
            """SELECT COUNT(DISTINCT meeting_id)
               FROM conflict_flags
               WHERE city_fips = %s AND is_current = TRUE""",
            (city_fips,),
        )
        existing_meetings_with_flags = cur.fetchone()[0]

        # Get all meetings
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

    print(f"=== SCANNER V2 VALIDATION REPORT ===\n")
    print(f"EXISTING FLAGS (is_current=TRUE):")
    print(f"  Total: {existing_total}")
    print(f"  High confidence (>=0.7): {existing_high}")
    print(f"  Mid confidence (0.5-0.7): {existing_mid}")
    print(f"  Low confidence (<0.5): {existing_low}")
    print(f"  Meetings with flags: {existing_meetings_with_flags}")
    print(f"  By type: {json.dumps(existing_by_type, indent=4)}")
    print()

    # Pre-load contributions and form700 interests once
    print("Loading contributions and Form 700 interests...")
    raw_contributions = _fetch_contributions_from_db(conn, city_fips)
    contributions = prefilter_contributions(raw_contributions)
    form700_interests = _fetch_form700_interests_from_db(conn, city_fips)
    print(f"  {len(raw_contributions):,} contributions -> {len(contributions):,} after prefilter, {len(form700_interests):,} Form 700 interests")

    # Step 2: Run v2 scanner in dry-run mode
    print(f"Running v2 scanner across {len(meetings)} meetings...")
    v2_total = 0
    v2_tier_counts: Counter = Counter()
    v2_type_counts: Counter = Counter()
    v2_confidence_buckets: Counter = Counter()  # 'high'/'mid'/'low'
    v2_meetings_with_flags = 0
    v2_skipped = 0
    errors = 0
    consecutive_errors = 0

    official_cache: dict = {}
    start_time = time.time()

    for i, (meeting_id, meeting_date) in enumerate(meetings, 1):
        try:
            if i % 100 == 0:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = _fresh_conn()

            result = scan_meeting_db(
                conn, str(meeting_id), city_fips,
                contributions=contributions,
                form700_interests=form700_interests,
            )
            consecutive_errors = 0

            if result.flags:
                v2_meetings_with_flags += 1

            for flag in result.flags:
                # Check if official can be resolved (same as production)
                official_id = resolve_official_id(conn, flag.council_member, city_fips, official_cache)
                if official_id is None:
                    v2_skipped += 1
                    continue

                v2_total += 1
                v2_tier_counts[flag.publication_tier] += 1
                v2_type_counts[flag.flag_type] += 1
                if flag.confidence >= 0.7:
                    v2_confidence_buckets["high"] += 1
                elif flag.confidence >= 0.5:
                    v2_confidence_buckets["mid"] += 1
                else:
                    v2_confidence_buckets["low"] += 1

            if i % 50 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed
                remaining = (len(meetings) - i) / rate
                print(f"  [{i}/{len(meetings)}] {v2_total} flags | {elapsed:.0f}s | ~{remaining:.0f}s remaining")

        except Exception as e:
            errors += 1
            consecutive_errors += 1
            print(f"  ERROR: {meeting_id} ({meeting_date}): {e}", file=sys.stderr)
            try:
                conn.close()
            except Exception:
                pass
            conn = _fresh_conn()
            if consecutive_errors >= 10:
                print("  FATAL: 10 consecutive errors.", file=sys.stderr)
                break

    elapsed = time.time() - start_time

    # Step 3: Print comparison report
    print(f"\nV2 SCANNER RESULTS:")
    print(f"  Total flags: {v2_total}")
    print(f"  High confidence (>=0.7): {v2_confidence_buckets.get('high', 0)}")
    print(f"  Mid confidence (0.5-0.7): {v2_confidence_buckets.get('mid', 0)}")
    print(f"  Low confidence (<0.5): {v2_confidence_buckets.get('low', 0)}")
    print(f"  Meetings with flags: {v2_meetings_with_flags}")
    print(f"  By tier: {dict(sorted(v2_tier_counts.items()))}")
    print(f"  By type: {dict(v2_type_counts.most_common())}")
    print(f"  Skipped (unresolved official): {v2_skipped}")
    print(f"  Errors: {errors}")
    print(f"  Time: {elapsed:.1f}s")

    # Delta analysis
    print(f"\n=== DELTA ANALYSIS ===")
    delta = v2_total - existing_total
    if existing_total > 0:
        pct = (delta / existing_total) * 100
        print(f"  Flag count change: {existing_total} → {v2_total} ({delta:+d}, {pct:+.1f}%)")
    else:
        print(f"  Flag count change: {existing_total} → {v2_total} ({delta:+d})")

    high_delta = v2_confidence_buckets.get("high", 0) - existing_high
    print(f"  High-confidence change: {existing_high} → {v2_confidence_buckets.get('high', 0)} ({high_delta:+d})")
    mid_delta = v2_confidence_buckets.get("mid", 0) - existing_mid
    print(f"  Mid-confidence change: {existing_mid} → {v2_confidence_buckets.get('mid', 0)} ({mid_delta:+d})")
    low_delta = v2_confidence_buckets.get("low", 0) - existing_low
    print(f"  Low-confidence change: {existing_low} → {v2_confidence_buckets.get('low', 0)} ({low_delta:+d})")

    meetings_delta = v2_meetings_with_flags - existing_meetings_with_flags
    print(f"  Meetings with flags: {existing_meetings_with_flags} → {v2_meetings_with_flags} ({meetings_delta:+d})")

    if existing_total > 0 and delta < 0:
        reduction_pct = abs(delta) / existing_total * 100
        print(f"\n  PRECISION IMPROVEMENT: {reduction_pct:.1f}% reduction in total flags")
        if existing_high > 0:
            high_retention = v2_confidence_buckets.get("high", 0) / existing_high * 100
            print(f"  High-confidence retention: {high_retention:.1f}%")

    # Save report to file
    report_path = Path(__file__).parent / "data" / "validation_reports"
    report_path.mkdir(parents=True, exist_ok=True)
    report_file = report_path / f"v2_validation_{date.today().isoformat()}.json"
    report_data = {
        "date": date.today().isoformat(),
        "city_fips": city_fips,
        "meetings_scanned": len(meetings),
        "errors": errors,
        "execution_seconds": round(elapsed, 1),
        "existing": {
            "total": existing_total,
            "high_conf": existing_high,
            "mid_conf": existing_mid,
            "low_conf": existing_low,
            "meetings_with_flags": existing_meetings_with_flags,
            "by_type": existing_by_type,
        },
        "v2": {
            "total": v2_total,
            "high_conf": v2_confidence_buckets.get("high", 0),
            "mid_conf": v2_confidence_buckets.get("mid", 0),
            "low_conf": v2_confidence_buckets.get("low", 0),
            "meetings_with_flags": v2_meetings_with_flags,
            "by_tier": dict(sorted(v2_tier_counts.items())),
            "by_type": dict(v2_type_counts.most_common()),
            "skipped": v2_skipped,
        },
        "delta": {
            "total": delta,
            "total_pct": round((delta / existing_total * 100), 1) if existing_total else 0,
            "high_conf": high_delta,
            "mid_conf": mid_delta,
            "low_conf": low_delta,
        },
    }
    report_file.write_text(json.dumps(report_data, indent=2))
    print(f"\n  Report saved: {report_file}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch conflict scanner")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be saved without writing")
    parser.add_argument("--validate", action="store_true", help="Compare v2 scanner output against existing DB flags")
    parser.add_argument("--meeting-id", help="Scan a single meeting by UUID")
    parser.add_argument("--city-fips", default=DEFAULT_FIPS, help="City FIPS code")
    args = parser.parse_args()

    if args.validate:
        run_validation(city_fips=args.city_fips, single_meeting_id=args.meeting_id)
    else:
        run_batch_scan(
            city_fips=args.city_fips,
            dry_run=args.dry_run,
            single_meeting_id=args.meeting_id,
        )
