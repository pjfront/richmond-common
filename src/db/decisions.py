"""
db.decisions — extracted from db.py (Phase 2.1).

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


# ── Decision Queue (S7) ─────────────────────────────────────


def insert_pending_decision(
    conn,
    city_fips: str,
    decision_type: str,
    severity: str,
    title: str,
    description: str,
    source: str,
    evidence: dict = None,
    entity_type: str = None,
    entity_id: str = None,
    link: str = None,
    dedup_key: str = None,
    review_class: str = "engineering",
    action_kind: str = "resolve_only",
    target_brief_id: str = None,
    target_content_version: int = None,
) -> Optional[uuid.UUID]:
    """Insert a pending decision. Returns UUID, or None if deduplicated.

    If dedup_key is set and a pending decision with that key already exists,
    the partial unique index prevents insertion and this returns None.
    """
    decision_id = uuid.uuid4()
    try:
        with conn.cursor() as cur:
            if dedup_key:
                cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (dedup_key,))
                cur.execute(
                    "SELECT id FROM pending_decisions WHERE dedup_key = %s AND status IN ('pending', 'deferred') LIMIT 1",
                    (dedup_key,),
                )
                if cur.fetchone():
                    conn.commit()
                    return None
            cur.execute(
                """INSERT INTO pending_decisions
                   (id, city_fips, decision_type, severity, title, description,
                    evidence, source, entity_type, entity_id, link, dedup_key,
                    review_class, action_kind, target_brief_id, target_content_version)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    decision_id, city_fips, decision_type, severity,
                    title, description, json.dumps(evidence or {}),
                    source, entity_type, entity_id, link, dedup_key,
                    review_class, action_kind, target_brief_id, target_content_version,
                ),
            )
        conn.commit()
        return decision_id
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return None


def update_decision_status(
    conn,
    decision_id: uuid.UUID,
    status: str,
    resolved_by: str = "operator",
    resolution_note: str = None,
    expected_version: int = None,
    idempotency_key: str | uuid.UUID = None,
) -> bool:
    """Apply the same audited, optimistic transition as the operator website.

    Legacy generic resolutions can read their current version immediately
    before applying. Publishing always requires an explicitly reviewed version.
    Callers retrying an uncertain request must reuse their idempotency key.
    """
    action = {"approved": "approve", "rejected": "reject", "deferred": "defer", "pending": "reopen"}.get(status)
    if action is None:
        raise ValueError(f"Unsupported review status: {status}")
    try:
        with conn.cursor() as cur:
            if expected_version is None:
                cur.execute("SELECT review_version, action_kind FROM pending_decisions WHERE id = %s", (decision_id,))
                row = cur.fetchone()
                if not row:
                    conn.commit()
                    return False
                if row[1] != "resolve_only":
                    raise ValueError("Publication decisions require an explicitly reviewed expected_version")
                expected_version = row[0]
            cur.execute(
                "SELECT public.review_decision(%s, %s, %s, %s, %s, %s)",
                (decision_id, action, expected_version, str(idempotency_key or uuid.uuid4()), resolution_note, resolved_by),
            )
            result = cur.fetchone()[0]
        conn.commit()
        return bool(result.get("ok"))
    except Exception:
        conn.rollback()
        raise


def query_pending_decisions(
    conn,
    city_fips: str,
    decision_type: str = None,
    severity: str = None,
) -> list[dict]:
    """Query pending decisions, ordered by severity rank then age.

    Severity order: critical > high > medium > low > info.
    Within each severity, oldest first (so nothing gets buried).
    """
    query = """
        SELECT id, city_fips, decision_type, severity, title, description,
               evidence, source, entity_type, entity_id, link, dedup_key,
               status, created_at, updated_at
        FROM pending_decisions
        WHERE city_fips = %s AND status = 'pending'
    """
    params: list = [city_fips]

    if decision_type:
        query += " AND decision_type = %s"
        params.append(decision_type)

    if severity:
        query += " AND severity = %s"
        params.append(severity)

    query += """
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'low' THEN 4
                WHEN 'info' THEN 5
                ELSE 6
            END,
            created_at ASC
    """

    with conn.cursor() as cur:
        cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

    return [
        {col: (str(val) if isinstance(val, uuid.UUID) else val)
         for col, val in zip(columns, row)}
        for row in rows
    ]


def query_resolved_decisions(
    conn,
    city_fips: str,
    days: int = 7,
    limit: int = 20,
) -> list[dict]:
    """Query recently resolved decisions, newest first."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, city_fips, decision_type, severity, title, description,
                      evidence, source, entity_type, entity_id, link, dedup_key,
                      status, resolved_at, resolved_by, resolution_note,
                      created_at, updated_at
               FROM pending_decisions
               WHERE city_fips = %s AND status != 'pending'
                 AND resolved_at >= NOW() - INTERVAL '%s days'
               ORDER BY resolved_at DESC
               LIMIT %s""",
            (city_fips, days, limit),
        )
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

    return [
        {col: (str(val) if isinstance(val, uuid.UUID) else val)
         for col, val in zip(columns, row)}
        for row in rows
    ]


def count_decisions_by_severity(
    conn,
    city_fips: str,
) -> dict[str, int]:
    """Count pending decisions grouped by severity."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT severity, COUNT(*) as cnt
               FROM pending_decisions
               WHERE city_fips = %s AND status = 'pending'
               GROUP BY severity""",
            (city_fips,),
        )
        rows = cur.fetchall()

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for severity, cnt in rows:
        counts[severity] = cnt
    return counts
