"""
netfile pipeline module — extracted from data_sync.py (Phase 2.3).

Each sync_X function is registered in data_sync.SYNC_SOURCES and dispatched
by data_sync.run_sync. Module-level helpers (netfile-specific) live alongside.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import psycopg2

from city_config import get_city_config, list_configured_cities
from db import (
    get_connection,
    create_sync_log,
    complete_sync_log,
    load_contributions_to_db,
    load_expenditures_to_db,
)
from pipeline_journal import PipelineJournal, check_anomalies

DEFAULT_FIPS = "0660620"


def sync_netfile(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync contributions from NetFile Connect2 API to Supabase.

    Fetches both electronically-filed transactions (via Connect2 API) and
    paper-filed contributions (via JSON data files extracted from PDFs
    downloaded from the NetFile public portal).

    For incremental syncs, checks for new contributions since the last sync.
    For full syncs, downloads all contributions.
    """
    from netfile_client import (
        fetch_all_transactions,
        normalize_transaction,
        deduplicate_contributions,
    )

    # ── Electronic filings (Connect2 API) ──
    # F460A=0 monetary, F460C=1 non-monetary, F497P1=20 / F497P2=21 late
    # (24-hour reports — required visibility during the final 90 days before
    # an election). Types 20/21 are intermittently 500 from NetFile, so wrap
    # the whole-type fetch in exponential backoff (2/4/8/16s) and on terminal
    # failure log + continue so a flaky late-contribution type never blocks
    # the rest of the sync.
    CONTRIBUTION_TYPES = [0, 1, 20, 21]

    print("  Fetching e-filed contributions from NetFile API...")
    all_transactions = []
    for type_id in CONTRIBUTION_TYPES:
        for attempt in range(4):
            try:
                all_transactions.extend(fetch_all_transactions(transaction_type=type_id))
                break
            except Exception as exc:
                if attempt == 3:
                    print(f"  WARNING: type {type_id} failed after 4 attempts ({exc}) — continuing")
                    break
                wait = 2 ** (attempt + 1)
                print(f"  type {type_id} failed ({exc}) — retry {attempt + 1}/3 in {wait}s")
                time.sleep(wait)

    # Normalize and deduplicate (same pipeline as netfile_client.py main)
    contributions = [normalize_transaction(tx) for tx in all_transactions]
    contributions = deduplicate_contributions(contributions)
    contributions = [c for c in contributions if c["amount"] != 0]
    print(f"  Fetched {len(contributions):,} e-filed contribution records")

    # ── Paper-filing PDF auto-extraction ──
    # Refresh src/data/paper_filings/*.json from the latest PDFs before the
    # JSON-load loop below picks them up. Reuses the contributions we just
    # normalized so the extractor doesn't re-pull the transaction feed.
    # Soft-fail: a broken extractor never blocks the sync — the JSON-load
    # loop falls back to whatever's already on disk.
    try:
        from netfile_paper_extractor import auto_extract_paper_filings

        ext_summary = auto_extract_paper_filings(transactions=contributions)
        if ext_summary["committees_extracted"]:
            print(
                f"  paper-extractor: refreshed {ext_summary['committees_extracted']} "
                f"committee(s), +{ext_summary['contributions_added']} contribution(s)"
            )
    except Exception as exc:
        print(f"  paper-extractor: skipped ({exc}) — using cached JSONs")

    # ── Paper filings (JSON data files from PDF extraction) ──
    paper_dir = Path(__file__).parent / "data" / "paper_filings"
    paper_count = 0
    if paper_dir.exists():
        import json as _json
        for json_file in sorted(paper_dir.glob("*.json")):
            with open(json_file, encoding="utf-8") as f:
                data = _json.load(f)
            committee = data.get("committee", "")
            fppc_id = data.get("fppc_id", "")
            for c in data.get("contributions", []):
                contributions.append({
                    "contributor_name": c.get("contributor_name", ""),
                    "contributor_employer": c.get("contributor_employer", ""),
                    "amount": c.get("amount", 0),
                    "date": c.get("date", ""),
                    "committee": committee,
                    "occupation": c.get("occupation", ""),
                    "source": "fppc_paper",
                    "filing_id": c.get("filing_id", ""),
                    "filer_fppc_id": fppc_id,
                    "entity_code": c.get("entity_code", "IND"),
                })
                paper_count += 1
        if paper_count:
            print(f"  Added {paper_count} paper-filed contributions from {len(list(paper_dir.glob('*.json')))} filing(s)")

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



def sync_donor_employer_merge(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Collapse same-name donor rows whose employer strings are near-equivalent.

    Wraps merge_donor_employers's rule engine into the SYNC_SOURCES
    enrichment contract so it auto-fires after every netfile sync via
    `data_sync --enrich`. Without this hook, fresh contributions
    accumulate employer-key fragmentation (e.g. "Buffy Wicks" at
    "California" + "California State Assembly") until a human runs
    the CLI manually.

    Three rules apply per `(city_fips, normalized_name)` cluster:
      Rule 1 (all-empty): every employer is in EMPTY_EQUIVALENTS
                          (NULL/N/A/None/Not employed/retired/...) —
                          collapse into a single keeper row.
      Rule 2 (empty + specific): empty rows merge into the specific row.
      Rule 3 (substring-of): one normalized employer is a >=4-char
                             substring or word-subset of another.

    Reads from `donors` and `contributions`. Writes only the rows that
    need to change. Idempotent — re-running on a clean DB is a no-op.
    """
    from merge_donor_employers import _is_empty_eq, _plan_cluster

    stats = {
        "records_fetched": 0,
        "records_new": 0,
        "records_updated": 0,
        "donors_merged": 0,
        "contributions_repointed": 0,
        "duplicate_contribs_dropped": 0,
    }

    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, name, normalized_name, employer
                 FROM donors
                WHERE city_fips = %s
                ORDER BY normalized_name, id""",
            (city_fips,),
        )
        all_rows = [
            {"id": str(r[0]), "name": r[1], "normalized_name": r[2], "employer": r[3]}
            for r in cur.fetchall()
        ]
        stats["records_fetched"] = len(all_rows)

        clusters: dict[str, list[dict]] = {}
        for r in all_rows:
            clusters.setdefault(r["normalized_name"], []).append(r)

        full_plan: list[tuple[str, str, str]] = []
        for rows in clusters.values():
            if len(rows) < 2:
                continue
            for drop_id, keep_id, reason in _plan_cluster(rows):
                full_plan.append((drop_id, keep_id, reason))

        if not full_plan:
            stats["note"] = "no employer-key fragmentation found"
            return stats

        for drop_id, keep_id, _reason in full_plan:
            # Promote employer onto keeper if keeper is empty-eq and drop isn't.
            cur.execute("SELECT employer FROM donors WHERE id = %s", (keep_id,))
            keep_emp = (cur.fetchone() or [None])[0]
            cur.execute("SELECT employer, occupation FROM donors WHERE id = %s", (drop_id,))
            drop_row = cur.fetchone() or (None, None)
            drop_emp, drop_occ = drop_row
            if _is_empty_eq(keep_emp) and not _is_empty_eq(drop_emp):
                cur.execute(
                    "UPDATE donors SET employer = %s WHERE id = %s",
                    (drop_emp, keep_id),
                )
            if drop_occ:
                cur.execute(
                    "UPDATE donors SET occupation = COALESCE(occupation, %s) WHERE id = %s",
                    (drop_occ, keep_id),
                )

            cur.execute(
                """SELECT id, amount, contribution_date, committee_id
                     FROM contributions WHERE donor_id = %s""",
                (drop_id,),
            )
            for cid, amount, cdate, comm_id in cur.fetchall():
                cur.execute(
                    """SELECT id FROM contributions
                        WHERE donor_id = %s AND amount = %s
                          AND contribution_date = %s
                          AND committee_id IS NOT DISTINCT FROM %s
                          AND id <> %s""",
                    (keep_id, amount, cdate, comm_id, cid),
                )
                if cur.fetchone():
                    cur.execute("DELETE FROM contributions WHERE id = %s", (cid,))
                    stats["duplicate_contribs_dropped"] += 1
                else:
                    cur.execute(
                        "UPDATE contributions SET donor_id = %s WHERE id = %s",
                        (keep_id, cid),
                    )
                    stats["contributions_repointed"] += 1

            cur.execute(
                "UPDATE entity_links SET donor_id = %s WHERE donor_id = %s",
                (keep_id, drop_id),
            )
            cur.execute("DELETE FROM donors WHERE id = %s", (drop_id,))
            stats["donors_merged"] += 1

    stats["records_updated"] = stats["donors_merged"]
    return stats


def sync_paper_filing_reconciliation(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Synthesize Form 460 cover-total reconciliation rows.

    For every Form 460 paper filing whose form_summary block is present,
    compute (form_total_this_period - DB_total_in_period) and insert a
    single synthetic row with the gap as `Unitemized contributions`.
    This makes DB cycle totals match the candidate's own legal claim on
    Form 460 cover Line 5 — the canonical ground truth.

    Runs AFTER donor_employer_merge and donor_dedup so the DB period
    total reflects post-cleanup state. Idempotent: existing UNI rows
    are deleted and re-inserted with current correct amounts.

    See load_paper_filings.reconcile_paper_filings_to_forms for the
    actual reconciliation logic.
    """
    from load_paper_filings import (
        discover_and_extract_all_form460_summaries,
        reconcile_paper_filings_to_forms,
    )

    # Refresh the form-summary cache from RSS (cheap — only extracts
    # new filing_ids; cached ones are skipped). This generalizes the
    # reconciliation beyond paper-only filers to ANY committee that
    # files a Form 460.
    discover_and_extract_all_form460_summaries()

    inner = reconcile_paper_filings_to_forms(conn, city_fips=city_fips)
    return {
        "records_fetched": inner["filings_examined"],
        "records_new": inner["rows_synthesized"],
        "records_updated": 0,
        "dollars_synthesized": inner["dollars_synthesized"],
        "filings_already_matched": inner["filings_already_matched"],
        "filings_over_form": inner["filings_over"],
        "over_filings_detail": inner.get("over_filings", []),
    }


def sync_donor_dedup(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Drop cross-filing duplicate contributions.

    Wraps dedup_contributions into the SYNC_SOURCES enrichment contract.
    Catches the "same gift filed twice" pattern: California Form 497
    is filed by both donor (Part 2) and recipient (Part 1), producing
    two near-date contribution rows that slip past the standard
    (donor_id, amount, contribution_date, committee_id) ON CONFLICT key.

    Pairs detected by ±14-day window. Keeper is the EARLIER-dated row
    (closer to the actual transaction; see dedup_contributions._choose_keeper
    for the full rationale).

    Should run AFTER sync_donor_employer_merge — collapsing donor rows
    first lets cross-filing pairs match by donor_id.
    """
    from dedup_contributions import find_cross_filing_duplicates

    stats = {
        "records_fetched": 0,
        "records_new": 0,
        "records_updated": 0,
        "duplicates_dropped": 0,
        "dollars_dropped": 0.0,
    }

    pairs = find_cross_filing_duplicates(conn, city_fips=city_fips)
    stats["records_fetched"] = len(pairs)

    if not pairs:
        stats["note"] = "no cross-filing duplicates"
        return stats

    with conn.cursor() as cur:
        for p in pairs:
            cur.execute("DELETE FROM contributions WHERE id = %s", (p["drop_id"],))
            stats["duplicates_dropped"] += 1
            stats["dollars_dropped"] += float(p["amount"])

    stats["records_updated"] = stats["duplicates_dropped"]
    return stats


