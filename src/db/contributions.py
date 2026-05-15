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


def load_contributions_to_db(
    conn,
    records: list[dict],
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Load combined contribution records into donors, committees, and contributions tables.

    Handles both CAL-ACCESS and NetFile record formats.
    Returns summary dict with counts.
    """
    donor_cache: dict[str, uuid.UUID] = {}   # (normalized_name, employer) -> id
    committee_cache: dict[str, uuid.UUID] = {}  # normalized committee name -> id
    stats = {"donors": 0, "committees": 0, "contributions": 0, "skipped": 0}

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

            # ── Upsert donor ──
            norm_donor = _normalize_name(donor_name)
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
            filing_id_str = str(filing_id) if filing_id else None
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
                      OR contributions.contributor_type IS NULL""",
                (uuid.uuid4(), city_fips,
                 donor_cache[donor_key], committee_cache[norm_committee],
                 amount, contrib_date, contrib_type,
                 filing_id_str, source_label,
                 contributor_type, type_source, entity_code_raw),
            )
            stats["contributions"] += 1

            # Commit in batches to avoid huge transactions
            if stats["contributions"] % 1000 == 0:
                conn.commit()

    conn.commit()

    # Cross-filing dedup pass (I124 item 2). The standard ON CONFLICT
    # key catches same-(donor, amount, date, committee) duplicates, but
    # the same legal contribution can appear under DIFFERENT filing_ids
    # with slightly-different dates when both the donor PAC and the
    # recipient committee file 497s. dedup_contributions handles that
    # case explicitly. Cheap (one query); idempotent.
    try:
        from dedup_contributions import apply_cross_filing_dedup
        dedup_stats = apply_cross_filing_dedup(conn, city_fips)
        if dedup_stats["dropped"]:
            stats["dedup_dropped"] = dedup_stats["dropped"]
    except Exception as exc:
        # Soft-fail — dedup is best-effort and a sync should not abort
        # because of it. Log and move on.
        print(f"[load_contributions_to_db] cross-filing dedup skipped: {exc}")

    return stats
