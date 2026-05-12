"""
db.flags — extracted from db.py (Phase 2.1).

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

from ._core import RICHMOND_FIPS


# ── Conflict Flag Helpers (Cloud Pipeline) ──────────────────

def save_conflict_flag(
    conn,
    city_fips: str,
    meeting_id: uuid.UUID,
    scan_run_id: uuid.UUID,
    flag_type: str,
    description: str,
    evidence: list,
    confidence: float,
    scan_mode: str = None,
    data_cutoff_date: date = None,
    agenda_item_id: uuid.UUID = None,
    official_id: uuid.UUID = None,
    legal_reference: str = None,
    publication_tier: int = None,
    confidence_factors: dict = None,
    scanner_version: int = None,
    match_details: dict = None,
) -> uuid.UUID:
    """Insert a conflict_flag linked to a scan_run.

    v3 additions: confidence_factors (JSONB breakdown of composite scoring),
    scanner_version (2=monolithic, 3=signal-based), and match_details
    (structured metadata: donor_name, committee, amounts, etc.).
    """
    flag_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO conflict_flags
               (id, city_fips, meeting_id, agenda_item_id, official_id,
                flag_type, description, evidence, confidence, legal_reference,
                scan_run_id, scan_mode, data_cutoff_date, is_current,
                publication_tier, confidence_factors, scanner_version, match_details)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s)""",
            (
                flag_id, city_fips, meeting_id, agenda_item_id, official_id,
                flag_type, description, json.dumps(evidence),
                confidence, legal_reference,
                scan_run_id, scan_mode, data_cutoff_date,
                publication_tier,
                json.dumps(confidence_factors) if confidence_factors else None,
                scanner_version,
                json.dumps(match_details) if match_details else None,
            ),
        )
    conn.commit()
    return flag_id


def supersede_flags_for_meeting(
    conn,
    meeting_id: uuid.UUID,
    new_scan_run_id: uuid.UUID,
    scan_mode: str = "prospective",
) -> int:
    """Mark existing prospective flags as superseded by a new scan.

    Returns the number of flags superseded.
    """
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE conflict_flags
               SET is_current = FALSE
               WHERE meeting_id = %s AND scan_mode = %s AND is_current = TRUE
                 AND scan_run_id != %s""",
            (meeting_id, scan_mode, new_scan_run_id),
        )
        count = cur.rowcount
    conn.commit()
    return count
