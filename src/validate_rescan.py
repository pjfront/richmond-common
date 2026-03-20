#!/usr/bin/env python3
from __future__ import annotations
"""V1 Rescan Validation: compare scan results before and after S9.5 cleanup.

Queries the database for the two most recent scan runs and compares:
- Total flag counts
- Percentage above 0.50 (public visibility threshold)
- Distribution by flag_type
- Publication tier distribution
- Flags that appeared, disappeared, or changed tier
- Top 5 highest-confidence flags for spot-checking

Usage:
    python validate_rescan.py
    python validate_rescan.py --before <scan_run_id> --after <scan_run_id>
    python validate_rescan.py --markdown  # output as markdown
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

RICHMOND_FIPS = "0660620"


def get_scan_runs(conn, limit: int = 5) -> list[dict]:
    """Get recent completed scan runs."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, scan_mode, flags_found, flags_by_tier,
                      contributions_count, form700_count,
                      execution_time_seconds, created_at, scanner_version
               FROM scan_runs
               WHERE city_fips = %s AND status = 'completed'
               ORDER BY created_at DESC
               LIMIT %s""",
            (RICHMOND_FIPS, limit),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_flags_for_run(conn, scan_run_id: str) -> list[dict]:
    """Get all flags for a specific scan run."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, flag_type, confidence, publication_tier,
                      description, evidence, confidence_factors,
                      scanner_version, is_current
               FROM conflict_flags
               WHERE scan_run_id = %s
               ORDER BY confidence DESC""",
            (scan_run_id,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def analyze_distribution(flags: list[dict]) -> dict:
    """Compute distribution stats for a set of flags."""
    total = len(flags)
    if total == 0:
        return {
            "total": 0,
            "above_050": 0,
            "above_050_pct": 0,
            "by_type": {},
            "by_tier": {},
            "avg_confidence": 0,
        }

    confidences = [f["confidence"] for f in flags if f["confidence"] is not None]
    above_050 = sum(1 for c in confidences if float(c) >= 0.50)

    by_type: dict[str, int] = {}
    for f in flags:
        ft = f["flag_type"]
        by_type[ft] = by_type.get(ft, 0) + 1

    by_tier: dict[int, int] = {}
    for f in flags:
        tier = f.get("publication_tier") or 0
        by_tier[tier] = by_tier.get(tier, 0) + 1

    return {
        "total": total,
        "above_050": above_050,
        "above_050_pct": (above_050 / total * 100) if total else 0,
        "by_type": by_type,
        "by_tier": by_tier,
        "avg_confidence": sum(float(c) for c in confidences) / len(confidences) if confidences else 0,
    }


def compare_flags(before_flags: list[dict], after_flags: list[dict]) -> dict:
    """Compare two sets of flags to find appeared/disappeared/changed."""
    # Key by (flag_type, description prefix) for fuzzy matching
    def flag_key(f: dict) -> str:
        desc = (f.get("description") or "")[:100]
        return f"{f['flag_type']}::{desc}"

    before_keys = {flag_key(f): f for f in before_flags}
    after_keys = {flag_key(f): f for f in after_flags}

    appeared = [after_keys[k] for k in after_keys if k not in before_keys]
    disappeared = [before_keys[k] for k in before_keys if k not in after_keys]

    changed_tier = []
    for k in before_keys:
        if k in after_keys:
            b_tier = before_keys[k].get("publication_tier")
            a_tier = after_keys[k].get("publication_tier")
            if b_tier != a_tier:
                changed_tier.append({
                    "key": k,
                    "before_tier": b_tier,
                    "after_tier": a_tier,
                    "description": before_keys[k].get("description", "")[:80],
                })

    return {
        "appeared": appeared,
        "disappeared": disappeared,
        "changed_tier": changed_tier,
    }


def print_report(
    before_run: dict,
    after_run: dict,
    before_stats: dict,
    after_stats: dict,
    comparison: dict,
    after_flags: list[dict],
    markdown: bool = False,
) -> None:
    """Print the validation report."""
    h1 = "# " if markdown else "=== "
    h2 = "## " if markdown else "--- "
    sep = "" if markdown else "=" * 60

    if sep:
        print(sep)
    print(f"{h1}S9.5 Rescan Validation Report")
    if sep:
        print(sep)

    print(f"\n{h2}Scan Runs Compared")
    print(f"  Before: {before_run['id']} ({before_run['created_at']})")
    print(f"    Mode: {before_run['scan_mode']}, Scanner v{before_run.get('scanner_version', '?')}")
    print(f"  After:  {after_run['id']} ({after_run['created_at']})")
    print(f"    Mode: {after_run['scan_mode']}, Scanner v{after_run.get('scanner_version', '?')}")

    print(f"\n{h2}Flag Count Summary")
    delta = after_stats["total"] - before_stats["total"]
    sign = "+" if delta > 0 else ""
    print(f"  Before: {before_stats['total']} flags")
    print(f"  After:  {after_stats['total']} flags ({sign}{delta})")
    print(f"  Above 0.50: {before_stats['above_050']} ({before_stats['above_050_pct']:.1f}%) -> "
          f"{after_stats['above_050']} ({after_stats['above_050_pct']:.1f}%)")
    print(f"  Avg confidence: {before_stats['avg_confidence']:.3f} -> {after_stats['avg_confidence']:.3f}")

    print(f"\n{h2}Distribution by Flag Type")
    all_types = sorted(set(list(before_stats["by_type"].keys()) + list(after_stats["by_type"].keys())))
    print(f"  {'Type':<30} {'Before':>8} {'After':>8} {'Delta':>8}")
    print(f"  {'-'*30} {'-'*8} {'-'*8} {'-'*8}")
    for ft in all_types:
        b = before_stats["by_type"].get(ft, 0)
        a = after_stats["by_type"].get(ft, 0)
        d = a - b
        sign = "+" if d > 0 else ""
        print(f"  {ft:<30} {b:>8} {a:>8} {sign}{d:>7}")

    print(f"\n{h2}Distribution by Publication Tier")
    all_tiers = sorted(set(list(before_stats["by_tier"].keys()) + list(after_stats["by_tier"].keys())))
    tier_labels = {0: "Unset", 1: "Tier 1 (high)", 2: "Tier 2 (medium)", 3: "Tier 3 (low)", 4: "Tier 4 (internal)"}
    print(f"  {'Tier':<25} {'Before':>8} {'After':>8}")
    print(f"  {'-'*25} {'-'*8} {'-'*8}")
    for t in all_tiers:
        label = tier_labels.get(t, f"Tier {t}")
        print(f"  {label:<25} {before_stats['by_tier'].get(t, 0):>8} {after_stats['by_tier'].get(t, 0):>8}")

    print(f"\n{h2}Changes")
    print(f"  Flags appeared:    {len(comparison['appeared'])}")
    print(f"  Flags disappeared: {len(comparison['disappeared'])}")
    print(f"  Tier changes:      {len(comparison['changed_tier'])}")

    if comparison["changed_tier"]:
        print(f"\n  Tier changes:")
        for c in comparison["changed_tier"][:10]:
            print(f"    Tier {c['before_tier']} -> {c['after_tier']}: {c['description']}")

    if comparison["appeared"]:
        print(f"\n  Sample new flags:")
        for f in comparison["appeared"][:5]:
            desc = (f.get("description") or "")[:80]
            print(f"    [{f['flag_type']}] conf={float(f.get('confidence', 0)):.2f}: {desc}")

    if comparison["disappeared"]:
        print(f"\n  Sample removed flags:")
        for f in comparison["disappeared"][:5]:
            desc = (f.get("description") or "")[:80]
            print(f"    [{f['flag_type']}] conf={float(f.get('confidence', 0)):.2f}: {desc}")

    # Spot-check: top 5 highest confidence from new scan
    print(f"\n{h2}Spot-Check: Top 5 Highest Confidence (After)")
    for f in after_flags[:5]:
        desc = (f.get("description") or "")[:100]
        tier = f.get("publication_tier", "?")
        print(f"  [{f['flag_type']}] tier={tier} conf={float(f.get('confidence', 0)):.2f}")
        print(f"    {desc}")

    if sep:
        print(f"\n{sep}")


def main() -> None:
    parser = argparse.ArgumentParser(description="V1 Rescan Validation")
    parser.add_argument("--before", help="Scan run ID for 'before' baseline")
    parser.add_argument("--after", help="Scan run ID for 'after' comparison")
    parser.add_argument("--markdown", action="store_true", help="Output as markdown")
    args = parser.parse_args()

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        runs = get_scan_runs(conn, limit=5)
        if len(runs) < 2 and not (args.before and args.after):
            print("Need at least 2 completed scan runs to compare.")
            print(f"Found {len(runs)} runs:")
            for r in runs:
                print(f"  {r['id']} ({r['created_at']}) mode={r['scan_mode']} flags={r['flags_found']}")
            sys.exit(1)

        if args.before and args.after:
            before_id = args.before
            after_id = args.after
            # Find run metadata
            before_run = next((r for r in runs if str(r["id"]) == before_id), {"id": before_id, "created_at": "?", "scan_mode": "?", "scanner_version": "?"})
            after_run = next((r for r in runs if str(r["id"]) == after_id), {"id": after_id, "created_at": "?", "scan_mode": "?", "scanner_version": "?"})
        else:
            # Use two most recent
            after_run = runs[0]
            before_run = runs[1]
            before_id = str(before_run["id"])
            after_id = str(after_run["id"])

        before_flags = get_flags_for_run(conn, before_id)
        after_flags = get_flags_for_run(conn, after_id)

        before_stats = analyze_distribution(before_flags)
        after_stats = analyze_distribution(after_flags)
        comparison = compare_flags(before_flags, after_flags)

        print_report(before_run, after_run, before_stats, after_stats,
                     comparison, after_flags, markdown=args.markdown)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
