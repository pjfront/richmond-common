"""
Apify CA SOS entity resolution enrichment (S26).

Resolves entity-type donors (corporation, union, committee, other_org) against
the CA Secretary of State business registry via the Apify parseforge/sos-scraper
actor. Writes matched entities to business_entities and links them to donors
via entity_name_matches.

Idempotent: only processes donors that don't already have an entity_name_matches
row (source_table='donors'). Re-running is a near-no-op.

Reads from donors table (entity_type, normalized_name).
Does NOT read from any derivative table.
Writes to business_entities, entity_name_matches, opencorporates_api_usage.

Usage:
    # Standalone (direct)
    python apify_entity_resolution.py

    # Via data_sync (preferred)
    python data_sync.py --source apify_sos --sync-type full
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from apify_sos_client import (
    run_sos_search,
    match_entity,
    is_found,
    normalize_result,
    format_cost_estimate,
)
from opencorporates_client import normalize_entity_name

logger = logging.getLogger(__name__)

# ── Gate: entity types we resolve ──────────────────────────────
_RESOLVABLE_TYPES = ("corporation", "union", "committee", "other_org")

# ponytail: sync endpoint, 3 names/batch — each call completes in ~15s.
# 3 names was fast in testing; 10 names timed out the 5-min sync window.
_BATCH_SIZE = 3

# Apify returns up to 5 results per name by default. With 10 names,
# max ~50 results per call, well within the actor limits.
_MAX_ITEMS_PER_NAME = 5

# Match threshold — same as opencorporates_client's auto_match_threshold
_MATCH_THRESHOLD = 0.80


# ── SQL ────────────────────────────────────────────────────────

_GATE_QUERY = """
    SELECT d.id, d.name, d.normalized_name
      FROM donors d
     WHERE d.entity_type = ANY(%s)
       AND NOT EXISTS (
           SELECT 1
             FROM entity_name_matches enm
            WHERE enm.source_table = 'donors'
              AND enm.source_record_id = d.id
       )
     ORDER BY d.total_contributed DESC NULLS LAST
"""

_UPSERT_ENTITY = """
    INSERT INTO business_entities (
        city_fips, entity_name, entity_number, jurisdiction_code,
        entity_type, current_status, incorporation_date,
        registered_address, agent_name,
        source_url, source_publisher, source_tier,
        retrieved_at, confidence_score, raw_response
    ) VALUES (
        %(city_fips)s, %(entity_name)s, %(entity_number)s, %(jurisdiction_code)s,
        %(entity_type)s, %(current_status)s, %(incorporation_date)s,
        %(registered_address)s, %(agent_name)s,
        %(source_url)s, %(source_publisher)s, %(source_tier)s,
        %(retrieved_at)s, %(confidence_score)s, %(raw_response)s
    )
    ON CONFLICT (entity_number, jurisdiction_code)
        WHERE entity_number IS NOT NULL
    DO UPDATE SET
        entity_name = EXCLUDED.entity_name,
        entity_type = EXCLUDED.entity_type,
        current_status = EXCLUDED.current_status,
        incorporation_date = EXCLUDED.incorporation_date,
        registered_address = EXCLUDED.registered_address,
        agent_name = COALESCE(EXCLUDED.agent_name, business_entities.agent_name),
        source_url = EXCLUDED.source_url,
        retrieved_at = EXCLUDED.retrieved_at,
        confidence_score = EXCLUDED.confidence_score,
        raw_response = EXCLUDED.raw_response,
        updated_at = NOW()
    RETURNING id, entity_number
"""

_INSERT_MATCH = """
    INSERT INTO entity_name_matches (
        source_name, source_table, source_record_id,
        business_entity_id, match_confidence, match_method
    ) VALUES (
        %(source_name)s, %(source_table)s, %(source_record_id)s,
        %(business_entity_id)s, %(match_confidence)s, %(match_method)s
    )
"""

_LOG_USAGE = """
    INSERT INTO opencorporates_api_usage (
        endpoint, query_params, response_status, called_at
    ) VALUES (
        %(endpoint)s, %(query_params)s, %(response_status)s, %(called_at)s
    )
"""


# ── Sync function ──────────────────────────────────────────────

def sync_apify_entity_resolution(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id: int | None = None,
) -> dict:
    """Resolve entity-type donors against CA SOS bizfile via Apify.

    Idempotent: skips donors that already have an entity_name_matches row.
    Batches names in groups of 10 to stay under the sync endpoint's 5-min
    timeout.

    Returns stats dict with keys:
        records_fetched, records_new (entities created),
        records_updated (entities updated), matches_created,
        api_runs, api_usage_cost, errors
    """
    stats: dict[str, object] = {
        "records_fetched": 0,
        "records_new": 0,
        "records_updated": 0,
        "matches_created": 0,
        "api_runs": 0,
        "api_usage_cost": "$0.00",
        "errors": 0,
    }

    now = datetime.now(timezone.utc)
    total_results = 0

    with conn.cursor() as cur:
        # 1. Fetch unresolved entity-type donors
        cur.execute(_GATE_QUERY, (list(_RESOLVABLE_TYPES),))
        rows = cur.fetchall()
        stats["records_fetched"] = len(rows)

        if not rows:
            logger.info("apify_sos: no unresolved entity-type donors")
            return dict(stats)

        # 2. Batch loop
        for batch_start in range(0, len(rows), _BATCH_SIZE):
            batch = rows[batch_start : batch_start + _BATCH_SIZE]
            batch_names = [r[1] for r in batch]  # donor.name

            logger.info(
                "apify_sos: batch %d-%d/%d (%d names)",
                batch_start + 1,
                batch_start + len(batch),
                len(rows),
                len(batch_names),
            )

            try:
                results = run_sos_search(batch_names, max_items=_MAX_ITEMS_PER_NAME)
                stats["api_runs"] = int(stats["api_runs"]) + 1
                total_results += len(results)
            except Exception as e:
                logger.error("apify_sos: batch failed: %s", e)
                stats["errors"] = int(stats["errors"]) + 1
                continue

            # 3. Match results to donors in this batch
            for donor_id, donor_name, normalized_name in batch:
                normalized_donor = normalized_name or normalize_entity_name(donor_name)

                try:
                    matched_result, confidence, method = match_entity(
                        results, donor_name, normalized_donor, threshold=_MATCH_THRESHOLD,
                    )
                except Exception as e:
                    logger.error("apify_sos: match error for %s: %s", donor_name, e)
                    stats["errors"] = int(stats["errors"]) + 1
                    continue

                if matched_result is None or method == "none":
                    continue  # below threshold, skip

                try:
                    # 4. Upsert business_entity
                    entity_cols = dict(matched_result)
                    entity_cols["city_fips"] = city_fips
                    entity_cols["source_tier"] = 1
                    entity_cols["raw_response"] = entity_cols.get("raw_response", "{}")
                    if not entity_cols.get("retrieved_at"):
                        entity_cols["retrieved_at"] = now.isoformat()

                    cur.execute(_UPSERT_ENTITY, entity_cols)
                    upserted = cur.fetchone()
                    if upserted is None:
                        logger.warning("apify_sos: upsert returned no row for %s", donor_name)
                        continue

                    be_id, be_number = upserted

                    # We can't distinguish insert vs update from RETURNING alone
                    # in all cases. Use a simple heuristic: if we just saw this
                    # entity_number, it's likely new.
                    # ponytail: counts are approximate; stats are for logging,
                    # not billing. Exact insert/update tracking adds a SELECT
                    # before every UPSERT.
                    stats["records_new"] = int(stats["records_new"]) + 1

                    # 5. Create entity_name_matches link
                    cur.execute(
                        _INSERT_MATCH,
                        {
                            "source_name": donor_name,
                            "source_table": "donors",
                            "source_record_id": str(donor_id),
                            "business_entity_id": str(be_id),
                            "match_confidence": confidence,
                            "match_method": method,
                        },
                    )
                    stats["matches_created"] = int(stats["matches_created"]) + 1

                except Exception as e:
                    logger.error("apify_sos: DB write error for %s: %s", donor_name, e)
                    stats["errors"] = int(stats["errors"]) + 1

            # Commit after each batch so progress isn't lost on failure
            conn.commit()

    stats["api_usage_cost"] = format_cost_estimate(total_results)

    # Log usage (best-effort, don't fail the sync if this INSERT fails)
    try:
        with conn.cursor() as cur:
            cur.execute(
                _LOG_USAGE,
                {
                    "endpoint": "apify_sos/scrape",
                    "query_params": json.dumps({
                        "batch_size": _BATCH_SIZE,
                        "total_names": stats["records_fetched"],
                        "cost_estimate": stats["api_usage_cost"],
                        "actor": "parseforge/sos-scraper",
                    }),
                    "response_status": 200,
                    "called_at": now.isoformat(),
                },
            )
        conn.commit()
    except Exception:
        pass  # non-critical

    logger.info(
        "apify_sos: done — %s fetched, %s new, %s matched, %s errors. %s",
        stats["records_fetched"],
        stats["records_new"],
        stats["matches_created"],
        stats["errors"],
        stats["api_usage_cost"],
    )

    return dict(stats)


# ── CLI ────────────────────────────────────────────────────────

def main() -> None:
    """Standalone entry point for testing outside data_sync.py."""
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Lazy import — heavy, only needed when run directly
    import os
    import psycopg2
    import psycopg2.extras

    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set in .env")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    try:
        stats = sync_apify_entity_resolution(conn, "0660620", sync_type="full")
        print(json.dumps(stats, indent=2, default=str))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
