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
    Idempotent: ON CONFLICT on the (city_fips, committee_name, payee_name,
    amount, expenditure_date, support_or_oppose, candidate_name) natural
    key (UNIQUE INDEX uq_independent_expenditures_natural_key, migration
    112). On conflict, refreshes mutable fields (description, expenditure_code,
    filing_id — latter retains the highest filing_id seen, matching the
    "most recent amendment wins" rule).

    Counter contract: returns inserted/updated/skipped from the DB's
    own RETURNING (xmax = 0) tally, never from "did execute succeed."
    Counter accuracy is verified by tests/test_calaccess_expenditures.py
    against a mocked cursor; integration coverage lives in the live
    sync run (the operator can SELECT COUNT(*) before+after to confirm).

    Pre-2026-05-16: this function had no ON CONFLICT and ran INSERT
    blind, growing the table by ~4,300 rows per monthly CAL-ACCESS sync.
    Fixed in Phase D-2 along with migration 112 which deduped existing
    rows and added the natural-key UNIQUE INDEX.

    Returns:
        Dict with keys: inserted, updated, skipped. Sum == len(records).
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0}

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
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (
                     city_fips, committee_name, (COALESCE(payee_name, '')),
                     amount, expenditure_date,
                     (COALESCE(support_or_oppose, '')),
                     (COALESCE(candidate_name, ''))
                   )
                   DO UPDATE SET
                     description = EXCLUDED.description,
                     expenditure_code = EXCLUDED.expenditure_code,
                     -- Keep the highest filing_id seen (matches migration
                     -- 102's "most recent amendment supersedes" rule).
                     filing_id = GREATEST(
                       independent_expenditures.filing_id,
                       EXCLUDED.filing_id
                     )
                   RETURNING (xmax = 0) AS inserted""",
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
            result = cur.fetchone()
            if result and result[0]:
                stats["inserted"] += 1
            else:
                stats["updated"] += 1

            # Commit periodically — large batches keep the transaction
            # bounded while still letting ON CONFLICT see prior rows
            # in this same load (committed-data only would miss them).
            if (stats["inserted"] + stats["updated"]) % 1000 == 0:
                conn.commit()

    conn.commit()
    return stats
