"""
Batch conflict scanner v3 — run scan_meeting_db across all meetings.

Resolves ConflictFlag name/number fields to database UUIDs and saves
to conflict_flags table via save_conflict_flag(). Stores v3 metadata
(confidence_factors JSONB, scanner_version) for every flag.

Usage:
  cd src && python3 batch_scan.py
  cd src && python3 batch_scan.py --dry-run
  cd src && python3 batch_scan.py --meeting-id <uuid>
  cd src && python3 batch_scan.py --validate   # compare v3 scanner vs existing DB flags
  cd src && python3 -u batch_scan.py --validate --workers 8  # parallel validation
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection, save_conflict_flag, supersede_flags_for_meeting, create_scan_run, complete_scan_run
from conflict_scanner import (
    scan_meeting_db, ScanResult, prefilter_contributions,
    _fetch_contributions_from_db, _fetch_form700_interests_from_db,
    TIER_LABELS,
)

DEFAULT_FIPS = "0660620"
SCANNER_VERSION = 3

# Publication tier boundaries (must match conflict_scanner.py)
TIER_THRESHOLDS = {1: 0.85, 2: 0.70, 3: 0.50}


def _fresh_conn():
    """Get a fresh database connection."""
    return get_connection()


def _scan_single_meeting_worker(
    meeting_id: str, meeting_date: str, city_fips: str,
    contributions: list[dict], form700_interests: list[dict],
) -> tuple[str, str, ScanResult | None, str | None]:
    """Worker function for parallel scanning (O5).

    Each worker creates its own DB connection (required for process isolation).
    Returns (meeting_id, meeting_date, result, error_message).
    """
    conn = _fresh_conn()
    try:
        result = scan_meeting_db(
            conn, meeting_id, city_fips,
            contributions=contributions,
            form700_interests=form700_interests,
        )
        return (meeting_id, meeting_date, result, None)
    except Exception as e:
        return (meeting_id, meeting_date, None, str(e))
    finally:
        conn.close()


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
    workers: int = 1,
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

    print(f"Found {len(meetings)} meetings to scan (scanner v{SCANNER_VERSION})", flush=True)
    if not meetings:
        print("No meetings found. Exiting.", flush=True)
        conn.close()
        return

    # Pre-load contributions and form700 interests once for the entire batch
    print("Loading contributions and Form 700 interests...", flush=True)
    raw_contributions = _fetch_contributions_from_db(conn, city_fips)
    contributions = prefilter_contributions(raw_contributions)
    form700_interests = _fetch_form700_interests_from_db(conn, city_fips)
    print(f"  {len(raw_contributions):,} contributions -> {len(contributions):,} after prefilter, {len(form700_interests):,} Form 700 interests", flush=True)

    # Create a scan run record with v3 scanner version
    scan_run_id = None
    if not dry_run:
        scan_run_id = create_scan_run(
            conn,
            city_fips=city_fips,
            scan_mode=scan_mode,
            data_cutoff_date=date.today(),
            triggered_by="batch_scan",
            contributions_count=len(contributions),
            form700_count=len(form700_interests),
            scanner_version=str(SCANNER_VERSION),
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

    def _process_batch_result(meeting_id, meeting_date, result, error_msg):
        """Process a single meeting's scan result (shared by sequential and parallel paths)."""
        nonlocal total_flags, total_skipped, meetings_with_flags, meetings_scanned
        nonlocal errors, consecutive_errors

        if error_msg:
            errors += 1
            consecutive_errors += 1
            print(f"  ERROR scanning meeting {meeting_id} ({meeting_date}): {error_msg}", file=sys.stderr, flush=True)
            return

        meetings_scanned += 1
        consecutive_errors = 0

        if not dry_run:
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
                    print(f"  [DRY] {meeting_date} | {flag.council_member} | {flag.flag_type} | T{flag.publication_tier} | {flag.confidence:.0%} | {flag.agenda_item_title[:60]}", flush=True)
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
                        confidence_factors=flag.confidence_factors,
                        scanner_version=flag.scanner_version,
                    )

                total_flags += 1

    # O5: Parallel or sequential scanning
    if workers > 1 and len(meetings) > 1:
        print(f"Scanning with {workers} parallel workers...", flush=True)
        conn.close()  # Workers use their own connections

        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _scan_single_meeting_worker,
                    str(mid), str(mdate), city_fips,
                    contributions, form700_interests,
                ): (mid, mdate)
                for mid, mdate in meetings
            }

            conn = _fresh_conn()  # Re-open for result processing
            completed = 0
            for future in as_completed(futures):
                mid_str, mdate_str, result, error_msg = future.result()
                mid = uuid.UUID(mid_str) if isinstance(mid_str, str) else mid_str
                _process_batch_result(mid, mdate_str, result, error_msg)

                completed += 1
                if completed % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed
                    remaining = (len(meetings) - completed) / rate if rate > 0 else 0
                    print(f"  [{completed}/{len(meetings)}] {total_flags} flags so far | {elapsed:.0f}s elapsed | ~{remaining:.0f}s remaining", flush=True)

                if consecutive_errors >= 10:
                    print("  FATAL: 10 consecutive errors. Stopping.", file=sys.stderr, flush=True)
                    break
    else:
        # Sequential path (workers=1 or single meeting)
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
                _process_batch_result(meeting_id, meeting_date, result, None)

                if i % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = i / elapsed
                    remaining = (len(meetings) - i) / rate
                    print(f"  [{i}/{len(meetings)}] {total_flags} flags so far | {elapsed:.0f}s elapsed | ~{remaining:.0f}s remaining", flush=True)

            except Exception as e:
                _process_batch_result(meeting_id, meeting_date, None, str(e))
                try:
                    conn.close()
                except Exception:
                    pass
                conn = _fresh_conn()
                if consecutive_errors >= 10:
                    print("  FATAL: 10 consecutive errors. Stopping.", file=sys.stderr, flush=True)
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
                "scanner_version": SCANNER_VERSION,
                "meetings_scanned": meetings_scanned,
                "total_flags": total_flags,
                "skipped": total_skipped,
                "errors": errors,
                "tier_counts": tier_dict,
                "type_counts": dict(type_counts),
                "workers": workers,
            },
            error_message=f"{errors} meetings failed" if errors else None,
        )

    if dry_run:
        elapsed = time.time() - start_time
    print(f"\n{'DRY RUN ' if dry_run else ''}BATCH SCAN v{SCANNER_VERSION} COMPLETE", flush=True)
    print(f"  Meetings scanned: {meetings_scanned}/{len(meetings)}", flush=True)
    print(f"  Meetings with flags: {meetings_with_flags}", flush=True)
    print(f"  Total flags: {total_flags}", flush=True)
    print(f"  By tier: {dict(sorted(tier_counts.items()))}", flush=True)
    print(f"  By type: {dict(type_counts.most_common())}", flush=True)
    print(f"  Skipped (unresolved official): {total_skipped}", flush=True)
    print(f"  Errors: {errors}", flush=True)
    print(f"  Time: {elapsed:.1f}s ({workers} workers)", flush=True)
    if not dry_run:
        print(f"  Scan run ID: {scan_run_id}", flush=True)

    conn.close()


def _tier_label(tier: int) -> str:
    """Human-readable tier label."""
    try:
        return TIER_LABELS[tier]
    except (KeyError, IndexError):
        return {
            1: "High-Confidence Pattern",
            2: "Medium-Confidence Pattern",
            3: "Low-Confidence Pattern",
            4: "Internal",
        }.get(tier, f"Tier {tier}")


def run_validation(city_fips: str = DEFAULT_FIPS, single_meeting_id: str | None = None, workers: int = 1):
    """Compare v3 scanner output against existing DB flags.

    Runs the v3 scanner in dry-run mode and produces a structured
    validation report comparing against is_current=TRUE flags in the
    database. Includes v3-specific metrics: publication tier distribution,
    confidence factor breakdowns, corroboration statistics.
    """
    conn = _fresh_conn()

    # ── Step 1: Snapshot existing flags ──────────────────────────
    with conn.cursor() as cur:
        # By type with confidence buckets (using v3 tier thresholds)
        cur.execute(
            """SELECT flag_type, COUNT(*) AS total,
                      COUNT(*) FILTER (WHERE confidence >= 0.85) AS tier1,
                      COUNT(*) FILTER (WHERE confidence >= 0.70 AND confidence < 0.85) AS tier2,
                      COUNT(*) FILTER (WHERE confidence >= 0.50 AND confidence < 0.70) AS tier3,
                      COUNT(*) FILTER (WHERE confidence < 0.50) AS tier4,
                      COALESCE(AVG(confidence), 0) AS avg_conf
               FROM conflict_flags
               WHERE city_fips = %s AND is_current = TRUE
               GROUP BY flag_type
               ORDER BY flag_type""",
            (city_fips,),
        )
        existing_by_type = {}
        existing_totals = {"total": 0, "tier1": 0, "tier2": 0, "tier3": 0, "tier4": 0}
        for flag_type, total, t1, t2, t3, t4, avg_c in cur.fetchall():
            existing_by_type[flag_type] = {
                "total": total, "tier1": t1, "tier2": t2, "tier3": t3, "tier4": t4,
                "avg_confidence": round(float(avg_c), 3),
            }
            existing_totals["total"] += total
            existing_totals["tier1"] += t1
            existing_totals["tier2"] += t2
            existing_totals["tier3"] += t3
            existing_totals["tier4"] += t4

        # Scanner version distribution of existing flags
        cur.execute(
            """SELECT COALESCE(scanner_version, 2), COUNT(*)
               FROM conflict_flags
               WHERE city_fips = %s AND is_current = TRUE
               GROUP BY scanner_version ORDER BY scanner_version""",
            (city_fips,),
        )
        existing_versions = {str(v): c for v, c in cur.fetchall()}

        # Count meetings with flags
        cur.execute(
            """SELECT COUNT(DISTINCT meeting_id)
               FROM conflict_flags
               WHERE city_fips = %s AND is_current = TRUE""",
            (city_fips,),
        )
        existing_meetings_with_flags = cur.fetchone()[0]

        # Get meetings to scan
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

    # ── Print existing state ─────────────────────────────────────
    print(f"{'='*60}", flush=True)
    print(f"  SCANNER V3 VALIDATION REPORT", flush=True)
    print(f"  {date.today().isoformat()} | {city_fips} | {len(meetings)} meetings", flush=True)
    print(f"{'='*60}\n", flush=True)

    print(f"EXISTING FLAGS (is_current=TRUE):", flush=True)
    print(f"  Total: {existing_totals['total']}", flush=True)
    print(f"  Scanner versions in DB: {existing_versions}", flush=True)
    print(f"  Tier 1 (>=0.85 High-Confidence):   {existing_totals['tier1']}", flush=True)
    print(f"  Tier 2 (>=0.70 Medium-Confidence):  {existing_totals['tier2']}", flush=True)
    print(f"  Tier 3 (>=0.50 Low-Confidence):     {existing_totals['tier3']}", flush=True)
    print(f"  Tier 4 (<0.50 Internal):            {existing_totals['tier4']}", flush=True)
    print(f"  Meetings with flags: {existing_meetings_with_flags}", flush=True)
    for ft, counts in sorted(existing_by_type.items()):
        print(f"    {ft}: {counts['total']} (avg conf {counts['avg_confidence']:.0%})", flush=True)
    print(flush=True)

    # ── Step 2: Pre-load shared data ─────────────────────────────
    print("Loading contributions and Form 700 interests...", flush=True)
    raw_contributions = _fetch_contributions_from_db(conn, city_fips)
    contributions = prefilter_contributions(raw_contributions)
    form700_interests = _fetch_form700_interests_from_db(conn, city_fips)
    print(f"  {len(raw_contributions):,} contributions -> {len(contributions):,} after prefilter, {len(form700_interests):,} Form 700 interests\n", flush=True)

    # ── Step 3: Run v3 scanner across all meetings ───────────────
    print(f"Running v3 scanner across {len(meetings)} meetings ({workers} workers)...", flush=True)
    v3_total = 0
    v3_tier_counts: Counter = Counter()
    v3_type_counts: Counter = Counter()
    v3_meetings_with_flags = 0
    v3_skipped = 0
    errors = 0
    consecutive_errors = 0

    # v3-specific: track confidence factor distributions
    factor_sums: dict[str, float] = defaultdict(float)
    factor_counts: dict[str, int] = defaultdict(int)
    corroboration_dist: Counter = Counter()  # signal_count -> flag_count
    confidence_values: list[float] = []  # all confidence scores for histogram

    official_cache: dict = {}
    start_time = time.time()

    def _process_result(meeting_id, meeting_date, result, error_msg):
        """Process a single meeting's validation result."""
        nonlocal v3_total, v3_meetings_with_flags, v3_skipped, errors, consecutive_errors

        if error_msg:
            errors += 1
            consecutive_errors += 1
            print(f"  ERROR: {meeting_id} ({meeting_date}): {error_msg}", file=sys.stderr, flush=True)
            return

        consecutive_errors = 0

        if result.flags:
            v3_meetings_with_flags += 1

        for flag in result.flags:
            official_id = resolve_official_id(conn, flag.council_member, city_fips, official_cache)
            if official_id is None:
                v3_skipped += 1
                continue

            v3_total += 1
            v3_tier_counts[flag.publication_tier] += 1
            v3_type_counts[flag.flag_type] += 1
            confidence_values.append(flag.confidence)

            if flag.confidence_factors:
                for factor_name, factor_val in flag.confidence_factors.items():
                    if factor_name == "signal_count":
                        corroboration_dist[int(factor_val)] += 1
                    elif isinstance(factor_val, (int, float)):
                        factor_sums[factor_name] += factor_val
                        factor_counts[factor_name] += 1

    # O5: Parallel or sequential validation
    if workers > 1 and len(meetings) > 1:
        print(f"  Using {workers} parallel workers...", flush=True)
        conn.close()  # Workers use their own connections

        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _scan_single_meeting_worker,
                    str(mid), str(mdate), city_fips,
                    contributions, form700_interests,
                ): (mid, mdate)
                for mid, mdate in meetings
            }

            conn = _fresh_conn()  # Re-open for result processing (official resolution)
            completed = 0
            for future in as_completed(futures):
                mid_str, mdate_str, result, error_msg = future.result()
                _process_result(mid_str, mdate_str, result, error_msg)

                completed += 1
                if completed % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed
                    remaining = (len(meetings) - completed) / rate if rate > 0 else 0
                    print(f"  [{completed}/{len(meetings)}] {v3_total} flags | {elapsed:.0f}s | ~{remaining:.0f}s remaining", flush=True)

                if consecutive_errors >= 10:
                    print("  FATAL: 10 consecutive errors.", file=sys.stderr, flush=True)
                    break
    else:
        # Sequential path
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
                _process_result(meeting_id, meeting_date, result, None)

                if i % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = i / elapsed
                    remaining = (len(meetings) - i) / rate
                    print(f"  [{i}/{len(meetings)}] {v3_total} flags | {elapsed:.0f}s | ~{remaining:.0f}s remaining", flush=True)

            except Exception as e:
                _process_result(meeting_id, meeting_date, None, str(e))
                try:
                    conn.close()
                except Exception:
                    pass
                conn = _fresh_conn()
                if consecutive_errors >= 10:
                    print("  FATAL: 10 consecutive errors.", file=sys.stderr, flush=True)
                    break

    elapsed = time.time() - start_time

    # ── Step 4: V3 results ───────────────────────────────────────
    print(f"\nV3 SCANNER RESULTS:", flush=True)
    print(f"  Total flags: {v3_total}", flush=True)
    for tier in sorted(v3_tier_counts.keys()):
        label = _tier_label(tier)
        count = v3_tier_counts[tier]
        pct = (count / v3_total * 100) if v3_total else 0
        print(f"  Tier {tier} ({label}): {count} ({pct:.1f}%)", flush=True)
    print(f"  Meetings with flags: {v3_meetings_with_flags}", flush=True)
    print(f"  By type: {dict(v3_type_counts.most_common())}", flush=True)
    print(f"  Skipped (unresolved official): {v3_skipped}", flush=True)
    print(f"  Errors: {errors}", flush=True)
    print(f"  Time: {elapsed:.1f}s ({workers} workers)", flush=True)

    # ── Step 5: Factor breakdown ─────────────────────────────────
    if factor_counts:
        print(f"\nCONFIDENCE FACTOR AVERAGES (v3):", flush=True)
        for factor_name in sorted(factor_counts.keys()):
            avg = factor_sums[factor_name] / factor_counts[factor_name]
            print(f"  {factor_name}: {avg:.3f} (n={factor_counts[factor_name]})", flush=True)

    if corroboration_dist:
        print(f"\nCORROBORATION DISTRIBUTION:", flush=True)
        for signal_count in sorted(corroboration_dist.keys()):
            flag_count = corroboration_dist[signal_count]
            pct = (flag_count / v3_total * 100) if v3_total else 0
            print(f"  {signal_count} signal(s): {flag_count} flags ({pct:.1f}%)", flush=True)

    # Confidence histogram (quintile buckets)
    if confidence_values:
        print(f"\nCONFIDENCE DISTRIBUTION:", flush=True)
        buckets = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
        for lo, hi in buckets:
            count = sum(1 for c in confidence_values if lo <= c < hi)
            pct = (count / len(confidence_values) * 100) if confidence_values else 0
            bar = "█" * int(pct / 2)
            print(f"  {lo:.1f}-{hi:.1f}: {count:4d} ({pct:5.1f}%) {bar}", flush=True)

    # ── Step 6: Delta analysis ───────────────────────────────────
    print(f"\n{'='*60}", flush=True)
    print(f"  DELTA ANALYSIS (existing DB → v3 rescan)", flush=True)
    print(f"{'='*60}", flush=True)

    delta = v3_total - existing_totals["total"]
    if existing_totals["total"] > 0:
        pct = (delta / existing_totals["total"]) * 100
        print(f"  Flag count: {existing_totals['total']} → {v3_total} ({delta:+d}, {pct:+.1f}%)", flush=True)
    else:
        print(f"  Flag count: {existing_totals['total']} → {v3_total} ({delta:+d})", flush=True)

    for tier in [1, 2, 3, 4]:
        old = existing_totals.get(f"tier{tier}", 0)
        new = v3_tier_counts.get(tier, 0)
        d = new - old
        label = _tier_label(tier)
        print(f"  Tier {tier} ({label}): {old} → {new} ({d:+d})", flush=True)

    meetings_delta = v3_meetings_with_flags - existing_meetings_with_flags
    print(f"  Meetings with flags: {existing_meetings_with_flags} → {v3_meetings_with_flags} ({meetings_delta:+d})", flush=True)

    # Type-by-type delta
    all_types = sorted(set(list(existing_by_type.keys()) + list(v3_type_counts.keys())))
    if all_types:
        print(f"\n  BY SIGNAL TYPE:", flush=True)
        for ft in all_types:
            old = existing_by_type.get(ft, {}).get("total", 0)
            new = v3_type_counts.get(ft, 0)
            d = new - old
            print(f"    {ft}: {old} → {new} ({d:+d})", flush=True)

    # Summary assessment
    if existing_totals["total"] > 0:
        print(f"\n  SUMMARY:", flush=True)
        if delta < 0:
            reduction_pct = abs(delta) / existing_totals["total"] * 100
            print(f"    {reduction_pct:.1f}% reduction in total flags (precision improvement)", flush=True)
        elif delta > 0:
            increase_pct = delta / existing_totals["total"] * 100
            print(f"    {increase_pct:.1f}% increase in total flags (new detectors finding more)", flush=True)
        else:
            print(f"    No change in total flag count", flush=True)

        # Check expected v3 behaviors
        tier1_count = v3_tier_counts.get(1, 0)
        tier3_plus_4 = v3_tier_counts.get(3, 0) + v3_tier_counts.get(4, 0)
        multi_signal = sum(c for s, c in corroboration_dist.items() if s >= 2)

        if tier1_count > 0 and multi_signal > 0:
            print(f"    ✓ Tier 1 flags exist ({tier1_count}) — corroboration system working", flush=True)
        elif tier1_count == 0:
            print(f"    ⚠ No Tier 1 flags — single-signal cap (0.8475) may be limiting", flush=True)

        if multi_signal > 0:
            print(f"    ✓ Multi-signal corroboration: {multi_signal} flags from 2+ independent signals", flush=True)

    # ── Step 7: Save structured report ───────────────────────────
    report_path = Path(__file__).parent / "data" / "validation_reports"
    report_path.mkdir(parents=True, exist_ok=True)
    report_file = report_path / f"v3_validation_{date.today().isoformat()}.json"

    factor_averages = {}
    for fn in sorted(factor_counts.keys()):
        factor_averages[fn] = round(factor_sums[fn] / factor_counts[fn], 4)

    report_data = {
        "date": date.today().isoformat(),
        "scanner_version": SCANNER_VERSION,
        "city_fips": city_fips,
        "meetings_scanned": len(meetings),
        "errors": errors,
        "execution_seconds": round(elapsed, 1),
        "workers": workers,
        "existing": {
            "total": existing_totals["total"],
            "by_tier": {f"tier{k}": existing_totals[f"tier{k}"] for k in [1, 2, 3, 4]},
            "scanner_versions": existing_versions,
            "meetings_with_flags": existing_meetings_with_flags,
            "by_type": existing_by_type,
        },
        "v3": {
            "total": v3_total,
            "by_tier": {f"tier{k}": v3_tier_counts.get(k, 0) for k in [1, 2, 3, 4]},
            "meetings_with_flags": v3_meetings_with_flags,
            "by_type": dict(v3_type_counts.most_common()),
            "skipped": v3_skipped,
            "factor_averages": factor_averages,
            "corroboration_distribution": {str(k): v for k, v in sorted(corroboration_dist.items())},
        },
        "delta": {
            "total": delta,
            "total_pct": round((delta / existing_totals["total"] * 100), 1) if existing_totals["total"] else 0,
            "by_tier": {
                f"tier{k}": v3_tier_counts.get(k, 0) - existing_totals.get(f"tier{k}", 0)
                for k in [1, 2, 3, 4]
            },
        },
    }
    report_file.write_text(json.dumps(report_data, indent=2))
    print(f"\n  Report saved: {report_file}", flush=True)

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch conflict scanner v3")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be saved without writing")
    parser.add_argument("--validate", action="store_true", help="Compare v3 scanner output against existing DB flags")
    parser.add_argument("--meeting-id", help="Scan a single meeting by UUID")
    parser.add_argument("--city-fips", default=DEFAULT_FIPS, help="City FIPS code")
    parser.add_argument(
        "--workers", type=int,
        default=min(os.cpu_count() or 1, 8),
        help="Number of parallel workers (default: min(cpu_count, 8))",
    )
    args = parser.parse_args()

    if args.validate:
        run_validation(city_fips=args.city_fips, single_meeting_id=args.meeting_id, workers=args.workers)
    else:
        run_batch_scan(
            city_fips=args.city_fips,
            dry_run=args.dry_run,
            single_meeting_id=args.meeting_id,
            workers=args.workers,
        )
