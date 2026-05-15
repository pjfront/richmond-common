"""
db.elections — extracted from db.py (Phase 2.1).

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


# ── Election Cycle Tracking (B.24) ──────────────────────────


def load_elections_to_db(
    conn,
    elections: list[dict],
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Upsert election records.

    Each record should have: election_date, election_type, election_name,
    jurisdiction, source, source_url (optional), notes (optional).

    Returns {inserted, updated, skipped}.
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0}

    with conn.cursor() as cur:
        for e in elections:
            election_date = e.get("election_date")
            election_type = e.get("election_type")
            if not election_date or not election_type:
                stats["skipped"] += 1
                continue

            cur.execute(
                """INSERT INTO elections
                   (city_fips, election_date, election_type, election_name,
                    jurisdiction, filing_deadline, source, source_url,
                    source_tier, notes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (city_fips, election_date, election_type)
                   DO UPDATE SET
                     election_name = COALESCE(EXCLUDED.election_name, elections.election_name),
                     jurisdiction = COALESCE(EXCLUDED.jurisdiction, elections.jurisdiction),
                     filing_deadline = COALESCE(EXCLUDED.filing_deadline, elections.filing_deadline),
                     source_url = COALESCE(EXCLUDED.source_url, elections.source_url),
                     notes = COALESCE(EXCLUDED.notes, elections.notes),
                     updated_at = NOW()
                   RETURNING (xmax = 0) AS is_insert""",
                (city_fips, election_date, election_type,
                 e.get("election_name"), e.get("jurisdiction"),
                 e.get("filing_deadline"), e.get("source", "manual"),
                 e.get("source_url"), e.get("source_tier", 1),
                 e.get("notes")),
            )
            row = cur.fetchone()
            if row and row[0]:
                stats["inserted"] += 1
            else:
                stats["updated"] += 1

    conn.commit()
    return stats


def load_election_candidates_to_db(
    conn,
    candidates: list[dict],
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Upsert election candidate records.

    Each record should have: election_id, candidate_name, office_sought,
    and optionally: official_id, fppc_id, committee_id, status, is_incumbent.

    Returns {inserted, updated, skipped, matched_officials}.
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0, "matched_officials": 0}

    with conn.cursor() as cur:
        for c in candidates:
            election_id = c.get("election_id")
            candidate_name = c.get("candidate_name", "").strip()
            office_sought = c.get("office_sought", "").strip()
            if not election_id or not candidate_name or not office_sought:
                stats["skipped"] += 1
                continue

            normalized = _normalize_name(candidate_name)
            official_id = c.get("official_id")

            cur.execute(
                """INSERT INTO election_candidates
                   (city_fips, election_id, official_id, candidate_name,
                    normalized_name, office_sought, party, fppc_id,
                    committee_id, status, is_incumbent, source, source_url)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (city_fips, election_id, normalized_name, office_sought)
                   DO UPDATE SET
                     official_id = COALESCE(EXCLUDED.official_id, election_candidates.official_id),
                     fppc_id = COALESCE(EXCLUDED.fppc_id, election_candidates.fppc_id),
                     committee_id = COALESCE(EXCLUDED.committee_id, election_candidates.committee_id),
                     status = COALESCE(EXCLUDED.status, election_candidates.status),
                     is_incumbent = EXCLUDED.is_incumbent,
                     updated_at = NOW()
                   RETURNING (xmax = 0) AS is_insert""",
                (city_fips, str(election_id),
                 str(official_id) if official_id else None,
                 candidate_name, normalized,
                 office_sought, c.get("party"),
                 c.get("fppc_id"), str(c["committee_id"]) if c.get("committee_id") else None,
                 c.get("status", "filed"),
                 c.get("is_incumbent", False),
                 c.get("source", "netfile"),
                 c.get("source_url")),
            )
            row = cur.fetchone()
            if row and row[0]:
                stats["inserted"] += 1
            else:
                stats["updated"] += 1

            if official_id:
                stats["matched_officials"] += 1

    conn.commit()
    return stats
