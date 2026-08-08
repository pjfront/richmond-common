"""
db.contributions — extracted from db.py (Phase 2.1).

Re-exported from `db` package for backwards compatibility.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

from ._core import RICHMOND_FIPS, sanitize_text
from .officials import _normalize_name


# ── Contribution Loading ─────────────────────────────────────

def _parse_contribution_date(date_str: str) -> Optional[date]:
    """Parse contribution date from either NetFile (ISO) or CAL-ACCESS format."""
    if not date_str:
        return None
    # ISO format: "2025-12-29"
    if "-" in date_str and len(date_str) >= 10:
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    # CAL-ACCESS format: "4/11/2001 12:00:00 AM"
    try:
        return datetime.strptime(date_str.split()[0], "%m/%d/%Y").date()
    except (ValueError, IndexError):
        pass
    return None


def _contribution_type_from_record(record: dict) -> str:
    """Map transaction_type or form_type to our contribution_type enum."""
    tx_type = record.get("transaction_type", "")
    if tx_type in ("F460A", "F497P1"):
        return "monetary"
    if tx_type == "F460C":
        return "nonmonetary"
    # CAL-ACCESS records without transaction_type
    form_type = record.get("form_type", "")
    if form_type == "F460":
        return "monetary"
    return "monetary"


def _should_skip_contribution_insert(
    natural_key: tuple,
    existing_contribs: dict,
    new_filing_id: str | None,
) -> bool:
    """Return True iff this contribution is unchanged vs what's already
    in the DB, and the INSERT...ON CONFLICT DO UPDATE WHERE clause would
    have made the update a no-op anyway.

    Without this gate, every netfile sync re-INSERTs all ~24K rows even
    when unchanged. The DO UPDATE WHERE clause prevents data changes but
    Postgres still counts each INSERT attempt as a write (lock, conflict
    check, WHERE evaluation) — burning Supabase write quota. This gate
    short-circuits before the INSERT statement runs.

    Args:
        natural_key: (normalized_donor, normalized_employer, amount,
            contribution_date, committee_name). Matches the keys we
            pre-fetched from the existing contributions table.
        existing_contribs: map from natural_key -> (filing_id,
            contributor_type), populated by the pre-fetch JOIN.
        new_filing_id: filing_id from the incoming record (string or
            None).

    Returns:
        True if INSERT can be safely skipped (row exists, no newer
        filing, type already classified). False if the row is new or
        would have caused a real update.

    The condition mirrors the DO UPDATE WHERE clause inside the
    contribution upsert. If you change one, change the other.
    """
    existing = existing_contribs.get(natural_key)
    if existing is None:
        return False  # new contribution; must insert
    existing_filing_id, existing_contributor_type = existing
    new_filing = new_filing_id or ""
    old_filing = existing_filing_id or ""
    has_newer_filing = new_filing > old_filing
    needs_classification = existing_contributor_type is None
    return not (has_newer_filing or needs_classification)


def load_contributions_to_db(
    conn,
    records: list[dict],
    city_fips: str = RICHMOND_FIPS,
    *,
    commit: bool = True,
) -> dict:
    """Load combined contribution records into donors, committees, and contributions tables.

    Handles both CAL-ACCESS and NetFile record formats.
    Returns summary dict with counts.
    """
    donor_cache: dict[str, uuid.UUID] = {}   # (normalized_name, employer) -> id
    committee_cache: dict[str, uuid.UUID] = {}  # normalized committee name -> id
    # Counter semantics (made strict 2026-05-16 after a misleading-counter incident):
    #   contributions  = rows ACTUALLY INSERTED as new (xmax = 0 on RETURNING)
    #   updated        = rows that existed and got DO UPDATE'd (filing_id newer
    #                    or contributor_type backfill)
    #   conflict_noop  = rows that hit ON CONFLICT but DO UPDATE WHERE was
    #                    false — no row touched. Distinct from "unchanged"
    #                    which is gate-skipped before the INSERT runs.
    #   unchanged      = rows the content-hash gate skipped (zero write cost)
    #   skipped        = malformed records (missing donor / amount / date)
    stats = {"donors": 0, "committees": 0, "contributions": 0,
             "updated": 0, "conflict_noop": 0, "unchanged": 0, "skipped": 0}

    # Canonical-donor map for collapsing OCR/alias drift on paper-filed
    # contributions. Applied uniformly to all sources because the cost
    # is one dict lookup per row and it prevents alias leakage from
    # NetFile API rows too. See src/prompts/canonical_donors.md.
    from canonical_donors import canonicalize_donor_name
    # Empty-employer normalization: collapse "n/a" / "None" / "Not
    # employed" / etc. to NULL at insert time so future syncs don't
    # reintroduce the employer-key fragmentation that I124 (4) cleaned
    # up. The donors natural key is (city_fips, normalized_name,
    # COALESCE(employer, '')) — without this, every empty-eq variant
    # creates a fresh donor row.
    from merge_donor_employers import _is_empty_eq

    # ── Content-hash gate pre-fetch (write-amplification fix) ──
    # Build a map of every existing contribution keyed on its natural
    # fields, so the main loop can skip INSERT attempts for unchanged
    # rows. The natural key (donor normalized_name + employer + amount
    # + date + committee name) matches what the incoming records will
    # have — donor_id/committee_id aren't known yet at pre-fetch time
    # since they're resolved inside the loop.
    #
    # One SELECT instead of 24K redundant INSERT attempts every sync.
    # See _should_skip_contribution_insert docstring for full rationale.
    existing_contribs: dict[tuple, tuple] = {}
    with conn.cursor() as cur:
        cur.execute(
            """SELECT
                 d.normalized_name,
                 COALESCE(d.employer, ''),
                 c.amount,
                 c.contribution_date,
                 cm.name,
                 c.filing_id,
                 c.contributor_type
               FROM contributions c
               JOIN donors d ON d.id = c.donor_id
               JOIN committees cm ON cm.id = c.committee_id
               WHERE c.city_fips = %s
                 AND c.contribution_date IS NOT NULL""",
            (city_fips,),
        )
        for row in cur.fetchall():
            key = (row[0], (row[1] or "").lower().strip(), row[2], row[3], row[4])
            existing_contribs[key] = (row[5], row[6])

    with conn.cursor() as cur:
        for record in records:
            # ── Extract fields (handle both formats) ──
            raw_donor_name = sanitize_text((record.get("contributor_name") or record.get("name") or "").strip())
            donor_name = canonicalize_donor_name(raw_donor_name)
            raw_employer = sanitize_text((record.get("contributor_employer") or record.get("employer") or "").strip())
            employer = "" if _is_empty_eq(raw_employer) else raw_employer
            occupation = sanitize_text((record.get("occupation") or record.get("contributor_occupation") or "").strip())
            amount = record.get("amount")
            date_str = record.get("date", "")
            committee_name = (record.get("committee") or record.get("filerName") or "").strip()
            source = record.get("source", "unknown")
            filing_id = record.get("filing_id", "")

            if not donor_name or amount is None or not committee_name:
                stats["skipped"] += 1
                continue

            contrib_date = _parse_contribution_date(date_str)
            if not contrib_date:
                stats["skipped"] += 1
                continue

            filing_id_str = str(filing_id) if filing_id else None
            norm_donor = _normalize_name(donor_name)

            # ── Content-hash gate ──
            # If this contribution already exists with the same natural
            # key and no meaningful change (no newer filing, type already
            # classified), skip the entire INSERT cycle: donor lookup,
            # committee lookup, classifier call, and contribution INSERT.
            # Mirrors the DO UPDATE WHERE clause semantics. See
            # _should_skip_contribution_insert for the rationale.
            #
            # Amount coerced to Decimal because Postgres returns NUMERIC
            # as Decimal but the incoming record may have it as float or
            # str. Without coercion, the dict lookup misses every match
            # and the gate becomes a no-op (write amplification returns).
            try:
                amount_key = Decimal(str(amount))
            except (InvalidOperation, ValueError):
                # Malformed amount — skip gate, let the INSERT path raise
                # the actual error visibly.
                amount_key = amount
            gate_key = (
                norm_donor,
                (employer or "").lower().strip(),
                amount_key,
                contrib_date,
                committee_name,
            )
            if _should_skip_contribution_insert(gate_key, existing_contribs, filing_id_str):
                stats["unchanged"] += 1
                continue

            # ── Upsert donor ──
            donor_key = (norm_donor, employer.lower().strip())
            if donor_key not in donor_cache:
                norm_employer = _normalize_name(employer) if employer else None
                cur.execute(
                    """SELECT id FROM donors
                       WHERE city_fips = %s AND normalized_name = %s
                         AND COALESCE(employer, '') = %s""",
                    (city_fips, norm_donor, employer or ""),
                )
                row = cur.fetchone()
                if row:
                    donor_cache[donor_key] = row[0]
                else:
                    donor_id = uuid.uuid4()
                    cur.execute(
                        """INSERT INTO donors
                           (id, city_fips, name, normalized_name, employer, normalized_employer, occupation)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (city_fips, normalized_name, COALESCE(employer, ''))
                           DO UPDATE SET occupation = COALESCE(EXCLUDED.occupation, donors.occupation)
                           RETURNING id""",
                        (donor_id, city_fips, donor_name, norm_donor,
                         employer or None, norm_employer, occupation or None),
                    )
                    donor_cache[donor_key] = cur.fetchone()[0]
                    stats["donors"] += 1

            # ── Upsert committee ──
            norm_committee = _normalize_name(committee_name)
            if norm_committee not in committee_cache:
                cur.execute(
                    "SELECT id FROM committees WHERE city_fips = %s AND name = %s",
                    (city_fips, committee_name),
                )
                row = cur.fetchone()
                if row:
                    committee_cache[norm_committee] = row[0]
                else:
                    committee_id = uuid.uuid4()
                    filer_id = record.get("filer_id") or record.get("filer_fppc_id") or ""
                    cur.execute(
                        """INSERT INTO committees
                           (id, city_fips, name, filer_id, committee_type, status)
                           VALUES (%s, %s, %s, %s, %s, 'active')
                           ON CONFLICT DO NOTHING
                           RETURNING id""",
                        (committee_id, city_fips, committee_name,
                         filer_id or None, "candidate" if source == "netfile" else "pac"),
                    )
                    result = cur.fetchone()
                    committee_cache[norm_committee] = result[0] if result else committee_id
                    stats["committees"] += 1

            # ── Classify contributor type ──
            from contributor_classifier import classify_contributor
            entity_code_raw = (record.get("entity_code") or "").strip() or None
            contributor_type, type_source = classify_contributor(
                name=donor_name,
                entity_code=entity_code_raw,
                source=source,
            )

            # ── Insert contribution (idempotent — skip if already exists) ──
            contrib_type = _contribution_type_from_record(record)
            source_label = "calaccess" if source == "calaccess" else "city_clerk"
            cur.execute(
                """INSERT INTO contributions
                   (id, city_fips, donor_id, committee_id, amount,
                    contribution_date, contribution_type, filing_id, source,
                    contributor_type, contributor_type_source, entity_code)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (donor_id, amount, contribution_date, committee_id)
                   WHERE contribution_date IS NOT NULL
                   DO UPDATE SET
                     filing_id = EXCLUDED.filing_id,
                     contributor_type = COALESCE(EXCLUDED.contributor_type, contributions.contributor_type),
                     contributor_type_source = COALESCE(EXCLUDED.contributor_type_source, contributions.contributor_type_source),
                     entity_code = COALESCE(EXCLUDED.entity_code, contributions.entity_code)
                   WHERE COALESCE(EXCLUDED.filing_id, '') > COALESCE(contributions.filing_id, '')
                      OR contributions.contributor_type IS NULL
                   RETURNING (xmax = 0) AS was_inserted""",
                (uuid.uuid4(), city_fips,
                 donor_cache[donor_key], committee_cache[norm_committee],
                 amount, contrib_date, contrib_type,
                 filing_id_str, source_label,
                 contributor_type, type_source, entity_code_raw),
            )
            # Distinguish actual insert / update / no-op:
            #   xmax = 0  → INSERT was the operation (brand-new row)
            #   xmax != 0 → DO UPDATE was the operation (existing row updated)
            #   no row    → ON CONFLICT triggered, DO UPDATE WHERE was false,
            #               nothing touched
            result = cur.fetchone()
            if result is None:
                stats["conflict_noop"] += 1
            elif result[0]:
                stats["contributions"] += 1
            else:
                stats["updated"] += 1

            # Commit in batches to avoid huge transactions. Sum all the
            # write-touching buckets so batch boundaries are based on actual
            # DB activity, not just the new-row count.
            total_writes = stats["contributions"] + stats["updated"] + stats["conflict_noop"]
            if commit and total_writes > 0 and total_writes % 1000 == 0:
                conn.commit()

    if commit:
        conn.commit()

    # Cross-filing dedup pass (I124 item 2). The standard ON CONFLICT
    # key catches same-(donor, amount, date, committee) duplicates, but
    # the same legal contribution can appear under DIFFERENT filing_ids
    # with slightly-different dates when both the donor PAC and the
    # recipient committee file 497s. dedup_contributions handles that
    # case explicitly. Cheap (one query); idempotent.
    try:
        if not commit:
            # Transaction-owning callers (notably Form 460 reconciliation)
            # must be able to replace derived rows atomically. The normal
            # loader path retains the historical post-load dedup behavior.
            return stats
        from dedup_contributions import apply_cross_filing_dedup
        dedup_stats = apply_cross_filing_dedup(conn, city_fips)
        if dedup_stats["dropped"]:
            stats["dedup_dropped"] = dedup_stats["dropped"]
    except Exception as exc:
        # Soft-fail — dedup is best-effort and a sync should not abort
        # because of it. Log and move on.
        print(f"[load_contributions_to_db] cross-filing dedup skipped: {exc}")

    return stats
