"""
Richmond Transparency Project — Contribution Context Enricher

Classifies donor patterns based on contribution history and updates
the donors table with pattern labels and aggregate statistics.

Pattern classification (rule-based, no LLM needed):
  - pac:         PAC/committee donor detected from name patterns
  - mega:        Top 1% by total ($75K+ for Richmond), concentrated giving
  - grassroots:  Many small donations (<$250 avg), multiple recipients
  - targeted:    Few donations to specific candidates, larger amounts
  - regular:     Default — doesn't match other patterns

Usage:
  cd src
  python contribution_enricher.py --city-fips 0660620
  python contribution_enricher.py --city-fips 0660620 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection, RICHMOND_FIPS

logger = logging.getLogger(__name__)

# ── PAC/Committee name patterns ───────────────────────────────────

PAC_NAME_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bPAC\b", re.IGNORECASE),
    re.compile(r"\bPolitical Action\b", re.IGNORECASE),
    re.compile(r"\bCommittee\b", re.IGNORECASE),
    re.compile(r"\bCoalition\b", re.IGNORECASE),
    re.compile(r"\bSponsored by\b", re.IGNORECASE),
    re.compile(r"\bIssues PAC\b", re.IGNORECASE),
    re.compile(r"\bCandidate PAC\b", re.IGNORECASE),
    re.compile(r"\bPAC Fund\b", re.IGNORECASE),
    # Common org suffixes that signal institutional donors
    re.compile(r"\bLocal \d+\b", re.IGNORECASE),  # e.g. "SEIU Local 1021"
    re.compile(r"\bIAFF\b", re.IGNORECASE),        # firefighters union
    re.compile(r"\bAFL-?CIO\b", re.IGNORECASE),
]


def is_pac_name(name: str) -> bool:
    """Detect PAC/committee/institutional donors from name patterns."""
    return any(pat.search(name) for pat in PAC_NAME_PATTERNS)


# ── Classification thresholds ─────────────────────────────────────
# These are derived from Richmond's actual data distribution.
# For multi-city, thresholds could be computed per-city from percentiles.

@dataclass
class PatternThresholds:
    """Configurable thresholds for donor pattern classification.

    Defaults are calibrated to Richmond's 2001-2025 contribution data:
    - Median donor: $540 total, 3 contributions, 1 recipient
    - P99 total: ~$75K
    """
    # Mega donor: top ~1% by total amount
    mega_total_min: float = 75_000.0
    # Grassroots: small average AND broad giving
    grassroots_avg_max: float = 250.0
    grassroots_min_contributions: int = 3
    grassroots_min_recipients: int = 2
    # Targeted: larger amounts to few recipients
    targeted_avg_min: float = 1_000.0
    targeted_max_recipients: int = 2
    targeted_min_total: float = 5_000.0


DEFAULT_THRESHOLDS = PatternThresholds()


# ── Donor context row (from donor_context view) ──────────────────

@dataclass
class DonorContext:
    """One row from the donor_context view."""
    donor_id: str
    donor_name: str
    contribution_count: int
    total_contributed: float
    avg_contribution: Optional[float]
    distinct_recipients: int
    contribution_span_days: Optional[int]

    @classmethod
    def from_row(cls, row: tuple) -> DonorContext:
        return cls(
            donor_id=str(row[0]),
            donor_name=row[1] or "",
            contribution_count=row[2] or 0,
            total_contributed=float(row[3] or 0),
            avg_contribution=float(row[4]) if row[4] is not None else None,
            distinct_recipients=row[5] or 0,
            contribution_span_days=int(row[6]) if row[6] is not None else None,
        )


# ── Pattern classification ────────────────────────────────────────

def classify_donor_pattern(
    ctx: DonorContext,
    thresholds: PatternThresholds = DEFAULT_THRESHOLDS,
) -> str:
    """Classify a donor into a pattern category.

    Classification priority (first match wins):
    1. pac — name matches PAC/committee patterns
    2. mega — total contributed exceeds P99 threshold
    3. grassroots — many small donations, broad giving
    4. targeted — larger amounts, concentrated on few recipients
    5. regular — default

    Returns pattern string: 'pac', 'mega', 'grassroots', 'targeted', or 'regular'.
    """
    # 1. PAC detection (name-based, highest priority)
    if is_pac_name(ctx.donor_name):
        return "pac"

    # Skip donors with no contributions (edge case: orphan donor rows)
    if ctx.contribution_count == 0 or ctx.total_contributed <= 0:
        return "regular"

    # 2. Mega donor (top ~1% by total)
    if ctx.total_contributed >= thresholds.mega_total_min:
        return "mega"

    # 3. Grassroots (small average, broad giving)
    if (
        ctx.avg_contribution is not None
        and ctx.avg_contribution <= thresholds.grassroots_avg_max
        and ctx.contribution_count >= thresholds.grassroots_min_contributions
        and ctx.distinct_recipients >= thresholds.grassroots_min_recipients
    ):
        return "grassroots"

    # 4. Targeted (larger amounts, concentrated recipients)
    if (
        ctx.avg_contribution is not None
        and ctx.avg_contribution >= thresholds.targeted_avg_min
        and ctx.distinct_recipients <= thresholds.targeted_max_recipients
        and ctx.total_contributed >= thresholds.targeted_min_total
    ):
        return "targeted"

    # 5. Default
    return "regular"


# ── Batch enrichment ──────────────────────────────────────────────

def enrich_donors(
    conn,
    city_fips: str = RICHMOND_FIPS,
    thresholds: PatternThresholds = DEFAULT_THRESHOLDS,
    dry_run: bool = False,
) -> dict:
    """Classify all donors for a city and update the donors table.

    Reads from the donor_context view, classifies each donor, and
    batch-updates donors with pattern + aggregate stats.

    Returns summary dict with counts per pattern.
    """
    stats: dict[str, int] = {
        "pac": 0,
        "mega": 0,
        "grassroots": 0,
        "targeted": 0,
        "regular": 0,
        "total": 0,
        "updated": 0,
    }

    with conn.cursor() as cur:
        # Read all donors from the view
        cur.execute(
            """SELECT donor_id, donor_name, contribution_count,
                      total_contributed, avg_contribution,
                      distinct_recipients, contribution_span_days
               FROM donor_context
               WHERE city_fips = %s""",
            (city_fips,),
        )
        rows = cur.fetchall()

    contexts = [DonorContext.from_row(row) for row in rows]
    stats["total"] = len(contexts)

    # Classify each donor
    updates: list[tuple] = []
    for ctx in contexts:
        pattern = classify_donor_pattern(ctx, thresholds)
        stats[pattern] += 1
        updates.append((
            pattern,
            ctx.total_contributed,
            ctx.contribution_span_days,
            ctx.distinct_recipients,
            ctx.donor_id,
        ))

    if dry_run:
        print(f"\n[DRY RUN] Would update {len(updates)} donors:")
        for pattern, count in sorted(stats.items()):
            if pattern not in ("total", "updated"):
                print(f"  {pattern:12s}: {count:>5d}")
        return stats

    # Batch update
    with conn.cursor() as cur:
        for batch_start in range(0, len(updates), 500):
            batch = updates[batch_start:batch_start + 500]
            for update_tuple in batch:
                cur.execute(
                    """UPDATE donors
                       SET donor_pattern = %s,
                           total_contributed = %s,
                           contribution_span_days = %s,
                           distinct_recipients = %s
                       WHERE id = %s""",
                    update_tuple,
                )
                stats["updated"] += cur.rowcount

    conn.commit()
    return stats


# ── CLI ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Enrich donor records with contribution pattern classification"
    )
    parser.add_argument(
        "--city-fips",
        default=RICHMOND_FIPS,
        help=f"City FIPS code (default: {RICHMOND_FIPS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify and report without updating the database",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    conn = get_connection()

    print(f"\n{'='*60}")
    print(f"Contribution Enricher — FIPS {args.city_fips}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE UPDATE'}")
    print(f"{'='*60}\n")

    stats = enrich_donors(conn, city_fips=args.city_fips, dry_run=args.dry_run)

    print(f"\nDonor pattern classification results:")
    print(f"  Total donors:   {stats['total']:>5d}")
    print(f"  ────────────────────────")
    for pattern in ["pac", "mega", "grassroots", "targeted", "regular"]:
        pct = (stats[pattern] / stats["total"] * 100) if stats["total"] else 0
        print(f"  {pattern:12s}: {stats[pattern]:>5d}  ({pct:5.1f}%)")

    if not args.dry_run:
        print(f"\n  Rows updated:   {stats['updated']:>5d}")

    conn.close()
    print(f"\nDone.")


if __name__ == "__main__":
    main()
