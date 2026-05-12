"""
db.sync_logs — extracted from db.py (Phase 2.1).

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


# ── Data Sync Log ───────────────────────────────────────────

def cleanup_stale_sync_logs(conn, max_age_hours: int = 1) -> int:
    """Mark any data_sync_log rows stuck in status='running' older than
    max_age_hours as 'failed'. Self-heals the orphan-row pattern where
    a sync process dies before writing its completion update.

    The longest legitimate sync (NetFile first run) takes ~18 minutes,
    so 1 hour is generous. Called automatically from create_sync_log()
    so every sync startup cleans up prior orphans.

    Returns the count of rows cleaned up.
    """
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE data_sync_log
               SET status = 'failed',
                   completed_at = NOW(),
                   error_message = COALESCE(
                     error_message,
                     'Process died before status update; auto-cleaned by next sync startup'
                   )
               WHERE status = 'running'
                 AND started_at < NOW() - (%s || ' hours')::INTERVAL
               RETURNING id""",
            (str(max_age_hours),),
        )
        rows = cur.fetchall()
    if rows:
        conn.commit()
        print(f"  [sync_log] Auto-cleaned {len(rows)} stale 'running' rows (>{max_age_hours}h old)")
    return len(rows)


def create_sync_log(
    conn,
    city_fips: str,
    source: str,
    sync_type: str = "incremental",
    triggered_by: str = "manual",
    pipeline_run_id: str = None,
) -> uuid.UUID:
    """Create a data_sync_log row at the start of a sync.

    Returns the log UUID. Update with complete_sync_log() when done.
    Auto-cleans any orphan 'running' rows older than 1 hour as a side
    effect, so a process that died before writing its completion update
    self-heals on the next sync startup.
    """
    cleanup_stale_sync_logs(conn)
    log_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO data_sync_log
               (id, city_fips, source, sync_type, triggered_by, pipeline_run_id, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'running')""",
            (log_id, city_fips, source, sync_type, triggered_by, pipeline_run_id),
        )
    conn.commit()
    return log_id


def complete_sync_log(
    conn,
    sync_log_id: uuid.UUID,
    records_fetched: int = None,
    records_new: int = None,
    records_updated: int = None,
    error_message: str = None,
    metadata: dict = None,
) -> None:
    """Mark a sync log entry as completed (or failed)."""
    status = "failed" if error_message else "completed"
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE data_sync_log
               SET records_fetched = %s, records_new = %s, records_updated = %s,
                   status = %s, error_message = %s, metadata = %s,
                   completed_at = NOW()
               WHERE id = %s""",
            (
                records_fetched, records_new, records_updated,
                status, error_message, json.dumps(metadata or {}),
                sync_log_id,
            ),
        )
    conn.commit()
