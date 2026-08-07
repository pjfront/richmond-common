"""Durable source-change event coordination.

The detector owns delivery attempts; ``data_sync`` owns the worker lease and
phase transitions.  Source-phase history remains in ``data_sync_log`` while
``source_change_jobs`` is the authority for end-to-end event completion.
"""
from __future__ import annotations

from typing import Any

import psycopg2.extras


def _rpc_row(conn, sql: str, params: tuple[Any, ...]) -> dict | None:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    conn.commit()
    return dict(row) if row else None


def claim_source_change_job(
    conn,
    *,
    change_id: str,
    source: str,
    dispatch_generation: int,
    pipeline_run_id: str | None = None,
    lease_minutes: int = 420,
) -> dict | None:
    """Claim one delivered event, or return ``None`` for an active/terminal duplicate."""
    return _rpc_row(
        conn,
        """SELECT * FROM claim_source_change_job(%s, %s, %s, %s, %s)""",
        (
            change_id,
            source,
            dispatch_generation,
            pipeline_run_id,
            lease_minutes,
        ),
    )


def get_source_change_job(conn, *, change_id: str) -> dict | None:
    """Read an event row without changing its state."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT * FROM source_change_jobs WHERE change_id = %s""",
            (change_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def mark_source_change_base_completed(
    conn,
    *,
    change_id: str,
    pipeline_run_id: str,
    dispatch_generation: int,
) -> dict | None:
    """Record that retries can resume at downstream enrichment."""
    return _rpc_row(
        conn,
        """SELECT * FROM mark_source_change_base_completed(%s, %s, %s)""",
        (change_id, pipeline_run_id, dispatch_generation),
    )


def retry_source_change_job(
    conn,
    *,
    change_id: str,
    error: str,
    dispatch_generation: int,
    pipeline_run_id: str | None = None,
) -> dict | None:
    """Release a failed worker to bounded backoff, or dead-letter it."""
    return _rpc_row(
        conn,
        """SELECT * FROM retry_source_change_job(%s, %s, %s, %s)""",
        (change_id, error, dispatch_generation, pipeline_run_id),
    )


def continue_source_change_job(
    conn,
    *,
    change_id: str,
    pipeline_run_id: str,
    dispatch_generation: int,
    delay_seconds: int = 60,
) -> dict | None:
    """Release a healthy bounded slice without spending a failure attempt."""
    return _rpc_row(
        conn,
        """SELECT * FROM continue_source_change_job(%s, %s, %s, %s)""",
        (change_id, pipeline_run_id, dispatch_generation, delay_seconds),
    )


def complete_source_change_job(
    conn,
    *,
    change_id: str,
    pipeline_run_id: str,
    dispatch_generation: int,
) -> dict | None:
    """Mark an event succeeded after its base and enrichment phases."""
    return _rpc_row(
        conn,
        """SELECT * FROM complete_source_change_job(%s, %s, %s)""",
        (change_id, pipeline_run_id, dispatch_generation),
    )


def get_change_sync_log(
    conn,
    *,
    city_fips: str,
    source: str,
    change_id: str,
) -> dict | None:
    """Read the source-phase log when recovering a crash between phase acks."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT status, metadata, error_message
               FROM data_sync_log
               WHERE city_fips = %s AND source = %s AND change_id = %s""",
            (city_fips, source, change_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None
