# src/seed_neighborhood_councils.py
"""
Seed the neighborhood_councils table from ground_truth/neighborhood_councils.json.

Idempotent: uses ON CONFLICT DO UPDATE so it's safe to re-run.

Usage:
    python seed_neighborhood_councils.py              # Seed all NCs
    python seed_neighborhood_councils.py --dry-run    # Show what would be inserted
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


def load_nc_config() -> list[dict]:
    """Load neighborhood council definitions from ground truth JSON."""
    gt_path = Path(__file__).parent / "ground_truth" / "neighborhood_councils.json"
    if not gt_path.exists():
        logger.error("Ground truth file not found: %s", gt_path)
        return []
    data = json.loads(gt_path.read_text())
    return data.get("neighborhood_councils", [])


def seed_neighborhood_councils(
    *, city_fips: str = CITY_FIPS, dry_run: bool = False
) -> int:
    """Insert neighborhood council records into the database.

    Returns count of NCs upserted.
    """
    ncs = load_nc_config()
    if not ncs:
        logger.error("No neighborhood councils found in ground truth")
        return 0

    if dry_run:
        active = sum(1 for nc in ncs if nc.get("is_active", True))
        inactive = len(ncs) - active
        for nc in ncs:
            status = "active" if nc.get("is_active", True) else "inactive"
            codes = nc.get("geojson_codes", [])
            print(
                f"  Would seed: {nc['name']} ({nc.get('nc_type', 'neighborhood_council')}, "
                f"{status}, geojson codes: {codes})"
            )
        print(f"\n{len(ncs)} neighborhood councils would be seeded "
              f"({active} active, {inactive} inactive) (dry run)")
        return len(ncs)

    from db import get_connection

    conn = get_connection()
    count = 0
    try:
        with conn.cursor() as cur:
            for nc in ncs:
                cur.execute(
                    """INSERT INTO neighborhood_councils
                       (city_fips, name, short_name, nc_type, geojson_codes,
                        is_active, meeting_schedule, meeting_time,
                        meeting_location, city_page_url, city_page_id,
                        document_center_path, notes, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                       ON CONFLICT (city_fips, name)
                       DO UPDATE SET
                           short_name = EXCLUDED.short_name,
                           nc_type = EXCLUDED.nc_type,
                           geojson_codes = EXCLUDED.geojson_codes,
                           is_active = EXCLUDED.is_active,
                           meeting_schedule = EXCLUDED.meeting_schedule,
                           meeting_time = EXCLUDED.meeting_time,
                           meeting_location = EXCLUDED.meeting_location,
                           city_page_url = EXCLUDED.city_page_url,
                           city_page_id = EXCLUDED.city_page_id,
                           document_center_path = EXCLUDED.document_center_path,
                           notes = EXCLUDED.notes,
                           updated_at = now()""",
                    (
                        city_fips,
                        nc["name"],
                        nc.get("short_name"),
                        nc.get("nc_type", "neighborhood_council"),
                        nc.get("geojson_codes", []),
                        nc.get("is_active", True),
                        nc.get("meeting_schedule"),
                        nc.get("meeting_time"),
                        nc.get("meeting_location"),
                        nc.get("city_page_url"),
                        nc.get("city_page_id"),
                        nc.get("document_center_path"),
                        nc.get("notes"),
                    ),
                )
                count += 1
                logger.info("Seeded: %s", nc["name"])
        conn.commit()
        logger.info("Seeded %d neighborhood councils", count)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed neighborhood councils from ground truth"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be inserted"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    count = seed_neighborhood_councils(dry_run=args.dry_run)
    if count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
