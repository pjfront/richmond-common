"""
db.scan_runs — extracted from db.py (Phase 2.1).

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


# ── Scan Runs (Cloud Pipeline) ───────────────────────────────

def create_scan_run(
    conn,
    city_fips: str,
    meeting_id: uuid.UUID = None,
    scan_mode: str = "prospective",
    data_cutoff_date: date = None,
    contributions_count: int = None,
    contributions_sources: dict = None,
    form700_count: int = None,
    triggered_by: str = "manual",
    pipeline_run_id: str = None,
    scanner_version: str = None,
) -> uuid.UUID:
    """Create a scan_runs row at the start of a pipeline execution.

    Returns the scan_run UUID. Update with complete_scan_run() when done.
    """
    run_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO scan_runs
               (id, city_fips, meeting_id, scan_mode, data_cutoff_date,
                contributions_count, contributions_sources, form700_count,
                triggered_by, pipeline_run_id, scanner_version, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'running')""",
            (
                run_id, city_fips, meeting_id, scan_mode, data_cutoff_date,
                contributions_count, json.dumps(contributions_sources or {}),
                form700_count, triggered_by, pipeline_run_id, scanner_version,
            ),
        )
    conn.commit()
    return run_id


def complete_scan_run(
    conn,
    scan_run_id: uuid.UUID,
    flags_found: int,
    flags_by_tier: dict,
    clean_items_count: int,
    enriched_items_count: int = None,
    execution_time_seconds: float = None,
    metadata: dict = None,
    error_message: str = None,
) -> None:
    """Mark a scan_run as completed (or failed) with results."""
    status = "failed" if error_message else "completed"
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE scan_runs
               SET flags_found = %s, flags_by_tier = %s,
                   clean_items_count = %s, enriched_items_count = %s,
                   execution_time_seconds = %s, metadata = %s,
                   status = %s, error_message = %s,
                   completed_at = NOW()
               WHERE id = %s""",
            (
                flags_found, json.dumps(flags_by_tier or {}),
                clean_items_count, enriched_items_count,
                execution_time_seconds, json.dumps(metadata or {}),
                status, error_message,
                scan_run_id,
            ),
        )
    conn.commit()


def fail_scan_run(conn, scan_run_id: uuid.UUID, error_message: str) -> None:
    """Mark a scan_run as failed."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE scan_runs
               SET status = 'failed', error_message = %s, completed_at = NOW()
               WHERE id = %s""",
            (error_message, scan_run_id),
        )
    conn.commit()
