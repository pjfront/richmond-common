"""
db.expenditures — extracted from db.py (Phase 2.1).

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
from .contributions import _parse_contribution_date


# ── Independent Expenditures (CAL-ACCESS EXPN_CD) ────────────────

def load_expenditures_to_db(
    conn,
    records: list[dict],
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Load independent expenditure records into independent_expenditures table.

    These connect PAC money to specific candidates (support/oppose).
    Follows same pattern as load_contributions_to_db.

    Returns summary dict with counts.
    """
    stats = {"loaded": 0, "skipped": 0}

    with conn.cursor() as cur:
        for record in records:
            committee = (record.get("committee") or "").strip()
            amount = record.get("amount")
            date_str = record.get("date", "")

            if not committee or amount is None:
                stats["skipped"] += 1
                continue

            exp_date = _parse_contribution_date(date_str)

            cur.execute(
                """INSERT INTO independent_expenditures
                   (city_fips, committee_name, candidate_name, support_or_oppose,
                    amount, expenditure_date, description, expenditure_code,
                    payee_name, filing_id, source)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (city_fips,
                 committee,
                 (record.get("candidate_name") or "").strip() or None,
                 (record.get("support_or_oppose") or "").strip() or None,
                 amount,
                 exp_date,
                 (record.get("expenditure_description") or "").strip() or None,
                 (record.get("expenditure_code") or "").strip() or None,
                 (record.get("payee_name") or "").strip() or None,
                 record.get("filing_id", ""),
                 "calaccess"),
            )
            stats["loaded"] += 1

            if stats["loaded"] % 1000 == 0:
                conn.commit()

    conn.commit()
    return stats
