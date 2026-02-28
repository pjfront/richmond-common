# src/seed_commissions.py
"""
Seed the commissions table from ground_truth/officials.json.

Inserts commission registry records (not members — that's the roster scraper).
Idempotent: uses ON CONFLICT DO UPDATE so it's safe to re-run.

Usage:
    python seed_commissions.py              # Seed all commissions
    python seed_commissions.py --dry-run    # Show what would be inserted
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)

CITY_FIPS = "0660620"


def load_commissions_config() -> list[dict]:
    """Load commission definitions from officials.json."""
    gt_path = Path(__file__).parent / "ground_truth" / "officials.json"
    if not gt_path.exists():
        logger.error("Ground truth file not found: %s", gt_path)
        return []
    data = json.loads(gt_path.read_text())
    return data.get("commissions", [])


def seed_commissions(*, city_fips: str = CITY_FIPS, dry_run: bool = False) -> int:
    """Insert commission registry records into the database.

    Returns count of commissions upserted.
    """
    commissions = load_commissions_config()
    if not commissions:
        logger.error("No commissions found in officials.json")
        return 0

    if dry_run:
        for c in commissions:
            print(f"  Would seed: {c['name']} ({c.get('type', 'advisory')}, "
                  f"{c.get('num_seats', '?')} seats)")
        print(f"\n{len(commissions)} commissions would be seeded (dry run)")
        return len(commissions)

    from db import get_connection

    conn = get_connection()
    count = 0
    try:
        with conn.cursor() as cur:
            for c in commissions:
                cur.execute(
                    """INSERT INTO commissions
                       (city_fips, name, commission_type, num_seats,
                        appointment_authority, form700_required,
                        term_length_years, meeting_schedule, website_roster_url)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT ON CONSTRAINT uq_commission
                       DO UPDATE SET
                           commission_type = EXCLUDED.commission_type,
                           num_seats = EXCLUDED.num_seats,
                           appointment_authority = EXCLUDED.appointment_authority,
                           form700_required = EXCLUDED.form700_required,
                           term_length_years = EXCLUDED.term_length_years,
                           meeting_schedule = EXCLUDED.meeting_schedule,
                           website_roster_url = EXCLUDED.website_roster_url""",
                    (
                        city_fips,
                        c["name"],
                        c.get("type", "advisory"),
                        c.get("num_seats"),
                        c.get("appointment_authority"),
                        c.get("form700_required", False),
                        c.get("term_length_years"),
                        c.get("meeting_schedule"),
                        c.get("website_roster_url"),
                    ),
                )
                count += 1

            conn.commit()
        logger.info("Seeded %d commissions for city_fips=%s", count, city_fips)
    finally:
        conn.close()

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed commission registry to database")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be inserted")
    parser.add_argument("--city-fips", default=CITY_FIPS, help="City FIPS code")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    count = seed_commissions(city_fips=args.city_fips, dry_run=args.dry_run)
    if not args.dry_run:
        print(f"Seeded {count} commissions to database")


if __name__ == "__main__":
    main()
