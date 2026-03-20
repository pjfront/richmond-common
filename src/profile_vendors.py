#!/usr/bin/env python3
from __future__ import annotations
"""Profile city_expenditures.normalized_vendor data quality.

Quick diagnostic to confirm vendor data is suitable for gazetteer-based matching
before switching from entity extraction. Outputs stats to stdout.

Usage:
    python profile_vendors.py [--fips FIPS_CODE]
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)


def profile_vendors(fips: str = "0660620") -> dict:
    """Query city_expenditures and return vendor name statistics."""
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            # Total rows
            cur.execute(
                "SELECT COUNT(*) FROM city_expenditures WHERE city_fips = %s",
                (fips,),
            )
            total = cur.fetchone()[0]

            # Null/empty normalized_vendor
            cur.execute(
                """SELECT COUNT(*) FROM city_expenditures
                   WHERE city_fips = %s
                   AND (normalized_vendor IS NULL OR normalized_vendor = '')""",
                (fips,),
            )
            null_count = cur.fetchone()[0]

            # Distinct vendor names
            cur.execute(
                """SELECT COUNT(DISTINCT normalized_vendor)
                   FROM city_expenditures
                   WHERE city_fips = %s
                   AND normalized_vendor IS NOT NULL
                   AND normalized_vendor != ''""",
                (fips,),
            )
            distinct_count = cur.fetchone()[0]

            # Length distribution
            cur.execute(
                """SELECT
                       MIN(LENGTH(normalized_vendor)),
                       MAX(LENGTH(normalized_vendor)),
                       AVG(LENGTH(normalized_vendor))::numeric(10,1),
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY LENGTH(normalized_vendor))::numeric(10,1)
                   FROM city_expenditures
                   WHERE city_fips = %s
                   AND normalized_vendor IS NOT NULL
                   AND normalized_vendor != ''""",
                (fips,),
            )
            min_len, max_len, avg_len, median_len = cur.fetchone()

            # Vendors shorter than 10 chars (name_in_text minimum)
            cur.execute(
                """SELECT COUNT(DISTINCT normalized_vendor)
                   FROM city_expenditures
                   WHERE city_fips = %s
                   AND normalized_vendor IS NOT NULL
                   AND LENGTH(normalized_vendor) < 10""",
                (fips,),
            )
            short_count = cur.fetchone()[0]

            # Top 20 vendors by expenditure count
            cur.execute(
                """SELECT normalized_vendor, COUNT(*) as cnt,
                          SUM(amount)::numeric(12,2) as total
                   FROM city_expenditures
                   WHERE city_fips = %s
                   AND normalized_vendor IS NOT NULL
                   AND normalized_vendor != ''
                   GROUP BY normalized_vendor
                   ORDER BY cnt DESC
                   LIMIT 20""",
                (fips,),
            )
            top_vendors = cur.fetchall()

            # Sample short vendors (< 10 chars)
            cur.execute(
                """SELECT DISTINCT normalized_vendor
                   FROM city_expenditures
                   WHERE city_fips = %s
                   AND normalized_vendor IS NOT NULL
                   AND LENGTH(normalized_vendor) < 10
                   AND normalized_vendor != ''
                   LIMIT 20""",
                (fips,),
            )
            short_samples = [row[0] for row in cur.fetchall()]

        return {
            "total_rows": total,
            "null_count": null_count,
            "null_rate": f"{null_count / total * 100:.1f}%" if total else "N/A",
            "distinct_vendors": distinct_count,
            "length_min": min_len,
            "length_max": max_len,
            "length_avg": float(avg_len) if avg_len else 0,
            "length_median": float(median_len) if median_len else 0,
            "short_vendors_count": short_count,
            "short_vendors_pct": f"{short_count / distinct_count * 100:.1f}%" if distinct_count else "N/A",
            "top_vendors": top_vendors,
            "short_samples": short_samples,
        }
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Profile city expenditure vendor data quality")
    parser.add_argument("--fips", default="0660620", help="City FIPS code (default: Richmond)")
    args = parser.parse_args()

    stats = profile_vendors(args.fips)

    print(f"\n=== Vendor Data Quality Profile (FIPS: {args.fips}) ===\n")
    print(f"Total expenditure rows:    {stats['total_rows']:,}")
    print(f"Null/empty vendor:         {stats['null_count']:,} ({stats['null_rate']})")
    print(f"Distinct vendor names:     {stats['distinct_vendors']:,}")
    print(f"\nName length distribution:")
    print(f"  Min: {stats['length_min']}, Max: {stats['length_max']}, "
          f"Avg: {stats['length_avg']:.1f}, Median: {stats['length_median']:.1f}")
    print(f"  Short (<10 chars): {stats['short_vendors_count']} ({stats['short_vendors_pct']})")

    if stats["short_samples"]:
        print(f"\nSample short vendors (<10 chars):")
        for v in stats["short_samples"]:
            print(f"  '{v}' ({len(v)} chars)")

    print(f"\nTop 20 vendors by transaction count:")
    print(f"  {'Vendor':<50} {'Count':>6} {'Total $':>14}")
    print(f"  {'-'*50} {'-'*6} {'-'*14}")
    for name, cnt, total in stats["top_vendors"]:
        print(f"  {name[:50]:<50} {cnt:>6} ${total:>12,.2f}")

    # Assessment
    print(f"\n=== Gazetteer Feasibility ===")
    if stats["distinct_vendors"] and stats["short_vendors_count"] / stats["distinct_vendors"] < 0.3:
        print("PASS: Majority of vendor names are >= 10 chars (suitable for name_in_text)")
    else:
        print("WARN: High proportion of short vendor names. name_in_text may miss matches.")

    if stats["total_rows"] and stats["null_count"] / stats["total_rows"] < 0.1:
        print("PASS: Low null rate in normalized_vendor")
    else:
        print("WARN: High null rate. Many expenditures lack vendor names.")


if __name__ == "__main__":
    main()
