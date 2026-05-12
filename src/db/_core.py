"""
db._core — extracted from db.py (Phase 2.1).

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

from dotenv import load_dotenv

load_dotenv()
psycopg2.extras.register_uuid()

RICHMOND_FIPS = "0660620"


def sanitize_text(value: str | None) -> str | None:
    """Strip characters that PostgreSQL TEXT columns reject.

    PyMuPDF and other extractors can produce NUL bytes (\\x00) from
    corrupted fonts or binary-embedded data in government PDFs.
    PostgreSQL raises "A string literal cannot contain NUL (0x00)
    characters" on insert. Strip at the DB boundary so all callers
    are protected.
    """
    if value is None:
        return None
    return value.replace("\x00", "")


def get_connection():
    """Get a PostgreSQL connection from DATABASE_URL.

    TCP keepalives are enabled so connections survive long idle stretches —
    e.g., escribemeetings_minutes scans HTTP for ~14 minutes while holding
    the DB connection. Without keepalives, the Supabase pooler (or any NAT
    in between) silently drops the idle TCP connection, and the next query
    fails with "SSL SYSCALL error: EOF detected".
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL not set. Add it to .env or environment.\n"
            "Example: postgresql://user:pass@localhost:5432/richmond_transparency"
        )
    return psycopg2.connect(
        database_url,
        connect_timeout=15,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )


def is_connection_alive(conn) -> bool:
    """Return True if the connection is open and usable.

    Checks both the closed flag and runs a trivial round-trip — psycopg2 only
    notices a server-closed connection on the next operation, so SELECT 1 is
    the cheapest way to confirm liveness before reusing a long-idle handle.
    """
    if conn is None or getattr(conn, "closed", 1):
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        return False


def init_schema(conn, schema_path: str = None):
    """Run schema.sql to initialize the database."""
    if schema_path is None:
        schema_path = Path(__file__).parent / "schema.sql"
    sql = Path(schema_path).read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def run_migration(conn, migration_path: str) -> None:
    """Run a SQL migration file."""
    sql = Path(migration_path).read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
