"""
db.journal — extracted from db.py (Phase 2.1).

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


# ── Pipeline Journal (Autonomy Zones Phase A) ────────────────


def write_journal_entry(
    conn,
    city_fips: str,
    session_id: uuid.UUID,
    entry_type: str,
    description: str,
    zone: str = "observation",
    target_artifact: str = None,
    metrics: dict = None,
) -> uuid.UUID:
    """Write one row to pipeline_journal. Returns entry UUID.

    This is the low-level writer. Prefer PipelineJournal class for
    instrumentation (handles non-fatal behavior and session grouping).
    """
    entry_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO pipeline_journal
               (id, city_fips, session_id, entry_type, zone,
                target_artifact, description, metrics)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                entry_id, city_fips, session_id, entry_type, zone,
                target_artifact, description, json.dumps(metrics or {}),
            ),
        )
    conn.commit()
    return entry_id


def get_journal_entries(
    conn,
    city_fips: str,
    days: int = 7,
    entry_types: list[str] = None,
    limit: int = 200,
) -> list[dict]:
    """Read recent journal entries, newest first.

    Used by the self-assessment module to gather pipeline telemetry.
    """
    query = """
        SELECT id, city_fips, session_id, entry_type, zone,
               target_artifact, description, metrics, created_at
        FROM pipeline_journal
        WHERE city_fips = %s
          AND created_at >= NOW() - INTERVAL '%s days'
    """
    params: list = [city_fips, days]

    if entry_types:
        placeholders = ", ".join(["%s"] * len(entry_types))
        query += f" AND entry_type IN ({placeholders})"
        params.extend(entry_types)

    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)

    with conn.cursor() as cur:
        cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

    return [
        {col: (str(val) if isinstance(val, uuid.UUID) else val)
         for col, val in zip(columns, row)}
        for row in rows
    ]


def get_recent_step_metrics(
    conn,
    city_fips: str,
    step_name: str,
    metric_key: str = None,
    limit: int = 10,
) -> list[dict]:
    """Get metrics from recent step_completed entries for anomaly detection.

    If metric_key is provided, returns only that key's values from each
    entry's metrics JSONB. Otherwise returns full metrics dicts.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT metrics, created_at
               FROM pipeline_journal
               WHERE city_fips = %s
                 AND target_artifact = %s
                 AND entry_type = 'step_completed'
               ORDER BY created_at DESC
               LIMIT %s""",
            (city_fips, step_name, limit),
        )
        rows = cur.fetchall()

    results = []
    for metrics_json, created_at in rows:
        m = metrics_json if isinstance(metrics_json, dict) else {}
        if metric_key:
            results.append({"value": m.get(metric_key), "created_at": created_at})
        else:
            results.append({"metrics": m, "created_at": created_at})
    return results
